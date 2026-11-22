"""The 48 Eve looks from the 12 Stellar Blade mods in E:\\Downloads\\eve_mod_download (user 11-15: one per distinct
mesh), and since 11-22 the Vindictus mods of the 11-14 survey (Herald of Goddess, Laniakea, Evil maid, Summer vacation).  Each look: label (Eve_Mod_<x> / Eve_Nude_<x>), the work folder under D:\\stellarblade_exports\\mods, the
.pak/.utoc/.ucas folders to stage (relative to <mod>\\unzipped; non-recursive), the mesh's virtual package path, the
archived Eve package it is swapped into, credits.  `needs`: download still missing (look waits)."""

MODS = {
    "NikkePlus": dict(nexus=347, author="DieLayt", title="Nikke Cooling Suit Plus - CNS Compatible",
                      file="1- Nikke Plus - CNS Version AIO 1.03"),
    "AlbionGirls": dict(nexus=4061, author="songeda", title="TFD Albion Girls Nell cns", file="Albion Girls 2"),
    "CakeUnveiledCS": dict(nexus=533, author="briefcasesharpie",
                           title="Cake Unveiled - Cooling Suit with Jacketless and CNS Option (Nikke Alice)",
                           file="All in One - CNS Version 6.0"),
    "YoRHaCeremonial": dict(nexus=550, author="Njaecha (nikojaeger)", title="YoRHa Unofficial Ceremonial Attire - Modular",
                            file="All in One v1.1.0"),
    "BlackSling": dict(nexus=4109, author="EldenEddy", title="Nikke-Cinderella Black Sling Swimsuit (CNS and Replacer)",
                       file="BlackSling 1.0.2 A CNS"),
    "CrimsonWingsBBB": dict(nexus=1933, author="Romaera", title="Crimson Wings Vinyl and Stocking CNS And Replacement",
                            file="Crimson Wings BBB AIO No Panty and Exposed Replace 5.1"),
    "CrimsonWingsOP": dict(nexus=3543, author="KYD88", title="Crimson Wings OP - 16 Color CNS Retexture",
                           file="CrimsonWingsOP 2.0"),
    "SkinSuitUndressed": dict(nexus=3929, author="SweetFluff3D", title="EVE Skin Suit Undressed",
                              file="EVE SkinSuit Undressed Mesh 1.1.0"),
    "EveNudeNatural": dict(nexus=740, author="SweetFluff3D", title="Eve Nude Natural",
                           file="Eve Nude Natural - Skin Suit 1.6 + Textures - Big Areola - Pubs 1.6"),
    "EveOriginalProportions": dict(nexus=30, author="byLemi21", title="Eve with no Clothes on (Original Proportions)",
                                   file="EveOriginalProportions 2.1"),
    "RevealingCrimsonWings": dict(nexus=221, author="Kaineriqa", title="Revealing Crimson Wings",
                                  file="RevealingCrimsonWingsNoPantiesV2 1.5"),
    "YoRHaN2TypeB": dict(nexus=3577, author="DeltaDNova", title="CNS - YoRHa No.2 Type B Uniform - Modular",
                         file="YoRHa N2 TypeB Uniform CNS v1.2.1"),
    # 2026-11-22: the Stellar Blade Vindictus mods of the 11-14 survey (Demon Maiden's outfit alone was done 11-14)
    "VindictusDemonMaiden": dict(nexus=1807, author="AlomX", title="Vindictus - Demon Maiden - CNS Compatible",
                                 file="Vindictus - DemonMaiden - Outfit 1.0 + Hair 1.0"),
    "VindictusLaniakea": dict(nexus=2233, author="AlomX", title="Vindictus - Laniakea Set. Charon's Signature - CNS only",
                              file="Vindictus - Laniakea 1.0"),
    "HeraldOfGoddess": dict(nexus=1670, author="NezYx0", title="EVE - Herald of Goddess",
                            file="(CNS) EVE - Herald of Goddess 1.1.1"),
    "EvilMaid": dict(nexus=1347, author="songeda", title="Evil maid from Vindictus", file="Evil maid 1.2 + Evil maid horn 1.0"),
    "SummerVacation": dict(nexus=1487, author="songeda", title="Summer vacation",
                           file="Summer vacation 1.1 / Summer vacation tits 1.1"),
}

