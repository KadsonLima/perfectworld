"""Sobe todos os bots de bots.json e reconecta se caírem.

Uso: python run_bots.py [bots.json]
Env: ANTHROPIC_API_KEY (opcional, chat com IA), PWBOT_DUMP=1 (log de pacotes)
"""
import json
import logging
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brain import Bot  # noqa: E402
from client import LoginError  # noqa: E402


def wait_port(host, port, timeout=600):
    import socket
    end = time.time() + timeout
    while time.time() < end:
        try:
            socket.create_connection((host, port), 3).close()
            return True
        except OSError:
            time.sleep(5)
    return False


def supervise(cfg, server):
    log = logging.getLogger(cfg.get("role") or cfg["login"])
    delay = 10
    while True:
        try:
            Bot(cfg, server, log).start()
        except LoginError as e:
            log.error("login: %s (nova tentativa em 5 min)", e)
            time.sleep(300)
            continue
        except Exception as e:
            log.warning("desconectado: %s", e)
        time.sleep(delay)
        delay = min(delay * 2, 300)


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(__file__), "bots.json")
    with open(path, encoding="utf-8") as f:
        conf = json.load(f)
    logging.basicConfig(level=logging.DEBUG if os.environ.get("PWBOT_DUMP") else logging.INFO,
                        format="%(asctime)s %(name)-12s %(levelname)s %(message)s")
    server = conf["server"]
    if not wait_port(server["host"], server["port"]):
        sys.exit("glinkd não respondeu")
    time.sleep(conf.get("startup_delay", 20))   # dá tempo do gamed carregar os mapas
    for b in conf["bots"]:
        if b.get("enabled", True):
            threading.Thread(target=supervise, args=(b, server), daemon=True).start()
            time.sleep(3)
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
