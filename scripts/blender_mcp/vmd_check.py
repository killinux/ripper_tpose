"""Runs INSIDE Blender (blender-mcp, or --python on a saved scene): put a VMD on
the mmd_tools model in the current scene and look for the things that go wrong
with a converted rig, then play it.

    python scripts/blender_mcp/mcp_exec.py scripts/blender_mcp/vmd_check.py 800

Checks, each printed as one "T|" line:
- bones the motion keys that the model does not have (by 日本語 name);
- morphs the motion drives that the model lacks;
- how many bones the motion animates and how many ride dynamic rigid bodies;
- posed mesh tears: edge stretch on the evaluated mesh at 12 frames, sampled
  with the rigid-body tracks MUTED - with them live, a frame outside the
  physics cache leaves the rigid bodies at rest while the body is posed, a
  fake 70x tear.  Reported twice: worst overall, and worst between body bones
  (cloth bones excluded).  A bone blink stretches the eyelid/eyeball margin
  edges (~1.4 mm at rest) by a few mm; that is the blink, not a defect;
- physics: the first 8 s stepped in order, max distance of any dynamic rigid
  body from the hips once a second (a blow-up reads as metres);
- morph values at the motion's first full blink.
Edit VMD below for another motion.
"""
import collections
import struct
import traceback

import bpy
import numpy as np

VMD = r"E:\Downloads\mmd\来杯好茶摇一摇2026.6.14by小王动画\适配【原神】芙宁娜.vmd"
SCALE = 0.08                      # VMD units -> metres, like the PMX import
BLINK = "\u307e\u3070\u305f\u304d"  # まばたき
HIPS = "\u4e0b\u534a\u8eab"         # 下半身
CLOTH = ("Skirt", "Sleeve", "Decoration", "Tassel", "Hair", "Rope", "Ribbon", "Accessory",
         "Earring", "Hari", "Cape", "Cloak", "Streamer", "Bowknot", "Tentacle", "Wing")


def esc(text):
    return str(text).encode("unicode_escape").decode()


def dominant(me, groups, vi):
    best = max(me.data.vertices[vi].groups, key=lambda g: g.weight, default=None)
    return groups.get(best.group, "?") if best else "-"


def read_vmd(path):
    data = open(path, "rb").read()
    pos = 50
    count = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    bones = collections.Counter()
    for _ in range(count):
        bones[data[pos:pos + 15].split(b"\0")[0].decode("cp932", "replace")] += 1
        pos += 111
    count = struct.unpack_from("<I", data, pos)[0]
    pos += 4
    morphs = collections.Counter()
    blink_frame = None
    for _ in range(count):
        name = data[pos:pos + 15].split(b"\0")[0].decode("cp932", "replace")
        frame, weight = struct.unpack_from("<If", data, pos + 15)
        pos += 23
        if weight > 0.5:
            morphs[name] += 1
            if name == BLINK and blink_frame is None and frame > 10 and weight >= 0.99:
                blink_frame = frame
    return bones, morphs, blink_frame


def stretch_report(scene, arm, meshes, frames):
    """(worst overall, worst between body bones) with the rigid tracks muted."""
    tracks = [c for pb in arm.pose.bones for c in pb.constraints if c.name == "mmd_tools_rigid_track"]
    for c in tracks:
        c.mute = True
    rest, groups = {}, {}
    for me in meshes:
        verts = np.array([v.co[:] for v in me.data.vertices])
        edges = np.array([e.vertices[:] for e in me.data.edges])
        rest[me.name] = (edges, np.linalg.norm(verts[edges[:, 0]] - verts[edges[:, 1]], axis=1) + 1e-6)
        groups[me.name] = {g.index: g.name for g in me.vertex_groups}
    worst, body = [], {}
    try:
        for f in frames:
            scene.frame_set(f)
            dg = bpy.context.evaluated_depsgraph_get()
            for me in meshes:
                ev = me.evaluated_get(dg)
                mesh = ev.to_mesh()
                if len(mesh.vertices) == len(me.data.vertices):
                    verts = np.array([v.co[:] for v in mesh.vertices])
                    edges, r0 = rest[me.name]
                    ratio = np.linalg.norm(verts[edges[:, 0]] - verts[edges[:, 1]], axis=1) / r0
                    over = np.nonzero(ratio > 3.0)[0]
                    for i in over[:400]:
                        a = dominant(me, groups[me.name], int(edges[i, 0]))
                        b = dominant(me, groups[me.name], int(edges[i, 1]))
                        if not (a.startswith(CLOTH) or b.startswith(CLOTH)):
                            key = "%s/%s" % (a, b)
                            body[key] = max(body.get(key, 0.0), float(ratio[i]))
                    i = int(ratio.argmax())
                    worst.append((float(ratio[i]), int(len(over)), f, me.name,
                                  dominant(me, groups[me.name], int(edges[i, 0])),
                                  dominant(me, groups[me.name], int(edges[i, 1]))))
                ev.to_mesh_clear()
    finally:
        for c in tracks:
            c.mute = False
    worst.sort(reverse=True)
    return worst, sorted(body.items(), key=lambda kv: -kv[1])


