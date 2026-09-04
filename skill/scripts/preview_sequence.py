#!/usr/bin/env python3
"""
组合动作 GIF 预览
==================
从 pet.json 读取 sequence 定义 + spritesheet 合图，按 enter→hold→leave→onComplete
逐帧提取并输出透明背景 GIF。

支持：
  - action 定义层 playRange + 步骤级 playRange 覆盖
  - spriteFlip / hold.flip 水平镜像
  - hold duration 模式（clip / once / fixed）→ 自动计算循环次数
  - 多 group 顺序拼接
  - onComplete 中 action 步骤（`{ action }` 单对象或旧版数组；跳过 move / hide 等非动画步骤）
  - 多源合并（runtime + patch）

依赖：
    pip install Pillow

CLI：
    # 列出可用 sequences
    python preview_sequence.py --pet runtime/pet.json --list

    # 预览单个 sequence
    python preview_sequence.py --pet runtime/pet.json --sequence happy_play

    # 指定输出路径和 hold 循环次数
    python preview_sequence.py --pet runtime/pet.json --sequence happy_play \
        --output preview.gif --hold-loops 3

    # 合并 patch（user/pet.patch.json 覆盖 runtime/pet.json）
    python preview_sequence.py --pet runtime/pet.json \
        --merge user/pet.patch.json --sequence happy_play

Agent 调用：
    from preview_sequence import preview_sequence_gif
    preview_sequence_gif(
        pet_json_path="runtime/pet.json",
        sequence_id="happy_play",
        output_path="happy_play.gif",
    )
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

from PIL import Image, ImageOps


def resolve_play_range(
    play_range: Optional[list], total_frames: int
) -> list[int]:
    """将 playRange 归一化为帧索引列表"""
    if not play_range or len(play_range) == 0:
        return list(range(total_frames))
    if isinstance(play_range[0], int):
        fr, to = play_range[0], play_range[1]
        return list(range(fr, to + 1))
    indices = []
    for segment in play_range:
        fr, to = segment[0], segment[1]
        indices.extend(range(fr, to + 1))
    return indices


def normalize_end_action_steps(end_value) -> list[dict]:
    """兼容 onComplete/onInterrupt：当前 `{ action }` 单对象与旧版 `[{ action }]` 数组。"""
    if not end_value:
        return []
    if isinstance(end_value, dict):
        if "action" in end_value:
            return [end_value]
        if end_value.get("op") == "playSequence" and end_value.get("id"):
            return [{"action": end_value["id"]}]
        return []
    if isinstance(end_value, list):
        steps = []
        for step in end_value:
            if not isinstance(step, dict):
                continue
            if "action" in step and "op" not in step:
                steps.append(step)
            elif step.get("op") == "playSequence" and step.get("id"):
                steps.append({"action": step["id"]})
        return steps
    return []


def extract_frames(
    img: Image.Image,
    frames: int,
    columns: int,
    cell_w: int,
    cell_h: int,
    row_offset: int = 0,
    frame_indices: Optional[list[int]] = None,
    flip: bool = False,
) -> list[Image.Image]:
    """从合图中按帧索引提取帧列表"""
    if frame_indices is None:
        frame_indices = list(range(frames))

    result = []
    cols = max(1, columns)
    for idx in frame_indices:
        col = idx % cols
        local_row = idx // cols
        x = col * cell_w
        y = (row_offset + local_row) * cell_h
        frame = img.crop((x, y, x + cell_w, y + cell_h))
        if flip:
            frame = ImageOps.mirror(frame)
        result.append(frame.convert("RGBA"))
    return result


def load_action_frames(
    action_def: dict,
    sprites_dir: str,
    step_play_range: Optional[list] = None,
    flip: bool = False,
    _img_cache: Optional[dict] = None,
) -> tuple[list[Image.Image], int]:
    """
    加载一个 action 的帧列表。
    返回 (frames, fps)。
    step_play_range 覆盖 action 定义层的 playRange。
    """
    if _img_cache is None:
        _img_cache = {}

    sheet_name = action_def["spritesheet"]
    sheet_path = os.path.join(sprites_dir, sheet_name)

    if not os.path.isfile(sheet_path):
        alt_dirs = [sprites_dir]
        parent = os.path.dirname(sprites_dir)
        for sub in ["official", "user", "runtime"]:
            alt_dirs.append(os.path.join(parent, sub))
        for d in alt_dirs:
            p = os.path.join(d, sheet_name)
            if os.path.isfile(p):
                sheet_path = p
                break

    if sheet_path not in _img_cache:
        if not os.path.isfile(sheet_path):
            print(f"  [WARN] 合图不存在: {sheet_path}", file=sys.stderr)
            return [], action_def.get("fps", 24)
        _img_cache[sheet_path] = Image.open(sheet_path).convert("RGBA")

    img = _img_cache[sheet_path]

    total_frames = action_def.get("frames", 1)
    columns = action_def.get("columns", total_frames)
    cell_w = action_def.get("cellWidth", img.width // max(1, columns))
    cell_h = action_def.get("cellHeight", cell_w)
    row_offset = action_def.get("row", 0)
    fps = action_def.get("fps", 24)

    action_play_range = action_def.get("playRange")
    effective_range = step_play_range if step_play_range is not None else action_play_range

    frame_indices = resolve_play_range(effective_range, total_frames)
    sprite_flip = action_def.get("spriteFlip", False)
    actual_flip = flip ^ sprite_flip

    return extract_frames(
        img, total_frames, columns, cell_w, cell_h,
        row_offset, frame_indices, actual_flip,
    ), fps


def resolve_action_def(
    action_id: str, actions: dict
) -> Optional[dict]:
    """从 actions.atomic / actions.transition 中查找 action 定义"""
    if action_id == "__hold_none__":
        return None
    atomic = actions.get("atomic", {})
    transition = actions.get("transition", {})
    return atomic.get(action_id) or transition.get(action_id)


def compute_hold_loops(hold: dict, fps: int, effective_frame_count: int) -> int:
    """根据 duration 模式计算 hold 应循环多少次"""
    duration = hold.get("duration", {})
    mode = duration.get("mode", "clip")

    if mode == "once":
        return 1
    elif mode == "fixed":
        sec = duration.get("sec", 5)
        if effective_frame_count <= 0 or fps <= 0:
            return 1
        frames_needed = sec * fps
        return max(1, round(frames_needed / effective_frame_count))
    elif mode == "untilMoveDone":
        return 2
    else:  # clip
        return 2


def build_sequence_frames(
    sequence_def: dict,
    actions: dict,
    sprites_dir: str,
    hold_loops_override: Optional[int] = None,
    include_on_complete: bool = True,
) -> tuple[list[Image.Image], list[tuple[int, int]]]:
    """
    构建 sequence 的完整帧列表。
    返回 (frames, fps_segments) — fps_segments 为 [(frame_count, fps), ...]
    """
    all_frames: list[Image.Image] = []
    fps_segments: list[tuple[int, int]] = []
    img_cache: dict = {}

    groups = sequence_def.get("groups", [])

    for gi, group in enumerate(groups):
        group_fps_scale = group.get("playbackFpsScale", 1.0)

        # --- enter ---
        enter_steps = group.get("enter", [])
        enter_fps_scale = group.get("enterPlaybackFpsScale", group_fps_scale)
        for step in enter_steps:
            action_id = step.get("action", "")
            action_def = resolve_action_def(action_id, actions)
            if not action_def:
                continue
            step_range = step.get("playRange")
            frames, fps = load_action_frames(
                action_def, sprites_dir, step_range, _img_cache=img_cache
            )
            if frames:
                scaled_fps = max(1, round(fps * enter_fps_scale))
                all_frames.extend(frames)
                fps_segments.append((len(frames), scaled_fps))

        # --- hold ---
        hold = group.get("hold", {})
        hold_action_id = hold.get("action", "")
        hold_flip = hold.get("flip", False)
        hold_fps_scale = group.get("holdPlaybackFpsScale", group_fps_scale)
        hold_action_def = resolve_action_def(hold_action_id, actions)

        if hold_action_def:
            step_range = hold.get("playRange")
            frames, fps = load_action_frames(
                hold_action_def, sprites_dir, step_range,
                flip=hold_flip, _img_cache=img_cache,
            )
            if frames:
                if hold_loops_override is not None:
                    loops = hold_loops_override
                else:
                    loops = compute_hold_loops(hold, fps, len(frames))
                scaled_fps = max(1, round(fps * hold_fps_scale))
                looped = frames * loops
                all_frames.extend(looped)
                fps_segments.append((len(looped), scaled_fps))

        # --- leave ---
        leave_steps = group.get("leave", [])
        leave_fps_scale = group.get("leavePlaybackFpsScale", group_fps_scale)
        for step in leave_steps:
            action_id = step.get("action", "")
            action_def = resolve_action_def(action_id, actions)
            if not action_def:
                continue
            step_range = step.get("playRange")
            frames, fps = load_action_frames(
                action_def, sprites_dir, step_range, _img_cache=img_cache
            )
            if frames:
                scaled_fps = max(1, round(fps * leave_fps_scale))
                all_frames.extend(frames)
                fps_segments.append((len(frames), scaled_fps))

    # --- onComplete（仅 action 步骤）---
    if include_on_complete:
        on_complete = normalize_end_action_steps(sequence_def.get("onComplete"))
        for step in on_complete:
            action_id = step["action"]
            action_def = resolve_action_def(action_id, actions)
            if not action_def:
                continue
            step_range = step.get("playRange")
            frames, fps = load_action_frames(
                action_def, sprites_dir, step_range, _img_cache=img_cache
            )
            if frames:
                all_frames.extend(frames)
                fps_segments.append((len(frames), fps))

    return all_frames, fps_segments


def rgba_to_gif_frame(rgba_image: Image.Image, alpha_threshold: int = 128) -> Image.Image:
    """
    RGBA → GIF 用 P 模式帧（与 chroma_key_to_gif 同策略）：
    index 0 专留透明；不透明色量化后整体 +1 占用 1–255。
    """
    rgba = rgba_image.convert("RGBA")
    r, g, b, a = rgba.split()
    a_bin = a.point(lambda p: 255 if p > alpha_threshold else 0)

    # 透明区预填黑，避免残色占用调色板
    flat = Image.merge("RGBA", (r, g, b, a_bin))
    black = Image.new("RGBA", flat.size, (0, 0, 0, 255))
    composited = Image.composite(flat, black, a_bin)

    img_p = composited.convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=255)
    src_pal = img_p.getpalette() or []

    # 不透明索引整体 +1，腾出 index 0；透明像素再强制写回 0
    shifted = img_p.point(lambda i: i + 1 if i < 255 else 255)
    clear = Image.new("P", shifted.size, 0)
    mask = a_bin.point(lambda p: 255 if p == 0 else 0)
    shifted.paste(clear, mask=mask)

    new_pal = [0, 0, 0]
    new_pal.extend(src_pal[: 255 * 3])
    while len(new_pal) < 768:
        new_pal.append(0)
    shifted.putpalette(new_pal[:768])
    return shifted


def frames_to_gif(
    frames: list[Image.Image],
    fps_segments: list[tuple[int, int]],
    output_path: str,
    loop: int = 0,
    uniform_size: bool = True,
) -> str:
    """将帧列表保存为透明背景 GIF"""
    if not frames:
        print("[ERROR] 无可用帧，无法生成 GIF", file=sys.stderr)
        return ""

    if uniform_size:
        max_w = max(f.width for f in frames)
        max_h = max(f.height for f in frames)
        unified = []
        for f in frames:
            if f.width != max_w or f.height != max_h:
                canvas = Image.new("RGBA", (max_w, max_h), (0, 0, 0, 0))
                x = (max_w - f.width) // 2
                y = max_h - f.height
                canvas.paste(f, (x, y))
                unified.append(canvas)
            else:
                unified.append(f)
        frames = unified

    durations: list[int] = []
    for seg_count, seg_fps in fps_segments:
        ms = max(10, round(1000 / seg_fps))
        for _ in range(seg_count):
            durations.append(ms)

    while len(durations) < len(frames):
        durations.append(42)

    palette_frames = [rgba_to_gif_frame(f) for f in frames]
    first = palette_frames[0]
    rest = palette_frames[1:] if len(palette_frames) > 1 else []

    first.save(
        output_path,
        save_all=True,
        append_images=rest,
        duration=durations,
        loop=loop,
        disposal=2,
        transparency=0,
        optimize=True,
    )
    return output_path


def deep_merge(base: dict, patch: dict) -> dict:
    """深度合并两个 dict（patch 覆盖 base）"""
    result = base.copy()
    for k, v in patch.items():
        if k in result and isinstance(result[k], dict) and isinstance(v, dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result


def load_pet_json(pet_path: str, merge_path: Optional[str] = None) -> dict:
    """加载 pet.json，可选合并 patch"""
    with open(pet_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if merge_path and os.path.isfile(merge_path):
        with open(merge_path, "r", encoding="utf-8") as f:
            patch = json.load(f)
        data = deep_merge(data, patch)
    return data


def list_sequences(data: dict) -> list[tuple[str, str]]:
    """列出所有 sequence id + name"""
    seqs = data.get("sequences", {})
    return [(sid, sdef.get("name", "")) for sid, sdef in seqs.items()]


def preview_sequence_gif(
    pet_json_path: str,
    sequence_id: str,
    output_path: Optional[str] = None,
    merge_path: Optional[str] = None,
    sprites_dir: Optional[str] = None,
    hold_loops: Optional[int] = None,
    include_on_complete: bool = True,
) -> str:
    """
    主函数：从 pet.json 读取 sequence → 提取帧 → 输出 GIF。
    返回输出文件路径。
    """
    data = load_pet_json(pet_json_path, merge_path)

    seqs = data.get("sequences", {})
    if sequence_id not in seqs:
        available = ", ".join(seqs.keys())
        print(
            f"[ERROR] sequence '{sequence_id}' 不存在。可用: {available}",
            file=sys.stderr,
        )
        return ""

    seq_def = seqs[sequence_id]
    actions = data.get("actions", {})

    if sprites_dir is None:
        sprites_dir = os.path.dirname(os.path.abspath(pet_json_path))

    if output_path is None:
        output_path = f"{sequence_id}.gif"

    print(f"[INFO] 生成 sequence '{sequence_id}' ({seq_def.get('name', '')}) → {output_path}")

    all_frames, fps_segments = build_sequence_frames(
        seq_def, actions, sprites_dir,
        hold_loops_override=hold_loops,
        include_on_complete=include_on_complete,
    )

    if not all_frames:
        print("[ERROR] 未提取到任何帧", file=sys.stderr)
        return ""

    total = len(all_frames)
    size = f"{all_frames[0].width}x{all_frames[0].height}"
    print(f"[INFO] 共 {total} 帧, 尺寸 {size}")

    result = frames_to_gif(all_frames, fps_segments, output_path)
    if result:
        file_size = os.path.getsize(result)
        print(f"[OK] 已保存: {result} ({file_size / 1024:.1f} KB)")
    return result


def main():
    parser = argparse.ArgumentParser(
        description="从 pet.json 生成组合动作 GIF 预览"
    )
    parser.add_argument(
        "--pet", required=True,
        help="pet.json 路径（runtime/pet.json 或 user/pet.patch.json）",
    )
    parser.add_argument(
        "--merge",
        help="额外 patch JSON 路径，合并覆盖 --pet（如 user/pet.patch.json）",
    )
    parser.add_argument(
        "--sprites-dir",
        help="合图搜索目录（默认与 --pet 同目录）",
    )
    parser.add_argument(
        "--sequence", "-s",
        help="要预览的 sequence id",
    )
    parser.add_argument(
        "--output", "-o",
        help="输出 GIF 路径（默认 <sequence_id>.gif）",
    )
    parser.add_argument(
        "--hold-loops", type=int, default=None,
        help="hold 循环次数覆盖（默认由 duration 模式决定）",
    )
    parser.add_argument(
        "--no-on-complete", action="store_true",
        help="不包含 onComplete 步骤的帧",
    )
    parser.add_argument(
        "--list", action="store_true",
        help="仅列出可用 sequences",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="为所有 sequences 生成 GIF",
    )
    parser.add_argument(
        "--out-dir",
        help="--all 模式下的输出目录（默认当前目录）",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.pet):
        print(f"[ERROR] 文件不存在: {args.pet}", file=sys.stderr)
        sys.exit(1)

    data = load_pet_json(args.pet, args.merge)

    if args.list:
        seqs = list_sequences(data)
        if not seqs:
            print("（无 sequences）")
        else:
            print(f"共 {len(seqs)} 个 sequences：")
            for sid, name in seqs:
                print(f"  {sid:30s} {name}")
        return

    if args.all:
        seqs = list_sequences(data)
        if not seqs:
            print("（无 sequences）")
            return
        out_dir = args.out_dir or "."
        os.makedirs(out_dir, exist_ok=True)
        for sid, name in seqs:
            out = os.path.join(out_dir, f"{sid}.gif")
            preview_sequence_gif(
                args.pet, sid, out,
                merge_path=args.merge,
                sprites_dir=args.sprites_dir,
                hold_loops=args.hold_loops,
                include_on_complete=not args.no_on_complete,
            )
        return

    if not args.sequence:
        print("[ERROR] 请指定 --sequence <id> 或 --list 或 --all", file=sys.stderr)
        sys.exit(1)

    preview_sequence_gif(
        args.pet,
        args.sequence,
        args.output,
        merge_path=args.merge,
        sprites_dir=args.sprites_dir,
        hold_loops=args.hold_loops,
        include_on_complete=not args.no_on_complete,
    )


if __name__ == "__main__":
    main()
