#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""base_mode_bubble 信箱未读提示单测。"""

from __future__ import annotations

import unittest

from base_mode_bubble import (
    MAILBOX_UNREAD_TIP,
    ensure_bubbles_on_base_modes,
    ensure_mailbox_unread_tip,
    pool_has_mailbox_unread,
)


def _bm(*actions: dict) -> dict:
    return {"enabled": True, "actions": list(actions)}


class TestMailboxUnreadTip(unittest.TestCase):
    def test_exactly_one_tip_when_two_eligible(self) -> None:
        bm = _bm(
            {
                "id": "wave",
                "sequence": "micro_wave_play",
                "mode": "once",
                "bubble": {"texts": ["嗨"], "dwellSec": [4, 6]},
            },
            {
                "id": "wink",
                "sequence": "micro_wink_play",
                "mode": "once",
                "bubble": {"texts": ["眨眨"], "dwellSec": [4, 6]},
            },
        )
        out, tip_id = ensure_mailbox_unread_tip(bm)
        self.assertIsNotNone(tip_id)
        tipped = [
            a
            for a in out["actions"]
            if any("{mailboxUnread}" in t for t in a["bubble"]["texts"])
        ]
        self.assertEqual(len(tipped), 1)
        self.assertEqual(tipped[0]["bubble"]["texts"][-1], MAILBOX_UNREAD_TIP)

    def test_skip_when_pool_already_has_placeholder(self) -> None:
        bm = _bm(
            {
                "id": "a",
                "sequence": "wave_play",
                "mode": "once",
                "bubble": {
                    "texts": ["x", "还有{mailboxUnread}条"],
                    "dwellSec": [4, 6],
                },
            },
            {
                "id": "b",
                "sequence": "wink_play",
                "mode": "once",
                "bubble": {"texts": ["y"], "dwellSec": [4, 6]},
            },
        )
        self.assertTrue(pool_has_mailbox_unread(bm))
        out, tip_id = ensure_mailbox_unread_tip(bm)
        self.assertIsNone(tip_id)
        self.assertEqual(out, bm)

    def test_skip_sleep_and_hold(self) -> None:
        bm = _bm(
            {
                "id": "sleep",
                "sequence": "lie_sleep_enter",
                "mode": "hold",
                "bubble": {"texts": ["Zzz"], "dwellSec": [4, 6]},
            },
            {
                "id": "hold_pose",
                "sequence": "micro_wave_play",
                "mode": "hold",
                "bubble": {"texts": ["停住"], "dwellSec": [4, 6]},
            },
        )
        out, tip_id = ensure_mailbox_unread_tip(bm)
        self.assertIsNone(tip_id)
        self.assertFalse(pool_has_mailbox_unread(out))

    def test_stable_pick_across_calls(self) -> None:
        bm = _bm(
            {
                "id": "alpha",
                "sequence": "wave_play",
                "mode": "once",
                "bubble": {"texts": ["a"], "dwellSec": [4, 6]},
            },
            {
                "id": "beta",
                "sequence": "wink_play",
                "mode": "once",
                "bubble": {"texts": ["b"], "dwellSec": [4, 6]},
            },
            {
                "id": "gamma",
                "sequence": "happy_play",
                "mode": "once",
                "bubble": {"texts": ["c"], "dwellSec": [4, 6]},
            },
        )
        _, id1 = ensure_mailbox_unread_tip(bm)
        _, id2 = ensure_mailbox_unread_tip(bm)
        self.assertEqual(id1, id2)

    def test_only_missing_still_appends_tip(self) -> None:
        bm = _bm(
            {
                "id": "micro_tail",
                "sequence": "micro_tail_wag_play",
                "mode": "once",
                "bubble": {"texts": ["有没有小鱼干"], "dwellSec": [4, 6]},
            },
            {
                "id": "sleep",
                "sequence": "lie_sleep_enter",
                "mode": "hold",
            },
        )
        out, filled = ensure_bubbles_on_base_modes(bm, only_missing=True)
        self.assertTrue(pool_has_mailbox_unread(out))
        self.assertIn("micro_tail", filled)
        tipped = out["actions"][0]["bubble"]["texts"]
        self.assertEqual(tipped[-1], MAILBOX_UNREAD_TIP)


if __name__ == "__main__":
    unittest.main()
