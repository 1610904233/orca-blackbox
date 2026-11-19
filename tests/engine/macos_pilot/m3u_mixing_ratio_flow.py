#!/usr/bin/env python3
# m3u_mixing_ratio_flow.py — macOS port: Feishu #78/#43 Ratio-mode round trip.
# feishu: baseline#78  (macOS port; corresponds to the enabled Windows
#         m3u_mixing_ratio_flow, registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   #5 a recommendation preset fills 50:50
#   #6 CONFIRM registers the scheme (a new sidebar entry)
#   #7/#43 single-clicking the entry opens Edit Mix with the stored params
#          (Ratio active, 50/50 preserved)
#   - confirming an edit updates the label in place
#   #8 CANCEL abandons both adds and edits
#
# macOS mapping:
#   add mix  -> teal + at (388,521); row 1 combo at (566,255), pick a PLA at
#               (558,321) to clear the cross-type banner; a recommendation
#               swatch below 'Mixing Recommendations' (first saturated square,
#               measured (458,639)) sets 50/50; OK at (672,707)
#   entries  -> sidebar labels (x<330, 530<y<660) e.g. F3 50%+F2 50%
#   edit mix -> clicking a label opens a window titled 'Edit Mix' with the
#               same geometry; the ratio bar sits ~18px above the legends
#               (window-relative y 367 when the legends are at 385)
#
# Artifacts: artifacts/mac/pilot/m3u/{report.log,result.json,*.png}.

from __future__ import annotations

import argparse
import colorsys
import re
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

from harness.platform.base import Rect  # noqa: E402
from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import recognize_text  # noqa: E402
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus, wait_for_model,
)

OUT = ARTIFACTS / "pilot" / "m3u"
DEFAULT_MODEL = HERE / "fixtures" / "mixed_filament_test.3mf"
ADD_BTN = (388, 521)


def mix_window(driver, app, win, needle):
    for w in driver.windows_for_pid(app.pid):
        if (w.on_screen and w.id != win.id and w.layer != 0
                and needle in (w.title or "").lower()):
            return w
    return None


def dlg_words(driver, win, dlg):
    return recognize_text(
        driver.capture_screen().crop(win.rect),
        Rect(dlg.rect.x - win.rect.x, dlg.rect.y - win.rect.y,
             dlg.rect.w, dlg.rect.h))


def entry_labels(driver, win):
    return [(w.text.strip(), w.rect) for w in recognize_text(driver.capture(win))
            if w.rect.x < 330 and 530 < w.rect.y < 660
            and re.search(r"\d+%", w.text)]


def legends(driver, win, dlg):
    out = []
    for w in dlg_words(driver, win, dlg):
        if "%" not in w.text:
            continue
        m = re.search(r"(\d+)%", w.text)
        if m:
            out.append((int(m.group(1)), w.rect))
    return out


def bar_y(legs):
    return (min(r.y for _v, r in legs) - 18) if legs else 367


