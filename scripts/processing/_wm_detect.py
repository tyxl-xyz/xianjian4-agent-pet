import cv2
import numpy as np
from PIL import Image

cap = cv2.VideoCapture('C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4')
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
green = cv2.inRange(hsv, (30, 30, 60), (95, 255, 255))
gray = rgb.mean(axis=2)
kernel = np.ones((9, 9), np.uint8)
green_d = cv2.dilate(green, kernel)
bg_gray = cv2.medianBlur(gray.astype(np.uint8), 15)
diff = np.abs(gray - bg_gray)
text = (diff > 28) & (green_d > 0)
text = text.astype(np.uint8) * 255
text = cv2.morphologyEx(text, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
ys, xs = np.where(text > 0)
print('背景区文字候选像素:', len(xs))
if len(xs):
    print('位置 x:', xs.min(), '-', xs.max(), 'y:', ys.min(), '-', ys.max())
    n, labels, stats, cent = cv2.connectedComponentsWithStats(text, connectivity=8)
    print('文字连通域数:', n - 1)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a > 50:
            print(f'  id{i} area={a} bbox=({stats[i,cv2.CC_STAT_LEFT]},{stats[i,cv2.CC_STAT_TOP]})-'
                  f'({stats[i,cv2.CC_STAT_LEFT]+stats[i,cv2.CC_STAT_WIDTH]},{stats[i,cv2.CC_STAT_TOP]+stats[i,cv2.CC_STAT_HEIGHT]})')
vis = rgb.copy()
vis[text > 0] = [255, 0, 0]
Image.fromarray(vis).save('lingxi-pet/_qa3/mengli_wm_detect.png')
print('saved detect overlay')