LOOKS = []


def look(label, mod, stage, mesh, base, title, **kw):
    LOOKS.append(dict(label=label, mod=mod, stage=stage, mesh=mesh, base=base, title=title, **kw))


# --- CNS ---------------------------------------------------------------------------------------------------------
NP = [("NikkePlus", "Nikke_Plus_CNS/CustomNanosuitSystem")]
for style, meshes in (("Full", ("Nikke_Full_AssBuff", "Nikke_Full_NoAssBuff", "Nikke_Full_NoEdits")),
                      ("Leotard", ("Nikke_Leotard_AssBuff", "Nikke_Leotard_NoAssBuff", "Nikke_Leotard_NoEdits")),
                      ("Jacketless", ("Nikke_Jacketless_Ass_Buff_Mesh_Merge", "Nikke_Jacketless_No_Ass_Buff",
                                      "Nikke_Jacketless_No_Edits"))):
    for shape, m in zip(("AssBuff", "NoAssBuff", "NoEdits"), meshes):
        look("Eve_Mod_NikkePlus_%s_%s" % (style, shape), "NikkePlus", NP,
             "SB_CNS/Content/OutfitMods/Nikke_Plus/Models/" + m, "CH_P_EVE_Nikke_06",
             "Nikke Plus %s %s" % (style, {"AssBuff": "Ass Buff", "NoAssBuff": "No Ass Buff", "NoEdits": "No Edits"}[shape]))

look("Eve_Mod_AlbionNell", "AlbionGirls", [("AlbionGirls", ".")], "albiongirl/Content/outfitmods/albion/CH_P_EVE_37",
     "CH_P_EVE_37", "TFD Albion Girls (Nell)")

CK = [("CakeUnveiledCS", ".")]
for name, mesh in (("Base", "CH_P_EVE_Nikke_06_Base"), ("Jacketless", "nikke_6_jacketless"),
                   ("OpenFront", "CH_P_EVE_Nikke_06_OpenFront"), ("HighCut_Base", "HighCut_Base"),
                   ("HighCut_Jacketless", "HighCut_Jacketless"), ("HighCut_OpenFront", "HighCut_OpenFront"),
                   ("JacketOnly", "CH_P_EVE_Nikke_06_Jacket_Only"), ("JacketlessPants", "nikke_6_jacketless_pants"),
                   ("ThiccJacketless", "nikke_6_jacketless4_reshape")):
    look("Eve_Mod_CakeCoolingSuit_" + name, "CakeUnveiledCS", CK,
         "CoolingSuit/Content/OutfitMods/Cake_Unveiled_Cooling_Suit/" + mesh, "CH_P_EVE_Nikke_06",
         "Cake Unveiled Cooling Suit - " + name.replace("_", " "), needs=["#1183 All in One for CNS"])

look("Eve_Mod_BlackSling", "BlackSling", [("BlackSling", "SB/Content/Paks/~mods")],
     "SB/Content/OutfitMods/BlackSling/SK_BlackSling", "CH_P_EVE_62", "Black Sling Swimsuit")

OP = [("CrimsonWingsOP", ".")]
for name, h in (("ShortType1", "32314f5b30a1243c"), ("ShortType2", "524467852daaa815"), ("Original", "933956cc72466002"),
                ("Long", "3af3fc378df182c3")):
    look("Eve_Mod_CrimsonWingsOP_" + name, "CrimsonWingsOP", OP,
         "SB/Content/CNSRepacked/%s/Art/Character/PC/CH_P_EVE_OneMillion_01/CH_P_EVE_OneMillion_01" % h,
         "CH_P_EVE_OneMillion_01", "Crimson Wings OP - " + {"ShortType1": "Short Type 1", "ShortType2": "Short Type 2",
                                                            "Original": "Original", "Long": "Long"}[name])

