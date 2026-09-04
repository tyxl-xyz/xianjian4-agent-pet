#!/usr/bin/env python3
"""
GIF 精灵图集生成器
==================
将一个或多个透明背景 GIF 合并为精灵图（spritesheet），输出 lossless WebP。
支持水平联合边界裁剪、垂直逐帧裁剪、统一缩放、底部对齐。
自动处理 WebP 16383px 宽度限制：超限时主交付为完整 PNG（供 build_pet_json
拷入 user/）；可选写入 _partN.webp 仅作工作区调试，不进 patch。

依赖：
    pip install Pillow numpy

CLI 用法：
    python make_spritesheet.py -o _build/happy --names idle_to_happy,happy,happy_to_idle a.gif b.gif c.gif
    # 未传 --prefix 时用 -o 目录名（happy.webp）；多批次切勿共用默认 sprite
    python make_spritesheet.py -o out/ --prefix idle --names idle idle.gif

Agent 用法（作为模块导入）：
    from make_spritesheet import make_spritesheet
    make_spritesheet(
        sources=[("idle", "idle.gif"), ("walk", "walk.gif")],
        output_dir="sprite_output/",
        name_prefix="cat",
        frame_size=720,
        fps=24,
    )
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageSequence

# 贴齐 generate_video 720p / chroma 默认输出；桌面逻辑显示由 displayWidth=128 控制
DEFAULT_FRAME_SIZE = 720
# libwebp / WebP FAQ：宽高均不得超过 16383
WEBP_MAX_DIMENSION = 16383

# -o 目录名过泛时，改用 --names 推断前缀，避免多批都落成 sprite.webp
_WEAK_OUTPUT_DIR_NAMES = frozenset(
    {
        "",
        ".",
        "..",
        "output",
        "out",
        "sprite_output",
        "sprites",
        "build",
        "_build",
        "tmp",
        "temp",
        "workdir",
        "workspace",
    }
)


def derive_prefix_from_names(names: list[str]) -> str | None:
    """从行名推断合图前缀：三段往返取中段 atomic，单行取该名。"""
    cleaned = [n.strip().replace("-", "_") for n in names if n and n.strip()]
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 3:
        mid = cleaned[1]
        left, right = cleaned[0], cleaned[2]
        if left.endswith(f"_to_{mid}") or right.startswith(f"{mid}_to_"):
            return mid
    return None


def derive_cli_prefix(
    output_dir: str,
    names: list[str],
    explicit: str | None,
) -> str:
    """
    CLI 未传 --prefix 时：优先用 -o 目录名（如 _build/happy → happy），
    目录名过泛则用 --names 推断，最后才回退 sprite（并告警）。
    """
    if explicit:
        return explicit
    base = Path(output_dir).resolve().name
    if base.lower() not in _WEAK_OUTPUT_DIR_NAMES and not base.startswith("."):
        safe = re.sub(r"[^\w\-]+", "_", base).strip("_")
        if safe:
            return safe
    from_names = derive_prefix_from_names(names)
    if from_names:
        return from_names
    print(
        "[警告] 未能推断合图 --prefix，回退为 sprite；"
        "多批次写入同一 user/ 时会撞名，请显式传入 --prefix <批次名>",
        file=sys.stderr,
    )
    return "sprite"


def sharpen_rgba(image: Image.Image) -> Image.Image:
    """轻微锐化 RGBA 图像，保留原始 alpha 通道。"""
    alpha = image.getchannel("A")
    rgb = Image.new("RGB", image.size, (0, 0, 0))
    rgb.paste(image.convert("RGB"), mask=alpha)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=0.6, percent=120, threshold=2))
    result = rgb.convert("RGBA")
    result.putalpha(alpha)
    return result


def get_union_left_right(frames: list[Image.Image]) -> tuple[int, int]:
    """计算所有帧的 alpha 边界左/右并集，防止水平跳动。"""
    left = frames[0].width
    right = 0
    for frame in frames:
        bbox = frame.getchannel("A").getbbox()
        if bbox is None:
            continue
        left = min(left, bbox[0])
        right = max(right, bbox[2])
    if right <= left:
        return 0, frames[0].width
    return left, right


def read_smart_frames(
    path: str,
    frame_size: int = DEFAULT_FRAME_SIZE,
    padding: int = 2,
) -> tuple[list[Image.Image], int, int]:
    """
    读取 GIF 并生成精灵帧：
    1. 水平联合边界（所有帧 left/right 并集）
    2. 垂直逐帧裁剪（每帧按自身 alpha 边界）
    3. 统一缩放（min(scale_h, scale_w)，防止宽帧截断）
    4. 底部对齐
    """
    image = Image.open(path)
    raw_frames = []
    durations = []
    for frame in ImageSequence.Iterator(image):
        raw_frames.append(frame.copy().convert("RGBA"))
        durations.append(max(10, int(frame.info.get("duration") or 100)))

    union_left, union_right = get_union_left_right(raw_frames)
    max_size = frame_size - padding * 2

    cropped_list = []
    max_crop_h = 0
    crop_w = union_right - union_left
    for frame in raw_frames:
        abbox = frame.getchannel("A").getbbox()
        if abbox is None:
            cropped_list.append(None)
            continue
        crop_box = (union_left, abbox[1], union_right, abbox[3])
        cf = frame.crop(crop_box)
        cropped_list.append(cf)
        max_crop_h = max(max_crop_h, cf.height)

    if max_crop_h == 0:
        max_crop_h = 1

    scale_h = max_size / max_crop_h
    scale_w = max_size / crop_w
    scale = min(scale_h, scale_w)

    result_frames = []
    for cf in cropped_list:
        if cf is None:
            result_frames.append(Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0)))
            continue
        new_w = max(1, int(round(cf.width * scale)))
        new_h = max(1, int(round(cf.height * scale)))
        resized = cf.resize((new_w, new_h), Image.Resampling.LANCZOS)
        resized = sharpen_rgba(resized)
        canvas = Image.new("RGBA", (frame_size, frame_size), (0, 0, 0, 0))
        x = (frame_size - resized.width) // 2
        y = frame_size - resized.height - padding
        canvas.alpha_composite(resized, (x, y))
        result_frames.append(canvas)

    total_ms = sum(durations)
    return result_frames, total_ms, len(raw_frames)


def checkerboard(size: tuple[int, int], cell: int = 16) -> Image.Image:
    """生成棋盘格背景。"""
    image = Image.new("RGBA", size, (245, 245, 245, 255))
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], cell):
        for x in range(0, size[0], cell):
            if (x // cell + y // cell) % 2:
                draw.rectangle((x, y, x + cell - 1, y + cell - 1), fill=(220, 220, 220, 255))
    return image


def make_spritesheet(
    sources: list[tuple[str, str]],
    output_dir: str,
    name_prefix: str = "sprite",
    frame_size: int = DEFAULT_FRAME_SIZE,
    fps: int = 24,
    padding: int = 2,
) -> dict:
    """
    Agent 友好接口：从多个 GIF 生成精灵图集。

    参数：
        sources     : [("row_name", "path/to/gif"), ...]
        output_dir   : 输出目录
        name_prefix  : 输出文件前缀（sprite.webp, sprite_contactsheet.png, ...）
        frame_size   : 每帧尺寸（正方形），默认 720（高清格；显示尺寸见 build_pet_json）
        fps          : 元数据中记录的帧率
        padding      : 帧内边距

    返回：
        {"sprite": path, "contactsheet": path, "manifest": path, "rows": [...]}
    """
    os.makedirs(output_dir, exist_ok=True)

    rows = []
    metadata = {
        # sprite / spritesheet 在写出前按实际主文件（.webp 或超限 .png）回填
        "frame_width": frame_size,
        "frame_height": frame_size,
        "fps": fps,
        "rows": [],
        "notes": (
            "Union left/right + per-frame top/bottom + uniform scale (min) + bottom-aligned."
        ),
    }

    for row_index, (name, path) in enumerate(sources):
        frames, total_ms, source_frames = read_smart_frames(path, frame_size, padding)
        rows.append((name, frames))
        metadata["rows"].append({
            "name": name,
            "row": row_index,
            "x": 0,
            "y": row_index * frame_size,
            "frames": len(frames),
            "source_frames": source_frames,
            "duration_ms": round(total_ms),
        })

    max_cols = max(len(frames) for _, frames in rows)
    sprite = Image.new("RGBA", (max_cols * frame_size, len(rows) * frame_size), (0, 0, 0, 0))

    for row_index, (_, frames) in enumerate(rows):
        for col_index, frame in enumerate(frames):
            sprite.alpha_composite(frame, (col_index * frame_size, row_index * frame_size))

    # 保存精灵图（处理 WebP 16383px 限制）
    # 超限：主交付 = 完整 PNG（manifest.sprite 必须指向它）；_part* 仅工作区调试
    oversized = sprite.width > WEBP_MAX_DIMENSION or sprite.height > WEBP_MAX_DIMENSION
    part_paths: list[str] = []
    if oversized:
        if frame_size > 0 and sprite.width > WEBP_MAX_DIMENSION:
            chunk_cols = max(1, WEBP_MAX_DIMENSION // frame_size)
            chunk_size = chunk_cols * frame_size
            for ci, x_start in enumerate(range(0, sprite.width, chunk_size)):
                x_end = min(x_start + chunk_size, sprite.width)
                chunk = sprite.crop((x_start, 0, x_end, sprite.height))
                chunk_path = os.path.join(output_dir, f"{name_prefix}_part{ci}.webp")
                chunk.save(chunk_path, "WEBP", lossless=True, quality=100, method=6)
                part_paths.append(chunk_path)
                print(f"  (调试分块 {ci}: {chunk_path})")
        png_path = os.path.join(output_dir, f"{name_prefix}.png")
        sprite.save(png_path, "PNG")
        sprite_path = png_path
        sprite_basename = f"{name_prefix}.png"
        print(
            f"  [WebP超限] {sprite.width}x{sprite.height} > {WEBP_MAX_DIMENSION}："
            f"主交付 {sprite_basename}（勿把 _part* 写入 user/）",
        )
    else:
        sprite_path = os.path.join(output_dir, f"{name_prefix}.webp")
        sprite.save(sprite_path, "WEBP", lossless=True, quality=100, method=6)
        sprite_basename = f"{name_prefix}.webp"

    # 生成联系表
    label_width = 150
    header_height = 34
    contact = checkerboard((label_width + sprite.width, header_height + sprite.height))
    draw = ImageDraw.Draw(contact)
    font = ImageFont.load_default()
    fmt_label = "PNG (WebP超限)" if oversized else "lossless WebP"
    draw.rectangle((0, 0, contact.width, header_height), fill=(28, 28, 28, 255))
    draw.text((label_width + 8, 10),
              f"{frame_size}x{frame_size} | {fps} fps | {max_cols} cols | {fmt_label}",
              fill=(255, 255, 255, 255), font=font)

    for row_index, (name, frames) in enumerate(rows):
        y = header_height + row_index * frame_size
        draw.rectangle((0, y, label_width - 1, y + frame_size - 1), fill=(34, 34, 34, 255))
        draw.text((10, y + 44), name, fill=(255, 255, 255, 255), font=font)
        draw.text((10, y + 62), f"{len(frames)} frames", fill=(190, 190, 190, 255), font=font)
        draw.line((label_width, y, contact.width, y), fill=(80, 80, 80, 255))
        for col_index, frame in enumerate(frames):
            x = label_width + col_index * frame_size
            contact.alpha_composite(frame, (x, y))
            draw.rectangle((x, y, x + frame_size - 1, y + frame_size - 1), outline=(125, 125, 125, 150))

    contact_path = os.path.join(output_dir, f"{name_prefix}_contactsheet.png")
    contact.convert("RGB").save(contact_path, "PNG")

    # 保存元数据（sprite / spritesheet 必须与真实主文件一致，供 build_pet_json 拷贝）
    metadata["sprite"] = sprite_basename
    metadata["spritesheet"] = sprite_basename
    metadata["columns"] = max_cols
    metadata["width"] = sprite.width
    metadata["height"] = sprite.height
    metadata["oversized_webp"] = oversized
    metadata["format"] = "png" if oversized else "webp"
    if part_paths:
        metadata["debug_parts"] = [os.path.basename(p) for p in part_paths]
    metadata["contactsheet"] = os.path.basename(contact_path)
    manifest_path = os.path.join(output_dir, f"{name_prefix}_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, ensure_ascii=False, indent=2)

    print(f"sprite      = {sprite_path}")
    print(f"contactsheet= {contact_path}")
    print(f"manifest    = {manifest_path}")

    return {
        "sprite": sprite_path,
        "contactsheet": contact_path,
        "manifest": manifest_path,
        "rows": metadata["rows"],
        "oversized_webp": oversized,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="GIF 精灵图集生成器")
    parser.add_argument("inputs", nargs="+", help="输入 GIF 文件路径")
    parser.add_argument("-o", "--output", required=True, help="输出目录")
    parser.add_argument("--names", type=str, default=None,
                        help="行名称（逗号分隔），如 'idle_to_happy,happy,happy_to_idle'")
    parser.add_argument(
        "--prefix",
        type=str,
        default=None,
        help="输出文件前缀（默认：-o 目录名，其次按 --names 推断；勿多批次共用 sprite）",
    )
    parser.add_argument(
        "--frame-size",
        type=int,
        default=DEFAULT_FRAME_SIZE,
        help=f"帧尺寸（正方形，默认 {DEFAULT_FRAME_SIZE}）",
    )
    parser.add_argument("--fps", type=int, default=24, help="元数据帧率")
    parser.add_argument("--padding", type=int, default=2, help="帧内边距")

    args = parser.parse_args()

    names = args.names.split(",") if args.names else [Path(p).stem for p in args.inputs]
    if len(names) != len(args.inputs):
        print(f"[错误] 名称数量 ({len(names)}) 与输入文件数量 ({len(args.inputs)}) 不匹配")
        sys.exit(1)

    prefix = derive_cli_prefix(args.output, names, args.prefix)
    sources = list(zip(names, args.inputs))
    make_spritesheet(
        sources=sources,
        output_dir=args.output,
        name_prefix=prefix,
        frame_size=args.frame_size,
        fps=args.fps,
        padding=args.padding,
    )

if __name__ == "__main__":
    main()
