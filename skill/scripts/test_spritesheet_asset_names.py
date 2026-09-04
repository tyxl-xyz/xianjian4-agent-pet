#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""多批次合图命名：防 sprite.webp 撞名覆盖。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from build_pet_json import (
    copy_webp_assets,
    is_debug_part_sheet_name,
    is_generic_sheet_name,
    resolve_sheet_path,
    resolve_webp_dest_names,
)

# make_spritesheet 依赖 Pillow；无 Pillow 时跳过 derive 相关用例
try:
    from make_spritesheet import derive_cli_prefix, derive_prefix_from_names

    _HAS_MAKE_SPRITESHEET = True
except ModuleNotFoundError:
    _HAS_MAKE_SPRITESHEET = False
    derive_cli_prefix = None  # type: ignore[assignment]
    derive_prefix_from_names = None  # type: ignore[assignment]


class TestGenericSheetName(unittest.TestCase):
    def test_sprite_variants(self) -> None:
        self.assertTrue(is_generic_sheet_name("sprite.webp"))
        self.assertTrue(is_generic_sheet_name("sprite.png"))
        self.assertTrue(is_generic_sheet_name("sprite_part0.webp"))
        self.assertTrue(is_generic_sheet_name("sprite_part12.webp"))
        self.assertFalse(is_generic_sheet_name("happy.webp"))
        self.assertFalse(is_generic_sheet_name("idle.webp"))

    def test_debug_part_names(self) -> None:
        self.assertTrue(is_debug_part_sheet_name("happy_part0.webp"))
        self.assertTrue(is_debug_part_sheet_name("sprite_part12.png"))
        self.assertFalse(is_debug_part_sheet_name("happy.png"))
        self.assertFalse(is_debug_part_sheet_name("happy.webp"))


class TestResolveSheetPath(unittest.TestCase):
    def test_declared_png_wins(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "happy.webp").write_bytes(b"webp")
            (root / "happy.png").write_bytes(b"png")
            path, name = resolve_sheet_path(root, "happy", "happy.png")
            self.assertEqual(name, "happy.png")
            self.assertEqual(path.read_bytes(), b"png")

    def test_fallback_png_when_webp_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "happy.png").write_bytes(b"png-only")
            path, name = resolve_sheet_path(root, "happy", None)
            self.assertEqual(name, "happy.png")
            self.assertEqual(path.read_bytes(), b"png-only")

    def test_missing_both_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(SystemExit) as ctx:
                resolve_sheet_path(root, "happy", "happy.webp")
            self.assertIn("happy.png", str(ctx.exception))


@unittest.skipUnless(_HAS_MAKE_SPRITESHEET, "需要 Pillow（make_spritesheet）")
class TestDerivePrefix(unittest.TestCase):
    def test_roundtrip_middle_name(self) -> None:
        self.assertEqual(
            derive_prefix_from_names(["idle_to_happy", "happy", "happy_to_idle"]),
            "happy",
        )

    def test_single_name(self) -> None:
        self.assertEqual(derive_prefix_from_names(["idle"]), "idle")

    def test_cli_uses_output_dir_basename(self) -> None:
        self.assertEqual(
            derive_cli_prefix(
                output_dir=r"D:\tmp\pet-run\_build\working",
                names=["idle_to_working", "working", "working_to_idle"],
                explicit=None,
            ),
            "working",
        )

    def test_cli_explicit_wins(self) -> None:
        self.assertEqual(
            derive_cli_prefix(
                output_dir=r"D:\tmp\pet-run\_build\working",
                names=["idle_to_working", "working", "working_to_idle"],
                explicit="custom_sheet",
            ),
            "custom_sheet",
        )

    def test_cli_weak_outdir_falls_back_to_names(self) -> None:
        self.assertEqual(
            derive_cli_prefix(
                output_dir="/tmp/output",
                names=["idle_to_fail", "fail", "fail_to_idle"],
                explicit=None,
            ),
            "fail",
        )