look("Eve_Mod_YoRHaN2TypeB", "YoRHaN2TypeB", [("YoRHaN2TypeB", "YoRHa_N2_TypeB_Uniform_CNS")],
     "SB/Content/OutfitMods/YoRHa_N2_TypeB_Uniform_CNS/SB_YoRHa_N2_TypeB_Modular_CNS", "CH_P_EVE_Nier_01",
     "YoRHa No.2 Type B Uniform", cns_json="YoRHaN2TypeB")

# --- replacers ------------------------------------------------------------------------------------------------------
look("Eve_Mod_YoRHaCeremonial", "YoRHaCeremonial", [("YoRHaCeremonial", ".")],
     "SB/Content/DLC_1/Art/Character/PC/CH_P_EVE_Nier_03/CH_P_EVE_Nier_03", "CH_P_EVE_Nier_03",
     "YoRHa Unofficial Ceremonial Attire")
look("Eve_Mod_RevealingCrimsonWings", "RevealingCrimsonWings", [("RevealingCrimsonWings", ".")],
     "SB/Content/Art/Character/PC/CH_P_EVE_39/CH_P_EVE_39", "CH_P_EVE_OneMillion_01", "Revealing Crimson Wings")
look("Eve_Mod_NudeNatural", "EveNudeNatural",
     [("EveNudeNatural", "Eve Nude Natural - Skin Suit-740-1-6-0-1751728110"),
      ("EveNudeNatural", "Eve Nude Natural Textures - Big Areola - Pubs-740-1-6-0-1751728177")],
     "SB/Content/Art/Character/PC/CH_P_EVE_InnerSuit/CH_P_EVE_InnerSuit", "CH_P_EVE_InnerSuit", "Eve Nude Natural")
look("Eve_Mod_SkinSuitUndressed", "SkinSuitUndressed", [("SkinSuitUndressed", ".")],
     "SB/Content/Art/Character/PC/CH_P_EVE_InnerSuit/CH_P_EVE_InnerSuit", "CH_P_EVE_InnerSuit", "Eve Skin Suit Undressed",
     needs=["#3929 EVE SkinSuit Undressed Textures - Bigger Areola"])
for name, sub in (("Barefoot_Pubic", "Barefoot with Pubic"), ("HighHeels", "High Heels"),
                  ("HighHeels_Pubic", "High Heels with Pubic")):
    look("Eve_Nude_" + name, "EveOriginalProportions", [("EveOriginalProportions", sub)],
         "SB/Content/Art/Character/PC/CH_P_EVE_InnerSuit/CH_P_EVE_InnerSuit", "CH_P_EVE_InnerSuit",
         "Eve Original Proportions - " + sub)

