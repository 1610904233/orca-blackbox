#!/usr/bin/env python3
# probe_241_hover242.py — 涂色模式悬停帧捕获（笔刷圈形态标定）
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for g in sorted((HERE / "tests").iterdir()):
    if g.is_dir() and not g.name.startswith("__"):
        sys.path.insert(0, str(g))

import argparse
import cv2
import m4e_mixing_paint as m4e
import m7_common as m7
import m8_common as m8
from m3_common import MIXED_3MF, add_common_args, boot_session
from harness import winutil as wu

ap = add_common_args(argparse.ArgumentParser(), default_model=MIXED_3MF)
args = ap.parse_args()
session = boot_session(args, model=args.model)
try:
    ok, frac = m8.wait_arrival(session, timeout_s=240)
    print("arrived", ok)
    m7.ensure_maximized(session)
    time.sleep(2)
    if not m4e.select_model(session):
        print("select FAILED")
        sys.exit(1)
    px, tip = m4e.find_slot(session, lambda t: "color" in t and "paint" in t)
    sx, sy = m4e.client(session, px, m4e.BAR_Y)
    wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.3)
    wu.real_click_screen(sx, sy)
    time.sleep(1.5)
    print("palette", m4e.palette_state(session)[:2])
    out = HERE / "artifacts"
    # 光标摆到模型中心，静置拍帧
    for (x, y) in ((1060, 470), (1100, 500), (1030, 440)):
        sx, sy = m4e.client(session, x, y)
        wu.user32.SetCursorPos(sx, sy)
        time.sleep(0.9)
        img = m4e.viewport_img(session)
        p = out / f"hover_{x}_{y}.png"
        cv2.imwrite(str(p), img)
        print("saved", p)
finally:
    session.close()
    print("closed")
