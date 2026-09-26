"""archive_exports 的离线测试（不需要 Blender、不碰真实的 D / E 盘）。

  python scripts\\archive\\tests\\test_archive.py      -> 最后一行 ARCHIVE_TEST=PASS
"""
import os
import shutil
import struct
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import archive_exports as ae  # noqa: E402
import games  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print("ok  ", msg)


def xps_string(s):
    b = s.encode("utf-8")
    n = len(b)
    prefix = bytes([n]) if n < 128 else bytes([(n & 0x7F) | 0x80, n >> 7])
    return prefix + b


def test_xps_parser(tmp):
    long_name = "Fiona_DF_Armor_Bottom_T_pc_female_shiningwill_lower_01_MI_D.png"    # 长度 >= 32：前缀是可打印字符
    names = ["abc.png", "T_Teeth01_NA.png", long_name, "x" * 140 + ".dds"]
    data = b"\x01\x02XPS" + b"\x00" * 8
    for n in names:
        data += b"\x00\x00\x00\x00" + xps_string("mesh_" + n[:3]) + b"\x01\x00\x00\x00\x02\x00\x00\x00"
        data += xps_string(n) + b"\x00\x00\x00\x00"
    p = os.path.join(tmp, "t.xps")
    open(p, "wb").write(data)
    check(ae.xps_textures(p) == sorted(names), "xps_textures finds short, >=32 and 2-byte-length names")


def pmx_text(s):
    b = s.encode("utf-16-le")
    return struct.pack("<i", len(b)) + b


def test_pmx_parser(tmp):
    head = b"PMX " + struct.pack("<f", 2.0) + bytes([8, 0, 0, 4, 1, 1, 2, 1, 1])
    body = b"".join(pmx_text(s) for s in ("m", "m", "", ""))
    vert = struct.pack("<3f3f2f", 0, 0, 0, 0, 1, 0, 0, 0) + bytes([0]) + bytes([0, 0]) + struct.pack("<f", 1.0)
    body += struct.pack("<i", 1) + vert                       # 1 个 BDEF1 顶点
    body += struct.pack("<i", 3) + bytes([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])   # 3 个索引 x 4 字节
    body += struct.pack("<i", 2) + pmx_text("tex\\a.png") + pmx_text("b.png")
    p = os.path.join(tmp, "t.pmx")
    open(p, "wb").write(head + body)
    check(ae.pmx_textures(p) == ["tex\\a.png", "b.png"], "pmx_textures reads the texture table after vertices/faces")


def test_copy_and_ledger(tmp):
    src_dir, game_dir = os.path.join(tmp, "D", "game"), os.path.join(tmp, "E", "Game")
    os.makedirs(src_dir)
    src = os.path.join(src_dir, "a.bin")
    open(src, "wb").write(os.urandom(300000))
    dst = os.path.join(game_dir, "Char", "blend", "m", "a.bin")
    digest, st = ae.copy_verified(src, dst)
    check(open(src, "rb").read() == open(dst, "rb").read() and not os.path.exists(dst + ".part"), "copy_verified copies exactly")
    led = ae.Ledger(game_dir)
    led.record(src, os.path.relpath(dst, game_dir), digest, st)
    led.save()
    led = ae.Ledger(game_dir)
    check(led.fresh(src), "ledger: unchanged source is fresh")
    time.sleep(0.05)
    open(src, "ab").write(b"x")
    check(not led.fresh(src), "ledger: modified source is not fresh")
    os.remove(dst)
    check(not led.fresh(src), "ledger: missing E: copy is not fresh")


def test_regen():
    r = ae.Regen([(r"D:\g\raw", "raw"), (r"D:\g\mods\*\*\export", "mod raw"), (r"D:\g\blender\*.blend", "dup")])
    check(r.reason(r"D:\g\raw\x\y.png") == "raw", "regen: plain prefix")
    check(r.reason(r"D:\g\mods\a\b\export\c\d.psk") == "mod raw", "regen: glob dir matches files below it")
    check(r.reason(r"D:\g\blender\x.blend") == "dup" and r.reason(r"D:\g\blender\x_gallery.png") is None,
          "regen: glob file pattern only matches what it says")
    check(r.reason(r"D:\g\keep\m.blend1") is not None and r.reason(r"D:\g\keep\m.blend") is None,
          "regen: .blend1 backups always count, .blend does not")


def test_product_skip_and_names():
    p = games.Product("A:b", "blend", "m?", r"D:\x", exclude=("parts", "*.npz"))
    check(p.character == "A_b" and p.model == "m_", "safe(): invalid Windows characters replaced")
    check(p.skip(r"parts\a.npz") and p.skip("z.npz") and p.skip("m.blend1") and not p.skip("m.blend"),
          "Product.skip: exclude dir, glob, and .blend1")


