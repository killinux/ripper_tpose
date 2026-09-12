"""Garment presets: the numbers behind the rigid bodies and joints.

Every value is what MMD modellers hand-type in PMXEditor, collected from the
community recipes and two hand-tuned reference PMX files (see README):

* mass tapers root -> tip (energy at the tip is what makes a chain whip);
* damping high and equal (0.9-0.995: "fluffy"), friction 0 for cloth;
* vertical joints lock translation and limit rotation; the limits grow down
  the chain; twist about the bone stays small;
* springs are what holds a rest shape.  0 drapes, 30 is a sculpture that
  jiggles (the add-on this replaces used 30 for everything, which is why a
  ribbon looped over the shoulder in the T-pose stayed there through a dance);
* lattice (横ジョイント) joints tie neighbouring chains of a ring or sheet:
  a little translation, generous rotation, no spring.  They are the standard
  cure for legs poking through a skirt.

Angles are degrees in the joint's own frame, Blender order: about X = the
tangent axis (swing in/out, the big one), about Y = the radial axis (swing
sideways), about Z = along the bone (twist).  mmd_tools maps Blender
(X, Y, Z) to PMX (X, Z, Y), so in PMXEditor the same joint reads X swing /
Y twist / Z sideways, which is how reference skirts are set up.

A pair (root, tip) is interpolated over the rows of a chain.
"""

PRESETS = {
    # A ring of chains under 下半身/腰: the classic skirt.  Root row is
    # "physics + bone alignment" so the waist never drifts.
    "skirt": dict(
        label="裙 / 裙摆 (skirt)", shape="BOX",
        mass=(1.0, 0.4), lin_damp=(0.9, 0.95), ang_damp=(0.99, 0.99), friction=0.0,
        swing=(20.0, 50.0), side=(10.0, 25.0), twist=(5.0, 5.0),
        spring=(5.0, 0.0), thickness=0.012,
        lattice=True, lattice_lin=0.02, lattice_ang=(30.0, 30.0, 10.0), root_mode=2),
    # Coats, cloaks, capes: a heavier sheet that keeps some body.
    "coat": dict(
        label="外套 / 披风 (coat)", shape="BOX",
        mass=(1.0, 0.5), lin_damp=(0.92, 0.96), ang_damp=(0.99, 0.99), friction=0.0,
        swing=(15.0, 35.0), side=(8.0, 20.0), twist=(5.0, 5.0),
        spring=(15.0, 5.0), thickness=0.02,
        lattice=True, lattice_lin=0.015, lattice_ang=(20.0, 20.0, 10.0), root_mode=2),
    # A single strip: ribbon, streamer, sash tail.  Light, free, drapes.
    "ribbon": dict(
        label="飘带 / 绶带 (ribbon)", shape="BOX",
        mass=(0.6, 0.2), lin_damp=(0.9, 0.95), ang_damp=(0.98, 0.98), friction=0.0,
        swing=(30.0, 60.0), side=(20.0, 45.0), twist=(10.0, 20.0),
        spring=(2.0, 0.0), thickness=0.01,
        lattice=False, lattice_lin=0.0, lattice_ang=(0.0, 0.0, 0.0), root_mode=2),
    # Long hanging sleeves: like a ribbon but anchored to a forearm that moves
    # fast, so slightly more damping and a small spring at the root.
    "sleeve": dict(
        label="长袖 / 水袖 (sleeve)", shape="BOX",
        mass=(0.8, 0.3), lin_damp=(0.92, 0.96), ang_damp=(0.99, 0.99), friction=0.0,
        swing=(25.0, 50.0), side=(15.0, 35.0), twist=(8.0, 15.0),
        spring=(5.0, 0.0), thickness=0.012,
        lattice=True, lattice_lin=0.02, lattice_ang=(30.0, 30.0, 10.0), root_mode=2),
    # Tassels, pendants, ropes, bead strings: round, free, no spring.
    "tassel": dict(
        label="流苏 / 吊坠 / 绳 (tassel)", shape="CAPSULE",
        mass=(0.8, 0.3), lin_damp=(0.9, 0.95), ang_damp=(0.98, 0.98), friction=0.0,
        swing=(20.0, 40.0), side=(20.0, 40.0), twist=(10.0, 10.0),
        spring=(0.0, 0.0), thickness=0.0,
        lattice=False, lattice_lin=0.0, lattice_ang=(0.0, 0.0, 0.0), root_mode=1),
    # Hair: the Purifier Inase reference - capsules, +-10 all axes, no spring.
    "hair": dict(
        label="头发 (hair)", shape="CAPSULE",
        mass=(1.0, 0.6), lin_damp=(0.9, 0.9), ang_damp=(0.99, 0.99), friction=0.0,
        swing=(10.0, 10.0), side=(10.0, 10.0), twist=(10.0, 10.0),
        spring=(0.0, 0.0), thickness=0.0,
        lattice=False, lattice_lin=0.0, lattice_ang=(0.0, 0.0, 0.0), root_mode=1),
    # Things that should keep their sculpted shape and only shiver: feather
    # clusters, rib cages, armour plates on a chain.
    "ornament": dict(
        label="饰物 / 保形 (ornament)", shape="BOX",
        mass=(1.0, 1.0), lin_damp=(0.95, 0.95), ang_damp=(0.99, 0.99), friction=0.0,
        swing=(5.0, 8.0), side=(5.0, 8.0), twist=(3.0, 3.0),
        spring=(30.0, 30.0), thickness=0.015,
        lattice=False, lattice_lin=0.0, lattice_ang=(0.0, 0.0, 0.0), root_mode=2),
}

PRESET_ITEMS = [(key, value["label"], "") for key, value in PRESETS.items()]

# Name hints for the automatic preset choice, checked in order.
NAME_HINTS = (
    (r"hair|ponytail|twintail|braid|bang|fringe", "hair"),
    (r"sleeve|sode", "sleeve"),
    (r"tassel|pendant|rope|chain|bead|string|cord|earring", "tassel"),
    (r"ribbon|streamer|sash|bow|tail|scar[ft]|veil|hanging|drape", "ribbon"),
    (r"coat|cloak|cape|mantle|shawl|robe|jacket", "coat"),
    (r"skirt|dress|frill|apron|hem|pleat|kilt", "skirt"),
    (r"decoration|feather|wing|rib|armou?r|plate|horn|spike|antenna", "ornament"),
)


def lerp(pair, row, rows):
    """Interpolate a (root, tip) pair over ``rows`` rows."""
    a, b = pair
    if rows <= 1:
        return a
    t = row / float(rows - 1)
    return a + (b - a) * t
