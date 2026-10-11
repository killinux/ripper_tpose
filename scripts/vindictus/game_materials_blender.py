r"""Vindictus game materials for an imported PMX (Blender 3.6) - the core of the vindictus_game_materials add-on.

A PMX holds one colour map per material.  The archived Vindictus .blend files
(E:\game_export\Vindictus\<character>\blend\<model>\<model>.blend, built by build_blend.py from the game's own
material instances) carry the full networks: colour with the instance tint, normal map, ORM / ARM (roughness,
metallic), skin translucency, hair colour ramp and opacity, brows and lashes, the eye's procedural iris.  For every
material of an imported Vindictus PMX this module finds the game material it was made from, appends that material
from the archive and copies its network INTO the PMX material, next to mmd_tools' own nodes, with its own output
node (all nodes vhq_*).  The MMD shader, its textures and everything the PMX export reads stay; set_mode() switches
between the two looks, as the ROE add-on (roe_game_materials) does.

PMX material names come from Blender2XPS in export_pmx.py:
    <render group>_<part>-<game material, "_" written "-">_<specular>_<bump 1>_<bump 2>
    4_Face-MI-Fiona-Face01-EyeBall_0.1_0_0     <- MI_Fiona_Face01_EyeBall on PCF_005_Face
    4_Head_0.1_0_0                             <- a part with one material keeps only the part: PCF_005_Head
    4_Onepiece-MI-PCF-Lower01-Onepiece_0.1_0_0 <- a material shared by two parts was split: MI_PCF_Lower01
Any other name is looked up as it is (punctuation and case ignored).  The .blend that holds most of the model's
materials is its home; a material found in several archived .blend files is taken from the home one.

Standalone check (imports the PMX with mmd_tools at 0.08):
    blender -b --factory-startup --python game_materials_blender.py -- <pmx> [--archive DIR] [--out x.blend]
        [--render prefix]
--render writes <prefix>_mmd.png and <prefix>_game.png (EEVEE, upper body) for comparison.
"""
import collections
import json
import os
import re
import sys

import bpy

PREFIX = "vhq_"
ARCHIVE = r"E:\game_export\Vindictus"
BASE_KEY = "vind_hq_base"
DEFAULT_PARAMS = {"normal": 1.0, "rough": 1.0, "metal": 1.0, "sss": 1.0}
SETTINGS = ("blend_method", "shadow_method", "alpha_threshold", "use_backface_culling", "show_transparent_back")
TRANSPARENCY = ("blend_method", "shadow_method", "alpha_threshold", "show_transparent_back")
# node properties never copied: identity, layout, sockets, read-only pointers (handled separately or defaults)
SKIP = {"rna_type", "name", "label", "location", "width", "width_hidden", "height", "dimensions", "parent", "select",
        "inputs", "outputs", "internal_links", "type", "bl_idname", "bl_label", "bl_description", "bl_icon",
        "bl_static_type", "bl_width_default", "bl_width_min", "bl_width_max", "bl_height_default", "bl_height_min",
        "bl_height_max", "show_options", "show_preview", "show_texture", "is_active_output", "hide", "mute", "color",
        "use_custom_color"}


def log(msg):
    print("[vindictus_game_materials] " + msg, flush=True)


