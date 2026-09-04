import cv2
import numpy as np
from PIL import Image

HUE_RANGE = (30, 95)
SAT_MIN = 30
VAL_MIN = 60


def load_orig(video, fi=60):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def flood_fill_bg(rgb, hue_range=HUE_RANGE, sat_min=SAT_MIN, val_min=VAL_MIN):
    """绿幕背景 = 与四边连通的绿色区域（flood-fill），保留被前景包围的绿色道具"""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    green = cv2.inRange(hsv, (hue_range[0], sat_min, val_min), (hue_range[1], 255, 255))
    h, w = green.shape

    # 从四边播种绿色连通域
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    green = cv2.morphologyEx(green, cv2.MORPH_OPEN, kernel)
    bg = np.zeros((h, w), np.uint8)
    # 用 floodFill 标记与边界连通的绿色（基于 green 掩码图填充 mask）
    mask = np.zeros((h+2, w+2), np.uint8)
    fill_val = 255
    for x in range(0, w):
        for y in [0, h-1]:
            if green[y, x] and mask[y+1, x+1] == 0:
                cv2.floodFill(green, mask, (x, y), fill_val,
                              flags=8 | (fill_val << 8) | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE)
    for y in range(0, h):
        for x in [0, w-1]:
            if green[y, x] and mask[y+1, x+1] == 0:
                cv2.floodFill(green, mask, (x, y), fill_val,
                              flags=8 | (fill_val << 8) | cv2.FLOODFILL_MASK_ONLY | cv2.FLOODFILL_FIXED_RANGE)

    # 实际掩码在 mask[1:h+1,1:w+1]
    bg = mask[1:h+1, 1:w+1].copy()
    # 背景 mask（被标记为背景的绿色）+ 常规形态学补强
    bg = cv2.morphologyEx(bg, cv2.MORPH_CLOSE, kernel, iterations=3)
    bg = cv2.dilate(bg, kernel, iterations=1)
    alpha = ((1.0 - bg.astype(np.float32) / 255.0) * 255).clip(0, 255).astype(np.uint8)
    alpha = cv2.GaussianBlur(alpha, (5, 5), 0)
    rgba = cv2.cvtColor(rgb, cv2.COLOR_RGB2RGBA)
    rgba[:, :, 3] = alpha
    return rgba, bg


def remove_watermark_corner(alpha, corner_ratio=0.25, min_area=150, max_area=8000):
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


for label, video in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
]:
    rgb = load_orig(video, 60)
    rgba, bg = flood_fill_bg(rgb)
    alpha = rgba[:, :, 3]
    alpha, _ = remove_watermark_corner(alpha)
    rgba[:, :, 3] = alpha
    # 等比缩放居中
    src_h = 1280
    scale = 720 / src_h
    new_w = max(1, int(round(720 * scale)))
    resized = cv2.resize(rgba, (new_w, 720), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((720, 720, 4), dtype=np.uint8)
    x0 = (720 - new_w) // 2
    canvas[:, x0:x0 + new_w] = resized
    Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa3/{label}_flood_test.png")
    print(f"{label}: flood-fill 抠图完成, bg_px={(bg>0).sum()}")
