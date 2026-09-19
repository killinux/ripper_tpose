# -*- coding: utf-8 -*-
"""List the component meshes that make up a Rise of Eros 'suit'.

A ROE outfit variant ('suit') is not shipped as one dressed FBX.  It is the
character's nude base body plus a set of clothing component meshes that all
skin to the shared skeleton.  Which components belong to a given suit is
recorded in the tiny stub bundle

    accessory_components_pc_<id>_suit_<suit>.ab

whose root GameObjects reference (by PPtr) the real meshes living in

    chara_components_pc_<id>.ab

This tool reads the stub and prints, one per line, the component object name as
it is exported by AssetStudio splitObjects (the ``lynn_<Area>_<Piece>_obj001``
form), which is also the per-object FBX/dir name.  Feed that list (minus any
pieces you do not want, e.g. an alternate open/closed state or an adult toy) to
``assemble_suit_blender.py --parts``.

Usage:
    python suit_parts.py <stub.ab>
    python suit_parts.py --game <AssetBundles dir> --id j01 --suit prouniform

Needs UnityPy (same dependency the hotelvip / vam tooling uses).
"""
import argparse
import os
import sys

import UnityPy


def _read(pptr):
    try:
        return pptr.read()
    except Exception:
        return None


def _renderer_name(go):
    """Return the mesh object's own name for a stub root GameObject.

    The stub root (``UniformJacket_obj001``) has one descendant carrying a
    Skinned/MeshRenderer whose GameObject name is the ``lynn_<Area>_<Piece>``
    component name — the name AssetStudio uses for that object's FBX.
    """
    def transform_of(g):
        for comp in g.m_Components:
            c = _read(comp.component if hasattr(comp, "component") else comp)
            if c is not None and type(c).__name__ in ("Transform", "RectTransform"):
                return c
        return None

    def walk(g, tr):
        for comp in g.m_Components:
            c = _read(comp.component if hasattr(comp, "component") else comp)
            if c is not None and type(c).__name__ in (
                    "SkinnedMeshRenderer", "MeshRenderer"):
                return g.m_Name
        for child in tr.m_Children:
            ctr = _read(child)
            if ctr is None:
                continue
            cgo = _read(ctr.m_GameObject)
            ctr2 = transform_of(cgo) if cgo else None
            if cgo and ctr2:
                found = walk(cgo, ctr2)
                if found:
                    return found
        return None

    tr = transform_of(go)
    return walk(go, tr) if tr else None


def suit_components(stub_path):
    env = UnityPy.load(stub_path)
    names = []
    for obj in env.objects:
        if obj.type.name != "GameObject":
            continue
        go = obj.read()
        tr = None
        for comp in go.m_Components:
            c = _read(comp.component if hasattr(comp, "component") else comp)
            if c is not None and type(c).__name__ == "Transform":
                tr = c
                break
        # only roots
        if tr is None or (tr.m_Father is not None and getattr(tr.m_Father, "path_id", 0)):
            continue
        name = _renderer_name(go)
        if name:
            names.append(name)
    return sorted(set(names))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stub", nargs="?", help="accessory_components_pc_<id>_suit_<suit>.ab")
    ap.add_argument("--game", help="AssetBundles directory (with --id/--suit)")
    ap.add_argument("--id", help="character id, e.g. j01")
    ap.add_argument("--suit", help="suit key, e.g. prouniform")
    args = ap.parse_args()

    stub = args.stub
    if not stub and args.game and args.id and args.suit:
        stub = os.path.join(
            args.game,
            "accessory_components_pc_%s_suit_%s.ab" % (args.id, args.suit))
    if not stub or not os.path.isfile(stub):
        ap.error("give a stub .ab path, or --game/--id/--suit")

    for name in suit_components(stub):
        print(name)


if __name__ == "__main__":
    main()
