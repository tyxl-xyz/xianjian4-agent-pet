#!/usr/bin/env python3
"""
帧/GIF/合图视觉门禁（草案）
==========================
检查透明 GIF 或已展开帧目录：空帧、尺寸跳动、可选首尾循环接缝。
输出 qa/review.json，供 Agent 对照 references/shared/qa-rubric.md。

接缝策略（默认）：score < 0.15 ok；0.15–0.28 仅 warning 不挡；≥ 0.28 才 error。
最终以目视为准。可用 --loop-warn / --loop-error 调整。

依赖：Pillow、numpy

用法：
  python inspect_frames.py --input hold.gif --out-dir ./qa --check-loop
  python inspect_frames.py --input ./frames_dir --out-dir ./qa
  python inspect_frames.py --spritesheet sheet.webp --frames 24 --columns 8 --row 0 --out-dir ./qa
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageSequence


def _load_gif_frames(path: Path) -> list[Image.Image]:
    im = Image.open(path)
    return [f.copy().convert("RGBA") for f in ImageSequence.Iterator(im)]


def _load_dir_frames(path: Path) -> list[Image.Image]:
    files = sorted(
        p
        for p in path.iterdir()
        if p.suffix.lower() in {".png", ".webp", ".gif", ".jpg", ".jpeg"}
    )
    if not files:
        raise SystemExit(f"帧目录为空: {path}")
    out: list[Image.Image] = []
    for p in files:
        if p.suffix.lower() == ".gif":
            out.extend(_load_gif_frames(p))
        else:
            out.append(Image.open(p).convert("RGBA"))
    return out


def _load_spritesheet_row(
    path: Path, *, frames: int, columns: int, row: int, cell_w: int | None, cell_h: int | None
) -> list[Image.Image]:
    sheet = Image.open(path).convert("RGBA")
    if cell_w is None:
        cell_w = sheet.width // columns
    if cell_h is None:
        # 假定按行堆叠；行高 = 总高 / 行数（未知行数时用单行切）
        rows = max(1, (frames + columns - 1) // columns)
        # 若只取一行，优先用「整高即 cell」当单行 sheet
        if sheet.height <= cell_w * 2:
            cell_h = sheet.height
        else:
            cell_h = sheet.height // max(1, rows)
    out: list[Image.Image] = []
    for i in range(frames):
        c = i % columns
        r = row + i // columns
        box = (c * cell_w, r * cell_h, (c + 1) * cell_w, (r + 1) * cell_h)
        out.append(sheet.crop(box))
    return out


def _alpha_bbox(frame: Image.Image) -> tuple[int, int, int, int] | None:
    return frame.getchannel("A").getbbox()


def _opaque_ratio(frame: Image.Image) -> float:
    a = np.asarray(frame.getchannel("A"), dtype=np.float32)
    return float((a > 8).mean())


def _bbox_metrics(frames: list[Image.Image]) -> dict:
    heights: list[int] = []
    widths: list[int] = []
    for f in frames:
        bb = _alpha_bbox(f)
        if bb is None:
            continue
        widths.append(bb[2] - bb[0])
        heights.append(bb[3] - bb[1])
    if not heights:
        return {"count": 0}
    h = np.array(heights, dtype=np.float32)
    w = np.array(widths, dtype=np.float32)
    return {
        "count": int(len(heights)),
        "height_mean": float(h.mean()),
        "height_std": float(h.std()),
        "height_cv": float(h.std() / max(h.mean(), 1e-6)),
        "width_mean": float(w.mean()),
        "width_std": float(w.std()),
        "width_cv": float(w.std() / max(w.mean(), 1e-6)),
    }


# 接缝分数：越小越好。默认偏松——中间带只 warning，不挡 ok；很高才 error。
# 最终仍以 qa-rubric 目视首尾为准（量化不替代 adopt）。
DEFAULT_LOOP_WARN = 0.15
DEFAULT_LOOP_ERROR = 0.28


def _loop_seam_score(
    first: Image.Image,
    last: Image.Image,
    *,
    warn_max: float = DEFAULT_LOOP_WARN,
    error_max: float = DEFAULT_LOOP_ERROR,
) -> dict:
    """首尾帧 alpha 加权 RGB 差异 → status: ok | warn | fail。"""
    a = np.asarray(first.resize((64, 64)), dtype=np.float32)
    b = np.asarray(last.resize((64, 64)), dtype=np.float32)
    mask = (a[..., 3] > 8) | (b[..., 3] > 8)
    if not mask.any():
        return {
            "score": 1.0,
            "status": "fail",
            "note": "both_empty",
            "warn_max": warn_max,
            "error_max": error_max,
        }
    diff = np.abs(a[..., :3] - b[..., :3]).mean(axis=2)
    score = float(diff[mask].mean() / 255.0)
    if score >= error_max:
        status = "fail"
    elif score >= warn_max:
        status = "warn"
    else:
        status = "ok"
    return {
        "score": score,
        "status": status,
        "warn_max": warn_max,
        "error_max": error_max,
    }


def inspect_frames(
    frames: list[Image.Image],
    *,
    check_loop: bool = False,
    empty_ratio_max: float = 0.02,
    size_cv_max: float = 0.18,
    loop_warn_max: float = DEFAULT_LOOP_WARN,
    loop_error_max: float = DEFAULT_LOOP_ERROR,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if len(frames) < 1:
        errors.append("no_frames")
        return {"ok": False, "errors": errors, "warnings": warnings, "frame_count": 0}

    empty_idx: list[int] = []
    for i, f in enumerate(frames):
        if _opaque_ratio(f) <= empty_ratio_max:
            empty_idx.append(i)
    if empty_idx:
        errors.append(f"empty_or_near_empty_frames:{empty_idx[:12]}")

    metrics = _bbox_metrics(frames)
    if metrics.get("count", 0) == 0:
        errors.append("all_frames_transparent")
    else:
        if metrics["height_cv"] > size_cv_max or metrics["width_cv"] > size_cv_max:
            warnings.append(
                f"size_jitter_high:height_cv={metrics['height_cv']:.3f},width_cv={metrics['width_cv']:.3f}"
            )

    loop = None
    if check_loop:
        if len(frames) < 2:
            errors.append("loop_check_needs_2_frames")
        else:
            loop = _loop_seam_score(
                frames[0],
                frames[-1],
                warn_max=loop_warn_max,
                error_max=loop_error_max,
            )
            score = loop["score"]
            status = loop["status"]
            if status == "fail":
                errors.append(
                    f"loop_seam_fail:score={score:.3f}(>={loop_error_max});须目视确认或 redo"
                )
            elif status == "warn":
                warnings.append(
                    f"loop_seam_warn:score={score:.3f}(>={loop_warn_max});须目视首尾后再 adopt"
                )
            else:
                warnings.append(f"loop_seam_ok:score={score:.3f}")

    ok = len(errors) == 0
    return {
        "ok": ok,
        "frame_count": len(frames),
        "errors": errors,
        "warnings": warnings,
        "bbox_metrics": metrics,
        "loop": loop,
        "policy": {
            "empty_ratio_max": empty_ratio_max,
            "size_cv_max": size_cv_max,
            "check_loop": check_loop,
            "loop_warn_max": loop_warn_max,
            "loop_error_max": loop_error_max,
            "note": "接缝量化：warn 不挡 ok；fail 才失败。最终对照 qa-rubric.md 目视确认",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Inspect GIF/frames/spritesheet for QA gate")
    ap.add_argument("--input", help="GIF 或帧目录")
    ap.add_argument("--spritesheet", help="spritesheet 图像")
    ap.add_argument("--frames", type=int, help="spritesheet 帧数")
    ap.add_argument("--columns", type=int, default=8)
    ap.add_argument("--row", type=int, default=0)
    ap.add_argument("--cell-w", type=int, default=None)
    ap.add_argument("--cell-h", type=int, default=None)
    ap.add_argument("--out-dir", required=True, help="输出目录（写 review.json）")
    ap.add_argument("--check-loop", action="store_true", help="检查首尾帧接缝（三段 hold）")
    ap.add_argument(
        "--loop-warn",
        type=float,
        default=DEFAULT_LOOP_WARN,
        help=f"接缝分数 ≥ 此值仅 warning（默认 {DEFAULT_LOOP_WARN}）",
    )
    ap.add_argument(
        "--loop-error",
        type=float,
        default=DEFAULT_LOOP_ERROR,
        help=f"接缝分数 ≥ 此值才 error/失败（默认 {DEFAULT_LOOP_ERROR}）",
    )
    ap.add_argument("--json-out", default=None, help="默认 {out-dir}/review.json")
    args = ap.parse_args()

    if bool(args.input) == bool(args.spritesheet):
        print("须指定其一：--input 或 --spritesheet", file=sys.stderr)
        return 2

    if args.input:
        src = Path(args.input)
        if src.is_dir():
            frames = _load_dir_frames(src)
        else:
            frames = _load_gif_frames(src)
    else:
        if not args.frames:
            print("--spritesheet 需要 --frames", file=sys.stderr)
            return 2
        frames = _load_spritesheet_row(
            Path(args.spritesheet),
            frames=args.frames,
            columns=args.columns,
            row=args.row,
            cell_w=args.cell_w,
            cell_h=args.cell_h,
        )

    report = inspect_frames(
        frames,
        check_loop=args.check_loop,
        loop_warn_max=args.loop_warn,
        loop_error_max=args.loop_error,
    )
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = Path(args.json_out) if args.json_out else out_dir / "review.json"
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    loop_status = (report.get("loop") or {}).get("status")
    print(
        json.dumps(
            {
                "review": str(out_path),
                "ok": report["ok"],
                "loop_status": loop_status,
                "warnings": report.get("warnings") or [],
                "errors": report.get("errors") or [],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
