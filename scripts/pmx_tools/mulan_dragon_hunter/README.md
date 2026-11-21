# 仿王者荣耀 花木兰·水晶猎龙者：用手头的零件拼一个（2026-11-01）

王者荣耀的模型没处下（模之屋上花木兰只有剑舞者一款，见下面），用户要求用已有材料拼一个尽量像的。
成品 `E:\game_export\RiseOfEros\_混搭\仿制_王者荣耀_花木兰_水晶猎龙者\花木兰_水晶猎龙者_仿制v1.pmx`。
**v2（同日下午，六处差距全部补上：Vindictus 的护胸 / 龙爪 / 短裤 / 肩甲，程序生成的水晶和水晶剑刃）见 [v2/README.md](v2/README.md)。**
**v11（2026-11-21，不再拼零件：照「MS移植第 44 期」的预览图重新建模，盔甲从皮肤上长出来，贴图全部程序生成）见 [v3/README.md](v3/README.md)。**
这一页是 v1 的配方。
这里是整条配方，三个脚本都是普通 Python（numpy + Pillow，PMX 读写用 mmd_tools 的模块，经 `pmx_head_swap/core.py` 加载）。

参考：官网原画 `https://game.gtimg.cn/images/yxzj/img201606/skin/hero-info/154/154-bigskin-4.jpg`（英雄 154 花木兰，第 4 款皮肤）：
铂金色高马尾、带角的头冠、黑紫色龙鳞板甲镶橙色水晶、露腰、龙爪手甲、鳞甲短裙、橙色水晶大剑、粉紫色眼睛。

## 零件

| 部位 | 来源 | 为什么 |
|---|---|---|
| 身体、脸、盔甲、翼冠、裙子物理 | Inase `pc_a08_outfit1_hd_裙子碰撞修正.pmx` | 黑金甲 + 翼冠，轮廓最像龙角头冠；Inase 本身银白发、游戏材质 |
| 高马尾（带 37 节头发物理） | 星刃 Eve `Eve_Nude_Barefoot.pmx` 的 `MI_Hair_New_Ponytail_4` + `MI_EVE_HR_01_TypeA` | 手头唯一的高马尾长发 |
| 大剑 | Inase a08 `pc_a08_hd.pmx` 的 `wp_a08_l`（两把插地大剑取一把） | 158 cm 的双手剑，斜背在背上 |
| 颜色 | 贴图改色 | 没有真的水晶件，颜色靠改 |

## 步骤

```powershell
$T = "scripts\blender_addons\pmx_outfit_transfer"
# 1. 去掉 Inase 自己的头发（连骨骼、刚体一起）
python $T\pick_cli.py ...\pc_a08_outfit1_hd_裙子碰撞修正.pmx build\s1_nohair.pmx --remove "pc_a08_hd_hair_00_hair_mat,pc_a08_hd_hair_01_hair_mat,pc_a08_hd_hair_02_hair_mat"
# 2. Eve 的马尾按骨骼搬上去：关掉身体贴合（会把头发拉变形 15 cm）和朝向对齐（刘海会转到脑后），不推离皮肤
python $T\cli.py ...\Eve_Nude_Barefoot.pmx build\s1_nohair.pmx build\s2_evehair.pmx --materials "MI_Hair_New_Ponytail_4,MI_EVE_HR_01_TypeA" --prefix eve --split none --no-fit --no-rotation --no-follow-body --min-gap 0
# 3. a08 的两把大剑搬过来（同一副骨架，不贴合）
python $T\cli.py ...\pc_a08_hd.pmx build\s2_evehair.pmx build\s3_weapons.pmx --materials "wp_a08_l,wp_a08_r" --prefix a08 --no-fit --no-rotation --no-follow-body --min-gap 0 --split none
# 4. 一把剑斜背到背上：剑柄在右肩上方，剑尖到左胯；骨骼 Point007_L 连同链子骨一起挪，挂到 上半身2
python place_sword.py build\s3_weapons.pmx build\s4_sword.pmx a08_wp_a08_l Point007_L --tilt 35 --gap 3 --centre-y 100
# 5. 另一把去掉
python $T\pick_cli.py build\s4_sword.pmx build\s5_onesword.pmx --remove "a08_wp_a08_r"
# 6. 改色：在 build\textures 里写出 *_mulan.png
python recolor.py build\textures
# 7. 组装：PMX 的贴图名不变，改过色的贴图顶替原名写进成品文件夹
python assemble.py build\s5_onesword.pmx out\ 花木兰_水晶猎龙者_仿制v1
```

