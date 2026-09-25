"""NARAKA: BLADEPOINT asset bundles -> the files inside them.

The game's StreamingAssets hold ~13k bundles named by hash.  Each is an
ordinary UnityFS bundle (Unity 2019.4) with three changes:

- the 8-byte signature is 15 1E 1C 0D 0D 23 21 00 instead of "UnityFS\0";
- compression id 6 is plain LZ4 block (Unity's 2/3);
- the blocks-info table and every data block start on a 4 KiB boundary
  (zero padding between them), so offsets are not contiguous;
- the header's sizes are offset (bundle size + 0x1E, blocks-info size
  + ~150), so the blocks-info is decoded until its zero padding.

open_bundle(path) returns [(node_name, bytes)], the serialized file(s) and
their .resS/.resource streams, ready for UnityPy.  open_lazy(path) returns
[(node_name, stream)] instead: seekable file objects that decompress only the
blocks actually read (a hero bundle is ~0.8 GB, the shared ones up to 1.7 GB).
"""
import bisect
import collections
import io
import struct

import lz4.block

SIGNATURE = bytes.fromhex("151e1c0d0d232100")
PAGE = 0x1000


def is_bundle(path):
    try:
        with open(path, "rb") as fh:
            return fh.read(8) == SIGNATURE
    except OSError:
        return False


def _lz4_unsized(src):
    """LZ4 block decode when neither size is known exactly (the header's
    blocks-info sizes are obfuscated).  Stops at the zero padding that follows
    the stream (a match offset of 0 is invalid LZ4).  Returns (data, bytes used)."""
    out = bytearray()
    i, n = 0, len(src)
    while i < n:
        token = src[i]
        i += 1
        lit = token >> 4
        if lit == 15:
            while True:
                b = src[i]
                i += 1
                lit += b
                if b != 255:
                    break
        out += src[i:i + lit]
        i += lit
        if i >= n:
            break
        off = src[i] | src[i + 1] << 8
        if off == 0 or off > len(out):
            i -= 1 + (lit > 0)
            break
        i += 2
        m = token & 15
        if m == 15:
            while True:
                b = src[i]
                i += 1
                m += b
                if b != 255:
                    break
        m += 4
        start = len(out) - off
        if off >= m:
            out += out[start:start + m]
        else:
            for k in range(m):
                out.append(out[start + k])
    return bytes(out), i


def _align(pos):
    return (pos + PAGE - 1) & ~(PAGE - 1)


def _read_cstr(buf, pos):
    end = buf.index(b"\0", pos)
    return buf[pos:end].decode("utf-8", "replace"), end + 1


def _header(head):
    """(blocks-info file offset, its compressed length) from the first 64 bytes."""
    if head[:8] != SIGNATURE:
        raise ValueError("not a NARAKA bundle")
    pos = 12
    _, pos = _read_cstr(head, pos)              # "5.x.x"
    _, pos = _read_cstr(head, pos)              # "2019.4.14f1"
    # u64 size (usually file size + 0x1E), u32 blocks-info size (a bit more
    # than the real one, 150-155 bytes), u32 junk, u32 flags (0x246)
    _, csize, _, _ = struct.unpack_from(">QIII", head, pos)
    return _align(pos + 20), csize


def _parse_info(info):
    p = 16
    (count,) = struct.unpack_from(">I", info, p)
    p += 4
    blocks = []
    for _ in range(count):
        blocks.append(struct.unpack_from(">IIH", info, p))
        p += 10
    (count,) = struct.unpack_from(">I", info, p)
    p += 4
    nodes = []
    for _ in range(count):
        off, size, flags = struct.unpack_from(">qqI", info, p)
        p += 20
        name, p = _read_cstr(info, p)
        nodes.append((off, size, flags, name))
    return blocks, nodes


def read_directory(data):
    """(blocks [(usize, csize, flags)], nodes [(offset, size, flags, name)], data_start)."""
    info_at, info_size = _header(data[:0x40])
    info, used = _lz4_unsized(data[info_at:info_at + info_size])
    blocks, nodes = _parse_info(info)
    return blocks, nodes, _align(info_at + used)


def decompress(data):
    blocks, nodes, pos = read_directory(data)
    out = bytearray()
    for usize, csize, flags in blocks:
        pos = _align(pos)
        chunk = data[pos:pos + csize]
        kind = flags & 0x3F
        if kind == 0:
            out += chunk
        elif kind in (2, 3, 6):
            out += lz4.block.decompress(chunk, uncompressed_size=usize)
        else:
            raise ValueError("compression %d not handled" % kind)
        pos += csize
    return bytes(out), nodes


def open_bundle(path):
    with open(path, "rb") as fh:
        data = fh.read()
    blob, nodes = decompress(data)
    return [(name, blob[off:off + size]) for off, size, _, name in nodes]


class _Blocks:
    """Random access to a bundle's uncompressed stream, block by block."""

    def __init__(self, path, cache=64):
        self.fh = open(path, "rb")
        info_at, info_size = _header(self.fh.read(0x40))
        self.fh.seek(info_at)
        info, used = _lz4_unsized(self.fh.read(info_size))
        blocks, self.nodes = _parse_info(info)
        self.blocks = []                         # (uoffset, usize, file offset, csize, kind)
        upos, fpos = 0, info_at + used
        for usize, csize, flags in blocks:
            fpos = _align(fpos)
            self.blocks.append((upos, usize, fpos, csize, flags & 0x3F))
            upos += usize
            fpos += csize
        self.starts = [b[0] for b in self.blocks]
        self.cache = collections.OrderedDict()
        self.limit = cache

    def block(self, i):
        got = self.cache.get(i)
        if got is not None:
            self.cache.move_to_end(i)
            return got
        _, usize, fpos, csize, kind = self.blocks[i]
        self.fh.seek(fpos)
        raw = self.fh.read(csize)
        got = raw if kind == 0 else lz4.block.decompress(raw, uncompressed_size=usize)
        self.cache[i] = got
        if len(self.cache) > self.limit:
            self.cache.popitem(last=False)
        return got

    def read(self, offset, size):
        out = bytearray()
        i = bisect.bisect_right(self.starts, offset) - 1
        while size > 0 and i < len(self.blocks):
            start = self.blocks[i][0]
            data = self.block(i)
            chunk = data[offset - start:offset - start + size]
            out += chunk
            offset += len(chunk)
            size -= len(chunk)
            i += 1
        return bytes(out)


class LazyNode(io.RawIOBase):
    def __init__(self, blocks, offset, size, name):
        self.blocks, self.base, self.size, self.name = blocks, offset, size, name
        self.pos = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def seek(self, pos, whence=0):
        self.pos = pos if whence == 0 else self.pos + pos if whence == 1 else self.size + pos
        return self.pos

    def tell(self):
        return self.pos

    def read(self, n=-1):
        if n is None or n < 0:
            n = self.size - self.pos
        n = max(0, min(n, self.size - self.pos))
        data = self.blocks.read(self.base + self.pos, n)
        self.pos += len(data)
        return data

    def readinto(self, buf):
        data = self.read(len(buf))
        buf[:len(data)] = data
        return len(data)


def open_lazy(path):
    blocks = _Blocks(path)
    return [(name, LazyNode(blocks, off, size, name)) for off, size, _, name in blocks.nodes]
