"""The game's background pictures -> one folder.

    python export_backgrounds.py              the picked set (128 pictures) -> <export-root>\\_backgrounds\\
    python export_backgrounds.py --list       the picks: file name <- catalog address
    python export_backgrounds.py --all        also every picture of the background folders -> _backgrounds\\全部\\<类别>\\
    python export_backgrounds.py --force      write the files that are there again

What the game keeps as 2D pictures (catalog.json; the 3D battle stages are another matter, see the README):

    剧情   Story/BG/                 55 visual-novel backgrounds (E001..E006 2048 px, S002..S027 1024 px) - all taken
    过场   Prologue_Epilogue/        the layers of the comic-like chapter openings / endings; only the full,
                                     opaque paintings without figures are picked (50 of 335 layers)
    界面   UI/BackGround/            menu backdrops; stored square (2048 x 2048) and shown 16:9 -> written 2048 x 1152;
                                     most are dimmed and blurred on purpose, the two sharp ones are picked
    抽卡   Icon/Portal/, Director/GachaIntro/   the recruit screens' backdrops
    天空   Effect/EP1_FX_Resources/Textures/Background/   painted skies of skill effects (small, 512 - 1024 px)
    全景   sky cubemaps of the stages (BackGround/.../*.png as Cubemap, six 1024 px faces) -> one 4096 x 2048
           equirectangular panorama each: an Environment Texture for Blender's world, or a 360 degree picture

The file name is  <类别>_<the game's own name>_<what it shows>.png ; next to the pictures: _总览_<类别>_<n>.jpg
(contact sheets) and, in <export-root>\\_meta\\backgrounds.json, which catalog address each file came from.
Pictures are the game's art: they go to the export root, never into the repository.
"""
from __future__ import annotations

import argparse
import math
import os
import re
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import tsquad_common as tc  # noqa: E402

log = tc.log
OUT_NAME = "_backgrounds"
PANORAMA_WIDTH = 4096
SQUASHED = ("界面",)                       # stored square, shown 16:9
CATEGORIES = ("剧情", "过场", "界面", "抽卡", "天空", "全景")
SHEET_FONT = r"C:\Windows\Fonts\msyh.ttc"

