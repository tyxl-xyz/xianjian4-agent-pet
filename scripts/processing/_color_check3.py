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

SCALE = 720 / 1280
X0 = int(round((720 - 720 * SCALE) / 2))

# 工作 f60 原始
orig = load_orig_frame("C:/Users/13544/Desktop/新建文件夹/工作.mp4", 60)
proc = load_proc_frame("lingxi-pet/_build/working/working.gif", 60)

# 角色mask（原始）：非绿且不在水印角落
hsv = cv2.cvtColor(orig, cv2.COLOR_RGB2HSV)
ogreen = cv2.inRange(hsv, (30, 30, 60), (95, 255, 255))
omask = (ogreen == 0)
orig_chars = orig[omask]
print("orig 角色像素数:", omask.sum(), "均值 RGB:", orig_chars.mean(axis=0).round(1))

# proc 角色mask
arr = np.array(proc)
pmask = arr[:, :, 3] > 128
print("proc 角色像素数:", pmask.sum(), "均值 RGB:", arr[pmask][:, :3].mean(axis=0).round(1))

# 角色区域颜色直方图对比（按区段）
print("\n=== 各亮度段颜色均值对比 ===")
for lo, hi in [(0, 60), (60, 120), (120, 180), (180, 240)]:
    osel = omask & (orig.mean(axis=2) >= lo) & (orig.mean(axis=2) < hi)
    # proc 需要映射回角色，用 mask 直接
    psel = pmask & (arr[:, :, :3].mean(axis=2) >= lo) & (arr[:, :, :3].mean(axis=2) < hi)
    if osel.sum() > 0:
        om = orig[osel].mean(axis=0).round(1)
    else:
        om = "N/A"
    if psel.sum() > 0:
        pm = arr[psel][:, :3].mean(axis=0).round(1)
    else:
        pm = "N/A"
    print(f"  {lo}-{hi}: orig={om} proc={pm}")

# 保存放大对比图便于视觉确认
cv2.imwrite("lingxi-pet/_qa/orig_work60.png", cv2.cvtColor(orig, cv2.COLOR_RGB2BGR))
print("\nsaved orig_work60.png")
