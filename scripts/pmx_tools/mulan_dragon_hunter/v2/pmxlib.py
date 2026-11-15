# Small helpers shared by the 水晶猎龙者 v2 scripts (plain Python: mmd_tools' pmx module via the head-swap core).
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
_ADDONS = os.path.normpath(os.path.join(HERE, "..", "..", "..", "blender_addons"))     # scripts/blender_addons
if not os.path.isdir(_ADDONS):
    _ADDONS = r"E:\code\othercode\ripper_tpose\scripts\blender_addons"
for p in (os.path.join(_ADDONS, "pmx_head_swap"), _ADDONS):
    if p not in sys.path:
        sys.path.insert(0, p)
import core  # noqa: E402  (pmx_head_swap/core.py)

oc = core.oc
pmx = oc.pmx_module()
UNIT_CM = oc.UNIT_CM


def load(path):
    return pmx.load(path)


def save(M, path):
    pmx.save(path, M, add_uv_count=M.header.additional_uvs)


def mat_faces(M):
    """material index -> (face_start, face_count)"""
    out, k = {}, 0
    for i, m in enumerate(M.materials):
        n = m.vertex_count // 3
        out[i] = (k, n)
        k += n
    return out


def mat_index(M, name):
    for i, m in enumerate(M.materials):
        if m.name == name:
            return i
    raise KeyError(name)


def mat_vertices(M, mi):
    s, n = mat_faces(M)[mi]
    vs = set()
    for f in M.faces[s:s + n]:
        vs.update(f)
    return sorted(vs)


def bone_index(M, name):
    for i, b in enumerate(M.bones):
        if b.name == name:
            return i
    raise KeyError(name)


def weights_of(M, v):
    return oc.weights_of(pmx, M.vertices[v])


def dominant_bone(M, v):
    ws = weights_of(M, v)
    return max(ws, key=lambda t: t[1])[0] if ws else 0


def bdef1(bone):
    w = pmx.BoneWeight()
    w.type, w.bones, w.weights = pmx.BoneWeight.BDEF1, [int(bone)], []
    return w


def new_vertex(M, co, normal, uv, bone):
    v = pmx.Vertex()
    v.co = [float(x) for x in co]
    v.normal = [float(x) for x in normal]
    v.uv = [float(x) for x in uv]
    v.additional_uvs = [[0.0, 0.0, 0.0, 0.0]] * M.header.additional_uvs
    v.weight = bdef1(bone)
    v.edge_scale = 1.0
    M.vertices.append(v)
    return len(M.vertices) - 1


def add_texture(M, rel_path):
    for i, t in enumerate(M.textures):
        if t.path.replace("\\", "/") == rel_path.replace("\\", "/"):
            return i
    t = pmx.Texture()
    t.path = rel_path
    M.textures.append(t)
    return len(M.textures) - 1


def new_material(M, name, name_e, tex, faces, diffuse=(1, 1, 1, 1), specular=(0.3, 0.3, 0.3), shininess=10,
                 ambient=(0.5, 0.5, 0.5), edge=False, edge_color=(0, 0, 0, 1), edge_size=1.0, toon=0, comment=""):
    """append faces (list of 3-tuples of vertex indices) as a new material at the end"""
    m = pmx.Material()
    m.name, m.name_e = name, name_e
    m.diffuse, m.specular, m.shininess, m.ambient = list(diffuse), list(specular), shininess, list(ambient)
    m.is_double_sided = False
    m.enabled_drop_shadow = m.enabled_self_shadow_map = m.enabled_self_shadow = True
    m.enabled_toon_edge = edge
    m.edge_color, m.edge_size = list(edge_color), edge_size
    m.texture, m.sphere_texture, m.sphere_texture_mode = tex, -1, 0
    m.is_shared_toon_texture, m.toon_texture = True, toon
    m.comment = comment
    m.vertex_count = len(faces) * 3
    M.materials.append(m)
    M.faces.extend([list(f) for f in faces])
    return len(M.materials) - 1


def swap_lr(name):
    if "左" in name:
        return name.replace("左", "右")
    if "右" in name:
        return name.replace("右", "左")
    for a, b in (("_L", "_R"), ("_R", "_L"), ("L ", "R "), ("R ", "L "), ("Left", "Right"), ("Right", "Left")):
        if a in name:
            return name.replace(a, b, 1)
    return name


def frame_from(d):
    """orthonormal (u, v, d) with d the given unit direction"""
    d = np.asarray(d, float)
    d = d / (np.linalg.norm(d) + 1e-12)
    a = np.array([1.0, 0, 0]) if abs(d[0]) < 0.9 else np.array([0, 1.0, 0])
    u = np.cross(d, a)
    u /= np.linalg.norm(u) + 1e-12
    v = np.cross(d, u)
    return u, v, d
