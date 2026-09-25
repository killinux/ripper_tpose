"""Export HoneySelect 2 models to .blend (+ optional FBX) straight from the asset bundles.

    python export_model.py --item fo_top:12                  # one list item on its own bones
    python export_model.py --item so_hair_b:9 --item ao_glasses:0
    python export_model.py --body female                     # nude base body + default head
    python export_model.py --card HS2_ill_F_000.png          # a character card, dressed
    python export_model.py --card HS2_ill_F_000.png --nude   # ... without clothes / accessories
    python export_model.py --all-cards [--nude]              # every card in UserData/chara
    python export_model.py --all-items --group hair          # batch a whole group/category

Common options: --out D:\\hs2_exports  --fbx  --no-preview  --no-blend (scene.json only)
                --state half (clothes in their half-undressed state)  --force

Item refs are `<list key>:<id>` or `<categoryNo>:<id>` exactly as list_models.py prints them.
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hs2_bundle  # noqa: E402
import hs2_data  # noqa: E402

BLENDER_DEFAULT = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
HERE = os.path.dirname(os.path.abspath(__file__))

HEAD_ROLES = {"o_head": "skin_head", "o_eyebase_l": "eye", "o_eyebase_r": "eye", "o_eyelashes": "eyelash",
              "o_eyeshadow": "eyeshadow", "o_namida": "tear", "o_tooth": "tooth", "o_tang": "tongue"}
# HS2 default skin colour: a card skinColor is applied as its ratio to this
DEFAULT_SKIN = (0.78, 0.683, 0.624)
BODY_SKIP = {"female": ("o_tang", "cm_o_dan00", "cm_o_dan_f", "o_body_cm"),
             "male": ("o_tang", "o_body_cf", "o_mnpa", "o_mnpb")}


def safe(text):
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in text).strip("_") or "x"


class Builder:
    def __init__(self, root, lists, deps, work_dir, state="full"):
        self.root, self.lists = root, lists
        self.bundles = hs2_bundle.Bundles(root, deps)
        self.scene = hs2_bundle.Scene(self.bundles, os.path.join(work_dir, "textures"))
        self.state = state
        self.sex = None
        self.sources = []

    def row(self, cat, item_id):
        row = self.lists.get(cat, {}).get(item_id)
        if row is None:
            raise KeyError("no list row %s:%d" % (hs2_data.MODEL_CATEGORIES.get(cat, (cat,))[0], item_id))
        return row

    def list_texture(self, cat, item_id, column):
        row = self.lists.get(cat, {}).get(item_id)
        if not row:
            return None
        bundle, tex = (row.get("MainAB") or "").strip(), (row.get(column) or "").strip()
        if not bundle or bundle == "0" or not tex or tex == "0":
            return None
        try:
            t = self.bundles.texture(bundle, tex)
        except FileNotFoundError:
            return None
        return self.scene.save_texture(t, column.replace("Tex", "").replace("NormalMap", "_BumpMap")) if t else None

    # ------------------------------------------------------------------ pieces
    def body(self, sex, nude_body=True):
        self.sex = sex
        info = hs2_data.BODIES[sex]
        skel = self.bundles.prefab(hs2_data.BASE_BUNDLE, info["skeleton"])
        self.scene.place(skel, "body")
        t = self.bundles.prefab(hs2_data.BASE_BUNDLE, info["prefab"])
        mapping, rends = self.scene.place(t, "bodymesh", merge=True)
        role = lambda n: "skin_body" if n.lower().startswith("o_body") else ("nipple" if n.lower().startswith("o_mnp") else "body")
        self.scene.add_renderers(rends, mapping, "body_" + sex, role, skip=BODY_SKIP[sex])
        hb = self.bundles.prefab(hs2_data.BASE_BUNDLE, info["head_bone"])
        self.scene.place(hb, "headbone", anchor="cf_J_Head_s")
        self.sources.append({"role": "body", "ref": "body:" + sex, "prefab": info["prefab"]})

    def head(self, head_id):
        cat = hs2_data.BODIES[self.sex]["head_cat"]
        row = self.row(cat, head_id)
        t = self.bundles.prefab(row["MainAB"], row["MainData"])
        if t is None:
            raise KeyError("prefab %s not in %s" % (row["MainData"], row["MainAB"]))
        mapping, rends = self.scene.place(t, "head", anchor="cf_J_Head_s", merge=True)
        self.scene.add_renderers(rends, mapping, "head", lambda n: HEAD_ROLES.get(n.lower(), "face"))
        self.sources.append({"role": "head", "ref": "%s:%d" % (hs2_data.MODEL_CATEGORIES[cat][0], head_id),
                             "prefab": row["MainData"], "name": hs2_data.display_name(row)})

    def item(self, cat, item_id, role_name, anchor=None, extra=None, standalone=False):
        extra = extra or {}
        row = self.row(cat, item_id)
        if not hs2_data.is_model_row(row):
            return None
        key, _sex, group, _label = hs2_data.MODEL_CATEGORIES[cat]
        t = self.bundles.prefab(row["MainAB"], row["MainData"])
        if t is None:
            self.scene.warnings.append("%s:%d prefab %s not found in %s" % (key, item_id, row["MainData"], row["MainAB"]))
            return None
        colors, hide, override = {}, set(), None
        if group == "clothes":
            hide, defaults = hs2_bundle.clothes_hidden_paths(t, self.state)
            colors.update(defaults)
            info = extra.get("clothes")
            if info:
                for i, ci in enumerate(info.get("colorInfo", [])[:3]):
                    colors["color%d" % (i + 1)] = ci["baseColor"]
                ci0 = (info.get("colorInfo") or [{}])[0]
                if "glossPower" in ci0:
                    colors["gloss"] = ci0["glossPower"]
                if "metallicPower" in ci0:
                    colors["metallic"] = ci0["metallicPower"]
            merge, place_anchor = not standalone, None
        elif group == "hair":
            info = extra.get("hair")
            if info:
                colors.update({"base_color": info.get("baseColor"), "top_color": info.get("topColor"),
                               "under_color": info.get("underColor")})
                for i, ci in enumerate(info.get("acsColorInfo", [])[:4]):
                    colors["acs_color%d" % (i + 1)] = ci.get("color")
            merge = False
            place_anchor = None if standalone else (anchor or "N_hair_Root")
        elif group == "accessory":
            colors.update(hs2_bundle.component_defaults(t, ("CmpAccessory",)))
            for k in list(colors):
                if k.lower().startswith("defcolor0"):
                    colors["color%s" % k[-1]] = colors.pop(k)
            info = extra.get("accessory")
            if info:
                for i, ci in enumerate(info.get("colorInfo", [])[:4]):
                    colors["color%d" % (i + 1)] = ci.get("color")
                move = info.get("addMove")
                if isinstance(move, list) and len(move) == 3 and isinstance(move[2], list):
                    override = _add_move_override(move[2])
            parent = (extra.get("accessory") or {}).get("parentKey") or (row.get("Parent") or "").strip()
            merge = False
            place_anchor = None if standalone else (parent if parent in self.scene.nodes else None)
            if not standalone and place_anchor is None:
                self.scene.warnings.append("%s:%d parent node %r missing, left at origin" % (key, item_id, parent))
        else:
            merge, place_anchor = not standalone, None
        tag = safe(role_name)
        mapping, rends = self.scene.place(t, tag, anchor=place_anchor, merge=merge,
                                          local_override=override, hide_paths=hide)
        role_fn = {"clothes": lambda n: "clothes", "accessory": lambda n: "accessory",
                   "hair": lambda n: "accessory" if "_acs" in n.lower() else "hair",
                   "head": lambda n: HEAD_ROLES.get(n.lower(), "face")}[group]
        self.scene.add_renderers(rends, mapping, tag, role_fn, colors=colors)
        if group == "clothes":
            self._clothes_masks(cat, item_id, row, tag)
        src = {"role": role_name, "ref": "%s:%d" % (key, item_id), "prefab": row["MainData"],
               "bundle": row["MainAB"], "name": hs2_data.display_name(row)}
        self.sources.append(src)
        return src

    def _clothes_masks(self, cat, item_id, row, tag):
        """The colour-region masks (`*_mc`) are not in the prefab materials: ChaControl puts
        the list row's ColorMaskTex (02/03 for the second/third renderer set) in at runtime."""
        sets = [("MainTex", "ColorMaskTex"), ("MainTex02", "ColorMask02Tex"), ("MainTex03", "ColorMask03Tex")]
        mats = [m for m in self.scene.materials.values() if m["source"] == tag]
        for main_col, mask_col in sets:
            main_name = (row.get(main_col) or "").strip()
            mask = self.list_texture(cat, item_id, mask_col)
            if not mask:
                continue
            for m in mats:
                cur = os.path.splitext(m["textures"].get("_MainTex", ""))[0]
                if main_col == "MainTex" and (not main_name or main_name == "0" or cur.startswith(main_name) or len(mats) == 1):
                    m["textures"].setdefault("_ColorMask", mask)
                elif main_name and main_name != "0" and cur.startswith(main_name):
                    m["textures"]["_ColorMask"] = mask

    # ------------------------------------------------------------------ skin / makeup from lists
    def skin(self, face=None, body=None):
        """Skin, makeup and eyes the way ChaControl composites them, as material overlays.

        Card ids pick the list textures; without a card the prefab materials' own textures
        and colours are used.  The overlay textures are channel-packed masks (see
        docs/honey-select-2-extraction.md): eyebrow / underhair / eyelash min(RGB), areola and iris B.
        """
        sex = self.sex
        face = face or {}
        body = body or {}
        mats = self.scene.materials
        by_role = {}
        for key, m in mats.items():
            by_role.setdefault(m["role"], []).append(m)

        def lt(cat, item_id, column="AddTex"):
            return self.list_texture(cat, int(item_id), column) if item_id is not None else None

        def col(card_value, *fallbacks):
            for v in (card_value,) + fallbacks:
                if v:
                    return list(v)
            return None

        tint = None
        if body.get("skinColor"):
            lin = lambda v: v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4  # noqa: E731
            tint = [min(1.6, lin(c) / lin(d)) for c, d in zip(body["skinColor"][:3], DEFAULT_SKIN)]
        for m in by_role.get("skin_head", []):
            tex = m["textures"]
            if "skinId" in face:
                main = lt(hs2_data.CAT_SKIN_FACE[sex], face["skinId"], "MainTex")
                if main:
                    tex["_MainTex"] = main
            brow = lt(hs2_data.CAT_EYEBROW, face.get("eyebrowId")) or tex.get("_Texture3")
            brow_col = col(face.get("eyebrowColor"), m["colors"].get("_EyebrowColor"), [0.3, 0.24, 0.2, 1.0])
            m["overlays"] = []
            if brow:
                m["overlays"].append({"label": "eyebrow", "tex": brow, "uv": "UV1", "alpha": "MIN",
                                      "color": brow_col, "strength": brow_col[3] if face else 1.0})
            if tint:
                m["skin_ratio"] = tint
        for m in by_role.get("skin_body", []):
            tex = m["textures"]
            if "skinId" in body:
                main = lt(hs2_data.CAT_SKIN_BODY[sex], body["skinId"], "MainTex")
                if main:
                    tex["_MainTex"] = main
            if "detailId" in body:
                nrm = lt(hs2_data.CAT_DETAIL_BODY[sex], body["detailId"], "NormalMapTex")
                if nrm:
                    tex["_BumpMap"] = nrm
            m["overlays"] = []
            if sex == "female":
                nip = lt(hs2_data.CAT_NIP, body.get("nipId")) or tex.get("_Texture2")
                nip_col = col(body.get("nipColor"), m["colors"].get("_nipcolor"), [0.8, 0.56, 0.52, 1.0])
                if nip:
                    m["overlays"].append({"label": "areola", "tex": nip, "uv": "UV1", "alpha": "B",
                                          "shade": "R", "color": nip_col})
            uh_id = body.get("underhairId")
            uh = lt(hs2_data.CAT_UNDERHAIR, uh_id) if uh_id is not None else tex.get("_Texture3")
            uh_col = col(body.get("underhairColor"), [0.12, 0.1, 0.09, 0.85])
            if uh:
                m["overlays"].append({"label": "underhair", "tex": uh, "uv": "UV2", "alpha": "MIN",
                                      "color": uh_col, "strength": uh_col[3]})
            if tint:
                m["skin_ratio"] = tint
        pupil = (face.get("pupil") or [{}])[0]
        for m in by_role.get("eye", []):
            tex = m["textures"]
            iris = lt(hs2_data.CAT_EYE, pupil.get("pupilId")) or tex.get("_Texture2")
            black = lt(hs2_data.CAT_EYEBLACK, pupil.get("blackId")) or tex.get("_Texture3")
            hl = lt(hs2_data.CAT_EYE_HL, face.get("hlId")) or tex.get("_Texture4")
            hl_col = col(face.get("hlColor"), [1, 1, 1, 0.6])
            m["base_mult"] = col(pupil.get("whiteColor"), m["colors"].get("_Color"), [0.85, 0.85, 0.85, 1])
            m["overlays"] = []
            # the eyeball UV is centred on the cornea; iris and pupil textures are scaled about
            # that centre by the card sliders (0.5 = texture as drawn; approximation of ChaControl)
            iw = 1.0 / (0.6 + 0.8 * float(pupil.get("pupilW", 0.5)))
            ih = 1.0 / (0.6 + 0.8 * float(pupil.get("pupilH", 0.5)))
            dy = -0.03 - (float(face.get("pupilY", 0.5)) - 0.5) * 0.3
            bw = iw * 2.4 / (0.6 + 0.8 * float(pupil.get("blackW", 0.5)))
            bh = ih * 2.4 / (0.6 + 0.8 * float(pupil.get("blackH", 0.5)))
            if iris:
                m["overlays"].append({"label": "iris", "tex": iris, "alpha": "B", "shade": "R", "st": _centred(iw, ih, dy),
                                      "color": col(pupil.get("pupilColor"), m["colors"].get("_Color2"), [0.35, 0.28, 0.25, 1])})
            if black:
                m["overlays"].append({"label": "pupil", "tex": black, "alpha": "A", "st": _centred(bw, bh, dy * bh / ih),
                                      "color": col(pupil.get("blackColor"), m["colors"].get("_Color3"), [0, 0, 0, 1])})
            if hl:
                m["overlays"].append({"label": "highlight", "tex": hl, "alpha": "MIN", "color": [1, 1, 1, 1],
                                      "strength": hl_col[3]})
        for m in by_role.get("eyelash", []):
            lash = lt(hs2_data.CAT_EYELASH, face.get("eyelashesId"))
            if lash:
                m["textures"]["_MainTex"] = lash
            m["base_solid"] = col(face.get("eyelashesColor"), m["colors"].get("_Color"), [0.1, 0.1, 0.1, 1])
            m["alpha_channel"] = "MIN"
        for m in by_role.get("eyeshadow", []):
            # o_eyeshadow is the eyelid's shadow on the eyeball (c_m_eyekage), not makeup:
            # a dark shell masked by the texture alpha
            m["base_solid"] = m["colors"].get("_Color") or [0.2, 0.2, 0.2, 1]
            m["alpha_channel"] = "A"
            m["opacity"] = 0.6
        for m in by_role.get("tear", []):
            m["opacity"] = 0.0
        # the separate nipple meshes share the body's UV0 island: give them the body material
        body_key = next((k for k, m in mats.items() if m["role"] == "skin_body"), None)
        if body_key:
            for part in self.scene.parts:
                if part["role"] == "nipple":
                    part["materials"] = [body_key] * len(part["materials"])
            for key in [k for k, m in mats.items() if m["role"] == "nipple"]:
                if not any(key in p["materials"] for p in self.scene.parts):
                    del mats[key]


