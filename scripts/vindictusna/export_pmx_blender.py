# -*- coding: utf-8 -*-
"""Vindictus .blend (build_blend.py / package_blend.py output) -> MMD .pmx, inside Blender 3.6 (headless).

The repo's Biped chain (Stellar Blade's export_pmx_blender.py on the Rise of Eros worker: mmd_tools writes the PMX,
Convert_to_MMD5 builds the MMD skeleton, IK and body colliders, mmd_cloth_physics the hair / skirt chains,
blender2xps bakes node colours into one texture per material).  What this file adds for the Vindictus rig:

  * the ValveBiped skeleton renamed to 3ds Max Biped names and the skinless sockets removed (rig.py) - it is a Max
    Biped underneath, so the Biped slot table of the worker (resolve_roe_slots) applies as it is;
  * eye bones (左目 / 右目) at each eyeball's centre - the game turns its eyeballs in the shader (no eye bones);
  * the breasts: the skin hangs on jiggle_L/Rbust_2 (Source jiggle bones under jiggle_*bust_1 on Spine2); those
    become 左胸 / 右胸 with a dynamic sphere and a spring joint each (Stellar Blade's BUST set-up);
  * the twist helpers (ForeTwist, ForeTwist1, Shoulder01, UpperArm01) are limb helpers, never cloth;
  * the model is already in metres facing -Y (build_blend.py), nothing is scaled or turned.

  blender -b <look>.blend --factory-startup --python export_pmx_blender.py -- --out <dir> [--name N]
          [--model-name M] [--comment C]
Prints VINDICTUS_PMX={json}.  Writes <out>/<name>.pmx + textures/ + <name>_converted.blend.
"""
import argparse
import importlib.util
import json
import os
import re
import shutil
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.realpath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
SB_SCRIPT = os.path.join(REPO, 'scripts', 'stellarblade', 'export_pmx_blender.py')
sys.path.insert(0, HERE)
import rig  # noqa: E402


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sb = load(SB_SCRIPT, 'sb_pmx')           # bake_node_colours / add_eye_bones / add_breast_physics / fix_pmx_materials ...
sb.BUST['bones'] = rig.BUST
# the game hangs the breast skin on jiggle_*bust_2 lightly (0.1-0.35 per vertex); place the sphere from every
# vertex the bone moves noticeably, not only the >= 0.3 ones (two vertices on Lynn)
sb.BUST['min_weight'] = 0.08


# MMD expressions from the face's Source flexes (build_blend.py makes them shape keys of the same name on the face
# skin, lashes, teeth ...).  The flexes are whole-face expressions; each MMD morph takes the first flex that exists
# (the names differ between heroines).  The raw flexes stay as well, listed under その他.
MORPHS = [
    ('まばたき', 'blink', 'EYE', ('blink',)),
    ('笑い', 'smile_eyes', 'EYE', ('blink_smile', 'closedeyes_mild', 'blink_half_smile')),
    ('ウィンク', 'wink', 'EYE', ('wink_L',)),          # + 'wink' by the side it closes, see wink_sides()
    ('ウィンク右', 'wink_R', 'EYE', ('wink_R',)),
    ('じと目', 'half_closed', 'EYE', ('blink_half',)),
    ('びっくり', 'surprised', 'EYE', ('surprised', 'shocked', 'surprised_a')),
    ('真面目', 'serious', 'EYEBROW', ('hostile',)),
    ('困る', 'trouble', 'EYEBROW', ('sorry', 'sad', 'worry')),
    ('にこり', 'cheerful', 'EYEBROW', ('mild', 'mild2')),
    ('怒り', 'anger', 'EYEBROW', ('angry', 'angry2', 'big_angry')),
    ('上', 'brow_up', 'EYEBROW', ('brow_up',)),
    ('あ', 'a', 'MOUTH', ('ah', 'mouth_a', 'a', 'chew_down')),
    ('い', 'i', 'MOUTH', ('mouth_e_half',)),
    ('う', 'u', 'MOUTH', ('woo', 'mouth_ou', 'oo')),
    ('え', 'e', 'MOUTH', ('mouth_e',)),
    ('お', 'o', 'MOUTH', ('oh', 'oo', 'mouth_ou', 'woo')),
    ('にっこり', 'smile_mouth', 'MOUTH', ('smile',)),
    ('にやり', 'grin', 'MOUTH', ('sneer', 'sneer1')),
    ('∧', 'mouth_∧', 'MOUTH', ('frown',)),
    ('喜び', 'happy', 'OTHER', ('happy',)),
    ('悲しい', 'sad', 'OTHER', ('sad',)),
    ('痛い', 'hurt', 'OTHER', ('hurt',)),
]


