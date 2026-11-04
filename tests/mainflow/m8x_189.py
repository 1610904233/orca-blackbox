#!/usr/bin/env python3
# m8x_189.py — 飞书基线 #189: 单盘整理（Shift+A 只动当前盘）
# feishu: baseline#189
# 行文: 多盘散乱 → 选中目标盘 → Shift+A → 当前盘对象紧密排布无重叠；
#       **其余盘对象位置不变**；无越界
#
# 布局：1 号盘 Prusa（旁观者，必须纹丝不动）；2 号盘两个 cube20（当前盘，
# 整理目标）。加盘后 import 会落在新的当前盘（#187 s1 实证）。
#
# 判定（复用 #188 的 3mf 对象级几何工具）：
#   P0 基线 plates={1:[Prusa], 2:[cubeA, cubeB]}
#   Shift+A 后 P1：
#     - 盘映射不变（不删盘、不迁对象——与 #188 全局整理删空盘成对照）
#     - 1 号盘 Prusa 的 12 元变换逐位一致（sig 相等）= 其余盘位置不变
#     - 2 号盘 ≥1 cube 移动 ≥2mm；两 cube 顶点级 AABB 间距 ≥2mm
#     - 2 号盘簇落在同一个 270×270 盘窗口内（盘间 pitch 未知，用窗口容纳
#       判据证明"没有对象跑出打印板范围"）
# 键盘：Shift+A 需英文布局（中文 IME 吞 Shift+组合键，#187 实证）。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x189]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P0 = ART / "m8x_189_p0.3mf"
P1 = ART / "m8x_189_p1.3mf"


def sig(m):
    return tuple(round(v, 3) for v in m)


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
        if "cube20" in (m7.object_info_text(session) or "").lower():
            return True
        time.sleep(1.5)
    return False


def blobs_stable(session, timeout_s=40):
    """整理完成 = 对象 blob 布局连续两轮稳定（2s 间隔）。"""
    import m8x_158 as c158
    prev = None
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        cur = c158.object_blobs(session)
        if prev is not None and prev and cur and \
                all(abs(a[0] - b[0]) <= 3 and abs(a[1] - b[1]) <= 3
                    for a, b in zip(prev, cur)):
            return True
        prev = cur
        time.sleep(2.0)
    return False


