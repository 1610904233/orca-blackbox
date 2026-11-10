#!/usr/bin/env python3
# m8x_192.py — 飞书基线 #192: 缩放 150% 等比
# feishu: baseline#192
# 行文: 立方体选中 → 点「缩放」→ 勾选等比 → 百分比输入 150 → 三轴尺寸
#       同步放大（27→40.5mm）；面板显示 40.5³；XY 中心不变。
# 夹具偏差留档：行文用内置 27mm 立方体，本仓用 cube20（20mm）——1.5×
# 比例语义一致，判定按 20→30mm（顶点级 AABB）。
# 入口 = op_gizmo_field("scale", 0, "150", fallback_dx=44)（#152 实证：
# index 0 = 等比百分比字段；Scale 槽选中态无 tooltip，用固定几何）。
# 判定（3mf 顶点级）：AABB=30×30×30；行范数=1.5（三轴同步）；XY 中心
# 不变 ±0.5；tz 贴床（=15）；Prusa 旁观逐位不变。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x192]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P0 = ART / "m8x_192_p0.3mf"
P1 = ART / "m8x_192_p1.3mf"


def patch_archiver(tag):
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def wait_cube_info(session, timeout_s=120):
    import m7_common as m7
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        info = m7.object_info_text(session) or ""
        if "8000" in info or "cube20" in info.lower():
            return True
        time.sleep(1.5)
    return False


def sig(m):
    return tuple(round(v, 3) for v in m)


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    import m8x_188 as c188
    import m8x_191 as c191
    from m3_common import add_common_args, boot_session

    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    results = {}
    patch_archiver("s1")
    for f in (P0, P1):
        f.unlink(missing_ok=True)
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["载入（1 号盘 Prusa 旁观）"] = (
            "PASS" if ok else f"FAIL ({frac:.2%})")
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)

        c158.import_model(session, CUBE)
        if not wait_cube_info(session):
            results["导入 cube20"] = "FAIL"
            return m7.m7_verdict(results)
        if not c191.select_cube(session):
            results["选中 cube20"] = "FAIL"
            return m7.m7_verdict(results)
        results["导入并选中 cube20"] = "PASS"

        if not m7.save_project_as(session, P0):
            results["另存 P0（基线）"] = "FAIL"
            return m7.m7_verdict(results)
        items0, _ = c188.project_geom(P0)
        oid0 = next((i for i, (_m, n) in items0.items()
                     if "cube20" in n.lower()), None)
        b0 = c188.mesh_boxes(P0)
        box0 = b0.get(oid0) if oid0 else None
        c0 = items0.get(oid0, (None, ""))[0] if oid0 else None
        print(f"{LOG} baseline box={box0} mat={c0}")

        # 缩放面板：等比百分比字段输 150（op_gizmo_field 自开自关面板）
        ok_t, text = m7.op_gizmo_field(
            session, lambda t: "scale" in t, "scale", 0, "150",
            fallback_dx=44)
        print(f"{LOG} scale 150: ok={ok_t} read={text!r}")
        results["等比缩放输入 150（回读）"] = (
            f"PASS (read={text!r})" if ok_t and str(text).startswith("150")
            else f"FAIL (read={text!r})")

        if not m7.save_project_as(session, P1):
            results["另存 P1"] = "FAIL"
            return m7.m7_verdict(results)
        items1, _ = c188.project_geom(P1)
        oid1 = next((i for i, (_m, n) in items1.items()
                     if "cube20" in n.lower()), None)
        b1 = c188.mesh_boxes(P1)
        box1 = b1.get(oid1) if oid1 else None
        c1 = items1.get(oid1, (None, ""))[0] if oid1 else None
        p0 = next((m for _i, (m, n) in items0.items()
                   if "prusa" in n.lower()), None)
        p1 = next((m for _i, (m, n) in items1.items()
                   if "prusa" in n.lower()), None)
        print(f"{LOG} after scale box={box1} mat={c1}")

        if box1:
            dims = (round(box1[2] * 2, 1), round(box1[3] * 2, 1))
            # 顶点 AABB 只取 XY，Z 从矩阵范数推（行主序 m[8]≈1.5 → 高 30）
            norms = [round(sum(v * v for v in c1[i * 3:i * 3 + 3]) ** 0.5, 3)
                     for i in range(3)] if c1 else None
            results["三轴尺寸 1.5×（20→30mm）"] = (
                f"PASS (xy={dims}, row-norms={norms})"
                if abs(box1[2] * 2 - 30) <= 0.3 and abs(box1[3] * 2 - 30) <= 0.3
                and norms and all(abs(nv - 1.5) <= 0.02 for nv in norms)
                else f"FAIL (xy={dims}, norms={norms})")
            if box0:
                dc = ((box1[0] - box0[0]) ** 2
                      + (box1[1] - box0[1]) ** 2) ** 0.5
                results["XY 中心位置不变"] = (
                    f"PASS (Δ={dc:.2f}mm)" if dc <= 0.5
                    else f"FAIL (Δ={dc:.2f}mm)")
        else:
            results["三轴尺寸 1.5×（20→30mm）"] = "FAIL (no box)"
        if c0 and c1:
            bed = abs(c1[11] - 15.0) <= 0.1        # 30/2 面着地
            results["贴床（tz=15）"] = (
                f"PASS (tz={c1[11]:.2f})" if bed
                else f"FAIL (tz={c1[11]:.2f}, want 15)")
        results["其余对象不受影响（Prusa 逐位不变）"] = (
            "PASS" if p0 and p1 and sig(p0) == sig(p1) else "FAIL")

        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
