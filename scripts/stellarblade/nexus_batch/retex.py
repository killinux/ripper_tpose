"""Texture parameters an instance sets ITSELF on top of the ancestor material fill_materials.py copies for it.

A parameter-only mod instance (Crimson Wings' SkinEve\\Inst_1 = MI_EVE_Cos_08_Vinyl + the outfit's own Baked NormalMap)
gets a copy of its nearest archived ancestor; the copy keeps the ancestor's maps, so every texture the instance (or an
instance between it and that ancestor) overrides must be swapped in afterwards.  For each candidate ancestor of a slot
this gives [{"param", "from": the ancestor's object path for that parameter (None when only the master's graph has
it), "to": the instance's object path}].  Reads the CUE4Parse JSON of the look (<work>\\<mod>\\cue\\<label>\\json).

    python -I -X utf8 retex.py [label|mod|ALL] ...      # read-only scan: which slots of which looks are affected
"""
import json
import os
import re
import sys
from pathlib import Path

WORK = Path(r"D:\stellarblade_exports\mods")


def _name(object_name):
    """MaterialInstanceConstant'MI_x' / Material'MA_x' -> MI_x"""
    m = re.search(r"'([^']+)'", object_name or "")
    return (m.group(1) if m else (object_name or "")).split(".")[0].rsplit("/", 1)[-1]


class JsonIndex:
    def __init__(self, json_dir):
        self.files = {}
        for p in Path(json_dir).rglob("*.json"):
            self.files.setdefault(p.stem.lower(), p)
        self.cache = {}

    def props(self, name):
        key = name.lower()
        if key not in self.cache:
            p = self.files.get(key)
            d = None
            if p is not None:
                try:
                    d = json.load(open(p, encoding="utf-8-sig"))
                except (OSError, ValueError):
                    d = None
            if isinstance(d, list):
                d = next((x for x in d if isinstance(x, dict) and _name(x.get("Name", "")).lower() == key),
                         d[0] if d else None)
            self.cache[key] = (d.get("Properties") or {}) if isinstance(d, dict) else {}
        return self.cache[key]

    def own_textures(self, name):
        return {t["ParameterInfo"]["Name"]: (t.get("ParameterValue") or {}).get("ObjectPath")
                for t in self.props(name).get("TextureParameterValues") or []
                if (t.get("ParameterValue") or {}).get("ObjectPath")}


def flattened(idx, chain_from):
    """textures of chain_from[0] with everything it inherits (chain_from = [it, parent, ..., master])"""
    out = {}
    for n in reversed(chain_from):
        out.update(idx.own_textures(n))
    return out


def retex_for(idx, chain):
    """{ancestor: [{"param", "from", "to"}]} for every ancestor in chain[1:]"""
    out = {}
    mine = flattened(idx, chain)                            # the instance with all it inherits
    for k in range(1, len(chain)):
        anc = chain[k]
        theirs = flattened(idx, chain[k:])
        diffs = [{"param": p, "from": theirs.get(p), "to": v} for p, v in sorted(mine.items()) if theirs.get(p) != v]
        if diffs:
            out[anc] = diffs
    return out


def scan(labels):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from looks import BY_LABEL, LOOKS
    if not labels or labels == ["ALL"]:
        labels = [lk["label"] for lk in LOOKS]
    else:
        labels = [x for n in labels for x in ([n] if n in BY_LABEL else [lk["label"] for lk in LOOKS if lk["mod"] == n])]
    for label in labels:
        lk = BY_LABEL[label]
        lw = WORK / lk["mod"] / "looks" / label
        jd = WORK / lk["mod"] / "cue" / label / "json"
        st = lw / "status.json"
        if not st.is_file() or not jd.is_dir():
            continue
        status = json.load(open(st, encoding="utf-8"))
        filled = (status.get("fill") or {}).get("filled") or {}
        slots = json.load(open(lw / "slots.json", encoding="utf-8"))
        idx = JsonIndex(jd)
        for s in slots:
            how = filled.get(s["use"]) or ""
            m = re.match(r"copy of (\S+)", how)
            if not m:
                continue
            anc = m.group(1)[:-4] if m.group(1).endswith("_mod") else m.group(1)
            diffs = retex_for(idx, s["chain"]).get(anc)
            if diffs:
                print("%s | slot %d %s <- %s" % (label, s["index"], s["use"], anc))
                for d in diffs:
                    print("      %-22s %s -> %s" % (d["param"], (d["from"] or "-").rsplit("/", 1)[-1],
                                                    d["to"].rsplit("/", 1)[-1]))


if __name__ == "__main__":
    scan(sys.argv[1:])
