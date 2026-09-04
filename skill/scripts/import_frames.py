#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将用户上传的序列帧 / GIF / webp 导入为 DesktopPet actions，并 merge 进 user/pet.patch.json。

依赖：Pillow（合图路径还会用到 make_spritesheet）
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from paths import ensure_user_dir  # noqa: E402
from merge_patch import apply_patch_file, load_json  # noqa: E402
from asset_review import require_review_pass, verify_image_metadata  # noqa: E402

IMAGE_EXTS = {".png", ".webp", ".jpg", ".jpeg", ".gif"}
DEFAULT_NON_IDLE_FPS = 24
# 合图格默认贴齐 720p；逻辑显示与 cell 解耦
DEFAULT_FRAME_SIZE = 720
DEFAULT_DISPLAY_SIZE = 128


def default_idle_fps(columns: int) -> int:
    """idle 未显式指定 fps 时：columns / 2（向下取整，至少 1）。"""
    return max(1, int(columns) // 2)


def resolve_action_fps(action_id: str, fps: int | None, columns: int) -> int:
    if fps is not None:
        return max(1, int(fps))
    if action_id == "idle":
        return default_idle_fps(columns)
    return DEFAULT_NON_IDLE_FPS


def parse_play_range(text: str | None) -> list[int] | list[list[int]] | None:
    if not text:
        return None
    text = text.strip()
    if not text:
        return None
    # 2,60 或 0,20;40,69
    if ";" in text:
        ranges: list[list[int]] = []
        for part in text.split(";"):
            a, b = part.split(",")
            ranges.append([int(a.strip()), int(b.strip())])
        return ranges
    a, b = text.split(",")
    return [int(a.strip()), int(b.strip())]


def list_frame_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    files = [
        p
        for p in sorted(source.iterdir())
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    ]
    if not files:
        raise FileNotFoundError(f"目录中无图片帧: {source}")
    return files


def assert_frame_payloads_have_motion(frame_payloads: list[bytes]) -> None:
    """动作至少两帧，且不能所有画面完全相同。"""
    if len(frame_payloads) < 2:
        raise ValueError(
            "素材只有一帧，不能作为桌宠 action 导入。"
            "静态 PNG/WebP/JPEG 只能作为 reference 图；请上传至少两帧且画面有变化的动作帧/GIF/WebP。"
        )
    first = frame_payloads[0]
    if all(payload == first for payload in frame_payloads[1:]):
        raise ValueError(
            "素材各帧画面完全相同，不是可见动作。"
            "静态图或重复帧只能作为 reference 图；请上传实际有动作变化的素材。"
        )


def assert_source_has_motion(source: Path) -> None:
    """拒绝单张静态图和逐帧完全相同的伪动作输入。"""
    from PIL import Image, ImageSequence

    if source.is_dir():
        paths = list_frame_files(source)
        payloads: list[bytes] = []
        for path in paths:
            with Image.open(path) as image:
                payloads.append(image.convert("RGBA").tobytes())
        assert_frame_payloads_have_motion(payloads)
        return

    if source.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"不支持的素材类型: {source}")
    with Image.open(source) as image:
        payloads = [frame.copy().convert("RGBA").tobytes() for frame in ImageSequence.Iterator(image)]
    assert_frame_payloads_have_motion(payloads)


def assert_ready_spritesheet_has_motion(
    source: Path,
    *,
    frames: int,
    columns: int,
    cell_w: int,
    cell_h: int,
    row: int | None,
) -> None:
    """已成图也须含至少两格不同画面，不能把 reference 伪装成 atlas。"""
    if frames < 2:
        raise ValueError(
            "--spritesheet-ready 的 action 至少需要两帧；单张静态图只能作为 reference 图。"
        )

    from PIL import Image

    with Image.open(source) as image:
        atlas = image.convert("RGBA")
        first_row = row or 0
        payloads: list[bytes] = []
        for index in range(frames):
            frame_row = first_row + index // columns
            frame_col = index % columns
            box = (
                frame_col * cell_w,
                frame_row * cell_h,
                (frame_col + 1) * cell_w,
                (frame_row + 1) * cell_h,
            )
            payloads.append(atlas.crop(box).tobytes())
    assert_frame_payloads_have_motion(payloads)


def frames_to_gif(frames: list[Path], out_gif: Path, fps: int) -> Path:
    from PIL import Image

    images = [Image.open(p).convert("RGBA") for p in frames]
    duration = max(10, int(1000 / max(fps, 1)))
    out_gif.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        out_gif,
        save_all=True,
        append_images=images[1:],
        duration=duration,
        loop=0,
        disposal=2,
    )
    return out_gif


