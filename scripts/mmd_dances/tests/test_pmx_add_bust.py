"""Offline tests of pmx_add_bust.py on small synthetic models (no game, no Blender; needs the pmx module that ships
inside mmd_tools - skipped where it is not installed).

    python -m unittest discover -s scripts/mmd_dances/tests      # from the repo root
"""
import math
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

import pmx_add_bust as ab  # noqa: E402

try:
    PMX = ab.pmx_module()
except SystemExit:
    PMX = None

UNIT = ab.DEFAULTS["unit_cm"]


def bone(name, parent, location, name_e=""):
    b = PMX.Bone()
    b.name, b.name_e, b.parent, b.location = name, name_e, parent, list(location)
    b.displayConnection = -1
    return b


def vertex(co, weights):
    v = PMX.Vertex()
    v.co, v.normal, v.uv = list(co), [0.0, 0.0, -1.0], [0.0, 0.0]
    w = PMX.BoneWeight()
    if len(weights) == 1:
        w.type, w.bones, w.weights = w.BDEF1, [weights[0][0]], []
    else:
        w.type, w.bones, w.weights = w.BDEF2, [weights[0][0], weights[1][0]], [weights[0][1]]
    v.weight = w
    return v


def model(left=("Bip001 OPAI_L", "Bip001 OPAI_L02"), right=("Bip001 OPAI_R", "Bip001 OPAI_R02"),
          weight_next=True, torso_body=True):
    """全ての親 > 上半身 > 上半身2 > 上半身3 > (root > next) per side; a ring of 12 vertices around each breast,
    0.8 on the next bone (or the root when weight_next is False) and 0.2 on 上半身3; a static body on 上半身3."""
    m = PMX.Model()
    m.name, m.name_e, m.comment, m.comment_e = "test", "", "", ""
    m.header = PMX.Header()
    m.bones = [bone("全ての親", -1, (0, 0, 0)), bone("上半身", 0, (0, 14, 0)), bone("上半身2", 1, (0, 15, 0)),
               bone("上半身3", 2, (0, 16, 0))]
    centres = {}
    for side, names in ((1, left), (-1, right)):
        if not names:
            continue
        root = len(m.bones)
        m.bones.append(bone(names[0], 3, (0.6 * side, 16.7, -0.3)))
        if names[1]:
            m.bones.append(bone(names[1], root, (0.9 * side, 16.7, -1.0)))
        centre = (1.0 * side, 16.6, -1.4)
        centres[side] = centre
        carrier = len(m.bones) - 1 if (names[1] and weight_next) else root
        for k in range(12):
            a = 2 * math.pi * k / 12
            co = (centre[0] + 0.4 * math.cos(a), centre[1] + 0.4 * math.sin(a), centre[2])
            m.vertices.append(vertex(co, [(carrier, 0.8), (3, 0.2)]))
    m.vertices.append(vertex((0, 16.5, -0.8), [(3, 1.0)]))
    n = len(m.vertices)
    m.faces = [(i, (i + 1) % n, n - 1) for i in range(n - 1)]
    mat = PMX.Material()
    mat.name, mat.name_e = "skin", ""
    mat.diffuse, mat.specular, mat.shininess, mat.ambient = [1, 1, 1, 1], [0, 0, 0], 5.0, [0.5, 0.5, 0.5]
    mat.edge_color, mat.edge_size = [0, 0, 0, 1], 1.0
    mat.texture, mat.sphere_texture, mat.toon_texture = -1, -1, 0
    mat.vertex_count = 3 * len(m.faces)
    m.materials = [mat]
    frame = PMX.Display()
    frame.name, frame.name_e, frame.isSpecial, frame.data = "other", "", False, [(0, i) for i in range(len(m.bones))]
    m.display = [frame]
    if torso_body:
        r = PMX.Rigid()
        r.name, r.name_e, r.bone, r.collision_group_number, r.collision_group_mask = "上半身3", "", 3, 0, 64511
        r.type, r.size, r.location, r.rotation = 2, [1.0, 2.0, 0.0], [0, 16.5, 0.2], [0, 0, 0]
        r.mass, r.velocity_attenuation, r.rotation_attenuation, r.bounce, r.friction, r.mode = 1, 0.5, 0.5, 0, 0.5, 0
        m.rigids = [r]
    return m, centres


