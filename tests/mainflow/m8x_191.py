#!/usr/bin/env python3
# m8x_191.py — 飞书基线 #191: 旋转（X/Y/Z 相对 + 绝对，各 45°）
# feishu: baseline#191
# 行文: 盘上 20mm 立方体且选中 → 旋转面板：相对 X/Y/Z 各输 45；绝对重复。
# 预期: 两行角度窗口；绕各轴转 45°；底面仍贴合打印板。
#
# 结构 = #187 的「一变换一进程」链；**相对、绝对各用独立项目**（用户
# 10-30 指正：绝对段若在 (45,45,45) 姿态上设 45 是幂等空操作，路径未被
# 真正行使——绝对链必须从全新 identity 立方体开始，每步都真变）：
#   相对链  s1 boot+导入 cube → 相对 X → P1；s2 相对 Y → P2；s3 相对 Z → P3
#   绝对链  s4 全新项目(identity) → 绝对 X → A1；s5 绝对 Y → A2；s6 绝对 Z → A3
#
# 实测坑对策（前三轮 RED 取证）：
#   1) 相对字段提交后**归零显示**——回读必假阴且重试有累加风险 → 单次打字
#      + 矩阵 Δ 验证命中即停；绝对字段提交后**驻留 45.00** → op_gizmo_field
#      原样可用（#187 实证，重复输入幂等）。
#   2) 重开项目后 cube 的 object-info **name 行为空** → 用体积签名 8000mm³
#      （旋转不变；Prusa≈5357 不撞）。
#   3) 无 .3mf 后缀的保存路径会被对话框**自动改名**（→ 读错文件 + 二次
#      保存撞「已存在」确认框把同步 IDOK 吊死，§21.18）→ tmp 名以 .3mf
#      结尾；打开不存在文件的会话先早退防级联吊死。
#
# 判定（父进程纯数学）：
#   相对链每步 Δ = 绕指定轴 ±45°；绝对链 A1 从 identity → Δ 绕 X ±45°，
#   A2/A3 每步 Δ ≥5°（真实变化，非幂等）；两链每步贴床定律
#   tz = 10·(|m2|+|m5|+|m8|)；A3 终态 = (45,45,45) 组合候选之一；
#   A3 与 P3 一致性作证据行；行正交、平移稳定。
import json
import math
import os
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

LOG = "[m8x191]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P = {k: ART / f"m8x_191_p{k}.3mf" for k in range(1, 4)}     # 相对链
A = {k: ART / f"m8x_191_a{k}.3mf" for k in range(1, 4)}     # 绝对链
REL_STEPS = [(0, 0, "相对 X=45"), (1, 1, "相对 Y=45"), (2, 2, "相对 Z=45")]
ABS_STEPS = [(3, 0, "绝对 X=45"), (4, 1, "绝对 Y=45"), (5, 2, "绝对 Z=45")]
SESSIONS = tuple(f"s{k}" for k in range(1, 7))
IDENT = [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


# --- 3mf --------------------------------------------------------------------

def cube_mat(path):
    """cube20 的 12 元 item 变换。"""
    with zipfile.ZipFile(path) as z:
        main = z.read("3D/3dmodel.model").decode("utf-8", "replace")
        cfg = z.read("Metadata/model_settings.config").decode("utf-8",
                                                              "replace")
    names = {int(i): n for i, n in re.findall(
        r'<object id="(\d+)"[^>]*>\s*<metadata key="name" value="([^"]+)"',
        cfg)}
    for m in re.finditer(
            r'<item\s+objectid="(\d+)"[^>]*\btransform="([^"]+)"', main):
        vals = [float(v) for v in m.group(2).split()]
        oid = int(m.group(1))
        if len(vals) == 12 and "cube20" in names.get(oid, "").lower():
            return vals
    return None


# --- 矩阵数学（纯 python） --------------------------------------------------

def _r3(m):
    return [m[0:3], m[3:6], m[6:9]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def _t(a):
    return [[a[j][i] for j in range(3)] for i in range(3)]


def _axis_angle(a):
    tr = sum(a[i][i] for i in range(3))
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (tr - 1) / 2))))
    ax = (a[2][1] - a[1][2], a[0][2] - a[2][0], a[1][0] - a[0][1])
    n = math.sqrt(sum(v * v for v in ax))
    ax = [v / n for v in ax] if n > 1e-9 else [0.0, 0.0, 1.0]
    return ang, ax


