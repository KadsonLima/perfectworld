"""Comportamento dos bots: chat com IA + papel de cada classe."""
import json
import os
import random
import struct
import threading
import time
import urllib.request
from collections import deque

from client import (CHANNEL_LOCAL, CHANNEL_WORLD, CHAT_BROADCAST, CLASSES,
                    GAMEDATA_S2C, PRIVATE_CHAT, Client)
from protocol import Reader

ROLES = {
    0: "tanque: segura o aggro, provoca os mobs e protege o grupo",
    1: "dano mágico em área, frágil, adora explodir mobs à distância",
    2: "suporte e controle, usa espíritos e debuffs",
    3: "invocadora de pets, controle e dano contínuo",
    4: "tanque bruto que vira tigre, muita vida",
    5: "assassino furtivo, dano físico alto e crítico",
    6: "dano físico à distância, kite e velocidade",
    7: "curandeiro do grupo: cura, ressuscita e dá buffs",
    8: "arcano, ilusionista que controla e atordoa",
    9: "místico, invoca plantas e cura em área",
}

MODEL = os.environ.get("PWBOT_MODEL", "claude-haiku-5-5")


def ask_claude(system, history):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    body = json.dumps({"model": MODEL, "max_tokens": 120, "system": system,
                       "messages": history}).encode()
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", body, {
        "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return "".join(b.get("text", "") for b in data["content"]).strip()


FALLBACK = ["Opa! Bora upar junto?", "To aqui, precisando de algo?",
            "Hoje o drop tá bom hein", "Se precisar de ajuda é só chamar!"]


class Bot:
    def __init__(self, cfg, server, log):
        self.cfg = cfg
        self.log = log
        self.c = Client(server["host"], server["port"], cfg["login"], cfg["password"],
                        cfg.get("role"), log)
        self.history = {}            # interlocutor -> deque de mensagens
        self.last_reply = 0
        self.cooldown = cfg.get("reply_cooldown", 4)

    # ---------------------------------------------------------------- vida
    def start(self):
        self.c.connect()
        self.c.handlers.append(self.on_packet)
        threading.Thread(target=self.idle_loop, daemon=True).start()
        self.c.run()

    @property
    def name(self):
        return self.c.role["name"]

    @property
    def klass(self):
        return self.c.role["occupation"]

    def persona(self):
        return (f"Você é {self.name}, um personagem {CLASSES.get(self.klass)} nível "
                f"{self.c.role['level']} no MMORPG Perfect World, jogando num servidor privado "
                f"brasileiro. Seu papel: {ROLES.get(self.klass)}. {self.cfg.get('persona', '')} "
                "Responda como um jogador real no chat: português informal, curto (máx. 80 "
                "caracteres), sem emojis, sem dizer que é IA ou bot a menos que perguntem diretamente.")

    # ---------------------------------------------------------------- pacotes
    def on_packet(self, t, p):
        r = Reader(p)
        if t == CHAT_BROADCAST:
            channel, _emo = r.u8(), r.u8()
            src = r.i32()
            msg = r.ustr()
            if src == self.c.roleid or src <= 0:
                return
            self.on_chat(channel, None, src, msg)
        elif t == PRIVATE_CHAT:
            r.u8(); r.u8()
            src_name = r.ustr()
            src = r.i32()
            if src == self.c.roleid:
                return
            r.ustr(); r.i32()
            self.on_chat("whisper", src_name, src, r.ustr())
        elif t != GAMEDATA_S2C and self.c.dump_unknown:
            self.log.debug("pkt 0x%02x %s", t, p[:64].hex())

    def on_chat(self, channel, src_name, src, msg):
        mentioned = self.name.lower() in msg.lower()
        if channel != "whisper" and not mentioned and channel != CHANNEL_LOCAL:
            return
        if channel == CHANNEL_LOCAL and not mentioned and random.random() > self.cfg.get("chatty", 0.15):
            return
        if time.time() - self.last_reply < self.cooldown:
            return
        self.last_reply = time.time()
        self.log.info("[%s] %s: %s", channel, src_name or src, msg)
        if msg.strip().startswith("!"):
            reply = self.command(msg.strip())
        else:
            h = self.history.setdefault(src, deque(maxlen=10))
            h.append({"role": "user", "content": msg})
            try:
                reply = ask_claude(self.persona(), list(h)) or random.choice(FALLBACK)
            except Exception as e:
                self.log.warning("IA falhou: %s", e)
                reply = random.choice(FALLBACK)
            h.append({"role": "assistant", "content": reply})
        if not reply:
            return
        time.sleep(min(1 + len(reply) * 0.05, 5))      # "digitando"
        if channel == "whisper":
            self.c.whisper(src_name, reply)
        else:
            self.c.say(reply, CHANNEL_LOCAL)

    def command(self, cmd):
        if cmd == "!ajuda":
            return "Comandos: !classe, !nivel, !ajuda"
        if cmd == "!classe":
            return f"Sou {CLASSES.get(self.klass)}, {ROLES.get(self.klass)}"
        if cmd == "!nivel":
            return f"Nível {self.c.role['level']}"
        return None

    # ---------------------------------------------------------------- papel
    def idle_loop(self):
        """Ações periódicas da classe. Skills configuradas em bots.json (skill ids do servidor)."""
        buffs = self.cfg.get("self_buffs", [])
        talk = self.cfg.get("ambient_lines", [])
        while self.c.running:
            time.sleep(self.cfg.get("buff_interval", 60))
            for skill in buffs:
                self.cast(skill, [self.c.roleid])
                time.sleep(2)
            if talk and random.random() < 0.2:
                self.c.say(random.choice(talk), CHANNEL_LOCAL)

    def cast(self, skill_id, targets):
        # C2S 0x29 CastSkill: skillid, force, count, targets (LE)
        body = struct.pack("<iBB", skill_id, 0, len(targets)) + b"".join(
            struct.pack("<i", t) for t in targets)
        self.c.send_gamedata(0x29, body)
