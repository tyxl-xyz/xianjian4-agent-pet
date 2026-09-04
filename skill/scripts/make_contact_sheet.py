#!/usr/bin/env python3
"""
Contact sheet（草案）
====================
把 GIF / 帧目录 / spritesheet 某一行拼成一张总览图，便于一次验收（对照 qa-rubric）。

依赖：Pillow

用法：
  python make_contact_sheet.py --input hold.gif --out ./qa/contact-sheet.png
  python make_contact_sheet.py --input ./frames --out ./qa/contact-sheet.png --max-frames 24
  python make_contact_sheet.py --spritesheet a.webp --frames 16 --columns 8 --row 0 --out ./qa/contact-sheet.png
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageSequence


def _load_gif(path: Path) -> list[Image.Image]:
    im = Image.open(path)
    return [f.copy().convert("RGBA") for f in ImageSequence.Iterator(im)]


def _load_dir(path: Path) -> list[Image.Image]:
    files = sorted(
        p for p in path.iterdir() if p.suffix.lower() in {".png", ".webp", ".gif", ".jpg", ".jpeg"}
    )
    frames: list[Image.Image] = []
    for p in files:
        if p.suffix.lower() == ".gif":
            frames.extend(_load_gif(p))
        else:
            frames.append(Image.open(p).convert("RGBA"))
    return frames


def _load_sheet(path: Path, frames: int, columns: int, row: int) -> list[Image.Image]:
    sheet = Image.open(path).convert("RGBA")
    cell_w = sheet.width // columns
    cell_h = sheet.height if sheet.height <= cell_w * 2 else sheet.height // max(1, (frames + columns - 1) // columns)
    out: list[Image.Image] = []
    for i in range(frames):
        c = i % columns
        r = row + i // columns
        out.append(sheet.crop((c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)))
    return out


def make_contact_sheet(
    frames: list[Image.Image],
    *,
    columns: int = 8,
    pad: int = 4,
    bg: tuple[int, int, int, int] = (40, 40, 40, 255),
    label: bool = True,
) -> Image.Image:
    if not frames:
        raise ValueError("no frames")
    cell_w = max(f.width for f in frames)
    cell_h = max(f.height for f in frames)
    cols = max(1, min(columns, len(frames)))
    rows = int(math.ceil(len(frames) / cols))
    label_h = 14 if label else 0
    sheet = Image.new(
        "RGBA",
        (cols * (cell_w + pad) + pad, rows * (cell_h + pad + label_h) + pad),
        bg,
    )
    draw = ImageDraw.Draw(sheet)
    for i, fr in enumerate(frames):
        r, c = divmod(i, cols)
        x = pad + c * (cell_w + pad)
        y = pad + r * (cell_h + pad + label_h)
        # 底部对齐放入 cell
        ox = x + (cell_w - fr.width) // 2
        oy = y + label_h + (cell_h - fr.height)
        sheet.paste(fr, (ox, oy), fr)
        if label:
            draw.text((x + 2, y), str(i), fill=(220, 220, 220, 255))
    return sheet


def main() -> int:
    ap = argparse.ArgumentParser(description="Build a contact sheet for visual QA")
    ap.add_argument("--input", help="GIF 或帧目录")
    ap.add_argument("--spritesheet")
    ap.add_argument("--frames", type=int)
    ap.add_argument("--columns", type=int, default=8)
    ap.add_argument("--row", type=int, default=0)
    ap.add_argument("--out", required=True)
    ap.add_argument("--max-frames", type=int, default=48, help="过多则均匀抽样")
    ap.add_argument("--sheet-columns", type=int, default=8, help="contact sheet 列数")
    args = ap.parse_args()

    if bool(args.input) == bool(args.spritesheet):
        print("须指定其一：--input 或 --spritesheet", file=sys.stderr)
        return 2

    if args.input:
        p = Path(args.input)
        frames = _load_dir(p) if p.is_dir() else _load_gif(p)
    else:
        if not args.frames:
            print("--spritesheet 需要 --frames", file=sys.stderr)
            return 2
        frames = _load_sheet(Path(args.spritesheet), args.frames, args.columns, args.row)

    if len(frames) > args.max_frames:
        step = max(1, len(frames) // args.max_frames)
        frames = frames[::step][: args.max_frames]

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    img = make_contact_sheet(frames, columns=args.sheet_columns)
    img.save(out)
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
