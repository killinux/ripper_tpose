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
  alpha test / transparency / emission follow the game flags.
  glass / flat  no colour texture (lenses, glass, glowing parts): _BaseColor, the material's own metallic /
        smoothness, its normal map if any; premultiplied see-through (URP _ALPHAPREMULTIPLY_ON: the diffuse x alpha,
        the reflections whole) is drawn by keep_reflections() - glass at alpha 0 shows only its reflections (h06's
        clear holographic raincoat, c05's lenses)
  brows / lashes  the add-on's "lash" / "brow" slots keep their material, its texture becomes the game's
        eyebrow blend (colour x alpha^2 over the face, no darkening): <game>__stroke.png
  iris  the add-on's "eye" slot keeps its procedural eye, its iris texture gets the game's _IrisColor
        tint: <game>__iris.png.  Both written to <cache>\\export and used by the PMX / XPS too
  tears keep what they have.

Slot -> game material, by the slot's colour texture: a game material's _BaseMap (FBX import), or the
export textures hq_material_data.py wrote (<material>__pmx_diffuse / __xps_diffuse: a PMX or XPS
import).  The name the ROE add-on stored from the FBX (``roe_source_materials`` + per-face
``roe_source_material_index``) breaks ties (body and skin share one albedo); in a suit's file
(pc_g01_yoga) the suit's own <material>@<suit> comes first, and a material uses its own copy of a
texture whose name other data shares (hq_material_data "overrides", on every slot).  The stored name wins
when the texture match went wrong (source_material: the add-on placed a texture by name - b04's yarn, e05's tails,
j07's / b14's hair with the outfit's hair texture - or the piece is glass), except on the add-on's head slots.

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

Standalone, for a .blend that was exported earlier (the out path may be the in path):
  blender -b --factory-startup <in.blend> --python hq_materials_blender.py -- <out.blend> [--cache DIR] [--preview] [--rebuild]
--preview re-renders <out>_preview.png with the batch's own preview sheet (export_character_model_blender
.render_preview) - the suits (export_suits.py) and the nude bases are upgraded this way.  A second run
upgrades only what is still albedo-only; --rebuild builds the earlier run's materials again (after a
data fix).
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
    source = bpy.data.images.get(material.get("roe_hq_source_image") or "")
    if source is not None:                      # a lash / brow / eye an earlier run converted
        return image_stem(source)
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


def pick_material(materials, albedo, source, old_name, suit=None):
    if not albedo:
        return None
    for suffix in EXPORT_SUFFIXES:                 # a PMX / XPS export texture names its material
        if albedo.lower().endswith(suffix):
            base = albedo[:-len(suffix)]
            return next((n for n in materials if safe_name(n) == base), None)
    albedo = re.sub(r"__[0-9a-f]{8}(?=_rgbx_)", "", albedo)      # a material's own copy of a shared name
    cands = [n for n, d in materials.items() if _base_map(d).lower() == albedo.lower()]
    # <name>@<suit>: the suit's own definition of a piece another suit names alike (hq_material_data)
    own = [n for n in cands if suit and n.lower().endswith("@" + suit)]
    cands = own or [n for n in cands if "@" not in n] or cands
    if source in cands:
        return source
    if len(cands) > 1 and old_name:
        # export_suits.py names a piece's material after the game one (+ "_mat", sometimes truncated):
        # lynn_UniformStockings_obj001_transparenc_mat is the _transparency variant, not the opaque one
        stem = re.sub(r"_mat$", "", re.sub(r"\.\d{3}$", "", old_name.lower()))
        named = [n for n in cands if n.lower() == stem or (len(stem) >= 8 and n.lower().startswith(stem))]
        if named:
            return min(named, key=len)
    if len(cands) > 1:
        skin = "skin" in (old_name or "").lower()
        cands = [n for n in cands if ("skin" in n.lower()) == skin] or cands
        cands.sort(key=lambda n: ("_ld" in n.lower(), n))
    return cands[0] if cands else None


HEAD_SLOTS = ("face", "eye", "lash", "brow", "eye_overlay")    # the ROE add-on's own head slots
FACE = re.compile(r"pc_[a-z]\d*(_fm)?_nk_face$")               # the family face (a nude base merges it into the body)


