r"""The heroines and their default looks; resolve() turns a look (+ command-line overrides) into the parts to build,
note() writes the .blend's 说明 text.

Every look stands on the same complete body: the game shares one female body and skeleton between all heroines,
and models/player/miri/miri_inner_2020_chn.mdl is the one inner-wear body whose skin is closed under its garment
(that garment is hidden).  Its hand / foot texture is not in the data: the hands take the player body's
(fiona.mdl) UVs, the feet are the player body's own feet, and a garter band modelled into its right thigh is
swapped for the clean leg of lynn_inner_oriental_odyssey.mdl (export_model.body_spec).

Fields of a look:
  name / cn          file name / Chinese name
  face               face model (+ 'only': just these materials of a base model that also carries body / hair)
  borrow             the face texture is not in the data: take another face's texture - UVs from that face's
                     closest surface points, then one smooth map per UV island (build_blend.py uv_from + warp)
  hair               hair model (variant _01 = no headgear)
  outfit / variant   armour set folder under models/armor/ and an optional piece variant (e.g. create)
  alias / override   missing material -> another material (alias: only when missing; override: always)
  solid / hide / synth   missing scalp -> hair colour; missing parts hidden; missing metal -> plain metal
  brow               face layer baked onto the face texture, tinted after the hair
  hair_rgb / hair_dyes / dyes   colours (sRGB): the game's item colours live in its encrypted item database,
                     these are mine, chosen from the character art; every material's VindDye group can change them
"""
import os
import re

import hfs

rgb = lambda *c: list(c)

