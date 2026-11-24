#!/usr/bin/env python3
# m7t89.py — macOS port: Feishu #89 create -> rotate -> paint -> slice.
# feishu: baseline#170  (macOS port; corresponds to the enabled Windows
#         m7t89, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   empty bed -> create a cube -> rotate Z 45 (field commits) -> select the
#   model -> Color Painting activates and a dab lands -> slice completes.
#
# macOS mapping:
#   create -> right-click Add Primitive > Cube on an empty boot; a generated-
#             gcode Warning is cleared with Yes (m8x_137 recipe).
#   rotate -> Rotate toolbar (772,90), relative Z field (1047,148); the
#             absolute row (y=174) must read ~45 after the commit.
#   paint  -> Color Painting toolbar (996,90); Filaments panel + dab at the
#             cube centre (814,396).
#   slice  -> mac_common.slice_and_export.
#
# Artifacts: artifacts/mac/pilot/m7t89/{report.log,result.json,work/*.gcode,
#            *.png}.

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
PILOTS = Path(__file__).resolve().parent         # tests/engine/macos_pilot
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

import AppKit  # noqa: E402
import numpy as np  # noqa: E402

from harness.platform.macos_ocr import recognize_text  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness import macos_video  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, slice_and_export,
)
import m7b_new_project as m7b  # noqa: E402
import m8x_137_flow_param_tabs as c137  # noqa: E402
import m8x_153_layout_print as c153  # noqa: E402
import m8x_192 as c192  # noqa: E402
import m7t74 as c74  # noqa: E402
from m8b_official_color import drag  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m7t89"
MODEL_POINT = (814, 396)
ROTATE_X = 772
PAINT_ICON = (996, 90)
PAINT_CHIP2 = (977, 145)       # palette tile for filament 2 (teal)
PAINT_CIRCLE = (925, 260)      # brush tool; triangle only selects faces


def paste(driver, win, x, y, text, rep):
    driver.click(win.rect.x + x, win.rect.y + y)
    time.sleep(0.4)
    pb = AppKit.NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, AppKit.NSPasteboardTypeString)
    driver.send_key("a", modifiers=("cmd",))
    time.sleep(0.2)
    driver.send_key("v", modifiers=("cmd",))
    time.sleep(0.4)
    driver.send_key("return")
    time.sleep(1.2)
    rep.log(f"[INFO] set {text} @({x},{y})")


