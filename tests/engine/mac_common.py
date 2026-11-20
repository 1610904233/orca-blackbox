"""Shared helpers for the macOS Phase C chain probes.

These probes are standalone (not registered in cases.py).  They use only the
platform-neutral ``harness.platform`` API, so they also serve as examples for
future macOS case migrations.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]  # repo root
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from harness import macos_video  # noqa: E402
from harness.platform.base import Frame, Rect  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402

ARTIFACTS = HERE / "artifacts" / "mac"


class Reporter:
    def __init__(self, out_dir: Path):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.lines: list[str] = []
        self.checks: list[dict] = []

    def log(self, text: str = "") -> None:
        print(text)
        self.lines.append(text)
        macos_video.mark(text)  # no-op unless a recording is active

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        state = "PASS" if ok else "FAIL"
        self.log(f"[{state}] {name}" + (f": {detail}" if detail else ""))
        self.checks.append({"name": name, "ok": bool(ok),
                            "detail": detail, "state": state})
        return ok

    def save(self, extra: dict | None = None) -> int:
        ok = all(c["ok"] for c in self.checks)
        code = 0 if ok else 2
        self.log(f"=== exit {code} ===")
        (self.out_dir / "report.log").write_text(
            "\n".join(self.lines) + "\n", encoding="utf-8")
        payload = {"checks": self.checks, "ok": ok, "exit_code": code}
        if extra:
            payload.update(extra)
        (self.out_dir / "result.json").write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8")
        return code


def close_stray_color_panel(driver, app, main_win) -> bool:
    """Close an app-owned floating 'Colors' (NSColorPanel) left from boot.

    The panel is a standard floating utility window, so it sits above the main
    window in every recorded frame.  It is normally opened by the colour cases
    themselves (m8b/m8x_153/m3x); a stale restored state can also surface it at
    launch, which both dirties the video and makes the chip-click toggle
    ambiguous.  Only windows owned by this app pid are touched.
    """
    closed = False
    try:
        for win in driver.windows_for_pid(app.pid):
            if win.id == main_win.id or not win.on_screen:
                continue
            if (win.title or "").strip().lower() != "colors":
                continue
            print(f"[mac_common] closing stray Colors panel id={win.id}")
            try:
                driver.close_window(win)
            except Exception as exc:  # noqa: BLE001 - cleanup must not be fatal
                print(f"[mac_common] close Colors failed: {exc}")
            closed = True
            time.sleep(0.3)
    except Exception:
        pass
    return closed


def _wizard_window(driver, pid):
    try:
        for win in driver.windows_for_pid(pid):
            if win.on_screen and (win.title or "").strip().lower() == "setup wizard":
                return win
    except Exception:
        pass
    return None


def _wizard_ocr(driver, win):
    frame = driver.capture_screen().crop(win.rect)
    return frame, recognize_text(frame, timeout_s=20)


def _ocr_word(words, label):
    wanted = label.strip().lower()
    return next((w for w in words if w.text.strip().lower() == wanted), None)


def _wizard_click(driver, win, word, dx: float = 0.0) -> None:
    driver.click(win.rect.x + word.rect.center[0] + dx,
                 win.rect.y + word.rect.center[1])


def complete_setup_wizard(driver, pid, timeout_s: float = 120.0) -> bool:
    """Walk the whole Setup Wizard: region -> UX program -> printer -> filament.

    The wizard is a WebView, so AX exposes only the window; every page is driven
    by OCR on the window pixels.  Defaults: keep Asia-Pacific, decline the UX
    program (Skip), select Snapmaker U1, select all filaments (All), Finish.
    Returns True once the wizard window is gone.  If anything unexpected
    happens the caller's normal `_dismiss_boot_blockers` fallback still closes
    it, so a launch never hangs on the wizard.
    """
    deadline = time.monotonic() + timeout_s
    attempts = 0
    last_page = ""
    while time.monotonic() < deadline:
        win = _wizard_window(driver, pid)
        if win is None:
            print("[mac_common] setup wizard: completed")
            return True
        try:
            frame, words = _wizard_ocr(driver, win)
        except Exception as exc:  # noqa: BLE001 - OCR can time out
            print(f"[mac_common] setup wizard OCR failed: {exc}")
            time.sleep(1.0)
            continue
        text = " ".join(w.text.strip().lower() for w in words)
        page = ("welcome" if "welcome to snapmaker orca" in text else
                "region" if "login region" in text else
                "ux" if "experience improvement" in text else
                "printer" if "printer selection" in text else
                "filament" if "filament selection" in text else "other")
        if page != last_page:
            print(f"[mac_common] setup wizard page: {page}")
            last_page = page
        attempts += 1
        if attempts % 10 == 1:
            print(f"[mac_common] setup wizard text: {text[:140]}")

        if page == "welcome":
            target = _ocr_word(words, "get started")
        elif page == "region":
            target = _ocr_word(words, "next")
        elif page == "ux":
            target = _ocr_word(words, "skip")
        elif page == "printer":
            u1 = _ocr_word(words, "snapmaker u1")
            if u1 is not None:
                try:
                    px = frame.pixel(int(round(u1.rect.x - 5)),
                                     int(round(u1.rect.center[1])))
                except Exception:
                    px = (0, 0, 0, 0)
                # Selected checkboxes paint the theme teal (BGR ~ 0,150,136).
                checked = px[1] > 110 and px[0] < 140
                print(f"[mac_common] setup wizard printer: u1={u1.rect.to_xywh()} "
                      f"px={px} checked={checked}")
                if not checked:
                    # The checkbox is ~5px left of the label's left edge.
                    # (_wizard_click centers on the word, which lands on the
                    # label and does not toggle the web checkbox.)
                    driver.click(win.rect.x + u1.rect.x - 5,
                                 win.rect.y + u1.rect.center[1])
                    time.sleep(1.5)
                    try:
                        frame2, _words2 = _wizard_ocr(driver, win)
                        px2 = frame2.pixel(int(round(u1.rect.x - 5)),
                                           int(round(u1.rect.center[1])))
                        print(f"[mac_common] setup wizard printer: after click px={px2}")
                    except Exception as exc:
                        print(f"[mac_common] setup wizard printer recheck: {exc}")
            target = _ocr_word(words, "next")
        elif page == "filament":
            if "at least one filament" in text:
                yes = _ocr_word(words, "yes")
                if yes is not None:
                    _wizard_click(driver, win, yes)
                    time.sleep(0.6)
                    continue
            alls = [w for w in words if w.text.strip().lower() == "all"]
            select_all = None
            if alls:
                # The big "All" select button sits under the vendor filters
                # (measured y~241); the filter checkboxes are higher up.
                preferred = [w for w in alls
                             if 200 <= w.rect.center[1] <= 300
                             and w.rect.center[0] < 150]
                select_all = (preferred or sorted(
                    alls, key=lambda w: w.rect.center[1]))[-1]
            if select_all is not None:
                print(f"[mac_common] setup wizard filament: select-all="
                      f"{select_all.rect.to_xywh()}")
                _wizard_click(driver, win, select_all)
                time.sleep(0.8)
                target = _ocr_word(words, "finish")
            else:
                target = _ocr_word(words, "finish")
        else:
            target = None
            for cand in ("next", "finish", "done", "complete", "ok", "yes"):
                target = _ocr_word(words, cand)
                if target is not None:
                    break

        if target is None:
            print(f"[mac_common] setup wizard: no action on page: {text[:120]}")
            time.sleep(0.8)
            continue
        print(f"[mac_common] setup wizard: click {target.text!r}")
        _wizard_click(driver, win, target)
        time.sleep(1.0)

    print("[mac_common] setup wizard: timed out")
    return _wizard_window(driver, pid) is None


def launch_and_focus(driver, datadir: Path, model: Path | None = None,
                     timeout_s: float = 150.0, log_path: Path | None = None):
    """Launch with an isolated datadir and bring the app forward for real clicks."""
    case_name = Path(sys.argv[0]).stem

    def _start_video(_win) -> bool:
        # Returning True makes the launcher hold the Setup Wizard/homepage for
        # ~2s so it is present in the first recorded frames.
        return macos_video.start(driver, case=case_name) is not None

    # Record as soon as the main window exists but before the launcher dismisses
    # boot blockers (Setup Wizard / homepage), so the video starts at boot.
    app = driver.launch(datadir=datadir, model=model, timeout_s=timeout_s,
                        dismiss_wizard=True, log_path=log_path,
                        on_window_found=_start_video,
                        handle_wizard=lambda pid, _w: complete_setup_wizard(
                            driver, pid))
    win = app.extra.get("window") or driver.find_main_window(app.pid, timeout_s=30)
    driver.set_foreground(win)
    time.sleep(0.8)
    driver.window_rect(win)  # refresh geometry after activation
    close_stray_color_panel(driver, app, win)
    return app, win


def close_app(driver, app, win) -> bool:
    """Close the window, wait, then terminate; returns True when gone."""
    try:
        driver.close_window(win)
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and app.alive():
            time.sleep(0.3)
    except Exception:
        pass
    if app.alive():
        app.terminate()
        time.sleep(0.5)
    fh = app.extra.get("log_fh")
    if fh:
        try:
            fh.close()
        except Exception:
            pass
    macos_video.stop("close_app")
    return not app.alive()


def frame_ok(frame: Frame, min_nonblack: float = 0.01,
             min_luma: float = 2.0) -> tuple[bool, dict]:
    stats = frame.stats()
    ok = (stats["nonblack_fraction"] >= min_nonblack
          and stats["mean_luma"] > min_luma
          and (stats["max_luma"] - stats["min_luma"]) > 4.0)
    return ok, stats


def wait_for_model(driver, app, win, *, timeout_s: float = 60.0,
                   threshold: float = 0.03, poll_s: float = 1.0):
    """Wait for the 3D viewport's chromatic content to reach the model threshold.

    Returns (ok, frame, colored_fraction, seen_dialog_ids).  Two consecutive
    polls above threshold rule out transient UI animation.
    """
    deadline = time.monotonic() + timeout_s
    last_frame = None
    last_frac = 0.0
    seen: set = set()
    while time.monotonic() < deadline:
        seen = dismiss_dialogs(driver, app, win, seen)
        frame = driver.capture(win)
        frac = frame.stats()["colored_fraction"]
        last_frame, last_frac = frame, frac
        if frac >= threshold:
            time.sleep(poll_s)
            frame2 = driver.capture(win)
            frac2 = frame2.stats()["colored_fraction"]
            if frac2 >= threshold:
                return True, frame2, max(frac, frac2), seen
        time.sleep(poll_s)
    return False, last_frame, last_frac, seen


def recover_saved_file(target: Path, started: float, roots,
                       *, timeout_s: float = 6.0) -> Path | None:
    """Move a just-saved file that landed in the wrong folder into ``target``.

    macOS shares the NSSavePanel "recent places" across datadirs, so a Save
    Project as... panel can open in the *previous* case's ``work`` folder even
    though the driver gets the right file name.  Search the allowed roots for
    a fresh file with the target stem and move it to the requested path.
    """
    target = Path(target)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if target.exists():
            return target
        candidates: list[Path] = []
        for root in roots:
            root = Path(root)
            if not root.is_dir():
                continue
            try:
                for cand in root.rglob(target.stem + "*"):
                    try:
                        if (cand.is_file() and cand != target
                                and cand.stat().st_mtime >= started - 2.0):
                            candidates.append(cand)
                    except OSError:
                        continue
            except OSError:
                continue
        if candidates:
            candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            src = candidates[0]
            try:
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(target))
                print(f"[mac_common] recovered save {src} -> {target}")
                return target
            except OSError as exc:
                print(f"[mac_common] save recovery move failed: {exc}")
                return None
        time.sleep(0.5)
    return None


def export_gcode_enabled(driver, win) -> bool:
    """File > Export G-code... is enabled only after a completed slice."""
    item = driver.find_control(win, role="AXMenuItem",
                               title="Export G-code", timeout_s=2)
    return item is not None and item.enabled


def slice_and_export(driver, win, rep, gcode: Path, search_roots,
                     *, timeout_s: float = 240.0, on_poll=None) -> bool:
    """Click Slice plate, wait for Export G-code, export through the panel.

    The export panel remembers a global last-used folder and its Save button
    does not commit through AXPress, so use accept_anywhere + fresh-file
    discovery (m8x_158 recipe).
    """
    sx = win.rect.w / 1200.0
    sy = win.rect.h / 800.0
    driver.click(win.rect.x + 1000 * sx, win.rect.y + 45 * sy)
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if on_poll is not None:
            try:
                on_poll()
            except Exception:
                pass
        if export_gcode_enabled(driver, win):
            break
        time.sleep(3.0)
    else:
        rep.log("[INFO] slice did not finish before the export gate")
        return False
    rows = [c for c in driver.controls(win, max_depth=12)
            if c.role == "AXMenuItem"
            and c.title.strip().lower().startswith("export g-code")]
    if not rows or not rows[0].enabled:
        return False
    driver.click_control(rows[0])
    time.sleep(1.5)
    # The export panel remembers a GLOBAL last-used folder; a user session can
    # leave it on ~/Desktop.  Include the standard folders so accept_anywhere
    # still finds (and moves) the freshly written file.
    roots = list(search_roots)
    for extra in (Path.home() / "Desktop", Path.home() / "Documents"):
        if extra.is_dir() and extra not in roots:
            roots.append(extra)
    saved = driver.save_file_dialog(
        win, gcode, default_dir=gcode.parent, accept_anywhere=True,
        search_roots=roots)
    return saved and gcode.exists() and gcode.stat().st_size > 0


def teal_fraction(frame: Frame, rect: Rect) -> float:
    """Fraction of teal pixels (active wx notebook tab colour 0,150,136)."""
    crop = frame.crop(rect)
    data = crop.data
    n = teal = 0
    for i in range(0, len(data), 4):
        b, g, r = data[i], data[i + 1], data[i + 2]
        n += 1
        if g > 110 and g > r + 40 and g > b + 5:
            teal += 1
    return teal / n if n else 0.0


def dismiss_dialogs(driver, app, main_win, seen: set | None = None) -> set:
    """Press Confirm/OK on filament-grouping / warning dialogs if they appear."""
    seen = seen if seen is not None else set()
    try:
        windows = driver.windows_for_pid(app.pid)
    except Exception:
        return seen
    for win in windows:
        if win.id == main_win.id or not win.on_screen or win.rect.area < 1000:
            continue
        if win.id in seen:
            continue
        title = (win.title or "").lower()
        if not any(k in title for k in ("filament", "group", "confirm",
                                        "slice", "warning", "preset",
                                        "delete", "remove", "clear")):
            continue
        seen.add(win.id)
        print(f"[mac_common] dialog: id={win.id} title={win.title!r}")
        for label in ("Confirm", "Delete", "Remove", "OK", "Yes",
                      "Got it", "Continue", "Close"):
            try:
                btn = driver.find_control(win, role="AXButton", title=label,
                                          timeout_s=0)
            except Exception:
                btn = None
            if btn is not None:
                print(f"[mac_common] press {label!r}: "
                      f"{driver.click_control(btn)}")
                time.sleep(1.0)
                break
    return seen
