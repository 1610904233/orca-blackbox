#!/usr/bin/env python3
# m8x_193.py — 飞书基线 #193: 涂色（不同区域不同颜色 + 多色切片分段）
# feishu: baseline#193
# 行文: 盘上有模型、已配置多色打印能力 → 点「涂色」→ 给不同区域选不同颜色
#       → 预览切片 → 区域按涂色显示、切片多色分段正确。
#
# 结构 = 三会话（两次涂色，一次准备），每条硬约束都有实测出处：
#   s0 准备  boot U1 4 丝 + 导入 cube20 → object-info 认证 → 另存 P0
#   s1 左半  打开 P0 → 认证 cube → 涂色面板 → 瓦片2 → 短笔划 → 存 P1
#   s2 右半  打开 P1 → 认证 cube → 涂色面板 → 瓦片4 → 短笔划 → 存 P2
#            → 切片 → 导出 gcode
#
# 为什么这么绕（8+ 轮实测）：
#   * 每个 app 会话的第 2 笔涂色恒不落墨（像素差 0.3–0.5）→ 一笔一会话；
#   * **新导入(import)后的首笔也常不落墨；打开项目(open)后的首笔稳定落墨**
#     （s1 实测 Δ=0 / s2 实测 Δ=114）→ 扫色会话一律走「打开项目」；
#   * 色块启发式会误选 Prusa 长条（359px）→ 目标点改用 object-info 的
#     体积签名 8000mm³ 认证（证明点落在 cube20 上）；
#   * 放大视图后笔划反而失效（实测 diff 0.1）→ 不放大，用 ±8px 短笔划
#     全部落在 28px 的小 cube 内。
#
# 判定（客观量）：
#   1) 两会话都能打开涂色面板（Filaments 标题 + ≥2 色瓦片）
#   2) 每笔涂色后**认证点的采样色差 ≥10**（直接证据；整框像素差作证据行）
#   3) 左右两处颜色彼此不同（Δ≥15）
#   4) 切片完成 + gcode used_filaments ≥2（多色分段）
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x193]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P0 = ART / "m8x_193_p0.3mf"
P1 = ART / "m8x_193_p1.3mf"
P2 = ART / "m8x_193_p2.3mf"
GCODE = ART / "m8x_193.gcode"
SAMP = ART / "m8x_193_samples.json"
TILE_Y = 152
TILE_X0 = 1432
TILE_PITCH = 33.5
SESSIONS = ("s0", "s1", "s2")


# --- 工具 -------------------------------------------------------------------

def patch_archiver(tag):
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def dump_results(tag, results):
    (ART / f"m8x_193_{tag}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


def boot_retry(args, model, tries=3):
    from m3_common import boot_session
    last = None
    for i in range(tries):
        try:
            return boot_session(args, model=model)
        except Exception as exc:                               # noqa: BLE001
            last = exc
            print(f"{LOG} boot try{i + 1} failed: {exc!r} — retry in 6s")
            time.sleep(6.0)
    raise last


def cube_point(session):
    """点候选点直到 object-info 报 8000mm³ → 返回**证明落在 cube20 上**的
    客户区坐标（色块启发式会误选 Prusa 长条，实测 359px）。"""
    import m7_common as m7
    from harness import winutil as wu
    for (cx, cy) in m7.model_candidates(session):
        for dx, dy in ((0, 0), (0, -8), (0, 8), (-6, 0), (6, 0)):
            sx, sy = m7.client(session, cx + dx, cy + dy)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.15)
            wu.real_click_screen(sx, sy)
            time.sleep(0.6)
            if "8000" in (m7.object_info_text(session) or ""):
                print(f"{LOG} cube point @({cx + dx},{cy + dy})")
                return (cx + dx, cy + dy)
    return None


def blob_at(session, pt):
    """pt 所在（或 25px 内最近）色块的 (cx, cy, bw, bh)。"""
    import cv2
    import numpy as np
    import m4e_mixing_paint as m4e
    from harness.anchors import VIEWPORT_X0 as VP_X0, VIEWPORT_Y0 as VP_Y0
    img = m4e.viewport_img(session)
    h, w = img.shape[:2]
    x0, y0 = VP_X0 + 10, VP_Y0 + 30
    x1, y1 = min(1400, w - 10), h - 60
    band = img[y0:y1, x0:x1].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 30).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    px, py = pt[0] - x0, pt[1] - y0
    best = None
    for k in range(1, n):
        if stats[k, cv2.CC_STAT_AREA] < 150:
            continue
        bx = stats[k, cv2.CC_STAT_LEFT]
        by = stats[k, cv2.CC_STAT_TOP]
        bw = stats[k, cv2.CC_STAT_WIDTH]
        bh = stats[k, cv2.CC_STAT_HEIGHT]
        inside = bx - 4 <= px <= bx + bw + 4 and by - 4 <= py <= by + bh + 4
        dist = 0 if inside else (abs(px - bx) + abs(py - by))
        if dist <= 25 and (best is None or
                           stats[k, cv2.CC_STAT_AREA] > best[0]):
            best = (stats[k, cv2.CC_STAT_AREA], k)
    if best is None:
        return None
    k = best[1]
    return (int(cents[k][0]) + x0, int(cents[k][1]) + y0,
            int(stats[k, cv2.CC_STAT_WIDTH]), int(stats[k, cv2.CC_STAT_HEIGHT]))


