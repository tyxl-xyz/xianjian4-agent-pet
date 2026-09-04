#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全解包、权威元数据预检和视觉审核清单生成。

预检阶段绝不写入桌宠 ``user/``。对 ZIP 只做受限解包；对每个可解析图片
读取真实尺寸和动画帧数。只有图片文件会进入 ``assets[*].reviewPaths`` 并送给
``view_image``；ZIP 中的非图片文件只进入 ``nonVisualFiles`` 清单，不调用
``view_image``。图片原格式无法可靠审核时，必须拒绝导入，不能转换格式绕过门禁。
审核结果由 ``--approve`` / ``--reject`` 写回清单，导入脚本随后验证清单
和源文件哈希，防止审核后替换素材。

示例：
  python preflight_asset_bundle.py --input upload.zip --out-dir ./_asset-review
  # 逐个 view_image 清单中的原始上传文件后：
  python preflight_asset_bundle.py --manifest ./_asset-review/review-manifest.json --approve
"""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from asset_review import IMAGE_EXTS, asset_metadata, sha256_file, sha256_tree  # noqa: E402

MAX_ENTRIES = 5000
MAX_ENTRY_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 512 * 1024 * 1024
MAX_COMPRESSION_RATIO = 1000
MAX_PIXELS = 50_000_000
ARCHIVE_EXTS = {".zip", ".rar", ".7z", ".tar", ".gz", ".tgz", ".bz2", ".xz"}


def _safe_member_name(name: str) -> PurePosixPath:
    if not name or "\x00" in name:
        raise ValueError("ZIP 含空文件名或 NUL 字符")
    normalized = name.replace("\\", "/")
    rel = PurePosixPath(normalized)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError(f"ZIP 路径不安全: {name}")
    return rel


def safe_extract_zip(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    total = 0
    with zipfile.ZipFile(source) as archive:
        infos = archive.infolist()
        if len(infos) > MAX_ENTRIES:
            raise ValueError(f"ZIP 文件数超过上限 {MAX_ENTRIES}")
        for info in infos:
            rel = _safe_member_name(info.filename)
            if rel.suffix.lower() in ARCHIVE_EXTS:
                raise ValueError(f"不支持嵌套压缩包，避免遗漏其中素材: {info.filename}")
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                raise ValueError(f"ZIP 含软链接，拒绝解包: {info.filename}")
            if info.file_size > MAX_ENTRY_BYTES:
                raise ValueError(f"ZIP 单文件过大: {info.filename}")
            total += info.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError(f"ZIP 解压后总大小超过上限 {MAX_TOTAL_BYTES} bytes")
            if info.compress_size and info.file_size / info.compress_size > MAX_COMPRESSION_RATIO:
                raise ValueError(f"ZIP 压缩比异常，疑似 Zip Bomb: {info.filename}")

            target = destination.joinpath(*rel.parts)
            target_parent = target.parent.resolve()
            if destination.resolve() not in target_parent.parents and target_parent != destination.resolve():
                raise ValueError(f"ZIP 路径越界: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as src, target.open("wb") as dst:
                shutil.copyfileobj(src, dst, length=1024 * 1024)


def _image_files(root: Path) -> list[Path]:
    """仅图片是视觉审核对象；视频、文本、音频等不得送给 view_image。"""
    return sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS
    )


def _non_visual_files(root: Path) -> list[dict[str, Any]]:
    """保留非图片文件的完整性清单，但不生成 reviewPaths。"""
    records: list[dict[str, Any]] = []
    for path in sorted(
        p for p in root.rglob("*") if p.is_file() and p.suffix.lower() not in IMAGE_EXTS
    ):
        records.append(
            {
                "path": path.relative_to(root).as_posix(),
                "extension": path.suffix.lower(),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def _copy_directory_without_symlinks(source: Path, staged: Path) -> None:
    for path in source.rglob("*"):
        if path.is_symlink():
            raise ValueError(f"素材目录含软链接，拒绝预检: {path}")
        if path.is_file() and path.suffix.lower() in ARCHIVE_EXTS:
            raise ValueError(f"素材目录含嵌套压缩包，避免遗漏其中素材: {path}")
    shutil.copytree(source, staged, symlinks=False)


def _expected_review_path(staged: Path, record: dict[str, Any]) -> str:
    """Return the one allowed review path: the staged original file itself."""
    raw = record.get("path")
    if not isinstance(raw, str) or not raw:
        raise ValueError("素材清单缺少相对路径")
    rel = PurePosixPath(raw)
    if rel.is_absolute() or any(part in {"", ".", ".."} for part in rel.parts):
        raise ValueError(f"素材清单路径不安全: {raw}")
    if rel.suffix.lower() not in IMAGE_EXTS:
        raise ValueError(f"审核路径必须是图片文件: {raw}")
    expected = staged.joinpath(*rel.parts).resolve()
    if staged.resolve() not in expected.parents or not expected.is_file():
        raise ValueError(f"审核原始文件不存在或越界: {raw}")
    return str(expected)


def _review_paths_complete(assets: list[dict[str, Any]], staged: Path) -> bool:
    """Accept only one direct staged-original path per visual asset."""
    try:
        return all(asset.get("reviewPaths") == [_expected_review_path(staged, asset)] for asset in assets)
    except ValueError:
        return False


def _build_manifest(source: Path, staged: Path) -> dict[str, Any]:
    files = _image_files(staged)
    if not files:
        raise ValueError("压缩包/目录中没有可审核的 PNG/JPEG/WebP/GIF 等视觉素材")
    assets: list[dict[str, Any]] = []
    metadata_ok = True
    for file_path in files:
        rel = file_path.relative_to(staged).as_posix()
        record: dict[str, Any] = {"path": rel, "review": "pending"}
        try:
            metadata = asset_metadata(file_path)
            if metadata.get("width", 0) * metadata.get("height", 0) > MAX_PIXELS:
                raise ValueError(f"图片像素数超过上限 {MAX_PIXELS}")
            record.update(metadata)
            record["reviewPaths"] = [str(file_path.resolve())]
        except Exception as exc:  # noqa: BLE001 - manifest must expose manual blockers
            metadata_ok = False
            record.update(
                {
                    "metadataError": str(exc),
                    "review": "manual",
                    "reviewPaths": [],
                }
            )
        assets.append(record)

    source_metadata = asset_metadata(staged) if source.is_dir() else None
    return {
        "schemaVersion": 1,
        "source": {
            "path": str(source.resolve()),
            "kind": "zip" if source.suffix.lower() == ".zip" else "directory" if source.is_dir() else "file",
            "sha256": sha256_tree(source) if source.is_dir() else sha256_file(source),
        },
        "stagedDir": str(staged.resolve()),
        "nonVisualFiles": _non_visual_files(staged),
        **({"sourceMetadata": source_metadata} if source.is_dir() else {}),
        "metadataStatus": "pass" if metadata_ok else "manual",
        "assets": assets,
        "review": {
            "decision": "pending",
            "reviewedBy": None,
            "reviewPathsComplete": _review_paths_complete(assets, staged),
        },
    }


def create_manifest(source: Path, out_dir: Path) -> Path:
    source = source.resolve()
    if not source.exists():
        raise FileNotFoundError(source)
    out_dir = out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    staged = out_dir / "staged"
    if staged.exists():
        raise ValueError(
            f"预检工作区已存在 staged，拒绝覆盖: {staged}；请使用新的 --out-dir"
        )
    if source.is_file() and source.suffix.lower() == ".zip":
        safe_extract_zip(source, staged)
    elif source.is_dir():
        _copy_directory_without_symlinks(source, staged)
    else:
        raise ValueError("输入必须是 ZIP 或素材目录")
    manifest = _build_manifest(source, staged)
    path = out_dir / "review-manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def update_decision(manifest_path: Path, decision: str, reviewed_by: str) -> None:
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if data.get("metadataStatus") != "pass":
        raise ValueError("元数据预检未通过，不能批准素材")
    assets = data.get("assets")
    if not isinstance(assets, list) or not assets:
        raise ValueError("审核清单缺少 assets")
    staged_raw = data.get("stagedDir")
    if not isinstance(staged_raw, str):
        raise ValueError("审核清单缺少 stagedDir")
    staged = Path(staged_raw).resolve()
    if decision == "pass" and not all(isinstance(asset, dict) for asset in assets):
        raise ValueError("审核清单 assets 格式无效")
    if decision == "pass" and not _review_paths_complete(assets, staged):
        raise ValueError("审核路径必须逐个指向 staged/ 中的原始上传文件；不能批准派生预览或转码副本")
    for asset in assets:
        asset["review"] = "pass" if decision == "pass" else "reject"
    data["review"] = {
        "decision": decision,
        "reviewedBy": reviewed_by,
        "reviewPathsComplete": _review_paths_complete(assets, staged),
    }
    manifest_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="上传素材安全解包、元数据预检与 view_image 审核清单")
    parser.add_argument("--input", type=Path, help="ZIP 或素材目录；创建预检清单")
    parser.add_argument("--out-dir", type=Path, help="预检工作区目录")
    parser.add_argument("--manifest", type=Path, help="已有 review-manifest.json")
    decision = parser.add_mutually_exclusive_group()
    decision.add_argument("--approve", action="store_true", help="view_image 全部通过后批准")
    decision.add_argument("--reject", action="store_true", help="拒绝本批素材")
    parser.add_argument("--reviewed-by", default="view_image")
    args = parser.parse_args()

    if args.input:
        if not args.out_dir:
            parser.error("--input 需要 --out-dir")
        path = create_manifest(args.input, args.out_dir)
        print(path)
        return 0
    if not args.manifest or not (args.approve or args.reject):
        parser.error("更新审核结果需要 --manifest 与 --approve/--reject")
    update_decision(args.manifest, "pass" if args.approve else "reject", args.reviewed_by)
    print(args.manifest)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
