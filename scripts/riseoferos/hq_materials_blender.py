"""The game's full materials on a ROE model in Blender (Blender side of hq_material_data.py).

The AssetStudio FBX route gives exact geometry, custom normals and weights, but the ROE add-on builds
albedo-only materials, and a PMX carries one colour texture per material.  apply() ties every slot to
its game material and builds the lit ones with all their inputs:

  pbr   albedo x _BaseColor x AO, normal map, MGAC (R metallic, G smoothness, B ambient occlusion;
        A is a copy of G), _Metallic / _Smoothness / _OcclusionStrength / _BumpScale; the AO also
        scales Specular (the game occludes indirect specular: a glossy crease must not mirror the sky)
  skin  pbr + subsurface scattering (the game's translucency / skin LUT) + the tiled detail normal
        (_DetailNormalMap x _DetailBumpScale, 70x on the faces)
  hair  albedo x _BaseColor (the per-character hair colour: the family's grey albedo is tinted, g by
        sRGB 0.54 / 0.41 / 0.41) x strand occlusion, alpha cut at _Cutoff, hair normal map
  colours (_BaseColor, _EmissionColor) are stored in sRGB and converted to linear, as the game does
  alpha test / transparency / emission follow the game flags.  Eyes, brows / lashes and tears keep
  what they have.

Slot -> game material, by the slot's colour texture: a game material's _BaseMap (FBX import), or the
export textures hq_material_data.py wrote (<material>__pmx_diffuse / __xps_diffuse: a PMX or XPS
import).  The name the ROE add-on stored from the FBX (``roe_source_materials`` + per-face
``roe_source_material_index``) breaks ties (body and skin share one albedo).

Two ways of building:
  new materials (default)  one shared "HQ_<game>" material per game material replaces the slot's -
                           the batch worker (export_character_model_blender.py; revert() puts the
                           add-on's materials back for XPS / GLB, use_pmx_textures() for PMX) and the
                           ROE add-on button "2.5 游戏原始材质"
  in place (in_place=True) the network is added INTO each existing material next to its own nodes
                           and gets its own output node, made the active one: an mmd_tools material
                           keeps its MMD shader, its textures and everything the PMX export reads,
                           and set_mode() switches between the two looks (the roe_game_materials
                           add-on, for animating an imported PMX in Blender)
Every node this module adds is named hq_*; apply_params() retunes them live (defaults: DEFAULT_PARAMS,
multipliers on the game's own values).

Standalone, for a .blend that was exported earlier:
  blender -b --factory-startup <in.blend> --python hq_materials_blender.py -- <out.blend> [--cache DIR]
"""
import json
import os
import re
import subprocess
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA_SCRIPT = os.path.join(HERE, "hq_material_data.py")
DEFAULT_EXPORT_ROOT = r"D:\roe_exports"
DEFAULT_PARAMS = {
    "normal": 1.0,           # x the game's _BumpScale
    "detail": 1.0,           # x the game's _DetailBumpScale (skin pores)
    "ao": 1.0,               # x the game's _OcclusionStrength (the result is kept within 0..1)
    "smooth": 1.0,           # x the game's _Smoothness (on MGAC G)
    "metal": 1.0,            # x the game's _Metallic (on MGAC R)
    "sss": 0.1,              # skin subsurface weight (Blender 3.x also scales the radius by it)
    "hair_rough": 0.45,      # hair roughness (the game's hair shader has no smoothness map)
    "spec_occlusion": True,  # AO also darkens the highlights
}
SUBSURFACE_RADIUS = (0.06, 0.02, 0.012)   # metres before the weight: ~6 / 2 / 1.2 mm red / green / blue
NORMAL_SLOTS = {"_BumpMap", "_DetailNormalMap", "_EyeBumpMap"}
EXPORT_SUFFIXES = ("__pmx_diffuse", "__xps_diffuse")
PREFIX = "hq_"
# kept for callers of the first version
SUBSURFACE = DEFAULT_PARAMS["sss"]
HAIR_ROUGHNESS = DEFAULT_PARAMS["hair_rough"]