# Story/BG/<name>.png - every one of them, with what it shows
STORY = {
    "E001": "花园拱门", "E002": "日式老街", "E003": "海滩", "E004": "山坡草地", "E005": "教室_黄昏",
    "E006": "白色舱室大厅", "S002_A": "小巷_夜", "S002_B": "高楼街道_夜", "S002_C": "楼顶停机坪_夜",
    "S003": "高层公寓", "S004_A": "道场", "S004_B": "群山", "S005_A": "客厅", "S005_B": "黄金神殿",
    "S006_A": "乡间住宅", "S006_B": "和室", "S008_A": "办公室", "S008_B": "楼群_月夜", "S009_A": "赌场",
    "S009_B": "废弃走廊", "S011": "和室_刀架", "S012_A": "教室", "S012_B": "学校走廊", "S013": "研究所_暗",
    "S014": "研究所", "S015": "欧式小镇_夜", "S016": "圆形竞技场", "S017": "人工岛_夜_鸟瞰",
    "S018_A": "霓虹商店街", "S018_B": "夜店舞台", "S018_C": "红色峡谷", "S018_D": "麦田", "S018_E": "雪山极光",
    "S019_A": "日式街道_秋", "S019_B": "酒店大堂", "S019_C": "竹林", "S019_D": "红叶寺院", "S019_E": "和室_茶几",
    "S019_F": "日式街道", "S020": "霓虹街_夜", "S021_A": "木廊_星空", "S021_B": "森林瀑布_夜",
    "S021_C": "竹篱_星空", "S021_D": "露天温泉_夜", "S022_A": "学校外景", "S022_B": "商店街", "S022_C": "咖啡店",
    "S022_D": "玩偶店", "S022_E": "电车车厢", "S023": "运河_夜", "S024": "石砖广场_夜", "S025_A": "密室会议室",
    "S025_B": "聚光灯竞技场", "S026": "拉面店", "S027": "图书馆",
}
PICKS = [("剧情", "Story/BG/%s.png" % name, label) for name, label in STORY.items()] + [
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_ep/texture/ep_02.png", "月下火海"),
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_ep/texture/ep_05.png", "大桥路面_夜"),
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_pl/texture/pl_02_1.png", "大桥夜景"),
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_pl/texture/pl_02_2.png", "大桥起火"),
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_pl/texture/pl_03_1.png", "霓虹都市_月夜"),
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_pl/texture/pl_03_2.png", "都市起火"),
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_pl/texture/pl_05_sky.png", "月夜云层"),
    ("过场", "Prologue_Epilogue/ep_01/Episode1_1_pl/texture/pl_06_sky.png", "火烧云"),
    ("过场", "Prologue_Epilogue/ep_02/Episode1_2_ep/texture/ep_01.png", "洞穴光柱"),
    ("过场", "Prologue_Epilogue/ep_02/Episode1_2_ep/texture/ep_02.png", "废弃隧道_暖光"),
    ("过场", "Prologue_Epilogue/ep_02/Episode1_2_ep/texture/ep_03.png", "夜晚街道_车流"),
    ("过场", "Prologue_Epilogue/ep_02/Episode1_2_pl/texture/pl_01.png", "都市街道_白天"),
    ("过场", "Prologue_Epilogue/ep_02/Episode1_2_pl/texture/pl_02.png", "学校远景"),
    ("过场", "Prologue_Epilogue/ep_02/Episode1_2_pl/texture/pl_03.png", "紫色魔法门"),
    ("过场", "Prologue_Epilogue/ep_03/Episode1_3_ep/texture/ep2_sky.png", "蓝色漩涡云"),
    ("过场", "Prologue_Epilogue/ep_03/Episode1_3_ep/texture/ep_01.png", "废墟街道_夜"),
    ("过场", "Prologue_Epilogue/ep_03/Episode1_3_pl/texture/pl_01.png", "海岸公路_夜"),
    ("过场", "Prologue_Epilogue/ep_03/Episode1_3_pl/texture/pl_03.png", "燃烧的公路"),
    ("过场", "Prologue_Epilogue/ep_04/Episode1_4_pl/texture/pl_01.png", "火海都市_蓝月"),
    ("过场", "Prologue_Epilogue/ep_04/Episode1_4_pl/texture/pl_02.png", "高塔_夜"),
    ("过场", "Prologue_Epilogue/ep_05/Episode1_5_ep/texture/ep_02.png", "林间溪流_月夜"),
    ("过场", "Prologue_Epilogue/ep_05/Episode1_5_pl/texture/pl_02.png", "都市俯瞰_红光"),
    ("过场", "Prologue_Epilogue/ep_06/Episode1_6_ep/texture/ep_01.png", "数据中心"),
    ("过场", "Prologue_Epilogue/ep_06/Episode1_6_pl/texture/pl_01.png", "郊外公路_月夜"),
    ("过场", "Prologue_Epilogue/ep_06/Episode1_6_pl/texture/pl_02.png", "工厂内部"),
    ("过场", "Prologue_Epilogue/ep_06/Episode1_6_pl/texture/pl_03.png", "工厂光柱"),
    ("过场", "Prologue_Epilogue/ep_07/Episode1_7_ep/texture/ep_03.png", "港口夜色"),
    ("过场", "Prologue_Epilogue/ep_07/Episode1_7_pl/texture/pl_01.png", "下水道大厅"),
    ("过场", "Prologue_Epilogue/ep_07/Episode1_7_pl/texture/pl_03.png", "隧道"),
    ("过场", "Prologue_Epilogue/ep_08/Episode1_8_ep/texture/ep_01.png", "废墟火海_月夜"),
    ("过场", "Prologue_Epilogue/ep_08/Episode1_8_pl/texture/pl_01.png", "港湾都市_夜"),
    ("过场", "Prologue_Epilogue/ep_08/Episode1_8_pl/texture/pl_02.png", "河岸_月夜"),
    ("过场", "Prologue_Epilogue/ep_08/Episode1_8_pl/texture/pl_03.png", "都市鸟瞰_夜"),
    ("过场", "Prologue_Epilogue/ep_09/Episode2_1_ep/texture/ep_01_0.png", "雪中机库废墟"),
    ("过场", "Prologue_Epilogue/ep_09/Episode2_1_ep/texture/ep_02.png", "沼泽_月夜"),
    ("过场", "Prologue_Epilogue/ep_09/Episode2_1_pl/texture/pl_01_0.png", "运输机舱"),
    ("过场", "Prologue_Epilogue/ep_09/Episode2_1_pl/texture/pl_03_0.png", "破顶的基地大厅"),
    ("过场", "Prologue_Epilogue/ep_10/Episode2_2_ep/texture/ep_01_0.png", "DSO总部大厅"),
    ("过场", "Prologue_Epilogue/ep_10/Episode2_2_ep/texture/ep_02_0.png", "雪中都市鸟瞰"),
    ("过场", "Prologue_Epilogue/ep_10/Episode2_2_ep/texture/ep_03_0.png", "风暴中的高塔"),
    ("过场", "Prologue_Epilogue/ep_10/Episode2_2_pl/texture/pl_02_0.png", "雪地公路关卡"),
    ("过场", "Prologue_Epilogue/ep_10/Episode2_2_pl/texture/pl_03_0.png", "雪原高塔"),
    ("过场", "Prologue_Epilogue/ep_11/Episode2_3_ep/texture/ep_02_0.png", "废墟广场_雪夜"),
    ("过场", "Prologue_Epilogue/ep_11/Episode2_3_ep/texture/ep_03_0.png", "废墟大街_雪"),
    ("过场", "Prologue_Epilogue/ep_11/Episode2_3_pl/texture/pl_01_0.png", "DSO会议室"),
    ("过场", "Prologue_Epilogue/ep_11/Episode2_3_pl/texture/pl_03_0.png", "雪原基地_白天"),
    ("过场", "Prologue_Epilogue/ep_12/Episode2_4_ep/texture/ep_01_0.png", "地铁隧道"),
    ("过场", "Prologue_Epilogue/ep_12/Episode2_4_ep/texture/ep_03_0.png", "雪夜隧道口"),
    ("过场", "Prologue_Epilogue/ep_12/Episode2_4_pl/texture/pl_02_0.png", "冰封车站大厅"),
    ("过场", "Prologue_Epilogue/ep_12/Episode2_4_pl/texture/pl_03_0.png", "冰封长廊"),
    ("界面", "UI/BackGround/BGUnit_SchoolClubPopup.png", "基地休息室"),      # the other menu backdrops are
    ("界面", "UI/BackGround/BGUnit_SchoolMap.png", "指挥室"),                # dimmed and blurred on purpose
    ("抽卡", "Icon/Portal/Portal_Bg_Premium1.png", "紫色都市"),
    ("抽卡", "Icon/Portal/Portal_Bg_Special1.png", "绿色光带"),
    ("抽卡", "Icon/Portal/Portal_Bg_Pickup1.png", "白绿"),
    ("抽卡", "Icon/Portal/Portal_Bg_Weapon1.png", "白色影棚"),
    ("抽卡", "Director/GachaIntro/Texutre/Spown_M_01.png", "夜空都市_鱼眼"),
    ("天空", "Effect/EP1_FX_Resources/Textures/Background/FX_t_BG_Sky_Day_02.png", "蓝天白云"),
    ("天空", "Effect/EP1_FX_Resources/Textures/Background/FX_t_BG_Sky_Sunset_01.png", "晚霞"),
    ("天空", "Effect/EP1_FX_Resources/Textures/Background/FX_t_BG_Sky_Night_05.png", "银河"),
    ("天空", "Effect/EP1_FX_Resources/Textures/Background/FX_t_BG_Sky_Night_06.png", "紫色夜云"),
    ("天空", "Effect/EP1_FX_Resources/Textures/Background/FX_t_BG_Sky_Night_10.png", "蓝色夜空"),
    ("天空", "Effect/EP1_FX_Resources/Textures/Background/FX_t_BG_Sky_Night_07.png", "蓝色星云"),
    ("全景", "BackGround/SquadBackGround/04_TK_Building/Texture/drt_quest_pv_2D_asagi_Sky_1.png", "霓虹都市_夜"),
    ("全景", "BackGround/Share/Skybox/Above Day C Equirect.png", "云海"),
    ("全景", "BackGround/SquadBackGround/02_Gosha_Academy/Sky/Sunless_BlueSky_03/Sunless_BlueSky_03_flat.png", "蓝天"),
    ("全景", "BackGround/SquadBackGround/Dun05_Fri/Materials/Epic_BlueSunset_EquiRect_flat 1.png", "日落"),
    ("全景", "BackGround/SquadBackGround/Dun06_Sat/Day Sun High CloudsLayer 2.png", "多云"),
    ("全景", "BackGround/Share/Skybox/AllSky_Overcast4_Low.png", "阴天"),
    ("全景", "BackGround/Share/Skybox/AllSky_Night_MoonBurst Equirect.png", "月夜"),
    ("全景", "BackGround/SquadBackGround/05_Forest/FantasySky_Night1.png", "夜云"),
    ("全景", "BackGround/Share/Skybox/AllSky_Space_AnotherPlanet Equirect.png", "行星日出"),
    ("全景", "BackGround/Share/Skybox/Materials/sky_school_rooftop_Day.png", "学校天台_白天"),
]
# --all: every picture under these folders, by category
ALL_FOLDERS = (("剧情", "Story/BG/"), ("过场", "Prologue_Epilogue/"), ("界面", "UI/BackGround/"),
               ("抽卡", "Icon/Portal/"), ("抽卡", "Director/GachaIntro/"),
               ("天空", "Effect/EP1_FX_Resources/Textures/Background/"), ("全景", "BackGround/"))
