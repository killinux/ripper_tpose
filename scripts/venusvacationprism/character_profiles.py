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