# --- names ---------------------------------------------------------------------------------------------------
def key(name):
    """Comparable form of a material name: lower case, every run of punctuation one '-', none at the ends."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def parse_pmx_name(name):
    """(part, material key) of a Blender2XPS name - the key is '' when only the part is left; (None, key) for any
    other name.  The XPS core never holds "_" (Blender2XPS writes them "-"), so everything after its first "_" is
    parameters, also when a burst / nude copy appended "_burst" / "_nude" or the 63-character limit cut them off;
    " 2", " 3" mark the 2nd, 3rd slot of one material on one part."""
    name = re.sub(r"\.\d{3}$", "", name)
    tokens = name.split("_")
    if len(tokens) < 2 or not tokens[0].isdigit() or not tokens[1]:
        return None, key(name)
    core = re.sub(r"\s+\d+$", "", tokens[1])
    part, _, mat = core.partition("-")
    return part, key(mat) if mat else ""


# --- the archive ---------------------------------------------------------------------------------------------
def blend_files(root):
    out = []
    if not os.path.isdir(root):
        return out
    for character in sorted(os.listdir(root)):
        folder = os.path.join(root, character, "blend")
        if not os.path.isdir(folder):
            continue
        for model in sorted(os.listdir(folder)):
            path = os.path.join(folder, model, model + ".blend")
            if os.path.isfile(path):
                out.append(path)
    return out


def index_path():
    return os.path.join(bpy.utils.user_resource("CONFIG"), "vindictus_game_materials_index.json")


def _save_index(entries, cache, root=None):
    """Merge entries into the cache file; with root, entries of .blend files under root that are gone are dropped."""
    try:
        with open(cache, encoding="utf-8") as fh:
            old = json.load(fh)
    except (OSError, ValueError):
        old = {}
    if root:
        old = {p: e for p, e in old.items() if not p.startswith(root)}
    old.update(entries)
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump(old, fh, ensure_ascii=False, indent=1)
    except OSError:
        pass


def archive_index(root=ARCHIVE, cache=None, fresh=False):
    """{blend path: {"stamp", "materials"[, "parts"]}} for every archived .blend.  Cached by size + mtime, so only new
    or changed .blend files are opened (names only, nothing is loaded); "parts" is added by blend_parts()."""
    cache = cache or index_path()
    old = {}
    if not fresh:
        try:
            with open(cache, encoding="utf-8") as fh:
                old = json.load(fh)
        except (OSError, ValueError):
            old = {}
    index, changed = {}, fresh
    for path in blend_files(root):
        st = os.stat(path)
        stamp = "%d:%d" % (st.st_size, int(st.st_mtime))
        entry = old.get(path)
        if entry and entry.get("stamp") == stamp:
            index[path] = entry
            continue
        with bpy.data.libraries.load(path, link=False) as (src, _dst):
            names = list(src.materials)
        index[path] = {"stamp": stamp, "materials": names}
        changed = True
    if changed or any(p.startswith(root) and p not in index for p in old):
        _save_index(index, cache, root)
    return index


def blend_parts(path, index, cache=None):
    """{part key: distinct materials in slot order} of an archived .blend's meshes (objects <model>_<part>).  The
    objects are linked for a moment (0.1 s) and the library removed again; cached in the index."""
    entry = index[path]
    if "parts" in entry:
        return entry["parts"]
    model = os.path.splitext(os.path.basename(path))[0]
    target = os.path.normcase(os.path.abspath(path))
    same = lambda lib: os.path.normcase(os.path.abspath(bpy.path.abspath(lib.filepath))) == target
    linked_before = any(same(lib) for lib in bpy.data.libraries)
    parts = {}
    with bpy.data.libraries.load(path, link=True) as (src, dst):
        dst.objects = list(src.objects)
    try:
        for obj in dst.objects:
            if obj is None or obj.type != "MESH":
                continue
            part = obj.name[len(model) + 1:] if obj.name.startswith(model + "_") else obj.name.rsplit("_", 1)[-1]
            mats = []
            for slot in obj.material_slots:
                if slot.material is not None and slot.material.name not in mats:
                    mats.append(slot.material.name)
            parts[key(part)] = mats
    finally:
        if not linked_before:                   # never take away a library the open file links itself
            for lib in [lib for lib in bpy.data.libraries if same(lib)]:
                bpy.data.libraries.remove(lib)
    entry["parts"] = parts
    _save_index({path: entry}, cache or index_path())
    return parts


def match(names, index, hint="", parts_of=None):
    """({PMX material name: (blend path, game material)}, home blend, unmatched names).
    hint is the model's name (its root object / file): every Fiona outfit has the same face materials, so a model
    whose other parts carry only their part name (PCF_067) ties between all of them - among the .blend files with at
    least half the best vote, the one named in the hint (the longest name) is home.  parts_of(path) gives a .blend's
    {part: materials} (blend_parts) for the names that kept only the part."""
    by_key = collections.defaultdict(list)
    for path, entry in index.items():
        for name in entry["materials"]:
            by_key[key(name)].append((path, name))
    signature = {n: parse_pmx_name(n) for n in names}
    found = {}
    for sig in set(signature.values()):
        part, mkey = sig
        hits = []
        if mkey:
            hits = by_key.get(mkey, [])
            if not hits and part:
                tail = "-" + key(part)
                if mkey.endswith(tail):
                    hits = by_key.get(mkey[:-len(tail)], [])
            if not hits and len(mkey) >= 20:       # cut off by the 63-character limit: the one longer name
                longer = [k for k in by_key if k.startswith(mkey)]
                if len(longer) == 1:
                    hits = by_key[longer[0]]
        found[sig] = hits
    votes = collections.Counter()
    for hits in found.values():
        votes.update({p for p, _n in hits})
    hint_key = key(hint) if hint else ""

    def named(path):
        mk = key(os.path.splitext(os.path.basename(path))[0])
        return bool(hint_key) and re.search(r"(^|-)%s($|-)" % re.escape(mk), hint_key) is not None

    best = max(votes.values()) if votes else 0
    preferred = sorted((p for p in index if named(p) and votes.get(p, 0) >= best * 0.5),
                       key=lambda p: (-len(os.path.basename(p)), -votes.get(p, 0)))
    home = preferred[0] if preferred else (votes.most_common(1)[0][0] if votes else None)
    picks = {}
    for sig, hits in found.items():
        if not hits:
            continue
        pick = next((h for h in hits if h[0] == home), None)
        if pick is None and parts_of and sig[0]:
            # not in home: the .blend whose part of that name wears it (a burst PMX's nude body is Fiona_BaseBody's
            # BaseBody, whose skin got the neck / tone fix), else the best voted
            part = key(sig[0])
            pick = next((h for h in sorted(hits, key=lambda h: -votes[h[0]]) if h[1] in parts_of(h[0]).get(part, [])),
                        None)
        picks[sig] = pick or max(hits, key=lambda h: votes[h[0]])
    order = ([home] if home else []) + [p for p, _v in votes.most_common() if p != home]
    for sig in found:
        part, mkey = sig
        if sig in picks or mkey or not part:
            continue
        for path in order:
            mats = (parts_of(path) if parts_of else {}).get(key(part), [])
            if len(mats) == 1:
                picks[sig] = (path, mats[0])
                break
    out = {n: picks[s] for n, s in signature.items() if s in picks}
    return out, home, [n for n in names if n not in out]


# --- copying a node network ----------------------------------------------------------------------------------
def copy_ramp(src, dst):
    dst.color_mode, dst.interpolation, dst.hue_interpolation = src.color_mode, src.interpolation, src.hue_interpolation
    while len(dst.elements) > 1:
        dst.elements.remove(dst.elements[-1])
    first, rest = src.elements[0], list(src.elements)[1:]
    dst.elements[0].position, dst.elements[0].color = first.position, tuple(first.color)
    for e in rest:
        new = dst.elements.new(e.position)
        new.color = tuple(e.color)


def copy_node(src, nodes, offset):
    node = nodes.new(src.bl_idname)
    node.name = PREFIX + src.name
    node.label = src.label
    node.location = (src.location.x + offset[0], src.location.y + offset[1])
    node.width = src.width
    node.hide, node.mute = src.hide, src.mute
    for prop in src.bl_rna.properties:
        ident = prop.identifier
        if ident in SKIP or prop.is_readonly:
            continue
        try:
            setattr(node, ident, getattr(src, ident))
        except (AttributeError, TypeError, ValueError, RuntimeError):
            pass
    if getattr(src, "color_ramp", None) is not None:
        copy_ramp(src.color_ramp, node.color_ramp)
    for sockets, targets in ((src.inputs, node.inputs), (src.outputs, node.outputs)):
        for i, sock in enumerate(sockets):
            if i < len(targets) and hasattr(sock, "default_value"):
                try:
                    targets[i].default_value = sock.default_value
                except (AttributeError, TypeError, ValueError):
                    pass
    return node


def copy_network(src_mat, dst_mat):
    """The whole node tree of src_mat into dst_mat as vhq_* nodes below its own; returns the vhq output node."""
    src_tree, tree = src_mat.node_tree, dst_mat.node_tree
    own = [n for n in tree.nodes if not n.name.startswith(PREFIX)]
    low = min((n.location.y for n in own), default=0.0)
    top = max((n.location.y for n in src_tree.nodes), default=0.0)
    offset = (0.0, low - top - 600.0)
    made = {n.name: copy_node(n, tree.nodes, offset) for n in src_tree.nodes}
    for link in src_tree.links:
        a, b = made.get(link.from_node.name), made.get(link.to_node.name)
        if a is None or b is None:
            continue
        out = next((s for s in a.outputs if s.identifier == link.from_socket.identifier), None)
        inp = next((s for s in b.inputs if s.identifier == link.to_socket.identifier), None)
        if out is not None and inp is not None:
            tree.links.new(out, inp)
    outputs = [n for n in made.values() if n.type == "OUTPUT_MATERIAL"]
    hq_out = outputs[0] if outputs else None
    if hq_out is not None:
        hq_out.name = PREFIX + "output"
    return hq_out


def _socket(node, *names):
    for name in names:
        sock = node.inputs.get(name)
        if sock is not None:
            return sock
    return None


def _gain(tree, bsdf, sock_name, gain_name):
    """Put a MULTIPLY node in front of a linked BSDF input (its factor is the slider); returns its name or None."""
    sock = _socket(bsdf, sock_name)
    if sock is None or not sock.is_linked:
        return None
    link = sock.links[0]
    node = tree.nodes.new("ShaderNodeMath")
    node.name = PREFIX + gain_name
    node.operation = "MULTIPLY"
    node.use_clamp = True
    node.inputs[1].default_value = 1.0
    node.location = (bsdf.location.x - 180, bsdf.location.y - 60 * (2 if gain_name.startswith("metal") else 3))
    tree.links.new(link.from_socket, node.inputs[0])
    tree.links.new(node.outputs["Value"], sock)
    return node.name


def settings_of(mat):
    return {name: getattr(mat, name) for name in SETTINGS}


def put_settings(mat, values):
    for name, value in (values or {}).items():
        try:
            setattr(mat, name, value)
        except (AttributeError, TypeError, ValueError):
            pass


def own_output(mat):
    return next((n for n in mat.node_tree.nodes if n.type == "OUTPUT_MATERIAL" and not n.name.startswith(PREFIX)),
                None)


def set_active_output(mat, output):
    # by name: Blender hands out a new Python wrapper per access, so `is` never matches
    for node in mat.node_tree.nodes:
        if node.type == "OUTPUT_MATERIAL":
            node.is_active_output = node.name == output.name


def mmd_alpha_source(mat):
    """(socket feeding it or None, value) of the alpha mmd_tools' MMD shader draws with.  A PMX can hide a material
    with alpha 0 (the nude body inside a burst / full PMX) and show it by a material morph; once the morph sliders
    are bound, an mmd_bind node feeds that input."""
    node = mat.node_tree.nodes.get("mmd_shader")
    sock = node.inputs.get("Alpha") if node is not None else None
    if sock is not None:
        return (sock.links[0].from_socket if sock.is_linked else None), sock.default_value
    mmd = getattr(mat, "mmd_material", None)
    return None, (mmd.alpha if mmd is not None else 1.0)


def _mmd_alpha_node(tree, bsdf):
    """vhq_mmd_alpha: the game alpha times the MMD alpha, in front of the BSDF's Alpha."""
    sock = _socket(bsdf, "Alpha")
    if sock is None:
        return None
    node = tree.nodes.new("ShaderNodeMath")
    node.name = PREFIX + "mmd_alpha"
    node.operation = "MULTIPLY"
    node.use_clamp = True
    node.location = (bsdf.location.x - 180, bsdf.location.y - 300)
    if sock.is_linked:
        tree.links.new(sock.links[0].from_socket, node.inputs[0])
    else:
        node.inputs[0].default_value = sock.default_value
    tree.links.new(node.outputs["Value"], sock)
    return node


