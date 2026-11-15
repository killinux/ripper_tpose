# -*- coding: utf-8 -*-
"""Drive MikuMikuDance itself (MMD 9.32 x64, optionally with MME + ray-mmd) to check PMX files the way users see them.

    python mmd_drive.py compare <original.pmx> <out prefix> [--step1 <x_材质.pmx>] [--raymmd-dir <folder>]
           [--size 1200x1800] [--bg <picture>] [--mmd <MikuMikuDance.exe>] [--ray-mmd <ray-mmd folder>]
    python mmd_drive.py shot <out.png> --model <pmx> [--model ...] [--ray] [--size 1200x1800] [--bg <picture>]
    python mmd_drive.py scene <ray-mmd folder> ...

"compare" renders, in ONE MMD session: the original PMX and the step-1 PMX in plain MMD (on a grey background
picture), then loads ray.x + the Helipad GoldenHour skybox + <folder>\\model.pmx, opens <folder>\\scene.emm in MME's
Map Effect File dialog, reads the MaterialMap tab back (how many materials point at our fx files) and renders -
<prefix>_original.png, <prefix>_step1.png, <prefix>_raymmd.png.  "scene" sets the same ray-mmd scene up and lets MMD
save it as <folder>\\scene.pmm (MME writes scene.emm next to it).  Every dialog MMD or MME shows on the way (model
information, MME compile errors, the delete confirmation) is recorded and closed; the result line is
MMD_DRIVE=<json> / MMD_SCENE=<json>.

How it drives MMD (all by window messages, no mouse; still, MMD's window pops up on the desktop for a minute):
  * buttons by control id - model "load" 435, model "delete" 437, accessory "load" 472 - clicked with a posted
    BM_CLICK (a sent one would block in MMD's modal file dialog);
  * the file dialog: the file-name box is the Edit with id 1148; the path must use BACKSLASHES (with forward
    slashes the dialog says the file does not exist), then IDOK;
  * menu commands by id - 276 file > render to picture file (renders at the "screen size", MMD's default camera
    shows the whole model), 212 view > screen size (Edit 621 width, 622 height), 232 background > load background
    picture file;
  * MMD's default camera frames a standing model; the camera panel's number boxes did not take posted values
    (tried 11-14), so close-ups are crops of a big render.
"""
import argparse
import json
import os
import subprocess
import sys
import time

import win32api
import win32con
import win32gui
import win32process

MMD_EXE = r"E:\tools\MikuMikuDanceE_v932x64\MikuMikuDance.exe"
RAY_MMD = r"E:\tools\MikuMikuDanceE_v932x64\ray-mmd-1.5.2"
ID_MODEL_LOAD, ID_MODEL_DELETE, ID_ACC_LOAD = 435, 437, 472
CMD_RENDER_PICTURE, CMD_SCREEN_SIZE, CMD_BG_PICTURE, CMD_SAVE_AS, CMD_OPEN = 276, 212, 232, 208, 205
CMD_MME_MAPPING, MME_FILE_OPEN, MME_FILE_SAVE = 40005, 40009, 40010


def windows_of(pid):
    out = []

    def cb(h, _):
        if win32gui.IsWindowVisible(h) and win32process.GetWindowThreadProcessId(h)[1] == pid:
            out.append(h)
        return True
    win32gui.EnumWindows(cb, None)
    return out


def children(h):
    out = []
    win32gui.EnumChildWindows(h, lambda c, _: out.append(c) or True, None)
    return out


def text_of(h):
    try:
        return win32gui.GetWindowText(h)
    except Exception:  # noqa: BLE001
        return ""


def dialog_texts(h):
    return [text_of(c) for c in children(h) if win32gui.GetClassName(c) in ("Static", "Edit", "RichEdit20W")
            and text_of(c).strip()]


def find_button(parent, cid):
    for c in children(parent):
        if win32gui.GetDlgCtrlID(c) == cid and win32gui.GetClassName(c) == "Button":
            return c
    return None