def _copy_key(ob, src, name, mirror=False):
    """new shape key = src (optionally mirrored across X: the delta of vertex v goes to the vertex at v's mirrored
    place).  Returns False when a mirror cannot be found for most of the moved vertices."""
    keys = ob.data.shape_keys.key_blocks
    base = [v.co.copy() for v in ob.data.vertices]
    sk = keys[src]
    new = ob.shape_key_add(name=name, from_mix=False)
    if not mirror:
        for i, p in enumerate(sk.data):
            new.data[i].co = p.co
        return True
    from mathutils.kdtree import KDTree
    kd = KDTree(len(base))
    for i, c in enumerate(base):
        kd.insert(c, i)
    kd.balance()
    moved = [i for i, c in enumerate(base) if (sk.data[i].co - c).length > 1e-6]
    hit = 0
    for i in moved:
        d = sk.data[i].co - base[i]
        m = base[i].copy(); m.x = -m.x
        co, j, dist = kd.find(m)
        if dist < 0.0005:
            new.data[j].co = base[j] + type(d)((-d.x, d.y, d.z))
            hit += 1
    if moved and hit < 0.9 * len(moved):
        ob.shape_key_remove(new)
        return False
    return True


def wink_sides(meshes):
    """which eye 'wink' closes: the moved vertices' mean X on the face skin (+X = the model's left, it faces -Y)"""
    for ob in meshes:
        keys = ob.data.shape_keys.key_blocks if ob.data.shape_keys else {}
        if 'wink' in keys and 'skin_face' in ob.name.lower():
            sk = keys['wink']
            xs = [ob.data.vertices[i].co.x for i in range(len(ob.data.vertices))
                  if (sk.data[i].co - ob.data.vertices[i].co).length > 1e-4]
            if xs:
                return 'L' if sum(xs) / len(xs) > 0 else 'R'
    return None


def add_morphs(root, meshes):
    have_any = {k.name for ob in meshes if ob.data.shape_keys for k in ob.data.shape_keys.key_blocks[1:]}
    if not have_any:
        return {'made': [], 'note': 'no flexes'}
    side = wink_sides(meshes)
    plan = []
    for name, name_e, cat, srcs in MORPHS:
        src = next((s for s in srcs if s in have_any), None)
        mirror = False
        if src is None and name in ('ウィンク', 'ウィンク右') and 'wink' in have_any and side:
            own = 'ウィンク' if side == 'L' else 'ウィンク右'
            src, mirror = 'wink', name != own
        if src:
            plan.append((name, name_e, cat, src, mirror))
    made = []
    for name, name_e, cat, src, mirror in plan:
        ok = False
        for ob in meshes:
            keys = ob.data.shape_keys.key_blocks if ob.data.shape_keys else None
            if keys and src in keys and name not in keys:
                ok = _copy_key(ob, src, name, mirror) or ok
        if ok:
            made.append((name, name_e, cat, src + (' (mirrored)' if mirror else '')))
    mmd = root.mmd_root
    have = {m.name for m in mmd.vertex_morphs}
    for name, name_e, cat, _src in made:
        if name not in have:
            item = mmd.vertex_morphs.add()
            item.name, item.name_e, item.category = name, name_e, cat
    for k in sorted(have_any):
        if k not in have and k not in {m[0] for m in made}:
            item = mmd.vertex_morphs.add()
            item.name, item.name_e, item.category = k, k, 'OTHER'
    for target, m in enumerate(made):
        mmd.vertex_morphs.move(mmd.vertex_morphs.find(m[0]), target)
    from mmd_tools.operators.display_item import DisplayItemQuickSetup
    if '表情' in mmd.display_item_frames:
        mmd.display_item_frames['表情'].data.clear()
    DisplayItemQuickSetup.load_facial_items(mmd)
    return {'made': ['%s <- %s' % (m[0], m[3]) for m in made], 'raw': len(have_any)}