# --- slots -----------------------------------------------------------------------------------------
def image_stem(image):
    name = os.path.basename(bpy.path.abspath(image.filepath or "")) or image.name
    name = re.sub(r"\.\d{3}$", "", name)
    name = re.sub(r"\.(png|tga|jpg|jpeg|dds|bmp)$", "", name, flags=re.IGNORECASE)
    return re.sub(r"\.\d{3}$", "", name)


def _upstream_image(socket, seen=None):
    seen = seen if seen is not None else set()
    for link in getattr(socket, "links", ()):
        node = link.from_node
        if node in seen:
            continue
        seen.add(node)
        if node.type == "TEX_IMAGE" and node.image:
            return node.image
        for inp in node.inputs:
            found = _upstream_image(inp, seen)
            if found:
                return found
    return None


def _principled(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    nodes = material.node_tree.nodes
    return nodes.get(PREFIX + "bsdf") or next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)


def slot_albedo(material):
    """The slot's colour texture: what feeds Base Color, mmd_tools' base texture (PMX import) or the
    XPS shader's Diffuse (XPS import)."""
    if material is None or not material.use_nodes or material.node_tree is None:
        return ""
    bsdf = _principled(material)
    image = _upstream_image(bsdf.inputs["Base Color"]) if bsdf else None
    nodes = material.node_tree.nodes
    if image is None:
        node = nodes.get("mmd_base_tex")
        image = node.image if node is not None and getattr(node, "image", None) else None
    if image is None:
        group = next((n for n in nodes if n.type == "GROUP" and "Diffuse" in n.inputs), None)
        image = _upstream_image(group.inputs["Diffuse"]) if group else None
    return image_stem(image) if image else ""


def slot_sources(obj):
    """{slot index: game material name the ROE add-on stored from the FBX (by face majority)}."""
    names = [n for n in str(obj.get("roe_source_materials", "")).split("\n")]
    attr = obj.data.attributes.get("roe_source_material_index")
    if not any(names) or attr is None:
        return {}
    count = len(obj.data.polygons)
    src = np.empty(count, dtype=np.int64)
    attr.data.foreach_get("value", src)
    slot_of = np.empty(count, dtype=np.int64)
    obj.data.polygons.foreach_get("material_index", slot_of)
    out = {}
    for index in range(len(obj.material_slots)):
        picked = src[slot_of == index]
        if len(picked):
            i = int(np.bincount(picked).argmax())
            if i < len(names) and names[i]:
                out[index] = names[i]
    return out


def safe_name(name):
    """File-name form of a material name, as hq_material_data.py writes the export textures."""
    return "".join(c if c.isalnum() or c in "-." else "_" for c in name)


def _base_map(mdef):
    return mdef["textures"].get("_BaseMap", {}).get("texture", "")


def pick_material(materials, albedo, source, old_name):
    if not albedo:
        return None
    for suffix in EXPORT_SUFFIXES:                 # a PMX / XPS export texture names its material
        if albedo.lower().endswith(suffix):
            base = albedo[:-len(suffix)]
            return next((n for n in materials if safe_name(n) == base), None)
    cands = [n for n, d in materials.items() if _base_map(d).lower() == albedo.lower()]
    if source in cands:
        return source
    if len(cands) > 1:
        skin = "skin" in (old_name or "").lower()
        cands = [n for n in cands if ("skin" in n.lower()) == skin] or cands
        cands.sort(key=lambda n: ("_ld" in n.lower(), n))
    return cands[0] if cands else None


def role_of(mdef):
    tex, kw = mdef["textures"], set(mdef["keywords"])
    if "_ShiftNoiseMap" in tex or "HAIR_AM" in kw:
        return "hair"
    if "_IrisAlbedoTex" in tex or "_BaseMap" not in tex:
        return None                        # eyes (procedural shader), tears, empties: keep
    if "_BumpMap" in tex or "_MetallicGlossMap" in tex:
        skin = "_SkinLutMap" in tex or mdef["floats"].get("_EanbleTranslucency", 0.0) > 0.0  # sic
        return "skin" if skin else "pbr"
    return None                            # albedo-only (brows / lashes): keep


