#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Shared safety-review and source-integrity checks for uploaded pet assets.

The visual model is only responsible for the ``review`` decision.  Numeric
metadata (bytes, dimensions and animation frame counts) is produced by this
module and checked again immediately before an importer writes ``user/``.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any

IMAGE_EXTS = {
    ".png",
    ".webp",
    ".gif",
    ".jpg",
    ".jpeg",
    ".bmp",
    ".avif",
    ".heic",
    ".heif",
    ".tif",
    ".tiff",
}


def sha256_file(path: Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            chunk = fh.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def sha256_tree(path: Path) -> str:
    """Hash a directory's relative names and bytes in stable order."""
    if not path.is_dir():
        raise FileNotFoundError(path)
    digest = hashlib.sha256()
    for child in sorted(p for p in path.rglob("*") if p.is_file()):
        rel = child.relative_to(path).as_posix().encode("utf-8")
        digest.update(len(rel).to_bytes(8, "big"))
        digest.update(rel)
        digest.update(bytes.fromhex(sha256_file(child)))
    return digest.hexdigest()


def source_sha256(path: Path) -> str:
    return sha256_tree(path) if path.is_dir() else sha256_file(path)


def _image_metadata(path: Path) -> dict[str, Any]:
    from PIL import Image, ImageSequence

    with Image.open(path) as image:
        width, height = image.size
        frame_count = 0
        for frame_count, _ in enumerate(ImageSequence.Iterator(image), start=1):
            if frame_count > 10000:
                raise ValueError(f"动画帧数超过安全上限: {path}")
        if frame_count == 0:
            frame_count = 1
    return {
        "format": path.suffix.lower().lstrip("."),
        "width": int(width),
        "height": int(height),
        "frameCount": int(frame_count),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def asset_metadata(path: Path) -> dict[str, Any]:
    """Return deterministic metadata for one image or a frame directory."""
    path = path.resolve()
    if path.is_dir():
        files = sorted(
            p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS
        )
        if not files:
            raise ValueError(f"素材目录中没有可解析图片: {path}")
        records = [asset_metadata(p) for p in files]
        return {
            "kind": "frame-directory",
            "fileCount": len(records),
            "frameCount": sum(int(r.get("frameCount", 0)) for r in records),
            "files": [
                {
                    "path": p.relative_to(path).as_posix(),
                    **record,
                }
                for p, record in zip(files, records)
            ],
            "sha256": sha256_tree(path),
        }
    if path.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"不支持的视觉素材类型: {path.suffix or path.name}")
    return {"kind": "image", **_image_metadata(path)}


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"无法读取审核清单: {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("审核清单必须是 JSON 对象")
    return data


def _asset_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    records = manifest.get("assets")
    if not isinstance(records, list) or not records:
        raise ValueError("审核清单缺少 assets")
    if not all(isinstance(item, dict) for item in records):
        raise ValueError("审核清单 assets 格式无效")
    return records


def _record_matches_source(record: dict[str, Any], source: Path) -> bool:
    try:
        current = asset_metadata(source)
    except Exception:  # noqa: BLE001 - converted to a useful gate error below
        return False
    if current.get("kind") == "frame-directory":
        return record.get("kind") == "frame-directory" and record.get("sha256") == current.get("sha256")
    return record.get("sha256") == current.get("sha256")


def _staged_original_path(manifest: dict[str, Any], record: dict[str, Any]) -> Path:
    """Validate that a record was reviewed as its exact staged original file."""
    staged_raw = manifest.get("stagedDir")
    if not isinstance(staged_raw, str):
        raise ValueError("审核清单缺少 stagedDir")
    staged = Path(staged_raw).resolve()
    raw = record.get("path")
    if not isinstance(raw, str) or not raw:
        raise ValueError("审核素材缺少相对路径")
    rel = PurePosixPath(raw)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError(f"审核素材路径不安全: {raw}")
    if rel.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"审核素材必须是图片文件: {raw}")
    expected = staged.joinpath(*rel.parts).resolve()
    if staged not in expected.parents or not expected.is_file():
        raise ValueError(f"审核原始文件不存在或越界: {raw}")
    if record.get("reviewPaths") != [str(expected)]:
        raise ValueError(f"审核路径不是解包后的原始上传文件: {raw}")
    return expected


def _is_in_staged(source: Path, staged: Path) -> bool:
    return source == staged or staged in source.parents


def require_review_pass(manifest_path: Path, source: Path) -> dict[str, Any]:
    """Fail closed unless every reviewed asset and the exact source still match."""
    manifest = load_manifest(manifest_path)
    review = manifest.get("review")
    if not isinstance(review, dict) or review.get("decision") != "pass":
        raise ValueError("素材视觉审核未通过：必须先调用 view_image 并将 decision 设为 pass")
    records = _asset_records(manifest)
    bad = [r.get("path", "<unknown>") for r in records if r.get("review") != "pass"]
    if bad:
        raise ValueError(f"仍有素材未通过视觉审核: {', '.join(map(str, bad[:5]))}")
    for record in records:
        _staged_original_path(manifest, record)
    if manifest.get("metadataStatus") != "pass":
        raise ValueError("素材权威元数据预检未通过，禁止导入")

    source = source.resolve()
    staged_dir_raw = manifest.get("stagedDir")
    if not isinstance(staged_dir_raw, str):
        raise ValueError("审核清单缺少 stagedDir")
    staged_dir = Path(staged_dir_raw).resolve()
    if not _is_in_staged(source, staged_dir):
        raise ValueError("导入必须使用审核清单 stagedDir 中的原始素材，不能改用外部副本")
    if source.is_dir():
        source_meta = asset_metadata(source)
        source_files = source_meta.get("files")
        if not isinstance(source_files, list) or not source_files:
            raise ValueError("导入目录中没有可审核图片")
        records_by_path = {str(record.get("path")): record for record in records}
        for child in source.rglob("*"):
            if not child.is_file() or child.suffix.lower() not in IMAGE_EXTS:
                continue
            rel = child.relative_to(staged_dir).as_posix()
            record = records_by_path.get(rel)
            if not isinstance(record, dict) or not _record_matches_source(record, child):
                raise ValueError(f"目录中存在未审核或审核后变更的素材: {rel}")
        return source_meta
    rel = source.relative_to(staged_dir).as_posix()
    matches = [
        record
        for record in records
        if record.get("path") == rel and _record_matches_source(record, source)
    ]
    if not matches:
        raise ValueError("审核清单与当前素材不匹配，素材可能已被替换；请重新预检")
    return matches[0]


def verify_image_metadata(record: dict[str, Any], source: Path) -> dict[str, Any]:
    """Re-read source metadata and reject TOCTOU or stale numeric metadata."""
    current = asset_metadata(source)
    if current.get("sha256") != record.get("sha256"):
        raise ValueError("素材哈希在审核后发生变化，请重新审核")
    if current.get("kind") == "image":
        for key in ("width", "height", "frameCount"):
            if key in record and int(record[key]) != int(current[key]):
                raise ValueError(f"权威元数据不一致: {key} 清单={record[key]} 实际={current[key]}")
    return current
