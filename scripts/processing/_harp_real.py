import cv2
import numpy as np
from PIL import Image
import sys
sys.path.insert(0, r"D:\TOOL\20260831-14-46-47-666\lingxi-pet")
from _lowpat_test import chroma_key_remove, remove_isolated_disconnected, zero_low_sat_semitransparent

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"
cap = cv2.VideoCapture(video)
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

alpha = chroma_key_remove(frame)
alpha, _ = remove_isolated_disconnected(alpha)
alpha, _ = zero_low_sat_semitransparent(alpha, frame)

# 竖琴真实位置：找原图中竖琴（青色）像素分布
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
H, S, V = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
# 竖琴青色：H 100-140, S>40, V>80
harp_mask = (H >= 100) & (H <= 145) & (S > 40) & (V > 80)
ys, xs = np.where(harp_mask)
print(f"竖琴青色像素: {len(xs)} px, bbox x:{xs.min()}-{xs.max()} y:{ys.min()}-{ys.max()}" if len(xs) else "无")
if len(xs):
    # 这些像素在处理后的 alpha
    harp_alpha = alpha[ys, xs]
    print(f"处理后竖琴像素 alpha: >128={int((harp_alpha>128).sum())}/{len(xs)} ({((harp_alpha>128).sum()/len(xs))*100:.0f}%), mean={harp_alpha.mean():.0f}")
    print(f"  >200={int((harp_alpha>200).sum())}, 16-200={int(((harp_alpha>16)&(harp_alpha<200)).sum())}, <=16={int((harp_alpha<=16).sum())}")

# 竖琴区域可视化对比（原图 vs 处理棋盘格）
h, w = rgb.shape[:2]
checker = np.zeros((h, w, 3), np.uint8)
cell = 16
for yy in range(0, h, cell):
    for xx in range(0, w, cell):
        if (yy//cell + xx//cell) % 2 == 0:
            checker[yy:yy+cell, xx:xx+cell] = (90, 90, 90)
        else:
            checker[yy:yy+cell, xx:xx+cell] = (140, 140, 140)
a = (alpha[:, :, None].astype(float) / 255.0)
comp = (rgb * a + checker * (1 - a)).astype(np.uint8)
if len(xs):
    pad = 60
    x0 = max(0, xs.min()-pad); x1 = min(w, xs.max()+pad)
    y0 = max(0, ys.min()-pad); y1 = min(h, ys.max()+pad)
    Image.fromarray(rgb[y0:y1, x0:x1]).save("lingxi-pet/_qa3/mengli_harp_orig.png")
    Image.fromarray(comp[y0:y1, x0:x1]).save("lingxi-pet/_qa3/mengli_harp_proc_checker.png")
    print(f"saved crops ({x1-x0},{y1-y0}) at ({x0},{y0})")
