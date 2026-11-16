#!/usr/bin/env python3
# m0_platform_contract.py — Phase B platform-driver contract (macOS first).
# feishu: none  (platform bring-up probe, not a business case)
#
# Standalone probe (NOT a pytest case, NOT in cases.py) that proves the
# platform abstraction's "eyes and hands" without importing any Win32
# module:
#
#   launch -> find main window -> screenshot (non-black / non-blank)
#   -> enumerate native AX controls -> press a safe control
#   -> read the state back -> restore -> close.
#
# Artifacts: artifacts/mac/contract_*.png, contract_controls.txt,
# contract_result.json, contract.log, app_launch.log.
#
# Exit code: 0 = all contract checks PASS, 2 = FAIL.

from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]  # repo root (tests/engine/..)
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness.platform.base import (  # noqa: E402
    ControlRef, DriverNotAvailable,
)
from harness.platform.factory import current_platform, get_driver  # noqa: E402

ARTIFACTS = HERE / "artifacts" / "mac"
SAFE_BUTTON_WORDS = ("view", "prepare", "preview", "fit", "top", "help",
                     "show", "info", "about")
UNSAFE_BUTTON_WORDS = ("quit", "close", "delete", "remove", "exit",
                       "force", "update", "reset", "cancel", "uninstall")


class Reporter:
    def __init__(self, path: Path):
        self.path = path
        self.lines: list[str] = []
        self.checks: list[dict] = []

    def log(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        state = "PASS" if ok else "FAIL"
        self.log(f"[{state}] {name}" + (f": {detail}" if detail else ""))
        self.checks.append({"name": name, "ok": bool(ok),
                            "detail": detail, "state": state})
        return ok

    def save(self, extra: dict | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self.lines) + "\n", encoding="utf-8")
        payload = {"checks": self.checks, "ok": all(c["ok"] for c in self.checks)}
        if extra:
            payload.update(extra)
        (self.path.parent / "contract_result.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")


def _safe_checkbox(controls: list[ControlRef]) -> ControlRef | None:
    for ctl in controls:
        if ctl.role != "AXCheckBox" or not ctl.enabled:
            continue
        if "AXPress" not in ctl.actions:
            continue
        if ctl.rect is None or ctl.rect.area <= 0:
            continue
        value = str(ctl.value).lower()
        if value in ("0", "1", "false", "true"):
            return ctl
    return None


def _safe_textfield(controls: list[ControlRef]) -> ControlRef | None:
    for ctl in controls:
        if ctl.role != "AXTextField" or not ctl.enabled:
            continue
        if ctl.rect is None or ctl.rect.area <= 0:
            continue
        if isinstance(ctl.value, str) and ctl.value:
            return ctl
    return None


def _safe_button(controls: list[ControlRef]) -> ControlRef | None:
    for ctl in controls:
        if ctl.role != "AXButton" or not ctl.enabled:
            continue
        if "AXPress" not in ctl.actions:
            continue
        text = " ".join((ctl.title, ctl.description, ctl.text())).strip().lower()
        if not text:
            continue
        if any(word in text for word in UNSAFE_BUTTON_WORDS):
            continue
        if any(word in text for word in SAFE_BUTTON_WORDS):
            return ctl
    return None


def _find_same_control(driver, win, ref: ControlRef) -> ControlRef | None:
    """Re-enumerate by role + rect (handles rebuilt panels)."""
    if ref.rect is None:
        return None
    for ctl in driver.controls(win):
        if ctl.role != ref.role or ctl.rect is None:
            continue
        if (abs(ctl.rect.x - ref.rect.x) < 4
                and abs(ctl.rect.y - ref.rect.y) < 4
                and abs(ctl.rect.w - ref.rect.w) < 4
                and abs(ctl.rect.h - ref.rect.h) < 4):
            return ctl
    return None


