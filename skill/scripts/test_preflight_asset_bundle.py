#!/usr/bin/env python3
"""预检清单只把图片交给 view_image。"""

from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import preflight_asset_bundle
from asset_review import sha256_file


def _fake_image_metadata(path: Path) -> dict[str, object]:
    return {
        "kind": "image",
        "format": path.suffix.lower().lstrip("."),
        "width": 2,
        "height": 2,
        "frameCount": 1,
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


class TestPreflightReviewScope(unittest.TestCase):
    def test_manifest_reviews_images_and_records_non_visual_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "bundle.zip"
            with zipfile.ZipFile(source, "w") as archive:
                archive.writestr("assets/reference.PNG", b"png-bytes")
                archive.writestr("assets/action.mp4", b"video-bytes")
                archive.writestr("assets/README.txt", b"notes")

            with patch.object(preflight_asset_bundle, "asset_metadata", _fake_image_metadata):
                manifest_path = preflight_asset_bundle.create_manifest(source, root / "review")

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual([asset["path"] for asset in manifest["assets"]], ["assets/reference.PNG"])
            self.assertEqual(
                manifest["assets"][0]["reviewPaths"],
                [str((root / "review" / "staged" / "assets" / "reference.PNG").resolve())],
            )
            self.assertEqual(
                {item["path"] for item in manifest["nonVisualFiles"]},
                {"assets/action.mp4", "assets/README.txt"},
            )

    def test_review_path_cannot_be_changed_to_non_image(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            staged = Path(tmp) / "staged"
            staged.mkdir()
            video = staged / "action.mp4"
            video.write_bytes(b"video")
            record = {
                "path": "action.mp4",
                "reviewPaths": [str(video.resolve())],
            }
            self.assertFalse(preflight_asset_bundle._review_paths_complete([record], staged))


if __name__ == "__main__":
    unittest.main()
