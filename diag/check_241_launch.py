"""确认 2.4.1 app 已起：找主窗口 + 截一张图（PNG）给用户看。"""
import subprocess, sys, time
sys.path.insert(0, 'C:/coil/orca-blackbox')
from harness import winutil

raw = subprocess.run(['tasklist', '/FI', 'IMAGENAME eq snapmaker-orca.exe', '/FO', 'CSV', '/NH'],
                     capture_output=True, text=True).stdout
pids = []
for ln in raw.splitlines():
    parts = [p.strip('"') for p in ln.split('","')]
    if len(parts) > 1 and parts[0].lower().startswith('snapmaker-orca'):
        try:
            pids.append(int(parts[1]))
        except ValueError:
            pass
print('pids:', pids)
if not pids:
    print('FAIL: no snapmaker-orca process')
    sys.exit(1)

hwnd = 0
for pid in pids:
    try:
        h = winutil.find_main_window(pid, timeout_s=30.0)
    except Exception as exc:                       # noqa: BLE001
        print(f'pid {pid}: no main window ({exc})')
        continue
    r = winutil.window_rect(h)
    print(f'pid {pid} hwnd=0x{h:X} class={winutil.window_class(h)!r} '
          f'title={winutil.window_title(h)!r} rect={r}')
    if not hwnd:
        hwnd = h
if not hwnd:
    print('FAIL: no main window found')
    sys.exit(1)

time.sleep(1.0)
w, hh, bgra = winutil.capture_window(hwnd)
import numpy as np
img = np.frombuffer(bgra, dtype=np.uint8).reshape(hh, w, 4)[:, :, :3]
print(f'capture {w}x{hh} mean_brightness={img.mean():.1f}')
import cv2
cv2.imwrite('C:/coil/launch_241.png', img)
print('saved C:/coil/launch_241.png')