def sync_alpha(mat, base):
    """Feed vhq_mmd_alpha from wherever the MMD shader takes its alpha now (morphs may have been bound since), and
    give a material that can be hidden mmd_tools' transparency settings in the game look too.  Such a material
    also loses its subsurface scattering: EEVEE draws a hidden SSS surface black over whatever lies exactly on it -
    the burst / full PMX's nude face and body lie on the dressed ones (checked: a static 0 cures it, a Subsurface
    input driven down to 0 by the alpha does not)."""
    tree = mat.node_tree
    node = tree.nodes.get(PREFIX + "mmd_alpha")
    if node is None:
        return False
    src, value = mmd_alpha_source(mat)
    inp = node.inputs[1]
    if src is not None:
        if not (inp.is_linked and inp.links[0].from_socket == src):
            for link in list(inp.links):
                tree.links.remove(link)
            tree.links.new(src, inp)
    else:
        for link in list(inp.links):
            tree.links.remove(link)
        inp.default_value = value
    changed = False
    see_through = src is not None or value < 0.999 or base.get("can_hide", False)
    game = base["game"]
    if see_through:
        # mmd_tools' own transparency settings, which hide and show such a material right in the MMD look; with alpha
        # clip or alpha hashed instead, Fiona_full's hidden nude face (BLEND in mmd_tools) drew black over the face
        for name in TRANSPARENCY:
            if name in base["mmd"] and game.get(name) != base["mmd"][name]:
                game[name] = base["mmd"][name]
                changed = True
    if see_through and base.get("sss") and not base.get("sss_off"):
        base["sss_off"] = True
        changed = True
    if base.get("sss_off"):
        bsdf = tree.nodes.get(base.get("bsdf", ""))
        sss = _socket(bsdf, "Subsurface", "Subsurface Weight") if bsdf is not None else None
        if sss is not None and not sss.is_linked:
            sss.default_value = 0.0
    if changed:
        mat[BASE_KEY] = json.dumps(base)
    return changed