CW = {   # one variant per distinct mesh (16 geometries among the 40 replacers; 11-15 md5 of the PSK points)
    "Exposed_Lux_NoPanty": "Crimson Wings Exposed/Lux_NoPanty/SkinVinyl",
    "Exposed_Panty": "Crimson Wings Exposed/Original Panty&NoPanty/Panty/OriginalSkin",
    "Exposed_NoPanty": "Crimson Wings Exposed/Original Panty&NoPanty/NoPanty/OriginalSkin",
    "LongDress_Vinyl_FullSuit": "Crimson Wings Long Dress No Panty BBB AIO Replacement/LongDressNoPanty_AIO/LongDressNoPanty_SkinVinylFullSuit",
    "LongDress_Vinyl_NoJacket": "Crimson Wings Long Dress No Panty BBB AIO Replacement/LongDressNoPanty_AIO/LongDressNoPanty_SkinVinylNoJacket",
    "LongDress_Vinyl_Sleeveless": "Crimson Wings Long Dress No Panty BBB AIO Replacement/LongDressNoPanty_AIO/LongDressNoPanty_SkinVinylSleeveless",
    "LongDress_FullSuit": "Crimson Wings Long Dress No Panty BBB AIO Replacement/LongDressNoPanty_AIO/__LongDressNoPanty_OriginalFullSuit",
    "LongDress_NoJacket": "Crimson Wings Long Dress No Panty BBB AIO Replacement/LongDressNoPanty_AIO/__LongDressNoPanty_OriginalNoJacket",
    "LongDress_Sleeveless": "Crimson Wings Long Dress No Panty BBB AIO Replacement/LongDressNoPanty_AIO/__LongDressNoPanty_OriginalSleeveless",
    "Nude": "Crimson Wings Nude",
    "ShortDress_Vinyl_FullSuit": "Crimson Wings Short Dress No Panty BBB AIO Replacement/ShortDressNoPanty_SkinVinylFullSuit",
    "ShortDress_Vinyl_NoJacket": "Crimson Wings Short Dress No Panty BBB AIO Replacement/ShortDressNoPanty_SkinVinylNoJacket",
    "ShortDress_Vinyl_Sleeveless": "Crimson Wings Short Dress No Panty BBB AIO Replacement/ShortDressNoPanty_SkinVinylSleeveless",
    "ShortDress_FullSuit": "Crimson Wings Short Dress No Panty BBB AIO Replacement/___ShortDressNoPanty_OriginalFullSuit",
    "ShortDress_NoJacket": "Crimson Wings Short Dress No Panty BBB AIO Replacement/___ShortDressNoPanty_OriginalNoJacket",
    "ShortDress_Sleeveless": "Crimson Wings Short Dress No Panty BBB AIO Replacement/___ShortDressNoPanty_OriginalSleeveless",
}
for name, sub in CW.items():
    look("Eve_Mod_CrimsonWingsBBB_" + name, "CrimsonWingsBBB", [("CrimsonWingsBBB", sub)],
         "CNS_CWings/Content/Art/Character/PC/CH_P_EVE_OneMillion_01/CH_P_EVE_OneMillion_01", "CH_P_EVE_OneMillion_01",
         "Crimson Wings BBB - " + name.replace("_", " "),
         needs=["#1933 Crimson Wings Base Textures For Replacement 5.1"] +
               (["#1933 Crimson Wings Nude and Stocking 5.1"] if name == "Nude" else []))

# --- 2026-11-22: the Vindictus mods (CNS outfits on the plain body package, songeda's replacers on the outfit they
# replace; their mounts are the mod's own name, e.g. evilmaid2337/Content/art/... = /Game/Art/...)
look("Eve_Mod_HeraldOfGoddess", "HeraldOfGoddess", [("HeraldOfGoddess", "~mods/CustomNanosuitSystem")],
     "SB/Content/OutfitMods/Herald_of_Goddess/CH_P_EVE_HOG", "CH_P_EVE_23", "Herald of Goddess", date="2026-11-22")  # 23's skirt bones
look("Eve_Mod_VindictusLaniakea", "VindictusLaniakea", [("VindictusLaniakea", ".")],
     "SB/Content/OutfitMods/VindictusLaniakea/Laniakea", "CH_P_EVE_01_Body", "Vindictus Laniakea",
     hair=dict(mesh="SB/Content/OutfitMods/VindictusLaniakeaHair/Laniakea_hair"), date="2026-11-22",
     # Blender's default (mmd_tools) physics flips the side ponytail over the head at once; MMD's way keeps it down
     preview_args=["--physics", "mmd"])      # its CNS hair (side ponytail)
look("Eve_Mod_EvilMaid", "EvilMaid",
     [("EvilMaid", "Evil maid-1347-1-2-1752854499"), ("EvilMaid", "Evil maid horn-1347-1-0-1752387385")],
     "evilmaid2337/Content/art/character/PC/CH_P_EVE_37/CH_P_EVE_37_TypeB", "CH_P_EVE_37_TypeB", "Evil Maid (Vindictus)",
     # the horns replace the Christmas DLC's sleigh earcuff: a one-bone accessory on SC_Hair (= the head bone)
     acc=[dict(mesh="evilacc/Content/art/character/pc/00_acc/acc_ear_christmas_02/ACC_EAR_Christmas_02",
               name="Eve_Horn_Mesh_01")], date="2026-11-22")