@unittest.skipIf(PMX is None, "mmd_tools' pmx module is not installed")
class FindTests(unittest.TestCase):
    def test_opai_and_xtra_names(self):
        for left, right in ((("Bip001 OPAI_L", "Bip001 OPAI_L02"), ("Bip001 OPAI_R", "Bip001 OPAI_R02")),
                            (("Xtra01Opp", "Xtra01Opp02"), ("Bip001 Xtra01", "Bip001 Xtra0102"))):
            m, _c = model(left, right)
            names = [b.name for b in m.bones]
            found = ab.find_breasts(m)
            self.assertEqual({s: (names[r], names[n]) for s, (r, n) in found.items()}, {1: left, -1: right})

    def test_unweighted_child_is_not_the_swing_bone(self):
        """g09: 右胸 carries the skin, its child chest_R02 nothing - the root itself swings."""
        m, _c = model(left=None, right=("右胸", "chest_R02"), weight_next=False)
        names = [b.name for b in m.bones]
        root, nxt = ab.find_breasts(m)[-1]
        self.assertEqual((names[root], nxt), ("右胸", None))

    def test_chest_l02_child_is_the_swing_bone(self):
        m, _c = model(left=("左胸", "chest_L02"), right=("右胸", "chest_R02"))
        names = [b.name for b in m.bones]
        found = ab.find_breasts(m)
        self.assertEqual({s: names[n] for s, (_r, n) in found.items()}, {1: "chest_L02", -1: "chest_R02"})

    def test_helpers_and_accessories_are_not_breasts(self):
        """左胸 beside a weighted Point_breast_UL helper; an AC breast_UL ornament beside OPAI bones."""
        for left, extra in ((("左胸", "Breast_L02"), "Point_breast_UL"), (("Bip001 OPAI_L", "Bip001 OPAI_L02"), "AC breast_UL")):
            m, _c = model(left=left)
            m.bones.append(bone(extra, 3, (0.5, 18.0, 0.5)))
            m.vertices.append(vertex((0.5, 18.0, 0.4), [(len(m.bones) - 1, 1.0)]))
            names = [b.name for b in m.bones]
            self.assertEqual(names[ab.find_breasts(m)[1][0]], left[0])

    def test_accessory_chain_on_a_breast_is_not_the_swing_bone(self):
        """c06: OPAI_R carries the skin and an ornament chain accessories01 hangs from it."""
        m, _c = model(right=("Bip001 OPAI_R", None))
        names = [b.name for b in m.bones]
        root = names.index("Bip001 OPAI_R")
        m.bones.append(bone("accessories01", root, (-0.9, 18.2, -0.8)))
        m.vertices.append(vertex((-0.9, 18.1, -0.8), [(len(m.bones) - 1, 1.0)]))
        self.assertEqual(ab.find_breasts(m)[-1], (root, None))

    def test_bones_by_name(self):
        m, _c = model(left=("boneA", "boneA2"), right=("boneB", "boneB2"))
        self.assertEqual(ab.find_breasts(m), {})
        found = ab.find_breasts(m, left="boneA", right="boneB")
        names = [b.name for b in m.bones]
        self.assertEqual({s: names[r] for s, (r, _n) in found.items()}, {1: "boneA", -1: "boneB"})


