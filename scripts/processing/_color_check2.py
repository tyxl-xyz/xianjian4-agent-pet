import cv2
import numpy as np
from PIL import Image

def load_orig_frame(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def load_proc_frame(gif_path, fi):
    gif = Image.open(gif_path)
    gif.seek(fi)
    return gif.convert("RGBA")

# 竖屏 720x1280 -> 等比缩放居中到 720x720: scale=720/1280=0.5625, width=405, x0=157
SCALE = 720 / 1280
X0 = int(round((720 - 720 * SCALE) / 2))

def map_pt(ox, oy):
    return int(X0 + ox * SCALE), int(oy * SCALE)

orig = load_orig_frame("C:/Users/13544/Desktop/新建文件夹/工作.mp4", 60)
proc = load_proc_frame("lingxi-pet/_build/working/working.gif", 60)

print("=== 角色区域采样（工作f60） ===")
for (ox, oy) in [(360, 500), (360, 700), (360, 950), (330, 420), (200, 900), (500, 600)]:
    px_, py_ = map_pt(ox, oy)
    op = orig[oy, ox]
    pp = np.array(proc.getpixel((px_, py_)))
    print(f"  原({ox},{oy})->后({px_},{py_}): orig={tuple(int(v) for v in op)} proc={tuple(int(v) for v in pp)}")

print("\n=== 不透明像素均值对比 ===")
arr = np.array(proc)
mask = arr[:, :, 3] > 128
pmean = arr[mask][:, :3].mean(axis=0)
hsv = cv2.cvtColor(orig, cv2.COLOR_RGB2HSV)
ogreen = cv2.inRange(hsv, (30, 30, 60), (95, 255, 255))
omask = ~ogreen
omean = orig[omask].mean(axis=0)
print(f"  orig 非绿像素均值 RGB={omean.round(1)}")
print(f"  proc 不透明像素均值 RGB={pmean.round(1)}")
