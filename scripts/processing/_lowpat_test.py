import cv2
import numpy as np

HUE_RANGE = (30, 95); SAT_MIN = 30; VAL_MIN = 60

def load_frame(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return frame

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
    return alpha

def remove_isolated_disconnected(alpha, min_area=30, max_area=20000, fg_thresh=40, main_contact=8):
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_id = np.argmax(areas) + 1
    max_area_main = areas[np.argmax(areas)]
    main_mask = (labels == main_id).astype(np.uint8)
    kernel = np.ones((main_contact * 2 + 1, main_contact * 2 + 1), np.uint8)
    main_dil = cv2.dilate(main_mask, kernel)
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    for i in range(1, n):
        if i == main_id:
            continue
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area or a > max_area_main * 0.5:
            continue
        blob = (labels == i)
        if np.any(blob & (main_dil > 0)):
            continue
        remove[blob] = 1
        removed_cnt += int(a)
    alpha[remove > 0] = 0
    return alpha, removed_cnt

def zero_low_sat_semitransparent(alpha, img_bgr, sat_thresh=45, alpha_max=200):
    """半透明(alpha<alpha_max)且原图饱和度低(白色文字特征)的像素置0"""
    hsv = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2HSV)
    S = hsv[:, :, 1]
    low_sat = S < sat_thresh
    semi = alpha < alpha_max
    mask = low_sat & semi
    # 保护 alpha 极低(背景)不处理
    mask = mask & (alpha > 16)
    alpha[mask] = 0
    return alpha, int(mask.sum())

for label, video in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
    ("lingsha", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4"),
    ("tianhe", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"),
]:
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    residual_frames = 0
    total_residual = 0
    char_affected = 0
    for i in range(0, total, 6):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret: break
        alpha = chroma_key_remove(frame)
        alpha, _ = remove_isolated_disconnected(alpha)
        before_high = int((alpha > 200).sum())
        alpha, cleared = zero_low_sat_semitransparent(alpha, frame)
        after_high = int((alpha > 200).sum())
        h, w = alpha.shape
        border = 0.12
        bh, bw = int(h*border), int(w*border)
        edge = np.zeros((h,w), bool)
        edge[:bh,:]=True; edge[-bh:,:]=True; edge[:,:bw]=True; edge[:,-bw:]=True
        semi = (alpha > 16) & (alpha < 200) & edge
        cnt = int(semi.sum())
        if cnt > 30:
            residual_frames += 1
            total_residual += cnt
        if before_high > 0 and (before_high - after_high) > before_high * 0.01:
            char_affected += 1
    cap.release()
    print(f"{label}: 有残留边缘帧={residual_frames}, 累计半透明px={total_residual}, 高alpha像素受损帧={char_affected}")
