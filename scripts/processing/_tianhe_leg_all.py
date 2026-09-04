import cv2
import numpy as np
from PIL import Image

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
frames = []
for i in range(total):
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ret, frame = cap.read()
    if ret:
        frames.append(frame)
cap.release()

# 源视频全帧：左腿区域非背景像素量
print("=== 源视频左腿区域逐帧非背景px（找突降帧） ===")
x0, y0, x1, y1 = 120, 780, 360, 1120
vals_src = []
for i in range(total):
    rgb = cv2.cvtColor(frames[i][y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    green = ((H >= 76) & (H <= 93) & (S > 25) & (V > 60))
    vals_src.append(int((~green).sum()))
for i in range(total):
    print(f"  f{i}: {vals_src[i]}", end="  ")
    if (i + 1) % 6 == 0:
        print()
print("\n")

# 处理后 GIF 全帧：左腿区域 alpha>128 逐帧
gif = Image.open("lingxi-pet/_build3/tianhe/tianhe.gif")
scale = 720 / 1280
x0g = int(157 + x0 * scale); x1g = int(157 + x1 * scale)
y0g = int(y0 * scale); y1g = int(y1 * scale)
print("=== 处理后GIF左腿区域逐帧 alpha>128（找突降帧） ===")
vals_gif = []
for i in range(total):
    gif.seek(i)
    arr = np.array(gif.convert("RGBA"))
    reg = arr[y0g:y1g, x0g:x1g]
    vals_gif.append(int((reg[:, :, 3] > 128).sum()))
for i in range(total):
    print(f"  f{i}: {vals_gif[i]}", end="  ")
    if (i + 1) % 6 == 0:
        print()
print("\n")
