"""Find the garments on an mmd_tools model and describe their shape.

A garment bone is one that drives real skin, has no rigid body yet and is
none of: an MMD standard bone (Japanese name), a body-skeleton bone (the
``body_regex``), a limb helper, a face bone, or anything carried in the hands
(``prop_regex`` ancestors).  Those bones form parent/child components; each
component is a set of *strands* (root-to-leaf paths, branching allowed) and
every bone has a *row* (depth from the component root).

Components with the same anchor bone and the same name stem are one garment.
A garment whose chains surround their anchor is a ``ring`` (a skirt), chains
that hang side by side make a ``sheet`` (a cape panel), a lone chain is a
``strand`` (ribbon, sleeve, tassel).  For rings and sheets the analysis also
pairs neighbouring chains row by row (the lattice); those pairs become the
horizontal joints.

Nothing here touches the scene; it only reads bones and vertex weights.
"""
import math
import re
from collections import defaultdict

from mathutils import Vector

from .presets import NAME_HINTS

JAPANESE = re.compile(r"[぀-ヿ一-鿿]")
LIMB_HELPER = re.compile(r"twist|elbow|knee|ankle|muscle|wrist", re.IGNORECASE)
HAIR_NAME = re.compile(NAME_HINTS[0][0], re.IGNORECASE)
FACE_PARENTS = ("頭", "首")
# strip trailing side/index tokens: Skirt_B1_01 -> Skirt, Sleeve_R1_010 -> Sleeve,
# pendant_M2_06 -> pendant, F_dress_02 -> F_dress, Hair_B1_01 -> Hair.  A letter
# token needs a separator in front of it, or "Tassel" would lose its "l".
STEM_TAIL = re.compile(r"(?:[_\-\.\s]+(?:[LRMBFT]{1,2}\d*|\d+)|\d+)+$")


class Garment:
    __slots__ = ("name", "stem", "anchor", "kind", "preset", "chains", "rows",
                 "bones", "pairs", "center", "enabled")

    def __init__(self, name, stem, anchor):
        self.name = name
        self.stem = stem
        self.anchor = anchor
        self.kind = "strand"
        self.preset = "ribbon"
        self.chains = []      # list of lists of bone names, root first
        self.rows = {}        # bone name -> row index
        self.bones = []       # every bone name, parents first
        self.pairs = []       # (bone a, bone b) lattice neighbours
        self.center = None    # anchor head, world
        self.enabled = True

    @property
    def depth(self):
        return max(self.rows.values()) + 1 if self.rows else 0

    def as_dict(self):
        return {"name": self.name, "kind": self.kind, "preset": self.preset,
                "anchor": self.anchor, "chains": len(self.chains), "rows": self.depth,
                "bones": len(self.bones), "pairs": len(self.pairs)}


def unit_scale(meshes):
    """Metres per Blender unit for this model, from its height: a PMX imported
    at mmd_tools' default 0.08 stands about 1.6 units tall, one imported at 1.0
    about 20.  Every absolute size in the presets is in metres and gets
    multiplied by this."""
    lo, hi = None, None
    for mesh in meshes:
        for corner in mesh.bound_box:
            z = (mesh.matrix_world @ Vector(corner)).z
            lo = z if lo is None else min(lo, z)
            hi = z if hi is None else max(hi, z)
    if lo is None or hi - lo < 1e-3:
        return 1.0
    return max(0.05, (hi - lo) / 1.65)


def skin_totals(arm, meshes, threshold=0.02):
    names = {bone.name for bone in arm.data.bones}
    total = defaultdict(float)
    for mesh in meshes:
        index_to_name = {group.index: group.name for group in mesh.vertex_groups
                         if group.name in names}
        for vertex in mesh.data.vertices:
            for item in vertex.groups:
                name = index_to_name.get(item.group)
                if name and item.weight > threshold:
                    total[name] += item.weight
    return total


def is_body_bone(bone, body_re):
    return bool(JAPANESE.search(bone.name)) or (body_re is not None
                                                and body_re.match(bone.name) is not None)


def anchor_of(bone, body_re):
    """First body bone above ``bone`` (its physics anchor)."""
    cur = bone.parent
    while cur is not None:
        if is_body_bone(cur, body_re):
            return cur
        cur = cur.parent
    return None


