import cv2
import numpy as np
from PIL import Image

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
cap.set(cv2.CAP_PROP_POS_FRAMES, 46)
ret, frame = cap.read()
cap.release()

# 阶段1: 收窄hue抠图
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

# 左腿区域
x0, y0, x1, y1 = 120, 780, 360, 1120
alpha1 = chroma_key_remove_narrow(frame)
print("阶段1(收窄hue)后左腿 alpha>128:", int((alpha1[y0:y1, x0:x1] > 128).sum()))

# 阶段2: 孤立块清除
def remove_isolated_disconnected(alpha, min_area=30, max_area=20000, fg_thresh=40, main_contact=8):
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_id = np.argmax(areas) + 1
    max_area_main = areas[np.argmax(areas)]
    main_mask = (labels == main_id).astype(np.uint8)
    kernel = np.ones((main_contact * 2 + 1, main_contact * 2 + 1), np.uint8)
    main_dil = cv2.dilate(main_mask, kernel)
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    removed_leg = 0
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
        # 该块是否落在左腿区域
        leg_overlap = int(blob[y0:y1, x0:x1].sum())
        if leg_overlap > 0:
            removed_leg += leg_overlap
            print(f"    删块 id{i} area={a} 质心=({centroids[i][0]:.0f},{centroids[i][1]:.0f}) 左腿重叠={leg_overlap}")
    alpha[remove > 0] = 0
    return alpha, removed_cnt, removed_leg

alpha2, removed, removed_leg = remove_isolated_disconnected(alpha1.copy())
print(f"阶段2(孤立块清除)删除px={removed}, 其中左腿区域={removed_leg}")
print("阶段2后左腿 alpha>128:", int((alpha2[y0:y1, x0:x1] > 128).sum()))

# 检查左腿区域在主连通域判定中是否被当作独立块
fg = (alpha1 > 40).astype(np.uint8)
n, labels, stats, cent = cv2.connectedComponentsWithStats(fg, connectivity=8)
areas = stats[1:, cv2.CC_STAT_AREA]
main_id = np.argmax(areas) + 1
# 找出左腿区域的label
leg_labels = set(labels[y0:y1, x0:x1][alpha1[y0:y1, x0:x1] > 40].flatten().tolist()) - {0}
print(f"左腿区域涉及的连通域labels: {leg_labels}")
for lb in leg_labels:
    if lb == main_id:
        print(f"  label {lb} 是主角色(id={main_id})")
    else:
        print(f"  label {lb} 独立块 area={stats[lb, cv2.CC_STAT_AREA]} (主角色area={areas[np.argmax(areas)]})")
