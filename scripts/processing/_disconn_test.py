import cv2
import numpy as np

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
    return alpha

def remove_isolated_disconnected(alpha, min_area=30, max_area=20000, fg_thresh=40, main_contact=8):
    """
    删除与主角色连通域无像素接触的独立小块（含半透明水印）。
    判定：alpha>fg_thresh 找连通域；最大者为主角色；
    其余面积在 [min_area,max_area] 的块，若与主角色相邻距离 > main_contact 则删除。
    """
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_id = np.argmax(areas) + 1
    max_area_main = areas[np.argmax(areas)]
    # 主角色 mask（带少量膨胀，避免删掉紧贴主体的部件）
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
        # 该块是否与膨胀后的主角色接触
        blob = (labels == i)
        if np.any(blob & (main_dil > 0)):
            continue  # 接触主体 → 保留（可能是流苏/飘带/道具边缘）
        remove[blob] = 1
        removed_cnt += int(a)
    alpha[remove > 0] = 0
    return alpha, removed_cnt

for label, video in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
    ("lingsha", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4"),
    ("tianhe", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"),
]:
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frames = []
    for i in range(total):
        ret, frame = cap.read()
        if not ret:
            break
        frames.append(frame)
    cap.release()
    total_removed = 0
    removed_frames = 0
    main_loss_frames = 0
    sample_step = max(1, total // 40)
    for i in range(0, total, sample_step):
        alpha = chroma_key_remove(frames[i])
        before_fg = int((alpha > 128).sum())
        alpha2, removed = remove_isolated_disconnected(alpha)
        after_fg = int((alpha2 > 128).sum())
        total_removed += removed
        if removed > 0:
            removed_frames += 1
        if before_fg > 0 and removed > before_fg * 0.08:
            main_loss_frames += 1
    print(f"{label}: 采样{len(range(0,total,sample_step))}帧, 清除块帧数={removed_frames}, "
          f"总清除px={total_removed}, 主角色疑似受损帧={main_loss_frames}")
