#!/usr/bin/env python3
"""修正版：5个新视频绿幕抠图（低 sat 阈值匹配灰绿幕）+ 水印清除 + 方形化 → GIF"""
import os
import sys
import numpy as np
import cv2
from PIL import Image

sys.path.insert(0, r"C:\Users\13544\AppData\Roaming\WPS 灵犀\serverdir\target_skills\lingxi-pet\scripts")
from chroma_key_to_gif import rgba_to_gif_frames, DEFAULT_ALPHA_THRESHOLD

# 逐视频绿幕参数（OpenCV 对 ffmpeg 抽帧实测）：hue, sat_min, val_min
# val_min 用于分离"亮背景绿 vs 暗角色同色部位"（如 tianhe_shoot 上衣绿 V 分布更暗）
VIDEO_PARAMS = {
    "tianhe_shoot":   ((72, 90),   60, 140),  # 射箭男：背景绿V>=150，val140 保上衣暗部
    "lingsha_ziying": ((28, 50),   40, 40),   # 黄绿 hue~41
    "lingsha_tianhe": ((42, 60),   40, 40),   # 标准绿 hue~52
    "mengli_ziying":  ((71, 87),   35, 40),   # 青绿 hue~81，背景S低至31；sat35 抠净背景且保竖琴/佩剑
    "mengli_lingsha": ((50, 72),   40, 40),   # 绿 hue~64
}
VAL_MIN = 40
DILATE_ITER = 1
OUT_SIZE = 720
SAMPLE_FPS = 24
ALPHA_THRESHOLD = DEFAULT_ALPHA_THRESHOLD
WM_MIN_AREA = 60
WM_MAX_AREA = 20000
WM_BORDER = 0.30

def chroma_key_remove(img_bgr, hue_range, sat_min, val_min=VAL_MIN, dilate_iter=DILATE_ITER):
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (hue_range[0], sat_min, val_min), (hue_range[1], 255, 255))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, k, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, k, iterations=2)
    mask = cv2.dilate(mask, k, iterations=dilate_iter)
    alpha = ((1 - mask.astype(np.float32) / 255.0) * 255).clip(0, 255).astype(np.uint8)
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha
    return rgba

def remove_wm(alpha, min_area=WM_MIN_AREA, max_area=WM_MAX_AREA, fg_thresh=16, border=WM_BORDER):
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main = np.argmax(areas) + 1
    maxa = areas.max()
    bh, bw = int(h * border), int(w * border)
    rm = np.zeros((h, w), np.uint8)
    cnt = 0
    for i in range(1, n):
        if i == main:
            continue
        a = stats[i, cv2.CC_STAT_AREA]
        # 清除：贴边的小块（水印/残留） + 贴边的大块背景（面积大但紧贴边缘、非角色主体）
        xc, yc = centroids[i]
        edge = (xc < bw or xc > w - bw) or (yc < bh or yc > h - bh)
        is_edge_blob = edge and a > 2000 and a <= maxa * 0.6
        is_small_wm = a < max_area and a > min_area and edge and a <= maxa * 0.5
        if is_small_wm or is_edge_blob:
            rm[labels == i] = 1
            cnt += int(a)
    alpha[rm > 0] = 0
    return alpha, cnt

def process_video(src, out_gif, hue_range, sat_min, val_min=VAL_MIN):
    cap = cv2.VideoCapture(src)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    print(f"  {os.path.basename(src)}: {total}帧 hue={hue_range} sat={sat_min} val={val_min}")
    frames_p = []
    t = 0.0; frame_idx = 0
    interval = 1.0 / SAMPLE_FPS
    src_h = src_w = None
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if src_h is None:
            src_h, src_w = frame.shape[:2]
        cur_t = frame_idx / fps
        if abs(cur_t - t) < interval * 0.5 or frame_idx == 0:
            rgba = chroma_key_remove(frame, hue_range, sat_min, val_min)
            a = rgba[:, :, 3]
            a, _ = remove_wm(a)
            rgba[:, :, 3] = a
            scale = OUT_SIZE / src_h
            nw = max(1, int(round(src_w * scale)))
            resized = cv2.resize(rgba, (nw, OUT_SIZE), interpolation=cv2.INTER_LANCZOS4)
            canvas = np.zeros((OUT_SIZE, OUT_SIZE, 4), dtype=np.uint8)
            x0 = (OUT_SIZE - nw) // 2
            canvas[:, x0:x0 + nw] = resized
            frames_p.append(rgba_to_gif_frames(Image.fromarray(canvas, mode="RGBA"), ALPHA_THRESHOLD))
            t += interval
        frame_idx += 1
        if frame_idx >= total:
            break
    cap.release()
    if not frames_p:
        print("  无帧"); return
    dur = max(10, round(1000 / SAMPLE_FPS / 10) * 10)
    frames_p[0].save(out_gif, save_all=True, append_images=frames_p[1:],
                     duration=dur, loop=0, transparency=0, disposal=2, optimize=True)
    print(f"  -> {os.path.basename(out_gif)} ({os.path.getsize(out_gif)/1024:.1f}KB {len(frames_p)}帧)")

def main():
    base = r"C:\Users\13544\Desktop\sucai"
    out_root = r"D:\TOOL\20260831-14-46-47-666\lingxi-pet\_build6"
    jobs = [
        ("Q版韩菱纱短视频生成.mp4", "tianhe_shoot"),
        ("Q版韩菱纱短视频生成1.mp4", "lingsha_ziying"),
        ("Q版韩菱纱短视频生成2.mp4", "lingsha_tianhe"),
        ("Q版韩菱纱短视频生成3.mp4", "mengli_ziying"),
        ("Q版韩菱纱短视频生成123.mp4", "mengli_lingsha"),
    ]
    for src_name, action_id in jobs:
        out_dir = os.path.join(out_root, action_id)
        os.makedirs(out_dir, exist_ok=True)
        print(f"[{action_id}]")
        hr, sm, vm = VIDEO_PARAMS[action_id]
        process_video(os.path.join(base, src_name), os.path.join(out_dir, action_id + ".gif"), hr, sm, vm)
    print("完成")

if __name__ == "__main__":
    main()
