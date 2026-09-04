import cv2
import numpy as np
from PIL import Image

HUE_RANGE = (30, 95); SAT_MIN = 30; VAL_MIN = 60

def load_orig(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def chroma_key_remove(img_bgr, dilate_iter=1):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (HUE_RANGE[0], SAT_MIN, VAL_MIN), (HUE_RANGE[1], 255, 255))
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

def remove_watermark_by_distance(alpha, min_area=30, max_area=20000, dist_thresh=20):
    """删除小孤立块：质心到角色实体(alpha>200)的距离超过阈值（在背景空白区）"""
    h, w = alpha.shape
    fg = (alpha > 40).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_id = np.argmax(areas) + 1
    max_area_main = areas[np.argmax(areas)]
    # 角色实体 mask（alpha>200）用于距离变换
    solid = (alpha > 200).astype(np.uint8)
    dist = cv2.distanceTransform((1 - solid), cv2.DIST_L2, 5)
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    for i in range(1, n):
        if i == main_id:
            continue
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area or a > max_area_main * 0.5:
            continue
        x_c, y_c = int(centroids[i][0]), int(centroids[i][1])
        if 0 <= x_c < w and 0 <= y_c < h:
            d = dist[y_c, x_c]
            if d >= dist_thresh:
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

for label, video, fi in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 60),
    ("lingsha", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4", 30),
    ("tianhe", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4", 90),
]:
    rgb = load_orig(video, fi)
    rgba = chroma_key_remove(rgb)
    alpha = rgba[:, :, 3].copy()
    alpha, removed = remove_watermark_by_distance(alpha)
    rgba[:, :, 3] = alpha
    canvas = center_square(rgba)
    Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa3/{label}_distwm.png")
    print(f"{label}: 删除像素={removed}")
