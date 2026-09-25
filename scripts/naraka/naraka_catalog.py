"""What there is to export, from the manifest alone (no bundle is opened).

Groups (all prefabs under assets/res/prefab/):
  outfit        actor_visual_part/<family>/<family>_lv_<skin>.prefab     hero outfits
  hair          actor_visual_part/<family>/*_hair_lv_<skin>.prefab       their hairstyles (named
                after the family, the hero or a short form: ch_f_shenmiao_hair_lv_s0
                lives in ch_f_ming_shenjiying, ch_m_yueshan_hair_* in guanningtieqi)
  outfit_part   other <family>_* prefabs (masks, cn/ext variants, ...)
  default_hair  actor_visual_part/hair_f_default|hair_m_default
  cosmetic      face, eyebrow, eyeshadow, beard, leftcuff
  full_body     actor_visual_part/full_body   (monsters, NPCs: whole models)
  dummy_body    actor_visual_part/ch_dummy_body (bare skeletons + stand-in bodies)
  other_body    remaining actor_visual_part folders (NPC families, events)
  weapon        weapon_prefab/<type>/*.prefab
`_ui` variants (lobby/UI copies of the same model) are listed but hidden by default.

Each outfit family belongs to one hero (FAMILY_HERO).  The six launch heroes'
families are named after their outfit line (mangjianke = Viper Ning, haoxia =
Tarka Ji, ...), which the hero-select icons (icon_hero_<family>_01) and the
effect/material paths that carry both names (fx_ch_f_ming_haikou_lv_s26 under
_fashion/cuisanniang/) give away; later heroes' families carry the hero's name.
"""
import re

VISUAL = "assets/res/prefab/actor_visual_part/"
WEAPON = "assets/res/prefab/weapon_prefab/"
COSMETIC = {"face", "eyebrow", "eyeshadow", "beard", "leftcuff"}


# hero codename (as in gui/art_source/herocareerdata_img) -> Chinese name; None
# where the characters could not be confirmed
HEROES = {
    "ninghongye": "宁红夜", "jianan": "迦南", "temuer": "特木尔", "tianhai": "天海",
    "yaodaoji": "妖刀姬", "hutao": "胡桃", "jicanghai": "季沧海", "cuisanniang": "崔三娘",
    "yueshan": "岳山", "wuchen": "无尘", "guqinghan": "顾清寒", "wutian": "武田信忠",
    "shenmiao": "沈妙", "yinziping": "殷紫萍", "hadi": "哈迪", "huwei": "胡为",
    "yulinglong": "玉玲珑", "jiyingying": "季莹莹", "weiqing": "魏轻", "liulian": "刘炼",
    "zhangqiling": "张起灵", "lixunhuan": "李寻欢", "yexiu": "叶修",
    "nangongjin": None, "wanjun": None, "wuzhen": None, "xila": None, "lanmeng": None, "ganxuan": None,
}
FAMILY_HERO = {
    "ch_f_ming_mangjianke": "ninghongye", "ch_f_hanhaimomin": "jianan", "ch_m_hunni_caoyuan": "temuer",
    "ch_m_ming_youseng": "tianhai", "ch_f_japan_yaodaoji": "yaodaoji", "ch_f_japan_onmyoji": "hutao",
    "ch_m_ming_haoxia": "jicanghai", "ch_f_ming_haikou": "cuisanniang", "ch_m_ming_guanningtieqi": "yueshan",
    "ch_m_ming_wuchen": "wuchen", "ch_f_ming_xiakenv": "guqinghan", "ch_m_japan_samurai": "wutian",
    "ch_f_ming_shenjiying": "shenmiao", "ch_f_ming_yinziping": "yinziping", "ch_m_hadi": "hadi",
    "ch_m_ming_huwei": "huwei", "ch_f_ming_yulinglong": "yulinglong", "ch_f_ming_jiyingying": "jiyingying",
    "ch_f_ming_weiqing": "weiqing", "ch_m_ming_liulian": "liulian", "ch_m_zhangqiling": "zhangqiling",
    "ch_m_lixunhuan": "lixunhuan", "ch_m_yexiu": "yexiu", "ch_f_ming_fengzhao": "nangongjin",
    "ch_m_wanjun": "wanjun", "ch_f_ming_wuzhen": "wuzhen", "ch_f_xila": "xila", "ch_f_lanmeng": "lanmeng",
    "ch_f_jiantianshi": "ganxuan",
}
DEFAULT_HAIR = {"f": "ch_f_hair_02", "m": "ch_m_hair_02"}


