#!/usr/bin/env python3
# probe_241_userpreset.py — 2.4.1：用户预设（... - STD-TEST / - FLOW-TEST）在耗材栏里
# 到底出现在哪里？
#
# 已知（10-12）：选择框左栏滚动到顶部后，首行就是 '------ System presets ------'，
# 下面只有厂商 + 'Add/Remove filament'——没有"用户配置/自定义"段。
# 假设 A：用户预设的父预设名在 2.4.1 不存在（STD-TEST inherits
#        'Snapmaker PLA SnapSpeed @U1'，2.4.1 只有 '... @U1 base' / '... @U1 0.8 nozzle'）
#        → 预设加载失败 → 从列表消失（数据问题，不是 UI 路径问题）。
# 假设 B：用户段存在但需要 hover/滚动到别处，或只在槽位已是用户预设时出现。
#
# 本探针：自己起一个实例（seeded datadir，含 user/default 预设），
#   1) 打印 datadir 里 user/default/filament 的文件；
#   2) 打开槽位选择框 → 左栏**滚到顶**再 OCR（scale 3 + 2 两遍）→ 打印所有行；
#   3) 左栏**滚到底**再 OCR → 打印所有行；
#   4) 打印选择框两个 pane 的所有子控件文本（若有）；
#   5) 打印 app 日志里与 preset 加载相关的行（若可读）。
# 只读；最后正常 close（这是自己起的实例）。
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

_LOG_NAME = "puser.log"


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
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[puser]"
ART = _HERE / "artifacts"
user32 = winutil.user32


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1]):rect[3], max(0, rect[0]):rect[2]]
    cv2.imwrite(str(ART / f"puser_{name}.png"), img)
    print(f"{LOG} shot -> puser_{name}.png")


def ocr_rows_multi(rect, scales=(3, 2), psms=(6, 4)):
    seen = []
    for sc in scales:
        for psm in psms:
            try:
                rows = m8._screen_ocr_rows(rect, psm=psm, scale=sc)
            except Exception as exc:                           # noqa: BLE001
                print(f"{LOG}   ocr scale={sc} psm={psm} <{exc!r}>")
                continue
            txt = [t for _y, t, _x in rows]
            key = " | ".join(txt)
            if key and key not in seen:
                seen.append(key)
                print(f"{LOG}   OCR scale={sc} psm={psm} ({len(rows)} rows): {key}")
    return seen


def scroll_pane(rect, notches, times, pause=0.15):
    cx = rect[0] + 60
    cy = (rect[1] + rect[3]) // 2
    for _ in range(times):
        winutil.real_wheel_screen(cx, cy, notches)
        time.sleep(pause)
    time.sleep(0.5)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    datadir = Path(args.datadir)
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        slots = m8.wait_slots(session)
        print(f"{LOG} slots: {[(s['slot'], m8.combo_text(s['combo'][2]) if s['combo'] else None) for s in slots]}")
        print(f"{LOG} user preset files on disk:")
        for p in sorted((datadir / "user" / "default" / "filament").glob("*")):
            print(f"{LOG}   {p.name}  {p.stat().st_size}B")
        pop, ch, how = m8._picker_open(session, 2)
        print(f"{LOG} picker open={bool(pop)} via {how!r}")
        if not pop:
            print(f"{LOG} picker did not open — abort")
            return 1
        time.sleep(0.9)
        for tag, notches, times in (("top", 3, 12), ("bottom", -3, 12), ("top2", 3, 14)):
            panes = m8._picker_panes(session)
            vend = next((p for p in panes if p["is_vendor"]), None)
            if not vend:
                print(f"{LOG} [{tag}] no vendor pane")
                continue
            scroll_pane(vend["rect"], notches, times)
            panes = m8._picker_panes(session)
            vend = next((p for p in panes if p["is_vendor"]), None)
            print(f"{LOG} --- left pane after scroll {tag} (rect={vend['rect'] if vend else None}) ---")
            if vend:
                ocr_rows_multi(vend["rect"])
                shot(f"left_{tag}", vend["rect"])
                kids = [k.strip() for k, _r, _h in export_util._children_texts(vend["hwnd"]) if k.strip()]
                print(f"{LOG}   left pane child texts ({len(kids)}): {kids[:20]}")
        # 右栏也看一眼（Snapmaker 分支下有没有 user 行）
        panes = m8._picker_panes(session)
        filt = next((p for p in panes if not p["is_vendor"]), None)
        if filt:
            print(f"{LOG} --- right pane (current branch) ---")
            ocr_rows_multi(filt["rect"])
            kids = [k.strip() for k, _r, _h in export_util._children_texts(filt["hwnd"]) if k.strip()]
            print(f"{LOG}   right pane child texts ({len(kids)}): {kids[:20]}")
        # app 日志：preset 加载错误
        logs = sorted((datadir / "log").glob("*.log*"))
        print(f"{LOG} log files: {[p.name for p in logs][:6]}")
        for lp in logs[:2]:
            try:
                txt = lp.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            hits = [ln for ln in txt.splitlines()
                    if any(k in ln for k in ("STD-TEST", "FLOW-TEST", "inherits",
                                             "not found", "Invalid preset"))]
            print(f"{LOG}   {lp.name}: {len(hits)} relevant line(s)")
            for ln in hits[:20]:
                print(f"{LOG}     {ln.strip()[:180]}")
        user32.keybd_event(0x1B, 0, 0, 0)
        time.sleep(0.4)
        user32.keybd_event(0x1B, 0, 2, 0)
        time.sleep(0.8)
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
