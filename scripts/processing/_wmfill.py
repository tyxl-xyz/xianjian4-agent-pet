import cv2
import numpy as np

cap = cv2.VideoCapture("C:/Users/13544/Desktop/新建文件夹/待机.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 40)
ret, frame = cap.read()
cap.release()
h, w = frame.shape[:2]
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
green = cv2.inRange(hsv, (30, 30, 60), (95, 255, 255))

# 只处理四角背景区域（角色集中在中央）
corner_regions = {
    "TL": (0, 0, int(h*0.25), int(w*0.25)),
    "TR": (0, int(w*0.75), int(h*0.25), w),
    "BL": (int(h*0.75), 0, h, int(w*0.25)),
    "BR": (int(h*0.75), int(w*0.75), h, w),
}
out = frame.copy()
for rn, (y0, x0, y1, x1) in corner_regions.items():
    reg = rgb[y0:y1, x0:x1]
    reg_hsv = cv2.cvtColor(reg, cv2.COLOR_RGB2HSV)
    reg_green = cv2.inRange(reg_hsv, (30, 30, 60), (95, 255, 255))
    # 局部背景绿 = 该区域绿色像素中值
    green_px = reg[reg_green > 0]
    if len(green_px) == 0:
        continue
    bg = np.median(green_px.reshape(-1, 3), axis=0)  # RGB中值
    gray = reg.mean(axis=2)
    # 文字 = 非绿 + 与背景中值亮度差较大
    bg_gray = np.median(gray[reg_green > 0])
    diff = np.abs(gray - bg_gray)
    text_mask = (diff > 22) & (reg_green == 0)
    text_mask = cv2.morphologyEx(text_mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    text_mask = cv2.dilate(text_mask, np.ones((3, 3), np.uint8), iterations=1)
    ys, xs = np.where(text_mask > 0)
    if len(xs) == 0:
        continue
    print(f"{rn}: text_px={len(xs)}, bg={bg.astype(int)}")
    # 填充背景绿（保持原背景的明度变化？直接用局部绿色像素均值更自然）
    # 用该区域整体绿色像素均值作为填充色
    fill = green_px.reshape(-1, 3).mean(axis=0)
    for yy, xx in zip(ys, xs):
        out[y0+yy, x0+xx] = fill

cv2.imwrite("lingxi-pet/_build/test/wm_f40_fill.png", out)
print("fill done")
