# Clothes tearing / 爆衣: survey part A, Blender and other DCCs

Compiled 2026-10-02 for the Cloth Tear add-on (Blender 3.6).

Tags:
- [VERIFIED]: I read it on the page.
- [SNIPPET]: from a search snippet only.
- [INFERRED]: my own reasoning.

"Ours" means the add-on as described in the brief: a time-driven release band, crease cracks, two cloth modifiers, and a GN merge.

## Key takeaways

- **Blender 5.2 LTS (released 2026-07-14) has built-in tearing, but only in the new Geometry Nodes *Cloth Dynamics* asset.** [VERIFIED]
  - It runs on an XPBD solver. An edge splits once its relative strain passes a *Threshold*.
  - Edges allowed to tear: *All*, a *Custom* edge group, or the borders of *Voronoi* islands.
  - It is experimental, has no self-collision, and colliders must be closed meshes.
  - None of this exists in 3.6.
- **The classic Cloth modifier cannot tear.** [VERIFIED]
  - A developer wrote in 2020 that it "does not support dynamic tearing or deletion of connected edges".
  - GSoC 2019 and 2021 (adaptive cloth) listed tearing only as future work.
- **Our two-cloth trick has a 2017 ancestor** (Lawrence Jaeger, building on Syziph). [VERIFIED]
  - A ripped duplicate is surface-deformed onto cloth 1, and a moving Dynamic Paint brush releases the pins of cloth 2.
  - Its stated flaw was that the seam shows at high resolution; our GN merge fixes that.
  - I found no open-source tool for 3.6 that tears a rigged garment better than ours. [INFERRED]
- **The big DCCs share one core method: pre-split the mesh, hold it with weld or glue constraints, and break them under stress.** This covers Maya, Houdini, 3ds Max and Marvelous Designer's new seam rip. [VERIFIED]
  - tyFlow, Cinema 4D and Blender 5.2 can also split at runtime.
  - Artists direct the tears with maps (glue strength, weakness, Tear Past) or animated constraint properties.
  - A pure time band like ours is unusual, but it gives the most direct control for 爆衣. [INFERRED]
- **Tearing add-ons are commercial, and most do not simulate physics.** [VERIFIED]
  - Dynamic tearing: ClothFX and Simply Tear.
  - Procedural GN tears and frays: Tear Painter, Cloth Ripper, Procedural Torn.
  - Open source: Molecular+ (particle links that break) and the new Cloth Lab (GPL, wraps 5.2).
  - extensions.blender.org has no tearing add-on.
- **Worth adopting, as ideas** [INFERRED]:
  1. release triggered by a nearby object (proximity or Dynamic Paint);
  2. a per-vertex delay or "weakness" map;
  3. automatic cracks from Voronoi islands or UV/sewing seams;
  4. a release that stays on once triggered and spreads along the cracks (3.6 Simulation Zone);
  5. an optional 5.2 backend that feeds our cracks to the *Custom* mode of Cloth Dynamics.

## 1. Blender

### (a) The two-cloth / pin-release family

**The original: blender-布料模拟撕裂效果**
- Link: https://www.bilibili.com/video/BV1Zk4y1x7Eo
- 峰峰居士, 2023-03-24, 6:06, about 26k views, no description. [VERIFIED]
- The author's later "布料撕裂模拟-几何节点" (BV1eSq8YkEvs, 2024-12, Blender 4.3) is a 13-second demo, not a tutorial. [VERIFIED]