def infer_cid(stem, albedos=()):
    """Character id (a01, g05 ...) from a model / file name, else from the texture names."""
    match = re.search(r"pc[_ ]([a-z]\d+)", (stem or "").lower())
    if match:
        return match.group(1)
    found = {}
    for name in albedos:
        m = re.search(r"pc_([a-z]\d+)", name.lower())
        if m:
            found[m.group(1)] = found.get(m.group(1), 0) + 1
    return max(found, key=found.get) if found else ""


# --- game data ---------------------------------------------------------------------------------------
def linear(color):
    """Unity stores material colours in sRGB and hands the shader linear values (linear colour
    space); Blender's colour sockets take linear values directly."""
    def one(c):
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return tuple(one(max(0.0, float(c))) for c in color[:3])


def texture_path(cache, name, normal=False):
    return os.path.join(cache, "textures", name + ("__nrm.png" if normal else ".png"))


def needed_textures(mdef, override):
    out = []
    for key, slot in mdef["textures"].items():
        if key in ("_ShiftNoiseMap", "_SkinLutMap"):
            continue                        # not used by the Blender materials
        name = override.get(key, slot["texture"])
        out.append((name, key in NORMAL_SLOTS or name.endswith("_Normal")))
    return out


def load_data(cid, cache, materials=(), albedos=(), python=None, log=print, game=None):
    """<cache>/<cid>.json, (re)made by hq_material_data.py when a wanted material or texture is missing."""
    path = os.path.join(cache, "%s.json" % cid)

    def complete(data):
        mats = data["materials"]
        wanted = set(materials) | {n for n, d in mats.items() if _base_map(d).lower() in {a.lower() for a in albedos}}
        for n in wanted:
            if n not in mats:
                continue
            for name, normal in needed_textures(mats[n], data.get("overrides", {}).get(n, {})):
                if not os.path.isfile(texture_path(cache, name, normal)):
                    return False
            if role_of(mats[n]) is not None:         # XPS / PMX export textures (hq_material_data.py)
                maps = data.get("exports", {}).get(n)
                if not maps or not all(os.path.isfile(os.path.join(cache, p)) for p in maps.values()):
                    return False
        # an albedo that is no game _BaseMap (eye iris, a prop from another bundle) stays unmatched on
        # a re-run too, so it does not make the cache incomplete
        return True

    data = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    summary = None
    if data is None or not complete(data):
        cmd = [python or os.environ.get("ROE_PYTHON") or "python", DATA_SCRIPT, cid, "--out", cache,
               "--materials", ",".join(sorted(m for m in materials if m)),
               "--albedos", ",".join(sorted(a for a in albedos if a))]
        if game:
            cmd += ["--game", game]
        run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=900, creationflags=0x08000000 if sys.platform == "win32" else 0)
        line = next((l for l in run.stdout.splitlines() if l.startswith("ROE_HQ_DATA=")), "")
        if run.returncode or not line:
            raise RuntimeError("hq_material_data.py failed (%s): %s" % (run.returncode, (run.stderr or run.stdout)[-600:]))
        summary = json.loads(line[len("ROE_HQ_DATA="):])
        log("[hq] data: %s" % line)
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    return data, summary


# --- material builder ----------------------------------------------------------------------------------
class Nodes:
    """Adds hq_* nodes to a material (after clearing it for a new material)."""

    def __init__(self, material, clear=True, offset=(0, 0)):
        self.nt = material.node_tree
        if clear:
            self.nt.nodes.clear()
        self.dx, self.dy = offset

    def new(self, kind, x, y, name, **props):
        node = self.nt.nodes.new(kind)
        node.name = PREFIX + name
        node.location = (x + self.dx, y + self.dy)
        for key, value in props.items():
            setattr(node, key, value)
        return node

    def link(self, out_socket, in_socket):
        self.nt.links.new(out_socket, in_socket)


def remove_hq_nodes(material):
    if material is None or not material.use_nodes or material.node_tree is None:
        return 0
    nodes = material.node_tree.nodes
    doomed = [n for n in nodes if n.name.startswith(PREFIX)]
    for node in doomed:
        nodes.remove(node)
    return len(doomed)


