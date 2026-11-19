#!/usr/bin/env python3
# m8x_191.py — macOS port: Feishu #191 rotate relative/absolute XYZ 45°.
# feishu: baseline#191  (macOS port; corresponds to the enabled Windows
#         m8x_191, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   relative X/Y/Z = 45 each and absolute X/Y/Z = 45 each produce real
#   rotations about the requested axis (each relative step Δ=45°), the
#   absolute chain starts from identity and every step is a real change,
#   the cube stays bed-contacted, translated stably, and the rotation
#   matrix remains orthonormal.
#
# macOS mapping:
#   scene  -> Prusa.stl + Import cube20 (auto-selected, volume 8000).
#   rotate -> Rotate toolbar (772,90); relative fields y=148, absolute
#             y=174, X/Y/Z centres 921/984/1047; click + Cmd+A paste +
#             Enter.  One session does the relative chain, a fresh session
#             does the absolute chain (both with 3 saves).
#   oracle -> mac_3mf item matrices + the Windows matrix math.
#
# Artifacts: artifacts/mac/pilot/m8x_191/{report.log,result.json,work/*.3mf,
#            *.png}.

from __future__ import annotations

import argparse
import math
import shutil
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

from harness.platform.macos_ocr import recognize_text  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)
import m8x_192 as c192  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_191"
PRUSA = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
ROTATE_X = 772
REL_Y = 148
ABS_Y = 174
X_CENTERS = (921, 984, 1047)
IDENT = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


# --- matrix math (same criteria as the Windows case) -----------------------

def _r3(m):
    return [m[0:3], m[3:6], m[6:9]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def _t(a):
    return [[a[j][i] for j in range(3)] for i in range(3)]


def _axis_angle(a):
    tr = sum(a[i][i] for i in range(3))
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))
    ax = (a[2][1] - a[1][2], a[0][2] - a[2][0], a[1][0] - a[0][1])
    n = math.sqrt(sum(v * v for v in ax))
    ax = [v / n for v in ax] if n > 1e-9 else [0.0, 0.0, 1.0]
    return ang, ax


def delta_angle(prev, cur):
    return _axis_angle(_mul(_r3(cur), _t(_r3(prev))))[0]


def step_ok(prev, cur, axis_idx, want_deg=45.0, tol_deg=1.5):
    rp, rc = _r3(prev), _r3(cur)
    if want_deg < 0.5:
        ang, _ax = _axis_angle(_mul(rc, _t(rp)))
        return ang <= tol_deg, round(ang, 1)
    for delta in (_mul(rc, _t(rp)), _mul(_t(rp), rc)):
        ang, ax = _axis_angle(delta)
        if abs(ang - want_deg) <= tol_deg and abs(ax[axis_idx]) >= 0.999:
            return True, round(ang, 1)
    return False, round(_axis_angle(_mul(rc, _t(rp)))[0], 1)


def bed_contact_ok(m, tol=0.05):
    want = 10.0 * (abs(m[2]) + abs(m[5]) + abs(m[8]))
    return abs(m[11] - want) <= tol, round(want, 3)


def rows_orthonormal(m, tol=0.02):
    rows = _r3(m)
    for r in rows:
        if abs(sum(v * v for v in r) ** 0.5 - 1.0) > tol:
            return False
    return abs(sum(rows[0][i] * rows[1][i] for i in range(3))) <= tol


# --- scene / input ---------------------------------------------------------

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
    row = [w.text for w in recognize_text(driver.capture(win))
           if abs(w.rect.y - y) < 4]
    rep.log(f"[INFO] rotate {text} @({x},{y}); row={row}")


def setup_scene(driver, datadir: Path, win, rep, tag: str):
    rows = [c for c in driver.controls(win, max_depth=12)
            if c.role == "AXMenuItem"
            and c.title.strip().lower().startswith("import ")
            and "3mf" in c.title.lower()]
    rep.check(f"{tag} 导入入口可用", bool(rows))
    if not rows:
        return False
    driver.click_control(rows[0])
    if not driver.open_file_dialog(win, CUBE):
        return False
    time.sleep(4.0)
    text = " ".join(w.text for w in recognize_text(driver.capture(win)))
    ok = "8000" in text
    rep.check(f"{tag} cube20 已选中（体积 8000）", ok, text[-100:])
    return ok


def ensure_rotate(driver, win):
    text = " ".join(w.text for w in recognize_text(driver.capture(win)))
    if "rotate (relative)" in text.lower():
        return True
    driver.click(win.rect.x + ROTATE_X, win.rect.y + 90)
    time.sleep(1.5)
    text = " ".join(w.text for w in recognize_text(driver.capture(win)))
    return "rotate (relative)" in text.lower()