def _centred(sx, sy, dy=0.0):
    """Mapping-node scale/offset that scales a texture about the UV centre (0.5, 0.5)."""
    return [sx, sy, 0.5 - 0.5 * sx, 0.5 - 0.5 * sy + dy * sy]


def _add_move_override(vectors):
    """Card accessory offsets: N_move gets [pos, rot, scale] #0, N_move2 #1 (added to the prefab's own)."""
    import numpy as np

    out = {}
    for i, node in enumerate(("N_move", "N_move2")):
        if len(vectors) < i * 3 + 3:
            break
        pos, rot, scl = vectors[i * 3:i * 3 + 3]
        if not any(abs(v) > 1e-6 for v in pos + rot) and all(abs(v - 1) < 1e-6 for v in scl):
            continue

        def fn(local, pos=pos, rot=rot, scl=scl):
            q = hs2_bundle.euler_quat(rot)
            m = hs2_bundle.trs_matrix(pos, q, scl)
            res = local.copy()
            res[:3, 3] = local[:3, 3] + np.asarray(pos) * 0.1  # card offsets are in 1/10 units (cm)
            res[:3, :3] = local[:3, :3] @ m[:3, :3]
            return res
        out[node] = fn
    return out


# ---------------------------------------------------------------------- jobs

def run_blender(blender, scene_json, blend, fbx, preview, log_path):
    cmd = [blender, "-b", "--factory-startup", "-P", os.path.join(HERE, "build_blend.py"), "--",
           "--scene", scene_json, "--out", blend]
    if fbx:
        cmd.append("--fbx")
    if not preview:
        cmd.append("--no-preview")
    t = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    with open(log_path, "w", encoding="utf-8") as f:
        f.write(proc.stdout)
        f.write(proc.stderr)
    report = None
    for line in proc.stdout.splitlines():
        if line.startswith("HS2_REPORT="):
            report = json.loads(line[len("HS2_REPORT="):])
    if proc.returncode != 0 or report is None:
        tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
        raise RuntimeError("Blender failed (%s):\n%s" % (log_path, tail))
    report["seconds"] = round(time.time() - t, 1)
    return report


