import cv2
import numpy as np

def load_orig(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)


def chroma_key_remove(rgb, hue_range=(30, 95), sat_min=30, val_min=60, dilate_iter=1):
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

# 找出水印出现帧，统计半透明残留的 alpha 与位置
video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"
found_frames = []
for fi in range(0, 121, 6):
    rgb = load_orig(video, fi)
    alpha = chroma_key_remove(rgb)
    h, w = alpha.shape
    # 四角区域
    regions = {
        "TL": (0, 0, int(h*0.30), int(w*0.30)),
        "TR": (0, int(w*0.70), int(h*0.30), w),
        "BL": (int(h*0.70), 0, h, int(w*0.30)),
        "BR": (int(h*0.70), int(w*0.70), h, w),
    }
    for rn, (y0, x0, y1, x1) in regions.items():
        reg = alpha[y0:y1, x0:x1]
        semi = (reg > 16) & (reg < 200)
        cnt = int(semi.sum())
        if cnt > 60:
            # 半透明像素的alpha分布
            vals = reg[semi]
            found_frames.append((fi, rn, cnt, int(vals.min()), int(np.median(vals)), int(vals.max())))

print("水印残留帧（帧, 角, 半透明px, alpha min/med/max）:")
for x in found_frames:
    print("  ", x)

# 抽样：看一个BR半透明残留的具体alpha直方图
if found_frames:
    fi, rn = found_frames[0][0], found_frames[0][1]
    rgb = load_orig(video, fi)
    alpha = chroma_key_remove(rgb)
    h, w = alpha.shape
    reg = alpha[int(h*0.70):, int(w*0.70):]
    semi = reg[(reg > 16) & (reg < 200)]
    hist, _ = np.histogram(semi, bins=[0,40,80,120,160,200])
    print(f"\n帧{fi} {rn} 半透明alpha直方图[0-40,40-80,80-120,120-160,160-200]: {hist}")
