"""Minimal MessagePack decoder (the subset MessagePack-CSharp writes for HS2 lists and cards).

Kept in-repo so the HoneySelect 2 scripts need nothing beyond UnityPy/numpy.
"""
import struct

__all__ = ["unpackb", "Unpacker"]


class Unpacker:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def _take(self, n):
        b = self.data[self.pos:self.pos + n]
        if len(b) != n:
            raise ValueError("msgpack: truncated at %d" % self.pos)
        self.pos += n
        return b

    def _u(self, fmt, n):
        return struct.unpack(fmt, self._take(n))[0]

    def _str(self, n):
        raw = self._take(n)
        try:
            return raw.decode("utf-8")
        except UnicodeDecodeError:
            return raw.decode("utf-8", "replace")

    def _array(self, n):
        return [self.unpack() for _ in range(n)]

    def _map(self, n):
        out = {}
        for _ in range(n):
            k = self.unpack()
            if isinstance(k, list):
                k = tuple(k)
            out[k] = self.unpack()
        return out

    def unpack(self):
        b = self._take(1)[0]
        if b <= 0x7F:
            return b
        if b >= 0xE0:
            return b - 0x100
        if 0x80 <= b <= 0x8F:
            return self._map(b & 0x0F)
        if 0x90 <= b <= 0x9F:
            return self._array(b & 0x0F)
        if 0xA0 <= b <= 0xBF:
            return self._str(b & 0x1F)
        if b == 0xC0:
            return None
        if b == 0xC2:
            return False
        if b == 0xC3:
            return True
        if b == 0xC4:
            return self._take(self._u(">B", 1))
        if b == 0xC5:
            return self._take(self._u(">H", 2))
        if b == 0xC6:
            return self._take(self._u(">I", 4))
        if b in (0xC7, 0xC8, 0xC9):  # ext 8/16/32
            n = self._u({0xC7: ">B", 0xC8: ">H", 0xC9: ">I"}[b], {0xC7: 1, 0xC8: 2, 0xC9: 4}[b])
            self._take(1)
            return self._take(n)
        if b == 0xCA:
            return self._u(">f", 4)
        if b == 0xCB:
            return self._u(">d", 8)
        if b == 0xCC:
            return self._u(">B", 1)
        if b == 0xCD:
            return self._u(">H", 2)
        if b == 0xCE:
            return self._u(">I", 4)
        if b == 0xCF:
            return self._u(">Q", 8)
        if b == 0xD0:
            return self._u(">b", 1)
        if b == 0xD1:
            return self._u(">h", 2)
        if b == 0xD2:
            return self._u(">i", 4)
        if b == 0xD3:
            return self._u(">q", 8)
        if b in (0xD4, 0xD5, 0xD6, 0xD7, 0xD8):  # fixext 1/2/4/8/16
            self._take(1)
            return self._take({0xD4: 1, 0xD5: 2, 0xD6: 4, 0xD7: 8, 0xD8: 16}[b])
        if b == 0xD9:
            return self._str(self._u(">B", 1))
        if b == 0xDA:
            return self._str(self._u(">H", 2))
        if b == 0xDB:
            return self._str(self._u(">I", 4))
        if b == 0xDC:
            return self._array(self._u(">H", 2))
        if b == 0xDD:
            return self._array(self._u(">I", 4))
        if b == 0xDE:
            return self._map(self._u(">H", 2))
        if b == 0xDF:
            return self._map(self._u(">I", 4))
        raise ValueError("msgpack: bad type byte 0x%02X at %d" % (b, self.pos - 1))


def unpackb(data):
    return Unpacker(bytes(data)).unpack()