try:
    window = bpy.context.window_manager.windows[0]
    scene = window.scene
    area = next(a for a in window.screen.areas if a.type == "VIEW_3D")
    region = next(r for r in area.regions if r.type == "WINDOW")
    root = next(o for o in scene.objects if getattr(o, "mmd_type", "") == "ROOT")
    from mmd_tools.core.model import Model

    rig = Model(root)
    arm = rig.armature()
    meshes = list(rig.meshes())

    vmd_bones, vmd_morphs, blink_frame = read_vmd(VMD)
    have = {pb.mmd_bone.name_j for pb in arm.pose.bones if pb.mmd_bone.name_j} | set(arm.data.bones.keys())
    missing = [(n, c) for n, c in vmd_bones.most_common() if n not in have]
    heavy = [(n, c) for n, c in missing if c > 1]
    morph_names = {m.name for m in root.mmd_root.bone_morphs} | {m.name for m in root.mmd_root.vertex_morphs}
    print("T| VMD %d bones / %d keys; not on the model: %d (%d of them with more than one key: %s)" % (
        len(vmd_bones), sum(vmd_bones.values()), len(missing), len(heavy),
        ", ".join("%s(%d)" % (esc(n), c) for n, c in heavy[:12]) or "-"))
    print("T| VMD live morphs: %s | model lacks: %s" % (
        ", ".join("%s(%d)" % (esc(n), c) for n, c in vmd_morphs.most_common(8)),
        ", ".join(esc(n) for n in vmd_morphs if n not in morph_names) or "none"))

    with bpy.context.temp_override(window=window, screen=window.screen, area=area, region=region,
                                   scene=scene, view_layer=window.view_layer):
        if window.screen.is_animation_playing:
            bpy.ops.screen.animation_cancel(restore_frame=False)
        # rest pose first: the physics binding, then the morph slider, then the motion
        if not root.mmd_root.is_built:
            rig.build()
        bound = sum(1 for pb in arm.pose.bones if "mmd_tools_rigid_track" in pb.constraints)
        if rig.morph_slider.placeholder(binded=True) is None:
            rig.morph_slider.create()
            rig.morph_slider.bind()
        bpy.ops.object.select_all(action="DESELECT")
        stack = [root]
        while stack:
            obj = stack.pop()
            try:
                obj.hide_set(False)
                obj.select_set(True)
            except RuntimeError:
                pass
            stack.extend(obj.children)
        window.view_layer.objects.active = root
        bpy.ops.mmd_tools.import_vmd(filepath=VMD, scale=SCALE, margin=0, bone_mapper="PMX",
                                     update_scene_settings=True)
        world = scene.rigidbody_world
        if world is not None:
            world.enabled = True
            world.point_cache.frame_start = scene.frame_start
            world.point_cache.frame_end = scene.frame_end
        action = arm.animation_data.action if arm.animation_data else None
        animated = len({fc.data_path.split('"')[1] for fc in action.fcurves if '"' in fc.data_path}) if action else 0
        print("T| motion frames %d-%d | %d bones animated | %d bones ride dynamic rigid bodies" % (
            scene.frame_start, scene.frame_end, animated, bound))

        step = max(1, (scene.frame_end - scene.frame_start) // 11)
        frames = list(range(scene.frame_start, scene.frame_end + 1, step))[:12]
        worst, body = stretch_report(scene, arm, meshes, frames)
        print("T| posed stretch worst: " + " | ".join(
            "f%d %.1fx (%d edges>3x) %s %s/%s" % (f, r, n, m[:14], esc(a), esc(b)) for r, n, f, m, a, b in worst[:3]))
        print("T| body-bone edges >3x (cloth excluded): %s" % (
            ", ".join("%s %.1fx" % (esc(k), v) for k, v in body[:6]) or "none"))

        dyn = [o for o in scene.objects if getattr(o, "mmd_type", "") == "RIGID_BODY" and o.rigid_body
               and o.rigid_body.type == "ACTIVE" and not o.rigid_body.kinematic]
        far = []
        for f in range(scene.frame_start, min(scene.frame_end, scene.frame_start + 240) + 1):
            scene.frame_set(f)
            if dyn and (f - scene.frame_start) % 24 == 0:
                bpy.context.view_layer.update()
                hips = (arm.matrix_world @ arm.pose.bones[HIPS].head) if HIPS in arm.pose.bones else arm.matrix_world.translation
                far.append((f,) + max(((o.matrix_world.translation - hips).length, o.name) for o in dyn))
        print("T| physics: %d dynamic bodies; max distance from hips per second: %s" % (
            len(dyn), " ".join("f%d=%.2fm" % (f, d) for f, d, _ in far) or "-"))
        blown = [(f, d, n) for f, d, n in far if d > 1.5]
        print("T| physics blow-ups (>1.5 m): %s" % (", ".join("f%d %s %.1fm" % (f, esc(n), d) for f, d, n in blown) or "none"))

        if blink_frame is not None:
            scene.frame_set(blink_frame)
            keys = rig.morph_slider.placeholder().data.shape_keys.key_blocks
            live = {k.name: round(k.value, 2) for k in keys if k.value > 0.05}
            print("T| at full-blink frame %d live morphs: %s" % (blink_frame, esc(live)))

        root.mmd_root.show_rigid_bodies = False
        root.mmd_root.show_joints = False
        root.mmd_root.show_armature = False
        space = area.spaces.active
        space.shading.type = "SOLID"
        space.shading.color_type = "TEXTURE"
        space.region_3d.view_perspective = "PERSP"
        bpy.ops.object.select_all(action="DESELECT")
        for me in meshes:
            me.select_set(True)
        bpy.ops.view3d.view_axis(type="FRONT")
        bpy.ops.view3d.view_selected()
        bpy.ops.object.select_all(action="DESELECT")
        scene.sync_mode = "NONE"
        scene.frame_set(scene.frame_start)
        bpy.ops.screen.animation_play()
    print("T| playing:", window.screen.is_animation_playing)
except Exception:
    traceback.print_exc()
