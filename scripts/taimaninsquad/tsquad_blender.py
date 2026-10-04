"""Shared by export_xps_blender.py and export_pmx_blender.py (both run inside Blender on a .blend
made by build_blend.py): take the toon scene apart into what a format converter understands.

The .blend's materials are node maths rebuilding the game's toon shader, the outline is a Solidify
hull with extra material slots, and the mouth interior's shape keys are driven by the face's.  XPS
and PMX know none of that: they want one colour texture per material, real geometry only, and shape
keys without drivers.  Nothing here is saved back to the source .blend.
"""
import json
import math
import os

import bpy
import numpy as np

# The breast physics settings (BUST, --bust key=value,...) and how a unit's own values scale them live in
# tsquad_common.py, where they can be tested without Blender; what is here puts them on the joints.
from tsquad_common import BUST, PMX_UNITS, bust_fitted, bust_sag_cm, parse_bust  # noqa: F401 - used through this module

BUST_BONES = ("左胸", "右胸")


def bust_bodies(scene):
    """The rigid bodies that move the breasts: the ones on 左胸 / 右胸 - or, where such a body is a static anchor that
    follows the bone (Rise of Eros: the swinging body hangs from it by a joint, "Bip001 Breast_L02"), the dynamic
    bodies jointed to it.  Measuring the anchor reads 0 cm however much the breasts swing."""
    named = [o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.mmd_rigid.name_j in BUST_BONES]
    joints = [o.rigid_body_constraint for o in scene.objects
              if getattr(o, "mmd_type", "") == "JOINT" and o.rigid_body_constraint is not None]
    out = []
    for body in named:
        if body.mmd_rigid.type != "0":                  # "0": follows its bone (static); "1" / "2": physics
            out.append(body)
            continue
        hung = [c.object2 for c in joints if c.object1 is body and c.object2 is not None
                and getattr(c.object2, "mmd_type", "") == "RIGID_BODY" and c.object2.mmd_rigid.type != "0"]
        out += hung or [body]
    return out


def breast_size_cm(scene, body):
    """How far the breast's skin lies from its bone, in cm: the rigid body sits in the weighted centre of
    the skin the bone moves, the bone's head at the chest.  Asagi's is 10.9, a flat chest 4 to 7, the
    largest 15.  None when the bone is not found."""
    for arm in scene.objects:
        if arm.type == "ARMATURE":
            bone = arm.data.bones.get(body.mmd_rigid.bone)
            if bone is not None:
                return (body.matrix_world.translation - arm.matrix_world @ bone.head_local).length * 100.0
    return None


def spring_bust(scene, params):
    """Turn the breast joints (rigid bodies on 左胸 / 右胸) into sliding springs, fitted to the size of
    the breasts and to the travel the game allows (tsquad_common.bust_fitted; both sides get the same
    values, from their mean size).  Works on the mmd_tools objects of a model in metres - a converted rig
    before the PMX export, or an imported PMX before Model.build().  Returns one dict per breast, [] when
    the model has no breast bodies."""
    pairs = []
    for obj in scene.objects:
        rbc = obj.rigid_body_constraint
        if getattr(obj, "mmd_type", "") != "JOINT" or rbc is None or rbc.object2 is None:
            continue
        body = rbc.object2
        if (body.mmd_rigid.name_j or body.mmd_rigid.bone) in BUST_BONES or body.mmd_rigid.bone in BUST_BONES:
            pairs.append((obj, rbc, body))
    sizes = [s for s in (breast_size_cm(scene, body) for _obj, _rbc, body in pairs) if s]
    size_cm = sum(sizes) / len(sizes) if sizes else None
    params, factor = bust_fitted(params, size_cm)
    done = []
    for obj, rbc, body in pairs:
        # the joint sits in the body's centre: no lever, so gravity only pulls and never turns it
        obj.matrix_world.translation = body.matrix_world.translation
        for axis, key in (("x", "sway_cm"), ("y", "depth_cm"), ("z", "bounce_cm")):
            setattr(rbc, "limit_lin_%s_lower" % axis, -params[key] / 100.0)
            setattr(rbc, "limit_lin_%s_upper" % axis, params[key] / 100.0)
        tilt = math.radians(params["tilt_deg"])
        for axis in "xyz":
            setattr(rbc, "limit_ang_%s_lower" % axis, -tilt)
            setattr(rbc, "limit_ang_%s_upper" % axis, tilt)
        mass = params["mass"]
        k = [mass * (2.0 * math.pi * params[key]) ** 2 for key in ("sway_hz", "depth_hz", "bounce_hz")]
        radius = max(body.mmd_rigid.size[0], 1e-3) * PMX_UNITS            # the spring is written in PMX units
        k_turn = 0.4 * mass * radius ** 2 * (2.0 * math.pi * params["tilt_hz"]) ** 2
        obj.mmd_joint.spring_linear = k
        obj.mmd_joint.spring_angular = (k_turn,) * 3
        softest = 2.0 * math.pi * min(params["sway_hz"], params["depth_hz"], params["bounce_hz"])
        body.rigid_body.mass = mass
        # Bullet damps as v *= (1 - d) ** dt, i.e. x'' + c x' + w^2 x = 0 with c = -ln(1 - d) = 2 ratio w
        body.rigid_body.linear_damping = 1.0 - math.exp(-2.0 * params["ratio"] * softest)
        body.rigid_body.angular_damping = params["ang_damp"]
        done.append({"body": body.mmd_rigid.name_j or body.name,
                     "size_cm": round(size_cm, 1) if size_cm else None, "factor": factor,
                     "travel_cm": [params["sway_cm"], params["depth_cm"], params["bounce_cm"]],
                     "hz": [params["sway_hz"], params["depth_hz"], params["bounce_hz"]], "ratio": params["ratio"],
                     "cap_cm": params["cap_cm"], "spring_move": [round(v, 1) for v in k],
                     "spring_turn": round(k_turn, 1), "move_damping": round(body.rigid_body.linear_damping, 7),
                     "sag_cm": round(bust_sag_cm(params), 2)})
    return done


