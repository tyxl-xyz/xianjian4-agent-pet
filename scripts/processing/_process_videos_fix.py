#!/usr/bin/env python3
"""修复版：四角色绿幕视频 → 透明 GIF。
管线：逐视频收窄 hue 抠图 → 形态学闭运算重连四肢 → 仅删边缘小孤立水印块 → 等比缩放居中。
修复点：天河左腿不再被孤立块清除误删。
"""
import os
import sys
import numpy as np
import cv2
from PIL import Image

sys.path.insert(0, r"C:\Users\13544\AppData\Roaming\WPS 灵犀\serverdir\target_skills\lingxi-pet\scripts")
from chroma_key_to_gif import rgba_to_gif_frames, DEFAULT_ALPHA_THRESHOLD

VIDEO_PARAMS = {
    "mengli": (55, 74),
    "ziying": (62, 74),
    "lingsha": (57, 68),
    "tianhe": (79, 90),
}
SAT_MIN = 30
VAL_MIN = 60
OUT_SIZE = 720
SAMPLE_FPS = 24
ALPHA_THRESHOLD = DEFAULT_ALPHA_THRESHOLD

WM_MIN_AREA = 40
WM_MAX_AREA = 6000
WM_BORDER = 0.16


def chroma_key_remove_narrow(img_bgr, hue_range, sat_min=SAT_MIN, val_min=VAL_MIN, dilate_iter=1):
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
    rgba = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha
    return rgba


def remove_isolated_disconnected_v2(alpha, min_area=WM_MIN_AREA, max_area=WM_MAX_AREA,
                                    fg_thresh=40, border=WM_BORDER):
    """修复版孤立块清除：先闭运算重连四肢，仅删贴近边缘的小孤立块（水印特征）。"""
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, close_k)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_id = np.argmax(areas) + 1
    max_area_main = areas[np.argmax(areas)]
    bh, bw = int(h * border), int(w * border)
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    for i in range(1, n):
        if i == main_id:
            continue
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area or a > max_area_main * 0.5:
            continue
        x_c, y_c = centroids[i]
        near_edge = (x_c < bw or x_c > w - bw) or (y_c < bh or y_c > h - bh)
        if not near_edge:
            continue
        blob = (labels == i)
        remove[blob] = 1
        removed_cnt += int(a)
    alpha[remove > 0] = 0
    return alpha, removed_cnt


def process_video(src_path, out_gif_path, hue_range):
    cap = cv2.VideoCapture(src_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS) or 24
    print(f"  {os.path.basename(src_path)}: {total} 帧, hue={hue_range}")

    frames_p = []
    t = 0.0
    frame_idx = 0
    target_interval = 1.0 / SAMPLE_FPS
    src_h, src_w = None, None

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        if src_h is None:
            src_h, src_w = frame.shape[:2]
        cur_t = frame_idx / fps
        if abs(cur_t - t) < target_interval * 0.5 or frame_idx == 0:
            rgba = chroma_key_remove_narrow(frame, hue_range)
            alpha = rgba[:, :, 3]
            alpha, _ = remove_isolated_disconnected_v2(alpha)
            rgba[:, :, 3] = alpha
            scale = OUT_SIZE / src_h
            new_w = max(1, int(round(src_w * scale)))
            resized = cv2.resize(rgba, (new_w, OUT_SIZE), interpolation=cv2.INTER_LANCZOS4)
            canvas = np.zeros((OUT_SIZE, OUT_SIZE, 4), dtype=np.uint8)
            x0 = (OUT_SIZE - new_w) // 2
            canvas[:, x0:x0 + new_w] = resized
            img = Image.fromarray(canvas, mode="RGBA")
            frames_p.append(rgba_to_gif_frames(img, ALPHA_THRESHOLD))
            t += target_interval
        frame_idx += 1
        if frame_idx >= total:
            break

    cap.release()
    if not frames_p:
        print("  [警告] 无帧产出")
        return

    duration_ms = max(10, round(1000 / SAMPLE_FPS / 10) * 10)
    frames_p[0].save(
        out_gif_path, save_all=True, append_images=frames_p[1:],
        duration=duration_ms, loop=0, transparency=0, disposal=2, optimize=True,
    )
    size_kb = os.path.getsize(out_gif_path) / 1024
    print(f"  -> {os.path.basename(out_gif_path)} ({size_kb:.1f} KB, {len(frames_p)} 帧)")


def main():
    base = r"C:\Users\13544\AppData\Roaming\WPS 灵犀\paste"
    out_root = r"D:\TOOL\20260831-14-46-47-666\lingxi-pet\_build4"
    jobs = [
        ("梦璃_20260831_165425_cdf44267.mp4", "mengli"),
        ("紫英_20260831_165425_a6fd9aa4.mp4", "ziying"),
        ("菱纱_20260831_165425_80bb1170.mp4", "lingsha"),
        ("天河_20260831_165425_222d101e.mp4", "tianhe"),
    ]
    for src_name, action_id in jobs:
        src = os.path.join(base, src_name)
        out_dir = os.path.join(out_root, action_id)
        os.makedirs(out_dir, exist_ok=True)
        out_gif = os.path.join(out_dir, f"{action_id}.gif")
        print(f"[{action_id}] {src_name}")
        process_video(src, out_gif, VIDEO_PARAMS[action_id])
    print("全部处理完成")


if __name__ == "__main__":
    main()
