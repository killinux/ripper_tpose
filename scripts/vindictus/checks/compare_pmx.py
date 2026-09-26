"""Side-by-side facts of two PMX files (mmd_tools' stdlib PMX reader, plain Python, no Blender).
  python compare_pmx.py <a.pmx> <b.pmx>"""
import importlib.util
import math
import sys
from collections import Counter

import os

MMD_PMX = os.path.join(os.environ.get("APPDATA", ""), "Blender Foundation", "Blender", "3.6", "scripts",
                       "addons", "mmd_tools", "core", "pmx", "__init__.py")
spec = importlib.util.spec_from_file_location("pmx", MMD_PMX)
pmx = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pmx)


def facts(path):
    m = pmx.load(path)
    bones = [b.name for b in m.bones]
    idx = {n: i for i, n in enumerate(bones)}
    wcount, wsum = Counter(), Counter()
    for v in m.vertices:
        w = v.weight
        bs = w.bones if hasattr(w, "bones") else []
        ws = w.weights if hasattr(w, "weights") else []
        if isinstance(ws, (int, float)):
            ws = [ws]
        if len(bs) == 1:
            ws = [1.0]
        elif len(bs) == 2 and len(ws) == 1:
            ws = [ws[0], 1 - ws[0]]
        elif hasattr(ws, "weights"):              # SDEF
            ws = [ws.weight, 1 - ws.weight]
        for b, x in zip(bs, ws):
            if b >= 0 and x > 1e-3:
                wcount[b] += 1
                wsum[b] += x
    out = {"vertices": len(m.vertices), "bones": len(bones), "materials": len(m.materials)}
    out["morphs"] = Counter(type(x).__name__ for x in m.morphs)
    out["morph_names"] = [x.name for x in m.morphs][:30]
    out["has_両目"] = "両目" in idx
    for n in ("下半身", "Bip001_Pelvis", "センター", "頭", "head neck upper", "左目", "左胸", "右胸",
              "Bip001_L_bust_1", "Bip001_L_bust_2", "Bip001_R_bust_2"):
        if n in idx:
            i = idx[n]
            par = m.bones[i].parent
            out["bone " + n] = "parent %s, skin %d verts / sum %.0f / avg %.2f" % (
                bones[par] if par is not None and par >= 0 else "-", wcount[i], wsum[i], wsum[i] / max(wcount[i], 1))
    rb = m.rigids
    out["rigid_bodies"] = len(rb)
    out["rigid modes"] = Counter(r.mode for r in rb)
    out["rigid groups"] = Counter(r.collision_group_number for r in rb)
    hair = [r for r in rb if "hair" in r.name.lower() or (r.bone is not None and r.bone >= 0 and "hair" in bones[r.bone].lower())]
    out["hair bodies"] = "%d (modes %s, shape %s, mass %s, damping %s, group %s)" % (
        len(hair), dict(Counter(r.mode for r in hair)), dict(Counter(r.type for r in hair)),
        sorted({round(r.mass, 2) for r in hair})[:3], sorted({(round(r.velocity_attenuation, 2), round(r.rotation_attenuation, 2)) for r in hair})[:2],
        dict(Counter(r.collision_group_number for r in hair)))
    bust = [r for r in rb if r.bone is not None and r.bone >= 0 and any(k in bones[r.bone] for k in ("胸", "bust"))]
    out["bust bodies"] = ["%s on %s: mode %d r %.2f mass %.1f damp %.2f/%.2f group %d" % (
        r.name, bones[r.bone], r.mode, r.size[0], r.mass, r.velocity_attenuation, r.rotation_attenuation, r.collision_group_number) for r in bust]
    js = m.joints
    out["joints"] = len(js)
    bj = [j for j in js if any(k in j.name for k in ("胸", "bust"))]
    out["bust joints"] = ["%s: rot limit %s..%s deg, spring rot %s" % (
        j.name, [round(math.degrees(a)) for a in j.minimum_rotation], [round(math.degrees(a)) for a in j.maximum_rotation],
        [round(s) for s in j.spring_rotation_constant]) for j in bj]
    hj = [j for j in js if "hair" in j.name.lower()]
    if hj:
        out["hair joints"] = "%d, rot limit %s deg, spring rot %s" % (
            len(hj), sorted({round(math.degrees(hj[0].maximum_rotation[0]))} | {round(math.degrees(j.maximum_rotation[0])) for j in hj})[:4],
            sorted({round(j.spring_rotation_constant[0]) for j in hj})[:4])
    frames = [(f.name, len(f.data)) for f in m.display]
    out["display frames"] = frames
    return out


a, b = sys.argv[1], sys.argv[2]
fa, fb = facts(a), facts(b)
for k in list(dict.fromkeys(list(fa) + list(fb))):
    print("%-22s | %s" % (k, fa.get(k, "-")))
    print("%-22s | %s" % ("", fb.get(k, "-")))
