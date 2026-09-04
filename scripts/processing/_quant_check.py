import cv2
import numpy as np
from PIL import Image
import sys
sys.path.insert(0, r"C:\Users\13544\AppData\Roaming\WPS 灵犀\serverdir\target_skills\lingxi-pet\scripts")
from chroma_key_to_gif import rgba_to_gif_frames

HUE_RANGE = (30, 95); SAT_MIN = 30; VAL_MIN = 60; OUT_SIZE = 720

def chroma_key_remove(img_bgr):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (HUE_RANGE[0], SAT_MIN, VAL_MIN), (HUE_RANGE[1], 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=2)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    return rgba

# 工作 f60 原帧
cap = cv2.VideoCapture("C:/Users/13544/Desktop/新建文件夹/工作.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()
src_h, src_w = frame.shape[:2]
scale = OUT_SIZE / src_h
new_w = max(1, int(round(src_w * scale)))
rgba = chroma_key_remove(frame)
resized = cv2.resize(rgba, (new_w, OUT_SIZE), interpolation=cv2.INTER_LANCZOS4)
canvas = np.zeros((OUT_SIZE, OUT_SIZE, 4), dtype=np.uint8)
x0 = (OUT_SIZE - new_w) // 2
canvas[:, x0:x0 + new_w] = resized

# 无损 PNG
Image.fromarray(canvas, mode="RGBA").save("lingxi-pet/_qa/work60_lossless.png")

# GIF 量化
img = Image.fromarray(canvas, mode="RGBA")
gif_p = rgba_to_gif_frames(img, 100)
gif_rgba = gif_p.convert("RGBA")

arr_png = np.array(Image.open("lingxi-pet/_qa/work60_lossless.png"))
arr_gif = np.array(gif_rgba)
m_png = arr_png[:, :, 3] > 128
m_gif = arr_gif[:, :, 3] > 128
print("PNG 角色像素:", m_png.sum(), "均值:", arr_png[m_png][:, :3].mean(axis=0).round(1))
print("GIF 角色像素:", m_gif.sum(), "均值:", arr_gif[m_gif][:, :3].mean(axis=0).round(1))
# 中亮段
for lo, hi in [(60, 120)]:
    a = arr_png[:, :, :3].mean(axis=2)
    b = arr_gif[:, :, :3].mean(axis=2)
    s1 = m_png & (a >= lo) & (a < hi)
    s2 = m_gif & (b >= lo) & (b < hi)
    print(f"  {lo}-{hi}: PNG={arr_png[s1][:, :3].mean(axis=0).round(1)} GIF={arr_gif[s2][:, :3].mean(axis=0).round(1)}")