def region_rgb(session, pt, r=4):
    """pt 邻域平均 BGR（涂色前后对比的直接判据）。"""
    import m4e_mixing_paint as m4e
    img = m4e.viewport_img(session)
    x, y = pt
    crop = img[max(0, y - r):y + r, max(0, x - r):x + r]
    if crop.size == 0:
        return None
    m = crop.reshape(-1, 3).mean(axis=0)
    return [round(float(v), 1) for v in m]


def rgb_dist(a, b):
    if not a or not b:
        return 0.0
    return sum((x - y) ** 2 for x, y in zip(a, b)) ** 0.5


def palette_tile_points(session):
    """从像素检测 palette 色瓦片的位置（6 个瓦片时 ImGui 会换行，固定间距
    实测 2–6 号读到白色背景 [238,238,238]）。返回按 (y,x) 排序的点列。"""
    import cv2
    import numpy as np
    import m4e_mixing_paint as m4e
    img = m4e.viewport_img(session)
    band = img[120:220, 1405:1730].astype(int)
    spread = band.max(axis=2) - band.min(axis=2)
    mask = (spread > 40).astype(np.uint8) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    n, _lab, stats, cents = cv2.connectedComponentsWithStats(mask, 8)
    pts = []
    for k in range(1, n):
        a = stats[k, cv2.CC_STAT_AREA]
        ww = stats[k, cv2.CC_STAT_WIDTH]
        hh = stats[k, cv2.CC_STAT_HEIGHT]
        if 40 <= a <= 1200 and 7 <= ww <= 42 and 7 <= hh <= 42:
            pts.append((int(cents[k][0]) + 1405, int(cents[k][1]) + 120))
    pts.sort()
    print(f"{LOG} tile points={pts}")
    return pts


def pick_tile_far_from(session, ref_rgb, exclude_pts=()):
    """选与 ref_rgb 色彩距离最大的瓦片（返回 (点, 距离, 明细)）。"""
    best = (None, -1.0)
    detail = []
    for pt in palette_tile_points(session):
        if any(abs(pt[0] - e[0]) < 8 and abs(pt[1] - e[1]) < 8
               for e in exclude_pts):
            continue
        sw = region_rgb(session, pt, r=3)
        if not sw:
            continue
        d = rgb_dist(sw, ref_rgb)
        detail.append((pt, sw, round(d)))
        if d > best[1]:
            best = (pt, d)
    print(f"{LOG} swatches vs {ref_rgb}: {detail} -> {best[0]}")
    return best[0], best[1], detail


def diff_rect(a, b, rect):
    x0, y0, x1, y1 = rect
    sa = a[y0:y1, x0:x1].astype(int)
    sb = b[y0:y1, x0:x1].astype(int)
    return float(abs(sa - sb).mean()) if sa.size else -1.0


def open_paint_gizmo(session):
    import m4e_mixing_paint as m4e
    from harness import winutil as wu
    px, tip = m4e.find_slot(session, lambda t: "color" in t and
                             "paint" in t)
    if px is None:
        print(f"{LOG} paint slot not found ({tip!r})")
        return False, None
    sx, sy = m4e.client(session, px, m4e.BAR_Y)
    wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    wu.real_click_screen(sx, sy)
    time.sleep(1.5)
    heading, tiles, _txt = m4e.palette_state(session)
    print(f"{LOG} palette heading={heading} tiles={tiles}")
    return bool(heading and tiles >= 2), px


def close_paint_gizmo(session, slot_x):
    import m4e_mixing_paint as m4e
    from harness import winutil as wu
    if slot_x is None:
        return
    sx, sy = m4e.client(session, slot_x, m4e.BAR_Y)
    wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    wu.real_click_screen(sx, sy)
    time.sleep(1.0)