def finish(builder, out_dir, name, meta, args):
    meta = dict(meta)
    meta["name"] = name
    meta["sources"] = builder.sources
    scene = builder.scene.write(out_dir, meta)
    line = "%s: %d parts, %d bones, %d materials" % (name, len(scene["parts"]), len(scene["nodes"]), len(scene["materials"]))
    if scene["warnings"]:
        line += ", %d warnings" % len(scene["warnings"])
    print(line, flush=True)
    for w in scene["warnings"][:12]:
        print("   warn: " + w, flush=True)
    if args.no_blend:
        return {"name": name, "dir": out_dir, "status": "scene-only"}
    blend = os.path.join(out_dir, name + ".blend")
    report = run_blender(args.blender, os.path.join(out_dir, "scene.json"), blend, args.fbx,
                         not args.no_preview, os.path.join(out_dir, "build.log"))
    status = "WARN" if report.get("missing_textures") or report.get("skipped") or scene["warnings"] else "PASS"
    print("   %s  %s  (%.1fs)" % (status, blend, report["seconds"]), flush=True)
    return {"name": name, "dir": out_dir, "blend": blend, "status": status, "report": report,
            "warnings": scene["warnings"]}


def export_items(refs, args, root, lists, deps):
    results = []
    for ref in refs:
        cat, item_id = hs2_data.parse_ref(ref)
        key = hs2_data.MODEL_CATEGORIES[cat][0]
        row = lists.get(cat, {}).get(item_id)
        if row is None or not hs2_data.is_model_row(row):
            print("skip %s: not a model row" % ref, flush=True)
            continue
        name = "%s_%03d_%s" % (key, item_id, safe(row["MainData"]))
        group = hs2_data.MODEL_CATEGORIES[cat][2]
        sub = "with_body" if args.with_body else ""
        out_dir = os.path.join(args.out, "items", key, name + (("_" + sub) if sub else ""))
        if not args.force and os.path.isfile(os.path.join(out_dir, name + ".blend")):
            print("have %s" % out_dir, flush=True)
            continue
        b = Builder(root, lists, deps, out_dir, args.state)
        if args.with_body:
            sex = hs2_data.MODEL_CATEGORIES[cat][1]
            b.body("male" if sex == "male" else "female")
            if group == "head":
                b.head(item_id)  # the item *is* the head
            else:
                b.head(hs2_data.BODIES[b.sex]["default_head"])
                b.item(cat, item_id, key, extra={})
            b.skin()
        else:
            b.sex = "male" if hs2_data.MODEL_CATEGORIES[cat][1] == "male" else "female"
            b.item(cat, item_id, key, standalone=True)
            if group == "head":
                b.skin()  # eyes, lashes, eyelid shadow the way the game dresses a bare head
        try:
            results.append(finish(b, out_dir, name, {"kind": "item", "ref": ref, "group": group}, args))
        except Exception as exc:  # noqa: BLE001
            print("   FAIL %s: %s" % (name, exc), flush=True)
            results.append({"name": name, "dir": out_dir, "status": "FAIL", "error": str(exc)})
    return results