def mmd_like_joints(scene, scale, gravity=98.0):
    """Make Blender's Bullet run the joints of an imported PMX the way MMD does (the findings of
    scripts/mmd_physics, the same three changes as its mmd_like.py): mmd_tools leaves every joint a
    SPRING2 constraint with 0.5 damping on each axis - MMD has no such damping, and it holds a soft
    spring nearly still; rotation springs come in unscaled (1 / scale^2 too stiff); gravity is 98 PMX
    units, not 9.81 m.  Blender hands SPRING1 damping to Bullet inverted: 0 here is Bullet's 1, what
    MMD runs with.  Returns the number of joints changed."""
    count = 0
    for obj in scene.objects:
        c = obj.rigid_body_constraint
        if c is None or c.type != "GENERIC_SPRING":
            continue
        c.spring_type = "SPRING1"
        for axis in "xyz":
            setattr(c, "spring_damping_" + axis, 0.0)
            setattr(c, "spring_damping_ang_" + axis, 0.0)
            setattr(c, "spring_stiffness_ang_" + axis, getattr(c, "spring_stiffness_ang_" + axis) * scale * scale)
        count += 1
    scene.gravity = (0.0, 0.0, -gravity * scale)
    return count


def isolate_loners(scene):
    """A PMX body whose mask says "collide with nothing" (the breasts) still collides in Blender: every
    rigid body sits in collision layer 0, and mmd_tools builds its non-collision constraints only for
    pairs that are close in the rest pose.  The forearm's collider kicked Asagi's right breast 5 cm when
    the hand passed her chest - something MMD would never show.  Each such body gets a collision layer of
    its own (call after Model.build()).  Returns their names."""
    layer, done = 19, []
    for obj in scene.objects:
        if getattr(obj, "mmd_type", "") != "RIGID_BODY" or obj.rigid_body is None:
            continue
        if all(obj.mmd_rigid.collision_group_mask) and layer > 0:
            obj.rigid_body.collision_collections = [i == layer for i in range(20)]
            done.append(obj.mmd_rigid.name_j or obj.name)
            layer -= 1
    return done


def scene_parts(keep_weapon=False):
    """(armature, meshes, removed mesh names): drops the light rig, cameras, empties, the hidden meshes
    (the em_* emote cards) and - unless asked to keep them - the weapons that are parked at the origin
    in the prefab pose.  Weapons carried on the body stay."""
    scene = bpy.context.scene
    removed = []
    for obj in list(scene.objects):
        if obj.type in ("LIGHT", "CAMERA", "EMPTY"):
            bpy.data.objects.remove(obj, do_unlink=True)
        elif obj.type == "MESH":
            parked = obj.get("tsq_role") == "weapon_parked"
            if (parked and not keep_weapon) or (not parked and obj.hide_render):
                removed.append(obj.name)
                bpy.data.objects.remove(obj, do_unlink=True)
            elif parked:                               # kept: the exporters take what is visible
                obj.hide_viewport = obj.hide_render = False
    bpy.context.view_layer.update()                    # else the view layer still lists the removed objects
    arm = next(o for o in scene.objects if o.type == "ARMATURE")
    meshes = [o for o in scene.objects if o.type == "MESH"]
    return arm, meshes, removed