class TestResolveAndCopy(unittest.TestCase):
    def _clip(
        self,
        *,
        action_id: str,
        kind: str,
        webp: Path,
        sheet: str = "sprite.webp",
    ) -> dict:
        return {
            "id": action_id,
            "kind": kind,
            "webp_path": webp,
            "entry": {
                "name": action_id,
                "spritesheet": sheet,
                "frames": 4,
                "columns": 4,
                "fps": 24,
            },
        }

    def test_rename_generic_sprite_to_batch_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build"
            user = root / "user"
            build.mkdir()
            user.mkdir()
            src = build / "sprite.webp"
            src.write_bytes(b"happy-sheet-bytes")

            clips = [
                self._clip(action_id="idle_to_happy", kind="transition", webp=src),
                self._clip(action_id="happy", kind="atomic", webp=src),
                self._clip(action_id="happy_to_idle", kind="transition", webp=src),
            ]
            resolve_webp_dest_names(clips, user)
            for c in clips:
                self.assertEqual(c["entry"]["spritesheet"], "happy.webp")
                self.assertEqual(c["dest_name"], "happy.webp")

            copy_webp_assets(clips, user)
            self.assertTrue((user / "happy.webp").is_file())
            self.assertFalse((user / "sprite.webp").exists())
            self.assertEqual((user / "happy.webp").read_bytes(), b"happy-sheet-bytes")

    def test_second_batch_does_not_overwrite_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = root / "user"
            user.mkdir()

            idle_src = root / "idle" / "sprite.webp"
            idle_src.parent.mkdir()
            idle_src.write_bytes(b"idle-bytes")
            idle_clips = [self._clip(action_id="idle", kind="atomic", webp=idle_src)]
            resolve_webp_dest_names(idle_clips, user)
            copy_webp_assets(idle_clips, user)
            self.assertEqual((user / "idle.webp").read_bytes(), b"idle-bytes")

            happy_src = root / "happy" / "sprite.webp"
            happy_src.parent.mkdir()
            happy_src.write_bytes(b"happy-bytes")
            happy_clips = [
                self._clip(action_id="idle_to_happy", kind="transition", webp=happy_src),
                self._clip(action_id="happy", kind="atomic", webp=happy_src),
                self._clip(action_id="happy_to_idle", kind="transition", webp=happy_src),
            ]
            resolve_webp_dest_names(happy_clips, user)
            copy_webp_assets(happy_clips, user)

            self.assertEqual((user / "idle.webp").read_bytes(), b"idle-bytes")
            self.assertEqual((user / "happy.webp").read_bytes(), b"happy-bytes")
            self.assertFalse((user / "sprite.webp").exists())

    def test_hard_collision_different_content_same_dest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = root / "user"
            user.mkdir()
            (user / "happy.webp").write_bytes(b"old-happy")

            src = root / "sprite.webp"
            src.write_bytes(b"new-different")
            clips = [
                self._clip(action_id="idle_to_happy", kind="transition", webp=src),
                self._clip(action_id="happy", kind="atomic", webp=src),
                self._clip(action_id="happy_to_idle", kind="transition", webp=src),
            ]
            with self.assertRaises(SystemExit) as ctx:
                resolve_webp_dest_names(clips, user)
            self.assertIn("happy.webp", str(ctx.exception))

    def test_same_content_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = root / "user"
            user.mkdir()
            payload = b"same-bytes"
            (user / "happy.webp").write_bytes(payload)
            src = root / "sprite.webp"
            src.write_bytes(payload)
            clips = [
                self._clip(action_id="happy", kind="atomic", webp=src),
            ]
            resolve_webp_dest_names(clips, user)
            copy_webp_assets(clips, user)
            self.assertEqual((user / "happy.webp").read_bytes(), payload)

    def test_oversized_png_renamed_and_copied(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / "build"
            user = root / "user"
            build.mkdir()
            user.mkdir()
            src = build / "sprite.png"
            src.write_bytes(b"oversized-png")
            # 调试分块不应被当作主图
            (build / "sprite_part0.webp").write_bytes(b"part-debug")

            clips = [
                self._clip(
                    action_id="idle_to_happy",
                    kind="transition",
                    webp=src,
                    sheet="sprite.png",
                ),
                self._clip(
                    action_id="happy",
                    kind="atomic",
                    webp=src,
                    sheet="sprite.png",
                ),
                self._clip(
                    action_id="happy_to_idle",
                    kind="transition",
                    webp=src,
                    sheet="sprite.png",
                ),
            ]
            resolve_webp_dest_names(clips, user)
            for c in clips:
                self.assertEqual(c["entry"]["spritesheet"], "happy.png")
                self.assertEqual(c["dest_name"], "happy.png")

            copy_webp_assets(clips, user)
            self.assertTrue((user / "happy.png").is_file())
            self.assertEqual((user / "happy.png").read_bytes(), b"oversized-png")
            self.assertFalse((user / "sprite.png").exists())
            self.assertFalse((user / "sprite_part0.webp").exists())
            self.assertFalse((user / "happy_part0.webp").exists())

    def test_reject_debug_part_as_main(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = root / "user"
            user.mkdir()
            src = root / "happy_part0.webp"
            src.write_bytes(b"part")
            clips = [self._clip(action_id="happy", kind="atomic", webp=src, sheet="happy_part0.webp")]
            with self.assertRaises(SystemExit) as ctx:
                resolve_webp_dest_names(clips, user)
            self.assertIn("调试分块", str(ctx.exception))

    def test_copy_missing_source_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            user = root / "user"
            user.mkdir()
            missing = root / "happy.png"
            clips = [
                self._clip(action_id="happy", kind="atomic", webp=missing, sheet="happy.png"),
            ]
            resolve_webp_dest_names(clips, user)
            with self.assertRaises(SystemExit) as ctx:
                copy_webp_assets(clips, user)
            self.assertIn("不存在", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
