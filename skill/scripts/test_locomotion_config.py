#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""locomotion_config：跑步素材 → sequences + wander baseMode。"""

from __future__ import annotations

import unittest

from locomotion_config import (
    RUN_LEFT_PLAY,
    RUN_RIGHT_PLAY,
    build_locomotion_enrichment,
    build_locomotion_sequences,
    merge_wander_into_base_modes,
)
from behaviors_format import fill_missing_locomotion


class LocomotionConfigTest(unittest.TestCase):
    def test_build_sequences_when_both_runs_exist(self) -> None:
        actions = {
            "atomic": {
                "idle": {"name": "待机"},
                "running_left": {"name": "向左跑"},
                "running_right": {"name": "向右跑"},
            }
        }
        seqs = build_locomotion_sequences(actions, {})
        self.assertIn(RUN_LEFT_PLAY, seqs)
        self.assertIn(RUN_RIGHT_PLAY, seqs)
        self.assertEqual(seqs[RUN_LEFT_PLAY]["groups"][0]["hold"]["action"], "running_left")
        self.assertEqual(
            seqs[RUN_RIGHT_PLAY]["groups"][0]["hold"]["move"]["target"]["edge"],
            "right",
        )

    def test_no_sequences_without_both_directions(self) -> None:
        actions = {"atomic": {"running_right": {}, "idle": {}}}
        self.assertEqual(build_locomotion_sequences(actions, {}), {})

    def test_enrich_incoming_sequences_only(self) -> None:
        patch = {
            "actions": {
                "atomic": {
                    "running_left": {},
                    "running_right": {},
                }
            },
            "sequences": {},
        }
        incoming = build_locomotion_enrichment(patch, existing_seq_ids=set())
        self.assertIn("sequences", incoming)
        self.assertNotIn("baseModes", incoming)

    def test_merge_wander_base_mode(self) -> None:
        patch = {
            "defaultActivity": "idle",
            "actions": {
                "atomic": {
                    "running_left": {},
                    "running_right": {},
                }
            },
            "sequences": {
                RUN_LEFT_PLAY: {},
                RUN_RIGHT_PLAY: {},
            },
        }
        bm = merge_wander_into_base_modes(patch, {})
        self.assertIsNotNone(bm)
        assert bm is not None
        wander = next(a for a in bm["actions"] if a["id"] == "wander")
        self.assertTrue(wander.get("directional"))
        self.assertEqual(wander["sequenceLeft"], RUN_LEFT_PLAY)
        self.assertEqual(wander["sequenceRight"], RUN_RIGHT_PLAY)

    def test_wander_idempotent(self) -> None:
        patch = {
            "baseModes": {
                "enabled": True,
                "homeActivity": "idle",
                "actions": [{"id": "wander", "directional": True}],
            },
            "actions": {"atomic": {"running_left": {}, "running_right": {}}},
            "sequences": {RUN_LEFT_PLAY: {}, RUN_RIGHT_PLAY: {}},
        }
        self.assertIsNone(merge_wander_into_base_modes(patch, {}))

    def test_behaviors_and_wander_together(self) -> None:
        actions = {
            "atomic": {
                "idle": {},
                "running_left": {},
                "running_right": {},
            }
        }
        behaviors = fill_missing_locomotion({}, actions)
        self.assertEqual(behaviors["dragging_left"], "running_left")
        self.assertEqual(behaviors["walking"], "running_right")
        patch = {"actions": actions, "sequences": build_locomotion_sequences(actions, {})}
        bm = merge_wander_into_base_modes(patch, {})
        self.assertIsNotNone(bm)


if __name__ == "__main__":
    unittest.main()
