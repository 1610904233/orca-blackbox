#!/usr/bin/env python3
# probe_241_userpreset_seeded.py — 打破"鸡生蛋"：把用户预设**播种进槽位**，
# 再看 2.4.1 的耗材双栏框里用户预设到底出现在哪。
#
# 手法：seed_profile() 之后、launch 之前，直接改 datadir 的 conf：
#   conf["orca_presets"][U1 0.8 那一项]["filament_01"] = 用户预设名  （= slot 2）
#   （`filament` = slot 1，`filament_0N` = slot N+1；实测结构见 j419）
# 然后空盘启动，dump：
#   1) 各槽位 combo 文本（用户预设名是否被接受/回显）
#   2) 选择框左右两栏的行（找"用户配置/自定义/User presets"分组）
#   3) 左右栏截图（拉回来人工复核）
# 只读探查（除了那个 conf 键）；会话正常关闭。
import argparse
import json
import sys
import time
from pathlib import Path

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE)); sys.path.insert(0, str(_HERE / "tests"))
for _g in sorted((_HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

_LOG_NAME = "puseed.log"


def _tee_log(name):
    import sys as _s
    p = Path(__file__).resolve().parents[1] / "artifacts" / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fh = open(p, "w", encoding="utf-8", errors="replace")

    class _T:
        def write(self, s):
            fh.write(s)
            fh.flush()
            try:
                if _s.__stdout__ is not None:
                    _s.__stdout__.write(s)
            except Exception:                                  # noqa: BLE001
                pass

        def flush(self):
            fh.flush()

    _s.stdout = _T()
    _s.stderr = _T()


_tee_log(_LOG_NAME)

from harness import export_util, profile, winutil  # noqa: E402
from m3_common import add_common_args, boot_session, ensure_gl_ready  # noqa: E402
import m7_common as m7  # noqa: E402
import m8_common as m8  # noqa: E402

LOG = "[puseed]"
USER_FIL = "Snapmaker PLA SnapSpeed @U1 - STD-TEST"


def patch_conf(datadir: Path, want: str) -> str:
    """把 conf 里 U1 那一项 orca_presets 的 filament_01（slot 2）设成用户预设。"""
    conf_path = datadir / "Snapmaker_Orca.conf"
    conf = profile.load_conf(conf_path)
    arr = conf.get("orca_presets")
    if not isinstance(arr, list) or not arr:
        return f"no orca_presets list (type={type(arr).__name__})"
    hit = None
    for entry in arr:
        if entry.get("machine", "").startswith("Snapmaker U1"):
            hit = entry
            break
    if hit is None:
        return f"no U1 entry; machines={[e.get('machine') for e in arr]}"
    before = hit.get("filament_01")
    hit["filament_01"] = want
    profile.write_conf(conf_path, conf)
    return f"filament_01: {before!r} -> {want!r}"


def shot(name, rect=None):
    import cv2
    import numpy as np
    sw, sh, buf = winutil.screen_grab()
    img = cv2.cvtColor(np.frombuffer(buf, np.uint8).reshape(sh, sw, 4),
                       cv2.COLOR_BGRA2BGR)
    if rect:
        img = img[max(0, rect[1] - 6):rect[3] + 6, max(0, rect[0] - 6):rect[2] + 6]
    cv2.imwrite(str(_HERE / "artifacts" / f"puseed_{name}.png"), img)
    print(f"{LOG} shot -> puseed_{name}.png")


def dump_panes(tag):
    panes = m8._picker_panes(session)
    print(f"{LOG} [{tag}] panes: {[(p['rect'], 'V' if p['is_vendor'] else 'F', len(p['rows'])) for p in panes]}")
    for p in panes:
        kind = "LEFT/vendor" if p["is_vendor"] else "RIGHT/filament"
        print(f"{LOG} [{tag}] {kind} rows:")
        for y, t, x in p["rows"]:
            print(f"{LOG}     y={y:5d} x={x:5d}  {t!r}")
    return panes


def main() -> int:
    global session
    ap = add_common_args(argparse.ArgumentParser(), default_model=None)
    args = ap.parse_args()
    args.model = None
    datadir = Path(args.datadir)
    # seed happens inside boot_session; we need it BEFORE launch, so re-seed here
    profile.seed_profile(datadir, fresh=True)
    print(f"{LOG} {patch_conf(datadir, USER_FIL)}")
    # boot_session re-seeds (fresh) and would wipe our patch — so seed with
    # fresh=False semantics: boot_session(fresh=True) rmtree+recopy. Patch AFTER
    # its seed by launching through launcher directly.
    from harness import launcher, shot_archive
    session = launcher.launch(exe=args.exe, datadir=datadir, model=None,
                              dismiss_wizard=True)
    _arch = shot_archive.start_archiver(session, "probe_241_userpreset_seeded")
    shot_archive.hook_stdout_tee(_arch)
    time.sleep(12.0)
    try:
        winutil.user32.ShowWindow(session.hwnd, 3)
        time.sleep(1.0)
    except Exception:                                          # noqa: BLE001
        pass
    ensure_gl_ready(session)
    winutil.demote_window(session.hwnd)
    try:
        m7.ensure_maximized(session)
        slots = m8.wait_slots(session)
        print(f"{LOG} slots: {[(s['slot'], m8.combo_text(s['combo'][2]) if s['combo'] else None) for s in slots]}")
        shot("00_slots")
        # user preset files present?
        for p in sorted((datadir / "user" / "default" / "filament").glob("*")):
            print(f"{LOG}   user preset on disk: {p.name}")
        pop, ch, how = m8._picker_open(session, 2)
        print(f"{LOG} picker open={bool(pop)} via {how!r} combo={m8.combo_text(ch) if ch else None!r}")
        if pop:
            time.sleep(0.9)
            panes = dump_panes("open")
            vend = next((p for p in panes if p["is_vendor"]), None)
            if vend:
                shot("01_left", vend["rect"])
                # 滚到顶 + 滚到底，看有没有被挤出去的分组
                for _i in range(12):
                    winutil.real_wheel_screen(vend["rect"][0] + 40,
                                              (vend["rect"][1] + vend["rect"][3]) // 2, 3)
                    time.sleep(0.12)
                time.sleep(0.5)
                dump_panes("left-top")
                for _i in range(12):
                    winutil.real_wheel_screen(vend["rect"][0] + 40,
                                              (vend["rect"][1] + vend["rect"][3]) // 2, -3)
                    time.sleep(0.12)
                time.sleep(0.5)
                dump_panes("left-bottom")
                shot("02_left_bottom")
            filt = m8._filament_pane(session)
            if filt:
                shot("03_right", filt["rect"])
            winutil.user32.keybd_event(0x1B, 0, 0, 0)
            time.sleep(0.05)
            winutil.user32.keybd_event(0x1B, 0, 2, 0)
            time.sleep(0.8)
        slots2 = m8.wait_slots(session)
        print(f"{LOG} slots after: {[(s['slot'], m8.combo_text(s['combo'][2]) if s['combo'] else None) for s in slots2]}")
        print(f"{LOG} app alive: {session.alive()}")
        return 0
    finally:
        session.close()
        print(f"{LOG} app closed")


if __name__ == "__main__":
    raise SystemExit(main())