def morph_hidden(root):
    """Names of the materials whose alpha one of the model's material morphs changes ('*': a morph on all of them) -
    they can be hidden or shown later, whether or not the morph sliders are bound yet."""
    out = set()
    mmd_root = getattr(root, "mmd_root", None)
    if mmd_root is None:
        return out
    for morph in mmd_root.material_morphs:
        for data in morph.data:
            alpha = data.diffuse_color[3]
            if (abs(alpha - 1.0) if data.offset_type == "MULT" else abs(alpha)) > 1e-4:
                out.add(data.material or "*")
    return out


def upgrade(dst, src, source_label, can_hide=False):
    """Copy src's network into dst (keeping dst's own nodes) and remember what the sliders and the switch need."""
    dst.use_nodes = True
    mmd = settings_of(dst)
    hq_out = copy_network(src, dst)
    if hq_out is None:
        raise RuntimeError("%s has no output node" % src.name)
    tree = dst.node_tree
    bsdf = next((n for n in tree.nodes if n.name.startswith(PREFIX) and n.type == "BSDF_PRINCIPLED"), None)
    base = {"source": source_label, "mmd": mmd, "game": settings_of(src), "can_hide": bool(can_hide),
            "normals": {n.name: n.inputs["Strength"].default_value for n in tree.nodes
                        if n.name.startswith(PREFIX) and n.type == "NORMAL_MAP"}}
    if bsdf is not None:
        base["bsdf"] = bsdf.name
        for sock_name, tag in (("Roughness", "rough"), ("Metallic", "metal")):
            gain = _gain(tree, bsdf, sock_name, tag + "_gain")
            sock = _socket(bsdf, sock_name)
            base[tag] = {"gain": gain} if gain else {"value": sock.default_value if sock is not None else 0.0}
        sss = _socket(bsdf, "Subsurface", "Subsurface Weight")
        base["sss"] = sss.default_value if sss is not None else 0.0
        _mmd_alpha_node(tree, bsdf)
    dst[BASE_KEY] = json.dumps(base)
    sync_alpha(dst, base)
    put_settings(dst, base["game"])
    set_active_output(dst, hq_out)


