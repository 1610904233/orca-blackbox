#!/usr/bin/env python3
# probe_242_hotrestart.py — #142 可行性：改参数后"热重启"（关+开，同一
# datadir，不带模型参数），验证软件是否自动恢复工程状态
#   1) 载入夹具、改一个可回读参数（缩放面板 120）
#   2) 正常关闭（不保存，遇保存提示选放弃）
#   3) 不带模型参数重启（fresh=False 复用 datadir）
#   4) 观察：标题/工程是否自动恢复、模型是否在盘、参数是否保留
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
import m8_common as m8
from harness import export_util, winutil
from m3_common import PRUSA_STL, add_common_args, boot_session

LOG = "[p242hr]"
WM_COMMAND = 0x0111


def dismiss_dialogs(session, prefer=("discard", "no", "cancel", "ok")):
    """关掉保存/提示框；优先点 discard/no（放弃未保存修改）。"""
    for _ in range(6):
        dlg = next(((c, t, r, h) for c, t, r, h in
                    m7._visible_toplevels(session.pid) if c == "#32770"), None)
        if not dlg:
            return
        kids = export_util._children_texts(dlg[3])
        print(f"{LOG} dialog {dlg[1]!r} kids="
              f"{[k[0][:16] for k in kids if k[0].strip()][:6]}")
        hit = None
        for key in prefer:
            hit = next(((t, r, h) for t, r, h in kids
                        if t.strip().lower() == key), None)
            if hit:
                break
        if hit:
            t, r, _h = hit
            cx, cy = (r[0] + r[2]) // 2, (r[1] + r[3]) // 2
            winutil.user32.SetCursorPos(cx, cy)
            winutil.real_click_screen(cx, cy)
            print(f"{LOG} clicked {t!r}")
        else:
            winutil.user32.SendMessageW(dlg[3], WM_COMMAND, 2, 0)  # IDCANCEL
            print(f"{LOG} sent IDCANCEL")
        time.sleep(2.0)


def main() -> int:
    ap = add_common_args(argparse.ArgumentParser(), default_model=PRUSA_STL)
    args = ap.parse_args()
    # --- 第一次会话：载入 + 改参数 ---
    session = boot_session(args, model=PRUSA_STL)
    try:
        ok, frac = m8.wait_arrival(session)
        print(f"{LOG} first session arrived={ok} frac={frac:.2%}")
        m7.ensure_maximized(session)
        time.sleep(2.0)
        pt = m7.select_object_strict(session)
        print(f"{LOG} selected pt={pt}")
        m7.click_slot(session, 1152)
        time.sleep(1.5)
        boxes = m7.gizmo_row_boxes(session, "scale")
        if boxes:
            m7.type_into_field(session, boxes[0][:2], "120", old_len=4,
                               recipe=5)
            print(f"{LOG} scale -> "
                  f"{m7.read_gizmo_field(session, 'scale', 0, timeout_s=4)[1]!r}")
        if m7.gizmo_row_boxes(session, "scale"):
            m7.click_slot(session, 1152)
            time.sleep(1.0)
        print(f"{LOG} closing app (unsaved changes)")
        session.close()
    finally:
        try:
            session.close()
        except Exception:
            pass
    time.sleep(5.0)
    # --- 第二次会话：不带模型参数，同 datadir ---
    session2 = boot_session(args, model=None, fresh=False)
    try:
        time.sleep(15.0)
        m7.ensure_maximized(session2)
        dismiss_dialogs(session2)
        titles = [(c, t) for c, t, r, h in m7._visible_toplevels(session2.pid)]
        print(f"{LOG} restart toplevels={titles}")
        frac = m7.model_colored_frac(session2)
        print(f"{LOG} restart colored frac={frac:.3%} blobs={m7.blob_count(session2)}")
        # 对象行（工程是否恢复）
        import m8x_152 as c152
        row = c152.objects_tab_select(session2)
        print(f"{LOG} restart object row={row}")
        # 参数：若是工程恢复，缩放面板读到 120
        info = m7.object_info_text(session2)
        print(f"{LOG} restart info={info[:60]!r}")
        return 0
    finally:
        session2.close()
        print(f"{LOG} closed")


if __name__ == "__main__":
    raise SystemExit(main())