def strip_outline(meshes):
    """Remove the inverted-hull outline: the Solidify modifier, its trailing material slots, its group."""
    count = 0
    for obj in meshes:
        for mod in list(obj.modifiers):
            if mod.type == "SOLIDIFY" and mod.name.startswith("TSQ Outline"):
                obj.modifiers.remove(mod)
                count += 1
        mats = obj.data.materials
        while len(mats) and mats[len(mats) - 1] is not None and mats[len(mats) - 1].get("tsq_kind") == "outline":
            mats.pop(index=len(mats) - 1)
        group = obj.vertex_groups.get("tsq_outline")
        if group is not None:
            obj.vertex_groups.remove(group)
    return count


def bake_shape_defaults(obj):
    """The expression the prefab starts with (``tsq_shape_defaults``, kept by build_blend.py: only
    125_Sokushitsuki's small horns) into the rest shape.  XPS has no morphs and an MMD morph rests at 0, so
    there the default has to BE the base.  The key stays, turned round: as ``<name>_off`` it leads from the
    new rest back to the old one.  Returns the new key names."""
    try:
        defaults = json.loads(obj.get("tsq_shape_defaults", "") or "{}")
    except ValueError:
        defaults = {}
    keys = obj.data.shape_keys
    if not defaults or keys is None:
        return []
    blocks = keys.key_blocks
    count = len(obj.data.vertices) * 3
    basis = np.empty(count, dtype=np.float32)
    blocks[0].data.foreach_get("co", basis)
    coords = {}
    for kb in blocks[1:]:
        coords[kb.name] = np.empty(count, dtype=np.float32)
        kb.data.foreach_get("co", coords[kb.name])
    shift = np.zeros(count, dtype=np.float32)
    for name, value in defaults.items():
        if name in coords:
            shift += (coords[name] - basis) * float(value)
    if not float(np.abs(shift).max()) > 0.0:
        return []
    rest = basis + shift
    blocks[0].data.foreach_set("co", rest)
    obj.data.vertices.foreach_set("co", rest)
    renamed = []
    for kb in blocks[1:]:
        if kb.name in defaults:
            kb.data.foreach_set("co", basis)           # 1.0 = the shape without the default
            kb.value = 0.0
            kb.name = kb.name + "_off"
            renamed.append(kb.name)
        else:
            kb.data.foreach_set("co", coords[kb.name] + shift)      # its own delta, on the new rest
    obj.data.update()
    del obj["tsq_shape_defaults"]
    return renamed


def clear_shape_key_drivers(meshes):
    """Drivers off, every key to 0 - after the prefab's default expression went into the rest shape."""
    count = 0
    for obj in meshes:
        bake_shape_defaults(obj)
        keys = obj.data.shape_keys
        if keys is None:
            continue
        if keys.animation_data:
            for fcurve in list(keys.animation_data.drivers):
                keys.animation_data.drivers.remove(fcurve)
                count += 1
        for kb in keys.key_blocks:
            kb.value = 0.0
    return count


def material_spec(mat):
    try:
        return json.loads(mat.get("tsq_spec", "") or "{}")
    except ValueError:
        return {}


def _upstream(node, keep):
    if node.name in keep:
        return
    keep.add(node.name)
    for sock in node.inputs:
        for link in sock.links:
            _upstream(link.from_node, keep)


def tinted_image(image, lin):
    """`image` multiplied by a linear colour (what a Multiply node on it would show), as a packed PNG
    image of its own: <stem>_<tint as hex>.png.  One per image and tint, however many materials ask."""
    stem = os.path.splitext(os.path.basename(bpy.path.abspath(image.filepath)) or image.name)[0]
    srgb = [c * 12.92 if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055 for c in lin]
    name = "%s_%02x%02x%02x.png" % ((stem,) + tuple(int(round(max(0.0, min(1.0, c)) * 255)) for c in srgb))
    done = bpy.data.images.get(name)
    if done is not None:
        return done
    px = image_pixels(image).astype(np.float64)
    rgb = px[..., :3]
    if image.colorspace_settings.name == "sRGB":       # the pixels are display values: multiply in linear
        low = rgb <= 0.04045
        rgb = np.where(low, rgb / 12.92, ((rgb + 0.055) / 1.055) ** 2.4) * np.asarray(lin)
        rgb = np.where(rgb <= 0.0031308, rgb * 12.92, 1.055 * np.clip(rgb, 0.0, None) ** (1 / 2.4) - 0.055)
    else:
        rgb = rgb * np.asarray(lin)
    px[..., :3] = np.clip(rgb, 0.0, 1.0)
    path = save_png(os.path.join(bpy.app.tempdir, name), px)
    out = bpy.data.images.load(path)
    out.name = name
    out.colorspace_settings.name = image.colorspace_settings.name
    out.alpha_mode = image.alpha_mode
    out.pack()
    return out


