"""TFD's UE 5.2 type mappings -> a Vindictus (UE 5.3) usmap for the level classes, patched from the level data:
- StaticMeshComponent has 2 more properties in 5.3 (OverrideMaterials moves 31 -> 33); appended as dummy bools;
- PrimitiveComponent has 3 more (BodyInstance 122 -> 127 in the static mesh chain, 96 -> 99 in BoxComponent's);
  they sit before IndirectLightingCacheQuality (5.3 index 45 = 5.2's 40) and are put at its start as dummy bools.
- HierarchicalInstancedStaticMeshComponent has 1 more (12 -> 13): AttachParent 170 -> 171 on plain HISM; in the
  foliage chain TranslatedInstanceSpaceOrigin .. UnbuiltInstanceBounds keep their places (locals 1-5),
  OcclusionLayerNumNodes (Int 8) sits at local 9, CacheMeshExtendedBounds at 10, InstanceCountToRender at 12 - so the
  new one is somewhere in locals 6-8; put at 6 as a dummy bool.
Everything else checked so far (SceneComponent, ActorComponent, InstancedStaticMeshComponent's own,
FoliageInstancedStaticMeshComponent's own) is unchanged.
  python patch_usmap.py <tfd.usmap> <out.usmap>"""
import sys

import usmap

m = usmap.load(sys.argv[1])
names = m["names"]


def dummy(label):
    names.append(label)
    return len(names) - 1


smc = m["structs"]["StaticMeshComponent"]
for k in range(2):
    smc["props"].append({"index": smc["count"] + k, "dim": 1, "name": dummy("Vdf53_StaticMeshComponent_New%d" % k),
                         "type": {"type": "Bool"}})
smc["count"] += 2

prim = m["structs"]["PrimitiveComponent"]
for p in prim["props"]:
    p["index"] += 3
prim["props"] = [{"index": k, "dim": 1, "name": dummy("Vdf53_PrimitiveComponent_New%d" % k), "type": {"type": "Bool"}}
                 for k in range(3)] + prim["props"]
prim["count"] += 3

hism = m["structs"]["HierarchicalInstancedStaticMeshComponent"]
for p in hism["props"]:
    if p["index"] >= 6:
        p["index"] += 1
hism["props"].append({"index": 6, "dim": 1, "name": dummy("Vdf53_HierarchicalInstancedStaticMeshComponent_New0"),
                      "type": {"type": "Bool"}})
hism["props"].sort(key=lambda p: p["index"])
hism["count"] += 1
# CacheMeshExtendedBounds is written as a plain struct WITH its own unversioned header (u16 0x0700 = 3 values) in
# these packages; CUE4Parse reads BoxSphereBounds natively (56 bytes, 2 off) -> give it a look-alike struct type.
bsb = "Vdf53BoxSphereBounds"
names.append(bsb)
m["structs"][bsb] = {"name": len(names) - 1, "super": None, "count": 3, "props": [
    {"index": 0, "dim": 1, "name": names.index("Origin"), "type": {"type": "Struct", "struct": names.index("Vector")}},
    {"index": 1, "dim": 1, "name": names.index("BoxExtent"), "type": {"type": "Struct", "struct": names.index("Vector")}},
    {"index": 2, "dim": 1, "name": names.index("SphereRadius"), "type": {"type": "Double"}}]}
m["order"].append(bsb)
for p in hism["props"]:
    if names[p["name"]] == "CacheMeshExtendedBounds":
        p["type"] = {"type": "Struct", "struct": len(names) - 1}
usmap.save(m, sys.argv[2])
check = usmap.load(sys.argv[2])
for cls, prop in (("StaticMeshComponent", "OverrideMaterials"), ("StaticMeshComponent", "BodyInstance"),
                  ("StaticMeshComponent", "RelativeLocation"), ("BoxComponent", "BodyInstance"),
                  ("InstancedStaticMeshComponent", "AttachParent"), ("StaticMeshComponent", "CreationMethod"),
                  ("HierarchicalInstancedStaticMeshComponent", "AttachParent"),
                  ("FoliageInstancedStaticMeshComponent", "StaticMesh"),
                  ("FoliageInstancedStaticMeshComponent", "CacheMeshExtendedBounds"),
                  ("FoliageInstancedStaticMeshComponent", "InstanceCountToRender"),
                  ("FoliageInstancedStaticMeshComponent", "InstancingRandomSeed")):
    idx = [i for i, c, n, t in usmap.schema(check, cls) if n == prop]
    print("%s.%s -> %s" % (cls, prop, idx))
