#!/usr/bin/env python3
# m8x_200.py — 飞书基线 #200: 打开项目
# feishu: baseline#200
# 行文步骤: 文件→打开项目 → 选择已保存的 .3mf → 加载完成
# 预期: 场景显示保存的模型与布局；打印参数/对象设置随项目恢复；标题显示项目文件名
#
# 黑盒断言：
#   1) 先存一个带改动的项目（Move X=40），文件确实出现在磁盘
#   2) 新建项目清空（真实点击，与 #199 同口径）
#   3) 文件→打开项目（**真实点击**，菜单截图留证）→ 原生对话框输入路径 → 加载
#   4) 模型回到盘上（彩色占比过门）
#   5) **对象位置恢复**：Move 面板 X 回读 = 40.00（= 保存时的编辑）
#   6) 标题显示项目文件名
#
# 录像：artifacts/shots/m8x_200/m8x_200_run.mp4

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x200]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
PROJ = ART / "m8x_200_proj.3mf"


def window_title(session):
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    ctypes.WinDLL("user32").GetWindowTextW(session.hwnd, buf, 256)
    return buf.value


def open_menu_row(session, label, shot_name):
    """真实点击文件菜单里的一行；顺带存菜单窗口截图（桌面录屏抓不到 popup）。"""
    import m7_common as m7
    from harness import topbar_util
    menu = topbar_util.open_file_menu(session)
    if not menu:
        return False
    _rect, mhwnd, mhmenu = menu
    rows = [lbl for _i, lbl in m7.list_menu(mhmenu)]
    print(f"{LOG} file menu rows: {rows}")
    try:
        import cv2
        import numpy as np
        from harness import winutil as _wu
        w_, h_, bgra_ = _wu.capture_window(mhwnd)
        img_ = np.frombuffer(bgra_, np.uint8).reshape(h_, w_, 4)
        cv2.imwrite(str(ART / shot_name), img_[:, :, :3])
        print(f"{LOG} menu shot -> {shot_name}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"{LOG} menu shot failed: {exc!r}")
    time.sleep(2.0)
    got = m7.click_menu_row(session, mhwnd, mhmenu, label)
    if got is None:
        m7.dismiss_menus(session)
        return False
    time.sleep(2.0)
    return True


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    from harness import export_util
    from m3_common import add_common_args, boot_session

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
        PROJ.unlink(missing_ok=True)

        # 1) 一次可验证的编辑 + 另存为
        if not m7.select_object_strict(session):
            results["选中模型"] = "FAIL"
            return m7.m7_verdict(results)
        results["选中模型"] = "PASS"
        ok_mv, txt = m7.op_gizmo_field(session, lambda t: "move" in t,
                                       "position", 0, "40")
        results["制造改动（Move X=40）"] = (
            "PASS" if ok_mv else f"FAIL (now {txt!r})")
        if not ok_mv:
            return m7.m7_verdict(results)
        saved = m7.save_project_as(session, PROJ)
        results["另存为项目文件"] = (
            f"PASS ({PROJ.stat().st_size // 1024}KB)" if saved and PROJ.exists()
            else "FAIL (no file)")
        if not saved or not PROJ.exists():
            return m7.m7_verdict(results)

        # 2) 新建项目清空场景（真实点击）
        if not open_menu_row(session, "new project", "m8x_200_menu_new.png"):
            results["新建项目"] = "FAIL (menu row)"
            return m7.m7_verdict(results)
        dlg = m7.wait_dialog(session.pid, timeout_s=6.0)
        if dlg:
            print(f"{LOG} save prompt: {dlg[1]!r} -> discard")
            m7.click_dialog_button(dlg[3], "no", fallback_first=True)
            time.sleep(2.5)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if m7.model_colored_frac(session) < m7.EMPTY_BED_FLOOR:
                break
            time.sleep(1.5)
        frac_empty = m7.model_colored_frac(session)
        results["新建后画布为空"] = (
            "PASS" if frac_empty < m7.EMPTY_BED_FLOOR
            else f"FAIL ({frac_empty:.3%})")
        if frac_empty >= m7.EMPTY_BED_FLOOR:
            return m7.m7_verdict(results)

        # 3) 文件 → 打开项目（真实点击）+ 原生对话框输入路径
        results["打开项目菜单点击"] = (
            "PASS" if open_menu_row(session, "open project",
                                    "m8x_200_menu_open.png") else "FAIL")
        dlg2 = m7.wait_dialog(session.pid, timeout_s=10.0, title_substr="open")
        if not dlg2:
            dlg2 = m7.wait_dialog(session.pid, timeout_s=6.0)
        results["打开对话框出现"] = f"PASS ({dlg2[1]!r})" if dlg2 else "FAIL"
        if not dlg2:
            return m7.m7_verdict(results)
        edit = export_util.find_edit(dlg2[3])
        if edit is None:
            results["文件名输入框定位"] = "FAIL"
            return m7.m7_verdict(results)
        results["文件名输入框定位"] = "PASS"
        from harness import winutil
        winutil.select_all(edit)
        winutil.msg_text(edit, str(PROJ))
        time.sleep(0.5)
        import ctypes
        ctypes.WinDLL("user32").SendMessageW(dlg2[3], 0x0111, 1, 0)  # IDOK
        deadline = time.monotonic() + 120
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(1.5)
            frac = m7.model_colored_frac(session)
        results["项目加载（模型回到盘上）"] = (
            "PASS" if frac >= 0.0025 else f"FAIL (frac={frac:.3%})")
        if frac < 0.0025:
            return m7.m7_verdict(results)

        # 4) 编辑是否随项目恢复：Move 面板 X 回读 = 40.00
        if m7.select_object_strict(session):
            m7.click_slot(session, 1064)          # Move 工具（固定几何）
            time.sleep(1.5)
            x_cell = ""
            boxes = m7.gizmo_row_boxes(session, "position")
            if boxes:
                x_cell = (boxes[0][2] or "").strip()
            print(f"{LOG} restored X cell = {x_cell!r}")
            results["编辑随项目恢复（X=40.00）"] = (
                f"PASS ({x_cell})" if x_cell.startswith("40") else
                f"FAIL (X={x_cell!r})")
        else:
            results["编辑随项目恢复（X=40.00）"] = "FAIL (not selectable)"

        title = window_title(session)
        print(f"{LOG} title after open: {title!r}")
        results["标题显示项目文件名"] = (
            f"PASS ({title!r})" if "m8x_200_proj" in (title or "")
            else f"FAIL ({title!r})")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