def _dump_controls(controls: list[ControlRef], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ctl in controls:
            fh.write(
                f"{ctl.role}\t{ctl.subrole}\ttitle={ctl.title!r}\t"
                f"desc={ctl.description!r}\tid={ctl.identifier!r}\t"
                f"value={ctl.value!r}\tactions={ctl.actions}\t"
                f"selected={ctl.selected}\tenabled={ctl.enabled}\t"
                f"rect={ctl.rect.to_xywh() if ctl.rect else None}\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", default=None,
                    help="path to Snapmaker Orca.app or its executable")
    ap.add_argument("--datadir", default=ARTIFACTS / "profile", type=Path,
                    help="isolated datadir (seeded if empty)")
    ap.add_argument("--model", default=None, help="optional .3mf/.stl to auto-load")
    ap.add_argument("--timeout", default=150.0, type=float,
                    help="main-window timeout in seconds")
    ap.add_argument("--keep", action="store_true",
                    help="leave the app running after the contract")
    args = ap.parse_args()

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    rep = Reporter(ARTIFACTS / "contract.log")
    rep.log(f"=== m0_platform_contract ===")
    rep.log(f"host_platform={current_platform()} python={sys.version.split()[0]}")
    rep.log(f"exe={args.exe or '<default>'} datadir={args.datadir} model={args.model}")

    app = None
    driver = None
    win = None
    frame_before = None
    frame_after = None
    selected = None
    exit_code = 2
    try:
        try:
            driver = get_driver()
        except DriverNotAvailable as exc:
            rep.check("driver available", False, str(exc))
            return 2
        rep.check("driver available", True,
                  f"{type(driver).__name__} message_input={driver.message_input}")

        try:
            app = driver.launch(
                exe=args.exe, datadir=args.datadir, model=args.model,
                timeout_s=args.timeout, dismiss_wizard=True,
                log_path=ARTIFACTS / "app_launch.log")
        except Exception as exc:  # noqa: BLE001
            rep.check("launch", False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc()
            return 2
        rep.check("launch", True,
                  f"pid={app.pid} bundle={app.bundle_id} blockers={app.extra.get('blockers')}")

        win = app.extra.get("window") or driver.find_main_window(
            app.pid, timeout_s=30.0)
        rect = driver.window_rect(win)
        rep.check("main window", bool(rect),
                  f"id={win.id} title={win.title!r} rect={rect.to_xywh()} "
                  f"scale={driver.dpi_scale(win):.2f}")

        try:
            frame_before = driver.capture(win)
            stats = frame_before.stats()
            frame_before.save_png(ARTIFACTS / "contract_capture_before.png")
            nonblack_ok = stats["nonblack_fraction"] >= 0.01
            nonblank_ok = (stats["mean_luma"] > 2.0
                           and (stats["max_luma"] - stats["min_luma"]) > 4.0)
            rep.check("capture non-black", nonblack_ok,
                      f"{frame_before.width}x{frame_before.height} "
                      f"nonblack={stats['nonblack_fraction']:.4f} "
                      f"mean_luma={stats['mean_luma']:.2f}")
            rep.check("capture non-blank", nonblank_ok,
                      f"min_luma={stats['min_luma']:.2f} "
                      f"max_luma={stats['max_luma']:.2f} "
                      f"colored={stats['colored_fraction']:.4f}")
        except Exception as exc:  # noqa: BLE001
            rep.check("capture non-black", False, f"{type(exc).__name__}: {exc}")
            frame_before = None

        try:
            controls = driver.controls(win)
            _dump_controls(controls, ARTIFACTS / "contract_controls.txt")
            native = [c for c in controls if c.role not in
                      ("AXWindow", "AXMenuBar", "AXGroup", "AXScrollArea",
                       "AXSplitGroup", "AXSplitter")]
            rep.check("controls enumerated", bool(native),
                      f"total={len(controls)} native={len(native)} "
                      f"roles={sorted({c.role for c in native})}")
        except Exception as exc:  # noqa: BLE001
            rep.check("controls enumerated", False, f"{type(exc).__name__}: {exc}")
            controls = []

        selected = _safe_checkbox(controls)
        action_kind = "checkbox"
        if selected is None:
            selected = _safe_textfield(controls)
            action_kind = "textfield"
        if selected is None:
            selected = _safe_button(controls)
            action_kind = "button"

        if selected is None:
            rep.check("safe control found", False,
                      "no checkbox/textfield/safe button in AX tree")
        else:
            rep.check("safe control found", True,
                      f"{action_kind} role={selected.role} "
                      f"title={selected.title!r} desc={selected.description!r} "
                      f"rect={selected.rect.to_xywh() if selected.rect else None}")

            if action_kind == "textfield":
                before_val = driver.control_text(selected)
                probe_text = "contract123"
                ok = driver.set_control_text(selected, probe_text)
                time.sleep(0.8)
                after_val = driver.control_text(selected)
                rep.check("control write", ok,
                          f"set {probe_text!r} -> {after_val!r} "
                          f"(was {before_val!r})")
                rep.check("state read back", probe_text in after_val,
                          f"readback={after_val!r}")
                # best-effort restore
                if before_val:
                    driver.set_control_text(selected, before_val)
            else:
                before_val = driver.control_text(selected)
                ok = driver.click_control(selected)
                time.sleep(1.0)
                after_val = driver.control_text(selected)
                if after_val == before_val:
                    fresh = _find_same_control(driver, win, selected)
                    if fresh is not None:
                        after_val = driver.control_text(fresh)
                try:
                    frame_after = driver.capture(win)
                    frame_after.save_png(
                        ARTIFACTS / "contract_capture_after.png")
                    diff = frame_before.difference(frame_after) \
                        if frame_before is not None else 0.0
                except Exception as exc:  # noqa: BLE001
                    diff = 0.0
                    rep.log(f"[WARN] post-click capture failed: {exc}")
                changed = (after_val != before_val) or diff > 0.002
                rep.check("control pressed", ok,
                          f"{selected.role} press={ok} "
                          f"value {before_val!r} -> {after_val!r}")
                rep.check("state read back", changed,
                          f"value_changed={after_val != before_val} "
                          f"frame_diff={diff:.4f}")
                # best-effort restore (checkbox/button toggle)
                if action_kind == "checkbox" and after_val != before_val:
                    driver.click_control(selected)
                    time.sleep(0.5)
                    restored = driver.control_text(selected)
                    rep.log(f"[INFO] checkbox restored: {restored!r}")

        if args.keep:
            rep.log(f"[INFO] --keep: app pid={app.pid} left running")
            rep.save({"kept": True, "pid": app.pid})
            exit_code = 0
            app = None  # do not terminate in finally
        else:
            try:
                driver.close_window(win)
                deadline = time.monotonic() + 15.0
                while time.monotonic() < deadline and app.alive():
                    time.sleep(0.3)
                method = "window close" if not app.alive() else "terminate"
                if app.alive():
                    app.terminate()
                    time.sleep(0.5)
                rep.check("close", not app.alive(), f"method={method}")
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")

        exit_code = 0 if all(c["ok"] for c in rep.checks) else 2
    finally:
        if app is not None and not args.keep:
            try:
                app.terminate()
            except Exception:
                pass
            try:
                fh = app.extra.get("log_fh")
                if fh:
                    fh.close()
            except Exception:
                pass
        rep.log(f"=== exit {exit_code} ===")
        rep.save({
            "exit_code": exit_code,
            "pid": app.pid if app is not None else None,
            "window": ({"id": win.id, "title": win.title,
                        "rect": win.rect.to_xywh()} if win else None),
            "selected_control": ({"role": selected.role,
                                  "title": selected.title,
                                  "description": selected.description,
                                  "rect": selected.rect.to_xywh() if selected.rect else None}
                                 if selected else None),
        })
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
