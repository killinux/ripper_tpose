r"""Vindictus（北美服）导出画廊：每个外观一张卡片——预览图、PMX 检查图、文件链接、说明。

    python make_gallery.py            # -> 本脚本旁的 index.html；缩略图写到 <导出根>\_meta\gallery_thumbs\

页面用 file:// 链接指向本机文件，缩略图放在导出根目录下，游戏素材不进仓库（和这里其它画廊同一条规矩）。
每次导出后重跑即可。
"""
import argparse
import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import looks  # noqa: E402

EXPORT = os.environ.get('VINDICTUSNA_EXPORT', r'E:\game_export\VindictusNA')
WORK = os.environ.get('VINDICTUSNA_WORK', r'E:\tools\vindictusna')
ORDER = ['fiona', 'evy', 'vella', 'lynn', 'arisha', 'delia', 'miri', 'miul', 'bel', 'lethor', 'tessa', 'danah', 'letty',
         'latiya', 'czern', 'sanyaa', 'neamhain', 'calia', 'lumielle']
COUNTS = {'female': 19, 'male': 9, 'npc_models': 116, 'monster_models': 929, 'outfit_sets': 451, 'complete_sets': 192}


def uri(p):
    try:
        return Path(p).as_uri()
    except (ValueError, OSError):
        return ''


def thumb(src, dst, width, crop=None, force=False):
    if not os.path.exists(src):
        return None
    if force or not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        im = Image.open(src).convert('RGB')
        if crop:
            w, h = im.size
            im = im.crop((int(w * crop[0]), int(h * crop[1]), int(w * crop[2]), int(h * crop[3])))
        im.thumbnail((width, width * 4))
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst, quality=84)
    return dst