def save_step(driver, win, rep, path: Path) -> bool:
    if not c192.save_project(driver, win, rep, path):
        return False
    ensure_rotate(driver, win)
    return path.exists()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    work = OUT / "work"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True)
    p = {k: work / f"m8x_191_p{k}.3mf" for k in (1, 2, 3)}
    a = {k: work / f"m8x_191_a{k}.3mf" for k in (1, 2, 3)}

    rep = Reporter(OUT)
    rep.log("=== m8x_191 macOS rotate relative/absolute ===")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)

        # ---------------- relative chain ---------------------------------
        app, win = launch_and_focus(
            driver, work / "profile_rel", model=PRUSA,
            timeout_s=args.timeout, log_path=OUT / "app_launch_rel.log")
        rep.check("relative launch", True, f"pid={app.pid}")
        ok, _f, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.01)
        rep.check("relative Prusa 载入", ok, f"colored={frac:.4f}")
        if not ok or not setup_scene(driver, work / "profile_rel", win,
                                     rep, "relative"):
            return rep.save({"stage": "rel-setup"})
        if not ensure_rotate(driver, win):
            return rep.save({"stage": "rel-panel"})
        for i, (x, axis) in enumerate(zip(X_CENTERS, "XYZ"), start=1):
            paste(driver, win, x, REL_Y, "45", rep)
            rep.check(f"relative {axis}=45 saved",
                      save_step(driver, win, rep, p[i]))
            driver.capture(win).save_png(OUT / f"rel_{axis}.png")
        closed = close_app(driver, app, win)
        rep.check("relative session closed", closed)
        app = None

        # ---------------- absolute chain (fresh identity) ----------------
        app, win = launch_and_focus(
            driver, work / "profile_abs", model=PRUSA,
            timeout_s=args.timeout, log_path=OUT / "app_launch_abs.log")
        rep.check("absolute launch", True, f"pid={app.pid}")
        ok, _f, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.01)
        rep.check("absolute Prusa 载入", ok, f"colored={frac:.4f}")
        if not ok or not setup_scene(driver, work / "profile_abs", win,
                                     rep, "absolute"):
            return rep.save({"stage": "abs-setup"})
        if not ensure_rotate(driver, win):
            return rep.save({"stage": "abs-panel"})
        for i, (x, axis) in enumerate(zip(X_CENTERS, "XYZ"), start=1):
            paste(driver, win, x, ABS_Y, "45", rep)
            rep.check(f"absolute {axis}=45 saved",
                      save_step(driver, win, rep, a[i]))
            driver.capture(win).save_png(OUT / f"abs_{axis}.png")
        closed = close_app(driver, app, win)
        rep.check("absolute session closed", closed)
        app = None

        # ---------------- matrix verdicts --------------------------------
        pmats = [c192.item(p[i], "cube20") for i in (1, 2, 3)]
        amats = [c192.item(a[i], "cube20") for i in (1, 2, 3)]
        if any(m is None for m in pmats + amats):
            rep.check("项目链矩阵可读", False, f"p={pmats} a={amats}")
            return rep.save({"stage": "matrices"})
        rep.check("项目链矩阵可读", True)

        prev = IDENT
        for i, axis in enumerate(("X", "Y", "Z")):
            good, ang = step_ok(prev, pmats[i], i)
            rep.check(f"相对链 {axis}=45（绕轴 Δ=45°）", good, f"Δ={ang}°")
            prev = pmats[i]
        good, ang = step_ok(IDENT, amats[0], 0)
        rep.check("绝对链 X=45（identity -> 绕 X 45°）", good, f"Δ={ang}°")
        for i, axis in enumerate(("Y", "Z"), start=1):
            dang = delta_angle(amats[i - 1], amats[i])
            rep.check(f"绝对链 {axis}=45 为真实变化（Δ>=5°）",
                      dang >= 5.0, f"Δ={dang:.1f}°")

        for label, m in (("P1", pmats[0]), ("P2", pmats[1]), ("P3", pmats[2]),
                         ("A1", amats[0]), ("A2", amats[1]), ("A3", amats[2])):
            bed, want = bed_contact_ok(m)
            rep.check(f"{label} 底面贴床", bed, f"tz={m[11]:.2f} want={want}")
        rep.check("终态旋转正交", rows_orthonormal(pmats[2])
                  and rows_orthonormal(amats[2]))
        rep.check("平移稳定（原地旋转）",
                  all(abs(m[9] - pmats[0][9]) <= 0.5
                      and abs(m[10] - pmats[0][10]) <= 0.5
                      for m in pmats + amats),
                  f"p={pmats[0][9:11]} a={amats[0][9:11]}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#191"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
