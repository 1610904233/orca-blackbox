#!/usr/bin/env python3
# probe_242_slotfallback.py — 2.4.2d 上冒烟 m7.find_slot 的固定几何回退
# （HANDOFF_242_ADAPT §4 第 1 项）。
#
# 依据：2.4.2 工具条 tooltip 全灭（probe_242_tipwin/tipnudge/tooltip 三种
# 挂法实证），m7.find_slot 已加 STATIC_SLOTS_241 静态表回退。本探针逐槽做
# 「效果验证」（交接单配方）：
#   rotate/move/scale：find_slot -> click -> gizmo_row_boxes 非空（面板真开），
#                       失败试 x±22 邻位，仍失败再试键盘快捷键通道；
#   add plate        ：find_slot -> click -> 盘层渲染宽度 >= 1.25x（m8x_186 口径）；
#   add（主按钮）    ：find_slot -> click -> #32768 形状菜单弹出；
#   arrange          ：find_slot -> click -> 视口差分/OCR 记录（软断言）；
#   其余槽位         ：只回读 find_slot 的 x（不点击，避免副作用）。
# 另验证 2.4.2 的选中判定通道：object_info_text / object_selected /
# select_object_strict（信息面板 OCR，无 tooltip 依赖）。
# 结论写 artifacts/slot_fallback_242.json。
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8_common as m8
import m8x_186 as c186
from harness import topbar_util
from m3_common import add_common_args, boot_session

LOG = "[p242sf]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"


def close_gizmo(session, x, row_label):
    """把开着的 gizmo 面板关回去（点槽位；不行就键盘快捷键）。"""
    if not m7.gizmo_row_boxes(session, row_label):
        return
    m7.click_slot(session, x)
    time.sleep(0.8)
    if m7.gizmo_row_boxes(session, row_label):
        m7.toggle_gizmo_key(session, row_label)
        time.sleep(0.8)
    print(f"{LOG} {row_label} panel closed="
          f"{not m7.gizmo_row_boxes(session, row_label)}")


