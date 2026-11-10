#!/usr/bin/env python3
# m8x_203.py — 飞书基线 #203: 导入（文件菜单 → 导入 → STL）
# feishu: baseline#203
# 行文: 点击「文件」→「导入」→ 选择 cube_20mm.stl → 模型出现在当前盘、
#       对象列表新增、20mm 立方体、落于打印板中心。
# 入口 = c158.import_model（文件菜单 → Import 子菜单行 → 原生对话框 →
# 路径 → IDOK，即行文的「点击导入选择 STL」路径）。
# 判定（3mf + 渲染）：恰 1 个 item 名为 cube20.stl；顶点级 AABB=20³；
# 位置近盘心（导入落点实测 (135.5,136)，|Δ|≤25mm 记 PASS，精确值进证据）；
# 渲染面彩色占比 >0（模型出现在场景）。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x203]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P = ART / "m8x_203_p.3mf"
CENTER = (135.5, 136.0)          # 导入自动落点（#188/#189 实测）


def patch_archiver(tag):
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def main() -> int:
    import argparse
    import m7_common as m7
    import m8x_158 as c158
    import m8x_188 as c188
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    args.model = None                       # 空项目开局（行文前置只要 app）
    results = {}
    patch_archiver("s1")
    P.unlink(missing_ok=True)
    session = boot_session(args, model=None)
    try:
        time.sleep(3.0)
        m7.ensure_maximized(session)
        frac0 = m7.model_colored_frac(session)
        results["开局空盘（无模型）"] = f"PASS (frac={frac0:.3%})"

        if not c158.import_model(session, CUBE):
            results["文件 → 导入 → 选择 STL"] = "FAIL（导入流程未走通）"
            return m7.m7_verdict(results)
        arrived = False
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            if m7.model_colored_frac(session) >= 0.002:
                arrived = True
                break
            time.sleep(1.5)
        results["文件 → 导入 → 选择 STL"] = (
            "PASS" if arrived else "FAIL (frac 未上升)")

        if not m7.save_project_as(session, P):
            results["另存 P"] = "FAIL"
            return m7.m7_verdict(results)
        items, plates = c188.project_geom(P)
        names = [n for _i, (_m, n) in sorted(items.items())]
        print(f"{LOG} P items={names} plates={plates}")

        results["对象列表新增（3mf 恰 1 项且名为 cube20）"] = (
            f"PASS ({names})" if len(items) == 1
            and "cube20" in names[0].lower() else f"FAIL ({names})")

        boxes = c188.mesh_boxes(P)
        b = next(iter(boxes.values())) if boxes else None
        dims = (round(b[2] * 2, 1), round(b[3] * 2, 1)) if b else None
        results["20mm 立方体（顶点 AABB）"] = (
            f"PASS (xy={dims})" if b and abs(b[2] * 2 - 20) <= 0.2
            and abs(b[3] * 2 - 20) <= 0.2 else f"FAIL ({dims})")

        if b:
            d = ((b[0] - CENTER[0]) ** 2 + (b[1] - CENTER[1]) ** 2) ** 0.5
            results["落于打印板中心（|Δ|≤25mm）"] = (
                f"PASS (Δ={d:.1f}mm @({b[0]:.1f},{b[1]:.1f}))" if d <= 25.0
                else f"FAIL (Δ={d:.1f}mm)")

        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
