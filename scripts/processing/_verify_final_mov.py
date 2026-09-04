import cv2
import numpy as np

mov = r"C:\Users\13544\AppData\Roaming\desktop-pet\accounts\230581940\pets\han-ling-sha\user\tianhe.mov"
cap = cv2.VideoCapture(mov)
print("总帧数:", int(cap.get(cv2.CAP_PROP_FRAME_COUNT)), "尺寸:", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
# stacked mov: 上半RGB 下半matte
frame = None
vals = []
for i in range(121):
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ret, f = cap.read()
    if not ret:
        break
    h, w = f.shape[:2]
    top = f[:h//2]
    matte = f[h//2:, :, 0]
    # 左腿区域（在256x256 frame中：原720x1280 → scale=256/1280=0.2, x0=(256-720*0.2)//2=(256-144)//2=56）
    scale = 256 / 1280
    x0g = int(56 + 120 * scale); x1g = int(56 + 360 * scale)
    y0g = int(780 * scale); y1g = int(1120 * scale)
    reg = matte[y0g:y1g, x0g:x1g]
    vals.append(int((reg > 128).sum()))
    if i in [0, 46, 50, 60]:
        # 保存RGB帧（叠加alpha）
        alpha = matte.astype(float) / 255.0
        rgba = cv2.cvtColor(top, cv2.COLOR_BGR2BGRA)
        rgba[:, :, 3] = matte
        cv2.imwrite(f"lingxi-pet/_qa5/mov_tianhe_f{i}.png", rgba)
cap.release()
print("左腿区域 alpha>128 全帧:")
for i in range(0, len(vals), 6):
    print("  ", " ".join(f"f{j}:{vals[j]}" for j in range(i, min(i+6, len(vals)))))
print("min:", min(vals), "at f", vals.index(min(vals)))
