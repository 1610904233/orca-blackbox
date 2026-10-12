#!/usr/bin/env python3
# analyze_gizmo_ocr.py — 离线复算 gizmo_row_boxes_img 的内部量（不需要 app/GUI）。
#
# 用法: python analyze_gizmo_ocr.py <screen_png> [offx offy w h]
# 屏幕截图 → 裁出主窗口 client 区（模拟 capture_bgr）→ 跑 mdu.ocr_words_img
# → 打印全部词 + label_ys/rows/cols/最终 boxes，钉死"多出来一空行"的来源。
import sys
from pathlib import Path

if sys.stdout is not None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_HERE)); sys.path.insert(0, str(_HERE / "tests"))
for _g in sorted((_HERE / "tests").iterdir()):
    if _g.is_dir() and not _g.name.startswith("__"):
        sys.path.insert(0, str(_g))

import cv2  # noqa: E402
from harness import mix_dialog_util as mdu  # noqa: E402
import m7_common as m7  # noqa: E402

ROW_LABEL = "position"


def main() -> int:
    src = sys.argv[1]
    off = (int(sys.argv[2]), int(sys.argv[3])) if len(sys.argv) > 4 else (8, 31)
    size = (int(sys.argv[4]), int(sys.argv[5])) if len(sys.argv) > 4 else (1200, 800)
    img = cv2.imread(src)
    print(f"screen png {img.shape}")
    x0, y0 = off
    crop = img[y0:y0 + size[1], x0:x0 + size[0]]
    print(f"client crop {crop.shape} from offset {off}")
    words = mdu.ocr_words_img(crop, scale=3)
    print(f"words: {len(words)}")
    for t, x, y, w, h in sorted(words, key=lambda z: (z[2], z[1])):
        mark = "  <-- label" if t.lower().startswith(ROW_LABEL) else ""
        print(f"  {t!r:20} x={x:5d} y={y:5d} w={w:3d} h={h:3d}{mark}")
    boxes = m7.gizmo_row_boxes_img(crop, ROW_LABEL, scale=3)
    print(f"gizmo_row_boxes({ROW_LABEL!r}) ({len(boxes)}): {boxes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
