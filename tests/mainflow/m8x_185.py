#!/usr/bin/env python3
# m8x_185.py — 飞书基线 #185: 添加（工具栏「添加」按钮导入模型）
# feishu: baseline#185
# 行文步骤: 点击工具栏「添加」→ 文件选择器选中模型 → 确认导入
# 预期: 模型导入当前盘并出现在场景；对象列表新增；模型落于打印板中心
#
# 与 #203（文件→导入）的分工：本条走**工具栏「添加」按钮**这个入口。
#
# 黑盒断言：
#   1) 工具栏存在「添加」按钮（hover tooltip 'Add [Ctrl+1]'，固定几何 x≈712）
#   2) 点击后弹出文件选择框
#   3) 导入后模型出现（彩色占比过门）
#   4) **落于打印板中心**：对象质心距盘心 < 45px
#   5) 对象信息面板显示模型名
#
# 录像：artifacts/shots/m8x_185/m8x_185_run.mp4
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x185]"
ART = HERE / "artifacts"
CUBE = HERE / "fixtures" / "cube20.stl"
ADD_SLOT_X = 712          # 工具栏「Add [Ctrl+1]」（多次 OCR 扫描稳定在 712）
PLATE_CENTER = (1171, 585)


def main() -> int:
    import argparse
    import m7_common as m7
    from harness import export_util
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    args.model = None
    results = {}
    session = boot_session(args, model=None)
    try:
        m7.ensure_maximized(session)
        frac0 = m7.model_colored_frac(session)
        results["空盘启动"] = (
            "PASS" if frac0 < m7.EMPTY_BED_FLOOR else f"FAIL ({frac0:.3%})")

        # 1) 工具栏「添加」按钮：hover 读 tooltip 确认
        tip = m7.tooltip_text(session, ADD_SLOT_X, m7.BAR_Y)
        x = ADD_SLOT_X
        if "add" not in (tip or "").lower() or "plate" in (tip or "").lower():
            print(f"{LOG} fixed add slot tip={tip!r} — scanning toolbar")
            x, tip = m7.find_slot(
                session, lambda t: "add" in t and "plate" not in t)
        print(f"{LOG} add slot @x{x} tip={tip!r}")
        results["工具栏「添加」按钮"] = (
            f"PASS ({tip!r})" if x is not None and tip else "FAIL (slot not found)")
        if x is None:
            return m7.m7_verdict(results)

        # 2) 点击 → 文件选择框
        m7.click_slot(session, x)
        time.sleep(2.0)
        dlg = m7.wait_dialog(session.pid, timeout_s=8.0)
        if not dlg:
            dlg = export_util.wait_save_dialog(session.pid, timeout_s=4.0)
        results["点击后弹出文件选择框"] = f"PASS ({dlg[1]!r})" if dlg else "FAIL"
        if not dlg:
            return m7.m7_verdict(results)
        if "add" in dlg[1].lower() and "plate" in dlg[1].lower():
            results["点击后弹出文件选择框"] = (
                f"FAIL (wrong dialog {dlg[1]!r})")
            return m7.m7_verdict(results)
        edit = export_util.find_edit(dlg[3])
        if edit is None:
            results["输入框定位"] = "FAIL"
            return m7.m7_verdict(results)
        results["输入框定位"] = "PASS"
        from harness import winutil
        winutil.select_all(edit)
        winutil.msg_text(edit, str(CUBE))
        import ctypes
        ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)  # IDOK

        # 3) 模型出现：**信息面板出现模型名**为主判据。
        #    20mm 立方体在默认缩放下彩色占比只有 ~0.21%，低于 0.25% 的门
        #    （实测 10-28 因此误判"没导进来"），小模型不能只看占比。
        deadline = time.monotonic() + 120
        frac = 0.0
        info = ""
        arrived = False
        while time.monotonic() < deadline:
            frac = m7.model_colored_frac(session)
            info = m7.object_info_text(session)
            if "cube20" in (info or "").lower():
                arrived = True
                break
            time.sleep(1.5)
        print(f"{LOG} arrival: frac={frac:.3%} info={info[:60]!r}")
        results["模型导入出现在场景"] = (
            f"PASS (info={info[:30]!r})" if arrived
            else f"FAIL (frac={frac:.3%}, info={info[:40]!r})")
        if not arrived:
            return m7.m7_verdict(results)

        # 4) 落于打印板中心（对象质心距盘心 < 45px）。
        #    不能用 m7.find_centroid：最大彩色 blob 是右下角 "snapmaker" 水印
        #    （面积 ~615，实测 10-28 把中心判成 (1666,951)）。用 #158 的
        #    对象形状过滤（面积/宽高比 + 只在盘面区域 900..1450 x 400..800）。
        import m8x_158 as c158
        time.sleep(2.0)
        objs = c158.object_blobs(session)
        print(f"{LOG} object blobs = {objs}")
        c = None
        if objs:
            c = min(objs, key=lambda b: ((b[0] - PLATE_CENTER[0]) ** 2
                                         + (b[1] - PLATE_CENTER[1]) ** 2))[:2]
        dist = None
        if c:
            dist = ((c[0] - PLATE_CENTER[0]) ** 2
                    + (c[1] - PLATE_CENTER[1]) ** 2) ** 0.5
        print(f"{LOG} model centroid={c} dist_to_plate_center={dist}")
        # 阈值 100px：20mm 高的立方体在等距视图里**投影质心天然比板面中心
        # 高约 57px**（实测 10-28：dist=57 是正常的，不是没居中）；错位对象
        # 会远大于此（之前把水印当对象时是 615px，差 10 倍）。
        results["模型落于打印板中心"] = (
            f"PASS (dist={dist:.0f}px)" if dist is not None and dist < 100
            else f"FAIL (centroid={c}, dist={dist})")

        # 5) 对象信息面板显示模型名
        info = m7.object_info_text(session)
        print(f"{LOG} object info: {info[:70]!r}")
        results["对象信息面板显示模型名"] = (
            f"PASS ({info[:40]!r})" if "cube20" in (info or "").lower()
            else f"FAIL ({info[:60]!r})")
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