def find_swatch(driver, win, dlg):
    frame = driver.capture(win)
    width = frame.width
    for y in range(600, min(frame.height, 720), 3):
        run = 0
        start = None
        for x in range(440, min(width, 700)):
            i = (y * width + x) * 4
            b, g, r = frame.data[i], frame.data[i + 1], frame.data[i + 2]
            _h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            hot = s > 0.45 and v > 0.45
            if hot and run == 0:
                start = x
            if hot:
                run += 1
            else:
                if run >= 12 and start is not None:
                    return (start + run // 2, y)
                run = 0
                start = None
    return None


def make_compatible(driver, win, dlg):
    driver.click(win.rect.x + 566, win.rect.y + 255)
    time.sleep(1.0)
    driver.click(win.rect.x + 558, win.rect.y + 321)
    time.sleep(1.5)
    text = " ".join(w.text for w in dlg_words(driver, win, dlg)).lower()
    return "cannot be mixed" not in text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    args = ap.parse_args()

    if args.datadir.exists():
        shutil.rmtree(args.datadir, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    rep = Reporter(OUT)
    rep.log("=== m3u macOS Ratio-mode round trip ===")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=DEFAULT_MODEL,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True, f"pid={app.pid} title={win.title!r}")
        ok, _f, frac, _seen = wait_for_model(
            driver, app, win, timeout_s=120.0, threshold=0.03)
        rep.check("multicolor project loads", ok, f"colored={frac:.4f}")
        if not ok:
            return rep.save({"stage": "load"})
        base = entry_labels(driver, win)
        rep.log(f"[INFO] base entries={[(t, r.to_xywh()) for t, r in base]}")
        rep.check("seeded entry present", len(base) >= 1,
                  f"entries={[t for t, _r in base]}")

        # --- #5/#6: recommendation badge -> 50/50 -> OK registers ---------
        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg = mix_window(driver, app, win, "add mix")
        rep.check("add mix dialog opens", dlg is not None,
                  dlg.rect.to_xywh() if dlg else "")
        if dlg is None:
            return rep.save({"stage": "dialog"})
        rep.check("compatible pair selectable", make_compatible(driver, win, dlg))
        sw = find_swatch(driver, win, dlg)
        rep.log(f"[INFO] recommendation swatch={sw}")
        rep.check("recommendation badge found", sw is not None)
        if sw is None:
            return rep.save({"stage": "swatch"})
        driver.click(win.rect.x + sw[0], win.rect.y + sw[1])
        time.sleep(1.0)
        legs = legends(driver, win, dlg)
        values = sorted(v for v, _r in legs)
        rep.log(f"[INFO] legends after badge={legs}")
        rep.check("#5 推荐预设填充 50/50", values == [50, 50] or values[-2:] == [50, 50],
                  f"values={values}")
        driver.capture(win).save_png(OUT / "ratio_5050.png")
        driver.click(win.rect.x + 672, win.rect.y + 707)   # OK
        time.sleep(2.0)
        ents = entry_labels(driver, win)
        rep.log(f"[INFO] entries after OK={[(t, r.to_xywh()) for t, r in ents]}")
        new = [e for e in ents if e[0] not in {t for t, _r in base}]
        rep.check("#6 OK 注册新方案", len(ents) == len(base) + 1 and bool(new),
                  f"entries={[t for t, _r in ents]}")
        if not new:
            return rep.save({"stage": "register"})
        label, rect = new[0]
        rep.check("新方案标签为 50/50",
                  "50%" in label and label.count("50%") == 2, label)

        # --- #7/#43: click the entry -> Edit Mix with 50/50 ----------------
        driver.click(win.rect.x + rect.center[0], win.rect.y + rect.center[1])
        time.sleep(1.5)
        edit = mix_window(driver, app, win, "edit mix")
        rep.check("#7 条目打开 Edit Mix", edit is not None,
                  edit.rect.to_xywh() if edit else "")
        if edit is None:
            return rep.save({"stage": "edit"})
        legs = legends(driver, win, edit)
        values = sorted(v for v, _r in legs)
        rep.check("#43 Edit Mix 保持 Ratio + 50/50",
                  values == [50, 50] or values[-2:] == [50, 50],
                  f"values={values}")

        # --- edit -> 90/10 -> OK updates the label ------------------------
        driver.click(win.rect.x + 450, win.rect.y + bar_y(legs))
        time.sleep(1.0)
        legs = legends(driver, win, edit)
        values = sorted(v for v, _r in legs)
        rep.log(f"[INFO] edit legends={values}")
        rep.check("编辑比例到 90/10", 90 in values and 10 in values,
                  f"values={values}")
        driver.click(win.rect.x + 672, win.rect.y + 707)   # OK
        time.sleep(2.0)
        ents2 = entry_labels(driver, win)
        rep.log(f"[INFO] entries after edit OK={[(t, r.to_xywh()) for t, r in ents2]}")
        edited = [e for e in ents2 if "90%" in e[0] and "10%" in e[0]]
        rep.check("编辑后标签原地更新（90/10）", bool(edited),
                  f"entries={[t for t, _r in ents2]}")
        if not edited:
            return rep.save({"stage": "edit-ok"})
        edited_label, edited_rect = edited[0]

        # --- edit -> change -> Cancel leaves the label --------------------
        driver.click(win.rect.x + edited_rect.center[0],
                     win.rect.y + edited_rect.center[1])
        time.sleep(1.5)
        edit2 = mix_window(driver, app, win, "edit mix")
        rep.check("重开 Edit Mix", edit2 is not None)
        if edit2 is None:
            return rep.save({"stage": "edit2"})
        legs = legends(driver, win, edit2)
        # Click the middle of the bar to move 90/10 towards 50/50.
        driver.click(win.rect.x + 600, win.rect.y + bar_y(legs))
        time.sleep(1.0)
        changed = sorted(v for v, _r in legends(driver, win, edit2))
        rep.log(f"[INFO] edit2 after middle click={changed}")
        rep.check("#8 取消前比例已改变", changed != [10, 90] and changed != [90, 10],
                  f"values={changed}")
        driver.click(win.rect.x + 488, win.rect.y + 709)   # Cancel
        time.sleep(1.5)
        ents3 = entry_labels(driver, win)
        rep.check("#8 Cancel 放弃编辑（标签不变）",
                  any(t == edited_label for t, _r in ents3),
                  f"entries={[t for t, _r in ents3]}")

        # --- add -> change -> Cancel adds nothing -------------------------
        driver.click(win.rect.x + ADD_BTN[0], win.rect.y + ADD_BTN[1])
        time.sleep(1.5)
        dlg3 = mix_window(driver, app, win, "add mix")
        rep.check("再次打开 Add Mix", dlg3 is not None)
        if dlg3 is not None:
            make_compatible(driver, win, dlg3)
            sw3 = find_swatch(driver, win, dlg3)
            if sw3 is not None:
                driver.click(win.rect.x + sw3[0], win.rect.y + sw3[1])
                time.sleep(1.0)
            driver.click(win.rect.x + 488, win.rect.y + 709)   # Cancel
            time.sleep(1.5)
        ents4 = entry_labels(driver, win)
        rep.check("#8 Cancel 放弃新增（条目数不变）",
                  len(ents4) == len(ents3),
                  f"{len(ents3)} -> {len(ents4)}")
        rep.check("app alive", app.alive())

        alive_before = app.alive()
        closed = close_app(driver, app, win)
        app = None
        rep.check("软件正常关闭", alive_before and closed,
                  f"alive_before={alive_before} closed={closed}")
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        exit_code = rep.save({"covered": ["#78"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
