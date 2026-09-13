"""Recover a UE4/UE5 pak AES-256 key from the game executable when it is NOT stored as one contiguous
32-byte constant.

Vindictus: Defying Fate builds the key at run time with eight ``mov dword [..], imm32`` instructions, so
the usual "scan the exe for 32 high-entropy bytes" finders come back empty.  This script walks the
.text section, collects immediates that code stores in sequence (imm64 x4, imm32 x8, imm8 x32) and
pairs of rip-relative 16-byte xmm constants, rebuilds every ordered group into a 32-byte candidate and
test-decrypts the first block of a pak's encrypted index with it: the right key decrypts to the mount
point FString (``../../../``).  Contiguous 32-byte windows are tried first, so plain keys are found too.

    python find_aes_key.py                       # Vindictus defaults (E:\\tools\\vindictus)
    python find_aes_key.py --exe Game.exe --pak Game-Windows.pak --out D:\\keys\\game_aes.txt

The key is printed and, with --out, written as one ``0x...`` line.  Keep that file out of the repo.
"""
import argparse
import os
import struct
import sys
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

PAK_MAGIC = 0x5A6F12E1
DEFAULT_EXE = r"E:\tools\vindictus\Vindictus\Binaries\Win64\Vindictus.exe"
DEFAULT_PAK = r"E:\tools\vindictus\Vindictus\Content\Paks\Vindictus-Windows.pak"


def pak_index_block(path):
    """First 16 bytes of the (encrypted) pak index, from the FPakInfo footer."""
    with open(path, "rb") as fh:
        fh.seek(-4096, 2)
        tail = fh.read()
    i = tail.rfind(struct.pack("<I", PAK_MAGIC))
    if i < 0:
        raise SystemExit("no pak footer magic in " + path)
    version, index_offset, index_size = struct.unpack_from("<IQQ", tail, i + 4)
    encrypted = tail[i - 1]
    with open(path, "rb") as fh:
        fh.seek(index_offset)
        block = fh.read(16)
    return version, encrypted, block


def plausible(plain):
    n = struct.unpack_from("<i", plain, 0)[0]
    return 1 <= n <= 1024 and plain[4:4 + min(9, n - 1)] == b"../../../"[:min(9, n - 1)]


def make_tester(block):
    tested = set()

    def test(key):
        if len(key) != 32 or key in tested or len(set(key)) < 20:
            return False
        tested.add(key)
        return plausible(Cipher(algorithms.AES(key), modes.ECB()).decryptor().update(block))
    return test, tested


def pe_sections(data):
    pe = struct.unpack_from("<I", data, 0x3C)[0]
    count = struct.unpack_from("<H", data, pe + 6)[0]
    opt_size = struct.unpack_from("<H", data, pe + 20)[0]
    sections = []
    for k in range(count):
        o = pe + 24 + opt_size + 40 * k
        name = data[o:o + 8].split(b"\0")[0].decode(errors="replace")
        vsize, vaddr, rsize, raddr = struct.unpack_from("<IIII", data, o + 8)
        sections.append((name, vaddr, vsize, raddr, rsize))
    return sections


def modrm_len(m):
    mod, rm = m >> 6, m & 7
    n = 1
    if mod != 3 and rm == 4:
        n += 1
    if mod == 1:
        n += 1
    elif mod == 2 or (mod == 0 and rm == 5):
        n += 4
    return n


