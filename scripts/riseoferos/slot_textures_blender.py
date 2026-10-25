"""Which of the named mesh objects have a colour image in every material slot, read-only - for make_gallery.py
--recheck-slots: the suit assembler lists the pieces it left without a colour texture (the fm ears, lenses ...),
and later steps (fix_suit_slots_blender.py, the game materials) fill some of them in.

  blender -b --factory-startup <x.blend> --python slot_textures_blender.py -- <object> [<object> ...]

A slot counts as textured when its game material's colour node (hq_albedo) or the image feeding its Principled
Base Color has an image; a slot with no material does not.  Prints ROE_SLOT_TEXTURES={json}: per object
{"found", "textured", "materials"}.
"""
import json
import sys

import bpy


def colour_image(mat):
    """The material's colour image: the game material's hq_albedo node, else the first image upstream of a
    Principled BSDF's Base Color; None without one."""
    if mat is None or not mat.use_nodes:
        return None
    node = mat.node_tree.nodes.get("hq_albedo")
    if node is not None and getattr(node, "image", None):
        return node.image
    for bsdf in (n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"):
        stack, seen = [bsdf.inputs["Base Color"]], set()
        while stack:
            for link in stack.pop(0).links:
                upstream = link.from_node
                if upstream in seen:
                    continue
                seen.add(upstream)
                if upstream.type == "TEX_IMAGE" and upstream.image:
                    return upstream.image
                stack.extend(upstream.inputs)
    return None


def main():
    names = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    state = {}
    for name in names:
        obj = bpy.data.objects.get(name)
        if obj is None or obj.type != "MESH":
            state[name] = {"found": False, "textured": False, "materials": []}
            continue
        mats = [slot.material for slot in obj.material_slots]
        images = [colour_image(mat) for mat in mats]
        state[name] = {"found": True, "textured": bool(mats) and all(images),
                       "materials": [[mat.name if mat else None, image.name if image else None]
                                     for mat, image in zip(mats, images)]}
    print("ROE_SLOT_TEXTURES=" + json.dumps(state, ensure_ascii=True))


main()
