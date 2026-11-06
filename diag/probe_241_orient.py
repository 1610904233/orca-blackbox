#!/usr/bin/env python3
# probe_241_orient.py — #195 orient 入口判别（结论已修正 11-06 晚）
#
# 判别结论（icon_changed=False / menu_changed=True）当时被解读为产品缺陷，
# 用户实测推翻：手点图标有效、菜单 Auto Rotate 不换盘。真实根因：本探针的
# 判别环境被**开着的 Rotate gizmo 面板**污染（rotate_verify 打字后未关面板
# → 画布处于变换模式 → 图标点击被抑制）；B 路的「对象互换盘」疑为行点击
# 几何偏移点到 Arrange 行（Arrange 带跨盘重排）。关闭面板后图标一次点击
# 即生效（#195 最终 GREEN 版，m8x_195.py 头注释有完整六轮取证）。
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[pkOrient]"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
PA = HERE / "artifacts" / "probe_orient_icon.3mf"
PB = HERE / "artifacts" / "probe_orient_menu.3mf"


def cube_mat_of(path):
    import m8x_191 as c191
    return c191.cube_mat(path)


def main() -> int:
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    import m8x_191 as c191
    import m8x_194 as c194
    from m3_common import add_common_args, boot_session
    from harness import topbar_util, winutil as wu

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok}")
        m7.ensure_maximized(session)
        if not c194.add_plate_verified(session):
            print(f"{LOG} add-plate FAILED")
            return 1
        c158.import_model(session, CUBE)
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if "8000" in (m7.object_info_text(session) or ""):
                break
            time.sleep(1.5)
        mat, note = c191.rotate_verify(session, 0, 0, None, PA)
        print(f"{LOG} tilt: {note}")
        if mat is None:
            return 1
        c191.select_cube(session)

        # A. 图标（预期 no-op 复现）
        icon = c194.find_plate_icon(session, "orient", center=(1390, 242))
        print(f"{LOG} A icon={icon}")
        if icon:
            sx, sy = m7.client(session, *icon)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.3)
            wu.real_click_screen(sx, sy)
            time.sleep(5.0)
        PB.unlink(missing_ok=True)
        if not m7.save_project_as(session, PB):
            print(f"{LOG} A save failed")
            return 1
        ma = cube_mat_of(PB)
        print(f"{LOG} A after-icon mat={ma}")
        changed_icon = ma is not None and ma != mat

        # B. 右键菜单 Auto Rotate
        sx, sy = m7.client(session, 1520, 330)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.3)
        wu.real_click_screen(sx, sy)
        time.sleep(0.5)
        wu.real_right_click_screen(sx, sy)
        time.sleep(1.2)
        got = None
        for rect, hwnd in [(m[:4], m[4]) for m in
                           topbar_util._enum_menu_windows(session.pid)]:
            if rect[0] - 60 <= sx <= rect[2] + 60 and \
                    rect[1] - 60 <= sy <= rect[3] + 60:
                got = hwnd
                break
        if not got:
            print(f"{LOG} B no menu")
            return 0
        hmenu = topbar_util.menu_hmenu(got)
        items = m7.list_menu(hmenu)
        print(f"{LOG} B menu: {[l for _i, l in items]}")
        row = m7.click_menu_row(session, got, hmenu, "auto rotate")
        print(f"{LOG} B clicked row={row}")
        time.sleep(5.0)
        PB.unlink(missing_ok=True)
        m7.save_project_as(session, PB)
        mb = cube_mat_of(PB)
        print(f"{LOG} B after-menu mat={mb}")
        changed_menu = mb is not None and mb != ma
        print(f"{LOG} RESULT icon_changed={changed_icon} menu_changed={changed_menu}")
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