def source_material(materials, picked, source, slot_name=""):
    """The slot's own game material when the colour-texture match picked another one.  The ROE add-on gives a slot
    its texture by name, which can miss: every slot of a mesh named *hair* gets the hair texture (a08's braid ring is
    drawn with the outfit atlas pc_a08_hd_body2, h01's scalp piece with the face), a name it cannot place gets the
    mesh's first texture (b04's yarn: material pc_b04_hd_yam, texture pc_b04_hd_yarn_...; f08's feathers use f04's
    texture), e05's tails came out one slot off, j07's and b14's hair carry the outfit's hair texture.  The FBX names
    the game material (source), so it wins when it is a lit one (pbr / skin / hair) with another colour texture, or a
    texture-less one (flat_kind: lenses, glass, a glowing part) where a texture was picked; where nothing matched (no
    texture, or one no game material uses: e08's hair, j06's weapon) a lit one is built too.  The add-on's head slots
    and a face keep the match (their stored names are not reliable: e04's face says eyebrow, l01's merged face body)."""
    if not source or source == picked or source not in materials:
        return picked
    name = re.sub(r"\.\d{3}$", "", slot_name or "")
    if name in HEAD_SLOTS or "eye_overlay" in name or (picked and FACE.match(picked)):
        return picked
    own = materials[source]
    if not picked or picked not in materials:
        return source if role_of(own) is not None and _base_map(own) else picked
    pick = materials[picked]
    if role_of(own) is not None and _base_map(own):
        return source if _base_map(own).lower() != _base_map(pick).lower() else picked
    if flat_kind(own) and _base_map(pick):
        return source
    return picked


EYE_TEXTURES = ("_IrisAlbedoTex", "_ScleraAlbedoTex", "_EyeBumpMap")


def flat_kind(mdef):
    """A lit material with no colour texture - the shader samples Unity's white default, so _BaseColor is the colour:
    "glass" when see-through (lenses, glass), "flat" when opaque (glowing parts).  None for textured materials, hair
    (k06's hair albedo sits in k04's bundle: hq_material_data reads it through the game's manifest) and eyes."""
    tex, kw = mdef["textures"], set(mdef["keywords"])
    if "_BaseMap" in tex or "_BaseColor" not in mdef["colors"]:
        return None
    if "_ShiftNoiseMap" in tex or "HAIR_AM" in kw or any(k in tex for k in EYE_TEXTURES):
        return None
    return "glass" if mdef["floats"].get("_Surface", 0.0) > 0.0 else "flat"


def premultiplied(mdef):
    """See-through with premultiplied alpha (URP Lit _ALPHAPREMULTIPLY_ON): the diffuse is scaled by alpha, the
    reflections stay whole - glass with _BaseColor alpha 0 shows only its reflections."""
    fl, kw = mdef["floats"], set(mdef["keywords"])
    return fl.get("_Surface", 0.0) > 0.0 and (fl.get("_EnablePremultiplyAlpha", 0.0) > 0.0 or "_ALPHAPREMULTIPLY_ON" in kw)


def see_through(mdef):
    """The game draws the material see-through: transparent surface, not hair (alpha-cut instead)."""
    return mdef["floats"].get("_Surface", 0.0) > 0.0 and role_of(mdef) != "hair"


def xps_alpha(mdef):
    """The XPS draws the slot with alpha (render group 7 -> 25; the add-on keeps a ROE model's other slots opaque, its
    atlases carry junk alpha): texture-less glass and see-through pieces whose _BaseColor alpha is below 1 (a clear
    coat, a glass slipper, a veil) - their export textures carry the alpha the game shows (hq_material_data)."""
    base = mdef["colors"].get("_BaseColor", [1.0, 1.0, 1.0, 1.0])
    return see_through(mdef) and (flat_kind(mdef) == "glass" or (len(base) > 3 and base[3] < 1.0))


def role_of(mdef):
    tex, kw = mdef["textures"], set(mdef["keywords"])
    if "_ShiftNoiseMap" in tex or "HAIR_AM" in kw:
        return "hair"
    if "_IrisAlbedoTex" in tex or "_BaseMap" not in tex:
        return None                        # eyes (procedural shader), tears, empties: keep
    # the lit shader with only a colour texture (b04's yarn, a01's glass slipper: DIRECT_SPECULAR) is pbr too
    if "_BumpMap" in tex or "_MetallicGlossMap" in tex or "DIRECT_SPECULAR" in kw:
        skin = "_SkinLutMap" in tex or mdef["floats"].get("_EanbleTranslucency", 0.0) > 0.0  # sic
        return "skin" if skin else "pbr"
    return None                            # albedo-only (brows / lashes): keep


