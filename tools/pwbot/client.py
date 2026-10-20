"""Cliente headless PW 1.5.5: login -> rolelist -> selectrole -> enterworld."""
import hashlib
import logging
import os
import struct
import threading
import time

from protocol import Link, Reader, hmac_md5, octets, ustr

# Protocolo externo (big-endian)
SERVER_INFO = 0x01
KEY_EXCHANGE = 0x02
LOGIN_ANNOUNCE = 0x03
ONLINE_ANNOUNCE = 0x04
ERROR_INFO = 0x05
GAMEDATA_S2C = 0x00
GAMEDATA_C2S = 0x22
SELECT_ROLE = 0x46
SELECT_ROLE_RE = 0x47
ENTER_WORLD = 0x48
PUBLIC_CHAT = 0x4F
CHAT_BROADCAST = 0x50
ROLE_LIST = 0x52
ROLE_LIST_RE = 0x53
KEEP_ALIVE = 0x5A
PRIVATE_CHAT = 0x60

CHANNEL_LOCAL, CHANNEL_WORLD, CHANNEL_TEAM, CHANNEL_GUILD = 0, 1, 2, 3

CLASSES = {0: "Guerreiro", 1: "Mago", 2: "Espiritualista", 3: "Feiticeira",
           4: "Bárbaro", 5: "Mercenário", 6: "Arqueiro", 7: "Sacerdote",
           8: "Arcano", 9: "Místico"}


class LoginError(Exception):
    pass


class Client:
    def __init__(self, host, port, login, password, role_name=None, log=None):
        self.host, self.port = host, port
        self.login, self.password = login, password
        self.role_name = role_name
        self.log = log or logging.getLogger(login)
        self.link = None
        self.userid = self.localsid = None
        self.roles = []          # [{roleid, name, occupation, level}]
        self.role = None
        self.in_world = False
        self.running = False
        self.handlers = []       # callbacks(ptype, payload)
        self.dump_unknown = os.environ.get("PWBOT_DUMP") == "1"
        self._lock = threading.Lock()

    # ------------------------------------------------------------ envio
    def send(self, ptype, payload):
        with self._lock:
            self.link.send(ptype, payload)

    def send_gamedata(self, cmd, body=b""):
        self.send(GAMEDATA_C2S, octets(struct.pack("<H", cmd) + body))

    # ------------------------------------------------------------ login
    def connect(self):
        self.link = Link(self.host, self.port)
        login = self.login.encode()
        pw_hash = hashlib.md5(login + self.password.encode()).digest()
        state = "info"
        while not self.in_world:
            for t, p in self.link.recv_packets():
                r = Reader(p)
                if t == SERVER_INFO and state == "info":
                    key = r.octets()
                    self._hash = hmac_md5(pw_hash, key)
                    self.send(LOGIN_ANNOUNCE, octets(login) + octets(self._hash) + b"\x00" + octets(b""))
                    state = "key"
                elif t == KEY_EXCHANGE and state == "key":
                    snonce = r.octets()
                    cnonce = os.urandom(16)
                    self.send(KEY_EXCHANGE, octets(cnonce) + b"\x01")
                    self.link.set_out_key(hmac_md5(login, self._hash + cnonce))
                    self.link.set_in_key(hmac_md5(login, self._hash + snonce))
                    state = "announce"
                elif t == ERROR_INFO:
                    code = r.i32()
                    msg = r.octets().decode("latin-1") if r.left() else ""
                    raise LoginError(f"erro {code} {msg}")
                elif t == ONLINE_ANNOUNCE:
                    self.userid, self.localsid = r.i32(), r.i32()
                    self.log.info("logado userid=%d", self.userid)
                    self.send(ROLE_LIST, struct.pack(">iii", self.userid, self.localsid, -1))
                    state = "roles"
                elif t == ROLE_LIST_RE:
                    self._on_role_list(r)
                elif t == SELECT_ROLE_RE:
                    res = r.i32()
                    if res != 0:
                        raise LoginError(f"SelectRole falhou: {res}")
                    self.send(ENTER_WORLD, struct.pack(">ii", self.role["roleid"], self.localsid) + b"\x00" * 16)
                    self.in_world = True
                    self.log.info("entrou no mundo como %s (%s)", self.role["name"],
                                  CLASSES.get(self.role["occupation"], "?"))
                elif self.dump_unknown:
                    self.log.debug("login pkt 0x%02x %s", t, p.hex())

    def _on_role_list(self, r):
        r.i32()                      # result
        handle = r.i32()
        r.i32(); r.i32()             # userid, localsid
        if r.left() and r.u8():
            roleid = r.i32()
            r.u8(); r.u8()           # gender, race
            occ = r.u8()
            level = r.i32()
            r.i32()                  # level2
            name = r.ustr()
            self.roles.append({"roleid": roleid, "name": name, "occupation": occ, "level": level})
        if handle != -1:
            self.send(ROLE_LIST, struct.pack(">iii", self.userid, self.localsid, handle))
            return
        if not self.roles:
            raise LoginError("conta sem personagens")
        pick = [x for x in self.roles if self.role_name in (None, x["name"])]
        if not pick:
            raise LoginError(f"personagem {self.role_name!r} não encontrado: "
                             f"{[x['name'] for x in self.roles]}")
        self.role = pick[0]
        self.send(SELECT_ROLE, struct.pack(">i", self.role["roleid"]) + b"\x00")

    # ------------------------------------------------------------ loop
    def run(self):
        self.running = True
        threading.Thread(target=self._keepalive, daemon=True).start()
        while self.running:
            for t, p in self.link.recv_packets():
                for h in self.handlers:
                    try:
                        h(t, p)
                    except Exception:
                        self.log.exception("handler falhou em 0x%02x", t)

    def _keepalive(self):
        while self.running:
            time.sleep(15)
            try:
                self.send(KEEP_ALIVE, b"\x5a")
            except OSError:
                return

    def stop(self):
        self.running = False
        if self.link:
            self.link.close()

    # ------------------------------------------------------------ chat
    @property
    def roleid(self):
        return self.role["roleid"]

    def say(self, text, channel=CHANNEL_LOCAL):
        self.send(PUBLIC_CHAT, bytes([channel, 0]) + struct.pack(">i", self.roleid)
                  + ustr(text[:80]) + octets(b""))

    def whisper(self, name, text):
        self.send(PRIVATE_CHAT, b"\x00\x00" + ustr(self.role["name"]) + struct.pack(">i", self.roleid)
                  + ustr(name) + struct.pack(">i", 0) + ustr(text[:80]) + octets(b"")
                  + struct.pack(">i", 0))