def paint_stroke(session, tile_pt, a, b2, rect, tag):
    """点瓦片 → 悬停 → 拖一笔 → 返回整框像素差。"""
    import cv2
    import m4e_mixing_paint as m4e
    import m7_common as m7
    from harness import winutil as wu
    tx, ty = tile_pt
    s1, s2 = m4e.client(session, tx, ty)
    wu.user32.SetCursorPos(s1, s2)
    time.sleep(0.25)
    wu.real_click_screen(s1, s2)                  # 选色
    time.sleep(0.8)
    h1, h2 = m4e.client(session, *a)
    wu.user32.SetCursorPos(h1, h2)
    time.sleep(0.9)                               # 悬停武装笔刷
    img_b = m4e.viewport_img(session)
    m7.real_drag_screen(session, a, b2, steps=40, settle=0.8)
    time.sleep(1.2)
    img_a = m4e.viewport_img(session)
    d = diff_rect(img_b, img_a, rect)
    cv2.imwrite(str(ART / f"m8x_193_{tag}_before.png"), img_b)
    cv2.imwrite(str(ART / f"m8x_193_{tag}_after.png"), img_a)
    print(f"{LOG} {tag}: tile@({tx},{ty}) {a}->{b2} diff={d:.2f}")
    return d


def open_proj(session, path):
    import m8x_187 as c187
    return c187.open_project(session, path)


# --- 会话 -------------------------------------------------------------------

