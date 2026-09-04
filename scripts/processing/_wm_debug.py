import cv2
import numpy as np

HUE_RANGE = (30, 95); SAT_MIN = 30; VAL_MIN = 60; DILATE_ITER = 1

def load_orig(video, fi=60):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def chroma_key_remove(img_bgr):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (HUE_RANGE[0], SAT_MIN, VAL_MIN), (HUE_RANGE[1], 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=DILATE_ITER)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    return alpha

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"
rgb = load_orig(video, 60)
alpha = chroma_key_remove(rgb)
h, w = alpha.shape

# 看看 BR 区域（水印位置）的 alpha 情况
print("=== BR区域 alpha 统计 ===")
reg = alpha[int(h*0.70):, int(w*0.70):]
print("BR区域 alpha 值域:", reg.min(), "-", reg.max(), "| 中值:", np.median(reg))
for th in [16, 40, 80, 128, 200]:
    print(f"  alpha>{th}: {(reg>th).sum()} px")

# 连通域（alpha>16）
fg = (alpha > 16).astype(np.uint8)
n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
print(f"\n连通域总数: {n-1}")
areas = stats[1:, cv2.CC_STAT_AREA]
order = np.argsort(areas)[::-1]
print("Top12 连通域（idx, 面积, 质心x, 质心y）:")
for i in order[:12]:
    idx = i + 1
    print(f"  {idx}: area={stats[idx, cv2.CC_STAT_AREA]}, centroid=({centroids[idx][0]:.0f},{centroids[idx][1]:.0f}), "
          f"bbox=({stats[idx,cv2.CC_STAT_LEFT]},{stats[idx,cv2.CC_STAT_TOP]})-"
          f"({stats[idx,cv2.CC_STAT_LEFT]+stats[idx,cv2.CC_STAT_WIDTH]},{stats[idx,cv2.CC_STAT_TOP]+stats[idx,cv2.CC_STAT_HEIGHT]})")

# BR 角区域(30%)内有哪些连通域
cx, cy = w*0.70, h*0.70
print("\n=== 质心在 BR 角(>0.70w, >0.70h) 的连通域 ===")
for i in range(1, n):
    if centroids[i][0] > cx and centroids[i][1] > cy:
        a = stats[i, cv2.CC_STAT_AREA]
        if a >= 10:
            print(f"  id={i}: area={a}, centroid=({centroids[i][0]:.0f},{centroids[i][1]:.0f})")
