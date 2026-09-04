import cv2
import numpy as np
from PIL import Image

HUE_RANGE = (30, 95); SAT_MIN = 30; VAL_MIN = 60; DILATE_ITER = 1

def load_orig(video, fi=60):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def chroma_key_remove(img_bgr, hue_range=HUE_RANGE, sat_min=SAT_MIN, val_min=VAL_MIN, dilate_iter=DILATE_ITER):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (hue_range[0], sat_min, val_min), (hue_range[1], 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=dilate_iter)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha
    return rgba

def remove_watermark_strong(alpha, corner_ratio=0.30, min_area=60, max_area=20000):
    h, w = alpha.shape
    fg = (alpha > 16).astype(np.uint8)
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
    src_h = rgba.shape[0]
    scale = 720 / src_h
    new_w = max(1, int(round(rgba.shape[1] * scale)))
    resized = cv2.resize(rgba, (new_w, 720), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((720, 720, 4), dtype=np.uint8)
    x0 = (720 - new_w) // 2
    canvas[:, x0:x0 + new_w] = resized
    return canvas

# 梦璃帧60（之前有水印残留）验证
for label, video, fi in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 60),
]:
    rgb = load_orig(video, fi)
    rgba = chroma_key_remove(rgb)
    before = rgba[:, :, 3].copy()
    after, removed = remove_watermark_strong(rgba[:, :, 3].copy())
    rgba[:, :, 3] = after
    # 角落半透明残留统计
    h, w = after.shape
    reg_before = before[int(h*0.70):, int(w*0.70):]
    reg_after = after[int(h*0.70):, int(w*0.70):]
    semi_before = int(((reg_before > 16) & (reg_before < 200)).sum())
    semi_after = int(((reg_after > 16) & (reg_after < 200)).sum())
    canvas = center_square(rgba)
    Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa3/{label}_strongwm.png")
    print(f"{label}: 删除像素={removed}, BR半透明 before={semi_before} after={semi_after}")
