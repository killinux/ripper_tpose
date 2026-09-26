"""把各游戏导出的模型归档到 E:\\game_export，按 ``<游戏>\\<角色>\\<格式>\\<造型>\\`` 存放，并列出 D 盘哪些目录可以删。

  python archive_exports.py --list                 已登记的游戏、各自在 D 盘的来源、有没有归档过
  python archive_exports.py vindictus [--dry-run]  归档一个游戏（可多个；all = 全部已登记的）
  python archive_exports.py --report               不拷贝，只刷新目录清单和 D 盘可删除清单
  python archive_exports.py --relink [game ...]    把画廊页里指向 D 盘的链接改成 E 盘的归档位置

选项
  --dest DIR        归档根目录（默认 E:\\game_export）
  --only NAME ...   只处理这些角色（或造型 id）
  --blender EXE     自检 / 打包 .blend 用的 Blender（默认 3.6.15）
  --no-check        跳过“能否单独打开”的自检
  --workers N       并行拷贝线程数（默认 4）
  --lanes N         并行 Blender 进程数（默认 6）

每个造型目录都要能单独打开：拷完以后逐个自检——.blend 在 Blender 里打开，每张贴图 / 每个外部文件
都必须在这个造型目录里而且存在；.xps / .pmx 解析出贴图名逐个找；VaM 物品查预设里的 Custom/ 引用。
源文件本来就缺的贴图（D 盘上也找不到）只记为提醒，不算归档出错。

.blend 引用了造型目录外的文件时（规则里 package=True），不按字节拷，而是在 Blender 里打开、把外部
文件拷进造型目录（``textures\\``）、改成相对路径另存（blend_package.py）。

只拷不删。每个文件边拷边算 md5，写完再从 E 盘读回来比一次；拷贝前后源文件的大小 / 修改时间变了
（别的窗口正在写）就不记账，下次再拷。账本 ``<游戏>\\_meta\\ledger.json`` 记下 D 盘原文件的
大小 / 修改时间 / md5 和去向；重跑时账本里对得上的文件直接跳过，所以以后同一个游戏又导出了新角色，
再跑一次同样的命令即可。源和目标在同一个盘（E 盘内部整理）时直接移动（规则里 move=True）。

D 盘可删除清单（``<dest>\\D盘可删除清单.md``）每次都现算：D 盘目录里每个文件要么在账本里且大小 /
修改时间没变、E 盘副本还在，要么属于登记过的“可重新生成的中间产物”，整个目录才算可以删。
硬链接（和游戏安装目录共用数据）单独算：删了不腾空间。最近两小时内还有写入的目录会标出来。
"""

import argparse
import datetime
import fnmatch
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import games  # noqa: E402

DEFAULT_DEST = r"E:\game_export"
DEFAULT_BLENDER = r"D:\Program Files\blender-3.6.15-windows-x64\blender.exe"
CLEANUP_NAME = "D盘可删除清单.md"
CHUNK = 8 << 20
BUSY_SECONDS = 2 * 3600


def now():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def norm(path):
    return os.path.normcase(os.path.normpath(path))


def inside(path, root):
    p, r = norm(path), norm(root)
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def gb(n):
    return "%.2f GB" % (n / 1e9) if n >= 1e8 else "%.0f MB" % (n / 1e6)


def walk_files(root):
    """root 下的全部文件（递归）；root 本身是文件就只有它。"""
    if os.path.isfile(root):
        yield root
        return
    for dirpath, _dirs, files in os.walk(root):
        for f in files:
            yield os.path.join(dirpath, f)


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default


def save_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    os.replace(tmp, path)


# ---------------------------------------------------------------------------------------- copy + ledger

class Changed(Exception):
    """源文件在拷贝过程中被改了（别的程序正在写）。"""


