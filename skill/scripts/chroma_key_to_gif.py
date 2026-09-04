#!/usr/bin/env python3
"""
HSV 色键去绿幕 + 分段导出 GIF
================================
将绿幕视频按时间段拆分为多段透明背景 GIF。
支持 CLI 调用，也可被 agent 作为模块导入。

依赖：
    pip install moviepy opencv-python Pillow numpy

    CLI 用法：
    # 单段导出
    python chroma_key_to_gif.py input.mp4 -o output.gif

    # 多段导出
    python chroma_key_to_gif.py input.mp4 --segments 0:2,2:6.5,11:15 -o phase1.gif phase2.gif phase3.gif

    # 自定义绿幕颜色（蓝色幕布）
    python chroma_key_to_gif.py input.mp4 --hue 200-260 -o output.gif

Agent 用法（作为模块导入）：
    from chroma_key_to_gif import chroma_key_video_to_gifs
    chroma_key_video_to_gifs("video.mp4", [
        {"name": "phase1", "start": 0, "end": 3},
        {"name": "phase2", "start": 3, "end": 7},
    ], output_dir="gifs/")
"""

import argparse
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageFilter

# ═══════════════════════════════════════════════════════════════════════════════
#  默认参数
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_HUE_RANGE = (35, 85)       # 绿幕色相范围（度）
DEFAULT_SAT_MIN = 80               # 最小饱和度
DEFAULT_VAL_MIN = 80               # 最小明度
DEFAULT_BLUR_RADIUS = 5            # 边缘羽化模糊半径（奇数）
DEFAULT_MORPH_ITER = 2             # 形态学迭代次数
# 对「背景绿 mask」膨胀：把边缘绿溢像素划入透明区（切绿边）
# HARD：mask=255 表示背景；切绿边必须 dilate，禁止 erode（erode 会把绿边包进角色）
DEFAULT_DESPILL_DILATE_ITER = 2
DEFAULT_OUTPUT_SIZE = 720          # 输出尺寸（像素，正方形；贴齐 720p 源，避免合图前先压分辨率）
DEFAULT_OUTPUT_FPS = 24            # 输出帧率（保留原始帧率）
DEFAULT_ALPHA_THRESHOLD = 100      # GIF 二值化 alpha 阈值 (0-255)

# 旧名兼容（曾误用 erode 切绿边）
DEFAULT_ERODE_ITER = DEFAULT_DESPILL_DILATE_ITER


# ═══════════════════════════════════════════════════════════════════════════════
#  核心函数
# ═══════════════════════════════════════════════════════════════════════════════

def chroma_key_remove(img_rgb: np.ndarray,
                      hue_range: tuple[int, int] = DEFAULT_HUE_RANGE,
                      sat_min: int = DEFAULT_SAT_MIN,
                      val_min: int = DEFAULT_VAL_MIN,
                      blur_radius: int = DEFAULT_BLUR_RADIUS,
                      morph_iter: int = DEFAULT_MORPH_ITER,
                      despill_dilate_iter: int = DEFAULT_DESPILL_DILATE_ITER,
                      erode_iter: int | None = None) -> np.ndarray:
    """
    基于 HSV 色键去除纯色背景。

    参数：
        img_rgb      : RGB 格式的 numpy 数组 (H, W, 3)
        hue_range    : 背景色相范围 (min, max)，单位度（OpenCV H：0–179）
        sat_min      : 最小饱和度阈值
        val_min      : 最小明度阈值
        blur_radius  : 边缘羽化高斯模糊半径（建议奇数）
        morph_iter   : 形态学开/闭运算迭代次数
        despill_dilate_iter : 对背景 mask 膨胀次数（切绿边；默认 2）
        erode_iter   : 已废弃别名；若传入则覆盖 despill_dilate_iter（语义已改为 dilate）

    返回：
        RGBA 格式的 numpy 数组 (H, W, 4)
    """
    if erode_iter is not None:
        despill_dilate_iter = erode_iter

    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)

    lower = np.array([hue_range[0], sat_min, val_min])
    upper = np.array([hue_range[1], 255, 255])
    # mask: 255 = 背景（幕布色），0 = 前景（角色）
    mask = cv2.inRange(hsv, lower, upper)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=morph_iter)

    # 膨胀背景 mask：边缘绿溢划入透明区。禁止 erode——会把绿边包进角色。
    if despill_dilate_iter > 0:
        mask = cv2.dilate(mask, kernel, iterations=despill_dilate_iter)

    mask_float = mask.astype(np.float32) / 255.0
    mask_blurred = cv2.GaussianBlur(mask_float, (blur_radius, blur_radius), 0)

    alpha = ((1.0 - mask_blurred) * 255).clip(0, 255).astype(np.uint8)

    rgba = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2RGBA)
    rgba[:, :, 3] = alpha
    return rgba