HEROES = {
    'fiona': dict(cn='菲欧娜', name='Fiona', outfit='valkyrie',
                  face=dict(mdl='models/player/fiona/fiona.mdl',
                            only=['fiona_skin_face01', 'fiona_eyeball_l01', 'fiona_eyeball_r01', 'fiona_eyelash01', 'fiona_teeth']),
                  hair=dict(mdl='models/npc/ceara/npc_ceara.mdl', only=['pc_fiona_ceara_hair', 'pc_fiona_ceara_hair_scalp']),
                  override={'fiona_skin_face01': 'pc_fiona_ceara_face', 'fiona_eyeball_l01': 'pc_fiona_ceara_eyeball_l01',
                            'fiona_eyeball_r01': 'pc_fiona_ceara_eyeball_r01'},
                  alias={'fiona_teeth': 'pc_fiona_ceara_teeth'}, brow=None,
                  hair_rgb=rgb(48, 32, 27), dyes=[rgb(222, 222, 228), rgb(212, 165, 70), rgb(36, 54, 110)]),
    'evy': dict(cn='伊菲', name='Evy', outfit='dorothy',
                face=dict(mdl='models/player/evy/evy.mdl',
                          only=['pc_evy_skin_face01', 'pc_evy_eyeball_l01', 'pc_evy_eyeball_r01', 'pc_evy_eyelash01', 'pc_evy_teeth']),
                borrow=dict(material='pc_evy_skin_face01', mdl='models/player/fiona/fiona.mdl', src_material='fiona_skin_face01'),
                override={'fiona_skin_face01': 'pc_fiona_ceara_face'},
                hair=dict(mdl='models/player/evy/evy_hair_pureshot_01.mdl'),
                alias={'pc_evy_pupil_l01': 'lynn_pupil_l01', 'pc_evy_pupil_r01': 'lynn_pupil_r01', 'pc_evy_teeth': 'lynn_teeth'},
                hide=['vella_hair_pureshot_scalp'], brow=None,
                hair_rgb=rgb(42, 30, 40), dyes=[rgb(64, 104, 186), rgb(240, 240, 240), rgb(150, 28, 40)]),
    'vella': dict(cn='维拉', name='Vella', outfit='dancingblade', variant='create',
                  face=dict(mdl='models/player/vella/vella_face01.mdl'),
                  borrow=dict(material='vella_skin_face01', mdl='models/player/lynn/pc_lynn_face01.mdl', src_material='lynn_skin_face'),
                  hair=dict(mdl='models/player/vella/pc_vella_hair_longblade_01.mdl'),
                  alias={'vella_eyeball_l01': 'lynn_eyeball_l01', 'vella_eyeball_r01': 'lynn_eyeball_r01',
                         'vella_eyelash01': 'lynn_eyelash', 'vella_teeth': 'lynn_teeth', 'vella_tong': 'latiya_tong'},
                  brow='lynn_brow01', hair_rgb=rgb(150, 38, 24), dyes=[rgb(150, 24, 30), rgb(30, 30, 34), rgb(200, 168, 88)]),
    'lynn': dict(cn='琳', name='Lynn', outfit='oriental_odyssey', head=True,
                 face=dict(mdl='models/player/lynn/pc_lynn_face01.mdl'),
                 hair=dict(mdl='models/player/lynn/pc_lynn_hair_apple_01.mdl'),
                 brow='lynn_brow01', hair_rgb=rgb(48, 32, 27), dyes=[rgb(165, 22, 32), rgb(236, 228, 212), rgb(22, 26, 40)]),
    'arisha': dict(cn='艾莉莎', name='Arisha', outfit='silverfox', variant='create',
                   face=dict(mdl='models/player/arisha/arisha.mdl',
                             only=['arisha_skin_face', 'arisha_eyeball_l01', 'arisha_eyeball_r01', 'arisha_eyelash', 'arisha_teeth']),
                   hair=dict(mdl='models/player/arisha/arisha_hair_silverfox_create_01.mdl'),
                   brow='arisha_brow01', hair_rgb=rgb(186, 160, 136), dyes=[rgb(232, 232, 236), rgb(120, 130, 150), rgb(40, 40, 48)]),
    'delia': dict(cn='黛莉娅', name='Delia', outfit='yukata_delia',
                  face=dict(mdl='models/player/delia/pc_delia_face01.mdl'),
                  hair=dict(mdl='models/player/delia/pc_delia_hair_crystal_rose_01.mdl'),
                  solid={'pc_delia_hair_crystal_rose_scalp': 'hair'}, synth={'pc_delia_hair_crystal_rose_metal': [0.95, 0.75, 0.4]},
                  brow='delia_brow01', hair_rgb=rgb(236, 214, 168), dyes=[rgb(226, 112, 146), rgb(246, 240, 230), rgb(56, 58, 118)]),
    'miri': dict(cn='芈璃', name='Miri', outfit='dragon_rises',
                 face=dict(mdl='models/player/miri/miri.mdl',
                           only=['miri_skin_face', 'miri_eyeball_l01', 'miri_eyeball_r01', 'miri_eyelash', 'miri_teeth']),
                 borrow=dict(material='miri_skin_face', mdl='models/player/lethor/lethor.mdl', src_material='lethor_skin_face'),
                 hair=dict(mdl='models/player/lynn/pc_lynn_hair_centipede_01.mdl'),
                 alias={'miri_pupil_l01': 'bel_pupil_l01', 'miri_pupil_r01': 'bel_pupil_r01', 'miri_teeth': 'lynn_teeth'},
                 brow='lethor_brow01', hair_rgb=rgb(26, 22, 24), dyes=[rgb(168, 28, 34), rgb(212, 165, 70), rgb(30, 30, 34)]),
    'miul': dict(cn='缪儿', name='Miul', outfit='devilhunter',
                 face=dict(mdl='models/player/miul/miul.mdl',
                           only=['miul_skin_face', 'miul_eyeball_l01', 'miul_eyeball_r01', 'miul_eyelash', 'miul_teeth']),
                 hair=dict(mdl='models/objects/m_mv/miul_mv/miul_cs2_hair.mdl'),
                 brow='miul_brow01', hair_rgb=rgb(226, 226, 232), dyes=[rgb(30, 30, 36), rgb(200, 200, 212), rgb(140, 20, 40)]),
    'bel': dict(cn='蓓尔', name='Bel', outfit='white_shark', variant='create',
                face=dict(mdl='models/player/bel/pc_bel_face01.mdl'),
                hair=dict(mdl='models/player/bel/bel_hair_sb_pony_01.mdl'),
                brow='bel_brow01', hair_rgb=rgb(88, 186, 182), dyes=[rgb(236, 236, 240), rgb(40, 60, 90), rgb(88, 186, 182)]),
    'lethor': dict(cn='蕾希', name='Lethor', outfit='kitsunemiko',
                   face=dict(mdl='models/player/lethor/pc_lethor_face01.mdl'),
                   hair=dict(mdl='models/player/lethor/pc_lethor_hair_crest_master_01.mdl'),
                   brow='lethor_brow01', hair_rgb=rgb(30, 30, 46), hair_dyes=[rgb(30, 30, 46), rgb(70, 44, 104), rgb(30, 30, 46)],
                   dyes=[rgb(242, 242, 242), rgb(176, 28, 38), rgb(190, 150, 70)]),
    'tessa': dict(cn='泰莎', name='Tessa', outfit='venetian',
                  face=dict(mdl='models/player/tessa/pc_tessa_face01.mdl'),
                  hair=dict(mdl='models/player/tessa/pc_tessa_hair_grace_01.mdl'),
                  brow='tessa_brow01', hair_rgb=rgb(238, 204, 214), hair_dyes=[rgb(238, 204, 214), rgb(226, 160, 186), rgb(238, 204, 214)],
                  dyes=[rgb(116, 38, 88), rgb(232, 212, 222), rgb(200, 168, 88)]),
    'danah': dict(cn='丹雅', name='Danah', outfit='rurosakura',
                  face=dict(mdl='models/player/danah/pc_danah_face01.mdl'),
                  hair=dict(mdl='models/player/danah/pc_danah_hair_chaste_01.mdl'),
                  solid={'pc_danah_hair_chaste_scalp': 'hair'}, hide=['pc_danah_hair_chaste_translucent'],
                  brow='danah_brow01', hair_rgb=rgb(22, 20, 22), dyes=[rgb(150, 24, 34), rgb(240, 236, 226), rgb(30, 30, 34)]),
    'letty': dict(cn='蕾媞', name='Letty', outfit='maid',
                  face=dict(mdl='models/player/letty/pc_letty_face01.mdl'),
                  hair=dict(mdl='models/player/letty/pc_letty_hair_applelong_01.mdl'),
                  brow='letty_brow01', hair_rgb=rgb(244, 214, 224), hair_dyes=[rgb(244, 214, 224), rgb(236, 168, 196), rgb(244, 214, 224)],
                  dyes=[rgb(30, 30, 40), rgb(246, 246, 246), rgb(228, 148, 178)]),
    'latiya': dict(cn='拉缇雅', name='Latiya', outfit='ninja',
                   face=dict(mdl='models/player/latiya/pc_latiya_face01.mdl'),
                   hair=dict(mdl='models/player/latiya/pc_latiya_hair_part_braid_01.mdl'),
                   brow='latiya_brow01', hair_rgb=rgb(28, 34, 52), hair_dyes=[rgb(28, 34, 52), rgb(44, 54, 88), rgb(28, 34, 52)],
                   dyes=[rgb(30, 32, 46), rgb(140, 28, 40), rgb(180, 180, 190)]),
    'czern': dict(cn='萨恩', name='Czern', outfit='western',
                  face=dict(mdl='models/player/czern/pc_czern_face01.mdl'),
                  hair=dict(mdl='models/player/czern/pc_czern_hair_sideponytail_01.mdl'),
                  brow='czern_brow01', hair_rgb=rgb(232, 234, 240), hair_dyes=[rgb(234, 236, 242), rgb(150, 170, 204), rgb(78, 108, 168)],
                  dyes=[rgb(118, 78, 50), rgb(230, 224, 208), rgb(58, 88, 138)]),
    'sanyaa': dict(cn='纱妮娅', name='Sanyaa', outfit='darknight',
                   face=dict(mdl='models/player/sanyaa/pc_sanyaa_face01.mdl'),
                   hair=dict(mdl='models/player/sanyaa/pc_sanyaa_hair_default_01.mdl'),
                   brow='sanyaa_brow01', hair_rgb=rgb(214, 220, 230), dyes=[rgb(30, 30, 40), rgb(170, 180, 200), rgb(58, 88, 168)]),
    'neamhain': dict(cn='内文', name='Neamhain', outfit='shiningwill',
                     face=dict(mdl='models/player/neamhain/pc_neamhain_face01.mdl'),
                     hair=dict(mdl='models/player/neamhain/pc_neamhain_hair_default_01.mdl'),
                     brow='neamhain_brow01', hair_rgb=rgb(238, 158, 50), dyes=[rgb(240, 236, 222), rgb(212, 165, 70), rgb(118, 38, 40)]),
    'calia': dict(cn='卡莉亚', name='Calia', outfit='calia_armor2',
                  face=dict(mdl='models/player/calia/pc_calia_face01.mdl'),
                  hair=dict(mdl='models/player/calia/pc_calia_hair_default_01.mdl'),
                  solid={'pc_calia_hair_default_01_scalp': 'hair'},
                  hide=['pc_calia_hair_default_01_trans', 'pc_female_calia_armor1_hairacc'],
                  synth={'pc_female_calia_armor2_onepiece_metal': [0.86, 0.87, 0.9]},
                  brow='calia_brow01', hair_rgb=rgb(200, 230, 220), dyes=[rgb(230, 234, 240), rgb(88, 138, 150), rgb(40, 40, 50)]),
    'lumielle': dict(cn='露米艾尔', name='Lumielle', outfit='highelf',
                     face=dict(mdl='models/player/lumielle/pc_lumielle_face01.mdl'),
                     hair=dict(mdl='models/player/arisha/arisha_hair_silverfox_01.mdl'),
                     brow='lumielle_brow01', hair_rgb=rgb(234, 208, 148), dyes=[rgb(240, 240, 234), rgb(186, 198, 148), rgb(212, 174, 90)]),
}
OUTFIT_NAME = {'valkyrie': 'Valkyrie', 'dorothy': 'Dorothy', 'dancingblade': 'DancingBlade', 'silverfox': 'SilverFox',
               'yukata_delia': 'Yukata', 'dragon_rises': 'DragonRises', 'devilhunter': 'DevilHunter',
               'white_shark': 'WhiteShark', 'kitsunemiko': 'KitsuneMiko', 'venetian': 'Venetian',
               'rurosakura': 'RuroSakura', 'maid': 'Maid', 'ninja': 'Ninja', 'western': 'Western', 'darknight': 'DarkKnight',
               'shiningwill': 'ShiningWill', 'calia_armor2': 'CaliaArmor2', 'highelf': 'HighElf',
               'oriental_odyssey': 'OrientalOdyssey'}