class Builder:
    def __init__(self, data, cache, uv_name, params=None):
        self.data, self.cache, self.uv = data, cache, uv_name
        self.params = dict(DEFAULT_PARAMS, **(params or {}))
        self.built, self.images = {}, []

    def image(self, name, normal=False, non_color=False):
        path = texture_path(self.cache, name, normal)
        if not os.path.isfile(path):
            raise FileNotFoundError(path)
        img = bpy.data.images.load(path, check_existing=True)
        if normal or non_color:
            img.colorspace_settings.name = "Non-Color"
        self.images.append(img)
        return img

    def tex(self, n, name, x, y, vector, node_name, normal=False, non_color=False):
        node = n.new("ShaderNodeTexImage", x, y, node_name)
        node.image = self.image(name, normal, non_color)
        n.link(vector, node.inputs["Vector"])
        return node

    def material(self, game, old, target=None):
        """A new material for a game material (shared by its slots), or - with `target` - the same
        network added into `target` beside its own nodes, with its own output made the active one."""
        if target is None and game in self.built:
            return self.built[game]
        mdef = self.data["materials"][game]
        role = role_of(mdef)
        if role is None:
            return None
        tex, fl, col, kw = mdef["textures"], mdef["floats"], mdef["colors"], set(mdef["keywords"])
        override = self.data.get("overrides", {}).get(game, {})
        if target is None:
            mat = bpy.data.materials.new("HQ_" + game)
            mat.use_nodes = True
            n = Nodes(mat, clear=True)
        else:
            mat = target
            mat.use_nodes = True
            remove_hq_nodes(mat)            # a second run rebuilds
            n = Nodes(mat, clear=False, offset=(-2800, -1800))
        out = n.new("ShaderNodeOutputMaterial", 900, 0, "output")
        bsdf = n.new("ShaderNodeBsdfPrincipled", 550, 0, "bsdf")
        n.link(bsdf.outputs["BSDF"], out.inputs["Surface"])
        uv = n.new("ShaderNodeUVMap", -1300, 0, "uv", uv_map=self.uv)
        albedo = self.tex(n, override.get("_BaseMap", tex["_BaseMap"]["texture"]), -900, 350, uv.outputs["UV"],
                          "albedo")
        tint = n.new("ShaderNodeMixRGB", -550, 350, "tint", blend_type="MULTIPLY")
        tint.inputs["Fac"].default_value = 1.0
        n.link(albedo.outputs["Color"], tint.inputs["Color1"])
        base_color = col.get("_BaseColor", [1.0, 1.0, 1.0, 1.0])
        tint.inputs["Color2"].default_value = linear(base_color) + (1.0,)
        base = tint.outputs["Color"]

        # ambient occlusion: MGAC B (pbr / skin), strand occlusion R of the common hair MGA (hair)
        occ_slot = "_OcclusionMaskMap" if role == "hair" else "_MetallicGlossMap"
        sep = None
        if occ_slot in tex:
            mask = self.tex(n, tex[occ_slot]["texture"], -900, 0, uv.outputs["UV"], "mask", non_color=True)
            sep = n.new("ShaderNodeSeparateRGB", -650, 0, "sep")
            n.link(mask.outputs["Color"], sep.inputs["Image"])
            ao = n.new("ShaderNodeMath", -450, 150, "ao", operation="MULTIPLY_ADD")    # 1 - s + s * ao
            n.link(sep.outputs["R" if role == "hair" else "B"], ao.inputs[0])
            shade = n.new("ShaderNodeMixRGB", -250, 300, "shade", blend_type="MULTIPLY")
            shade.inputs["Fac"].default_value = 1.0
            n.link(base, shade.inputs["Color1"])
            n.link(ao.outputs["Value"], shade.inputs["Color2"])
            base = shade.outputs["Color"]
            if role != "hair":
                # the game occludes indirect specular too; without this a glossy surface in a crease
                # (the coat lining: smoothness 0.9, AO 0.55) mirrors the whole sky and turns grey
                spec = n.new("ShaderNodeMath", -250, 150, "spec", operation="MULTIPLY_ADD")
                n.link(ao.outputs["Value"], spec.inputs[0])
                n.link(spec.outputs["Value"], bsdf.inputs["Specular"])
        n.link(base, bsdf.inputs["Base Color"])

        if role == "hair":
            bsdf.inputs["Roughness"].default_value = self.params["hair_rough"]
        elif sep is not None:
            metal = n.new("ShaderNodeMath", -250, 0, "metal", operation="MULTIPLY", use_clamp=True)
            n.link(sep.outputs["R"], metal.inputs[0])
            n.link(metal.outputs["Value"], bsdf.inputs["Metallic"])
            rough = n.new("ShaderNodeMath", -250, -150, "rough", operation="MULTIPLY_ADD", use_clamp=True)
            n.link(sep.outputs["G"], rough.inputs[0])                                    # 1 - g * smoothness
            rough.inputs[2].default_value = 1.0
            n.link(rough.outputs["Value"], bsdf.inputs["Roughness"])
        else:                               # no MGAC map: the flat values
            bsdf.inputs["Metallic"].default_value = 0.0
            bsdf.inputs["Roughness"].default_value = min(1.0, max(0.3, 1.0 - fl.get("_Smoothness", 0.5)))

        # transparency: the game flags; a new material also inherits a transparent slot's blend settings
        old_bsdf = _principled(old) if target is None else None
        old_alpha = bool(old_bsdf and old_bsdf.inputs["Alpha"].is_linked)
        cut = role == "hair" or fl.get("_EnableAlphaTest", 0.0) > 0.0 or "_ALPHATEST_ON" in kw
        see_through = fl.get("_Surface", 0.0) > 0.0 and role != "hair"
        if cut or see_through or old_alpha:
            if cut:
                alpha = n.new("ShaderNodeMath", -250, -450, "alpha", operation="GREATER_THAN")
                n.link(albedo.outputs["Alpha"], alpha.inputs[0])
                alpha.inputs[1].default_value = fl.get("_Cutoff", 0.5)
            else:
                alpha = n.new("ShaderNodeMath", -250, -450, "alpha", operation="MULTIPLY")
                n.link(albedo.outputs["Alpha"], alpha.inputs[0])
                alpha.inputs[1].default_value = base_color[3]
            n.link(alpha.outputs["Value"], bsdf.inputs["Alpha"])
            if target is None:
                if old_alpha:
                    mat.blend_method, mat.shadow_method = old.blend_method, old.shadow_method
                    mat.alpha_threshold = old.alpha_threshold
                    mat.show_transparent_back = old.show_transparent_back
                else:
                    mat.blend_method = mat.shadow_method = "CLIP" if cut else "HASHED"
                    mat.alpha_threshold = 0.5
        elif target is None:
            mat.blend_method, mat.shadow_method = "OPAQUE", "OPAQUE"
        if target is None:
            mat.use_backface_culling = False    # (in place: the imported material's own settings stay)

        emission = col.get("_EmissionColor", [0.0, 0.0, 0.0, 1.0])
        if fl.get("_EnableEmission", 0.0) > 0.0 and max(emission[:3]) > 1e-4:
            if "_EmissionMap" in tex:
                em_tex = self.tex(n, tex["_EmissionMap"]["texture"], -900, -1000, uv.outputs["UV"], "emission_tex")
                em = n.new("ShaderNodeMixRGB", -550, -1000, "emission", blend_type="MULTIPLY")
                em.inputs["Fac"].default_value = 1.0
                n.link(em_tex.outputs["Color"], em.inputs["Color1"])
                em.inputs["Color2"].default_value = linear(emission) + (1.0,)
                n.link(em.outputs["Color"], bsdf.inputs["Emission"])
            else:
                bsdf.inputs["Emission"].default_value = linear(emission) + (1.0,)
            bsdf.inputs["Emission Strength"].default_value = 1.0

        if role == "skin":
            bsdf.inputs["Subsurface Radius"].default_value = SUBSURFACE_RADIUS
            n.link(base, bsdf.inputs["Subsurface Color"])
            mat.use_sss_translucency = True

        # normal map (+ detail normal, blended in tangent space: UDN)
        detail_scale = 0.0
        if "_BumpMap" in tex and fl.get("_BumpScale", 1.0) > 0.0:
            main = self.tex(n, tex["_BumpMap"]["texture"], -900, -400, uv.outputs["UV"], "normal_tex", normal=True)
            packed = main.outputs["Color"]
            detail = tex.get("_DetailNormalMap")
            if detail and fl.get("_DetailBumpScale", 0.0) > 0.0 and role == "skin":
                detail_scale = fl["_DetailBumpScale"]
                mapping = n.new("ShaderNodeMapping", -1100, -700, "detail_map")
                mapping.inputs["Scale"].default_value = (detail["scale"][0], detail["scale"][1], 1.0)
                n.link(uv.outputs["UV"], mapping.inputs["Vector"])
                det = self.tex(n, detail["texture"], -900, -700, mapping.outputs["Vector"], "detail_tex", normal=True)
                v1 = n.new("ShaderNodeVectorMath", -650, -400, "v1", operation="MULTIPLY_ADD")
                n.link(main.outputs["Color"], v1.inputs[0])
                v1.inputs[1].default_value = (2.0, 2.0, 2.0)
                v1.inputs[2].default_value = (-1.0, -1.0, -1.0)
                v2 = n.new("ShaderNodeVectorMath", -650, -700, "v2", operation="MULTIPLY_ADD")
                n.link(det.outputs["Color"], v2.inputs[0])
                add = n.new("ShaderNodeVectorMath", -450, -550, "add", operation="ADD")
                n.link(v1.outputs["Vector"], add.inputs[0])
                n.link(v2.outputs["Vector"], add.inputs[1])
                norm = n.new("ShaderNodeVectorMath", -300, -550, "norm", operation="NORMALIZE")
                n.link(add.outputs["Vector"], norm.inputs[0])
                pack = n.new("ShaderNodeVectorMath", -150, -550, "pack", operation="MULTIPLY_ADD")
                n.link(norm.outputs["Vector"], pack.inputs[0])
                pack.inputs[1].default_value = (0.5, 0.5, 0.5)
                pack.inputs[2].default_value = (0.5, 0.5, 0.5)
                packed = pack.outputs["Vector"]
            nmap = n.new("ShaderNodeNormalMap", 150, -400, "normal", space="TANGENT", uv_map=self.uv)
            n.link(packed, nmap.inputs["Color"])
            n.link(nmap.outputs["Normal"], bsdf.inputs["Normal"])

        mat["roe_game_material"] = game
        mat["roe_hq_role"] = role
        mat["roe_hq_base"] = json.dumps({"bump": fl.get("_BumpScale", 1.0), "detail": detail_scale,
                                         "occ": fl.get("_OcclusionStrength", 1.0),
                                         "smooth": fl.get("_Smoothness", 1.0), "metal": fl.get("_Metallic", 1.0),
                                         "role": role})
        apply_params(mat, self.params)
        if target is not None:
            set_active_output(mat, out)
        else:
            self.built[game] = mat
        return mat


