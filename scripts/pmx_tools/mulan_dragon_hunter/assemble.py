# Assemble the delivery folder: copy the build PMX (renamed) + its textures, with the recoloured *_mulan.png written
# under the ORIGINAL texture names (the PMX's texture paths stay as they are), and set the model name / comment.
#   python assemble.py <build.pmx> <out dir> <model name>
import os
import shutil
import sys

sys.path.insert(0, r"E:\code\othercode\ripper_tpose\scripts\blender_addons\pmx_head_swap")
import core  # noqa: E402

src, out_dir, name = sys.argv[1], sys.argv[2], sys.argv[3]
pmx = core.oc.pmx_module()
M = pmx.load(src)
os.makedirs(os.path.join(out_dir, "textures"), exist_ok=True)
n_recol = 0
for t in M.textures:
    p = t.path
    base = os.path.basename(p)
    stem, ext = os.path.splitext(base)
    recol = os.path.join(os.path.dirname(p), stem + "_mulan.png")
    dst = os.path.join(out_dir, "textures", base)
    if os.path.isfile(recol):
        shutil.copyfile(recol, dst)
        n_recol += 1
    else:
        shutil.copyfile(p, dst)
    t.path = dst
M.name = M.name_e = name
M.comment = ("仿王者荣耀 花木兰·水晶猎龙者（拼合版）：身体 / 脸 / 盔甲 Rise of Eros Inase a08_outfit1，马尾 Stellar Blade Eve，"
             "双剑 Inase a08；贴图改色。ripper_tpose pmx_outfit_transfer / recolor.py\r\n") + (M.comment or "")
out = os.path.join(out_dir, name + ".pmx")
pmx.save(out, M, add_uv_count=M.header.additional_uvs)
back = pmx.load(out)
missing = [t.path for t in back.textures if not os.path.isfile(t.path)]
print("wrote", out, "| textures", len(back.textures), "recoloured", n_recol, "missing", missing)