def candidate_bones(arm, meshes, body_regex=None, prop_regex=r"\bProp\d*$",
                    min_weight=2.0, include_hair=True, with_rigid=()):
    """Bones that could carry cloth physics."""
    body_re = re.compile(body_regex) if body_regex else None
    prop_re = re.compile(prop_regex, re.IGNORECASE) if prop_regex else None
    total = skin_totals(arm, meshes)

    def carried(bone):
        cur = bone
        while cur is not None:
            if prop_re and prop_re.search(cur.name):
                return True
            cur = cur.parent
        return False

    def under_face(bone):
        cur = bone.parent
        while cur is not None:
            if cur.name in FACE_PARENTS:
                return True
            cur = cur.parent
        return False

    free = set()
    for bone in arm.data.bones:
        name = bone.name
        if name in with_rigid or is_body_bone(bone, body_re):
            continue
        if name.startswith(("_dummy_", "_shadow_", "unused")):
            continue
        if LIMB_HELPER.search(name) or total.get(name, 0.0) < min_weight:
            continue
        if carried(bone):
            continue
        if under_face(bone) and not (include_hair and HAIR_NAME.search(name)):
            continue
        free.add(name)
    return free, total, body_re


def components(arm, free):
    """Connected components over the parent link, as {root: (order, rows, children)}."""
    bones = arm.data.bones
    parent_in = {}
    for name in free:
        parent = bones[name].parent
        parent_in[name] = parent.name if parent is not None and parent.name in free else None
    roots = [name for name, parent in parent_in.items() if parent is None]
    children = defaultdict(list)
    for name, parent in parent_in.items():
        if parent is not None:
            children[parent].append(name)
    result = {}
    for root in roots:
        order, rows, stack = [], {root: 0}, [root]
        while stack:
            cur = stack.pop()
            order.append(cur)
            for child in sorted(children.get(cur, ())):
                rows[child] = rows[cur] + 1
                stack.append(child)
        result[root] = (order, rows, children)
    return result


def strands(root, children):
    """Root-to-leaf paths of one component."""
    out = []

    def walk(name, path):
        path = path + [name]
        kids = children.get(name, ())
        if not kids:
            out.append(path)
        for kid in sorted(kids):
            walk(kid, path)

    walk(root, [])
    return out


def name_stem(name):
    stem = STEM_TAIL.sub("", name)
    return stem or name


def guess_preset(garment):
    text = " ".join(garment.chains[0][:2]) if garment.chains else garment.name
    for pattern, preset in NAME_HINTS:
        if re.search(pattern, text, re.IGNORECASE):
            return preset
    if garment.kind == "ring":
        return "skirt"
    if garment.kind == "sheet":
        return "coat"
    return "ribbon"


def segment(arm, bone, members):
    """World head and segment vector of a bone (towards its first child in the
    garment, else its own tail).  A child parked absurdly far away (a branch tip)
    falls back to the tail, as the reference implementation does."""
    mw = arm.matrix_world
    head = mw @ bone.head_local
    tail_vec = (mw @ bone.tail_local) - head
    child = next((c for c in bone.children if c.name in members), None)
    vec = ((mw @ child.head_local) - head) if child is not None else tail_vec
    if child is not None and tail_vec.length > 0.015 and vec.length > 2.5 * tail_vec.length:
        vec = tail_vec
    if vec.length < 1e-6:
        vec = Vector((0.0, 0.0, -0.03 * max(bone.length, 1.0)))
    return head, vec


def azimuth(point, center):
    return math.atan2(point.y - center.y, point.x - center.x)