# --- live tuning / looks -------------------------------------------------------------------------------
def hq_materials_of(meshes):
    seen, out = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.get("roe_hq_base") and mat.name not in seen:
                seen.add(mat.name)
                out.append(mat)
    return out


def apply_params(materials, params=None):
    """Retune the hq_* nodes: every value is the game's own value x the multiplier (DEFAULT_PARAMS)."""
    p = dict(DEFAULT_PARAMS, **(params or {}))
    for mat in (materials if isinstance(materials, (list, tuple, set)) else [materials]):
        base = json.loads(mat.get("roe_hq_base", "{}") or "{}")
        if not base or not mat.use_nodes:
            continue
        nodes = mat.node_tree.nodes
        node = nodes.get(PREFIX + "normal")
        if node is not None:
            node.inputs["Strength"].default_value = base["bump"] * p["normal"]
        node = nodes.get(PREFIX + "v2")
        if node is not None:
            d = base["detail"] * p["detail"]
            node.inputs[1].default_value = (2.0 * d, 2.0 * d, 0.0)
            node.inputs[2].default_value = (-d, -d, 0.0)
        node = nodes.get(PREFIX + "ao")
        if node is not None:
            s = min(1.0, max(0.0, base["occ"] * p["ao"]))
            node.inputs[1].default_value = s
            node.inputs[2].default_value = 1.0 - s
        node = nodes.get(PREFIX + "spec")
        if node is not None:                     # MULTIPLY_ADD: ao * a + b
            node.inputs[1].default_value = 0.5 if p["spec_occlusion"] else 0.0
            node.inputs[2].default_value = 0.0 if p["spec_occlusion"] else 0.5
        node = nodes.get(PREFIX + "metal")
        if node is not None:
            node.inputs[1].default_value = base["metal"] * p["metal"]
        node = nodes.get(PREFIX + "rough")
        if node is not None:
            node.inputs[1].default_value = -base["smooth"] * p["smooth"]
        bsdf = nodes.get(PREFIX + "bsdf")
        if bsdf is not None:
            if base.get("role") == "skin":
                bsdf.inputs["Subsurface"].default_value = p["sss"]
            elif base.get("role") == "hair":
                bsdf.inputs["Roughness"].default_value = p["hair_rough"]


