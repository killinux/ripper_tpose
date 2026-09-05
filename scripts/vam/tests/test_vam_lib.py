"""Synthetic regression for vam_lib.py.  Pure Python + numpy, no Blender,
no game data: every fixture is built in a temp directory.

Covers:
  * lenient JSON (trailing commas, BOM) and HSV colours
  * .vab DAZMesh binary round trip (writer mirrors the documented layout)
  * .vmb morph deltas
  * package index: SELF:/, Creator.Package.latest:/, pinned version, bare
    Custom/ paths, case-insensitive members, duplicate packages
  * catalog keys for scenes / presets / clothing and --only selection
  * AssetStudio dump parsers (mesh, morph bank, texture control, character)
  * skin texture name classifier across the creator naming schemes seen
  * to_blender mirror + winding reversal, displacement transfer,
    nearest-distance / vertex-normal helpers behind skin-layer detection

Usage:
  python test_vam_lib.py          -> prints VAM_LIB_TEST=PASS
"""

import io
import json
import os
import shutil
import struct
import sys
import tempfile
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import vam_lib as vl  # noqa: E402

MARKER = "VAM_LIB_TEST"


# --------------------------------------------------------------------------
# fixture writers
# --------------------------------------------------------------------------

def w_str(buf, text):
    data = text.encode("utf-8")
    length = len(data)
    while True:
        byte = length & 0x7F
        length >>= 7
        if length:
            buf.write(bytes([byte | 0x80]))
        else:
            buf.write(bytes([byte]))
            break
    buf.write(data)


def make_vab(name="Dress", materials=("mat-a", "mat-b")):
    """A quad + a triangle sharing an edge; one UV seam splits vertex 0."""
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (2, 0.5, 0)]
    polys = [(0, (0, 1, 2, 3)), (1, (1, 4, 2))]
    uv_polys = [(0, (5, 1, 2, 3)), (1, (1, 4, 2))]        # uv vert 5 duplicates 0
    uvs = [(0, 0), (1, 0), (1, 1), (0, 1), (0.9, 0.5), (0.05, 0.05)]
    buf = io.BytesIO()
    for text in ("DynamicStore", "1.0", "DAZMesh", "1.0", name, name + "-2",
                 name + "-1", name + "-3"):
        w_str(buf, text)
    buf.write(struct.pack("<i", len(verts)))
    for v in verts:
        buf.write(struct.pack("<3f", *v))
    buf.write(struct.pack("<i", len(materials)))
    for m in materials:
        w_str(buf, m)
    buf.write(struct.pack("<i", len(polys)))
    for plist in (polys, uv_polys):
        for mat, idx in plist:
            buf.write(struct.pack("<ii", mat, len(idx)))
            buf.write(struct.pack("<%di" % len(idx), *idx))
    buf.write(struct.pack("<i", len(uvs)))
    for uv in uvs:
        buf.write(struct.pack("<2f", *uv))
    buf.write(struct.pack("<i", 1))
    buf.write(struct.pack("<ii", 5, 0))
    buf.write(b"\x00" * 32)                             # trailing wrap data
    return buf.getvalue(), verts, polys, uvs


def make_hair_vab(scalp="UdaneScalp", scalp_verts=4, segments=3):
    """Two guides (slots 0 and 2), slots 1 and 3 empty."""
    buf = io.BytesIO()
    w_str(buf, "DynamicStore"); w_str(buf, "1.0"); buf.write(b"\x01")
    w_str(buf, "RuntimeHairGeometryCreator"); w_str(buf, "1.1"); w_str(buf, scalp)
    buf.write(struct.pack("<if", segments, 0.02))
    buf.write(b"\x00")
    buf.write(struct.pack("<i", scalp_verts))
    buf.write(bytes([0, 1, 0, 1]))
    buf.write(struct.pack("<i", scalp_verts))
    for slot in range(scalp_verts):
        if slot in (0, 2):
            buf.write(struct.pack("<ii", slot, segments))
            for k in range(segments):
                buf.write(struct.pack("<3f", slot * 0.1, 1.7 - 0.02 * k, 0.0))
        else:
            buf.write(struct.pack("<ii", slot, 0))
    buf.write(b"\x00" * 16)
    return buf.getvalue()


def make_vmb(records):
    buf = io.BytesIO()
    buf.write(struct.pack("<i", len(records)))
    for idx, (x, y, z) in records:
        buf.write(struct.pack("<i3f", idx, x, y, z))
    return buf.getvalue()


