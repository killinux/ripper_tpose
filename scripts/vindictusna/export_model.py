r"""Export a Vindictus heroine: .blend with the game's materials at full texture resolution, + XPS and PMX.

    python export_model.py lynn                         # her look from looks.py (face, hair, outfit, colours)
    python export_model.py lynn --outfit valkyrie       # another armour set (python list_models.py --outfits)
    python export_model.py lynn --nude                  # the complete body, no outfit
    python export_model.py lynn --xps --pmx             # also XPS (XNALara) and MMD PMX
    python export_model.py --all --xps --pmx            # every heroine of looks.py
    python export_model.py lynn --redo                  # build again (otherwise an existing .blend is reused
                                                        #   for --xps / --pmx)

Output (E:\game_export\VindictusNA, scripts/archive layout):
    <Name>\blend\<Look>\<Look>.blend   + textures\ (relative), <Look>_front/_34/_side/_back/_face.png, 说明 text
    <Name>\xps\<Look>\<Look>.xps       + textures, blender2xps report
    <Name>\pmx\<Look>\<Look>.pmx       + textures\, <Look>_converted.blend
Work files (extracted game files, PNGs, configs, logs): VINDICTUSNA_WORK (default E:\tools\vindictusna).

How a look is put together (see README): every heroine stands on the same complete female body (the game shares
one body and skeleton between all of them), with her own face, hair and the outfit pieces on top; textures the
game data lacks are substituted and listed in the .blend's 说明 text.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import hfs  # noqa: E402
import looks  # noqa: E402
import textures  # noqa: E402

WORK = hfs.WORK
ROOT = os.path.join(WORK, 'root')
PNG = os.path.join(WORK, 'png')
STATS = os.path.join(WORK, 'stats.json')
EXPORT = os.environ.get('VINDICTUSNA_EXPORT', r'E:\game_export\VindictusNA')
BLENDER = os.environ.get('BLENDER', r'D:\Program Files\blender-3.6.15-windows-x64\blender.exe')
HDRI = os.path.join(os.path.dirname(BLENDER), '3.6', 'datafiles', 'studiolights', 'world', 'studio.exr')
TEX_KEYS = ('basetexture', 'basetexture2', 'bumpmap', 'normalmap', 'iris', 'hairmask', 'phongexponenttexture',
            'phongexponentmap', 'envmapmask', 'refracttinttexture', 'detail', 'selfillummask')
# the complete body (see looks.BODY): the closed inner-wear body + the player body's hands / feet + a clean leg
BODY_MDL = 'models/player/miri/miri_inner_2020_chn.mdl'
FIONA_MDL = 'models/player/fiona/fiona.mdl'
LYNN_ORIENTAL = 'models/player/lynn/lynn_inner_oriental_odyssey.mdl'


def lin(c):
    f = lambda x: (x / 255 / 12.92) if x / 255 <= 0.04045 else ((x / 255 + 0.055) / 1.055) ** 2.4
    return [round(f(x), 4) for x in c]


def local(game_path):
    return os.path.join(ROOT, game_path.replace('/', os.sep))


# ---------------------------------------------------------------------------------------------- game files
def fetch_models(paths):
    low = hfs.lower_index()
    names = []
    for p in paths:
        for ext in ('.mdl', '.vvd', '.dx90.vtx'):
            q = p.lower()[:-4] + ext
            if q in low:
                names.append(low[q])
            elif ext != '.dx90.vtx':
                raise SystemExit('not in the game data: %s' % q)
    hfs.fetch(ROOT, names)
    return [local(low[p.lower()]) for p in paths]


def fetch_materials(mdl_files, extra_materials=(), layers=()):
    """vmts of every material the models use (by their cd paths, else by name) + the textures those vmts name"""
    import source_mdl
    low = hfs.lower_index()
    by_base = {}
    for n in low:
        if n.endswith('.vmt'):
            by_base.setdefault(n.rsplit('/', 1)[-1][:-4], []).append(n)
    want = set()
    for f in mdl_files:
        sm = source_mdl.load_model(f)
        for mat in {me.material for bp in sm.bodyparts for md in bp.models for me in md.meshes}:
            b = mat.replace('\\', '/').lower().rsplit('/', 1)[-1]
            hit = next((q for cd in sm.cdtextures
                        for q in [('materials/' + cd.replace('\\', '/').lower() + b + '.vmt').replace('//', '/')]
                        if q in low), None)
            want.update([hit] if hit else by_base.get(b, [])[:3])
    for m in extra_materials:
        want.update(by_base.get(m.lower(), [])[:3])
    hfs.fetch(ROOT, [low[v] for v in want], quiet=True)
    vtfs = set()
    for v in want:
        try:
            t = re.sub(r'//[^\n]*', '', open(local(low[v]), errors='ignore').read())
        except OSError:
            continue
        for k, x in re.findall(r'"\$([a-z0-9_]+)"\s+"?([^"\r\n]*)"?', t, re.I):
            q = 'materials/' + x.strip().replace('\\', '/').lower().lstrip('/') + '.vtf'
            if k.lower() in TEX_KEYS and x.strip() and q.replace('.vtf.vtf', '.vtf') in low:
                vtfs.add(low[q.replace('.vtf.vtf', '.vtf')])
    for layer in layers:
        hits = [n for n in low if n.startswith('materials/models/player/face_layer/') and n.endswith('/%s.vtf' % layer.lower())]
        vtfs.update(low[h] for h in hits)
    hfs.fetch(ROOT, sorted(vtfs), quiet=True)
    n = textures.vtf_to_png([(local(v), os.path.join(PNG, v.rsplit('/', 1)[-1][:-4] + '.png')) for v in vtfs])
    textures.update_stats(STATS, PNG)
    # eyes: a full sclera beside the game's eyeball texture (build_blend.py puts both in the eye material behind a
    # switch; XPS / PMX bake the full one - their eye bones turn the ball)
    for v in want:
        try:
            t = re.sub(r'//[^\n]*', '', open(local(low[v]), errors='ignore').read())
        except OSError:
            continue
        if re.match(r'\s*"?eyes"?', t, re.I):
            k = re.search(r'"\$basetexture"\s+"?([^"\r\n]+)"?', t, re.I)
            if k:
                b = k.group(1).strip().replace('\\', '/').rsplit('/', 1)[-1].lower()
                src, dst = os.path.join(PNG, b + '.png'), os.path.join(PNG, b + '_sclera.png')
                if os.path.exists(src) and (not os.path.exists(dst) or os.path.getmtime(dst) < os.path.getmtime(src)):
                    textures.fill_sclera(src, dst)
    return len(want), len(vtfs), n


def vmt_base(material):
    """basetexture basename of a material's vmt anywhere under the extracted root"""
    m = material.lower() + '.vmt'
    for dp, _dn, fn in os.walk(os.path.join(ROOT, 'materials')):
        for f in fn:
            if f.lower() == m:
                t = re.sub(r'//[^\n]*', '', open(os.path.join(dp, f), errors='ignore').read())
                k = re.search(r'"\$basetexture"\s+"?([^"\r\n]+)"?', t, re.I)
                if k:
                    return k.group(1).strip().replace('\\', '/').rsplit('/', 1)[-1].lower()
    return None


