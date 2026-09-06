"""Synthetic regression for vam_duf.py, the Blender -> VaM (DSON) writer.

Pure Python + numpy.  Every fixture is built in memory, except the last test,
which checks the writer's coordinate constant against real data when the VaM
install is present (a package that ships the creator's own .duf next to the
.vab VaM produced from it) and skips otherwise.

Covers:
  * the measured coordinate maps and their inverses, and that going through
    Blender agrees with vam_lib's own basis
  * winding survives Blender -> DAZ (the two mirrors cancel)
  * per-vertex UVs, and seam UVs split into defaults + polygon_vertex_indices
  * quads stay quads, n-gons and out-of-range indices are refused
  * build_duf reference integrity, and that check_duf catches a dangling url
  * gzip and plain round trip
  * morph .dsf: delta conversion, Genesis 2 vertex guard, gender parent

Usage:
  python test_vam_duf.py          -> prints VAM_DUF_TEST=PASS
"""

import glob
import os
import shutil
import sys
import tempfile
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import vam_duf as vd  # noqa: E402
import vam_lib as vl  # noqa: E402

MARKER = "VAM_DUF_TEST"

VAM_INSTALL = r"E:\tools\vam\vam1.22\vam1.22\1.22"
# The one package that shipped its DUF source next to the item it produced.
SAMPLE_PACKAGE = "VL_13.Lashes_2.1.var"
SAMPLE_DUF = "Custom/Hair/Female/VL_13/Lashes_2.0/Lashes_Skin_subd.duf"
SAMPLE_VAB = "Custom/Hair/Female/VL_13/Lashes_2.0/Lashes_Lid_upp.vab"


def cube(space="blender"):
    """Unit cube with outward-facing quads, in metres."""
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64)
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
             [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    return vd.DufMesh("cube", verts, faces, space=space)


def outward_fraction(verts, faces):
    verts = np.asarray(verts, dtype=np.float64)
    centre = verts.mean(axis=0)
    out = 0
    for face in faces:
        a, b, c = verts[face[0]], verts[face[1]], verts[face[2]]
        normal = np.cross(b - a, c - a)
        if np.dot(normal, verts[face].mean(axis=0) - centre) > 0:
            out += 1
    return out / float(len(faces))


def test_coordinates():
    vam = np.array([[0.3, 1.6, 0.07], [-0.5, 0.0, -1.25]])
    daz = vd.vam_to_daz(vam)
    assert np.allclose(daz, [[-30.0, 160.0, 7.0], [50.0, 0.0, -125.0]]), daz
    assert np.allclose(vd.daz_to_vam(daz), vam)

    # Going VaM -> Blender -> DAZ must land on the same place as VaM -> DAZ.
    through_blender = vd.blender_to_daz(vl.to_blender(vam))
    assert np.allclose(through_blender, daz, atol=1e-5), through_blender
    assert np.allclose(vd.daz_to_blender(daz), vl.to_blender(vam), atol=1e-6)

    # A metre of VaM is a hundred DAZ units and nothing is reordered.
    assert vd.DAZ_SCALE == 100.0
    assert np.allclose(vd.vam_to_daz([[1, 2, 3]]), [[-100, 200, 300]])


def test_winding():
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                      [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1]], dtype=np.float64)
    faces = [[0, 3, 2, 1], [4, 5, 6, 7], [0, 1, 5, 4],
             [1, 2, 6, 5], [2, 3, 7, 6], [3, 0, 4, 7]]
    assert outward_fraction(verts, faces) == 1.0, "fixture is not outward-facing"
    # Blender -> DAZ is a rotation, so a Blender-outward mesh stays outward
    # (DAZ authors counter-clockwise from outside, same as Blender).
    assert outward_fraction(vd.blender_to_daz(verts), faces) == 1.0
    # VaM -> DAZ is the mirror, which is exactly why VaM's own meshes read as
    # clockwise from outside.
    assert outward_fraction(vd.vam_to_daz(verts), faces) == 0.0


