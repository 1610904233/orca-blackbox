#!/usr/bin/env python3
# m3k_mixing_match.py — macOS port: Feishu #95/#107 colour matching in the
# mixing dialog.
# feishu: baseline#95 baseline#107  (macOS port; corresponds to the enabled
#         Windows m3k_mixing_match, registered in cases.MACOS_BASELINE)
# The Windows case's step labels #10/#15/#27 are not Feishu baseline numbers;
# Feishu #10/#15 are unrelated detector cases (mac status 不适用).
#
# Windows assertions:
#   #10 switch the Match Mode combo from Auto to Manual (text-confirmed)
#   #15 Start Matching renders the colour-mapping result view
#   #27 Confirm closes the dialog and the app stays alive
#
# macOS mapping:
#   entry  -> the sidebar "Color Mixing Match" link opens a SEPARATE window
#             (title 'Color Mixing Match', layer 8, ~500x728)
#   combo  -> the self-drawn Match Mode combo at window-relative
#             (482,119); its dropdown lists Auto/Manual right below it
#   result -> the dialog's "Matched" preview turns from a grey gradient into
#             coloured swatches; the Color Mapping rows and the gamut banner
#             ("The mix ratios for N ... outside the recommended ranges")
#             appear, and Confirm is enabled
#   confirm-> closes the dialog window
#
# #95 uses Manual (its Feishu flow), #107 uses Auto from the start:
#   #107 Auto -> Start Matching -> Rematch (starts the next match directly)
#        -> Confirm -> dialog closes -> the sidebar Color Mixing list gains the
#        mapped mixed filaments and the plate model changes colour.
# The two cases use separate app sessions so #95's manual dialog is never
# reused for #107.
#
# The shared mixed_filament_test.3mf is a 0.8-nozzle project (also used by the
# Windows cases); Auto matching only supports 0.4.  make_04_project() rewrites
# a copy to the user's real 0.4 project: printer_settings_id/print_settings_id
# are switched (not just the Printer panel's Diameter field) and the Snapmaker
# slots use the official Snapmaker PLA Full Spectrum @U1 0.4 nozzle preset.
#
# Artifacts: artifacts/mac/pilot/m3k/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
import colorsys
import json
import re
import shutil
import subprocess
import sys
import time
import traceback
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
PILOTS = Path(__file__).resolve().parent         # tests/engine/macos_pilot
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3k"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
MATCHED_PREVIEW = Rect(585, 345, 195, 160)   # window-relative
PLATE_REGION = Rect(430, 80, 770, 620)       # main canvas, right of sidebar
MIX_ENTRY = re.compile(r"[Ff]\d+\s+\d+%")


def make_04_project(src: Path, dst: Path) -> None:
    """Copy the 0.8 mixed fixture and switch the real preset ids to 0.4.

    Auto matching rejects non-0.4 nozzles (the app says "Automatic color mixing
    matching is not supported for the current nozzle diameter"), and changing
    only the Printer panel's Diameter leaves the project on the 0.8 preset:
    Auto then yields a grey Matched preview (sat ~0.04) and Confirm does not
    apply.  The rewrite mirrors the user's project: Snapmaker U1 (0.4 nozzle),
    0.24mm process and Snapmaker PLA Full Spectrum @U1 0.4 nozzle filaments.
    """
    mapping = {
        "Generic PETG @U1 0.8 nozzle": (
            "Generic PETG @U1 0.4 nozzle", "GFSG00_01"),
        "Snapmaker PLA Silk @U1 0.8 nozzle": (
            "Snapmaker PLA Full Spectrum @U1 0.4 nozzle", "1195313935011"),
    }
    with zipfile.ZipFile(src) as zin, \
            zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for entry in zin.infolist():
            data = zin.read(entry.filename)
            if entry.filename == "Metadata/project_settings.config":
                cfg = json.loads(data.decode("utf-8"))
                cfg["printer_settings_id"] = "Snapmaker U1 (0.4 nozzle)"
                cfg["printer_variant"] = "0.4"
                cfg["nozzle_diameter"] = ["0.4"] * 4
                cfg["print_compatible_printers"] = [
                    "Snapmaker U1 (0.4 nozzle)"]
                cfg["print_settings_id"] = (
                    "0.24mm Standard @Snapmaker U1 (0.4 nozzle)")
                cfg["default_print_profile"] = cfg["print_settings_id"]
                names: list[str] = []
                ids: list[str] = []
                for old, old_id in zip(cfg["filament_settings_id"],
                                        cfg["filament_ids"]):
                    name, sid = mapping.get(
                        old, (old.replace("@U1 0.8 nozzle",
                                          "@U1 0.4 nozzle"), None))
                    names.append(name)
                    ids.append(sid or old_id)
                cfg["filament_settings_id"] = names
                cfg["filament_ids"] = ids
                cfg["filament_vendor"] = ["Snapmaker"] * len(names)
                cfg["filament_type"] = ["PLA"] * len(names)
                data = json.dumps(cfg, indent=4).encode("utf-8")
            zout.writestr(entry, data)


