# -*- coding: utf-8 -*-
"""PMX with expressions from the open .blend, in a BACKGROUND Blender.

Runs scripts/final/export_ff7_pmx_blender.py - the exact script the batch uses (manual == batch) - on
the saved .blend (or on a temporary copy when the file has unsaved changes), so the open scene is never
converted or changed.  One export at a time; poll() is called from a timer by the add-on.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

import bpy

HERE = os.path.dirname(os.path.realpath(__file__))           # the add-on is junction-installed from the repo
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
EXPORTER = os.path.join(REPO, "scripts", "final", "export_ff7_pmx_blender.py")
PREVIEWER = os.path.join(REPO, "scripts", "stellarblade", "preview_pmx_blender.py")
DEFAULT_OUT = r"E:\game_export\FF7Remake\_face_trial"
JOB = {}
STATUS = {"text": "", "pmx": ""}


def available():
    return os.path.isfile(EXPORTER)


def default_out():
    return DEFAULT_OUT if os.path.isdir(os.path.dirname(DEFAULT_OUT)) else os.path.join(tempfile.gettempdir(),
                                                                                         "ff7_pmx")


def running():
    return bool(JOB) and JOB.get("proc") is not None and JOB["proc"].poll() is None


def _spawn(cmd, log):
    fh = open(log, "w", encoding="utf-8", errors="replace")
    flags = 0x08000000 if sys.platform == "win32" else 0            # CREATE_NO_WINDOW: no console pops up
    return subprocess.Popen(cmd, stdout=fh, stderr=subprocess.STDOUT, creationflags=flags), fh


def start(blend, out_dir, name, face_data, model_name="", comment="", skirt_to_legs=False,
          categories=("EYE", "EYEBROW", "MOUTH", "OTHER"), strengths=None, previews=False, temp_copy=""):
    if running():
        raise RuntimeError("a PMX export is already running")
    if not available():
        raise RuntimeError("exporter not found: %s" % EXPORTER)
    os.makedirs(out_dir, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    log = os.path.join(tempfile.gettempdir(), "ff7_face_pmx_%s.log" % stamp)
    cmd = [bpy.app.binary_path, "-b", blend, "--python", EXPORTER, "--", "--out", out_dir, "--name", name,
           "--face-data", face_data, "--face-categories", ",".join(categories)]
    for cat, value in (strengths or {}).items():
        cmd += ["--face-strength", "%s=%g" % (cat, value)]
    if model_name:
        cmd += ["--model-name", model_name]
    if comment:
        cmd += ["--comment", comment]
    if skirt_to_legs:
        cmd.append("--skirt-to-legs")
    proc, fh = _spawn(cmd, log)
    JOB.clear()
    JOB.update(proc=proc, fh=fh, log=log, started=time.time(), stage="export", previews=previews,
               pmx=os.path.join(out_dir, name, name + ".pmx"), temp_copy=temp_copy, report=None)
    STATUS.update(text="导出中… (log %s)" % log, pmx="")
    return log


def _line(log, prefix):
    try:
        with open(log, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None, ""
    line = next((l for l in reversed(text.splitlines()) if l.startswith(prefix)), "")
    return (json.loads(line[len(prefix):]) if line else None), text[-1500:]


def poll():
    """None while running, else the finished job's summary (also left in STATUS)."""
    if not JOB or JOB.get("proc") is None:
        return {}
    if JOB["proc"].poll() is None:
        STATUS["text"] = "%s… %d s" % ("导出中" if JOB["stage"] == "export" else "渲染预览图中",
                                         time.time() - JOB["started"])
        return None
    JOB["fh"].close()
    if JOB["stage"] == "export":
        report, tail = _line(JOB["log"], "FF7_PMX_REPORT=")
        JOB["report"] = report
        if report is None:
            STATUS.update(text="导出失败，见日志 %s" % JOB["log"], pmx="")
            return _finish({"ok": False, "log": JOB["log"], "tail": tail})
        if JOB["previews"] and os.path.isfile(PREVIEWER):
            log = JOB["log"].replace(".log", "_preview.log")
            JOB["proc"], JOB["fh"] = _spawn([bpy.app.binary_path, "-b", "--python", PREVIEWER, "--",
                                             "--pmx", report["pmx"]], log)
            JOB.update(stage="preview", preview_log=log)
            return None
    report = JOB["report"] or {}
    dist = report.get("distortion") or {}
    summary = {"ok": True, "pmx": report.get("pmx", JOB["pmx"]), "morphs": len(report.get("vertex_morphs") or []),
               "torn": dist.get("torn"), "grant": len(report.get("grant_order_violations") or []),
               "seconds": round(time.time() - JOB["started"]), "log": JOB["log"]}
    STATUS.update(text="完成：%d 个表情，撕裂 %s，付与错误 %d，%d 秒" % (
        summary["morphs"], summary["torn"], summary["grant"], summary["seconds"]), pmx=summary["pmx"])
    return _finish(summary)


def _finish(summary):
    temp = JOB.get("temp_copy")
    if temp and os.path.isfile(temp):
        try:
            os.remove(temp)
        except OSError:
            pass
    JOB["proc"] = None
    JOB["summary"] = summary
    return summary