def fix_eye_pivots(arm, meshes):
    """The game's eyeball mesh is the FRONT HALF of a sphere (Lynn: r 18 mm, 17 mm deep), not a ball.
    add_eye_bones puts the pivot at back-most point + radius, right for a whole ball with a bulging cornea - here the
    back-most points are the cap's rim, on the sphere's centre plane, so the pivot landed on the cornea and a turned eye
    swung out through the lids.  Move each eye bone to the least-squares sphere centre of the vertices it carries."""
    import numpy as np
    out = []
    for side in ('L', 'R'):
        name = 'Bip001 %s Eye' % side
        if name not in arm.data.bones:
            continue
        pts = []
        for m in meshes:
            vg = m.vertex_groups.get(name)
            if vg is None:
                continue
            for v in m.data.vertices:
                if any(g.group == vg.index and g.weight > 0.5 for g in v.groups):
                    pts.append(tuple(m.matrix_world @ v.co))
        if len(pts) < 20:
            continue
        P = np.array(pts)
        c = np.linalg.lstsq(np.c_[2 * P, np.ones(len(P))], (P ** 2).sum(1), rcond=None)[0]
        ctr, r = Vector(c[:3]), float(np.sqrt(c[3] + (c[:3] ** 2).sum()))
        if not 0.005 < r < 0.03:        # an eyeball is 13-20 mm; 37 mm was both eyes on one bone (10-31, sb.add_eye_bones)
            raise RuntimeError('%s: sphere fit r %.1f mm over %d vertices - not one eyeball' % (name, r * 1000, len(P)))
        bpy.context.view_layer.objects.active = arm
        bpy.ops.object.mode_set(mode='EDIT')
        eb = arm.data.edit_bones[name]
        inv = arm.matrix_world.inverted()
        d = (eb.tail - eb.head).normalized()
        old = arm.matrix_world @ eb.head
        eb.head = inv @ ctr
        eb.tail = eb.head + d * max(r * 1.5, 0.01)
        bpy.ops.object.mode_set(mode='OBJECT')
        out.append('%s: pivot moved %.1f mm back to the sphere centre (r %.1f mm)' % (name, (old - ctr).length * 1000, r * 1000))
    if len(out) != 2:
        raise RuntimeError('eye bones: %d of 2 eyes (%s)' % (len(out), ', '.join(b.name for b in arm.data.bones if 'Eye' in b.name)))
    return out


def prepare(arm, meshes):
    stats = {'height_m': round(max((m.matrix_world @ Vector(c)).z for m in meshes for c in m.bound_box), 3)}
    stats['rig'] = rig.to_biped(arm, meshes)
    stats['dropped_far_bones'] = len(sb.drop_far_sockets(arm, meshes))
    stats['eye_bones'] = sb.add_eye_bones(arm, meshes)
    stats['eye_pivots'] = fix_eye_pivots(arm, meshes)
    stats['undeformed_sockets'] = sb.undeform_sockets(arm, meshes)
    return stats


