# 爆衣 in the MMD / PMX world: survey, part C

Checked 2026-10-02. Each claim carries a tag:
- [VERIFIED]: I read it on the page or in the source code.
- [SNIPPET]: from a search snippet only.
- [INFERRED]: my own reasoning.

## Key takeaways

- **PMX 爆衣 is nearly always an on/off switch, not a tear.** Models use material-alpha morphs (服消し / 脱衣 / 透過) or vertex morphs that hide the cloth [VERIFIED]. Real 破れ / 中破 states are rare [INFERRED]. When the vertex count differs they ship as separate models, because a vertex morph needs the same vertex count [VERIFIED].
- **The PMX format sets hard limits.**
  - Bone morphs hold only a move and a rotation, with no scale.
  - Material morphs cannot swap textures or fade a texture's own alpha.
  - MMD does not load PMX 2.1, so no flip or impulse morphs and no soft bodies [VERIFIED].
- **The best match for "pieces fly off" is わたり's 連続面毎に分解エフェクト (MME).**
  - A PMXEditor plugin writes each connected island's centre into 追加UV1.
  - A vertex shader then throws, spins and fades each island [VERIFIED].
  - Our tear already knows its islands, so we could write that UV channel from Blender automatically [INFERRED].
- **Physics 爆衣 in MMD rests on two MMD 9.00 features:** per-bone physics ON/OFF keys and 外部親. PMX joints cannot break [VERIFIED].
- **Baking to bones gives the most faithful MMD playback of our cloth.** Dem Bones (BSD-3) fits rigid bones, which matches MMD's no-scale bones. Then export a VMD. MMD 9.31 x64 accepts up to 600k bone keys and 20k morph keys per model [VERIFIED].
- **MMDAlembic is a free MMD plugin that plays Alembic vertex animation.** It is the most direct route, but its core is closed and we have not tested it [VERIFIED that it exists].

## 1. How PMX models do 爆衣

