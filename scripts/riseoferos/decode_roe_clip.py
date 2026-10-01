"""Decode a Rise of Eros AnimationClip from an asset bundle into plain per-frame bone transforms.

ROE character motions are Unity *generic* clips: every curve is bound to a Transform by the CRC32
of its path below the Animator (``Bip001/Bip001 Pelvis/...``), and the keys live in Unity's packed
``m_StreamedClip`` (cubic Hermite segments), ``m_DenseClip`` (sampled) and ``m_ConstantClip``.
AssetStudio's FBX export of the same bundle carries no animation, so the clip is decoded here.

The output JSON (Unity space: left-handed, Y up, metres) holds the skeleton the clip animates and,
for each sampled frame, the local position / rotation (x, y, z, w) / scale of every transform; a
transform the clip does not touch keeps its rest value.  ``make_roe_vmd.py`` turns it into a VMD.

Usage:
  python decode_roe_clip.py <bundle.ab> --list
  python decode_roe_clip.py <bundle.ab> <clip name> <out.json> [--fps 30]
"""
import argparse
import json
import struct
import zlib

import UnityPy


def read_skeleton(env, root_name=None):
    """Transforms of the prefab that owns the Animator: name, parent, rest TRS, path, path CRC.

    A bundle can hold several animated prefabs (the nude-body bundles carry FX timelines next to the body), so
    the Animator is the one on the GameObject called ``root_name``, or else the one over the most transforms."""
    transforms = {}
    animator_gos = []
    for obj in env.objects:
        if obj.type.name == "Transform":
            transforms[obj.path_id] = obj.read_typetree()
        elif obj.type.name == "Animator":
            animator_gos.append(obj.read_typetree()["m_GameObject"]["m_PathID"])
    names = {}
    for obj in env.objects:
        if obj.type.name == "GameObject":
            names[obj.path_id] = obj.read_typetree()["m_Name"]
    tf_of_go = {t["m_GameObject"]["m_PathID"]: pid for pid, t in transforms.items()}

    def size(pid):
        return 1 + sum(size(c["m_PathID"]) for c in transforms[pid]["m_Children"] if c["m_PathID"] in transforms)
    roots = [tf_of_go[go] for go in animator_gos if go in tf_of_go]
    if root_name:
        roots = [pid for pid in roots if names.get(transforms[pid]["m_GameObject"]["m_PathID"]) == root_name]
        if not roots:
            raise SystemExit("no Animator on a GameObject named %s" % root_name)
    root = max(roots, key=size)
    bones = []

    def walk(pid, parent, path):
        t = transforms[pid]
        name = names[t["m_GameObject"]["m_PathID"]]
        here = "" if parent < 0 else (name if not path else path + "/" + name)
        index = len(bones)
        p, r, s = t["m_LocalPosition"], t["m_LocalRotation"], t["m_LocalScale"]
        bones.append({"name": name, "parent": parent, "path": here, "tf": pid,
                      "crc": zlib.crc32(here.encode("utf-8")),
                      "pos": [p["x"], p["y"], p["z"]], "rot": [r["x"], r["y"], r["z"], r["w"]],
                      "scale": [s["x"], s["y"], s["z"]]})
        for child in t["m_Children"]:
            walk(child["m_PathID"], index, here)

    walk(root, -1, "")
    read_bind_poses(env, transforms, bones, names)
    return bones


def read_bind_poses(env, transforms, bones, names):
    """World matrix of every skinned bone at bind time (Unity space), from the skinned meshes.

    The prefab's Transform values are not always the pose the meshes were bound in: the body agrees,
    but the g04 fan's carrier sits at scale 2.19 in the Transforms while its mesh was bound with it
    folded differently.  Our FBX/PMX rests are the bind pose, so motion deltas must start from it:
    bone world at bind = renderer world (rest) * inverse(bindpose).
    """
    index_of_tf = {}
    for i, b in enumerate(bones):
        index_of_tf[b["tf"]] = i
    meshes = {o.path_id: o for o in env.objects if o.type.name == "Mesh"}
    for obj in env.objects:
        if obj.type.name != "SkinnedMeshRenderer":
            continue
        smr = obj.read_typetree()
        mesh = meshes.get(smr["m_Mesh"]["m_PathID"])
        go = smr["m_GameObject"]["m_PathID"]
        renderer_tf = next((pid for pid, t in transforms.items() if t["m_GameObject"]["m_PathID"] == go), None)
        if mesh is None or renderer_tf not in index_of_tf:
            continue
        binds = mesh.read_typetree()["m_BindPose"]
        for bone_ptr, m in zip(smr["m_Bones"], binds):
            i = index_of_tf.get(bone_ptr["m_PathID"])
            if i is None or "bind" in bones[i]:
                continue
            rows = [[m["e%d%d" % (r, c)] for c in range(4)] for r in range(4)]
            bones[i]["bind"] = {"renderer": index_of_tf[renderer_tf], "inv": rows}


