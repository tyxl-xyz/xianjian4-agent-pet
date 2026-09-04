import cv2
import numpy as np

# 逐视频背景 hue 范围（留安全余量），saturation 下限也校准
VIDEO_PARAMS = {
    "mengli": (55, 74),
    "ziying": (62, 74),
    "lingsha": (57, 68),
    "tianhe": (79, 90),
}

def load_frame(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return frame

def chroma_key_remove_narrow(img_bgr, hue_range, sat_min=30, val_min=60, dilate_iter=1):
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

# 背景清除完整度：角落背景区域应几乎全透明（alpha 很低）
# 道具保留：竖琴/剑/弓 色相像素应 alpha 高

def check_bg_clean(alpha, rgb, label):
    h, w = alpha.shape
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[:,:,0].astype(int), hsv[:,:,1].astype(int), hsv[:,:,2].astype(int)
    # 判定真实背景：角落在绿幕 hue 范围且 S>40
    bg_mask = np.zeros((h,w), bool)
    bh, bw = int(h*0.12), int(w*0.12)
    bg_mask[:bh,:]=True; bg_mask[-bh:,:]=True; bg_mask[:,:bw]=True; bg_mask[:,-bw:]=True
    # 背景绿像素
    params = VIDEO_PARAMS[label]
    bg_green = bg_mask & (H>=params[0]-2) & (H<=params[1]+2) & (S>40) & (V>60)
    if bg_green.sum() == 0:
        return 1.0, 0
    bg_alpha = alpha[bg_green]
    clean = (bg_alpha < 60).mean()  # 背景应大部分 alpha<60
    return clean, int(bg_green.sum())

def check_prop_keep(alpha, rgb, prop_hue, label):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[:,:,0].astype(int), hsv[:,:,1].astype(int), hsv[:,:,2].astype(int)
    # 道具色相像素（竖琴H110-135、剑H100-120、弓H0-20、菱纱无道具）
    prop = (H>=prop_hue[0]) & (H<=prop_hue[1]) & (S>40) & (V>60)
    if prop.sum() == 0:
        return 1.0, 0
    pa = alpha[prop]
    keep = (pa > 160).mean()
    return keep, int(prop.sum())

PROPS = {
    "mengli": (110, 135, "竖琴"),
    "ziying": (100, 120, "剑"),
    "lingsha": None,
    "tianhe": (0, 20, "弓"),
}

for label, (hr0, hr1) in VIDEO_PARAMS.items():
    video = f"C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/" + {
        "mengli": "梦璃_20260831_165425_cdf44267.mp4",
        "ziying": "紫英_20260831_165425_a6fd9aa4.mp4",
        "lingsha": "菱纱_20260831_165425_80bb1170.mp4",
        "tianhe": "天河_20260831_165425_222d101e.mp4",
    }[label]
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    bg_clean_vals = []
    prop_keep_vals = []
    frames = []
    for i in range(0, total, 10):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret: break
        frames.append(frame)
    cap.release()
    for frame in frames:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        alpha = chroma_key_remove_narrow(frame, (hr0, hr1))
        clean, _ = check_bg_clean(alpha, rgb, label)
        bg_clean_vals.append(clean)
        if PROPS[label] is not None:
            ph0, ph1, pname = PROPS[label]
            keep, _ = check_prop_keep(alpha, rgb, (ph0, ph1), label)
            prop_keep_vals.append(keep)
    print(f"{label}: 背景干净度(应≈1)={np.mean(bg_clean_vals):.3f}, "
          + (f"{PROPS[label][2]}保留率={np.mean(prop_keep_vals)*100:.1f}%" if PROPS[label] else "无道具"))
