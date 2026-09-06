"""Write the DAZ DSON files VaM 1.22 imports: ``.duf`` scenes and ``.dsf`` morphs.

The reverse of ``export_vam_models.py``.  VaM has no mesh import of its own,
but it ships an in-game creator (``DAZRuntimeCreator``, loaded onto a Person
as the Clothing Creator / Hair Creator item) whose Import button takes a DAZ
``.duf`` scene file.  It then fits the mesh to the body itself
(``CreateDAZSkinWrap``) and the Store button writes the ``.vam`` / ``.vaj`` /
``.vab`` triple this repo already reads.  So a Blender mesh only has to reach
VaM as valid DSON -- no Unity, no DAZ Studio.

Everything below was calibrated against files VaM itself accepted, not guessed:

* ``VL_13.Lashes_2.1`` ships the creator's own ``Lashes_Skin_subd.duf`` next
  to the ``.vab`` it produced (392 verts / 282 quads).  Comparing them vertex
  by vertex gives the whole conversion, to float32 precision (1.5e-07):

      VaM vertex = (-x, y, z) * 0.01   of the DUF vertex

  Vertex order, polygon order, winding, quads and UVs all survive 1:1, so the
  only thing a writer has to get right is the coordinate map.

* DAZ winding is counter-clockwise seen from outside (measured on a closed
  DAZ mesh: 88.7% of faces have their right-hand normal pointing away from
  the centroid) -- the same convention as Blender, and the mirror in the map
  above is what leaves VaM's own meshes wound clockwise from outside.

* UV seams: ``uvs.values`` holds one entry per vertex first, seam duplicates
  appended after; ``polygon_vertex_indices`` carries ``[poly, vertex, uv]``
  only for the corners that deviate.

* Morphs are ``.dsf`` files with a ``modifier_library``; VaM compiles them to
  ``.vmi``/``.vmb`` on startup.  Genesis 2 is 21556 vertices for both genders.
"""

import gzip
import json
import os

import numpy as np

# DSON version DAZ Studio 4 writes and VaM accepts.
FILE_VERSION = "0.6.0.0"

# VaM/Unity works in metres, DAZ in centimetres, and the X axis is mirrored
# between them (see the calibration in the module docstring).
DAZ_SCALE = 100.0

# What the Genesis 2 morph ``.dsf`` files in the installed packages point at.
GENESIS2_PARENT = {
    "female": "/data/DAZ%203D/Genesis%202/Female/Genesis2Female.dsf#GenesisFemale-1",
    "male": "/data/DAZ%203D/Genesis%202/Male/Genesis2Male.dsf#Genesis2Male",
}
GENESIS2_VERTS = 21556

# The creator's own warning: "Vertex count very high.  Recommend decimation
# (<50000 for wrap and <25000 for sim) & reimport".
WRAP_VERTEX_LIMIT = 50000
SIM_VERTEX_LIMIT = 25000


def vam_to_daz(verts):
    """VaM/Unity metres -> DAZ centimetres."""
    verts = np.asarray(verts, dtype=np.float64)
    out = np.empty_like(verts)
    out[:, 0] = -verts[:, 0] * DAZ_SCALE
    out[:, 1] = verts[:, 1] * DAZ_SCALE
    out[:, 2] = verts[:, 2] * DAZ_SCALE
    return out


def daz_to_vam(verts):
    """DAZ centimetres -> VaM/Unity metres (the inverse of :func:`vam_to_daz`)."""
    verts = np.asarray(verts, dtype=np.float64)
    out = np.empty_like(verts)
    out[:, 0] = -verts[:, 0] / DAZ_SCALE
    out[:, 1] = verts[:, 1] / DAZ_SCALE
    out[:, 2] = verts[:, 2] / DAZ_SCALE
    return out