`build\textures` 就是第 5 步 PMX 旁边换装插件拷出来的贴图文件夹。

## 改色规则（recolor.py）

按 HSV 分类，只改贴图：
- 头发：黑发的亮度拉伸后映射到「暖棕阴影 → 铂金 → 近白高光」的渐变，alpha 不动；
- 盔甲（body1 / body2）：金边（色相 0.07–0.17、饱和度 > 0.18）→ 橙色水晶色（色相按明度从红橙到黄橙，饱和度 0.8+，提亮）；
  深色布料（明度 < 0.42）→ 黑紫；灰色板甲（饱和度 < 0.14、明度 0.42–0.9，翼冠和肩甲）→ 深紫；皮肤按色相（0–0.09、中等饱和、亮）保留；
- 大剑：金 → 橙，钢色的暗部 → 黑紫、亮部 → 橙色（水晶刃）；
- 眼睛：虹膜是低饱和的蓝灰盘（色相 0.45–0.78、饱和度 > 0.07）→ 品红粉（饱和度大幅提高）。第一版只抓到了饱和的外圈，瞳孔主体没变。

## 踩过的坑

- 换装插件默认的身体贴合是给衣服用的：拿来搬头发，头发随 Eve → Inase 的体型差被拉了 15 cm；`--no-fit`。
- 默认的骨骼朝向对齐按 頭 骨尾巴方向转了头发，刘海跑到脑后；`--no-rotation`。
- a08 的「武器」是两把 158 cm 的大剑**插在地上**（骨骼 Point007_L/R 在原点，顶点集中在剑柄）：
  放到背上要用包围盒中点当转轴，用顶点均值整把剑会偏到左膝（第一次就是这样）。
- 渲染时 `--factory-startup` 的 mmd_tools 没有 MMD 共用 toon → 设 `shared_toon_folder`（见 pmx-head-swap.md）。

## 和原画的差距（下一版可做）

护胸是 a08 的链甲比基尼（原画是黑色板甲）；没有龙爪手甲；裙子是 a08 的长布片（原画是鳞甲短裙）；水晶只是颜色；大剑是 a08 的款式。

## 顺带：模之屋（aplaybox.com）的搜索接口

网页是脚本渲染的，直接抓不到结果。它的接口：
`POST https://api.aplaybox.com/api/web/v1/work/search`，JSON
`{"is_login":0,"user_uid":"","download_type":-1,"type":1,"keyword":"...","sort_by":1,"user_title_type_id":0,"current_page":1,"per_page":30,"page_type":2}`，
要带请求头 `language: cn`；结果在 `data.result.data.data[]`（`work_name`、`nick_name`、`work_uuid` → `https://www.aplaybox.com/details/model/<work_uuid>`）。
用 curl 只有英文关键词能搜，任何中文关键词都返回 `Server Error`（原因没查出来）。
某作者的全部作品：`POST .../api/web/v1/user/getTargetUserWorks` `{"target_user_uid":"<uid>","work_type_id":1,"current_page":1,"per_page":60}`。
王者荣耀相关：PunPun28th（uid 759019231）发了 75 个英雄的大厅高模（每个英雄第一款皮肤），花木兰只有剑舞者（`1541_HuaMuLan_Show3`）。
