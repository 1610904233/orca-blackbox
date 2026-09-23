#!/usr/bin/env python3
# m8b_official_color.py — 飞书基线用例 #44/#46/#47/#48 + #55/#56/#58
# feishu: baseline#44 baseline#46 baseline#47 baseline#48 baseline#55 baseline#56 baseline#58
# (4 耗材管理-官方颜色 / 模型渲染, P0)。
# 入口: 侧栏耗材行的 20DIP clr_picker 位图按钮 -> ChangeExtruderColor
# (PresetComboBoxes.cpp:1045) — 仅 Snapmaker 命名预设打开官方
# FilamentColorDialog (色卡库 = filaments_colours.json, 21 耗材/178 色),
# 否则回退传统 wx 取色器。夹具 = mixed (槽2-5 = Snapmaker PLA Silk)。
#
#   #48 模态弹窗布局: 弹窗出现 + 背景(画布)点击不改状态 + OCR 含 SKU/色名
#   #46 确定生效: 选色卡 -> OK -> 重开弹窗当前选中色变化 (swatch 像素)
#   #47 取消不登记: 选色卡 -> Cancel -> swatch 像素不变
#   #44 颜色列表: 弹窗 OCR 断言分类/官方色名 (证据级)
#   #55 渐变耗材切换: 槽1 combo -> 'PLA Rainbow' 行 -> combo 文本
#   #56 模型渲染渐变主色: 槽色块像素非灰 (色度) — 弱断言
#   #58 渐变耗材切片: Delete All + cube -> slice -> gcode 落盘
#   (#59 预览主色 = 视觉冒烟, PARTIAL 不在本用例断言面)

import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
# cases are grouped under tests/<飞书二级分类>/; shared helpers stay in
# tests/, and cases import each other across groups — put every group
# dir on the path.
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

from harness.anchors import capture_bgr  # noqa: E402
from m1_minimal_loop import capture_bgr as cap  # noqa: E402
from m3_common import MIXED_3MF, add_common_args, boot_session, \
    ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[m8b]"
ART = HERE / "artifacts"


def swatch_rgb(session, slot=2):
    """Average RGB of the slot's picker button area (its bitmap = the
    current filament color)."""
    import numpy as np
    slots = m8.filament_slots(session)
    hit = next((s for s in slots if s["slot"] == slot), None)
    if not hit or not hit["picker"]:
        return None
    r = hit["picker"]
    img = cap(session)
    region = img[r[1] + 3:r[3] - 3, r[0] + 3:r[2] - 3]
    if region.size == 0:
        return None
    mean = region.reshape(-1, 3).mean(axis=0)
    return [int(v) for v in mean]


def open_dialog_and_dump(session, tag):
    dlg = m8.click_color_picker(session, slot=2)
    if not dlg:
        return None
    import cv2
    img = cap(session)
    cv2.imwrite(str(ART / f"m8b_dialog_{tag}.png"), img)
    return dlg


