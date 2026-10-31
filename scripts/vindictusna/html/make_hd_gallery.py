r"""Vindictus（北美服）高清版画廊：每位女主角的游戏原版和 AI 放大版（export_model.py --upscale）同机位对比，拖动滑块看差别。

    python make_hd_gallery.py            # 缺的对比图先用 Blender 渲（4 个并行），再写本脚本旁的 hd.html
    python make_hd_gallery.py --render   # 全部重渲

对比图（脸 / 眼睛 / 衣服 / 全身，compare_views_blender.py）写到 <导出根>\_meta\hd_compare\，网页用的 JPEG 在
<导出根>\_meta\hd_thumbs\；页面用 file:// 链接，游戏素材不进仓库。
"""
import argparse
import datetime
import html
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_gallery as mg  # noqa: E402
from make_gallery import EXPORT, ORDER, looks, uri  # noqa: E402

BLENDER = os.environ.get('BLENDER', r'D:\Program Files\blender-3.6.15-windows-x64\blender.exe')
SCRIPT = os.path.join(os.path.dirname(HERE), 'compare_views_blender.py')
RENDERS = os.path.join(EXPORT, '_meta', 'hd_compare')
THUMBS = os.path.join(EXPORT, '_meta', 'hd_thumbs')
VIEWS = (('face', '脸', 980), ('outfit', '衣服', 760), ('eyes', '眼睛', 1500))
MODELS_SHEET = r'E:\tools\vindictusna\upscale_trial\smoke\smoke_sheet.png'


def paths(h):
    look = looks.resolve(h)
    name, tag = look['name'], look['look']
    return look, name, tag, {lab: os.path.join(EXPORT, name, 'blend', t, t + '.blend')
                             for lab, t in (('orig', tag), ('hd', tag + '_HD'))}


def render(job):
    blend, prefix = job
    log = prefix + '.log'
    with open(log, 'w', encoding='utf-8', errors='replace') as fh:
        r = subprocess.run([BLENDER, '-b', blend, '--factory-startup', '--python', SCRIPT, '--', prefix],
                           stdout=fh, stderr=subprocess.STDOUT)
    ok = r.returncode == 0 and 'Traceback' not in open(log, encoding='utf-8', errors='replace').read()
    return blend, ok


def jobs_for(force):
    jobs = []
    for h in ORDER:
        _look, _name, tag, blends = paths(h)
        for lab, blend in blends.items():
            prefix = os.path.join(RENDERS, '%s_%s' % (tag, lab))
            outs = [prefix + '_%s.png' % v for v in ('face', 'eyes', 'outfit', 'body')]
            if os.path.exists(blend) and (force or not all(os.path.exists(o) and os.path.getmtime(o) > os.path.getmtime(blend)
                                                          for o in outs)):
                jobs.append((blend, prefix))
    return jobs


def jpg(src, dst, width):
    if not os.path.exists(src):
        return None
    if not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src):
        im = Image.open(src).convert('RGB')
        im = im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        im.save(dst, quality=90)
    return dst


def dir_size(d):
    n = sum(os.path.getsize(os.path.join(dp, f)) for dp, _dn, fn in os.walk(d) for f in fn) if os.path.isdir(d) else 0
    return n


def mb(n):
    return '%.0f MB' % (n / 1048576) if n else '-'


def card(h):
    look, name, tag, blends = paths(h)
    e = html.escape
    hd = tag + '_HD'
    out = ['<article class="card" id="%s"><header><h2>%s <small>%s</small></h2><p class="outfit">%s</p></header>' % (
        h, e(look['cn']), e(name), e(looks.OUTFIT_CN.get(look['outfit'], look['outfit'])))]
    if not os.path.exists(blends['hd']):
        out.append('<div class="empty">高清版还没导出</div></article>')
        return '\n'.join(out), False
    cells = []
    for v, label, w in VIEWS:
        a = jpg(os.path.join(RENDERS, '%s_orig_%s.png' % (tag, v)), os.path.join(THUMBS, '%s_orig_%s.jpg' % (tag, v)), w)
        b = jpg(os.path.join(RENDERS, '%s_hd_%s.png' % (tag, v)), os.path.join(THUMBS, '%s_hd_%s.jpg' % (tag, v)), w)
        if not (a and b):
            continue
        cells.append('<figure class="%s"><div class="cmp"><img src="%s" alt="原版 %s"><img class="hd" src="%s" alt="高清 %s">'
                     '<i class="bar"></i><input type="range" min="0" max="100" value="50" aria-label="%s 对比">'
                     '<span class="tag l">原版</span><span class="tag r">高清</span></div><figcaption>%s · '
                     '<a href="%s" target="_blank">原版原图</a> · <a href="%s" target="_blank">高清原图</a></figcaption></figure>' % (
                         v, uri(a), label, uri(b), label, label, label,
                         uri(os.path.join(RENDERS, '%s_orig_%s.png' % (tag, v))), uri(os.path.join(RENDERS, '%s_hd_%s.png' % (tag, v)))))
    out.append('<div class="views">%s</div>' % ''.join(cells) if cells else '<div class="empty">对比图还没渲</div>')
    links = []
    for label, kind in (('.blend', 'blend'), ('XPS', 'xps'), ('PMX', 'pmx')):
        d_hd, d_or = (os.path.join(EXPORT, name, kind, t) for t in (hd, tag))
        if os.path.isdir(d_hd):
            links.append('<a class="file" href="%s">%s 高清 <span>%s（原版 %s）</span></a>' % (
                uri(d_hd), label, mb(dir_size(d_hd)), mb(dir_size(d_or))))
    out.append('<nav class="files">%s</nav></article>' % ''.join(links))
    return '\n'.join(out), True