def classify(arm, garment, unit=1.0):
    """Ring / sheet / strand, and the lattice pairs for rings and sheets."""
    bones = arm.data.bones
    mw = arm.matrix_world
    chains = garment.chains
    if len(chains) < 2:
        garment.kind = "strand"
        garment.pairs = []
        return
    center = garment.center
    roots = [mw @ bones[chain[0]].head_local for chain in chains]
    # typical segment length, for the "are these neighbours" distance
    seg_lengths = []
    for chain in chains:
        for name in chain:
            seg_lengths.append(segment(arm, bones[name], set(chain))[1].length)
    typical = sorted(seg_lengths)[len(seg_lengths) // 2] if seg_lengths else 0.1 * unit
    near = max(0.06 * unit, 2.5 * typical)

    ordered = list(range(len(chains)))
    kind = "sheet"
    if len(chains) >= 4:
        angles = [azimuth(r, center) for r in roots]
        ordered.sort(key=lambda i: angles[i])
        gaps = [((angles[ordered[(k + 1) % len(ordered)]] - angles[ordered[k]]) % (2 * math.pi))
                for k in range(len(ordered))]
        if max(gaps) < math.radians(120):
            kind = "ring"
    if kind == "sheet":
        # order along the principal horizontal direction of the roots
        mean = sum(roots, Vector()) / len(roots)
        best, best_axis = -1.0, Vector((1, 0, 0))
        for k in range(12):
            axis = Vector((math.cos(k * math.pi / 12), math.sin(k * math.pi / 12), 0))
            spread = sum(((r - mean).dot(axis)) ** 2 for r in roots)
            if spread > best:
                best, best_axis = spread, axis
        ordered.sort(key=lambda i: (roots[i] - mean).dot(best_axis))
    garment.kind = kind

    pairs = []
    count = len(ordered)
    links = count if kind == "ring" else count - 1
    for k in range(links):
        a = chains[ordered[k]]
        b = chains[ordered[(k + 1) % count]]
        pairs.extend(pair_rows(arm, a, b, near))
    garment.pairs = pairs


def pair_rows(arm, chain_a, chain_b, near):
    """Match every bone of chain A with the bone of chain B at the closest height,
    when the two sit near enough to be the same piece of cloth."""
    bones = arm.data.bones

    def centres(chain):
        out = []
        for name in chain:
            head, vec = segment(arm, bones[name], set(chain))
            out.append((name, head + vec * 0.5))
        return out

    ca, cb = centres(chain_a), centres(chain_b)
    pairs, used = [], set()
    for name_a, pos_a in ca:
        best = None
        for name_b, pos_b in cb:
            dz = abs(pos_a.z - pos_b.z)
            dist = (pos_a - pos_b).length
            if dist <= near and (best is None or dz < best[0]):
                best = (dz, name_b)
        if best is not None and (name_a, best[1]) not in used:
            used.add((name_a, best[1]))
            pairs.append((name_a, best[1]))
    return pairs


def find_garments(arm, meshes, body_regex=None, prop_regex=r"\bProp\d*$",
                  include_hair=True, min_weight=2.0, with_rigid=()):
    """The garments of ``arm``: a list of Garment, parents-first bone order."""
    free, total, body_re = candidate_bones(arm, meshes, body_regex, prop_regex,
                                           min_weight, include_hair, with_rigid)
    comps = components(arm, free)
    bones = arm.data.bones
    mw = arm.matrix_world
    unit = unit_scale(meshes)

    grouped = defaultdict(list)
    for root, (order, rows, children) in comps.items():
        if len(order) < 2:
            continue                      # a lone bone is a plate, not cloth
        anchor = anchor_of(bones[root], body_re)
        anchor_name = anchor.name if anchor is not None else "-"
        grouped[(anchor_name, name_stem(root))].append((root, order, rows, children))

    garments = []
    for (anchor_name, stem), items in sorted(grouped.items()):
        garment = Garment("%s@%s" % (stem, anchor_name), stem, anchor_name)
        anchor = bones.get(anchor_name)
        garment.center = (mw @ anchor.head_local) if anchor is not None else Vector()
        for root, order, rows, children in sorted(items):
            for path in strands(root, children):
                garment.chains.append(path)
            for name in order:
                if name not in garment.rows:
                    garment.rows[name] = rows[name]
                    garment.bones.append(name)
        garment.bones.sort(key=lambda n: garment.rows[n])
        classify(arm, garment, unit)
        garment.preset = guess_preset(garment)
        garments.append(garment)
    return garments


def skin_extent(arm, meshes, bone_name, frame, head, vec, weight_min=0.3):
    """Half-width (along the frame's tangent) and half-thickness (along its
    outward axis) of the skin this bone drives, as the 90th percentile of the
    vertex offsets from the segment.  Returns None when the bone drives too
    little for a measurement."""
    x_axis, y_axis, z_axis = frame
    centre = head + vec * 0.5
    tangents, radials = [], []
    for mesh in meshes:
        group = mesh.vertex_groups.get(bone_name)
        if group is None:
            continue
        index = group.index
        mwm = mesh.matrix_world
        for vertex in mesh.data.vertices:
            for item in vertex.groups:
                if item.group == index and item.weight >= weight_min:
                    rel = (mwm @ vertex.co) - centre
                    tangents.append(abs(rel.dot(z_axis)))
                    radials.append(abs(rel.dot(x_axis)))
                    break
    if len(tangents) < 8:
        return None
    tangents.sort()
    radials.sort()
    k = int(len(tangents) * 0.9)
    return tangents[k], radials[k]
