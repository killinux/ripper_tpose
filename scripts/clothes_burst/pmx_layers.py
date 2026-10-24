"""Several outfits of one character in ONE PMX, worn one over another, taken off one by one with a slider per step -
so a burst can blow them off layer by layer (outer outfit -> the one under it -> ... -> nude).

The outer model is the base: its skeleton, head, hair, expressions, rigid bodies and joints stay as they are.  From
each inner model only the named materials are copied in (its outfit, its own skin pieces, or a whole nude body), with
pmx_add_nude.add_nude(): bones by name, the mesh posed onto the outer model's skeleton where the rigs differ (limb
roots onto the outer joints, normals turned with the surface), weights moved onto the outer bones; the model's own
weights are kept (no SDEF rings, no finger clean-up - these are game weights).  Inner layers follow the outer outfit in
the draw order, outermost first; a name the file has already gets _<layer>.

One layer shows at a time; the sliders are STEPS, raised in order and left up - all of them at 1 = the innermost layer:
  - inner layers' materials: alpha 0 in the file (edge alpha 0 too) - the file opens wearing the outer outfit;
  - step k <n>_<name>脱ぎ (group, in the 表情 display frame) takes layer k off and puts layer k+1 on:
      <layer k>非表示 (outer layer: material morph, alpha x 0) or <layer k>消去 (an inner layer: material morph adding
        the alpha back off - MMD computes a material morph as base x multiplies + adds, so the alpha the previous step
        ADDED cannot be multiplied away; 1 - 1 = 0),
      <layer k>収納 (vertex morph: the layer pulled to 10 % of its distance from the axis of the standard bone it
        follows - inside the body.  Hidden anyway; it keeps Blender's alpha-hashed hidden surfaces off the skin now
        on top, and a step raised out of order leaves the layer inside the body instead of at negative alpha on it),
      <layer k+1>表示 (material morph: that layer's alpha added back);
  - the parts are not in the display frame (a VMD can still key them).
Each step is what a layer-by-layer burst keys at its stage: the outfit's fragments fly while the next layer appears.
Each copied material's comment says layer=<layer> (and source=<its name in the inner model> when renamed).

  python pmx_layers.py <outer.pmx> --outer "<materials>" [--outer-name A]
                       --layer <name> <inner.pmx> "<materials>" [--layer ...]  (outermost first)
                       --out <merged.pmx> [--model-name "..."] [--stow 0.1] [--pmx-module ...]

<materials>: comma separated names, shell wildcards allowed.  Morph names go into VMD files as Shift-JIS, 15 bytes:
keep layer names short and in characters Shift-JIS has (A, B, 裸体).  Textures are copied under the output's folder.
Prints PMX_LAYERS=<json>.
"""
import argparse
import json
import os
import sys

import numpy as np  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pmx_add_nude import add_nude, material_ranges, pose_transforms, weights_of  # noqa: E402
from pmx_nude_switch import OTHER, _offset, pick, pmx_module, save  # noqa: E402

HIDE, SHOW, ERASE, STOW, STEP = "%s非表示", "%s表示", "%s消去", "%s収納", "%d_%s脱ぎ"


def pose_size(outer, model):
    """(largest joint move in units, largest bone turn in degrees) posing model onto outer's skeleton takes.  On the
    same rig it is nothing, and the model's own normals are kept: turning them with the surface recomputes them from
    the geometry, which flips the odd one where the mesh is degenerate (Reika B's navel: 90 degrees)."""
    poses, _turned, _report = pose_transforms(outer, model)
    move = max(float(np.linalg.norm(h2 - h)) for _R, h, h2 in poses)
    turn = max(float(np.degrees(np.arccos(np.clip((np.trace(R) - 1) / 2, -1.0, 1.0)))) for R, _h, _h2 in poses)
    return move, turn


def sjis_bytes(name):
    try:
        return len(name.encode("shift_jis"))
    except UnicodeEncodeError:
        return None


def note(mat, text):
    mat.comment = (mat.comment + "\n" if mat.comment else "") + text


