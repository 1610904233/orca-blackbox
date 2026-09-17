#!/usr/bin/env python3
# diag_m8_bootshot.py — boot the app with the mixed fixture, wait, then
# dump every top-level window (class/title/rect/visible) + one screenshot
# at t=+15s and t=+40s. Answers: does an import-error dialog appear? is
# the bed empty? Attributes the m2 model-arrival failure.

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))

import ctypes  # noqa: E402
from harness import launcher, profile, winutil  # noqa: E402
from harness.anchors import capture_bgr  # noqa: E402
from m3_common import add_common_args  # noqa: E402
from m1_minimal_loop import capture_bgr as cap1  # noqa: E402

LOG = "[bootshot]"
ART = HERE / "artifacts" / "m8_probe"
ART.mkdir(parents=True, exist_ok=True)
user32 = ctypes.WinDLL("user32")


def top_windows(pid):
    out = []
    EnumWindows = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ssize_t,
                                    ctypes.c_ssize_t)

    def cb(hwnd, _lp):
        wpid = ctypes.c_size_t()
        user32.GetWindowThreadProcessId(ctypes.c_void_p(hwnd),
                                        ctypes.byref(wpid))
        if wpid.value == pid:
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(ctypes.c_void_p(hwnd), cls, 64)
            txt = ctypes.create_unicode_buffer(128)
            user32.GetWindowTextW(ctypes.c_void_p(hwnd), txt, 128)
            vis = user32.IsWindowVisible(ctypes.c_void_p(hwnd))
            r = winutil.window_rect(hwnd)
            if vis or txt.value:
                out.append(f"  {cls.value} {txt.value!r} vis={bool(vis)} "
                           f"rect={r}")
        return True

    user32.EnumWindows(EnumWindows(cb), 0)
    return out


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=str(HERE / "fixtures" /
                                           "mixed_filament_test.3mf"))
    args = ap.parse_args()
    datadir = Path(args.datadir)
    profile.seed_profile(datadir, fresh=True)
    session = launcher.launch(exe=args.exe, datadir=datadir,
                              model=args.model, dismiss_wizard=True)
    try:
        for t in (15, 40):
            time.sleep(t if t == 15 else 25)
            print(f"{LOG} --- t=+{t}s top-level windows ---")
            for line in top_windows(session.pid):
                print(line)
            import cv2
            img = cap1(session)
            cv2.imwrite(str(ART / f"bootshot_{t}.png"), img)
        frac = None
        from harness.anchors import has_colored_content
        img = cap1(session)
        frac, _ = has_colored_content(img) if False else (None, None)
        print(f"{LOG} alive={session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
