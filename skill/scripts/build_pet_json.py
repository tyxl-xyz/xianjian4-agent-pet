#!/usr/bin/env python3
"""
从 make_spritesheet / encode_action_webm 产出自动生成 DesktopPet v3 pet.patch.json（actions 骨架）。

合图策略由 manifest 结构自动推断，无需用户选择：
  - 1 manifest 多 row → 同 spritesheet + 不同 row（策略 A）
  - 多 manifest 或单 row → 各 action 独立 spritesheet（策略 B）
  - `*_video_manifest.json` 或目录内 `{id}.mov` / `{id}.webm` → 写入 actions
  - 默认创建宠：仅 `videoHevc`（stacked `.mov`）；可选伴生 `video`（`.webm`）
  - 同目录 `{id}.mov` / manifest `videoHevc` → 写入 actions.*.videoHevc（stacked-alpha）

落盘防撞名：泛名 sprite.webp / sprite.png 会按批次动作重命名（如 happy.webp / happy.png）；
WebP 超限主交付为 .png（manifest.sprite）；*_partN.webp 仅调试，拒绝写入 user/。
`.webm` / `.mov` 与 webp/png 同等拷贝到 user/。
user/ 目标已存在且内容不同时拒绝覆盖。顶层 spritesheetPath 仅缺失或为泛名时才更新。

Phase A 每批次仅 merge actions（禁止默认 --auto-sequences）。
actions 齐后 Phase C 用 generate_sequences.py --require-ready。

用法:
  python build_pet_json.py --manifest-dir _build/happy/ --out "{userDir}" \\
    --pet-id my-cat --display-name "我的猫" --default-activity idle

  python build_pet_json.py --manifest-dir out/ --out "{userDir}" \\
    --merge "{patch}"
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

TRANSITION_RE = re.compile(r"^(.+)_to_(.+)$")
GENERIC_SHEET_STEM_RE = re.compile(r"^sprite(_part\d+)?$", re.IGNORECASE)

# 逻辑显示边长：与高清 cell（合图 frame_size，默认 720）解耦；引擎用 scale=display/cell
DEFAULT_DISPLAY_SIZE = 128


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def is_transition_id(action_id: str) -> bool:
    return "_to_" in action_id and TRANSITION_RE.match(action_id) is not None


def infer_row_kind(
    action_id: str,
    row_index: int,
    total_rows: int,
) -> str:
    """根据行位置与 id 推断 atomic / transition。"""
    if total_rows == 1:
        return "transition" if is_transition_id(action_id) else "atomic"
    if total_rows == 3:
        if row_index == 1:
            return "atomic"
        return "transition"
    if total_rows == 2:
        if is_transition_id(action_id):
            return "transition"
        return "atomic" if row_index == 1 else "transition"
    # 多行：中间行偏 atomic，首尾偏 transition
    if row_index == 0 or row_index == total_rows - 1:
        return "transition" if is_transition_id(action_id) else "atomic"
    return "atomic"


def normalize_row_name(name: str) -> str:
    return name.strip().replace("-", "_")


def rows_from_manifest(manifest: dict[str, Any], fallback_id: str) -> list[dict[str, Any]]:
    if manifest.get("rows"):
        return manifest["rows"]
    frames = manifest.get("output_frames") or manifest.get("frames")
    if frames is None:
        raise ValueError(f"manifest 缺少 rows 或 output_frames: {fallback_id}")
    return [{"name": fallback_id, "row": 0, "frames": int(frames)}]


def clip_entry_from_row(
    manifest: dict[str, Any],
    row: dict[str, Any],
    spritesheet: str,
    kind: str,
    total_rows: int,
    display_name: str | None = None,
) -> dict[str, Any]:
    fw = int(manifest["frame_width"])
    fh = int(manifest["frame_height"])
    cols = int(manifest.get("columns") or row.get("frames") or 1)
    fps = int(row.get("fps") or manifest.get("fps") or 24)
    entry: dict[str, Any] = {
        "name": display_name or row.get("display_name") or row["name"],
        "spritesheet": spritesheet,
        "frames": int(row["frames"]),
        "columns": cols,
        "fps": fps,
        "cellWidth": fw,
        "cellHeight": fh,
    }
    row_idx = row.get("row")
    if total_rows > 1 and row_idx is not None:
        entry["row"] = int(row_idx)
    if kind == "atomic":
        entry["loop"] = row.get("loop", True)
        entry["showInMenu"] = row.get("showInMenu", row.get("show_in_menu", False))
    else:
        entry["playOnce"] = True
        entry["showInMenu"] = False
    if row.get("displayScale") is not None:
        entry["displayScale"] = row["displayScale"]
    return entry


def manifest_sheet_basename(manifest: dict[str, Any]) -> str | None:
    """manifest 声明的主合图文件名（优先 spritesheet，其次 sprite）。"""
    for key in ("spritesheet", "sprite"):
        val = manifest.get(key)
        if val:
            return str(val)
    return None


def resolve_sheet_path(manifest_dir: Path, prefix: str, declared: str | None) -> tuple[Path, str]:
    """
    解析合图主文件：WebP 超限时主交付为 PNG。

    顺序：manifest 声明 → 同前缀 .webp → 同前缀 .png。
    均不存在则 SystemExit（禁止静默跳过导致 user/ 缺图）。
    """
    candidates: list[str] = []
    if declared:
        candidates.append(Path(declared).name)
    for name in (f"{prefix}.webp", f"{prefix}.png"):
        if name not in candidates:
            candidates.append(name)

    for name in candidates:
        path = manifest_dir / name
        if path.is_file():
            return path, name

    tried = ", ".join(candidates)
    raise SystemExit(
        f"未找到合图主文件（prefix={prefix!r}）。已尝试: {tried}。"
        f"若宽度超过 WebP 16383，make_spritesheet 应产出 {prefix}.png 且 manifest.sprite 指向它。",
    )


def manifest_pair_paths(manifest_path: Path, manifest: dict[str, Any]) -> tuple[Path, str]:
    """manifest.json → 对应合图路径与文件名（.webp 或超限时的 .png）。"""
    if manifest_path.name.endswith("_manifest.json"):
        prefix = manifest_path.name[: -len("_manifest.json")]
    else:
        prefix = manifest_path.stem.replace("_manifest", "")
    declared = manifest_sheet_basename(manifest)
    return resolve_sheet_path(manifest_path.parent, prefix, declared)


def video_clip_entry(
    action_id: str,
    kind: str,
    video_name: str | None = None,
    *,
    frames: int,
    fps: int,
    cell: int,
    display_name: str | None = None,
    video_hevc: str | None = None,
    video_alpha_layout: str | None = None,
) -> dict[str, Any]:
    """纯 video / videoHevc clip：cell 用 displaySize 占位。"""
    if not video_name and not video_hevc:
        raise SystemExit(
            f"actions 缺少 video 与 videoHevc: action_id={action_id!r}",
        )
    if video_name:
        suffix = Path(video_name).suffix.lower()
        if suffix in {".mov", ".mp4"}:
            raise SystemExit(
                f"actions.*.video 须为 .webm，got {video_name}；"
                f".mov/.mp4 应写入 videoHevc + videoAlphaLayout=stacked"
            )
    entry: dict[str, Any] = {
        "name": display_name or action_id,
        "frames": max(1, int(frames)),
        "columns": 1,
        "fps": max(1, int(fps)),
        "cellWidth": cell,
        "cellHeight": cell,
    }
    if video_name:
        entry["video"] = video_name
    if video_hevc:
        entry["videoHevc"] = video_hevc
        entry["videoAlphaLayout"] = video_alpha_layout or "stacked"
    if kind == "atomic":
        entry["loop"] = True
        entry["showInMenu"] = False
    else:
        entry["playOnce"] = True
        entry["showInMenu"] = False
    return entry


def _resolve_mac_companion(
    manifest_dir: Path,
    action_id: str,
    row: dict[str, Any] | None = None,
) -> tuple[Path | None, str | None]:
    """返回 (mov_path, layout)。"""
    row = row or {}
    hevc_name = str(row.get("videoHevc") or "").strip()
    layout = str(row.get("videoAlphaLayout") or "stacked").strip() or "stacked"
    if hevc_name:
        path = manifest_dir / Path(hevc_name).name
        if path.is_file():
            return path, layout
    for cand in (
        manifest_dir / f"{action_id}.mov",
        manifest_dir / f"{action_id}.mp4",
    ):
        if cand.is_file():
            return cand, layout
    return None, None


def collect_video_clips(manifest_dir: Path, display_size: int) -> list[dict[str, Any]]:
    """从 *_video_manifest.json 与裸 *.webm / *.mov 收集 clips。"""
    clips: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    cell = max(1, int(display_size))

    video_manifests = sorted(manifest_dir.glob("*_video_manifest.json"))
    for manifest_path in video_manifests:
        manifest = load_json(manifest_path)
        rows = rows_from_manifest(manifest, manifest_path.stem.replace("_video_manifest", ""))
        total = len(rows)
        for i, row in enumerate(rows):
            action_id = normalize_row_name(str(row.get("id") or row.get("name") or f"clip_{i}"))
            video_name = str(row.get("video") or "").strip()
            video_path: Path | None = None
            if video_name:
                video_path = manifest_dir / Path(video_name).name
                if not video_path.is_file():
                    raise SystemExit(f"video_manifest 声明的 webm 不存在: {video_path}")
            kind = row.get("kind") or infer_row_kind(action_id, i, total)
            mac_path, mac_layout = _resolve_mac_companion(manifest_dir, action_id, row)
            if video_path is None and mac_path is None:
                raise SystemExit(
                    f"video_manifest 行 {action_id!r} 无 video 也无可用 videoHevc/.mov",
                )
            entry = video_clip_entry(
                action_id,
                kind,
                video_path.name if video_path else None,
                frames=int(row.get("frames") or 1),
                fps=int(row.get("fps") or manifest.get("fps") or 24),
                cell=cell,
                display_name=row.get("display_name"),
                video_hevc=mac_path.name if mac_path else None,
                video_alpha_layout=mac_layout
                or str(row.get("videoAlphaLayout") or "stacked"),
            )
            clips.append(
                {
                    "id": action_id,
                    "kind": kind,
                    "entry": entry,
                    "webp_path": None,
                    "video_path": video_path,
                    "video_hevc_path": mac_path,
                    "manifest_path": manifest_path,
                },
            )
            seen_ids.add(action_id)

    for webm in sorted(manifest_dir.glob("*.webm")):
        action_id = normalize_row_name(webm.stem)
        if action_id in seen_ids:
            continue
        kind = "transition" if is_transition_id(action_id) else "atomic"
        mac_path, mac_layout = _resolve_mac_companion(manifest_dir, action_id)
        entry = video_clip_entry(
            action_id,
            kind,
            webm.name,
            frames=1,
            fps=24,
            cell=cell,
            video_hevc=mac_path.name if mac_path else None,
            video_alpha_layout=mac_layout,
        )
        clips.append(
            {
                "id": action_id,
                "kind": kind,
                "entry": entry,
                "webp_path": None,
                "video_path": webm,
                "video_hevc_path": mac_path,
                "manifest_path": None,
            },
        )
        seen_ids.add(action_id)

    for mov in sorted(manifest_dir.glob("*.mov")):
        action_id = normalize_row_name(mov.stem)
        if action_id in seen_ids:
            continue
        kind = "transition" if is_transition_id(action_id) else "atomic"
        entry = video_clip_entry(
            action_id,
            kind,
            None,
            frames=1,
            fps=24,
            cell=cell,
            video_hevc=mov.name,
            video_alpha_layout="stacked",
        )
        clips.append(
            {
                "id": action_id,
                "kind": kind,
                "entry": entry,
                "webp_path": None,
                "video_path": None,
                "video_hevc_path": mov,
                "manifest_path": None,
            },
        )
        seen_ids.add(action_id)

    return clips


def merge_video_onto_sheet_clips(
    sheet_clips: list[dict[str, Any]],
    video_clips: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """同 id：保留图集 entry，附加 video/videoHevc；仅视频的 id 追加。"""
    by_id = {c["id"]: c for c in sheet_clips}
    for vc in video_clips:
        aid = vc["id"]
        if aid in by_id:
            if vc["entry"].get("video"):
                by_id[aid]["entry"]["video"] = vc["entry"]["video"]
                by_id[aid]["video_path"] = vc.get("video_path")
            if vc["entry"].get("videoHevc"):
                by_id[aid]["entry"]["videoHevc"] = vc["entry"]["videoHevc"]
                by_id[aid]["entry"]["videoAlphaLayout"] = vc["entry"].get(
                    "videoAlphaLayout",
                    "stacked",
                )
                by_id[aid]["video_hevc_path"] = vc.get("video_hevc_path")
        else:
            by_id[aid] = vc
    return list(by_id.values())


def collect_clips(manifest_dir: Path, display_size: int = DEFAULT_DISPLAY_SIZE) -> list[dict[str, Any]]:
    sheet_manifests = sorted(
        p
        for p in manifest_dir.glob("*_manifest.json")
        if not p.name.endswith("_video_manifest.json")
    )
    if not sheet_manifests:
        sheet_manifests = sorted(
            p
            for p in manifest_dir.glob("*manifest*.json")
            if not p.name.endswith("_video_manifest.json")
            and "_video_manifest" not in p.name
        )

    clips: list[dict[str, Any]] = []
    for manifest_path in sheet_manifests:
        manifest = load_json(manifest_path)
        if manifest.get("format") == "video_webm":
            continue
        prefix = manifest_path.name.replace("_manifest.json", "").replace(".json", "")
        sheet_path, sheet_name = manifest_pair_paths(manifest_path, manifest)

        rows = rows_from_manifest(manifest, prefix)
        total = len(rows)
        for i, row in enumerate(rows):
            action_id = normalize_row_name(str(row.get("id") or row.get("name") or prefix))
            kind = row.get("kind") or infer_row_kind(action_id, i, total)
            clips.append(
                {
                    "id": action_id,
                    "kind": kind,
                    "entry": clip_entry_from_row(manifest, row, sheet_name, kind, total),
                    "webp_path": sheet_path,
                    "video_path": None,
                    "manifest_path": manifest_path,
                }
            )

    video_clips = collect_video_clips(manifest_dir, display_size)
    if clips and video_clips:
        return merge_video_onto_sheet_clips(clips, video_clips)
    if video_clips:
        return video_clips
    if clips:
        return clips
    raise SystemExit(f"未找到 spritesheet manifest 或 .webm/.mov: {manifest_dir}")


def build_categories(
    atomic: dict[str, Any],
    transition: dict[str, Any],
) -> dict[str, Any]:
    cats: dict[str, Any] = {}
    if atomic:
        cats["atomic"] = {
            "name": "原子动作",
            "states": sorted(atomic.keys()),
        }
    if transition:
        cats["transition"] = {
            "name": "过渡动作",
            "states": sorted(transition.keys()),
        }
    return cats


def build_pet_skeleton(
    clips: list[dict[str, Any]],
    pet_id: str,
    display_name: str,
    default_activity: str,
    description: str = "",
    display_size: int = DEFAULT_DISPLAY_SIZE,
) -> dict[str, Any]:
    atomic: dict[str, Any] = {}
    transition: dict[str, Any] = {}

    for clip in clips:
        if clip["kind"] == "transition":
            transition[clip["id"]] = clip["entry"]
        else:
            atomic[clip["id"]] = clip["entry"]

    if default_activity not in atomic and default_activity in transition:
        raise SystemExit(
            f"defaultActivity={default_activity!r} 应是 atomic，当前仅在 transition 中",
        )
    if default_activity not in atomic and atomic:
        default_activity = next(iter(sorted(atomic.keys())))

    home = atomic.get(default_activity) or {}
    cell_w = int(home.get("cellWidth") or DEFAULT_DISPLAY_SIZE)
    cell_h = int(home.get("cellHeight") or DEFAULT_DISPLAY_SIZE)
    spritesheet_path = (
        home.get("spritesheet")
        or next(
            (c["entry"].get("spritesheet") for c in clips if c["entry"].get("spritesheet")),
            None,
        )
        or home.get("video")
        or home.get("videoHevc")
        or clips[0]["entry"].get("video")
        or clips[0]["entry"].get("videoHevc")
        or ""
    )
    # 高清格（cell）可远大于逻辑显示；禁止把 display 绑成 cell，否则默认窗口会变成 720px
    dw = max(1, int(display_size))
    if cell_w > 0 and cell_h > 0 and cell_w != cell_h:
        dh = max(1, int(round(dw * cell_h / cell_w)))
    else:
        dh = dw

    pet: dict[str, Any] = {
        "id": pet_id,
        "displayName": display_name,
        "description": description or f"{display_name}桌宠",
        "schemaVersion": 3,
        "spritesheetPath": spritesheet_path,
        "cellWidth": cell_w,
        "cellHeight": cell_h,
        "columns": int(home.get("columns") or 1),
        "displayWidth": dw,
        "displayHeight": dh,
        "defaultActivity": default_activity,
        "actions": {
            "atomic": atomic,
            "transition": transition,
        },
        "categories": build_categories(atomic, transition),
    }
    return pet


def merge_pet(existing: dict[str, Any], new_pet: dict[str, Any]) -> dict[str, Any]:
    merged = dict(existing)
    for key in ("id", "displayName", "description", "schemaVersion", "defaultActivity"):
        if key in new_pet:
            merged[key] = new_pet[key]
    for key in (
        "spritesheetPath",
        "cellWidth",
        "cellHeight",
        "columns",
        "displayWidth",
        "displayHeight",
    ):
        if key not in new_pet:
            continue
        # 顶层 spritesheetPath 仅作兜底；已有非泛名则保留，泛名可被本批具体名替换
        if key == "spritesheetPath":
            old = merged.get(key)
            if old is None or is_generic_sheet_name(str(old)):
                merged[key] = new_pet[key]
            continue
        # cell/columns：随新批次刷新，支持从旧 128 格升级到高清格
        if key in ("cellWidth", "cellHeight", "columns"):
            merged[key] = new_pet[key]
            continue
        # display*：仅在缺失时补默认；已有逻辑显示尺寸不覆盖（避免被误写成 cell）
        if key not in merged:
            merged[key] = new_pet[key]

    actions = merged.setdefault("actions", {})
    for kind in ("atomic", "transition"):
        bucket = actions.setdefault(kind, {})
        bucket.update(new_pet.get("actions", {}).get(kind, {}))

    cats = merged.setdefault("categories", {})
    for cat_key in ("atomic", "transition"):
        new_states = new_pet.get("categories", {}).get(cat_key, {}).get("states", [])
        if not new_states:
            continue
        block = cats.setdefault(cat_key, {"name": new_pet["categories"][cat_key]["name"], "states": []})
        block["states"] = sorted(set(block.get("states", [])) | set(new_states))

    return merged


def is_generic_sheet_name(name: str) -> bool:
    """make_spritesheet 默认前缀 sprite / sprite_partN（含 .png），多批次落盘会撞名。"""
    return GENERIC_SHEET_STEM_RE.match(Path(name).stem) is not None


def is_debug_part_sheet_name(name: str) -> bool:
    """WebP 超限时的调试分块 *_partN.webp，禁止当作主合图写入 user/。"""
    stem = Path(name).stem
    return bool(re.search(r"_part\d+$", stem, re.IGNORECASE))


def derive_batch_stem(clips_for_src: list[dict[str, Any]]) -> str:
    """从同批 clips 推断落盘文件名前缀（优先唯一 atomic / 三段中段）。"""
    atomics = [c["id"] for c in clips_for_src if c.get("kind") == "atomic"]
    if len(atomics) == 1:
        return str(atomics[0])
    if len(clips_for_src) == 3 and clips_for_src[1].get("kind") == "atomic":
        return str(clips_for_src[1]["id"])
    if atomics:
        return str(atomics[0])
    return str(clips_for_src[0]["id"])


def _sha256_file(path: Path) -> bytes:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.digest()


def resolve_webp_dest_names(clips: list[dict[str, Any]], out_dir: Path) -> None:
    """
    为即将写入 user/ 的合图确定唯一 dest_name，并回写 entry.spritesheet。

    - 泛名 sprite.webp / sprite_partN.webp → 按批次动作重命名（如 happy.webp）
    - 目标已存在且内容不同 → 拒绝覆盖（SystemExit）
    - 目标已存在且内容相同 → 幂等跳过
    - 无 webp_path（纯 video）跳过
    """
    by_src: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for clip in clips:
        src = clip.get("webp_path")
        if src is None:
            continue
        by_src[src].append(clip)

    for src, group in by_src.items():
        src_name = src.name
        if is_debug_part_sheet_name(src_name):
            raise SystemExit(
                f"拒绝将调试分块 {src_name} 作为主合图写入 user/。"
                f"WebP 超限时应使用完整 {{prefix}}.png（manifest.sprite）。",
            )
        dest_name = src_name
        if is_generic_sheet_name(src_name):
            stem = derive_batch_stem(group)
            m = GENERIC_SHEET_STEM_RE.match(Path(src_name).stem)
            part_suffix = m.group(1) if m and m.group(1) else ""
            # 泛名 sprite.png（超限主交付）→ happy.png；sprite_partN 不应走到这里
            dest_name = f"{stem}{part_suffix}{src.suffix}"

        dest = out_dir / dest_name
        if src.exists() and dest.exists():
            if _sha256_file(dest) != _sha256_file(src):
                raise SystemExit(
                    f"user/ 已存在不同内容的合图 {dest_name}，拒绝覆盖。"
                    f"请为 make_spritesheet 使用唯一 --prefix（建议与批次目录同名，如 --prefix happy）。",
                )

        for clip in group:
            clip["dest_name"] = dest_name
            clip["entry"]["spritesheet"] = dest_name


def resolve_video_dest_names(clips: list[dict[str, Any]], out_dir: Path) -> None:
    """为 .webm 确定 dest，并回写 entry.video；冲突同合图策略。"""
    by_src: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for clip in clips:
        src = clip.get("video_path")
        if src is None:
            continue
        by_src[src].append(clip)

    for src, group in by_src.items():
        dest_name = src.name
        if Path(dest_name).suffix.lower() != ".webm":
            raise SystemExit(f"video 资产须为 .webm: {src}")
        dest = out_dir / dest_name
        if src.exists() and dest.exists():
            if _sha256_file(dest) != _sha256_file(src):
                raise SystemExit(
                    f"user/ 已存在不同内容的视频 {dest_name}，拒绝覆盖。"
                    f"请使用唯一动作 id 文件名（如 fail.webm）。",
                )
        for clip in group:
            clip["video_dest_name"] = dest_name
            clip["entry"]["video"] = dest_name


def resolve_video_hevc_dest_names(clips: list[dict[str, Any]], out_dir: Path) -> None:
    """为 Mac .mov/.mp4 确定 dest，并回写 entry.videoHevc。"""
    by_src: dict[Path, list[dict[str, Any]]] = defaultdict(list)
    for clip in clips:
        src = clip.get("video_hevc_path")
        if src is None:
            continue
        by_src[src].append(clip)

    for src, group in by_src.items():
        dest_name = src.name
        if Path(dest_name).suffix.lower() not in {".mov", ".mp4"}:
            raise SystemExit(f"videoHevc 资产须为 .mov/.mp4: {src}")
        dest = out_dir / dest_name
        if src.exists() and dest.exists():
            if _sha256_file(dest) != _sha256_file(src):
                raise SystemExit(
                    f"user/ 已存在不同内容的 Mac 视频 {dest_name}，拒绝覆盖。"
                    f"请使用唯一动作 id 文件名（如 fail.mov）。",
                )
        for clip in group:
            clip["video_hevc_dest_name"] = dest_name
            clip["entry"]["videoHevc"] = dest_name
            clip["entry"]["videoAlphaLayout"] = clip["entry"].get(
                "videoAlphaLayout",
                "stacked",
            )


def copy_webp_assets(clips: list[dict[str, Any]], out_dir: Path) -> None:
    seen: set[Path] = set()
    for clip in clips:
        src = clip.get("webp_path")
        if src is None:
            continue
        dest_name = str(clip.get("dest_name") or src.name)
        if is_debug_part_sheet_name(dest_name) or is_debug_part_sheet_name(src.name):
            raise SystemExit(
                f"拒绝拷贝调试分块到 user/: {src.name} → {dest_name}",
            )
        if src in seen:
            continue
        if not src.is_file():
            raise SystemExit(
                f"合图源文件不存在，无法写入 user/: {src}。"
                f"请确认 make_spritesheet 已产出主文件，且 manifest.sprite 与之一致。",
            )
        seen.add(src)
        shutil.copy2(src, out_dir / dest_name)


def copy_video_assets(clips: list[dict[str, Any]], out_dir: Path) -> None:
    seen: set[Path] = set()
    for clip in clips:
        for key, dest_key in (
            ("video_path", "video_dest_name"),
            ("video_hevc_path", "video_hevc_dest_name"),
        ):
            src = clip.get(key)
            if src is None:
                continue
            dest_name = str(clip.get(dest_key) or src.name)
            if src in seen:
                continue
            if not src.is_file():
                raise SystemExit(f"视频源文件不存在，无法写入 user/: {src}")
            seen.add(src)
            shutil.copy2(src, out_dir / dest_name)


def main() -> None:
    parser = argparse.ArgumentParser(description="manifest → DesktopPet v3 pet.patch.json")
    parser.add_argument("--manifest-dir", type=Path, required=True, help="含 webp 与 *_manifest.json 的目录")
    parser.add_argument("--out", type=Path, required=True, help="灵犀 user 层目录，如 .../accounts/{accountId}/pets/{petId}/user")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--default-activity", default="idle")
    parser.add_argument("--description", default="")
    parser.add_argument(
        "--display-size",
        type=int,
        default=DEFAULT_DISPLAY_SIZE,
        help=f"逻辑显示边长（默认 {DEFAULT_DISPLAY_SIZE}；与合图 cell/frame_size 解耦）",
    )
    parser.add_argument("--merge", type=Path, help="合并到已有 pet.patch.json（保留 sequences/behaviors 等）；省略则写入 {out}/pet.patch.json")
    parser.add_argument("--dry-run", action="store_true", help="只打印 JSON，不写文件")
    parser.add_argument(
        "--auto-sequences",
        type=int,
        default=0,
        metavar="N",
        help="随机生成 N 条 sequences（默认 0；须在 Phase C 单独执行，勿在素材批次中用）",
    )
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="与 --auto-sequences 联用：默认四态 actions 齐后才生成",
    )
    parser.add_argument(
        "--extra",
        nargs="*",
        default=[],
        metavar="ATOMIC",
        help="与 --require-ready 联用：用户额外要求的状态",
    )
    parser.add_argument(
        "--sequence-prompt",
        default="",
        help="用户指定的组合玩法自然语言；非空时跳过 --auto-sequences，由 Agent 按 lingxi-pet Phase C / prompt-playbook 生成",
    )
    parser.add_argument("--sequence-seed", type=int, help="--auto-sequences 随机种子")
    args = parser.parse_args()

    if not args.manifest_dir.is_dir():
        raise SystemExit(f"目录不存在: {args.manifest_dir}")

    clips = collect_clips(args.manifest_dir, display_size=args.display_size)
    # 在组骨架前解析落盘名，避免多批默认 sprite.webp 互相覆盖
    resolve_webp_dest_names(clips, args.out)
    resolve_video_dest_names(clips, args.out)
    resolve_video_hevc_dest_names(clips, args.out)
    pet = build_pet_skeleton(
        clips,
        pet_id=args.pet_id,
        display_name=args.display_name,
        default_activity=args.default_activity,
        description=args.description,
        display_size=args.display_size,
    )

    patch_path = args.merge if args.merge else args.out / "pet.patch.json"

    if patch_path.is_file():
        pet = merge_pet(load_json(patch_path), pet)

    seq_note = ""
    if args.sequence_prompt.strip():
        seq_note = "（有 sequence prompt，sequences 由 Agent 按 lingxi-pet Phase C 生成）"
    elif args.auto_sequences > 0:
        import sys

        script_dir = Path(__file__).resolve().parent
        if str(script_dir) not in sys.path:
            sys.path.insert(0, str(script_dir))
        from generate_sequences import generate_default_sequences, merge_sequences_into_pet

        if args.require_ready:
            from action_readiness import check_actions_ready

            readiness = check_actions_ready(pet, extra_roundtrip_atomics=args.extra)
            if not readiness.ready:
                raise SystemExit(readiness.message())

        new_seqs = generate_default_sequences(
            pet,
            count=args.auto_sequences,
            seed=args.sequence_seed,
        )
        if new_seqs:
            pet = merge_sequences_into_pet(pet, new_seqs)
            seq_note = f"，随机生成 {len(new_seqs)} 条 sequences"

    text = json.dumps(pet, ensure_ascii=False, indent=2) + "\n"
    if args.dry_run:
        print(text)
        return

    args.out.mkdir(parents=True, exist_ok=True)
    copy_webp_assets(clips, args.out)
    copy_video_assets(clips, args.out)
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(text, encoding="utf-8")
    print(f"已写入 {patch_path}")
    seq_count = len(pet.get("sequences", {}))
    print(
        f"actions: {len(pet['actions']['atomic'])} atomic, "
        f"{len(pet['actions']['transition'])} transition, "
        f"sequences: {seq_count}{seq_note}",
    )
    if seq_count == 0 and not args.sequence_prompt.strip():
        print(
            "提示：默认四态 merge 完成后，执行 "
            "action_readiness.py → generate_sequences.py --require-ready --merge-in",
        )


if __name__ == "__main__":
    main()