def infer_cid(stem, albedos=()):
    """Character id (a01, g05 ...) from a model / file name, else from the texture names."""
    match = re.search(r"pc[_ ]([a-z]\d+|[a-z]_[a-z]+\d+)", (stem or "").lower())
    if match:
        return match.group(1)
    found = {}
    for name in albedos:
        m = re.search(r"pc_([a-z]\d+|[a-z]_[a-z]+\d+)", name.lower())
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
            if role_of(mats[n]) is not None or flat_kind(mats[n]):   # XPS / PMX export textures (hq_material_data.py)
                maps = data.get("exports", {}).get(n)
                if not maps or not all(os.path.isfile(os.path.join(cache, p)) for p in maps.values()):
                    return False
                if n not in data.get("export_signatures", {}):     # made before the signatures: check once
                    return False
                if "bump" not in maps:                  # (10-04) every material has one now, flat if need be
                    return False
        # an albedo that is no game _BaseMap (eye iris, a prop from another bundle) stays unmatched on
        # a re-run too, so it does not make the cache incomplete - except a shared piece
        # (Common_<piece>_rgbx_Albedo) no run has looked up yet: its bundle is only read when asked for
        looked = set(data.get("pieces", ()))
        for a in albedos:
            m = re.match(r"common_(.+?)_rgbx_albedo$", a.lower())
            if m and m.group(1) not in looked:
                return False
        return True

    data = None
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    summary = None
    # schema 2 (2026-10-01) added the suits' component bundles, 3 the shared accessory pieces (found by
    # albedo name), 4 the same-name textures told apart + <material>@<suit>, 5 (10-04) the manifest's texture
    # bundles (another character's textures) + glass / glowing parts' export maps: an older cache lacks those
    if data is None or data.get("schema", 1) < 5 or not complete(data):
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
        if target is None and (game, self.uv) in self.built:
            return self.built[(game, self.uv)]
        mdef = self.data["materials"][game]
        role = role_of(mdef) or flat_kind(mdef)
        if role is None:
            return None
        flat = role in ("glass", "flat")        # no colour texture: _BaseColor is the colour
        tex, fl, col, kw = mdef["textures"], mdef["floats"], mdef["colors"], set(mdef["keywords"])
        override = self.data.get("overrides", {}).get(game, {})

        def tname(slot):                    # the material's own copy when the name is shared (hq_material_data)
            return override.get(slot, tex[slot]["texture"])

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
        base_color = col.get("_BaseColor", [1.0, 1.0, 1.0, 1.0])
        if flat:
            albedo = None
            colour = n.new("ShaderNodeRGB", -550, 350, "tint")
            colour.outputs["Color"].default_value = linear(base_color) + (1.0,)
            base = colour.outputs["Color"]
        else:
            albedo = self.tex(n, tname("_BaseMap"), -900, 350, uv.outputs["UV"], "albedo")
            tint = n.new("ShaderNodeMixRGB", -550, 350, "tint", blend_type="MULTIPLY")
            tint.inputs["Fac"].default_value = 1.0
            n.link(albedo.outputs["Color"], tint.inputs["Color1"])
            tint.inputs["Color2"].default_value = linear(base_color) + (1.0,)
            base = tint.outputs["Color"]

        # ambient occlusion: MGAC B (pbr / skin), strand occlusion R of the common hair MGA (hair)
        occ_slot = "_OcclusionMaskMap" if role == "hair" else "_MetallicGlossMap"
        sep = None
        if occ_slot in tex:
            mask = self.tex(n, tname(occ_slot), -900, 0, uv.outputs["UV"], "mask", non_color=True)
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
        elif flat or premultiplied(mdef):   # glass, a glowing part: the material's own values
            bsdf.inputs["Metallic"].default_value = min(1.0, max(0.0, fl.get("_Metallic", 0.0)))
            bsdf.inputs["Roughness"].default_value = min(1.0, max(0.05, 1.0 - fl.get("_Smoothness", 0.5)))
        else:                               # no MGAC map: the flat values
            bsdf.inputs["Metallic"].default_value = 0.0
            bsdf.inputs["Roughness"].default_value = min(1.0, max(0.3, 1.0 - fl.get("_Smoothness", 0.5)))

        # transparency: the game flags; a new material also inherits a transparent slot's blend settings
        old_bsdf = _principled(old) if target is None else None
        old_alpha = bool(old_bsdf and old_bsdf.inputs["Alpha"].is_linked)
        cut = role == "hair" or (not flat and (fl.get("_EnableAlphaTest", 0.0) > 0.0 or "_ALPHATEST_ON" in kw))
        clear = see_through(mdef)
        premult = clear and premultiplied(mdef)
        alpha = None
        if cut or clear or (old_alpha and not flat):
            if cut:
                alpha = n.new("ShaderNodeMath", -250, -450, "alpha", operation="GREATER_THAN")
                n.link(albedo.outputs["Alpha"], alpha.inputs[0])
                alpha.inputs[1].default_value = fl.get("_Cutoff", 0.5)
            elif flat:
                alpha = n.new("ShaderNodeValue", -250, -450, "alpha")
                alpha.outputs["Value"].default_value = base_color[3] if clear else 1.0
            else:
                alpha = n.new("ShaderNodeMath", -250, -450, "alpha", operation="MULTIPLY")
                n.link(albedo.outputs["Alpha"], alpha.inputs[0])
                alpha.inputs[1].default_value = base_color[3]
            if not premult:                 # premultiplied: keep_reflections() below mixes by it
                n.link(alpha.outputs["Value"], bsdf.inputs["Alpha"])
            if target is None:
                if premult or (flat and clear):
                    # glass: sorted blending, no shadow (the game's transparent pass writes no depth)
                    mat.blend_method, mat.shadow_method = "BLEND", "NONE"
                    mat.show_transparent_back = False
                elif old_alpha and not flat:
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
                em_tex = self.tex(n, tname("_EmissionMap"), -900, -1000, uv.outputs["UV"], "emission_tex")
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
            main = self.tex(n, tname("_BumpMap"), -900, -400, uv.outputs["UV"], "normal_tex", normal=True)
            packed = main.outputs["Color"]
            detail = tex.get("_DetailNormalMap")
            if detail and fl.get("_DetailBumpScale", 0.0) > 0.0 and role == "skin":
                detail_scale = fl["_DetailBumpScale"]
                mapping = n.new("ShaderNodeMapping", -1100, -700, "detail_map")
                mapping.inputs["Scale"].default_value = (detail["scale"][0], detail["scale"][1], 1.0)
                n.link(uv.outputs["UV"], mapping.inputs["Vector"])
                det = self.tex(n, tname("_DetailNormalMap"), -900, -700, mapping.outputs["Vector"], "detail_tex", normal=True)
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

        if premult:
            keep_reflections(n, bsdf, out, alpha.outputs["Value"], base)
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
            self.built[(game, self.uv)] = mat
        return mat