def layer_vertices(model, mats):
    """vertices used by the materials mats and by no other material (only those may be moved)"""
    ranges = material_ranges(model)
    mine, others = set(), set()
    for k, (s, e) in enumerate(ranges):
        target = mine if k in mats else others
        for f in model.faces[s:e]:
            target.update(f)
    return sorted(mine - others), len(mine & others)


def _core_next():
    """MMD standard bone -> the joints its axis runs to (first one the model has); "tail" = the bone's own tail"""
    out = {"上半身": ["上半身2", "首"], "上半身1": ["上半身2"], "上半身2": ["上半身3", "首"], "上半身3": ["首"],
           "首": ["頭"], "頭": [], "下半身": ["HIPS"]}
    for s in ("左", "右"):
        out.update({s + "肩": [s + "腕"], s + "腕": [s + "ひじ"], s + "ひじ": [s + "手首"], s + "手首": [s + "中指１"],
                    s + "足": [s + "ひざ"], s + "ひざ": [s + "足首"], s + "足首": [s + "つま先"],
                    s + "足D": [s + "ひざD", s + "ひざ"], s + "ひざD": [s + "足首D", s + "足首"],
                    s + "足首D": [s + "足先EX", s + "つま先"], s + "胸": ["tail"],
                    s + "親指０": [s + "親指１"], s + "親指１": [s + "親指２"], s + "親指２": ["tail"]})
        for f in ("人指", "中指", "薬指", "小指"):
            out.update({s + f + "０": [s + f + "１"], s + f + "１": [s + f + "２"], s + f + "２": [s + f + "３"],
                        s + f + "３": ["tail"]})
    return out


CORE_NEXT = _core_next()


def core_segments(model):
    """per bone: the axis (a, b) of the MMD standard bone it is or hangs under - joint to next joint, deep inside the
    body.  Helper bones (game rigs have many, some just under the skin) take their standard ancestor's axis; a pull
    toward a helper's own segment left boot and stocking pieces showing on the shins of the nude."""
    loc = np.array([b.location for b in model.bones], dtype=np.float64)
    by_name = {b.name: i for i, b in enumerate(model.bones)}

    def tail_of(i):
        c = model.bones[i].displayConnection
        if isinstance(c, int):
            return loc[c] if c >= 0 else loc[i]
        return loc[i] + np.array(c, dtype=np.float64) if c is not None else loc[i]

    axis = {}
    for name, nexts in CORE_NEXT.items():
        i = by_name.get(name)
        if i is None:
            continue
        b = loc[i]
        for n in nexts:
            if n == "tail":
                b = tail_of(i)
                break
            if n == "HIPS" and "左足" in by_name and "右足" in by_name:
                b = (loc[by_name["左足"]] + loc[by_name["右足"]]) / 2
                break
            if n in by_name:
                b = loc[by_name[n]]
                break
        axis[i] = (loc[i], b)
    out = {}
    for i in range(len(model.bones)):
        j, hops = i, 0
        while j is not None and j >= 0 and j not in axis and hops < 64:
            j, hops = model.bones[j].parent, hops + 1
        out[i] = axis.get(j, (loc[i], loc[i]))
    return out


def stow_morph(pmx, model, verts, name, name_e, factor):
    """vertex morph pulling verts to `factor` of their distance from the nearest standard-bone axis among the bones
    they are weighted to - inside the body, following it in any pose"""
    seg = core_segments(model)
    m = pmx.VertexMorph(name, name_e, OTHER)
    depth = []
    for vi in verts:
        p = np.array(model.vertices[vi].co, dtype=np.float64)
        best = None
        for b, _w in weights_of(pmx, model.vertices[vi]):
            a, t = seg[b]
            d = t - a
            ll = float(d @ d)
            s = 0.0 if ll < 1e-12 else float(np.clip((p - a) @ d / ll, 0.0, 1.0))
            q = a + s * d
            dist = float(np.linalg.norm(p - q))
            if best is None or dist < best[0]:
                best = (dist, q)
        if best is None:
            continue
        o = pmx.VertexMorphOffset()
        o.index = vi
        o.offset = [float(x) for x in (best[1] - p) * (1.0 - factor)]
        m.offsets.append(o)
        depth.append(best[0] * (1.0 - factor))
    return m, {"vertices": len(m.offsets), "pulled_cm_median": round(float(np.median(depth)) * 8, 2) if depth else 0,
               "pulled_cm_max": round(float(max(depth)) * 8, 2) if depth else 0}


