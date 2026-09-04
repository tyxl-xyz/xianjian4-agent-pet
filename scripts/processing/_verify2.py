import cv2
import numpy as np

def chroma_key_remove(img_bgr, hue_range=(30, 95), sat_min=30, val_min=60):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (hue_range[0], sat_min, val_min), (hue_range[1], 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=2)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    return alpha

def remove_watermark_corner(alpha, corner_ratio=0.25, min_area=150, max_area=8000):
    """仅删除位于四角区域、且非主角色的孤立小块（水印）。"""
    h, w = alpha.shape
    fg = (alpha > 128).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    max_area = areas[np.argmax(areas)]
    cx = w * corner_ratio
    cy = h * corner_ratio
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area or a > max_area * 0.5:
            continue
        x_c, y_c = centroids[i]
        # 四角区域判定
        in_corner = (x_c < cx or x_c > w - cx) and (y_c < cy or y_c > h - cy)
        if not in_corner:
            continue
        remove[labels == i] = 1
        removed_cnt += int(a)
    alpha[remove > 0] = 0
    return alpha, removed_cnt

def analyze_video(path, label):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    frames = []
    for i in range(total):
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    sample_step = max(1, len(frames) // 50)
    removed_total = 0
    removed_frames = 0
    char_issues = 0
    for i in range(0, len(frames), sample_step):
        frame = cv2.resize(frames[i], (720, 720), interpolation=cv2.INTER_LANCZOS4)
        alpha = chroma_key_remove(frame)
        before_fg = (alpha > 128).sum()
        alpha2, removed = remove_watermark_corner(alpha)
        after_fg = (alpha2 > 128).sum()
        if removed > 0:
            removed_total += removed
            removed_frames += 1
        # 主角色损失检测：如果删除像素过多（>5%前景），警告
        if before_fg > 0 and removed > before_fg * 0.05:
            char_issues += 1
    print(f"{label}: 采样{len(frames)//sample_step+1}帧, 有水印帧={removed_frames}, "
          f"总删除像素={removed_total}, 疑似误删角色帧={char_issues}")

for name in ["待机", "工作", "开心", "难过"]:
    analyze_video(f"C:/Users/13544/Desktop/新建文件夹/{name}.mp4", name)