def main() -> int:
    import argparse
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    import m8x_186 as c186
    import m8x_187 as c187
    import m8x_188 as c188
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
        results["载入模型（1 号盘 Prusa）"] = (
            "PASS" if ok else f"FAIL ({frac:.2%})")
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)

        # 2 号盘（空白，加盘后当前盘切换过去）
        w0 = c186._plate_width(session)
        m7.click_slot(session, 756)
        time.sleep(4.0)
        w1 = c186._plate_width(session)
        print(f"{LOG} plate width {w0} -> {w1}")
        results["新建 2 号盘（盘层变宽）"] = (
            f"PASS ({w0}px -> {w1}px)" if w0 and w1 and w1 >= w0 * 1.25
            else f"FAIL ({w0}px -> {w1}px)")

        # 两个 cube20 落在 2 号盘（当前盘）
        c158.import_model(session, CUBE)
        if not wait_cube_info(session):
            results["2 号盘导入 cube20 #1"] = "FAIL (info 无 cube20)"
            return m7.m7_verdict(results)
        time.sleep(2.0)
        c158.import_model(session, CUBE)
        if not wait_cube_info(session):
            results["2 号盘导入 cube20 #2"] = "FAIL (info 无 cube20)"
            return m7.m7_verdict(results)
        results["2 号盘导入两个 cube20"] = "PASS"

        # 基线 P0：1 号盘 Prusa + 2 号盘两 cube
        if not m7.save_project_as(session, P0):
            results["另存 P0（基线）"] = "FAIL"
            return m7.m7_verdict(results)
        items0, plates0 = c188.project_geom(P0)
        print(f"{LOG} P0 plates={plates0} items={items0}")
        two_plate2 = len(plates0.get(2, [])) == 2
        one_plate1 = len(plates0.get(1, [])) == 1
        results["P0 基线（1 号盘 1 对象 / 2 号盘 2 对象）"] = (
            f"PASS (plates={ {k: len(v) for k, v in plates0.items()} })"
            if two_plate2 and one_plate1
            else f"FAIL (plates={ {k: len(v) for k, v in plates0.items()} })")

        # Shift+A（英文布局；当前盘 = 2 号盘）
        c187.english_layout(session)
        c187.focus_canvas(session)
        c187.press(session, 0x41, shift=True)
        results["Shift+A 单盘整理（布局稳定）"] = (
            "PASS" if blobs_stable(session) else "FAIL (布局未稳定)")

        if not m7.save_project_as(session, P1):
            results["另存 P1（整理后）"] = "FAIL"
            return m7.m7_verdict(results)
        items1, plates1 = c188.project_geom(P1)
        print(f"{LOG} P1 plates={plates1} items={items1}")

        # 1) 盘映射不变（不删盘、不迁对象）
        same_map = ({k: sorted(v) for k, v in plates1.items()}
                    == {k: sorted(v) for k, v in plates0.items()})
        results["盘映射不变（不删盘不迁对象）"] = (
            f"PASS (plates={ {k: len(v) for k, v in plates1.items()} })"
            if same_map else f"FAIL ({plates0} -> {plates1})")

        # 2) 其余盘（1 号盘）对象逐位不变
        p1_ids = plates1.get(1, [])
        untouched = all(
            oid in items0 and sig(items1[oid][0]) == sig(items0[oid][0])
            for oid in p1_ids)
        moved1 = [(oid, items1[oid][1],
                   round(((items1[oid][0][9] - items0[oid][0][9]) ** 2
                          + (items1[oid][0][10] - items0[oid][0][10]) ** 2)
                         ** 0.5, 1))
                  for oid in p1_ids if oid in items0 and oid in items1]
        print(f"{LOG} plate1 moved={moved1}")
        results["1 号盘 Prusa 位置不变（其余盘不受影响）"] = (
            f"PASS (moved={moved1})" if untouched
            else f"FAIL (moved={moved1})")

        # 3) 当前盘（2 号盘）真整理了：≥1 cube 移动 ≥2mm
        p2_ids = plates1.get(2, [])
        moved2 = []
        for oid in p2_ids:
            if oid in items0 and oid in items1:
                d = ((items1[oid][0][9] - items0[oid][0][9]) ** 2
                     + (items1[oid][0][10] - items0[oid][0][10]) ** 2) ** 0.5
                moved2.append((oid, items1[oid][1], round(d, 1)))
        print(f"{LOG} plate2 moved={moved2}")
        results["2 号盘重排（≥1 对象移动 ≥2mm）"] = (
            f"PASS ({moved2})" if any(d >= 2.0 for _o, _n, d in moved2)
            else f"FAIL ({moved2})")

        # 4) 2 号盘两 cube 顶点级 AABB 间距 ≥2mm
        exact = c188.mesh_boxes(P1)
        boxes = [(oid, exact.get(oid)) for oid in sorted(p2_ids)]
        gap = (c188.aabb_gap(boxes[0][1], boxes[1][1])
               if len(boxes) == 2 and boxes[0][1] and boxes[1][1] else None)
        print(f"{LOG} plate2 boxes={boxes} gap={gap}")
        results["2 号盘无重叠（AABB 间距 ≥2mm）"] = (
            f"PASS (gap={gap:.4f}mm)"
            if gap is not None and gap >= 2.0 - 1e-3
            else f"FAIL (gap={gap})")

        # 5) 2 号盘簇在同一个 270×270 盘窗口内（盘间 pitch 未知 → 窗口容纳）
        if boxes and all(b for _o, b in boxes):
            xs0 = min(b[0] - b[2] for _o, b in boxes)
            xs1 = max(b[0] + b[2] for _o, b in boxes)
            ys0 = min(b[1] - b[3] for _o, b in boxes)
            ys1 = max(b[1] + b[3] for _o, b in boxes)
            span = (round(xs1 - xs0, 1), round(ys1 - ys0, 1))
        else:
            span = (None, None)
        print(f"{LOG} plate2 span={span}")
        results["无越界（2 号盘簇容纳于 270×270）"] = (
            f"PASS (span={span}mm)" if span[0] is not None
            and span[0] <= 270.0 and span[1] <= 270.0
            else f"FAIL (span={span})")

        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