def build(pmx, outer, outer_name, outer_mats, layers, factor=0.1):
    """layers = [(name, model, material indices)] outermost first; outer is changed in place.  Returns a report."""
    report = {"outer": {"name": outer_name, "materials": [outer.materials[k].name for k in outer_mats]}, "layers": []}
    for k in outer_mats:
        note(outer.materials[k], "layer=%s" % outer_name)
    after = max(outer_mats)
    shown = []                                      # (layer name, its material indices in outer)
    for name, model, take in layers:
        before = {m.name for m in outer.materials}
        move, turn = pose_size(outer, model)
        normals = "bones" if move < 1e-3 and turn < 0.5 else "surface"
        rep, new = add_nude(pmx, outer, model, take, snaps=[], overrides={}, after=after, suffix="_" + name,
                            donor=None, sdef_joints=(), finger_cm=0, normals=normals)
        rep["normals"] = dict(rep.get("normals") or {}, turned_with=normals, pose_move_cm=round(move * 8, 3),
                              pose_turn_deg=round(turn, 3))
        for k_in, k_out in zip(take, new):
            mat = outer.materials[k_out]
            src = model.materials[k_in].name
            note(mat, "layer=%s" % name + ("; source=%s" % src if mat.name != src else ""))
        shown.append((name, new))
        after = new[-1]
        report["layers"].append({"name": name, "materials": [outer.materials[k].name for k in new],
                                 "renamed": {model.materials[a].name: outer.materials[b].name for a, b in zip(take, new)
                                             if outer.materials[b].name != model.materials[a].name},
                                 "posed": {k: rep.get(k) for k in ("spine_spread", "bones_turned", "weights", "normals")},
                                 "vertices_added": rep["vertices_added"], "faces_added": rep["faces_added"],
                                 "clashed_before": sorted(before & {model.materials[k].name for k in take})})
    # every layer's materials (outer first), the inner ones hidden in the file
    layer_mats = [(outer_name, list(outer_mats))] + shown
    mats = outer.materials
    alpha, edge = {}, {}
    for _name, idx in shown:
        for k in idx:
            alpha[k], edge[k] = float(mats[k].diffuse[3]), float(mats[k].edge_color[3])
            mats[k].diffuse = list(mats[k].diffuse[:3]) + [0.0]
            mats[k].edge_color = list(mats[k].edge_color[:3]) + [0.0]
    names = [n for n, _ in layer_mats]
    wanted = [HIDE % outer_name] + [STOW % n for n in names[:-1]] + [SHOW % n for n in names[1:]] + \
        [ERASE % n for n in names[1:-1]] + [STEP % (i + 1, n) for i, n in enumerate(names[:-1])]
    have = {m.name for m in outer.morphs}
    clash = [n for n in wanted if n in have]
    if clash:
        raise SystemExit("the outer model has morphs named %s already" % clash)
    long = {n: sjis_bytes(n) for n in wanted if sjis_bytes(n) is None or sjis_bytes(n) > 15}
    if long:
        raise SystemExit("morph names a VMD cannot hold (Shift-JIS, 15 bytes): %s" % long)
    index = {}

    def add(m):
        index[m.name] = len(outer.morphs)
        outer.morphs.append(m)

    hide = pmx.MaterialMorph(HIDE % outer_name, "Hide layer %s" % outer_name, OTHER)
    hide.offsets = [_offset(pmx, k, 0) for k in outer_mats]
    add(hide)
    report["stow"] = {}
    for n, idx in layer_mats[:-1]:
        verts, shared = layer_vertices(outer, set(idx))
        m, rep = stow_morph(pmx, outer, verts, STOW % n, "Stow layer %s" % n, factor)
        rep["shared_with_other_materials_not_moved"] = shared
        report["stow"][n] = rep
        add(m)
    for n, idx in shown:
        m = pmx.MaterialMorph(SHOW % n, "Show layer %s" % n, OTHER)
        m.offsets = [_offset(pmx, k, 1, alpha[k], edge[k]) for k in idx]
        add(m)
    for n, idx in shown[:-1]:
        # the alpha <n>表示 added, taken away again (an add cannot be multiplied away): 1 - 1 = 0 when taken off in order
        m = pmx.MaterialMorph(ERASE % n, "Erase layer %s" % n, OTHER)
        m.offsets = [_offset(pmx, k, 1, -alpha[k], -edge[k]) for k in idx]
        add(m)
    steps = []
    for i, n in enumerate(names[:-1]):
        nxt = names[i + 1]
        g = pmx.GroupMorph(STEP % (i + 1, n), "Take off layer %s" % n, OTHER)
        parts = ([HIDE % n] if i == 0 else [ERASE % n]) + [STOW % n, SHOW % nxt]
        for part in parts:
            o = pmx.GroupMorphOffset()
            o.morph, o.factor = index[part], 1.0
            g.offsets.append(o)
        add(g)
        steps.append((g.name, parts))
    frame = next((d for d in outer.display if d.isSpecial and d.name in ("表情", "Exp")), None) or \
        next((d for d in outer.display if d.name in ("表情", "Exp")), None)
    if frame is not None:
        frame.data += [(1, index[s]) for s, _p in steps]
    report["steps"] = {s: p for s, p in steps}
    report["morphs"] = list(index)
    report["display_frame"] = frame.name if frame is not None else None
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("outer")
    ap.add_argument("--outer", dest="outer_mats", required=True, help="the outer model's outfit materials")
    ap.add_argument("--outer-name", default="A")
    ap.add_argument("--layer", nargs=3, action="append", required=True, metavar=("NAME", "PMX", "MATERIALS"),
                    help="an inner layer: its name, its PMX, the materials taken from it (outermost first)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model-name", default="")
    ap.add_argument("--model-name-e", default="")
    ap.add_argument("--stow", type=float, default=0.1,
                    help="a taken-off layer is pulled to this share of its distance from its bones (default 0.1)")
    ap.add_argument("--pmx-module", default="")
    a = ap.parse_args()
    pmx = pmx_module(a.pmx_module)
    outer = pmx.load(a.outer)
    outer_mats = pick(outer, a.outer_mats, "--outer")
    layers = []
    for name, path, mats in a.layer:
        model = pmx.load(path)
        layers.append((name, model, pick(model, mats, "--layer %s" % name)))
    report = build(pmx, outer, a.outer_name, outer_mats, layers, a.stow)
    if a.model_name:
        outer.name = a.model_name
    if a.model_name_e:
        outer.name_e = a.model_name_e
    names = [a.outer_name] + [l["name"] for l in report["layers"]]
    lines = ["打开时穿的是 %s（%s）。" % (names[0], "、".join(report["outer"]["materials"]))]
    for i, n in enumerate(names[:-1]):
        lines.append("%s 拉到 1：脱掉 %s，换成 %s。" % (STEP % (i + 1, n), n, names[i + 1]))
    outer.comment = (outer.comment.rstrip() + "\n\n" if outer.comment.strip() else "") + \
        "几层衣服叠在一个模型里，按顺序一层一层脱（scripts/clothes_burst/pmx_layers.py）：\n" + "\n".join(lines) + \
        "\n表情面板里只有这几个滑块，按顺序拉，拉上去的不用放回；全拉到 1 是最里面那层。"
    report["textures_copied"] = save(pmx, outer, a.outer, a.out)
    report["written"] = os.path.abspath(a.out)
    report["counts"] = {"vertices": len(outer.vertices), "faces": len(outer.faces), "materials": len(outer.materials),
                        "bones": len(outer.bones), "morphs": len(outer.morphs), "rigid_bodies": len(outer.rigids),
                        "joints": len(outer.joints), "textures": len(outer.textures)}
    print("PMX_LAYERS=" + json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
