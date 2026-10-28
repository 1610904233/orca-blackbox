#!/usr/bin/env python3
# m8x_201.py — 飞书基线 #201: 保存项目
# feishu: baseline#201
# 行文步骤: 对场景做一次修改 → 文件→保存项目 → 观察保存结果并重新打开验证
# 预期: 保存成功无报错；重新打开后修改被保留
#
# 与 #200（打开项目）的分工：#200 验证"另存为 + 打开"，本条验证**普通保存**
# （项目已命名 → 静默写入、不弹对话框）以及重开后"旋转 45°"这一改动的保留。
#
# 两段式（多进程）：同一 app 会话里第 2 个 gizmo 面板会失聪，所以
#   s1 = 导入改动 → 另存为命名 → 旋转 Z=45 → 文件→保存项目（断言无对话框、
#        文件 MD5 变化）
#   s2 = 全新 app → 打开该项目 → 旋转面板 Z 回读 45.00（改动保留）
#
# 录像：artifacts/shots/m8x_201_s1/m8x_201_s1_run.mp4、_s2
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x201]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
PROJ = ART / "m8x_201_proj.3mf"
SESSIONS = ("s1", "s2")


def md5(path):
    import hashlib
    return hashlib.md5(path.read_bytes()).hexdigest() if path.exists() else ""


def window_title(session):
    import ctypes
    buf = ctypes.create_unicode_buffer(256)
    ctypes.WinDLL("user32").GetWindowTextW(session.hwnd, buf, 256)
    return buf.value


def patch_archiver(tag):
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def save_project(session, expect_dialog=False, path=None):
    """文件 → 保存项目（真实点击）。返回 (ok, dialog_seen)。"""
    import m7_common as m7
    from harness import export_util, topbar_util, winutil
    menu = topbar_util.open_file_menu(session)
    if not menu:
        return False, False
    _r, mhwnd, mhmenu = menu
    print(f"{LOG} file menu rows: {[l for _i, l in m7.list_menu(mhmenu)]}")
    try:
        import cv2
        import numpy as np
        from harness import winutil as _wu
        w_, h_, bgra_ = _wu.capture_window(mhwnd)
        img_ = np.frombuffer(bgra_, np.uint8).reshape(h_, w_, 4)
        cv2.imwrite(str(ART / "m8x_201_menu_save.png"), img_[:, :, :3])
    except Exception as exc:                                   # noqa: BLE001
        print(f"{LOG} menu shot failed: {exc!r}")
    time.sleep(1.0)
    got = m7.click_menu_row(session, mhwnd, mhmenu, "save project")
    if got is None:
        m7.dismiss_menus(session)
        return False, False
    time.sleep(2.0)
    dlg = export_util.wait_save_dialog(session.pid, timeout_s=3.0)
    if dlg:
        print(f"{LOG} save dialog appeared: {dlg[1]!r}")
        if path is None:
            topbar_util.close_menu_windows(session.pid)
            return False, True
        edit = export_util.find_edit(dlg[3])
        if edit is None:
            return False, True
        winutil.select_all(edit)
        winutil.msg_text(edit, str(path))
        import ctypes
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)
        return export_util.wait_file(path, timeout_s=20.0), True
    return True, False


def run_s1(args, results):
    """保存会话：导入改动 → 另存为 → 旋转 45 → 普通保存。"""
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    from m3_common import boot_session

    patch_archiver("s1")
    PROJ.unlink(missing_ok=True)
    session = boot_session(args, model=args.model)
    ok = False
    try:
        arrived, frac = m8.wait_arrival(session)
        results["s1 载入模型"] = "PASS" if arrived else f"FAIL ({frac:.2%})"
        if not arrived:
            return False
        m7.ensure_maximized(session)
        c158.import_model(session, CUBE)          # 改动 1（无需 gizmo）
        time.sleep(6.0)
        named = m7.save_project_as(session, PROJ)  # 先命名（另存为）
        results["s1 项目已命名（另存为）"] = (
            f"PASS ({PROJ.stat().st_size // 1024}KB)" if named and PROJ.exists()
            else "FAIL")
        if not PROJ.exists():
            return False

        # 改动 2：旋转 Z=45（本会话唯一一次 gizmo）
        if not m7.select_object_strict(session):
            results["s1 选中模型"] = "FAIL"
            return False
        results["s1 选中模型"] = "PASS"
        ok_rot, txt = m7.op_gizmo_field(session, lambda t: "rotate" in t,
                                        "rotate", -1, "45")
        results["s1 旋转 Z=45 提交"] = (
            "PASS" if ok_rot else f"FAIL (now {txt!r})")
        if not ok_rot:
            return False

        before = md5(PROJ)
        saved, dlg_seen = save_project(session)
        results["s1 普通保存无对话框（已命名项目）"] = (
            "PASS" if saved and not dlg_seen
            else f"FAIL (saved={saved}, dialog={dlg_seen})")
        after = md5(PROJ)
        results["s1 保存写入文件（MD5 变化）"] = (
            "PASS" if after and after != before else "FAIL (same md5)")
        ok = bool(after and after != before)
        return ok
    finally:
        session.close()
        print(f"{LOG} session closed (s1)")