def set_active_output(material, output):
    # by name: Blender hands out a new Python wrapper per access, so `is` never matches
    for node in material.node_tree.nodes:
        if node.type == "OUTPUT_MATERIAL":
            node.is_active_output = node.name == output.name


def set_mode(materials, mode):
    """'game': the hq_* network renders; 'mmd': the material's own output (mmd_tools' MMD shader) does.
    Both stay linked, so mmd_tools never re-links anything behind our back."""
    switched = 0
    for mat in materials:
        if mat is None or not mat.use_nodes:
            continue
        nodes = mat.node_tree.nodes
        hq_out = nodes.get(PREFIX + "output")
        own = next((n for n in nodes if n.type == "OUTPUT_MATERIAL" and not n.name.startswith(PREFIX)), None)
        target = hq_out if mode == "game" else own
        if hq_out is None or target is None:
            continue
        set_active_output(mat, target)
        switched += 1
    return switched


def remove_hq(materials):
    """Take the hq_* network out of in-place materials (their own output becomes active again)."""
    removed = 0
    for mat in materials:
        if mat is None or not mat.use_nodes:
            continue
        own = next((n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL"
                    and not n.name.startswith(PREFIX)), None)
        if own is None:
            continue                            # a whole HQ material (batch): nothing to fall back to
        if remove_hq_nodes(mat):
            set_active_output(mat, own)
            for key in ("roe_game_material", "roe_hq_role", "roe_hq_base"):
                if key in mat:
                    del mat[key]
            removed += 1
    return removed


