import cv2
import numpy as np
from PIL import Image
import sys
sys.path.insert(0, r"D:\TOOL\20260831-14-46-47-666\lingxi-pet")
from _lowpat_test import chroma_key_remove, remove_isolated_disconnected, zero_low_sat_semitransparent

# 处理梦璃 f60
video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"
cap = cv2.VideoCapture(video)
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()

alpha = chroma_key_remove(frame)
alpha, _ = remove_isolated_disconnected(alpha)
alpha, _ = zero_low_sat_semitransparent(alpha, frame)

# 竖琴区域（原图坐标 300-480 x, 704-1088 y）
# 先看全图 alpha 直方图
print("全图 alpha>128 占比:", (alpha>128).mean().round(3))
print("全图 alpha>200 占比:", (alpha>200).mean().round(3))
print("全图 alpha 16-200 占比:", ((alpha>16)&(alpha<200)).mean().round(3))

# 竖琴中心区域采样 alpha
reg = alpha[700:1100, 300:500]
print("\n竖琴区域 alpha 统计: mean=", reg.mean().round(1), "| >128:", (reg>128).mean().round(3), "| 16-200:", ((reg>16)&(reg<200)).mean().round(3))

# 保存原图竖琴区域 + 处理后竖琴区域对比（透明底+棋盘格）
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
rgba[:, :, 3] = alpha
# 棋盘格背景合成
h, w = rgba.shape[:2]
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
# 竖琴放大区域
y0, y1, x0, x1 = 680, 1100, 280, 520
Image.fromarray(comp[y0:y1, x0:x1]).save("lingxi-pet/_qa3/mengli_harp_checker.png")
print("saved harp checker crop", (x1-x0, y1-y0))