# --- what the add-on calls -----------------------------------------------------------------------------------
def materials_of(meshes):
    seen, out = set(), []
    for obj in meshes:
        for slot in obj.material_slots:
            mat = slot.material
            if mat is not None and mat.name not in seen:
                seen.add(mat.name)
                out.append(mat)
    return out


def hq_materials_of(meshes):
    return [m for m in materials_of(meshes) if m.get(BASE_KEY)]


def apply_params(materials, params=None):
    """Sliders: every value is the game's own value x the factor (DEFAULT_PARAMS = the game)."""
    p = dict(DEFAULT_PARAMS, **(params or {}))
    for mat in materials:
        base = json.loads(mat.get(BASE_KEY, "{}") or "{}")
        if not base or not mat.use_nodes:
            continue
        nodes = mat.node_tree.nodes
        for name, strength in base.get("normals", {}).items():
            node = nodes.get(name)
            if node is not None:
                node.inputs["Strength"].default_value = strength * p["normal"]
        bsdf = nodes.get(base.get("bsdf", ""))
        if bsdf is None:
            continue
        for tag, sock_name in (("rough", "Roughness"), ("metal", "Metallic")):
            entry = base.get(tag, {})
            if entry.get("gain"):
                node = nodes.get(entry["gain"])
                if node is not None:
                    node.inputs[1].default_value = p[tag]
            elif "value" in entry:
                sock = _socket(bsdf, sock_name)
                if sock is not None:
                    sock.default_value = min(1.0, max(0.0, entry["value"] * p[tag]))
        sss = _socket(bsdf, "Subsurface", "Subsurface Weight")
        if sss is not None and base.get("sss") and not base.get("sss_off"):
            sss.default_value = base["sss"] * p["sss"]


