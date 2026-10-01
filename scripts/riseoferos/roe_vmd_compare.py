"""Side-by-side check video for make_roe_vmd.py: the game mesh driven straight from the decoded clip
(left) and the PMX playing the exported VMD through mmd_tools' own importer (right).

  blender -b --factory-startup --python roe_vmd_compare.py -- <clip.json> <model.pmx> <motion.vmd> <game.fbx> <out.mp4>
  ... -- <her.json> <her.pmx> <her.vmd> <her.fbx> <his.json> <his.pmx> <his.vmd> <his.fbx> <out.mp4> [--gap 1.2]
                                                       (an H scene: both actors on each side, in their scene places)

(render_roe_motion_videos.py / render_roe_eros_videos.py run it per clip; make_roe_vmd.py --compare calls
render_compare directly.)
Workbench solid shading, orthographic camera, no physics: the point is whether the body moves the same, so hair
and cloth chains of the PMX stay at rest here (render_pmx_dance.py shows the simulated version).
"""
import json
import math
import os
import re
import sys

import addon_utils
import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_roe_vmd import FRAME0, SCALE, Game, fit_scale_offset, topo  # noqa: E402

GAP = 0.85      # metres each model sits off the centre line (the outfits carry wide props)


def drive_game_armature(arm, game, frames):
    """Key the AssetStudio FBX armature (game bone names) from the decoded clip, full transforms."""
    rest = game.rest_world()
    bones = topo(arm)
    pairs = [(rest[game.index[b.name]].translation, arm.matrix_world @ b.head_local)    # Bip001 / a00's Bip000
             for b in bones if b.name in game.index and re.match(r"Bip\d{3} ", b.name)]
    s, off, resid = fit_scale_offset(pairs)
    print("game FBX fit: scale %.4f, worst residual %.1f mm over %d joints" % (s, resid * 1000, len(pairs)))
    ao = arm.matrix_world
    to_world = Matrix.Translation(off) @ Matrix.Scale(s, 4)
    rl = {b.name: b.matrix_local for b in bones}
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
    for f in frames:
        w = game.world(f)
        d = {}
        for b in bones:
            gi = game.index.get(b.name)
            if gi is None:
                d[b.name] = d[b.parent.name] if b.parent else Matrix()
                continue
            dw = to_world @ w[gi] @ rest[gi].inverted() @ to_world.inverted()
            d[b.name] = ao.inverted() @ dw @ ao
        for b in bones:
            parent = d[b.parent.name] if b.parent else Matrix()
            try:
                basis = rl[b.name].inverted() @ parent.inverted() @ d[b.name] @ rl[b.name]
            except ValueError:      # parent at scale 0 (a00's hidden semen bones): the child just rides it
                basis = Matrix()
            # scale too: the game side must look like the game.  g04's showcase clips hold the fan at
            # 15% of its bind (battle) size; dropping the scale here hid that the PMX, which cannot
            # scale bones, shows it 6.7x too big
            loc, rot, sc = basis.decompose()
            pb = arm.pose.bones[b.name]
            pb.location, pb.rotation_quaternion, pb.scale = loc, rot, sc
            pb.keyframe_insert("location", frame=f + FRAME0)
            pb.keyframe_insert("rotation_quaternion", frame=f + FRAME0)
            pb.keyframe_insert("scale", frame=f + FRAME0)


def label(text, x, font):
    cu = bpy.data.curves.new("label", "FONT")
    cu.body = text
    cu.font = font
    cu.size = 0.09
    cu.align_x = "CENTER"
    ob = bpy.data.objects.new("label", cu)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (x, -0.3, 1.95)
    ob.rotation_euler = (1.5708, 0, 0)
    mat = bpy.data.materials.new("label")
    mat.diffuse_color = (1.0, 0.85, 0.4, 1.0)
    cu.materials.append(mat)
    return ob


def render_compare(game, pmx, vmd, game_fbx, out_mp4):
    render_pairs([(game, pmx, vmd, game_fbx)], out_mp4)


