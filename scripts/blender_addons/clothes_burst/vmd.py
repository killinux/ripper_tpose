# -*- coding: utf-8 -*-
"""MMD 爆衣的表情关键帧（VMD）：只有表情帧的 VMD，或把这些帧合进一段动作的 VMD。纯 Python（不用 bpy），
插件和命令行（scripts/riseoferos/burst_vmd.py）共用。

两种做法（shards.py / mmd.py 做出的表情）：
  碎片飞散  第 F 帧衣服隐藏（衣服非表示_材質）、原位的碎片显示（爆衣碎片_材質），碎片 8 帧内飞出（爆衣，先快后慢），
            第 F+6 帧起 24 帧落地（爆衣落下，越落越快），之后淡出；身体在 F..F+2 换成完整的（裸体形状）——
            这时碎片已经离开身体，完整身体不会从碎片里穿出来
  直接消失  衣服在 N 帧内淡出（N = 1 就是一下子没了），淡完那一帧身体换成完整的
MMD 的表情帧之间是直线插值，曲线用几个关键帧拼出来。帧数按 30 fps；slow 把时间拉长（1.5 = 慢一半）。

几层衣服叠在一个模型里（scripts/clothes_burst/pmx_layers.py：步骤滑块 1_A脱ぎ、2_B脱ぎ……）时一层一层爆（layer_keys）：
第 k 层在 F = start + (k-1) x interval 帧爆开：这层的碎片（k_爆衣碎片_材質）在 F 帧出现在原位、飞出（k_爆衣）、落地
（k_爆衣落下）、淡出，和一件衣服时一样；步骤滑块 k 在 F+1 帧拉到 1（这层隐藏、收进身体，下一层出现）——碎片这时已经
离开，下一层不会从还在原位的碎片里穿出来（下一层的脚是光脚、这层是高跟靴，大腿的皮肤贴着紧身衣），F 帧这层和碎片
重合、看起来一样。这层没有碎片（只有皮肤）时步骤滑块在 F 帧拉；直接消失时只拉步骤滑块。
"""
import re
import struct

OUTFIT = "衣服非表示_材質"       # 衣服的材质 alpha x 0
SHARDS = "爆衣碎片_材質"         # 碎片的材质 alpha 加回来
THROW = "爆衣"                  # 碎片飞出去（顶点表情）
FALL = "爆衣落下"               # 碎片落到地上（顶点表情，叠加在 爆衣 上）
BODY = "裸体形状"               # 身体换成完整的（两份身体时是材质表情，一份身体时是顶点表情）
GROUP = "衣服非表示"            # 组合表情：OUTFIT + BODY，平时拉滑块用
STEP = re.compile(r"^(\d+)_(.+)脱ぎ$")   # pmx_layers.py 的步骤滑块：第几步、脱掉哪一层

THROW_CURVE = [(0, 0.0), (1, 0.45), (2, 0.70), (4, 0.88), (8, 1.0)]
FALL_CURVE = [(0, 0.0), (4, 0.03), (8, 0.12), (12, 0.27), (16, 0.48), (20, 0.75), (24, 1.0)]
FALL_START = 6
BODY_FRAMES = 2

DEFAULTS = {
    "start": 120,           # 爆开帧
    "slow": 1.0,            # 时间拉长倍数
    "shards": True,         # 碎片飞散（False = 直接消失）
    "vanish_frames": 1,     # 直接消失：衣服淡出用几帧（1 = 一下子）
    "fade_start": 26,       # 碎片：爆开后第几帧开始淡出
    "fade_end": 40,         # ... 第几帧完全消失（<= fade_start = 不消失）
    "interval": 90,         # 几层衣服时：一层爆开到下一层爆开隔几帧
}
SIGNATURE = b"Vocaloid Motion Data 0002"


def stage_names(k):
    """几层衣服时第 k 层（步骤滑块 k_X脱ぎ）的碎片表情：{"throw", "fall", "shards"}（都不超过 VMD 的 15 字节）"""
    return {"throw": "%d_%s" % (k, THROW), "fall": "%d_%s" % (k, FALL), "shards": "%d_%s" % (k, SHARDS)}


