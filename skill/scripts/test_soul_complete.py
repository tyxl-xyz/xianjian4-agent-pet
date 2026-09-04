#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""soul.json 完备性硬门禁。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from write_soul_patch import (
    SOUL_REQUIRED_KEYS,
    default_soul_from_pet,
    validate_soul_errors,
    write_soul,
)


class TestValidateSoulErrors(unittest.TestCase):
    def test_simplified_handwritten_fails(self) -> None:
        slim = {
            "version": 1,
            "name": "宇航小兽",
            "personality": "活泼好奇",
            "appearance": "白色宇航服",
            "creator": "lingxi",
        }
        errs = validate_soul_errors(slim)
        for key in SOUL_REQUIRED_KEYS:
            self.assertTrue(
                any(key in e for e in errs),
                f"应报告缺少 {key}: {errs}",
            )

    def test_from_pet_template_ok(self) -> None:
        soul = default_soul_from_pet(
            {"id": "astro", "displayName": "宇航小兽", "description": "太空小兽"}
        )
        self.assertEqual(validate_soul_errors(soul), [])

    def test_empty_greetings_fails(self) -> None:
        soul = default_soul_from_pet({"displayName": "猫"})
        soul["greetings"] = []
        errs = validate_soul_errors(soul)
        self.assertTrue(any("greetings" in e for e in errs))

    def test_missing_reaction_bucket_fails(self) -> None:
        soul = default_soul_from_pet({"displayName": "猫"})
        del soul["reactions"]["onFail"]
        errs = validate_soul_errors(soul)
        self.assertTrue(any("onFail" in e for e in errs))

    def test_empty_user_name_fails(self) -> None:
        soul = default_soul_from_pet({"displayName": "猫"})
        soul["userName"] = "  "
        errs = validate_soul_errors(soul)
        self.assertTrue(any("userName" in e for e in errs))


class TestWriteSoulHardGate(unittest.TestCase):
    def test_refuse_incomplete_write(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            user = Path(tmp) / "user"
            user.mkdir()
            soul_path = user / "soul.json"
            info = {
                "userDir": str(user),
                "soulJson": str(soul_path),
                "patch": str(user / "pet.patch.json"),
                "mode": "user-only",
            }
            with mock.patch("write_soul_patch.ensure_user_dir", return_value=info):
                with self.assertRaises(SystemExit) as ctx:
                    write_soul(
                        "astro-mascot",
                        {
                            "name": "宇航小兽",
                            "personality": "活泼",
                            "appearance": "宇航服",
                        },
                    )
            self.assertIn("soul.json 不完备", str(ctx.exception))
            self.assertFalse(soul_path.exists())

    def test_from_pet_merge_upgrades_slim_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            user = Path(tmp) / "user"
            user.mkdir()
            soul_path = user / "soul.json"
            soul_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "name": "宇航小兽",
                        "personality": "活泼好奇",
                        "appearance": "白色宇航服",
                        "creator": "lingxi",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            patch_path = user / "pet.patch.json"
            patch_path.write_text(
                json.dumps(
                    {
                        "id": "astro-mascot",
                        "displayName": "宇航小兽",
                        "description": "太空小兽",
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            info = {
                "userDir": str(user),
                "soulJson": str(soul_path),
                "patch": str(patch_path),
                "mode": "user-only",
            }
            template = default_soul_from_pet(
                {"id": "astro-mascot", "displayName": "宇航小兽", "description": "太空小兽"}
            )
            with mock.patch("write_soul_patch.ensure_user_dir", return_value=info):
                report = write_soul("astro-mascot", template, replace=False)
            self.assertTrue(report["ok"])
            data = json.loads(soul_path.read_text(encoding="utf-8"))
            self.assertEqual(validate_soul_errors(data), [])
            # 保留 Agent 额外字段
            self.assertEqual(data.get("personality"), "活泼好奇")
            self.assertEqual(data.get("name"), "宇航小兽")


if __name__ == "__main__":
    unittest.main()