def keep_reflections(n, bsdf, out, alpha, base):
    """Premultiplied alpha (URP Lit _ALPHAPREMULTIPLY_ON, blend One / OneMinusSrcAlpha): the diffuse fades with alpha,
    the reflections and the glow stay whole - glass at alpha 0 is only its reflections.  Surface = mix(alpha;
    transparent + reflections + glow, the full BSDF): the reflections are a metal BSDF on the material's F0 (0.04 grey
    for a dielectric, the colour for a metal: mixed by metallic) with the same roughness and normal."""
    def same(src, dst):
        if src.is_linked:
            n.link(src.links[0].from_socket, dst)
        elif hasattr(dst, "default_value"):
            dst.default_value = src.default_value

    refl = n.new("ShaderNodeBsdfPrincipled", 550, -900, "reflect")
    f0 = n.new("ShaderNodeMixRGB", 300, -900, "f0", blend_type="MIX")
    f0.inputs["Color1"].default_value = (0.04, 0.04, 0.04, 1.0)
    n.link(base, f0.inputs["Color2"])
    same(bsdf.inputs["Metallic"], f0.inputs["Fac"])
    n.link(f0.outputs["Color"], refl.inputs["Base Color"])
    refl.inputs["Metallic"].default_value = 1.0
    same(bsdf.inputs["Roughness"], refl.inputs["Roughness"])
    if bsdf.inputs["Normal"].is_linked:
        same(bsdf.inputs["Normal"], refl.inputs["Normal"])
    clear = n.new("ShaderNodeBsdfTransparent", 550, -650, "clear")
    add = n.new("ShaderNodeAddShader", 750, -700, "add_reflect")
    n.link(clear.outputs["BSDF"], add.inputs[0])
    n.link(refl.outputs["BSDF"], add.inputs[1])
    glow = bsdf.inputs["Emission"]
    if glow.is_linked or max(glow.default_value[:3]) > 0.0:
        emit = n.new("ShaderNodeEmission", 550, -1250, "glow")
        same(glow, emit.inputs["Color"])
        emit.inputs["Strength"].default_value = bsdf.inputs["Emission Strength"].default_value
        add2 = n.new("ShaderNodeAddShader", 750, -1000, "add_glow")
        n.link(add.outputs["Shader"], add2.inputs[0])
        n.link(emit.outputs["Emission"], add2.inputs[1])
        add = add2
    mix = n.new("ShaderNodeMixShader", 750, -150, "premult")
    n.link(alpha, mix.inputs["Fac"])
    n.link(add.outputs["Shader"], mix.inputs[1])
    n.link(bsdf.outputs["BSDF"], mix.inputs[2])
    n.link(mix.outputs["Shader"], out.inputs["Surface"])