def plain_material(mat):
    """Toon / unlit node tree -> Principled BSDF fed by the base map (x _BaseColor when it tints),
    alpha linked only where the game alpha-blends.  Returns True when the material was rebuilt."""
    if mat is None or mat.get("tsq_kind") not in ("toon", "unlit") or not mat.use_nodes:
        return False
    spec = material_spec(mat)
    colors = spec.get("colors", {})
    tint = colors.get("_BaseColor") or colors.get("_Color") or [1.0, 1.0, 1.0, 1.0]
    tree = mat.node_tree
    base = next((tree.nodes.get(n) for n in ("_BaseMap", "_MainTex", "_MainTexture") if tree.nodes.get(n)), None)
    keep = set()
    if base is not None:
        _upstream(base, keep)
    for node in list(tree.nodes):
        if node.name not in keep:
            tree.nodes.remove(node)
    out = tree.nodes.new("ShaderNodeOutputMaterial")
    out.location = (600, 0)
    bsdf = tree.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (250, 0)
    bsdf.inputs["Roughness"].default_value = 0.7
    spec_in = bsdf.inputs.get("Specular") or bsdf.inputs.get("Specular IOR Level")
    if spec_in is not None:
        spec_in.default_value = 0.1
    tree.links.new(bsdf.outputs[0], out.inputs["Surface"])
    lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in tint[:3]]
    tinted = any(abs(1.0 - c) > 0.02 for c in tint[:3])
    if base is not None:
        if tinted and base.image is not None:
            # A tinted COPY of the picture, not a Multiply node: the exporters bake node maths, and
            # Blender2XPS bakes per mesh but keeps one file per material - of two meshes sharing a
            # tinted material (face + face_out) the second got the first one's texels, black elsewhere.
            base.image = tinted_image(base.image, lin)
        tree.links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
        if mat.blend_method != "OPAQUE":
            tree.links.new(base.outputs["Alpha"], bsdf.inputs["Alpha"])
    else:                                              # no picture: the colour is all there is (FX_Black)
        bsdf.inputs["Base Color"].default_value = (lin[0], lin[1], lin[2], 1.0)
        mat.diffuse_color = (lin[0], lin[1], lin[2], 1.0)
        mmd = getattr(mat, "mmd_material", None)       # where Blender2XPS looks first when mmd_tools is on
        if mmd is not None:
            mmd.diffuse_color = (lin[0], lin[1], lin[2])
        if mat.blend_method != "OPAQUE":
            bsdf.inputs["Alpha"].default_value = tint[3]
    return True


def plain_materials(meshes):
    done = []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.name not in done and plain_material(mat):
                done.append(mat.name)
    return done


def unpack_images_to(folder):
    """Packed images -> files in <folder> (mmd_tools and Blender2XPS copy texture FILES; the .blend
    keeps its images packed).  The source .blend is not saved."""
    os.makedirs(folder, exist_ok=True)
    used, done = set(), 0
    for image in bpy.data.images:
        if image.source != "FILE" or not image.packed_file:
            continue
        stem, ext = os.path.splitext(os.path.basename(bpy.path.abspath(image.filepath)) or image.name)
        ext = ext or ".png"
        name, n = stem + ext, 1
        while name.lower() in used:
            n += 1
            name = "%s_%d%s" % (stem, n, ext)
        used.add(name.lower())
        path = os.path.join(folder, name)
        with open(path, "wb") as fh:
            fh.write(bytes(image.packed_file.data))
        image.filepath = path
        image.unpack(method="REMOVE")
        done += 1
    return done


def repack_images_from(folder):
    root, done = os.path.normcase(os.path.abspath(folder)), 0
    for image in bpy.data.images:
        if image.source == "FILE" and not image.packed_file and image.filepath:
            path = os.path.normcase(os.path.abspath(bpy.path.abspath(image.filepath)))
            if path.startswith(root) and os.path.isfile(path):
                image.pack()
                done += 1
    return done


def image_pixels(image):
    w, h = image.size
    px = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    return px.reshape(h, w, 4)


def save_png(path, rgba):
    """rgba: float (h, w, 4) in display (sRGB) values, rows bottom-up as Blender stores them."""
    h, w = rgba.shape[:2]
    image = bpy.data.images.new(os.path.basename(path), w, h, alpha=True)
    image.alpha_mode = "STRAIGHT"
    image.pixels.foreach_set(np.ascontiguousarray(rgba, dtype=np.float32).ravel())
    image.filepath_raw = path
    image.file_format = "PNG"
    image.save()
    bpy.data.images.remove(image)
    return path
