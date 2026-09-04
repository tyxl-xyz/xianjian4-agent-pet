#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""默认三态组合：enrich 门禁；禁止 generate_sequences 顶替 enrich。"""

from __future__ import annotations

import unittest

from enrich_pet_patch import (
    build_enrichment,
    check_default_combo_complete,
)
from generate_sequences import assert_enrich_before_random_sequences


def _full_actions() -> dict:
    atomic = {
        "idle": {"name": "发呆", "spritesheet": "idle.webp", "frames": 4, "columns": 4},
        "working": {"name": "工作", "spritesheet": "working.webp", "frames": 4, "columns": 4},
        "fail": {"name": "失败", "spritesheet": "fail.webp", "frames": 4, "columns": 4},
        "happy": {"name": "开心", "spritesheet": "happy.webp", "frames": 4, "columns": 4},
    }
    transition = {}
    for state in ("working", "fail", "happy"):
        transition[f"idle_to_{state}"] = {
            "name": f"to {state}",
            "spritesheet": f"{state}.webp",
            "frames": 2,
            "columns": 4,
            "playOnce": True,
        }
        transition[f"{state}_to_idle"] = {
            "name": f"from {state}",
            "spritesheet": f"{state}.webp",
            "frames": 2,
            "columns": 4,
            "playOnce": True,
        }
    return {"atomic": atomic, "transition": transition}


class TestEnrichComboCheck(unittest.TestCase):
    def test_actions_only_not_complete(self) -> None:
        patch = {
            "id": "astro",
            "defaultActivity": "idle",
            "actions": _full_actions(),
            "sequences": {},
            "behaviors": {},
        }
        report = check_default_combo_complete(patch)
        self.assertFalse(report["ok"])
        self.assertTrue(report["applicable"])
        joined = " ".join(report["errors"])
        self.assertIn("working_play", joined)
        self.assertIn("fail_play", joined)
        self.assertIn("happy_play", joined)

    def test_enrich_then_check_ok(self) -> None:
        patch = {
            "id": "astro",
            "defaultActivity": "idle",
            "actions": _full_actions(),
            "sequences": {},
            "behaviors": {},
        }
        incoming = build_enrichment(patch)
        # 模拟 merge：把增量并入
        patch["sequences"] = {**(patch.get("sequences") or {}), **incoming.get("sequences", {})}
        patch["behaviors"] = incoming.get("behaviors", {})
        report = check_default_combo_complete(patch)
        self.assertEqual(report["errors"], [], msg=report)
        self.assertTrue(report["ok"])

    def test_default_triplet_sequence_chinese_names(self) -> None:
        patch = {
            "id": "astro",
            "defaultActivity": "idle",
            "actions": _full_actions(),
            "sequences": {},
            "behaviors": {},
        }
        seqs = build_enrichment(patch)["sequences"]
        self.assertEqual(seqs["working_play"]["name"], "工作一下")
        self.assertEqual(seqs["fail_play"]["name"], "失败一下")
        self.assertEqual(seqs["happy_play"]["name"], "开心一下")

    def test_triplet_label_fallback_when_atomic_name_missing(self) -> None:
        actions = _full_actions()
        for state in ("working", "fail", "happy"):
            actions["atomic"][state].pop("name", None)
        patch = {
            "id": "astro",
            "defaultActivity": "idle",
            "actions": actions,
            "sequences": {},
            "behaviors": {},
        }
        seqs = build_enrichment(patch)["sequences"]
        self.assertEqual(seqs["working_play"]["name"], "工作一下")
        self.assertEqual(seqs["fail_play"]["name"], "失败一下")
        self.assertEqual(seqs["happy_play"]["name"], "开心一下")

    def test_idle_play_alone_not_enough(self) -> None:
        patch = {
            "id": "astro",
            "defaultActivity": "idle",
            "actions": _full_actions(),
            "sequences": {
                "idle_play": {
                    "name": "发呆",
                    "steps": [{"action": "idle", "duration": "clip"}],
                }
            },
            "behaviors": {},
        }
        report = check_default_combo_complete(patch)
        self.assertFalse(report["ok"])
        self.assertIn("working_play", " ".join(report["errors"]))

    def test_not_applicable_without_triplets(self) -> None:
        patch = {
            "actions": {
                "atomic": {"idle": {"name": "发呆"}, "wave": {"name": "挥手"}},
                "transition": {},
            },
            "sequences": {},
        }
        report = check_default_combo_complete(patch)
        self.assertFalse(report["applicable"])
        # 无默认三态可 enrich 时不挡「仅 atomic 导入」场景
        self.assertTrue(report["ok"])

    def test_rejects_empty_actions_reference_only_package(self) -> None:
        report = check_default_combo_complete(
            {
                "actions": {"atomic": {}, "transition": {}},
                "sequences": {},
                "behaviors": {},
            }
        )
        self.assertFalse(report["ok"])
        self.assertIn("actions 为空", " ".join(report["errors"]))


class TestGenerateSequencesGate(unittest.TestCase):
    def test_blocks_when_enrich_missing(self) -> None:
        pet = {
            "defaultActivity": "idle",
            "actions": _full_actions(),
            "sequences": {"idle_play": {"name": "x", "steps": []}},
            "behaviors": {},
        }
        with self.assertRaises(SystemExit) as ctx:
            assert_enrich_before_random_sequences(pet)
        msg = str(ctx.exception)
        self.assertIn("enrich", msg.lower())
        self.assertIn("working_play", msg)

    def test_allows_when_enrich_done(self) -> None:
        pet = {
            "defaultActivity": "idle",
            "actions": _full_actions(),
            "sequences": {
                "working_play": {"name": "w", "steps": []},
                "fail_play": {"name": "f", "steps": []},
                "happy_play": {"name": "h", "steps": []},
            },
            "behaviors": {
                "working": "working_play",
                "success": "happy_play",
                "fail": "fail_play",
            },
        }
        assert_enrich_before_random_sequences(pet)  # 不抛


if __name__ == "__main__":
    unittest.main()
