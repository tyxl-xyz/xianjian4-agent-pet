import cv2
import numpy as np
from PIL import Image

# 原始视频帧（工作 f60）
cap = cv2.VideoCapture("C:/Users/13544/Desktop/新建文件夹/工作.mp4")
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()
orig = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

# 处理后 GIF f60
gif = Image.open("lingxi-pet/_build/working/working.gif")
gif.seek(60)
proc = gif.convert("RGBA")

print("=== 对比几个采样点的颜色 ===")
# 取角色服装中央（约 x=360, y=500 附近原始坐标），注意处理后缩放居中
# 原始 720x1280，处理后 405 宽居中。原始 x:360 -> 缩放后 x=157+360*0.5625=360 仍在中间
sample_pts = [(360, 400), (360, 600), (360, 900), (360, 1000)]
for (x, y) in sample_pts:
    op = orig[y, x]
    # GIF是方形720，角色缩放到405宽居中。原x=360 在角色内
    px = proc.getpixel((360, y))  # 近似
    print(f"  ({x},{y}): orig RGB={tuple(int(v) for v in op)}  proc RGBA={px}")

print("\n=== 统计GIF整体颜色分布（不透明像素） ===")
arr = np.array(proc)
mask = arr[:, :, 3] > 128
if mask.sum() > 0:
    px = arr[mask][:, :3]
    mean = px.mean(axis=0)
    print(f"  proc 不透明像素均值 RGB={mean.round(1)}")
    # 常见颜色
    from collections import Counter
    # 量化到 32 级
    q = (px // 32).astype(int)
    keys = [tuple(rgb) for rgb in q]
    cnt = Counter(keys)
    print("  前8高频色:")
    for k, c in cnt.most_common(8):
        v = np.array(k) * 32 + 16
        print(f"    {tuple(v.astype(int))}: {c}")
