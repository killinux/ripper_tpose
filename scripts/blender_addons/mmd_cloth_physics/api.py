"""Script entry points: what the batch exporters call, what the UI wraps."""
import bpy

from . import analyze, build, collide
from .presets import PRESETS


def model_of(obj):
    from mmd_tools.core.model import Model

    root = obj
    while root is not None and getattr(root, "mmd_type", "") != "ROOT":
        root = root.parent
    if root is None:
        root = next((o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT"), None)
    if root is None:
        raise RuntimeError("no mmd_tools model in the scene")
    model = Model(root)
    arm = model.armature()
    if arm is None:
        raise RuntimeError("the mmd_tools model has no armature")
    meshes = [m for m in model.meshes()]
    return model, root, arm, meshes


def analyze_model(obj, body_regex=None, prop_regex=r"\bProp\d*$", include_hair=True,
                  min_weight=2.0, skin=None):
    """The garments of the model that contains ``obj``."""
    model, root, arm, meshes = model_of(obj)
    with_rigid = set(build.existing_rigids().keys())
    return analyze.find_garments(arm, meshes, body_regex, prop_regex, include_hair,
                                 min_weight, with_rigid, skin=skin)


def setup(obj, garments=None, presets=None, body_regex=None, prop_regex=r"\bProp\d*$",
          include_hair=True, lattice=True, reverse_joints=False, measure_skin=True,
          thickness_scale=1.0, body_colliders=True, log=print, collision="classes", seat=True,
          attach_ends=True, hair_collision="classes", loosen=1.0, legs_inside="leave"):
    """Analyse (unless ``garments`` is given), build colliders if the model has
    none, then rigid bodies and joints for every enabled garment.

    ``presets`` maps a garment name (or its stem) to a preset key and overrides
    the automatic choice.  ``collision``: "classes" (default) gives the body
    colliders a group per body part and every cloth body the parts it does not
    start inside (collide.py); "near" is the rule before 2026-10-18 (cloth
    starting near the body collides with nothing).  ``seat`` moves each box
    onto its cloth; ``attach_ends`` ties a chain whose end is sewn onto another
    body to that body too.  With "classes": ``hair_collision`` "none" makes the
    hair collide with nothing (no chatter against the shoulders, as the ROE
    exports had it); ``loosen`` > 1 widens the joint limits of every colliding
    chain by that factor (less twitching where a leg pushes a hem past its
    limit, more swing) - both measured 2026-10-24, collide.py; ``legs_inside``
    "collide" lets cloth that starts inside a leg collider hit the legs anyway
    (pushed out in the first frames; tight skirts).  Returns a report dict for
    manifests."""
    model, root, arm, meshes = model_of(obj)
    skin = analyze.SkinIndex(arm, meshes)
    if garments is None:
        garments = analyze_model(obj, body_regex, prop_regex, include_hair, skin=skin)
    presets = presets or {}
    for garment in garments:
        key = presets.get(garment.name) or presets.get(garment.stem)
        if key in PRESETS:
            garment.preset = key
    unit = analyze.unit_scale(meshes)
    options = {"lattice": lattice, "reverse_joints": reverse_joints,
               "measure_skin": measure_skin, "thickness_scale": thickness_scale, "unit": unit,
               "skin": skin, "collision": collision, "seat": seat}
    report = {"garments": [], "rigid_bodies": 0, "joints": 0, "lattice": 0, "body_colliders": 0,
              "unit": round(unit, 4)}

    def work():
        if body_colliders and not build.kinematic_shapes():
            report["body_colliders"] = build.ensure_body_colliders(model, arm, meshes, log, unit, skin)
        options["colliders"] = analyze.collider_shapes(list(model.rigidBodies()))
        for garment in garments:
            if not garment.enabled:
                continue
            rigids, joints, lat = build.build_garment(model, arm, meshes, garment, options, log)
            entry = garment.as_dict()
            entry.update({"rigid_bodies": rigids, "joints": joints, "lattice": lat})
            report["garments"].append(entry)
            report["rigid_bodies"] += rigids
            report["joints"] += joints + lat
            report["lattice"] += lat
        if attach_ends:
            report["attached_ends"] = build.attach_loose_ends(model, arm, garments, options, log)
            report["joints"] += report["attached_ends"]
        if collision == "classes":
            have = build.existing_rigids()
            hair = {have[b].name for g in garments if g.enabled and g.preset == "hair" for b in g.bones if b in have}
            report["collision"] = collide.assign(arm, list(model.rigidBodies()), unit, log=log, keep_size=hair,
                                                 no_collide=hair if hair_collision == "none" else (),
                                                 legs_inside=legs_inside)
            if loosen != 1.0:
                report["loosened_joints"] = collide.loosen_colliding(
                    list(model.joints()), report["collision"].get("classes", {}), loosen, log=log)

    build.with_world_off(work)
    bpy.context.view_layer.update()
    if log:
        log("mmd_cloth_physics: %d garments, %d rigid bodies, %d joints (%d lattice)"
            % (len(report["garments"]), report["rigid_bodies"], report["joints"],
               report["lattice"]))
    return report
