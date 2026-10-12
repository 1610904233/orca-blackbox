#!/usr/bin/env python3
# probe_241_usergroup.py — 用户预设分组：行文本被截断（'Snapmaker PLA SnapS...'），
# 试"hover 行 → 读 tooltip"拿全名，作为 disambiguator。
#
# 背景（j436 实测）：空盘启动后槽位已是用户预设（FLOW-TEST），打开选择框左栏是
#   '------ User presets ------' / '~ Custom »' / '------ Add/Remove filament ------'
# 右栏三行都是被截断的 'Snapmaker PLA ...' —— 目标后缀（- STD-TEST）匹配不到。
# 本探针：点进 Custom 分组 → 依次 hover 每个右栏行 → OCR 行下方/右侧的 tooltip →
# 打印看到的全名；顺带 dump 行的 rect（看能不能用位置+tooltip 消歧）。
import argparse
import sys
import time
from pathlib import Path

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE)); sys.path.insert(0, str(_HERE / "tests"))
for _g in sorted((_HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

_LOG_NAME = "pug.log"


def _tee_log(name):
    import sys as _s
    p = Path(__file__).resolve().parents[1] / "artifacts" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p, "w", encoding="utf-8", errors="replace")

    class _T:
        def write(self, s):
            fh.write(s)
            fh.flush()
            try:
                if _s.__stdout__ is not None:
                    _s.__stdout__.write(s)
            except Exception:                                  # noqa: BLE001
                pass

        def flush(self):
            fh.flush()

    _s.stdout = _T()
    _s.stderr = _T()


_tee_log(_LOG_NAME)

from harness import export_util, mix_dialog_util as mdu, winutil  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[pug]"
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 8):rect[3] + 8, max(0, rect[0] - 8):rect[2] + 8]
    cv2.imwrite(str(_HERE / "artifacts" / f"pug_{name}.png"), img)
    print(f"{LOG} shot -> pug_{name}.png")


def ocr_region(rect, scale=3, psm=6):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    x0, y0, x1, y1 = [int(v) for v in rect]
    crop = img[max(0, y0):y1, max(0, x0):x1]
    if crop.size == 0:
        return []
    return [w[0] for w in mdu.ocr_words_img(crop, scale=scale, psm=psm)]


def main() -> int:
    global session
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    args.model = None
    session = boot_session(args, model=None)
    try:
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        slots = m8.wait_slots(session)
        print(f"{LOG} slots: {[(s['slot'], m8.combo_text(s['combo'][2]) if s['combo'] else None) for s in slots]}")
        pop, ch, how = m8._picker_open(session, 2)
        print(f"{LOG} picker open={bool(pop)} via {how!r} combo={m8.combo_text(ch) if ch else None!r}")
        if not pop:
            return 1
        time.sleep(0.9)
        panes = m8._picker_panes(session)
        vend = next((p for p in panes if p["is_vendor"]), None)
        print(f"{LOG} left rows: {[(y, t) for y, t, _x in vend['rows']] if vend else None}")
        # 点 'Custom »'（用户配置分支）
        got = m8._picker_click_text(session, vend["rows"], "custom", startswith=False) if vend else ""
        print(f"{LOG} clicked custom row: {got!r}")
        time.sleep(1.2)
        panes = m8._picker_panes(session)
        filt = next((p for p in panes if not p["is_vendor"]), None)
        print(f"{LOG} after Custom: panes={[(p['rect'], 'V' if p['is_vendor'] else 'F', len(p['rows'])) for p in panes]}")
        if not filt:
            print(f"{LOG} no right pane")
            return 1
        print(f"{LOG} right rows: {[(y, t, x) for y, t, x in filt['rows']]}")
        shot("01_custom_group", filt["rect"])
        # 逐行 hover → 读 tooltip（行下方 + 行右侧两块都试）
        for i, (y, t, x) in enumerate(filt["rows"]):
            hx = max(filt["rect"][0] + 40, x + 60)
            print(f"{LOG} --- hover row {i} {t!r} @({hx},{y})")
            user32.SetCursorPos(int(hx), int(y))
            time.sleep(1.4)
            below = ocr_region((filt["rect"][0] - 10, y + 6, filt["rect"][2] + 330, y + 40))
            right = ocr_region((filt["rect"][2] + 4, y - 20, filt["rect"][2] + 420, y + 24))
            print(f"{LOG}   tooltip below: {below}")
            print(f"{LOG}   text right  : {right}")
            shot(f"02_row{i}_hover", (filt["rect"][0] - 20, y - 30,
                                      filt["rect"][2] + 400, y + 45))
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.05)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.6)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