def probe_gizmo(session, report, name, row_label):
    """点静态槽位（±22 邻位重试），验证 gizmo 面板真的打开。"""
    x, tip = m7.find_slot(session, lambda t: name in t)
    entry = {"pred": name, "find_slot": [x, tip]}
    print(f"{LOG} find_slot({name!r}) -> ({x}, {tip!r})")
    if x is None:
        report[f"slot:{name}"] = {**entry, "verdict": "NOT_FOUND"}
        return None
    hit, boxes = None, []
    for cand in (x, x - 22, x + 22):
        if cand != x:
            print(f"{LOG} neighbour retry x={cand}")
        m7.click_slot(session, cand)
        time.sleep(1.5)
        boxes = m7.gizmo_row_boxes(session, row_label)
        if boxes:
            hit = cand
            break
    if hit is None:
        # 键盘通道独立验证（区分「x 漂了」和「点击通道坏了」）
        m7.toggle_gizmo_key(session, row_label)
        time.sleep(1.2)
        kb = bool(m7.gizmo_row_boxes(session, row_label))
        print(f"{LOG} {name}: click x{x}(±22) all missed; keyboard={kb}")
        close_gizmo(session, x, row_label)
        report[f"slot:{name}"] = {**entry, "verdict": "CLICK_MISSED",
                                  "keyboard_opens": kb}
        return None
    print(f"{LOG} {name}: panel OPEN at x={hit}, grid={boxes[:3]}…")
    report[f"slot:{name}"] = {**entry, "verdict": "OK", "hit_x": hit,
                              "grid_head": boxes[:3]}
    close_gizmo(session, hit, row_label)
    return hit


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    args = ap.parse_args()
    report: dict = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} arrived={ok} frac={frac:.3%}")
        report["arrival"] = [ok, round(frac, 5)]
        m7.ensure_maximized(session)
        time.sleep(2.0)

        # 0) tooltip 存活判定（预期 2.4.2 = False）
        alive = m7.tooltips_alive(session)
        report["tooltips_alive"] = alive

        # 1) 选中判定通道（无 tooltip）：信息面板 OCR + strict 点击
        sel_pt = m7.select_object_strict(session)
        info = m7.object_info_text(session)
        print(f"{LOG} strict select pt={sel_pt} info={info[:60]!r}")
        report["select_strict"] = sel_pt is not None
        report["object_info_text"] = info[:80]
        report["object_selected"] = m7.object_selected(session)
        if sel_pt is None:
            print(f"{LOG} selection channel dead — later gizmo tests are "
                  f"still informative (panels may open empty)")

        # 2) gizmo 三槽：面板网格非空 = 效果验证
        for name, row in (("rotate", "rotate"), ("move", "position"),
                          ("scale", "scale")):
            probe_gizmo(session, report, name, row)

        # 3) add（主按钮）：形状菜单弹出
        x, tip = m7.find_slot(session, lambda t: "add" in t
                              and "plate" not in t)
        print(f"{LOG} find_slot(add) -> ({x}, {tip!r})")
        if x is not None:
            m7.click_slot(session, x)
            time.sleep(1.0)
            menus = topbar_util._enum_menu_windows(session.pid)
            report["slot:add"] = {"find_slot": [x, tip],
                                  "verdict": "OK" if menus else "NO_MENU"}
            print(f"{LOG} add menu popups={len(menus)}")
            topbar_util.close_menu_windows(session.pid)
            time.sleep(0.5)
        else:
            report["slot:add"] = {"verdict": "NOT_FOUND"}

        # 4) arrange（软断言）：记录点击前后视口差分 + OCR
        x, tip = m7.find_slot(session, lambda t: "arrange" in t)
        print(f"{LOG} find_slot(arrange) -> ({x}, {tip!r})")
        report["slot:arrange"] = {"find_slot": [x, tip]}
        if x is not None:
            import numpy as np
            before = m7.capture_bgr(session)
            m7.click_slot(session, x)
            time.sleep(6.0)
            after = m7.capture_bgr(session)
            diff = float(np.mean(np.abs(
                after[110:-60].astype(int)
                - before[110:-60].astype(int))))
            cents = m7.find_centroids(session, limit=3)
            report["slot:arrange"].update(
                {"viewport_mad": round(diff, 2), "centroids_after": cents})
            print(f"{LOG} arrange: viewport_mad={diff:.2f} cents={cents}")

        # 5) add plate（最后做，视图会拉远）：盘层宽度 >= 1.25x
        w0 = c186._plate_width(session)
        x, tip = m7.find_slot(session, lambda t: "add plate" in t)
        print(f"{LOG} find_slot(add plate) -> ({x}, {tip!r}) plate_w0={w0}")
        entry = {"find_slot": [x, tip], "plate_w0": w0}
        if x is None:
            report["slot:add plate"] = {**entry, "verdict": "NOT_FOUND"}
        else:
            hit = None
            for cand in (x, x - 22, x + 22):
                if cand != x:
                    print(f"{LOG} neighbour retry x={cand}")
                m7.click_slot(session, cand)
                time.sleep(3.5)
                w1 = c186._plate_width(session)
                print(f"{LOG} plate_w after x={cand}: {w1} (was {w0})")
                if w0 and w1 and w1 >= w0 * 1.25:
                    hit = (cand, w1)
                    break
            report["slot:add plate"] = {
                **entry,
                "verdict": "OK" if hit else "NO_WIDEN",
                **({"hit_x": hit[0], "plate_w1": hit[1]} if hit else {})}

        # 6) 其余槽位：只回读 x（不点击）
        for name in ("auto orient", "split to objects", "split to parts",
                     "variable layer", "face", "mesh boolean",
                     "support painting", "seam painting", "color painting"):
            x, tip = m7.find_slot(session, lambda t, n=name: n in t)
            report[f"x:{name}"] = [x, tip]
            print(f"{LOG} find_slot({name!r}) -> ({x}, {tip!r})")

        out = ART / "slot_fallback_242.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                       encoding="utf-8")
        print(f"{LOG} report -> {out}")
        print(f"{LOG} SUMMARY tooltips_alive={alive} "
              f"select={report.get('select_strict')} "
              + " ".join(f"{k}={v.get('verdict', v) if isinstance(v, dict) else v}"
                         for k, v in report.items()
                         if k.startswith("slot:")))
        return 0
    finally:
        session.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
