#!/usr/bin/env python3
"""encode_action_webm + build_pet_json video 路径冒烟（需本机 ffmpeg）。"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

SCRIPTS = Path(__file__).resolve().parent


def _make_gif(path: Path) -> None:
    """带真实透明边的 GIF（供编码后 alpha 门禁）。"""
    frames: list[Image.Image] = []
    for i in range(4):
        im = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        x = 4 + (i % 2) * 2
        for yy in range(8, 24):
            for xx in range(x, x + 16):
                im.putpixel((xx, yy), (220, 40, 40, 255))
        frames.append(im)
    frames[0].save(
        path,
        save_all=True,
        append_images=frames[1:],
        duration=100,
        loop=0,
        disposal=2,
    )


class TestEnsureFfmpegCli(unittest.TestCase):
    def test_ensure_only_no_auto_install_exits_when_missing(self) -> None:
        """--no-auto-install 且 PATH 无可用 ffmpeg 时应非零退出。"""
        env = {**dict(**{k: v for k, v in __import__("os").environ.items()})}
        # 清空常见覆盖，并让 PATH 找不到 ffmpeg
        for key in ("LINGXI_FFMPEG", "IMAGEIO_FFMPEG_EXE", "FFMPEG_BINARY"):
            env.pop(key, None)
        env["PATH"] = "/usr/bin:/bin"
        r = subprocess.run(
            [
                sys.executable,
                str(SCRIPTS / "encode_action_webm.py"),
                "--ensure-only",
                "--no-auto-install",
            ],
            capture_output=True,
            text=True,
            env=env,
        )
        # 若系统 /usr/bin 碰巧有 ffmpeg+vp9 则跳过断言
        if shutil.which("ffmpeg") and Path("/usr/bin/ffmpeg").exists():
            self.skipTest("环境 /usr/bin 已有 ffmpeg")
        self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)


def _resolve_ffmpeg_for_test() -> str | None:
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "encode_action_webm.py"), "--ensure-only"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return None
    lines = [ln.strip() for ln in (r.stdout or "").splitlines() if ln.strip()]
    return lines[-1] if lines else None


@unittest.skipUnless(
    _resolve_ffmpeg_for_test(),
    "需要可用 ffmpeg（ensure-only 自动安装）",
)
class TestEncodeActionWebm(unittest.TestCase):
    def test_gif_to_stacked_mov_and_build_patch(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mov_smoke_") as tmp:
            td = Path(tmp)
            gif = td / "smoke.gif"
            _make_gif(gif)
            out = td / "smoke.mov"
            r = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "encode_action_webm.py"),
                    "--input",
                    str(gif),
                    "-o",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr + "\n" + r.stdout)
            self.assertTrue(out.is_file())
            self.assertGreater(out.stat().st_size, 0)
            self.assertFalse((td / "smoke.webm").is_file())
            self.assertTrue((td / "smoke_video_manifest.json").is_file())

            user = td / "user"
            r2 = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_pet_json.py"),
                    "--manifest-dir",
                    str(td),
                    "--out",
                    str(user),
                    "--pet-id",
                    "smoke",
                    "--display-name",
                    "Smoke",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r2.returncode, 0, r2.stderr or r2.stdout)
            patch = json.loads((user / "pet.patch.json").read_text(encoding="utf-8"))
            clip = patch["actions"]["atomic"].get("smoke") or patch["actions"][
                "transition"
            ].get("smoke")
            self.assertIsNotNone(clip)
            self.assertNotIn("video", clip)
            self.assertFalse((user / "smoke.webm").is_file())
            self.assertEqual(clip.get("videoHevc"), "smoke.mov")
            self.assertEqual(clip.get("videoAlphaLayout"), "stacked")
            self.assertTrue((user / "smoke.mov").is_file())

    def test_also_webm_emits_webm_companion(self) -> None:
        with tempfile.TemporaryDirectory(prefix="also_webm_") as tmp:
            td = Path(tmp)
            gif = td / "smoke.gif"
            _make_gif(gif)
            out = td / "smoke.mov"
            r = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "encode_action_webm.py"),
                    "--input",
                    str(gif),
                    "-o",
                    str(out),
                    "--also-webm",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr + "\n" + r.stdout)
            self.assertTrue(out.is_file())
            self.assertTrue((td / "smoke.webm").is_file())
            self.assertIn("透明校验通过", r.stdout)

    def test_stacked_premultiplies_white_under_transparent(self) -> None:
        """透明区若 RGB 为白，stacked 上半须预乘成近黑，否则合成会出白边。"""
        with tempfile.TemporaryDirectory(prefix="webm_premul_") as tmp:
            td = Path(tmp)
            gif = td / "white_under.gif"
            frames: list[Image.Image] = []
            for i in range(4):
                # 故意把透明区填白（模拟常见 straight-alpha / 合成残留）
                # 各帧略有差异，避免 Pillow 合并为单帧导致 frames_hint=1
                im = Image.new("RGBA", (48, 48), (255, 255, 255, 0))
                x0 = 12 + (i % 2)
                for yy in range(12, 36):
                    for xx in range(x0, x0 + 24):
                        im.putpixel((xx, yy), (240, 120, 40, 255))
                frames.append(im)
            frames[0].save(
                gif,
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
                disposal=2,
            )
            out = td / "white_under.mov"
            r = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "encode_action_webm.py"),
                    "--input",
                    str(gif),
                    "-o",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr + "\n" + r.stdout)
            mov = td / "white_under.mov"
            self.assertTrue(mov.is_file())

            from encode_action_webm import verify_stacked_mac_video

            stats = verify_stacked_mac_video(mov)
            mean_r, mean_g, mean_b = stats["transparent_rgb_mean"]
            self.assertLess((mean_r + mean_g + mean_b) / 3.0, 24.0)

    def test_opaque_gif_fails_alpha_gate(self) -> None:
        with tempfile.TemporaryDirectory(prefix="webm_opaque_") as tmp:
            td = Path(tmp)
            gif = td / "opaque.gif"
            frames = [
                Image.new("RGBA", (32, 32), (255, 0, 0, 255)),
                Image.new("RGBA", (32, 32), (0, 255, 0, 255)),
            ]
            frames[0].save(
                gif,
                save_all=True,
                append_images=frames[1:],
                duration=100,
                loop=0,
            )
            out = td / "opaque.mov"
            r = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "encode_action_webm.py"),
                    "--input",
                    str(gif),
                    "-o",
                    str(out),
                ],
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(r.returncode, 0, r.stdout + r.stderr)
            combined = r.stderr + r.stdout
            self.assertTrue(
                "透明校验失败" in combined or "matte" in combined.lower() or "stacked" in combined.lower(),
                combined[-2000:],
            )


class TestProbeGifFrames(unittest.TestCase):
    """不依赖 ffmpeg：GIF 帧数探测与 frames=1 禁写。"""

    def test_probe_gif_uses_fps_hint(self) -> None:
        from encode_action_webm import probe_gif, write_video_manifest

        with tempfile.TemporaryDirectory(prefix="gif_probe_") as tmp:
            td = Path(tmp)
            gif = td / "n.gif"
            _make_gif(gif)
            got = probe_gif(gif, fps_hint=24)
            self.assertEqual(got["frames"], 4)
            self.assertEqual(got["fps"], 24)
            self.assertAlmostEqual(got["duration"], 4 / 24, places=5)

            with self.assertRaises(SystemExit) as ctx:
                write_video_manifest(
                    td,
                    "bad",
                    [
                        {
                            "id": "x",
                            "frames": 1,
                            "fps": 24,
                            "video": "x.webm",
                            "kind": "atomic",
                        }
                    ],
                )
            self.assertIn("frames<2", str(ctx.exception))


class TestBuildPetJsonVideoOnly(unittest.TestCase):
    """不依赖 ffmpeg：裸 .webm + video_manifest。"""

    def test_collect_webm_writes_video_field(self) -> None:
        with tempfile.TemporaryDirectory(prefix="webm_build_") as tmp:
            td = Path(tmp)
            webm = td / "fail.webm"
            webm.write_bytes(b"fake-webm")
            (td / "fail_video_manifest.json").write_text(
                json.dumps(
                    {
                        "format": "video_webm",
                        "prefix": "fail",
                        "fps": 24,
                        "frame_width": 128,
                        "frame_height": 128,
                        "rows": [
                            {
                                "id": "idle_to_fail",
                                "name": "idle_to_fail",
                                "row": 0,
                                "frames": 10,
                                "fps": 24,
                                "video": "idle_to_fail.webm",
                                "kind": "transition",
                            },
                            {
                                "id": "fail",
                                "name": "fail",
                                "row": 1,
                                "frames": 20,
                                "fps": 24,
                                "video": "fail.webm",
                                "kind": "atomic",
                            },
                            {
                                "id": "fail_to_idle",
                                "name": "fail_to_idle",
                                "row": 2,
                                "frames": 10,
                                "fps": 24,
                                "video": "fail_to_idle.webm",
                                "kind": "transition",
                            },
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (td / "idle_to_fail.webm").write_bytes(b"a")
            (td / "fail_to_idle.webm").write_bytes(b"b")

            user = td / "user"
            r = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_pet_json.py"),
                    "--manifest-dir",
                    str(td),
                    "--out",
                    str(user),
                    "--pet-id",
                    "t",
                    "--display-name",
                    "T",
                    "--default-activity",
                    "fail",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
            patch = json.loads((user / "pet.patch.json").read_text(encoding="utf-8"))
            self.assertEqual(patch["actions"]["atomic"]["fail"]["video"], "fail.webm")
            self.assertEqual(
                patch["actions"]["transition"]["idle_to_fail"]["video"],
                "idle_to_fail.webm",
            )
            self.assertNotIn("spritesheet", patch["actions"]["atomic"]["fail"])
            self.assertTrue((user / "fail.webm").is_file())

    def test_collect_mov_only_writes_video_hevc(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mov_build_") as tmp:
            td = Path(tmp)
            (td / "idle_video_manifest.json").write_text(
                json.dumps(
                    {
                        "format": "video_webm",
                        "prefix": "idle",
                        "fps": 24,
                        "frame_width": 128,
                        "frame_height": 128,
                        "rows": [
                            {
                                "id": "idle",
                                "name": "idle",
                                "row": 0,
                                "frames": 12,
                                "fps": 24,
                                "videoHevc": "idle.mov",
                                "videoAlphaLayout": "stacked",
                                "kind": "atomic",
                            }
                        ],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            (td / "idle.mov").write_bytes(b"fake-mov")

            user = td / "user"
            r = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "build_pet_json.py"),
                    "--manifest-dir",
                    str(td),
                    "--out",
                    str(user),
                    "--pet-id",
                    "t",
                    "--display-name",
                    "T",
                    "--default-activity",
                    "idle",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(r.returncode, 0, r.stderr or r.stdout)
            patch = json.loads((user / "pet.patch.json").read_text(encoding="utf-8"))
            idle = patch["actions"]["atomic"]["idle"]
            self.assertNotIn("video", idle)
            self.assertEqual(idle["videoHevc"], "idle.mov")
            self.assertEqual(idle["videoAlphaLayout"], "stacked")
            self.assertTrue((user / "idle.mov").is_file())


if __name__ == "__main__":
    unittest.main()
