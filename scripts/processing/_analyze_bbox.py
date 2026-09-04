import cv2
import numpy as np

def analyze(path, label):
    cap = cv2.VideoCapture(path)
    # 读若干帧
    frames = []
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    for i in range(total):
        ret, frame = cap.read()
        if not ret: break
        if i % 12 == 0:
            frames.append(frame)
    cap.release()
    print(f"=== {label} === frames sampled={len(frames)}")
    for idx, frame in enumerate(frames):
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        # 绿幕范围(35-85 hue)，找出非绿像素
        mask_green = cv2.inRange(hsv, (35, 80, 80), (85, 255, 255))
        non_green = ~mask_green
        ys, xs = np.where(non_green)
        if len(xs) == 0:
            print(f"  frame{idx}: no non-green")
            continue
        x0, x1 = xs.min(), xs.max()
        y0, y1 = ys.min(), ys.max()
        bw, bh = x1-x0+1, y1-y0+1
        print(f"  frame{idx}: bbox=({x0},{y0})-({x1},{y1}) size={bw}x{bh} ratio_hw={bh/bw:.2f} "
              f"x%={bw/w*100:.0f} y%={bh/h*100:.0f} "
              f"top%={y0/h*100:.0f} bottom%={(h-1-y1)/h*100:.0f} "
              f"left%={x0/w*100:.0f} right%={(w-1-x1)/w*100:.0f}")

for name in ["待机","工作","开心","难过"]:
    analyze(f"C:/Users/13544/Desktop/新建文件夹/{name}.mp4", name)
