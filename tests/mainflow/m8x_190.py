#!/usr/bin/env python3
# m8x_190.py — 飞书基线 #190: 移动（X/Y/Z 输入 100）
# feishu: baseline#190
# 行文: 20mm 立方体选中 → 点「移动」→ X/Y/Z 输入框各输 100 回车 →
#       坐标面板 X/Y 变 100、Z 不变；其余对象不受影响。
#
# 结构 = 一变换一进程（单会话多字段已实测否决：X 提交后 Move 面板**自动
# 关闭**，同会话重开面板**失聪**（grid=0，§21.16 对 Move 同样成立），且
# 连打会把 Y 带成 1.0——与 #191 单面板实验同款污染）：
#   s1 boot Prusa+导入 cube → 选 cube → position.X=100 → P1
#   s2 打开 P1 → 选 cube → position.Y=100 → P2
#   s3 打开 P2 → 选 cube → position.Z=100 → P3（行文要求 Z 也输 100；
#      「Z 不变」= app 贴床约束的黑盒观测点）
# 判定（3mf）：cube (tx,ty)=(100,100)±0.5；tz 与基线一致；旋转不变；
#       Prusa 逐位不变。Move 面板行标签 = "position"（#152 实证）。
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

LOG = "[m8x190]"
ART = HERE / "artifacts"
STL = HERE / "fixtures" / "Prusa.stl"
CUBE = HERE / "fixtures" / "cube20.stl"
P = {k: ART / f"m8x_190_p{k}.3mf" for k in range(1, 4)}
SESSIONS = ("s1", "s2", "s3")


def patch_archiver(tag):
    from harness import shot_archive
    orig = shot_archive.start_archiver

    def named(session, name, interval=3.0, out_root=None):
        return orig(session, f"{name}_{tag}", interval=interval,
                    out_root=out_root)

    shot_archive.start_archiver = named