OUTFIT_CN = {'valkyrie': '女武神', 'dorothy': '多萝西', 'dancingblade': '舞刃', 'silverfox': '银狐', 'yukata_delia': '黛莉娅浴衣',
             'dragon_rises': '龙腾', 'devilhunter': '恶魔猎人', 'white_shark': '白鲨', 'kitsunemiko': '狐巫女', 'venetian': '威尼斯',
             'rurosakura': '流浪樱', 'maid': '女仆', 'ninja': '忍者', 'western': '西部', 'darknight': '暗夜骑士',
             'shiningwill': '闪耀意志', 'calia_armor2': '卡莉亚专属第二套', 'highelf': '高等精灵', 'oriental_odyssey': '东方奥德赛'}
SKIP = ('_ex_', '_vol', '_mv', '_broken', 'cloth_test', '_minor', '_twopiece', '_delete', '_us_')
PARTS = ('onepiece', 'upper', 'lower', 'hand', 'foot', 'head')


def part_of(base):
    return next((p for p in PARTS if '_' + p in base), 'other')


def outfit_pieces(set_dir, variant=None, head=False):
    """onepiece (else upper + lower) + hand + foot (+ head) of an armour set, from the catalogue"""
    pre = 'models/armor/%s/' % set_dir.lower().strip('/')
    names = sorted(n for n in hfs.lower_index() if n.startswith(pre) and n.endswith('.mdl') and n.count('/') == pre.count('/'))
    if not names:
        raise SystemExit('no armour set models/armor/%s (python list_models.py --outfits)' % set_dir)
    base = [n.rsplit('/', 1)[-1][:-4] for n in names]
    base = [b for b in base if not any(x in b for x in SKIP) and (b.startswith('pc_female') or b.startswith('pc_fiona')
                                                                   or b.startswith('pc_evy') or b.startswith('female'))]
    if variant:
        base = [b for b in base if '_%s_' % variant in b] or base
    else:
        base = [b for b in base if '_create_' not in b]
    by_part = {}
    for b in sorted(base, key=lambda b: (not b.startswith('pc_female'), len(b))):
        by_part.setdefault(part_of(b), b)
    parts = ['onepiece'] if 'onepiece' in by_part else ['upper', 'lower']
    parts += ['hand', 'foot'] + (['head'] if head else [])
    return [pre + by_part[p] + '.mdl' for p in parts if p in by_part]