def set_mode(materials, mode):
    """'game': the vhq network renders with the game material's blend settings; 'mmd': the material's own output
    (mmd_tools' MMD shader) with mmd_tools' settings.  Both networks stay linked."""
    switched = 0
    for mat in materials:
        base = json.loads(mat.get(BASE_KEY, "{}") or "{}")
        if not base or not mat.use_nodes:
            continue
        hq_out, own = mat.node_tree.nodes.get(PREFIX + "output"), own_output(mat)
        target = hq_out if mode == "game" else own
        if target is None:
            continue
        sync_alpha(mat, base)
        set_active_output(mat, target)
        put_settings(mat, base["game"] if mode == "game" else base["mmd"])
        switched += 1
    return switched


def remove(materials):
    """Take the vhq network out again: the material is as mmd_tools made it."""
    removed = 0
    for mat in materials:
        base = json.loads(mat.get(BASE_KEY, "{}") or "{}")
        if not base or not mat.use_nodes:
            continue
        nodes = mat.node_tree.nodes
        for node in [n for n in nodes if n.name.startswith(PREFIX)]:
            nodes.remove(node)
        own = own_output(mat)
        if own is not None:
            set_active_output(mat, own)
        put_settings(mat, base.get("mmd"))
        del mat[BASE_KEY]
        removed += 1
    return removed


def apply(meshes, archive=ARCHIVE, params=None, rebuild=False, hint="", root=None):
    """Give every material of the meshes its game network.  hint: the model's name (match()); root: the mmd_tools
    root, for its material morphs (morph_hidden()).  Returns a report dict: home .blend, upgraded (PMX name -> game
    material), already (skipped, done before), unmatched, errors."""
    report = {"home": None, "upgraded": {}, "already": [], "unmatched": [], "errors": []}
    hidden = morph_hidden(root)
    targets = []
    for mat in materials_of(meshes):
        if mat.get(BASE_KEY):
            if not rebuild:
                report["already"].append(mat.name)
                continue
            remove([mat])
        targets.append(mat)
    if not targets:
        return report
    index = archive_index(archive)
    if not index:
        raise RuntimeError("存档里没有 .blend：%s\\<角色>\\blend\\<模型>\\<模型>.blend" % archive)
    picks, home, unmatched = match([m.name for m in targets], index, hint, lambda path: blend_parts(path, index))
    report["home"], report["unmatched"] = home, unmatched
    wanted = collections.defaultdict(set)
    for path, name in picks.values():
        wanted[path].add(name)
    loaded = {}
    for path, names in wanted.items():
        with bpy.data.libraries.load(path, link=False) as (src, dst):
            present = [n for n in sorted(names) if n in src.materials]
            dst.materials = list(present)
        for name, mat in zip(present, dst.materials):
            if mat is not None:                     # appended under its own name or with .001 when taken
                loaded[(path, name)] = mat
    try:
        for mat in targets:
            pick = picks.get(mat.name)
            if pick is None:
                continue
            src = loaded.get(pick)
            if src is None:
                report["errors"].append("%s: %s not loaded from %s" % (mat.name, pick[1], pick[0]))
                continue
            try:
                upgrade(mat, src, "%s : %s" % (os.path.basename(pick[0]), pick[1]),
                        can_hide="*" in hidden or mat.name in hidden)
                report["upgraded"][mat.name] = pick[1]
            except Exception as exc:          # one bad material must not stop the rest
                report["errors"].append("%s: %s" % (mat.name, exc))
    finally:
        for src in loaded.values():
            bpy.data.materials.remove(src)
    apply_params([m for m in targets if m.get(BASE_KEY)], params)
    return report


