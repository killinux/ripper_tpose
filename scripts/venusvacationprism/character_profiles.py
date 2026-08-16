"""Verified complete-character profiles for Venus Vacation PRISM.

The game stores a character as separate body/outfit, face, and hair resources.
The filename-hash mapping in :mod:`map_characters` can recover named resources,
but it cannot safely choose every body: several verified bodies have no known
internal basename in the installed name database.  This module is the small,
reviewable registry used by a complete-character exporter.

Resource IDs are integers so callers can compare them directly with RDB
entries.  ``label`` is an actual hashable internal name only when ``kind`` is
``"named"``.  Labels on ``"curated_body"`` entries are stable local aliases and
must never be passed through ``rdb_name_hash``.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping


FULL_SUPPORT = "full"
LEGACY_VERIFIED_SUPPORT = "legacy_verified"
FALLBACK_REQUIRED_SUPPORT = "fallback_required"


@dataclass(frozen=True)
class ComponentProfile:
    """One verified BODY, FACE, or HAIR resource bundle."""

    label: str
    model_index: int
    package_id: int
    g1m: int
    oid: int
    grp: int
    ktid: int
    mtl: int
    texture_slots: int
    kind: str
    internal_name: str | None = None

    @property
    def resource_ids(self) -> Mapping[str, int]:
        return MappingProxyType({
            "g1m": self.g1m,
            "oid": self.oid,
            "grp": self.grp,
            "ktid": self.ktid,
            "mtl": self.mtl,
        })

    @property
    def package_name(self) -> str:
        return f"0x{self.package_id:08x}.fdata"


@dataclass(frozen=True)
class AlphaProfile:
    """Material indices that need portable alpha/iris reconstruction."""

    body: tuple[int, ...]
    face: tuple[int, ...]
    hair: tuple[int, ...]
    face_iris: tuple[int, ...] = (2, 3)
    mode: str = "HASHED"


@dataclass(frozen=True)
class VerificationStatus:
    """What was actually checked in the corresponding formal delivery."""

    source_assets: bool
    material_reconstruction: bool
    blend_roundtrip: bool
    fbx_roundtrip: bool
    visual_review: bool
    glb_roundtrip: bool | None = None
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class RegressionBaseline:
    """Format-independent invariants for automated export regression tests."""

    mesh_objects: int
    armatures: int
    vertices: int
    polygons: int
    materials: int
    blend_used_images: int
    blend_packed_images: int
    output_formats: tuple[str, ...]
    fbx_relink_required: bool = True
    fbx_bounds_tolerance: float | None = None
    glb_readback_vertices: int | None = None
    glb_readback_polygons: int | None = None
    neck_min_distance: float | None = None
    neck_vertices_within_0_001: int | None = None
    body_mesh_objects: int | None = None
    body_skin_linked_meshes: int | None = None
    visual_assertions: tuple[str, ...] = ()


@dataclass(frozen=True)
class CharacterProfile:
    """A complete character selection plus material and QA policies."""

    key: str
    name_en: str
    name_zh: str
    code: str
    aliases: tuple[str, ...]
    components: Mapping[str, ComponentProfile]
    alpha: AlphaProfile
    body_postprocess: Mapping[str, Any]
    face_postprocess: Mapping[str, Any]
    support_level: str
    automated_export_enabled: bool
    limitations: tuple[str, ...]
    verified: VerificationStatus
    expected: RegressionBaseline


def _component(
    label: str,
    model_index: int,
    package_id: int,
    g1m: int,
    oid: int,
    grp: int,
    ktid: int,
    mtl: int,
    texture_slots: int,
    *,
    kind: str = "named",
) -> ComponentProfile:
    return ComponentProfile(
        label=label,
        model_index=model_index,
        package_id=package_id,
        g1m=g1m,
        oid=oid,
        grp=grp,
        ktid=ktid,
        mtl=mtl,
        texture_slots=texture_slots,
        kind=kind,
        internal_name=label if kind == "named" else None,
    )


def _frozen(values: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a read-only policy mapping (all nested collections are tuples)."""

    return MappingProxyType(dict(values))