def mixing_window(driver, app, win):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.id != win.id and w.layer != 0
                and "color mixing match" in (w.title or "").lower()):
            return w
    return None


def dlg_words(driver, win, dlg):
    """Window-relative OCR boxes for the dialog (frame = crop(win.rect))."""
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def find(words, needle):
    for w in words:
        if needle in w.text.lower():
            return w
    return None


def click_word(driver, win, word, tag):
    driver.click(win.rect.x + word.rect.center[0],
                 win.rect.y + word.rect.center[1])
    print(f"[m3k] click {tag!r} ({word.text!r})")


def sat_share(frame) -> float:
    n = hit = 0
    for y in range(int(MATCHED_PREVIEW.y),
                   int(MATCHED_PREVIEW.bottom), 2):
        for x in range(int(MATCHED_PREVIEW.x),
                       int(MATCHED_PREVIEW.right), 2):
            if y >= frame.height or x >= frame.width:
                continue
            i = (y * frame.width + x) * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            _h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            n += 1
            if s > 0.25 and v > 0.25:
                hit += 1
    return hit / max(1, n)


def diff_fraction(a, b, rect: Rect, threshold: int = 40) -> float:
    """Share of pixels whose max channel changed (plate model redraw)."""
    n = changed = 0
    for y in range(int(rect.y), int(rect.bottom), 2):
        for x in range(int(rect.x), int(rect.right), 2):
            if y >= a.height or x >= a.width or y >= b.height or x >= b.width:
                continue
            i = (y * a.width + x) * 4
            d = max(abs(a.data[i + c] - b.data[i + c]) for c in range(3))
            n += 1
            if d > threshold:
                changed += 1
    return changed / max(1, n)


def mixed_entries(words) -> int:
    """Count sidebar Color Mixing ratio rows (e.g. 'F1 47%+F3 53%')."""
    side = " ".join(w.text for w in words if w.rect.x < 430)
    return len(MIX_ENTRY.findall(side))


def wait_matched(driver, win, dlg, rep, tag, timeout_s: float = 60.0):
    """Wait for a completed match: coloured preview + Color Mapping rows."""
    deadline = time.time() + timeout_s
    after = 0.0
    words: list = []
    while time.time() < deadline:
        time.sleep(2.0)
        words = dlg_words(driver, win, dlg)
        after = sat_share(driver.capture(win))
        rep.log(f"[INFO] {tag} poll sat={after:.3f} "
                f"color_mapping={find(words, 'color mapping') is not None}")
        if after > 0.10 and find(words, "color mapping") is not None:
            return True, words, after
    return False, words, after


def confirm_dialog(driver, app, win, dlg, rep, tag) -> bool:
    """Press Confirm and wait for the dialog to close (updating may lag)."""
    words = dlg_words(driver, win, dlg)
    confirm = find(words, "confirm")
    if confirm is None:
        rep.log(f"[INFO] {tag} Confirm missing")
        return False
    click_word(driver, win, confirm, "Confirm")
    deadline = time.time() + 30.0
    while time.time() < deadline:
        time.sleep(1.0)
        if mixing_window(driver, app, win) is None:
            return True
        # A replacement warning may sit on top of / inside the dialog.
        try:
            words = dlg_words(driver, win, dlg)
        except Exception:
            words = []
        for label in ("continue", "yes", "ok"):
            extra = find(words, label)
            if extra is not None and find(words, "confirm") is None:
                click_word(driver, win, extra, label.title())
                break
        for w in driver.windows_for_pid(app.pid):
            if w.id in (win.id, dlg.id) or not w.on_screen:
                continue
            try:
                other = recognize_text(driver.capture_screen().crop(w.rect))
            except Exception:
                continue
            text = " ".join(t.text for t in other).lower()
            rep.log(f"[INFO] {tag} extra window {w.title!r}: {text[:120]}")
            for label in ("continue", "yes", "ok"):
                extra = find(other, label)
                if extra is not None:
                    driver.click(w.rect.x + extra.rect.center[0],
                                 w.rect.y + extra.rect.center[1])
                    break
    return mixing_window(driver, app, win) is None


