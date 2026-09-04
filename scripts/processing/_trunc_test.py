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
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha
    return rgba

def truncate_corner_semitransparent(alpha, corner_ratio=0.30, keep_thresh=200):
    """四角区域内，alpha<keep_thresh 的像素置0（清半透明水印，保留角色实体）"""
    h, w = alpha.shape
    ch, cw = int(h * corner_ratio), int(w * corner_ratio)
    out = alpha.copy()
    # 四个角
    corners = [
        (slice(0, ch), slice(0, cw)),
        (slice(0, ch), slice(w - cw, w)),
        (slice(h - ch, h), slice(0, cw)),
        (slice(h - ch, h), slice(w - cw, w)),
    ]
    removed = 0
    for ys, xs in corners:
        reg = out[ys, xs]
        mask = reg < keep_thresh
        removed += int(mask.sum())
        reg[mask] = 0
    return out, removed

def center_square(rgba):
    src_h = rgba.shape[0]
    scale = 720 / src_h
    new_w = max(1, int(round(rgba.shape[1] * scale)))
    resized = cv2.resize(rgba, (new_w, 720), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((720, 720, 4), dtype=np.uint8)
    x0 = (720 - new_w) // 2
    canvas[:, x0:x0 + new_w] = resized
    return canvas

for label, video, fi in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 60),
    ("lingsha", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4", 30),
    ("tianhe", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4", 90),
]:
    rgb = load_orig(video, fi)
    rgba = chroma_key_remove(rgb)
    alpha, removed = truncate_corner_semitransparent(rgba[:, :, 3].copy())
    rgba[:, :, 3] = alpha
    canvas = center_square(rgba)
    Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa3/{label}_trunc.png")
    print(f"{label}: 四角半透明清除={removed}px")
