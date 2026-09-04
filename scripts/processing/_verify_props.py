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

# 道具保留率客观检测：比较抠图前后道具色相像素的保留
def prop_retention(video, fi, prop_hue_range, y0,y1,x0,x1, label):
    rgb = load_orig(video, fi)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H = hsv[:, :, 0]
    prop_mask = (H >= prop_hue_range[0]) & (H <= prop_hue_range[1]) & (hsv[:,:,1] > 40)
    total_prop = int(prop_mask[y0:y1, x0:x1].sum())
    # 抠图后该区域这些色相像素 alpha 保留情况
    alpha = chroma_key_remove(cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR))
    alpha2, _ = remove_isolated_disconnected(alpha)
    kept_before = int((alpha > 128)[y0:y1, x0:x1][prop_mask[y0:y1, x0:x1]].sum()) if total_prop else 0
    kept_after = int((alpha2 > 128)[y0:y1, x0:x1][prop_mask[y0:y1, x0:x1]].sum()) if total_prop else 0
    print(f"{label}: 道具色相像素 {total_prop}, 抠图后保留(不透明) {kept_before}, 接触判定后 {kept_after}, "
          f"保留率={kept_after/max(total_prop,1)*100:.0f}%")

# 竖琴色相 H110-130
prop_retention("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60, (110,135), 704, 1088, 300, 480, "梦璃竖琴")
# 剑色相 H100-120
prop_retention("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 60, (100,120), 576, 1088, 300, 480, "紫英剑")
# 弓色相 H0-25（红色弓）
prop_retention("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4", 60, (0,20), 576, 1088, 250, 500, "天河弓")

# 水印残留客观检测：处理后 alpha 中边缘区域的半透明像素
print("\n=== 水印残留检测（处理后各帧边缘 alpha 半透明像素） ===")
for label, video in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
    ("lingsha", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4"),
    ("tianhe", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"),
]:
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # 抽帧统计
    residual_frames = 0
    total_residual = 0
    for i in range(0, total, 6):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret: break
        alpha = chroma_key_remove(frame)
        alpha, _ = remove_isolated_disconnected(alpha)
        h, w = alpha.shape
        # 边缘带 12% 内的半透明残留（水印文字 alpha 约 16-200）
        border = 0.12
        bh, bw = int(h*border), int(w*border)
        edge = np.zeros((h,w), bool)
        edge[:bh,:]=True; edge[-bh:,:]=True; edge[:,:bw]=True; edge[:,-bw:]=True
        semi = (alpha > 16) & (alpha < 200) & edge
        cnt = int(semi.sum())
        if cnt > 30:
            residual_frames += 1
            total_residual += cnt
    cap.release()
    print(f"  {label}: 有残留边缘帧={residual_frames}, 累计半透明px={total_residual}")
