"""删 D 盘上已经归档完的导出目录（用户要求删的时候用；归档脚本本身只拷不删）。

  python delete_archived.py                         只列出：每个登记过的 D 盘来源目录能不能删、多大、最近一次写入
  python delete_archived.py --delete D:\\a D:\\b     删这几个
  python delete_archived.py --delete-all --keep D:\\roe_exports   除了 --keep 的全删

每个目录删之前的一刻再核对一遍：里面每个文件都要么在账本里（已拷到 E 盘、之后没改过、E 盘那份还在），
要么是登记过的可重新生成的中间产物；不能有 junction / 符号链接（递归删除不能顺着它们删到别处）；
最近 --min-age 分钟（默认 30）内有写入的不删（可能有别的窗口在用）。任何一条不满足就跳过并说明原因。
"""
import argparse
import os
import shutil
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive_exports as ae  # noqa: E402
import games  # noqa: E402


def sources():
    out = []
    for game in games.GAMES.values():
        for root in game.sources:
            if os.path.exists(root) and not ae.inside(root, ae.DEFAULT_DEST):
                out.append((root, game))
    return out


def verify(root, game, ledger):
    """(可以删?, 没归档的文件, junction / 链接, 最近写入时间, 大小, 能腾出)"""
    regen = ae.Regen(game.regen())
    pending, reparse = [], []
    newest = 0.0
    size = freed = 0
    for dirpath, dirs, files in os.walk(root):
        for d in list(dirs):
            st = os.lstat(os.path.join(dirpath, d))
            if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                reparse.append(os.path.join(dirpath, d))
                dirs.remove(d)
        for f in files:
            p = os.path.join(dirpath, f)
            st = os.lstat(p)
            if getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                reparse.append(p)
                continue
            newest = max(newest, st.st_mtime)
            size += st.st_size
            nlink = os.stat(p).st_nlink if st.st_size >= (16 << 20) else 1
            freed += st.st_size if nlink <= 1 else 0
            if regen.reason(p) is None and not ledger.fresh(p):
                pending.append(p)
    return not pending and not reparse, pending, reparse, newest, size, freed


def rmtree(root):
    errors = []

    def onerror(func, path, _exc):
        try:
            os.chmod(path, stat.S_IWRITE)
            func(path)
        except OSError as exc:
            errors.append("%s: %s" % (path, exc))
    shutil.rmtree(root, onerror=onerror)
    return errors


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--delete", nargs="+", default=[], help="要删的 D 盘目录")
    ap.add_argument("--delete-all", action="store_true", help="删全部能删的（配合 --keep）")
    ap.add_argument("--keep", nargs="+", default=[], help="这些不删")
    ap.add_argument("--min-age", type=float, default=30, help="最近多少分钟内有写入的不删（默认 30）")
    args = ap.parse_args()
    ledger = ae.AllLedgers(ae.DEFAULT_DEST)
    keep = {ae.norm(k) for k in args.keep}
    wanted = {ae.norm(d) for d in args.delete}
    now = time.time()
    free0 = shutil.disk_usage("D:\\").free
    rows = []
    for root, game in sources():
        ok, pending, reparse, newest, size, freed = verify(root, game, ledger)
        age = (now - newest) / 60 if newest else 1e9
        rows.append((root, game, ok, age))
        print("%-34s %-4s %8.2f GB  能腾出 %8.2f GB  最近写入 %8.0f 分钟前  未归档 %d  链接 %d" % (
            root, "可删" if ok else "不行", size / 1e9, freed / 1e9, age, len(pending), len(reparse)))
        for p in (pending + reparse)[:5]:
            print("        " + p)
    print("D: 可用 %.1f GB" % (free0 / 1e9))
    if not (args.delete or args.delete_all):
        return
    for root, game, ok, age in rows:
        n = ae.norm(root)
        if n in keep or not (args.delete_all or n in wanted):
            continue
        if not ok:
            print("跳过 %s：还有没归档的文件 / 链接" % root)
            continue
        if age < args.min_age:
            print("跳过 %s：%.0f 分钟前还有写入" % (root, age))
            continue
        ok2 = verify(root, game, ae.AllLedgers(ae.DEFAULT_DEST))[0]
        if not ok2:
            print("跳过 %s：刚才核对之后又变了" % root)
            continue
        errors = rmtree(root)
        print("%s %s%s" % ("已删" if not os.path.exists(root) else "没删干净", root,
                           "（%d 个错误，例如 %s）" % (len(errors), errors[0]) if errors else ""), flush=True)
    free1 = shutil.disk_usage("D:\\").free
    print("D: 可用 %.1f GB -> %.1f GB（+%.1f GB）" % (free0 / 1e9, free1 / 1e9, (free1 - free0) / 1e9))


if __name__ == "__main__":
    main()
