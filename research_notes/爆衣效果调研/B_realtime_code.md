# Survey B: open-source tearable cloth (demos, solvers, engines, research, middleware)

Checked 2026-10-02. Tags: [VERIFIED] read on the page or in the code; [SNIPPET] search snippet only; [INFERRED] my reasoning. Stars as of that day. RT = real-time.

## Key takeaways

1. **There are only two tear rules.**
   - (a) Delete a constraint once its length is more than k × its rest length [VERIFIED].
   - (b) Split a vertex: take one end of the over-stretched edge, put a plane through it perpendicular to the edge, and give the triangles on one side a duplicate vertex. PBD 2006, PhysX 2.8 and FleX all do this [VERIFIED].
   - Production code also pre-marks tear lines and caps splits per step: PhysX 2.8 `NX_CLOTH_VERTEX_TEARABLE`, FleX `maxSplits` = 4, SOFA `fractureMaxLength` [VERIFIED].
2. **Blender 5.2 LTS (July 2026) now tears cloth.** Its experimental XPBD *Cloth Dynamics* node takes a relative-strain *Threshold* and has three modes: *All*, *Custom* (edge group) and *Voronoi* (untearable islands) [VERIFIED]. It is the closest open-source (GPL) match to our add-on, but it releases on stress, not on time.
3. **Our design is the standard workaround for clothes on a character.** Obi's developer advises stitching skinned cloth along a seam and removing the stitches on cue [VERIFIED]. Houdini Vellum pre-cuts the cloth and joins it with breakable welds [VERIFIED]. Only the trigger differs: they release on force, we release on time.
4. **Best upgrade:** release the band where measured strain says so, not on a timer. Add Obi-style "debilitation" around each release and a cap on releases per frame (section 8) [INFERRED].
5. **Most engines have dropped tearing.**
   - PhysX 3 removed it, PhysX 5's new deformable surface "won't support tearing", and Unity 5 and Magica Cloth have none [VERIFIED].
   - Jolt, Godot SoftBody3D and Chaos Cloth document none [VERIFIED].
   - Of the products I checked, real-time tearing survives in Obi (not for skinned cloth) and the old FleX [VERIFIED]. I did not check every asset on the market [INFERRED].
6. **Research code runs offline and is heavy to integrate.** ARCSim (non-profit licence), CD-MPM/AnisoMPM and SOFA Tearing (GPL) are sources of ideas, not drop-in solvers. C-IPC deliberately limits strain instead of fracturing [VERIFIED].
7. **Cheap visual layer:** a noise-threshold burn edge, driven by our release attribute, would hide the straight seams [INFERRED].

## 1. Classic demos (all RT)