def resolve(hero, outfit=None, variant=None, hair=None, nude=False, head=False):
    if hero not in HEROES:
        raise SystemExit('unknown heroine %r; known: %s' % (hero, ', '.join(HEROES)))
    look = dict(HEROES[hero])
    look['hero'] = hero
    if hair:
        h = hair.lower().replace('\\', '/')
        if '/' not in h:
            h = next((n for n in hfs.lower_index() if n.endswith('/' + h if h.endswith('.mdl') else '/' + h + '.mdl')), h)
        look['hair'] = dict(mdl=h)
    if outfit:
        look['outfit'], look['variant'] = outfit, variant
    elif variant:
        look['variant'] = variant
    look['head'] = head or look.get('head', False)
    if nude:
        look['outfit'] = None
        look['pieces'] = []
        look['outfit_name'] = 'Nude'
    else:
        look['pieces'] = outfit_pieces(look['outfit'], look.get('variant'), look['head'])
        look['outfit_name'] = OUTFIT_NAME.get(look['outfit'], ''.join(w.title() for w in re.split(r'[_/]', look['outfit'])))
    look['look'] = '%s_%s' % (look['name'], look['outfit_name'])
    return look


def note(look, cfg, build_log, face_tex, brow_rgb):
    """the .blend's 说明 text (Chinese)"""
    cn = look['cn']
    oc = OUTFIT_CN.get(look['outfit'] or '', look['outfit'] or '')
    L = ['洛奇英雄传 Vindictus（北美服）%s · %s —— 说明' % (cn, oc or '裸体'), '',
         '来源',
         '  游戏：%s（NEXON，Source 引擎），从 .hfs 包里读出（scripts/vindictusna）' % hfs.GAME_DIR,
         '  身体：models/player/miri/miri_inner_2020_chn.mdl —— 所有女角色共用一副身体和骨架；',
         '        这是内衬模型里唯一一副衣服下面皮肤完整的身体，它那件小内衣藏在「_未使用的默认部件」里',
         '  脸：  %s%s' % (look['face']['mdl'], '（只取脸部：%s）' % '、'.join(look['face']['only']) if look['face'].get('only') else ''),
         '  头发：%s' % look['hair']['mdl']]
    if look['pieces']:
        L += ['  服装：models/armor/%s/ —— %s' % (look['outfit'], '、'.join(os.path.basename(p)[:-4] for p in look['pieces'])),
              '        （服装中文名是游戏内部文件名的意译，不是官方名；官方道具名在加密的道具库里，没有读取）']
    L.append('')
    fix = []
    if look.get('override') and look['hero'] == 'fiona':
        fix.append('脸：菲欧娜自己的脸部贴图对不上她的脸部网格，用游戏里和她同脸的 NPC「Ceara」的脸、眼睛贴图和头发。')
    if look.get('borrow'):
        b = look['borrow']
        fix.append('脸部贴图：%s 的脸部皮肤贴图（%s）游戏包里没有。脸型用她自己的网格，贴图借用 %s 的脸（%s）：'
                   '先按三维位置取对方脸面上最近点的贴图坐标，再按每块贴图区域拟合一个平滑映射（五官不会被撕开）。'
                   '妆容来自别人的脸，只是借用，不是她的原貌。' % (cn, b['material'], b['mdl'].split('/')[2], b['src_material']))
    if look.get('alias'):
        fix.append('游戏包里缺的贴图换成别的角色的同类贴图：' + '；'.join('%s → %s' % kv for kv in look['alias'].items()) + '。')
    if look.get('solid'):
        fix.append('头皮贴图游戏包里没有（%s），改成和头发同色的纯色材质。' % '、'.join(look['solid']))
    if look.get('hide'):
        fix.append('贴图游戏包里没有的部件隐藏在「_未使用的默认部件」里：%s。' % '、'.join(look['hide']))
    if look.get('synth'):
        fix.append('金属部件贴图游戏包里没有（%s），做成纯金属材质。' % '、'.join(look['synth']))
    if look.get('brow'):
        fix.append('眉毛：游戏运行时把捏脸图层叠到脸上，这里把 face_layer 的 %s 预先叠进脸部贴图（%s），颜色 RGB%s。'
                   % (look['brow'], face_tex, tuple(brow_rgb)))
    m = re.search(r'figure (\S+): (\d+) bones shaped', build_log)
    if m:
        fix.append('体型：游戏给每位角色定了默认体型（csf/%s，%s 根骨骼的缩放，比如小腿、手臂粗细和腿长），'
                   '已按游戏的方式加到骨骼上并烘焙进网格和骨架（静止姿势就是她的体型）。' % (m.group(1), m.group(2)))
    fix.append('手和脚：这副身体的手脚贴图游戏包里没有。手借用玩家身体（fiona.mdl）的贴图坐标，脚换成玩家身体自己的脚；'
               '右大腿上的吊袜带凸起换成了琳的东方内衬里干净的右腿。')
    L += ['我补 / 修的部分（游戏数据里没有或有问题的）'] + ['  %d. %s' % (i + 1, t) for i, t in enumerate(fix)] + ['']
    L += ['颜色',
          '  服装和头发的贴图是染色遮罩（R / G / B 三个染色槽），游戏按玩家选的颜色上色；默认配色在加密的道具库里，没有读取。',
          '  这里的颜色是按角色立绘配的：头发 RGB%s；服装 染色1 RGB%s / 染色2 RGB%s / 染色3 RGB%s。' % (
              tuple(look['hair_rgb']), *[tuple(c) for c in look['dyes']]),
          '  每个材质里的「VindDye」节点组可以改：染色1(R) / 染色2(G) / 染色3(B) / 强度 Gain。', '',
          '结构',
          '  %s_rig   骨架（ValveBiped，游戏原名），所有网格都绑在上面，可以摆姿势' % look['name'],
          '  %s        身体、手、脚、脸、眼睛、睫毛、牙齿、头发' % look['name']]
    if look['pieces']:
        L.append('  %s   服装' % look['outfit_name'])
    L += ['',
          '材质：法线贴图是 DirectX 规范（绿通道已翻转接入）；皮肤次表面散射按真实皮肤（红 3.6 / 绿 1.35 / 蓝 0.75 毫米）；',
          '      金属件按游戏的 $surface metal；头发各向异性高光。',
          '灯光：3 盏平行光 + Blender 自带的 studio 环境贴图（只用于反射和补光，背景是纯色）。',
          '单位：1 游戏单位 = 1 英寸（0.0254 米），人物身高约 1.84 米（游戏原比例）。']
    miss = sorted(set(re.findall(r'MAT (\S+)\s+\S*\s+kind=\S+\s+dye=\S+\s+base=None', build_log)))
    miss = [m for m in miss if m.lower() not in {'pc_fiona_inner_2020contest_chn', 'miri_skin_body_hand'}
            and m.lower() not in {x.lower() for x in look.get('hide', [])}
            and not (look.get('borrow') and m.lower() == look['borrow']['material'].lower())]
    if miss:
        L += ['', '仍然没有贴图的材质（显示为灰色）：' + '、'.join(miss)]
    return '\n'.join(L) + '\n'


