# -*- coding: utf-8 -*-
"""Clothes from HONEY SELECT (the first game, Unity 5.3 asset bundles) worn by a HoneySelect 2 character card.

    python hs1_outfit_export.py --hs1 <folder holding abdata\\> --item <bundle>:<prefab> [--item ...]
           --chara <HS2 card .png | file name in UserData/chara/female> --name <label> [--hide REGEX] [--force]

First use: hankokoli's "gantz suit (female)" (Patreon 42572478, 2020): abdata\\chara\\hankokoli\\gantz_female_suit.unity3d
holds the top, bottom, body / arm suit (panst), gloves and shoes, gantz_female_socks.unity3d the socks.  This machine
has no Honey Select 1, so no HS1 body: the clothes go on the HS2 character instead.

How: every HS1 prefab is placed into the HS2 scene with merge=True, so its cf_J_* bones become the HS2 skeleton's
bones of the same name, and hs2_bundle bakes each skinned vertex as sum w x (HS2 bone world x the HS1 mesh's bind
pose) x v - the clothes follow the HS2 skeleton (a retarget by bones; Illusion kept the bone names and axes from HS1
to AI / HS2).  Objects of the other clothes state (*_b), the body copies the clothes carry (O_body_*, the
uncensor cf_O_unc_*) are left out by name (--hide); 'skin' / 'skin_arm' in this mod are the suit's latex layer, not skin.
The HS2 body is shaped differently from HS1's and pokes through the tight suit: body faces the clothes cover are deleted
afterwards (mask_covered_body.py, what the games' body masks do), then the previews are rendered.
Writes <out>/cards/<name>/ like export_model.py --card.  Prints HS1_OUTFIT={json}.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import export_model as em  # noqa: E402
import hs2_bundle  # noqa: E402
import hs2_data  # noqa: E402

HIDE_DEFAULT = r"(?i)^(o_body_|cf_o_unc|.*_b$|.*_b_|n_bot_n_)"


def hidden_ids(root_t, rx):
    """path ids of the GameObjects under root_t whose names match rx."""
    out, stack = set(), [root_t]
    while stack:
        t = stack.pop()
        go = t.m_GameObject.read()
        if t is not root_t and rx.search(go.m_Name):
            out.add(t.m_GameObject.path_id)
        for c in t.m_Children:
            ct = c.read()
            stack.append(ct)
    return out


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--hs1", required=True, help="folder holding the HS1 mod's abdata\\")
    ap.add_argument("--item", action="append", required=True, help="<bundle rel path>:<prefab name>")
    ap.add_argument("--chara", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--hide", default=HIDE_DEFAULT, help="regex of GameObject names to leave out")
    ap.add_argument("--color", action="append", default=[],
                    help="MATERIAL_REGEX=#RRGGBB: base colour multiplied onto those HS1 materials (the coordinate "
                         "card's colours are not read; hankokoli's suit is black in his previews)")
    ap.add_argument("--unit", type=float, default=10.0,
                    help="HS1 units -> HS2 units (HS1 bind poses: hips at 1.13, HS2 at 11.3)")
    ap.add_argument("--game")
    ap.add_argument("--out", default=hs2_data.EXPORTS_DEFAULT)
    ap.add_argument("--blender", default=os.environ.get("BLENDER", em.BLENDER_DEFAULT))
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)
    args.fbx, args.no_preview, args.no_blend = False, False, False

    root = hs2_data.game_root(args.game)
    lists = hs2_data.load_lists(root, os.path.join(args.out, "_cache"))
    deps = hs2_data.load_manifest_deps(root)
    chara = args.chara
    if not os.path.isfile(chara):
        chara = os.path.join(root, "UserData", "chara", "female", chara if chara.lower().endswith(".png") else chara + ".png")
    card = hs2_data.read_card(chara)
    out_dir = os.path.join(args.out, "cards", args.name)
    if not args.force and os.path.isfile(os.path.join(out_dir, args.name + ".blend")):
        print("have %s" % out_dir, flush=True)
        return
    b = em.Builder(root, lists, deps, out_dir, "full")
    b.body(card["sex"])
    for role, cat, item_id, extra in hs2_data.card_parts(card):
        group = hs2_data.MODEL_CATEGORIES[cat][2]
        if role == "head":
            b.head(item_id)
        elif group == "hair":
            try:
                b.item(cat, item_id, role, extra=extra)
            except KeyError as exc:
                b.scene.warnings.append(str(exc))
    b.skin(card["face"], card["body"])

    hs1 = hs2_bundle.Bundles(os.path.abspath(args.hs1), {})
    rx = re.compile(args.hide)
    placed = []
    for k, spec in enumerate(args.item):
        rel, prefab = spec.rsplit(":", 1)
        t = hs1.prefab(rel, prefab)
        if t is None:
            raise SystemExit("prefab %s not in %s" % (prefab, rel))
        hide = hidden_ids(t, rx)
        tag = "hs1_%02d_%s" % (k, em.safe(prefab))
        b.scene.unit_scale[tag] = args.unit           # HS1 is in metres, HS2 in tenths of a metre
        mapping, rends = b.scene.place(t, tag, merge=True, hide_paths=hide)
        b.scene.add_renderers(rends, mapping, tag, lambda n: "clothes", colors={})
        shown = [go.m_Name for go, _r, _n, hidden in rends if not hidden]
        placed.append({"item": spec, "shown": shown, "hidden": len(rends) - len(shown)})
        b.sources.append({"role": "hs1_clothes", "ref": spec, "prefab": prefab, "bundle": rel})
    colours = []
    for spec in args.color:
        pat, hexc = spec.split("=", 1)
        prx = re.compile(pat)
        rgb = [int(hexc.lstrip("#")[i:i + 2], 16) / 255.0 for i in (0, 2, 4)] + [1.0]
        for key, m in b.scene.materials.items():
            if m["source"].startswith("hs1_") and prx.search(m["name"]):
                m["override"]["base_color"] = m["override"]["color1"] = rgb    # clothes read color1
                colours.append(key)
    meta = {"kind": "card", "card": os.path.basename(chara), "character": card["name"], "sex": card["sex"],
            "hs1_items": placed, "hs1_colours": args.color}
    args.no_preview = True                       # previews after the body mask
    res = em.finish(b, out_dir, args.name, meta, args)
    names = sorted({n for it in placed for n in it["shown"]})
    import subprocess
    cmd = [args.blender, "-b", res["blend"], "--factory-startup", "--python", os.path.join(HERE, "mask_covered_body.py"),
           "--", "--body", "o_body_cf", "--clothes-regex", r"^(%s)(\.\d+)?$" % "|".join(re.escape(n) for n in names),
           "--save", "--preview", os.path.join(out_dir, args.name)]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    line = next((l for l in p.stdout.splitlines() if l.startswith("MASK_BODY=")), None)
    mask = json.loads(line[len("MASK_BODY="):]) if line else {"error": (p.stdout + p.stderr)[-800:]}
    print("HS1_OUTFIT=" + json.dumps({"result": {k: v for k, v in res.items() if k != "report"}, "items": placed,
                                      "coloured": colours, "body_mask": mask}, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:])
