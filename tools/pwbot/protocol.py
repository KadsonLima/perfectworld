"""Camada de rede do Perfect World 1.5.5 (glinkd, versão 10505).

Framing: CUINT tipo, CUINT tamanho, payload. Campos do protocolo "externo"
(login, chat, rolelist) são big-endian; comandos de jogo dentro de GameData
são little-endian.
"""
import hashlib
import hmac
import socket
import struct


# ---------------------------------------------------------------- primitivas
def cuint(n):
    if n < 0x80:
        return bytes([n])
    if n < 0x4000:
        return struct.pack(">H", n | 0x8000)
    if n < 0x20000000:
        return struct.pack(">I", n | 0xC0000000)
    return b"\xE0" + struct.pack(">I", n)


def octets(b):
    return cuint(len(b)) + b


def ustr(s):
    return octets(s.encode("utf-16-le"))


class Reader:
    def __init__(self, data, pos=0):
        self.d = data
        self.p = pos

    def left(self):
        return len(self.d) - self.p

    def raw(self, n):
        if self.p + n > len(self.d):
            raise EOFError
        v = self.d[self.p:self.p + n]
        self.p += n
        return v

    def u8(self):
        return self.raw(1)[0]

    def i32(self):
        return struct.unpack(">i", self.raw(4))[0]

    def u32(self):
        return struct.unpack(">I", self.raw(4))[0]

    def le(self, fmt):
        return struct.unpack("<" + fmt, self.raw(struct.calcsize("<" + fmt)))

    def cuint(self):
        b = self.u8()
        if b < 0x80:
            return b
        if b < 0xC0:
            return ((b & 0x3F) << 8) | self.u8()
        if b < 0xE0:
            return ((b & 0x1F) << 24) | (self.u8() << 16) | (self.u8() << 8) | self.u8()
        return self.u32()

    def octets(self):
        return self.raw(self.cuint())

    def ustr(self):
        return self.octets().decode("utf-16-le", "replace")


def split_packets(buf):
    """Extrai pacotes completos de um bytearray; retorna lista de (tipo, payload)."""
    out = []
    while buf:
        r = Reader(bytes(buf[:16]))
        try:
            t = r.cuint()
            n = r.cuint()
        except EOFError:
            break
        if r.p + n > len(buf):
            break
        out.append((t, bytes(buf[r.p:r.p + n])))
        del buf[:r.p + n]
    return out


# ---------------------------------------------------------------- cripto
class RC4:
    def __init__(self, key):
        s = list(range(256))
        j = 0
        for i in range(256):
            j = (j + s[i] + key[i % len(key)]) & 0xFF
            s[i], s[j] = s[j], s[i]
        self.s, self.i, self.j = s, 0, 0

    def __call__(self, data):
        s, i, j = self.s, self.i, self.j
        out = bytearray(len(data))
        for k, c in enumerate(data):
            i = (i + 1) & 0xFF
            j = (j + s[i]) & 0xFF
            s[i], s[j] = s[j], s[i]
            out[k] = c ^ s[(s[i] + s[j]) & 0xFF]
        self.i, self.j = i, j
        return bytes(out)


class MPPC:
    """Descompressor MPPC em streaming (janela 8K, offset 0 = alinhar byte)."""

    def __init__(self):
        self.bits = bytearray()
        self.pos = 0          # posição em bits dentro de self.bits
        self.hist = bytearray()

    def _get(self, n):
        if self.pos + n > len(self.bits) * 8:
            raise EOFError
        v = 0
        for _ in range(n):
            byte = self.bits[self.pos >> 3]
            v = (v << 1) | ((byte >> (7 - (self.pos & 7))) & 1)
            self.pos += 1
        return v

    def feed(self, data):
        self.bits += data
        out = bytearray()
        while True:
            save = self.pos
            try:
                out += self._token()
            except EOFError:
                self.pos = save
                break
        drop = self.pos >> 3
        if drop:
            del self.bits[:drop]
            self.pos -= drop * 8
        if len(self.hist) > 16384:
            del self.hist[:len(self.hist) - 8192]
        return bytes(out)

    def _token(self):
        g = self._get
        if g(1) == 0:
            lit = g(7)
        elif g(1) == 0:
            lit = g(7) | 0x80
        else:
            if g(1) == 0:
                off = g(13) + 320
            elif g(1) == 0:
                off = g(8) + 64
            else:
                off = g(6)
            if off == 0:              # flush: pula até o próximo byte
                self.pos = (self.pos + 7) & ~7
                return b""
            n = 0
            while g(1) == 1:
                n += 1
                if n > 11:
                    raise ValueError("MPPC: tamanho inválido")
            length = 3 if n == 0 else (1 << (n + 1)) + g(n + 1)
            h = self.hist
            start = len(h) - off
            if start < 0:
                raise ValueError("MPPC: offset fora da janela")
            chunk = bytearray()
            for k in range(length):
                c = h[start + k]
                h.append(c)
                chunk.append(c)
            return bytes(chunk)
        self.hist.append(lit)
        return bytes([lit])


def hmac_md5(key, msg):
    return hmac.new(key, msg, hashlib.md5).digest()


# ---------------------------------------------------------------- conexão
class Link:
    """Socket com criptografia de saída e decripto+descompressão de entrada."""

    def __init__(self, host, port, timeout=30):
        self.sock = socket.create_connection((host, port), timeout)
        self.sock.settimeout(timeout)
        self.enc = None
        self.dec = None
        self.mppc = None
        self.buf = bytearray()

    def send(self, ptype, payload):
        data = cuint(ptype) + cuint(len(payload)) + payload
        if self.enc:
            data = self.enc(data)
        self.sock.sendall(data)

    def set_out_key(self, key):
        self.enc = RC4(key)

    def set_in_key(self, key):
        self.dec = RC4(key)
        self.mppc = MPPC()

    def recv_packets(self):
        data = self.sock.recv(65536)
        if not data:
            raise ConnectionError("conexão fechada pelo servidor")
        if self.dec:
            data = self.mppc.feed(self.dec(data))
        self.buf += data
        return split_packets(self.buf)

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