def test_mesh_and_uvs():
    mesh = cube()
    assert mesh.uvs is None and mesh.uv_pairs == []
    geom = mesh.geometry("cube-1")
    assert geom["vertices"]["count"] == 8 and geom["polylist"]["count"] == 6
    # polylist rows are [face group, material group, v0, v1, v2, (v3)]
    assert geom["polylist"]["values"][0] == [0, 0, 0, 3, 2, 1]
    assert geom["polygon_material_groups"]["values"] == ["default"]

    # Per-vertex UVs need no polygon_vertex_indices.
    uvs = np.linspace(0, 1, 16).reshape(8, 2)
    plain = vd.DufMesh("plain", cube().verts, [f for f in geom_faces(geom)],
                       uvs=uvs, space="daz")
    assert plain.uv_pairs == [] and len(plain.uvs) == 8
    assert plain.uv_set()["vertex_count"] == 8

    # A seam: two faces disagree about the UV of vertex 1.
    faces = [[0, 1, 2], [1, 3, 2]]
    verts = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0]], dtype=np.float64)
    corner_uvs = np.array([[0, 0], [1, 0], [0, 1], [1, 1], [0.25, 0.75]])
    uv_faces = [[0, 1, 2], [4, 3, 2]]          # second face uses uv 4 for vertex 1
    seam = vd.DufMesh("seam", verts, faces, uvs=corner_uvs, uv_faces=uv_faces, space="daz")
    assert len(seam.uvs) == 5, seam.uvs           # 4 defaults + 1 duplicate
    assert seam.uv_pairs == [[1, 1, 4]], seam.uv_pairs
    assert np.allclose(seam.uvs[4], [0.25, 0.75])
    uv_set = seam.uv_set()
    assert uv_set["vertex_count"] == 4 and uv_set["uvs"]["count"] == 5

    # DSON has no n-gons and no dangling indices.
    for bad, why in (([[0, 1, 2, 3, 0]], "n-gon"), ([[0, 1, 9]], "index")):
        try:
            vd.DufMesh("bad", verts, bad, space="daz")
        except AssertionError:
            pass
        else:
            raise AssertionError("accepted a bad face (%s)" % why)


def geom_faces(geom):
    return [poly[2:] for poly in geom["polylist"]["values"]]


def test_materials_and_document():
    verts = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float64)
    mesh = vd.DufMesh("shirt", verts, [[0, 1, 2], [0, 2, 3]],
                      uvs=np.zeros((4, 2)), face_materials=[0, 1],
                      material_names=["body", "trim"], space="blender")
    doc = vd.build_duf(mesh)
    assert vd.check_duf(doc) == [] or all("no UVs" not in w for w in vd.check_duf(doc))
    assert [m["id"] for m in doc["material_library"]] == ["shirt_body", "shirt_trim"]
    assert [m["groups"] for m in doc["scene"]["materials"]] == [["body"], ["trim"]]
    # every scene reference resolves locally, nothing points at the DAZ library
    assert doc["scene"]["nodes"][0]["url"] == "#shirt"
    assert doc["scene"]["materials"][0]["geometry"] == "#shirt-3"
    assert doc["asset_info"]["type"] == "scene_subset"
    assert doc["file_version"] == vd.FILE_VERSION

    # two meshes in one file keep their own ids
    other = vd.DufMesh("hat", verts, [[0, 1, 2]], space="blender")
    two = vd.build_duf([mesh, other])
    assert len(two["geometry_library"]) == 2 and len(two["node_library"]) == 2
    vd.check_duf(two)

    # check_duf is the thing that catches what VaM would report as
    # "Could not find geometry" once the file is already in the importer.
    broken = vd.build_duf(mesh)
    broken["scene"]["materials"][0]["geometry"] = "#nope"
    try:
        vd.check_duf(broken)
    except AssertionError:
        pass
    else:
        raise AssertionError("check_duf missed a dangling geometry url")

    big = vd.build_duf(mesh)
    big["geometry_library"][0]["vertices"]["count"] = 60000
    big["geometry_library"][0]["vertices"]["values"] = [[0, 0, 0]] * 60000
    big["geometry_library"][0]["polylist"]["values"] = [[0, 0, 0, 1, 2]]
    big["geometry_library"][0]["polylist"]["count"] = 1
    warnings = vd.check_duf(big)
    assert any("decimating" in w for w in warnings), warnings


def test_write_and_read(tmp):
    mesh = cube()
    doc = vd.build_duf(mesh, asset_id="/test.duf")
    gz = vd.write_dson(os.path.join(tmp, "a.duf"), doc)
    plain = vd.write_dson(os.path.join(tmp, "b.duf"), doc, compress=False)
    assert open(gz, "rb").read(2) == b"\x1f\x8b", "default must be gzipped like DAZ's own"
    assert open(plain, "rb").read(1) == b"{"
    for path in (gz, plain):
        back = vd.read_dson(path)
        assert back["geometry_library"][0]["polylist"]["values"][0] == [0, 0, 0, 3, 2, 1]
        vd.check_duf(back)
    # nested directories are created
    nested = vd.write_dson(os.path.join(tmp, "deep", "c.duf"), doc)
    assert os.path.isfile(nested)