NAME_PREFIXES = re.compile(r"^(BGUnit_|Portal_Bg_|FX_t_BG_)")


# ---------------------------------------------------------------- names
def file_stem(key: str) -> str:
    """The game's own name of a picture, short: chapter-episode in front of a cutscene layer
    (Episode1_3_pl/texture/pl_01.png -> 1-3_pl_01), the folder-wide prefixes (BGUnit_ ...) dropped."""
    stem = NAME_PREFIXES.sub("", os.path.splitext(key.rsplit("/", 1)[-1])[0])
    stem = re.sub(r"[^0-9A-Za-z]+", "_", stem).strip("_") or "x"
    m = re.search(r"Episode(\d+)_(\d+)_(?:pl|ep)/", key)
    return "%s-%s_%s" % (m.group(1), m.group(2), stem) if m else stem


def picture_name(category: str, key: str, label: str) -> str:
    return "%s_%s_%s.png" % (category, file_stem(key), label)


# ---------------------------------------------------------------- pictures
def cube_to_equirect(faces, width: int) -> np.ndarray:
    """Six cubemap faces (+X -X +Y -Y +Z -Z, each [n, n, channels], row 0 = t 0 as the faces are stored)
    -> an equirectangular picture [width / 2, width, channels], laid out like Unity's panoramic skybox:
    the middle column looks along +X, a quarter to its left along +Z (forward), the top row straight up."""
    height = width // 2
    n = faces[0].shape[0]
    lon = (0.5 - (np.arange(width) + 0.5) / width) * 2.0 * np.pi          # u = 0.5 - atan2(z, x) / 2 pi
    lat = (0.5 - (np.arange(height) + 0.5) / height) * np.pi
    lon, lat = np.meshgrid(lon, lat)
    x, y, z = np.cos(lat) * np.cos(lon), np.sin(lat), np.cos(lat) * np.sin(lon)
    ax, ay, az = np.abs(x), np.abs(y), np.abs(z)
    stack = np.stack([np.asarray(f, dtype=np.float32) for f in faces])
    out = np.zeros((height, width) + stack.shape[3:], dtype=np.float32)
    on_x, on_y = (ax >= ay) & (ax >= az), (ay > ax) & (ay >= az)
    on_z = ~on_x & ~on_y
    table = ((0, on_x & (x > 0), -z, -y, ax), (1, on_x & (x <= 0), z, -y, ax),     # face, where, s, t, major axis
             (2, on_y & (y > 0), x, z, ay), (3, on_y & (y <= 0), x, -z, ay),
             (4, on_z & (z > 0), x, -y, az), (5, on_z & (z <= 0), -x, -y, az))
    for face, where, sc, tc_, ma in table:
        s = (sc[where] / ma[where] + 1.0) * 0.5 * n - 0.5
        t = (tc_[where] / ma[where] + 1.0) * 0.5 * n - 0.5
        s0, t0 = np.clip(np.floor(s).astype(int), 0, n - 1), np.clip(np.floor(t).astype(int), 0, n - 1)
        s1, t1 = np.clip(s0 + 1, 0, n - 1), np.clip(t0 + 1, 0, n - 1)
        fs, ft = np.clip(s - s0, 0.0, 1.0)[:, None], np.clip(t - t0, 0.0, 1.0)[:, None]
        img = stack[face]
        out[where] = (img[t0, s0] * (1 - fs) * (1 - ft) + img[t0, s1] * fs * (1 - ft)
                      + img[t1, s0] * (1 - fs) * ft + img[t1, s1] * fs * ft)
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def cube_faces(tex) -> list[np.ndarray]:
    """The six faces of a Cubemap as RGB arrays.  The faces follow each other in the image data; they are
    stored top row first (a Texture2D is stored bottom row first), so they are not flipped."""
    from UnityPy.export import Texture2DConverter

    data = bytes(tex.get_image_data())
    count = getattr(tex, "m_ImageCount", 6) or 6
    if count != 6:
        raise ValueError("%d images in the cubemap, not 6" % count)
    size = len(data) // count
    reader = tex.object_reader
    return [np.asarray(Texture2DConverter.parse_image_data(
        data[i * size:(i + 1) * size], tex.m_Width, tex.m_Height, tex.m_TextureFormat,
        getattr(reader, "version", (0, 0, 0, 0)), getattr(reader, "platform", 0),
        getattr(tex, "m_PlatformBlob", None), False).convert("RGB")) for i in range(count)]


