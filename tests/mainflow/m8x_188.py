#!/usr/bin/env python3
# m8x_188.py — 飞书基线 #188: 全局整理（多盘 + 空盘删除）
# feishu: baseline#188
# 行文: 项目有多个盘且对象散乱 → 新建空白盘 → 点 A → 所有盘对象重排到位；
#       对象间无重叠（间距≥2mm）、不越界、**空白盘会被删除**
#
# 黑盒判定全部走**项目 3mf 的精确几何**（对象级，不受渲染噪声影响）：
#   P0 = 加空盘后的基线：两对象在 1 号盘 + 空白 2 号盘（2 个 <plate> 块）
#   P1 = 全局整理后：两对象仍在 1 号盘、位置重排（≥1 对象移动 ≥2mm）、
#        旋转不变（Auto-rotate 默认关，若开了只记证据）、
#        AABB 间距 ≥2mm（旋转感知足迹：Prusa 91.5×19.5 / cube 20×20）、
#        足迹在 U1 可打印区 [0.5,270.5]×[1,271] 内、
#        <plate> 块恰 1 个 = 空盘被整理删除
#   3mf 事实（j673–j675 探针实证）：盘数 = Metadata/model_settings.config 的
#   <plate> 块；对象身份 = <object> 的 name；盘归属 = <plate> 里 model_instance
#   的 object_id；位姿 = 3D/3dmodel.model 的 <item objectid=N transform=...>
#
# 单会话（无 gizmo 面板 → 无 2.4.1 同会话失聪问题）；整理入口照抄 m8x_158
# 的实证序列：焦点回画布 → A 键 → 顶栏 Arrange 图标(x844) → 面板 [Arrange]
# @(892,300)。散乱=导入自动错位（行文预期只断言整理后状态，不伪造重叠）。
import re
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x188]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P0 = ART / "m8x_188_p0.3mf"
P1 = ART / "m8x_188_p1.3mf"

# U1 可打印区（resources/Snapmaker/machine/Snapmaker U1 (0.8 nozzle).json）
BED_X = (0.5, 270.5)
BED_Y = (1.0, 271.0)
# 夹具足迹（mm，局部 XY）
FOOTPRINT = {"prusa": (91.5, 19.5), "cube": (20.0, 20.0)}


# --- 3mf 解析 ---------------------------------------------------------------

def _read(path, name):
    with zipfile.ZipFile(path) as z:
        return z.read(name).decode("utf-8", "replace")


def project_geom(path):
    """(items, plates)：items = {object_id: (12 变换浮点, 对象名)}，
    plates = {plater_id: [object_id...]}。"""
    raw = {}
    for m in re.finditer(
            r'<item\s+objectid="(\d+)"[^>]*\btransform="([^"]+)"',
            _read(path, "3D/3dmodel.model")):
        vals = [float(v) for v in m.group(2).split()]
        if len(vals) == 12:
            raw[int(m.group(1))] = vals
    cfg = _read(path, "Metadata/model_settings.config")
    names = {int(i): n for i, n in re.findall(
        r'<object id="(\d+)"[^>]*>\s*<metadata key="name" value="([^"]+)"',
        cfg)}
    items = {oid: (mat, names.get(oid, "")) for oid, mat in raw.items()}
    plates = {}
    for pm in re.finditer(r"<plate>(.*?)</plate>", cfg, re.S):
        pid = re.search(r'key="plater_id" value="(\d+)"', pm.group(1))
        ids = [int(i) for i in re.findall(
            r'key="object_id" value="(\d+)"', pm.group(1))]
        if pid:
            plates[int(pid.group(1))] = ids
    return items, plates


def footprint_aabb(mat, dims, tol=1e-6):
    """旋转感知的 XY 包围盒（中心 + 半长宽）。3mf 行主序、行向量约定：
    局部 X → (m0,m1,m2)，局部 Y → (m3,m4,m5)；中心平移 (m9,m10)。"""
    lx, ly = dims
    hx = (abs(mat[0]) * lx + abs(mat[1]) * ly) / 2.0
    hy = (abs(mat[3]) * lx + abs(mat[4]) * ly) / 2.0
    return (mat[9], mat[10], hx, hy)


def dims_for(name):
    key = "prusa" if "prusa" in (name or "").lower() else "cube"
    return FOOTPRINT[key]


