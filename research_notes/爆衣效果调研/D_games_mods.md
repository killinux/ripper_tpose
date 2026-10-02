# 爆衣 survey, part D: character games and their mod ecosystems

## Key takeaways

- **No shipping character game I could check tears cloth at runtime** [INFERRED]. Commercial 爆衣 uses three tricks:
  - discrete stage swaps: Senran Kagura, Soulcalibur [PRESS], DOA6 "breakable" costumes [MOD];
  - texture damage layers: DOA6 Break Blow dirt and blood [MOD], MK injuries [PRESS];
  - a shader threshold: Honey Select 2's built-in per-garment `breakRate` drives the shader property `_AlphaEx` [INFERRED, binary read].
- **The closest match to Cloth Tear is ClothingRipper, a free VaM plugin** (Mxx, CC BY, 2026) [MOD].
  - It deletes triangles along cut lines and sweeps the tear across the garment over a set "travel time" [MOD].
  - It ramps pins to zero and fades the fallen pieces out [MOD].
  - Several of its features carry over directly: hide over-stretched triangles, the detach curve, a reversible rip-progress %, and seeded 2–64 piece cuts [MOD].
- **VaM's own undress works from stress, not time.**
  - Each sim vertex is held to the skin by a joint. The "Undress Threshold" slider writes GPUTools `ClothSettings.BreakThreshold` [INFERRED, binary read].
  - Two community plugins, Stripwise and ZipUnzipIt, instead animate per-vertex rigidity through space bounds or a texture threshold [MOD]. That is the same idea as our Geometry Nodes pin-release band.
- **Illusion games swap whole meshes per state.**
  - Koikatsu has four states: On / Shift / Hang / Off [MOD].
  - AI-Shoujo and HS2 use `objTopDef`/`objTopHalf` and `objBotDef`/`objBotHalf` [MOD].
  - The only tearing is HS2's break slider (shader alpha threshold plus a body alpha-mask update) [INFERRED], plus alpha-mask and overlay mods [MOD].
- **Skyrim and Fallout 4 mods swap whole items** (the VSU Framework links up to 3 states) or paint overlays [MOD]. I found no HDT-SMP/FSMP mod that tears or detaches cloth.
- **What this means for export:**
  - PMX/VMD carries only bone and morph keys. A tear reaches MMD only as rigid per-piece bones keyed in VMD, or as discrete stage meshes switched by morphs. A threshold dissolve would need an MME shader [INFERRED].
  - For VaM, export a sim-enabled garment and let VaM or ClothingRipper tear it [INFERRED].
  - VaM 2 has no cloth simulation yet [DEV].
- **Capcom's CEDEC 2024 Street Fighter 6 talk shows AAA cloth is art-directed**: wind keyed per frame and cloth motion baked to joint animation [DEV]. That supports our time-driven design and a bake-to-bones export.

## Method

- Sources: pages opened on 2026-10-02.
- Local read-only checks: VaM 1.22 and HS2 DX `Assembly-CSharp.dll` (metadata, IL), HS2 stock cards, and sideload.betterrepack.com folder listings (no mods downloaded).
- The search quota ran out during section 4, so several commercial items rest on wikis and press.

## Pattern map

| Title / system | Pattern | Basis |
|---|---|---|
| Senran Kagura | discrete stage swap (top and bottom, 2–3 stages each) | [PRESS] + [INFERRED] |
| Soulcalibur IV–VI, Akiba's Trip | discrete part removal per body zone | [PRESS] |
| DOA6 | texture damage layer + breakable costume swap | [DEV] + [MOD] |
| Mortal Kombat 11 / 1 | texture/decal damage | [INFERRED] |
| Resident Evil 2 (2019) | localized runtime damage + limb loss (method unknown) | [PRESS] |
| Stellar Blade (mods) | whole-outfit swap on shield break | [MOD] |
| HS2 / AI-Shoujo | shader threshold (`_AlphaEx`) + body alpha mask | [INFERRED] |
| Koikatsu / HS2 states, Skyrim VSU, FO4 power armor | discrete mesh, item or piece swap | [MOD] |
| VaM built-in "Undress" | stress-driven break of skin joints (pins) | [MOD] + [INFERRED] |
| VaM ClothingRipper | runtime cut of the mesh + pin release (the only runtime tear found) | [MOD] |
| VaM ClothingDissolve | dissolve threshold | [MOD] |

## 1. Virt-A-Mate

