#!/usr/bin/env python3
# m8x_204.py — 飞书基线 #204: 导出（STL）
# feishu: baseline#204
# 行文步骤: 选中模型 → 文件→导出 → 选择导出格式（STL）→ 选择路径 → 导出
# 预期: 目标路径生成 .stl；导出几何与场景一致；无报错、可被重新导入
#
# 黑盒断言：
#   1) 文件→导出 的子菜单里**列出 STL 选项**（打印子菜单原文）
#   2) 导出后目标文件存在，且是**合法 STL**（binary 尺寸 84+50n / ascii 头 solid），
#      三角形数 > 0
#   3) **可被重新导入**：File→导入 该 STL → 盘上对象数增加（模型在盘 + 信息面板）
#
# 录像：artifacts/shots/m8x_204/m8x_204_run.mp4
import struct
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x204]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
OUT_STL = ART / "m8x_204_export.stl"


def stl_triangles(path: Path):
    """(kind, triangles) — binary if size matches 84+50n, else ascii 段计数。"""
    data = path.read_bytes()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + 50 * n:
            return "binary", n
    head = data[:200].lower()
    if b"facet" in head or head.lstrip().startswith(b"solid"):
        return "ascii", data.lower().count(b"facet normal")
    return "unknown", 0


def export_stl(session, out_path: Path, timeout_s=30.0):
    """文件 → 导出（子菜单）→ STL 行 → 保存对话框 → 路径。返回 (ok, 选项列表)。"""
    import m7_common as m7
    from harness import export_util, topbar_util, winutil
    menu = topbar_util.open_file_menu(session)
    if not menu:
        return False, []
    mrect, mhwnd, mhmenu = menu
    items = m7.list_menu(mhmenu)
    print(f"{LOG} file menu: {[l for _i, l in items]}")
    idx = topbar_util.find_item(mhmenu, "export")
    if idx is None:
        m7.dismiss_menus(session)
        return False, []
    topbar_util.hover_row(mrect, len(items), idx)
    sub = topbar_util.wait_submenu(session.pid, {mhwnd}, timeout_s=5.0)
    if not sub:
        m7.dismiss_menus(session)
        return False, []
    srect, shmenu = sub[0], sub[2]
    sub_items = m7.list_menu(shmenu)
    names = [l for _i, l in sub_items]
    print(f"{LOG} export submenu: {names}")
    row = next((i for i, l in sub_items if "stl" in l.lower()), None)
    if row is None:
        m7.dismiss_menus(session)
        return False, names
    cx = (srect[0] + srect[2]) // 2
    clicked = False
    for yy in topbar_util.submenu_row_candidates(srect, len(sub_items), row):
        winutil.user32.SetCursorPos(cx, yy)
        time.sleep(0.2)
        winutil.real_click_screen(cx, yy)
        # STL 导出的对话框标题**不一定含 'save'**（实测 10-28：wait_save_dialog
        # 匹配不到 → 误判"导出没反应"），所以等"任何带 Edit 的 #32770"。
        dlg = None
        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline:
            cand = m7.wait_dialog(session.pid, timeout_s=0.5)
            if cand and export_util.find_edit(cand[3]) is not None:
                dlg = cand
                break
            time.sleep(0.3)
        if dlg:
            print(f"{LOG} export dialog: {dlg[1]!r}")
            clicked = True
            break
    if not clicked:
        m7.dismiss_menus(session)
        return False, names
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        return False, names
    winutil.select_all(edit)
    winutil.msg_text(edit, str(out_path))
    import ctypes
    ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK
    return export_util.wait_file(out_path, timeout_s=timeout_s), names


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
        OUT_STL.unlink(missing_ok=True)

        if not m7.select_object_strict(session):
            results["选中模型"] = "FAIL"
            return m7.m7_verdict(results)
        results["选中模型"] = "PASS"

        # 1) 文件 → 导出 → STL
        exported, opt_names = export_stl(session, OUT_STL)
        results["导出子菜单列出 STL"] = (
            f"PASS ({opt_names})" if any("stl" in n.lower() for n in opt_names)
            else f"FAIL ({opt_names})")
        results["导出生成 STL 文件"] = (
            f"PASS ({OUT_STL.stat().st_size // 1024}KB)"
            if exported and OUT_STL.exists() else "FAIL")
        if not OUT_STL.exists():
            return m7.m7_verdict(results)

        # 2) 合法性 + 几何量
        kind, tris = stl_triangles(OUT_STL)
        print(f"{LOG} exported STL: kind={kind} triangles={tris}")
        results["STL 合法（binary/ascii 且三角形>0）"] = (
            f"PASS ({kind}, {tris} tris)" if kind != "unknown" and tris > 0
            else f"FAIL (kind={kind}, tris={tris})")

        # 3) 可被重新导入：导入刚导出的 STL → 盘上对象数增加
        import m8x_158 as c158
        before = len(c158.object_blobs(session))
        c158.import_model(session, OUT_STL)
        deadline = time.monotonic() + 120
        info = ""
        while time.monotonic() < deadline:
            time.sleep(2.0)
            info = m7.object_info_text(session)
            if "m8x_204_export" in (info or "").lower():
                break
        after = len(c158.object_blobs(session))
        print(f"{LOG} re-import: blobs {before} -> {after} info={info[:60]!r}")
        results["导出的 STL 可重新导入"] = (
            f"PASS ({info[:40]!r})" if "m8x_204_export" in (info or "").lower()
            else f"FAIL (info={info[:60]!r}, blobs {before}->{after})")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