| Repo | Stack | Tear rule | Stars / licence |
|---|---|---|---|
| [dissimulate/Tearable-Cloth](https://github.com/dissimulate/Tearable-Cloth) | JS canvas, Verlet | In `Constraint.resolve()`: `if (dist > tearDist) this.p1.free(this)`, with `tearDist` 60 against a spacing of 8 (7.5× rest). A non-left mouse drag empties `this.constraints` within `mouse.cut` = 8 | 1,504; **no licence file** [VERIFIED] |
| [suntabu/Unity_Tearable_Cloth](https://github.com/suntabu/Unity_Tearable_Cloth) | Unity port of the above | Same | 7; Apache-2.0 [VERIFIED] |
| [bennybroseph/Unity-Physics](https://github.com/bennybroseph/Unity-Physics) | Unity, own springs | A spring past its limit "breaks, and any triangles associated with that spring are ripped as well" | 42; none shown [VERIFIED] |
| [NiallHornFX/VerletClothMeshComponent](https://github.com/NiallHornFX/VerletClothMeshComponent) | UE4, PBD | None ("In the future this could be used to allow tearing") | 46; MIT [VERIFIED] |
| [OccultParrot/ClothSim](https://github.com/OccultParrot/ClothSim) | Godot 4 | Right-click cuts sticks | 0; MIT [VERIFIED] |
| [xavieryarde/ClothSimGL](https://github.com/xavieryarde/ClothSimGL) | C++/OpenGL, Verlet | Mouse "Tear mode"; rule not documented | 25; MIT [VERIFIED] |
| [jbargu/cloth-simulation-bevy-rust](https://github.com/jbargu/cloth-simulation-bevy-rust) | Rust/Bevy | Right mouse removes links near the cursor | 9; MIT [VERIFIED] |
| [Balaur engine](https://balaurengine.org/blog/soft-bodies/) | Rust, Rapier | "Past `tear_strain` or `tear_force` an edge breaks, and the node's `on_tear` runs" | MIT; blog 2026-09-25 [VERIFIED] |

- Nothing notable exists for Godot or WebGPU.
- The "XPBD tearing" repos I found (tensor-cloth-wgsl, XPBD_tear) have 0–1 stars and are AI-generated [VERIFIED].
- **For Blender 3.6:** the length/rest test is the trigger our band needs, computed per crack edge in GN [INFERRED].

## 2. PBD / XPBD

**Müller, Heidelberger, Hennix, Ratcliff, "Position Based Dynamics"** ([PDF](https://matthias-research.github.io/pages/publications/posBasedDyn.pdf); VRIPHYS 2006, with JVCIR 2007 as the journal version)
- Quote: "Whenever the stretching of an edge exceeds a specified threshold value, we select one of the edge's adjacent vertices. We then put a split plane through that vertex perpendicular to the edge direction and split the vertex. All triangles above the split plane are assigned to the original vertex while all triangles below are assigned to the duplicate." [VERIFIED]
- The demo tears 4,264 vertices at 47 fps; the authors were at AGEIA [VERIFIED]. RT.
- **For Blender 3.6:** the resulting topology is the same as our Split Edges, so take only the stretch trigger [INFERRED].

**Ten Minute Physics** ([index](https://matthias-research.github.io/pages/tenMinutePhysics/index.html); repo 917 stars, no licence)
- 25 tutorials. Cloth (#14) and self-collision (#15) are covered, but **there is no tearing demo** [VERIFIED].

**Jan Bender's [PositionBasedDynamics](https://github.com/InteractiveComputerGraphics/PositionBasedDynamics)** (MIT, 2.3k)
- Neither the feature list nor the demo folders include tearing [VERIFIED].
- **For Blender 3.6:** nothing to take.

**How XPBD breaks constraints** ([Macklin, Müller, Chentanez 2016](https://matthias-research.github.io/pages/publications/XPBD.pdf))
- The paper keeps a per-constraint λ that "provides useful information on the total constraint force, and can be used to drive force dependent effects (e.g.: breakable joints)" [VERIFIED].
- Since λ = −α̃⁻¹C and α̃ = α/Δt², the force is about λ/Δt². A constraint breaks when that force passes a limit [VERIFIED formula; rule INFERRED].
- Global solvers must re-factor when topology changes "such as due to tearing or fracturing"; local PBD solvers do not [VERIFIED].
- Blender 5.2's [XPBD Simulation](https://developer.blender.org/docs/features/nodes/xpbd_simulation/) does both parts [VERIFIED]:
  - it can write λ to an attribute "for driving secondary effects such as cloth tearing";
  - its "Simulated Topology" updater "supports changes to topology during simulation", matching vertices by their original index.
- Obi gives tear resistance in Newtons [VERIFIED].
- **For Blender 3.6:** the built-in cloth exposes no λ, so use strain as the force proxy [INFERRED].

**Blender 5.2 LTS Cloth Dynamics** ([manual source](https://projects.blender.org/blender/blender-manual/raw/branch/main/manual/modeling/geometry_nodes/simulation/cloth_dynamics.rst); [blog, 2026-07-30](https://code.blender.org/2026/07/geometry-nodes-physics/)); licence GPL [INFERRED]
- Tearing "splits the mesh along edges where stretching forces become too large" [VERIFIED].
- The *Threshold* is "relative strain … with equivalent stress depending on the stretchiness factor" [VERIFIED].
- Modes: *All*, *Custom* (an *Edge Group*), and *Voronoi*, which makes "untearable islands" [VERIFIED].
- The Pin Group pins to the rest shape. The input mesh is the geometry "that should be animated or simulated … used as the rest shape", so an armature-deformed garment works [VERIFIED].
- Experimental, with no self-collision [VERIFIED]. It first shipped in 5.2 [SNIPPET].
- **For Blender 3.6:** two options [INFERRED]:
  - Bake in 5.2, with *Custom* set to our crack edges and the Pin Group set to our garment pins, then import into 3.6 as Alembic, which handles a changing vertex count.
  - Copy the Voronoi-island idea to generate crack edges automatically.

## 3. NVIDIA

**PhysX 2.8** (proprietary, RT)
- SDK sample code quoted on the [Ogre forum](https://www.ogre3d.org/addonforums//6/t-2741.html) [VERIFIED]:
  - `NX_CLF_TEARABLE` makes the cooker set `NX_CLOTH_MESH_TEARABLE`;
  - buffers are over-allocated (`TEAR_MEMORY_FACTOR 2`), because "the SDK only tears cloth as long as there is room in these buffers";
  - `NX_CLOTH_VERTEX_TEARABLE` marks tear lines.
- `tearFactor` is an elongation limit. Unity 4 documents it as: "How far cloth vertices need to be stretched, before the cloth will tear… zero… disabled" ([docs](https://docs.unity3d.com/462/Documentation/ScriptReference/InteractiveCloth-tearFactor.html)) [VERIFIED].
- `tearVertex(vertex, normal)` gives the triangles above the plane to the duplicate vertex [SNIPPET]. Hardware tearing was limited per mesh patch, so users were told to "specify tear lines" [SNIPPET]. The split rule is the PBD paper's [INFERRED].
- **Why it was dropped:** "PhysX 3 cloth is a rewrite of the PhysX 2 deformables, tailored towards simulating character cloth. Softbodies, tearing, and two-way interaction have been removed" ([3.4 manual](https://archive.docs.nvidia.com/gameworks/content/gameworkslibrary/physx/guide/Manual/Cloth.html)) [VERIFIED]. The constraints are cooked into a `PxClothFabric` that instances share [VERIFIED], so tearing would need a re-cook [INFERRED].

**PhysX 5** ([repo](https://github.com/NVIDIA-Omniverse/PhysX); BSD-3, 4,780)
- NVIDIA's Simon Schirm, 2024-11-26: particle cloth "is deprecated", and the new PxDeformableSurface "won't support tearing" ([#328](https://github.com/NVIDIA-Omniverse/PhysX/discussions/328)) [VERIFIED].

**FleX** ([repo](https://github.com/NVIDIAGameWorks/FleX); 814 stars; RT)
- **Licence:** LICENSE.txt is the "Nvidia Source Code License (1-Way Commercial)": royalty-free, redistributable with the licence attached [VERIFIED]. File headers still say "NVIDIA Confidential Information" [VERIFIED].
- **Source:** the solver ships prebuilt in `lib/<platform>` [VERIFIED folder; binary-only INFERRED]. The tearing code is source, in `extensions/flexExtCloth.cpp` and `core/cloth.h` [VERIFIED].
- **`NvFlexExtTearClothMesh` step by step** [VERIFIED]:
  1. Loop over springs while `splits < maxSplits` and while spare particles remain (`maxParticles − numParticles`).
  2. A spring tears if `Length(p-q) > springRestLengths[i]*maxStrain` and neither end is fixed (w == 0).
  3. Pick an end with `Randf() > 0.5f ? a : b`.
  4. Split plane `Normalize(p-q)`: `ClothMesh::SplitVertex` moves the triangles whose centroid is on one side to a new vertex.
  5. `SeparateVertex` flood-fills the neighbours to un-share bow-tie vertices.
  6. Output particle clones (copy position, velocity and phase) and triangle-index edits.
- **Demo `tearing.h`:** `maxStrain` 3.0, 4 splits per step, 2,048-entry buffers [VERIFIED].
- **Stability:** sharp tugs exploded the demo. Macklin advised the local relaxation mode ([2017](https://forums.developer.nvidia.com/t/instability-in-flex-cloth-tearing/51326)) [VERIFIED].
- **For Blender 3.6:** the best algorithm to port into a numpy PBD solver, like the one in our Bone Cloth add-on [INFERRED].

**Warp / Newton** (Apache-2.0)
- No tearing examples. Newton's cloth examples are bending, hanging, style3d, h1, twist, franka, rollers and poker_cards [VERIFIED].

## 4. Other engines

**[Bullet](https://github.com/bulletphysics/bullet3)** (zlib, 14.8k; RT)
- `btSoftBody::cutLink(n0, n1, pos)` inserts two coincident nodes and rewires the links [VERIFIED].
- `refine(ImplicitFn*, accuracy, cut)` inserts nodes where edges cross an implicit surface and, with `cut`, duplicates them [VERIFIED].
- The `Init_Cutting1` demo cuts with an `ImplicitSphere` at the mouse hit point [VERIFIED].
- There is no stress-driven tearing [VERIFIED].
- **For Blender 3.6:** the idea only, i.e. cut along any curve by inserting vertices first [INFERRED].

**Godot SoftBody3D**
- The API has no tearing or topology calls, and the docs recommend Jolt [VERIFIED].
- The community has only custom Verlet scripts [VERIFIED].

**[Jolt](https://github.com/jrouwe/JoltPhysics)** (MIT, 11.6k)
- Soft bodies support edge, bend, rod, volume, tether and skinned constraints, plus pressure. There is no tearing [VERIFIED].
- Tearing would mean rebuilding `SoftBodySharedSettings` [INFERRED].

## 5. Research code

**[ARCSim](https://graphics.eecs.berkeley.edu/resources/ARCSim/)** (Pfaff et al., SIGGRAPH 2014; offline)
- v0.3.1 "supports dynamic fracturing and tearing of thin sheets" [VERIFIED].
- It refines the mesh around crack tips and coarsens it elsewhere [VERIFIED].
- Licence: "non-profit use", with citation required [VERIFIED].
- **For Blender 3.6:** reference only. There is no skinned-character path and no commercial use [INFERRED].

**[SOFA Tearing](https://github.com/InfinyTech3D/Tearing)** (GPL or commercial; 12 stars)
- Parameters [VERIFIED]:
  - `seuilStress`: the element stress that marks an element fractured;
  - `fractureMaxLength`: the maximum fracture length per step;
  - `nbFractureMax`: the maximum number of fractures.
- Paths are cut "from one point to a direction". Readiness level is TRL 4 for surfaces and TRL 3 for volumes [VERIFIED].
- **For Blender 3.6:** copy the per-step length cap as a tear-speed limit [INFERRED].

**MPM** (offline)
- **Jiang, Gast, Teran 2017:** the abstract does not mention tearing [VERIFIED]. A figure caption about "tearing apart a fibrous material" may come from this paper [SNIPPET]. I found no code.
- **[CD-MPM](https://github.com/penn-graphics-research/ziran2019)** (MIT, 250) and **[AnisoMPM](https://github.com/penn-graphics-research/ziran2020)** (231; licence not shown): damage degrades the tensile energy "to allow for material separation". AnisoMPM makes cracks follow the fibre direction [VERIFIED].
- **[taichi_elements](https://github.com/taichi-dev/taichi_elements)** (MIT, Blender add-on): water, elastic, snow and sand only; no cloth [VERIFIED].
- **Genesis** (Apache-2.0): PBD cloth without tearing [VERIFIED].
- **For Blender 3.6:** not suitable for garments [INFERRED].

**[C-IPC](https://github.com/ipc-sim/Codim-IPC)** (Apache-2.0, 249)
- Quote: "either fracture should be captured beyond this regime or else a stable and controllable strain limit imposed … we focus on … strain limit". So it does **not** fracture [VERIFIED].

**2018–2026 work**
- Fan, Chitalu, Komura (CGF 2025): phase-field tearing of thin shells [SNIPPET]; I found no code.
- FracGen (arXiv, 2026-09-29): generates video of fracture, not specific to cloth [VERIFIED].
- The only production-grade open code I found is Blender 5.2's [INFERRED].

## 6. Middleware (commercial)

**[Obi Cloth](https://obi.virtualmethodstudio.com/manual/7.0/clothtearing.html)** (RT)
- Parameters [VERIFIED]:
  - *Tear Capacity*: spare particles pre-allocated; 1 means every triangle can tear.
  - *Tear Resistance Multiplier*: "How much force must be applied … in Newtons", scaled per particle.
  - *Tear Debilitation*: "multiplies the tear factor of all edges incident to a torn particle". High values give more coherent tear paths, and 0.2–0.6 "tend to give the most realistic result".
- No tethers and no skinned meshes [VERIFIED].
- For Obi Rope, the developer says the heavier end particle splits and both halves get half the mass [VERIFIED].
- For clothes on a character, the developer says to "use stitch constraints to stitch skinned cloth particles together" and remove them on cue ([2023](https://obi.virtualmethodstudio.com/forum/thread-3838.html)) [VERIFIED]. That is our pattern.

**Magica Cloth**
- The developer wrote on 2022-04-20: "does not have a tearing function, so basically it can stretch but not tear". The Magica Cloth 2 feature list has no tearing either [VERIFIED].

**Unity Cloth**
- Unity 4's InteractiveCloth had `tearFactor`. In Unity 5, "tearing is no longer supported" [VERIFIED].

**Unreal**
- The Chaos Cloth update posts for 5.7 (2025-11-12) and 5.8 (2026-06-17) do not mention tearing [VERIFIED].
- A YouTube "Chaos Cloth: Interactive Tearing" claims tearing in 5.4.1 [SNIPPET].
- Chaos Flesh: no tearing found [SNIPPET].
- The PhysX-2-based UE3 cloth had `ClothTearFactor` [SNIPPET].

**Havok Cloth**
- The 2009 announcement does not mention tearing [VERIFIED].

**[Houdini Vellum](https://www.sidefx.com/docs/houdini/vellum/breaking_tearing.html)**
- *Edge Fracture* pre-cuts the cloth. *Vellum Weld Points* re-joins it, with *Breaking* and a *Threshold* [VERIFIED].
- *Normalize Stress* keeps the thresholds stable across substeps [VERIFIED].
- There is no official Houdini Engine for Blender [SNIPPET].
- **For Blender 3.6:** the same structure as ours, but triggered by stress.

## 7. Non-physics damage (RT)

**Dissolve and burn shaders**
- [godotshaders 3D burn dissolve](https://godotshaders.com/shader/3d-burn-dissolve/) (MIT): `ALPHA = smoothstep(dissolve_amount - burn_size, dissolve_amount, sample)`, plus an emissive band [VERIFIED].
- [BurnDissolveUnityBootCamp](https://github.com/caliber44/BurnDissolveUnityBootCamp) (MIT, URP): spreads the burn with a compute shader [VERIFIED].
- **For Blender 3.6:** compare noise with (frame − release_frame), then mix to Transparent and add an emissive rim [INFERRED].

**Painting holes into textures**
- [IRCSS/TexturePaint](https://github.com/IRCSS/TexturePaint) (MIT, 382): renders brushes into the texture in UV space, with world-space distance and seam dilation [VERIFIED].
- **For Blender 3.6:** use Dynamic Paint or vertex-colour masks for alpha, which also work as tear seeds [INFERRED].

**Damage by blend shapes**
- Common practice, but I found no notable open-source clothing example.

## 8. What to adopt (Blender 3.6, offline)

1. **Strain-driven band** [INFERRED].
   - A free probe cloth (or cloth 1 when not in garment mode) runs first. GN measures length/rest on each crack edge.
   - A Simulation Zone (available since 3.6 [SNIPPET]) records `release_frame` when the strain exceeds k. Cloth 2's pin band reads that attribute.
   - In garment mode, measure the stretch caused by the body instead, e.g. inflation morphs for the "burst" case.
2. **Debilitation and a cap.** After an edge releases, lower the thresholds of its neighbouring crack edges (Obi's "tear debilitation"; the exact Obi scaling is not documented), and limit releases per frame [INFERRED].
3. **Automatic crack lines from Voronoi islands** [INFERRED].
4. **Optional numpy PBD path:** FleX's split-and-separate step, for tears that are not pre-marked [INFERRED].
5. **Shader fray** on the release front [INFERRED].

## Gaps

- The PhysX 2.8 `NxClothDesc`/`NxCloth` pages and the UDK pages were blocked (403), so those details come from forum quotes and snippets.
- I did not read the node group inside 5.2's Cloth Dynamics. Its behaviour with an animated rest shape and with colliders is untested.
- I did not check the Chaos source; the YouTube tearing claim is unverified.
- Obi documents its split rule only for rope. Havok's docs are not public.
- Jiang 2017's tearing content and Fan 2025's code are unconfirmed.
- I found no notable GPU-PBD or neural cloth-tearing paper with released code.
- The GitHub API was rate-limited, so some star counts come from scraping the repo pages.
