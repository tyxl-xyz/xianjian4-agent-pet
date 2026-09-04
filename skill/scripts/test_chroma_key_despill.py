#!/usr/bin/env python3
"""chroma_key_to_gif：背景 mask 须 dilate 切绿边（禁止 erode 包入绿边）。"""

from __future__ import annotations

import unittest

import numpy as np

from chroma_key_to_gif import chroma_key_remove


def _make_green_fringe_plate(
    size: int = 64,
    *,
    bg: tuple[int, int, int] = (80, 220, 40),
    subject: tuple[int, int, int] = (40, 40, 40),
    fringe: tuple[int, int, int] = (114, 180, 102),
) -> np.ndarray:
    """
    中心深色角色 + 一圈已落入默认绿幕 hue 的亮绿边 + 外圈绿幕。
    亮绿边若被包进前景，opaque 像素会带明显绿色。
    """
    img = np.zeros((size, size, 3), dtype=np.uint8)
    img[:, :] = bg
    # 角色核
    img[20:44, 20:44] = subject
    # 环状绿边（应被切掉）
    img[18:20, 18:46] = fringe
    img[44:46, 18:46] = fringe
    img[18:46, 18:20] = fringe
    img[18:46, 44:46] = fringe
    return img


def _greenish_opaque_count(rgba: np.ndarray) -> int:
    rgb = rgba[:, :, :3].astype(np.int16)
    a = rgba[:, :, 3]
    opaque = a > 128
    greenish = (
        opaque
        & (rgb[:, :, 1] > rgb[:, :, 0] + 20)
        & (rgb[:, :, 1] > rgb[:, :, 2] + 20)
        & (rgb[:, :, 1] > 80)
    )
    return int(greenish.sum())


class ChromaKeyDespillTests(unittest.TestCase):
    def test_default_dilate_removes_green_fringe(self) -> None:
        img = _make_green_fringe_plate()
        rgba = chroma_key_remove(img, blur_radius=1, morph_iter=1, despill_dilate_iter=2)
        self.assertEqual(_greenish_opaque_count(rgba), 0)
        # 角色核仍应有不透明像素
        self.assertGreater(int((rgba[20:44, 20:44, 3] > 128).sum()), 100)

    def test_legacy_erode_alias_means_dilate_not_erode(self) -> None:
        """旧参数 erode_iter 现映射为 dilate；不得再出现「包绿边」行为。"""
        img = _make_green_fringe_plate()
        rgba = chroma_key_remove(img, blur_radius=1, morph_iter=1, erode_iter=2)
        self.assertEqual(_greenish_opaque_count(rgba), 0)

    def test_zero_dilate_keeps_fringe_when_classified_as_bg_then_shrunk_wrongly(self) -> None:
        """
        对照：若对背景 mask 错误 erode（旧 bug），绿边会变不透明。
        这里用手动 erode 复现旧行为，证明方向敏感。
        """
        import cv2

        img = _make_green_fringe_plate()
        hsv = cv2.cvtColor(img, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, np.array([35, 80, 80]), np.array([85, 255, 255]))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
        bad = cv2.erode(mask, kernel, iterations=2)
        alpha = ((1.0 - bad.astype(np.float32) / 255.0) * 255).astype(np.uint8)
        rgba = cv2.cvtColor(img, cv2.COLOR_RGB2RGBA)
        rgba[:, :, 3] = alpha
        self.assertGreater(_greenish_opaque_count(rgba), 0)


if __name__ == "__main__":
    unittest.main()
