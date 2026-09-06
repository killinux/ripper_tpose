"""Diagnose and repair limb helper bones that hang off the wrong bone.

WHY THIS EXISTS
---------------
Game rigs carry small "helper" bones next to the real joints — twist correctives
(``ForeTwist``, ``ThighTwist``, ``CalfTwist``, ``UpArmTwist``) and joint pads
(``Point_elbow``, ``AC elbow``, ``knee_L``, ``muscle_elbow``).  They are not
decoration: they often hold more skin than the joint itself.  On the Rise of
Eros male base ``ForeTwist`` holds 309 vertices and 246 units of weight around
the wrist, while the hand bone holds 193.

The exporter's rigs hang those helpers off whatever bone was convenient when the
character was authored, and the game fixes it at runtime with constraints that do
not survive an export:

  * ``ForeTwist`` sits under the UPPER ARM, as a *sibling* of the forearm.
  * ``ThighTwist`` sits under the SPINE, as a *sibling* of the thigh.

The skin still belongs to the forearm and the thigh.  So the moment the limb
moves and the helper does not, the two halves of the same surface separate:

  * straightening the elbow into the MMD rest pose ripped the wrist open;
  * dancing pulled the thigh skin along with the torso while the calf skin
    followed the leg, leaving a hard seam ringing the knee.

The knee case is the nastier one, because it is invisible in the rest pose — the
geometry gate in the exporter cannot see it.  Only a posed render shows it.

HOW THE REPAIR DECIDES
----------------------
Re-parenting is safe in itself (head, tail and roll are preserved, so nothing
moves in the rest pose), but re-parenting the WRONG bone is not: ``butt_*``,
``skirt_*`` and ``Pauldrons_*`` sit just as close to the thigh and shoulder
heads, and hanging them off a limb would swing a skirt with the leg.

So two independent signals have to agree:

  1. **Name** — the bone matches the 3ds Max Biped helper convention
     (``twist``/``elbow``/``knee``/``ankle``/``muscle strand``), or it sits
     exactly on a joint.  This is a naming *convention* shared by the rigs, not
     a guess about one model.
  2. **Skin** — the weighted centroid of the vertices the bone actually drives
     is projected onto every limb segment (shoulder→elbow, elbow→wrist,
     hip→knee, knee→ankle).  Limbs are scored by how squarely the skin sits
     inside them: sideways distance, plus a penalty for falling outside the
     segment, plus a small bias toward the distal bone so a pad sitting exactly
     on a joint follows the half that turns.

A bone is moved only when the winning limb is not the one it already hangs
under, and a helper whose own parent is being moved is left to travel with it.

USAGE
-----
  # look only — prints a table, changes nothing
  blender --background --python fix_limb_helpers.py -- --input model.blend

  # repair and save a copy
  blender --background --python fix_limb_helpers.py -- --input model.blend \\
      --fix --save model_fixed.blend

  # repair in place (overwrite the input .blend)
  blender --background --python fix_limb_helpers.py -- --input model.blend --fix --save -

A ``.pmx`` can be given as input too (mmd_tools imports it); use ``--save`` to
write a .blend and re-export from there.

Joints come from the ROE Biped resolver in ``export_character_model_blender.py``
when it recognises the rig, otherwise from MMD bone names, so this works both
before and after the MMD conversion.
"""

import argparse
import importlib.util
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
WORKER = os.path.join(HERE, "export_character_model_blender.py")

# MMD fallbacks, in both spellings mmd_tools produces (左腕 and 腕.L).
MMD_SLOTS = {}
for _side, _jp, _suffix in (("left", "左", "L"), ("right", "右", "R")):
    for _role, _name in (("upper_arm_bone", "腕"), ("lower_arm_bone", "ひじ"),
                         ("hand_bone", "手首"), ("thigh_bone", "足"),
                         ("calf_bone", "ひざ"), ("foot_bone", "足首")):
        MMD_SLOTS["%s_%s" % (_side, _role)] = (_jp + _name, "%s.%s" % (_name, _suffix))


def load_worker():
    spec = importlib.util.spec_from_file_location("roe_char_worker", WORKER)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load %s" % WORKER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def open_input(path):
    if path.lower().endswith(".pmx"):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        bpy.ops.preferences.addon_enable(module="mmd_tools")
        bpy.ops.mmd_tools.import_model(filepath=path, scale=0.08,
                                       types={"MESH", "ARMATURE"})
    elif path:
        bpy.ops.wm.open_mainfile(filepath=path)
    armatures = [o for o in bpy.data.objects
                 if o.type == "ARMATURE" and "backup" not in o.name.lower()]
    if not armatures:
        raise SystemExit("no armature in %s" % (path or "the current file"))
    arm = max(armatures, key=lambda o: len(o.data.bones))
    meshes = [o for o in bpy.data.objects if o.type == "MESH"
              and any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]
    return arm, meshes