def curve_bindings(bindings):
    """One (binding, component) per curve index, in Unity's order (position 3, rotation 4, scale 3)."""
    out = []
    for b in bindings:
        width = 1
        if b["typeID"] == 4:
            width = {1: 3, 2: 4, 3: 3, 4: 3}.get(b["attribute"], 1)
        out.extend((b, k) for k in range(width))
    return out


def streamed_keys(words):
    """Unity's StreamedClip: frames of (time, keys); each key = curve index + cubic coefficients."""
    raw = struct.pack("<%dI" % len(words), *words)
    pos, frames = 0, []
    while pos < len(raw):
        time, count = struct.unpack_from("<fi", raw, pos)
        pos += 8
        keys = []
        for _ in range(count):
            index, c0, c1, c2, c3 = struct.unpack_from("<i4f", raw, pos)
            pos += 20
            keys.append((index, (c0, c1, c2, c3)))
        frames.append((time, keys))
    return frames


class Clip:
    def __init__(self, tree):
        self.name = tree["m_Name"]
        muscle = tree["m_MuscleClip"]
        self.start, self.stop = muscle["m_StartTime"], muscle["m_StopTime"]
        clip = muscle["m_Clip"]["data"]
        self.curves = curve_bindings(tree["m_ClipBindingConstant"]["genericBindings"])
        streamed = clip["m_StreamedClip"]
        self.n_streamed = streamed["curveCount"]
        # per streamed curve: sorted segment start times and coefficients
        self.segments = [[] for _ in range(self.n_streamed)]
        for time, keys in streamed_keys(streamed["data"]):
            for index, coeff in keys:
                if 0 <= index < self.n_streamed:
                    self.segments[index].append((time, coeff))
        dense = clip["m_DenseClip"]
        self.dense = dense
        self.n_dense = dense["m_CurveCount"]
        self.const = clip["m_ConstantClip"]["data"]

    def value(self, index, t):
        if index < self.n_streamed:
            seg = self.segments[index]
            lo = None
            for start, coeff in seg:
                if start <= t:
                    lo = (start, coeff)
                else:
                    break
            if lo is None:
                lo = seg[0]
            dt = t - lo[0]
            c0, c1, c2, c3 = lo[1]
            return ((c0 * dt + c1) * dt + c2) * dt + c3
        index -= self.n_streamed
        if index < self.n_dense:
            d = self.dense
            f = (t - d["m_BeginTime"]) * d["m_SampleRate"]
            n = d["m_FrameCount"]
            f0 = max(0, min(n - 1, int(f)))
            f1 = min(n - 1, f0 + 1)
            w = min(max(f - f0, 0.0), 1.0)
            a = d["m_SampleArray"][f0 * self.n_dense + index]
            b = d["m_SampleArray"][f1 * self.n_dense + index]
            return a + (b - a) * w
        return self.const[index - self.n_dense]


def clips_in(env):
    """{clip name: AnimationClip object} of a loaded bundle (the last one when names repeat; see named_clips)."""
    return {o.peek_name(): o for o in env.objects if o.type.name == "AnimationClip"}


def named_clips(env, name):
    """Every AnimationClip called ``name``.  An H-scene bundle has two per name: eros07_p1 of the woman
    (~650 curves) and of the man (~190), each made for its own skeleton."""
    return [o for o in env.objects if o.type.name == "AnimationClip" and o.peek_name() == name]


def binding_hits(clip_obj, bones):
    """How many of the clip's Transform bindings land on this skeleton."""
    crcs = {b["crc"] for b in bones}
    tree = clip_obj.read_typetree()
    return sum(1 for b in tree["m_ClipBindingConstant"]["genericBindings"] if b["typeID"] == 4 and b["path"] in crcs)


def pick_clip(clip_objs, bones):
    """The clip of that name made for this skeleton (most bindings on it)."""
    return max(clip_objs, key=lambda o: binding_hits(o, bones))