def model_point(frame):
    """Centroid of the teal cube inside the viewport (window-relative)."""
    xs = []
    ys = []
    for y in range(120, 640, 3):
        row = y * frame.width * 4
        for x in range(460, 880, 3):
            i = row + x * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            if g > r + 30 and g > b + 5 and g > 60:
                xs.append(x)
                ys.append(y)
    if not xs:
        return MODEL_POINT
    xs.sort()
    ys.sort()
    return (xs[len(xs) // 2], ys[len(ys) // 2])


def blue_centroid(frame):
    """Centroid of the blue cube after slot 1 is recoloured (#0303FC)."""
    xs = []
    ys = []
    for y in range(120, 640, 2):
        row = y * frame.width * 4
        for x in range(460, 880, 2):
            i = row + x * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            if b > 140 and b > r + 40 and b > g + 40:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return (int(sum(xs) / len(xs)), int(sum(ys) / len(ys)))


def interior_blue_point(frame):
    """Blue pixel well inside the cube, restricted to the 3D viewport.

    A full-frame centroid is pulled toward the blue filament chip in the
    sidebar; eroding the viewport mask gives a point that is guaranteed to be
    on the cube and at least 4px away from its silhouette.
    """
    arr = np.frombuffer(frame.data, np.uint8).reshape(
        frame.height, frame.width, 4)
    b = arr[:, :, 0].astype(int)
    g = arr[:, :, 1].astype(int)
    r = arr[:, :, 2].astype(int)
    mask = (b > 140) & (b > r + 40) & (b > g + 40)
    view = np.zeros_like(mask)
    view[120:640, 460:880] = True
    mask &= view
    eroded = mask.copy()
    for dy in range(-4, 5):
        for dx in range(-4, 5):
            eroded &= np.roll(np.roll(mask, dy, axis=0), dx, axis=1)
    ys, xs = np.nonzero(eroded)
    if len(xs) == 0:
        return None
    ys0, xs0 = np.nonzero(mask)
    i = int(np.argmin((xs - xs0.mean()) ** 2 + (ys - ys0.mean()) ** 2))
    return (int(xs[i]), int(ys[i]))


def _dismiss_save_prompt(driver, app, win) -> bool:
    """If a 'Save changes?' dialog appears, choose No/Discard."""
    for w in driver.windows_for_pid(app.pid):
        if w.id == win.id or not w.on_screen:
            continue
        if "save" not in (w.title or "").lower():
            continue
        try:
            words = recognize_text(driver.capture(w), timeout_s=15)
        except Exception:
            return False
        for word in words:
            if word.text.strip().lower() in (
                    "no", "discard", "don't save", "dont save"):
                driver.click(w.rect.x + word.rect.center[0],
                             w.rect.y + word.rect.center[1])
                time.sleep(1.0)
                return True
    return False


class _Log:
    def log(self, text: str = "") -> None:
        print(text)


def phase2(args) -> int:
    """Fresh app session started by OPENING the project, then paint + slice.

    Windows §21.20: the first dab only lands in a session whose app was
    started by opening the project; an in-session open is not enough on macOS.
    """
    checks: list[dict] = []

    def chk(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
        return ok

    log = _Log()
    proj = Path(args.project).expanduser().resolve()
    out_json = Path(args.out_json).expanduser()
    driver = None
    app = None
    win = None
    try:
        driver = get_driver()
        paint_datadir = OUT / "profile_paint"
        shutil.rmtree(paint_datadir, ignore_errors=True)
        src_profile = Path(args.datadir)
        if src_profile.exists():
            # Reuse the initialized phase-1 profile (no first-run wizard) but
            # start a fresh app session by OPENING the project.
            shutil.copytree(src_profile, paint_datadir)
        app, win = launch_and_focus(
            driver, paint_datadir, model=proj, timeout_s=args.timeout,
            log_path=OUT / "app_launch_paint.log")
        chk("paint session opened project",
            proj.stem.lower() in (win.title or "").lower(),
            f"title={win.title!r}")
        time.sleep(3.0)

        before_chip, panel, expected = c153.set_slot_colour_rgb(
            driver, app, win, log)
        chk("slot-1 colour prepared for contrast", expected is not None,
            f"chip={before_chip} hex={expected}")
        # set_slot_colour_rgb already closed the Colors panel; closing it a
        # second time disturbs the following gizmo session.
        time.sleep(1.0)

        pt = interior_blue_point(driver.capture(win))
        chk("paint point on cube", pt is not None, str(pt))
        if pt is not None:
            driver.click(win.rect.x + pt[0], win.rect.y + pt[1])
            time.sleep(1.0)
            driver.click(win.rect.x + PAINT_ICON[0],
                         win.rect.y + PAINT_ICON[1])
            time.sleep(2.0)
            # Proven probe sequence: choose filament 2 + circle brush and
            # stroke BEFORE any OCR; OCR pauses break the ImGui gizmo state.
            driver.click(win.rect.x + PAINT_CHIP2[0],
                         win.rect.y + PAINT_CHIP2[1])
            time.sleep(0.8)
            driver.click(win.rect.x + PAINT_CIRCLE[0],
                         win.rect.y + PAINT_CIRCLE[1])
            time.sleep(0.8)
            before_frame = driver.capture(win)
            before = before_frame.pixel(*pt)
            bg = (600, 200)
            bg_before = before_frame.pixel(*bg)
            drag(win.rect.x + pt[0] - 8, win.rect.y + pt[1],
                 win.rect.x + pt[0] + 8, win.rect.y + pt[1], steps=8)
            time.sleep(1.0)
            after_frame = driver.capture(win)
            after = after_frame.pixel(*pt)
            bg_after = after_frame.pixel(*bg)
            text = " ".join(w.text for w in recognize_text(after_frame))
            active = ("selected filament" in text.lower()
                      and "remap filaments" in text.lower())
            chk("cube selected", "object name: cube" in text.lower(), "")
            chk("color painting activates", active, text[-140:])
            delta = max(abs(before[i] - after[i]) for i in range(3))
            bg_delta = max(abs(bg_before[i] - bg_after[i]) for i in range(3))
            log.log(f"[INFO] phase2 paint {before[:3]} -> {after[:3]} "
                    f"delta={delta} bg_delta={bg_delta}")
            chk("paint dab changes colour",
                active and delta >= 20 and bg_delta <= 5,
                f"panel={active} delta={delta} bg_delta={bg_delta}")
            after_frame.save_png(OUT / "painted_phase2.png")
            time.sleep(2.5)  # hold the visible stroke for the recording
            driver.click(win.rect.x + PAINT_ICON[0],
                         win.rect.y + PAINT_ICON[1])
            time.sleep(1.0)

        gcode = OUT / "work" / "m7t89_phase2.gcode"
        ok = slice_and_export(
            driver, win, log, gcode,
            [OUT / "work", OUT, ARTIFACTS / "pilot", HERE / "fixtures"])
        chk("slice completes",
            ok and gcode.exists() and gcode.stat().st_size > 0,
            f"size={gcode.stat().st_size if gcode.exists() else 0}")
    except Exception as exc:  # noqa: BLE001
        chk("phase2 unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                close_app(driver, app, win)
            except Exception:
                pass
    payload = {"checks": checks, "ok": all(c["ok"] for c in checks)}
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8")
    return 0 if payload["ok"] else 2


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--phase2", action="store_true")
    ap.add_argument("--project", default=None, type=Path)
    ap.add_argument("--out-json", default=None, type=Path)
    args = ap.parse_args()
    if args.phase2:
        if args.project is None or args.out_json is None:
            raise SystemExit("--phase2 requires --project and --out-json")
        return phase2(args)

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    work.mkdir(parents=True)
    gcode = work / "m7t89.gcode"
    proj = work / "m7t89_rotated.3mf"

    rep = Reporter(OUT)
    rep.log("=== m7t89 macOS create/rotate/paint/slice ===")
    rep.log(f"datadir={args.datadir}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=None,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        time.sleep(4.0)
        rep.check("empty bed at boot", True, win.title)

        rep.check("model created (M-20)", m7b._add_cube(driver, app, win))
        time.sleep(2.5)
        rep.check("Prepare ready", c137.ensure_prepare(driver, app, win, rep))
        driver.capture(win).save_png(OUT / "created.png")
        driver.click(win.rect.x + MODEL_POINT[0],
                     win.rect.y + MODEL_POINT[1])
        time.sleep(1.0)

        driver.click(win.rect.x + ROTATE_X, win.rect.y + 90)
        time.sleep(1.8)
        paste(driver, win, 1047, 148, "45", rep)
        driver.capture(win).save_png(OUT / "rotated.png")
        rep.check("另存旋转后项目", c192.save_project(driver, win, rep, proj)
                  and proj.exists())
        if not proj.exists():
            return rep.save({"stage": "save-rotated"})
        t = c192.item(proj, "Cube")
        ang, axis, norms = c74.mat_info(t) if t is not None else (0, [], [])
        rep.log(f"[INFO] rotated t={t} ang={ang:.1f} axis={axis} norms={norms}")
        rep.check("rotate Z commits 45",
                  t is not None and abs(ang - 45.0) <= 2.0
                  and abs(axis[2]) >= 0.95,
                  f"ang={ang:.1f} axis={axis}")

        # --- phase 1 done; phase 2 must start by OPENING the project ---
        rep.log("[INFO] phase-1 done: closing; child opens the saved project")
        alive_before = app.alive()
        fh = app.extra.get("log_fh")
        if fh:
            try:
                fh.close()
            except Exception:
                pass
        try:
            app.terminate()
        except Exception:
            pass
        deadline = time.monotonic() + 10.0
        while app.alive() and time.monotonic() < deadline:
            time.sleep(0.3)
        rep.check("phase-1 software closed", not app.alive(),
                  f"alive_before={alive_before}")
        app = None

        rep.log("[INFO] phase-2 child: open project -> paint -> slice")
        phase2_json = OUT / "phase2_result.json"
        env = os.environ.copy()
        env["ORCA_BB_VIDEO"] = "0"
        proc = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()),
             "--phase2", "--datadir", str(args.datadir),
             "--project", str(proj), "--out-json", str(phase2_json)],
            env=env, capture_output=True, text=True, timeout=600,
            cwd=str(HERE))
        rep.log(f"[INFO] phase2 rc={proc.returncode}")
        if proc.stdout:
            rep.log(proc.stdout[-1200:])
        if proc.stderr:
            rep.log(proc.stderr[-1200:])
        payload = (json.loads(phase2_json.read_text(encoding="utf-8"))
                   if phase2_json.exists()
                   else {"checks": [], "ok": False})
        for check in payload.get("checks", []):
            rep.check(check["name"], check["ok"], check.get("detail", ""))
        rep.check("phase2 child completed", bool(payload.get("ok")),
                  f"rc={proc.returncode}")
        return rep.save({"covered": ["#170"]})
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        else:
            macos_video.stop("m7t89")
        exit_code = rep.save({"covered": ["#170"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