def mats_of(mdl_file):
    import source_mdl
    sm = source_mdl.load_model(mdl_file)
    return sorted({me.material for bp in sm.bodyparts for md in bp.models for me in md.meshes})


# ---------------------------------------------------------------------------------------------- config
def body_spec(name):
    return {'mdl': local(BODY_MDL), 'collection': name, 'tag': 'body', 'skip_models': ['censor'],
            'hide_materials': ['pc_fiona_inner_2020contest_chn'],
            'uv_from': [{'material': 'miri_skin_body_hand', 'mdl': local(FIONA_MDL), 'src_material': 'fiona_skin_body01',
                         'use_material': 'miri_skin_body01'}],
            'feet_from': [{'material': 'miri_skin_body_hand', 'mdl': local(FIONA_MDL), 'src_material': 'fiona_skin_body01',
                           'use_material': 'miri_skin_body01', 'z_max': 12.0}],
            'replace_region': [{'material': 'miri_skin_body01', 'mdl': local(LYNN_ORIENTAL), 'src_material': 'fiona_skin_body01',
                                'x_range': [-30, 0], 'z_range': [5.0, 35.0]}]}


def make_config(look, files, figure=None):
    name, tag = look['name'], look['look']
    hair_c = look['hair_rgb']
    light = sum(hair_c) / 3 > 120
    brow_c = look.get('brow_rgb') or [int(c * (0.62 if light else 1.0)) for c in hair_c]
    hair_l = lin(hair_c)
    models = [body_spec(name)]
    face = {'mdl': files[look['face']['mdl']], 'collection': name, 'tag': 'face'}
    if look['face'].get('only'):
        face['only_materials'] = look['face']['only']
    face_mat = [m for m in (look['face'].get('only') or mats_of(face['mdl']))
                if 'skin_face' in m.lower() or m.lower().endswith('_face')][0]
    if look.get('borrow'):
        b = look['borrow']
        face['uv_from'] = [{'material': b['material'], 'mdl': files[b['mdl']], 'src_material': b['src_material'],
                            'use_material': b['src_material'], 'normal_match': 0.3, 'warp': True}]
        face_tex_mat = b['src_material']
    else:
        face_tex_mat = look.get('override', {}).get(face_mat.lower(), face_mat)
    models.append(face)
    hair = {'mdl': files[look['hair']['mdl']], 'collection': name, 'tag': 'hair'}
    if look['hair'].get('only'):
        hair['only_materials'] = look['hair']['only']
    if look.get('hide'):
        hair['hide_materials'] = look['hide']
    models.append(hair)
    hair_mats = look['hair'].get('only') or mats_of(hair['mdl'])
    for p in look['pieces']:
        part = os.path.basename(p)[:-4].rsplit('_', 1)[-1]
        spec = {'mdl': files[p], 'collection': look['outfit_name'], 'tag': 'outfit_' + part}
        if look.get('hide'):
            spec['hide_materials'] = look['hide']
        models.append(spec)

    comp = os.path.join(WORK, 'comp', tag)
    if os.path.isdir(comp):
        shutil.rmtree(comp)
    os.makedirs(comp)
    face_tex = vmt_base(face_tex_mat)
    if face_tex and look.get('brow'):
        src, brow = os.path.join(PNG, face_tex + '.png'), os.path.join(PNG, look['brow'] + '.png')
        if os.path.exists(src) and os.path.exists(brow):
            textures.composite(src, os.path.join(comp, face_tex + '.png'), [(brow, brow_c, 1.0)])
    hair_dyes = [lin(c) for c in look['hair_dyes']] if look.get('hair_dyes') else [hair_l] * 3
    out = os.path.join(WORK, 'build', tag)
    os.makedirs(out, exist_ok=True)
    alias = {'miri_skin_body01': 'fiona_skin_body01'}
    alias.update(look.get('alias', {}))
    cfg = {
        'name': name, 'tag': tag, 'scale': 0.0254, 'flip_normal_green': True, 'dye_gain': 2.0,
        'hdri': HDRI, 'hdri_strength': 0.8, 'key': 2.6, 'fill': 0.7, 'rim': 1.8,
        'models': models, 'material_roots': [ROOT], 'png_dirs': [comp, PNG], 'tex_stats': STATS,
        'alias': alias, 'override': look.get('override', {}),
        'solid': {k: (hair_l if c == 'hair' else lin(c)) for k, c in look.get('solid', {}).items()},
        'synth': {k: (x if isinstance(x, dict) else {'metal': x}) for k, x in look.get('synth', {}).items()},
        'force_dye': look.get('force_dye', []),
        'dye_default': [lin(c) for c in look['dyes']], 'dye': {m.lower(): hair_dyes for m in hair_mats},
        'face_hide': ['outfit_head'], 'render_dir': out, 'out_blend': os.path.join(out, tag + '.blend'),
        'views': {'front': [0, -1, 0.08], '34': [-0.7, -0.8, 0.1]}, 'res': [600, 900],
        'figure': figure,
    }
    path = os.path.join(WORK, 'cfg', tag + '.json')
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(cfg, open(path, 'w', encoding='utf-8'), indent=1, ensure_ascii=False)
    return path, cfg, face_tex, brow_c


