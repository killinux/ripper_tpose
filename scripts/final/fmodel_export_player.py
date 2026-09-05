"""用 UI 自动化驱动 FModel，把 FF7 Rebirth 的 End/Content/Character/Player 整目录导出为 ActorX。

FModel 没有命令行；它的「Save Folder's Packages Models」是唯一的批量入口，
本脚本用 pywinauto（UIA 后端）替人点：备份并改写 AppSettings（指向 Rebirth、
经典浏览器、Mesh Format=ActorX）→ 启动 FModel → Load → 展开树到 Player →
Shift+F10 弹出上下文菜单 → 触发导出 → 轮询导出目录直到 3 分钟没有新文件。

    python fmodel_export_player.py [--folder Player] [--restore]

注意：
- 全程不要碰键鼠；本脚本只用 UIA 的 Select/Invoke 与键盘，不用鼠标坐标（高 DPI 下坐标会偏）。
- 结束后用 --restore（或脚本自动）把 AppSettings 还原成备份，避免影响其它游戏的 FModel 配置。
- pywinauto 需先 `pip install pywinauto`。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

from pywinauto import Application, Desktop
from pywinauto.keyboard import send_keys

SETTINGS = os.path.join(os.environ["APPDATA"], "FModel", "AppSettings.json")
BACKUP = SETTINGS + ".before_rebirth_batch.bak"
FMODEL = r"E:\tools\fmodel\FModel.exe"
GAME = r"D:\Program Files (x86)\Steam\steamapps\common\FINAL FANTASY VII REBIRTH"
EXPORT_ROOT = r"D:\ff7rebirth_exports\fmodel_exports"
MENU_ITEM = "Save Folder's Packages Models"


def restore_settings():
    if os.path.exists(BACKUP):
        shutil.copy2(BACKUP, SETTINGS)
        os.remove(BACKUP)
        print("AppSettings 已还原")


def prepare_settings():
    if not os.path.exists(BACKUP):
        shutil.copy2(SETTINGS, BACKUP)
    d = json.load(open(SETTINGS, encoding="utf-8"))
    d["GameDirectory"] = GAME
    d["ModelDirectory"] = EXPORT_ROOT
    d["OutputDirectory"] = EXPORT_ROOT
    d["FeaturePreviewNewAssetExplorer"] = False   # 新浏览器没有目录右键菜单
    d["MeshExportFormat"] = 0                     # ActorX (psk/pskx)
    d["LodExportFormat"] = 0                      # First Level Only
    d["TextureExportFormat"] = 0                  # PNG
    json.dump(d, open(SETTINGS, "w", encoding="utf-8"), indent=2, ensure_ascii=False)


def launch():
    subprocess.call(["taskkill", "/IM", "FModel.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3)
    Application(backend="uia").start(FMODEL)
    for _ in range(90):
        time.sleep(1)
        try:
            win = Application(backend="uia").connect(title_re="FModel.*", timeout=1).window(title_re="FModel.*")
            if win.exists():
                win.wait("visible", timeout=30)
                return win
        except Exception:
            pass
    raise SystemExit("FModel 没有出现")


def log_text(win):
    return "".join((x.window_text() or "") for x in win.descendants(control_type="Document"))


def find_item(win, name, tries=20):
    rx = re.compile(r"^%s( \||$)" % re.escape(name))
    for _ in range(tries):
        for c in win.descendants(control_type="TreeItem"):
            if rx.match(c.window_text()):
                return c
        time.sleep(1)
    raise SystemExit("树里找不到 " + name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--folder", default="Player", help="Character 下要整目录导出的子目录")
    ap.add_argument("--restore", action="store_true", help="只还原 AppSettings 备份")
    ap.add_argument("--keep-settings", action="store_true", help="结束后不还原 AppSettings")
    args = ap.parse_args()
    if args.restore:
        restore_settings(); return

    prepare_settings()
    win = launch()
    win.set_focus(); time.sleep(2)
    load = win.child_window(title="Load", control_type="Button")
    load.wait("exists visible enabled", timeout=60)
    load.invoke()
    for i in range(120):
        time.sleep(5)
        if "virtual paths loaded" in log_text(win):
            print("archives loaded (%ds)" % ((i + 1) * 5)); break
    else:
        raise SystemExit("Load 超时")

    win.child_window(title="Folders", control_type="TabItem").click_input(); time.sleep(2)
    for n in ("End", "Content", "Character"):
        it = find_item(win, n)
        try:
            it.expand()
        except Exception:
            it.double_click_input()
        time.sleep(2)
    target = find_item(win, args.folder)
    target.select(); time.sleep(0.5); target.set_focus(); time.sleep(0.5)
    send_keys("+{F10}"); time.sleep(1.2)
    pid = win.process_id()
    item = None
    for w in Desktop(backend="uia").windows():
        try:
            if w.process_id() != pid:
                continue
            for c in w.descendants(control_type="MenuItem"):
                if c.window_text() == MENU_ITEM:
                    item = c
        except Exception:
            pass
    if item is None:
        send_keys("{ESC}")
        raise SystemExit("没找到菜单项 %s" % MENU_ITEM)
    item.invoke()
    print("已触发：%s -> %s" % (MENU_ITEM, args.folder))

    # 轮询：3 分钟没有新文件即视为完成
    stamp = time.time()
    quiet = 0
    while True:
        time.sleep(30)
        newest = 0
        for root, _d, files in os.walk(EXPORT_ROOT):
            for f in files:
                try:
                    newest = max(newest, os.path.getmtime(os.path.join(root, f)))
                except OSError:
                    pass
        if newest > stamp:
            stamp = newest; quiet = 0
        else:
            quiet += 30
        if quiet >= 180:
            break
    n = sum(1 for root, _d, files in os.walk(EXPORT_ROOT) for f in files if f.lower().endswith((".psk", ".pskx")))
    print("导出结束：磁盘上共 %d 个 psk/pskx" % n)
    if not args.keep_settings:
        subprocess.call(["taskkill", "/IM", "FModel.exe", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        restore_settings()


if __name__ == "__main__":
    main()
