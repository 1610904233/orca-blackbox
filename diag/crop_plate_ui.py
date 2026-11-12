import cv2
import numpy as np
import glob
import os

# 找最新的 m8x_185 或 probe 帧（有 Orca 主窗口、已加载模型）
cands = []
for pat in ('m8x_185', 'm8x_204', 'm8x_201_s2', 'probe_241_plate2'):
    d = os.path.join(r'C:\coil\orca-blackbox\artifacts\shots', pat)
    if os.path.isdir(d):
        for f in glob.glob(os.path.join(d, 'L*_main.png')):
            cands.append((os.path.getmtime(f), f))
cands.sort()
if not cands:
    print('no frames')
    raise SystemExit
p = cands[-1][1]
img = cv2.imread(p)
print('using', p, img.shape)
H, W = img.shape[:2]

# 底部条
bot = img[max(0, H - 90):H, 0:W]
bot_big = cv2.resize(bot, None, fx=1.6, fy=1.6, interpolation=cv2.INTER_NEAREST)
for gx in range(0, W, 40):
    X = int(gx * 1.6)
    cv2.line(bot_big, (X, 0), (X, 12), (0, 255, 255), 1)
    if gx % 200 == 0:
        cv2.putText(bot_big, str(gx), (X + 2, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
# 右侧列
right = img[240:720, 1440:W]
right_big = cv2.resize(right, None, fx=2.2, fy=2.2, interpolation=cv2.INTER_NEAREST)
for gy in range(0, right.shape[0], 40):
    Y = int(gy * 2.2)
    cv2.line(right_big, (0, Y), (14, Y), (0, 255, 255), 1)
    cv2.putText(right_big, str(240 + gy), (16, Y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
for gx in range(0, right.shape[1], 40):
    X = int(gx * 2.2)
    cv2.line(right_big, (X, 0), (X, 12), (0, 255, 255), 1)
w = max(bot_big.shape[1], right_big.shape[1])
def pad(a, w):
    if a.shape[1] == w:
        return a
    return cv2.copyMakeBorder(a, 0, 0, 0, w - a.shape[1], cv2.BORDER_CONSTANT, value=(40, 40, 40))
out = np.vstack([pad(right_big, w), pad(bot_big, w)])
cv2.imwrite(r'C:\coil\orca-blackbox\artifacts\m8x_plate_ui.png', out)
print('wrote plate_ui', out.shape)
