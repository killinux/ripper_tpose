# -*- coding: utf-8 -*-
"""The Elden Ring player skeleton (c0000) for XPS / PMX: rename it to 3ds Max Biped names.

FromSoftware's skeleton is a 3ds Max Biped with the prefix dropped and underscores: Pelvis, Spine, Spine1, Spine2,
Neck, Head, L_Clavicle, L_UpperArm, L_Forearm, L_Hand, L_Finger0 / 01 / 02 ..., L_Thigh, L_Calf, L_Foot, L_Toe0, the
twist helpers L_UpArmTwist(1), L_ForeArmTwist(1), L_ThighTwist(1), L_CalfTwist(1), L_FootTwist, and the chest
helpers L_Pectoral (the breasts hang on them, half and half with Spine2).  Renamed Bip001 *, the repo's Biped tools
take it as it is: blender2xps maps the names onto the XPS standard ones (XPS poses apply) and the Rise of Eros /
Stellar Blade PMX chain resolves its MMD slots from them (resolve_roe_slots).

  Master                -> Bip001                (the root on the floor = 全ての親)
  Pelvis / Spine* / Neck / Head -> Bip001 <name>
  L_<X> / R_<X>         -> Bip001 L <X> / Bip001 R <X>     (ForeArmTwist -> ForeTwist, Max's spelling)
"""
import re

SPECIAL = {"ForeArmTwist": "ForeTwist", "ForeArmTwist1": "ForeTwist1"}
CORE = re.compile(r"^(Pelvis|Spine\d?|Neck|Head)$")
# helpers riding a limb segment (the game drives them procedurally; without that they follow their parent)
LIMB_HELPER = r"|uparmtwist\d*$|foretwist\d*$|thightwist\d*$|calftwist\d*$|foottwist$"
BUST = (("左胸", "Bip001 L Pectoral"), ("右胸", "Bip001 R Pectoral"))
EYE_MATERIAL = re.compile(r"(^|[^a-z])eyes?([^a-z]|$)|eyeball|iris", re.IGNORECASE)


def biped_name(name):
    if name == "Master":
        return "Bip001"
    if CORE.match(name):
        return "Bip001 " + name
    m = re.match(r"^([LR])_(.+)$", name)
    if m:
        return "Bip001 %s %s" % (m.group(1), SPECIAL.get(m.group(2), m.group(2)))
    return name


def to_biped(arm, meshes):
    """Rename the armature's bones (vertex groups follow).  Blender, object mode.  Returns {'renamed': n}"""
    renamed = 0
    for b in arm.data.bones:
        new = biped_name(b.name)
        if new != b.name:
            old = b.name
            b.name = new                         # vertex groups of objects using this armature follow
            for m in meshes:
                vg = m.vertex_groups.get(old)
                if vg is not None and m.vertex_groups.get(new) is None:
                    vg.name = new
            renamed += 1
    return {"renamed": renamed}


def leave_out(scene, pattern):
    """Delete the mesh objects whose name (= the FLVER material) matches pattern, and hidden ones.  Returns names."""
    import bpy
    rx = re.compile(pattern) if pattern else None
    gone = []
    for o in list(scene.objects):
        if o.type != "MESH":
            continue
        if o.hide_render or o.hide_get() or (rx and rx.search(o.name)):
            gone.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    return gone
