# Assemble the v11 delivery folder: PMX (renamed) + textures copied next to it, the recoloured *_mulan.png (hair, eyes -
# v2/recolor2.py) written under the ORIGINAL names, texture paths saved relative to the PMX, model name / comment set.
#   python assemble11.py <build.pmx> <out dir> <model name>
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "v2"))
import pmxlib as L  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
src, out_dir, name = sys.argv[1], sys.argv[2], sys.argv[3]
M = L.load(os.path.abspath(src))
src_dir = os.path.dirname(os.path.abspath(src))
os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
n_recol, missing = 0, []
for t in M.textures:
    p = t.path
    base = os.path.basename(p)
    stem, _ext = os.path.splitext(base)
    found = None
    for cand in (p, os.path.join(src_dir, p), os.path.join(src_dir, "textures", base)):
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
    t.path = os.path.abspath(dst)      # mmd_tools saves it relative to the PMX (a relative string would go by the CWD)
M.name = M.name_e = name
M.comment = ("仿王者荣耀 花木兰·水晶猎龙者 v11：照「MS移植第四十四期」（游戏原模型的 HS2 移植）的预览图重新建模。\r\n"
             "身体 / 脸：Rise of Eros Inase a08（裸体版）；马尾：Stellar Blade Eve。\r\n"
             "黑甲、胸甲、腰甲、肩 / 臂 / 腿甲片、护胫：从身体表面按轮廓裁出外推（skinshell.py）；\r\n"
             "头冠、水晶、晶翼、领口、利爪、膝甲、铁靴、裙甲花瓣、背饰、短剑、水晶大剑：程序建模（parts.py）；贴图全部程序生成。\r\n"
             "ripper_tpose scripts/pmx_tools/mulan_dragon_hunter/v3\r\n")
out = os.path.join(out_dir, name + ".pmx")
L.save(M, out)
back = L.load(os.path.abspath(out))     # the loader turns the saved relative paths absolute
miss2 = [t.path for t in back.textures if not os.path.isfile(t.path)]
print("wrote", out, "| textures", len(back.textures), "recoloured", n_recol, "missing src", missing, "missing out", miss2)