def blender_to_daz(verts):
    """Blender metres (Z up) -> DAZ centimetres (Y up).

    Composing Blender->VaM (``vam_lib.to_blender`` inverted) with VaM->DAZ
    cancels both mirrors, so this is a plain rotation: face winding carries
    over from Blender unchanged.
    """
    verts = np.asarray(verts, dtype=np.float64)
    out = np.empty_like(verts)
    out[:, 0] = verts[:, 0] * DAZ_SCALE
    out[:, 1] = verts[:, 2] * DAZ_SCALE
    out[:, 2] = -verts[:, 1] * DAZ_SCALE
    return out


def daz_to_blender(verts):
    """DAZ centimetres -> Blender metres (the inverse of :func:`blender_to_daz`)."""
    verts = np.asarray(verts, dtype=np.float64)
    out = np.empty_like(verts)
    out[:, 0] = verts[:, 0] / DAZ_SCALE
    out[:, 1] = -verts[:, 2] / DAZ_SCALE
    out[:, 2] = verts[:, 1] / DAZ_SCALE
    return out


def blender_to_vam(verts):
    """Blender metres -> VaM metres (the inverse of ``vam_lib.to_blender``)."""
    verts = np.asarray(verts, dtype=np.float64)
    out = np.empty_like(verts)
    out[:, 0] = -verts[:, 0]
    out[:, 1] = verts[:, 2]
    out[:, 2] = -verts[:, 1]
    return out


def vam_to_blender(verts):
    """VaM metres -> Blender metres (same map as ``vam_lib.to_blender``)."""
    verts = np.asarray(verts, dtype=np.float64)
    out = np.empty_like(verts)
    out[:, 0] = -verts[:, 0]
    out[:, 1] = -verts[:, 2]
    out[:, 2] = verts[:, 1]
    return out


TO_DAZ = {"daz": lambda v: np.asarray(v, dtype=np.float64),
          "vam": vam_to_daz, "blender": blender_to_daz}


# --------------------------------------------------------------------------
# Fitting an outside figure onto VaM's body
# --------------------------------------------------------------------------
# A garment ripped from another game or another DAZ generation arrives in its
# own units, at its own height, around its own body.  VaM's creator wraps onto
# the base Genesis 2 body, so the mesh has to be moved there first.  Both
# figures stand upright facing the same way, so only a uniform scale and a
# translation are free -- solving for a rotation as well would let a bad
# correspondence tip the figure over.

def nearest_points(points, cloud, chunk=1024):
    """For each point, the closest point of ``cloud`` and the distance to it."""
    points = np.asarray(points, dtype=np.float64)
    cloud = np.asarray(cloud, dtype=np.float64)
    hit = np.empty_like(points)
    distance = np.empty(len(points))
    for start in range(0, len(points), chunk):
        block = points[start:start + chunk]
        d2 = ((block[:, None, :] - cloud[None, :, :]) ** 2).sum(-1)
        index = d2.argmin(1)
        hit[start:start + chunk] = cloud[index]
        distance[start:start + chunk] = np.sqrt(d2[np.arange(len(block)), index])
    return hit, distance


def _scale_and_shift(source, target):
    """Least-squares uniform scale + translation taking source onto target."""
    sc, tc = source.mean(0), target.mean(0)
    spread = ((source - sc) ** 2).sum()
    scale = 1.0 if spread == 0 else float(((source - sc) * (target - tc)).sum() / spread)
    return scale, tc - scale * sc


