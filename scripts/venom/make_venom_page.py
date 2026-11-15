"""html/venom_female_models.html: where female Venom (She-Venom / Gwenom / symbiote girls) models can be had, tagged
with what this PC has (and what is already exported: E:\\game_export, see the venom collection _毒液合集).

    python -I scripts\\venom\\make_venom_page.py

Data in data\\ (2026-11-15): nexus_venom.json - Nexus v2 GraphQL sweep (nexus_venom.py writes the full list; the repo
copy keeps only the 64 entries this page lists), sketchfab_venom.json - Sketchfab public search, br_venom_hits.json -
BetterRepack HS2 / AI zipmod crawl (br_crawl_venom.py); web searches are the hand list below."""
import html
import json
import os
import re
import sys
import time

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
HERE = os.path.join(SCRIPT_DIR, "data")
OUT = os.path.normpath(os.path.join(SCRIPT_DIR, "..", "..", "html", "venom_female_models.html"))
COLLECTION = r"E:\game_export\_毒液合集\index.html"
INSTALLED = {"stellarblade", "finalfantasy7remake", "finalfantasy7rebirth", "honeyselect2", "marvelrivals"}
FEMALE = re.compile(r"she.?venom|she.?anti|she.?carnage|gwenom|female|girl|woman|lady|ladies|sue.?storm|black.?widow|"
                    r"squirrel|juri|manon|jill|mileena|hela|storm|mayhem|april|earth.?x|nu.?udra|cbbe|serana|"
                    r"anne.?weying|spider.?gwen", re.I)
NOT_FEMALE_SF = re.compile(r"mal0|ladybug|quiet|drone|opossum|scream|darkills|marlena|low poly girl|spider female|"
                           r"kaethrix|^venom$", re.I)
WHY_GAME = {
    "marvelrivals": "scripts/marvelrivals 能转；游戏本体的贴图要新版映射文件（Nexus #13477 Variant Skin Studio）",
    "marvelsspidermanremastered": "Insomniac 引擎：本机没有流程，也没装",
    "marvelsspiderman2": "Insomniac 新版 .model：顶点格式没有工具能读（2026-11-15 试过，ALERT 只支持到 Rift Apart）",
    "spidermanmilesmorales": "Insomniac 引擎：本机没有流程，也没装",
    "streetfighter6": "RE 引擎：本机没装；scripts/re_engine 是按生化危机 2 / 3 做的，没试过街霸 6",
    "residentevil32020": "RE 引擎：scripts/re_engine 不用游戏本体转 mod 自带的部分（头发等游戏贴图是纯色）",
    "marvelheroesomega": "不用游戏本体：mod 的 .upk 自带模型和贴图，scripts/marvelheroes/export_upk.py 直接转 Blender",
}
EXPORT_ROOT = r"E:\game_export"


GAME_DIRS = {"MarvelHeroesOmega": "marvelheroesomega", "ResidentEvil3": "residentevil32020",
             "MarvelRivals": "marvelrivals", "SpiderMan2": "marvelsspiderman2"}


def exported_mods():
    """(game domain, mod id) -> exported .blend: the export reports of Marvel Heroes (mod id from the Nexus zip
    name) and every <game>\\<char>\\blend\\<label>_<mod id>[_variant]\\<label>.blend in the archive."""
    import glob
    found = {}
    for rep in glob.glob(os.path.join(EXPORT_ROOT, "MarvelHeroesOmega", "*", "_meta", "report_*.json")):
        r = json.load(open(rep, encoding="utf-8"))
        m = re.search(r" (\d+) [\d.]+ \d{4}-\d{2}-\d{2}T", os.path.basename(r.get("source", "")))
        blend = (r.get("blend") or {}).get("blend")
        if m and blend and os.path.isfile(blend):
            found[("marvelheroesomega", int(m.group(1)))] = blend
    for game_dir, domain in GAME_DIRS.items():
        for blend in glob.glob(os.path.join(EXPORT_ROOT, game_dir, "*", "blend", "*", "*.blend")):
            label = os.path.basename(os.path.dirname(blend))
            char_dir = os.path.dirname(os.path.dirname(os.path.dirname(blend)))
            # only a finished export counts: .blend + PMX + XPS (a test .blend alone is not tagged)
            if not (os.path.isfile(os.path.join(char_dir, "pmx", label, label + ".pmx"))
                    and os.path.isfile(os.path.join(char_dir, "xps", label, label + ".xps"))):
                continue
            m = re.search(r"_(\d{3,6})(?:_[A-Za-z][\w-]*)?$", label)
            if m:
                found.setdefault((domain, int(m.group(1))), blend)
    return found


