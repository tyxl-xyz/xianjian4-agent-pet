#!/usr/bin/env python3
"""
幕布色建议（固定色板 + 最大最小环距）
====================================
写 generate_image prompt 前，或基准图 redo-bg 时调用。

用法：
  python suggest_screen_color.py --hues 55,160
  python suggest_screen_color.py --from-image reference.png
  python suggest_screen_color.py --hues 55 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from screen_palette import (
    SCREEN_PALETTE,
    extract_subject_hues,
    nearest_palette_family,
    suggest_screen_from_hues,
)


def _parse_hues(text: str) -> list[int]:
    out: list[int] = []
    for part in text.replace(";", ",").split(","):
        part = part.strip()
        if not part:
            continue
        out.append(int(part) % 180)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="建议幕布色板项（OpenCV H）")
    ap.add_argument(
        "--hues",
        type=str,
        default=None,
        help="角色有色簇 OpenCV H，逗号分隔，如 55,160",
    )
    ap.add_argument(
        "--from-image",
        type=Path,
        default=None,
        help="从基准图提取非幕布高饱和 hue 再建议",
    )
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    if not args.hues and not args.from_image:
        print("请提供 --hues 或 --from-image", file=sys.stderr)
        return 2

    subject_hues: list[int] = []
    if args.hues:
        subject_hues.extend(_parse_hues(args.hues))

    if args.from_image:
        if not args.from_image.is_file():
            print(f"文件不存在: {args.from_image}", file=sys.stderr)
            return 2
        arr = np.asarray(Image.open(args.from_image).convert("RGB"))
        # 四角估幕布
        h, w = arr.shape[:2]
        corners = [
            arr[0:12, 0:12].reshape(-1, 3).mean(axis=0),
            arr[0:12, w - 12 : w].reshape(-1, 3).mean(axis=0),
            arr[h - 12 : h, 0:12].reshape(-1, 3).mean(axis=0),
            arr[h - 12 : h, w - 12 : w].reshape(-1, 3).mean(axis=0),
        ]
        screen_rgb = np.mean(corners, axis=0)
        subject_hues.extend(extract_subject_hues(arr, screen_rgb))
        current = nearest_palette_family(screen_rgb)
    else:
        current = None

    # 去重保序
    seen: set[int] = set()
    uniq: list[int] = []
    for h in subject_hues:
        if h not in seen:
            seen.add(h)
            uniq.append(h)

    result = suggest_screen_from_hues(uniq)
    result["current_family_from_image"] = current
    result["palette"] = {
        name: {
            "rgb": list(e["rgb"]),
            "hue_range": list(e["hue_range"]),
        }
        for name, e in SCREEN_PALETTE.items()
    }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"suggested: {result['family']}")
        print(f"  RGB: {tuple(result['rgb'])}")
        print(f"  prompt: Solid {result['prompt_name']} ...")
        print(f"  chroma: --hue {result['chroma_hue_arg']}")
        print(f"  subject_hues: {result['subject_hues']}")
        print(f"  min_distance: {result['min_distance']}")
        print(f"  reason: {result['reason']}")
        if current:
            print(f"  image_current_family: {current}")
            if current != result["family"]:
                print(f"  → 建议 redo-bg 从 {current} 换到 {result['family']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