def ensure_gif(source: Path, work: Path, fps: int) -> Path:
    """任意输入收敛为单个 GIF，供 make_spritesheet 使用。"""
    from PIL import Image, ImageSequence

    if source.is_dir():
        frames = list_frame_files(source)
        return frames_to_gif(frames, work / "seq.gif", fps)

    suffix = source.suffix.lower()
    if suffix == ".gif":
        dest = work / source.name
        shutil.copy2(source, dest)
        return dest

    if suffix in {".webp", ".png", ".jpg", ".jpeg"}:
        img = Image.open(source)
        dest = work / f"{source.stem}.gif"
        frames = [f.copy().convert("RGBA") for f in ImageSequence.Iterator(img)]
        if len(frames) <= 1:
            # 静态图：复制为单帧 gif
            frames = [img.convert("RGBA")]
        duration = max(10, int(1000 / max(fps, 1)))
        frames[0].save(
            dest,
            save_all=True,
            append_images=frames[1:],
            duration=duration,
            loop=0,
            disposal=2,
        )
        return dest

    raise ValueError(f"不支持的素材类型: {source}")


def build_clip(
    *,
    action_id: str,
    kind: str,
    spritesheet: str,
    frames: int,
    columns: int,
    fps: int,
    cell_w: int,
    cell_h: int,
    display_name: str | None,
    row: int | None,
    play_range: Any,
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "name": display_name or action_id,
        "spritesheet": spritesheet,
        "frames": frames,
        "columns": columns,
        "fps": fps,
        "cellWidth": cell_w,
        "cellHeight": cell_h,
        "showInMenu": True,
    }
    if row is not None:
        entry["row"] = row
    if play_range is not None:
        entry["playRange"] = play_range
    if kind == "atomic":
        entry["loop"] = True
    else:
        entry["playOnce"] = True
        m = re.match(r"^(.+)_to_(.+)$", action_id)
        if m:
            entry["from"] = m.group(1)
            entry["to"] = m.group(2)
    return entry


def import_via_spritesheet(
    *,
    pet_id: str,
    action_id: str,
    kind: str,
    source: Path,
    fps: int | None,
    frame_size: int,
    display_name: str | None,
    play_range: Any,
    review_manifest: Path,
) -> dict[str, Any]:
    from make_spritesheet import make_spritesheet

    review_record = require_review_pass(review_manifest, source)
    verify_image_metadata(review_record, source)
    assert_source_has_motion(source)
    info = ensure_user_dir(pet_id)
    user_dir = Path(info["userDir"])
    # 合图前尚未知 columns：idle 暂用 8，落盘前再按 columns//2 校正
    work_fps = fps if fps is not None else (
        8 if action_id == "idle" else DEFAULT_NON_IDLE_FPS
    )
    with tempfile.TemporaryDirectory(prefix="lingxi-pet-import-") as tmp:
        work = Path(tmp)
        gif = ensure_gif(source, work, work_fps)
        build_dir = work / "sheet"
        sheet = make_spritesheet(
            sources=[(action_id, str(gif))],
            output_dir=str(build_dir),
            name_prefix=action_id,
            frame_size=frame_size,
            fps=work_fps,
        )
        webp = Path(sheet["sprite"])
        if not webp.is_file():
            raise RuntimeError("make_spritesheet 未产出 sprite")
        manifest: dict[str, Any] = {}
        manifest_path = sheet.get("manifest")
        if manifest_path and Path(manifest_path).is_file():
            manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))

        dest_name = f"{action_id}.webp"
        dest = user_dir / dest_name
        # 若产出为 png 分块兜底，仍按 action_id.webp 命名复制可能失败；统一复制原扩展名
        if webp.suffix.lower() != ".webp":
            dest_name = f"{action_id}{webp.suffix.lower()}"
            dest = user_dir / dest_name
        shutil.copy2(webp, dest)

        rows = manifest.get("rows") or sheet.get("rows") or []
        frames = 1
        row = None
        if isinstance(rows, list) and rows:
            frames = int(rows[0].get("frames") or 1)
            if rows[0].get("row") is not None:
                row = int(rows[0]["row"])
        columns = int(manifest.get("columns") or frames)
        cell_w = int(manifest.get("frame_width") or frame_size)
        cell_h = int(manifest.get("frame_height") or frame_size)
        final_fps = resolve_action_fps(action_id, fps, columns)

        clip = build_clip(
            action_id=action_id,
            kind=kind,
            spritesheet=dest_name,
            frames=frames,
            columns=columns,
            fps=final_fps,
            cell_w=cell_w,
            cell_h=cell_h,
            display_name=display_name,
            row=row,
            play_range=play_range,
        )

    bucket = "atomic" if kind == "atomic" else "transition"
    patch_frag = {"actions": {bucket: {action_id: clip}}}
    if info["mode"] == "user-only":
        existing = load_json(Path(info["patch"]))
        if not existing:
            patch_frag.update(
                {
                    "id": pet_id,
                    "displayName": pet_id,
                    "schemaVersion": 3,
                    "defaultActivity": "idle",
                    "displayWidth": DEFAULT_DISPLAY_SIZE,
                    "displayHeight": DEFAULT_DISPLAY_SIZE,
                    "behaviors": {},
                    "sequences": {},
                    "categories": {"sequence": {"name": "组合", "states": []}},
                }
            )
    report = apply_patch_file(pet_id, patch_frag)
    report["actionId"] = action_id
    report["kind"] = kind
    report["spritesheet"] = dest_name
    return report