class MMD:
    def __init__(self, exe=MMD_EXE):
        self.proc = subprocess.Popen([exe], cwd=os.path.dirname(exe))
        self.pid = self.proc.pid
        self.main = None
        self.events = []
        for _ in range(60):
            time.sleep(0.5)
            for h in windows_of(self.pid):
                if win32gui.GetClassName(h) == "Polygon Movie Maker":
                    self.main = h
            if self.main:
                break
        if not self.main:
            self.proc.kill()
            raise RuntimeError("MMD main window not found")
        time.sleep(2)
        self.idle(settle=2, label="start")

    def close(self):
        self.proc.kill()

    def dialogs(self, exclude=()):
        return [h for h in windows_of(self.pid) if win32gui.GetClassName(h) == "#32770" and h not in exclude]

    def wait_dialog(self, timeout=30, exclude=()):
        t0 = time.time()
        while time.time() - t0 < timeout:
            d = self.dialogs(exclude)
            if d:
                return d[0]
            time.sleep(0.3)
        return None

    def file_dialog(self, path, timeout=30, exclude=()):
        d = self.wait_dialog(timeout, exclude)
        if d is None:
            raise RuntimeError("no file dialog")
        edits = [c for c in children(d) if win32gui.GetClassName(c) == "Edit" and win32gui.IsWindowVisible(c)]
        edits = [c for c in edits if win32gui.GetDlgCtrlID(c) == 1148] or edits
        if not edits:
            raise RuntimeError("file dialog without a file name box: %r" % dialog_texts(d))
        win32gui.SendMessage(edits[0], win32con.WM_SETTEXT, 0, os.path.normpath(path))
        time.sleep(0.3)
        win32api.PostMessage(find_button(d, 1), win32con.BM_CLICK, 0, 0)
        for _ in range(100):
            time.sleep(0.2)
            if d not in self.dialogs():
                return
        raise RuntimeError("file dialog did not close: %r" % dialog_texts(d))

    # ---- MME's "Map Effect File" dialog (MMEffect > Effect Mapping)

    def mapping_dialog(self):
        win32api.PostMessage(self.main, win32con.WM_COMMAND, CMD_MME_MAPPING, 0)
        for _ in range(30):
            time.sleep(0.3)
            for h in windows_of(self.pid):
                if win32gui.GetWindowText(h) == "Map Effect File":
                    return h
        raise RuntimeError("MME's Map Effect File dialog did not open")

    def mapping_rows(self, dlg, tab="MaterialMap"):
        """[(object or '  |-- n: subsetn', effect file)] of one tab of the dialog (pywinauto reads the list)."""
        from pywinauto import Application
        app = Application(backend="win32").connect(process=self.pid)
        tc = [c for c in children(dlg) if win32gui.GetClassName(c) == "SysTabControl32"][0]
        app.window(handle=tc).wrapper_object().select(tab)
        time.sleep(0.8)
        lv = app.window(handle=[c for c in children(dlg) if win32gui.GetClassName(c) == "SysListView32"][0])
        lvw = lv.wrapper_object()
        return [tuple(lvw.get_item(i, j).text() for j in range(lvw.column_count())) for i in range(lvw.item_count())]

    def load_emm(self, emm):
        """File > Open in the Map Effect File dialog; returns the MaterialMap rows afterwards; MME's messages
        (e.g. "Failed to load effect mapping for the following objects") go to the events."""
        dlg = self.mapping_dialog()
        win32api.PostMessage(dlg, win32con.WM_COMMAND, MME_FILE_OPEN, 0)
        self.file_dialog(emm, exclude=(dlg,))
        time.sleep(2)
        for h in self.dialogs(exclude=(dlg,)):
            self.events.append({"when": "emm " + os.path.basename(emm), "title": text_of(h),
                                "texts": dialog_texts(h)})
            b = find_button(h, 1) or find_button(h, 2)
            if b:
                win32api.PostMessage(b, win32con.BM_CLICK, 0, 0)
        time.sleep(1)
        rows = self.mapping_rows(dlg)
        win32api.PostMessage(find_button(dlg, 1), win32con.BM_CLICK, 0, 0)     # OK
        time.sleep(1)
        self.idle(settle=3, label="after emm")
        return rows

    def idle(self, settle=4.0, timeout=600, label=""):
        """Wait until no dialog has been up for `settle` seconds; record and close every dialog on the way."""
        t0 = quiet = time.time()
        while time.time() - t0 < timeout:
            ds = self.dialogs()
            if ds:
                for d in ds:
                    self.events.append({"when": label, "title": text_of(d), "texts": dialog_texts(d)})
                    for cid in (1, 2, 6, 7):
                        b = find_button(d, cid)
                        if b:
                            win32api.PostMessage(b, win32con.BM_CLICK, 0, 0)
                            break
                    else:
                        win32api.PostMessage(d, win32con.WM_CLOSE, 0, 0)
                quiet = time.time()
            elif time.time() - quiet > settle:
                return
            time.sleep(0.3)

    def click(self, cid):
        b = find_button(self.main, cid)
        if not b:
            raise RuntimeError("button %d not found" % cid)
        win32api.PostMessage(b, win32con.BM_CLICK, 0, 0)

    def load_model(self, path):
        self.click(ID_MODEL_LOAD)
        self.file_dialog(path)
        self.idle(label="model " + os.path.basename(path))

    def delete_model(self):
        self.click(ID_MODEL_DELETE)
        self.idle(settle=2, label="model delete")

    def load_accessory(self, path):
        self.click(ID_ACC_LOAD)
        self.file_dialog(path)
        self.idle(label="accessory " + os.path.basename(path))

    def screen_size(self, w, h):
        """view > screen size.  Waits for the dialog by its title and retries: once (CCFF7R sample, 11-14) the
        dialog came up late, another dialog was taken for it and the renders came out at the default 640x360."""
        for _attempt in range(3):
            win32api.PostMessage(self.main, win32con.WM_COMMAND, CMD_SCREEN_SIZE, 0)
            d = None
            for _ in range(40):
                time.sleep(0.3)
                d = next((x for x in self.dialogs() if text_of(x) == "screen size"), None)
                if d:
                    break
            if d is None:
                self.idle(settle=1, label="before screen size")
                continue
            for c in children(d):
                cid = win32gui.GetDlgCtrlID(c)
                if cid in (621, 622):
                    win32gui.SendMessage(c, win32con.WM_SETTEXT, 0, str(w if cid == 621 else h))
            win32api.PostMessage(find_button(d, 1), win32con.BM_CLICK, 0, 0)
            time.sleep(1)
            self.idle(settle=1, label="screen size")
            return
        raise RuntimeError("MMD's screen size dialog did not open")

    def background(self, picture):
        win32api.PostMessage(self.main, win32con.WM_COMMAND, CMD_BG_PICTURE, 0)
        self.file_dialog(os.path.abspath(picture))
        self.idle(settle=1, label="background")

    def open_pmm(self, pmm):
        """file > open.  When the scene has changes (even the screen size counts) MMD first asks "There is a change
        point not preserved. Are you OK?" - answered with OK, then the file dialog."""
        win32api.PostMessage(self.main, win32con.WM_COMMAND, CMD_OPEN, 0)
        for _ in range(3):
            d = self.wait_dialog(15)
            if d is None:
                raise RuntimeError("no dialog after file > open")
            if any(win32gui.GetClassName(c) == "Edit" and win32gui.GetDlgCtrlID(c) == 1148 for c in children(d)):
                self.file_dialog(pmm)
                self.idle(settle=8, label="open " + os.path.basename(pmm))
                return
            self.events.append({"when": "open pmm", "title": text_of(d), "texts": dialog_texts(d)})
            win32api.PostMessage(find_button(d, 1) or find_button(d, 6), win32con.BM_CLICK, 0, 0)
            time.sleep(1)
        raise RuntimeError("file > open did not reach the file dialog")

    def render_picture(self, path):
        path = os.path.abspath(path)
        if os.path.exists(path):
            os.remove(path)
        win32api.PostMessage(self.main, win32con.WM_COMMAND, CMD_RENDER_PICTURE, 0)
        self.file_dialog(path)
        for _ in range(300):
            time.sleep(0.5)
            if os.path.isfile(path) and os.path.getsize(path) > 0:
                time.sleep(1.0)
                break
        self.idle(settle=2, label="render")
        return os.path.isfile(path)

    def ray(self, ray_mmd=RAY_MMD, sky=None):
        self.load_accessory(os.path.join(ray_mmd, "ray.x"))
        self.load_model(sky or os.path.join(ray_mmd, "Skybox", "Helipad GoldenHour", "Sky with box.pmx"))


