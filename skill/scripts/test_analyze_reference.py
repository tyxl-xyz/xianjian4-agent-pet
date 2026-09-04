#!/usr/bin/env python3
"""analyze_reference：幕布铺满 + 满画面构图冒烟。"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image

from analyze_reference import analyze


def _save(arr: np.ndarray, path: Path) -> None:
    Image.fromarray(arr.astype(np.uint8), mode="RGB").save(path)


class AnalyzeReferenceTests(unittest.TestCase):
    def test_full_frame_character_passes(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ok.png"
            arr = np.zeros((200, 200, 3), dtype=np.uint8)
            arr[:, :] = (80, 220, 40)
            # 包围盒约 84% x 80%，脚底~8%，头顶~12%
            arr[24:184, 16:184] = (40, 40, 40)
            _save(arr, path)
            report = analyze(path, expected="green")
            self.assertTrue(report["ok"], report.get("errors"))

    def test_tiny_centered_character_fails_framing(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "tiny.png"
            arr = np.zeros((200, 200, 3), dtype=np.uint8)
            arr[:, :] = (80, 220, 40)
            # 中心小块 ~30% — 应触发包围盒过小 / 脚底过大
            arr[70:130, 70:130] = (40, 40, 40)
            _save(arr, path)
            report = analyze(path, expected="green")
            self.assertFalse(report["ok"])
            joined = " ".join(report.get("errors") or [])
            self.assertTrue(
                "包围盒" in joined or "脚底" in joined,
                report.get("errors"),
            )

    def test_white_border_fails_screen_fill(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "border.png"
            arr = np.full((200, 200, 3), 253, dtype=np.uint8)
            arr[20:180, 20:180] = (80, 220, 40)
            arr[40:160, 40:160] = (40, 40, 40)
            _save(arr, path)
            report = analyze(path, expected="green")
            self.assertFalse(report["ok"])
            self.assertTrue(
                any("白" in e or "四角" in e for e in (report.get("errors") or [])),
                report.get("errors"),
            )

    def test_gradient_screen_fails_without_crop_foot(self) -> None:
        """渐变蓝幕 + 角色未贴底：只报幕布不匀，不报假裁脚。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "grad.png"
            h = w = 200
            arr = np.zeros((h, w, 3), dtype=np.uint8)
            for y in range(h):
                t = y / (h - 1)
                # 顶浅蓝 → 底深蓝，四角色差会超阈值
                b = int(220 - 120 * t)
                arr[y, :] = (40, 80, b)
            # 角色偏上，真实脚底边距约 25%（若误用全局均值会假报裁脚）
            arr[30:150, 20:180] = (40, 40, 40)
            _save(arr, path)
            report = analyze(path, expected="blue")
            self.assertFalse(report["ok"])
            self.assertTrue(
                (report.get("framing") or {}).get("skipped"),
                report.get("framing"),
            )
            joined = " ".join(report.get("errors") or [])
            self.assertIn("渐变", joined)
            self.assertNotIn("脚底边距过小", joined)
            self.assertNotIn("脚底边距过大", joined)
            self.assertNotIn("头顶边距", joined)

    def test_solid_screen_ok_foot_margin(self) -> None:
        """均匀幕布 + 脚底约 8%：构图应通过。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "foot_ok.png"
            arr = np.zeros((200, 200, 3), dtype=np.uint8)
            arr[:, :] = (80, 220, 40)
            # top=24/200=12%, foot=(200-184)/200=8%, w=168/200=84%, h=160/200=80%
            arr[24:184, 16:184] = (40, 40, 40)
            _save(arr, path)
            report = analyze(path, expected="green")
            self.assertTrue(report["ok"], report.get("errors"))
            m = (report.get("framing") or {}).get("margins") or {}
            self.assertAlmostEqual(m.get("foot", -1), 0.08, places=2)

    def test_solid_screen_true_crop_foot_fails(self) -> None:
        """均匀幕布 + 真实裁脚（贴底）：仍应报脚底边距过小。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "crop_foot.png"
            arr = np.zeros((200, 200, 3), dtype=np.uint8)
            arr[:, :] = (80, 220, 40)
            # 贴底：y1=199 → foot≈0；头顶留约 12%
            arr[24:200, 16:184] = (40, 40, 40)
            _save(arr, path)
            report = analyze(path, expected="green")
            self.assertFalse(report["ok"])
            joined = " ".join(report.get("errors") or [])
            self.assertIn("脚底边距过小", joined)
            self.assertFalse((report.get("framing") or {}).get("skipped"))

    def test_green_screen_green_eyes_fails_key_conflict(self) -> None:
        """绿幕 + 绿眼睛点缀 → 色键冲突 FAIL。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "green_eyes.png"
            arr = np.zeros((200, 200, 3), dtype=np.uint8)
            arr[:, :] = (80, 220, 40)
            arr[24:184, 16:184] = (40, 40, 40)
            # 双眼：高饱和绿（落入默认 hue 35–85）
            arr[50:62, 60:78] = (60, 200, 70)
            arr[50:62, 122:140] = (60, 200, 70)
            _save(arr, path)
            report = analyze(path, expected="green")
            self.assertFalse(report["ok"], report)
            kc = report.get("key_conflict") or {}
            self.assertFalse(kc.get("ok"), kc)
            joined = " ".join(report.get("errors") or [])
            self.assertIn("色键冲突", joined)
            self.assertIn("redo-bg", (report.get("hint") or ""))

    def test_green_screen_pink_nose_only_passes_key(self) -> None:
        """绿幕 + 仅粉鼻（远离绿 hue）→ 色键通过。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "pink_nose.png"
            arr = np.zeros((200, 200, 3), dtype=np.uint8)
            arr[:, :] = (80, 220, 40)
            arr[24:184, 16:184] = (40, 40, 40)
            arr[100:112, 90:110] = (220, 120, 150)
            _save(arr, path)
            report = analyze(path, expected="green")
            self.assertTrue(report["ok"], report.get("errors"))
            self.assertTrue((report.get("key_conflict") or {}).get("ok"))

    def test_cyan_screen_green_eyes_passes_key(self) -> None:
        """青幕 + 绿眼睛 → 色键通过。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "cyan_green_eyes.png"
            arr = np.zeros((200, 200, 3), dtype=np.uint8)
            arr[:, :] = (40, 200, 200)
            arr[24:184, 16:184] = (40, 40, 40)
            arr[50:62, 60:78] = (60, 200, 70)
            arr[50:62, 122:140] = (60, 200, 70)
            _save(arr, path)
            report = analyze(path, expected="cyan")
            self.assertTrue(report["ok"], report.get("errors"))
            self.assertTrue((report.get("key_conflict") or {}).get("ok"))


if __name__ == "__main__":
    unittest.main()