def test_morph(tmp):
    deltas = {0: (0.001, 0.0, 0.0), 5: (0.0, -0.002, 0.0)}
    doc = vd.build_morph_dsf("Belly Out", deltas, gender="female",
                             group="/Morphs/ripper", label="Belly Out")
    mod = doc["modifier_library"][0]
    assert mod["parent"].endswith("Genesis2Female.dsf#GenesisFemale-1")
    assert mod["morph"]["vertex_count"] == 21556
    assert mod["morph"]["deltas"]["count"] == 2
    # 1 mm along Blender +X is 0.1 cm along DAZ +X; Blender +Y is DAZ -Z.
    assert mod["morph"]["deltas"]["values"][0] == [0, 0.1, 0.0, -0.0]
    assert mod["morph"]["deltas"]["values"][1] == [5, 0.0, 0.0, 0.2]
    assert doc["scene"]["modifiers"][0]["url"] == "#Belly Out"

    male = vd.build_morph_dsf("Chest", {1: (0, 0, 0.01)}, gender="male")
    assert male["modifier_library"][0]["parent"].endswith("Genesis2Male.dsf#Genesis2Male")

    array = vd.build_morph_dsf("Arr", np.array([[3, 0.01, 0, 0]]), space="vam")
    assert array["modifier_library"][0]["morph"]["deltas"]["values"][0] == [3, -1.0, 0.0, 0.0]

    for bad in ({}, {vd.GENESIS2_VERTS: (0, 0, 0)}):
        try:
            vd.build_morph_dsf("Bad", bad)
        except AssertionError:
            pass
        else:
            raise AssertionError("accepted bad deltas %r" % (bad,))

    path = vd.write_dson(os.path.join(tmp, "m.dsf"), doc)
    assert vd.read_dson(path)["modifier_library"][0]["id"] == "Belly Out"


def test_against_real_pair():
    """VaM's own numbers: a DUF the creator imported and the .vab it produced."""
    matches = glob.glob(os.path.join(VAM_INSTALL, "AddonPackages", "**", SAMPLE_PACKAGE),
                        recursive=True)
    if not matches:
        return "skipped (no VaM install)"
    with zipfile.ZipFile(matches[0]) as package:
        tmp = tempfile.mkdtemp(prefix="vam_duf_sample_")
        try:
            duf_path = os.path.join(tmp, "sample.duf")
            with open(duf_path, "wb") as fh:
                fh.write(package.read(SAMPLE_DUF))
            doc = vd.read_dson(duf_path)
            mesh = vl.parse_dazmesh_vab(package.read(SAMPLE_VAB))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    # our validator must accept a file VaM itself accepted
    vd.check_duf(doc)
    geom = doc["geometry_library"][0]
    duf_verts = np.asarray(geom["vertices"]["values"], dtype=np.float64)
    vab_verts = np.asarray(mesh.verts, dtype=np.float64)
    assert len(duf_verts) == len(vab_verts) == 392, len(duf_verts)
    error = np.abs(vd.daz_to_vam(duf_verts) - vab_verts).max()
    assert error < 1e-6, "coordinate map drifted: max error %g" % error
    # polygons come through untouched, quads included
    assert [poly[2:] for poly in geom["polylist"]["values"][:2]] == \
        [list(mesh.poly_idx[:4]), list(mesh.poly_idx[4:8])]
    assert set(mesh.poly_len.tolist()) == {4}
    return "checked against %s" % SAMPLE_PACKAGE


def main():
    tmp = tempfile.mkdtemp(prefix="vam_duf_test_")
    note = ""
    try:
        test_coordinates()
        test_winding()
        test_mesh_and_uvs()
        test_materials_and_document()
        test_write_and_read(tmp)
        test_morph(tmp)
        note = test_against_real_pair()
    except AssertionError as exc:
        print("%s=FAIL" % MARKER)
        print(repr(exc))
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("%s=PASS %s" % (MARKER, note))
    return 0


if __name__ == "__main__":
    sys.exit(main())