def fit_to_reference(source, reference, iterations=6, sample=2500, cloud_sample=8000):
    """Scale + translation putting ``source`` on top of ``reference``.

    Starts from matching height and foot plane, then refines by re-fitting to
    nearest points (a scaled ICP with the rotation locked to identity).  Pass
    only the parts of the figure that are posed the same in both -- feeding it
    arms that are A-posed on one side and T-posed on the other drags the whole
    fit.  Returns (scale, translate, residual distances of the sample).
    """
    source = np.asarray(source, dtype=np.float64)
    reference = np.asarray(reference, dtype=np.float64)
    assert len(source) and len(reference), "nothing to fit"

    lo, hi = source[:, 2].min(), source[:, 2].max()
    ref_lo, ref_hi = reference[:, 2].min(), reference[:, 2].max()
    scale = float((ref_hi - ref_lo) / (hi - lo)) if hi > lo else 1.0
    translate = np.array([
        reference[:, 0].mean() - scale * source[:, 0].mean(),
        np.median(reference[:, 1]) - scale * np.median(source[:, 1]),
        ref_lo - scale * lo,
    ])

    picked = source[::max(1, len(source) // sample)]
    cloud = reference[::max(1, len(reference) // cloud_sample)]
    distance = None
    for _ in range(iterations):
        target, distance = nearest_points(picked * scale + translate, cloud)
        scale, translate = _scale_and_shift(picked, target)
    if distance is None:
        _, distance = nearest_points(picked * scale + translate, cloud)
    return scale, translate, distance


def _round(values, digits=6):
    """Trim float noise so the files stay small and diffable."""
    return [[round(float(x), digits) or 0.0 for x in row] for row in np.asarray(values)]


def _num(chan_id, name, label, value, step=0.01, minimum=-10000.0,
         maximum=10000.0, visible=None, percent=False):
    channel = {"id": chan_id, "type": "float", "name": name, "label": label}
    if visible is not None:
        channel["visible"] = visible
    channel["value"] = value
    channel["current_value"] = value
    channel["min"] = minimum
    channel["max"] = maximum
    if percent:
        channel["display_as_percent"] = True
    channel["step_size"] = step
    return channel


def _vec3(axis_names, label_suffix, values, step=0.01, visible=None, percent=False):
    return [_num(axis, axis_names[i], "%s %s" % (axis.upper(), label_suffix),
                 float(values[i]), step=step, visible=visible, percent=percent)
            for i, axis in enumerate("xyz")]


def _colour(chan_id, name, label, value, group):
    return {"channel": {"id": chan_id, "type": "color", "name": name, "label": label,
                        "value": list(value), "current_value": list(value),
                        "min": 0, "max": 1, "clamped": True,
                        "default_image_gamma": 0, "mappable": True},
            "group": group}


def _scalar(chan_id, name, label, value, group, mappable=True):
    return {"channel": {"id": chan_id, "type": "float", "name": name, "label": label,
                        "value": value, "current_value": value, "min": 0, "max": 1,
                        "clamped": True, "display_as_percent": True, "step_size": 0.01,
                        "default_image_gamma": 1, "mappable": mappable},
            "group": group}


class DufMesh(object):
    """One mesh on its way into VaM.

    ``verts`` are in ``space`` ("blender", "vam" or "daz") and are converted
    to DAZ centimetres on construction.  ``faces`` is a list of 3- or 4-vertex
    index lists (DSON has no n-gons).  ``uvs`` is either one UV per vertex or,
    together with ``uv_faces`` (uv indices parallel to ``faces``), a per-corner
    layout that gets split into defaults plus seam duplicates.
    """

    def __init__(self, name, verts, faces, uvs=None, uv_faces=None,
                 face_materials=None, material_names=None, space="blender",
                 group_name=None):
        assert space in TO_DAZ, "unknown space %r" % (space,)
        self.name = str(name)
        self.verts = TO_DAZ[space](verts)
        assert self.verts.ndim == 2 and self.verts.shape[1] == 3, "verts must be Nx3"
        self.faces = [list(int(i) for i in face) for face in faces]
        assert self.faces, "%s has no faces" % self.name
        for face in self.faces:
            assert len(face) in (3, 4), \
                "%s: DSON polygons are triangles or quads, got %d corners" % (self.name, len(face))
            for i in face:
                assert 0 <= i < len(self.verts), "%s: vertex index %d out of range" % (self.name, i)

        self.material_names = [str(m) for m in (material_names or ["default"])]
        assert self.material_names, "%s has no materials" % self.name
        if face_materials is None:
            face_materials = [0] * len(self.faces)
        self.face_materials = [int(m) for m in face_materials]
        assert len(self.face_materials) == len(self.faces), \
            "%s: %d face materials for %d faces" % (self.name, len(self.face_materials), len(self.faces))
        for m in self.face_materials:
            assert 0 <= m < len(self.material_names), \
                "%s: material index %d out of range" % (self.name, m)

        self.group_name = str(group_name or self.name)
        self.uvs, self.uv_pairs = self._build_uvs(uvs, uv_faces)

    def _build_uvs(self, uvs, uv_faces):
        """Return (uv values, [poly, vertex, uv] triples for the seams)."""
        if uvs is None:
            return None, []
        uvs = np.asarray(uvs, dtype=np.float64)
        assert uvs.ndim == 2 and uvs.shape[1] == 2, "uvs must be Mx2"
        if uv_faces is None:
            assert len(uvs) == len(self.verts), \
                "%s: %d uvs for %d vertices and no uv_faces" % (self.name, len(uvs), len(self.verts))
            return uvs, []

        assert len(uv_faces) == len(self.faces), \
            "%s: %d uv faces for %d faces" % (self.name, len(uv_faces), len(self.faces))
        # First UV seen on a vertex becomes its default; every corner that
        # disagrees gets an appended entry and a polygon_vertex_indices row.
        default = [None] * len(self.verts)
        for face, uv_face in zip(self.faces, uv_faces):
            assert len(uv_face) == len(face), "%s: uv face length mismatch" % self.name
            for vert, uv in zip(face, uv_face):
                if default[vert] is None:
                    default[vert] = int(uv)
        values = [uvs[default[v]] if default[v] is not None else (0.0, 0.0)
                  for v in range(len(self.verts))]
        pairs = []
        extra = {}
        for poly, (face, uv_face) in enumerate(zip(self.faces, uv_faces)):
            for vert, uv in zip(face, uv_face):
                uv = int(uv)
                if uv == default[vert]:
                    continue
                slot = extra.get(uv)
                if slot is None:
                    slot = len(values)
                    extra[uv] = slot
                    values.append(uvs[uv])
                pairs.append([poly, int(vert), slot])
        return np.asarray(values, dtype=np.float64), pairs

    def geometry(self, geom_id):
        polys = [[0, mat] + face for face, mat in zip(self.faces, self.face_materials)]
        geom = {
            "id": geom_id,
            "name": self.name,
            "type": "polygon_mesh",
            "vertices": {"count": len(self.verts), "values": _round(self.verts, 4)},
            "polygon_groups": {"count": 1, "values": [self.group_name]},
            "polygon_material_groups": {"count": len(self.material_names),
                                        "values": list(self.material_names)},
            "polylist": {"count": len(polys), "values": polys},
        }
        if self.uvs is not None:
            geom["default_uv_set"] = "#%s" % self.name
        return geom

    def uv_set(self):
        if self.uvs is None:
            return None
        return {"id": self.name, "name": self.name, "label": "%s UVs" % self.name,
                "vertex_count": len(self.verts),
                "uvs": {"count": len(self.uvs), "values": _round(self.uvs, 6)},
                "polygon_vertex_indices": self.uv_pairs}


def _node(node_id, name, centre, end):
    return {
        "id": node_id, "name": name, "type": "node", "label": name,
        "rotation_order": "YXZ", "inherits_scale": True,
        "center_point": _vec3(("xOrigin", "yOrigin", "zOrigin"), "Origin", centre, visible=False),
        "end_point": _vec3(("xEnd", "yEnd", "zEnd"), "End", end, visible=False),
        "orientation": _vec3(("xOrientation", "yOrientation", "zOrientation"),
                             "Orientation", (0, 0, 0), visible=False),
        "rotation": _vec3(("XRotate", "YRotate", "ZRotate"), "Rotate", (0, 0, 0), step=0.5),
        "translation": _vec3(("XTranslate", "YTranslate", "ZTranslate"), "Translate",
                             (0, 0, 0), step=1),
        "scale": _vec3(("XScale", "YScale", "ZScale"), "Scale", (1, 1, 1),
                       step=0.005, percent=True),
        "general_scale": _num("general_scale", "Scale", "Scale", 1.0, step=0.005,
                              percent=True),
    }


def _material(mat_id):
    """A plain DAZ Default material -- VaM only needs the slot to exist."""
    return {
        "id": mat_id, "type": "Plastic",
        "diffuse": _colour("diffuse", "Diffuse Color", "Diffuse Color", (1, 1, 1), "/Diffuse"),
        "diffuse_strength": _scalar("diffuse_strength", "Diffuse Strength",
                                    "Diffuse Strength", 1, "/Diffuse"),
        "specular": _colour("specular", "Specular Color", "Specular Color",
                            (0.6, 0.6, 0.6), "/Specular"),
        "specular_strength": _scalar("specular_strength", "Specular Strength",
                                     "Specular Strength", 1, "/Specular"),
        "glossiness": _scalar("glossiness", "Glossiness", "Glossiness", 1, "/Specular"),
        "ambient": _colour("ambient", "Ambient Color", "Ambient Color", (0, 0, 0), "/Ambient"),
        "ambient_strength": _scalar("ambient_strength", "Ambient Strength",
                                    "Ambient Strength", 1, "/Ambient"),
        "transparency": _scalar("transparency", "Opacity Strength", "Opacity Strength",
                                1, "/Opacity"),
    }


def _scene_material(mat_id, url, geometry, groups, uv_set):
    def chan(chan_id, name, kind, value):
        return {"channel": {"id": chan_id, "type": kind, "name": name,
                            "current_value": value, "image": None}}
    entry = {
        "id": mat_id, "url": url, "geometry": geometry, "groups": list(groups),
        "diffuse": chan("diffuse", "Diffuse Color", "color", [1, 1, 1]),
        "diffuse_strength": chan("diffuse_strength", "Diffuse Strength", "float", 1),
        "specular": chan("specular", "Specular Color", "color", [0.6, 0.6, 0.6]),
        "specular_strength": chan("specular_strength", "Specular Strength", "float", 1),
        "glossiness": chan("glossiness", "Glossiness", "float", 1),
        "ambient": chan("ambient", "Ambient Color", "color", [0, 0, 0]),
        "ambient_strength": chan("ambient_strength", "Ambient Strength", "float", 1),
        "transparency": chan("transparency", "Opacity Strength", "float", 1),
    }
    if uv_set:
        entry["uv_set"] = uv_set
    return entry


def build_duf(meshes, asset_id=None, author="ripper_tpose", modified=None):
    """A self-contained DSON scene subset holding ``meshes``.

    Self-contained matters: VaM resolves ``url`` references against the DAZ
    content directories it reads out of the registry, and complains "could not
    found libraries" for anything it cannot reach.  Every reference here is a
    local ``#id``.
    """
    if isinstance(meshes, DufMesh):
        meshes = [meshes]
    meshes = list(meshes)
    assert meshes, "no meshes to write"
    names = [m.name for m in meshes]
    assert len(set(names)) == len(names), "mesh names must be unique: %s" % (names,)

    geometry_library, node_library, uv_library, material_library = [], [], [], []
    scene_nodes, scene_materials = [], []
    for mesh in meshes:
        geom_id = "%s-1" % mesh.name
        node_id = mesh.name
        scene_node_id = "%s-2" % mesh.name
        scene_geom_id = "%s-3" % mesh.name

        centre = mesh.verts.mean(axis=0) if len(mesh.verts) else np.zeros(3)
        top = mesh.verts.max(axis=0) if len(mesh.verts) else np.zeros(3)
        geometry_library.append(mesh.geometry(geom_id))
        node_library.append(_node(node_id, mesh.name, centre,
                                  (centre[0], top[1], centre[2])))
        uv = mesh.uv_set()
        if uv is not None:
            uv_library.append(uv)

        scene_nodes.append({
            "id": scene_node_id, "url": "#%s" % node_id, "name": mesh.name,
            "label": mesh.name,
            "geometries": [{"id": scene_geom_id, "url": "#%s" % geom_id,
                            "name": mesh.name, "label": mesh.name,
                            "type": "polygon_mesh"}],
        })
        uv_url = "#%s" % mesh.name if uv is not None else None
        for index, material in enumerate(mesh.material_names):
            mat_id = "%s_%s" % (mesh.name, material)
            material_library.append(_material(mat_id))
            scene_materials.append(_scene_material(
                "%s-1" % mat_id, "#%s" % mat_id, "#%s" % scene_geom_id,
                [material], uv_url))

    doc = {
        "file_version": FILE_VERSION,
        "asset_info": {
            "id": asset_id or ("/%s.duf" % meshes[0].name),
            "type": "scene_subset",
            "contributor": {"author": author, "email": "", "website": ""},
            "revision": "1.0",
        },
        "geometry_library": geometry_library,
        "node_library": node_library,
    }
    if modified:
        doc["asset_info"]["modified"] = modified
    if uv_library:
        doc["uv_set_library"] = uv_library
    doc["material_library"] = material_library
    doc["scene"] = {"nodes": scene_nodes, "materials": scene_materials}
    return doc


def build_morph_dsf(name, deltas, gender="female", group="/Morphs/Custom",
                    label=None, vertex_count=GENESIS2_VERTS, space="blender",
                    minimum=0.0, maximum=1.0, author="ripper_tpose",
                    region=None, asset_id=None):
    """A Genesis 2 morph.  ``deltas`` is a dict {vertex index: (dx, dy, dz)}.

    Drop the result in ``Custom/Atom/Person/Morphs/<gender>/<creator>/<...>``
    and VaM compiles it to ``.vmi``/``.vmb`` on the next startup.
    """
    assert gender in GENESIS2_PARENT, "gender must be female or male"
    if isinstance(deltas, dict):
        items = sorted(deltas.items())
        indices = [int(i) for i, _ in items]
        offsets = np.asarray([d for _, d in items], dtype=np.float64)
    else:
        deltas = np.asarray(deltas, dtype=np.float64)
        assert deltas.ndim == 2 and deltas.shape[1] == 4, \
            "deltas must be a dict or an Nx4 [index, dx, dy, dz] array"
        indices = [int(i) for i in deltas[:, 0]]
        offsets = deltas[:, 1:]
    assert len(indices), "morph %s has no deltas" % name
    for i in indices:
        assert 0 <= i < vertex_count, "morph %s: vertex %d outside the %d vertex base" % (
            name, i, vertex_count)
    # Deltas are differences of positions, so the same linear map applies.
    offsets = TO_DAZ[space](offsets) if len(offsets) else offsets
    values = [[i] + [round(float(x), 7) for x in row] for i, row in zip(indices, offsets)]

    modifier = {
        "id": name, "name": name,
        "parent": GENESIS2_PARENT[gender],
        "presentation": {"type": "Modifier/Shape", "label": "", "description": "",
                         "icon_large": "", "colors": [[0.3529412] * 3, [1, 1, 1]]},
        "channel": {"id": "value", "type": "float", "name": "Value",
                    "label": label or name, "auto_follow": True, "value": 0,
                    "min": minimum, "max": maximum, "clamped": True,
                    "display_as_percent": True, "step_size": 0.01},
        "group": group,
        "morph": {"vertex_count": int(vertex_count),
                  "deltas": {"count": len(values), "values": values}},
    }
    if region:
        modifier["region"] = region
    return {
        "file_version": FILE_VERSION,
        "asset_info": {"id": asset_id or ("/%s.dsf" % name), "type": "modifier",
                       "contributor": {"author": author, "email": "", "website": ""},
                       "revision": "1.0"},
        "modifier_library": [modifier],
        "scene": {"modifiers": [{"id": "%s-1" % name, "url": "#%s" % name}]},
    }


def write_dson(path, doc, compress=True):
    """Write a DSON document.  DAZ gzips these by default and so does VaM's
    own sample, so that is the default here too; plain text is easier to
    debug and VaM reads it as well."""
    text = json.dumps(doc, ensure_ascii=False, indent=1).encode("utf-8")
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    if compress:
        with gzip.GzipFile(path, "wb", mtime=0) as fh:
            fh.write(text)
    else:
        with open(path, "wb") as fh:
            fh.write(text)
    return path


def read_dson(path):
    """Read a ``.duf``/``.dsf``, compressed or not."""
    with open(path, "rb") as fh:
        raw = fh.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return json.loads(raw.decode("utf-8"))


def check_duf(doc):
    """Assert the invariants VaM's importer relies on; return warnings.

    Every "Could not find ..." message in VaM's importer is a dangling ``url``,
    so the references are checked here rather than in front of the user.
    """
    for key in ("file_version", "asset_info", "geometry_library", "node_library", "scene"):
        assert key in doc, "missing %s" % key

    geometries = {}
    for geom in doc["geometry_library"]:
        verts = geom["vertices"]
        polys = geom["polylist"]
        assert verts["count"] == len(verts["values"]), "%s: vertex count mismatch" % geom["id"]
        assert polys["count"] == len(polys["values"]), "%s: polygon count mismatch" % geom["id"]
        materials = geom["polygon_material_groups"]["values"]
        groups = geom["polygon_groups"]["values"]
        for poly in polys["values"]:
            assert len(poly) in (5, 6), "%s: polygon with %d entries" % (geom["id"], len(poly))
            assert 0 <= poly[0] < len(groups), "%s: face group out of range" % geom["id"]
            assert 0 <= poly[1] < len(materials), "%s: material group out of range" % geom["id"]
            for i in poly[2:]:
                assert 0 <= i < verts["count"], "%s: vertex %d out of range" % (geom["id"], i)
        geometries[geom["id"]] = geom

    uv_sets = {}
    for uv in doc.get("uv_set_library", []):
        assert uv["uvs"]["count"] == len(uv["uvs"]["values"]), "%s: uv count mismatch" % uv["id"]
        assert uv["uvs"]["count"] >= uv["vertex_count"], \
            "%s: fewer uvs than vertices" % uv["id"]
        for poly, vertex, index in uv.get("polygon_vertex_indices") or []:
            assert 0 <= index < uv["uvs"]["count"], "%s: uv index out of range" % uv["id"]
            assert vertex >= 0 and poly >= 0, "%s: negative index" % uv["id"]
        uv_sets[uv["id"]] = uv

    nodes = {n["id"] for n in doc["node_library"]}
    materials = {m["id"] for m in doc.get("material_library", [])}
    scene_geometries = {}
    for node in doc["scene"]["nodes"]:
        assert node["url"].lstrip("#") in nodes, "scene node %s: dangling url" % node["id"]
        for geom in node.get("geometries", []):
            target = geom["url"].lstrip("#")
            assert target in geometries, "scene geometry %s: dangling url" % geom["id"]
            scene_geometries[geom["id"]] = geometries[target]
    for material in doc["scene"].get("materials", []):
        assert material["url"].lstrip("#") in materials, \
            "scene material %s: dangling url" % material["id"]
        geom = scene_geometries.get(material["geometry"].lstrip("#"))
        assert geom is not None, "scene material %s: dangling geometry" % material["id"]
        known = set(geom["polygon_material_groups"]["values"])
        for group in material.get("groups", []):
            assert group in known, "scene material %s: unknown group %s" % (material["id"], group)

    warnings = []
    for geom in doc["geometry_library"]:
        count = geom["vertices"]["count"]
        if count > WRAP_VERTEX_LIMIT:
            warnings.append("%s has %d vertices; VaM recommends decimating below %d "
                            "before wrapping" % (geom["id"], count, WRAP_VERTEX_LIMIT))
        elif count > SIM_VERTEX_LIMIT:
            warnings.append("%s has %d vertices; fine for a wrap, too many for the "
                            "cloth sim (VaM recommends below %d)"
                            % (geom["id"], count, SIM_VERTEX_LIMIT))
        if geom.get("default_uv_set") and not doc.get("uv_set_library"):
            warnings.append("%s names a uv set but the file has none" % geom["id"])
        if not geom.get("default_uv_set"):
            warnings.append("%s has no UVs; textures cannot be assigned in VaM" % geom["id"])
    return warnings