def grey_background(path, size):
    if not os.path.isfile(path):
        from PIL import Image
        Image.new("RGB", size, (128, 128, 132)).save(path)
    return path


def assigned(rows, pack_dir):
    """How many subsets of the MaterialMap tab point into the pack's fx folder."""
    pack = os.path.normcase(os.path.abspath(pack_dir))
    return sum(1 for name, fx in rows if name.strip().startswith("|--") and os.path.normcase(fx).startswith(pack))


def compare(original, prefix, step1=None, raymmd_dir=None, size=(1200, 1800), bg=None, exe=MMD_EXE,
            ray_mmd=RAY_MMD):
    """original / step-1 PMX in plain MMD, then ray.x + skybox + <raymmd_dir>\\model.pmx + scene.emm."""
    outs, info = {}, {}
    m = MMD(exe)
    try:
        m.screen_size(*size)
        m.background(bg or grey_background(prefix + "_bg.png", size))
        for key, pmx in (("original", original), ("step1", step1)):
            if pmx:
                m.load_model(pmx)
                m.idle(settle=4, label="settle " + key)
                if m.render_picture("%s_%s.png" % (prefix, key)):
                    outs[key] = os.path.abspath("%s_%s.png" % (prefix, key))
                m.delete_model()
        if raymmd_dir:
            m.ray(ray_mmd)
            m.load_model(os.path.join(raymmd_dir, "model.pmx"))
            rows = m.load_emm(os.path.join(raymmd_dir, "scene.emm"))
            info["subsets_assigned"] = assigned(rows, os.path.join(raymmd_dir, "fx"))
            info["subsets"] = sum(1 for name, _fx in rows if name.strip().startswith("|--"))
            m.idle(settle=8, label="settle ray")
            if m.render_picture(prefix + "_raymmd.png"):
                outs["raymmd"] = os.path.abspath(prefix + "_raymmd.png")
    finally:
        m.close()
    return outs, m.events, info


