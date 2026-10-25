"""Recipe for AION2's nude body (export_model.py <G>_Nude): base skin + shape guides for its openings.

AION2 has no nude body asset: the base body (GF_BaseBody / GF_BasePants) is a default top + skirt and tights,
GF_RootMesh is a 1,120-face proxy, the shop mannequin (Character/ETC/Mannequin/<G>) is closed and nude but another
mesh (0.7-1.4 cm off the costumes' body, no shared vertex).  Every costume part that shows skin carries it in its
<G>_BaseBody material slot.  What was measured on the 172 female parts (10-25):
  * their skins come from one master body: away from the garments they share vertex POSITIONS (e.g. 4,392 of
    GF_Seethrough_01_Body's 5,333 skin vertices sit on GF_Underwear_01_Body's, same UV);
  * but each costume cuts the master along its garment's edge (new vertices only it has: 63 of the 65 rim vertices
    of GF_Underwear_01_Body's cup openings exist in no other part) and the parts triangulate differently - a union of
    their faces has 23,734 non-manifold edges and twice the body's area.  Face-level merging cannot work.
So the nude body is ONE costume's skin (the base, default the underwear set: arms, torso, legs, feet, welded at the
waist, five clean openings: two cups, two strap slits, the bikini area) and every opening is capped by
build_blend.py, the cap shaped onto
  * the other costumes' skin around it where they show it (the guide coincides with the real body: the breasts), or
  * the mannequin where no costume shows any skin (the bikini area), with the guide-to-rim offset blended away.

This script picks nothing any more - it measures the base's openings and writes the guide: every other costume's
skin triangle within GUIDE_REACH of an opening, as <export-root>\\_meta\\aion2_nude_<G>_guide.npy (float32 n x 3 x 3).

    python nude_survey.py --gender GF            # the base's openings and how much guide skin covers each
    python nude_survey.py --gender GF --write    # + recipe aion2_nude_<G>.json and the guide .npy
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import struct
import sys
from collections import defaultdict

import numpy as np

UMODEL = r"E:\aion2_exports\umodel_exports"
EXPORT_ROOT = r"E:\aion2_exports"
QUANT = 1000.0         # position keys on a 0.01 mm grid (PSK coordinates are cm; Blender's importer keeps them)
GUIDE_REACH = 12.0     # cm around an opening's rim
DEFAULT_BASE = {"GF": ["GF_Underwear_01_Body", "GF_Underwear_01_Pants"],
                "GM": ["GM_Underwear_01_Body", "GM_Underwear_01_Pants"]}


def read_psk(path: str) -> dict:
    """Points, wedges (point, u, v, material), faces (3 wedges, material), material names of a PSK."""
    out = {"points": None, "wedges": None, "faces": None, "materials": []}
    with open(path, "rb") as fh:
        data = fh.read()
    pos = 0
    while pos + 32 <= len(data):
        cid = data[pos:pos + 20].split(b"\0")[0].decode("ascii", "replace")
        _flag, size, count = struct.unpack_from("<iii", data, pos + 20)
        body = data[pos + 32:pos + 32 + size * count]
        pos += 32 + size * count
        if cid == "PNTS0000":
            out["points"] = np.frombuffer(body, "<f4").reshape(count, 3)
        elif cid == "VTXW0000":
            if count <= 65536:
                rec = np.frombuffer(body, dtype=[("p", "<u2"), ("pad", "<u2"), ("u", "<f4"), ("v", "<f4"), ("m", "u1"), ("r", "u1"), ("pad2", "<u2")])
            else:
                rec = np.frombuffer(body, dtype=[("p", "<u4"), ("u", "<f4"), ("v", "<f4"), ("m", "u1"), ("r", "u1"), ("pad2", "<u2")])
            out["wedges"] = rec
        elif cid in ("FACE0000", "FACE3200"):
            if cid == "FACE0000":
                rec = np.frombuffer(body, dtype=[("w", "<u2", 3), ("m", "u1"), ("a", "u1"), ("s", "<u4")])
            else:
                rec = np.frombuffer(body, dtype=[("w", "<u4", 3), ("m", "u1"), ("a", "u1"), ("s", "<u4")])
            out["faces"] = rec
        elif cid == "MATT0000":
            out["materials"] = [body[i * size:i * size + 64].split(b"\0")[0].decode("utf-8", "replace") for i in range(count)]
    return out


def skin_triangles(psk: dict, skin_name: str):
    """(n, 3, 3) float32 corner positions of the triangles in the skin material slot, or None."""
    skin = [i for i, n in enumerate(psk["materials"]) if n == skin_name]
    if not skin or psk["faces"] is None:
        return None
    faces = psk["faces"]
    w = faces["w"][np.isin(faces["m"], skin)].astype(np.int64)
    if not len(w):
        return None
    return psk["points"][psk["wedges"]["p"][w].astype(np.int64)]


def openings(tris: np.ndarray):
    """Boundary loops of a triangle soup: [(perimeter cm, centre, rim points (k, 3))], largest first."""
    keys = np.round(tris.astype(np.float64) * QUANT).astype(np.int64)
    edges = defaultdict(int)
    for f in keys:
        f = [tuple(v) for v in f]
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            edges[(a, b) if a < b else (b, a)] += 1
    bnd = [e for e, n in edges.items() if n == 1]
    adj = defaultdict(list)
    for e in bnd:
        adj[e[0]].append(e)
        adj[e[1]].append(e)
    seen, loops = set(), []
    for e in bnd:
        if e in seen:
            continue
        stack, loop = [e], []
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            loop.append(x)
            for v in x:
                stack.extend(y for y in adj[v] if y not in seen)
        pts = np.array(sorted({v for x in loop for v in x}), dtype=np.float64) / QUANT
        per = sum(np.linalg.norm(np.subtract(a, b)) / QUANT for a, b in loop)
        loops.append((per, pts.mean(axis=0), pts))
    return sorted(loops, key=lambda t: -t[0])


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gender", default="GF", choices=["GF", "GM"])
    ap.add_argument("--umodel", default=UMODEL)
    ap.add_argument("--base", help="comma-separated costume parts whose skin is the body (default: the underwear set)")
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()
    g = args.gender
    skin_name = g + "_BaseBody"
    base = args.base.split(",") if args.base else DEFAULT_BASE[g]
    pattern = os.path.join(args.umodel, "Character", "Player", g, "Armor", "Special", "*", "*.psk")
    paths = {os.path.splitext(os.path.basename(p))[0]: p for p in glob.glob(pattern)}
    missing = [b for b in base if b not in paths]
    if missing:
        raise SystemExit("base parts not exported yet: %s (export_model.py exports them on the first nude run)" % missing)
    base_tris = np.concatenate([skin_triangles(read_psk(paths[b]), skin_name) for b in base])
    loops = openings(base_tris)
    neck = max(loops, key=lambda l: l[1][2])                 # the highest opening stays open for the head
    holes = [l for l in loops if l is not neck]
    print("base %s: %d skin triangles, openings: %s (neck %.0f cm left open)" % (
        " + ".join(base), len(base_tris), ", ".join("%.0f cm" % l[0] for l in holes), neck[0]))
    rim = np.concatenate([l[2] for l in holes])
    # One guide per part: build_blend.py shapes each cap onto the SINGLE part whose skin passes closest to that
    # opening's rim (same mesh family = the very same surface).  All parts merged into one guide made the cups
    # lumpy: a hundred slightly different breasts (10-25).
    guides = {}
    for stem, path in sorted(paths.items()):
        if stem in base or stem.split("_")[-1] not in ("Body", "Pants", "A", "B"):
            continue
        t = skin_triangles(read_psk(path), skin_name)
        if t is None:
            continue
        c = t.mean(axis=1)
        d = np.full(len(c), np.inf)
        for i in range(0, len(rim), 256):                   # distance of each centre to the nearest rim point
            dd = np.linalg.norm(c[:, None, :] - rim[None, i:i + 256, :], axis=2).min(axis=1)
            d = np.minimum(d, dd)
        near = t[d < GUIDE_REACH]
        if len(near):
            guides[stem] = near.astype(np.float32)
    print("guides: %d parts, %d skin triangles within %.0f cm of the openings" % (
        len(guides), sum(len(t) for t in guides.values()), GUIDE_REACH))
    if args.write:
        meta = os.path.join(EXPORT_ROOT, "_meta")
        np.savez_compressed(os.path.join(meta, "aion2_nude_%s_guides.npz" % g), **guides)
        rel = lambda p: os.path.relpath(p, args.umodel).replace("\\", "/")
        with open(os.path.join(meta, "aion2_nude_%s.json" % g), "w", encoding="utf-8") as fh:
            json.dump({"gender": g, "skin_material": skin_name,
                       "parts": [{"stem": b, "psk_rel": rel(paths[b]), "role": "base"} for b in base],
                       "guide": "aion2_nude_%s_guides.npz" % g,
                       "openings_cm": [round(l[0], 1) for l in holes]}, fh, indent=1)
        print("recipe -> %s" % os.path.join(meta, "aion2_nude_%s.json" % g))
    return 0


if __name__ == "__main__":
    sys.exit(main())