def run_s2(args, results):
    """验证会话：全新 app → 打开项目 → 旋转面板回读 45.00。"""
    import m7_common as m7
    from harness import topbar_util
    from m3_common import boot_session

    patch_archiver("s2")
    args.model = None
    session = boot_session(args, model=None)
    try:
        time.sleep(3.0)
        m7.ensure_maximized(session)
        menu = topbar_util.open_file_menu(session)
        results["s2 文件菜单打开"] = "PASS" if menu else "FAIL"
        if not menu:
            return False
        _r, mhwnd, mhmenu = menu
        print(f"{LOG} file menu rows: {[l for _i, l in m7.list_menu(mhmenu)]}")
        time.sleep(1.5)
        got = m7.click_menu_row(session, mhwnd, mhmenu, "open project")
        results["s2 点击打开项目"] = "PASS" if got is not None else "FAIL"
        if got is None:
            m7.dismiss_menus(session)
            return False
        from harness import export_util
        dlg = m7.wait_dialog(session.pid, timeout_s=10.0, title_substr="open")
        if not dlg:
            dlg = m7.wait_dialog(session.pid, timeout_s=5.0)
        results["s2 打开对话框"] = f"PASS ({dlg[1]!r})" if dlg else "FAIL"
        if not dlg:
            return False
        edit = export_util.find_edit(dlg[3])
        if edit is None:
            results["s2 输入框定位"] = "FAIL"
            return False
        import ctypes
        from harness import winutil
        winutil.select_all(edit)
        winutil.msg_text(edit, str(PROJ))
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)
        deadline = time.monotonic() + 120
        frac = 0.0
        while time.monotonic() < deadline:
            frac = m7.model_colored_frac(session)
            if frac >= 0.0025:
                break
            time.sleep(1.5)
        results["s2 项目加载（模型在盘）"] = (
            "PASS" if frac >= 0.0025 else f"FAIL ({frac:.3%})")
        if frac < 0.0025:
            return False
        title = window_title(session)
        results["s2 标题为项目名"] = (
            f"PASS ({title!r})" if "m8x_201_proj" in (title or "")
            else f"FAIL ({title!r})")

        # 改动是否保留：旋转面板 Z 回读 45.00
        if not m7.select_object_strict(session):
            results["s2 选中模型"] = "FAIL"
            return False
        results["s2 选中模型"] = "PASS"
        # 打开 Rotate 面板要**校验+重试**：单纯点一下常被吞（实测 10-26：
        # 面板没开、Z 读到空），点一次不行就按 'R' 再切一次。
        boxes = []
        for attempt in range(3):
            m7.click_slot(session, 1108)          # Rotate 工具（固定几何）
            time.sleep(1.5)
            boxes = m7.gizmo_row_boxes(session, "rotate")
            print(f"{LOG} rotate panel attempt{attempt + 1}: {boxes}")
            if boxes:
                break
            m7.toggle_gizmo_key(session, "rotate")
            time.sleep(1.0)
            boxes = m7.gizmo_row_boxes(session, "rotate")
            if boxes:
                break
        z_cell = (boxes[-1][2] or "").strip() if boxes else ""
        if not z_cell:
            # Z 单元格常读到空（聚焦态 OCR 不稳）：用带**去焦回读**的
            # read_gizmo_field 再试（m8x_152 的 s3 就是靠它把 45 读回来的）
            _b2, z_cell2 = m7.read_gizmo_field(session, "rotate", -1,
                                               expect="45", timeout_s=8.0)
            print(f"{LOG} defocused Z read = {z_cell2!r}")
            z_cell = (z_cell2 or "").strip() or z_cell
        print(f"{LOG} restored Z cell = {z_cell!r}")
        results["s2 旋转改动保留（Z=45.00）"] = (
            f"PASS ({z_cell})" if z_cell.startswith("45") else
            f"FAIL (Z={z_cell!r})")
        return z_cell.startswith("45")
    finally:
        session.close()
        print(f"{LOG} session closed (s2)")


def session_main(tag, args):
    results = {}
    ok = run_s1(args, results) if tag == "s1" else run_s2(args, results)
    (ART / f"m8x_201_{tag}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if ok else 1


def main() -> int:
    import argparse
    import os
    from m3_common import add_common_args
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    ap.add_argument("--session", choices=SESSIONS, default=None)
    args = ap.parse_args()
    if args.session:
        return session_main(args.session, args)

    results = {}
    for tag in SESSIONS:
        out = ART / f"m8x_201_{tag}.json"
        out.unlink(missing_ok=True)
        r = subprocess.run(
            [sys.executable, "-u", str(Path(__file__).resolve()),
             "--session", tag,
             *(["--exe", str(args.exe)] if args.exe else []),
             "--datadir", str(args.datadir)],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", env={**os.environ,
                                   "PYTHONIOENCODING": "utf-8"}, timeout=900)
        print(f"{LOG} === {tag} rc={r.returncode} ===")
        for ln in (r.stdout or "").splitlines()[-40:]:
            print(f"{LOG}   {ln}")
        if (r.stderr or "").strip():
            for ln in r.stderr.splitlines()[-6:]:
                print(f"{LOG}   E {ln}")
        if out.exists():
            results.update(json.loads(out.read_text(encoding="utf-8")))
        else:
            results[f"{tag} 会话结果缺失"] = "FAIL (no json)"
    print("\n[m3] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    all_ok = bool(results) and all(str(v).startswith("PASS")
                                   for v in results.values())
    print("[m3] " + ("GREEN" if all_ok else "RED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