def test_relink():
    table = {os.path.normcase(r"D:\g\blend\A\A.blend"): r"E:\a\G\Chr\blend\A\A.blend",
             os.path.normcase(r"D:\g\x y.png"): r"E:\a\G\_meta\x y.png"}

    def resolve(p):
        return table.get(os.path.normcase(os.path.normpath(p)))
    html = ('<a href="file:///D:/g/blend/A/A.blend">D:\\g\\blend\\A\\A.blend</a>'
            '<img src="file:///D:/g/x%20y.png"><div data-search="a d:\\g\\blend\\a\\a.blend">'
            '<pre>D:\\g\\blend\\A\\A.blend</pre><code>D:\\g\\blend\\A\\A.blend</code>'
            '<span>D:\\g\\unknown.png</span>')
    with tempfile.TemporaryDirectory() as tmp:
        page = os.path.join(tmp, "index.html")
        open(page, "w", encoding="utf-8", newline="").write(html.replace("<a", "\r\n<a"))
        stats = ae.relink_html(page, resolve)
        out = open(page, encoding="utf-8", newline="").read()
    check("file:///E:/a/G/Chr/blend/A/A.blend" in out and ">E:\\a\\G\\Chr\\blend\\A\\A.blend<" in out,
          "relink: URL and backslash forms")
    check("file:///E:/a/G/_meta/x%20y.png" in out, "relink: URL-encoded names")
    check("e:\\a\\g\\chr\\blend\\a\\a.blend" in out, "relink: lower-case search text stays lower-case")
    check("<pre>D:\\g\\blend\\A\\A.blend</pre>" in out and "<code>D:\\g\\blend\\A\\A.blend</code>" in out,
          "relink: <pre>/<code> left alone")
    check(stats["unmapped"] == 1 and "\r\n<a" in out, "relink: unmapped counted, line endings kept")


def test_relative_page(tmp):
    old_dir = os.path.join(tmp, "old", "_list")
    new_dir = os.path.join(tmp, "new", "_meta", "list")
    os.makedirs(new_dir)
    page = os.path.join(new_dir, "index.html")
    open(page, "w", encoding="utf-8").write('<img src="../outfits/o1/o1_preview.png"><a href="#top">t</a>'
                                            '<img src="thumbs/a.jpg">')
    moved = {os.path.normcase(os.path.join(tmp, "old", "outfits", "o1")): os.path.join(tmp, "new", "Hero", "blend", "o1"),
             os.path.normcase(old_dir): new_dir}

    def resolve(p):
        n = os.path.normcase(os.path.normpath(p))
        for d, t in moved.items():
            if n == d or n.startswith(d + os.sep):
                return os.path.join(t, os.path.normpath(p)[len(d) + 1:])
        return None
    ae.relink_relative_page(page, old_dir, resolve)
    out = open(page, encoding="utf-8").read()
    check('src="../../Hero/blend/o1/o1_preview.png"' in out and 'href="#top"' in out and 'src="thumbs/a.jpg"' in out,
          "relative list page: moved targets re-pointed, anchors and same-dir links kept")


def test_cleanup_report(tmp):
    d_root = os.path.join(tmp, "D", "toy_exports")
    dest = os.path.join(tmp, "E", "game_export")
    for rel, data in (("blend\\A\\A.blend", b"a" * 1000), ("blend\\A\\textures\\t.png", b"t" * 500),
                      ("raw\\x.psk", b"r" * 700), ("blend\\B\\B.blend", b"b" * 800)):
        p = os.path.join(d_root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)

    def collect():
        return [games.Product("Chr", "blend", "A", os.path.join(d_root, "blend", "A"), main="A.blend")], []
    toy = games.Game("toy", "Toy", "Toy", sources=[d_root], collect=collect,
                     regenerable=[(os.path.join(d_root, "raw"), "raw = 原始解包")])
    saved = dict(games.GAMES), list(games.KNOWN_EXPORT_DIRS)
    games.GAMES.clear()
    games.GAMES["toy"] = toy
    games.KNOWN_EXPORT_DIRS[:] = []
    try:
        ae.archive_game(toy, dest, None, 2, None, 1, False, False)
        check(os.path.isfile(os.path.join(dest, "Toy", "Chr", "blend", "A", "textures", "t.png")),
              "archive_game: product copied into <game>/<char>/<fmt>/<model>")
        s = ae.cleanup_report(dest)
        check(not s["ok"] and len(s["partial"]) == 1, "cleanup: root with an unarchived model is partial")
        subs = [os.path.normcase(p) for p, _s, _f in s["partial"][0][5]]
        check(os.path.normcase(os.path.join(d_root, "blend", "A")) in subs and
              os.path.normcase(os.path.join(d_root, "raw")) in subs, "cleanup: archived and regenerable subdirs listed")
        shutil.rmtree(os.path.join(d_root, "blend", "B"))
        s = ae.cleanup_report(dest)
        check(len(s["ok"]) == 1 and not s["partial"], "cleanup: fully archived root becomes deletable")
        ae.write_readmes(dest, ae.scan_catalog(dest))
        check("| Chr | 1 | blend 1 |" in open(os.path.join(dest, "README.md"), encoding="utf-8").read(),
              "catalog README lists the character")
        text = open(os.path.join(dest, "Toy", "README.md"), encoding="utf-8").read()
        check("A.blend" in text, "game README links the model")
    finally:
        games.GAMES.clear()
        games.GAMES.update(saved[0])
        games.KNOWN_EXPORT_DIRS[:] = saved[1]


def main():
    tmp = tempfile.mkdtemp(prefix="archive_test_")
    try:
        test_xps_parser(tmp)
        test_pmx_parser(tmp)
        test_copy_and_ledger(tmp)
        test_regen()
        test_product_skip_and_names()
        test_relink()
        test_relative_page(tmp)
        test_cleanup_report(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("ARCHIVE_TEST=PASS")


if __name__ == "__main__":
    main()
