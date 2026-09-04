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

# 找梦璃残留最大的帧，定位残留像素
video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"
cap = cv2.VideoCapture(video)
total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
best = None
for i in range(0, total, 3):
    cap.set(cv2.CAP_PROP_POS_FRAMES, i)
    ret, frame = cap.read()
    if not ret: break
    alpha = chroma_key_remove(frame)
    alpha, _ = remove_isolated_disconnected(alpha)
    h, w = alpha.shape
    border = 0.12
    bh, bw = int(h*border), int(w*border)
    edge = np.zeros((h,w), bool)
    edge[:bh,:]=True; edge[-bh:,:]=True; edge[:,:bw]=True; edge[:,-bw:]=True
    semi = (alpha > 16) & (alpha < 200) & edge
    cnt = int(semi.sum())
    if best is None or cnt > best[0]:
        best = (cnt, i, semi, frame)
cap.release()

cnt, fi, semi, frame = best
h, w = semi.shape
ys, xs = np.where(semi)
print(f"最大残留帧 f{fi}: {cnt}px, 位置 x:{xs.min()}-{xs.max()} y:{ys.min()}-{ys.max()}")
# 可视化：原图标记残留位置
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
vis = rgb.copy()
vis[semi] = [255, 0, 0]
Image.fromarray(vis).save("lingxi-pet/_qa3/mengli_residual_loc.png")
# 放大残留区域
if len(xs):
    pad = 30
    x0 = max(0, xs.min()-pad); x1 = min(w, xs.max()+pad)
    y0 = max(0, ys.min()-pad); y1 = min(h, ys.max()+pad)
    Image.fromarray(rgb[y0:y1, x0:x1]).save("lingxi-pet/_qa3/mengli_residual_zoom.png")
    print(f"放大区域 ({x0},{y0})-({x1},{y1})")
print("saved")
