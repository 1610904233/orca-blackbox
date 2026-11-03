#!/usr/bin/env python3
# m8x_187.py — 飞书基线 #187: 自动定位/调整对象（Shift+Q / Q）
# feishu: baseline#187
# 前置（按行文）：**两个以上盘**，每盘上都有倾斜放置的模型
# 步骤: Shift+Q（当前盘）→ Q（所有盘）→ 观察朝向
# 预期: 当前盘模型自动旋转到较优朝向；所有盘模型同样；仍在盘内且底面贴合；尺寸不变
#
# 判据 = 3mf 里各 build item 的**变换矩阵**（精确，不受渲染噪声影响）：
#   P  = 基线：两个盘各一个倾斜模型（X 轴 45°）
#   PA = 按 Shift+Q 后（**应只有 1 个 item 变化** = 只有当前盘）
#   PB = 按 Q 后（**所有 item 底面贴合** = 某旋转行 ≈(0,0,±1)；
#        auto-orient 不保证 yaw 轴对齐——cube 面着地但偏航 45° 是正确结果）
#   另：所有 item 旋转行范数 ≈ 1（尺寸不变）；tz 不增（底面落到床上）
#
# 键盘：先切英文布局（中文 IME 会吞掉 Shift+Q —— 测试方 10-29 指出）
#
# 多进程（同会话第 2 个 gizmo 面板会失聪）：
#   s1 旋转 X=45 → 加第二个盘 → 在新盘导入 cube20 → 另存 P
#   s2 打开 P → 按名选中 cube20 → 绝对 X=45（0→45 真变化）→ 普通保存写回 P
#   （全选方案已否决：混合旋转值让 absolute 字段呈混合态，打字永远落不进；
#     另存为覆盖 P 已否决：同步 IDOK 吊死在「是否替换」确认框 → 普通保存）
#   s3 打开 P → Shift+Q → 另存 PA → Q → 另存 PB → 判定
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE / "tests"))
for _g in sorted((HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

LOG = "[m8x187]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P = ART / "m8x_187_proj.3mf"
PA = ART / "m8x_187_after_shiftq.3mf"
PB = ART / "m8x_187_after_q.3mf"
SESSIONS = ("s1", "s2", "s3")


# --- 3mf 变换 ---------------------------------------------------------------

def item_mats(path: Path):
    """所有 .model part 里的 build item 变换（12 个数，行主序 3x4）。"""
    out = []
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith(".model"):
                    continue
                txt = z.read(name).decode("utf-8", "replace")
                for m in re.finditer(r'<item\b[^>]*\btransform="([^"]+)"',
                                     txt):
                    vals = [float(v) for v in m.group(1).split()]
                    if len(vals) == 12:
                        out.append(vals)
    except Exception as exc:                                   # noqa: BLE001
        print(f"{LOG} read {path.name} failed: {exc!r}")
    return out


def rot_rows(m):
    """旋转的 3 行（3MF 行主序：m[0:3]/m[3:6]/m[6:9]；m[9:12] 是平移）。"""
    return [m[0:3], m[3:6], m[6:9]]


def is_axis_aligned(m, tol=0.02):
    """旋转部分是否轴对齐（每行恰有一个 ≈±1，其余 ≈0）。"""
    for row in rot_rows(m):
        big = sum(1 for v in row if abs(abs(v) - 1.0) < tol)
        small = sum(1 for v in row if abs(v) < tol)
        if not (big == 1 and small == 2):
            return False
    return True


def face_down(m, tol=0.02):
    """较优朝向的客观判据：某一局部轴竖直（某旋转行 ≈ (0,0,±1)）= 模型以
    面着地。auto-orient 只保证底面贴合/悬空最少，**不保证水平偏航对齐轴**
    （实测 10-30：cube 倾 45° 时棱着地 tz=10√2≈14.14，Q 后 r0=(0,0,-1)、
    tz=10=20/2 面着地，但 yaw 45°——对可打印性无影响，轴对齐判据会把
    正确行为误判 FAIL）。"""
    return any(abs(r[0]) < tol and abs(r[1]) < tol
               and abs(abs(r[2]) - 1.0) < tol for r in rot_rows(m))


def scale_ok(m, tol=0.02):
    for row in rot_rows(m):
        if abs(sum(v * v for v in row) ** 0.5 - 1.0) > tol:
            return False
    return True


def sig(m):
    return tuple(round(v, 3) for v in m)


# --- 工具 -------------------------------------------------------------------

def patch_archiver(tag):
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def english_layout(session):
    """切英文键盘布局（中文 IME 会吞 Shift+Q）。"""
    import ctypes
    u = ctypes.WinDLL("user32")
    hkl = u.LoadKeyboardLayoutW("00000409", 0x00000001)   # KLF_ACTIVATE
    u.PostMessageW(session.hwnd, 0x0050, 0, hkl)           # WM_INPUTLANGCHANGE
    time.sleep(0.8)
    print(f"{LOG} english layout hkl=0x{hkl & 0xffffffff:x}")
    return hkl


def press(session, vk, shift=False):
    from harness import winutil as wu
    if shift:
        wu.user32.keybd_event(0x10, 0, 0, 0)
        time.sleep(0.05)
    wu.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.06)
    wu.user32.keybd_event(vk, 0, 2, 0)
    if shift:
        time.sleep(0.05)
        wu.user32.keybd_event(0x10, 0, 2, 0)
    time.sleep(0.4)


def focus_canvas(session):
    import m7_common as m7
    from harness import winutil as _wu
    sx, sy = m7.client(session, m7.VIEWPORT_X0 + 60, 700)
    _wu.user32.SetCursorPos(sx, sy)
    time.sleep(0.2)
    _wu.real_click_screen(sx, sy)
    time.sleep(0.6)


def open_project(session, path):
    import m7_common as m7
    from harness import export_util, topbar_util, winutil
    menu = topbar_util.open_file_menu(session)
    if not menu:
        return False
    _r, mhwnd, mhmenu = menu
    print(f"{LOG} file menu: {[l for _i, l in m7.list_menu(mhmenu)]}")
    time.sleep(0.8)
    if m7.click_menu_row(session, mhwnd, mhmenu, "open project") is None:
        m7.dismiss_menus(session)
        return False
    dlg = m7.wait_dialog(session.pid, timeout_s=10.0, title_substr="open")
    if not dlg:
        dlg = m7.wait_dialog(session.pid, timeout_s=5.0)
    if not dlg:
        return False
    edit = export_util.find_edit(dlg[3])
    if edit is None:
        return False
    winutil.select_all(edit)
    winutil.msg_text(edit, str(path))
    import ctypes
    ctypes.WinDLL("user32").SendMessageW(dlg[3], 0x0111, 1, 0)
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline:
        if m7.model_colored_frac(session) >= 0.0025:
            time.sleep(3.0)
            return True
        time.sleep(1.5)
    return False


def tilt_x_abs(session, deg):
    """把当前选中对象（可多选）绕**绝对 X** 转 deg 度（本会话唯一一次 gizmo）。"""
    import m7_common as m7
    ok, txt = m7.op_gizmo_field(session, lambda t: "rotate" in t,
                                "rotate", 3, str(deg))
    print(f"{LOG} tilt X={deg}: ok={ok} read={txt!r}")
    return ok


def find_and_select_cube(session, tries=3):
    """遍历候选点、按 object-info 面板认出 cube20 并选中它（方案 B+）。

    全选两个旋转值不同的模型时 absolute 字段呈混合态（读作 0-00），
    op_gizmo_field 的打字 recipe 全部落空（实测 10-30：'char 3 not landed
    yet'，循环 ~12 分钟后被客机 DWM 崩溃风暴连锅端）。单选 cube 字段干净
    （0→45 是真变化），与 s1 已验证的打字路径完全一致。"""
    import m7_common as m7
    from harness import winutil as wu
    for _ in range(tries):
        for cx, cy in m7.model_candidates(session):
            sx, sy = m7.client(session, cx, cy)
            wu.user32.SetCursorPos(sx, sy)
            time.sleep(0.2)
            wu.real_click_screen(sx, sy)
            time.sleep(0.9)
            info = m7.object_info_text(session) or ""
            print(f"{LOG} click @({cx},{cy}) info={info[:60]!r}")
            if "cube20" in info.lower():
                return (cx, cy)
        time.sleep(1.0)
    return None


# --- 会话 -------------------------------------------------------------------

def boot_retry(args, model, tries=3):
    """boot_session 带重试：上一会话 app 刚退出时 datadir 里可能还有文件锁，
    fresh seed 会抛 shutil.Error(WinError 183)（实测 10-29：s2 因此直接崩）。"""
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


def run_s1(args, results):
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158

    patch_archiver("s1")
    for f in (P, PA, PB):
        f.unlink(missing_ok=True)
    session = boot_retry(args, args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["s1 载入模型（1 号盘）"] = "PASS" if ok else f"FAIL ({frac:.2%})"
        if not ok:
            return False
        m7.ensure_maximized(session)
        if not m7.select_object_strict(session):
            results["s1 选中模型"] = "FAIL"
            return False
        results["s1 选中模型"] = "PASS"
        results["s1 1 号盘模型倾斜 X=45"] = (
            "PASS" if tilt_x_abs(session, 45) else "FAIL")
        # 「Add plate」的 tooltip OCR 常读到乱码（实测 'SO US =~'），所以这里
        # 只记证据、不作判定；加盘是否成功由后面"项目里有 2 个 item"来证明。
        tip = m7.tooltip_text(session, 756, m7.BAR_Y)
        results["s1 添加新盘（证据行，tooltip 常乱码）"] = (
            f"PASS (tip={tip!r})")
        m7.click_slot(session, 756)
        time.sleep(4.0)
        c158.import_model(session, CUBE)
        deadline = time.monotonic() + 120
        arrived = False
        while time.monotonic() < deadline:
            if "cube20" in (m7.object_info_text(session) or "").lower():
                arrived = True
                break
            time.sleep(1.5)
        results["s1 新盘导入 cube20"] = "PASS" if arrived else "FAIL"
        if not arrived:
            return False
        saved = m7.save_project_as(session, P)
        mats = item_mats(P)
        results["s1 另存 P（两盘两模型）"] = (
            f"PASS ({len(mats)} item(s))" if saved and len(mats) >= 2
            else f"FAIL (items={len(mats)})")
        return bool(mats) and len(mats) >= 2
    finally:
        dump_results("s1", results)        # close() 挂起也不丢判定证据
        session.close()
        print(f"{LOG} session closed (s1)")


def save_plain(session, path):
    """文件 → 保存项目（原地写回）。已命名项目的普通保存是静默的。

    不能用 save_project_as 覆盖已存在的 P：IDOK 是同步 SendMessageW，目标
    已存在时系统弹『是否替换』内联确认框，发送方**永远不返回**（实测 10-30
    s2 因此吊死 10 分钟直到会话超时）。用文件 mtime 变化验证写入完成。"""
    import m8x_201 as c201
    t0 = path.stat().st_mtime if path.exists() else 0.0
    ok, dlg = c201.save_project(session)
    if dlg or not ok:
        print(f"{LOG} plain save: ok={ok} dialog={dlg}")
        return False
    for _ in range(40):
        try:
            if (path.exists() and path.stat().st_mtime > t0
                    and path.stat().st_size > 0):
                return True
        except OSError:
            pass
        time.sleep(1.0)
    return False


def run_s2(args, results):
    import m7_common as m7

    patch_archiver("s2")
    args.model = None
    time.sleep(5.0)                       # 给上一会话的 app 留时间释放文件锁
    session = boot_retry(args, None)
    try:
        time.sleep(3.0)
        m7.ensure_maximized(session)
        results["s2 打开项目 P"] = "PASS" if open_project(session, P) else "FAIL"
        mats0 = item_mats(P)              # s1 的基线：Prusa 斜 45 / cube 正放
        hit = find_and_select_cube(session)
        results["s2 按名选中 cube20"] = (
            f"PASS (info @ {hit})" if hit
            else "FAIL (2 号盘 cube 不可见/点不中)")
        if not hit:
            return False
        results["s2 cube20 倾斜 X=45"] = (
            "PASS" if tilt_x_abs(session, 45) else "FAIL")
        if not save_plain(session, P):
            results["s2 保存 P（普通保存原地写回）"] = "FAIL"
            return False
        mats = item_mats(P)
        changed = [i for i, (a, b) in enumerate(zip(mats0, mats))
                   if sig(a) != sig(b)]
        tilted = [m for m in mats if not is_axis_aligned(m)]
        print(f"{LOG} s2 changed={changed} tilted={len(tilted)}/{len(mats)}")
        results["s2 倾斜生效（≥1 个 item 变化）"] = (
            f"PASS (item {changed})" if len(mats) >= 1 and len(changed) >= 1
            else f"FAIL (changed={changed}, items={len(mats)})")
        results["s2 基线：两模型均倾斜"] = (
            f"PASS ({len(tilted)}/{len(mats)} 倾斜)"
            if len(mats) >= 2 and len(tilted) == len(mats)
            else f"FAIL ({len(tilted)}/{len(mats)} 倾斜)")
        return (len(mats) >= 2 and len(tilted) == len(mats)
                and len(changed) >= 1)
    finally:
        dump_results("s2", results)
        session.close()
        print(f"{LOG} session closed (s2)")


def run_s3(args, results):
    import m7_common as m7

    patch_archiver("s3")
    args.model = None
    PA.unlink(missing_ok=True)             # 防旧文件 + 防覆盖确认框吊死 IDOK
    PB.unlink(missing_ok=True)
    time.sleep(5.0)
    session = boot_retry(args, None)
    try:
        time.sleep(3.0)
        m7.ensure_maximized(session)
        results["s3 打开项目 P"] = "PASS" if open_project(session, P) else "FAIL"
        english_layout(session)
        m0 = item_mats(P)
        print(f"{LOG} baseline mats={m0}")

        # 1) Shift+Q → 应只改**当前盘**那一个
        focus_canvas(session)
        press(session, 0x51, shift=True)
        time.sleep(4.0)
        if not m7.save_project_as(session, PA):
            results["s3 另存 PA（Shift+Q 后）"] = "FAIL"
            return False
        m1 = item_mats(PA)
        changed = [i for i, (a, b) in enumerate(zip(m0, m1))
                   if sig(a) != sig(b)]
        print(f"{LOG} after Shift+Q: mats={m1} changed={changed}")
        results["Shift+Q 只改当前盘（恰 1 个 item 变化）"] = (
            f"PASS (item {changed})" if len(changed) == 1
            else f"FAIL (changed={changed}, items={len(m0)})")

        # 2) Q → 所有盘摆平
        focus_canvas(session)
        press(session, 0x51)
        time.sleep(4.0)
        if not m7.save_project_as(session, PB):
            results["s3 另存 PB（Q 后）"] = "FAIL"
            return False
        m2 = item_mats(PB)
        print(f"{LOG} after Q: mats={m2}")
        faced = [face_down(m) for m in m2]
        axis = [is_axis_aligned(m) for m in m2]
        print(f"{LOG} after Q: face_down={faced} axis_aligned={axis}")
        results["Q 摆平所有盘（所有 item 底面贴合）"] = (
            f"PASS ({sum(faced)}/{len(m2)} 面着地, axis={axis})"
            if m2 and all(faced) else f"FAIL (face_down={faced})")
        results["尺寸不变（所有 item 缩放≈1）"] = (
            f"PASS ({len(m2)} items)" if m2 and all(scale_ok(m) for m in m2)
            else "FAIL (scale deviates)")
        tz0 = [round(m[11], 2) for m in m0]
        tz2 = [round(m[11], 2) for m in m2]
        print(f"{LOG} tz: baseline={tz0} after Q={tz2}")
        results["底面贴合（tz 不增）"] = (
            f"PASS ({tz0} -> {tz2})"
            if all(b <= a + 0.5 for a, b in zip(tz0, tz2))
            else f"FAIL ({tz0} -> {tz2})")
        return all(str(v).startswith("PASS") for v in results.values())
    finally:
        dump_results("s3", results)
        session.close()
        print(f"{LOG} session closed (s3)")


def dump_results(tag, results):
    (ART / f"m8x_187_{tag}.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")


def session_main(tag, args):
    results = {}
    fn = {"s1": run_s1, "s2": run_s2, "s3": run_s3}[tag]
    ok = fn(args, results)
    dump_results(tag, results)
    return 0 if ok else 1


def main() -> int:
    import argparse
    import os
    from m3_common import add_common_args
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    ap.add_argument("--session", choices=SESSIONS, default=None)
    args = ap.parse_args()
    if args.session:
        return session_main(args.session, args)
    results = {}
    for tag in SESSIONS:
        out = ART / f"m8x_187_{tag}.json"
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
                timeout=900)
        except subprocess.TimeoutExpired:
            # 10-29 实测：s2 挂起 900s 后 TimeoutExpired 没人接，父进程整个
            # 崩掉，s3 连跑的机会都没有。接住、记 FAIL、继续下一个会话。
            print(f"{LOG} === {tag} TIMEOUT after 900s ===")
        if r is not None:
            print(f"{LOG} === {tag} rc={r.returncode} ===")
            for ln in (r.stdout or "").splitlines()[-40:]:
                print(f"{LOG}   {ln}")
            if (r.stderr or "").strip():
                for ln in r.stderr.splitlines()[-6:]:
                    print(f"{LOG}   E {ln}")
        if out.exists():
            results.update(json.loads(out.read_text(encoding="utf-8")))
        else:
            results[f"{tag} 会话结果缺失"] = "FAIL (no json)"
    print("\n[m3] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    all_ok = bool(results) and all(str(v).startswith("PASS")
                                   for v in results.values())
    print("[m3] " + ("GREEN" if all_ok else "RED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
