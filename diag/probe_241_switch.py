#!/usr/bin/env python3
# probe_241_switch.py — 验证新的两级导航原语（m8_common.switch_filament_preset）
#
# 依序验证：
#   1) 'Generic ABS'        —— 系统预设 → Generic → ABS
#   2) 'Snapmaker PLA Silk' —— 系统预设 → Snapmaker → PLA Silk
#   3) '- ST'               —— 用户预设（用户配置 → 自定义 → Snapmaker PLA SnapSpeed @U1 - STD-TEST）
# 每步打印返回的 combo 文本 + 截图；不改工程、不保存。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[sw241]"
ART = HERE / "artifacts"


def shot(name):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4), cv2.COLOR_BGRA2BGR)
    ART.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(ART / f"m8xSW_{name}.png"), img)
    print(f"{LOG} shot -> m8xSW_{name}.png")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        slots = m8.wait_slots(session)
        print(f"{LOG} slots before: {[(s['slot'], s['combo'][0]) for s in slots]}")
        shot("00_before")
        for target in ("Generic ABS", "Snapmaker PLA Silk", "- ST"):
            t0 = time.monotonic()
            got = m8.switch_filament_preset(session, 2, target)
            dt = time.monotonic() - t0
            print(f"{LOG} switch({target!r}) -> {got!r}  [{dt:.0f}s]")
            shot("after_" + target.replace(" ", "_").replace("-", ""))
        slots = m8.wait_slots(session)
        print(f"{LOG} slots after: {[(s['slot'], s['combo'][0]) for s in slots]}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
