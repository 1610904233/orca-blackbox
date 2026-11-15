#!/usr/bin/env python3
# m0_platform_contract.py — platform driver contract smoke (macOS port Phase 0).
# feishu: none  (无基线表映射)
#
# Exercises the semantic driver API end-to-end on the Windows backend:
#   factory -> launch -> discovery -> geometry -> capture -> template match
#   -> message click -> state change -> control enumeration -> close
#
# Why this exists: the 74 baseline cases still call winutil directly. Before
# they can migrate to harness.platform, the backend must prove it reproduces
# the primitives they rely on. When a future refactor changes a primitive,
# this case fails first instead of 40 unrelated GUI cases.
#
# Run on the guest rig (explicit case; not part of the baseline suite):
#   & runner\hv_go.ps1 -Cases m0_platform_contract -Exe <exe>
#
# Exit code 0 = contract green.

import argparse
import sys
import time
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parents[2]  # repo root (cases live in tests/)
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import anchors, profile  # noqa: E402
from harness.platform import get_driver  # noqa: E402

LOG = "[platform]"


def frame_bgr(frame):
    """Driver Frame (BGRA top-down) -> OpenCV BGR, same as anchors.capture_bgr."""
    arr = np.frombuffer(frame.pixels, np.uint8).reshape(
        frame.height, frame.width, 4)
    return cv2.cvtColor(arr, cv2.COLOR_BGRA2BGR)


def wait_template(driver, window, template, timeout_s=45.0, poll_s=0.5):
    """Poll driver.capture + template match; returns (score, client_x, client_y)."""
    deadline = time.monotonic() + timeout_s
    best = (0.0, 0, 0)
    while time.monotonic() < deadline:
        img = frame_bgr(driver.capture(window))
        score, x, y, w, h = anchors.match(img, template)
        best = (float(score), x + w // 2, y + h // 2)
        if score >= anchors.MATCH_THRESHOLD:
            return best
        time.sleep(poll_s)
    return best


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=HERE / "artifacts" / "profile",
                    type=Path)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args()

    checks = []

    def check(name, ok, detail=""):
        checks.append((name, bool(ok)))
        tail = f" — {detail}" if detail else ""
        print(f"{LOG} {'PASS' if ok else 'FAIL'} {name}{tail}")
        return bool(ok)

    driver = get_driver()
    check("backend selected", driver.name == "windows", driver.name)
    check("message_input capability", driver.message_input is True)

    profile.seed_profile(args.datadir, fresh=args.fresh)
    app = driver.launch(args.exe, datadir=args.datadir,
                        dismiss_blockers=True, dismiss_wizard=True)
    try:
        check("launch returns live app", app.alive(), f"pid={app.pid}")
        window = app.main_window
        cls = driver.window_class(window)
        title = driver.window_title(window)
        check("main window class readable", bool(cls), cls)
        print(f"{LOG} info: title={title!r} pid={app.pid}")

        rect = driver.window_rect(window)
        client = driver.client_rect(window)
        check("window_rect non-empty",
              rect.width > 100 and rect.height > 100, str(rect.as_tuple()))
        check("client_rect non-empty",
              client.width > 100 and client.height > 100,
              str(client.as_tuple()))

        frame = driver.capture(window)
        check("capture matches client size",
              (frame.width, frame.height) == (client.width, client.height),
              f"{frame.width}x{frame.height}")
        img = frame_bgr(frame)
        colored = anchors.has_colored_content(img)
        check("capture has app content", colored > 0.005, f"colored={colored:.3f}")

        sw, sh = driver.screen_size()
        shot = driver.capture_screen()
        check("screen capture size",
              (shot.width, shot.height) == (sw, sh),
              f"{shot.width}x{shot.height}")
        scale = driver.dpi_scale(window)
        check("dpi scale is 1.0 on the 96-DPI rig", abs(scale - 1.0) < 1e-6,
              f"{scale:.3f}")

        sx, sy = driver.client_to_screen(window, 10, 10)
        bx, by = driver.screen_to_client(window, sx, sy)
        check("client<->screen round-trip", (bx, by) == (10, 10),
              f"({bx},{by})")

        controls = driver.controls(window)
        check("native controls enumerated", len(controls) > 0,
              f"{len(controls)} controls")
        slice_btn = driver.find_control(window, name="Slice plate")
        print(f"{LOG} info: find_control('Slice plate') -> "
              f"{'found' if slice_btn else 'not found'}")

        # Boot page selection is racy; wait for Prepare like m1/m2 do.
        score, _, _ = wait_template(driver, window, anchors.TAB_PREPARE_ACTIVE,
                                    timeout_s=45.0)
        check("boot settled on Prepare", score >= anchors.MATCH_THRESHOLD,
              f"score={score:.3f}")

        if score >= anchors.MATCH_THRESHOLD:
            tscore, tx, ty = wait_template(
                driver, window, anchors.TAB_PREVIEW_INACTIVE, timeout_s=10.0)
            check("Preview tab located", tscore >= anchors.MATCH_THRESHOLD,
                  f"score={tscore:.3f}")
            if tscore >= anchors.MATCH_THRESHOLD:
                driver.click(window, tx, ty, screen=False)
                switched = False
                deadline = time.monotonic() + 10.0
                while time.monotonic() < deadline:
                    time.sleep(0.5)
                    prev = frame_bgr(driver.capture(window))
                    s, *_ = anchors.match(prev, anchors.TAB_PREVIEW_ACTIVE)
                    if (s >= anchors.MATCH_THRESHOLD
                            and anchors.is_tab_teal(
                                prev, *anchors.TAB_PREVIEW_PROBE)):
                        switched = True
                        break
                check("message click switched to Preview", switched)

                # Return to Prepare so close happens from a known page.
                s2, px, py = wait_template(
                    driver, window, anchors.TAB_PREPARE_INACTIVE,
                    timeout_s=10.0)
                if s2 >= anchors.MATCH_THRESHOLD:
                    driver.click(window, px, py, screen=False)
                    wait_template(driver, window, anchors.TAB_PREPARE_ACTIVE,
                                  timeout_s=10.0)

        try:
            driver.send_key(window, "esc")
            check("send_key accepted", True)
        except Exception as exc:  # noqa: BLE001 — probe reports, not raises
            check("send_key accepted", False, str(exc))
    finally:
        app.close()

    failed = [name for name, ok in checks if not ok]
    print(f"{LOG} {len(checks) - len(failed)}/{len(checks)} checks passed")
    if failed:
        print(f"{LOG} FAIL: " + ", ".join(failed))
        return 2
    print(f"{LOG} PASS: driver contract green")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