# --- entry points --------------------------------------------------------------------------------------
def apply(meshes, stem="", export_root=None, cache=None, python=None, log=print, in_place=False, params=None,
          cid=None, game=None):
    """Build the game materials on the slots of `meshes`.  Returns (state, report); state is what
    revert() needs to put the replaced materials back (empty for in_place)."""
    slots = []                              # (obj, index, old material, colour texture, stored name)
    for obj in meshes:
        sources = slot_sources(obj)
        for index, slot in enumerate(obj.material_slots):
            slots.append((obj, index, slot.material, slot_albedo(slot.material), sources.get(index, "")))
    albedos = sorted({s[3] for s in slots if s[3]})
    cid = cid or infer_cid(stem, albedos)
    if not cid:
        raise RuntimeError("cannot tell the character id (pc_<letter><digits>) from %r or the textures" % stem)
    cache = cache or os.environ.get("ROE_HQ_CACHE") or os.path.join(export_root or DEFAULT_EXPORT_ROOT,
                                                                     "_hq_materials")
    names = sorted({s[4] for s in slots if s[4]})
    plain = [a for a in albedos if not a.lower().endswith(EXPORT_SUFFIXES)]
    data, summary = load_data(cid, cache, names, plain, python, log, game)
    picks = [pick_material(data["materials"], albedo, source, old.name if old else "")
             for _obj, _index, old, albedo, source in slots]
    wanted = sorted({g for g in picks if g})
    if wanted:                              # PMX / XPS names resolve only once the definitions are read
        data, more = load_data(cid, cache, wanted, (), python, log, game)
        summary = more or summary
    uv_names = {o.data.uv_layers[0].name for o in meshes if o.data.uv_layers}
    builder = Builder(data, cache, sorted(uv_names)[0] if uv_names else "UVMap", params)
    state, upgraded, kept, errors, done = [], [], [], [], set()
    for (obj, index, old, albedo, source), game_mat in zip(slots, picks):
        label = "%s[%d]" % (obj.name, index)
        if game_mat is None or (in_place and (old is None or old.name.startswith("mmd_"))):
            kept.append(label)
            continue
        if in_place and old.name in done:
            upgraded.append("%s %s (shared)" % (label, game_mat))
            continue
        if len(obj.data.uv_layers) and obj.data.uv_layers[0].name != builder.uv:
            errors.append("%s: UV map %s != %s" % (label, obj.data.uv_layers[0].name, builder.uv))
            continue
        try:
            new = builder.material(game_mat, old, target=old if in_place else None)
        except Exception as exc:
            errors.append("%s %s: %s" % (label, game_mat, exc))
            continue
        if new is None:
            kept.append("%s (%s)" % (label, game_mat))
            continue
        if in_place:
            done.add(old.name)
        else:
            obj.material_slots[index].material = new
            state.append((obj, index, old))
        upgraded.append("%s %s (%s)" % (label, game_mat, new["roe_hq_role"]))
        # what XPS / PMX use instead of the node tree (the add-on's XPS export reads roe_hq_xps,
        # use_pmx_textures() reads roe_hq_pmx); on both materials so either can be exported
        maps = data.get("exports", {}).get(game_mat)
        if maps and not in_place:
            xps = {k: os.path.join(cache, v) for k, v in maps.items() if k != "pmx"}
            for mat in (old, new):
                if mat is not None:
                    mat["roe_hq_xps"] = json.dumps(xps)
                    mat["roe_hq_pmx"] = os.path.join(cache, maps["pmx"])
    report = {"cache": cache, "character": cid, "upgraded": upgraded, "kept": kept, "errors": errors,
              "overrides": data.get("overrides", {}), "images": len(set(builder.images))}
    if summary:
        report["decoded"] = summary.get("decoded")
        report["missing"] = summary.get("missing")
    return state, report


