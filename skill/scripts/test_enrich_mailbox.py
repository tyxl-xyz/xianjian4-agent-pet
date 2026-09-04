#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""enrich 自动写入 mailboxPresentation 烟测。"""

from __future__ import annotations

import unittest

from enrich_pet_patch import (
    DEFAULT_DISAPPEAR_AFTER_SEC,
    DEFAULT_DISAPPEAR_AWAY_SEC,
    build_enrichment,
    build_mailbox_presentation_add,
)


class TestMailboxPresentationEnrich(unittest.TestCase):
    def test_add_timing_only_when_no_sequences(self) -> None:
        add = build_mailbox_presentation_add({}, set())
        self.assertEqual(
            add,
            {
                "disappearAfterSec": DEFAULT_DISAPPEAR_AFTER_SEC,
                "disappearAwaySec": DEFAULT_DISAPPEAR_AWAY_SEC,
            },
        )
        self.assertNotIn("mailboxImage", add or {})
        self.assertNotIn("awaySequence", add or {})

    def test_attach_known_sequences_when_present(self) -> None:
        add = build_mailbox_presentation_add(
            {},
            {"away_disappear_play", "return_appear_play", "happy_play"},
        )
        assert add is not None
        self.assertEqual(add["awaySequence"], "away_disappear_play")
        self.assertEqual(add["readLetterSequence"], "return_appear_play")
        self.assertNotIn("mailboxImage", add)

    def test_idempotent_skips_existing_keys(self) -> None:
        patch = {
            "mailboxPresentation": {
                "disappearAfterSec": 60,
                "awaySequence": "custom_away",
            }
        }
        add = build_mailbox_presentation_add(
            patch,
            {"away_disappear_play", "return_appear_play"},
        )
        assert add is not None
        self.assertNotIn("disappearAfterSec", add)
        self.assertNotIn("awaySequence", add)
        self.assertEqual(add["disappearAwaySec"], DEFAULT_DISAPPEAR_AWAY_SEC)
        self.assertEqual(add["readLetterSequence"], "return_appear_play")

    def test_build_enrichment_includes_mailbox(self) -> None:
        patch = {
            "actions": {
                "atomic": {"idle": {"name": "idle"}},
                "transition": {},
            }
        }
        incoming = build_enrichment(patch)
        self.assertIn("mailboxPresentation", incoming)
        mp = incoming["mailboxPresentation"]
        self.assertEqual(mp["disappearAfterSec"], DEFAULT_DISAPPEAR_AFTER_SEC)
        self.assertNotIn("mailboxImage", mp)


if __name__ == "__main__":
    unittest.main()