def tidy(image: Image.Image, category: str) -> Image.Image:
    """Alpha dropped when the picture is opaque anyway; a menu backdrop back to the 16:9 it is shown at."""
    if image.mode == "RGBA" and image.getextrema()[3][0] == 255:
        image = image.convert("RGB")
    if category in SQUASHED and image.width == image.height:
        image = image.resize((image.width, int(round(image.width * 9 / 16))), Image.LANCZOS)
    return image


class Pictures:
    """The textures and cubemaps of the catalog, by address."""

    def __init__(self, root: str = tc.EXPORT_ROOT):
        import tsquad_scene as ts

        self.loader = ts.Loader(root)
        self.by_key: dict[str, dict[str, dict]] = {}
        for a in tc.catalog_assets(root):
            if isinstance(a["key"], str) and a["type"] in ("Texture2D", "Cubemap"):
                self.by_key.setdefault(a["key"], {})[a["type"]] = a
        self._containers: dict[str, dict] = {}

    def _container(self, bundle: str) -> dict:
        if bundle not in self._containers:
            table: dict[str, list] = {}
            for sf in self.loader.serialized_files(bundle):
                for obj in sf.objects.values():
                    if obj.type.name == "AssetBundle":
                        for guid, info in obj.read().m_Container:
                            table.setdefault(guid, []).append(info.asset)
            self._containers[bundle] = table
        return self._containers[bundle]

    def entry(self, key: str) -> dict:
        kinds = self.by_key.get(key)
        if not kinds:
            raise KeyError("not in the catalog: %s" % key)
        return kinds.get("Texture2D") or kinds["Cubemap"]

    def texture(self, key: str):
        a = self.entry(key)
        for pptr in self._container(a["bundle"]).get(a["guid"], []):
            reader = self.loader.deref(pptr)
            if reader is not None and reader.type.name == a["type"]:
                return reader.read()
        raise KeyError("no %s behind %s in %s" % (a["type"], key, a["bundle"]))

    def image(self, key: str, width: int = PANORAMA_WIDTH) -> Image.Image:
        """A texture as it is; a cubemap as an equirectangular panorama `width` wide."""
        tex = self.texture(key)
        if self.entry(key)["type"] == "Cubemap":
            return Image.fromarray(cube_to_equirect(cube_faces(tex), width))
        return tex.image


