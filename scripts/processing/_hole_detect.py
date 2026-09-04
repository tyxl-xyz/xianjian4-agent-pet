import cv2
import numpy as np
from PIL import Image

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def chroma_key_remove_narrow(img_bgr, hue_range=(79, 90), sat_min=30, val_min=60, dilate_iter=1):
    rgbx = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgbx, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (hue_range[0], sat_min, val_min), (hue_range[1], 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=dilate_iter)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    return alpha

def remove_isolated_disconnected_v2(alpha, min_area=40, max_area=6000, fg_thresh=40, border=0.16):
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, close_k)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_id = np.argmax(areas) + 1
    max_area_main = areas[np.argmax(areas)]
    bh, bw = int(h * border), int(w * border)
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    for i in range(1, n):
        if i == main_id:
            continue
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area or a > max_area_main * 0.5:
            continue
        x_c, y_c = centroids[i]
        near_edge = (x_c < bw or x_c > w - bw) or (y_c < bh or y_c > h - bh)
        if not near_edge:
            continue
        blob = (labels == i)
        remove[blob] = 1
        removed_cnt += int(a)
    alpha[remove > 0] = 0
    return alpha, removed_cnt

# 源中角色区域
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
green = ((H >= 76) & (H <= 93) & (S > 25) & (V > 60))
char_region = ~green  # 非背景 = 角色/道具

alpha = chroma_key_remove_narrow(frame)
alpha2, _ = remove_isolated_disconnected_v2(alpha)

# 角色区域内被删成透明的像素（alpha<=16）
holes = char_region & (alpha2 <= 16)
print(f"角色区域内被删成透明的像素: {int(holes.sum())}")
ys, xs = np.where(holes)
if len(xs):
    print(f"  洞bbox x:{xs.min()}-{xs.max()} y:{ys.min()}-{ys.max()}")
    # 连通域分组
    h2, w2 = holes.shape
    n, labels, stats, cent = cv2.connectedComponentsWithStats(holes.astype(np.uint8), connectivity=8)
    print(f"  洞连通域数: {n-1}")
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a > 100:
            print(f"    id{i} area={a} bbox=({stats[i,cv2.CC_STAT_LEFT]},{stats[i,cv2.CC_STAT_TOP]})-"
                  f"({stats[i,cv2.CC_STAT_LEFT]+stats[i,cv2.CC_STAT_WIDTH]},{stats[i,cv2.CC_STAT_TOP]+stats[i,cv2.CC_STAT_HEIGHT]}) "
                  f"质心=({cent[i][0]:.0f},{cent[i][1]:.0f})")

# 可视化：洞标记在原图上
vis = rgb.copy()
vis[holes > 0] = [255, 0, 0]
Image.fromarray(vis).save("lingxi-pet/_qa5/tianhe_holes_f60.png")
print("saved holes overlay")