CSS = mg.CSS + """
main{max-width:1132px}.grid{grid-template-columns:1fr}
.views{display:grid;grid-template-columns:1fr 1fr;gap:10px;align-items:start}
.views figure{margin:0}.views figure.eyes{grid-column:1 / -1}
figcaption{color:var(--dim);font-size:12px;margin-top:4px}figcaption a{color:var(--acc)}
.cmp{position:relative;overflow:hidden;border-radius:8px;background:#2a2d33;line-height:0}
.cmp img{width:100%;display:block}.cmp img.hd{position:absolute;inset:0;height:100%;clip-path:inset(0 0 0 50%)}
.cmp input{position:absolute;inset:0;width:100%;height:100%;margin:0;opacity:0;cursor:ew-resize}
.cmp .bar{position:absolute;top:0;bottom:0;left:50%;width:2px;background:#fff;box-shadow:0 0 6px #000;pointer-events:none}
.cmp .tag{position:absolute;top:8px;font-size:12px;line-height:1.4;padding:2px 8px;border-radius:999px;background:rgba(0,0,0,.55);color:#fff;pointer-events:none}
.cmp .l{left:8px}.cmp .r{right:8px}
.empty{color:var(--dim);padding:30px;text-align:center;border:1px dashed var(--line);border-radius:8px}
.lead a{color:var(--acc)}
@media (max-width:700px){.views{grid-template-columns:1fr}}
"""

JS = """<script>
document.querySelectorAll('.cmp').forEach(c => { const r = c.querySelector('input'), hd = c.querySelector('.hd'),
  bar = c.querySelector('.bar'); const set = v => { hd.style.clipPath = 'inset(0 0 0 ' + v + '%)'; bar.style.left = v + '%'; };
  r.addEventListener('input', () => set(r.value)); set(r.value); });
</script>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=os.path.join(HERE, 'hd.html'))
    ap.add_argument('--render', action='store_true', help='render every comparison again')
    ap.add_argument('--procs', type=int, default=4)
    a = ap.parse_args()
    os.makedirs(RENDERS, exist_ok=True)
    jobs = jobs_for(a.render)
    if jobs:
        print('rendering %d comparison sets (%d at a time) ...' % (len(jobs), a.procs), flush=True)
        with ThreadPoolExecutor(a.procs) as pool:
            for blend, ok in pool.map(render, jobs):
                print('  %s %s' % ('ok' if ok else 'FAILED', os.path.basename(blend)), flush=True)
    cards, n = [], 0
    for h in ORDER:
        c, done = card(h)
        cards.append(c)
        n += done
    total = sum(dir_size(os.path.join(EXPORT, looks.resolve(h)['name'], k, looks.resolve(h)['look'] + '_HD'))
                for h in ORDER for k in ('blend', 'xps', 'pmx'))
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M')
    page = ['<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">',
            '<meta name="viewport" content="width=device-width, initial-scale=1">',
            '<title>Vindictus 高清版对比</title><style>%s</style></head><body><main>' % CSS,
            '<h1>洛奇英雄传 Vindictus（北美服）· 高清版（AI 放大）</h1>',
            '<p class="lead">每位女主角的游戏原版和高清版，同一机位渲染，<b>拖动图上的竖线</b>对比（左原版、右高清）。'
            '高清版用 AI 模型 4x-UltraSharp 把颜色贴图和服装 / 头发的染色遮罩放大 4 倍（最大 4096），法线、高光等遮罩保持游戏原尺寸；'
            '放大出来的细节是 AI 补的，游戏里本来没有。两边都按 10-31 修正后的贴图 Alpha 规则渲染（之前做的 .blend 里，脸部贴图 Alpha 里的遮罩'
            '会把眼周、唇线、鼻孔压暗），差别只来自贴图。原版不动，高清版在每位角色的 <code>&lt;外观&gt;_HD</code> 文件夹（.blend / XPS / PMX），'
            'PMX 在 MMD 里的名字带「·高清」。<a href="index.html">← 回到画廊</a>'
            '　<a href="%s" target="_blank">为什么选这个 AI 模型（三种模型对比）</a></p>' % uri(MODELS_SHEET),
            '<div class="stats"><span>高清版 <b>%d</b> / 19</span><span>三种格式共 <b>%.1f GB</b></span><span>生成于 %s</span></div>' % (
                n, total / 1073741824, now),
            '<section class="grid">'] + cards + ['</section></main>', JS, '</body></html>']
    open(a.out, 'w', encoding='utf-8').write('\n'.join(page))
    print(a.out, 'cards', len(cards), 'with HD', n)


if __name__ == '__main__':
    main()