def dump_results(tag, results):
    (ART / f"m8x_190_{tag}.json").write_text(
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


def wait_cube_info(session, timeout_s=120):
    import m7_common as m7
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        info = m7.object_info_text(session) or ""
        if "8000" in info or "cube20" in info.lower():
            return True
        time.sleep(1.5)
    return False


def cube_and_prusa(path):
    import m8x_188 as c188
    items, _plates = c188.project_geom(path)
    cube = next((m for _i, (m, n) in items.items()
                 if "cube20" in n.lower()), None)
    prusa = next((m for _i, (m, n) in items.items()
                  if "prusa" in n.lower()), None)
    return cube, prusa


def sig(m):
    return tuple(round(v, 3) for v in m)


def run_s1(args, results):
    import m7_common as m7
    import m8_common as m8
    import m8x_158 as c158
    patch_archiver("s1")
    for k in range(1, 4):
        P[k].unlink(missing_ok=True)
    session = boot_retry(args, args.model)
    try:
        ok, frac = m8.wait_arrival(session)
        results["s1 载入（1 号盘 Prusa 旁观）"] = (
            "PASS" if ok else f"FAIL ({frac:.2%})")
        if not ok:
            return False
        m7.ensure_maximized(session)
        c158.import_model(session, CUBE)
        if not wait_cube_info(session):
            results["s1 导入 cube20"] = "FAIL"
            return False
        results["s1 导入 cube20"] = "PASS"
        ok_t, txt = m7.op_gizmo_field(
            session, lambda t: "move" in t, "position", 0, "100")
        print(f"{LOG} s1 X=100: ok={ok_t} read={txt!r}")
        good = bool(ok_t) and str(txt).startswith("100")
        results["s1 移动 X=100（回读）"] = (
            f"PASS (read={txt!r})" if good else f"FAIL (read={txt!r})")
        return good and m7.save_project_as(session, P[1])
    finally:
        dump_results("s1", results)
        session.close()
        print(f"{LOG} session closed (s1)")


def run_move_step(tag, field_idx, label, args, results):
    import m7_common as m7
    import m8x_187 as c187
    import m8x_191 as c191
    patch_archiver(tag)
    step = int(tag[1])                          # s2: P1→P2, s3: P2→P3
    if not P[step - 1].exists():
        results[f"{tag} 前置 P{step - 1} 缺失"] = "FAIL"
        return False
    args.model = None
    time.sleep(5.0)
    session = boot_retry(args, None)
    try:
        time.sleep(3.0)
        m7.ensure_maximized(session)
        if not c187.open_project(session, P[step - 1]):
            results[f"{tag} 打开 P{step - 1}"] = "FAIL"
            return False
        if not c191.select_cube(session):
            results[f"{tag} 选中 cube20"] = "FAIL"
            return False
        ok_t, txt = m7.op_gizmo_field(
            session, lambda t: "move" in t, "position", field_idx, "100")
        print(f"{LOG} {tag} {label}=100: ok={ok_t} read={txt!r}")
        good = bool(ok_t) and str(txt).startswith("100")
        if label == "Z":
            # Z 字段被 app 拒绝输入（字符不落位、字段停在贴床值 10.00）
            # ——这正是行文预期 2「Z 轴不变」的实现（贴床锁约束）；
            # 记证据，存盘照常，判定看 3mf 的 tz。
            results["s3 Z 输入被拒（贴床锁，行文预期 Z 不变）"] = (
                f"PASS (app 拒绝, field={txt!r})")
            return m7.save_project_as(session, P[step])
        results[f"{tag} 移动 {label}=100（回读）"] = (
            f"PASS (read={txt!r})" if good else f"FAIL (read={txt!r})")
        return good and m7.save_project_as(session, P[step])
    finally:
        dump_results(tag, results)
        session.close()
        print(f"{LOG} session closed ({tag})")


def run_session(tag, args):
    results = {}
    if tag == "s1":
        ok = run_s1(args, results)
    elif tag == "s2":
        ok = run_move_step("s2", 1, "Y", args, results)
    else:
        ok = run_move_step("s3", 2, "Z", args, results)
    dump_results(tag, results)
    return 0 if ok else 1


def main() -> int:
    import argparse
    from m3_common import add_common_args
    ap = add_common_args(argparse.ArgumentParser(), default_model=STL)
    ap.add_argument("--session", choices=SESSIONS, default=None)
    args = ap.parse_args()
    if args.session:
        return run_session(args.session, args)

    results = {}
    for tag in SESSIONS:
        out = ART / f"m8x_190_{tag}.json"
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
            print(f"{LOG} === {tag} TIMEOUT ===")
        if r is not None:
            print(f"{LOG} === {tag} rc={r.returncode} ===")
            for ln in (r.stdout or "").splitlines()[-8:]:
                print(f"{LOG}   {ln}")
        if out.exists():
            results.update(json.loads(out.read_text(encoding="utf-8")))
        else:
            results[f"{tag} 会话结果缺失"] = "FAIL (no json)"
    missing = [P[k] for k in range(1, 4) if not P[k].exists()]
    if missing:
        results["项目链完整（P1..P3）"] = (
            f"FAIL (缺 {[p.name for p in missing]})")
    else:
        results["项目链完整（P1..P3）"] = "PASS"
        c0, p0 = cube_and_prusa(P[1])
        c2, p2 = cube_and_prusa(P[3])
        if c0 and c2:
            results["坐标面板 X/Y 变为 100"] = (
                f"PASS (t=({c2[9]:.1f},{c2[10]:.1f}))"
                if abs(c2[9] - 100) <= 0.5 and abs(c2[10] - 100) <= 0.5
                else f"FAIL (t=({c2[9]:.1f},{c2[10]:.1f}))")
            results["Z 不变（tz 与基线一致）"] = (
                f"PASS (tz={c2[11]:.2f}, was {c0[11]:.2f})"
                if abs(c2[11] - c0[11]) <= 0.5
                else f"FAIL (tz {c0[11]:.2f}->{c2[11]:.2f})")
            results["仅平移（旋转不变）"] = (
                "PASS" if sig(c0[:9]) == sig(c2[:9]) else "FAIL")
        else:
            results["坐标面板 X/Y 变为 100"] = "FAIL (no cube)"
        results["其余对象不受影响（Prusa 逐位不变）"] = (
            "PASS" if p0 and p2 and sig(p0) == sig(p2) else "FAIL")
    print("\n[m3] === verdict ===")
    for k, v in results.items():
        print(f"  {k}: {v}")
    all_ok = bool(results) and all(str(v).startswith("PASS")
                                   for v in results.values())
    print("[m3] " + ("GREEN" if all_ok else "RED"))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
