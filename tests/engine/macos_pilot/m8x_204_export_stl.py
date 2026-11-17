#!/usr/bin/env python3
# m8x_204_export_stl.py — macOS port: Feishu #204 export STL.
# feishu: none  (macOS port; corresponds to the enabled Windows m8x_204,
#         registered in cases.MACOS_BASELINE)
#
# Windows assertions:
#   1) File > Export submenu lists STL
#   2) export writes a valid STL (binary 84+50n or ascii facets, triangles > 0)
#   3) the exported STL can be re-imported
#
# macOS mapping:
#   Export entry  -> the File menu has flat rows instead of a submenu:
#                    "Export all objects as one STL..." / "...as STLs...".
#                    The check maps to "the File menu lists STL exports".
#   save dialog   -> NSSavePanel + driver.save_file_dialog (default folder is
#                    the model's directory, i.e. this case's work dir).
#   re-import     -> Import 3MF/STL... + driver.open_file_dialog, then the
#                    object list must show the exported file's name.
#
# Artifacts: artifacts/mac/pilot/m8x_204/{report.log,result.json,
# work/*.stl, before/after_import.png}.

from __future__ import annotations

import argparse
import shutil
import struct
import sys
import time
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parents[3]       # repo root
ENGINE = Path(__file__).resolve().parents[1]     # tests/engine
PILOTS = Path(__file__).resolve().parent         # tests/engine/macos_pilot
for path in (str(HERE), str(ENGINE), str(PILOTS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from harness.platform.factory import get_driver  # noqa: E402
from harness.platform.macos_ocr import (  # noqa: E402
    joined_text, recognize_text,
)
from mac_common import (  # noqa: E402
    ARTIFACTS, Reporter, close_app, launch_and_focus,
)
import m7b_new_project as m7b  # noqa: E402

OUT = ARTIFACTS / "pilot" / "m8x_204"
DEFAULT_MODEL = HERE / "fixtures" / "Prusa.stl"
COLORED_GATE = 0.0025


def stl_triangles(path: Path):
    """(kind, triangles) — binary 84+50n, else ascii facet count."""
    data = path.read_bytes()
    if len(data) >= 84:
        n = struct.unpack_from("<I", data, 80)[0]
        if len(data) == 84 + 50 * n:
            return "binary", n
    head = data[:200].lower()
    if b"facet" in head or head.lstrip().startswith(b"solid"):
        return "ascii", data.lower().count(b"facet normal")
    return "unknown", 0


def menu_items(driver, win, needle: str):
    return [c for c in driver.controls(win, max_depth=12)
            if c.role == "AXMenuItem" and needle in c.title.lower()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", default=None)
    ap.add_argument("--datadir", default=OUT / "profile", type=Path)
    ap.add_argument("--model", default=DEFAULT_MODEL, type=Path)
    ap.add_argument("--timeout", default=150.0, type=float)
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()

    work = OUT / "work"
    for path in (args.datadir, work):
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    inputs = work / "inputs"
    export_dir = work / "export"
    inputs.mkdir(parents=True)
    export_dir.mkdir(parents=True)
    model = inputs / "m8x_204_model.stl"
    shutil.copy2(args.model, model)
    # Export here, not next to the model: the panel's default name equals the
    # project name, which would collide with the model file and raise the
    # overwrite prompt.
    out_stl = export_dir / "m8x_204_export.stl"

    rep = Reporter(OUT)
    rep.log("=== m8x_204 macOS export STL ===")
    rep.log(f"datadir={args.datadir} model={model}")

    driver = None
    app = None
    win = None
    exit_code = 2
    try:
        driver = get_driver()
        rep.check("driver available", True, type(driver).__name__)
        app, win = launch_and_focus(
            driver, args.datadir, model=model,
            timeout_s=args.timeout, log_path=OUT / "app_launch.log")
        rep.check("launch", True,
                  f"pid={app.pid} title={win.title!r} "
                  f"blockers={app.extra.get('blockers')}")
        time.sleep(3.0)

        # Wait for the model, then select it (Windows select_object_strict).
        deadline = time.monotonic() + 60.0
        vp = 0.0
        while time.monotonic() < deadline:
            vp = m7b._vp_colored(driver.capture(win))
            if vp >= COLORED_GATE:
                break
            time.sleep(1.0)
        rep.check("载入模型", vp >= COLORED_GATE, f"viewport={vp:.4f}")
        sel = driver.find_control(win, role="AXMenuItem",
                                  title="Select All", timeout_s=3)
        rep.check("Select All 可用", sel is not None and sel.enabled,
                  f"enabled={getattr(sel, 'enabled', None)}")
        if sel is not None:
            driver.click_control(sel)
            time.sleep(1.0)

        # --- 1) File menu lists the STL export ------------------------
        stl_rows = menu_items(driver, win, "stl")
        rep.log(f"[INFO] STL menu rows: {[(c.title, c.enabled) for c in stl_rows]}")
        rep.check("File 菜单列出 STL 导出项",
                  any("export" in c.title.lower() for c in stl_rows),
                  f"rows={[c.title for c in stl_rows]}")

        export = next((c for c in stl_rows
                       if c.title.strip().lower().startswith("export all objects as one")
                       and "stl" in c.title.lower()), None)
        if export is None:
            export = next((c for c in stl_rows
                           if "export" in c.title.lower()), None)
        rep.check("STL 导出入口可点",
                  export is not None and export.enabled,
                  f"item={export.title if export else None}")

        # --- 2) Export -> save dialog -> valid STL --------------------
        out_stl.unlink(missing_ok=True)
        pressed = driver.click_control(export) if export is not None else False
        rep.log(f"[INFO] press {export.title if export else None!r} -> {pressed}")
        # The STL export panel remembers a global last-used folder and appends
        # its own .stl extension.  Do not navigate its deep column view: save
        # wherever it defaults, then claim the newest fresh .stl under our
        # artifact tree and move it to the case target.
        exported = driver.save_file_dialog(
            win, out_stl, default_dir=export_dir,
            titles=("save", "save as", "export", "export stl"),
            accept_anywhere=True, name_is_stem=True,
            search_roots=(HERE / "artifacts" / "mac",
                          Path.home() / "Documents",
                          Path.home() / "Desktop",
                          Path.home() / "Downloads"))
        rep.check("导出生成 STL 文件", exported and out_stl.exists(),
                  f"size={out_stl.stat().st_size if out_stl.exists() else 0}")
        if not out_stl.exists():
            raise RuntimeError("export produced no STL")
        kind, tris = stl_triangles(out_stl)
        rep.log(f"[INFO] exported STL: kind={kind} triangles={tris}")
        rep.check("STL 合法（binary/ascii 且三角形>0）",
                  kind != "unknown" and tris > 0, f"kind={kind} tris={tris}")

        # --- 3) re-import the exported STL ----------------------------
        before = driver.capture(win)
        before.save_png(OUT / "before_import.png")
        rows = [c for c in driver.controls(win, max_depth=12)
                if c.role == "AXMenuItem"
                and c.title.strip().lower().startswith("import ")
                and "3mf" in c.title.lower()]
        rep.check("导入入口可用", bool(rows))
        driver.click_control(rows[0])
        reimported = driver.open_file_dialog(win, out_stl)
        rep.check("导出 STL 可被重新导入", reimported)

        # The object list should name the imported file.  Only accept OCR
        # evidence once the open panel is gone: while it is up, its file row
        # contains the same name and would be a false positive.
        rep.check("导入后应用存活", app.alive())
        deadline = time.monotonic() + 60.0
        stem_ok = False
        last_text = ""
        while time.monotonic() < deadline:
            panel_open = driver.find_file_dialog(
                win.pid, titles=driver._OPEN_PANEL_TITLES,
                exclude_id=win.id, timeout_s=0.0) is not None
            if not panel_open:
                words = recognize_text(driver.capture_screen().crop(win.rect))
                last_text = joined_text(words)
                if "m8x_204_export" in last_text.lower():
                    stem_ok = True
                    break
            time.sleep(2.0)
        after = driver.capture(win)
        after.save_png(OUT / "after_import.png")
        title = driver._refresh(win).title
        rep.log(f"[INFO] after re-import: title={title!r} "
                f"object_name_seen={stem_ok} ocr={last_text[:160]!r}")
        rep.check("对象列表显示导入模型名", reimported and stem_ok,
                  f"title={title!r}")

        rep.check("app alive", app.alive())
    except Exception as exc:  # noqa: BLE001
        rep.check("unexpected", False, f"{type(exc).__name__}: {exc}")
        traceback.print_exc()
    finally:
        if app is not None and not args.keep:
            try:
                rep.check("close", close_app(driver, app, win))
            except Exception as exc:  # noqa: BLE001
                rep.check("close", False, f"{type(exc).__name__}: {exc}")
        elif app is not None:
            rep.log(f"[INFO] --keep: app pid={app.pid} left running")
        exit_code = rep.save({"covered": ["#204"]})
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