def resolve_slots(worker, arm):
    """Limb bone names, from the ROE Biped resolver or from MMD names."""
    try:
        slots, _missing = worker.resolve_roe_slots(arm)
        if slots.get("left_lower_arm_bone") and slots.get("left_calf_bone"):
            return slots, "ROE Biped"
    except Exception:
        pass
    bones = arm.data.bones
    slots = {}
    for role, names in MMD_SLOTS.items():
        for name in names:
            if name in bones:
                slots[role] = name
                break
    if not slots.get("left_lower_arm_bone"):
        raise SystemExit("could not identify the limb bones in this rig")
    return slots, "MMD names"


def d_bone_names(joint_name):
    """The MMD deform-chain twin of a limb bone: 足 -> 足D, ひざ.L -> ひざD.L.

    After the MMD conversion the leg mesh rides a parallel D chain that copies
    the FK bone's rotation, so a helper already sitting under 足D is exactly
    where it belongs even though its skin measures against 足.
    """
    if "." in joint_name:
        stem, suffix = joint_name.rsplit(".", 1)
        return (stem + "D." + suffix,)
    return (joint_name + "D",)


def already_on_deform_chain(arm, bone_name, joint_name):
    twins = d_bone_names(joint_name)
    bone = arm.data.bones.get(bone_name)
    while bone is not None:
        if bone.name in twins:
            return True
        bone = bone.parent
    return False


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(prog="fix_limb_helpers")
    parser.add_argument("--input", default="",
                        help=".blend or .pmx to inspect (default: the file Blender opened)")
    parser.add_argument("--fix", action="store_true", help="re-parent the misparented bones")
    parser.add_argument("--save", default="",
                        help="write the result here; '-' overwrites the input .blend")
    options = parser.parse_args(argv)

    worker = load_worker()
    arm, meshes = open_input(options.input)
    slots, source = resolve_slots(worker, arm)

    print("\narmature : %s (%d bones, %d skinned meshes)"
          % (arm.name, len(arm.data.bones), len(meshes)))
    print("limbs    : identified from %s" % source)

    if not meshes:
        raise SystemExit("no mesh is skinned to this armature, nothing to judge")

    # A rig imported straight from FBX is Y-up in armature space; the limb maths
    # is orientation-independent, but the ROE resolver expects Z-up.
    plans, report = worker.plan_joint_helper_moves(arm, meshes, slots)

    # On an already-converted rig the legs deform through the D chain, so a
    # helper under 足D/ひざD is correct even though its skin measures against 足.
    on_d_chain = {entry["bone"] for entry in report
                  if entry["verdict"] == "misparented"
                  and already_on_deform_chain(arm, entry["bone"], entry["belongs_to"])}
    for entry in report:
        if entry["bone"] in on_d_chain:
            entry["verdict"] = "ok (D chain)"
    plans = [plan for plan in plans if plan[0] not in on_d_chain]

    print("\n%-28s %-24s %-24s %6s %7s  %s"
          % ("helper bone", "current parent", "skin belongs to", "t", "lateral", "verdict"))
    print("-" * 118)
    for entry in sorted(report, key=lambda e: (e["verdict"] != "misparented", e["bone"])):
        print("%-28s %-24s %-24s %6s %7s  %s"
              % (entry["bone"][:28], entry["parent"][:24], entry["belongs_to"][:24],
                 "" if entry["t"] is None else "%.2f" % entry["t"],
                 "" if entry["lateral_ratio"] is None else "%.2f" % entry["lateral_ratio"],
                 entry["verdict"]))

    misparented = [e for e in report if e["verdict"] == "misparented"]
    print("\n%d helper bone(s) hang off the wrong limb; %d will be re-parented "
          "(the rest travel with their parent)." % (len(misparented), len(plans)))

    if not options.fix:
        if plans:
            print("Run again with --fix --save <out.blend> to repair.")
        return

    moved = worker.apply_joint_helper_moves(arm, plans)
    for line in moved:
        print("  moved  %s" % line)

    target = options.save
    if target == "-":
        target = options.input
    if target:
        if target.lower().endswith(".pmx"):
            raise SystemExit("--save writes a .blend; re-export the PMX from it")
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(target), check_existing=False)
        print("saved   %s" % os.path.abspath(target))
    else:
        print("(nothing written: pass --save to keep the repair)")


if __name__ == "__main__":
    main()
