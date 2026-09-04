#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""behaviors 字符串契约 + Codex locomotion 默认补全。"""

from __future__ import annotations

import unittest

from behaviors_format import (
    build_locomotion_behaviors,
    coerce_behavior_value,
    fill_missing_locomotion,
    sanitize_behaviors_map,
)
from enrich_pet_patch import build_enrichment


class TestCoerceBehaviorValue(unittest.TestCase):
    def test_string_ok(self) -> None:
        self.assertEqual(coerce_behavior_value("  working_play "), "working_play")

    def test_object_actions_coerced(self) -> None:
        val = {"actions": [{"id": "working_play", "weight": 1}]}
        self.assertEqual(coerce_behavior_value(val), "working_play")

    def test_object_picks_highest_weight(self) -> None:
        val = {
            "actions": [
                {"id": "a_play", "weight": 1},
                {"id": "b_play", "weight": 9},
            ]
        }
        self.assertEqual(coerce_behavior_value(val), "b_play")

    def test_invalid_none(self) -> None:
        self.assertIsNone(coerce_behavior_value(123))
        self.assertIsNone(coerce_behavior_value({"actions": []}))


class TestSanitizeBehaviors(unittest.TestCase):
    def test_strict_rejects_uncoercible(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            sanitize_behaviors_map({"working": [1, 2]}, strict=True)
        self.assertIn("behaviors.working", str(ctx.exception))
        self.assertIn("字符串", str(ctx.exception))

    def test_strict_coerces_object(self) -> None:
        clean, warns = sanitize_behaviors_map(
            {"working": {"actions": [{"id": "working_play", "weight": 1}]}},
            strict=True,
        )
        self.assertEqual(clean, {"working": "working_play"})
        self.assertTrue(any("自动规范" in w for w in warns))

    def test_lenient_drops_garbage(self) -> None:
        clean, warns = sanitize_behaviors_map(
            {"working": "ok", "bad": {"nope": True}},
            strict=False,
        )
        self.assertEqual(clean, {"working": "ok"})
        self.assertTrue(warns)


class TestLocomotion(unittest.TestCase):
    def test_codex_running_ids(self) -> None:
        actions = {
            "atomic": {
                "idle": {},
                "running_right": {},
                "running_left": {},
            }
        }
        loco = build_locomotion_behaviors(actions)
        self.assertEqual(loco["walking"], "running_right")
        self.assertEqual(loco["walking_flip"], "running_left")
        self.assertEqual(loco["dragging_left"], "running_left")
        self.assertEqual(loco["dragging_right"], "running_right")
        self.assertEqual(loco["dragging"], "idle")
        self.assertEqual(loco["moving_to_target"], "running_right")
        self.assertEqual(loco["moving_to_target_flip"], "running_left")

    def test_little_meng_running_as_left(self) -> None:
        actions = {"atomic": {"running": {}, "running_right": {}, "idle": {}}}
        loco = build_locomotion_behaviors(actions)
        self.assertEqual(loco["walking_flip"], "running")
        self.assertEqual(loco["walking"], "running_right")

    def test_fill_missing_preserves_existing(self) -> None:
        actions = {"atomic": {"idle": {}, "running_right": {}, "running_left": {}}}
        filled = fill_missing_locomotion(
            {"working": "working_play", "walking": "custom_run"},
            actions,
        )
        self.assertEqual(filled["working"], "working_play")
        self.assertEqual(filled["walking"], "custom_run")
        self.assertEqual(filled["walking_flip"], "running_left")


class TestEnrichFixesBadBehaviors(unittest.TestCase):
    def test_enrich_coerces_object_and_adds_loco(self) -> None:
        patch = {
            "id": "shinchan",
            "defaultActivity": "idle",
            "actions": {
                "atomic": {
                    "idle": {"name": "待机"},
                    "running_right": {"name": "右跑"},
                    "running_left": {"name": "左跑"},
                    "working": {"name": "工作"},
                },
                "transition": {},
            },
            "sequences": {
                "working_play": {"name": "工作", "groups": []},
            },
            "behaviors": {
                "working": {"actions": [{"id": "working_play", "weight": 1}]},
            },
        }
        incoming = build_enrichment(patch)
        beh = incoming["behaviors"]
        self.assertEqual(beh["working"], "working_play")
        self.assertEqual(beh["walking"], "running_right")
        self.assertEqual(beh["walking_flip"], "running_left")
        self.assertEqual(beh["dragging"], "idle")
        self.assertNotIsInstance(beh["working"], dict)


if __name__ == "__main__":
    unittest.main()