def file_url(path):
    import urllib.parse
    return "file:///" + urllib.parse.quote(path.replace("\\", "/"), safe="/:")


def esc(s):
    return html.escape(str(s or ""))


def main():
    nexus = json.load(open(os.path.join(HERE, "nexus_venom.json"), encoding="utf-8"))
    cand = []
    for m in nexus:
        name, summ = m["name"], m.get("summary") or ""
        if not re.search(r"venom|symbio|gwenom|carnage", name, re.I):
            continue
        if not FEMALE.search(name + " " + summ):
            continue
        if re.search(r"maximum carnage|venomancy|venom snake|venom blade|venomous|frostbite|poison|kadachi|"
                     r"symbiotic settlements|moons carnage|riot|moveset", name, re.I):
            continue
        cand.append(m)
    cand.sort(key=lambda m: (m["game"]["name"], -(m["downloads"] or 0)))
    sf = [r for r in json.load(open(os.path.join(HERE, "sketchfab_venom.json"), encoding="utf-8"))
          if not NOT_FEMALE_SF.search(r["name"])]
    sf.sort(key=lambda r: -r["likes"])
    br = []
    if os.path.isfile(os.path.join(HERE, "br_venom_hits.json")):
        seen = set()
        for h in json.load(open(os.path.join(HERE, "br_venom_hits.json"), encoding="utf-8")):
            if h["url"] not in seen:
                seen.add(h["url"])
                br.append(h)
    paid = [
        ("She-Venom: Fortnite + Marvel Rivals（Blender）", "MayoSplash，itch.io，10 美元起；Sketchfab 上有免费样本（上表第一行）",
         "https://mayosplash.itch.io/she-venom-blender-mayo"),
        ("She-Venom（Blender / SFM）", "MayoSplash，Gumroad，标价 0 美元起，条款写明不许公开、不许再分发",
         "https://mayosplash34.gumroad.com/l/kdsuo"),
        ("She Venom - Zarina（VRM）", "BlackShark Studios，Gumroad，4.99 美元，VRChat 用的 VRM",
         "https://blacksharkstudios.gumroad.com/l/shevenom-zarina-vrm"),
        ("MCU She-Venom for G8F & G9", "RenderHub，DAZ Genesis 8 / 9 的服装（要有 DAZ 角色）",
         "https://www.renderhub.com/inn/mcu-she-venom-for-g8f-g9"),
        ("she venom rig", "CGTrader，付费绑定模型", "https://www.cgtrader.com/3d-models/character/other/she-venom-rig"),
        ("she venom（Sven Co-op 玩家模型）", "ModDB，游戏用的低模", "https://www.moddb.com/addons/she-venom"),
    ]
    css = """
:root{--bg:#f6f6f4;--fg:#1d1d1f;--muted:#666;--card:#fff;--line:#ddd;--accent:#2563eb;--tag:#eef2ff}
@media (prefers-color-scheme:dark){:root{--bg:#18181b;--fg:#ececec;--muted:#a1a1aa;--card:#232327;--line:#3a3a40;--accent:#7aa2ff;--tag:#2b2f45}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.6 "Microsoft YaHei",system-ui,sans-serif}
main{max-width:1300px;margin:0 auto;padding:24px 16px}
h1{font-size:26px;margin:0 0 6px} h2{font-size:20px;margin:28px 0 8px}
.lead{color:var(--muted)} table{border-collapse:collapse;width:100%;background:var(--card);font-size:14px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--card)} img{width:96px;height:72px;object-fit:cover;border-radius:4px}
a{color:var(--accent)} .tag{display:inline-block;background:var(--tag);border-radius:10px;padding:0 8px;font-size:12px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 16px}
"""
    o = ["<!doctype html><html lang='zh'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,"
         "initial-scale=1'><title>女性毒液模型</title><style>%s</style></head><body><main>" % css,
         "<h1>女性毒液（She-Venom / Gwenom / 共生体）模型：哪里有</h1>",
         "<p class='lead'>%s 整理。来源：Nexus Mods 全站按名字搜（venom、symbiote、gwenom、carnage），筛出女性角色；"
         "Sketchfab 可下载模型；BetterRepack 的 HS2 / AI 少女 zipmod 库；网页搜索（itch.io、Gumroad、RenderHub、CGTrader、"
         "BOOTH、ModDB）。Smutbase 从这台电脑连不上（TLS 错误），没查到。</p>" % time.strftime("%Y-%m-%d"),
         "<div class='box'><b>怎么用：</b>Sketchfab 上的模型最省事：登录免费账号就能下载（glTF / FBX），"
         "直接导入 Blender，再用我们的工具转 PMX / XPS。游戏 mod 一般要先有那个游戏和对应的转换流程；"
         "Marvel Heroes Omega、生化危机 2 / 3 重制版的 mod 不用游戏本体，下载下来就能转。"
         "DeviantArt、BowlRoll、BOOTH 上没找到现成的女毒液 PMX / XPS。"
         "<br><b>已经转好的</b>（blend / PMX / XPS）在毒液合集画廊：<a href='%s'>%s</a>。</div>" % (
             file_url(COLLECTION), esc(COLLECTION)),
         "<h2>一、Sketchfab：能免费下载的（%d 个）</h2>" % len(sf),
         "<table><tr><th>预览</th><th>名字</th><th>作者</th><th>面数</th><th>许可</th><th>链接</th></tr>"]
    for r in sf:
        uid = r["url"].rsplit("-", 1)[-1]
        link = "https://sketchfab.com/models/%s" % uid
        o.append("<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td><a href='%s'>Sketchfab</a></td></tr>" % (
            "<img src='%s' loading='lazy'>" % esc(r["thumb"]) if r.get("thumb") else "", esc(r["name"]), esc(r["user"]),
            "{:,}".format(r["faces"] or 0), esc(r["license"]), link))
    o.append("</table>")
    done = exported_mods()
    o.append("<h2>二、游戏 mod（Nexus，%d 个）</h2>" % len(cand))
    o.append("<p>Marvel Heroes Omega 的 mod 例外：不用游戏本体，mod 的 .upk 里自带模型和贴图，"
             "用 <code>scripts/marvelheroes/export_upk.py</code> 直接转 Blender（Nexus 下载要用你自己的浏览器）。</p>")
    o.append("<table><tr><th>预览</th><th>游戏</th><th>mod</th><th>下载量</th><th>成人</th><th>本机</th><th>简介</th></tr>")
    for m in cand:
        dom = m["game"]["domainName"]
        url = "https://www.nexusmods.com/%s/mods/%s" % (dom, m["modId"])
        if (dom, m["modId"]) in done:
            local = "<span class='tag'>已导出 Blender</span> <a href='%s'>%s</a>" % (
                file_url(done[(dom, m["modId"])]), esc(done[(dom, m["modId"])]))
        elif dom in INSTALLED:
            local = "<span class='tag'>本机装了这个游戏</span>" + (" " + esc(WHY_GAME[dom]) if dom in WHY_GAME else "")
        else:
            local = esc(WHY_GAME.get(dom, "本机没装"))
        o.append("<tr><td>%s</td><td>%s</td><td><a href='%s'>#%s %s</a></td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            "<img src='%s' loading='lazy'>" % esc(m["pictureUrl"]) if m.get("pictureUrl") else "", esc(m["game"]["name"]),
            url, m["modId"], esc(m["name"]), "{:,}".format(m["downloads"] or 0), "是" if m["adultContent"] else "",
            local, esc((m.get("summary") or "")[:140])))
    o.append("</table>")
    o.append("<h2>三、HS2 / AI 少女 zipmod（BetterRepack 公开库）</h2>")
    if br:
        o.append("<p>库里 20,982 个 zipmod，名字里带 venom / symbiote / carnage / gwenom 的只有下面这个，而且是 Studio 用的"
                 " Marvel Rivals 毒液（男性），没有女性的。</p>")
        o.append("<table><tr><th>文件</th><th>位置</th></tr>")
        for h in br:
            o.append("<tr><td><a href='%s'>%s</a></td><td>%s / %s</td></tr>" % (h["url"], esc(h["file"]), esc(h["pack"]),
                                                                              esc(h["folder"])))
        o.append("</table>")
    else:
        o.append("<p>库里 2 万多个 zipmod，文件名里带 venom / symbiote / carnage / gwenom 的一个都没有。</p>")
    o.append("<h2>四、付费或别的格式</h2><table><tr><th>名字</th><th>说明</th><th>链接</th></tr>")
    for n, d, u in paid:
        o.append("<tr><td>%s</td><td>%s</td><td><a href='%s'>%s</a></td></tr>" % (esc(n), esc(d), u, esc(u.split('/')[2])))
    o.append("</table></main></body></html>")
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(o))
    print("PAGE", OUT, "sketchfab", len(sf), "nexus", len(cand), "br", len(br))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