def rgba_to_gif_frames(rgba_image: Image.Image,
                       alpha_threshold: int = DEFAULT_ALPHA_THRESHOLD) -> Image.Image:
    """
    将 RGBA 图像转换为 GIF 兼容的 P 模式图像。

    GIF 只支持二值透明度。策略（最稳妥）：
    1. alpha 高斯模糊后按阈值二值化，减少锯齿
    2. 透明区 RGB 预填黑，避免绿边残色占用调色板
    3. 不透明像素量化到最多 255 色，再整体 +1，腾出 index 0
    4. index 0 专留透明色 RGB(0,0,0)；保存时配合 transparency=0

    这样不会出现 ADAPTIVE 把透明区黑像素散落到非 0 索引、导致背景变实心黑的问题，
    也不会把角色身上的纯黑不透明像素误标为透明。
    """
    rgba = rgba_image.convert("RGBA")
    r, g, b, a = rgba.split()
    a_blur = a.filter(ImageFilter.GaussianBlur(radius=1))
    a_arr = np.asarray(a_blur)
    opaque = a_arr > alpha_threshold

    rgb = np.stack(
        [np.asarray(r), np.asarray(g), np.asarray(b)],
        axis=-1,
    ).copy()
    rgb[~opaque] = (0, 0, 0)
    rgb_img = Image.fromarray(rgb, mode="RGB")

    # 量化到 255 色（暂用 index 0–254），随后整体平移腾出 index 0
    img_p = rgb_img.convert("P", palette=Image.ADAPTIVE, colors=255)
    src_pal = img_p.getpalette() or []
    pixels = np.asarray(img_p, dtype=np.uint16)

    out = np.zeros(pixels.shape, dtype=np.uint8)
    if opaque.any():
        # clip 防御极端情况下 palette 长度异常
        out[opaque] = np.clip(pixels[opaque] + 1, 1, 255).astype(np.uint8)

    new_pal = [0, 0, 0]  # index 0：透明色
    new_pal.extend(src_pal[: 255 * 3])
    while len(new_pal) < 768:
        new_pal.append(0)

    result = Image.fromarray(out, mode="P")
    result.putpalette(new_pal[:768])
    return result


def extract_gif(video_path: str, start: float, end: float,
                output_path: str,
                sample_fps: float = DEFAULT_OUTPUT_FPS,
                target_size: int = DEFAULT_OUTPUT_SIZE,
                hue_range: tuple[int, int] = DEFAULT_HUE_RANGE,
                sat_min: int = DEFAULT_SAT_MIN,
                val_min: int = DEFAULT_VAL_MIN,
                blur_radius: int = DEFAULT_BLUR_RADIUS,
                morph_iter: int = DEFAULT_MORPH_ITER,
                despill_dilate_iter: int = DEFAULT_DESPILL_DILATE_ITER,
                erode_iter: int | None = None,
                alpha_threshold: int = DEFAULT_ALPHA_THRESHOLD):
    """从视频中提取一个片段，去绿幕后导出为 GIF。"""
    if erode_iter is not None:
        despill_dilate_iter = erode_iter
    from moviepy import VideoFileClip

    clip = VideoFileClip(video_path)
    # GIF89a delay 精度为 10ms；显式量化，避免 int(41.6)=41 再被 PIL 存成 40 的隐性偏差
    duration_ms = max(10, round(1000 / sample_fps / 10) * 10)
    frame_interval = 1.0 / sample_fps

    palette_frames = []
    t = start
    while t < end:
        frame = clip.get_frame(t)
        rgba = chroma_key_remove(frame,
                                hue_range=hue_range,
                                sat_min=sat_min,
                                val_min=val_min,
                                blur_radius=blur_radius,
                                morph_iter=morph_iter,
                                despill_dilate_iter=despill_dilate_iter)
        img = Image.fromarray(rgba).resize((target_size, target_size), Image.LANCZOS)
        palette_frames.append(rgba_to_gif_frames(img, alpha_threshold))
        t += frame_interval

    clip.close()

    if not palette_frames:
        print(f"  [警告] {start}s~{end}s 内未提取到任何帧")
        return

    palette_frames[0].save(
        output_path,
        save_all=True,
        append_images=palette_frames[1:],
        duration=duration_ms,
        loop=0,
        transparency=0,
        disposal=2,
        optimize=True,
    )

    size_kb = os.path.getsize(output_path) / 1024
    print(f"  -> {os.path.basename(output_path)}  ({size_kb:.1f} KB, {len(palette_frames)} 帧, {end - start:.1f}s)")


