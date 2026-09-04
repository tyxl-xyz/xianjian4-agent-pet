import cv2
import numpy as np
from PIL import Image

def load_orig(video, fi=60):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def chroma_key_remove(rgb, hue_range=(30, 95), sat_min=30, val_min=60, dilate_iter=1):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (hue_range[0], sat_min, val_min), (hue_range[1], 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=dilate_iter)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    rgba = cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA)
    rgba[:, :, 3] = alpha
    return rgba


def remove_watermark_strong(alpha, corner_ratio=0.30, min_area=60, max_area=12000):
    """增强版：四角范围加大到30%，面积60起；同时清理半透明孤立块"""
    h, w = alpha.shape
    fg = (alpha > 128).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    max_area_main = areas[np.argmax(areas)]
    cx = w * corner_ratio
    cy = h * corner_ratio
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area or a > max_area_main * 0.5:
            continue
        x_c, y_c = centroids[i]
        in_corner = (x_c < cx or x_c > w - cx) and (y_c < cy or y_c > h - cy)
        if not in_corner:
            continue
        remove[labels == i] = 1
        removed_cnt += int(a)
    alpha[remove > 0] = 0
    return alpha, removed_cnt


def center_square(rgba):
    src_h, src_w = rgba.shape[:2]
    scale = 720 / src_h
    new_w = max(1, int(round(src_w * scale)))
    resized = cv2.resize(rgba, (new_w, 720), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((720, 720, 4), dtype=np.uint8)
    x0 = (720 - new_w) // 2
    canvas[:, x0:x0 + new_w] = resized
    return canvas


# 对比 dilate=1 vs dilate=2 对道具保留的影响
for label, video in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
]:
    rgb = load_orig(video, 60)
    for di in [1, 2]:
        rgba = chroma_key_remove(rgb, dilate_iter=di)
        alpha = rgba[:, :, 3]
        alpha, _ = remove_watermark_strong(alpha)
        rgba[:, :, 3] = alpha
        canvas = center_square(rgba)
        Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa3/{label}_d{di}.png")
        print(f"{label} dilate={di}: done")