def run_mixing_session(driver, datadir: Path, model: Path, manual: bool,
                       rep, tag: str) -> bool:
    """One app session.  #95 uses Manual; #107 uses Auto from the start."""
    app = None
    win = None
    try:
        app, win = launch_and_focus(
            driver, datadir, model=model, timeout_s=150.0,
            log_path=datadir.parent / f"app_launch_{tag}.log")
        rep.check(f"{tag} launch", True,
                  f"pid={app.pid} title={win.title!r}")
        ok, frame, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        frame.save_png(OUT / f"{tag}_loaded.png")
        rep.check(f"{tag} 模型载入（0.4 混色夹具）", ok,
                  f"colored={frac:.4f}")
        if not ok:
            return False
        loaded_frame = frame
        before_words = recognize_text(frame)
        before_mixes = mixed_entries(before_words)
        side = " ".join(w.text for w in before_words if w.rect.x < 430)
        rep.log(f"[INFO] {tag} sidebar={side!r}")
        rep.check(f"{tag} 0.4 工程预设（Printer/工艺）",
                  "0.4mm" in side and "0.24" in side, side[:160])

        entry = next((w for w in before_words
                      if "color mixing match" in w.text.lower()
                      and w.rect.x < 500), None)
        rep.check(f"{tag} 混色入口", entry is not None)
        if entry is None:
            return False
        click_word(driver, win, entry, "Color Mixing Match")
        time.sleep(1.5)
        dlg = mixing_window(driver, app, win)
        rep.check(f"{tag} 混色对话框窗口", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return False

        words = dlg_words(driver, win, dlg)
        rep.check(f"{tag} 对话框内容（Match Mode / Start Matching）",
                  find(words, "match mode") is not None
                  and find(words, "start matching") is not None,
                  [w.text for w in words][:10])
        if manual:
            mode = find(words, "auto")
            rep.check(f"{tag} 默认 Auto", mode is not None)
            if mode is None:
                return False
            click_word(driver, win, mode, "Auto combo")
            time.sleep(1.0)
            words = dlg_words(driver, win, dlg)
            manual_opt = find(words, "manual")
            rep.check(f"{tag} 下拉出现 Manual", manual_opt is not None)
            if manual_opt is None:
                return False
            click_word(driver, win, manual_opt, "Manual")
            time.sleep(1.0)
            words = dlg_words(driver, win, dlg)
            rep.check(f"{tag} 已切到 Manual",
                      find(words, "manual") is not None
                      and find(words, "match mode") is not None)
        else:
            rep.check(f"{tag} 默认 Match Mode = Auto",
                      find(words, "auto") is not None,
                      f"mode={[w.text for w in words if 100 < w.rect.y < 140]}")
        start = find(words, "start matching")
        rep.check(f"{tag} Start Matching 可点击", start is not None)
        if start is None:
            return False
        before = sat_share(driver.capture(win))
        click_word(driver, win, start, "Start Matching")
        ok, words, after = wait_matched(driver, win, dlg, rep, tag)
        driver.capture(win).save_png(OUT / f"{tag}_matched.png")
        rep.check(f"{tag} 匹配后视图渲染（{before:.3f} -> {after:.3f}）",
                  ok and after - before > 0.03)
        rep.check(f"{tag} Color Mapping 列表/警告出现",
                  find(words, "color mapping") is not None
                  and find(words, "→") is not None,
                  f"ocr={[w.text for w in words][-12:]}")
        if not ok:
            return False

        if not manual:
            # Auto's second match: Rematch starts it directly (no Start
            # Matching click), as in the user's recorded flow.
            rematch = find(words, "rematch")
            rep.check(f"{tag} Rematch 可点击", rematch is not None)
            if rematch is None:
                return False
            click_word(driver, win, rematch, "Rematch")
            ok2, words, after2 = wait_matched(
                driver, win, dlg, rep, f"{tag} rematch")
            driver.capture(win).save_png(OUT / f"{tag}_rematched.png")
            rep.check(f"{tag} Rematch 后匹配完成（sat={after2:.3f}）",
                      ok2 and after2 > 0.10)
            if not ok2:
                return False

        gone = confirm_dialog(driver, app, win, dlg, rep, tag)
        rep.check(f"{tag} Confirm 关闭对话框", gone)
        if not gone:
            return False
        rep.check(f"{tag} 应用仍存活", app.alive())
        time.sleep(2.0)
        if not manual:
            after_frame = driver.capture(win)
            after_frame.save_png(OUT / f"{tag}_applied.png")
            after_words = recognize_text(after_frame)
            after_mixes = mixed_entries(after_words)
            rep.check(f"{tag} 颜色映射结果生效（Color Mixing 混色耗材）",
                      after_mixes > before_mixes and after_mixes >= 2,
                      f"mixed entries {before_mixes} -> {after_mixes}")
            changed = diff_fraction(loaded_frame, after_frame, PLATE_REGION)
            rep.check(f"{tag} 模型颜色更新（画布像素变化）",
                      changed > 0.01, f"changed={changed:.4f}")
        return True
    finally:
        if app is not None:
            try:
                close_app(driver, app, win)
            except Exception:
                pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m3k macOS mixing match (#95 manual / #107 auto) ===")
    driver = None
    exit_code = 2
    work = OUT / "work"
    for d in (OUT / "profile95", OUT / "profile107", work):
        if d.exists():
            shutil.rmtree(d, ignore_errors=True)
    work.mkdir(parents=True)
    model = work / "m3k_04.3mf"
    try:
        make_04_project(DEFAULT_MODEL, model)
        rep.check("夹具切换为 0.4 工程", model.exists())
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        ok95 = run_mixing_session(driver, OUT / "profile95", model, True,
                                  rep, "#95")
        ok107 = run_mixing_session(driver, OUT / "profile107", model, False,
                                   rep, "#107")
        if not ok95 or not ok107:
            return rep.save({"stage": "session"})
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        subprocess.run(
            ["pkill", "-f", "Snapmaker_Orca --datadir"], capture_output=True)
        exit_code = rep.save({"covered": ["#95", "#107"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
