# Throne of Desire NFS tools

`extract_nfs.py` reads the X-Legend `mobilepack/packageindex` and
`FileListPC.txt` files used by the Steam build of Throne of Desire. It supports
the `0x20190503` index, reverses the per-record XOR applied to offsets and
sizes, and decompresses zlib-backed assets without modifying the game.

Scan the complete asset catalog:

```powershell
python scripts/throneofdesire/extract_nfs.py scan `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --output '.tmp\throneofdesire\inventory.json'
```

Extract one numbered Gamebryo model group for validation:

```powershell
python scripts/throneofdesire/extract_nfs.py extract-model `
  --game 'D:\Program Files (x86)\Steam\steamapps\common\ThroneOfDesire' `
  --model m001 `
  --output '.tmp\throneofdesire\m001'
```

The model helper finds the package from X-Legend's 32-bit package hash, selects
the KFM that references the requested NIF, and selects the immediately following
NIF chunk. A manifest records the original hashes, offsets, sizes, and SHA-256
digests. Custom `LZMA` streams are classified but intentionally not decoded;
the model and KFM assets verified so far use zlib.