def mesh_boxes(path):
    """{object_id: (cx, cy, hx, hy)} —— 顶点级精确的世界 XY 包围盒。
    路径：3dmodel.model 的 <object> 块里 component p:path 指向网格 .model，
    顶点 min/max 算局部盒，再用 item 矩阵投影（|R|·h，含 z 贡献）。"""
    out = {}
    with zipfile.ZipFile(path) as z:
        main = z.read("3D/3dmodel.model").decode("utf-8", "replace")
        oid2file = {}
        for om in re.finditer(r'<object id="(\d+)"[^>]*>(.*?)</object>',
                              main, re.S):
            cm = re.search(r'p:path="([^"]+)"', om.group(2))
            if cm:
                oid2file[int(om.group(1))] = cm.group(1)
        names = {n.lstrip("/") for n in z.namelist()}
        for im in re.finditer(
                r'<item\s+objectid="(\d+)"[^>]*\btransform="([^"]+)"', main):
            oid = int(im.group(1))
            f = (oid2file.get(oid) or "").lstrip("/")   # p:path 是包内绝对 URI（/3D/...），zip 条目无前导斜杠
            m = [float(v) for v in im.group(2).split()]
            if not f or f not in names or len(m) != 12:
                continue
            txt = z.read(f).decode("utf-8", "replace")
            vs = []
            for vm in re.finditer(r"<vertex\b[^>]*/?>", txt):
                ax = re.search(r'\bx="([^"]+)"', vm.group(0))
                ay = re.search(r'\by="([^"]+)"', vm.group(0))
                az = re.search(r'\bz="([^"]+)"', vm.group(0))
                if ax and ay and az:
                    vs.append((float(ax.group(1)), float(ay.group(1)),
                               float(az.group(1))))
            if not vs:
                continue
            xs, ys, zs = zip(*vs)
            c = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2,
                 (min(zs) + max(zs)) / 2)
            h = ((max(xs) - min(xs)) / 2, (max(ys) - min(ys)) / 2,
                 (max(zs) - min(zs)) / 2)
            out[oid] = (
                m[0] * c[0] + m[1] * c[1] + m[2] * c[2] + m[9],
                m[3] * c[0] + m[4] * c[1] + m[5] * c[2] + m[10],
                abs(m[0]) * h[0] + abs(m[1]) * h[1] + abs(m[2]) * h[2],
                abs(m[3]) * h[0] + abs(m[4]) * h[1] + abs(m[5]) * h[2])
    return out


def aabb_gap(a, b):
    """两 AABB 的 XY 间距（负数 = 重叠深度）。单轴分离时取该轴分离量
    （首跑实测：X 向并排重叠、Y 向恰好分离 2.0mm = app 的默认整理间距，
    旧公式在此错报 -53.7）。"""
    dx = max(a[0] - a[2] - (b[0] + b[2]), b[0] - b[2] - (a[0] + a[2]))
    dy = max(a[1] - a[3] - (b[1] + b[3]), b[1] - b[3] - (a[1] + a[3]))
    if dx > 0 and dy > 0:
        return (dx * dx + dy * dy) ** 0.5
    if dx > 0:
        return dx
    if dy > 0:
        return dy
    return max(dx, dy)


def sig(m):
    return tuple(round(v, 3) for v in m)


# --- 会话 -------------------------------------------------------------------

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