# ---------------------------------------------------------------- contact sheets
def contact_sheets(rows: list[dict], out_dir: str, cols: int = 5, per_page: int = 30, cell: int = 384) -> list[str]:
    """_总览_<类别>_<n>.jpg: the pictures of each category, small, with their file names."""
    try:
        font = ImageFont.truetype(SHEET_FONT, 15)
    except OSError:
        font = ImageFont.load_default()
    label, box = 24, int(cell * 0.72)
    written = []
    for name in os.listdir(out_dir):                    # sheets of an earlier, larger set
        if name.startswith("_总览_") and name.endswith(".jpg"):
            os.remove(os.path.join(out_dir, name))
    for category in CATEGORIES:
        files = [r for r in rows if r["category"] == category]
        for page in range(math.ceil(len(files) / per_page)):
            chunk = files[page * per_page:(page + 1) * per_page]
            sheet = Image.new("RGB", (cols * cell, math.ceil(len(chunk) / cols) * (box + label)), (38, 38, 44))
            draw = ImageDraw.Draw(sheet)
            for i, row in enumerate(chunk):
                with Image.open(row["file"]) as im:
                    im = im.convert("RGB")
                    im.thumbnail((cell - 8, box - 6))
                x, y = (i % cols) * cell, (i // cols) * (box + label)
                sheet.paste(im, (x + (cell - im.width) // 2, y + (box - im.height) // 2))
                text = "%s  %s" % (row["label"], file_stem(row["key"]))
                draw.text((x + 6, y + box + 1), "%s  %dx%d" % (text[:34], row["width"], row["height"]),
                          fill=(236, 236, 236), font=font)
            path = os.path.join(out_dir, "_总览_%s_%d.jpg" % (category, page + 1))
            sheet.save(path, quality=90)
            written.append(path)
    return written


# ---------------------------------------------------------------- export
def export_picks(pictures: Pictures, out_dir: str, force: bool = False, width: int = PANORAMA_WIDTH):
    """Write PICKS into out_dir; returns (rows for the manifest, addresses that failed)."""
    rows, failed = [], []
    os.makedirs(out_dir, exist_ok=True)
    for category, key, label in PICKS:
        path = os.path.join(out_dir, picture_name(category, key, label))
        try:
            a = pictures.entry(key)
            if force or not os.path.isfile(path):
                tidy(pictures.image(key, width), category).save(path)
            with Image.open(path) as im:
                size = im.size
        except Exception as exc:  # noqa: BLE001 - one picture must not stop the rest
            log("FAILED %s: %s" % (key, exc))
            failed.append(key)
            continue
        rows.append({"file": path, "category": category, "label": label, "key": key, "type": a["type"],
                     "bundle": a["bundle"], "width": size[0], "height": size[1]})
    return rows, failed


def export_all(pictures: Pictures, out_dir: str, force: bool = False, width: int = PANORAMA_WIDTH) -> int:
    """Every picture under ALL_FOLDERS -> out_dir/全部/<类别>/ (cubemaps: the sky-sized ones, as panoramas)."""
    n = 0
    for category, prefix in ALL_FOLDERS:
        folder = os.path.join(out_dir, "全部", category)
        os.makedirs(folder, exist_ok=True)
        for key in sorted(k for k in pictures.by_key if k.startswith(prefix)):
            kind = pictures.entry(key)["type"]
            if (category == "全景") != (kind == "Cubemap"):
                continue
            name = re.sub(r"[^0-9A-Za-z._-]+", "_", os.path.splitext(key[len(prefix):])[0].replace("/", "__"))
            path = os.path.join(folder, name + ".png")
            if os.path.isfile(path) and not force:
                continue
            try:
                if kind == "Cubemap" and pictures.texture(key).m_Width < 512:      # reflection probes, 16 - 64 px
                    continue
                tidy(pictures.image(key, width), category).save(path)
                n += 1
            except Exception as exc:  # noqa: BLE001
                log("FAILED %s: %s" % (key, exc))
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter,
                                 allow_abbrev=False)
    ap.add_argument("--list", action="store_true", help="print the picks (file name <- catalog address), write nothing")
    ap.add_argument("--all", action="store_true", help="also every picture of the background folders, into 全部\\<类别>\\")
    ap.add_argument("--force", action="store_true", help="write the files that are there again")
    ap.add_argument("--width", type=int, default=PANORAMA_WIDTH, help="width of the panoramas (%d)" % PANORAMA_WIDTH)
    ap.add_argument("--out", default="", help="the folder (default <export-root>\\%s)" % OUT_NAME)
    ap.add_argument("--export-root", default=tc.EXPORT_ROOT)
    a = ap.parse_args()
    if a.list:
        for category, key, label in PICKS:
            print("%-44s <- %s" % (picture_name(category, key, label), key))
        print("%d pictures" % len(PICKS))
        return 0

    tc.check_game()
    out_dir = a.out or os.path.join(a.export_root, OUT_NAME)
    pictures = Pictures(a.export_root)
    rows, failed = export_picks(pictures, out_dir, a.force, a.width)
    sheets = contact_sheets(rows, out_dir)
    tc.save_json(os.path.join(tc.meta_dir(a.export_root), "backgrounds.json"), rows)
    by = {c: sum(1 for r in rows if r["category"] == c) for c in CATEGORIES}
    log("%d pictures in %s (%s), %d contact sheets" % (
        len(rows), out_dir, ", ".join("%s %d" % kv for kv in by.items()), len(sheets)))
    if a.all:
        log("%d more pictures in %s" % (export_all(pictures, out_dir, a.force, a.width), os.path.join(out_dir, "全部")))
    if failed:
        log("%d failed: %s" % (len(failed), ", ".join(failed)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