def list_clips(env):
    """[(clip name, seconds)] sorted by name."""
    out = []
    for name, obj in sorted(clips_in(env).items()):
        t = obj.read_typetree()["m_MuscleClip"]
        out.append((name, t["m_StopTime"] - t["m_StartTime"]))
    return out


def blendshape_curves(clip_obj, fps=30.0):
    """Blend-shape weights a clip keys on skinned meshes (typeID 137), sampled like decode_clip:
    {"<renderer path CRC>:<attribute CRC>": [weight 0..100 per frame]}.  The attribute is the CRC32 of
    "blendShape.<shape name>"; ROE's H scenes key their scene shapes (E07_Pussy_fixShape ...) this way."""
    clip = Clip(clip_obj.read_typetree())
    n_frames = int(round((clip.stop - clip.start) * fps)) + 1
    out = {}
    for index, (binding, _comp) in enumerate(clip.curves):
        if binding["typeID"] == 137:
            key = "%d:%d" % (binding["path"], binding["attribute"])
            out[key] = [round(clip.value(index, clip.start + f / fps), 4) for f in range(n_frames)]
    return out


def decode_clip(clip_obj, bones, out_path, fps=30.0):
    """Sample one clip on the given skeleton (read_skeleton) and write the JSON; returns a one-line summary."""
    by_crc = {b["crc"]: i for i, b in enumerate(bones)}
    clip = Clip(clip_obj.read_typetree())
    # which bone/channel each curve drives
    drive, unbound = {}, set()
    animator_curves = {}            # curves bound to the Animator itself (root motion), by attribute
    for index, (binding, comp) in enumerate(clip.curves):
        if binding["typeID"] == 95:
            animator_curves[binding["attribute"]] = index
            continue
        if binding["typeID"] != 4:
            continue
        bone = by_crc.get(binding["path"])
        if bone is None:
            unbound.add(binding["path"])
            continue
        channel = {1: "pos", 2: "rot", 3: "scale"}.get(binding["attribute"])
        if channel:
            drive.setdefault((bone, channel), {})[comp] = index
    n_frames = int(round((clip.stop - clip.start) * fps)) + 1
    frames = []
    for f in range(n_frames):
        t = clip.start + f / fps
        local = {}
        for (bone, channel), comps in drive.items():
            vals = [clip.value(comps[k], t) if k in comps else bones[bone][channel][k]
                    for k in range(4 if channel == "rot" else 3)]
            if channel == "rot":
                n = sum(v * v for v in vals) ** 0.5 or 1.0
                vals = [v / n for v in vals]
            local.setdefault(bone, {})[channel] = [round(v, 7) for v in vals]
        frames.append(local)
    animated = sorted({bone for bone, _ in drive})
    root_curves = {str(attr): [round(clip.value(index, clip.start + f / fps), 6) for f in range(n_frames)]
                   for attr, index in sorted(animator_curves.items())}
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump({"clip": clip.name, "fps": fps, "duration": clip.stop - clip.start,
                   "bones": bones, "animated": animated, "animator_curves": root_curves,
                   "frames": [{str(k): v for k, v in fr.items()} for fr in frames]}, fh, ensure_ascii=False)
    return ("clip %s: %.2f s -> %d frames at %g fps, %d bones animated of %d (%d with a bind pose), "
            "%d curve paths unbound" % (clip.name, clip.stop - clip.start, n_frames, fps, len(animated), len(bones),
                                        sum(1 for b in bones if "bind" in b), len(unbound)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("bundle")
    ap.add_argument("clip", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--fps", type=float, default=30.0)
    ap.add_argument("--skeleton", help="take the skeleton and bind poses from this bundle instead (the battle "
                                       "clips live with the low-detail prefab, whose hair renderer sits 2.47 m "
                                       "away; our PMX is the _hd one; H-scene clips need the nude body's bundle)")
    ap.add_argument("--root", help="the GameObject whose Animator owns the skeleton (default: the largest one)")
    args = ap.parse_args()
    env = UnityPy.load(args.bundle)
    if args.list or not args.clip:
        for name, seconds in list_clips(env):
            print("%-30s %.2f s" % (name, seconds))
        return
    bones = read_skeleton(UnityPy.load(args.skeleton) if args.skeleton else env, args.root)
    clips = named_clips(env, args.clip)
    if not clips:
        raise SystemExit("no clip %s in %s" % (args.clip, args.bundle))
    print(decode_clip(pick_clip(clips, bones), bones, args.out, args.fps))


if __name__ == "__main__":
    main()