def write_var(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, payload in files.items():
            if isinstance(payload, str):
                payload = payload.encode("utf-8")
            zf.writestr(name, payload)


SCENE = """{
  "atoms" : [
    { "id" : "Person", "type" : "Person", "storables" : [
        { "id" : "geometry", "character" : "Female Custom",
          "morphs" : [ { "uid" : "SELF:/Custom/Atom/Person/Morphs/female/Body.vmi", "name" : "Body", "value" : "1", }, ],
          "clothing" : [ { "id" : "Maker.Pack.latest:/Custom/Clothing/Female/Maker/Dress/Dress.vam", "internalId" : "Maker:Dress", "enabled" : "true", }, ],
          "hair" : [ ], },
        { "id" : "textures", "faceDiffuseUrl" : "SELF:/Custom/Atom/Person/Textures/face.png", },
    ], },
    { "id" : "Light", "type" : "InvisibleLight", "storables" : [ ] },
  ],
}"""


def build_install(root):
    addon = os.path.join(root, "AddonPackages")
    os.makedirs(os.path.join(addon, "sub"))
    vab, _v, _p, _u = make_vab()
    write_var(os.path.join(addon, "Maker.Pack.1.var"), {
        "meta.json": '{ "creatorName" : "Maker", "packageName" : "Pack", }',
        "Custom/Clothing/Female/Maker/Dress/Dress.vam":
            '{ "itemType" : "ClothingFemale", "uid" : "Maker:Dress", "displayName" : "Dress", }',
        "Custom/Clothing/Female/Maker/Dress/Dress.vaj": '{ "storables" : [ ] }',
        "Custom/Clothing/Female/Maker/Dress/Dress.vab": vab,
    })
    # A newer version in a sub folder must win ".latest".
    write_var(os.path.join(addon, "sub", "Maker.Pack.2.var"), {
        "meta.json": '{ "creatorName" : "Maker", "packageName" : "Pack", }',
        "Custom/Clothing/Female/Maker/Dress/Dress.vam":
            '{ "itemType" : "ClothingFemale", "uid" : "Maker:Dress", "displayName" : "Dress", }',
        "Custom/Clothing/Female/Maker/Dress/Dress.vaj": '{ "storables" : [ ] }',
        "Custom/Clothing/Female/Maker/Dress/Dress.vab": vab,
        "Custom/Clothing/Female/Maker/Dress/tex/Dress.png": b"\x89PNG",
        "Custom/Hair/Female/Maker/Bob/Bob.vam":
            '{ "itemType" : "HairFemale", "uid" : "Maker:Bob", "displayName" : "Bob" }',
        "Custom/Hair/Female/Maker/Bob/Bob.vab": make_hair_vab(),
    })
    write_var(os.path.join(addon, "Look.Scene.3.var"), {
        "meta.json": "{}",
        "Saves/scene/Look/Angel.json": SCENE,
        "Custom/Atom/Person/Appearance/Preset_Angel.vap":
            '{ "storables" : [ { "id" : "geometry", "character" : "Kayla", "morphs" : [ ] } ] }',
        "Custom/Atom/Person/Morphs/female/Body.vmi":
            '{ "id" : "Body", "isPoseControl" : "false", "numDeltas" : "2", }',
        "Custom/Atom/Person/Morphs/female/Body.vmb":
            make_vmb([(0, (0.1, 0, 0)), (99999, (5, 5, 5))]),
        "Custom/Atom/Person/Textures/Face.PNG": b"\x89PNG-face",
    })
    # A loose copy of the same package id is ignored, not double counted.
    shutil.copyfile(os.path.join(addon, "Look.Scene.3.var"),
                    os.path.join(addon, "sub", "Look.Scene.3.var"))
    os.makedirs(os.path.join(root, "Custom", "Atom", "Person", "Textures", "Local"))
    with open(os.path.join(root, "Custom", "Atom", "Person", "Textures", "Local",
                           "skin.jpg"), "wb") as handle:
        handle.write(b"JPG")
    os.makedirs(os.path.join(root, "Saves", "scene"))
    return root


# --------------------------------------------------------------------------
# tests
# --------------------------------------------------------------------------

def test_json_and_colours():
    data = vl.lenient_json_loads("﻿{ \"a\" : [ 1, 2, ], \"b\" : { \"c\" : \"x\", }, }")
    assert data == {"a": [1, 2], "b": {"c": "x"}}, data
    rgb = vl.storable_color({"h": "0", "s": "1", "v": "1"})
    assert [round(c, 6) for c in rgb] == [1.0, 0.0, 0.0], rgb
    assert vl.storable_color(None, "dflt") == "dflt"
    assert vl.as_bool("true") and not vl.as_bool("false") and vl.as_bool(None, True)
    assert vl.sanitize('a/b:c*d?e"f<g>h|i j') == "a_b_c_d_e_f_g_h_i_j"
    assert vl.make_key("Maker.Pack.1", "My Dress") == "Maker.Pack.1~My_Dress"


def test_vab_and_vmb():
    data, verts, polys, uvs = make_vab()
    assert vl.is_dazmesh_vab(data[:64])
    assert not vl.is_dazmesh_vab(b"\x0cDynamicStore\x031.0\x01\x1aRuntimeHair")
    mesh = vl.parse_dazmesh_vab(data)
    assert mesh.name == "Dress" and mesh.ids == ["Dress-2", "Dress-1", "Dress-3"]
    assert mesh.material_names == ["mat-a", "mat-b"]
    assert mesh.num_verts == 5 and mesh.num_polys == 2
    assert np.allclose(mesh.verts, np.asarray(verts, dtype=np.float32))
    assert mesh.poly_mat.tolist() == [0, 1] and mesh.poly_len.tolist() == [4, 3]
    assert mesh.poly_idx.tolist() == [0, 1, 2, 3, 1, 4, 2]
    assert mesh.uv_poly_idx.tolist() == [5, 1, 2, 3, 1, 4, 2]
    assert np.allclose(mesh.uvs, np.asarray(uvs, dtype=np.float32))
    # Corrupt the UV map count -> must fail loudly, not silently.
    bad = bytearray(data)
    pos = data.rindex(struct.pack("<ii", 5, 0)) - 4
    bad[pos:pos + 4] = struct.pack("<i", 7)
    try:
        vl.parse_dazmesh_vab(bytes(bad))
    except ValueError:
        pass
    else:
        raise AssertionError("corrupt UV map accepted")
    idx, delta = vl.parse_vmb(make_vmb([(3, (1, 2, 3)), (7, (-1, 0, 0.5))]))
    assert idx.tolist() == [3, 7] and delta.shape == (2, 3) and delta[1, 2] == 0.5
    try:
        vl.parse_vmb(make_vmb([(3, (1, 2, 3))])[:-4])
    except ValueError:
        pass
    else:
        raise AssertionError("truncated vmb accepted")


def test_hair():
    data = make_hair_vab()
    assert vl.is_runtime_hair_vab(data[:96]) and not vl.is_dazmesh_vab(data[:64])
    guides = vl.parse_hair_vab(data)
    assert guides.scalp == "UdaneScalp" and guides.scalp_token == "udane"
    assert guides.segments == 3 and abs(guides.segment_length - 0.02) < 1e-6
    assert guides.scalp_verts == 4 and guides.mask.tolist() == [0, 1, 0, 1]
    assert guides.roots.tolist() == [0, 2] and len(guides.strands) == 2
    assert np.allclose(guides.strands[1][0], [0.2, 1.7, 0.0])
    fanned = vl.hair_children(guides.strands, 4, 0.01, seed=1)
    assert len(fanned) == 8 and all(s.shape == (3, 3) for s in fanned)
    assert np.array_equal(fanned[0], guides.strands[0])            # guide kept verbatim
    assert np.all(np.linalg.norm(fanned[1] - guides.strands[0], axis=1) <= 0.01 * 1.4 + 1e-6)
    assert vl.hair_children(guides.strands, 1, 0.01) == guides.strands
    straight = np.stack([np.zeros(30), 1.7 - 0.02 * np.arange(30), np.zeros(30)], axis=1)
    curved = straight.copy()
    curved[:, 2] = 0.1 * np.sin(np.linspace(0, 3, 30))
    kept, dropped = vl.drop_unstyled_guides([straight, curved, straight[:5]], 0.02)
    assert dropped == 0 and len(kept) == 3, (dropped, len(kept))    # hanging straight hair stays
    sideways = np.stack([0.02 * np.arange(30), np.full(30, 1.7), np.zeros(30)], axis=1)
    kept, dropped = vl.drop_unstyled_guides([sideways, curved], 0.02)
    assert dropped == 1 and len(kept) == 1 and kept[0] is not sideways, (dropped, len(kept))
    try:
        vl.parse_hair_vab(data[:-40])
    except (ValueError, IndexError, struct.error):
        pass
    else:
        raise AssertionError("truncated hair file accepted")


def test_index_and_catalog(root):
    index = vl.PackageIndex(root)
    ids = sorted(p.id for p in index.packages)
    assert ids == ["Look.Scene.3", "Maker.Pack.1", "Maker.Pack.2"], ids
    assert index.latest("maker.pack").version == 2
    assert index.package_for("Maker.Pack.1").version == 1
    assert index.package_for("Maker.Pack.latest").version == 2
    assert index.package_for("Nobody.Nothing.latest") is None
    look = index.by_id["Look.Scene.3"]
    pkg, member = index.resolve("SELF:/Custom/Atom/Person/Textures/face.png", look)
    assert pkg is look and member == "Custom/Atom/Person/Textures/Face.PNG", member
    pkg, member = index.resolve(
        "Maker.Pack.latest:/Custom/Clothing/Female/Maker/Dress/Dress.vam", look)
    assert pkg.version == 2 and member.endswith("Dress.vam")
    pkg, member = index.resolve("Custom/Atom/Person/Textures/Local/skin.jpg", look)
    assert pkg is index.local and member.endswith("skin.jpg"), (pkg, member)
    assert index.resolve("SELF:/Custom/missing.png", look) == (None, None)
    assert index.resolve("", look) == (None, None)
    assert vl.region_from_morph_path("Custom/Atom/Person/Morphs/female_genitalia/x.vmi") \
        == "female_genitalia"
    assert vl.region_from_morph_path("Custom/Atom/Person/Morphs/female/x.vmi") == "female"

    catalog = vl.Catalog(index)
    keys = {e.key: e for e in catalog.entries()}
    expected = {"Look.Scene.3~Angel~Person", "Look.Scene.3~Preset_Angel",
                "Maker.Pack.1~Dress", "Maker.Pack.2~Dress", "Maker.Pack.2~Bob"}
    assert expected <= set(keys), sorted(keys)
    scene = keys["Look.Scene.3~Angel~Person"]
    assert scene.extra["character"] == "Female Custom"
    assert scene.extra["morphs"] == 1 and scene.extra["clothing"] == 1
    assert scene.extra["skinTextures"] == 1 and scene.extra["source"] == "scene"
    assert keys["Look.Scene.3~Preset_Angel"].extra["source"] == "preset"
    dress = keys["Maker.Pack.2~Dress"]
    assert dress.kind == "clothing" and dress.extra["exportable"] is True
    bob = keys["Maker.Pack.2~Bob"]
    assert bob.kind == "hair" and bob.extra["exportable"] is True
    assert catalog.by_uid("maker:dress").kind == "clothing"

    chosen, unknown = catalog.select(["Look.Scene.3~Angel~Person", "preset_angel"])
    assert [e.key for e in chosen] == ["Look.Scene.3~Angel~Person", "Look.Scene.3~Preset_Angel"]
    assert not unknown
    chosen, unknown = catalog.select(["dress"])
    assert not chosen and unknown and "ambiguous" in unknown[0], unknown
    chosen, unknown = catalog.select([], indices=[1, 999])
    assert len(chosen) == 1 and "out of range" in unknown[0]


MESH_DUMP = """MonoBehaviour Base
\tstring m_Name = ""
\tstring geometryId = "GenesisFemale-1:Genitalia-default"
\tint _numBaseVertices = 4
\tint _numBasePolygons = 1
\tint _numUVVertices = 4
\tint _numMaterials = 2
\tvector _materialNames
\t\tArray Array
\t\tint size = 2
\t\t\t[0]
\t\t\tstring data = "Face"
\t\t\t[1]
\t\t\tstring data = "Hidden"
\tvector _baseVertices
\t\tArray Array
\t\tint size = 4
\t\t\t[0]
\t\t\tVector3f data
\t\t\t\tfloat x = 0
\t\t\t\tfloat y = 0
\t\t\t\tfloat z = 0
\t\t\t[1]
\t\t\tVector3f data
\t\t\t\tfloat x = 1
\t\t\t\tfloat y = 0
\t\t\t\tfloat z = 0
\t\t\t[2]
\t\t\tVector3f data
\t\t\t\tfloat x = 1
\t\t\t\tfloat y = 1
\t\t\t\tfloat z = 0
\t\t\t[3]
\t\t\tVector3f data
\t\t\t\tfloat x = 0
\t\t\t\tfloat y = 1
\t\t\t\tfloat z = 0
\tMeshPoly _basePolyList
\t\tArray Array
\t\tint size = 1
\t\t\t[0]
\t\t\tMeshPoly data
\t\t\t\tint materialNum = 1
\t\t\t\tvector vertices
\t\t\t\t\tArray Array
\t\t\t\t\tint size = 4
\t\t\t\t\t\t[0]
\t\t\t\t\t\tint data = 0
\t\t\t\t\t\t[1]
\t\t\t\t\t\tint data = 1
\t\t\t\t\t\t[2]
\t\t\t\t\t\tint data = 2
\t\t\t\t\t\t[3]
\t\t\t\t\t\tint data = 3
\tUInt8 debugGrafting = 0
\tMeshPoly _UVPolyList
\t\tArray Array
\t\tint size = 1
\t\t\t[0]
\t\t\tMeshPoly data
\t\t\t\tint materialNum = 1
\t\t\t\tvector vertices
\t\t\t\t\tArray Array
\t\t\t\t\tint size = 4
\t\t\t\t\t\t[0]
\t\t\t\t\t\tint data = 3
\t\t\t\t\t\t[1]
\t\t\t\t\t\tint data = 2
\t\t\t\t\t\t[2]
\t\t\t\t\t\tint data = 1
\t\t\t\t\t\t[3]
\t\t\t\t\t\tint data = 0
\tvector _OrigUV
\t\tArray Array
\t\tint size = 4
\t\t\t[0]
\t\t\tVector2f data
\t\t\t\tfloat x = 0
\t\t\t\tfloat y = 0
\t\t\t[1]
\t\t\tVector2f data
\t\t\t\tfloat x = 1
\t\t\t\tfloat y = 0
\t\t\t[2]
\t\t\tVector2f data
\t\t\t\tfloat x = 1
\t\t\t\tfloat y = 1
\t\t\t[3]
\t\t\tVector2f data
\t\t\t\tfloat x = 0
\t\t\t\tfloat y = 1
\tUInt8 _usePatches = 0
"""

BANK_DUMP = """MonoBehaviour Base
\tDAZMorph _morphs
\t\tArray Array
\t\tint size = 2
\t\t\t[0]
\t\t\tDAZMorph data
\t\t\t\tUInt8 isPoseControl = 0
\t\t\t\tstring morphName = "Breast Size"
\t\t\t\tstring displayName = "Breast Size"
\t\t\t\tstring region = "Chest"
\t\t\t\tstring group = "Morph/Chest"
\t\t\t\tint numDeltas = 2
\t\t\t\tDAZMorphVertex deltas
\t\t\t\t\tArray Array
\t\t\t\t\tint size = 2
\t\t\t\t\t\t[0]
\t\t\t\t\t\tDAZMorphVertex data
\t\t\t\t\t\t\tint vertex = 4
\t\t\t\t\t\t\tVector3f delta
\t\t\t\t\t\t\t\tfloat x = 0.5
\t\t\t\t\t\t\t\tfloat y = 0
\t\t\t\t\t\t\t\tfloat z = -0.25
\t\t\t\t\t\t[1]
\t\t\t\t\t\tDAZMorphVertex data
\t\t\t\t\t\t\tint vertex = 9
\t\t\t\t\t\t\tVector3f delta
\t\t\t\t\t\t\t\tfloat x = 1
\t\t\t\t\t\t\t\tfloat y = 2
\t\t\t\t\t\t\t\tfloat z = 3
\t\t\t[1]
\t\t\tDAZMorph data
\t\t\t\tUInt8 isPoseControl = 1
\t\t\t\tstring morphName = "Left Hand Fist"
\t\t\t\tstring displayName = "Left Hand Fist"
\t\t\t\tint numDeltas = 0
\t\t\t\tDAZMorphVertex deltas
\t\t\t\t\tArray Array
\t\t\t\t\tint size = 0
"""

CONTROL_DUMP = """MonoBehaviour Base
\tvector faceMaterialNums
\t\tArray Array
\t\tint size = 2
\t\t\t[0]
\t\t\tint data = 2
\t\t\t[1]
\t\t\tint data = 11
\tvector torsoMaterialNums
\t\tArray Array
\t\tint size = 0
\tvector limbMaterialNums
\t\tArray Array
\t\tint size = 1
\t\t\t[0]
\t\t\tint data = 0
\tvector genitalMaterialNums
\t\tArray Array
\t\tint size = 1
\t\t\t[0]
\t\t\tint data = 28
\tstring uvSetName = "Base Female"
"""

CHARACTER_DUMP = """MonoBehaviour Base
\tstring assetBundleName = "f_rky"
\tstring assetName = "RenKayla"
\tstring displayName = "Kayla"
\tstring displayNameAlt = "by Ren"
\tstring UVname = "UV: Base Female"
\tUInt8 isMale = 0
"""


def test_dump_parsers(tmp):
    path = os.path.join(tmp, "DAZMergedMesh @1.txt")
    open(path, "w", encoding="utf-8").write(MESH_DUMP)
    mesh, header = vl.parse_dump_mesh(path)
    assert header["geometryId"] == "GenesisFemale-1:Genitalia-default"
    assert mesh.material_names == ["Face", "Hidden"]
    assert mesh.num_verts == 4 and mesh.poly_mat.tolist() == [1]
    assert mesh.poly_idx.tolist() == [0, 1, 2, 3] and mesh.uv_poly_idx.tolist() == [3, 2, 1, 0]
    assert mesh.uvs.shape == (4, 2) and mesh.uvs[2].tolist() == [1.0, 1.0]
    assert vl._dump_header(path)["_numBaseVertices"] == "4"

    bank = os.path.join(tmp, "DAZMorphSubBank @2.txt")
    open(bank, "w", encoding="utf-8").write(BANK_DUMP)
    morphs = list(vl.parse_dump_morph_bank(bank))
    assert [m[0]["name"] for m in morphs] == ["Breast Size", "Left Hand Fist"]
    info, idx, delta = morphs[0]
    assert info["isPoseControl"] is False and info["region"] == "Chest"
    assert idx.tolist() == [4, 9] and delta.tolist() == [[0.5, 0.0, -0.25], [1.0, 2.0, 3.0]]
    assert morphs[1][0]["isPoseControl"] is True and morphs[1][1].size == 0

    control = os.path.join(tmp, "DAZCharacterTextureControl @3.txt")
    open(control, "w", encoding="utf-8").write(CONTROL_DUMP)
    groups = vl.parse_dump_texture_control(control)
    assert groups == {"face": [2, 11], "torso": [], "limb": [0], "genital": [28]}, groups

    character = os.path.join(tmp, "DAZCharacter @4.txt")
    open(character, "w", encoding="utf-8").write(CHARACTER_DUMP)
    info = vl.parse_dump_character(character)
    assert info == {"displayName": "Kayla", "bundle": "f_rky", "asset": "RenKayla",
                    "isMale": False, "uv": "UV: Base Female"}, info


def test_texture_names():
    cases = {
        "V5BreeHeadM": ("face", "diffuse", 0),
        "V5BreeHeadSS": ("face", "gloss", 0),
        "V5BreeHead2M": ("face", "diffuse", 1),
        "V5BreeHeadNM": ("face", "normal", 0),
        "V5BreeTorsoS_Nipples": ("torso", "specular", 0),
        "V5BreeInMouthM": ("mouth", "diffuse", 0),
        "genitalia_G2F": ("genitals", "diffuse", 0),
        "genitaliaS_G2F": ("genitals", "specular", 0),
        "faceD": ("face", "diffuse", 0),
        "faceBrowlessD": None,
        "torsoN": ("torso", "normal", 0),
        "EyesM": ("eyes", "diffuse", 0),
        "MouthNM": ("mouth", "normal", 0),
        "Tina Face D Nude": ("face", "diffuse", 1),
        "Tina Gen G": ("genitals", "gloss", 0),
        "Tina-Face-D-Liner": None,
        "Kayla FaceD (B)": None,
        "Kayla GenitalsN": ("genitals", "normal", 0),
        "RyBelle_faceNM": ("face", "normal", 0),
        "RyBelle_face": ("face", "diffuse", 0),
        "RyBelle_faceBU": None,
        "RyBelle_faceMU01": None,
        "M5PhillipFace01S": ("face", "specular", 1),
        "M5PhillipFace01": ("face", "diffuse", 1),
        "M5PhillipFace01SI": None,
        "M5PhillipLashes": ("lashes", "diffuse", 0),
        "V5BreeLashes2": ("lashes", "diffuse", 1),
        "Lashes": ("lashes", "diffuse", 0),
        "black": None,
        "V5BreeEyesNM": ("eyes", "normal", 0),
    }
    for name, expected in cases.items():
        got = vl.classify_texture_name(name)
        assert got == expected, (name, got, expected)
    picks = vl.pick_default_textures(["V5BreeHead2M", "V5BreeHeadM", "V5BreeHeadS",
                                      "faceBrowlessD", "Lashes", "V5BreeLashes2"])
    assert picks[("face", "diffuse")] == "V5BreeHeadM"
    assert picks[("face", "specular")] == "V5BreeHeadS"
    assert picks[("lashes", "diffuse")] == "Lashes"


def test_geometry():
    verts = np.asarray([[1.0, 2.0, 3.0]], dtype=np.float32)
    assert vl.to_blender(verts).tolist() == [[-1.0, -3.0, 2.0]]
    poly_len = np.asarray([4, 3, 3], dtype=np.int32)
    poly_idx = np.asarray([0, 1, 2, 3, 1, 4, 2, 5, 5, 6], dtype=np.int32)
    uv_idx = np.asarray([9, 1, 2, 3, 1, 4, 2, 5, 5, 6], dtype=np.int32)
    poly_mat = np.asarray([0, 1, 1], dtype=np.int32)
    faces, loops, mats = vl.clean_polygons(poly_len, poly_idx, uv_idx, poly_mat)
    assert faces == [(3, 2, 1, 0), (2, 4, 1)], faces          # reversed, degenerate dropped
    assert loops.tolist() == [3, 2, 1, 9, 2, 4, 1] and mats.tolist() == [0, 1]
    faces, loops, mats = vl.clean_polygons(poly_len, poly_idx, uv_idx, poly_mat,
                                           keep_mask=np.asarray([False, True, True]))
    assert faces == [(2, 4, 1)] and mats.tolist() == [1]

    base = np.asarray([[0, 0, 0], [1, 0, 0], [0, 1, 0], [10, 10, 10]], dtype=np.float32)
    moved = base.copy()
    moved[0] += (0, 0, 1)
    moved[1] += (0, 0, 1)
    moved[2] += (0, 0, 1)
    points = np.asarray([[0.3, 0.3, 0.0], [10, 10, 10.01]], dtype=np.float32)
    out = vl.transfer_displacement(points, base, moved, k=3)
    assert abs(out[0, 2] - 1.0) < 1e-4, out                    # carried by the moved trio
    assert abs(out[1, 2] - 10.01) < 1e-3, out                  # far vertex did not move
    same = vl.transfer_displacement(points, base, base)
    assert np.array_equal(same, points)

    dist = vl.nearest_distance(points, base)
    assert abs(dist[1] - 0.01) < 1e-4 and abs(dist[0] - np.sqrt(0.18)) < 1e-4, dist
    quad = np.asarray([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float32)
    normals = vl.vertex_normals(quad, np.asarray([4]), np.asarray([0, 1, 2, 3]))
    assert np.allclose(normals, [[0, 0, 1]] * 4), normals        # CCW -> +Z
    shell = quad + np.asarray([0, 0, 0.0005], dtype=np.float32)
    assert vl.skin_layer_fraction(shell, quad) == 1.0
    assert vl.skin_layer_fraction(shell + 1.0, quad) == 0.0


BONE_DUMP = """MonoBehaviour Base
\tUInt8 isRoot = 0
\tstring _id = "head"
\tVector3f _worldPosition
\t\tfloat x = 0
\t\tfloat y = 1.6184
\t\tfloat z = -0.0228
\tVector3f _maleWorldPosition
\t\tfloat x = 0
\t\tfloat y = 0
\t\tfloat z = 0
\tVector3f _worldOrientation
\t\tfloat x = 1.45
\t\tfloat y = 0
\t\tfloat z = 0
\tVector3f _maleWorldOrientation
\t\tfloat x = 0
\t\tfloat y = 0
\t\tfloat z = 0
\tPPtr<$DAZBones> dazBones
\t\tint m_FileID = 0
\t\tSInt64 m_PathID = 4770755750654332344
\tPPtr<$DAZBone> parentBone
\t\tint m_FileID = 0
\t\tSInt64 m_PathID = -55
"""


def test_transforms_and_rig(tmp):
    # Unity Euler: 90 deg about Y maps +Z to +X (v' = Ry v).
    ry = vl.unity_euler_matrix((0, 90, 0))
    assert np.allclose(ry @ np.array([0, 0, 1.0]), [1, 0, 0], atol=1e-9)
    rx = vl.unity_euler_matrix((90, 0, 0))
    assert np.allclose(rx @ np.array([0, 1.0, 0]), [0, 0, 1], atol=1e-9)
    # Order: Z first, then X, then Y  ->  R = Ry Rx Rz
    rzxy = vl.unity_euler_matrix((10, 20, 30))
    expect = vl.unity_euler_matrix((0, 20, 0)) @ vl.unity_euler_matrix((10, 0, 0)) \
        @ vl.unity_euler_matrix((0, 0, 30))
    assert np.allclose(rzxy, expect)
    # Matrix conversion agrees with the point conversion.
    T = vl.trs_matrix((1, 2, 3), (10, 20, 30), 2.0)
    p = np.array([0.5, -0.25, 4.0])
    lhs = (vl.to_blender_matrix(T) @ np.append(vl.to_blender(p[None, :])[0], 1.0))[:3]
    rhs = vl.to_blender((T @ np.append(p, 1.0))[:3][None, :])[0]
    assert np.allclose(lhs, rhs, atol=1e-5), (lhs, rhs)

    path = os.path.join(tmp, "DAZBone @-1.txt")
    open(path, "w", encoding="utf-8").write(BONE_DUMP)
    bone = vl.parse_dump_bone(path)
    assert bone["id"] == "head" and bone["parentPathId"] == -55 and bone["isRoot"] is False
    assert bone["female"] == [0, 1.6184, -0.0228] and bone["orientFemale"] == [1.45, 0, 0]

    rig = vl.BoneRig({
        "hip": {"parent": None, "female": [0, 1.0, 0], "male": None,
                "orientFemale": [0, 0, 0], "orientMale": None},
        "neck": {"parent": "hip", "female": [0, 1.5, 0], "male": None,
                 "orientFemale": [0, 0, 0], "orientMale": None},
        "head": {"parent": "neck", "female": [0, 1.6, 0], "male": None,
                 "orientFemale": [0, 0, 0], "orientMale": None},
    })
    assert rig.chain("head") == ["hip", "neck", "head"]
    rest_pos, rest_rot = rig.rest_local("head", "female")
    assert np.allclose(rest_pos, [0, 0.1, 0]) and np.allclose(rest_rot, np.eye(3))
    # Unposed person: head at its rest world position.
    unposed = {"control": {}}
    assert np.allclose(rig.transform("head", unposed, "female", posed=True)[:3, 3], [0, 1.6, 0])
    # A saved bone rotation is the full local rotation (Unity euler): neck
    # bent 90 deg about X, Rx(90) maps +y to +z.
    posed = {"control": {}, "neck": {"rotation": {"x": "90", "y": "0", "z": "0"}}}
    head = rig.transform("head", posed, "female", posed=True)
    assert np.allclose(head[:3, 3], [0, 1.5, 0.1], atol=1e-6), head[:3, 3]
    # No controls saved -> FK from the atom root: an asset 5 cm above the
    # bent head lands 5 cm above the upright head.
    cua = {"position": {"x": "0", "y": "1.5", "z": "0.15"},
           "rotation": {"x": "90", "y": "0", "z": "0"}}
    placed = vl.attachment_rest_transform(rig, "female", posed, "head", cua)
    assert np.allclose(placed[:3, 3], [0, 1.65, 0], atol=1e-6), placed[:3, 3]
    assert np.allclose(placed[:3, :3], np.eye(3), atol=1e-6)
    # Control states: the JSON only stores values that differ from VaM's
    # defaults (hip/chest/head/hands/feet On, the rest Off).
    assert vl.control_state({}, "headControl") == ("On", "On")
    assert vl.control_state({}, "neckControl") == ("Off", "Off")
    assert vl.control_state({"hipControl": {"positionState": "Off"}}, "hipControl") == ("Off", "On")
    # A head control in the Off state follows the head bone: exact anchor, and
    # the person's container transform is undone (root moved +1 x, yawed 90).
    posed = {"control": {"position": {"x": "1", "y": "0", "z": "0"},
                         "rotation": {"x": "0", "y": "90", "z": "0"}},
             "headControl": {"positionState": "Off", "rotationState": "Off",
                             "localPosition": {"x": "0", "y": "1.6", "z": "0"},
                             "localRotation": {"x": "0", "y": "0", "z": "0"}}}
    # World head = container * local = (1, 1.6, 0).  Yaw +90 turns +z into +x,
    # so an asset at world x = 0.9 is 10 cm behind the head and must land at
    # z = -0.1 behind the upright person.
    cua = {"position": {"x": "0.9", "y": "1.6", "z": "0"},
           "rotation": {"x": "0", "y": "90", "z": "0"}}
    placed = vl.attachment_rest_transform(rig, "female", posed, "head", cua)
    assert np.allclose(placed[:3, 3], [0, 1.6, -0.1], atol=1e-6), placed[:3, 3]
    assert np.allclose(placed[:3, :3], np.eye(3), atol=1e-6)
    # A head control left On (default) is only a target.  The head bone is
    # where the neck control (Off -> following) plus the saved head rotation
    # put it: neck at world (1, 1.5, 0) yawed 90, head bent 90 about its X.
    posed = {"control": {"position": {"x": "1", "y": "0", "z": "0"},
                         "rotation": {"x": "0", "y": "90", "z": "0"}},
             "neckControl": {"localPosition": {"x": "0", "y": "1.5", "z": "0"},
                             "localRotation": {"x": "0", "y": "0", "z": "0"}},
             "headControl": {"localPosition": {"x": "0.3", "y": "1.9", "z": "0"},
                             "localRotation": {"x": "0", "y": "0", "z": "0"}},
             "head": {"rotation": {"x": "90", "y": "0", "z": "0"}}}
    head = rig.posed_world("head", posed, "female")
    assert np.allclose(head[:3, 3], [1, 1.6, 0], atol=1e-6), head[:3, 3]
    assert np.allclose(head[:3, :3], vl.unity_euler_matrix((90, 90, 0)), atol=1e-6)
    # An asset 5 cm along the bent head's own +y (= world +x) with the head's
    # rotation sits 5 cm above the upright head, unrotated.
    cua = {"position": {"x": "1.05", "y": "1.6", "z": "0"},
           "rotation": {"x": "90", "y": "90", "z": "0"}}
    placed = vl.attachment_rest_transform(rig, "female", posed, "head", cua)
    assert np.allclose(placed[:3, 3], [0, 1.65, 0], atol=1e-6), placed[:3, 3]
    assert np.allclose(placed[:3, :3], np.eye(3), atol=1e-6)
    # Linked to the control node itself it follows that node instead: node at
    # world (1, 1.9, -0.3) yawed 90 -> asset offset (-0.3, -0.3, 0.05) in the
    # node frame, rotation Rx(90) relative to it.
    placed = vl.attachment_rest_transform(rig, "female", posed, "headControl", cua)
    assert np.allclose(placed[:3, 3], [-0.3, 1.3, 0.05], atol=1e-6), placed[:3, 3]
    assert np.allclose(placed[:3, :3], vl.unity_euler_matrix((90, 0, 0)), atol=1e-6)
    # An On head control one bone length (within 3 cm) from the neck was
    # reached: it is the head, whatever the (possibly stale) saved rotation.
    reached = {"control": {},
               "neckControl": {"localPosition": {"x": "0", "y": "1.5", "z": "0"},
                               "localRotation": {"x": "0", "y": "0", "z": "0"}},
               "headControl": {"localPosition": {"x": "0", "y": "1.6", "z": "0.02"},
                               "localRotation": {"x": "0", "y": "45", "z": "0"}},
               "head": {"rotation": {"x": "90", "y": "0", "z": "0"}}}
    head = rig.posed_world("head", reached, "female")
    assert np.allclose(head[:3, 3], [0, 1.6, 0.02], atol=1e-6), head[:3, 3]
    assert np.allclose(head[:3, :3], vl.unity_euler_matrix((0, 45, 0)), atol=1e-6)
    # ... and an all-On chain with no Off control starts from the hip control.
    all_on = {"control": {},
              "hipControl": {"localPosition": {"x": "0.5", "y": "1", "z": "0"},
                             "localRotation": {"x": "0", "y": "0", "z": "0"}},
              "neck": {"rotation": {"x": "0", "y": "0", "z": "90"}}}
    # Rz(90) maps +y to -x: the head sits 10 cm to -x of the neck.
    head = rig.posed_world("head", all_on, "female")
    assert np.allclose(head[:3, 3], [0.4, 1.5, 0], atol=1e-6), head[:3, 3]
    # Root-linked assets just lose the person's own transform.
    moved = {"control": {"position": {"x": "1", "y": "0", "z": "0"}}}
    placed = vl.attachment_rest_transform(rig, "female", moved, "control",
                                          {"position": {"x": "1", "y": "1", "z": "0"}}, 2.0)
    assert np.allclose(placed[:3, 3], [0, 1, 0]) and np.isclose(placed[0, 0], 2.0)


def test_model_bundle(tmp):
    root = build_install(os.path.join(tmp, "game"))
    index = vl.PackageIndex(root)
    pkg = index.by_id["Maker.Pack.2"]
    bundle = vl.ModelBundle(os.path.join(tmp, "out"), "k", "clothing", "Dress")
    first = bundle.add_texture(pkg, "Custom/Clothing/Female/Maker/Dress/tex/Dress.png")
    again = bundle.add_texture(pkg, "custom/clothing/female/maker/dress/tex/dress.png")
    assert first == "Dress.png" and again == first
    other = bundle.add_texture(index.by_id["Look.Scene.3"],
                               "Custom/Atom/Person/Textures/Face.PNG")
    assert other == "Face.png" or other == "Face.PNG", other
    mesh = vl.parse_dazmesh_vab(make_vab()[0])
    faces, loops, mats = vl.clean_polygons(mesh.poly_len, mesh.poly_idx, mesh.uv_poly_idx,
                                           mesh.poly_mat)
    bundle.add_object("Dress", mesh.verts, faces, mesh.uvs[loops], mats,
                      [vl.material_spec("mat-a"), vl.material_spec("mat-b")])
    path = bundle.write()
    payload = json.load(open(path, encoding="utf-8"))
    arrays = np.load(os.path.join(tmp, "out", "model.npz"))
    assert payload["objects"][0]["faces"] == 2 and payload["objects"][0]["vertices"] == 5
    assert arrays["o0_face_len"].tolist() == [4, 3]
    assert arrays["o0_loop_uv"].shape == (7, 2)
    assert arrays["o0_verts"][1].tolist() == [-1.0, 0.0, 0.0]   # mirrored X
    bundle.add_curves("Hair", [np.zeros((3, 3)), np.ones((2, 3))],
                      vl.material_spec("Hair", hair=True), 0.0007)
    bundle.write()
    arrays = np.load(os.path.join(tmp, "out", "model.npz"))
    payload = json.load(open(path, encoding="utf-8"))
    assert payload["objects"][1]["curve"] and payload["objects"][1]["strands"] == 2
    assert arrays["o1_strand_len"].tolist() == [3, 2] and arrays["o1_points"].shape == (5, 3)


def main():
    tmp = tempfile.mkdtemp(prefix="vam_lib_test_")
    try:
        test_json_and_colours()
        test_vab_and_vmb()
        test_hair()
        test_index_and_catalog(build_install(os.path.join(tmp, "install")))
        test_dump_parsers(tmp)
        test_texture_names()
        test_geometry()
        test_transforms_and_rig(tmp)
        test_model_bundle(tmp)
    except AssertionError as exc:
        print("%s=FAIL" % MARKER)
        print(repr(exc))
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("%s=PASS" % MARKER)
    return 0


if __name__ == "__main__":
    sys.exit(main())