**1.1 Sim clothing "Undress" (VaM 1.x, built in)**
- URLs: [undress guide (PDF)](https://1387905758.rsc.cdn77.org/internal_data/attachments/33/33752-0f04ece18feab02558c9cdf6eab9589d.data), [1.17 notes](https://www.patreon.com/meshedvr/posts/time-for-new-1-27030445), [1.21 notes](https://www.patreon.com/meshedvr/posts/vam-1-21-77428912).
- Licence: proprietary.
- Settings (Physics tab of a sim item, v1.19 screenshot) [MOD]: Sim Enabled, Undress, Undress Threshold, Iterations, Stiffness, Distance Scale, Compression Resistance, Skin Joint Strength, Gravity Multiplier, Weight, Drag, Collision Enabled / Radius / Power, Friction, Static Multiplier, Reset Simulation.
- The guide: "Only 'Sim' clothes can be manually undressed", and "Undress Threshold" "defines how easy a clothing item can be removed by virtual hands" [MOD].
- Saved storables include `allowDetach`, `detachThreshold`, `jointStrength` [MOD].
- Release notes [DEV]:
  - 1.17 added custom clothing import, "Full support for sim included".
  - 1.21 added trigger actions for "undress of all clothing".
- On desktop, the DesktopClothGrab plugin (LEFT ALT; CC BY-NC-SA) grabs cloth [MOD]. No paid ripping items on the Hub [MOD].
- **Opinion:** add an optional "release when strain > k" mode to our pin band. For VaM export, ship sim clothing with a red-channel sim texture so VaM's own undress works.

**1.2 How VaM's cloth works**
- Licence: proprietary.
- MeshedVR: VaM1 hair and cloth simulation run better on Nvidia GPUs "due to how they seem to handle compute shaders more efficiently" ([post](https://www.patreon.com/meshedvr/posts/downloading-and-32794384)) [DEV].
- What the 1.22 binary shows [INFERRED, local IL read]:
  - It contains `GPUTools.Cloth.*` (particles, joints, kernels).
  - `ClothSimControl.SyncDetachThreshold` writes `ClothSettings.BreakThreshold`; `SyncJointStrength` writes `JointStrength`.
  - `ClothSettings` also has `BreakEnabled`, `CreateNearbyJoints`, `InnerIterations`.
- So "undress" breaks vertex-to-skin joints; the mesh is never cut [INFERRED].
- GPUTools is probably "GPU Cloth Tools" (Andrii Shpak, deprecated Asset Store #79734). Obi tearable-mesh bindings are compiled in but not used for clothing [INFERRED].
- **Opinion:** a pin-strength map plus a break threshold is enough to make clothes come off. True fracture is optional.

**1.3 ClothingRipper (Mxx)**
- URL: [hub.virtamate.com/resources/clothingripper.67518](https://hub.virtamate.com/resources/clothingripper.67518/).
- Licence: free, CC BY; v5, 2026-07-03 [MOD]; the .cs source ships inside the .var [INFERRED].
- How it cuts [MOD]:
  - It "tears clothing by deleting triangles from the clothing's mesh along the cut line", so low-poly items tear "wider" and blockier.
  - Cut types: random (2–64 pieces, seed, raggedness); drawn (free, straight line, plane, edge path); "open cut" slits.
  - "Seam Width (rings)" sets how many triangle rings are removed.
- How pieces come off [MOD]:
  - "Detach Duration" ramps a piece's pins to zero; "Detach Curve" shapes the sag.
  - "Rip Burst Force (radial/outward)" pushes pieces away; pieces fade out through material alpha.
  - "Progressive Rip" sweeps the tear over a "Rip Travel Time" along a chosen direction. "Rip Progress %" can be keyed in Timeline and is reversible.
  - "Hide Over-Stretched Triangles" hides triangles stretched past N× rest length.
  - Interactive options: "Tear At Stretch", "Loosen Cloth As It Tears", "Unpin When Stretched".
- **Opinion:** the most useful reference here. Copy the over-stretch hiding, the detach curve, the radial burst, the reversible progress scrub, the plane / edge-path cut tools and the seeded random cutter.

**1.4 ClothingDissolve (Mxx)**
- URL: [resource 69436](https://hub.virtamate.com/resources/clothingdissolve.69436/).
- Licence: free, CC BY-ND; 2026-09-11 [MOD].
- Mechanism [MOD]: a 0→1 noise dissolve "with a glowing edge", scale, seed and edge softness, an optional direction sweep and per-item sliders. Shadows fade with the alpha, and it can be keyed in Timeline.
- **Opinion:** cheap to add as an EEVEE alpha-clip mode. It reaches PMX only through an MME shader driven by a morph [INFERRED].

**1.5 Stripwise Lite (GossamerVR) and ZipUnzipIt (coinstacc)**
- URLs: [Stripwise](https://hub.virtamate.com/resources/30792/), [ZipUnzipIt](https://hub.virtamate.com/resources/zipunzipit-experimental.64496/).
- Licence: both free, CC BY [MOD].
- Stripwise [MOD]:
  - "control the rigidity of clothing within X, Y, and Z bounds".
  - Bounds are measured in the T-pose's "character space", so the cutoff follows the limbs in any pose.
  - It has a falloff exponent and invert modes, and can be keyed in Timeline.
- ZipUnzipIt [MOD]: sets each vertex's skin-joint rigidity to its base value or 0, by a threshold read from a texture's red channel, with a "bandwidth" that smooths the transition.
- **Opinion:** these are our Geometry Nodes pin band. Borrow the rest-pose-space bounds and the threshold-plus-bandwidth parametrisation, and add a "release time" map driven by a texture or vertex group.

**1.6 Torn looks made with textures and presets** (all free) [MOD]
- VamEssentials "Alphas" (alpha textures that "Add Openings"); CuteSvetlana's "Ripped transparent masks and normal maps"; "Super Hero Battle Suit" (3 standard + 3 damaged presets); ClothingStripper Set01 (strips "in stages").
- **Opinion:** the cheapest VaM export: bake our torn frame into an alpha mask plus a preset.

**1.7 VaM 2**
- URL: [public roadmap](https://trello.com/b/KByJdWtA/vam2-public-roadmap). Licence: proprietary.
- State of the roadmap (last activity 2026-09-30) [DEV]:
  - beta1.2 is out (Unity 6000.5.0b6).
  - "Wrap clothing" sits under beta1.X.
  - "betaX Simulated Clothing" holds two empty cards, untouched since 2022.
- **Opinion:** nothing to target yet.

## 2. Illusion games

**2.1 Koikatsu / Koikatsu Sunshine / EmotionCreators clothing states**
- URL: [ClothingStateMenu](https://github.com/ManlyMarco/Illusion_ClothingStateMenu). Licence: LGPL-3.0 [MOD].
- `ClothButton.cs` reads `fileStatus.clothesState[kind]`, names the four values "On", "Shift", "Hang", "Off", and advances them with `ChaControl.SetClothesStateNext(kind)` [MOD].
- [ClothCycler](https://github.com/Njaecha/ClothCycler) cycles on / half / off when you double right-click a body part [MOD].

**2.2 AI-Shoujo / HS2 state meshes**
- URL: [hooh-hooah ModdingTool `CmpClothes.cs`](https://github.com/hooh-hooah/ModdingTool/blob/master/Assets/Modding%20Tool%20Runtime/Scripts/AIHS2/CmpClothes.cs) (public; licence file not found).
- `CmpClothes` holds `objTopDef`/`objTopHalf`, `objBotDef`/`objBotHalf`, `objOpt01/02` and `useBreak`. `FindAssistFilter` binds the child meshes named `*_top_a` / `*_top_b` and `*_bot_a` / `*_bot_b` [MOD].
- The half states are authored meshes that the game toggles [INFERRED].
- **Opinion (2.1–2.2):** bake our tear into N static stage meshes. They work as Illusion-style half meshes and as PMX morph-switched stages.

**2.3 HS2's built-in garment break**
- Licence: proprietary; found by local inspection, no public docs or manual mention.
- What the files show [INFERRED, local IL and card read]:
  - All 14 stock cards store per part `{id, colorInfo, breakRate, hideOpt}`.
  - The character maker's clothes panel (`CvsC_Clothes`) has a slider field `ssBreak`.
  - `ChaControl.ChangeBreakClothes` checks `CmpClothes.useBreak` and writes `breakRate` to `ChaShader.ClothesBreak`, which is the shader property `_AlphaEx`, on the garment's renderers.
  - It then calls `ChangeAlphaMaskEx` and `ChangeAlphaMask2`, which update the body alpha masks.
- **Opinion:** worth adopting as an export product. Bake a per-texel "tear time" texture, so a single threshold value replays the tear in game shaders.

**2.4 Plugins and Studio timeline**
- KK_ChaAlphaMask (Nakay) turns alpha masks on per clothing state ([compendium](https://github.com/Frostation/KK-Plugins-Compendium/blob/master/Plugins%20Compendium.md)) [MOD].
- Material Editor (KK_Plugins, GPL-3.0): its rows have a Timeline button; [PR #411](https://github.com/IllusionMods/KK_Plugins/pull/411) fixed it so renderer "Enabled" and shadow settings can be keyframed [MOD]. That is visibility switched over time.
- [Timeline](https://joan6694.bitbucket.io/) (closed source) documents camera, object, light, HSPE and RendererEditor tracks; I found no clothing-state track [DEV].
- VNGE's VNFrame tracks clothes states 0/1/2 [SNIPPET].
- **Opinion:** this is discrete swapping over time; nothing new to copy.

**2.5 Sideloader zipmods**
- A file-name scan of 881 KK/EC and AI/HS2 pack folders found one torn garment: "[nashi] Torn Pantyhose v1.2" [MOD].
- **Opinion:** this community does damage with overlays and alpha masks, not torn meshes.

## 3. Skyrim / Fallout 4

**3.1 VSU Framework ("Various States of Undress")**
- URL: [Nexus 74851](https://www.nexusmods.com/skyrimspecialedition/mods/74851).
- Licence: free; Papyrus with PapyrusUtil as a hard requirement [MOD]; source not checked.
- Rules in .ini files (`ModID|State1FormID~Plugin|State2…|State3…`) link related items; the database is rebuilt in the in-game mod menu [MOD].
- Mods built on it [MOD]:
  - [VSU Degradation](https://www.nexusmods.com/skyrimspecialedition/mods/75694) swaps armour to "damaged versions" as its condition drops, NPCs included.
  - [Wayward Knight](https://www.nexusmods.com/skyrimspecialedition/mods/134775) makes "a breakable skirt effect à la Nier Automata".
  - VSU for OStim swaps in "partially undressed versions" during animations.
- **Opinion:** stage swapping again; our equivalent is exporting stage meshes.

**3.2 Dirt and Blood** ([Nexus 38886](https://www.nexusmods.com/skyrimspecialedition/mods/38886); free)
- Body overlays in 4 dirt and 4 dirt-plus-blood stages; "Just Blood" ties blood to missing health without scripts [MOD].
- **Opinion:** skip; it marks the body, not cloth.

**3.3 Fallout 4**
- Vanilla power-armour pieces at zero durability "fall off the frame" [SNIPPET]; [Scarcity](https://www.nexusmods.com/fallout4/mods/21228) destroys them for good [MOD].
- Damaged clothing is a separate item (Damaged Hazmat Suit, [49256](https://www.nexusmods.com/fallout4/mods/49256)) [MOD].
- **Opinion:** skip.

**3.4 HDT-SMP / FSMP physics**
- I found no mod that breaks constraints to detach or tear cloth ([FSMP](https://www.nexusmods.com/skyrimspecialedition/mods/57339)). See Gaps.

## 4. Commercial games

**Senran Kagura** (Marvelous / Tamsoft; proprietary)
- SHINOVI VERSUS: certain moves break the top and bottom one stage each; 3 stages each is a full break ([Famitsu](https://www.famitsu.com/news/201212/13025840.html)) [PRESS].
- Burst Re:Newal: the costume tears in 2 levels; a 絶・秘伝忍法 then causes 全破壊 (full destruction) with a per-character cut-in ([4Gamer](https://www.4gamer.net/games/389/G038902/20171027016/)) [PRESS].
- Shinobi Transformation clears the damage ([wiki](https://senrankagura.fandom.com/wiki/Costume_Destruction)) [PRESS].
- The break level is a runtime value that players poke with Cheat Engine ([forum](https://senran-international.boards.net/thread/1668/estival-pc-modding-thread)) [PRESS].
- Pattern: discrete stage swap [INFERRED].
- **Opinion:** stage swaps export cleanly to PMX. Our simulation can author the in-between stages.

**Dead or Alive 6** (Koei Tecmo; proprietary)
- Producer Shimbori: body parts that are hit repeatedly show bruises and bleeding ([4Gamer](https://www.4gamer.net/games/422/G042216/20180615175/)) [DEV].
- Mods show [MOD]:
  - Break Blow damage is stored as separate battle-damage material textures ([#25](https://www.nexusmods.com/deadoralive6/mods/25)).
  - Some costumes are "breakable": a "Broken Form" appears after a Break Blow ([#17](https://www.nexusmods.com/deadoralive6/mods/17), [#60](https://www.nexusmods.com/deadoralive6/mods/60)).
- **Opinion:** maps well to PMX: a material morph for the damage layer plus stage meshes.

**Soulcalibur IV–VI** (Bandai Namco; proprietary)
- IV: three armour zones (High / Middle / Low) break separately and stay broken all match [PRESS].
- V and VI: a strong finishing hit strips 1–2 parts, and created characters lose everything down to underwear. SCVI 2.2 lets players turn this off ([wiki](https://soulcalibur.fandom.com/wiki/Equipment_Destruction)) [PRESS].
- Flying-debris visuals [INFERRED].
- **Opinion:** zone removal plus rigid debris means per-piece bones in VMD, an easy export.

**Akiba's Trip: Undead & Undressed** (proprietary)
- Attacks weaken the upper, middle or lower clothing; holding the button then strips that piece ([Wikipedia](https://en.wikipedia.org/wiki/Akiba%27s_Trip:_Undead_%26_Undressed)) [PRESS].

**Mortal Kombat 11 / Mortal Kombat 1** (NetherRealm; proprietary)
- MK11 (Unreal Engine 3): Krushing Blows show "graphic body injuries" ([Wikipedia](https://en.wikipedia.org/wiki/Mortal_Kombat_11)) [PRESS].
- MK1's damage is described as subtle, dynamic scrapes, slashes and blood [SNIPPET].
- Pattern: texture and decal layers [INFERRED].

**Resident Evil 2 (2019)** (Capcom; proprietary)
- Enemies react "to damage from gunshots in real-time and capable of having limbs blown off" ([Wikipedia](https://en.wikipedia.org/wiki/Resident_Evil_2_(2019_video_game))) [PRESS].
- Director Kadoi: 「ゾンビの欠損表現など細部に至るまでこだわっています」 ("we were particular about every detail, down to how zombies lose body parts") ([GAME Watch](https://game.watch.impress.co.jp/docs/interview/1139977.html)) [DEV].

**Stellar Blade** (Shift Up; proprietary)
- I found no runtime suit damage in the base game [INFERRED].
- Mods add it [MOD]:
  - [Enemies Strip Eve](https://www.nexusmods.com/stellarblade/mods/672): "When Eve's shields hit 0, her outfit swaps into the skinsuit"; a layered variant adds several breaks.
  - [Immersive Nanosuit Damage](https://www.nexusmods.com/stellarblade/mods/3148) swaps outfit presets of the CNS mod (Custom Nanosuit System) per shield level, through UE4SS Lua.
- **Opinion:** confirms swap-on-event as what modders reach for first.

**Street Fighter 6 cloth (not damage)** (Capcom; proprietary)
- CEDEC 2024 talk [DEV]:
  - Havok Cloth plus RE ENGINE's Chain feature.
  - "演出風" (staged wind) keyed per frame for each move; about 100 parameters for one character.
  - Cloth motion baked to joint animation overrides the simulation when needed.
- Reports: [CGWORLD](https://cgworld.jp/article/202410-cedec03-sf6.html), [4Gamer](https://www.4gamer.net/games/635/G063504/20240830070/).
- **Opinion:** strong support for a time-driven, art-directed tear and for baking our result to bones for PMX.

## Gaps

- **Commercial internals:** I found no developer talk on how Senran Kagura, DOA6, Soulcalibur VI, MK11/MK1 or the RE remakes build their damage. RE3 and RE4 were not checked. Stellar Blade's base game is judged only from the mods.
- **Titles not verified:** Onechanbara, Valkyrie Drive, Bullet Girls, Ikki Tousen, Tekken 8, DOAXVV.
- **VaM:**
  - I did not read the ClothingRipper or ClothingDissolve source (.var not downloaded).
  - The GPUTools ↔ "GPU Cloth Tools" link is unconfirmed.
  - The VaM 2 cloth plans are blank.
- **Illusion:** a Timeline clothing-state track is unverified. The HS2 break findings come from binaries only (UI label, which items set `useBreak`, and the `_AlphaEx` shader math untested); AI-Shoujo is assumed to share the code.
- **Skyrim / Fallout 4:** VSU's source and licence are unchecked. No SMP/FSMP tearing or physics detach was found.
