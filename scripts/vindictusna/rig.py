"""The Vindictus player skeleton (ValveBiped) for XPS / PMX: rename it to 3ds Max Biped names.

The game's skeleton IS a 3ds Max Biped exported through Valve's tools: ValveBiped.Bip01 > _Pelvis > _Spine >
_Spine1 > _Spine2 > _Spine4 > _Neck1 > _Head1, the clavicles under the neck, the thighs under _Spine, fingers
_Finger0 / 01 / 02 ... as in Max.  Renaming it Bip001 * lets the repo's Biped tools take it as they are:
blender2xps maps Bip001 names onto the XPS standard names (XPS poses apply) and the Rise of Eros / Stellar Blade
PMX chain resolves its MMD slots from them (resolve_roe_slots).

  ValveBiped.Bip01          -> Bip001
  ValveBiped.Bip01_<X>_<Y>  -> Bip001 <X> <Y>          (Bip001 L Thigh, Bip001 R Finger01 ...)
  _Neck1 / _Head1 / _Spine4 -> Bip001 Neck / Head / Spine3
  ValveBiped.Anim_Attachment_* (weapon, camera and effect sockets, no skin) are removed;
  the twist helpers (_ForeTwist, _ForeTwist1, _Shoulder01, _UpperArm01) and the breast chain
  (jiggle_L/Rbust_1 > _2; _L/R_Breast carries no skin) keep their names apart from the prefix.
"""
import re

SPECIAL = {'Neck1': 'Neck', 'Head1': 'Head', 'Spine4': 'Spine3'}
SOCKET = re.compile(r'^ValveBiped\.Anim_Attachment', re.I)
# helpers riding a limb segment (the game drives them procedurally; without that they follow their parent)
LIMB_HELPER = r'|foretwist\d*$|shoulder01$|upperarm01$'
BUST = (('左胸', 'jiggle_Lbust_2'), ('右胸', 'jiggle_Rbust_2'))


def full_sclera():
    """Switch every eye material of the .blend to its full sclera (build_blend.py's "FullSclera" node) before a bake:
    XPS / PMX eye bones turn the whole eyeball, and the game's eyeball texture is black outside the almond the lids
    leave open.  Returns the materials switched."""
    import bpy
    done = []
    for mat in bpy.data.materials:
        node = mat.node_tree.nodes.get('FullSclera') if mat.use_nodes and mat.node_tree else None
        if node is not None:
            node.outputs[0].default_value = 1.0
            done.append(mat.name)
    return done


def biped_name(name):
    if name == 'ValveBiped.Bip01':
        return 'Bip001'
    m = re.match(r'^ValveBiped\.Bip01_(.+)$', name)
    if not m:
        return name
    parts = m.group(1).split('_')
    parts[-1] = SPECIAL.get(parts[-1], parts[-1])
    return 'Bip001 ' + ' '.join(parts)


def to_biped(arm, meshes):
    """Rename the armature's bones (vertex groups follow) and delete the skinless sockets.  Blender, object mode.
    Returns {'renamed': n, 'sockets_removed': [...]}"""
    import bpy
    sockets = [b.name for b in arm.data.bones if SOCKET.match(b.name)]
    weighted = set()
    for m in meshes:
        names = {vg.index: vg.name for vg in m.vertex_groups}
        for v in m.data.vertices:
            for g in v.groups:
                if g.weight > 1e-5 and g.group in names:
                    weighted.add(names[g.group])
    sockets = [s for s in sockets if s not in weighted]
    if sockets:
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        for s in sockets:
            eb = arm.data.edit_bones.get(s)
            if eb is not None:
                for c in eb.children:
                    c.parent = eb.parent
                arm.data.edit_bones.remove(eb)
        bpy.ops.object.mode_set(mode='OBJECT')
    renamed = 0
    for b in arm.data.bones:
        new = biped_name(b.name)
        if new != b.name:
            old = b.name
            b.name = new                         # vertex groups of objects using this armature follow
            for m in meshes:                     # (and any that did not, e.g. objects whose modifier points elsewhere)
                vg = m.vertex_groups.get(old)
                if vg is not None and m.vertex_groups.get(new) is None:
                    vg.name = new
            renamed += 1
    return {'renamed': renamed, 'sockets_removed': sockets}