def import_spritesheet_ready(
    *,
    pet_id: str,
    action_id: str,
    kind: str,
    source: Path,
    frames: int,
    columns: int,
    fps: int | None,
    cell_w: int,
    cell_h: int,
    row: int | None,
    display_name: str | None,
    play_range: Any,
    review_manifest: Path,
) -> dict[str, Any]:
    review_record = require_review_pass(review_manifest, source)
    current = verify_image_metadata(review_record, source)
    if current.get("kind") != "image":
        raise ValueError("--spritesheet-ready 只接受单个合图文件")
    if source.suffix.lower() not in {".webp", ".png"}:
        raise ValueError("--spritesheet-ready 仅支持直接导入 PNG/WebP 合图；不要改名或转码后再审核")
    width = int(current["width"])
    height = int(current["height"])
    if columns <= 0 or frames <= 0 or cell_w <= 0 or cell_h <= 0:
        raise ValueError("合图 frames/columns/cell 尺寸必须为正数")
    if columns * cell_w != width:
        raise ValueError(f"合图宽度不一致: columns*cellWidth={columns * cell_w} != {width}")
    last_row = (row or 0) + (frames - 1) // columns
    if (last_row + 1) * cell_h > height:
        raise ValueError(f"合图行越界: last_row={last_row} cellHeight={cell_h} 图高={height}")
    assert_ready_spritesheet_has_motion(
        source,
        frames=frames,
        columns=columns,
        cell_w=cell_w,
        cell_h=cell_h,
        row=row,
    )
    info = ensure_user_dir(pet_id)
    user_dir = Path(info["userDir"])
    dest_name = f"{action_id}{source.suffix.lower()}"
    dest = user_dir / dest_name
    if source.resolve() != dest.resolve():
        shutil.copy2(source, dest)
    cols = columns or frames
    clip = build_clip(
        action_id=action_id,
        kind=kind,
        spritesheet=dest_name,
        frames=frames,
        columns=cols,
        fps=resolve_action_fps(action_id, fps, cols),
        cell_w=cell_w,
        cell_h=cell_h,
        display_name=display_name,
        row=row,
        play_range=play_range,
    )
    bucket = "atomic" if kind == "atomic" else "transition"
    patch_frag: dict[str, Any] = {"actions": {bucket: {action_id: clip}}}
    if info["mode"] == "user-only" and not Path(info["patch"]).is_file():
        patch_frag.update(
            {
                "id": pet_id,
                "displayName": pet_id,
                "schemaVersion": 3,
                "defaultActivity": "idle",
                "displayWidth": DEFAULT_DISPLAY_SIZE,
                "displayHeight": DEFAULT_DISPLAY_SIZE,
                "behaviors": {},
                "sequences": {},
                "categories": {"sequence": {"name": "组合", "states": []}},
            }
        )
    report = apply_patch_file(pet_id, patch_frag)
    report["actionId"] = action_id
    report["kind"] = kind
    report["spritesheet"] = dest_name
    return report


