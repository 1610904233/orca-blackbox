import cv2, glob, os
d = r'C:\coil\orca-blackbox\artifacts\shots'
pats = ['**/L*ROTATE-ACTIVE*_main.png', '**/L*rotate*_main.png',
        '**/L*rotate*grid*_main.png', '**/L*Rotate*_main.png']
found = []
for pat in pats:
    found += glob.glob(os.path.join(d, pat), recursive=True)
found = sorted(set(found), key=os.path.getmtime)
print('found', len(found))
for f in found[-5:]:
    print('  ', f, os.path.getsize(f))
if not found:
    # 退而求其次：把 m8x_156_s1 的全部 L 帧列出来
    for f in sorted(glob.glob(os.path.join(d, 'm8x_156_s1', 'L*.png')))[-8:]:
        print('  s1:', f)
    raise SystemExit
img = cv2.imread(found[-1])
print('using', found[-1], img.shape)
crop = img[470:650, 1110:1330]
big = cv2.resize(crop, None, fx=4.5, fy=4.5, interpolation=cv2.INTER_NEAREST)
for gx in range(0, crop.shape[1], 20):
    X = int(gx * 4.5)
    cv2.line(big, (X, 0), (X, 14), (0, 255, 255), 2)
    cv2.putText(big, str(1110 + gx), (X + 2, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
for gy in range(0, crop.shape[0], 20):
    Y = int(gy * 4.5)
    cv2.line(big, (0, Y), (14, Y), (0, 255, 255), 2)
    cv2.putText(big, str(470 + gy), (16, Y + 6), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 255, 255), 1)
cv2.imwrite(r'C:\coil\orca-blackbox\artifacts\m8x156_gizmo_zoom.png', big)
print('wrote zoom', big.shape)