def collect_records(data, sections):
    """Immediates and rip-relative 16-byte constants in .text, in instruction order."""
    text = next((s for s in sections if s[0] == ".text"), None)
    if text is None:
        raise SystemExit("no .text section")
    text_va, text_off, text_len = text[1], text[3], text[4]

    def rva_to_off(rva):
        for _n, va, vs, ra, rs in sections:
            if va <= rva < va + max(vs, rs):
                return ra + (rva - va)
        return None

    recs = {"q": [], "d": [], "b": [], "x": []}
    o, end = text_off, text_off + text_len
    while o < end - 12:
        b0, b1 = data[o], data[o + 1]
        if b0 in (0x48, 0x49) and 0xB8 <= b1 <= 0xBF:                  # mov r64, imm64
            recs["q"].append((o, data[o + 2:o + 10]))
            o += 10
            continue
        if b0 == 0xC7 and (b1 >> 3) & 7 == 0 and b1 >> 6 != 3:           # mov r/m32, imm32
            n = modrm_len(b1)
            recs["d"].append((o, data[o + 1 + n:o + 5 + n]))
            o += 5 + n
            continue
        if b0 == 0xC6 and (b1 >> 3) & 7 == 0 and b1 >> 6 != 3:           # mov r/m8, imm8
            n = modrm_len(b1)
            recs["b"].append((o, data[o + 1 + n:o + 2 + n]))
            o += 2 + n
            continue
        hit = None                                                        # movups/movaps/movdqa/movdqu/vmovups xmm, [rip+d32]
        if b0 == 0x0F and b1 in (0x10, 0x28) and data[o + 2] & 0xC7 == 0x05:
            hit = (3, 7)
        elif b0 in (0x66, 0xF3) and b1 == 0x0F and data[o + 2] == 0x6F and data[o + 3] & 0xC7 == 0x05:
            hit = (4, 8)
        elif b0 == 0xC5 and b1 == 0xF8 and data[o + 2] in (0x10, 0x28) and data[o + 3] & 0xC7 == 0x05:
            hit = (4, 8)
        if hit:
            disp_pos, length = hit
            disp = struct.unpack_from("<i", data, o + disp_pos)[0]
            foff = rva_to_off(text_va + (o - text_off) + length + disp)
            if foff is not None and foff + 16 <= len(data):
                recs["x"].append((o, data[foff:foff + 16]))
            o += length
            continue
        o += 1
    return recs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--exe", default=DEFAULT_EXE)
    ap.add_argument("--pak", default=DEFAULT_PAK, help="any pak of the game with an encrypted index")
    ap.add_argument("--out", default="", help="write the key here as one 0x... line (keep it out of the repo)")
    ap.add_argument("--no-contiguous", action="store_true", help="skip the plain 32-byte window pass")
    args = ap.parse_args()

    version, encrypted, block = pak_index_block(args.pak)
    print("pak v%d, encrypted index=%d" % (version, encrypted))
    if not encrypted:
        raise SystemExit("this pak's index is not encrypted - nothing to find")
    test, tested = make_tester(block)
    data = open(args.exe, "rb").read()
    found = []
    t0 = time.time()

    if not args.no_contiguous:
        for off in range(0, len(data) - 32, 16):        # aligned plain keys first (cheap)
            if test(data[off:off + 32]):
                found.append((off, data[off:off + 32], "contiguous"))
        print("contiguous 16-aligned windows: %d tested, %.0f s" % (len(tested), time.time() - t0))

    if not found:
        recs = collect_records(data, pe_sections(data))
        print("records: " + ", ".join("%s=%d" % (k, len(v)) for k, v in recs.items()))
        for kind, count, gap in (("q", 4, 40), ("d", 8, 24), ("b", 32, 16), ("x", 2, 64)):
            rs = recs[kind]
            for s in range(len(rs) - count + 1):
                group = rs[s:s + count]
                if all(group[k + 1][0] - group[k][0] <= gap for k in range(count - 1)):
                    parts = [g[1] for g in group]
                    for key in (b"".join(parts), b"".join(reversed(parts))):
                        if test(key):
                            found.append((group[0][0], key, "%s run" % kind))
        print("pattern candidates: %d tested, %.0f s" % (len(tested), time.time() - t0))

    if not found:
        print("NO KEY FOUND (try a memory dump of the running game)")
        return 1
    for off, key, how in found:
        print("KEY 0x%s  (%s @ file offset 0x%X)" % (key.hex().upper(), how, off))
    if args.out:
        with open(args.out, "w", encoding="ascii") as fh:
            fh.write("0x" + found[0][1].hex().upper() + "\n")
        print("written to " + args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