CHARACTER_PROFILES: Mapping[str, CharacterProfile] = MappingProxyType({
    "misaki": CharacterProfile(
        key="misaki",
        name_en="Misaki",
        name_zh="海咲",
        code="MIS",
        aliases=("misaki", "mis", "海咲"),
        components=MappingProxyType({
            "BODY": _component(
                "COS_MIS_001", 837, 0x8BAAA1CE,
                0xBCEA6C57, 0xAEE4A5D0, 0xC3D9FDD5,
                0x2DEDAD04, 0xBD258495, 11),
            "FACE": _component(
                "FACE_MIS_001", 847, 0x91DDC350,
                0x6ED8E62F, 0x60D31FA8, 0x75C877AD,
                0xB9CE6E2C, 0x6F13FE6D, 69),
            "HAIR": _component(
                "HAIR_MIS_001", 723, 0x2C910555,
                0xA23CFD34, 0x943736AD, 0xA92C8EB2,
                0xF2ED37C7, 0xA2781572, 26),
        }),
        alpha=AlphaProfile(
            body=(),
            face=(1, 4, 5, 6, 8, 9, 10),
            hair=(0, 1, 2, 3),
        ),
        body_postprocess=_frozen({
            "profile": "standard_native_pbr",
            "resolved_texture_slots": 11,
            "unresolved_texture_slots": 0,
            "material_indices": (0,),
            "geometry_transform": "identity",
        }),
        face_postprocess=_frozen({
            "profile": "type43_type44_iris_overlay",
            "iris_material_indices": (2, 3),
            "radial_blend": (0.10, 0.18),
        }),
        support_level=LEGACY_VERIFIED_SUPPORT,
        automated_export_enabled=False,
        limitations=(
            "The verified material/assembly implementation existed as a legacy "
            "one-off workflow and has not yet been promoted to the reusable exporter.",
            "Proprietary type43/type44 iris layers require the recorded overlay "
            "reconstruction; a plain glTF conversion is not visually equivalent.",
        ),
        verified=VerificationStatus(
            source_assets=True,
            material_reconstruction=True,
            blend_roundtrip=True,
            fbx_roundtrip=True,
            visual_review=True,
            evidence=(
                "misaki/complete/Misaki_Complete_report.json",
                "misaki/complete/Misaki_Complete_validation_blend.json",
                "misaki/complete/Misaki_Complete_validation_fbx.json",
            ),
        ),
        expected=RegressionBaseline(
            mesh_objects=54,
            armatures=3,
            vertices=160_036,
            polygons=262_859,
            materials=16,
            blend_used_images=60,
            blend_packed_images=60,
            output_formats=("blend", "fbx"),
            visual_assertions=(
                "iris overlays are visible and not reduced to dark pupil centres",
                "face and hair alpha cards use HASHED blending after FBX relink",
            ),
        ),
    ),
    "elise": CharacterProfile(
        key="elise",
        name_en="Elise",
        name_zh="伊莉丝",
        code="ELS",
        aliases=("elise", "els", "伊莉丝"),
        components=MappingProxyType({
            "BODY": _component(
                "BODY_ELS_DEFAULT_834", 834, 0x8BAAA1CE,
                0xA37B6D08, 0x9575A681, 0xAA6AFE86,
                0x197CC273, 0xA3B68546, 46,
                kind="curated_body"),
            "FACE": _component(
                "FACE_ELS_001", 773, 0x3455A5E5,
                0x44B32DC4, 0x36AD673D, 0x4BA2BF42,
                0x9F3D1937, 0x44EE4602, 69),
            "HAIR": _component(
                "HAIR_ELS_001", 867, 0xCF08E7EA,
                0x781744C9, 0x6A117E42, 0x7F06D647,
                0xD85BE2D2, 0x78525D07, 14),
        }),
        alpha=AlphaProfile(
            body=(),
            face=(1, 4, 5, 6, 8, 9, 10),
            hair=(0, 1),
        ),
        body_postprocess=_frozen({
            "profile": "elise_body834_runtime_fallback",
            "resolved_texture_slots": 22,
            "unresolved_texture_slots": 24,
            "textured_material_indices": (1, 2, 3, 4, 7),
            "solid_runtime_fallback_material_indices": (0, 5, 6),
            "skin_fallback_material_index": 2,
            "skin_fallback_source": "Misaki same-UV skin base and normal",
            "geometry_transform": "identity",
        }),
        face_postprocess=_frozen({
            "profile": "type43_iris_atlas_fit",
            "iris_material_indices": (2, 3),
            "fit_scale": 0.375,
        }),
        support_level=FALLBACK_REQUIRED_SUPPORT,
        automated_export_enabled=False,
        limitations=(
            "BODY834 has 24 runtime KTID handles absent from all 2,412 installed "
            "kidsobjdb files; only 22 of its 46 slots resolve natively.",
            "BODY material 2 uses the documented same-UV Misaki skin fallback, "
            "so the reference delivery is not a fully native source reconstruction.",
            "Raw Blender FBX import is expected to look wrong until the material "
            "relink script restores alpha and normal-map semantics.",
        ),
        verified=VerificationStatus(
            source_assets=True,
            material_reconstruction=True,
            blend_roundtrip=True,
            fbx_roundtrip=True,
            visual_review=True,
            evidence=(
                "elise/complete/Elise_Complete_report.json",
                "elise/complete/README.txt",
            ),
        ),
        expected=RegressionBaseline(
            mesh_objects=71,
            armatures=3,
            vertices=176_094,
            polygons=260_140,
            materials=21,
            blend_used_images=34,
            blend_packed_images=34,
            output_formats=("blend", "fbx"),
            fbx_bounds_tolerance=0.002,
            visual_assertions=(
                "relinked FBX matches the Blend material appearance",
                "iris atlas is fitted at scale 0.375",
                "BODY material 2 uses the declared same-UV skin fallback",
            ),
        ),
    ),
    "honoka": CharacterProfile(
        key="honoka",
        name_en="Honoka",
        name_zh="穗香",
        code="HON",
        aliases=("honoka", "hon", "穗香"),
        components=MappingProxyType({
            "BODY": _component(
                "BODY_HON_HIPHOP_1479", 1479, 0xF1C80847,
                0xA3BDDE26, 0x95B8179F, 0xAAAD6FA4,
                0x21887515, 0xA3F8F664, 48,
                kind="curated_body"),
            "FACE": _component(
                "FACE_HON_001", 824, 0x71FD9D40,
                0x63A9B01F, 0x55A3E998, 0x6A99419D,
                0x5F16E23C, 0x63E4C85D, 69),
            "HAIR": _component(
                "HAIR_HON_001", 117, 0x0CB0DF45,
                0x970DC724, 0x8908009D, 0x9DFD58A2,
                0x9835ABD7, 0x9748DF62, 19),
        }),
        alpha=AlphaProfile(
            body=(2, 4),
            face=(1, 4, 5, 6, 8, 9, 10),
            hair=(0, 1, 2),
        ),
        body_postprocess=_frozen({
            "profile": "honoka_hiphop_native_pbr",
            "resolved_texture_slots": 48,
            "unresolved_texture_slots": 0,
            "selection_evidence": (
                "Honoka skeleton cluster",
                "character-exclusive Hip-Hop Coord visual identity",
            ),
            "rejected_body_indices": (864,),
            "geometry_transform": "identity",
        }),
        face_postprocess=_frozen({
            "profile": "derived_iris_overlay",
            "iris_material_indices": (2, 3),
        }),
        support_level=FULL_SUPPORT,
        automated_export_enabled=True,
        limitations=(
            "BODY_HON_HIPHOP_1479 is a registry alias selected by skeleton and "
            "visual evidence, not a recoverable internal filename.",
            "FBX needs the generated relink sidecar to restore portable alpha and "
            "normal-map semantics in Blender.",
        ),
        verified=VerificationStatus(
            source_assets=True,
            material_reconstruction=True,
            blend_roundtrip=True,
            fbx_roundtrip=True,
            glb_roundtrip=True,
            visual_review=True,
            evidence=(
                "honoka/complete/manifest.json",
                "honoka/complete/Honoka_Complete_report.json",
                "honoka/complete/metadata/qa/Honoka_Independent_Final_QA.json",
                "honoka/complete/Honoka_Complete_Rigged_report.json",
            ),
        ),
        expected=RegressionBaseline(
            mesh_objects=71,
            armatures=3,
            vertices=297_544,
            polygons=420_661,
            materials=24,
            blend_used_images=67,
            blend_packed_images=67,
            output_formats=("blend", "fbx", "glb"),
            fbx_bounds_tolerance=0.002,
            glb_readback_vertices=299_948,
            glb_readback_polygons=420_661,
            neck_min_distance=1.0039092558145057e-05,
            neck_vertices_within_0_001=43,
            visual_assertions=(
                "clear pupils and transparent outer eye layers",
                "no visible neck seam from front or right",
                "Blend and relinked FBX previews match",
            ),
        ),
    ),
    "nanami": CharacterProfile(
        key="nanami",
        name_en="Nanami",
        name_zh="七海",
        code="NNM",
        aliases=("nanami", "nnm", "七海"),
        components=MappingProxyType({
            "BODY": _component(
                "BODY_NANAMI_TRAD_722", 722, 0x26C40D9E,
                0x4A842A7D, 0x3C7E63F6, 0x5173BBFB,
                0x538BB39E, 0x4ABF42BB, 55,
                kind="curated_body"),
            "FACE": _component(
                "FACE_NNM_001", 858, 0xAEF558E6,
                0x4C9271C5, 0x3E8CAB3E, 0x53820343,
                0x93465556, 0x4CCD8A03, 69),
            "HAIR": _component(
                "HAIR_NNM_001", 815, 0x49A89AEB,
                0x7FF688CA, 0x71F0C243, 0x86E61A48,
                0xCC651EF1, 0x8031A108, 21),
        }),
        alpha=AlphaProfile(
            body=(),
            face=(1, 4, 5, 6, 8, 9, 10),
            hair=(0, 1, 2),
        ),
        body_postprocess=_frozen({
            "profile": "nanami_trad_dry_static",
            "resolved_texture_slots": 55,
            "unresolved_texture_slots": 0,
            "selected_render_pass": "unknown1",
            "active_conditional_mesh_indices": (7, 8, 9, 30),
            "common_required_mesh_indices": (23, 24),
            "excluded_runtime_dt2_mesh_indices": (10, 11, 12, 31, 32, 33),
            "dry_multi_material_indices": (4, 11),
            "excluded_runtime_wet_material_indices": (5, 12, 13),
            "cloth_uv_set": 1,
            "base_color_slots": (21, 22),
            "slot22_overlay_factor": 0.054318,
            "normal_slot": 23,
            "normal_strength": 0.15,
            "repair_cloth_normals_and_tangents": True,
            "rejected_body_indices": (830,),
            "geometry_transform": "identity",
        }),
        face_postprocess=_frozen({
            "profile": "derived_iris_overlay",
            "iris_material_indices": (2, 3),
        }),
        support_level=FULL_SUPPORT,
        automated_export_enabled=True,
        limitations=(
            "The portable default intentionally flattens the dry unknown1 pass; "
            "wet/DT2 runtime passes remain only in the preserved source resources.",
            "BODY_NANAMI_TRAD_722 is a registry alias and must be selected by its "
            "recorded model index/resource IDs rather than filename hashing.",
            "FBX needs the generated relink sidecar to restore alpha and normals.",
        ),
        verified=VerificationStatus(
            source_assets=True,
            material_reconstruction=True,
            blend_roundtrip=True,
            fbx_roundtrip=True,
            glb_roundtrip=True,
            visual_review=True,
            evidence=(
                "nanami/complete/SHA256_MANIFEST.json",
                "nanami/complete/reports/qa/delivery_validation.json",
                "nanami/complete/reports/qa/final_dynamic_qa.json",
            ),
        ),
        expected=RegressionBaseline(
            mesh_objects=75,
            armatures=4,
            vertices=230_539,
            polygons=352_425,
            materials=28,
            blend_used_images=72,
            blend_packed_images=72,
            output_formats=("blend", "fbx", "glb"),
            fbx_bounds_tolerance=0.002,
            glb_readback_vertices=231_023,
            glb_readback_polygons=352_425,
            neck_min_distance=1.0969845789077226e-05,
            neck_vertices_within_0_001=43,
            visual_assertions=(
                "no chest rectangle",
                "no black/white pull artifact",
                "no triangle normal mosaic",
                "no visible neck seam",
            ),
        ),
    ),
    "fiona": CharacterProfile(
        key="fiona",
        name_en="Fiona",
        name_zh="菲欧娜",
        code="FON",
        aliases=("fiona", "fon", "菲欧娜"),
        components=MappingProxyType({
            "BODY": _component(
                "BODY_FON_CLASSICAL_LOLITA_857", 857, 0xAB6B8248,
                0x1257E927, 0x045222A0, 0x19477AA5,
                0x862FCA34, 0x12930165, 54,
                kind="curated_body"),
            "FACE": _component(
                "FACE_FON_001", 1125, 0xDD9A6ABE,
                0xAFF2DB9D, 0xA1ED1516, 0xB6E26D1B,
                0x9BF3267E, 0xB02DF3DB, 69),
            "HAIR": _component(
                "HAIR_FON_001", 828, 0x784DACC3,
                0xE356F2A2, 0xD5512C1B, 0xEA468420,
                0xD511F019, 0xE3920AE0, 14),
        }),
        alpha=AlphaProfile(
            body=(0, 1, 2, 3, 6, 7, 8, 11),
            face=(1, 4, 5, 6, 8, 9, 10),
            hair=(0, 1),
        ),
        body_postprocess=_frozen({
            "profile": "fiona_classical_lolita_native_pbr",
            "resolved_texture_slots": 54,
            "unresolved_texture_slots": 0,
            "selection_evidence": (
                "Fiona-exclusive Classical Lolita visual identity",
                "FACE_FON_001 and HAIR_FON_001 zero-transform head fit",
            ),
            "rejected_face_indices": (860,),
            "geometry_transform": "identity",
            "skin_linked_meshes_after_conversion": 32,
            "static_nun_mesh_indices": (5, 6, 8, 9, 10, 11, 17, 18),
            "static_nun_vertex_count": 12_813,
            "game_cloth_simulation_reproduced": False,
        }),
        face_postprocess=_frozen({
            "profile": "derived_iris_overlay",
            "iris_material_indices": (2, 3),
        }),
        support_level=FULL_SUPPORT,
        automated_export_enabled=True,
        limitations=(
            "The high collar hides a non-welded FACE001/BODY857 interface; "
            "the verified front, side, and back views show no visible gap.",
            "FACE_FON_000 is deliberately rejected: despite its closer neck-ring "
            "distance, it sits about 4.41 units too high for every Fiona hairstyle.",
            "Eight BODY NUN cloth meshes (12,813 vertices) are complete in bind "
            "pose but static/unbound converter output; 32 of 40 BODY meshes are "
            "skin-linked, and game-time cloth simulation is not reproduced.",
            "FBX needs the generated relink sidecar to restore alpha and normals.",
        ),
        verified=VerificationStatus(
            source_assets=True,
            material_reconstruction=True,
            blend_roundtrip=True,
            fbx_roundtrip=True,
            glb_roundtrip=True,
            visual_review=True,
            evidence=(
                "fiona/complete/SHA256SUMS.txt",
                "fiona/complete/validation/Fiona_Complete_Rigged_report.json",
                "fiona/complete/validation/Fiona_delivery_manifest.json",
            ),
        ),
        expected=RegressionBaseline(
            mesh_objects=78,
            armatures=3,
            vertices=281_364,
            polygons=428_599,
            materials=25,
            blend_used_images=65,
            blend_packed_images=65,
            output_formats=("blend", "fbx", "glb"),
            fbx_bounds_tolerance=0.002,
            glb_readback_vertices=283_178,
            glb_readback_polygons=428_599,
            body_mesh_objects=40,
            body_skin_linked_meshes=32,
            visual_assertions=(
                "FACE001 eyes and hairline align at identity",
                "high collar hides the non-welded neck interface",
                "clear pupils and transparent hair/eye layers",
                "Blend and relinked FBX previews match",
            ),
        ),
    ),
    "tamaki": CharacterProfile(
        key="tamaki",
        name_en="Tamaki",
        name_zh="环",
        code="TAM",
        aliases=("tamaki", "tam", "环", "たまき"),
        components=MappingProxyType({
            "BODY": _component(
                "BODY_TAM_SKINNY_DENIM_842", 842, 0x8BAAA1CE,
                0x50A25411, 0x429C8D8A, 0x5791E58F,
                0x1132BC8A, 0x50DD6C4F, 33,
                kind="curated_body"),
            "FACE": _component(
                "FACE_TAM_001", 850, 0xA00AAF19,
                0xF34EAAF8, 0xE548E471, 0xFA3E3C76,
                0xC4114283, 0xF389C336, 69),
            "HAIR": _component(
                "HAIR_TAM_001", 813, 0x3ABDF11E,
                0x26B2C1FD, 0x18ACFB76, 0x2DA2537B,
                0xFD300C1E, 0x26EDDA3B, 14),
        }),
        alpha=AlphaProfile(
            body=(),
            face=(1, 4, 5, 6, 8, 9, 10),
            hair=(0, 1),
        ),
        body_postprocess=_frozen({
            "profile": "tamaki_skinny_denim_static",
            "resolved_texture_slots": 30,
            "unresolved_texture_slots": 3,
            "unresolved_texture_slot_indices": (26, 27, 32),
            "unresolved_texture_handles": (
                0xDFD76BBB, 0xA026470E, 0xFF848649),
            "unresolved_texture_g1t_ids": (
                0x3828E790, 0x73FA791D, 0xB8ABCFC2),
            "unresolved_texture_policy": "prune_if_unreferenced",
            "static_cloth_meshes": (11,),
            "static_cloth_vertex_counts": (3_101,),
            "static_cloth_materials": (1,),
            "static_cloth_invalid_joint_slots": (6, 7),
            "static_cloth_invalid_nonzero_lanes": 160,
            "selection_evidence": (
                "Tamaki-exclusive Skinny Denim visual identity",
                "BODY842/FACE_TAM_001 skeleton and neck fit",
            ),
            "geometry_transform": "identity",
        }),
        face_postprocess=_frozen({
            "profile": "derived_iris_overlay",
            "iris_material_indices": (2, 3),
        }),
        support_level=FULL_SUPPORT,
        automated_export_enabled=True,
        limitations=(
            "BODY texture slots 26, 27, and 32 map through OBJDB but their G1T "
            "assets are absent from this installation; they are proven unused by "
            "portable material semantics and are pruned without fabricated images.",
            "The 3,101-vertex left trouser NUN panel is complete in bind pose but "
            "remains static because its physics driver indices are not skeletal "
            "joint weights. It is the only mesh newly detached by this fallback; "
            "25 of 32 BODY meshes are skin-linked after conversion, while meshes "
            "19 through 24 were already static/unbound converter output.",
            "FBX needs the generated relink sidecar to restore alpha and normals.",
        ),
        verified=VerificationStatus(
            source_assets=True,
            material_reconstruction=True,
            blend_roundtrip=True,
            fbx_roundtrip=True,
            glb_roundtrip=True,
            visual_review=True,
            evidence=(
                "tamaki/complete/SHA256SUMS.txt",
                "tamaki/complete/validation/Tamaki_Complete_Rigged_report.json",
                "tamaki/complete/components/body/cloth_static_fallback_report.json",
                "tamaki/complete/validation/Tamaki_delivery_manifest.json",
            ),
        ),
        expected=RegressionBaseline(
            mesh_objects=78,
            armatures=3,
            vertices=358_368,
            polygons=468_659,
            materials=22,
            blend_used_images=60,
            blend_packed_images=60,
            output_formats=("blend", "fbx", "glb"),
            fbx_bounds_tolerance=0.002,
            glb_readback_vertices=362_419,
            glb_readback_polygons=468_659,
            neck_min_distance=1.95241373148747e-05,
            neck_vertices_within_0_001=43,
            body_mesh_objects=32,
            body_skin_linked_meshes=25,
            visual_assertions=(
                "no visible neck seam",
                "clear pupils and transparent hair/eye layers",
                "skinny-denim cloth geometry is complete in bind pose",
                "Blend and relinked FBX previews match",
            ),
        ),
    ),
})


