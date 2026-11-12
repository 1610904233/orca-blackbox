#!/usr/bin/env python3
# probe_242_bisect152.py — m8x_152 s4 僵尸态二分定位（两个会话一次跑完）
# S1: 用例的 select_small_then + **手工 recipe5 真键盘**缩放 -> 关面板 -> 选中测试
# S2: 探针式 select_object_strict + **用例原样 op_gizmo_field(recipe0 起)**
#     -> 关面板 -> 选中测试
# 判读：S1 绿 S2 红 => 毒在 op_gizmo_field 内部（recipe0 链路）
#       S1 红          => 毒在前置 select_small_then / 会话早期状态
import argparse
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import m7_common as m7
import m8x_152 as c152
from harness import winutil
from m3_common import PRUSA_STL, add_common_args

LOG = "[p242bs]"


def sel(session):
    return m7.object_selected(session)


def try_select(session, tag):
    cands = m7.model_candidates(session)
    print(f"{LOG} {tag} candidates={cands[:4]}")
    for cx, cy in cands[:3]:
        sx, sy = m7.client(session, cx, cy)
        winutil.real_click_with_foreground(session.hwnd, sx, sy)
        for _ in range(3):
            if sel(session):
                print(f"{LOG} {tag} SELECTED @({cx},{cy})")
                return True
            time.sleep(0.7)
    print(f"{LOG} {tag} NOT selectable")
    return False


def one_session(args, tag, mode):
    results = {}
    session = c152.m7_boot(args, model=PRUSA_STL)
    try:
        deadline = time.monotonic() + 240
        frac = m7.model_colored_frac(session)
        while frac < 0.0025 and time.monotonic() < deadline:
            time.sleep(2.0)
            frac = m7.model_colored_frac(session)
        print(f"{LOG} {tag} arrived frac={frac:.2%}")
        m7.ensure_maximized(session)
        time.sleep(1.5)
        if mode == "helper":
            if not c152.select_small_then(session, results):
                print(f"{LOG} {tag} select_small_then FAILED")
                return
            print(f"{LOG} {tag} select_small_then OK")
            m7.click_slot(session, 1152)
            time.sleep(1.5)
            boxes = m7.gizmo_row_boxes(session, "scale")
            if boxes:
                m7.type_into_field(session, boxes[0][:2], "120", old_len=4,
                                   recipe=5)
                print(f"{LOG} {tag} typed(recipe5) -> "
                      f"{m7.read_gizmo_field(session, 'scale', 0, timeout_s=4)[1]!r}")
            m7.click_slot(session, 1152)
            time.sleep(1.2)
        else:
            if not m7.select_object_strict(session):
                print(f"{LOG} {tag} pre-select FAILED")
                return
            print(f"{LOG} {tag} pre-select OK")
            ok, text = m7.op_gizmo_field(session, lambda t: "scale" in t,
                                         "scale", 0, "120", fallback_dx=44)
            print(f"{LOG} {tag} op_gizmo_field ok={ok} text={text!r}")
            if m7.gizmo_row_boxes(session, "scale"):
                m7.click_slot(session, 1152)
                time.sleep(1.2)
        print(f"{LOG} {tag} panel closed={not m7.gizmo_row_boxes(session, 'scale')}")
        try_select(session, tag)
    except Exception as exc:  # noqa: BLE001
        print(f"{LOG} {tag} FAILED: {exc!r}")
    finally:
        session.close()
        print(f"{LOG} {tag} closed")


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    one_session(args, "S1-helper+recipe5", "helper")
    one_session(args, "S2-strict+op_gizmo_field", "strict")
    print(f"{LOG} DONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