@unittest.skipIf(PMX is None, "mmd_tools' pmx module is not installed")
class AddTests(unittest.TestCase):
    def test_template_bodies_and_joints(self):
        m, centres = model()
        report = ab.add_bust(PMX, m, dict(ab.DEFAULTS))
        self.assertEqual(len(m.rigids), 1 + 4)
        self.assertEqual(len(m.joints), 2)
        names = [b.name for b in m.bones]
        for side, label in ((1, "左胸"), (-1, "右胸")):
            anchor = next(r for r in m.rigids if r.name == label)
            swing = next(r for r in m.rigids if r.bone == names.index("Bip001 OPAI_%s02" % ("L" if side > 0 else "R")))
            self.assertEqual((anchor.mode, anchor.type, anchor.collision_group_number, anchor.collision_group_mask),
                             (0, 0, 15, 0))
            self.assertAlmostEqual(anchor.size[0] * UNIT, 2.4, places=5)
            self.assertAlmostEqual(anchor.location[0], 0.75 * side, places=5)      # halfway to the next bone
            self.assertEqual(swing.mode, 1)
            for got, want in zip(swing.location, centres[side]):
                self.assertAlmostEqual(got, want, places=5)
            self.assertAlmostEqual(swing.size[0] * UNIT, 3.0, places=5)           # 0.8 x 0.4 u = 2.56 cm -> 3
            joint = next(j for j in m.joints if m.rigids[j.dest_rigid] is swing)
            self.assertIs(m.rigids[joint.src_rigid], anchor)
            self.assertEqual([round(math.degrees(x), 3) for x in joint.maximum_rotation], [10.0] * 3)
            self.assertEqual(list(joint.spring_rotation_constant), [0.0] * 3)
            self.assertEqual(report["sides"][label]["vertices"], 12)

    def test_roots_renamed_english_name_kept(self):
        m, _c = model()
        ab.add_bust(PMX, m, dict(ab.DEFAULTS))
        names = [b.name for b in m.bones]
        self.assertIn("左胸", names)
        self.assertIn("右胸", names)
        self.assertEqual(m.bones[names.index("左胸")].name_e, "Bip001 OPAI_L")
        m2, _c = model()
        ab.add_bust(PMX, m2, dict(ab.DEFAULTS), rename=False)
        self.assertNotIn("左胸", [b.name for b in m2.bones])

    def test_one_bone_breast_hangs_on_the_torso_body(self):
        m, _c = model(left=("左胸", None), right=("右胸", None))
        ab.add_bust(PMX, m, dict(ab.DEFAULTS))
        self.assertEqual(len(m.rigids), 1 + 2)
        for j in m.joints:
            self.assertEqual(m.rigids[j.src_rigid].name, "上半身3")
            self.assertEqual(m.rigids[j.dest_rigid].mode, 1)

    def test_one_bone_breast_without_a_body_above_is_skipped(self):
        m, _c = model(left=("左胸", None), right=("右胸", None), torso_body=False)
        report = ab.add_bust(PMX, m, dict(ab.DEFAULTS))
        self.assertEqual(len(m.rigids), 0)
        self.assertIn("skipped", report["sides"]["左胸"])

    def test_side_with_a_body_is_left_alone(self):
        m, _c = model()
        names = [b.name for b in m.bones]
        r = PMX.Rigid()
        r.name, r.name_e, r.bone, r.collision_group_number, r.collision_group_mask = "x", "", names.index(
            "Bip001 OPAI_L02"), 15, 0
        r.type, r.size, r.location, r.rotation = 0, [0.5, 0, 0], [1, 16.6, -1.4], [0, 0, 0]
        r.mass, r.velocity_attenuation, r.rotation_attenuation, r.bounce, r.friction, r.mode = 1, 0.5, 0.5, 0, 0.5, 1
        m.rigids.append(r)
        report = ab.add_bust(PMX, m, dict(ab.DEFAULTS))
        self.assertIn("skipped", report["sides"]["左胸"])
        self.assertNotIn("skipped", report["sides"]["右胸"])
        self.assertEqual(len(m.rigids), 2 + 2)

    def test_radius_is_kept_within_bounds(self):
        m, _c = model()
        opts = dict(ab.DEFAULTS, radius=(1.0, 2.0))
        ab.add_bust(PMX, m, opts)
        swing = [r for r in m.rigids if r.mode == 1]
        self.assertTrue(all(abs(r.size[0] * UNIT - 2.0) < 1e-6 for r in swing))   # 2.56 cm -> at most 2


@unittest.skipIf(PMX is None, "mmd_tools' pmx module is not installed")
class FileTests(unittest.TestCase):
    def test_written_file_differs_only_by_the_rig(self):
        m, _c = model()
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, "in.pmx"), os.path.join(tmp, "out", "out.pmx")
            PMX.save(src, m)
            report = ab.build(PMX, src, out, dict(ab.DEFAULTS), dry_run=False, bust=False)
            self.assertTrue(report["check"]["ok"], report["check"])
            self.assertEqual(report["check"]["renamed"], [("Bip001 OPAI_L", "左胸"), ("Bip001 OPAI_R", "右胸")])
            self.assertEqual(report["check"]["bodies"], "1 -> 5")
            with self.assertRaises(SystemExit):
                ab.build(PMX, src, src, dict(ab.DEFAULTS), dry_run=False, bust=False)

    def test_dry_run_writes_nothing(self):
        m, _c = model()
        with tempfile.TemporaryDirectory() as tmp:
            src, out = os.path.join(tmp, "in.pmx"), os.path.join(tmp, "out", "out.pmx")
            PMX.save(src, m)
            ab.build(PMX, src, out, dict(ab.DEFAULTS), dry_run=True)
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
