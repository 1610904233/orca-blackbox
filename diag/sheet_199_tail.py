import cv2, numpy as np
p = r'C:\coil\orca-blackbox\artifacts\shots\m8x_199\m8x_199_run.mp4'
cap = cv2.VideoCapture(p)
fps = cap.get(cv2.CAP_PROP_FPS)
n = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
secs = n / max(fps, 1)
print('secs', round(secs, 1))
t0 = max(0.0, secs - 26)
cells = []
t = t0
while t < secs:
    cap.set(cv2.CAP_PROP_POS_FRAMES, int(t * fps))
    ok, fr = cap.read()
    if ok:
        small = cv2.resize(fr, (480, 260), interpolation=cv2.INTER_AREA)
        cv2.putText(small, f'{t:.1f}s', (5, 18), cv2.FONT_HERSHEY_SIMPLEX,
                    0.55, (0, 255, 255), 1)
        cells.append(small)
    t += 0.8
cap.release()
cols = 4
while len(cells) % cols:
    cells.append(np.zeros_like(cells[0]))
rows = [np.hstack(cells[i:i+cols]) for i in range(0, len(cells), cols)]
out = np.vstack(rows)
cv2.imwrite(r'C:\coil\orca-blackbox\artifacts\m8x199_tail.png', out)
print('grid', out.shape, 'cells', len(cells), 'from', round(t0, 1))
