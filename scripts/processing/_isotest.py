import cv2
import numpy as np

# 思路：先完整抠图（含水印残留），然后对 alpha 做连通域分析，
# 将「透明背景中的孤立小不透明块」（水印文字）强制置透明。
# 角色是主要大块不透明区，不受影响。

def chroma_key_remove(img_bgr, hue_range=(30,95), sat_min=30, val_min=60):
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
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2BGRA)
    rgba[:, :, 3] = alpha
    return rgba

def remove_isolated_watermark(rgba, min_area=300, max_area=6000):
    """将透明区域中孤立的不透明小块（面积在 min_area..max_area 且非连接大块）置透明。"""
    alpha = rgba[:, :, 3]
    # 找不透明区域(alpha>128)
    fg = (alpha > 128).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    h, w = alpha.shape
    total_fg = int((fg > 0).sum())
    # 找出面积最大的连通块（角色主体）
    areas = stats[1:, cv2.CC_STAT_AREA]
    if len(areas) == 0:
        return rgba
    max_area_id = int(np.argmax(areas)) + 1
    max_area = areas[np.argmax(areas)]
    # 只处理「明显小于角色主体」且面积在合理文字范围、且不贴主体大块的孤立块
    remove = np.zeros((h, w), np.uint8)
    for i in range(1, n):
        if i == max_area_id:
            continue
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area:
            continue
        if a > max_area * 0.5:
            continue
        remove[labels == i] = 1
    alpha[remove > 0] = 0
    rgba[:, :, 3] = alpha
    return rgba

cap = cv2.VideoCapture("C:/Users/13544/Desktop/新建文件夹/待机.mp4")
h, w = 720, 720
for fi in [0, 40, 80, 120]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    if not ret:
        continue
    # 缩放到720x720（竖屏拉伸——先只测水印清除效果）
    frame = cv2.resize(frame, (720, 720), interpolation=cv2.INTER_LANCZOS4)
    rgba = chroma_key_remove(frame)
    before = rgba.copy()
    after = remove_isolated_watermark(rgba)
    cv2.imwrite(f"lingxi-pet/_build/test/iso_f{fi}_before.png", before)
    cv2.imwrite(f"lingxi-pet/_build/test/iso_f{fi}_after.png", after)
    print(f"f{fi}: done")
cap.release()
print("all done")
