r"""What the game has: heroines (faces, hairs, inner wear) and the female armour sets, with texture status.

    python list_models.py                       # heroines: face / hair / inner-wear models, missing textures
    python list_models.py --hairs lynn          # every hair model of one heroine
    python list_models.py --outfits             # female armour sets (pieces, complete = every texture in the data)
    python list_models.py --outfits --complete --grep plate

The first --outfits run reads ~4,600 piece models and their materials (a few minutes, 8 processes); the result is
cached in <work>\outfits.json and refreshed with --rescan.
"""
import argparse
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hfs  # noqa: E402

ROOT = os.path.join(hfs.WORK, 'root')
OUTFITS = os.path.join(hfs.WORK, 'outfits.json')
SKIP_PIECE = re.compile(r'_(broken|mv)\d*$|_broken|cloth_test')


def heroines():
    """female heroes = the game's own animation folders models/player/_anim/female/<hero>/"""
    out = set()
    for n in hfs.lower_index():
        m = re.match(r'models/player/_anim/female/([^/]+)/', n)
        if m:
            out.add(m.group(1))
    return sorted(out)


def material_status(mdl_names):
    """{mdl: {material: vmt folder or None}} - a material counts when its vmt exists and its $basetexture vtf too"""
    from roster_lite import mdl_info
    low = hfs.lower_index()
    hfs.fetch(ROOT, [low[m] for m in mdl_names if m in low], procs=8, quiet=True)
    by_base = {}
    for n in low:
        if n.endswith('.vmt'):
            by_base.setdefault(n.rsplit('/', 1)[-1][:-4], []).append(n)
    vtf = {n for n in low if n.endswith('.vtf')}
    info, want = {}, set()
    for m in mdl_names:
        p = os.path.join(ROOT, low.get(m, m).replace('/', os.sep))
        inf = mdl_info(p) if os.path.exists(p) else None
        info[m] = inf
        for t in (inf or {}).get('textures', []):
            want.update(by_base.get(t.replace('\\', '/').lower().rsplit('/', 1)[-1], [])[:3])
    hfs.fetch(ROOT, [low[v] for v in want], procs=8, quiet=True)
    cache = {}

    def ok(t):
        if t in cache:
            return cache[t]
        cache[t] = None
        for v in by_base.get(t, []):
            try:
                s = re.sub(r'//[^\n]*', '', open(os.path.join(ROOT, low[v].replace('/', os.sep)), errors='ignore').read())
            except OSError:
                continue
            k = re.search(r'"\$basetexture"\s+"?([^"\r\n]+)"?', s, re.I)
            if k and 'materials/' + k.group(1).strip().replace('\\', '/').lower() + '.vtf' in vtf:
                cache[t] = v.rsplit('/', 1)[0]
                break
        return cache[t]
    res = {}
    for m, inf in info.items():
        if inf:
            res[m] = {t.replace('\\', '/').lower().rsplit('/', 1)[-1]: ok(t.replace('\\', '/').lower().rsplit('/', 1)[-1])
                      for t in inf['textures']}
    return res


def show_heroines(only=None, hairs=False):
    low = hfs.lower_index()
    for h in heroines():
        if only and h != only:
            continue
        d = 'models/player/%s/' % h
        fs = sorted(n for n in low if n.startswith(d) and n.endswith('.mdl') and n.count('/') == 3)
        base = [n for n in fs if n in (d + h + '.mdl', d + 'pc_' + h + '.mdl')]
        faces = [n for n in fs if re.search(r'face0?\d\.mdl$', n)]
        hair = [n for n in fs if 'hair' in n.rsplit('/', 1)[-1] and (hairs or re.search(r'_0?1\.mdl$', n))]
        inner = [n for n in fs if '_inner_' in n.rsplit('/', 1)[-1]]
        st = material_status(base + faces + hair + inner)
        print('== %s' % h)
        for kind, lst in (('base', base), ('face', faces), ('hair', hair), ('inner', inner)):
            for n in lst:
                miss = [t for t, v in st.get(n, {}).items() if not v and t != 'glint']
                print('   %-5s %-52s %s' % (kind, n.rsplit('/', 1)[-1], ('missing ' + ', '.join(miss)) if miss else 'ok'))


def scan_outfits():
    low = hfs.lower_index()
    pieces = sorted(n for n in low if n.startswith('models/armor/') and n.endswith('.mdl')
                    and (n.rsplit('/', 1)[-1].startswith(('pc_female', 'pc_fiona', 'pc_evy', 'female_')))
                    and not SKIP_PIECE.search(n.rsplit('/', 1)[-1][:-4]))
    print('reading %d female armour pieces ...' % len(pieces), flush=True)
    st = material_status(pieces)
    sets = {}
    for n in pieces:
        sd = '/'.join(n.split('/')[2:-1])
        b = n.rsplit('/', 1)[-1][:-4]
        mats = st.get(n, {})
        s = sets.setdefault(sd, {'pieces': {}, 'missing': set()})
        s['pieces'][b] = sorted(mats)
        s['missing'].update(t for t, v in mats.items() if not v and t != 'glint')
    out = {k: {'pieces': v['pieces'], 'missing': sorted(v['missing']), 'complete': not v['missing']}
           for k, v in sorted(sets.items())}
    json.dump(out, open(OUTFITS, 'w'), indent=1)
    return out


def show_outfits(complete=False, grep=None, rescan=False):
    data = json.load(open(OUTFITS)) if os.path.exists(OUTFITS) and not rescan else scan_outfits()
    n = 0
    for k, v in data.items():
        if complete and not v['complete']:
            continue
        if grep and not re.search(grep, k, re.I):
            continue
        parts = sorted({p for b in v['pieces'] for p in ('onepiece', 'upper', 'lower', 'hand', 'foot', 'head') if '_' + p in b})
        print('%-40s %-9s %-40s %s' % (k, 'complete' if v['complete'] else 'missing', ','.join(parts),
                                       ', '.join(v['missing'][:3]) + (' ...' if len(v['missing']) > 3 else '')))
        n += 1
    print('%d sets (%d complete of %d)' % (n, sum(v['complete'] for v in data.values()), len(data)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--hairs', metavar='HERO')
    ap.add_argument('--hero')
    ap.add_argument('--outfits', action='store_true')
    ap.add_argument('--complete', action='store_true')
    ap.add_argument('--grep')
    ap.add_argument('--rescan', action='store_true')
    a = ap.parse_args()
    if a.outfits:
        show_outfits(a.complete, a.grep, a.rescan)
    elif a.hairs:
        show_heroines(a.hairs, hairs=True)
    else:
        show_heroines(a.hero)


if __name__ == '__main__':
    main()
