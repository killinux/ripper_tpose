"""Decode Unity AnimationClips (generic transform curves) - enough to pose a face.

The face of an Action Taimanin character is about 28 bones, and its expressions are clips
(``animation_char/<char>/ani_story/ani_face_<char>_story_smile_01.anim`` ...).  A clip stores

* bindings   (path hash, attribute) per curve group: attribute 1 = position (3 curves), 2 = rotation
             quaternion (4), 3 = scale (3), 4 = Euler angles (3); the path hash is the CRC32 of the
             transform path below the Animator ("root_face/Bone_face/Bone_Face_Lip_L");
* curves     in three stores, in this order: streamed (keys with cubic coefficients), dense (one sample per
             frame), constant (one value).  Binding k owns the next 3 or 4 curve indices.

Clip.sample(t) returns {path hash: {"position" | "rotation" | "scale" | "euler": tuple}} - only what the clip
keys.  Nothing here needs Blender or the game; the reader takes the type tree UnityPy gives.
"""
from __future__ import annotations

import bisect
import struct
import zlib

ATTRIBUTES = {1: ("position", 3), 2: ("rotation", 4), 3: ("scale", 3), 4: ("euler", 3)}
TRANSFORM = 4                                           # class id of Transform


def path_hash(path: str) -> int:
    return zlib.crc32(path.encode("utf-8")) & 0xFFFFFFFF


def _streamed(words: list[int]) -> list[tuple[float, list[tuple[int, tuple]]]]:
    """[(time, [(curve index, (c0, c1, c2, value))])] from the uint32 stream."""
    data = struct.pack("<%dI" % len(words), *words)
    frames, pos = [], 0
    while pos + 8 <= len(data):
        time, count = struct.unpack_from("<fi", data, pos)
        pos += 8
        keys = []
        for _ in range(count):
            index, c0, c1, c2, value = struct.unpack_from("<iffff", data, pos)
            pos += 20
            keys.append((index, (c0, c1, c2, value)))
        frames.append((time, keys))
    return frames


class Clip:
    def __init__(self, tree: dict):
        self.name = tree.get("m_Name", "")
        self.rate = float(tree.get("m_SampleRate") or 30.0)
        muscle = tree["m_MuscleClip"]
        self.start, self.stop = float(muscle.get("m_StartTime", 0.0)), float(muscle.get("m_StopTime", 0.0))
        clip = muscle["m_Clip"]
        clip = clip.get("data", clip)
        streamed, dense, constant = clip["m_StreamedClip"], clip["m_DenseClip"], clip["m_ConstantClip"]
        self.streamed_count = int(streamed["curveCount"])
        # per streamed curve: key times and (time, coefficients)
        self.keys: list[list[tuple[float, tuple]]] = [[] for _ in range(self.streamed_count)]
        for time, keys in _streamed(list(streamed["data"])):
            for index, coeff in keys:
                if 0 <= index < self.streamed_count:
                    self.keys[index].append((time, coeff))
        self.key_times = [[k[0] for k in curve] for curve in self.keys]
        self.dense_count = int(dense["m_CurveCount"])
        self.dense_frames = int(dense["m_FrameCount"])
        self.dense_rate = float(dense["m_SampleRate"] or self.rate)
        self.dense_begin = float(dense["m_BeginTime"])
        self.dense = list(dense["m_SampleArray"])
        self.constant = list(constant["data"])
        self.bindings = []                              # (path hash, attribute name, first curve, curve count)
        index = 0
        for binding in (tree.get("m_ClipBindingConstant") or {}).get("genericBindings") or []:
            name, count = ATTRIBUTES.get(binding["attribute"], ("float", 1))
            transform = binding.get("typeID", TRANSFORM) == TRANSFORM and binding["attribute"] in ATTRIBUTES
            self.bindings.append((int(binding["path"]) & 0xFFFFFFFF, name if transform else "float", index,
                                  count if transform else 1))
            index += count if transform else 1
        self.curve_count = index

    def value(self, curve: int, t: float) -> float:
        if curve < self.streamed_count:
            times = self.key_times[curve]
            if not times:
                return 0.0
            i = max(bisect.bisect_right(times, t) - 1, 0)
            time, (c0, c1, c2, value) = self.keys[curve][i]
            dt = t - time
            if time < -1e30 or dt <= 0.0:              # the first key is stamped -infinity: its value holds
                return value
            return ((c0 * dt + c1) * dt + c2) * dt + value
        curve -= self.streamed_count
        if curve < self.dense_count:
            if not self.dense_frames:
                return 0.0
            f = (t - self.dense_begin) * self.dense_rate
            lo = min(max(int(f), 0), self.dense_frames - 1)
            hi = min(lo + 1, self.dense_frames - 1)
            a, b = self.dense[lo * self.dense_count + curve], self.dense[hi * self.dense_count + curve]
            return a + (b - a) * min(max(f - lo, 0.0), 1.0)
        curve -= self.dense_count
        return self.constant[curve] if curve < len(self.constant) else 0.0

    def sample(self, t: float) -> dict[int, dict[str, tuple]]:
        out: dict[int, dict[str, tuple]] = {}
        for path, name, first, count in self.bindings:
            if name == "float":
                continue
            out.setdefault(path, {})[name] = tuple(self.value(first + k, t) for k in range(count))
        return out

    def times(self) -> list[float]:
        """Every frame time of the clip at its sample rate, the stop time included."""
        count = max(int(round((self.stop - self.start) * self.rate)), 0)
        return [self.start + i / self.rate for i in range(count)] + [self.stop]