**1.1 Vertex morph (shrink, or move away): common**
- **Examples:**
  - The BOOTH shop 寅と羊の道具屋 sells models with ワンピース消し / パンティー消し / スカート消し morphs under 表情操作 → その他 ([Sophia](https://booth.pm/ja/items/3092927); terms: no resale, R-18 use allowed) [VERIFIED]. How they work is not stated.
  - "Hidden morphs shrink polygons into the body" [SNIPPET, X post by firis_games].
- **PMXEditor workflow:** deform the mesh (scale the vertices inward), save the shape as an アーカイブ, create a new 頂点 morph, then アーカイブから選択 → 入れ替え ([miu-mmd blog](https://ameblo.jp/miu-mmd/entry-12940743165.html)) [VERIFIED].
- **Physics variant:** [【心得】(進階教學)MMD脫衣教學:脫上衣篇](https://forum.gamer.com.tw/C.php?bsn=60610&snA=291) (Bahamut, 2021):
  - Drop the jacket in PMXEditor's TransformView physics, using 闇鍋プラグイン one-rigid-body-per-vertex.
  - Save the fallen shape and add it as a morph ("地上的形狀").
  - Key that morph in MMD, with the garment model attached to 上半身2 by 外部親 [VERIFIED].
- **Limit:** the 中破 version of 軽巡棲鬼 shipped as a separate model "頂点数が異なるために" ([sm25630580](https://www.nicovideo.jp/watch/sm25630580)) [VERIFIED]. A morph only moves vertices in a straight line [INFERRED].
- **Opinion — easiest automatic export:** pre-split the seams so the topology never changes. Then use Blender "Save as Shape Key" at chosen frames → mmd_tools vertex morph 爆衣 in the OTHER panel. A few staged keys approximate the fall.

**1.2 Material morph (alpha): the most common**
- **Guide:** [【MMD】衣服を透けさせる材質モーフを作る【PmxEditor】](https://shinshimmder.memo.wiki/d/%A1%DAMMD%A1%DB%B0%E1%C9%FE%A4%F2%C6%A9%A4%B1%A4%B5%A4%BB%A4%EB%BA%E0%BC%C1%A5%E2%A1%BC%A5%D5%A4%F2%BA%EE%A4%EB%A1%DAPmxEditor%A1%DB) [VERIFIED]:
  - Use 乗算 with every value 0, or 加算 with 非透過度 −1 and edge α −1.
  - Name the morph (for example 脱衣) and add it to the 表情 frame.
  - For in-between values, move the material to the end of the draw order.
- **Reverse trick:** set the material's base Tr to 0 and use a 加算 +1 morph, so a hidden layer (a torn version) appears ([gentle wiki 衣装](https://seesaawiki.jp/gentle/d/%b0%e1%c1%f5)) [VERIFIED].
- **What the spec allows:** material morphs only add or multiply diffuse / specular / ambient / edge / texture tints. There is no texture index. The "A" of the texture tint only blends RGB, so the texture's own alpha cannot be morphed ([PMX仕様.txt](https://gist.github.com/FlandreDaisuki/90ae5abf3138a15994526b6bfec73c2c)) [VERIFIED].
- **Version notes:**
  - MMD 9.20 fixed ground shadows staying on Tr=0 materials; 9.21 drops their self-shadow ([changelog](https://w.atwiki.jp/vpvpwiki/pages/476.html)) [VERIFIED].
  - MMDAgent-EX applies only the texture coefficients of material morphs [VERIFIED].
- **Plugin:** PMXエディタ用 材質ON/OFFモーフ生成 v1.2.0 ([BowlRoll 255624](https://bowlroll.net/file/255624), uploader "Anonymous User"), with ON / OFF / ×0 buttons [VERIFIED].
- **Opinion — yes:** give each torn piece its own material, write one fade morph per piece, key it at the frame the piece detaches, and gather them in a group morph.

**1.3 Bone morph / re-weighting**
- PMX bone-morph offsets are a move plus a quaternion, with no scale. Bones have a scale value only inside PMD/PMX editors [VERIFIED spec]. So scaling cloth bones to zero cannot work in MMD [INFERRED].
- **Re-weighting tutorial:** [ボーン操作で水着をポロリできるようにする](https://shinshimmder.memo.wiki/d/%a5%dc%a1%bc%a5%f3%c1%e0%ba%ee%a4%c7%bf%e5%c3%e5%a4%f2%a5%dd%a5%ed%a5%ea%a4%c7%a4%ad%a4%eb%a4%e8%a4%a6%a4%cb%a4%b9%a4%eb) [VERIFIED]:
  - 闇鍋プラグイン (T0R0, [BowlRoll 9765](https://bowlroll.net/file/9765)) adds child bones.
  - The swimsuit's weights move onto those bones, which are then keyed in MMD.
- The Bahamut post's method 2 is the same idea [VERIFIED].
- **Opinion — partly:** one bone per torn piece is a natural bake target. VMD keys beat bone morphs, which can only blend in a straight line.

**1.4 Group / flip morph**
- **Group morph:** a weighted list of other morphs, with no nesting [VERIFIED spec].
- **Flip morph (PMX 2.1):** picks one of several morphs from a single slider ([極北P blog](https://kkhk22.seesaa.net/article/282940510.html)). Only MMM and PMXEditor support it ([sm19380831](https://www.nicovideo.jp/watch/sm19380831)) [VERIFIED].
- **Opinion — yes:** one master 爆衣 group slider over the stage morphs. Avoid flip morphs.

**1.5 UV / 追加UV morphs and staged 破れ textures**
- UV morphs can only move UVs inside one texture [SNIPPET].
- **Subtexture trick** ([LearnMMD, Bandages 2018](https://learnmmd.com/http:/learnmmd.com/subtexture/)) [VERIFIED]:
  - Sphere mode 3 reads 追加UV1.
  - A UV1 morph slides an opaque→transparent mask without moving the base texture.
  - It works in plain MMD; MME has a blending bug with it.
- **Staged textures** need extra material layers switched by morphs, or UV-morphed atlases [INFERRED].
- **破れ morphs exist** but their method is undocumented: the prize model モドキ式虎徹アンダースーツ ([sm18320059](https://www.nicovideo.jp/watch/sm18320059)) and アリオスガンダム 大破モーフ ([sm25218615](https://www.nicovideo.jp/watch/sm25218615)) [VERIFIED].
- **Opinion — yes, untested idea:** store each vertex's tear time in 追加UV1.x and use a hard-step alpha subtexture. One UV1 morph then opens the holes progressively, in plain MMD.

**1.6 Names, panel, tools**
- **Names seen:** ○○消し, 服消し, 脱衣, 服透過, 破れ, 中破 / 大破. "爆衣" itself is rare in Japanese names [INFERRED].
- **Panel byte:** 1 = 眉 (bottom left), 2 = 目 (top left), 3 = 口 (top right), 4 = その他 (bottom right), 0 = system. 爆衣 goes in その他 [VERIFIED spec, BOOTH].
- **More PMXEditor plugins** ([VPVP list](https://w.atwiki.jp/vpvpwiki/pages/228.html)) [VERIFIED]:
  - モーフリバース (くま): works on vertex, material and UV morphs.
  - 簡易左右分割モーフ作成 (sevrunear).
  - モーフ非表示化 (葡萄Ｐ / しえら).
  - 標準モーフチェッカー (T0R0): warns about 255+ morphs and long names.
- **[mmd_tools](https://github.com/MMD-Blender/blender_mmd_tools)** (main branch) [VERIFIED source]:
  - It creates and exports vertex (shape key), bone, material (MULT / ADD), UV and group morphs.
  - UV morphs take `uv_index` 0–4, i.e. UV plus 追加UV1–4.
  - Morph categories are SYSTEM / EYEBROW / EYE / MOUTH / OTHER.
  - Extra UV layers export as 追加UV: the xy part comes from layer `UVn`, the zw part from layer `_UVn`, and V is flipped.
  - It reads and writes PMX 2.0 only.

## 2. MME effects for bursting, tearing and disintegration

**服を破るMME — E教授**
- **URL:** [BowlRoll 263174](https://bowlroll.net/file/263174) (v3.2.1, re-uploaded 2021-09-29). Usage write-up: [「服を破るMME ver3.2」を使ってみる](https://nekonekokeikaku.livedoor.blog/archives/23811331.html).
- **Terms:** not readable, because BowlRoll downloads are gated.
- **How it works** [VERIFIED]:
  - Assign HukuYaburu_v2.fx to the material subsets.
  - Load HukuYaburuController_v3_2.pmx plus the yaburu1.x / yaburu2.x accessories. Each accessory's position is a hole centre; parent it to a bone. Its Si value sets the hole size.
  - Controller morphs mix the TEX1 / TEX2 tear shapes and TEX3 bullet holes. The holes become transparent.
  - 中身捏造 colours the holes for models with no body underneath.
  - It is built on 舞力介入P's full.fx 1.4 ([gentle wiki](https://seesaawiki.jp/gentle/d/%bf%c2%bb%ce%b8%fe%a4%b1%a5%a8%a5%d5%a5%a7%a5%af%a5%c8)).
- **Opinion — no:** holes are placed by hand. We could key the accessories along our tear points, but nothing falls away.

**服に穴を開けたりするエフェクト (PostTexAlphaMask v0.3) — 千成**
- [BowlRoll 155184](https://bowlroll.net/file/155184), 2018-01-12 [VERIFIED]. How it works and its terms are unknown.

**部位破壊エフェクト / 連続面毎に分解エフェクト — わたり (plugins by どるるP)**
- **URLs:**
  - 破壊エフェクトセット: [BowlRoll 11169](https://bowlroll.net/file/11169).
  - Videos: [sm18919170](https://www.nicovideo.jp/watch/sm18919170), [sm19453784](https://www.nicovideo.jp/watch/sm19453784).
  - 部位破壊準備プラグイン: [BowlRoll 8954](https://bowlroll.net/file/8954) [VERIFIED].
- **How it works** (readme in [iori-komatsu/ray-mmd-distribution](https://github.com/iori-komatsu/ray-mmd-distribution)) [VERIFIED]:
  - The plugin 連続面重心書き込み writes each connected island's centre into 追加UV1; w > 0 marks a processed vertex.
  - The vertex shader spins each island around its centre and adds impact speed spreading out from 崩壊中心.
  - It also adds gravity (t²/2) and a fade.
  - Settings are bones (衝撃速度, 回転速度, 重力ﾍﾞｸﾄﾙ, 崩壊開始F …), keyed only at frame 0.
  - **Side effects:** faces turn double-sided and outlines and ground shadows are lost. Bone or morph deformation skews the throw directions, so pre-pose the model in PMXEditor.
- **Terms:** none in the readme. The ray-mmd port and the porter's own changes are MIT.
- **Derivatives:**
  - sdPostFractureSmoke adds smoke and light ([guide](https://pennennennennennenem.github.io/MME/sdPostFractureSmoke/index.html)). サンドマン's terms: "商用・非商用問わず自由に".
  - sdPBR ≥ 2.50 has a fracture effect.
  - わたり made an MMM port ([PIP blog](https://pip-mmd.hatenablog.com/entry/ar1167332)) [VERIFIED].
- **Opinion — yes, the strongest automatic match:**
  - Write the island centres into 追加UV1 via mmd_tools, converted to PMX space with V flipped.
  - Caveat: the motion is a calculated throw, not our cloth simulation, and it starts from the rest pose.

**モデル崩壊エフェクト — Led/折鶴P**
- **URL:** [BowlRoll 54621](https://bowlroll.net/file/54621) (v1.5); video [sm24627227](https://www.nicovideo.jp/watch/sm24627227).
- **How it works:** a bundled PMXEditor plugin pre-processes the model. It is "very heavy, MMD often crashes" ([VPVP](https://w.atwiki.jp/vpvpwiki/pages/272.html)). The author recommends a modified AutoLuminous, which its dark glare needs. エーアイス made an MMM port [VERIFIED].
- **Terms:** only "check the applied model's terms".
- **Opinion:** the same family as 分解; it gives a collapse look, not our simulation.

**E教授's destruction set**
- 自由切断 v3.2 ([263173](https://bowlroll.net/file/263173)): its v3.2 note says the cut parts can be moved by morphs [VERIFIED].
- 自由貫通 ([263171](https://bowlroll.net/file/263171)).
- 街とかを荒廃させるMME ([263168](https://bowlroll.net/file/263168)).
- 強力なエネルギー波で吹き飛ぶMME ([263169](https://bowlroll.net/file/263169)).
- **Opinion:** good for slicing and holes, not cloth.

**Dissolve Shader — セルゆかり**
- [BowlRoll 203940](https://bowlroll.net/file/203940), 2019-07-31 [VERIFIED]. Probably a noise-threshold alpha cut [INFERRED]. Terms unknown.
- **Opinion:** polish for fading pieces out.

**Host support**
- **MikuMikuMoving:** shader-type MME must be ported. 折鶴P wrote FxConverter for this, and ports exist for both destruction effects above [VERIFIED].
- **[nanoem](https://github.com/hkrn/nanoem)** (MIT/MPL): loads .fx files; "post effects and not too complex effects mostly load", with no guarantee of matching MME [VERIFIED].
- **[saba](https://github.com/benikabocha/saba)** (MIT): its own viewer. The README mentions no effects [INFERRED].
- **[MMDAgent-EX](https://mmdagent-ex.dev/docs/mmd-effect/):** no MME, only pseudo AutoLuminous and diffusion. PMX goes through PMD+CSV, with no 追加UV and no 外部親 [VERIFIED]. So the 分解 and subtexture tricks fail there.

## 3. Physics-based 爆衣 in MMD

- **No breakable joints: confirmed at the format level.**
  - PMX 2.0 joints are spring 6DOF only. PMX 2.1 adds 6DOF / P2P / ConeTwist / Slider / Hinge.
  - Neither version has a break threshold.
  - PMX physics follows Bullet 2.75 "MMDとの互換性のため" (for compatibility with MMD) [VERIFIED spec].
- **Per-bone physics toggle**
  - MMD 9.00 (2014-03-15) added 物理演算オン/オフモード and 外部親 [VERIFIED].
  - A ◇ key turns physics OFF (the bone follows keys); a × key turns it ON. Both work only in オン/オフ or トレース mode ([how-to](https://how-to-use-music-video.com/%E3%83%9C%E3%83%BC%E3%83%B3%E6%93%8D%E4%BD%9C%E3%83%91%E3%83%8D%E3%83%AB%EF%BD%9E%E7%89%A9%E7%90%86%E3%83%9C%E3%82%BF%E3%83%B3%EF%BD%9E-mmd%E3%81%AE%E4%BD%BF%E3%81%84%E6%96%B9-37/); official explainer [sm23146306](https://www.nicovideo.jp/watch/sm23146306)) [VERIFIED].
  - **In a VMD file** the flag sits in interpolation bytes 2–3 [VERIFIED code]. [babylon-mmd's parser](https://github.com/noname0310/babylon-mmd/blob/main/src/Loader/Parser/vmdObject.ts) defines 0x63,0x0F as off and 0x00,0x00 as on, but its own comment block says the opposite. mmd_tools has no code for the flag [VERIFIED].
- **Pre-9.0 workaround:** toggle physics through IK ON/OFF, via the 物理ONOFF plugin (魚卵.どるる, [BowlRoll 30885](https://bowlroll.net/file/30885)). Obsolete since 9.00 [VERIFIED].
- **Recipes**
  - The Bahamut post lists three ways: morph + keys, re-weight + keys, and physics ON/OFF + keys (used for the bra). It attaches the separate garment model by 外部親 [VERIFIED].
  - **Release pattern:** keep the cloth bodies kinematic (physics OFF), with no joints to the body. Switch them ON at the tear frame so they fall onto the body colliders [INFERRED]. Collision filtering uses 16 groups [VERIFIED spec].
- **PMX 2.1 features**
  - Soft bodies, with anchor bodies and pin vertices. Their anchors cannot be released at run time [INFERRED from spec].
  - Impulse morphs, which give rigid bodies a speed or a spin [VERIFIED].
  - **Support:**
    - PMXEditor TransformView previews 2.1 physics.
    - MMM supports soft bodies from 1.1.7 ([sm19033111](https://www.nicovideo.jp/watch/sm19033111)), and impulse / point / line from 1.1.7.8 ([sm19128294](https://www.nicovideo.jp/watch/sm19128294)).
    - nanoem has a soft-body class in its code.
    - MMD: no. The 2012 VPVP table marks 2.1 as unsupported ([VPVP](https://w.atwiki.jp/vpvpwiki/pages/284.html)), and the format's author calls it "MMDで使えないPMX".
    - mmd_tools refuses any version other than 2.0 [VERIFIED].
  - **Example:** an impulse morph lifts a skirt's rigid bodies, which are then baked (MMM, [sm27745273](https://www.nicovideo.jp/watch/sm27745273)) [VERIFIED].
- **Setup tool:** PmxTailor (miu, MIT; [BowlRoll 267191](https://bowlroll.net/file/267191), [GitHub](https://github.com/miu200521358/pmx_tailor)) builds bones, weights, rigid bodies and joints by scanning a cloth mesh [VERIFIED].
- **Opinion — lossy:** we could auto-build rigid chains for the pieces and emit OFF→ON keys at each piece's detach frame. But the result is MMD's own Bullet run, not our simulation, and MMD's physics output changes from render to render [VERIFIED how-to].

## 4. Blender → MMD routes

**4.1 Shape-key snapshots**: see 1.1. Free; 20k morph keys per model [VERIFIED].

**4.2 Bake the cloth to bones, then export a VMD**
- **Tools:**
  - [Dem Bones](https://github.com/electronicarts/dem-bones) (EA SEED, BSD-3, v1.2.1): fits rigid bones to an animated mesh (SSDR). Its command-line tool reads Alembic / FBX and writes FBX [VERIFIED].
  - [Blender DemBones](https://dener.itch.io/blender-dembones): from $15 [VERIFIED]; GPL [SNIPPET].
  - [Ossim](https://blenderartists.org/t/ossim-bake-simulations-to-armature-ue4-unity-now-with-blender-2-8-support/1115900): commercial; supports cloth and Blender 4.0+ [VERIFIED].
  - [BonesToMesh-blender](https://github.com/GustJc/BonesToMesh-blender) (MIT): IK from each bone tail to the nearest vertex, then a visual-key bake [VERIFIED].
  - "Bake simulation to bone" (Superhive, paid) [SNIPPET].
- **Limits:**
  - MMD 9.31 x64 loads at most 600,000 bone keys and 20,000 morph keys per model ([td53319](https://3d.nicovideo.jp/works/td53319)) [VERIFIED].
  - VMD names are 15 bytes ([summary](https://togetter.com/li/881598)) [VERIFIED].
  - Up to 4 bone weights per vertex (BDEF4), and no scale [VERIFIED].
  - Worked example: 150 bones × 4,000 frames = 600k keys [INFERRED].
- **Opinion — yes, the best route:** the pieces are nearly rigid, so a few bones per piece will do. Reuse our VMD writer and bake every frame with physics OFF.

**4.3 Vertex-cache playback**
- **MMDAlembic (ash000):** an MMD plugin, "MMDで頂点アニメーション".
  - The v2.1 video ([sm41207099](https://www.nicovideo.jp/watch/sm41207099), 2022) is tagged blender / marvelousdesigner / cloth.
  - v3.6 is on [BowlRoll 283437](https://bowlroll.net/file/283437) (2024-06-12) [VERIFIED].
  - [GitHub](https://github.com/ash0000000/MMDAlembic) holds only a dsound/d3d9 proxy loader, with no licence [VERIFIED].
  - **Opinion:** possibly zero conversion (Blender Alembic → MMD); test it first.
- **MME vertex-animation player:** I found none. It looks feasible, because MME supports vertex texture fetch (VTF) [VERIFIED VTF; INFERRED feasibility].
- **[MMDBridge](https://github.com/uimac/mmdbridge)** (MIT): exports MMD → Alembic, the opposite direction [VERIFIED].
- **A Chinese cloth tutorial** ([BV1Kh411s72v](https://www.bilibili.com/video/BV1Kh411s72v/)) has parts going MMD export → C4D → MD → Blender [VERIFIED], so it renders outside MMD [INFERRED].

**4.4 Accessory (.x) sequences**: no documented example found. Keying per-frame 表示 toggles would work but is heavy [INFERRED].

## Gaps

- **Not read because BowlRoll downloads are gated:** the readmes and terms for 服を破るMME, Dissolve Shader and PostTexAlphaMask, and the internals and limits of MMDAlembic.
- **Not read because Nico Seiga is region-blocked:** E教授's distribution notes.
- **Bilibili:** its API blocked me, so I read no Chinese "爆衣 PE 教程".
- **MMD changelog:** I read nothing after 9.24. Whether 9.3x supports PMX 2.1 is inferred from the absence of any mention.
- **Unverified:**
  - 物理リセット in MMD and MMM.
  - Any display-frame bone limit.
  - The VMD physics-flag polarity: test a VMD saved by MMD.
- **Untested:** the subtexture tear-time idea and the 追加UV1 centroid export. Both use 追加UV1, so they cannot be combined without editing the .fx.
- **Not checked:** R-18 / iwara examples.