**Syziph (2017) and Lawrence Jaeger (2017)**
- Links: https://openvisualfx.com/2017/09/30/stretching-tearing-cloth-in-blender/ and https://medium.com/@_k1ff_/tearing-cloth-in-blender-61a9b9cddd47
- Blender 2.79, free .blend files. [VERIFIED]
- Syziph: Surface Deform, cloth, and a Vertex Weight Mix that animates the pinning; the torn parts are separate objects. [VERIFIED]
- Jaeger [VERIFIED]:
  - Hooks pull cloth 1.
  - A duplicate is ripped in place with V, has a *Tear Pin* group, and is surface-deformed onto cloth 1.
  - A moving Dynamic Paint brush (volume + proximity, fade) writes `dp_weight`.
  - A Vertex Weight Mix (Pin + Tear Pin, masked by `dp_weight`) feeds the pin group of cloth 2, so the cloth tears where the brush has passed.
  - His caveat: "When working with higher resolution, the tear becomes noticeable."
- Rigged garment: yes, if the driver cloth follows the rig. [INFERRED]
- Adopt? **Yes, the moving-brush trigger.** It fits our pin-weight pipeline directly.

**Restart, swap and weld variants**
- Bake, turn the result into a shape key, knife-cut, simulate again (PIXXO 3D, https://www.blendernation.com/2025/09/14/learn-how-to-rip-cloth-in-blender/). [VERIFIED]
- Swap to a pre-cut duplicate at the tear frame (https://blenderartists.org/t/cloth-tearing-before-impact/1441145, 2022). [VERIFIED]
- Switching a Weld modifier off mid-simulation resets the cloth (https://devtalk.blender.org/t/cloth-tearing-test/15312, 2020). [VERIFIED]
- Adopt? No. They do confirm that the split must sit before the cloth modifier.

**specoolar (Shahzod Boyhonov), X post, 2025-07-27**
- Link: https://x.com/specoolar/status/1949561184136626650
- "Found a workaround to simulate tearing clothes using geometry nodes and blender's cloth simulation" (44-second video). [VERIFIED]
- Method: GN drives vertex groups that control the cloth's properties. The torn edges become "super stretchy without collisions" and are removed afterwards with a Mask modifier. [SNIPPET]
- One cloth, no topology change during the simulation. [INFERRED]
- Adopt? **Maybe as a fast-preview mode.** It costs about half of two cloths, but the pieces stay tethered by soft strips. [INFERRED]

**Bilibili GN variants** (metadata only; mechanisms unverified)
- 双雷交火, "Blender几何节点+传统布料 撕碎教程！" (BV14vKTzPESU, 2025-06). The description says only "CGMatter", so it is a translation. [VERIFIED]
- 勤恳的鱼, "blender-几何节点让布料撕裂更可控" (BV1hntU6cEDD, 2026-09-02, 11:36). [VERIFIED]
- 小chan哥, "blender用几何节点撕裂布料细节补充" (BV1eWoLB3Ere, 2026-04). [VERIFIED]
- Adopt? Unknown. BV1hntU6cEDD has an auto-generated subtitle track and is worth watching.

**Other searches**
- 撕衣服 added nothing new. 爆衣 returned game and anime clips; the only Blender item is a 7-second clip (BV1it4y1t77H) "用BLENDER粒子做爆衣" (made with particles). [VERIFIED]
- Japanese searches (布 破れる, 服 破く) found only add-on news. [SNIPPET]

### (b) Molecular / Molecular Plus

- Link: https://github.com/u3dreal/molecular-plus
- Licence: GPL-3.0-or-later. [VERIFIED]
- Blender versions [VERIFIED]:
  - The README says 4.2 to 5.1+, but the v1.21.9 manifest requires 5.1.0 or later.
  - The late-2023 builds (1.13 to 1.14) ran on 3.x; the author wrote "i'm developing on 3.6".
  - The original is by Pyroevil; there is also a scorpion81 fork.
- Mechanism [VERIFIED]:
  - A Cython solver links particles together.
  - A link breaks when it stretches past `LINK_BROKEN` ("0.01 = 1% … 2.0 = 200%").
  - Options: random variation, a separate expansion limit, and a texture-controlled break value.
- Cloth [VERIFIED]:
  - cgdive lists "cloth tearing" as a use; the README lists "Cloth and fabric simulation".
  - But it simulates spheres only, and its output is particles ("Convert for GeoNodes" makes points).
  - Rebuilding a torn mesh from the particles is not documented.
- Rigged garment: I found no way to pin it to a rig. [INFERRED]
- Adopt? No.

### (c) Explode modifier / particle shredding

- Manual: https://docs.blender.org/manual/en/latest/modeling/modifiers/physics/explode.html [VERIFIED]
  - Faces follow particles.
  - *Cut Edges* splits the mesh "based on location of emitted particles".
  - It reads only the initial vertex weights; weights changed by other modifiers are ignored.
- So the timing must come from particle birth, not from a modifier band. [INFERRED]
- The pieces fly off as rigid faces, with no cloth behaviour. [INFERRED]
- Adopt? Not for tearing. At most a confetti finisher for scraps.

### (d) Cell Fracture, rigid-body constraints, BCB, Fracture Modifier

- **Cell Fracture:** GPL-3+; bundled up to 4.1, an extension from 4.2. [VERIFIED]
- **Rigid-body constraints:** a *Breakable* option with an impulse *Threshold*. [VERIFIED]
- **Bullet Constraints Builder:** GPL-2, targets Blender 2.78, made for building collapse (https://github.com/KaiKostack/bullet-constraints-builder). [VERIFIED]
- **Fracture Modifier** (custom build) [VERIFIED]:
  - Fake cloth = shards with point constraints that break above an impulse threshold, plus "Automerge Distance and Perform Merge" to hide the cracks.
  - Its Blend Swap demo (CC-BY, FM build based on 2.79) says: "This is not a cloth simulation."
- Adopt? No: rigid pieces, and the branch is dead. The FM's automerge is the same idea as our merge. [INFERRED]

### (e) Fake tears

- **Mask + Vertex Weight Proximity:** the Mask modifier hides vertices by group, and Vertex Weight Proximity sets weights from the distance to an object. [VERIFIED, manual]
- **Shader dissolve:** an animated noise threshold with an emission edge, in Alpha Blend (coeleveld, Blender 2.82). [VERIFIED]
- **Procedural GN fakes:** [VERIFIED]
  - Bradley Animation, 2021: "Fake Cloth breakage effect… everything procedural" (https://www.youtube.com/watch?v=qydt7RTk7nQ).
  - Ken Liang, 2021: "doesn't require actual simulations".
- **Booleans:** a classic destruction trick (Creative Shrimp, 2014). [VERIFIED]
- **Animated alpha masks:** no source verified.
- All of these work on rigged meshes. [INFERRED]
- Adopt? **Yes, as add-ons to our effect:** Mask + Vertex Weight Proximity to delete slivers and far-flung scraps, a dissolve edge for magic-style 爆衣, and frayed borders.

### (f) Geometry Nodes simulation solvers

**Blender 5.2 Cloth Dynamics**
- Manual: https://docs.blender.org/manual/en/latest/modeling/geometry_nodes/simulation/cloth_dynamics.html
- Blog: https://code.blender.org/2026/07/geometry-nodes-physics/ (Jacques Lucke, 2026-07-30)
- Inputs [VERIFIED]:
  - Pin Group, "for pinning vertices to their rest position";
  - Stretchiness and Bendiness;
  - Substeps and Constraint Iterations;
  - Collision Radius;
  - Tearing: Mode (All, Custom with an Edge Group, Voronoi with a scale) and a Threshold, defined as "Edge length threshold… relative strain".
- Developer docs [VERIFIED]:
  - Topology changes go through "Set Geo Updater – Simulated Topology… special cases like cloth tearing".
  - Pin goals usually come from "animation that is applied before simulation".
- So pins that follow an armature look possible, but this is untested. [INFERRED]
- Demo file: "Space Fabric Cloth Tear" by Cartesian Caramel (CC-BY). [VERIFIED]
- Adopt? **Yes, as an optional 5.2 backend.** Custom mode can take our crease edges directly.

**Bradley Animation**
- A pay-what-you-want bundle for GN 5.2 (https://ko-fi.com/s/7b2d5fa6e5): Basic Cloth Tearing, Pressure Bounce Tearing, Zippering, Stitch Tightening. [VERIFIED]
- A GN 4.3 "Cloth Tearing Transition" tutorial (2025-02); the mechanism is not stated. [VERIFIED]
- Adopt? Study the files.

**Polycount, "Simulation Nodes Generalised Cloth Solver"**
- Pay what you want from $2.64, Blender 4.3+, video "Tear Cloth in Blender with Simulation Nodes" (2024-12-15). [VERIFIED]
- The tearing internals are not documented. One buyer asks how to use it on rigged characters. [VERIFIED]
- Adopt? No.

**Free XPBD-style GN cloth files** by Xeofrios and justry (Blender Artists, 2024) do not tear. [VERIFIED]

### (g) Add-ons

| Add-on | Licence / price | Blender | Mechanism | Rigged garment | Adopt? |
|---|---|---|---|---|---|
| ClothFX (AlbertoFX), superhivemarket.com/products/clothfx | GPL. $20 on Superhive [VERIFIED]; cgdive says "in May 2026 it became free" [VERIFIED there; conflicts] | 4.5–5.0 | Pre-torn mesh (generated or custom tear map). A collider triggers edge splitting on contact, by proximity, or by particles; own dynamics with a "Stress Parameter"; tears in real time, then bakes [VERIFIED] | Not mentioned | The idea: object triggers + tear maps |
| Simply Tear (TAngraFX) | MIT. Lite $9 static, Pro $27 dynamic [VERIFIED] | 4.4–5.1 | Draw tear lines; three algorithms; mesh "activator" objects; internals not documented [VERIFIED] | Not mentioned | No |
| Cloth Ripper (MASSXRZ) | $14 / $49 | 4.0–5.2 | Procedural GN tears and fraying from vertex groups; "supports animated objects, Alembics and Rigs" [VERIFIED] | Yes (fake) | Cosmetic only |
| Tear Painter (Nodes Interactive) | $14.99 | 4.2–5.2 | GN tears and fuzz painted with brush strokes; works on animated meshes [VERIFIED] | Yes (fake) | Cosmetic only |
| Procedural Torn | $15 | 4.1–5.1 | GN tears masked by a weight map [VERIFIED] | Not stated | No |
| Cloth Lab, github.com/dodohan0721/cloth-lab | GPL-3.0+ | 5.2+ for tearing | Wraps 5.2 Cloth Dynamics: tears the whole cloth, selected edges or a fragment pattern; threshold; keyframed grab controls; a bake that stores per-frame meshes; v0.7, 2026-09-26 [VERIFIED] | Not stated | A reference for the 5.2 backend |

- Simply Cloth Studio 2.0 bundles only the static Simply Tear Lite. [VERIFIED]
- extensions.blender.org: searching "tear", "rip", "cloth" and "fabric" found no tearing add-on. [VERIFIED]

### (h) Development history

- **Classic Cloth manual (5.2):** no tearing feature. [VERIFIED]
- **2017 cloth improvements post:** no tearing; commenters asked for it. [VERIFIED]
- **devtalk, 2020:** ZedDB wrote: "the cloth solver does not support dynamic tearing or deletion of connected edges… Things would need to be restructured and rewritten". [VERIFIED] This is the closest thing to an official statement.
- **GSoC adaptive cloth:** the 2019 proposal named "dynamic tearing of cloth" as a future improvement; the 2021 one called itself the "foundation to add Adaptive Cloth Tearing" but left tearing out of scope. [VERIFIED] It was never merged. [INFERRED]
- **Fracture Modifier branch:** fake cloth only. [VERIFIED]
- **2026:** 5.2 adds tearing through GN XPBD. [VERIFIED]

## 2. How the big DCCs define tearing

| DCC | What triggers the tear | How the topology splits | Rigged garment |
|---|---|---|---|
| **Maya nCloth, Tearable Surface** (docs 2014/2016) | The Glue Strength is exceeded, typically on collision; a painted Glue Strength map chooses where [VERIFIED] | Pre-split: "separating all of its faces… merging the nCloth's vertices… constraining… points… together using the Weld constraint method" [VERIFIED] | Yes [INFERRED] |
| **Houdini Vellum** | A weld breaks past its Threshold (stretch stress, bend stress, stretch distance, stretch ratio, bend angle) [VERIFIED]. The Vellum Constraint Property DOP can change thresholds or set "Remove" through a VEXpression [VERIFIED], which allows time- or attribute-driven breaks [INFERRED] | Pre-cut (Edge Fracture along curves) plus Vellum Weld Points, which fuse separate points logically [VERIFIED] | Yes [INFERRED] |
| **3ds Max Cloth** (2025 help) | Forces exceed the weld Strength (= Tear Threshold), or the cloth hits an object set to "Cuts Cloth" [VERIFIED] | "You must specify where the cloth will tear before you run the simulation." Make Tear turns a vertex selection into a Weld; seams can be set Tearable [VERIFIED] | Yes [INFERRED] |
| **tyFlow** (the free version allows commercial use; it lacks multithreading, GPU and tyCache export [VERIFIED]) | Stretch past a "Maximum %" for a set number of frames; weakness, with an optional animated weakness map; a "Max tears/step" limit [VERIFIED]. Particle Break's "Treat breaks as tears" lets events break bindings [VERIFIED] | Splits at runtime; "Chamfer pinched verts" cleans up the results [VERIFIED] | Yes [INFERRED] |
| **Cinema 4D** (S26+) | Cloth Tearing, Tear Past (+ map), Tear Guiding cone angle [VERIFIED, SDK]. The name suggests a stretch threshold [INFERRED]. Vertex maps and a Cloth Belt control the release [VERIFIED, tutorial] | At runtime [INFERRED] | Yes [INFERRED] |
| **Marvelous Designer 2026.1** (2026-08-24, from $39/month) | [Beta] Seamline Ripping: you mark "part or all of an existing sewing line"; it opens when the forces meet a "Rip Resistance" (yield strength and damage accumulation rate) [VERIFIED] | The sewing lines are the pre-split. Procedural fraying, which cannot be exported as a mesh and is disabled on Mac [VERIFIED] | Yes [INFERRED] |
| **Ours** | A time band | Pre-split along the crease cracks, pinned to cloth 1, rejoined by a GN merge | Yes |

**What this means for us** [INFERRED]
- The DCCs agree with our topology model and differ only in the trigger.
- In our stack, the pin group of cloth 2 cannot read cloth 2's own strain, so a true stress trigger is out of reach.
- What carries over: delay or weakness maps, a cap on release speed (like tyFlow's "Max tears/step"), and seam-based crack presets (like Marvelous Designer).

## Gaps

- **Videos not watched**, so mechanisms are unverified for: the Bilibili GN tutorials (and the CGMatter original, not located), Bradley's 4.3 tutorial, and the Polycount solver.
- **specoolar's method** comes only from a search snippet.
- **Molecular:** no documented route from particles back to a torn mesh.
- **Explode + cloth "Cut Edges":** no tutorial found.
- **Commercial tools:** ClothFX's price claims conflict; ClothFX and Simply Tear internals are undocumented.
- **Cinema 4D:** the Tear Past manual text was unreachable, so its meaning is inferred.
- **Maya:** newer docs returned errors; the facts rest on the 2014/2016 pages.
- **Blender 5.2:** untested whether pins follow an armature-deformed input.
- **Not checked:** the tyFlow PRO price; Fracture Modifier builds after 2.79.
- **Access:** Bilibili's API returned HTTP 412 here (pages read via WebFetch); the web-search budget ran out near the end.
