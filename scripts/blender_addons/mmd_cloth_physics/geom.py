"""Rigid-body shapes in Blender world space and how deep one sits in another.

numpy, no scene changes.  Used by the collision groups (collide.py), the box seating (build.py) and the lattice's
"does this link run through the body" test (analyze.py).  The maths is scripts/mmd_physics/cloth_collision_pmx.py's,
on mmd_tools' axes: a BOX has half extents size[0..2] on its local X / Y / Z, a CAPSULE runs along local Z with
radius size[0] and cylinder length size[1], a SPHERE has radius size[0].
"""
import numpy as np

SPHERE, BOX, CAPSULE = 0, 1, 2
KIND = {"SPHERE": SPHERE, "BOX": BOX, "CAPSULE": CAPSULE}


class Shape:
    __slots__ = ("kind", "c", "R", "size", "seg", "r")

    def __init__(self, kind, c, R, size):
        self.kind = int(kind)
        self.c = np.array(c, float).reshape(3)
        self.R = np.array(R, float).reshape(3, 3)
        self.size = np.array(list(size) + [0.0] * (3 - len(size)), float)[:3]
        if self.kind == CAPSULE:
            ax = self.R[:, 2] * self.size[1] * 0.5
            self.seg = (self.c - ax, self.c + ax)
        elif self.kind == SPHERE:
            self.seg = (self.c, self.c)
        else:
            self.seg = None
        self.r = self.size[0] if self.kind != BOX else 0.0

    def resized(self, size):
        return Shape(self.kind, self.c, self.R, size)

    def moved(self, c):
        return Shape(self.kind, c, self.R, self.size)

    def samples(self, n=24):
        a, b = self.seg
        return a + (b - a) * np.linspace(0, 1, n)[:, None]


def of_object(obj):
    """The shape of an mmd_tools rigid body object, in world space."""
    rb = obj.mmd_rigid
    m = np.array(obj.matrix_world)
    scale = np.linalg.norm(m[:3, :3], axis=0)
    scale[scale < 1e-9] = 1.0
    return Shape(KIND.get(rb.shape, BOX), m[:3, 3], m[:3, :3] / scale, np.array(rb.size, float) * float(scale.mean()))


def point_seg(p, a, b):
    ab = b - a
    L = float(ab @ ab)
    t = np.clip(((p - a) @ ab) / L, 0, 1) if L > 1e-12 else np.zeros(len(p))
    return np.linalg.norm(p - (a + t[:, None] * ab), axis=1)


def signed_box(p, s):
    ex = np.abs((p - s.c) @ s.R) - s.size
    return np.linalg.norm(np.maximum(ex, 0), axis=1) + np.minimum(np.max(ex, axis=1), 0)


def box_samples(s, k=5):
    g = np.linspace(-1, 1, k)
    return s.c + (np.array([[x, y, z] for x in g for y in g for z in g]) * s.size) @ s.R.T


def depth(d, c):
    """How far shape d sits inside shape c (> 0 = overlap)."""
    if c.kind != BOX and d.kind != BOX:
        return float(c.r + d.r - point_seg(d.samples(), *c.seg).min())
    if c.kind != BOX:
        return float(c.r - signed_box(c.samples(), d).min())
    if d.kind != BOX:
        return float(d.r - signed_box(d.samples(), c).min())
    return float(-signed_box(box_samples(d), c).min())


def surface_distance(p, s):
    """Signed distance of points to the shape's surface (< 0 inside)."""
    p = np.atleast_2d(np.asarray(p, float))
    return signed_box(p, s) if s.kind == BOX else point_seg(p, *s.seg) - s.r


def crosses(a, b, shapes, inside):
    """Does the straight line from a to b run through any of ``shapes`` - deeper than ``inside`` and deeper than
    both of its ends (a link lying along the body, ends and all on its surface, does not count)?"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    pts = a + (b - a) * np.linspace(0.15, 0.85, 15)[:, None]
    for s in shapes:
        ends = surface_distance(np.stack([a, b]), s)
        if (surface_distance(pts, s) < min(-inside, float(ends.min()) - inside)).any():
            return True
    return False


def nearest(shapes, p):
    """(shape, closest point on its axis / centre) of the shape whose surface is nearest to p, or (None, None)."""
    p = np.asarray(p, float)
    best, where = None, None
    for s in shapes:
        d = float(surface_distance(p[None], s)[0])
        if best is None or d < best[0]:
            if s.kind == BOX:
                q = s.c
            else:
                a, b = s.seg
                ab = b - a
                L = float(ab @ ab)
                t = float(np.clip((p - a) @ ab / L, 0, 1)) if L > 1e-12 else 0.0
                q = a + ab * t
            best, where = (d, s), q
    return (best[1], where) if best else (None, None)
