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

def remove_isolated_watermark(alpha, min_area=300, max_area=8000):
    fg = (alpha > 128).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    h, w = alpha.shape
    areas = stats[1:, cv2.CC_STAT_AREA]
    if len(areas) == 0:
        return alpha
    max_area = areas[np.argmax(areas)]
    remove = np.zeros((h, w), np.uint8)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area:
            continue
        if a > max_area * 0.5:
            continue
        remove[labels == i] = 1
    alpha[remove > 0] = 0
    return alpha

def analyze_video(path, label):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    removed_total = 0
    removed_frames = 0
    char_broken = 0
    frames_with_any_fg = 0
    # 采样部分帧评估
    sample_step = max(1, total // 40)
    for i in range(0, total, sample_step):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret:
            continue
        frame = cv2.resize(frame, (720, 720), interpolation=cv2.INTER_LANCZOS4)
        alpha = chroma_key_remove(frame)
        before_fg = (alpha > 128).sum()
        # 角色连通块数（水印会导致多于1个块）
        fg_before = (alpha > 128).astype(np.uint8)
        n_before, _, _, _ = cv2.connectedComponentsWithStats(fg_before, connectivity=8)
        after = remove_isolated_watermark(alpha)
        fg_after = (after > 128).astype(np.uint8)
        n_after, labels, stats, _ = cv2.connectedComponentsWithStats(fg_after, connectivity=8)
        areas = stats[1:, cv2.CC_STAT_AREA]
        main_area = areas[np.argmax(areas)] if len(areas) else 0
        removed = int((before_fg > 0).sum() - (after > 0).sum())
        # 角色主体面积是否明显缩小（>15% 视为误删）
        if main_area < before_fg * 0.85:
            char_broken += 1
        if removed > 0:
            removed_total += removed
            removed_frames += 1
    cap.release()
    print(f"{label}: 采样帧={total//sample_step + 1}, 有水印残留帧={removed_frames}, "
          f"总清除像素={removed_total}, 角色疑似误删帧={char_broken}")

for name in ["待机", "工作", "开心", "难过"]:
    analyze_video(f"C:/Users/13544/Desktop/新建文件夹/{name}.mp4", name)

# 测量已有 idle.mov 的角色构图（方形 256x256）
mov = "C:/Users/13544/AppData/Roaming/desktop-pet/accounts/230581940/pets/han-ling-sha/user/idle.mov"
cap = cv2.VideoCapture(mov)
ret, frame = cap.read()
cap.release()
h, w = frame.shape[:2]
top = frame[:h // 2]  # 上半 RGB
rgb = cv2.cvtColor(top, cv2.COLOR_BGR2RGB)
alpha_full = frame[h // 2:, :, 0]  # 下半 matte（灰度）
ys, xs = np.where(alpha_full > 128)
if len(xs):
    print(f"existing idle.mov frame: {w}x{h//2}, 角色 bbox=({xs.min()},{ys.min()})-({xs.max()},{ys.max()})")
    bw, bh = xs.max()-xs.min()+1, ys.max()-ys.min()+1
    print(f"  宽占{bw/w*100:.0f}%, 高占{bh/(h//2)*100:.0f}%, top={ys.min()/(h//2)*100:.0f}%, bottom={(h//2-1-ys.max())/(h//2)*100:.0f}%")
