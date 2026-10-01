"""Physics preview of several PMX + VMD pairs in one scene - an H scene's two actors - with the camera fitted to the
whole motion.

  blender -b --python roe_eros_preview.py -- <out.mp4> <pmx> <vmd> [<pmx> <vmd> ...]

render_pmx_dance.py does this for one model; this one takes any number, which share the scene origin as the game's
two prefabs do.  Run it WITHOUT --factory-startup (mmd_tools comes from the user's add-ons).  For each pair: import
the PMX with its physics, Model.build() (otherwise no bone reads the simulation), morph sliders, the VMD with a
30-frame lead-in (the bodies ease from the rest pose instead of being flung).  The VMD import selects only that
model's objects: with everything selected one VMD would drive both.  Then MMD-like physics (mmd_physics/mmd_like.py),
a floor collider (roe_preview_scene.py: hair and breasts rest on the floor instead of hanging through it), bake (a
render on a live cache does not replay the stepped simulation), save the .blend beside the mp4, fit a three-quarter
landscape camera to the meshes over the motion, render the motion only: the lead-in is simulated but cut, since it
starts from the standing rest pose.
"""
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "mmd_physics"))
sys.path.insert(0, HERE)
from mmd_like import mmd_like_physics  # noqa: E402
from roe_preview_scene import add_floor_collider, motion_box  # noqa: E402

SCALE = 0.08
MARGIN = 30
YAW = 25.0          # degrees round from the front, towards the models' left


def load_pair(pmx, vmd):
    from mmd_tools.core.model import Model

    before = set(bpy.data.objects)
    bpy.ops.mmd_tools.import_model(filepath=pmx, scale=SCALE, types={"MESH", "ARMATURE", "MORPHS", "PHYSICS"})
    root = next(o for o in bpy.data.objects if o not in before and getattr(o, "mmd_type", "") == "ROOT")
    rig = Model(root)
    rig.build()
    rig.morph_slider.create()
    rig.morph_slider.bind()
    bpy.ops.object.select_all(action="DESELECT")
    for obj in [root] + list(root.children_recursive):
        if obj.type in ("ARMATURE", "MESH", "EMPTY"):
            try:
                obj.select_set(True)
            except RuntimeError:
                pass
    bpy.context.view_layer.objects.active = root
    bpy.ops.mmd_tools.import_vmd(filepath=vmd, scale=SCALE, margin=MARGIN, bone_mapper="PMX",
                                 update_scene_settings=True)
    return root


def fit_camera(scene, camera):
    """What the meshes show over the motion (not the 30 lead-in frames, whose rest pose spreads the arms; a scale
    morph's folded vertices and the outer 0.25% of the points per axis left out) inside a 1280x720 frame seen from
    YAW degrees round and slightly above; the distance comes from the box's projected corners."""
    meshes = [o for o in scene.objects if o.type == "MESH" and o.visible_get()
              and not o.name.startswith("floor") and o.dimensions.length < 20]
    lo, hi = (Vector(v) for v in motion_box(scene, meshes, scene.frame_start + MARGIN, scene.frame_end, 3))
    lo.z = max(lo.z, -0.05)
    centre = (lo + hi) / 2
    yaw = math.radians(YAW)
    back = Vector((math.sin(yaw), -math.cos(yaw), 0.18)).normalized()      # from the centre towards the camera
    forward = -back
    right = forward.cross(Vector((0, 0, 1))).normalized()
    up = right.cross(forward)
    tan_h = 18.0 / 50.0                                  # 50 mm lens, 36 mm sensor across the 1280 width
    tan_v = tan_h * 720 / 1280
    dist = 0.5
    for x in (lo.x, hi.x):
        for y in (lo.y, hi.y):
            for z in (lo.z, hi.z):
                v = Vector((x, y, z)) - centre
                depth = v.dot(forward)
                dist = max(dist, abs(v.dot(right)) / tan_h - depth, abs(v.dot(up)) / tan_v - depth)
    dist *= 1.06
    camera.location = centre + back * dist
    camera.rotation_euler = forward.to_track_quat("-Z", "Y").to_euler()
    print("camera: bbox %s .. %s, distance %.2f m" % (tuple(round(v, 2) for v in lo), tuple(round(v, 2) for v in hi), dist))


def main():
    argv = sys.argv[sys.argv.index("--") + 1:]
    out_mp4 = argv[0]
    pairs = list(zip(argv[1::2], argv[2::2]))
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="mmd_tools")
    end = 0
    for pmx, vmd in pairs:
        load_pair(pmx, vmd)
        end = max(end, bpy.context.scene.frame_end)
    scene = bpy.context.scene
    scene.frame_end = end
    converted = mmd_like_physics(scene, SCALE, 98.0, None)
    world = scene.rigidbody_world
    if world is not None:
        world.enabled = True
        world.point_cache.frame_start = scene.frame_start
        world.point_cache.frame_end = scene.frame_end
    print("physics: MMD-like joints (%d converted), %d rigid bodies, frames %d-%d"
          % (converted, len(world.collection.objects) if world and world.collection else 0,
             scene.frame_start, scene.frame_end))

    scene.render.engine = "BLENDER_EEVEE"
    scene.render.film_transparent = False
    scene.view_settings.view_transform = "Standard"
    sky = bpy.data.worlds.new("preview_world")
    sky.use_nodes = True
    sky.node_tree.nodes["Background"].inputs[0].default_value = (0.34, 0.34, 0.37, 1.0)
    sky.node_tree.nodes["Background"].inputs[1].default_value = 1.35
    scene.world = sky
    for name, energy, rotation in (("key", 3.2, (0.95, 0.0, 0.65)), ("fill", 1.1, (1.15, 0.0, -2.2))):
        lamp = bpy.data.objects.new(name, bpy.data.lights.new(name, type="SUN"))
        lamp.data.energy = energy
        lamp.rotation_euler = rotation
        scene.collection.objects.link(lamp)
    floor_mesh = bpy.data.meshes.new("floor")
    floor_mesh.from_pydata([(-5, -5, 0), (5, -5, 0), (5, 5, 0), (-5, 5, 0)], [], [(0, 1, 2, 3)])
    floor = bpy.data.objects.new("floor", floor_mesh)
    scene.collection.objects.link(floor)
    floor_material = bpy.data.materials.new("floor")
    floor_material.diffuse_color = (0.28, 0.28, 0.30, 1.0)
    floor_mesh.materials.append(floor_material)

    if scene.rigidbody_world is not None:
        add_floor_collider(scene)      # the floor above is only a picture; the physics lands on this one
        cache = scene.rigidbody_world.point_cache
        with bpy.context.temp_override(scene=scene, point_cache=cache):
            bpy.ops.ptcache.bake(bake=True)
        print("physics baked: frames %d-%d" % (cache.frame_start, cache.frame_end))

    camera = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
    camera.data.lens = 50
    scene.collection.objects.link(camera)
    scene.camera = camera
    fit_camera(scene, camera)
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.eevee.taa_render_samples = 16
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.filepath = out_mp4
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(os.path.splitext(out_mp4)[0] + ".blend"), check_existing=False)
    # the lead-in is simulated (baked above) but not shown: it starts from the rest pose, so every part opened
    # with both actors standing in the A-pose and dropping into the scene - "the head falls down in the middle"
    scene.frame_start += MARGIN
    bpy.ops.render.render(animation=True)
    print("ROE_EROS_PREVIEW_DONE %s" % out_mp4)


if __name__ == "__main__":
    main()
