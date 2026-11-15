# Assemble the delivery folder: PMX (renamed) + textures copied next to it, the recoloured *_mulan.png written under
# the ORIGINAL names, texture paths saved relative to the PMX (textures\<name>), model name / comment set.
#   python assemble2.py <build.pmx> <out dir> <model name>
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pmxlib as L  # noqa: E402

src, out_dir, name = sys.argv[1], sys.argv[2], sys.argv[3]
M = L.load(src)
src_dir = os.path.dirname(os.path.abspath(src))
os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
n_recol, missing = 0, []
for t in M.textures:
    p = t.path
    base = os.path.basename(p)
    stem, ext = os.path.splitext(base)
    found = None
    for cand in (p, os.path.join(src_dir, p), os.path.join(src_dir, "textures", base), os.path.join(os.path.dirname(src_dir), p)):
        if os.path.isfile(cand):
            found = cand
            break
    if found is None:
        missing.append(p)
        continue
    recol = os.path.join(os.path.dirname(found), stem + "_mulan.png")
    dst = os.path.join(out_dir, "textures", base)
    if os.path.isfile(recol):
        shutil.copyfile(recol, dst)
        n_recol += 1
    else:
        shutil.copyfile(found, dst)
    t.path = os.path.abspath(dst)      # mmd_tools saves it relative to the PMX (relpath of a relative string = CWD!)
M.name = M.name_e = name
M.comment = ("仿王者荣耀 花木兰·水晶猎龙者 v2（拼合版）：身体 / 脸 Rise of Eros Inase a08（裸体版），翼冠 Inase a08_outfit1，"
             "马尾 Stellar Blade Eve，肩甲 Vindictus Miri (Dragon Rises)，右手龙爪 Vindictus Miul (Devil Hunter)，"
             "左护腕 / 短裤 / 靴子 Vindictus Bel (White Shark)，马甲 Vindictus Sanyaa (Dark Knight)，剑柄 Inase a08，"
             "水晶和剑刃程序生成；贴图改色。ripper_tpose scripts/pmx_tools/mulan_dragon_hunter\r\n") + (M.comment or "")
out = os.path.join(out_dir, name + ".pmx")
L.save(M, out)
back = L.load(os.path.abspath(out))     # the loader turns the saved relative paths absolute
miss2 = [t.path for t in back.textures if not os.path.isfile(t.path)]
print("wrote", out, "| textures", len(back.textures), "recoloured", n_recol, "missing src", missing, "missing out", miss2)