# --- brows / lashes and the iris -----------------------------------------------------------------------
# The ROE add-on's head slots "lash" / "brow" draw the family's eyebrow atlas (the lashes darkened to 0.55 and
# their alpha x 1.5), "eye" the raw iris texture.  The game's own shaders (as the fighter project's RoeEyebrow /
# RoeEye.shader read them from the compiled code) do otherwise:
#   Pinkcore/Heros/Eyebrow  Lambert on albedo x _BaseColor x 0.96, no highlight; _ALPHAPREMULTIPLY_ON multiplies
#                           the colour by alpha and SrcBlend SrcAlpha by alpha again, DstBlend OneMinusSrcAlpha:
#                           colour x alpha^2 over the face x (1 - alpha) (c: SrcBlend One, colour x alpha)
#   Pinkcore/Heros/Eye      iris x _IrisColor (lerp by its alpha), 31 of the 55 eye materials tint it - m's
#                           pale blue iris is drawn dark purple, c's red, j's pink
# Both go into a texture (<cache>\export\<game>__stroke.png / __iris.png) the slot's image node then shows:
# straight alpha blending of colour x alpha (or the tinted iris) gives the game's result in the .blend, and
# the PMX / XPS, which copy that image (and bake the eye from it), draw the same.
STROKE_SLOTS = ("lash", "brow")
EYE_SLOTS = ("eye",)
DIELECTRIC_DIFFUSE = 0.96        # URP: the diffuse share of a non-metal (kDielectricSpec.a)


def _to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1.0 / 2.4) - 0.055)


def _image_node(material):
    """The one texture node of an add-on lash / brow / eye material."""
    if material is None or not material.use_nodes or material.node_tree is None:
        return None
    return next((n for n in material.node_tree.nodes if n.type == "TEX_IMAGE" and n.image), None)


def _source_image(material, node):
    """The texture the add-on gave the slot - on a second run too (kept with a fake user, the node then
    shows the converted one)."""
    image = bpy.data.images.get(material.get("roe_hq_source_image") or "")
    if image is None:
        image = node.image
        image.use_fake_user = True
        material["roe_hq_source_image"] = image.name
    return image


def _pixels(image):
    """RGBA as stored (an 8-bit sRGB image: the file's values / 255, no colour conversion)."""
    w, h = image.size
    px = np.empty(w * h * 4, dtype=np.float32)
    image.pixels.foreach_get(px)
    return px.reshape(h, w, 4), (w, h)


def _write_image(path, rgba, size):
    """Save RGBA as an 8-bit PNG (written aside, then moved: another lane may convert the same family
    texture at the same time) and return it loaded."""
    tmp = bpy.data.images.new("hq_tmp", size[0], size[1], alpha=True)
    tmp.pixels.foreach_set(np.ascontiguousarray(rgba, dtype=np.float32).ravel())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    part = "%s.%d.png" % (path[:-4], os.getpid())
    tmp.filepath_raw = part
    tmp.file_format = "PNG"
    tmp.save()
    bpy.data.images.remove(tmp)
    os.replace(part, path)
    image = bpy.data.images.load(path, check_existing=True)
    if image.packed_file:                # an earlier run's copy, packed into this .blend
        image.unpack(method="REMOVE")
    image.reload()
    return image


