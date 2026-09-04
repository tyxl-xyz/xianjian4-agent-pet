#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""P0：WebP 超限时主交付 PNG，并经 build_pet_json 写入 user/。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from build_pet_json import (
    build_pet_skeleton,
    collect_clips,
    copy_webp_assets,
    load_json,
    resolve_webp_dest_names,
)
from make_spritesheet import WEBP_MAX_DIMENSION, make_spritesheet

FRAME = 720
FRAMES = 24  # 24*720 = 17280 > 16383
ROWS = ("idle_to_happy", "happy", "happy_to_idle")


def _make_gif(path: Path, n: int, color: tuple[int, int, int]) -> None:
    frames: list[Image.Image] = []
    for i in range(n):
        im = Image.new("RGBA", (FRAME, FRAME), (0, 0, 0, 0))
        block = Image.new("RGBA", (FRAME // 2, FRAME // 2), (*color, 255))
        im.paste(block, (FRAME // 4 + (i % 5), FRAME // 4))
        frames.append(im)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=40,
        loop=0,
        disposal=2,
    )


class TestOversizedWebpP0(unittest.TestCase):
    def test_oversized_delivers_png_to_user(self) -> None:
        self.assertGreater(FRAMES * FRAME, WEBP_MAX_DIMENSION)
        with tempfile.TemporaryDirectory(prefix="p0-verify-") as tmp:
            root = Path(tmp)
            build = root / "_build" / "happy"
            user = root / "user"
            ws = root / "ws"
            build.mkdir(parents=True)
            user.mkdir()
            ws.mkdir()

            sources: list[tuple[str, str]] = []
            colors = [(220, 80, 80), (80, 200, 80), (80, 80, 220)]
            for name, color in zip(ROWS, colors):
                gif = ws / f"{name}.gif"
                _make_gif(gif, FRAMES, color)
                sources.append((name, str(gif)))

            result = make_spritesheet(
                sources=sources,
                output_dir=str(build),
                name_prefix="happy",
                frame_size=FRAME,
                fps=24,
            )
            self.assertTrue(result.get("oversized_webp"))
            self.assertTrue(str(result["sprite"]).endswith("happy.png"))

            manifest = json.loads((build / "happy_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["sprite"], "happy.png")
            self.assertEqual(manifest.get("format"), "png")
            self.assertTrue((build / "happy.png").is_file())
            self.assertFalse((build / "happy.webp").exists())
            self.assertTrue((build / "happy_part0.webp").is_file())

            clips = collect_clips(build)
            self.assertTrue(all(c["entry"]["spritesheet"] == "happy.png" for c in clips))
            resolve_webp_dest_names(clips, user)
            copy_webp_assets(clips, user)
            pet = build_pet_skeleton(
                clips,
                pet_id="verify-hd",
                display_name="验证",
                default_activity="happy",
            )
            (user / "pet.patch.json").write_text(
                json.dumps(pet, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

            self.assertTrue((user / "happy.png").is_file())
            self.assertEqual(list(user.glob("*_part*.webp")), [])
            patch = load_json(user / "pet.patch.json")
            self.assertEqual(patch["displayWidth"], 128)
            self.assertEqual(patch["cellWidth"], FRAME)
            self.assertEqual(patch["actions"]["atomic"]["happy"]["spritesheet"], "happy.png")


if __name__ == "__main__":
    unittest.main()