def export_body(sex, args, root, lists, deps, head_id=None):
    name = "body_%s" % sex
    out_dir = os.path.join(args.out, "bodies", name)
    b = Builder(root, lists, deps, out_dir, args.state)
    b.body(sex)
    b.head(hs2_data.BODIES[sex]["default_head"] if head_id is None else head_id)
    b.skin()
    return finish(b, out_dir, name, {"kind": "body", "sex": sex}, args)


def export_card(path, args, root, lists, deps):
    card = hs2_data.read_card(path)
    stem = os.path.splitext(os.path.basename(path))[0]
    name = stem + ("_nude" if args.nude else "")
    out_dir = os.path.join(args.out, "cards", name)
    if not args.force and os.path.isfile(os.path.join(out_dir, name + ".blend")):
        print("have %s" % out_dir, flush=True)
        return {"name": name, "dir": out_dir, "status": "have"}
    b = Builder(root, lists, deps, out_dir, args.state)
    b.body(card["sex"])
    for role, cat, item_id, extra in hs2_data.card_parts(card):
        group = hs2_data.MODEL_CATEGORIES[cat][2]
        if role == "head":
            b.head(item_id)
            continue
        if args.nude and group == "clothes":
            continue
        if group == "accessory" and (args.no_accessories or (args.nude and not args.keep_accessories)):
            continue
        try:
            b.item(cat, item_id, role, extra=extra)
        except KeyError as exc:
            b.scene.warnings.append(str(exc))
    b.skin(card["face"], card["body"])
    meta = {"kind": "card", "card": os.path.basename(path), "character": card["name"], "sex": card["sex"],
            "nude": bool(args.nude)}
    return finish(b, out_dir, name, meta, args)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--game", help="HoneySelect 2 folder (default %s or HS2_ROOT)" % hs2_data.GAME_DEFAULT)
    ap.add_argument("--out", default=hs2_data.EXPORTS_DEFAULT)
    ap.add_argument("--blender", default=os.environ.get("BLENDER", BLENDER_DEFAULT))
    ap.add_argument("--item", action="append", default=[], help="list ref, e.g. fo_top:12 (repeatable)")
    ap.add_argument("--all-items", action="store_true", help="every model item (filter with --group/--category)")
    ap.add_argument("--group", choices=["head", "clothes", "hair", "accessory"])
    ap.add_argument("--category", help="list key or categoryNo, e.g. fo_top or 240")
    ap.add_argument("--with-body", action="store_true", help="items: dress them on the default body")
    ap.add_argument("--body", choices=["female", "male"])
    ap.add_argument("--head", type=int, help="--body: head id (default 0)")
    ap.add_argument("--card", action="append", default=[], help="card PNG (path, or file name in UserData/chara/*)")
    ap.add_argument("--all-cards", action="store_true")
    ap.add_argument("--nude", action="store_true", help="cards: leave clothes and accessories off")
    ap.add_argument("--keep-accessories", action="store_true", help="--nude: keep the accessories (glasses, hats, ...)")
    ap.add_argument("--no-accessories", action="store_true", help="cards: leave the accessories off")
    ap.add_argument("--state", choices=["full", "half"], default="full", help="clothes state")
    ap.add_argument("--fbx", action="store_true", help="also write an FBX next to the .blend")
    ap.add_argument("--no-preview", action="store_true")
    ap.add_argument("--no-blend", action="store_true", help="stop after scene.json/parts/textures")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    root = hs2_data.game_root(args.game)
    cache = os.path.join(args.out, "_cache")
    lists = hs2_data.load_lists(root, cache)
    deps = hs2_data.load_manifest_deps(root)
    if not os.path.isfile(args.blender) and not args.no_blend:
        raise SystemExit("Blender not found: %s (pass --blender or --no-blend)" % args.blender)

    results = []
    refs = list(args.item)
    if args.all_items:
        cat_filter = None
        if args.category:
            cat_filter = int(args.category) if args.category.isdigit() else hs2_data.KEY_TO_CATEGORY[args.category]
        for it in hs2_data.model_items(lists):
            if args.group and it["group"] != args.group:
                continue
            if cat_filter is not None and it["category"] != cat_filter:
                continue
            refs.append(it["ref"])
    if refs:
        results += export_items(refs, args, root, lists, deps)
    if args.body:
        results.append(export_body(args.body, args, root, lists, deps, args.head))
    cards = []
    for c in args.card:
        if os.path.isfile(c):
            cards.append(c)
            continue
        for sex in ("female", "male"):
            p = os.path.join(root, "UserData", "chara", sex, c if c.lower().endswith(".png") else c + ".png")
            if os.path.isfile(p):
                cards.append(p)
                break
        else:
            raise SystemExit("card not found: %s" % c)
    if args.all_cards:
        cards += [c["path"] for c in hs2_data.list_cards(root) if "error" not in c]
    for path in cards:
        try:
            results.append(export_card(path, args, root, lists, deps))
        except Exception as exc:  # noqa: BLE001
            print("FAIL %s: %s" % (path, exc), flush=True)
            results.append({"name": os.path.basename(path), "status": "FAIL", "error": str(exc)})
    if not results:
        ap.print_help()
        return 1
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    print("done: " + ", ".join("%s %d" % kv for kv in sorted(summary.items())), flush=True)
    log = os.path.join(args.out, "_exports.jsonl")
    os.makedirs(args.out, exist_ok=True)
    with open(log, "a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps({k: v for k, v in r.items() if k != "report"}, ensure_ascii=False) + "\n")
    return 0 if not summary.get("FAIL") else 2


if __name__ == "__main__":
    sys.exit(main())