# ------------------------------------------------------------------------------------------------ NPCs / bosses
# Female NPCs and bosses whose textures are in the NA data (10-31 survey: list_models-style material check, breast-bone
# skin weights for the gender).  Each is ONE complete game model (body, face, hair, clothes) - no assembly.
# Not here: Alice (built from Lann's face / hair and a male raiment: not a woman), Lady's mate (= lady.mdl, smaller),
# Iset's story / playable copies; the bosses with missing textures need a name remap first (see README).
NPC_DYES = [rgb(200, 200, 206), rgb(56, 60, 74), rgb(190, 160, 92)]
NPCS = {
    'ceara': dict(name='Ceara', cn='Ceara', kind='剧情 NPC', look='Ceara', models=['models/npc/ceara/npc_ceara.mdl'],
                  csf='csf/npc_ceara.csf', hair_mats=['pc_fiona_ceara_hair', 'pc_fiona_ceara_hair_scalp'],
                  about='主线剧情的女主角级 NPC；菲欧娜的脸和头发就是借她的'),
    'eire': dict(name='Eire', cn='Eire', kind='剧情 NPC', look='Eire', models=['models/npc/eire/npc_eire.mdl'],
                 about='第二季剧情 NPC（模型的事件表是第二季 Crom Cruach、Elahan 两段结局过场）'),
    'iset_npc': dict(name='Iset', cn='Iset（NPC 版）', kind='剧情 NPC', look='Iset_NPC', models=['models/npc/iset/npc_iset.mdl'],
                     about='穿长袍、戴兜帽的 NPC 版'),
    'dwyn': dict(name='Dwyn', cn='Dwyn', kind='剧情 NPC', look='Dwyn', models=['models/npc/female/dwyn_face.mdl'],
                 override={'kadan_teeth': 'lynn_teeth'}, dyes=[rgb(196, 198, 204), rgb(44, 58, 104), rgb(196, 162, 84)],
                 hide=['pc_uni_knightplate2_head', 'pc_uni_knightplate2_feather'],
                 hide_why='头盔和羽饰是第 8 章过场里拿在手上的道具（整个挂在 bone_helmet 骨上，绑定姿势下飘在头左边约 60 厘米）',
                 about='骑士板甲，露脸的版本（dwyn_face.mdl，第 8 章过场用；dwyn.mdl 是戴头盔不露脸的）'),
    'dwyn_helmet': dict(name='Dwyn', cn='Dwyn（戴头盔）', kind='剧情 NPC', look='Dwyn_Helmet',
                        models=['models/npc/female/dwyn.mdl'],
                        dyes=[rgb(196, 198, 204), rgb(44, 58, 104), rgb(196, 162, 84)],
                        about='骑士板甲戴头盔、不露脸的版本（dwyn.mdl；露脸的是 dwyn_face.mdl）'),
    'lady': dict(name='Lady', cn='Lady（人偶）', kind='女性 Boss', look='Lady', models=['models/monster/lady/lady.mdl'],
                 about='人偶 Boss（伙伴版 lady_mate.mdl 是同一个网格，小一号）'),
    'iset_boss': dict(name='Iset', cn='Iset（Boss 版）', kind='女性 Boss', look='Iset_Boss', models=['models/monster/iset/iset.mdl'],
                      about='Boss 战的本体（另有剧情版 iset_story.mdl、国服可操作版 iset_playable.mdl）'),
}


