#!/usr/bin/env python3
"""静态素材不得伪装为桌宠 action。"""

from __future__ import annotations

import unittest

from import_frames import assert_frame_payloads_have_motion


class TestImportMotionGate(unittest.TestCase):
    def test_rejects_single_frame(self) -> None:
        with self.assertRaisesRegex(ValueError, "只有一帧"):
            assert_frame_payloads_have_motion([b"frame"])

    def test_rejects_repeated_static_frames(self) -> None:
        with self.assertRaisesRegex(ValueError, "完全相同"):
            assert_frame_payloads_have_motion([b"same", b"same", b"same"])

    def test_accepts_changed_frames(self) -> None:
        assert_frame_payloads_have_motion([b"frame-a", b"frame-b"])


if __name__ == "__main__":
    unittest.main()