def render_pairs(actors, out_mp4, gap=GAP):
    """``actors``: [(Game, pmx, vmd, game fbx)].  Every game model goes left, every PMX right, each keeping its
    place in the scene (an H scene's two actors share one origin, as in the game)."""
    scene = bpy.context.scene
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    game = max((a[0] for a in actors), key=lambda g: len(g.frames))
    frames = list(range(len(game.frames)))
    # some outfits skin a mesh to the root node and Blender's importer then dies on a missing
    # bind setup (KeyError: pc_g04_hd); the add-on's scoped importer fix supplies it
    from roe_xps_addon import import_fbx_compat
    addon_utils.enable("mmd_tools", default_set=False)
    garm = root = None
    for actor_game, pmx, vmd, game_fbx in actors:
        # left: the game
        before = set(bpy.data.objects)
        import_fbx_compat(filepath=game_fbx, automatic_bone_orientation=False)
        arm = next(o for o in bpy.data.objects if o not in before and o.type == "ARMATURE")
        top = arm
        while top.parent:
            top = top.parent
        bpy.context.view_layer.update()
        drive_game_armature(arm, actor_game, list(range(len(actor_game.frames))))
        top.location.x -= gap
        # right: PMX + VMD through mmd_tools
        before = set(bpy.data.objects)
        bpy.ops.mmd_tools.import_model(filepath=pmx, scale=SCALE, types={"MESH", "ARMATURE", "MORPHS", "DISPLAY"})
        mroot = next(o for o in bpy.data.objects if o not in before and getattr(o, "mmd_type", "") == "ROOT")
        for o in bpy.context.view_layer.objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = mroot
        mroot.select_set(True)
        bpy.ops.mmd_tools.import_vmd(filepath=vmd, scale=SCALE, margin=0, update_scene_settings=False)
        mroot.location.x += gap
        garm, root = garm or arm, root or mroot
    if os.environ.get("ROE_COMPARE_FAN"):
        import numpy as np
        group = os.environ["ROE_COMPARE_FAN"]
        print("armatures:", [(o.name, len(o.data.bones)) for o in bpy.data.objects if o.type == "ARMATURE"])
        meshes = [o for o in bpy.data.objects if o.type == "MESH" and group in o.vertex_groups]
        for o in meshes:
            print("fan mesh", o.name, "deformed by", [m.object.name for m in o.modifiers if m.type == "ARMATURE"])
        for f in (30, 50, 60):
            scene.frame_set(f + FRAME0)
            deps = bpy.context.evaluated_depsgraph_get()
            for o in meshes:
                gi = o.vertex_groups[group].index
                ids = [v.index for v in o.data.vertices if any(g.group == gi and g.weight > 0.9 for g in v.groups)]
                ev = o.evaluated_get(deps)
                pts = np.array([tuple(ev.matrix_world @ ev.data.vertices[i].co) for i in ids])
                c = pts - pts.mean(0)
                vt = np.linalg.svd(c)[2]
                n, d0 = vt[2], vt[0]
                print("f%d %-28s %d verts plane normal %s  long axis %s  centre %s" % (
                    f, o.name[:28], len(ids), np.round(n * np.sign(n[1] or 1), 3),
                    np.round(d0 * np.sign(d0[2] or 1), 3), np.round(pts.mean(0) - np.array(tuple(o.matrix_world.translation)), 3)))
        return
    if os.environ.get("ROE_COMPARE_DEBUG"):
        from mmd_tools.core.model import Model
        parm = Model(root).armature()
        pj = {pb.mmd_bone.name_j: pb for pb in parm.pose.bones}
        pj.update({pb.mmd_bone.name_e: pb for pb in parm.pose.bones          # game names of shortened bones
                   if pb.mmd_bone.name_e and pb.mmd_bone.name_e not in pj})
        for f in [int(x) for x in os.environ["ROE_COMPARE_DEBUG"].split(",")]:
            scene.frame_set(f + FRAME0)
            rows = []
            for gpb in garm.pose.bones:
                ppb = pj.get(gpb.name)
                if ppb is None:
                    continue
                dg = (garm.matrix_world @ gpb.matrix).to_quaternion() @ \
                    (garm.matrix_world @ gpb.bone.matrix_local).to_quaternion().inverted()
                dp = (parm.matrix_world @ ppb.matrix).to_quaternion() @ \
                    (parm.matrix_world @ ppb.bone.matrix_local).to_quaternion().inverted()
                a = math.degrees(dg.rotation_difference(dp).angle)
                rows.append((min(a, 360 - a), gpb.name))
            rows.sort(reverse=True)
            print("compare f%d worst rotation deltas game vs pmx: %s" % (f, [("%s %.1f" % (n, a)) for a, n in rows[:14]]))
            print("compare f%d props: %s" % (f, [("%s %.1f" % (n, a)) for a, n in rows
                                                 if any(k in n for k in ("fan", "Fan", "Dummy001", "Prop1", "cons"))]))
        return

    # frame both models over the whole motion
    lo, hi = Vector((1e9,) * 3), Vector((-1e9,) * 3)
    deps = bpy.context.evaluated_depsgraph_get()
    for f in frames[::20]:
        scene.frame_set(f + FRAME0)
        deps = bpy.context.evaluated_depsgraph_get()
        for o in bpy.data.objects:
            if o.type != "MESH" or o.name.startswith("label"):
                continue
            ev = o.evaluated_get(deps)
            for c in ev.bound_box:
                p = ev.matrix_world @ Vector(c)
                lo = Vector(map(min, lo, p))
                hi = Vector(map(max, hi, p))
    centre = (lo + hi) / 2
    height = hi.z - lo.z
    width = hi.x - lo.x

    font = bpy.data.fonts.load("C:/Windows/Fonts/msyh.ttc")
    for text, x in (("游戏原版（解码的动作）", -gap), ("PMX + 导出的 VMD", gap)):
        ob = label(text, x, font)
        ob.location.z = hi.z + 0.08
        ob.location.y = centre.y

    cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    scene.collection.objects.link(cam)
    scene.camera = cam
    # orthographic: with a perspective camera the two models, 1.7 m apart, were seen ~19 deg apart and
    # the g04 fan looked edge-on on one side and open on the other although both had the same pose
    cam.data.type = "ORTHO"
    span = max(width + 0.3, (height + 0.35) * 16 / 9)
    cam.data.ortho_scale = span
    dist = 8.0
    target = Vector((centre.x, centre.y, centre.z + 0.06))
    cam.location = target + Vector((0.18, -1.0, 0.08)).normalized() * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    world = bpy.data.worlds.new("bg")
    world.color = (0.32, 0.33, 0.36)
    scene.world = world
    print("framing: bbox %s .. %s, camera distance %.2f m" % (tuple(round(v, 2) for v in lo),
                                                             tuple(round(v, 2) for v in hi), dist))

    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.show_cavity = True
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.fps = int(round(game.fps))
    scene.frame_start, scene.frame_end = frames[0] + FRAME0, frames[-1] + FRAME0
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.filepath = out_mp4
    os.makedirs(os.path.dirname(os.path.abspath(out_mp4)), exist_ok=True)
    if os.environ.get("ROE_COMPARE_STILLS"):
        scene.render.image_settings.file_format = "PNG"
        def probe(tag):
            deps = bpy.context.evaluated_depsgraph_get()
            for o in bpy.data.objects:
                if o.type == "MESH" and "Right_fan_02" in o.vertex_groups:
                    gi = o.vertex_groups["Right_fan_02"].index
                    ev = o.evaluated_get(deps)
                    ids = [v.index for v in o.data.vertices if any(g.group == gi and g.weight > 0.9 for g in v.groups)][:3]
                    print("probe %s frame %d %s %s" % (tag, scene.frame_current, o.name[:16],
                                                       [tuple(round(c, 3) for c in ev.matrix_world @ ev.data.vertices[i].co) for i in ids]))
        for f in [int(x) for x in os.environ["ROE_COMPARE_STILLS"].split(",")]:
            scene.frame_set(f + FRAME0)
            probe("before")
            scene.render.filepath = os.path.splitext(out_mp4)[0] + "_f%03d.png" % f
            bpy.ops.render.render(write_still=True)
            probe("after")
        return
    bpy.ops.render.render(animation=True)
    print("compare video:", out_mp4)


def main():
    """-- <clip.json> <pmx> <vmd> <game.fbx> [<clip.json> <pmx> <vmd> <game.fbx> ...] <out.mp4> [--gap metres]"""
    args = sys.argv[sys.argv.index("--") + 1:]
    gap = GAP
    if "--gap" in args:
        gap = float(args[args.index("--gap") + 1])
        del args[args.index("--gap"):args.index("--gap") + 2]
    out_mp4 = args[-1]
    groups = [args[k:k + 4] for k in range(0, len(args) - 1, 4)]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    render_pairs([(Game(json.load(open(js, encoding="utf-8"))), pmx, vmd, fbx) for js, pmx, vmd, fbx in groups],
                 out_mp4, gap)


if __name__ == "__main__":
    main()
