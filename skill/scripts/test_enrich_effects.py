#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enrich 自动写入 atomic.effect 烟测。"""

from __future__ import annotations

import unittest

from enrich_pet_patch import (
    build_atomic_effect_add,
    build_enrichment,
    infer_effect_for_atomic,
)


class TestEffectEnrich(unittest.TestCase):
    def test_infer_by_id_and_name(self) -> None:
        self.assertEqual(infer_effect_for_atomic("idle", {"name": "发呆"}), "idle")
        self.assertEqual(infer_effect_for_atomic("sleep", {"name": "趴着睡觉"}), "sleep")
        self.assertEqual(infer_effect_for_atomic("hang", {"name": "悬垂"}), "dizzy")
        self.assertEqual(infer_effect_for_atomic("walk_right", {"name": "向右走"}), "walking")
        self.assertIsNone(infer_effect_for_atomic("mystery_pose", {"name": "神秘姿势"}))

    def test_add_only_missing_effect(self) -> None:
        patch = {
            "actions": {
                "atomic": {
                    "idle": {"name": "发呆", "file": "idle.webp"},
                    "happy": {"name": "开心", "effect": "happy"},
                    "zzz": {"name": "睡觉"},
                },
                "transition": {
                    "idle_to_happy": {"name": "切入开心"},
                },
            }
        }
        add = build_atomic_effect_add(patch)
        assert add is not None
        self.assertEqual(add["atomic"]["idle"]["effect"], "idle")
        self.assertEqual(add["atomic"]["zzz"]["effect"], "sleep")
        self.assertNotIn("happy", add["atomic"])

    def test_build_enrichment_includes_effects(self) -> None:
        patch = {
            "actions": {
                "atomic": {"idle": {"name": "idle"}, "happy": {"name": "开心"}},
                "transition": {},
            }
        }
        incoming = build_enrichment(patch)
        self.assertIn("actions", incoming)
        self.assertEqual(incoming["actions"]["atomic"]["idle"]["effect"], "idle")
        self.assertEqual(incoming["actions"]["atomic"]["happy"]["effect"], "happy")

    def test_idempotent_skips_existing_effect(self) -> None:
        patch = {
            "actions": {
                "atomic": {"idle": {"name": "发呆", "effect": "micro"}},
            }
        }
        self.assertIsNone(build_atomic_effect_add(patch))


if __name__ == "__main__":
    unittest.main()