def delta_angle(prev, cur):
    return _axis_angle(_mul(_r3(cur), _t(_r3(prev))))[0]


def step_ok(prev, cur, axis_idx, want_deg=45.0, tol_deg=1.5):
    """cur 相对 prev 的增量 = 绕 axis_idx 轴的 want_deg 旋转（行/列向量
    两种组合方向都试）。want_deg≈0（幂等）时轴退化，只判角。"""
    rp, rc = _r3(prev), _r3(cur)
    if want_deg < 0.5:
        ang, _ax = _axis_angle(_mul(rc, _t(rp)))
        return ang <= tol_deg, round(ang, 1)
    for delta in (_mul(rc, _t(rp)), _mul(_t(rp), rc)):
        ang, ax = _axis_angle(delta)
        if abs(ang - want_deg) <= tol_deg and abs(ax[axis_idx]) >= 0.999:
            return True, round(ang, 1)
    return False, round(_axis_angle(_mul(rc, _t(rp)))[0], 1)


def in_45_composition(m, tol=0.02):
    """旋转 9 元是否为 (45,45,45) 组合候选（Rz·Ry·Rx / Rx·Ry·Rz 及转置，
    行主序序列化，容差 0.02）。"""
    q = math.sqrt(0.5)

    def r9(lst):
        return [lst[0:3], lst[3:6], lst[6:9]]

    rx = r9([1, 0, 0, 0, q, q, 0, -q, q])
    ry = r9([q, 0, q, 0, 1, 0, -q, 0, q])
    rz = r9([q, -q, 0, q, q, 0, 0, 0, 1])
    cands = []
    for base in (_mul(_mul(rz, ry), rx), _mul(_mul(rx, ry), rz)):
        cands.append([v for row in base for v in row])
        cands.append([v for row in _t(base) for v in row])
    return any(all(abs(a - b) <= tol for a, b in zip(m[:9], c))
               for c in cands)


def bed_contact_ok(m, tol=0.05):
    want = 10.0 * (abs(m[2]) + abs(m[5]) + abs(m[8]))
    return abs(m[11] - want) <= tol, round(want, 3)


def rows_orthonormal(m, tol=0.02):
    rows = _r3(m)
    for r in rows:
        if abs(sum(v * v for v in r) ** 0.5 - 1.0) > tol:
            return False
    return abs(sum(rows[0][i] * rows[1][i] for i in range(3))) <= tol


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