def arrange_all(session):
    """m8x_158 的实证入口序列：A 键 → 顶栏图标(x844) → 面板 [Arrange]。
    整理完成 = 对象 blob 布局连续两轮稳定（间隔 2s，40s 上限）。"""
    import m7_common as m7
    import m8x_158 as c158
    from harness import winutil as wu
    sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
    wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    wu.real_click_screen(sx, sy)          # 焦点回画布
    time.sleep(0.5)
    wu.user32.keybd_event(0x41, 0, 0, 0)  # A
    time.sleep(0.06)
    wu.user32.keybd_event(0x41, 0, 2, 0)
    time.sleep(2.0)
    for attempt, (bx, by) in enumerate(((892, 300), (892, 296), (900, 304))):
        print(f"{LOG} arrange panel attempt {attempt + 1} @({bx},{by})")
        m7.click_slot(session, 844)
        time.sleep(2.0)
        px, py = m7.client(session, bx, by)
        wu.user32.SetCursorPos(px, py)
        time.sleep(0.3)
        wu.real_click_screen(px, py)
        time.sleep(4.0)
        print(f"{LOG}   blobs={c158.object_blobs(session)}")
    prev = None
    deadline = time.monotonic() + 40
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
        results["载入模型（1 号盘）"] = "PASS" if ok else f"FAIL ({frac:.2%})"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)

        # 两对象散乱（导入自动错位；行文预期只断言整理后状态）
        c158.import_model(session, CUBE)
        if not wait_cube_info(session):
            results["同盘导入 cube20"] = "FAIL (info 无 cube20)"
            return m7.m7_verdict(results)
        results["同盘导入 cube20（两对象）"] = "PASS"

        # 新建空白盘（m8x_186 的客观信号：盘层渲染变宽）
        w0 = c186._plate_width(session)
        m7.click_slot(session, 756)
        time.sleep(4.0)
        w1 = c186._plate_width(session)
        print(f"{LOG} plate width {w0} -> {w1}")
        results["新建空白盘（盘层变宽）"] = (
            f"PASS ({w0}px -> {w1}px)" if w0 and w1 and w1 >= w0 * 1.25
            else f"FAIL ({w0}px -> {w1}px)")

        # 基线 P0：2 盘（1 号盘两对象 + 空 2 号盘）
        if not m7.save_project_as(session, P0):
            results["另存 P0（基线）"] = "FAIL"
            return m7.m7_verdict(results)
        items0, plates0 = project_geom(P0)
        print(f"{LOG} P0 plates={plates0} items={items0}")
        results["另存 P0（基线 2 盘）"] = (
            f"PASS (plates={sorted(plates0)})" if len(plates0) == 2
            else f"FAIL (plates={sorted(plates0)}，空盘未序列化?)")

        # 全局整理
        results["全局整理（A + [Arrange]）"] = (
            "PASS" if arrange_all(session) else "FAIL (布局未稳定)")
        w2 = c186._plate_width(session)
        results["整理后盘层宽度（证据行）"] = f"PASS ({w0}->{w1}->{w2}px)"

        if not m7.save_project_as(session, P1):
            results["另存 P1（整理后）"] = "FAIL"
            return m7.m7_verdict(results)
        items1, plates1 = project_geom(P1)
        print(f"{LOG} P1 plates={plates1} items={items1}")

        # 1) 整理真的动了位置（按 object_id 配对）
        moved = []
        for oid, (mat1, name) in items1.items():
            if oid in items0:
                mat0, _n = items0[oid]
                d = ((mat1[9] - mat0[9]) ** 2
                     + (mat1[10] - mat0[10]) ** 2) ** 0.5
                moved.append((oid, name, round(d, 1)))
        print(f"{LOG} moved={moved}")
        results["对象重排（≥1 对象移动 ≥2mm）"] = (
            f"PASS ({moved})" if any(d >= 2.0 for _o, _n, d in moved)
            else f"FAIL ({moved})")

        # 2) 旋转不变（证据；Auto-rotate 若开会转，只记不判）
        rot_same = all(
            oid not in items0 or sig(mat[:9]) == sig(items0[oid][0][:9])
            for oid, (mat, _n) in items1.items())
        results["整理不转模型（证据行）"] = f"PASS (rot_same={rot_same})"

        # 3) 两对象都在 1 号盘（整理不该把对象搬去别的盘）
        p1_objs = plates1.get(1, [])
        results["对象仍在 1 号盘"] = (
            f"PASS ({p1_objs})" if sorted(p1_objs) == sorted(items1)
            else f"FAIL (plate1={p1_objs}, items={sorted(items1)})")

        # 4) 无重叠：AABB 间距 ≥2mm（顶点级精确足迹；失败兜底名义尺寸）。
        #    容差 1e-3：3mf 变换是 float32 序列化，app 的 2mm 整理间距实测
        #    读回 1.99999982（差 0.2nm）——严格 >=2.0 会把正确结果误杀。
        exact = mesh_boxes(P1)
        boxes = []
        for oid, (mat, name) in sorted(items1.items()):
            box = exact.get(oid) or footprint_aabb(mat, dims_for(name))
            boxes.append((oid, name, box))
        gap = aabb_gap(boxes[0][2], boxes[1][2]) if len(boxes) == 2 else None
        print(f"{LOG} boxes={boxes} gap={gap}")
        results["对象无重叠（AABB 间距 ≥2mm）"] = (
            f"PASS (gap={gap:.4f}mm)" if gap is not None and gap >= 2.0 - 1e-3
            else f"FAIL (gap={gap})")

        # 5) 不越界（U1 可打印区）
        oob = [oid for oid, _n, (cx, cy, hx, hy) in boxes
               if not (BED_X[0] <= cx - hx and cx + hx <= BED_X[1]
               and BED_Y[0] <= cy - hy and cy + hy <= BED_Y[1])]
        results["无越界（U1 可打印区）"] = (
            f"PASS ({[b[1] for b in boxes]})"
            if not oob else f"FAIL (越界 object {oob})")

        # 6) 空盘被删除
        results["空白盘被删除（P1 恰 1 盘）"] = (
            f"PASS (plates={sorted(plates1)})" if len(plates1) == 1
            else f"FAIL (plates={sorted(plates1)})")

        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} session closed")


if __name__ == "__main__":
    raise SystemExit(main())