def burst_keys(start=DEFAULTS["start"], slow=DEFAULTS["slow"], shards=DEFAULTS["shards"],
               vanish_frames=DEFAULTS["vanish_frames"], fade_start=DEFAULTS["fade_start"],
               fade_end=DEFAULTS["fade_end"], interval=None):
    """[(morph, frame, weight)]，start 至少 1（开关在前一帧打 0）。interval 只有 layer_keys 用。"""
    if start < 1:
        raise ValueError("start must be at least 1 (the switch is keyed on the frame before)")

    def at(f):
        return int(round(start + f * slow))
    keys = []
    if shards:
        keys += [(OUTFIT, start - 1, 0.0), (OUTFIT, start, 1.0)]
        keys += [(SHARDS, start - 1, 0.0), (SHARDS, start, 1.0)]
        if fade_end > fade_start:
            keys += [(SHARDS, at(fade_start), 1.0), (SHARDS, at(fade_end), 0.0)]
        keys += [(THROW, at(f), w) for f, w in THROW_CURVE]
        keys += [(FALL, at(FALL_START + f), w) for f, w in FALL_CURVE]
        keys += [(BODY, start, 0.0), (BODY, at(BODY_FRAMES), 1.0)]
    else:
        n = max(1, int(vanish_frames))
        keys += [(OUTFIT, start - 1, 0.0), (OUTFIT, at(n - 1) if n > 1 else start, 1.0)]
        end = at(n - 1) if n > 1 else start
        keys += [(BODY, end - 1, 0.0), (BODY, end, 1.0)]
    return keys


def layer_keys(steps, start=DEFAULTS["start"], slow=DEFAULTS["slow"], shards=DEFAULTS["shards"],
               vanish_frames=DEFAULTS["vanish_frames"], fade_start=DEFAULTS["fade_start"],
               fade_end=DEFAULTS["fade_end"], interval=DEFAULTS["interval"]):
    """一层一层爆：steps = [(k, 步骤滑块名, 这层有没有碎片)]，按顺序；第 i 个在 start + i x interval 帧。
    [(morph, frame, weight)]。"""
    if start < 1:
        raise ValueError("start must be at least 1 (the switch is keyed on the frame before)")
    keys = []
    for i, step_entry in enumerate(steps):
        k, step = step_entry[0], step_entry[1]
        has_shards = shards and (len(step_entry) < 3 or step_entry[2])
        f0 = start + i * int(interval)

        def at(f, f0=f0):
            return int(round(f0 + f * slow))
        if has_shards:
            names = stage_names(k)
            keys += [(step, f0, 0.0), (step, f0 + 1, 1.0)]      # the layer goes when its fragments leave
            keys += [(names["shards"], f0 - 1, 0.0), (names["shards"], f0, 1.0)]
            if fade_end > fade_start:
                keys += [(names["shards"], at(fade_start), 1.0), (names["shards"], at(fade_end), 0.0)]
            keys += [(names["throw"], at(f), w) for f, w in THROW_CURVE]
            keys += [(names["fall"], at(FALL_START + f), w) for f, w in FALL_CURVE]
        elif shards:
            keys += [(step, f0 - 1, 0.0), (step, f0, 1.0)]      # a layer of skin only: swapped at once
        else:
            n = max(1, int(vanish_frames))
            keys += [(step, f0 - 1, 0.0), (step, at(n - 1) if n > 1 else f0, 1.0)]
    return keys


def _sjis(name, size):
    return name.encode("shift_jis")[:size].ljust(size, b"\0")


def _morph_records(keys):
    return b"".join(_sjis(name, 15) + struct.pack("<If", frame, weight) for name, frame, weight in keys)


def write_morph_vmd(path, keys, model=""):
    """只有表情帧的 VMD（在 MMD 里叠加在任何动作上读入）。"""
    data = SIGNATURE.ljust(30, b"\0") + _sjis(model, 20)
    data += struct.pack("<I", 0)                                    # 骨骼帧
    data += struct.pack("<I", len(keys)) + _morph_records(keys)
    data += struct.pack("<IIII", 0, 0, 0, 0)                        # 镜头、光源、自影、IK / 显示
    with open(path, "wb") as handle:
        handle.write(data)
    return len(keys)


def merge(motion, path, keys):
    """motion 这段 VMD 原样留下（骨骼、别的表情、镜头……），只把这几个表情（爆衣的那几个和 keys 里有的）的帧换成
    keys，写到 path。返回被替换掉的旧帧数。"""
    with open(motion, "rb") as handle:
        data = handle.read()
    if not data.startswith(b"Vocaloid Motion Data"):
        raise ValueError("not a VMD: " + motion)
    pos = 50
    n_bones, = struct.unpack_from("<I", data, pos)
    pos += 4 + n_bones * 111
    n_morphs, = struct.unpack_from("<I", data, pos)
    body = data[pos + 4:pos + 4 + n_morphs * 23]
    ours = {_sjis(name, 15) for name in {OUTFIT, SHARDS, THROW, FALL, BODY} | {k[0] for k in keys}}
    kept = [body[i:i + 23] for i in range(0, len(body), 23) if body[i:i + 15] not in ours]
    records = b"".join(kept) + _morph_records(keys)
    out = data[:pos] + struct.pack("<I", len(kept) + len(keys)) + records + data[pos + 4 + n_morphs * 23:]
    with open(path, "wb") as handle:
        handle.write(out)
    return n_morphs - len(kept)