def main():
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--name', default='')
    ap.add_argument('--model-name', default='', help='name shown in MMD (default: --name)')
    ap.add_argument('--comment', default='', help='model comment (credits / source)')
    args = ap.parse_args(argv)

    roe = sb.load_worker()
    scene = bpy.context.scene
    name = args.name or os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    out_dir = os.path.abspath(args.out)
    path = os.path.join(out_dir, name + '.pmx')
    report = {'name': name, 'pmx': path, 'source': bpy.data.filepath}
    for obj in list(scene.objects):                  # the hidden default parts the look replaced
        if obj.type == 'MESH' and (obj.hide_render or obj.hide_get()):
            bpy.data.objects.remove(obj, do_unlink=True)
    arm = next(o for o in scene.objects if o.type == 'ARMATURE')
    meshes = [o for o in scene.objects if o.type == 'MESH']

    if os.path.isdir(out_dir):                      # a generated folder: start clean, no stale textures
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)
    report['full_sclera'] = rig.full_sclera()        # eye bones turn the ball: no black lid shadow on it
    baked = sb.bake_node_colours(meshes, os.path.join(out_dir, 'textures'))
    report.update(prepare(arm, meshes))

    roe.enable_addon('mmd_tools')
    roe.enable_addon('Convert_to_MMD5')
    slots, missing_optional = roe.resolve_roe_slots(arm)
    for (mmd_name, source_name), side in zip(sb.BUST['bones'], ('left', 'right')):
        if source_name in arm.data.bones:
            slots['%s_chest_bone' % side] = source_name          # -> 左胸 / 右胸
            missing_optional = [m for m in missing_optional if m != '%s_chest_bone' % side]
    report['slots'] = {k: v for k, v in slots.items() if v}
    report['missing_optional_slots'] = missing_optional
    missing_required = [r for r in roe.ROE_MMD_REQUIRED_SLOTS if not slots[r]]
    if missing_required:
        raise RuntimeError('rig lacks joints the MMD conversion needs: %s' % ', '.join(missing_required))
    roe.bake_rig_transforms(arm, meshes)
    report['premerged_helpers'] = sb.premerge_spine_helpers(arm, meshes, slots)
    before = roe.edge_lengths(meshes)
    helper_plans, _helper_report = roe.plan_joint_helper_moves(arm, meshes, slots)
    report['reparented_helpers'] = roe.apply_joint_helper_moves(arm, helper_plans)
    report['relaxed_groups'] = roe.relax_shoulder_weights(arm, slots)
    report['arm_down_deg'] = roe.apose_arms(arm, meshes, slots)
    skin_before = roe.snapshot_skin(arm, meshes)
    try:                                             # twist helpers ride their limb, never cloth
        import mmd_cloth_physics.analyze as cloth_analyze
        if rig.LIMB_HELPER not in cloth_analyze.LIMB_HELPER.pattern:
            cloth_analyze.LIMB_HELPER = re.compile(cloth_analyze.LIMB_HELPER.pattern + rig.LIMB_HELPER, re.IGNORECASE)
    except ImportError:
        pass
    names_before, weighted_before = set(arm.data.bones.keys()), sb.weighted_bones(meshes)
    root, conv = roe.convert_rig_to_mmd(arm, meshes, slots, missing_optional, helper_plans, skin_before)
    report.update(conv)
    report['stray_recipients'] = sorted((sb.weighted_bones(meshes) - weighted_before) & names_before)
    slot_names = {v for v in slots.values() if v}
    report['retired_helpers'] = sorted(weighted_before - sb.weighted_bones(meshes) - slot_names)
    report['anchored_hub_roots'] = sb.anchor_hub_roots(arm)
    report['anchored_skin_helpers'] = sb.anchor_skin_helpers(arm, meshes)
    report['released_rest_overlaps'] = sb.release_rest_overlaps()
    report['bust_physics'] = sb.add_breast_physics(root, arm, meshes)
    report['rigid_bodies'] = sum(1 for o in scene.objects if getattr(o, 'mmd_type', '') == 'RIGID_BODY')
    report['joints'] = sum(1 for o in scene.objects if getattr(o, 'mmd_type', '') == 'JOINT')
    report['distortion'] = roe.mesh_distortion(before, meshes)
    report['hidden_materials'] = roe.hide_transparent_materials(meshes)
    report['materials'] = sb.fix_pmx_materials(meshes, baked, os.path.join(out_dir, 'textures'))
    report['morphs'] = add_morphs(root, [o for o in scene.objects if o.type == 'MESH' and o.data.shape_keys])

    root.mmd_root.name = root.mmd_root.name_e = args.model_name or name
    root.name = args.model_name or name
    comment = args.comment or ('Converted from Vindictus (Mabinogi Heroes, NEXON) by ripper_tpose '
                               '(scripts/vindictusna). Personal use only.')
    text = bpy.data.texts.new(name + '_comment')
    text.from_string(comment.replace(chr(92) + 'n', '\n'))
    root.mmd_root.comment_text = root.mmd_root.comment_e_text = text.name

    bpy.ops.object.mode_set(mode='OBJECT')
    bpy.ops.object.select_all(action='DESELECT')
    stack = [root]
    while stack:
        obj = stack.pop()
        try:
            obj.hide_set(False)
            obj.select_set(True)
        except (ReferenceError, RuntimeError):
            pass
        stack.extend(obj.children)
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.export_pmx(filepath=path, scale=12.5, copy_textures=True, log_level='ERROR')
    if not os.path.isfile(path) or os.path.getsize(path) == 0:
        raise RuntimeError('PMX not written: %s' % path)
    report['grant_order_violations'] = roe.verify_grant_order(path)
    report['bytes'] = os.path.getsize(path)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out_dir, name + '_converted.blend'))
    print('VINDICTUS_PMX=' + json.dumps(report, ensure_ascii=False, default=str), flush=True)


if __name__ == '__main__':
    main()
