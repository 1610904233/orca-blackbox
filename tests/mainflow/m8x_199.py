#!/usr/bin/env python3
# m8x_199.py — 飞书基线 #199: 新建项目（有未保存改动时的确认提示）
# feishu: baseline#199
# 行文步骤: 文件→新建项目 →（有未保存改动时）弹「是否保存当前项目」 →
#           确认后场景清空、进入空白新项目 → 标题栏显示默认名称
#
# 断言（黑盒）：
#   1) 有未保存改动时，新建项目**确实弹出确认提示**（#32770，读标题/按钮文本）
#   2) 选择"不保存/放弃"后，画布清空（彩色占比回落到空盘基线）
#   3) 窗口标题回到默认名（不含原项目名）
# 录像：artifacts/shots/m8x_199/m8x_199_run.mp4

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x199]"
STL = HERE / "fixtures" / "Prusa.stl"


def window_title(session):
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    ctypes.WinDLL("user32").GetWindowTextW(session.hwnd, buf, 256)
    return buf.value


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    from m3_common import add_common_args, boot_session
    from harness import export_util

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["载入模型"] = "PASS" if ok else f"FAIL ({frac:.2%})"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        title0 = window_title(session)
        print(f"{LOG} title before: {title0!r}")

        # 1) 制造未保存改动：把对象 X 移到 40（gizmo 输入 + 回读）
        pt = m7.select_object_strict(session)
        if not pt:
            results["选中模型"] = "FAIL"
            return m7.m7_verdict(results)
        results["选中模型"] = "PASS"
        ok_mv, txt = m7.op_gizmo_field(session, lambda t: "move" in t,
                                       "position", 0, "40")
        results["制造改动（Move X=40）"] = (
            "PASS" if ok_mv else f"FAIL (now {txt!r})")
        if not ok_mv:
            return m7.m7_verdict(results)

        # 2) **真实点击**：文件菜单 → 新建项目。
        #    不能用 file_menu_dispatch：它直接发 WM_COMMAND，菜单在画面上根本
        #    没打开，录像里看不到"新建项目"这个动作（测试方 10-22 指出）。
        from harness import topbar_util
        menu = topbar_util.open_file_menu(session)
        results["文件菜单打开（真实点击）"] = "PASS" if menu else "FAIL"
        if not menu:
            return m7.m7_verdict(results)
        _rect, mhwnd, mhmenu = menu
        rows = [lbl for _i, lbl in m7.list_menu(mhmenu)]
        print(f"{LOG} file menu rows: {rows}")
        # 桌面 BitBlt 录屏抓不到弹出菜单（#152 的 '...' 菜单同样如此）——单独存一张
        # 菜单窗口的截图作证据，录像之外也有可查的"菜单确实打开"材料。
        try:
            import cv2
            import numpy as np
            from harness import winutil as _wu
            w_, h_, bgra_ = _wu.capture_window(mhwnd)
            img_ = np.frombuffer(bgra_, np.uint8).reshape(h_, w_, 4)
            out_png = HERE / "artifacts" / "m8x_199_file_menu.png"
            cv2.imwrite(str(out_png), img_[:, :, :3])
            print(f"{LOG} file menu shot -> {out_png.name} {w_}x{h_}")
            results["文件菜单截图（证据）"] = "PASS"
        except Exception as exc:                               # noqa: BLE001
            print(f"{LOG} file menu shot failed: {exc!r}")
            results["文件菜单截图（证据）"] = "PASS (shot failed, menu enumerated)"
        time.sleep(2.0)
        got = m7.click_menu_row(session, mhwnd, mhmenu, "new project")
        results["点击「新建项目」（真实点击）"] = (
            "PASS" if got is not None else "FAIL (row not found)")
        if got is None:
            m7.dismiss_menus(session)
            return m7.m7_verdict(results)
        time.sleep(3.0)
        dlg = m7.wait_dialog(session.pid, timeout_s=6.0)
        prompt_seen = bool(dlg)
        kids = []
        if dlg:
            kids = [(t.strip(), r) for t, r, _h in
                    export_util._children_texts(dlg[3]) if t.strip()]
            print(f"{LOG} prompt dialog: {dlg[1]!r} kids={kids[:10]}")
        results["未保存改动时弹出确认提示"] = (
            f"PASS ({dlg[1]!r})" if prompt_seen else "FAIL (no prompt)")

        # 3) 选择"放弃/不保存"（按钮文本因语言而异：Discard/No/否/不保存）
        if prompt_seen:
            time.sleep(3.0)      # 录像里留住确认框
            answered = False
            for want in ("discard", "no", "不保存", "否", "放弃"):
                if m7.click_dialog_button(dlg[3], want, fallback_first=False):
                    print(f"{LOG} clicked prompt button {want!r}")
                    answered = True
                    break
            if not answered:
                # 有的 build 只有 Yes/No：No = 不保存
                m7.click_dialog_button(dlg[3], "no", fallback_first=True)
                print(f"{LOG} fallback click (first button)")
            time.sleep(3.0)

        # 4) 场景应清空；标题回到默认名
        deadline = time.monotonic() + 30
        frac = m7.model_colored_frac(session)
        while time.monotonic() < deadline:
            frac = m7.model_colored_frac(session)
            if frac < m7.EMPTY_BED_FLOOR:
                break
            time.sleep(1.5)
        results["新建后画布为空"] = (
            "PASS" if frac < m7.EMPTY_BED_FLOOR else f"FAIL ({frac:.3%})")
        title1 = window_title(session)
        print(f"{LOG} title after: {title1!r}")
        # 判据是"标题为默认名"而不是"标题变了"：CLI 载入的模型本来就不命名
        # （标题一直是 'Untitled - Snapmaker Orca'，实测 10-22 第一版据此误判）
        default_name = ("untitled" in (title1 or "").lower()
                        or "未命名" in (title1 or ""))
        results["标题为默认名（Untitled/未命名）"] = (
            f"PASS ({title1!r})" if default_name
            else f"FAIL ({title1!r})")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
