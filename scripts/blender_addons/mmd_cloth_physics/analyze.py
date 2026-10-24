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
pairs neighbouring chains (the lattice); those pairs become the horizontal
joints.

Neighbours come from the mesh (2026-10-18): two chains are tied where their
cloth touches - vertices weighted to both, or mesh edges running from one's
cloth into the other's - bone to the bone it touches most.  Chains whose cloth
lies on separate mesh pieces (a skirt of loose strands) are tied row by row
when they hang next to each other round the body (ordered by where their cloth
is, not their root bones) and the link stays outside the body colliders.
Before, chains were ordered by the angle of their ROOT bones round the anchor
and every consecutive pair was tied: Inase a08's side, front and back panels
all hang under one hip plate, so the front panels were tied to the back ones
through the thighs, and strands sharing their first bones tied bones to
themselves (424 such joints over the ROE models).

Nothing here touches the scene; it only reads bones, vertex weights and the
body colliders.
"""
import math
import re
from collections import Counter, defaultdict

import numpy as np
from mathutils import Vector

from . import geom
from .presets import NAME_HINTS

JAPANESE = re.compile(r"[぀-ヿ一-鿿]")
LIMB_HELPER = re.compile(r"twist|elbow|knee|ankle|muscle|wrist", re.IGNORECASE)
# never cloth, whatever the body regex says: a game rig's extra toes and fingers (ROE Amano: only the big toe has the
# Bip001 prefix, ToeFourth_L hangs bare under 足先EX) and the breast helpers below a breast bone (Breast_L03,
# Breast_LT_00, Nipple_L).  No dynamic bone of the 212 ROE main PMX or the other games' test models matches.
NOT_CLOTH = re.compile(r"^(?:bip0\d\d[ _])?(?:toe|finger|thumb|nipple|breast)", re.IGNORECASE)
HAIR_NAME = re.compile(NAME_HINTS[0][0], re.IGNORECASE)
FACE_PARENTS = ("頭", "首")
# strip trailing side/index tokens: Skirt_B1_01 -> Skirt, Sleeve_R1_010 -> Sleeve,
# pendant_M2_06 -> pendant, F_dress_02 -> F_dress, Hair_B1_01 -> Hair.  A letter
# token needs a separator in front of it, or "Tassel" would lose its "l".
STEM_TAIL = re.compile(r"(?:[_\-\.\s]+(?:[LRMBFT]{1,2}\d*|\d+)|\d+)+$")
MIN_CONTACT = 4             # shared vertices + crossing edges that make two bones one cloth
LINK_INSIDE = 0.005         # metres: a loose-strand link deeper than this in a body collider runs through the body


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


def skinned_meshes(arm):
    """The meshes an Armature modifier binds to ``arm`` (for callers that only hand over the armature)."""
    import bpy

    return [o for o in bpy.data.objects if o.type == "MESH"
            and any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]


class SkinIndex:
    """Every vertex of the model once - world position, the bones driving it and how much, its strongest bone - and
    the mesh edges, so the per-bone questions (which vertices, which neighbours, which piece of mesh) do not walk the
    whole mesh again for every bone."""

    def __init__(self, arm, meshes):
        names = {bone.name for bone in arm.data.bones}
        self.bone_ids, self.bone_names = {}, []
        cos, vv, vb, vw, edges = [], [], [], [], []
        offset = 0
        for mesh in meshes:
            data = mesh.data
            n = len(data.vertices)
            if not n:
                continue
            co = np.empty(n * 3)
            data.vertices.foreach_get("co", co)
            mw = np.array(mesh.matrix_world)
            cos.append(co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3])
            ids = {}
            for group in mesh.vertex_groups:
                if group.name in names:
                    ids[group.index] = self._id(group.name)
            for vertex in data.vertices:
                for item in vertex.groups:
                    b = ids.get(item.group)
                    if b is not None and item.weight > 0.0:
                        vv.append(offset + vertex.index)
                        vb.append(b)
                        vw.append(item.weight)
            e = np.empty(len(data.edges) * 2, dtype=np.int64)
            data.edges.foreach_get("vertices", e)
            edges.append(e.reshape(-1, 2) + offset)
            offset += n
        self.co = np.concatenate(cos) if cos else np.zeros((0, 3))
        self.vv = np.array(vv, dtype=np.int64)
        self.vb = np.array(vb, dtype=np.int64)
        self.vw = np.array(vw, float)
        self.edges = np.concatenate(edges) if edges else np.zeros((0, 2), dtype=np.int64)
        self.strongest = np.full(len(self.co), -1, dtype=np.int64)
        if len(self.vv):
            order = np.lexsort((-self.vw, self.vv))
            first = np.ones(len(order), bool)
            first[1:] = self.vv[order][1:] != self.vv[order][:-1]
            self.strongest[self.vv[order][first]] = self.vb[order][first]
        self._contact = None
        self._island = None

    def _id(self, name):
        if name not in self.bone_ids:
            self.bone_ids[name] = len(self.bone_names)
            self.bone_names.append(name)
        return self.bone_ids[name]

    def totals(self, threshold=0.02):
        """Bone name -> summed weight over the vertices it drives by more than ``threshold``."""
        out = defaultdict(float)
        m = self.vw > threshold
        for b, w in zip(self.vb[m].tolist(), self.vw[m].tolist()):
            out[self.bone_names[b]] += w
        return out

    def points(self, name, weight_min=0.3):
        """World positions of the vertices ``name`` drives by at least ``weight_min``."""
        b = self.bone_ids.get(name)
        if b is None:
            return np.zeros((0, 3))
        return self.co[self.vv[(self.vb == b) & (self.vw >= weight_min)]]

    def strong_points(self, name):
        """World positions of the vertices whose strongest bone is ``name``."""
        b = self.bone_ids.get(name)
        return self.co[self.strongest == b] if b is not None else np.zeros((0, 3))

    def driven(self, name, weight_min=0.05, without=None):
        """Indices of the vertices ``name`` drives (> ``weight_min``), less those bone ``without`` drives too."""
        b = self.bone_ids.get(name)
        if b is None:
            return np.zeros(0, dtype=np.int64)
        m = self.vw > weight_min
        mine = np.unique(self.vv[m & (self.vb == b)])
        w = self.bone_ids.get(without) if without is not None else None
        return mine if w is None else np.setdiff1d(mine, self.vv[m & (self.vb == w)])

    def shared_points(self, a, b, weight_min=0.05, without=None):
        """World positions of the vertices both bones drive (less those bone ``without`` drives too)."""
        ib = self.bone_ids.get(b)
        if ib is None or a not in self.bone_ids:
            return np.zeros((0, 3))
        vb = self.vv[(self.vb == ib) & (self.vw > weight_min)]
        return self.co[np.intersect1d(self.driven(a, weight_min, without), vb)]

    def shared_counts(self, name, weight_min=0.05, without=None):
        """Bone name -> how many vertices it drives (> ``weight_min``) that ``name`` drives too - one pass; ``without``:
        not counting the vertices that bone drives as well."""
        b = self.bone_ids.get(name)
        if b is None:
            return {}
        m = self.vw > weight_min
        mine = self.driven(name, weight_min, without)
        hit = m & np.isin(self.vv, mine) & (self.vb != b)
        ids, counts = np.unique(self.vb[hit], return_counts=True)
        return {self.bone_names[i]: int(c) for i, c in zip(ids.tolist(), counts.tolist())}

    def contact(self, a, b):
        """How much cloth bones a and b share: vertices both drive (> 0.05) plus mesh edges from a vertex whose
        strongest bone is one to a vertex whose strongest bone is the other."""
        if self._contact is None:
            self._build_contact()
        ia, ib = self.bone_ids.get(a), self.bone_ids.get(b)
        if ia is None or ib is None or ia == ib:
            return 0
        return self._contact.get((min(ia, ib), max(ia, ib)), 0)

    def _build_contact(self):
        m = self.vw > 0.05
        vv, vb = self.vv[m], self.vb[m]
        order = np.argsort(vv, kind="stable")
        vv, vb = vv[order], vb[order]
        counts = Counter()
        if len(vv):
            starts = np.flatnonzero(np.r_[True, vv[1:] != vv[:-1]])
            ends = np.r_[starts[1:], len(vv)]
            for s, e in zip(starts[ends - starts > 1].tolist(), ends[ends - starts > 1].tolist()):
                bs = sorted(set(vb[s:e].tolist()))
                for i in range(len(bs)):
                    for j in range(i + 1, len(bs)):
                        counts[(bs[i], bs[j])] += 1
        if len(self.edges):
            a, b = self.strongest[self.edges[:, 0]], self.strongest[self.edges[:, 1]]
            keep = (a >= 0) & (b >= 0) & (a != b)
            counts.update(zip(np.minimum(a[keep], b[keep]).tolist(), np.maximum(a[keep], b[keep]).tolist()))
        self._contact = counts

    def islands(self, name):
        """The connected mesh pieces the vertices ``name`` drives most lie on."""
        if self._island is None:
            parent = np.arange(len(self.co))

            def find(i):
                while parent[i] != i:
                    parent[i] = parent[parent[i]]
                    i = parent[i]
                return i

            for u, v in self.edges.tolist():
                ru, rv = find(u), find(v)
                if ru != rv:
                    parent[ru] = rv
            self._island = np.array([find(i) for i in range(len(self.co))], dtype=np.int64)
        b = self.bone_ids.get(name)
        return set(self._island[self.strongest == b].tolist()) if b is not None else set()


def panel_normal(points, min_points=20, flat=0.3):
    """The normal of a flat-enough patch of cloth (smallest principal axis), or None."""
    if len(points) < min_points:
        return None
    lam, vec = np.linalg.eigh(np.cov((points - points.mean(0)).T))
    if lam[1] <= 1e-12 or lam[0] / lam[1] > flat:
        return None
    return Vector(vec[:, 0].tolist())


def collider_shapes(objects=None):
    """Shapes of the kinematic (bone-following) rigid bodies on MMD standard bones - the body colliders."""
    import bpy

    out = []
    for obj in (objects if objects is not None else bpy.data.objects):
        if getattr(obj, "mmd_type", "") != "RIGID_BODY" or str(obj.mmd_rigid.type) not in ("0", "STATIC"):
            continue
        if not JAPANESE.search(obj.mmd_rigid.bone or "") and not JAPANESE.search(obj.mmd_rigid.name_j or ""):
            continue
        out.append(geom.of_object(obj))
    return out


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
        if LIMB_HELPER.search(name) or NOT_CLOTH.search(name) or total.get(name, 0.0) < min_weight:
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
    """World head and segment vector of a bone (towards its child in the
    garment, else its own tail).  At a branch, a first child parked absurdly far
    away falls back to the tail, as the reference implementation does; a bone
    with ONE child in the garment always reaches it - game rigs give chain bones
    2 cm tail stubs (CCFF7R Aerith's skirt links are 15-20 cm apart), and the
    stub made every box 2-3 cm long."""
    mw = arm.matrix_world
    head = mw @ bone.head_local
    tail_vec = (mw @ bone.tail_local) - head
    kids = [c for c in bone.children if c.name in members]
    child = kids[0] if kids else None
    vec = ((mw @ child.head_local) - head) if child is not None else tail_vec
    if len(kids) > 1 and tail_vec.length > 0.015 and vec.length > 2.5 * tail_vec.length:
        vec = tail_vec
    if child is None and bone.parent is not None and bone.parent.name in members:
        # a chain's last link whose tail is a stub (FF7 Tifa's skirt: 1 cm, pointing sideways) carries on in the
        # direction of the link above it
        up = head - (mw @ bone.parent.head_local)
        if up.length > 1e-6 and tail_vec.length < 0.3 * up.length:
            vec = up.normalized() * max(tail_vec.length, 0.5 * up.length)
    if vec.length < 1e-6:
        vec = Vector((0.0, 0.0, -0.03 * max(bone.length, 1.0)))
    return head, vec


def azimuth(point, center):
    return math.atan2(point.y - center.y, point.x - center.x)


def classify(arm, garment, unit=1.0, skin=None, colliders=None, mode="mesh"):
    """Ring / sheet / strand, and the lattice pairs for rings and sheets.

    ``skin`` (a SkinIndex) and ``colliders`` (body collider shapes) are found when not given.  ``mode="legacy"``
    pairs chains the way this add-on did before 2026-10-18 (consecutive by root angle, row by row), for comparisons."""
    bones = arm.data.bones
    chains = garment.chains
    if len(chains) < 2:
        garment.kind = "strand"
        garment.pairs = []
        return
    if mode != "legacy" and skin is None:
        skin = SkinIndex(arm, skinned_meshes(arm))
    if mode != "legacy" and colliders is None:
        colliders = collider_shapes()
    center = garment.center
    mw = arm.matrix_world
    # typical segment length, for the "are these neighbours" distance
    seg_lengths = []
    for chain in chains:
        for name in chain:
            seg_lengths.append(segment(arm, bones[name], set(chain))[1].length)
    typical = sorted(seg_lengths)[len(seg_lengths) // 2] if seg_lengths else 0.1 * unit
    near = max(0.06 * unit, 2.5 * typical)
    if mode == "legacy":
        where = [mw @ bones[chain[0]].head_local for chain in chains]
    else:
        where = [chain_centre(arm, chain, skin) for chain in chains]

    ordered = list(range(len(chains)))
    kind = "sheet"
    if len(chains) >= 4:
        angles = [azimuth(r, center) for r in where]
        ordered.sort(key=lambda i: angles[i])
        gaps = [((angles[ordered[(k + 1) % len(ordered)]] - angles[ordered[k]]) % (2 * math.pi))
                for k in range(len(ordered))]
        if max(gaps) < math.radians(120):
            kind = "ring"
    if kind == "sheet":
        # order along the principal horizontal direction of the chains
        mean = sum(where, Vector()) / len(where)
        best, best_axis = -1.0, Vector((1, 0, 0))
        for k in range(12):
            axis = Vector((math.cos(k * math.pi / 12), math.sin(k * math.pi / 12), 0))
            spread = sum(((r - mean).dot(axis)) ** 2 for r in where)
            if spread > best:
                best, best_axis = spread, axis
        ordered.sort(key=lambda i: (where[i] - mean).dot(best_axis))
    garment.kind = kind

    count = len(ordered)
    links = count if kind == "ring" else count - 1
    consecutive = [(ordered[k], ordered[(k + 1) % count]) for k in range(links)]
    if mode == "legacy":
        pairs = []
        for i, j in consecutive:
            pairs.extend(pair_rows(arm, chains[i], chains[j], near))
        garment.pairs = pairs
        return

    lineage = {name: ancestors(bones[name]) for chain in chains for name in chain}

    def related(a, b):
        return a == b or a in lineage[b] or b in lineage[a]

    pairs, seen = [], set()

    def add(a, b):
        key = (min(a, b), max(a, b))
        if not related(a, b) and key not in seen:
            seen.add(key)
            pairs.append((a, b))

    touching = set()
    for i in range(count):
        for j in range(i + 1, count):
            found = pair_by_contact(chains[i], chains[j], skin, related)
            if found:
                touching.add((i, j))
                for a, b in found:
                    add(a, b)
    centres = {}
    for i, j in consecutive:
        if (min(i, j), max(i, j)) in touching:
            continue
        own_i = [n for n in chains[i] if n not in chains[j]]
        own_j = [n for n in chains[j] if n not in chains[i]]
        pieces_i = set().union(*(skin.islands(n) for n in own_i)) if own_i else set()
        pieces_j = set().union(*(skin.islands(n) for n in own_j)) if own_j else set()
        if pieces_i & pieces_j:
            continue                     # one piece of mesh, cut between them: a slit, leave it open
        for a, b in pair_rows(arm, chains[i], chains[j], near):
            for name in (a, b):
                if name not in centres:
                    head, vec = segment(arm, bones[name], set(garment.bones))
                    centres[name] = head + vec * 0.5
            if colliders and geom.crosses(centres[a], centres[b], colliders, LINK_INSIDE * unit):
                continue                 # the link would run through a leg / the hips
            add(a, b)
    garment.pairs = pairs


def ancestors(bone):
    out = set()
    cur = bone.parent
    while cur is not None:
        out.add(cur.name)
        cur = cur.parent
    return out


def chain_centre(arm, chain, skin):
    """Where a chain's cloth is: the centre of the vertices its bones drive most, else of its bones."""
    pts = [skin.strong_points(name) for name in chain]
    pts = np.concatenate(pts) if pts else np.zeros((0, 3))
    if len(pts) >= 3:
        return Vector(pts.mean(0).tolist())
    mw = arm.matrix_world
    bones = arm.data.bones
    return sum((mw @ bones[name].head_local for name in chain), Vector()) / len(chain)


def pair_by_contact(chain_a, chain_b, skin, related, min_contact=MIN_CONTACT):
    """Bones of two chains tied where their cloth touches: every bone of either chain to the bone of the other it
    shares the most cloth with (at least ``min_contact``)."""
    only_a = [n for n in chain_a if n not in chain_b]
    only_b = [n for n in chain_b if n not in chain_a]
    out, linked = [], set()
    for a in only_a:
        best = max(((skin.contact(a, b), b) for b in only_b if not related(a, b)), default=(0, None))
        if best[0] >= min_contact:
            out.append((a, best[1]))
            linked.add(best[1])
    for b in only_b:
        if b in linked:
            continue
        best = max(((skin.contact(a, b), a) for a in only_a if not related(a, b)), default=(0, None))
        if best[0] >= min_contact:
            out.append((best[1], b))
    return out


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
                  include_hair=True, min_weight=2.0, with_rigid=(), skin=None, mode="mesh"):
    """The garments of ``arm``: a list of Garment, parents-first bone order."""
    free, total, body_re = candidate_bones(arm, meshes, body_regex, prop_regex,
                                           min_weight, include_hair, with_rigid)
    comps = components(arm, free)
    bones = arm.data.bones
    mw = arm.matrix_world
    unit = unit_scale(meshes)
    if mode != "legacy" and skin is None:
        skin = SkinIndex(arm, meshes)
    colliders = collider_shapes() if mode != "legacy" else None

    grouped = defaultdict(list)
    for root, (order, rows, children) in comps.items():
        if len(order) < 2:
            continue                      # a lone bone is a plate, not cloth
        anchor = anchor_of(bones[root], body_re)
        anchor_name = anchor.name if anchor is not None else "-"
        grouped[(anchor_name, name_stem(root))].append((root, order, rows, children))
    hints = {}
    for key, items in grouped.items():               # what guess_preset reads: the first strand's first two bones
        root, _order, _rows, children = sorted(items)[0]
        hints[key] = named_preset(strands(root, children)[0][:2])
    if mode != "legacy":
        grouped, hints = merge_touching(grouped, hints, skin)

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
        classify(arm, garment, unit, skin, colliders, mode)
        garment.preset = hints.get((anchor_name, stem)) or guess_preset(garment)
        garments.append(garment)
    return garments


