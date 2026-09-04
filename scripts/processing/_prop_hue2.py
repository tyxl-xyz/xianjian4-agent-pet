import cv2
import numpy as np
from PIL import Image

def load_orig(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def hue_hist(rgb, y0, y1, x0, x1, label):
    reg = rgb[y0:y1, x0:x1]
    hsv = cv2.cvtColor(reg, cv2.COLOR_RGB2HSV)
    H = hsv[:, :, 0].reshape(-1)
    S = hsv[:, :, 1].reshape(-1)
    V = hsv[:, :, 2].reshape(-1)
    print(f"{label}: 区域({x0},{y0})-({x1},{y1})")
    # 背景绿占比
    green = ((H >= 30) & (H <= 95) & (S >= 20) & (V >= 60))
    print(f"  背景绿像素占比: {green.mean()*100:.0f}%")
    # 非背景像素的色相分布（道具/角色）
    nong = ~green
    nh = H[nong]
    ns = S[nong]
    nv = V[nong]
    if len(nh) == 0:
        print("  无非背景像素")
        return
    hist = np.bincount(nh, minlength=180)
    top = np.argsort(hist)[::-1][:10]
    print(f"  非背景色相Top10: {[(int(t), int(hist[t])) for t in top if hist[t] > 50]}")

# 梦璃竖琴（中部偏下，避开角色脸部）
rgb = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60)
h, w = rgb.shape[:2]
hue_hist(rgb, int(h*0.55), int(h*0.85), int(w*0.35), int(w*0.65), "梦璃-竖琴区域")
hue_hist(rgb, 0, int(h*0.15), 0, int(w*0.15), "梦璃-背景TL")

# 紫英剑（中部）
rgb = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 60)
hue_hist(rgb, int(h*0.45), int(h*0.85), int(w*0.35), int(w*0.65), "紫英-剑区域")
hue_hist(rgb, 0, int(h*0.15), 0, int(w*0.15), "紫英-背景TL")

# 天河弓（中部）
rgb = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4", 60)
hue_hist(rgb, int(h*0.45), int(h*0.85), int(w*0.30), int(w*0.70), "天河-弓区域")
hue_hist(rgb, 0, int(h*0.15), 0, int(w*0.15), "天河-背景TL")