def run_prepare(args, results):
    """s0: boot + 导入 cube20 + 认证 + 另存 P0（不涂色）。"""
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    patch_archiver("s0")
    for f in (P0, P1, P2, GCODE, SAMP):
        f.unlink(missing_ok=True)
    session = boot_retry(args, args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["s0 载入（Prusa 默认 U1 4 丝）"] = (
            "PASS" if ok else f"FAIL ({frac:.2%})")
        if not ok:
            return False
        m7.ensure_maximized(session)
        c158.import_model(session, CUBE)
        if cube_point(session) is None:
            results["s0 导入 cube20（object-info 认证）"] = "FAIL"
            return False
        results["s0 导入 cube20（object-info 认证）"] = "PASS"
        ok_save = m7.save_project_as(session, P0)
        results["s0 另存 P0（基准项目）"] = "PASS" if ok_save else "FAIL"
        return bool(ok_save)
    finally:
        dump_results("s0", results)
        session.close()
        print(f"{LOG} session closed (s0)")


def run_paint(tag, args, src_proj, dst_proj, tile_i, results):
    """s1/s2: 打开项目 → 认证 cube → 涂色面板 → 一笔 → 存盘。
    笔划方向/采样点按 tag 区分（s1 左上短划、s2 右下短划）。"""
    import m7_common as m7
    import m8_common as m8
    patch_archiver(tag)
    if not src_proj.exists():
        results[f"{tag} 前置 {src_proj.name} 缺失"] = "FAIL"
        return False
    args.model = None
    time.sleep(5.0)
    session = boot_retry(args, None)
    try:
        time.sleep(3.0)
        m7.ensure_maximized(session)
        if not open_proj(session, src_proj):
            results[f"{tag} 打开 {src_proj.name}"] = "FAIL"
            return False
        results[f"{tag} 打开 {src_proj.name}"] = "PASS"
        pt = cube_point(session)
        if pt is None:
            results[f"{tag} 选中 cube20（object-info 认证）"] = "FAIL"
            return False
        results[f"{tag} 选中 cube20（object-info 认证）"] = f"PASS (@{pt})"
        blob = blob_at(session, pt)
        cx, cy = (blob[0], blob[1]) if blob else pt
        bw = blob[2] if blob else 28
        bh = blob[3] if blob else 34
        results[f"{tag} cube 锚点"] = f"PASS (@({cx},{cy}) {bw}x{bh})"
        rect = (cx - bw // 2 - 6, cy - bh // 2 - 6,
                cx + bw // 2 + 6, cy + bh // 2 + 6)

        pal_ok, px = open_paint_gizmo(session)
        results[f"{tag} 涂色面板（Filaments palette）"] = (
            "PASS" if pal_ok else "FAIL")
        if not pal_ok:
            return False

        # ±8px 短笔划，整段落在小 cube 内
        if tag == "s1":
            y = cy - 5
            a, b2 = (cx - 8, y), (cx + 2, y)
            spt = (cx - 3, y)
        else:
            y = cy + 5
            a, b2 = (cx - 2, y), (cx + 8, y)
            spt = (cx + 3, y)
        c0 = region_rgb(session, spt)
        # 选色：与「参考色」差异最大的瓦片。s1 参考 = 模型底色；s2 参考 =
        # s1 已涂色（保证两处颜色不同）。序号猜色实测会撞同色（Δ=4）。
        samp0 = {}
        if SAMP.exists():
            samp0 = json.loads(SAMP.read_text(encoding="utf-8"))
        if tag == "s1":
            ref = c0
            excl = ()
        else:
            ref = ((samp0.get("s1") or {}).get("rgb") or c0)
            e = (samp0.get("s1") or {}).get("tile")
            excl = (tuple(e),) if e else ()
        tile_pt, tile_d, _det = pick_tile_far_from(session, ref, excl)
        results[f"{tag} 选色（挑与参考色差异最大的瓦片）"] = (
            f"PASS (@{tile_pt}, Δ={tile_d:.0f})" if tile_pt
            else "FAIL (无可读瓦片)")
        if tile_pt is None:
            return False
        d = paint_stroke(session, tile_pt, a, b2, rect, f"{tag}_stroke")
        c1 = region_rgb(session, spt)
        dc = rgb_dist(c1, c0)
        print(f"{LOG} {tag} sample {c0} -> {c1} Δ={dc:.0f} rect_diff={d:.2f}")
        results[f"{tag} 涂色（瓦片{tile_i + 1}，采样色差≥10）"] = (
            f"PASS (Δ={dc:.0f})" if dc >= 10 else f"FAIL (Δ={dc:.0f})")
        results[f"{tag} 笔划像素差（证据行）"] = f"PASS (diff={d:.1f})"
        samp = {}
        if SAMP.exists():
            samp = json.loads(SAMP.read_text(encoding="utf-8"))
        samp[tag] = {"pt": list(spt), "rgb": c1, "tile": list(tile_pt)}
        SAMP.write_text(json.dumps(samp), encoding="utf-8")

        close_paint_gizmo(session, px)
        if not m7.save_project_as(session, dst_proj):
            results[f"{tag} 另存 {dst_proj.name}"] = "FAIL"
            return False
        results[f"{tag} 另存 {dst_proj.name}"] = "PASS"

        if tag == "s2":
            m7.op_slice(session, results, key="切片完成", export_to=GCODE)
            if GCODE.exists():
                used = m8.used_filaments(GCODE.read_bytes())
                results["切片多色分段（used_filaments ≥2）"] = (
                    f"PASS (used={used})" if len(used) >= 2
                    else f"FAIL (used={used})")
            else:
                results["切片多色分段（used_filaments ≥2）"] = "FAIL (无 gcode)"
        return dc >= 10
    finally:
        dump_results(tag, results)
        session.close()
        print(f"{LOG} session closed ({tag})")


def session_main(tag, args):
    results = {}
    if tag == "s0":
        ok = run_prepare(args, results)
    elif tag == "s1":
        ok = run_paint("s1", args, P0, P1, 1, results)
    else:
        ok = run_paint("s2", args, P1, P2, 3, results)
    dump_results(tag, results)
    return 0 if ok else 1


def main() -> int:
    import argparse
    from m3_common import add_common_args
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    ap.add_argument("--session", choices=SESSIONS, default=None)
    args = ap.parse_args()
    if args.session:
        return session_main(args.session, args)

    results = {}
    for tag in SESSIONS:
        out = ART / f"m8x_193_{tag}.json"
        out.unlink(missing_ok=True)
        r = None
        try:
            r = subprocess.run(
                [sys.executable, "-u", str(Path(__file__).resolve()),
                 "--session", tag,
                 *(["--exe", str(args.exe)] if args.exe else []),
                 "--datadir", str(args.datadir)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", env={**os.environ,
                                       "PYTHONIOENCODING": "utf-8"},
                timeout=600)
        except subprocess.TimeoutExpired:
            print(f"{LOG} === {tag} TIMEOUT ===")
        if r is not None:
            print(f"{LOG} === {tag} rc={r.returncode} ===")
            for ln in (r.stdout or "").splitlines()[-10:]:
                print(f"{LOG}   {ln}")
        if out.exists():
            results.update(json.loads(out.read_text(encoding="utf-8")))
        else:
            results[f"{tag} 会话结果缺失"] = "FAIL (no json)"

    # 跨会话：两处颜色彼此不同
    if SAMP.exists():
        samp = json.loads(SAMP.read_text(encoding="utf-8"))
        lrgb = (samp.get("s1") or {}).get("rgb")
        rrgb = (samp.get("s2") or {}).get("rgb")
        dlr = rgb_dist(rrgb, lrgb) if lrgb and rrgb else 0.0
        print(f"{LOG} cross-session L={lrgb} R={rrgb} Δ={dlr:.0f}")
        results["两处颜色不同（左右采样差异≥15）"] = (
            f"PASS (Δ={dlr:.0f})" if dlr >= 15 else f"FAIL (Δ={dlr:.0f})")
    else:
        results["两处颜色不同（左右采样差异≥15）"] = "FAIL (无采样文件)"

    print("\n[m3] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    all_ok = bool(results) and all(str(v).startswith("PASS")
                                  for v in results.values())
    print("[m3] " + ("GREEN" if all_ok else "RED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