def compare_many(items, size=(1200, 1800), bg=None, exe=MMD_EXE, ray_mmd=RAY_MMD):
    """compare() for many models in ONE MMD session (the window pops up once; the user asked why every sample
    opened its own MMD, 11-14): first the plain-MMD renders of every model (load, render, delete), then ray.x and
    the skybox once and every ray-mmd version (load, scene.emm, render, delete).
    items: [(prefix, original, step1 or None, raymmd_dir or None)] -> ({prefix: {variant: png}}, {prefix: info},
    {prefix: [events]})."""
    outs, info, events = {}, {}, {}
    m = MMD(exe)
    try:
        m.screen_size(*size)
        if bg:
            m.background(bg)
        for prefix, original, step1, _rd in items:
            outs.setdefault(prefix, {})
            for key, pmx in (("original", original), ("step1", step1)):
                if pmx:
                    n0 = len(m.events)
                    m.load_model(pmx)
                    m.idle(settle=4, label="settle " + key)
                    if m.render_picture("%s_%s.png" % (prefix, key)):
                        outs[prefix][key] = os.path.abspath("%s_%s.png" % (prefix, key))
                    m.delete_model()
                    events.setdefault(prefix, []).extend(m.events[n0:])
        if any(rd for *_x, rd in items):
            m.ray(ray_mmd)
            for prefix, _o, _s, rd in items:
                if not rd:
                    continue
                n0 = len(m.events)
                m.load_model(os.path.join(rd, "model.pmx"))
                rows = m.load_emm(os.path.join(rd, "scene.emm"))
                info[prefix] = {"subsets_assigned": assigned(rows, os.path.join(rd, "fx")),
                                "subsets": sum(1 for name, _fx in rows if name.strip().startswith("|--"))}
                m.idle(settle=8, label="settle ray")
                if m.render_picture(prefix + "_raymmd.png"):
                    outs[prefix]["raymmd"] = os.path.abspath(prefix + "_raymmd.png")
                m.delete_model()
                events.setdefault(prefix, []).extend(m.events[n0:])
    finally:
        m.close()
    return outs, info, events


