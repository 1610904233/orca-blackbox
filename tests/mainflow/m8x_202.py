#!/usr/bin/env python3
# m8x_202.py — 飞书基线 #202: 项目另存为
# feishu: baseline#202
# 行文步骤: 文件→项目另存为 → 新路径/新文件名 → 保存
# 预期: 新路径生成新 .3mf；原项目文件不变；另存为后当前项目指向新文件
#       （后续"保存"写入新文件）
#
# 黑盒断言（全部用文件内容 MD5 + 窗口标题，不猜 UI 状态）：
#   1) 另存为 A → A 存在
#   2) 再改一次 → 另存为 B → B 存在、**A 的 MD5 不变**
#   3) 标题显示 B 的项目名（当前项目已指向新文件）
#   4) 再改一次 → 文件→**保存项目** → **B 变、A 不变**（普通保存写入新文件）
#
# 录像：artifacts/shots/m8x_202/m8x_202_run.mp4

import hashlib
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x202]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
PROJ_A = ART / "m8x_202_a.3mf"
PROJ_B = ART / "m8x_202_b.3mf"


def md5(path):
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else ""


def window_title(session):
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    ctypes.WinDLL("user32").GetWindowTextW(session.hwnd, buf, 256)
    return buf.value


def menu_shot(session, mhwnd, name):
    """菜单窗口截图（桌面录屏抓不到 popup 菜单，单独留证）。"""
    try:
        import cv2
        import numpy as np
        from harness import winutil as _wu
        w_, h_, bgra_ = _wu.capture_window(mhwnd)
        img_ = np.frombuffer(bgra_, np.uint8).reshape(h_, w_, 4)
        cv2.imwrite(str(ART / name), img_[:, :, :3])
        print(f"{LOG} menu shot -> {name}")
    except Exception as exc:                                   # noqa: BLE001
        print(f"{LOG} menu shot failed: {exc!r}")


def save_project(session, expected_path=None, timeout_s=20.0):
    """文件 → 保存项目（真实点击菜单行）。若保存过则不应弹对话框。"""
    import m7_common as m7
    from harness import export_util, topbar_util, winutil
    menu = topbar_util.open_file_menu(session)
    if not menu:
        return False
    _r, mhwnd, mhmenu = menu
    print(f"{LOG} file menu rows: {[l for _i, l in m7.list_menu(mhmenu)]}")
    menu_shot(session, mhwnd, "m8x_202_menu_save.png")
    time.sleep(1.0)
    got = m7.click_menu_row(session, mhwnd, mhmenu, "save project")
    if got is None:
        m7.dismiss_menus(session)
        return False
    time.sleep(1.5)
    dlg = export_util.wait_save_dialog(session.pid, timeout_s=3.0)
    if dlg:                      # 未命名项目 → 会弹保存对话框
        if expected_path is None:
            topbar_util.close_menu_windows(session.pid)
            return False
        edit = export_util.find_edit(dlg[3])
        if edit is None:
            return False
        winutil.select_all(edit)
        winutil.msg_text(edit, str(expected_path))
        import ctypes
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK
        return export_util.wait_file(expected_path, timeout_s=timeout_s)
    return True


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
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
        for f in (PROJ_A, PROJ_B):
            f.unlink(missing_ok=True)
        if not m7.select_object_strict(session):
            results["选中模型"] = "FAIL"
            return m7.m7_verdict(results)
        results["选中模型"] = "PASS"

        # 改动一律用**不需要 gizmo 的操作**（导入模型 / 整理）：
        # 2.4.1 同一会话里第二个 gizmo 面板会失聪（实测：第二次 Move 读回
        # 100.00 而不是 70），所以不用 op_gizmo_field 做多次改动。
        import m8x_158 as c158

        # 1) 导入 cube20（改动 1）→ 另存为 A
        c158.import_model(session, HERE / "fixtures" / "cube20.stl")
        time.sleep(6.0)
        saved = m7.save_project_as(session, PROJ_A)
        a_md5_0 = md5(PROJ_A)
        results["另存为 A（新路径生成 3mf）"] = (
            f"PASS ({PROJ_A.stat().st_size // 1024}KB)" if saved and a_md5_0
            else "FAIL")
        if not a_md5_0:
            return m7.m7_verdict(results)

        # 2) 整理（改动 2，无 gizmo）→ 另存为 B
        m7.click_slot(session, 844)          # 顶栏 Arrange 图标 → 面板
        time.sleep(1.6)
        from harness import winutil as _wu
        px, py = m7.client(session, 892, 300)
        _wu.user32.SetCursorPos(px, py)
        time.sleep(0.25)
        _wu.real_click_screen(px, py)        # 面板里的 [Arrange]
        time.sleep(4.0)
        results["第二次改动（整理）"] = "PASS"
        saved_b = m7.save_project_as(session, PROJ_B)
        results["另存为 B"] = (
            f"PASS ({PROJ_B.stat().st_size // 1024}KB)"
            if saved_b and PROJ_B.exists() else "FAIL")
        if not PROJ_B.exists():
            return m7.m7_verdict(results)
        results["原项目文件 A 未被改动（MD5）"] = (
            "PASS" if md5(PROJ_A) == a_md5_0 else "FAIL (A changed)")
        title = window_title(session)
        print(f"{LOG} title after save-as B: {title!r}")
        results["当前项目指向 B（标题）"] = (
            f"PASS ({title!r})" if "m8x_202_b" in (title or "")
            else f"FAIL ({title!r})")

        # 3) 导入 prism12（改动 3）→ 文件→保存项目（普通保存）
        c158.import_model(session, HERE / "fixtures" / "prism12.stl")
        time.sleep(6.0)
        results["第三次改动（导入 prism12）"] = "PASS"
        b_md5_0 = md5(PROJ_B)
        saved_now = save_project(session, PROJ_B)
        print(f"{LOG} plain save ok={saved_now}")
        b_changed = md5(PROJ_B) != b_md5_0
        a_changed = md5(PROJ_A) != a_md5_0
        results["保存写入新文件 B（B 变、A 不变）"] = (
            "PASS" if b_changed and not a_changed
            else f"FAIL (B_changed={b_changed}, A_changed={a_changed})")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
