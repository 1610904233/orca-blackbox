#!/usr/bin/env python3
# diag_241_uicheck.py — 2.4.1 界面只读体检（不改任何东西）
#
# 基线跑完 4/36，失败形态指向"菜单条目/工具条提示读不到"（如 Delete All row not found、
# toolbar Add slot not found (tip='')）。本探针对同一台客机、同一个夹具只做只读检查：
#   1) 窗口/前台/分辨率是不是正常（排除台架前台问题）
#   2) 工具条 hover 提示能不能读到（tip 空 = hover 扫描失效；tip 有但缺某条目 = 界面变了）
#   3) 顶栏 Edit 下拉的实际菜单行 + 子菜单（对照 2.4.0 的 'Delete All' / 'Import' 等）
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness import export_util, topbar_util, winutil  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[ui241]"


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} model arrived={ok} frac={frac:.4f}")
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        sw, sh, _ = winutil.screen_grab()
        print(f"{LOG} screen={sw}x{sh} rect={winutil.window_rect(session.hwnd)} "
              f"fg={winutil.user32.GetForegroundWindow()} main={session.hwnd} "
              f"fg_is_main={winutil.user32.GetForegroundWindow() == session.hwnd}")

        print(f"{LOG} --- toolbar hover scan ---")
        for name in ("add", "delete", "arrange", "slice", "move", "rotate", "scale",
                     "color painting", "support painting", "measure", "emboss"):
            pred = (lambda n: (lambda t: n in (t or "").lower()))(name)
            try:
                x, tip = m7.find_slot(session, pred)
            except Exception as exc:                                  # noqa: BLE001
                x, tip = None, f"<exception {exc!r}>"
            print(f"{LOG}   slot {name!r}: x={x} tip={tip!r}")

        print(f"{LOG} --- topbar Edit dropdown ---")
        info = topbar_util.open_dropdown_menu(session)
        if not info:
            print(f"{LOG}   dropdown did NOT open")
        else:
            rect, hwnd, hmenu = info
            items = topbar_util.menu_items(hmenu)
            print(f"{LOG}   rows({len(items)}): {[lbl for _i, lbl, _s in items]}")
            for i, lbl, _st in items:
                _id, sub = topbar_util.item_info(hmenu, i)
                if sub:
                    subs = [l for _j, l, _s in topbar_util.menu_items(sub)]
                    print(f"{LOG}   submenu {lbl!r}: {subs}")
            topbar_util.close_menu_windows(session.pid)
            time.sleep(0.6)

        print(f"{LOG} --- bed right-click menu ---")
        try:
            menu = m7.open_context_menu(session, where="bed")
            if menu:
                hwnd2, hmenu2 = menu
                print(f"{LOG}   bed rows: {[l for _i, l in m7.list_menu(hmenu2)]}")
                m7.dismiss_menus(session)
            else:
                print(f"{LOG}   bed context menu did NOT open")
        except Exception as exc:                                      # noqa: BLE001
            print(f"{LOG}   bed context menu exception: {exc!r}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
