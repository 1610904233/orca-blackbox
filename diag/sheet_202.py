import cv2, numpy as np, glob, os
p = r'C:\coil\orca-blackbox\artifacts\shots\m8x_202\m8x_202_run.mp4'
cap = cv2.VideoCapture(p)
fps = cap.get(cv2.CAP_PROP_FPS); n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
secs = n / max(fps, 1)
print('fps', fps, 'frames', n, 'secs', round(secs, 1))
# 每 1.5s 取一帧，拼成网格（6 列）
cells = []
t = 0.0
while t < secs:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
    ok, fr = cap.read()
    if ok:
        small = cv2.resize(fr, (320, 173), interpolation=cv2.INTER_AREA)
        cv2.putText(small, f'{t:.0f}s', (4, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 255), 1)
        cells.append(small)
    t += 1.5
cap.release()
cols = 6
while len(cells) % cols:
    cells.append(np.zeros_like(cells[0]))
rows = [np.hstack(cells[i:i+cols]) for i in range(0, len(cells), cols)]
out = np.vstack(rows)
cv2.imwrite(r'C:\coil\orca-blackbox\artifacts\m8x202_sheet.png', out)
print('grid', out.shape, 'cells', len(cells))
