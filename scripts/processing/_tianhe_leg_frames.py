import cv2
import numpy as np
from PIL import Image

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
frames = {}
for fi in [44, 46, 48, 50, 52, 54, 56]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    if ret:
        frames[fi] = frame
cap.release()

# 处理后GIF同帧
gif = Image.open("lingxi-pet/_build3/tianhe/tianhe.gif")
scale = 720 / 1280
x0g = int(157 + 120 * scale); x1g = int(157 + 360 * scale)
y0g = int(780 * scale); y1g = int(1120 * scale)

for fi in [44, 46, 48, 50, 52, 54]:
    frame = frames.get(fi)
    if frame is None:
        continue
    # 源帧左腿区域裁剪放大
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    Image.fromarray(rgb[740:1160, 100:400]).save(f"lingxi-pet/_qa5/src_f{fi}.png")
    # 处理帧
    gif.seek(fi)
    arr = np.array(gif.convert("RGBA"))
    Image.fromarray(arr[y0g:y1g, x0g:x1g]).save(f"lingxi-pet/_qa5/proc_f{fi}.png")
print("saved")
