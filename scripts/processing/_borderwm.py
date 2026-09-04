import cv2
import numpy as np
from PIL import Image

def load_orig(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def detect_wm_border(rgb, border=0.22):
    """仅在外围边带内，检测低饱和(<55)、非纯暗(V>110)的像素=白色水印文字"""
    h, w = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(int), hsv[:, :, 2].astype(int)
    # 边带 mask
    bh, bw = int(h * border), int(w * border)
    border_mask = np.zeros((h, w), bool)
    border_mask[:bh, :] = True
    border_mask[-bh:, :] = True
    border_mask[:, :bw] = True
    border_mask[:, -bw:] = True
    # 水印：低饱和 + 亮度中高 + 在边带
    wm = border_mask & (S < 55) & (V > 110)
    # 排除绿色背景本体（S低但接近黑/深色的绿影不算）
    # 打开形态学去噪
    wm = wm.astype(np.uint8) * 255
    wm = cv2.morphologyEx(wm, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    # 只保留面积适中的文字块（50-5000）
    n, labels, stats, _ = cv2.connectedComponentsWithStats(wm, connectivity=8)
    keep = np.zeros_like(wm)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if 50 <= a <= 6000:
            keep[labels == i] = 255
    return keep, n - 1

for label, video, fi in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 60),
]:
    rgb = load_orig(video, fi)
    wm, nb = detect_wm_border(rgb)
    vis = rgb.copy()
    vis[wm > 0] = [255, 0, 0]
    Image.fromarray(vis).save(f"lingxi-pet/_qa3/{label}_borderwm.png")
    print(f"{label}: 边带水印块数={nb}, 覆盖px={int((wm>0).sum())}")