def import_batch_roundtrip(
    *,
    pet_id: str,
    atomic_id: str,
    home: str,
    sources: list[Path],
    fps: int | None,
    frame_size: int,
    review_manifest: Path,
) -> list[dict[str, Any]]:
    if len(sources) != 3:
        raise ValueError("batch-roundtrip 需要恰好 3 个来源：enter, hold, leave")
    # 三段批默认 24；显式 --fps 覆盖。idle 公式仅作用于 action_id=idle 的单次导入
    batch_fps = fps if fps is not None else DEFAULT_NON_IDLE_FPS
    ids = [f"{home}_to_{atomic_id}", atomic_id, f"{atomic_id}_to_{home}"]
    kinds = ["transition", "atomic", "transition"]
    for source in sources:
        record = require_review_pass(review_manifest, source)
        verify_image_metadata(record, source)
    reports = []
    for src, aid, kind in zip(sources, ids, kinds):
        reports.append(
            import_via_spritesheet(
                pet_id=pet_id,
                action_id=aid,
                kind=kind,
                source=src,
                fps=batch_fps,
                frame_size=frame_size,
                display_name=None,
                play_range=None,
                review_manifest=review_manifest,
            )
        )
    return reports


def main() -> int:
    parser = argparse.ArgumentParser(description="上传帧/GIF/webp → pet.patch.json actions")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument("--action-id", help="单个 action id")
    parser.add_argument("--kind", choices=["atomic", "transition"], default="atomic")
    parser.add_argument("--source", help="帧目录 / gif / webp")
    parser.add_argument(
        "--fps",
        type=int,
        default=None,
        help="播放帧率；省略时 idle=columns//2，其它=24",
    )
    parser.add_argument(
        "--frame-size",
        type=int,
        default=DEFAULT_FRAME_SIZE,
        help=f"合图格边长（默认 {DEFAULT_FRAME_SIZE}）",
    )
    parser.add_argument("--display-name", default=None)
    parser.add_argument("--play-range", default=None, help="如 2,60 或 0,20;40,69")
    parser.add_argument("--spritesheet-ready", action="store_true")
    parser.add_argument("--frames", type=int, default=None)
    parser.add_argument("--columns", type=int, default=None)
    parser.add_argument(
        "--cell-width",
        type=int,
        default=DEFAULT_DISPLAY_SIZE,
        help="已有合图 cell 宽（--spritesheet-ready；须与源图一致，默认 128）",
    )
    parser.add_argument(
        "--cell-height",
        type=int,
        default=DEFAULT_DISPLAY_SIZE,
        help="已有合图 cell 高（--spritesheet-ready；须与源图一致，默认 128）",
    )
    parser.add_argument("--row", type=int, default=None)
    parser.add_argument("--batch-roundtrip", help="atomic id，配合 --sources 三段")
    parser.add_argument("--home", default="idle")
    parser.add_argument("--sources", help="逗号分隔的三个路径")
    parser.add_argument("--review-manifest", type=Path, required=True,
                        help="preflight_asset_bundle.py 生成且已 view_image 通过的审核清单")
    args = parser.parse_args()

    play_range = parse_play_range(args.play_range)

    if args.batch_roundtrip:
        if not args.sources:
            raise SystemExit("batch-roundtrip 需要 --sources a,b,c")
        paths = [Path(p.strip()) for p in args.sources.split(",") if p.strip()]
        reports = import_batch_roundtrip(
            pet_id=args.pet_id,
            atomic_id=args.batch_roundtrip,
            home=args.home,
            sources=paths,
            fps=args.fps,
            frame_size=args.frame_size,
            review_manifest=args.review_manifest,
        )
        print(json.dumps({"ok": True, "reports": reports}, ensure_ascii=False, indent=2))
        return 0

    if not args.action_id or not args.source:
        raise SystemExit("单次导入需要 --action-id 与 --source")

    source = Path(args.source)
    if args.spritesheet_ready:
        if args.frames is None:
            raise SystemExit("--spritesheet-ready 需要 --frames")
        report = import_spritesheet_ready(
            pet_id=args.pet_id,
            action_id=args.action_id,
            kind=args.kind,
            source=source,
            frames=args.frames,
            columns=args.columns or args.frames,
            fps=args.fps,
            cell_w=args.cell_width,
            cell_h=args.cell_height,
            row=args.row,
            display_name=args.display_name,
            play_range=play_range,
            review_manifest=args.review_manifest,
        )
    else:
        report = import_via_spritesheet(
            pet_id=args.pet_id,
            action_id=args.action_id,
            kind=args.kind,
            source=source,
            fps=args.fps,
            frame_size=args.frame_size,
            display_name=args.display_name,
            play_range=play_range,
            review_manifest=args.review_manifest,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