def hero_of(family):
    """(codename, Chinese name or None) of an outfit family, or (None, None)."""
    code = FAMILY_HERO.get(family)
    return code, HEROES.get(code) if code else None


def hero_label(family):
    code, zh = hero_of(family)
    if not code:
        return ""
    return "%s %s" % (zh, code) if zh else code


class Item:
    __slots__ = ("name", "path", "bundle", "group", "family", "sex", "skin", "ui")

    def __init__(self, **kw):
        for k in self.__slots__:
            setattr(self, k, kw.get(k))

    def as_dict(self):
        return {k: getattr(self, k) for k in self.__slots__}


def sex_of(name):
    m = re.match(r"(?:ch|hair|mo)_([fm])_", name)
    return m.group(1) if m else None


def build(manifest):
    items = []
    for bundle, assets in manifest.items():
        for path in assets:
            if not path.endswith(".prefab"):
                continue
            name = path.rsplit("/", 1)[-1][:-7]
            ui = name.endswith("_ui") or "_ui_" in name
            if path.startswith(WEAPON):
                items.append(Item(name=name, path=path, bundle=bundle, group="weapon",
                                  family=path[len(WEAPON):].split("/")[0], ui=ui))
                continue
            if not path.startswith(VISUAL):
                continue
            folder = path[len(VISUAL):].split("/")[0]
            kw = dict(name=name, path=path, bundle=bundle, family=folder, sex=sex_of(name) or sex_of(folder), ui=ui)
            if folder in ("hair_f_default", "hair_m_default"):
                items.append(Item(group="default_hair", **kw))
            elif folder in COSMETIC:
                items.append(Item(group="cosmetic", **kw))
            elif folder == "full_body":
                items.append(Item(group="full_body", **kw))
            elif folder == "ch_dummy_body":
                items.append(Item(group="dummy_body", **kw))
            elif folder.startswith("ch_") and "_hair_lv_" in name:
                items.append(Item(group="hair", skin=name.split("_hair_lv_", 1)[1], **kw))
            elif name.startswith(folder + "_lv_"):
                items.append(Item(group="outfit", skin=name[len(folder) + 4:], **kw))
            elif name.startswith(folder + "_") and folder.startswith("ch_"):
                items.append(Item(group="outfit_part", **kw))
            else:
                items.append(Item(group="other_body", **kw))
    items.sort(key=lambda i: (i.group, i.family or "", _natural(i.name)))
    return items


def _natural(text):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text)]


def hair_for(items, outfit):
    """The hairstyle an outfit is shown with: the family's hair of the same skin
    (<..>_hair_lv_<skin>), else the skin with its _NN / _suffix parts dropped one
    at a time (s0_02 -> s0), else the family's basic b0 hair, else its first
    hair, else the default hair of the sex.  Returns (item, how)."""
    hairs = [i for i in items if i.group == "hair" and i.family == outfit.family and not i.ui]
    by_skin = {}
    for h in sorted(hairs, key=lambda i: (not i.name.startswith(outfit.family + "_hair_lv_"), _natural(i.name))):
        by_skin.setdefault(h.skin, h)
    parts = (outfit.skin or "").split("_")
    while parts:
        cand = by_skin.get("_".join(parts))
        if cand is not None:
            return cand, "same skin" if len(parts) == len((outfit.skin or "").split("_")) else "skin prefix"
        parts = parts[:-1]
    if "b0" in by_skin:
        return by_skin["b0"], "family b0"
    if hairs:
        return sorted(hairs, key=lambda i: _natural(i.name))[0], "family first"
    default = DEFAULT_HAIR.get(outfit.sex)
    for i in items:
        if i.name == default:
            return i, "default"
    return None, "none"
