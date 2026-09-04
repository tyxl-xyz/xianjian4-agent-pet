import cv2
import numpy as np

HUE_RANGE = (30, 95); SAT_MIN = 30; VAL_MIN = 60

def load_orig(video, fi):
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
    mask = cv2.dilate(mask, kernel, iterations=1)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    return alpha

# 用 alpha>40 找前景（含半透明水印）
for label, video in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
    ("lingsha", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4"),
    ("tianhe", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"),
]:
    print(f"=== {label} ===")
    for fi in [0, 30, 60, 90, 120]:
        rgb = load_orig(video, fi)
        alpha = chroma_key_remove(rgb)
        h, w = alpha.shape
        fg = (alpha > 40).astype(np.uint8)
        n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
        areas = stats[1:, cv2.CC_STAT_AREA]
        if len(areas) == 0:
            continue
        main = np.argmax(areas) + 1
        main_l = stats[main, cv2.CC_STAT_LEFT]; main_t = stats[main, cv2.CC_STAT_TOP]
        main_r = main_l + stats[main, cv2.CC_STAT_WIDTH]; main_b = main_t + stats[main, cv2.CC_STAT_HEIGHT]
        blobs = []
        for i in range(1, n):
            if i == main:
                continue
            a = stats[i, cv2.CC_STAT_AREA]
            if a < 30 or a > 20000:
                continue
            bl = stats[i, cv2.CC_STAT_LEFT]; bt = stats[i, cv2.CC_STAT_TOP]
            br = bl + stats[i, cv2.CC_STAT_WIDTH]; bb = bt + stats[i, cv2.CC_STAT_HEIGHT]
            # 到主角色包围盒的间距
            dx = max(bl - main_r, main_l - br, 0)
            dy = max(bt - main_b, main_t - bb, 0)
            dist = (dx**2 + dy**2) ** 0.5
            # 质心相对主盒
            in_box = (main_l <= centroids[i][0] <= main_r) and (main_t <= centroids[i][1] <= main_b)
            blobs.append((i, a, round(dist,0), in_box, round(centroids[i][0],0), round(centroids[i][1],0)))
        # 汇总：水印应是小面积且明显远离主盒（dist 大）
        far = [b for b in blobs if b[2] > 50 and not b[3]]
        near = [b for b in blobs if b[2] <= 50 or b[3]]
        print(f"  f{fi}: 主盒({main_l},{main_t})-({main_r},{main_b}) 面积{areas[np.argmax(areas)]} | "
              f"孤立块{len(blobs)}: 远块{len(far)} 近块{len(near)}")
        for b in far[:6]:
            print(f"    [远] id{b[0]} area{b[1]} dist={b[2]} in_box={b[3]} c=({b[4]},{b[5]})")
