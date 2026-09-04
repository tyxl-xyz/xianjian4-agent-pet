import cv2
import numpy as np
from PIL import Image

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
print("总帧数:", total)
frames = []
for i in range(total):
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ret, frame = cap.read()
    if ret:
        frames.append(frame)
cap.release()

def analyze_leg(frame, x0, y0, x1, y1):
    rgb = cv2.cvtColor(frame[y0:y1, x0:x1], cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
    green = ((H >= 76) & (H <= 93) & (S > 25) & (V > 60))
    non_green = (~green).astype(np.uint8)
    return int(non_green.sum()), float(green.mean())

print("\n=== 源视频左腿区域非背景像素量 ===")
x0, y0, x1, y1 = 120, 780, 360, 1120
for i in [0, 20, 40, 60, 80, 100, 120]:
    if i >= len(frames):
        break
    nong, g = analyze_leg(frames[i], x0, y0, x1, y1)
    print(f"  f{i}: 非背景px={nong}")

print("\n=== 处理后GIF左腿区域alpha ===")
gif = Image.open("lingxi-pet/_build3/tianhe/tianhe.gif")
scale = 720 / 1280
x0g = int(157 + x0 * scale); x1g = int(157 + x1 * scale)
y0g = int(y0 * scale); y1g = int(y1 * scale)
for i in [0, 20, 40, 60, 80, 100, 120]:
    gif.seek(i)
    arr = np.array(gif.convert("RGBA"))
    reg = arr[y0g:y1g, x0g:x1g]
    alpha = reg[:, :, 3]
    print(f"  f{i}: alpha>128={(alpha>128).sum()}, alpha16-200={((alpha>16)&(alpha<200)).sum()}")
