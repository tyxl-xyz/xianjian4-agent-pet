#!/usr/bin/env python3
"""创建自定义宠的动作交付门禁。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from action_readiness import check_actions_ready


def _full_pet(*, frames: int = 2) -> dict:
    atomics = {
        "idle": {"spritesheet": "idle.webp", "frames": frames},
        "working": {"spritesheet": "working.webp", "frames": frames},
        "fail": {"spritesheet": "fail.webp", "frames": frames},
        "happy": {"spritesheet": "happy.webp", "frames": frames},
    }
    transition = {}
    for state in ("working", "fail", "happy"):
        transition[f"idle_to_{state}"] = {
            "spritesheet": f"{state}.webp",
            "frames": frames,
        }
        transition[f"{state}_to_idle"] = {
            "spritesheet": f"{state}.webp",
            "frames": frames,
        }
    return {
        "defaultActivity": "idle",
        "actions": {"atomic": atomics, "transition": transition},
    }


class TestActionReadiness(unittest.TestCase):
    def test_empty_actions_cannot_create_custom_pet(self) -> None:
        report = check_actions_ready(
            {"defaultActivity": "idle", "actions": {"atomic": {}, "transition": {}}}
        )
        self.assertFalse(report.ready)
        self.assertEqual(report.missing_atomics, ["idle", "working", "fail", "happy"])

    def test_rejects_single_frame_action(self) -> None:
        report = check_actions_ready(_full_pet(frames=1))
        self.assertFalse(report.ready)
        self.assertEqual(
            report.invalid_frame_counts,
            [
                "idle",
                "working",
                "fail",
                "happy",
                "idle_to_working",
                "working_to_idle",
                "idle_to_fail",
                "fail_to_idle",
                "idle_to_happy",
                "happy_to_idle",
            ],
        )

    def test_rejects_missing_or_empty_media(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "idle.webp").write_bytes(b"ok")
            report = check_actions_ready(_full_pet(), media_root=root)
        self.assertFalse(report.ready)
        self.assertIn("working:working.webp", report.missing_media_files)

    def test_accepts_complete_media_closure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("idle.webp", "working.webp", "fail.webp", "happy.webp"):
                (root / name).write_bytes(b"nonempty")
            report = check_actions_ready(_full_pet(), media_root=root)
        self.assertTrue(report.ready, msg=report.message())


if __name__ == "__main__":
    unittest.main()