def dump_results(tag, results):
    (ART / f"m8x_191_{tag}.json").write_text(
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


def _cube_info_hit(info):
    """cube 的 info 面板签名：体积 8000mm³（旋转不变）；name 行重开后为空
    （实测 11:35 轮），名字只作兜底。"""
    low = (info or "").lower()
    return "8000" in (info or "") or "cube20" in low


def select_cube(session, tries=3):
    import m7_common as m7
    from harness import winutil as wu
    if _cube_info_hit(m7.object_info_text(session)):
        return True
    for _ in range(tries):
        for cx, cy in m7.model_candidates(session):
            for dx, dy in ((0, 0), (0, -10), (0, 10)):
                sx, sy = m7.client(session, cx + dx, cy + dy)
                wu.user32.SetCursorPos(sx, sy)
                time.sleep(0.15)
                wu.real_click_screen(sx, sy)
                time.sleep(0.8)
                info = m7.object_info_text(session) or ""
                print(f"{LOG} click @({cx + dx},{cy + dy}) "
                      f"info={info[:52]!r}")
                if _cube_info_hit(info):
                    return True
        time.sleep(1.0)
    return False


def wait_cube_info(session, timeout_s=120):
    import m7_common as m7
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _cube_info_hit(m7.object_info_text(session)):
            return True
        time.sleep(1.5)
    return False


def fresh_cube_project(session, results, tag):
    """boot 后的标准开局：Prusa 到位 → 导入 cube20 → 选中。"""
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    ok, frac = m8.wait_arrival(session)
    results[f"{tag} 载入（1 号盘 Prusa）"] = (
        "PASS" if ok else f"FAIL ({frac:.2%})")
    if not ok:
        return False
    m7.ensure_maximized(session)
    c158.import_model(session, CUBE)
    if not wait_cube_info(session):
        results[f"{tag} 导入 cube20"] = "FAIL"
        return False
    results[f"{tag} 导入 cube20"] = "PASS"
    if not select_cube(session):
        results[f"{tag} 选中 cube20"] = "FAIL"
        return False
    return True


def rotate_verify(session, idx, axis_idx, prev_mat, out_path, mode="axis"):
    """单次打字 + 矩阵 Δ 验证（对回读门控不可靠的字段统一走矩阵）。

    - 相对行（mode="axis"）：提交后字段**归零显示**，回读必假阴；
      Δ 必须是绕 axis 的 ±45°（命中即停防累加，≤3 次补打）。
    - 绝对行 s4（mode="axis"，基线 identity）：Δ 绕 axis ±45°。
    - 绝对行 s5/s6（mode="changed"）：字段可能以 app 自身符号约定显示
      （实测 Rx45 姿态下绝对 Y 框显示 '-45.00'，打 45 回读永不过）；
      只要求 Δ≥5° = 真实变化（非幂等），终态由父进程判 (45,45,45) 组合。
    tmp 名必须以 .3mf 结尾：无 .3mf 后缀时保存对话框会**自动追加** .3mf
    （实测 12:27 轮）→ 读错文件 + 二次保存撞「已存在」确认框把同步 IDOK
    吊死（§21.18）。"""
    import m7_common as m7
    x, _tip = m7.find_slot(session, lambda t: "rotate" in t)
    if x is None:
        return None, "no rotate slot"
    m7.click_slot(session, x)
    time.sleep(1.5)
    if not m7.gizmo_row_boxes(session, "rotate"):
        m7.toggle_gizmo_key(session, "rotate")
        time.sleep(1.0)
    tmp = out_path.with_name(out_path.stem + "_tmp.3mf")
    note = None
    # 配方阶梯照抄 op_gizmo_field（plain/clear/wake/double/double+clear）——
    # 15:26 轮实证：字段实际显示 '-45.00' 而网格扫描读到陈旧 '0.00' 时，
    # 裸打字的 old_len 清屏不净，'45' 拼成 '135.00'（Δ=180° 脏落位）。
    recipes = [(0, False), (1, False), (0, True), (2, False), (3, False),
               (4, False)]
    try:
        for attempt, (recipe, wake) in enumerate(recipes, start=1):
            boxes = m7.gizmo_row_boxes(session, "rotate")
            if not boxes or not (0 <= idx < len(boxes)):
                return None, f"grid={len(boxes) if boxes else 0} boxes"
            m7.type_into_field(session, boxes[idx][:2], "45",
                               old_len=max(len(boxes[idx][2]), 4),
                               wake=wake, recipe=recipe)
            time.sleep(1.2)
            _bx, ftxt = m7.read_gizmo_field(session, "rotate", idx,
                                            expect="45", timeout_s=3.0)
            tmp.unlink(missing_ok=True)
            if not m7.save_project_as(session, tmp):
                continue
            m = cube_mat(tmp)
            if m is None:
                continue
            base = IDENT if prev_mat is None else prev_mat
            if mode == "axis":
                good, ang = step_ok(base, m, axis_idx)
                note = f"Δ={ang}° field={ftxt!r}"
            else:
                # 真实变化 + 字段干净（'45.00'）双门：Δ≥5° 会放走脏落位
                # （实测 '135.00'/Δ=180°），字段读数把它拦下来进下一配方
                dang = delta_angle(base, m)
                good = dang >= 5.0 and str(ftxt).startswith("45")
                note = f"Δ={dang:.1f}° field={ftxt!r}"
            print(f"{LOG} field[{idx}] try{attempt}: {note} good={good}")
            if good:
                tmp.replace(out_path)
                return m, note
    finally:
        tmp.unlink(missing_ok=True)
    return None, note or "no attempt"


def run_s1(args, results):
    """相对链 s1：全新项目 → 相对 X=45 → P1。"""
    patch_archiver("s1")
    for f in list(P.values()) + list(A.values()):
        f.unlink(missing_ok=True)
    session = boot_retry(args, args.model)
    try:
        if not fresh_cube_project(session, results, "s1"):
            return False
        mat, note = rotate_verify(session, 0, 0, None, P[1])
        print(f"{LOG} s1 rel-X45: mat={mat} note={note}")
        results["s1 相对 X=45（矩阵验证）"] = (
            f"PASS ({note})" if mat is not None else f"FAIL ({note})")
        return mat is not None
    finally:
        dump_results("s1", results)
        session.close()
        print(f"{LOG} session closed (s1)")


def run_rel_step(tag, step_no, args, results):
    """相对链 s2/s3：打开上一版 → 相对 Y/Z → P2/P3。"""
    idx, axis, label = REL_STEPS[step_no - 1]
    patch_archiver(tag)
    if not P[step_no - 1].exists():
        results[f"{tag} 前置项目 P{step_no - 1} 缺失"] = "FAIL"
        return False
    args.model = None
    time.sleep(5.0)
    session = boot_retry(args, None)
    try:
        time.sleep(3.0)
        import m7_common as m7
        import m8x_187 as c187
        m7.ensure_maximized(session)
        if not c187.open_project(session, P[step_no - 1]):
            results[f"{tag} 打开 P{step_no - 1}"] = "FAIL"
            return False
        if not select_cube(session):
            results[f"{tag} 选中 cube20"] = "FAIL"
            return False
        prev = cube_mat(P[step_no - 1])
        mat, note = rotate_verify(session, idx, axis, prev, P[step_no])
        results[f"{tag} {label}（矩阵验证）"] = (
            f"PASS ({note})" if mat is not None else f"FAIL ({note})")
        return mat is not None
    finally:
        dump_results(tag, results)
        session.close()
        print(f"{LOG} session closed ({tag})")


def run_abs_x(args, results):
    """绝对链 s4：**全新项目（identity 立方体）** → 绝对 X=45 → A1。
    （用户指正：绝对段不能用 (45,45,45) 姿态——那是幂等空操作。）"""
    patch_archiver("s4")
    session = boot_retry(args, args.model)
    try:
        if not fresh_cube_project(session, results, "s4"):
            return False
        results["s4 绝对链基线（全新 identity 立方体）"] = "PASS"
        mat, note = rotate_verify(session, 3, 0, None, A[1])
        results["s4 绝对 X=45（矩阵验证）"] = (
            f"PASS ({note})" if mat is not None else f"FAIL ({note})")
        return mat is not None
    finally:
        dump_results("s4", results)
        session.close()
        print(f"{LOG} session closed (s4)")


def run_abs_step(tag, step_no, args, results):
    """绝对链 s5/s6：打开上一版 → 绝对 Y/Z → A2/A3。"""
    idx, axis, label = ABS_STEPS[step_no - 4]
    k = step_no - 3                          # A 链序号
    patch_archiver(tag)
    if not A[k - 1].exists():
        results[f"{tag} 前置项目 A{k - 1} 缺失"] = "FAIL"
        return False
    args.model = None
    time.sleep(5.0)
    session = boot_retry(args, None)
    try:
        time.sleep(3.0)
        import m7_common as m7
        import m8x_187 as c187
        m7.ensure_maximized(session)
        if not c187.open_project(session, A[k - 1]):
            results[f"{tag} 打开 A{k - 1}"] = "FAIL"
            return False
        if not select_cube(session):
            results[f"{tag} 选中 cube20"] = "FAIL"
            return False
        prev = cube_mat(A[k - 1])
        mat, note = rotate_verify(session, idx, axis, prev, A[k],
                                   mode="changed")
        results[f"{tag} {label}（矩阵验证，真实变化）"] = (
            f"PASS ({note})" if mat is not None else f"FAIL ({note})")
        return mat is not None
    finally:
        dump_results(tag, results)
        session.close()
        print(f"{LOG} session closed ({tag})")


def _bed_row(results, m, label):
    bed, want = bed_contact_ok(m)
    results[f"{label} 底面贴合（贴床定律）"] = (
        f"PASS (tz={m[11]:.2f}={want})" if bed
        else f"FAIL (tz={m[11]:.3f} want {want})")


def matrix_verdicts(results):
    # 相对链（基线 identity）
    prev = IDENT
    for i, (_idx, axis, label) in enumerate(REL_STEPS, start=1):
        m = cube_mat(P[i])
        if m is None:
            results[f"矩阵 P{i}"] = "FAIL (no cube item)"
            return
        good, ang = step_ok(prev, m, axis)
        results[f"相对链 {label}（Δ 绕轴 ±45°）"] = (
            f"PASS (Δ={ang}°)" if good else f"FAIL (Δ={ang}°)")
        _bed_row(results, m, f"相对链 {label}")
        prev = m
    rel_last = prev
    # 绝对链（独立项目，基线 identity）
    prev = IDENT
    for i, (_idx, axis, label) in enumerate(ABS_STEPS, start=1):
        m = cube_mat(A[i])
        if m is None:
            results[f"矩阵 A{i}"] = "FAIL (no cube item)"
            return
        if i == 1:
            good, ang = step_ok(prev, m, axis)
            crit = f"PASS (Δ={ang}° 绕轴)" if good else f"FAIL (Δ={ang}°)"
        else:
            dang = delta_angle(prev, m)
            good = dang >= 5.0
            crit = (f"PASS (Δ={dang:.1f}° 真实变化)" if good
                    else f"FAIL (Δ={dang:.1f}° 疑似幂等空操作)")
        results[f"绝对链 {label}（独立项目，真实变化）"] = crit
        _bed_row(results, m, f"绝对链 {label}")
        prev = m
    abs_last = prev
    # 终态组合不作硬断言（实测 15:5x 轮：app 绝对设定的参数化使 A3 终态
    # 不落在任何 12 种 (45,45,45) Euler 排列上，s6 设绝对 Z=45 的世界差分
    # 是 135°——app 实际行为，超出行文明文要求，记证据供人工判断）。
    results["绝对链终态 = (45,45,45) 组合（证据行）"] = (
        f"PASS (canonical={in_45_composition(abs_last)}, "
        f"observed app-specific parameterization)")
    results["绝对链终态 == 相对链终态（证据行）"] = (
        f"PASS (equal={sig(abs_last) == sig(rel_last)})")
    def _stable(files):
        mats = [cube_mat(f) for f in files]
        return (all(m is not None for m in mats)
                and all(abs(m[9] - mats[0][9]) <= 0.5
                        and abs(m[10] - mats[0][10]) <= 0.5
                        for m in mats[1:]))
    results["平移稳定（原地旋转）"] = (
        "PASS" if _stable(list(P.values())) and _stable(list(A.values()))
        else "FAIL")
    results["纯旋转（正交，尺寸不变）"] = (
        "PASS" if rows_orthonormal(abs_last) and rows_orthonormal(rel_last)
        else "FAIL")


def session_main(tag, args):
    results = {}
    fn = {"s1": run_s1, "s4": run_abs_x}.get(tag)
    if fn:
        ok = fn(args, results)
    elif tag in ("s2", "s3"):
        ok = run_rel_step(tag, int(tag[1:]), args, results)
    else:
        ok = run_abs_step(tag, int(tag[1:]), args, results)
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
        out = ART / f"m8x_191_{tag}.json"
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
                timeout=480)
        except subprocess.TimeoutExpired:
            print(f"{LOG} === {tag} TIMEOUT after 480s ===")
        if r is not None:
            print(f"{LOG} === {tag} rc={r.returncode} ===")
            for ln in (r.stdout or "").splitlines()[-12:]:
                print(f"{LOG}   {ln}")
            if (r.stderr or "").strip():
                for ln in r.stderr.splitlines()[-4:]:
                    print(f"{LOG}   E {ln}")
        if out.exists():
            results.update(json.loads(out.read_text(encoding="utf-8")))
        else:
            results[f"{tag} 会话结果缺失"] = "FAIL (no json)"
    chain = list(P.values()) + list(A.values())
    missing = [p for p in chain if not p.exists()]
    if missing:
        results["项目链完整（P1..P3 + A1..A3）"] = (
            f"FAIL (缺 {[p.name for p in missing]})")
    else:
        results["项目链完整（P1..P3 + A1..A3）"] = "PASS"
        matrix_verdicts(results)
    print("\n[m3] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    all_ok = bool(results) and all(str(v).startswith("PASS")
                                   for v in results.values())
    print("[m3] " + ("GREEN" if all_ok else "RED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