def save_scenes(raymmd_dirs, exe=MMD_EXE, ray_mmd=RAY_MMD):
    """<dir>\\scene.pmm for every dir, in ONE MMD session: ray.x + Helipad skybox loaded once, then per model
    load model.pmx, open scene.emm, File > Save As scene.pmm (MME writes the matching scene.emm next to it and reads
    it back whenever the .pmm is opened), delete the model.  Yields one result per dir."""
    m = MMD(exe)
    try:
        m.ray(ray_mmd)
        for d in raymmd_dirs:
            n0 = len(m.events)
            m.load_model(os.path.join(d, "model.pmx"))
            rows = m.load_emm(os.path.join(d, "scene.emm"))
            n = assigned(rows, os.path.join(d, "fx"))
            pmm = os.path.join(d, "scene.pmm")
            if os.path.exists(pmm):
                os.remove(pmm)
            win32api.PostMessage(m.main, win32con.WM_COMMAND, CMD_SAVE_AS, 0)
            m.file_dialog(pmm)
            m.idle(settle=3, label="save pmm")
            m.delete_model()
            yield {"dir": d, "pmm": pmm if os.path.isfile(pmm) else None, "subsets_assigned": n,
                   "problems": problems(m.events[n0:])}
    finally:
        m.close()


def problems(events):
    """The dialogs that are not routine (model information on load, the delete confirmation)."""
    return [e for e in events if "nfomation" not in e["title"] and e["title"] not in ("model delete", "open file data")]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("original")
    c.add_argument("prefix")
    c.add_argument("--step1")
    c.add_argument("--raymmd-dir", help="the ray-mmd folder make_hq_materials wrote (model.pmx, scene.emm, fx)")
    s = sub.add_parser("shot")
    s.add_argument("out")
    s.add_argument("--model", action="append", default=[])
    s.add_argument("--ray", action="store_true")
    sc = sub.add_parser("scene")
    sc.add_argument("raymmd_dir", nargs="+")
    for p in (c, s, sc):
        p.add_argument("--size", default="1200x1800")
        p.add_argument("--bg")
        p.add_argument("--mmd", default=MMD_EXE)
        p.add_argument("--ray-mmd", default=RAY_MMD)
    args = ap.parse_args()
    size = tuple(int(v) for v in args.size.split("x"))
    info = {}
    if args.cmd == "scene":
        for res in save_scenes(args.raymmd_dir, args.mmd, args.ray_mmd):
            print("MMD_SCENE=" + json.dumps(res, ensure_ascii=False), flush=True)
        return
    if args.cmd == "compare":
        outs, events, info = compare(args.original, args.prefix, args.step1, args.raymmd_dir, size, args.bg,
                                     args.mmd, args.ray_mmd)
    else:
        m = MMD(args.mmd)
        outs = {}
        try:
            m.screen_size(*size)
            if args.bg:
                m.background(args.bg)
            if args.ray:
                m.ray(args.ray_mmd)
            for p in args.model:
                m.load_model(p)
            m.idle(settle=8, label="settle")
            if m.render_picture(args.out):
                outs["shot"] = os.path.abspath(args.out)
        finally:
            m.close()
        events = m.events
    print("MMD_DRIVE=" + json.dumps({"outs": outs, "info": info, "problems": problems(events), "events": events},
                                    ensure_ascii=False))


if __name__ == "__main__":
    main()