def size_of(p):
    if not os.path.exists(p):
        return ''
    n = os.path.getsize(p)
    return '%.1f MB' % (n / 1048576) if n > 1048576 else '%d KB' % (n // 1024)


def report(look, kind):
    p = os.path.join(WORK, 'build', look, kind + '.log')
    if not os.path.exists(p):
        return {}
    t = open(p, encoding='utf-8', errors='replace').read()
    m = re.search(r'VINDICTUS_%s=(\{.*\})' % kind.upper(), t)
    try:
        return json.loads(m.group(1)) if m else {}
    except ValueError:
        return {}


def card(h, tdir, force):
    look = looks.resolve(h)
    name, tag = look['name'], look['look']
    bdir = os.path.join(EXPORT, name, 'blend', tag)
    xdir = os.path.join(EXPORT, name, 'xps', tag)
    pdir = os.path.join(EXPORT, name, 'pmx', tag)
    blend, xps, pmx = (os.path.join(bdir, tag + '.blend'), os.path.join(xdir, tag + '.xps'), os.path.join(pdir, tag + '.pmx'))
    imgs = []
    for v, crop in (('front', (0.15, 0, 0.85, 1)), ('34', (0.15, 0, 0.85, 1)), ('back', (0.15, 0, 0.85, 1)),
                    ('face', (0.12, 0.05, 0.88, 0.8))):
        t = thumb(os.path.join(bdir, '%s_%s.png' % (tag, v)), os.path.join(tdir, '%s_%s.jpg' % (tag, v)), 420, crop, force)
        if t:
            imgs.append((v, t, os.path.join(bdir, '%s_%s.png' % (tag, v))))
    pmx_imgs = []
    for v in ('preview_morphs', 'preview_dance'):
        t = thumb(os.path.join(pdir, v + '.png'), os.path.join(tdir, '%s_%s.jpg' % (tag, v)), 900, None, force)
        if t:
            pmx_imgs.append((v, t, os.path.join(pdir, v + '.png')))
    pr, xr = report(tag, 'pmx'), report(tag, 'xps')
    note = os.path.join(WORK, 'build', tag, '说明.txt')
    fixes = []
    if os.path.exists(note):
        t = open(note, encoding='utf-8').read()
        sec = t.split('我补 / 修的部分', 1)[-1].split('\n\n', 1)[0]
        fixes = [re.sub(r'^\s*\d+\.\s*', '', l).strip() for l in sec.splitlines()[1:] if l.strip()]
    morphs = (pr.get('morphs') or {}).get('made') or []
    done = os.path.exists(blend)
    e = html.escape
    out = ['<article class="card%s" id="%s">' % ('' if done else ' pending', h)]
    out.append('<header><h2>%s <small>%s</small></h2><p class="outfit">%s <code>%s</code></p></header>' % (
        e(look['cn']), e(name), e(looks.OUTFIT_CN.get(look['outfit'], look['outfit'])), e(look['outfit'])))
    if imgs:
        out.append('<div class="views">' + ''.join(
            '<a href="%s" target="_blank"><img loading="lazy" src="%s" alt="%s %s"></a>' % (uri(full), uri(t), e(tag), v)
            for v, t, full in imgs) + '</div>')
    else:
        out.append('<div class="views empty">还没导出</div>')
    links = []
    for label, p in (('.blend', blend), ('XPS', xps), ('PMX', pmx)):
        if os.path.exists(p):
            links.append('<a class="file" href="%s">%s <span>%s</span></a>' % (uri(os.path.dirname(p)), label, size_of(p)))
    if links:
        out.append('<nav class="files">' + ''.join(links) + '</nav>')
    facts = []
    if pr:
        facts.append('PMX %s 骨 · %s 刚体 · %s 关节 · 表情 %d 个' % (pr.get('bones'), pr.get('rigid_bodies'), pr.get('joints'),
                                                          len(morphs) + int((pr.get('morphs') or {}).get('raw') or 0)))
    if xr:
        facts.append('XPS %s 骨 · %s 网格' % (xr.get('bones'), xr.get('meshes')))
    if facts:
        out.append('<p class="facts">' + ' ｜ '.join(e(f) for f in facts) + '</p>')
    if pmx_imgs:
        out.append('<details><summary>PMX 检查（表情 / 舞蹈物理）</summary>' + ''.join(
            '<a href="%s" target="_blank"><img loading="lazy" src="%s" alt="%s"></a>' % (uri(full), uri(t), v)
            for v, t, full in pmx_imgs) + '</details>')
    if fixes:
        out.append('<details><summary>替代 / 修补（%d）</summary><ul>%s</ul></details>' % (
            len(fixes), ''.join('<li>%s</li>' % e(f) for f in fixes)))
    out.append('</article>')
    return '\n'.join(out), done


CSS = """
:root{--bg:#16181c;--card:#1f2228;--line:#2e323a;--fg:#e8e8ea;--dim:#9aa0aa;--acc:#7cc4a0;--warn:#e0a060}
@media (prefers-color-scheme: light){:root:not([data-theme="dark"]){--bg:#f4f4f2;--card:#ffffff;--line:#dcdcd8;--fg:#1d1f23;--dim:#5d636c;--acc:#2f7a55;--warn:#a85d10}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}
main{max-width:1500px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:22px;margin:0 0 6px}.lead{color:var(--dim);margin:0 0 14px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 18px}.stats span{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px}
.stats b{color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(440px,1fr));gap:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:12px;min-width:0}
.card.pending{opacity:.55}
.card h2{font-size:18px;margin:0}.card h2 small{color:var(--dim);font-weight:400;font-size:13px;margin-left:6px}
.outfit{margin:2px 0 8px;color:var(--dim)}.outfit code{font-size:12px}
.views{display:grid;grid-template-columns:repeat(4,1fr);gap:4px}.views img{width:100%;border-radius:6px;display:block;background:#2a2d33}
.views.empty{color:var(--dim);padding:40px;text-align:center;border:1px dashed var(--line);border-radius:8px}
.files{display:flex;gap:8px;margin:10px 0 4px;flex-wrap:wrap}
.file{color:var(--fg);text-decoration:none;border:1px solid var(--line);border-radius:6px;padding:3px 9px}
.file span{color:var(--dim);font-size:12px}.file:hover{border-color:var(--acc)}
.facts{color:var(--dim);margin:6px 0;font-size:13px}
details{margin-top:6px}summary{cursor:pointer;color:var(--acc)}details img{width:100%;margin-top:6px;border-radius:6px}
details ul{margin:6px 0 0 18px;padding:0;color:var(--dim);font-size:13px}
@media (max-width:520px){.grid{grid-template-columns:1fr}.views{grid-template-columns:repeat(2,1fr)}}
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'index.html'))
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    tdir = os.path.join(EXPORT, '_meta', 'gallery_thumbs')
    cards, n_done = [], 0
    for h in ORDER:
        c, done = card(h, tdir, a.force)
        cards.append(c)
        n_done += done
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    page = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<title>Vindictus 北美服画廊</title><style>%s</style></head><body><main>' % CSS,
            '<h1>洛奇英雄传 Vindictus（北美服）· 女性角色</h1>',
            '<p class="lead">每位一个外观：.blend（游戏材质、全分辨率贴图、角色体型、表情形态键）+ XPS + PMX（物理、MMD 表情）。'
            '点图片看原图，点文件按钮打开所在文件夹。生成于 %s，scripts/vindictusna。</p>' % now,
            '<div class="stats"><span>已导出 <b>%d</b> / 19</span><span>游戏里可玩角色 <b>%d</b>（女 %d · 男 %d）</span>'
            '<span>NPC 模型 <b>%d</b></span><span>怪物模型 <b>%d</b></span><span>女性服装 <b>%d</b> 套（贴图齐全 %d）</span></div>' % (
                n_done, COUNTS['female'] + COUNTS['male'], COUNTS['female'], COUNTS['male'], COUNTS['npc_models'],
                COUNTS['monster_models'], COUNTS['outfit_sets'], COUNTS['complete_sets']),
            '<section class="grid">'] + cards + ['</section></main></body></html>']
    open(a.out, 'w', encoding='utf-8').write('\n'.join(page))
    print(a.out, 'cards', len(cards), 'done', n_done)


if __name__ == '__main__':
    main()