def _normalize_alias(value: str) -> str:
    return "".join(
        character for character in value.strip().casefold()
        if character not in " _-"
    )


def _build_alias_index() -> Mapping[str, str]:
    result: dict[str, str] = {}
    for key, profile in CHARACTER_PROFILES.items():
        candidates = (
            key,
            profile.name_en,
            profile.name_zh,
            profile.code,
            *profile.aliases,
        )
        for candidate in candidates:
            normalized = _normalize_alias(candidate)
            previous = result.setdefault(normalized, key)
            if previous != key:
                raise RuntimeError(
                    f"Character alias {candidate!r} is shared by {previous!r} and {key!r}")
    return MappingProxyType(result)


CHARACTER_ALIASES: Mapping[str, str] = _build_alias_index()


def resolve_character_key(name: str) -> str:
    """Return the canonical profile key for an English/Chinese name or code."""

    normalized = _normalize_alias(name)
    try:
        return CHARACTER_ALIASES[normalized]
    except KeyError as exc:
        valid = ", ".join(profile.name_en for profile in CHARACTER_PROFILES.values())
        raise KeyError(f"Unknown character {name!r}; verified profiles: {valid}") from exc


def get_character_profile(name: str) -> CharacterProfile:
    """Resolve ``name`` and return its verified complete-character profile."""

    return CHARACTER_PROFILES[resolve_character_key(name)]


def enabled_character_profiles() -> tuple[CharacterProfile, ...]:
    """Return profiles currently safe to expose as fully automated exports."""

    return tuple(
        profile for profile in CHARACTER_PROFILES.values()
        if profile.automated_export_enabled
    )
