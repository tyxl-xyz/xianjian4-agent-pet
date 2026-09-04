import cv2
import numpy as np
from PIL import Image

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
frames = {}
for fi in range(121):
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    if ret:
        frames[fi] = frame
cap.release()

def chroma_key_remove_narrow(img_bgr, hue_range=(79, 90), sat_min=30, val_min=60, dilate_iter=1):
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
    return alpha


def remove_isolated_disconnected_v2(alpha, min_area=40, max_area=6000, fg_thresh=40, border=0.16):
    """
    修复版：仅删除"面积小(40-6000) 且 质心贴近画面边缘(边带16%)"的孤立块（水印特征）。
    先对前景做形态学闭运算，使四肢/道具与主体重连，避免误删腿部。
    """
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    # 形态学闭运算重连细小断裂（躯干-四肢、道具-主体）
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
        # 只删 alpha 掩码中原本独立、且不在主体膨胀范围内的像素
        blob = (labels == i)
        remove[blob] = 1
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


# 左腿区域（原图坐标）
x0, y0, x1, y1 = 120, 780, 360, 1120
print("=== 修复版逐帧左腿 alpha>128（应全程保留~2.7万，不再突降） ===")
leg_vals = []
for fi in range(121):
    alpha = chroma_key_remove_narrow(frames[fi])
    alpha2, removed = remove_isolated_disconnected_v2(alpha)
    leg_vals.append(int((alpha2[y0:y1, x0:x1] > 128).sum()))
for fi in range(121):
    print(f"  f{fi}: {leg_vals[fi]}", end="  ")
    if (fi + 1) % 6 == 0:
        print()
print("\nmin:", min(leg_vals), "at frame", leg_vals.index(min(leg_vals)))

# 渲染 f46 和 f50 对比
for fi in [46, 50, 60]:
    frame = frames[fi]
    alpha = chroma_key_remove_narrow(frame)
    alpha2, _ = remove_isolated_disconnected_v2(alpha)
    rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha2
    canvas = center_square(rgba)
    Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa5/tianhe_fixed_f{fi}.png")
print("rendered fixed frames")