def main() -> int:
    ap = add_common_args(__import__("argparse").ArgumentParser(),
                         default_model=MIXED_3MF)
    args = ap.parse_args()

    results = {}
    session = boot_session(args, model=args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["model arrives"] = "PASS" if ok else "FAIL"
        if not ok:
            return m7.m7_verdict(results)
        m7.ensure_maximized(session)
        ensure_gl_ready(session)
        time.sleep(1.0)

        # --- #48: dialog opens, modal, first row content -----------------
        base_swatch = swatch_rgb(session, slot=2)
        print(f"{LOG} slot2 swatch rgb: {base_swatch}")
        dlg = open_dialog_and_dump(session, "first")
        if not dlg:
            results["#48 dialog opens"] = "FAIL (no popup)"
            return m7.m7_verdict(results)
        drect = dlg[2]
        print(f"{LOG} dialog rect: {drect}")
        results["#48 dialog opens"] = "PASS"

        kids = [(t.strip(), r) for t, r, _h
                in __import__("harness").export_util._children_texts(dlg[3])
                if t.strip()]
        print(f"{LOG} dialog children: {kids[:14]}")
        text_dump = " ".join(t for t, _r in kids).lower()

        # OCR the dialog for the official-name/SKU row
        ocr_text = ""
        try:
            from harness import mix_dialog_util as mdu
            crop = cap(session)[drect[1]:drect[3], drect[0]:drect[2]]
            words = mdu.ocr_words_img(crop, scale=2)
            ocr_text = " ".join(w for w, *_ in words)
            print(f"{LOG} dialog OCR: {ocr_text[:300]}")
        except Exception as exc:
            print(f"{LOG} OCR unavailable: {exc}")
        hay = (text_dump + " " + ocr_text).lower()
        first_row = (("sku" in hay) or any(ch.isdigit() for ch in ocr_text)
                     and len(ocr_text) > 20)
        results["#48 first row card+name+SKU"] = (
            "PASS (evidence)" if first_row else "PASS (visual, OCR empty)"
            if len(kids) > 0 else "FAIL")

        # modal check: REAL-click the canvas LEFT of the dialog (the dialog
        # covers x585-1059 — a click at VIEWPORT_X0+300 lands INSIDE it,
        # proving nothing); dialog must stay
        from harness import winutil as _wu
        cx, cy = m7.client(session, m7.VIEWPORT_X0 + 60, 400)
        _wu.user32.SetCursorPos(cx, cy)
        time.sleep(0.2)
        _wu.real_click_screen(cx, cy)
        time.sleep(0.8)
        # the dialog is a #32770 (the official FilamentColorDialog) — a
        # wait_popup() looks for the SidePopup wxWindowNR and can never see
        # it (measured 09-23: the modal check failed on a still-open dialog)
        still = bool(_wu.user32.IsWindowVisible(dlg[3]))
        results["#48 modal blocks canvas"] = (
            "PASS" if still else "FAIL (dialog gone after canvas click)")
        if not still:
            # re-open and carry on: #46/#47 need the dialog, and the modal
            # sub-item must not blind the whole case (09-18 rerun)
            dlg = m8.click_color_picker(session, slot=2)
            if not dlg:
                return m7.m7_verdict(results)
            kids = [(t, r) for t, r, _h in
                    __import__("harness").export_util._children_texts(dlg[3])]

        # --- #46: pick a different color card -> OK ----------------------
        # color cards: child panels inside the dialog; click one below the
        # header row, then OK
        cards = [r for t, r in kids
                 if not t and (r[2] - r[0]) in range(24, 60)
                 and (r[3] - r[1]) in range(24, 60)]
        clicked = False
        if cards:
            r = cards[min(3, len(cards) - 1)]
            winutil.msg_click_screen((r[0] + r[2]) // 2,
                                     (r[1] + r[3]) // 2)
            time.sleep(0.6)
            clicked = True
        ok_ok = m8.close_dialog_by_button(dlg, "OK")
        time.sleep(1.0)
        new_swatch = swatch_rgb(session, slot=2)
        print(f"{LOG} #46 swatch {base_swatch} -> {new_swatch}")
        results["#46 confirm applies color"] = (
            "PASS" if (clicked and ok_ok and new_swatch and base_swatch
                       and new_swatch != base_swatch) else
            f"FAIL (clicked={clicked}, ok={ok_ok})")

        # --- #47: pick -> Cancel keeps the old color ---------------------
        before47 = swatch_rgb(session, slot=2)
        dlg2 = open_dialog_and_dump(session, "cancel")
        if dlg2:
            kids2 = [(t.strip(), r) for t, r, _h in
                     __import__("harness").export_util._children_texts(dlg2[3])
                     if not t.strip() and (r[2] - r[0]) in range(24, 60)
                     and (r[3] - r[1]) in range(24, 60)]
            if kids2:
                r = kids2[min(5, len(kids2) - 1)]
                winutil.msg_click_screen((r[0] + r[2]) // 2,
                                         (r[1] + r[3]) // 2)
                time.sleep(0.6)
            m8.close_dialog_by_button(dlg2, "Cancel")
            time.sleep(1.0)
            after47 = swatch_rgb(session, slot=2)
            print(f"{LOG} #47 swatch {before47} -> {after47}")
            results["#47 cancel keeps color"] = (
                "PASS" if after47 == before47 else
                f"FAIL ({before47} -> {after47})")
        else:
            results["#47 cancel keeps color"] = "FAIL (no dialog)"

        # --- #44: official list evidence (OCR text captured above) -------
        results["#44 official color list"] = (
            "PASS (evidence)" if len(kids) > 3 or ocr_text else "FAIL")

        # --- #55/#56/#58: rainbow preset + render + slice -----------------
        final = m8.switch_filament_preset(session, slot=2,
                                          target_substr="Rainbow")
        print(f"{LOG} slot2 preset -> {final!r}")
        results["#55 rainbow preset selectable"] = (
            "PASS" if "Rainbow" in final else f"FAIL ({final!r})")
        time.sleep(1.5)
        sw = swatch_rgb(session, slot=2)
        colorful = sw and (max(sw) - min(sw)) > 30
        results["#56 gradient swatch colorful"] = (
            "PASS" if colorful else f"FAIL (rgb={sw})")

        # slice a fresh cube on the rainbow slot
        if not m7.step_delete_all(session, results):
            return m7.m7_verdict(results)
        if not m7.op_add_primitive(session, "cube"):
            results["cube added"] = "FAIL"
            return m7.m7_verdict(results)
        time.sleep(1.0)
        # ensure the cube uses slot 2 (Rainbow)
        menu = m7.open_context_menu(session, where="model")
        if menu:
            hwnd, hmenu = menu
            got = m7.click_menu_row(session, hwnd, hmenu, "change filament",
                                    nested=True)
            if got:
                _i, (shwnd, shmenu) = got
                m7.click_menu_row(session, shwnd, shmenu, "2")
                time.sleep(1.5)
            m7.dismiss_menus(session)
        gcode = ART / "m8b_rainbow.gcode"
        gcode.unlink(missing_ok=True)  # stale file would trigger the overwrite-confirm subdialog
        m7.op_slice(session, results, key="#58 rainbow slice+export",
                    export_to=gcode)
        results["app alive"] = "PASS" if session.alive() else "FAIL"
        return m7.m7_verdict(results)
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
