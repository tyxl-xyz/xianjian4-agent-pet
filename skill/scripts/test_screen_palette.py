#!/usr/bin/env python3
"""screen_palette / suggest_screen_from_hues 冒烟。"""

from __future__ import annotations

import unittest

from screen_palette import suggest_screen_from_hues


class SuggestScreenColorTests(unittest.TestCase):
    def test_cow_cat_hues_prefer_blue_or_cyan(self) -> None:
        # 绿眼睛≈55，粉鼻子≈160
        r = suggest_screen_from_hues([55, 160])
        self.assertIn(r["family"], {"blue", "cyan"})
        self.assertNotEqual(r["family"], "green")
        self.assertNotEqual(r["family"], "magenta")
        self.assertIsNotNone(r["min_distance"])
        self.assertGreaterEqual(int(r["min_distance"]), 25)

    def test_empty_defaults_green(self) -> None:
        r = suggest_screen_from_hues([])
        self.assertEqual(r["family"], "green")


if __name__ == "__main__":
    unittest.main()
