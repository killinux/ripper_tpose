"""Which meshes, materials and textures the renderers of a ROE bundle draw, and which bundle each lives in.

    python inspect_bundle_renderers.py scene_meta3d_gachaintro.ab           # the gacha's opening scene
    python inspect_bundle_renderers.py gacha_video_prefab_pc_gacha01.ab
    python inspect_bundle_renderers.py <bundle> --roots                     # + its root objects and their renderers

Made for the gacha intro girl (pc_gacha01, 2026-10-25): a model put together from several characters' parts whose
own bundle holds placeholder materials (default_material_bare) - the game's real assignment sits on the renderers of
the scene / prefab that shows it, in other characters' bundles.  This prints that assignment; export_gacha_model.py
takes its bundle list from it.

Bundles point at each other by CAB name.  The index CAB -> bundle file of every chara_* / gacha_* / accessory_* /
scene_* bundle (install dir + download cache, the newer copy wins) is built on first use - a few minutes - and kept
in --index (default %TEMP%\\roe_cab_index.json; bundles added since are indexed on the next run)."""
import argparse
import json
import os
import sys
import tempfile

import UnityPy

GAME = r"D:\Program Files (x86)\Steam\steamapps\common\Rise of Eros\RiseOfEros_Data\StreamingAssets\AssetBundles"
DOWNLOADS = os.path.join(os.path.expanduser("~"), "AppData", "LocalLow", "Pinkcore", "Rise of Eros", "AssetBundles")
PREFIXES = ("chara_", "gacha_", "accessory_", "scene_")


def inventory():
    found = {}
    for root in (GAME, DOWNLOADS):
        if not os.path.isdir(root):
            continue
        for name in os.listdir(root):
            if name.endswith(".ab"):
                path = os.path.join(root, name)
                if name not in found or os.path.getmtime(path) > os.path.getmtime(found[name]):
                    found[name] = path
    return found


def cab_index(bundles, path):
    index = {}
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            index = json.load(fh)
    known = set(index.values())
    todo = [n for n in bundles if n.startswith(PREFIXES) and n not in known]
    for i, name in enumerate(todo):
        if i % 500 == 0:
            print("indexing %d / %d bundles" % (i, len(todo)), file=sys.stderr)
        try:
            # env.files is keyed by the bundle's own path; the CAB names are the files inside it
            for bundle in UnityPy.load(bundles[name]).files.values():
                for key in getattr(bundle, "files", {}):
                    index[key.lower().split(".")[0]] = name
        except Exception as exc:  # noqa: BLE001 - a broken bundle only costs its own entries
            print("skip %s: %s" % (name, exc), file=sys.stderr)
    if todo:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(index, fh)
    return index


def externals(path, index):
    out = []
    for sf in UnityPy.load(path).assets:
        for e in getattr(sf, "externals", []):
            cab = e.path.split("/")[-1].lower().split(".")[0]
            out.append(index.get(cab))
    return [b for b in out if b]


def with_deps(name, bundles, index, depth=3, seen=None):
    seen = {} if seen is None else seen
    if name in seen or depth < 0 or name not in bundles or (seen and not name.startswith(("chara_", "gacha_"))):
        return seen
    seen[name] = bundles[name]
    for dep in externals(bundles[name], index):
        with_deps(dep, bundles, index, depth - 1, seen)
    return seen


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("bundle")
    ap.add_argument("--index", default=os.path.join(tempfile.gettempdir(), "roe_cab_index.json"))
    ap.add_argument("--roots", action="store_true", help="also list the root objects and their renderers")
    ap.add_argument("--all", action="store_true",
                    help="every renderer; default: the skinned ones (the characters - a scene's furniture is static "
                         "MeshRenderers whose env_* bundles are not loaded)")
    args = ap.parse_args()
    bundles = inventory()
    if args.bundle not in bundles:
        raise SystemExit("no such bundle: %s" % args.bundle)
    index = cab_index(bundles, args.index)
    deps = with_deps(args.bundle, bundles, index)
    print("bundles loaded: %d (%s + chara_ / gacha_ dependencies)" % (len(deps), args.bundle))
    own = {sf.name for sf in UnityPy.load(bundles[args.bundle]).assets}
    env = UnityPy.load(*deps.values())

    def where(obj):
        return index.get(obj.assets_file.name.lower().split(".")[0], obj.assets_file.name)

    for o in env.objects:
        kinds = ("SkinnedMeshRenderer", "MeshRenderer") if args.all else ("SkinnedMeshRenderer",)
        if o.assets_file.name not in own or o.type.name not in kinds:
            continue
        d = o.read()
        try:
            go = d.m_GameObject.read().m_Name
        except Exception:  # noqa: BLE001
            go = "?"
        print("%s %s" % (o.type.name, go))
        if o.type.name == "SkinnedMeshRenderer":
            try:
                mo = d.m_Mesh.deref()
                m = mo.read()
                print("    mesh %s (%d vertices) [%s]" % (m.m_Name, m.m_VertexData.m_VertexCount, where(mo)))
            except Exception as exc:  # noqa: BLE001
                print("    mesh ? (%s)" % exc)
        for mp in d.m_Materials:
            try:
                mo = mp.deref()
                mat = mo.read()
                print("    material %s [%s]" % (mat.m_Name, where(mo)))
                for key, tex in mat.m_SavedProperties.m_TexEnvs:
                    if tex.m_Texture.m_PathID:
                        try:
                            to = tex.m_Texture.deref()
                            print("        %s = %s [%s]" % (key, to.read().m_Name, where(to)))
                        except Exception as exc:  # noqa: BLE001
                            print("        %s = ? (%s)" % (key, exc))
            except Exception as exc:  # noqa: BLE001
                print("    material ? (%s)" % exc)
    if args.roots:
        transforms = {o.path_id: o.read() for o in env.objects
                      if o.assets_file.name in own and o.type.name == "Transform"}
        for t in transforms.values():
            if t.m_Father and t.m_Father.path_id:
                continue
            try:
                print("root %s (%d children)" % (t.m_GameObject.read().m_Name, len(t.m_Children)))
            except Exception:  # noqa: BLE001
                pass


if __name__ == "__main__":
    main()
