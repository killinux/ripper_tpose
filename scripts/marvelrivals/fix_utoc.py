"""Repairs a Marvel Rivals mod container (.utoc) whose header says "encrypted" while its directory index was written in
plain text - the data blocks are encrypted, the index is not, and its size is no multiple of 16 (seen on Nexus #10647
Symbiotic Assassin Black Widow, 2026-07).  CUE4Parse decrypts the index because of the flag and stops with "AES-ECB
input length must be a multiple of 16 bytes"; clearing the flag lists the files but then reads the encrypted blocks as
plain data ("Could not load standard asset").  So the index is encrypted the way the engine expects (zero-padded to 16,
AES-256-ECB with the game key), DirectoryIndexSize is updated and everything after the index moves along.

Works on a COPY: python -I fix_utoc.py <in.utoc> <out.utoc> <aes key hex>.  Leaves a correct container unchanged
(exit code 0, prints UTOC_OK); prints UTOC_FIXED after a repair.
"""
import struct
import sys

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"-==--==--==--==-"
ENCRYPTED, SIGNED = 0x02, 0x04


def layout(d):
    if d[:16] != MAGIC:
        raise ValueError("not an IoStore .utoc")
    (hdr_size, entries, blocks, block_entry, n_methods, method_len, _block_size,
     index_size, _partitions) = struct.unpack_from("<IIIIIIIII", d, 0x14)
    flags = d[0x50]
    seeds = struct.unpack_from("<I", d, 0x54)[0]
    no_hash = struct.unpack_from("<I", d, 0x60)[0] if d[0x10] >= 5 else 0
    off = hdr_size + 12 * entries + 10 * entries + 4 * seeds + 4 * no_hash + block_entry * blocks + n_methods * method_len
    if flags & SIGNED:
        hash_size = struct.unpack_from("<I", d, off)[0]
        off += 4 + 2 * hash_size + 20 * blocks
    return {"flags": flags, "index_off": off, "index_size": index_size, "entries": entries}


def looks_plain(index):
    """A plain directory index starts with the mount point FString ("../../../")."""
    n = struct.unpack_from("<i", index, 0)[0]
    return 0 < n < 512 and index[4:4 + min(n, 9)].startswith(b"../")


def fix(data, key_hex):
    d = bytearray(data)
    lay = layout(d)
    index = bytes(d[lay["index_off"]:lay["index_off"] + lay["index_size"]])
    if not (lay["flags"] & ENCRYPTED) or not looks_plain(index):
        return None
    key = bytes.fromhex(key_hex[2:] if key_hex.lower().startswith("0x") else key_hex)
    padded = index + b"\0" * (-len(index) % 16)
    enc = Cipher(algorithms.AES(key), modes.ECB()).encryptor()
    cipher = enc.update(padded) + enc.finalize()
    out = d[:lay["index_off"]] + cipher + d[lay["index_off"] + lay["index_size"]:]
    struct.pack_into("<I", out, 0x30, len(cipher))
    return bytes(out)


def main():
    src, dst, key = sys.argv[1], sys.argv[2], sys.argv[3]
    with open(src, "rb") as f:
        data = f.read()
    fixed = fix(data, key)
    with open(dst, "wb") as f:
        f.write(fixed if fixed is not None else data)
    print("UTOC_FIXED" if fixed is not None else "UTOC_OK")


if __name__ == "__main__":
    main()
