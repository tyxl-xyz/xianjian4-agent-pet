#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
多行合图导入（共享 spritesheet + row）
====================================
将「一张大图、多行动作」写入 user/：只复制一个合图文件，patch 里各 atomic 用 row 引用。
禁止默认拆成多个 webp。

依赖：Pillow

用法：
  python import_atlas_sheet.py --pet-id doraemon --sheet spritesheet.webp \\
    --columns 8 --cell-w 192 --cell-h 208 \\
    --rows-spec "idle:0:6:4:待机,running_right:1:8:12:向右跑"

  python import_atlas_sheet.py --pet-id my-pet --sheet sheet.webp --infer-grid \\
    --rows-spec "idle:0:6,wave:3:4:8:挥手" --display-size 128

rows-spec 单项：action_id:row:frames[:fps[:display_name]]

idle 未写 fps 时：fps = max(1, columns // 2)；其它动作未写时默认 8。
用户显式写了 fps 则以用户为准。
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from merge_patch import apply_patch_file, load_json  # noqa: E402
from behaviors_format import fill_missing_locomotion  # noqa: E402
from paths import ensure_user_dir  # noqa: E402
from asset_review import require_review_pass, verify_image_metadata  # noqa: E402

SPEC_RE = re.compile(
    r"^(?P<id>[a-zA-Z0-9_-]+):(?P<row>\d+):(?P<frames>\d+)"
    r"(?::(?P<fps>\d+))?(?::(?P<name>.+))?$"
)

DEFAULT_NON_IDLE_FPS = 8

# ── Codex 格式预设表（版本化，新版本只需追加条目）──
# 格式：(cols, rows, cell_w, cell_h) → 行映射列表
# 每条行映射：(row, action_id, frames, fps, display_name)
# "frames" 和 "fps" 可被 --rows-spec 中的同名参数覆盖；
# "fps" 设为 None 时按现有公式推断。
CODEX_PRESETS: dict[tuple[int, int, int, int], list[tuple[int, str, int, int | None, str]]] = {
    # Codex v1: 8 cols × 9 rows × 192×208
    # 官方来源: openai/skills/.curated/hatch-pet/references/animation-rows.md
    (8, 9, 192, 208): [
        (0, "idle",           6, None, "待机"),       # fps=None → columns//2
        (1, "running_right",  8, 12,    "向右跑"),
        (2, "running_left",   8, 12,    "向左跑"),
        (3, "waving",         4, 8,     "挥手"),
        (4, "jumping",        5, 8,     "跳跃"),
        (5, "failed",         8, 8,     "失败"),
        (6, "waiting",        6, 8,     "等待"),
        (7, "working",        6, 10,    "工作中"),      # Codex 叫 running（处理中），灵犀映射为 working
        (8, "review",         6, 8,     "审查"),
    ],
    # ── 未来扩展：Codex v2 (11 行) 在此追加 ──
    # (8, 11, 192, 208): [
    #     ...
    # ],
}


def default_idle_fps(columns: int) -> int:
    """idle 未显式指定 fps 时：columns / 2（向下取整，至少 1）。"""
    return max(1, int(columns) // 2)


def resolve_row_fps(action_id: str, fps: int | None, columns: int) -> int:
    if fps is not None:
        return max(1, int(fps))
    if action_id == "idle":
        return default_idle_fps(columns)
    return DEFAULT_NON_IDLE_FPS


def parse_rows_spec(text: str) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for raw in text.split(","):
        part = raw.strip()
        if not part:
            continue
        m = SPEC_RE.match(part)
        if not m:
            raise ValueError(
                f"无法解析 rows-spec 项: {part!r}，期望 action_id:row:frames[:fps[:name]]"
            )
        fps_raw = m.group("fps")
        name = (m.group("name") or "").strip() or m.group("id")
        items.append(
            {
                "id": m.group("id"),
                "row": int(m.group("row")),
                "frames": int(m.group("frames")),
                "fps": int(fps_raw) if fps_raw is not None else None,
                "name": name,
            }
        )
    if not items:
        raise ValueError("rows-spec 为空")
    return items


def apply_default_fps(rows: list[dict[str, Any]], columns: int) -> list[dict[str, Any]]:
    for r in rows:
        r["fps"] = resolve_row_fps(r["id"], r.get("fps"), columns)
    return rows


def detect_codex_preset(
    image_w: int, image_h: int,
) -> tuple[tuple[int, int, int, int], list[tuple[int, str, int, int | None, str]]] | None:
    """检测图片尺寸是否命中已知 Codex 格式预设。

    返回 (grid_key, row_mappings) 或 None。
    """
    for (cols, rows, cell_w, cell_h), mappings in CODEX_PRESETS.items():
        if image_w == cols * cell_w and image_h == rows * cell_h:
            return (cols, rows, cell_w, cell_h), mappings
    return None


def infer_grid(image_w: int, image_h: int, columns: int | None) -> dict[str, int]:
    """根据常见等规格网格推断 columns / rows / cell。"""
    candidates_cols = [columns] if columns else [8, 10, 6, 4, 12, 16]
    best: dict[str, int] | None = None
    for cols in candidates_cols:
        if not cols or image_w % cols != 0:
            continue
        cell_w = image_w // cols
        # 优先正方形格，否则用 cell_w 估行高
        for cell_h in (cell_w, 208, 192, 256, 128):
            if image_h % cell_h != 0:
                continue
            rows = image_h // cell_h
            if rows < 1 or rows > 32:
                continue
            score = 0
            if cell_w == 192 and cell_h == 208 and cols == 8:
                score = 100
            elif abs(cell_w - cell_h) <= 16:
                score = 50
            else:
                score = 10
            score += max(0, 20 - abs(rows - 9))  # 略偏好多行表
            cand = {
                "columns": cols,
                "rows": rows,
                "cellWidth": cell_w,
                "cellHeight": cell_h,
                "score": score,
            }
            if best is None or cand["score"] > best["score"]:
                best = cand
    if best is None:
        raise ValueError(
            f"无法从 {image_w}x{image_h} 推断网格；请显式传入 --columns --cell-w --cell-h"
        )
    return best


def build_atomic(
    *,
    action_id: str,
    name: str,
    sheet_name: str,
    row: int,
    frames: int,
    columns: int,
    fps: int,
    cell_w: int,
    cell_h: int,
) -> dict[str, Any]:
    return {
        "name": name,
        "spritesheet": sheet_name,
        "row": row,
        "frames": frames,
        "columns": columns,
        "fps": fps,
        "cellWidth": cell_w,
        "cellHeight": cell_h,
        "loop": True,
        "showInMenu": True,
    }


def import_atlas_sheet(
    *,
    pet_id: str,
    sheet: Path,
    rows: list[dict[str, Any]],
    columns: int,
    cell_w: int,
    cell_h: int,
    display_size: int | None,
    display_name: str | None,
    description: str | None,
    sheet_dest_name: str | None,
    review_manifest: Path | None,
) -> dict[str, Any]:
    from PIL import Image

    if not sheet.is_file():
        raise FileNotFoundError(sheet)

    if review_manifest is None:
        raise ValueError("上传素材导入必须提供 --review-manifest；先完成 view_image 审核")
    review_record = require_review_pass(review_manifest, sheet)
    verify_image_metadata(review_record, sheet)

    source_suffix = sheet.suffix.lower()
    if source_suffix not in {".webp", ".png"}:
        raise ValueError(
            f"现成合图仅支持直接导入 PNG/WebP，收到 {source_suffix or '无扩展名'}；"
            "不要在审核阶段转码，改用受支持原格式重新提供素材"
        )
    dest_name = sheet_dest_name or f"spritesheet{source_suffix}"
    if Path(dest_name).suffix.lower() != source_suffix:
        raise ValueError(
            f"合图直接导入必须保留原始格式 {source_suffix}；"
            "请使用同扩展名的 --sheet-dest-name"
        )

    img = Image.open(sheet)
    iw, ih = img.size
    if columns * cell_w != iw:
        raise ValueError(
            f"网格元数据不一致: columns*cellWidth={columns * cell_w} != 图像宽 {iw}"
        )
    if cell_w <= 0 or cell_h <= 0 or columns <= 0:
        raise ValueError("网格参数必须为正数")
    for row in rows:
        if row["frames"] <= 0:
            raise ValueError(f"动作 {row['id']} 的 frames 必须为正数")
        last_row = row["row"] + (row["frames"] - 1) // columns
        if (last_row + 1) * cell_h > ih:
            raise ValueError(
                f"动作 {row['id']} 行越界: last_row={last_row} cell_h={cell_h} 图高={ih}"
            )

    apply_default_fps(rows, columns)

    info = ensure_user_dir(pet_id)
    user_dir = Path(info["userDir"])
    dest = user_dir / dest_name
    shutil.copy2(sheet, dest)

    atomics = {
        r["id"]: build_atomic(
            action_id=r["id"],
            name=r["name"],
            sheet_name=dest_name,
            row=r["row"],
            frames=r["frames"],
            columns=columns,
            fps=r["fps"],
            cell_w=cell_w,
            cell_h=cell_h,
        )
        for r in rows
    }

    dw = display_size if display_size else min(128, cell_w)
    dh = display_size if display_size else min(128, cell_h)
    # 保持比例：若只给一边，按 cell 比缩放
    if display_size:
        dh = max(1, int(round(display_size * cell_h / max(cell_w, 1))))

    patch_frag: dict[str, Any] = {
        "id": pet_id,
        "schemaVersion": 3,
        "defaultActivity": "idle" if "idle" in atomics else next(iter(atomics)),
        "displayWidth": dw,
        "displayHeight": dh,
        "actions": {"atomic": atomics},
        # Codex / 多行合图：默认补 walking/dragging，避免引擎空 behaviors 指向 run_* 错 id
        "behaviors": fill_missing_locomotion({}, {"atomic": atomics}),
        "sequences": {},
        "categories": {"sequence": {"name": "组合", "states": []}},
    }
    if display_name:
        patch_frag["displayName"] = display_name
    elif info["mode"] == "user-only":
        existing = load_json(Path(info["patch"]))
        patch_frag["displayName"] = existing.get("displayName") or pet_id
    if description:
        patch_frag["description"] = description

    # 去掉易误导的旁路字段（若旧 patch 里有）
    existing = load_json(Path(info["patch"])) if Path(info["patch"]).is_file() else {}
    cleanup = {}
    if "spritesheetPath" in existing:
        cleanup["spritesheetPath"] = None  # merge 层若忽略 None 则靠下文说明

    report = apply_patch_file(pet_id, patch_frag)
    # 显式重写 patch：删除非灵犀字段 spritesheetPath
    patch_path = Path(info["patch"])
    data = load_json(patch_path)
    data.pop("spritesheetPath", None)
    # 合并 atomic（apply 已做）；确保顶层尺寸与 sequences 占位
    data.setdefault("sequences", {})
    data.setdefault("categories", {"sequence": {"name": "组合", "states": []}})
    data["actions"] = data.get("actions") or {}
    data["actions"]["atomic"] = {
        **(data["actions"].get("atomic") or {}),
        **atomics,
    }
    # 幂等补 locomotion（不覆盖已有 working/fail 等）
    existing_beh = data.get("behaviors") if isinstance(data.get("behaviors"), dict) else {}
    data["behaviors"] = fill_missing_locomotion(
        {k: v for k, v in existing_beh.items() if isinstance(v, str) and v.strip()},
        data["actions"],
    )
    data["displayWidth"] = dw
    data["displayHeight"] = dh
    data["id"] = pet_id
    if display_name:
        data["displayName"] = display_name
    if description:
        data["description"] = description
    patch_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report.update(
        {
            "sheet": dest_name,
            "columns": columns,
            "cellWidth": cell_w,
            "cellHeight": cell_h,
            "displayWidth": dw,
            "displayHeight": dh,
            "actions": list(atomics.keys()),
            "behaviors": data.get("behaviors"),
            "split": False,
            "next": (
                "compose-sequence（编组合）；behaviors 须为字符串映射 "
                '{"working":"working_play"}，禁止 {actions:[...]} 对象格式；'
                "勿在 sequences 为空时宣称完成"
            ),
        }
    )
    return report


def _rows_spec_from_codex_mappings(
    mappings: list[tuple[int, str, int, int | None, str]],
) -> str:
    """将 Codex 预设映射列表转为 --rows-spec 字符串。"""
    parts = []
    for (row, action_id, frames, fps, name) in mappings:
        if fps is not None:
            parts.append(f"{action_id}:{row}:{frames}:{fps}:{name}")
        else:
            # fps=None → 由脚本按公式推断（idle: columns//2）
            parts.append(f"{action_id}:{row}:{frames}:{name}")
    return ",".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Import multi-row atlas as shared spritesheet + row")
    ap.add_argument("--pet-id", required=True)
    ap.add_argument("--sheet", required=True, type=Path)
    ap.add_argument("--rows-spec", default=None, help="id:row:frames[:fps[:name]],...")
    ap.add_argument("--preset", default=None, choices=["codex", "codex:latest"],
                     help="自动检测 Codex 格式并填充 rows-spec（当前支持 codex v1 = 8x9x192x208）")
    ap.add_argument("--columns", type=int, default=None)
    ap.add_argument("--cell-w", type=int, default=None)
    ap.add_argument("--cell-h", type=int, default=None)
    ap.add_argument("--infer-grid", action="store_true", help="从图尺寸推断网格")
    ap.add_argument("--display-size", type=int, default=128, help="逻辑显示边（宽），高按格比例")
    ap.add_argument("--display-name", default=None)
    ap.add_argument("--description", default=None)
    ap.add_argument("--sheet-name", default="spritesheet.webp", help="写入 user/ 的文件名")
    ap.add_argument("--review-manifest", type=Path, required=True,
                    help="preflight_asset_bundle.py 生成且已 view_image 通过的审核清单")
    args = ap.parse_args()

    from PIL import Image

    img = Image.open(args.sheet)
    iw, ih = img.size

    # ── 阶段 1：确定 rows-spec ──
    rows_spec_text = args.rows_spec
    codex_preset_detected = None

    if rows_spec_text is None and args.preset:
        # --preset 显式指定：检测图片尺寸是否匹配预设
        preset = detect_codex_preset(iw, ih)
        if preset is None:
            print(
                json.dumps({
                    "error": f"图片尺寸 {iw}x{ih} 不匹配任何已知 Codex 预设；"
                             f"已知预设: {list(CODEX_PRESETS.keys())}，请用 --rows-spec 手动指定",
                }, ensure_ascii=False),
                file=sys.stderr,
            )
            return 2
        (cols, rows_count, cw, ch), mappings = preset
        rows_spec_text = _rows_spec_from_codex_mappings(mappings)
        codex_preset_detected = {(cols, rows_count, cw, ch): mappings}
        print(
            json.dumps({
                "codex_preset": {
                    "grid": [cols, rows_count, cw, ch],
                    "image": [iw, ih],
                    "auto_rows_spec": rows_spec_text,
                },
            }, ensure_ascii=False),
        )

    if rows_spec_text is None:
        print("需要 --rows-spec 或 --preset codex", file=sys.stderr)
        return 2

    rows = parse_rows_spec(rows_spec_text)

    # ── 阶段 2：确定网格参数 ──
    columns = args.columns
    cell_w = args.cell_w
    cell_h = args.cell_h

    # 预设命中时自动填充网格参数
    if codex_preset_detected:
        key = next(iter(codex_preset_detected))
        columns = columns or key[0]
        cell_w = cell_w or key[2]
        cell_h = cell_h or key[3]

    if args.infer_grid or columns is None or cell_w is None or cell_h is None:
        grid = infer_grid(iw, ih, columns)
        columns = columns or grid["columns"]
        cell_w = cell_w or grid["cellWidth"]
        cell_h = cell_h or grid["cellHeight"]
        print(
            json.dumps(
                {"infer_grid": {"columns": columns, "cellWidth": cell_w, "cellHeight": cell_h, "image": [iw, ih]}},
                ensure_ascii=False,
            )
        )
    if columns is None or cell_w is None or cell_h is None:
        print("需要 --columns/--cell-w/--cell-h 或 --infer-grid", file=sys.stderr)
        return 2

    apply_default_fps(rows, columns)

    report = import_atlas_sheet(
        pet_id=args.pet_id,
        sheet=args.sheet,
        rows=rows,
        columns=columns,
        cell_w=cell_w,
        cell_h=cell_h,
        display_size=args.display_size,
        display_name=args.display_name,
        description=args.description,
        sheet_dest_name=args.sheet_name,
        review_manifest=args.review_manifest,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