# ---------------------------------------------------------------------------------------------- Blender steps
def blender(script, args, blend=None, log=None):
    cmd = [BLENDER, '-b']
    if blend:
        cmd.append(blend)
    cmd += ['--factory-startup', '--python', os.path.join(HERE, script), '--'] + list(args)
    t0 = time.time()
    with open(log, 'w', encoding='utf-8', errors='replace') if log else open(os.devnull, 'w') as fh:
        r = subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT)
    text = open(log, encoding='utf-8', errors='replace').read() if log else ''
    if r.returncode != 0 or 'Traceback' in text:
        tail = '\n'.join(l for l in text.splitlines() if l.strip())[-1500:]
        raise RuntimeError('%s failed (%s):\n%s' % (script, log, tail))
    return time.time() - t0, text


def export(hero, args):
    look = looks.resolve(hero, outfit=args.outfit, variant=args.variant, hair=args.hair, nude=args.nude,
                         head=args.head)
    name, tag = look['name'], look['look']
    blend_dir = os.path.join(EXPORT, name, 'blend', tag)
    blend = os.path.join(blend_dir, tag + '.blend')
    t0 = time.time()
    print('== %s  %s  (%s)' % (tag, look['cn'], ', '.join(os.path.basename(p) for p in look['pieces']) or 'nude'), flush=True)
    if args.redo or not os.path.exists(blend):
        paths = [look['face']['mdl'], look['hair']['mdl']] + look['pieces'] + [BODY_MDL, FIONA_MDL, LYNN_ORIENTAL]
        if look.get('borrow'):
            paths.append(look['borrow']['mdl'])
        local_files = fetch_models(paths)
        files = dict(zip(paths, local_files))
        extra = list(look.get('alias', {}).values()) + list(look.get('override', {}).values())
        n_vmt, n_vtf, n_new = fetch_materials(local_files, extra, [look['brow']] if look.get('brow') else [])
        print('  %d materials, %d textures (%d converted now)' % (n_vmt, n_vtf, n_new), flush=True)
        figure = None
        fig_name = 'csf/bodyshape_%s_default.fig' % look['hero']
        low = hfs.lower_index()
        if not args.no_figure and fig_name in low:
            hfs.fetch(ROOT, [low[fig_name]], quiet=True)
            figure = local(low[fig_name])
        cfg_path, cfg, face_tex, brow_c = make_config(look, files, figure)
        if args.prepare_only:
            print('  prepared: %s' % cfg_path, flush=True)
            return tag
        build_dir = os.path.dirname(cfg['out_blend'])
        sec, text = blender('build_blend.py', [cfg_path], log=os.path.join(build_dir, 'build.log'))
        print('  built in %.0fs' % sec, flush=True)
        note = os.path.join(build_dir, '说明.txt')
        open(note, 'w', encoding='utf-8').write(looks.note(look, cfg, text, face_tex, brow_c))
        if os.path.isdir(blend_dir):
            shutil.rmtree(blend_dir)
        sec, _ = blender('package_blend.py', [cfg['out_blend'], blend_dir, tag, note, 'outfit_head'],
                         log=os.path.join(build_dir, 'package.log'))
        print('  packaged in %.0fs -> %s' % (sec, blend), flush=True)
    if args.xps:
        out = os.path.join(EXPORT, name, 'xps', tag)
        if os.path.isdir(out):
            shutil.rmtree(out)
        sec, text = blender('export_xps_blender.py', ['--out', out, '--name', tag], blend=blend,
                            log=os.path.join(WORK, 'build', tag, 'xps.log'))
        res = json.loads(text.split('VINDICTUS_XPS=', 1)[1].splitlines()[0])
        print('  XPS %s: %d bones, %d meshes (%.0fs)' % ('ok' if res['ok'] else 'FAILED', res['bones'] or 0,
                                                        res['meshes'] or 0, sec), flush=True)
    if args.pmx:
        out = os.path.join(EXPORT, name, 'pmx', tag)
        sec, text = blender('export_pmx_blender.py', ['--out', out, '--name', tag, '--model-name', look['cn']],
                            blend=blend, log=os.path.join(WORK, 'build', tag, 'pmx.log'))
        res = json.loads(text.split('VINDICTUS_PMX=', 1)[1].splitlines()[0])
        print('  PMX: %d bones, %d rigid bodies, %d joints, torn %s (%.0fs)' % (
            res.get('bones', 0), res.get('rigid_bodies', 0), res.get('joints', 0),
            (res.get('distortion') or {}).get('torn'), sec), flush=True)
    print('  done in %.0fs' % (time.time() - t0), flush=True)
    return tag


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('heroes', nargs='*', help='internal hero names (python list_models.py)')
    ap.add_argument('--all', action='store_true', help='every heroine of looks.py')
    ap.add_argument('--outfit', help='armour set folder under models/armor/ (instead of the look\'s)')
    ap.add_argument('--variant', help='piece variant inside the set, e.g. create')
    ap.add_argument('--hair', help='hair model (game path or file name)')
    ap.add_argument('--head', action='store_true', help='include the outfit\'s head piece (hat / helmet)')
    ap.add_argument('--nude', action='store_true', help='the complete body only')
    ap.add_argument('--xps', action='store_true')
    ap.add_argument('--pmx', action='store_true')
    ap.add_argument('--redo', action='store_true', help='rebuild the .blend even if it exists')
    ap.add_argument('--prepare-only', action='store_true',
                    help='extract, convert and write the build config only (run once before parallel exports)')
    ap.add_argument('--no-figure', action='store_true',
                    help="keep the shared body's proportions (default: the heroine's own body shape from the game)")
    a = ap.parse_args()
    heroes = list(looks.HEROES) if a.all else a.heroes
    if not heroes:
        ap.print_help()
        return
    failed = []
    for h in heroes:
        try:
            export(h, a)
        except Exception as ex:          # noqa: BLE001 - report and go on with the next heroine
            print('  FAILED: %s' % ex, flush=True)
            failed.append(h)
    if failed:
        print('failed: %s' % ', '.join(failed))
        sys.exit(1)


if __name__ == '__main__':
    main()