def stroke_texture(px, mdef):
    """The eyebrow atlas (file values) -> what straight alpha blending needs to draw the game's result."""
    rgb = _to_linear(px[..., :3]) * np.array(linear(mdef.get("colors", {}).get("_BaseColor", (1, 1, 1))),
                                              np.float32) * DIELECTRIC_DIFFUSE
    alpha = px[..., 3:4]
    floats, keywords = mdef.get("floats", {}), set(mdef.get("keywords", ()))
    premultiply = floats.get("_EnablePremultiplyAlpha", 0.0) > 0.5 or "_ALPHAPREMULTIPLY_ON" in keywords
    if premultiply and int(round(floats.get("_SrcBlend", 5.0))) == 5:      # SrcAlpha: x alpha twice
        rgb = rgb * alpha
    return np.concatenate([_to_srgb(rgb), alpha], axis=-1)


def iris_texture(px, mdef):
    tint = mdef.get("colors", {}).get("_IrisColor", (1, 1, 1, 1))
    amount = float(tint[3]) if len(tint) > 3 else 1.0
    lin = _to_linear(px[..., :3])
    lin = lin * (1.0 - amount) + lin * np.array(linear(tint), np.float32) * amount
    return np.concatenate([_to_srgb(lin), px[..., 3:4]], axis=-1)


def pick_eye(materials, iris, source, suit=None, cid=None):
    """The game eye material of an "eye" slot: the slot's FBX source when it is one, else the one whose
    _IrisAlbedoTex is the slot's iris (the suit's own, then the character's, then the family's)."""
    def eye(name):
        return "_IrisColor" in materials[name].get("colors", {})
    if source in materials and eye(source):
        return source
    cands = [n for n, d in materials.items() if eye(n) and iris
             and d["textures"].get("_IrisAlbedoTex", {}).get("texture", "").lower() == iris.lower()]
    own = [n for n in cands if suit and n.lower().endswith("@" + suit)]
    cands = own or [n for n in cands if "@" not in n] or cands
    cands = [n for n in cands if cid and ("pc_%s_" % cid) in n.lower()] or cands
    cands.sort(key=lambda n: ("_ld_" in n.lower(), len(n), n))
    return cands[0] if cands else None


def game_stroke(material, game, mdef, cache):
    """Lash / brow slot -> the game's eyebrow blend (see above).  Returns the texture written."""
    node, bsdf = _image_node(material), _principled(material)
    if node is None or bsdf is None:
        return None
    px, size = _pixels(_source_image(material, node))
    name = safe_name(game) + "__stroke.png"
    node.image = _write_image(os.path.join(cache, "export", name), stroke_texture(px, mdef), size)
    nt = material.node_tree
    for socket, output in (("Base Color", "Color"), ("Alpha", "Alpha")):
        for link in list(bsdf.inputs[socket].links):
            if link.from_node.type in ("HUE_SAT", "MATH"):          # the add-on's darkening / alpha gain
                nt.nodes.remove(link.from_node)
        nt.links.new(node.outputs[output], bsdf.inputs[socket])
    bsdf.inputs["Specular"].default_value = 0.0                     # the game's eyebrow shader: Lambert only
    bsdf.inputs["Roughness"].default_value = 1.0
    material.blend_method = "BLEND"
    material.shadow_method = "NONE"
    material["roe_hq_stroke"] = game
    return name


