import cv2
import numpy as np

cap = cv2.VideoCapture("C:/Users/13544/Desktop/新建文件夹/待机.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 40)
ret, frame = cap.read()
cap.release()
h, w = frame.shape[:2]
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

# 右下角水印区域（从观察大概 x 600-720, y 1050-1280 附近），扩一点
reg = rgb[int(h*0.78):h, int(w*0.55):w]
reg_hsv = cv2.cvtColor(reg, cv2.COLOR_RGB2HSV)
reg_green = cv2.inRange(reg_hsv, (30, 30, 60), (95, 255, 255))
gray = reg.mean(axis=2)
bg = np.median(gray[reg_green > 0])
diff = np.abs(gray - bg)
text_mask = (diff > 20) & (reg_green == 0)
text_px = reg[text_mask]
if len(text_px) > 0:
    hsv_px = cv2.cvtColor(text_px.reshape(1, -1, 3), cv2.COLOR_RGB2HSV).reshape(-1, 3)
    print("水印像素 RGB 均值:", text_px.mean(axis=0).round(1))
    print("水印像素 HSV 均值:", hsv_px.mean(axis=0).round(1))
    print("水印像素 H 范围:", hsv_px[:,0].min(), "-", hsv_px[:,0].max())
    print("水印像素 S 范围:", hsv_px[:,1].min(), "-", hsv_px[:,1].max())
    print("水印像素 V 范围:", hsv_px[:,2].min(), "-", hsv_px[:,2].max())
    # 水印像素色相落在哪个范围
    h_vals = hsv_px[:,0]
    for lo, hi, name in [(0,15,"红"),(15,25,"橙黄"),(25,35,"黄"),(35,85,"绿"),(85,100,"青"),(100,130,"蓝"),(130,170,"紫/品红")]:
        cnt = int(((h_vals>=lo)&(h_vals<hi)).sum())
        print(f"  H[{lo}-{hi}] {name}: {cnt} px")
else:
    print("未检测到水印像素")