look("Eve_Mod_VindictusDemonMaiden_Hair", "VindictusDemonMaiden",
     [("VindictusDemonMaiden", "Vindictus - DemonMaiden - Outfit-1807-1-0-1754919465"),
      ("VindictusDemonMaiden", "Vindictus - DemonMaiden - Hair-1807-1-0-1754919553")],
     "SB/Content/OutfitMods/VindictusDemonMaidenOutfit/CH_P_EVE_DemonMaiden", "CH_P_EVE_01_Body",
     "Vindictus Demon Maiden (with her hair and horns)",
     hair=dict(mesh="SB/Content/DLC_2/Art/Character/PC/00_HR/EVE_HR_Nikke_03/EVE_HR_Nikke_03"), date="2026-11-22")  # replaces that hair
for name, sub in (("", "Summer vacation-1487-1-1-1752848183"), ("_Tits", "Summer vacation tits-1487-1-1-1752848216")):
    look("Eve_Mod_SummerVacation" + name, "SummerVacation", [("SummerVacation", sub)],
         "summer651/Content/Art/Character/PC/CH_P_EVE_51/CH_P_EVE_51", "CH_P_EVE_51",
         "Summer Vacation" + (" (tits)" if name else ""), date="2026-11-22")

BY_LABEL = {lk["label"]: lk for lk in LOOKS}
assert len(BY_LABEL) == len(LOOKS), len(LOOKS)

# dependency downloads (add_dep.py unpacks them into <work>\<mod>\unzipped\<dep>\): once a mod's dep folders are
# there, its looks stage them too (every folder in them holding a .utoc) and stop waiting
import os as _os  # noqa: E402
from pathlib import Path as _Path  # noqa: E402

_WORK = _Path(r"D:\stellarblade_exports\mods")
DEPS = {"CrimsonWingsBBB": ["_dep_base"], "CakeUnveiledCS": ["_dep_1183"], "SkinSuitUndressed": ["_dep_textures"]}
NUDE_UPDATE = "_dep_nude_update"            # Crimson Wings "Nude and Stocking" 5.1 (the AIO's two are misbuilt)


def _dep_dirs(mod, dep):
    root = _WORK / mod / "unzipped" / dep
    if not root.is_dir():
        return None
    return sorted({str(p.parent.relative_to(_WORK / mod / "unzipped")).replace("\\", "/") for p in root.rglob("*.utoc")})


for _lk in LOOKS:
    _deps = DEPS.get(_lk["mod"])
    if not _deps:
        continue
    _found = [_dep_dirs(_lk["mod"], d) for d in _deps]
    if any(f is None for f in _found):
        continue
    if _lk["label"].endswith("_Nude"):
        # the update has its two triples in ONE folder (Romaera_CW_Nude_1566_P + Romaera_CW_NudeStocking_1566_P), both
        # at the same package path: stage only the non-stocking one, by stem (a folder-wide stage would mount both and
        # CUE4Parse would pick one at random - trap 1)
        _root = _WORK / _lk["mod"] / "unzipped"
        _utocs = sorted((_root / NUDE_UPDATE).rglob("*.utoc")) if (_root / NUDE_UPDATE).is_dir() else []
        _pick = [u for u in _utocs if "stocking" not in u.stem.lower()] or _utocs[:1]
        if not _pick:
            continue
        _lk["stage"] = [(_lk["mod"], str(u.parent.relative_to(_root)).replace("\\", "/"), u.stem) for u in _pick]
    for _f in _found:
        _lk["stage"] = list(_lk["stage"]) + [(_lk["mod"], s) for s in _f]
    _lk.pop("needs", None)
