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
# material names: English in the game and most mods, Chinese in some (Tifa Gantz: 蒂法 眼球 / 蒂法 毛发)
EYE_MATERIAL = re.compile(r"(^|[^a-z])eyes?([^a-z]|$)|eyeball|iris|眼球|眼睛|瞳孔|虹膜", re.IGNORECASE)
HAIR_MATERIAL = re.compile(r"hair|毛发|头发|頭髮|髪|髮", re.IGNORECASE)
# Havok cloth / physics proxies ([cloth]HR_A_0109_007, [cloth]BD_M_2140_Board_001 in Elden Ring, BD_M_[Bone]RopeA_02
# in Sekiro): bones the game's cloth or ragdoll moves, no chain of their own - mods reuse them for hair and for
# breast / butt jiggle
CLOTH_PROXY = re.compile(r"^\[cloth\]|\[bone\]", re.IGNORECASE)
# a hair chain of the part's own skeleton (Sekiro Tifa: Hair01..05, one chain for the whole back hair): the
# generated strands take its weight over the hanging part
HAIR_CHAIN = re.compile(r"^hair\d+$", re.IGNORECASE)


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


def split_bust_cloth(arm, meshes):
    """A cloth proxy carrying BOTH breasts (Tifa Gantz: [cloth]BD_M_2140_Board_001, one bone for the chest, the game's
    jiggle) -> its weight goes to Bip001 L / R Pectoral by side (+X = her left; a 2 cm hand-over at the middle), so
    the PMX gets one jiggle body per breast.  A proxy qualifies when at least 60 % of its weight sits in front of the
    spine between Spine2 - 10 cm and the neck, with 25 %+ on each side.  Blender object mode, Biped names."""
    import numpy as np
    bones = arm.data.bones
    need = ("Bip001 Spine2", "Bip001 Neck", "Bip001 L Pectoral", "Bip001 R Pectoral")
    if not all(n in bones for n in need):
        return ["no Spine2 / Neck / Pectoral bones"]
    mw = arm.matrix_world
    sp, nk = mw @ bones["Bip001 Spine2"].head_local, mw @ bones["Bip001 Neck"].head_local
    out = []
    for b in bones:
        if not CLOTH_PROXY.search(b.name):
            continue
        rows = []                                      # (mesh, vertex index, x, y, z, w)
        for m in meshes:
            vg = m.vertex_groups.get(b.name)
            if vg is None:
                continue
            for v in m.data.vertices:
                for g in v.groups:
                    if g.group == vg.index and g.weight > 1e-4:
                        p = m.matrix_world @ v.co
                        rows.append((m, v.index, p.x, p.y, p.z, g.weight))
        if len(rows) < 50:
            continue
        a = np.array([r[2:] for r in rows])
        w = a[:, 3]
        front = (a[:, 2] > sp.z - 0.10) & (a[:, 2] < nk.z) & (a[:, 1] < sp.y - 0.02)
        left, right = w[a[:, 0] > 0.01].sum() / w.sum(), w[a[:, 0] < -0.01].sum() / w.sum()
        if w[front].sum() / w.sum() < 0.6 or min(left, right) < 0.25:
            continue
        moved = 0
        for m in {r[0] for r in rows}:
            vg = m.vertex_groups[b.name]
            gl = m.vertex_groups.get("Bip001 L Pectoral") or m.vertex_groups.new(name="Bip001 L Pectoral")
            gr = m.vertex_groups.get("Bip001 R Pectoral") or m.vertex_groups.new(name="Bip001 R Pectoral")
            for (mm, vi, x, _y, _z, wt) in rows:
                if mm is not m:
                    continue
                t = min(max((x + 0.01) / 0.02, 0.0), 1.0)          # 0 = right side, 1 = left side
                for grp, share in ((gl, t), (gr, 1.0 - t)):
                    if share > 0:
                        grp.add([vi], wt * share, "ADD")
                vg.remove([vi])
                moved += 1
        out.append("%s: %d vertices -> Bip001 L / R Pectoral (left %.0f %%, right %.0f %%)"
                   % (b.name, moved, left * 100, right * 100))
    return out


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