def md5_file(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                return h.hexdigest()
            h.update(b)


def copy_verified(src, dst):
    """拷一个文件：边读边算 md5，写到 .part 再改名，最后从目标读回来再算一次。返回 (md5, 拷贝前的 stat)。"""
    st0 = os.stat(src)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    part = dst + ".part"
    h = hashlib.md5()
    n = 0
    with open(src, "rb") as fi, open(part, "wb") as fo:
        while True:
            b = fi.read(CHUNK)
            if not b:
                break
            h.update(b)
            fo.write(b)
            n += len(b)
    st1 = os.stat(src)
    if n != st0.st_size or st1.st_size != st0.st_size or st1.st_mtime != st0.st_mtime:
        os.remove(part)
        raise Changed(src)
    digest = h.hexdigest()
    shutil.copystat(src, part)
    os.replace(part, dst)
    if md5_file(dst) != digest:
        raise IOError("md5 mismatch after copy: %s" % dst)
    return digest, st0


def plan_files(item):
    """(源文件, 目标相对路径) 列表。item 是 games.Product 或 games.Meta。"""
    pairs = []
    for src_rel, dst_rel in item.pairs():
        src = os.path.join(item.src, src_rel) if src_rel else item.src
        if not os.path.exists(src):
            continue
        if os.path.isfile(src):
            pairs.append((src, dst_rel))
            continue
        for f in walk_files(src):
            rel = os.path.relpath(f, src)
            if item.skip(os.path.join(src_rel, rel) if src_rel else rel):
                continue
            pairs.append((f, os.path.join(dst_rel, rel) if dst_rel else rel))
    return pairs


class Ledger:
    """<游戏>\\_meta\\ledger.json：D 盘源文件 -> 大小 / 修改时间 / md5 / E 盘位置。"""

    def __init__(self, game_dir):
        self.game_dir = game_dir
        self.path = os.path.join(game_dir, "_meta", "ledger.json")
        data = load_json(self.path, {"files": {}})
        self.files = {norm(k): v for k, v in data["files"].items()}

    def fresh(self, src):
        """源文件在账本里、大小和修改时间都没变、E 盘那份还在。"""
        e = self.files.get(norm(src))
        if not e:
            return False
        try:
            st = os.stat(src)
        except OSError:
            return False
        return (e["size"] == st.st_size and abs(e["mtime"] - st.st_mtime) < 1e-3
                and os.path.exists(os.path.join(self.game_dir, e["dest"])))

    def record(self, src, dest_rel, digest, st, how="copy"):
        self.files[norm(src)] = {"src": src, "dest": dest_rel, "size": st.st_size, "mtime": st.st_mtime,
                                 "md5": digest, "how": how, "archived": now()}

    def save(self):
        save_json(self.path, {"files": {e["src"]: e for e in sorted(self.files.values(), key=lambda e: e["src"])}})


# ---------------------------------------------------------------------------------------- self-contained checks

def xps_textures(path):
    """.xps 里的贴图名。

    XPS 的字符串 = 7-bit 变长长度前缀 + UTF-8 字节。从图片扩展名往前找：候选串里不能有控制字符，
    前缀字节要等于长度；取满足条件的最长那个（长度 >= 32 时前缀本身是可打印字符，最短匹配可能落在名字中间）。
    """
    with open(path, "rb") as f:
        data = f.read()
    names = set()
    pat = re.compile(rb"\.(png|dds|tga|jpg|jpeg|bmp|tif|tiff)(?![A-Za-z0-9])", re.I)
    for m in pat.finditer(data):
        end, best = m.end(), None
        for length in range(m.end() - m.start() + 1, 256):
            start = end - length
            if start < 2 or data[start] < 0x20 or data[start] == 0x7F:
                break
            if length < 128:
                ok = data[start - 1] == length
            else:
                ok = data[start - 2] == (length & 0x7F) | 0x80 and data[start - 1] == length >> 7
            if ok:
                best = start
        if best is not None:
            try:
                names.add(data[best:end].decode("utf-8"))
            except UnicodeDecodeError:
                pass
    return sorted(names)


def pmx_textures(path):
    """.pmx 贴图表（相对 .pmx 所在目录的路径）。"""
    import struct
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"PMX ":
        raise ValueError("not a PMX file")
    n = data[8]
    g = data[9:9 + n]
    enc = "utf-16-le" if g[0] == 0 else "utf-8"
    add_uv, vsz, bsz = g[1], g[2], g[5]
    pos = 9 + n

    def text():
        nonlocal pos
        (ln,) = struct.unpack_from("<i", data, pos)
        s = data[pos + 4:pos + 4 + ln].decode(enc, "replace")
        pos += 4 + ln
        return s

    for _ in range(4):
        text()
    (nv,) = struct.unpack_from("<i", data, pos)
    pos += 4
    weight_len = {0: bsz, 1: 2 * bsz + 4, 2: 4 * bsz + 16, 3: 2 * bsz + 4 + 36, 4: 4 * bsz + 16}
    for _ in range(nv):
        pos += 32 + 16 * add_uv
        kind = data[pos]
        pos += 1 + weight_len[kind] + 4
    (nf,) = struct.unpack_from("<i", data, pos)
    pos += 4 + nf * vsz
    (nt,) = struct.unpack_from("<i", data, pos)
    pos += 4
    return [text() for _ in range(nt)]


def vam_references(root):
    """VaM 物品目录里 .vap/.vam/.vaj/.vmi/.json 引用的 Custom/... 路径。"""
    refs = set()
    pat = re.compile(r'"((?:SELF:/)?Custom/[^"]+)"')
    for f in walk_files(root):
        if f.lower().endswith((".vap", ".vam", ".vaj", ".vmi", ".json")):
            text = open(f, encoding="utf-8", errors="replace").read()
            for m in pat.finditer(text):
                refs.add(m.group(1).replace("SELF:/", ""))
    return sorted(refs)


def run_blender_lanes(script, jobs, blender, lanes, tag):
    """jobs 分成 lanes 份，每份一个 Blender 进程跑 script，合并各自写出的 JSON 结果。"""
    if not jobs:
        return {}
    lanes = max(1, min(lanes, len(jobs)))
    result = {}
    with tempfile.TemporaryDirectory() as tmp:
        procs = []
        for i in range(lanes):
            part = jobs[i::lanes]
            lst, out = os.path.join(tmp, "%s%d.json" % (tag, i)), os.path.join(tmp, "%s%d.out.json" % (tag, i))
            save_json(lst, part)
            log = open(os.path.join(tmp, "%s%d.log" % (tag, i)), "w", encoding="utf-8", errors="replace")
            cmd = [blender, "-b", "--factory-startup", "--python", os.path.join(HERE, script), "--", lst, out]
            procs.append((subprocess.Popen(cmd, stdout=log, stderr=subprocess.STDOUT), out, log))
        for proc, out, log in procs:
            proc.wait()
            log.close()
            result.update(load_json(out, {}))
        if len(result) < len(jobs):
            tails = []
            for i in range(lanes):
                with open(os.path.join(tmp, "%s%d.log" % (tag, i)), encoding="utf-8", errors="replace") as f:
                    tails.append(f.read()[-1500:])
            print("   !! %s: %d of %d results; log tails:\n%s" % (script, len(result), len(jobs), "\n".join(tails)))
    return result


def self_check(product_dir, fmt, main, product_src, blend_refs, source_of=None):
    """返回 (问题, 提醒)。问题 = 这个造型目录不能单独打开；提醒 = 源文件本来就缺的东西。

    source_of(E 盘文件) -> 它在 D 盘的来源（账本反查）。缺的文件按“引用它的文件在 D 盘的位置”换算回
    D 盘再看一次：D 盘上也没有 = 源文件本来就缺（提醒）；D 盘上有 = 归档漏拷了（问题）。
    """
    problems, warnings = [], []
    main_path = os.path.join(product_dir, main) if main else None
    if main_path and not os.path.isfile(main_path):
        return ["主文件不存在: %s" % main], []

    def was_missing_in_source(p, owner=None):
        src_owner = source_of(owner) if (source_of and owner) else None
        if src_owner:
            p = os.path.normpath(os.path.join(os.path.dirname(src_owner), os.path.relpath(p, os.path.dirname(owner))))
        elif product_src and inside(p, product_dir):
            p = os.path.join(product_src, os.path.relpath(p, product_dir))
        return not os.path.exists(p)

    if fmt == "blend" or any(f.lower().endswith(".blend") for f in walk_files(product_dir)):
        for blend in [f for f in walk_files(product_dir) if f.lower().endswith(".blend")]:
            refs = blend_refs.get(blend)
            if refs is None:
                problems.append("没有自检结果: %s" % os.path.relpath(blend, product_dir))
                continue
            for p, exists, _packed in refs:
                if p.startswith("<open failed"):
                    problems.append("%s 打不开: %s" % (os.path.basename(blend), p))
                elif not exists:
                    (warnings if was_missing_in_source(p, blend) else problems).append(
                        "%s 缺文件: %s" % (os.path.basename(blend), p))
                elif not inside(p, product_dir):
                    problems.append("%s 引用了目录外的文件: %s" % (os.path.basename(blend), p))
    if fmt in ("xps", "pmx"):
        exts = (".xps", ".mesh") if fmt == "xps" else (".pmx",)
        for model in [f for f in walk_files(product_dir) if f.lower().endswith(exts)]:
            base = os.path.dirname(model)
            try:
                names = pmx_textures(model) if fmt == "pmx" else xps_textures(model)
            except Exception as exc:  # noqa: BLE001
                problems.append("%s 解析失败: %s" % (os.path.basename(model), exc))
                continue
            for n in names:
                p = os.path.normpath(os.path.join(base, n.replace("\\", os.sep)))
                if not os.path.isfile(p):
                    (warnings if was_missing_in_source(p, model) else problems).append(
                        "%s 缺贴图: %s" % (os.path.basename(model), n))
                elif not inside(p, product_dir):
                    problems.append("%s 贴图在目录外: %s" % (os.path.basename(model), n))
    if fmt == "vam":
        for ref in vam_references(product_dir):
            if not os.path.isfile(os.path.join(product_dir, ref.replace("/", os.sep))):
                problems.append("VaM 引用缺文件: %s" % ref)
    return problems, warnings


# ---------------------------------------------------------------------------------------- archive one game

def move_item(src, dst):
    """同盘移动：目标不存在就整个改名，否则逐个文件改名后删掉空目录。"""
    if not os.path.exists(dst):
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        os.replace(src, dst)
        return
    for f in list(walk_files(src)):
        t = os.path.join(dst, os.path.relpath(f, src))
        os.makedirs(os.path.dirname(t), exist_ok=True)
        os.replace(f, t)
    for dirpath, _dirs, _files in sorted(os.walk(src), key=lambda x: -len(x[0])):
        try:
            os.rmdir(dirpath)
        except OSError:
            pass


def package_blends(jobs, game_dir, ledger, blender, lanes):
    """jobs 交给 blend_package.py；核对它拷的每个文件（md5）并记账。返回 {目标 .blend: [问题]}。"""
    print("   packaging %d .blend in Blender (%d lanes) ..." % (len(jobs), lanes), flush=True)
    stats = {j["src"]: os.stat(j["src"]) for j in jobs}
    res = run_blender_lanes("blend_package.py", jobs, blender, lanes, "pkg")
    out = {}
    for j in jobs:
        r = res.get(j["dest"])
        if r is None:
            out[j["dest"]] = ["打包没有结果"]
            continue
        problems = list(r.get("problems", []))
        for src_file, dst_file in r.get("copied", []):
            try:
                st = os.stat(src_file)
                digest = md5_file(src_file)
                if md5_file(dst_file) != digest:
                    problems.append("拷贝后 md5 不一致: %s" % dst_file)
                    continue
            except OSError as exc:
                problems.append("拷贝核对失败: %s (%s)" % (dst_file, exc))
                continue
            if inside(dst_file, game_dir):
                ledger.record(src_file, os.path.relpath(dst_file, game_dir), digest, st)
        st1 = os.stat(j["src"])
        if st1.st_size != stats[j["src"]].st_size or st1.st_mtime != stats[j["src"]].st_mtime:
            problems.append("打包过程中源 .blend 被改了，下次再跑")
        elif not problems:
            ledger.record(j["src"], j["dest_rel"], md5_file(j["src"]), st1, how="package")
        out[j["dest"]] = problems
    ledger.save()
    bad = sum(1 for v in out.values() if v)
    print("   packaged: %d OK, %d with problems" % (len(jobs) - bad, bad), flush=True)
    return out


def needs_package(blend, refs, pdir, d_blend):
    """E 盘这份 .blend 还引用着造型目录外的文件，或者缺的文件在 D 盘上其实有 -> 应该改用打包。"""
    for p, exists, _packed in refs:
        if p.startswith("<open failed"):
            return False
        if exists and not inside(p, pdir):
            return True
        if not exists:
            try:
                d_equiv = os.path.normpath(os.path.join(os.path.dirname(d_blend),
                                                        os.path.relpath(p, os.path.dirname(blend))))
            except ValueError:
                continue
            if os.path.exists(d_equiv):
                return True
    return False


def archive_game(game, dest, only, workers, blender, lanes, check, dry_run, recheck=False):
    game_dir = os.path.join(dest, game.folder)
    products, metas = game.collect()
    if only:
        wanted = {o.lower() for o in only}
        products = [p for p in products if p.character.lower() in wanted or p.model.lower() in wanted]
        metas = []
    print("== %s: %d products, %d meta items" % (game.folder, len(products), len(metas)), flush=True)
    ledger = Ledger(game_dir)
    moves_path = os.path.join(game_dir, "_meta", "moves.json")
    moves = load_json(moves_path, {})
    dirmap_path = os.path.join(game_dir, "_meta", "dirmap.json")
    dirmap = load_json(dirmap_path, {})
    jobs, pkg_jobs, skipped, total_bytes, to_move = [], [], 0, 0, []
    for item in products + metas:
        if getattr(item, "move", False):
            to_move.append(item)
            continue
        base_rel = item.dest_rel()
        for src, rel in plan_files(item):
            dest_rel = os.path.join(base_rel, rel) if rel else base_rel
            if getattr(item, "package", False) and src.lower().endswith(".blend"):
                if not ledger.fresh(src):
                    pkg_jobs.append({"src": src, "dest": os.path.join(game_dir, dest_rel),
                                     "product_src": item.src, "product_dest": os.path.join(game_dir, base_rel),
                                     "dest_rel": dest_rel})
                else:
                    skipped += 1
                continue
            if ledger.fresh(src):
                skipped += 1
                continue
            size = os.path.getsize(src)
            total_bytes += size
            jobs.append((src, os.path.join(game_dir, dest_rel), dest_rel, size))
        if isinstance(item, games.Product) and item.include is None or isinstance(item, games.Meta):
            dirmap[item.src] = base_rel
    print("   to copy: %d files, %s (unchanged, skipped: %d); to package: %d .blend; to move: %d dirs"
          % (len(jobs), gb(total_bytes), skipped, len(pkg_jobs), len(to_move)), flush=True)
    if dry_run:
        for p in products:
            how = "move" if p.move else ("package" if p.package else "copy")
            print("   %-16s %-6s %-40s %-7s <- %s" % (p.character, p.fmt, p.model, how, p.src))
        for m in metas:
            print("   %-16s %-6s %-40s %-7s <- %s" % ("_meta", "", m.name, "move" if m.move else "copy", m.src))
        return
    free = shutil.disk_usage(os.path.splitdrive(dest)[0] + os.sep).free
    if total_bytes > free - (5 << 30):
        raise SystemExit("not enough space on %s: need %s, free %s" % (dest, gb(total_bytes), gb(free)))

    for item in to_move:
        target = os.path.join(game_dir, item.dest_rel())
        if os.path.exists(item.src):
            move_item(item.src, target)
            moves[item.src] = item.dest_rel()
    if to_move:
        save_json(moves_path, moves)

    changed, done_bytes = [], 0

    def run(job):
        src, dst, dest_rel, size = job
        try:
            digest, st = copy_verified(src, dst)
        except Changed:
            return src, dest_rel, None, None, size
        return src, dest_rel, digest, st, size

    with ThreadPoolExecutor(max(1, workers)) as ex:
        for i, (src, dest_rel, digest, st, size) in enumerate(ex.map(run, jobs), 1):
            if digest is None:
                changed.append(src)
            else:
                ledger.record(src, dest_rel, digest, st)
            done_bytes += size
            if i % 500 == 0 or i == len(jobs):
                print("   copied %d/%d (%s)" % (i, len(jobs), gb(done_bytes)), flush=True)
                ledger.save()
    ledger.save()
    save_json(dirmap_path, dirmap)
    if changed:
        print("   !! %d files changed while copying (someone is writing them) - not recorded, rerun later:" % len(changed))
        for c in changed[:10]:
            print("      " + c)

    pkg_problems = package_blends(pkg_jobs, game_dir, ledger, blender, lanes) if pkg_jobs else {}

    # 造型信息（说明 / 预览 / 自检结果）合并进 _meta\models.json：以后 D 盘删了也还在
    models_path = os.path.join(game_dir, "_meta", "models.json")
    models = load_json(models_path, {})
    items = []   # (key, 造型目录, 格式, 主文件, D 盘来源目录或 None)
    for p in products:
        key = "%s/%s/%s" % (p.character, p.fmt, p.model)
        entry = models.get(key, {})
        entry.update({"character": p.character, "fmt": p.fmt, "model": p.model, "source": p.src, "archived": now()})
        for field, value in (("desc", p.desc), ("main", p.main), ("preview", p.preview)):
            if value or field not in entry:        # 清单没了（D 盘删过）时别把原来的说明冲掉
                entry[field] = value
        models[key] = entry
        items.append((key, os.path.join(game_dir, p.dest_rel()), p.fmt, p.main, None if p.move else p.src))
    if recheck:        # 连 D 盘上已经删掉、这次没收集到的造型也重新自检（只看 E 盘）
        seen = {it[0] for it in items}
        for key, m in models.items():
            if key not in seen:
                src = m.get("source")
                items.append((key, os.path.join(game_dir, m["character"], m["fmt"], m["model"]), m["fmt"],
                              m.get("main"), src if src and os.path.exists(src) and not inside(src, dest) else None))
    blend_refs = {}
    if check:
        blends = []
        for _key, pdir, _fmt, _main, _src in items:
            blends += [f for f in walk_files(pdir) if f.lower().endswith(".blend")]
        print("   self-check: %d .blend in Blender (%d lanes) ..." % (len(blends), lanes), flush=True)
        blend_refs = run_blender_lanes("blend_selfcheck.py", blends, blender, lanes, "chk")
    src_by_dest = {norm(os.path.join(game_dir, e["dest"])): e["src"] for e in ledger.files.values()}

    def source_of(dest_file):
        return src_by_dest.get(norm(dest_file))

    if check:
        # 按字节拷过来、却还引用着造型目录外（D 盘上确实存在）文件的 .blend：改成打包，再查一次
        fix_jobs = []
        for key, pdir, fmt, main, src in items:
            if not src or not os.path.isdir(pdir):
                continue
            for blend in [f for f in walk_files(pdir) if f.lower().endswith(".blend")]:
                d_blend = source_of(blend)
                e = ledger.files.get(norm(d_blend)) if d_blend else None
                if not e or e.get("how", "copy") != "copy" or not os.path.exists(d_blend):
                    continue
                if needs_package(blend, blend_refs.get(blend, []), pdir, d_blend):
                    fix_jobs.append({"src": d_blend, "dest": blend, "product_src": src, "product_dest": pdir,
                                     "dest_rel": os.path.relpath(blend, game_dir)})
        if fix_jobs:
            print("   %d copied .blend still point outside their folder -> packaging them" % len(fix_jobs), flush=True)
            pkg_problems.update(package_blends(fix_jobs, game_dir, ledger, blender, lanes))
            blend_refs.update(run_blender_lanes("blend_selfcheck.py", [j["dest"] for j in fix_jobs], blender, lanes,
                                                "chk2"))
            src_by_dest = {norm(os.path.join(game_dir, e["dest"])): e["src"] for e in ledger.files.values()}

    bad = 0
    if check:
        for key, pdir, fmt, main, src in items:
            if os.path.isdir(pdir):
                problems, warnings = self_check(pdir, fmt, main, src, blend_refs, source_of)
            else:
                problems, warnings = ["造型目录不见了: %s" % pdir], []
            for d, ps in pkg_problems.items():
                if inside(d, pdir):
                    problems += ps
            entry = models[key]
            entry["selfContained"] = not problems
            entry["problems"] = problems[:20]
            entry["warnings"] = warnings[:20]
            entry["checked"] = now()
            if problems:
                bad += 1
                print("   !! %s: %d problems, e.g. %s" % (key, len(problems), problems[0]))
    save_json(models_path, dict(sorted(models.items())))
    print("   self-check: %s" % ("skipped" if not check else "%d/%d OK" % (len(items) - bad, len(items))),
          flush=True)


# ---------------------------------------------------------------------------------------- catalog + README

def dir_stats(path):
    files = list(walk_files(path))
    return len(files), sum(os.path.getsize(f) for f in files)


def scan_catalog(dest):
    """从 E 盘现有内容 + 各游戏 _meta\\models.json 生成目录。"""
    catalog = {"updated": now(), "root": dest, "games": {}}
    for game in games.GAMES.values():
        game_dir = os.path.join(dest, game.folder)
        models = load_json(os.path.join(game_dir, "_meta", "models.json"), {})
        if not models:
            continue
        chars = {}
        for key, m in sorted(models.items()):
            pdir = os.path.join(game_dir, m["character"], m["fmt"], m["model"])
            if not os.path.isdir(pdir):
                continue
            nfiles, size = dir_stats(pdir)
            c = chars.setdefault(m["character"], {"models": {}})
            e = c["models"].setdefault(m["model"], {"desc": m.get("desc", ""), "formats": {}})
            if m.get("desc") and not e["desc"]:
                e["desc"] = m["desc"]
            e["formats"][m["fmt"]] = {
                "dir": os.path.relpath(pdir, dest), "main": m.get("main"), "preview": m.get("preview"),
                "files": nfiles, "bytes": size, "archived": m.get("archived"),
                "selfContained": m.get("selfContained"), "problems": m.get("problems", []),
                "warnings": m.get("warnings", [])}
        catalog["games"][game.folder] = {"key": game.key, "title": game.title,
                                         "characters": dict(sorted(chars.items(), key=lambda kv: kv[0].lower())),
                                         "characterNames": game.character_names}
    return catalog


def fmt_counts(chars):
    counts = {}
    for c in chars.values():
        for m in c["models"].values():
            for f in m["formats"]:
                counts[f] = counts.get(f, 0) + 1
    return counts


def link(path):
    return "<%s>" % path.replace("\\", "/")


def write_readmes(dest, catalog):
    lines = ["# 游戏模型归档", "",
             "按 `<游戏>\\<角色>\\<格式>\\<造型>\\` 存放。每个造型目录都能单独打开（贴图打包在 .blend 里，"
             "或者就在目录里、路径是相对的），整个目录拷到别处也一样。",
             "", "本页和 `catalog.json`、各游戏的 `README.md` 都由 `scripts\\archive\\archive_exports.py` 生成，"
             "别手改；D 盘哪些目录已经可以删见 [%s](%s)。" % (CLEANUP_NAME, link(CLEANUP_NAME)), "",
             "更新于 %s" % catalog["updated"], "",
             "| 游戏 | 角色 | 造型 | 格式 | 大小 |", "|---|---|---|---|---|"]
    total = 0
    for folder, g in catalog["games"].items():
        chars = g["characters"]
        n_models = sum(len(c["models"]) for c in chars.values())
        size = sum(f["bytes"] for c in chars.values() for m in c["models"].values() for f in m["formats"].values())
        total += size
        counts = " · ".join("%s %d" % kv for kv in sorted(fmt_counts(chars).items()))
        lines.append("| [%s](%s) | %d | %d | %s | %s |" % (folder, link(folder + "/README.md"), len(chars), n_models,
                                                         counts, gb(size)))
    lines += ["", "合计 %s。" % gb(total), ""]
    for folder, g in catalog["games"].items():
        lines += ["## %s" % folder, "", g["title"], "", "| 角色 | 造型 | 格式 |", "|---|---|---|"]
        for cname, c in g["characters"].items():
            label = g["characterNames"].get(cname, "")
            counts = " · ".join("%s %d" % kv for kv in sorted(fmt_counts({cname: c}).items()))
            lines.append("| %s%s | %d | %s |" % (cname, "（%s）" % label if label else "", len(c["models"]), counts))
        lines.append("")
    extra = [d for d in sorted(os.listdir(dest)) if os.path.isdir(os.path.join(dest, d))
             and d not in catalog["games"] and not d.startswith((".", "_"))]
    if extra:
        lines += ["## 还没按这个结构整理的目录", ""]
        lines += ["- `%s\\`" % d for d in extra]
        lines.append("")
    write_text(os.path.join(dest, "README.md"), "\n".join(lines))
    save_json(os.path.join(dest, "catalog.json"), catalog)

    for folder, g in catalog["games"].items():
        out = ["# %s" % g["title"], "",
               "目录结构 `<角色>\\<格式>\\<造型>\\`，每个造型目录可以单独打开。由 `scripts\\archive\\archive_exports.py %s` "
               "生成。" % g["key"], ""]
        for cname, c in g["characters"].items():
            label = g["characterNames"].get(cname, "")
            fmts = sorted({f for m in c["models"].values() for f in m["formats"]})
            out += ["## %s%s" % (cname, " · %s" % label if label else ""), "",
                    "| 造型 | 说明 | %s | 预览 |" % " | ".join(fmts), "|---|---|%s---|" % ("---|" * len(fmts))]
            for mid, m in sorted(c["models"].items(), key=lambda kv: kv[0].lower()):
                cells, preview = [], ""
                for f in fmts:
                    e = m["formats"].get(f)
                    if not e:
                        cells.append("")
                        continue
                    rel = os.path.relpath(os.path.join(dest, e["dir"]), os.path.join(dest, folder))
                    target = os.path.join(rel, e["main"]) if e["main"] else rel
                    mark = "" if e["selfContained"] is not False else " ⚠"
                    cells.append("[%s](%s) %s%s" % (os.path.basename(e["main"] or f), link(target), gb(e["bytes"]), mark))
                    if e.get("preview") and not preview:
                        preview = "[看图](%s)" % link(os.path.join(rel, e["preview"]))
                out.append("| %s | %s | %s | %s |" % (mid, m["desc"].replace("|", "/").replace("\n", " "),
                                                      " | ".join(cells), preview))
            out.append("")
        problems = [(cname, mid, f, e["problems"]) for cname, c in g["characters"].items()
                    for mid, m in c["models"].items() for f, e in m["formats"].items() if e["problems"]]
        if problems:
            out += ["## 自检没过的（⚠）", ""]
            for cname, mid, f, ps in problems:
                out.append("- %s / %s / %s：%s" % (cname, f, mid, "；".join(ps[:3])))
            out.append("")
        warned = [(cname, mid, f, e["warnings"]) for cname, c in g["characters"].items()
                  for mid, m in c["models"].items() for f, e in m["formats"].items() if e.get("warnings")]
        if warned:
            out += ["## 源文件本来就缺的东西（D 盘上也没有，不是归档弄丢的）", ""]
            for cname, mid, f, ws in warned:
                out.append("- %s / %s / %s：%s" % (cname, f, mid, "；".join(ws[:3]) + (" …" if len(ws) > 3 else "")))
            out.append("")
        write_text(os.path.join(dest, folder, "README.md"), "\n".join(out))


# ---------------------------------------------------------------------------------------- cleanup report

def file_state(path):
    """(大小, 删掉能腾出的大小)：大文件查一下硬链接数，和别处共用数据的删了不腾空间。"""
    st = os.stat(path)
    freed = st.st_size
    if st.st_size >= (16 << 20) and st.st_nlink > 1:
        freed = 0
    return st.st_size, freed, st.st_mtime


class Regen:
    """可重新生成的路径表：普通路径按前缀匹配，带 * ? [ 的按通配符匹配（本身或它下面的文件）。"""

    def __init__(self, entries):
        self.plain, self.globs = [], []
        for p, why in entries:
            n = norm(p)
            if any(c in n for c in "*?["):
                self.globs.append((re.compile(fnmatch.translate(n)), re.compile(fnmatch.translate(n + os.sep + "*")),
                                   why))
            else:
                self.plain.append((n, why))

    def reason(self, path):
        n = norm(path)
        for p, why in self.plain:
            if n == p or n.startswith(p + os.sep):
                return why
        for exact, under, why in self.globs:
            if exact.match(n) or under.match(n):
                return why
        if n.endswith(".blend1"):
            return "*.blend1 = Blender 自动备份"
        return None


class AllLedgers:
    """所有游戏的账本合在一起查（一个 D 盘目录里的东西可能归到了不同游戏）。"""

    def __init__(self, dest):
        self.files = {}
        for game in games.GAMES.values():
            game_dir = os.path.join(dest, game.folder)
            for k, e in Ledger(game_dir).files.items():
                self.files[k] = (game_dir, e)

    def fresh(self, src):
        hit = self.files.get(norm(src))
        if not hit:
            return False
        game_dir, e = hit
        try:
            st = os.stat(src)
        except OSError:
            return False
        return (e["size"] == st.st_size and abs(e["mtime"] - st.st_mtime) < 1e-3
                and os.path.exists(os.path.join(game_dir, e["dest"])))


def cleanup_report(dest):
    """D 盘来源目录逐个文件核对，列出可以整个删的最大目录。"""
    sections = {"ok": [], "partial": [], "todo": []}
    covered_roots = {}   # norm -> 原样路径
    t_now = time.time()
    ledger = AllLedgers(dest)
    for game in games.GAMES.values():
        game_dir = os.path.join(dest, game.folder)
        if not os.path.isfile(os.path.join(game_dir, "_meta", "ledger.json")) and \
                not os.path.isfile(os.path.join(game_dir, "_meta", "moves.json")):
            continue
        regen = Regen(game.regen())
        for root in game.sources:
            covered_roots[norm(root)] = root
            if not os.path.exists(root) or inside(root, dest):
                continue
            state = {}   # 目录 -> [全部可删?, 大小, 文件数, 原样路径, 能腾出]
            pending, reasons, newest = [], set(), 0.0
            for f in walk_files(root):
                try:
                    size, freed, mtime = file_state(f)
                except OSError:
                    continue
                newest = max(newest, mtime)
                why = regen.reason(f)
                ok = why is not None or ledger.fresh(f)
                if why:
                    reasons.add(why)
                if not ok:
                    pending.append(f)
                d = os.path.dirname(f)
                while True:
                    s = state.setdefault(norm(d), [True, 0, 0, d, 0])
                    s[0] = s[0] and ok
                    s[1] += size
                    s[2] += 1
                    s[4] += freed
                    if norm(d) == norm(root) or len(d) <= 3:
                        break
                    d = os.path.dirname(d)
            if not state:
                continue
            top = state[norm(root)]
            busy = t_now - newest < BUSY_SECONDS
            notes = sorted(reasons) + (list(game.notes) if norm(root) == norm(game.sources[0]) else [])
            if busy:
                notes.insert(0, "**%d 分钟前还有写入，可能有别的窗口在用，确认没人用了再删**" % ((t_now - newest) / 60))
            if top[0]:
                sections["ok"].append((root, top[1], top[4], top[2], game, notes))
                continue
            subs = []
            for key, (ok, size, count, path, freed) in sorted(state.items()):
                if not ok or key == norm(root):
                    continue
                parent = norm(os.path.dirname(path))
                if parent in state and state[parent][0]:
                    continue
                subs.append((path, size, freed))
            sections["partial"].append((root, top[1], top[4], top[2], game, subs, pending, notes))
    for d in games.KNOWN_EXPORT_DIRS:
        if norm(d) in covered_roots or not os.path.exists(d):
            continue
        inner = [r for r in covered_roots if r.startswith(norm(d) + os.sep)]
        size = freed = count = 0
        for f in walk_files(d):
            if any(norm(f).startswith(r + os.sep) for r in inner):
                continue
            try:
                s, fr, _m = file_state(f)
            except OSError:
                continue
            size += s
            freed += fr
            count += 1
        note = "（不含已登记的 %s）" % "、".join(os.path.basename(covered_roots[r]) for r in inner) if inner else ""
        sections["todo"].append((d, note, size, freed, count))

    lines = ["# D 盘可删除清单", "",
             "生成于 %s，由 `scripts\\archive\\archive_exports.py` 现算。删之前想再确认一遍就跑 "
             "`python scripts\\archive\\archive_exports.py --report` 刷新本页。" % now(), "",
             "判定：目录里**每个文件**要么已经拷到 `%s` 并按 md5 校验过、而且之后 D 盘这份没再改过，"
             "要么是登记过的中间产物（原始解包、探测输出、.blend1 备份），可以用仓库脚本重新生成。" % dest, "",
             "「能腾出」扣掉了硬链接：和游戏安装目录共用数据的文件删了不省空间。", ""]
    total = sum(r[2] for r in sections["ok"])
    lines += ["## 可以整个删除（能腾出约 %s）" % gb(total), ""]
    if sections["ok"]:
        lines += ["| D 盘目录 | 大小 | 能腾出 | 文件 | 归档到 | 备注 |", "|---|---|---|---|---|---|"]
        for root, size, freed, count, game, notes in sections["ok"]:
            lines.append("| `%s` | %s | %s | %d | `%s` | %s |" % (
                root, gb(size), gb(freed), count, os.path.join(dest, game.folder),
                "；".join(notes) if notes else "全部已归档"))
    else:
        lines.append("（暂无）")
    lines.append("")
    if sections["partial"]:
        lines += ["## 部分归档（还不能整个删）", ""]
        for root, size, freed, count, game, subs, pending, notes in sections["partial"]:
            lines += ["### `%s`（%s，%d 个文件；%d 个还没归档）" % (root, gb(size), count, len(pending)), ""]
            if notes:
                lines += ["- " + n for n in notes]
                lines.append("")
            if subs:
                lines += ["其中可以整个删的子目录（能腾出合计 %s）：" % gb(sum(s[2] for s in subs)), ""]
                lines += ["- `%s`（%s）" % (p, gb(s)) for p, s, fr in subs[:60]]
                if len(subs) > 60:
                    lines.append("- ……还有 %d 个" % (len(subs) - 60))
                lines.append("")
            lines += ["还没归档的文件（前 20 个）：", ""]
            lines += ["- `%s`" % p for p in pending[:20]]
            lines.append("")
    if sections["todo"]:
        lines += ["## 还没处理的导出目录", "", "| D 盘目录 | 大小 | 能腾出 | 文件 |", "|---|---|---|---|"]
        for d, note, size, freed, count in sorted(sections["todo"], key=lambda r: -r[2]):
            lines.append("| `%s`%s | %s | %s | %d |" % (d, note, gb(size), gb(freed), count))
        lines.append("")
    write_text(os.path.join(dest, CLEANUP_NAME), "\n".join(lines))
    return sections


# ---------------------------------------------------------------------------------------- gallery relink

PATH_RE = re.compile(r"(file:///)?([A-Za-z]):([\\/])([^\"'<>|\r\n\t]*)")
KEEP_RE = re.compile(r"(<pre\b.*?</pre>|<code\b.*?</code>)", re.S | re.I)


def build_resolver(dest):
    files, dirs, roots = {}, [], {}
    for game in games.GAMES.values():
        game_dir = os.path.join(dest, game.folder)
        ledger = Ledger(game_dir)
        for e in ledger.files.values():
            files[norm(e["src"])] = os.path.join(game_dir, e["dest"])
        for src, rel in load_json(os.path.join(game_dir, "_meta", "dirmap.json"), {}).items():
            dirs.append((norm(src), os.path.join(game_dir, rel)))
        for src, rel in load_json(os.path.join(game_dir, "_meta", "moves.json"), {}).items():
            dirs.append((norm(src), os.path.join(game_dir, rel)))
        for src, target in game.aliases(game_dir).items():
            files[norm(src)] = target
            dirs.append((norm(src), target))
        # 造型的源目录 -> 造型目录（只对一个源目录只出一个造型的；共用目录的靠账本里的逐个文件）
        models = load_json(os.path.join(game_dir, "_meta", "models.json"), {})
        by_src = {}
        for m in models.values():
            if m.get("source"):
                by_src.setdefault(norm(m["source"]), []).append(m)
        for src, ms in by_src.items():
            if len({(m["character"], m["fmt"], m["model"]) for m in ms}) == 1:
                m = ms[0]
                dirs.append((src, os.path.join(game_dir, m["character"], m["fmt"], m["model"])))
        for root in game.sources:
            roots[norm(root)] = game_dir
    dirs.sort(key=lambda d: -len(d[0]))

    def resolve(path):
        n = norm(path)
        if n in files:
            return files[n]
        for d, target in dirs:
            if n == d:
                return target
            if n.startswith(d + os.sep):
                return os.path.join(target, os.path.normpath(path)[len(d) + 1:])
        return roots.get(n)
    return resolve


def read_raw(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_raw(path, text):
    """原样写回（不改换行符）。"""
    tmp = path + ".part"
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    os.replace(tmp, path)


def relink_html(path, resolve):
    text = read_raw(path)
    stats = {"mapped": 0, "unmapped": 0}

    def repl(m):
        url, drive, sep, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        raw = drive + ":" + sep + rest
        cuts = [len(raw)] + [i for i in range(len(raw) - 1, 2, -1) if raw[i] in " ，。；、（）()"]
        for cut in cuts:
            cand = raw[:cut].rstrip()
            path_ = urllib.parse.unquote(cand) if url else cand
            new = resolve(path_)
            if not new:
                continue
            if url:
                out = "file:///" + urllib.parse.quote(new.replace("\\", "/"), safe="/:")
            elif sep == "/":
                out = new.replace("\\", "/")
            else:
                out = new
            if path_ == path_.lower() and path_ != path_.upper():
                out = out.lower()
            stats["mapped"] += 1
            return out + raw[len(cand):]
        if drive.upper() == "D":
            stats["unmapped"] += 1
        return m.group(0)

    parts = KEEP_RE.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = PATH_RE.sub(repl, parts[i])
    new_text = "".join(parts)
    if new_text != text:
        write_raw(path, new_text)
    return stats


REL_RE = re.compile(r'((?:src|href)=")([^"#:?][^"#?]*)(")')


def relink_relative_page(page, old_dir, resolve):
    """归档过来的列表页（相对链接）：按页面原来所在目录解析每个相对链接，指到归档后的位置。"""
    text = read_raw(page)
    new_dir = os.path.dirname(page)
    stats = {"mapped": 0, "unmapped": 0}

    def repl(m):
        url = urllib.parse.unquote(m.group(2))
        if os.path.exists(os.path.join(new_dir, url.replace("/", os.sep))):
            return m.group(0)                     # 从新位置已经能找到（改过了，或者本来就在同一目录）
        old_abs = os.path.normpath(os.path.join(old_dir, url.replace("/", os.sep)))
        new_abs = resolve(old_abs)
        if not new_abs:
            stats["unmapped"] += 1
            return m.group(0)
        stats["mapped"] += 1
        rel = os.path.relpath(new_abs, new_dir).replace(os.sep, "/")
        return m.group(1) + urllib.parse.quote(rel, safe="/:") + m.group(3)

    new_text = REL_RE.sub(repl, text)
    if new_text != text:
        write_raw(page, new_text)
    return stats


# ---------------------------------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("games", nargs="*", help="游戏 key（见 --list），all = 全部")
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--only", nargs="+")
    ap.add_argument("--blender", default=DEFAULT_BLENDER)
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--lanes", type=int, default=6)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--recheck", action="store_true", help="E 盘上登记过的造型全部重新自检（包括 D 盘已删的）")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--relink", action="store_true", help="改写画廊页里的 D 盘链接（默认：本次处理的游戏）")
    args = ap.parse_args()

    if args.list:
        for key, g in games.GAMES.items():
            done = os.path.exists(os.path.join(args.dest, g.folder, "_meta", "models.json"))
            print("%-14s -> %-14s %-9s sources: %s" % (key, g.folder, "archived" if done else "-", ", ".join(g.sources)))
        return
    keys = list(games.GAMES) if args.games == ["all"] else args.games
    for key in keys:
        if key not in games.GAMES:
            raise SystemExit("unknown game %r (known: %s)" % (key, ", ".join(games.GAMES)))
    if not keys and not args.report and not args.relink:
        ap.print_help()
        return
    os.makedirs(args.dest, exist_ok=True)
    if not args.relink or args.report:
        for key in keys:
            archive_game(games.GAMES[key], args.dest, args.only, args.workers, args.blender, args.lanes,
                         not args.no_check, args.dry_run, args.recheck)
    if args.dry_run:
        return
    if args.relink or keys:
        resolve = build_resolver(args.dest)
        for key in (keys or list(games.GAMES)):
            game = games.GAMES[key]
            for rel in game.galleries:
                page = os.path.join(REPO, rel)
                if os.path.exists(page):
                    s = relink_html(page, resolve)
                    print("== relink %s: %d links -> E:, %d D: links left" % (rel, s["mapped"], s["unmapped"]))
            for name, old_dir in game.list_pages:
                for page in [f for f in walk_files(os.path.join(args.dest, game.folder, "_meta", name))
                             if f.lower().endswith((".html", ".htm"))]:
                    s = relink_relative_page(page, os.path.join(old_dir, os.path.relpath(
                        os.path.dirname(page), os.path.join(args.dest, game.folder, "_meta", name))), resolve)
                    print("== relink %s: %d links fixed, %d left" % (page, s["mapped"], s["unmapped"]))
    write_readmes(args.dest, scan_catalog(args.dest))
    sections = cleanup_report(args.dest)
    print("== catalog: %s" % os.path.join(args.dest, "README.md"))
    print("== cleanup: %s" % os.path.join(args.dest, CLEANUP_NAME))
    for root, size, freed, count, game, notes in sections["ok"]:
        print("   CAN DELETE  %-44s %s (frees %s)" % (root, gb(size), gb(freed)))
    for root, size, freed, count, game, subs, pending, notes in sections["partial"]:
        print("   PARTIAL     %-44s %s  (%d files not archived)" % (root, gb(size), len(pending)))


if __name__ == "__main__":
    main()
