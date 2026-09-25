"""Unity 2019.4 Mesh (read as a typetree dict) -> numpy arrays.

UnityPy's Mesh class trips over NARAKA's meshes, so the vertex streams are
decoded here straight from m_VertexData: channels 0 position, 1 normal,
2 tangent, 3 colour, 4-11 uv0-7, 12 blend weights, 13 blend indices; each
stream is interleaved with a stride of its channels' sizes, streams are laid
end to end, each starting on a 16-byte boundary.
"""
import numpy as np

# VertexFormat (2019+) -> (numpy dtype, normaliser)
FORMATS = {
    0: (np.float32, None), 1: (np.float16, None),
    2: (np.uint8, 255.0), 3: (np.int8, 127.0),
    4: (np.uint16, 65535.0), 5: (np.int16, 32767.0),
    6: (np.uint8, None), 7: (np.int8, None),
    8: (np.uint16, None), 9: (np.int16, None),
    10: (np.uint32, None), 11: (np.int32, None),
}
NAMES = {0: "vertices", 1: "normals", 2: "tangents", 3: "colors", 12: "weights", 13: "bone_indices"}
for _i in range(8):
    NAMES[4 + _i] = "uv%d" % _i


def _bytes(value):
    if isinstance(value, (bytes, bytearray, memoryview)):
        return bytes(value)
    return bytes(bytearray(value))


def decode(tt, resource_reader=None):
    """{"vertices": (n,3), "normals", "uv0".., "weights": (n,4), "bone_indices": (n,4),
    "indices": (m,), "submeshes": [(first index, count, topology)], "bindposes": (b,4,4),
    "bone_hashes": [...], "root_hash": int, "name": str}."""
    vd = tt["m_VertexData"]
    count = vd["m_VertexCount"]
    data = _bytes(vd["m_DataSize"]) if vd.get("m_DataSize") is not None else b""
    stream = tt.get("m_StreamData") or {}
    if not data and stream.get("size"):
        if resource_reader is None:
            raise ValueError("mesh data lives in %s; no reader" % stream.get("path"))
        data = resource_reader(stream["path"], stream["offset"], stream["size"])
    channels = vd["m_Channels"]
    # stream strides and offsets
    strides = {}
    for ch in channels:
        if ch["dimension"] & 0xF:
            size = np.dtype(FORMATS[ch["format"]][0]).itemsize * (ch["dimension"] & 0xF)
            strides[ch["stream"]] = max(strides.get(ch["stream"], 0), ch["offset"] + size)
    starts, pos = {}, 0
    for s in sorted(strides):
        starts[s] = pos
        pos += strides[s] * count
        pos = (pos + 15) & ~15
    out = {"name": tt.get("m_Name", "")}
    for i, ch in enumerate(channels):
        dim = ch["dimension"] & 0xF
        if not dim:
            continue
        dtype, norm = FORMATS[ch["format"]]
        itemsize = np.dtype(dtype).itemsize
        stride = strides[ch["stream"]]
        buf = np.frombuffer(data, dtype=np.uint8, count=stride * count, offset=starts[ch["stream"]])
        buf = buf.reshape(count, stride)[:, ch["offset"]:ch["offset"] + itemsize * dim]
        arr = np.ascontiguousarray(buf).view(dtype).reshape(count, dim)
        if norm:
            arr = arr.astype(np.float32) / norm
        out[NAMES.get(i, "ch%d" % i)] = arr
    idx = _bytes(tt["m_IndexBuffer"])
    out["indices"] = np.frombuffer(idx, dtype=np.uint32 if tt.get("m_IndexFormat") == 1 else np.uint16).astype(np.int64)
    isz = 4 if tt.get("m_IndexFormat") == 1 else 2
    out["submeshes"] = []
    for sm in tt["m_SubMeshes"]:
        first = sm["firstByte"] // isz
        tri = out["indices"][first:first + sm["indexCount"]] + sm.get("baseVertex", 0)
        out["indices"][first:first + sm["indexCount"]] = tri
        out["submeshes"].append((first, sm["indexCount"], sm["topology"]))
    bp = tt.get("m_BindPose") or []
    out["bindposes"] = np.array([[[m["e%d%d" % (r, c)] for c in range(4)] for r in range(4)] for m in bp],
                                dtype=np.float64).reshape(-1, 4, 4)
    out["bone_hashes"] = list(tt.get("m_BoneNameHashes") or [])
    out["root_hash"] = tt.get("m_RootBoneNameHash")
    shapes = tt.get("m_Shapes") or {}
    out["shapes"] = shapes if shapes.get("shapes") else None
    return out