def chroma_key_video_to_gifs(
    video_path: str,
    segments: list[dict],
    output_dir: str,
    sample_fps: float = DEFAULT_OUTPUT_FPS,
    target_size: int = DEFAULT_OUTPUT_SIZE,
    hue_range: tuple[int, int] = DEFAULT_HUE_RANGE,
    sat_min: int = DEFAULT_SAT_MIN,
    val_min: int = DEFAULT_VAL_MIN,
    blur_radius: int = DEFAULT_BLUR_RADIUS,
    morph_iter: int = DEFAULT_MORPH_ITER,
    despill_dilate_iter: int = DEFAULT_DESPILL_DILATE_ITER,
    erode_iter: int | None = None,
    alpha_threshold: int = DEFAULT_ALPHA_THRESHOLD,
) -> list[str]:
    """
    Agent 友好接口：一次性将视频按多段去绿幕导出为 GIF。

    参数：
        video_path   : 输入视频路径
        segments     : 分段列表，每项 {"name": str, "start": float, "end": float}
        output_dir   : 输出目录
        其余参数同 extract_gif

    返回：
        生成的 GIF 文件路径列表
    """
    if erode_iter is not None:
        despill_dilate_iter = erode_iter
    os.makedirs(output_dir, exist_ok=True)
    results = []

    for seg in segments:
        out_path = os.path.join(output_dir, f"{seg['name']}.gif")
        extract_gif(
            video_path=video_path,
            start=seg["start"],
            end=seg["end"],
            output_path=out_path,
            sample_fps=sample_fps,
            target_size=target_size,
            hue_range=hue_range,
            sat_min=sat_min,
            val_min=val_min,
            blur_radius=blur_radius,
            morph_iter=morph_iter,
            despill_dilate_iter=despill_dilate_iter,
            alpha_threshold=alpha_threshold,
        )
        results.append(out_path)

    return results


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def parse_hue_range(text: str) -> tuple[int, int]:
    parts = text.replace(":", "-").split("-")
    if len(parts) != 2:
        raise ValueError(f"色相范围格式错误: {text}，应为 'min-max'，如 '35-85'")
    return int(parts[0]), int(parts[1])

def parse_segments(text: str) -> list[tuple[float, float]]:
    segments = []
    for part in text.split(","):
        pair = part.strip().split(":")
        if len(pair) != 2:
            raise ValueError(f"分段格式错误: '{part}'，应为 'start:end'，如 '0:2'")
        segments.append((float(pair[0]), float(pair[1])))
    return segments

def main():
    parser = argparse.ArgumentParser(
        description="HSV 色键去绿幕 + 分段导出 GIF",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("input", help="输入视频路径")
    parser.add_argument("-o", "--output", nargs="+", required=True, help="输出 GIF 路径")
    parser.add_argument("--segments", type=str, default=None, help="时间段: '0:2,2:6.5,11:15'")
    parser.add_argument("--hue", type=str, default=None, help="色相范围 'min-max'（OpenCV H 0–179）")
    parser.add_argument("--sat", type=int, default=DEFAULT_SAT_MIN)
    parser.add_argument("--val", type=int, default=DEFAULT_VAL_MIN)
    parser.add_argument("--blur", type=int, default=DEFAULT_BLUR_RADIUS)
    parser.add_argument(
        "--dilate",
        type=int,
        default=DEFAULT_DESPILL_DILATE_ITER,
        help="背景 mask 膨胀次数，用于切绿边（默认 2；0=关闭）",
    )
    parser.add_argument("--size", type=int, default=DEFAULT_OUTPUT_SIZE)
    parser.add_argument("--fps", type=float, default=DEFAULT_OUTPUT_FPS)
    parser.add_argument("--alpha-threshold", type=int, default=DEFAULT_ALPHA_THRESHOLD)

    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[错误] 视频文件不存在: {args.input}")
        sys.exit(1)

    hue_range = parse_hue_range(args.hue) if args.hue else DEFAULT_HUE_RANGE

    if args.segments:
        segments = parse_segments(args.segments)
        if len(segments) != len(args.output):
            print(f"[错误] 分段数量 ({len(segments)}) 与输出文件数量 ({len(args.output)}) 不匹配")
            sys.exit(1)
    else:
        if len(args.output) != 1:
            print("[错误] 未指定 --segments 时只能提供 1 个输出文件")
            sys.exit(1)
        from moviepy import VideoFileClip

        clip = VideoFileClip(args.input)
        segments = [(0, clip.duration)]
        clip.close()

    for i, ((start, end), out_path) in enumerate(zip(segments, args.output)):
        print(f"[分段 {i + 1}: {start}s ~ {end}s]")
        extract_gif(
            video_path=args.input, start=start, end=end, output_path=out_path,
            sample_fps=args.fps, target_size=args.size,
            hue_range=hue_range, sat_min=args.sat, val_min=args.val,
            blur_radius=args.blur, despill_dilate_iter=args.dilate,
            alpha_threshold=args.alpha_threshold,
        )

    print("\n完成！")

if __name__ == "__main__":
    main()