def csf_colours(path):
    """a costume preset (csf/*.csf, KeyValues: one block per slot with "sn" item number and "color") ->
    {slot: [[r, g, b] or None] x 3}.  The colours are packed 0xRRGGBB: npc_ceara.csf's hair 9966098 = (152, 18, 18),
    the dark red of her portrait (scaleform/npc_portrait/ceara.dds).  -1 = no colour."""
    t = open(path, encoding='utf-8', errors='ignore').read()
    out = {}
    for name, body in re.findall(r'"(\w+)"\s*\{([^{}]*)\}', t):
        m = re.search(r'"color"\s+"([-\d ]+)"', body)
        if m:
            out[name.lower()] = [[(v >> 16) & 255, (v >> 8) & 255, v & 255] if v >= 0 else None
                                 for v in map(int, m.group(1).split())]
    return out


def resolve_npc(key):
    look = dict(NPCS[key])
    look.update(hero=key, npc=True, pieces=[], outfit=None, outfit_name=look['look'])
    look.setdefault('dyes', NPC_DYES)
    return look


def note_npc(look, cfg, build_log):
    """the .blend's 说明 text for an NPC / boss (one complete game model)"""
    L = ['洛奇英雄传 Vindictus（北美服）%s —— 说明' % look['cn'], '',
         '来源',
         '  游戏：%s（NEXON，Source 引擎），从 .hfs 包里读出（scripts/vindictusna）' % hfs.GAME_DIR,
         '  模型：%s —— %s，一个完整的游戏模型（身体、脸、头发、衣服都在里面），没有拼装' % ('、'.join(look['models']), look['kind']),
         '  %s' % look.get('about', ''), '']
    fix = []
    if look.get('override'):
        fix.append('游戏包里缺贴图的材质整个换成别的角色的同类材质：' + '；'.join('%s → %s' % kv for kv in look['override'].items()) + '。')
    if look.get('hide'):
        fix.append('默认隐藏 %s：%s。.blend 里取消隐藏就能看到；XPS / PMX 里不带。' % ('、'.join(look['hide']), look.get('hide_why', '')))
    if fix:
        L += ['我补 / 修的部分'] + ['  %d. %s' % (i + 1, t) for i, t in enumerate(fix)] + ['']
    dyed = sorted(set(re.findall(r'MAT (\S+)\s+\S*\s+kind=\S+\s+dye=True', build_log)))
    if look.get('csf') and cfg.get('dye'):
        L += ['颜色（游戏官方）',
              '  头发按游戏里这个 NPC 的外观预设 %s 上色（%s）：%s。' % (
                  look['csf'], '、'.join(cfg['dye']), ' / '.join('RGB(%d, %d, %d)' % tuple(c) for c in look.get('hair_rgb', []))), '']
        dyed = [m for m in dyed if m.lower() not in cfg['dye']]
    if dyed:
        L += ['颜色',
              '  这些材质的贴图是染色遮罩（R / G / B 三个染色槽）：%s。游戏给 NPC 上什么颜色没有读到，这里的颜色是我配的：' % '、'.join(dyed),
              '  染色1 RGB%s / 染色2 RGB%s / 染色3 RGB%s；每个材质里的「VindDye」节点组可以改。' % tuple(tuple(c) for c in look['dyes']), '']
    L += ['结构',
          '  %s_rig   骨架（ValveBiped，游戏原名），所有网格都绑在上面，可以摆姿势' % look['name'],
          '  %s        模型' % look['name'], '',
          '材质：法线贴图是 DirectX 规范（绿通道已翻转接入）；皮肤次表面散射按真实皮肤（红 3.6 / 绿 1.35 / 蓝 0.75 毫米）。',
          '灯光：3 盏平行光 + Blender 自带的 studio 环境贴图（只用于反射和补光，背景是纯色）。',
          '单位：1 游戏单位 = 1 英寸（0.0254 米），游戏原比例。']
    miss = sorted(set(re.findall(r'MAT (\S+)\s+\S*\s+kind=\S+\s+dye=\S+\s+base=None', build_log)))
    if miss:
        L += ['', '仍然没有贴图的材质（显示为灰色）：' + '、'.join(miss)]
    return '\n'.join(L) + '\n'