def game_iris(material, game, mdef, cache):
    """Eye slot -> its iris texture x the game's _IrisColor.  Returns the texture written (None: no tint)."""
    node = _image_node(material)
    if node is None:
        return None
    source = _source_image(material, node)
    material["roe_hq_iris"] = game
    tint = mdef.get("colors", {}).get("_IrisColor", (1, 1, 1, 1))
    if all(abs(float(c) - 1.0) < 1e-4 for c in tint[:3]):
        node.image = source
        return None
    px, size = _pixels(source)
    name = safe_name(game) + "__iris.png"
    node.image = _write_image(os.path.join(cache, "export", name), iris_texture(px, mdef), size)
    return name


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
          cid=None, game=None, rebuild=False):
    """Build the game materials on the slots of `meshes`.  Returns (state, report); state is what
    revert() needs to put the replaced materials back (empty for in_place).  A slot that already has
    one of these materials keeps it, unless `rebuild`."""
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
    suit = re.match(r"pc_%s_(.+)$" % cid, (stem or "").lower())
    suit = suit.group(1) if suit else None       # pc_g01_yoga -> yoga (accessory_components_pc_g01_suit_yoga)
    picks = [source_material(data["materials"],
                             pick_material(data["materials"], albedo, source, old.name if old else "", suit), source,
                             old.name if old else "")
             for _obj, _index, old, albedo, source in slots]
    wanted = sorted({g for g in picks if g})
    if wanted:                              # PMX / XPS names resolve only once the definitions are read
        data, more = load_data(cid, cache, wanted, (), python, log, game)
        summary = more or summary
    # each slot samples its own mesh's first UV layer: a suit's FBX pieces call it UVMap, the body UV0
    builder = Builder(data, cache, "UVMap", params)
    state, upgraded, kept, errors, done = [], [], [], [], set()
    strokes, irises = [], []
    for (obj, index, old, albedo, source), game_mat in zip(slots, picks):
        label = "%s[%d]" % (obj.name, index)
        # brows / lashes / iris: the add-on's own materials, converted in place (the XPS and PMX use them)
        kind = None if in_place or old is None else \
            "stroke" if old.name in STROKE_SLOTS else "eye" if old.name in EYE_SLOTS else None
        if kind == "eye":
            game_mat = pick_eye(data["materials"], albedo, source, suit, cid)
        if kind and game_mat and (kind == "eye" or "_BaseMap" in data["materials"][game_mat]["textures"]):
            if old.name not in done:
                try:
                    fn = game_iris if kind == "eye" else game_stroke
                    written = fn(old, game_mat, data["materials"][game_mat], cache)
                    (irises if kind == "eye" else strokes).append("%s %s (%s)" % (label, game_mat, written or "untinted"))
                except Exception as exc:
                    errors.append("%s %s: %s" % (label, game_mat, exc))
                done.add(old.name)
            continue
        if not in_place and old is not None and old.get("roe_hq_role"):
            if not rebuild:
                # an earlier run's material: a second run (pieces it could not resolve then) leaves it
                upgraded.append("%s %s (%s, earlier run)" % (label, old.name, old["roe_hq_role"]))
                continue
            if game_mat is not None and not old.name.endswith("__replaced"):
                old.name = old.name[:50] + "__replaced"     # the rebuilt one takes HQ_<game>, not .001
        if game_mat is None or (in_place and (old is None or old.name.startswith("mmd_"))):
            kept.append(label)
            continue
        if in_place and old.name in done:
            upgraded.append("%s %s (shared)" % (label, game_mat))
            continue
        builder.uv = obj.data.uv_layers[0].name if len(obj.data.uv_layers) else "UVMap"
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
                    if xps_alpha(data["materials"][game_mat]):
                        mat["roe_hq_alpha"] = 1     # roe_xps_addon.roe_xps_render_group: alpha group
                    elif "roe_hq_alpha" in mat:
                        del mat["roe_hq_alpha"]
    report = {"cache": cache, "character": cid, "upgraded": upgraded, "kept": kept, "errors": errors,
              "strokes": strokes, "irises": irises,
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
        raise SystemExit("usage: -- <out.blend> [--cache DIR] [--preview] [--rebuild]")
    out_path = os.path.abspath(argv[0])
    cache = argv[argv.index("--cache") + 1] if "--cache" in argv else None
    meshes = [o for o in bpy.data.objects if o.type == "MESH"]
    stem = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
    _state, report = apply(meshes, stem, cache=cache, rebuild="--rebuild" in argv)
    for img in {n.image for m in bpy.data.materials if m.use_nodes for n in m.node_tree.nodes
                if n.type == "TEX_IMAGE" and n.image}:
        if not img.packed_file and os.path.isfile(bpy.path.abspath(img.filepath)):
            img.pack()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0      # no .blend1 next to the product
    bpy.ops.wm.save_as_mainfile(filepath=out_path, check_existing=False, compress=False)
    report["out"] = out_path
    if "--preview" in argv:            # after the save: the preview camera / lights never reach the .blend
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import export_character_model_blender as worker  # noqa: E402  (the batch's own preview sheet)
        root, stem_out = os.path.dirname(out_path), os.path.splitext(os.path.basename(out_path))[0]
        report["preview"] = worker.render_preview(meshes, os.path.join(root, stem_out + "_preview.png"),
                                                  os.path.join(root, "." + stem_out))
    print("ROE_HQ_BLEND=" + json.dumps(report, ensure_ascii=True))


if __name__ == "__main__":
    main()