def revert(state):
    """Put the add-on's albedo materials back (XPS / GLB / PMX are built from those)."""
    for obj, index, old in state:
        obj.material_slots[index].material = old


def _base_color_image_node(material):
    """The image node that feeds Base Color (first one upstream), or None."""
    bsdf = _principled(material)
    if bsdf is None:
        return None
    stack, seen = [bsdf.inputs["Base Color"]], set()
    while stack:
        socket = stack.pop(0)
        for link in socket.links:
            node = link.from_node
            if node in seen:
                continue
            seen.add(node)
            if node.type == "TEX_IMAGE" and node.image:
                return node
            stack.extend(node.inputs)
    return None


def use_pmx_textures(state):
    """PMX (mmd_tools) only takes one colour texture per material: swap each reverted material's
    albedo for albedo x _BaseColor x AO (hq_material_data.py export/<name>__pmx_diffuse.png).  Call
    after revert(), right before the PMX export (the last export: it rewrites the scene anyway)."""
    swapped = []
    for obj, index, old in state:
        path = old.get("roe_hq_pmx") if old is not None else None
        node = _base_color_image_node(old) if path and os.path.isfile(path) else None
        if node is None:
            continue
        node.image = bpy.data.images.load(path, check_existing=True)
        swapped.append("%s[%d] %s" % (obj.name, index, os.path.basename(path)))
    return swapped


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if not argv:
        raise SystemExit("usage: -- <out.blend> [--cache DIR]")
    out_path = os.path.abspath(argv[0])
    cache = argv[argv.index("--cache") + 1] if "--cache" in argv else None
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    _state, report = apply(meshes, stem, cache=cache)
    for img in {n.image for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes
                if n.type == "TEX_IMAGE" and n.image}:
        if not img.packed_file and os.path.isfile(bpy.path.abspath(img.filepath)):
            img.pack()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 next to the product
    bpy.ops.wm.save_as_mainfile(filepath=out_path, check_existing=False, compress=False)
    report["out"] = out_path
    print("ROE_HQ_BLEND=" + json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
