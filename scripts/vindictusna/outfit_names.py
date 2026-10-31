"""Chinese names for the 451 female armour sets (models/armor/<set>/pc_female_*).

The official names live in the encrypted item database (sqlite/heroes.db3) and are not read, so these are
translations of the internal folder names (myth names transliterated, '?' = unsure). kind() sorts a set into the
catalogue's groups."""
import re

CN = {
    # dated / event sets
    '2014_hanbok': '2014 韩服', '2015setubun': '2015 节分祭', '2016_summer': '2016 夏日', '2017_beginner': '2017 新手装',
    '2017_hanbok': '2017 韩服', '2017contest': '2017 设计大赛', '2019_bind': '2019 绑带', '2020contest_chn': '2020 设计大赛（国服）',
    '2020contest_tw': '2020 设计大赛（台服）', '2021contest_tw': '2021 设计大赛（台服）', '2021contest_usa': '2021 设计大赛（美服）',
    '2021dino': '2021 恐龙', '2021openwaist': '2021 露腰装', '2022_ti': '2022 缇同款', '2022_ti_test': '2022 缇同款（测试）',
    '2022ninja': '2022 忍者', '2022qipao': '2022 旗袍', '2023_arme_v2': '2023 Arme v2', '2023_edgebikini': '2023 镶边比基尼',
    '2023_golfwear': '2023 高尔夫装', '2023_goth': '2023 哥特', '2023_gremlin': '2023 小魔怪', '2023_highleg': '2023 高衩',
    '2023_latex': '2023 乳胶衣', '2023_lingerie': '2023 内衣', '2023_mixplate': '2023 混合板甲', '2023_neamhain': '2023 内文同款',
    '2023_onmyoji': '2023 阴阳师', '2023_open_shoulder': '2023 露肩装', '2023_oriental_armor': '2023 东方铠甲',
    '2023_pilot_suit_girl': '2023 驾驶员战斗服', '2023_plate': '2023 板甲', '2023_purebikini': '2023 纯色比基尼',
    '2023_sexysister': '2023 性感修女', '2023_techwearninja': '2023 机能风忍者', '2023_vanhelsing': '2023 范海辛',
    '2024_bloomers': '2024 体操灯笼裤', '2024_brigit': '2024 布丽吉特同款', '2024_chinadress': '2024 中国风连衣裙',
    '2024_chinesedress': '2024 中式礼服', '2024_dress': '2024 礼服裙', '2024_jailer_cosplay': '2024 狱卒 cos',
    '2024_leggings': '2024 打底裤', '2024_leotard': '2024 紧身体操服', '2024_maid': '2024 女仆', '2024_milkcow': '2024 奶牛装',
    '2024_navy_officer': '2024 海军军官', '2024_racequeen': '2024 赛车女郎', '2024_succubus': '2024 魅魔',
    '2024_swimsuit_a': '2024 泳装 A', '2024_swimsuit_b': '2024 泳装 B', '2025_apron': '2025 围裙', '2025_barbary': '2025 巴巴里海盗',
    '2025_bikini_armor': '2025 比基尼铠甲', '2025_cardcaptor': '2025 魔卡少女', '2025_china': '2025 中国风', '2025_couple': '2025 情侣装',
    '2025_fantasy': '2025 奇幻', '2025_fusion_hanbok': '2025 改良韩服', '2025_irusan': '2025 猫王伊鲁桑', '2025_kimono': '2025 和服',
    '2025_knitgarter': '2025 针织吊袜', '2025_lingerie_succubus': '2025 魅魔内衣', '2025_medusa': '2025 美杜莎',
    '2025_medusa_test': '2025 美杜莎（测试）', '2025_navalband': '2025 海军乐队', '2025_newtown': '2025 新城街头',
    '2025_prof_a': '2025 教授 A', '2025_prof_c': '2025 教授 C', '2025_prof_k': '2025 教授 K', '2025_prof_t': '2025 教授 T',
    '2025_reverse': '2025 逆装（逆兔女郎?）', '2025_santa': '2025 圣诞', '2025_seashore': '2025 海边', '2025_sidebackless2': '2025 侧露背装 2',
    '2025_sleeveless': '2025 无袖', '2025_steam': '2025 蒸汽朋克', '2025_street': '2025 街头', '2025_street_lower': '2025 街头（下装）',
    '2025_street_upper': '2025 街头（上装）', '2025_torn': '2025 破损风', '2025_valkyrie': '2025 女武神', '2025_viking': '2025 维京',
    '2025_witch': '2025 女巫', '2026_android': '2026 仿生人', '2026_cheerleader': '2026 啦啦队', '2026_cowgirl': '2026 女牛仔',
    '2026_devil': '2026 恶魔', '2026_fairy': '2026 妖精', '2026_funkydenim': '2026 潮流牛仔', '2026_hotpants': '2026 热裤',
    '2026_jeans': '2026 牛仔裤', '2026_luxswim': '2026 奢华泳装', '2026_mecha': '2026 机甲', '2026_oriental_dress': '2026 东方礼服',
    '2026_pajama': '2026 睡衣', '2026_ponyk': '2026 Ponyk?', '2026_rider': '2026 骑手', '2026_runway': '2026 T 台时装',
    '2026_sf1': '2026 科幻 1', '2026_shaman': '2026 萨满', '2026_slingshot': '2026 V 字泳衣', '2026_slip': '2026 吊带睡裙',
    '2026_under': '2026 内衣', '2026_wedding': '2026 婚纱', '2026_wedding_soft': '2026 婚纱（柔和款）',
    '21contest_chn': '21 设计大赛（国服）', '21contest_tw': '21 设计大赛（台服）', '21contest_usa': '21 设计大赛（美服）',
    '22contest_chn': '22 设计大赛（国服）', '22leggings': '22 打底裤', '23contest_chn': '23 设计大赛（国服）',
    '24contest_chn': '24 设计大赛（国服）', '24contest_kor': '24 设计大赛（韩服）', '24contest_kor2': '24 设计大赛（韩服）2',
    '24contest_kor_silver2': '24 设计大赛（韩服）银奖 2', '25contest_chn': '25 设计大赛（国服）', '25contest_tw': '25 设计大赛（台服）',
    # regional folders
    '_chn/boyishqipao': '帅气旗袍', '_chn/chinaplate': '中国风板甲', '_chn/chinaset_evy': '中国风套装·伊菲',
    '_chn/chinaset_fiona': '中国风套装·菲欧娜', '_chn/cintamani': '如意宝珠', '_chn/clement': 'Clement', '_chn/crown': '王冠',
    '_chn/gallantry': '英勇', '_chn/gangsi': '僵尸', '_chn/ironrivet': '铁铆钉', '_chn/pansyqipao': '三色堇旗袍', '_chn/sage': '贤者',
    '_chn/silkuni': '丝绸制服', '_chn/sunny': '晴天', '_chn/tiger': '虎', '_chn/tomboy': '假小子', '_chn/traditional': '传统服饰',
    '_chn/training': '训练服', '_chn/velvet': '天鹅绒', '_chn/wanfighter': 'Wan 格斗家?', '_chn/xiaogui': '小鬼',
    '_chn/zinniaqipao': '百日菊旗袍', '_jpn/kimono1': '和服 1', '_jpn/magi': 'Magi（魔笛?联动）', '_jpn/sao': '刀剑神域 SAO 联动',
    '_usa/superbowl': '超级碗',
    # the rest, alphabetical
    'adventurer': '冒险家', 'agent_rochest': '罗切斯特特工', 'aidan': '艾丹同款', 'akiba': '秋叶原', 'aladin': '阿拉丁',
    'apex_senior': 'Apex 学姐', 'arcana': '秘仪（塔罗）', 'armageddon': '末日', 'armor_125lv': '125 级铠甲',
    'avatar_regina': '蕾吉娜化身', 'avatar_regina2': '蕾吉娜化身 2', 'avatar_regina3': '蕾吉娜化身 3', 'baseball': '棒球',
    'baseballgirl': '棒球女孩', 'battlemail': '战斗锁甲', 'beginner_cloth': '新手布衣', 'betmen': '蝙蝠侠风', 'biker': '机车',
    'bikini': '比基尼', 'black_gale': '黑色狂风', 'blackhammer': '黑锤', 'blacksmith': '铁匠', 'bless': '祝福', 'bloodfist': '血拳',
    'bloodsilk': '血丝', 'bloomer': '体操灯笼裤', 'blossom': '花开', 'body_hidden': '隐藏身体用', 'bolero': '波蕾若短外套',
    'border_guardian': '边境守卫', 'bres': '布雷斯', 'brigit': '布丽吉特同款', 'bunny_2022': '2022 兔女郎', 'bunny_girl2': '兔女郎 2',
    'bunny_suit': '兔女郎装', 'bunnyhood': '兔耳兜帽', 'butterfly': '蝴蝶', 'calia_armor1': '卡莉亚专属第一套',
    'calia_armor2': '卡莉亚专属第二套', 'calm': '平静', 'cardigan': '开衫', 'cardigan2': '开衫 2', 'casual': '休闲',
    'casual_jacket': '休闲夹克', 'catslady': '猫女', 'champion': '冠军', 'chiulin': 'Chiulin', 'cichol': '奇科尔同款',
    'claire': '克莱尔', 'cleric': '牧师', 'commander_soul': '指挥官之魂', 'contest2014': '2014 设计大赛',
    'contest2015': '2015 设计大赛', 'contest2015eu': '2015 设计大赛（欧服）', 'cook': '厨师', 'crest_master': '纹章大师',
    'crimsonrage': '绯红之怒', 'cristal_seethrough': '水晶透视装', 'cristal_seethrough2': '水晶透视装 2', 'crystal': '水晶',
    'crystalrose': '水晶玫瑰', 'damage_feather': '破损羽毛', 'dancer': '舞者', 'dancingblade': '舞刃', 'dancingblossom': '舞樱',
    'darknight': '暗夜骑士', 'darkrev': 'Darkrev', 'datealive': '约会大作战联动', 'death': '死神', 'deathclaw': '死爪',
    'deathknight': '死亡骑士', 'deathknight2': '死亡骑士 2', 'deepmaze': '深渊迷宫', 'demon_hunter': '恶魔猎手',
    'demon_stoker': '恶魔司炉', 'desperado_black': '黑色亡命徒', 'devilhunter': '恶魔猎人', 'deviloon': '小恶魔',
    'devilsine': 'Devilsine', 'dino': '恐龙', 'dobok': '跆拳道服', 'dolphin': '海豚', 'dorothy': '多萝西', 'dragon_rises': '龙腾',
    'dullahan': '无头骑士', 'egypt': '埃及', 'elculous': 'Elculous', 'elegantpain': '优雅之痛', 'elite_officer': '精英军官',
    'elven_knight': '精灵骑士', 'eochaid': '约海德', 'epona': '艾波娜同款', 'ergreaver': 'Erg 收割者', 'evil_knight': '邪恶骑士',
    'evy_tshirt': '伊菲 T 恤', 'eweca': '艾维卡', 'explorer': '探险家', 'fairy': '妖精', 'fairytail': '妖精的尾巴?',
    'fallen': '堕落者', 'fallenangel': '堕天使', 'fallenrock': '落岩', 'feather': '羽毛', 'finesteel': '精钢', 'flamenco': '弗拉明戈',
    'formal': '正装', 'formal_plate': '正装板甲', 'fringe': '流苏', 'frostheart': '霜之心', 'frozen': '冰封', 'fullmetal': '全金属',
    'fungus': '菌菇', 'fusion_hanbok': '改良韩服', 'gangster': '黑帮', 'gangster2': '黑帮 2', 'garter': '吊袜带', 'gem': '宝石',
    'girlfriend': '女友装', 'glasgavelen': '格拉斯加布林', 'goblin': '哥布林', 'gothic': '哥特', 'gothic_wear': '哥特服',
    'guardian': '守护者', 'harness': '束带', 'heremon': '赫雷蒙', 'hige': 'Hige', 'high_techer': '高科技', 'highelf': '高等精灵',
    'hiheel_test': '高跟鞋（测试）', 'holy_knight': '圣骑士', 'hoodie': '连帽衫', 'horror': '恐怖', 'hound': '猎犬', 'idol': '偶像',
    'infinitycrown': '无限王冠', 'ingkara': 'Ingkara', 'invisible': '隐形', 'iset': '伊塞特同款', 'ivyplate': '常春藤板甲',
    'justice_rose': '正义玫瑰', 'kitsunemiko': '狐巫女', 'knightplate': '骑士板甲', 'kobold': '狗头人', 'l_strike': 'L 打击',
    'laniakea': '拉尼亚凯亚', 'laura': '劳拉同款', 'legend': '传说', 'leggings': '打底裤', 'lightplate': '轻板甲',
    'lightplate2': '轻板甲 2', 'lionknight': '狮子骑士', 'lotus_flower4': '莲花 4', 'lughlamhfada': '长臂卢赫',
    'lumielle_armor1': '露米艾尔专属第一套', 'lumielle_armor2': '露米艾尔专属第二套', 'macha': '玛查', 'macha_avatar': '玛查化身',
    'maddog': '疯狗', 'magnolia': '木兰', 'mai': '舞', 'maid': '女仆', 'maid2': '女仆 2', 'maid3': '女仆 3', 'midnight': '午夜',
    'minidress': '迷你裙', 'miri': '芈璃同款', 'musketeer': '火枪手', 'natural': '自然', 'neamhain': '内文同款',
    'neamhain_armor1': '内文专属第一套', 'neamhain_armor2': '内文专属第二套', 'neberez': '内维雷斯同款', 'necromancer': '死灵法师',
    'net': '网纱', 'new_glasgavelen': '新格拉斯加布林', 'new_legend': '新传说', 'nightmare': '梦魇', 'nightofgold': '黄金之夜',
    'ninja': '忍者', 'noble': '贵族', 'noppamas': '诺帕玛（泰国水灯节）', 'northern': '北方', 'nurse': '护士', 'nursestyle': '护士风',
    'office_lady': '办公室女郎', 'office_look': '办公室造型', 'officer': '军官', 'openwaist': '露腰装', 'openwaist2': '露腰装 2',
    'oriental_odyssey': '东方奥德赛', 'orna': 'Orna', 'padding': '羽绒服', 'peacock': '孔雀', 'phantom': '幻影', 'phoenix': '凤凰',
    'phoenix_soul': '凤凰之魂', 'pirate': '海盗', 'pitbull': '比特犬', 'platinum_bullet': '白金子弹', 'posh': '时髦',
    'premium_youth': '高级青春', 'prestige_devil': '威望恶魔', 'prince': '王子', 'pytonshock': '蟒蛇冲击', 'qipao': '旗袍',
    'queens_lust': '女王之欲', 'rage': '狂怒', 'reinforce': '强化', 'richmagic': '富魔法', 'ridecat': '骑猫（坐骑装）',
    'ridepan2': '骑熊猫 2（坐骑装）', 'ridepan3': '骑熊猫 3（坐骑装）', 'ridepig': '骑猪（坐骑装）', 'rideshiba1': '骑柴犬（坐骑装）',
    'romel': '罗梅尔', 'rosedrop': '玫瑰露', 'royalguard': '皇家卫队', 'royalheavy': '皇家重甲', 'royallight': '皇家轻甲',
    'rurosakura': '流浪樱', 'russian': '俄罗斯', 's2ep2_nighthawk': '第二季 夜鹰', 's2ep2_vampbride': '第二季 吸血鬼新娘',
    's2ep2_vampslayer': '第二季 吸血鬼猎人', 'saintnova': '圣新星', 'santa2011': '2011 圣诞', 'santa2012': '2012 圣诞',
    'sanyaa_armor1': '纱妮娅专属第一套', 'sanyaa_armor2': '纱妮娅专属第二套', 'savage': '野性', 'scarlet': '绯红',
    'scavenger': '拾荒者', 'scholar': '学者', 'school': '校服', 'secretagent': '特工', 'secretagent2': '特工 2',
    'selren': '赛伦同款', 'sexyrose': '性感玫瑰', 'sheriff': '警长', 'shiningwill': '闪耀意志', 'shiny_stania': '闪耀斯塔尼亚',
    'shirt': '衬衫', 'shirt2': '衬衫 2', 'shirt3': '衬衫 3', 'shooting_star': '流星', 'shortshirt': '短衬衫', 'shouette_act': 'Shouette',
    'sidebackless': '侧露背装', 'siete': '席耶特同款', 'silkofgold': '金丝', 'silver_checker': '银格', 'silverfox': '银狐',
    'skeleton': '骷髅', 'slit': '开衩', 'snaker': '蛇行者', 'sophomore': '二年级生', 'sorceress': '女术士',
    'sorceressdark': '黑暗女术士', 'southern_winter': '南方之冬', 'spidercloth': '蜘蛛丝衣', 'spiderlord': '蜘蛛领主',
    'standalone': 'Standalone', 'steamhero': '蒸汽英雄', 'steel_office': '钢铁办公', 'stewardess': '空姐',
    'sting_quasar': '刺·类星体', 'stripe': '条纹', 'studded': '铆钉', 'succubus': '魅魔', 'succubus_queen': '魅魔女王同款',
    'summercasual': '夏日休闲', 'suspender_jean': '背带牛仔', 'swarouge': 'Swarouge', 'sweety_bear': '甜心熊',
    'swordwind_tunic': '剑风束腰外衣', 'tarata': 'Tarata', 'taros': 'Taros', 'temptationer': '诱惑者', 'ti': '缇同款',
    'topless_suit': 'Topless 套装', 'trainingcube': '训练魔方', 'tw_contest2018': '2018 设计大赛（台服）', 'twinkle': '闪烁',
    'uaithne': '乌艾斯尼', 'uniform': '制服', 'valkyrie': '女武神', 'vampire': '吸血鬼', 'vanguard_knight': '先锋骑士',
    'venetian': '威尼斯', 'vikahorn': 'Vikahorn', 'viking': '维京', 'waredge_battlesuit': '战刃战斗服', 'wedding2': '婚纱 2',
    'western': '西部', 'weusi_kuzza': 'Weusi Kuzza', 'white_shark': '白鲨', 'wild_duke': '狂野公爵', 'windtalker': '风语者',
    'wing': '翅膀', 'wing_devil': '恶魔之翼', 'wingplate': '翼板甲', 'witch': '女巫', 'yukata': '浴衣', 'yukata2016': '2016 浴衣',
    'yukata2017': '2017 浴衣', 'yukata_delia': '黛莉娅浴衣', 'yuri': '百合',
}

HEROES = ('calia', 'lumielle', 'neamhain', 'sanyaa', 'evy_', 'miri', 'yukata_delia', 'chinaset_')
NPC_BOSS = ('aidan', 'brigit', 'cichol', 'epona', 'iset', 'laura', 'neberez', 'neamhain', 'selren', 'siete', 'succubus_queen',
            'ti', 'regina', 'macha')


def kind(name):
    """catalogue group of a set folder name"""
    b = name.rsplit('/', 1)[-1]
    if name.startswith(('_chn/', '_jpn/', '_usa/')):
        return '地区专属'
    if 'contest' in b:
        return '设计大赛'
    if b.startswith(HEROES) or '_armor' in b:
        return '角色专属'
    if re.sub(r'^\d{4}_', '', b) in NPC_BOSS or b.startswith(('avatar_regina', 'macha')):
        return 'NPC / Boss 同款'
    if re.match(r'(19|20)\d\d|\d\d[a-z]', b) or re.search(r'20\d\d$', b):
        return '活动 / 年份款'
    return '常规'