def named_preset(names):
    """The preset a garment's first bone names ask for (NAME_HINTS), or None when they say nothing."""
    text = " ".join(names)
    for pattern, preset in NAME_HINTS:
        if re.search(pattern, text, re.IGNORECASE):
            return preset
    return None


def merge_touching(grouped, hints, skin, min_contact=MIN_CONTACT):
    """Groups of chains under one anchor whose cloth touches are one garment, whatever their names.  CCFF7R Aerith's
    skirt is CB_skirtA / LF_skA / RF_skirtTip ...: every chain its own garment by name stem, so no lattice between
    them and the panels swung apart.  A group whose names ask for a preset joins only groups asking for the same one
    or for none (a08's hip chain stays a tassel though it is glued to the skirt), hair only hair.  Returns the new
    (grouped, hints); a merged group is named after its largest member plus "+<count>"."""
    keys = sorted(grouped)
    names = {k: [n for _root, order, _rows, _kids in grouped[k] for n in order] for k in keys}
    owner = {k: k for k in keys}
    members = {k: [k] for k in keys}

    def find(k):
        while owner[k] != k:
            k = owner[k]
        return k

    def kinds(k):
        return {hints[m] for m in members[k]} - {None}

    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            ra, rb = find(a), find(b)
            if ra == rb or a[0] != b[0]:
                continue
            together = kinds(ra) | kinds(rb)
            hair = {hints[m] == "hair" for m in members[ra] + members[rb]}
            if len(together) > 1 or len(hair) > 1:
                continue
            if any(skin.contact(x, y) >= min_contact for x in names[a] for y in names[b]):
                owner[rb] = ra
                members[ra] += members.pop(rb)
    out, out_hints = {}, {}
    for root, group in members.items():
        if len(group) == 1:
            out[root], out_hints[root] = grouped[root], hints[root]
            continue
        big = max(group, key=lambda k: len(names[k]))
        key = (big[0], "%s+%d" % (big[1], len(group) - 1))
        out[key] = [item for k in group for item in grouped[k]]
        out_hints[key] = next(iter(kinds(root)), None)
    return out, out_hints


def extent_of(points, frame, centre):
    """skin_extent's measure on points already gathered (SkinIndex.points): 90th percentile of the offsets from
    ``centre`` along the frame's tangent (Z) and outward (X) axes, or None for fewer than 8 points."""
    if len(points) < 8:
        return None
    rel = points - np.array(centre)
    return (float(np.percentile(np.abs(rel @ np.array(frame[2])), 90)),
            float(np.percentile(np.abs(rel @ np.array(frame[0])), 90)))


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
