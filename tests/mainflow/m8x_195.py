#!/usr/bin/env python3
# m8x_195.py — 飞书基线 #195: 调整零件朝向（Auto orient）
# feishu: baseline#195
# 行文: 当前盘上有模型 → 点盘右侧工具栏「调整零件朝向」按钮 → 零件自动
#       旋转到较优打印朝向（大平面贴合、悬垂减少）；仍在盘内、底面贴合、
#       尺寸不变。
#
# 入口 = 盘侧工具栏 orient 图标（行文原文路径），点击定位用**图形中心**
# (1404,241)——tooltip 命中点是悬停 padding，点击不中按钮（用户实测手点
# 图标有效；此前的「产品缺陷」结论系自动化定位误差，已收回）。
# 布局：1 号盘 Prusa（旁观者，必须逐位不变）；2 号盘（当前）cube20 先倾斜
# 相对 X=45（复用 #191 的矩阵验证打字，其存盘兼作基线 P0——棱着地
# tz=14.14），Auto orient 后应面着地（某旋转行 ≈(0,0,±1)，tz=10）。
# 判定：盘映射不变；cube 面着地 + 贴床定律 + 正交（尺寸不变）+ 原地
# （|Δtx|,|Δty|≤0.5，仍在盘内）；1 号盘 Prusa 逐位不变。
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x195]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P0 = ART / "m8x_195_p0.3mf"
P1 = ART / "m8x_195_p1.3mf"


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
    import m8x_187 as c187
    import m8x_188 as c188
    import m8x_191 as c191
    import m8x_194 as c194
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
        results["载入（1 号盘 Prusa）"] = "PASS" if ok else f"FAIL ({frac:.2%})"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)

        if not c194.add_plate_verified(session):
            results["新建 2 号盘（当前盘）"] = "FAIL（宽度未变）"
            return m7.m7_verdict(results)
        results["新建 2 号盘（当前盘）"] = "PASS"

        c158.import_model(session, CUBE)
        if not wait_cube_info(session):
            results["2 号盘导入 cube20"] = "FAIL"
            return m7.m7_verdict(results)
        results["2 号盘导入 cube20"] = "PASS"

        # 倾斜相对 X=45（矩阵验证打字；存盘兼作基线 P0）
        mat, note = c191.rotate_verify(session, 0, 0, None, P0)
        results["cube 倾斜 X=45（棱着地）"] = (
            f"PASS ({note})" if mat is not None else f"FAIL ({note})")
        if mat is None:
            return m7.m7_verdict(results)

        items0, plates0 = c188.project_geom(P0)
        print(f"{LOG} P0 plates={ {k: v for k, v in plates0.items()} }")
        base_ok = (len(plates0) == 2 and len(plates0.get(2, [])) == 1
                   and len(plates0.get(1, [])) == 1)
        results["P0 基线（2 盘各 1 对象，cube 斜）"] = (
            f"PASS (plates={ {k: len(v) for k, v in plates0.items()} })"
            if base_ok else
            f"FAIL (plates={ {k: len(v) for k, v in plates0.items()} })")
        if not base_ok:
            return m7.m7_verdict(results)

        # 关闭 Rotate 面板（rotate_verify 打开后不关；面板开着 = 画布处于
        # 变换模式，盘侧图标点击被抑制——五轮 no-op 的根因；#194 点图标前
        # 从未开过面板所以有效，用户手点同理。op_gizmo_field 自身会关）。
        rx, _rtip = m7.find_slot(session, lambda t: "rotate" in t)
        if rx is not None and m7.gizmo_row_boxes(session, "rotate"):
            m7.click_slot(session, rx)
            time.sleep(1.0)
        from harness import winutil as wu
        ax, ay = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
        wu.user32.SetCursorPos(ax, ay)
        time.sleep(0.2)
        wu.real_click_screen(ax, ay)
        time.sleep(0.6)
        icon = c194.find_plate_icon(session, "orient", center=(1404, 241),
                                    radius=18)
        if icon is None:
            results["盘侧朝向按钮（图形中心定位）"] = "FAIL（tooltip 未验证到 orient）"
            return m7.m7_verdict(results)
        results["盘侧朝向按钮（图形中心定位）"] = f"PASS (@{icon})"
        sx, sy = m7.client(session, *icon)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.35)
        wu.real_click_screen(sx, sy)
        time.sleep(1.2)
        wu.real_click_screen(sx, sy)          # 保底第二击（orient 幂等）
        time.sleep(6.0)                       # auto orient 通常秒级，留余量

        if not m7.save_project_as(session, P1):
            results["另存 P1（朝向调整后）"] = "FAIL"
            return m7.m7_verdict(results)
        items1, plates1 = c188.project_geom(P1)
        print(f"{LOG} P1 plates={ {k: v for k, v in plates1.items()} }")

        cube0 = next(m for oid, (m, n) in items0.items()
                     if "cube20" in n.lower())
        cube1_m, cube1_n = next((m, n) for oid, (m, n) in items1.items()
                                if "cube20" in n.lower())

        results["盘映射不变（不删盘不迁对象）"] = (
            f"PASS (plates={ {k: len(v) for k, v in plates1.items()} })"
            if {k: sorted(v) for k, v in plates1.items()}
            == {k: sorted(v) for k, v in plates0.items()}
            else f"FAIL ({plates0} -> {plates1})")

        faced = c187.face_down(cube1_m)
        results["较优朝向：面着地（大平面贴合）"] = (
            "PASS (rot rows face-down)" if faced
            else f"FAIL (mat={cube1_m})")

        bed, want = c191.bed_contact_ok(cube1_m)
        results["底面贴合（贴床定律）"] = (
            f"PASS (tz={cube1_m[11]:.2f}={want})" if bed
            else f"FAIL (tz={cube1_m[11]:.3f} want {want})")

        results["尺寸不变（正交）"] = (
            "PASS" if c191.rows_orthonormal(cube1_m) else "FAIL")

        drift = ((cube1_m[9] - cube0[9]) ** 2
                 + (cube1_m[10] - cube0[10]) ** 2) ** 0.5
        results["原地旋转（仍在盘内，|Δt|≤0.5）"] = (
            f"PASS (drift={drift:.2f}mm)" if drift <= 0.5
            else f"FAIL (drift={drift:.2f}mm)")

        p1_id = plates1.get(1, [])
        untouched = all(
            oid in items0 and sig(items1[oid][0]) == sig(items0[oid][0])
            for oid in p1_id)
        results["1 号盘 Prusa 逐位不变（只动当前盘）"] = (
            "PASS" if untouched and p1_id else "FAIL")

        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