# --- standalone check ----------------------------------------------------------------------------------------
def _render(scene, path):
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


def _cli():
    argv = sys.argv[sys.argv.index("--") + 1:]
    pmx_path = argv[0]
    archive = argv[argv.index("--archive") + 1] if "--archive" in argv else ARCHIVE
    out = argv[argv.index("--out") + 1] if "--out" in argv else None
    prefix = argv[argv.index("--render") + 1] if "--render" in argv else None
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="mmd_tools")
    bpy.ops.mmd_tools.import_model(filepath=pmx_path, scale=0.08, types={"MESH", "ARMATURE", "MORPHS"})
    root = next(o for o in bpy.data.objects if getattr(o, "mmd_type", "") == "ROOT")
    meshes = [o for o in root.children_recursive if o.type == "MESH" and getattr(o, "mmd_type", "NONE") == "NONE"]
    report = apply(meshes, archive, hint="%s %s" % (root.name, os.path.basename(pmx_path)), root=root)
    print("VGM_REPORT=" + json.dumps(report, ensure_ascii=False))
    if prefix:
        from mathutils import Vector
        scene = bpy.context.scene
        scene.render.engine = "BLENDER_EEVEE"
        scene.render.resolution_x, scene.render.resolution_y = 800, 1000
        scene.eevee.taa_render_samples = 32
        scene.view_settings.view_transform = "Standard"
        world = bpy.data.worlds.new("world")
        world.use_nodes = True
        world.node_tree.nodes["Background"].inputs[0].default_value = (0.35, 0.35, 0.38, 1.0)
        scene.world = world
        for name, energy, rot in (("key", 3.0, (0.9, 0.0, 0.6)), ("fill", 1.0, (1.1, 0.0, -2.3))):
            lamp = bpy.data.objects.new(name, bpy.data.lights.new(name, "SUN"))
            lamp.data.energy = energy
            lamp.rotation_euler = rot
            scene.collection.objects.link(lamp)
        lo = Vector((min(v[i] for o in meshes for v in (o.matrix_world @ Vector(c) for c in o.bound_box)) for i in range(3)))
        hi = Vector((max(v[i] for o in meshes for v in (o.matrix_world @ Vector(c) for c in o.bound_box)) for i in range(3)))
        cam = bpy.data.objects.new("cam", bpy.data.cameras.new("cam"))
        scene.collection.objects.link(cam)
        cam.data.lens = 60
        target = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + (hi.z - lo.z) * 0.80))
        cam.location = target + Vector((0.0, -(hi.z - lo.z) * 0.62, 0.0))
        cam.rotation_euler = (1.5708, 0.0, 0.0)
        scene.camera = cam
        mats = hq_materials_of(meshes)
        set_mode(mats, "mmd")
        _render(scene, os.path.abspath(prefix + "_mmd.png"))
        set_mode(mats, "game")
        _render(scene, os.path.abspath(prefix + "_game.png"))
    if out:
        bpy.ops.wm.save_as_mainfile(filepath=os.path.abspath(out))


if __name__ == "__main__":
    _cli()
