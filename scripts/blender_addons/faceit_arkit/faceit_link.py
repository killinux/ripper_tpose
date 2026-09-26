# -*- coding: utf-8 -*-
"""Hook a model with ARKit shape keys into Faceit for live capture (Face Cap, Live Link Face, ...).

Does what Faceit's Setup -> Register Selected Object and Shapes -> Smart Match would do, but works
headless too (those operators touch the UI area) and also matches ARKit shapes spelled another way
(eyeBlink_L, EyeBlinkLeft, Eye_Blink_L ...).  Checked against Faceit 2.3.40."""
import importlib
import socket

import addon_utils
import bpy

from . import arkit

HEAD_NAMES = ("head", "Head", "Bip001 Head", "Bip001_Head", "Bip01 Head", "J_Bip_C_Head", "頭",
              "mixamorig:Head", "CC_Base_Head", "DEF-spine.006", "c_head.x", "HEAD")
SOURCES = (("FACECAP", "Face Cap", "bannaflak Face Cap (iOS), OSC"),
           ("EPIC", "Live Link Face", "Epic Live Link Face (iOS)"),
           ("IFACIALMOCAP", "iFacialMocap", "iFacialMocap (iOS)"),
           ("TILE", "Hallway Tile", "Hallway Tile / Cube"))


def faceit_package():
    """Module name of the installed Faceit add-on (the folder may not be called 'faceit')."""
    for mod in addon_utils.modules(refresh=False):
        if mod.bl_info.get("name", "").upper() == "FACEIT":
            return mod.__name__
    return None


def faceit_state():
    name = faceit_package()
    if name is None:
        return "missing", None
    enabled = name in bpy.context.preferences.addons
    return ("enabled" if enabled else "disabled"), name


def _faceit(sub):
    name = faceit_package()
    if name is None:
        raise RuntimeError("Faceit is not installed")
    return importlib.import_module(name + "." + sub)


def arkit_targets(meshes):
    """{ARKit name: sorted shape key names across the meshes} (any common spelling)."""
    out = {}
    for obj in meshes:
        if obj.data.shape_keys is None:
            continue
        for ark, key in arkit.match_names([k.name for k in obj.data.shape_keys.key_blocks[1:]]).items():
            out.setdefault(ark, set()).add(key)
    return {k: sorted(v) for k, v in out.items()}


def guess_head_bone(arm, meshes):
    bones = arm.data.bones
    root = bones.get("FACIAL_C_FacialRoot")
    if root is not None and root.parent is not None:
        return root.parent.name
    for name in HEAD_NAMES:
        if name in bones:
            return name
    # else the non-facial bone carrying the most weight on the face meshes
    totals = {}
    for obj in meshes:
        names = {g.index: g.name for g in obj.vertex_groups}
        for v in obj.data.vertices:
            for g in v.groups:
                n = names.get(g.group, "")
                if n in bones and not n.upper().startswith("FACIAL_"):
                    totals[n] = totals.get(n, 0.0) + g.weight
    return max(totals, key=totals.get) if totals else ""


def is_registered(scene, meshes):
    names = {i.name for i in getattr(scene, "faceit_face_objects", [])}
    targets = sum(1 for e in getattr(scene, "faceit_arkit_retarget_shapes", []) if len(e.target_shapes))
    return all(o.name in names for o in meshes) and targets > 0, targets


def register(scene, arm, meshes, head_bone="", source="FACECAP", require_enabled=True):
    """Register the meshes + ARKit targets + head bone with Faceit and set the live source.
    Returns a report dict.  Needs Faceit enabled (it reads its own preferences while streaming);
    a headless run that only enabled it for the session passes require_enabled=False."""
    state, _name = faceit_state()
    if state == "missing" or (require_enabled and state != "enabled"):
        raise RuntimeError("Faceit is %s - enable it in Preferences > Add-ons first" % state)
    fdata = _faceit("core.faceit_data")
    regions = _faceit("core.retarget_list_utils")
    handlers = _faceit("core.faceit_handlers")

    targets = arkit_targets(meshes)
    if not targets:
        raise RuntimeError("none of %s has ARKit shape keys - bake them first" % ", ".join(o.name for o in meshes))
    with_keys = [o for o in meshes if o.data.shape_keys is not None]

    # Setup tab: registered objects (kept if already there) + the body armature
    items = scene.faceit_face_objects
    for obj in with_keys:
        if obj.name not in items:
            item = items.add()
            item.name = obj.name
            item.obj_pointer = obj
    scene.faceit_body_armature = arm

    # Shapes tab: the ARKit list with its targets (what Smart Match fills)
    if scene.faceit_retargeting_naming_scheme != "ARKIT":
        scene.faceit_retargeting_naming_scheme = "ARKIT"
    lst = scene.faceit_arkit_retarget_shapes
    lst.clear()
    missing = []
    for name, data in fdata.get_arkit_shape_data().items():
        entry = lst.add()
        entry.name = name
        entry.display_name = data["name"]
        for key in targets.get(name, []):
            entry.target_shapes.add().name = key
        if name not in targets:
            missing.append(name)
    regions.set_base_regions_from_dict(lst)

    # Mocap tab: head rotation on the head bone, eyes through the eyeLook shape keys (they turn
    # the eyeball AND move the lids; rotating the eye bones as well would turn the eyes twice)
    head_bone = head_bone or guess_head_bone(arm, meshes)
    scene.faceit_head_target_object = arm
    scene.faceit_head_sub_target = head_bone
    handlers.register_mocap_engine_defaults(scene)
    for engine in scene.faceit_live_mocap_settings:
        if engine.name == "A2F":
            continue
        engine.animate_shapes = True
        engine.animate_head_rotation = True
        engine.animate_head_location = False
        engine.animate_eye_rotation_shapes = True
        engine.animate_eye_rotation_bones = False
    scene.faceit_live_source = source
    settings = scene.faceit_live_mocap_settings.get(source)
    return {"objects": [o.name for o in with_keys], "targets": 52 - len(missing), "missing": missing,
            "head": "%s / %s" % (arm.name, head_bone), "source": source,
            "port": settings.port if settings else None, "lan_ip": lan_ip()}


def lan_ip():
    """This PC's address on the local network (what the phone app needs); nothing is sent."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()
