#!/usr/bin/env python3
"""
将「已抠像」GIF / 带 alpha 视频编码为透明桌宠短视频。

默认主产物：stacked-alpha `{stem}.mov`（上半 RGB、下半灰度 matte，H.264）。
可选：`--also-webm` 额外产出 VP9+yuva420p `.webm`（引擎仍可播放，创建宠默认不生成）。

输入必须已是透明素材（推荐 chroma_key_to_gif 产物）。
禁止直接喂未抠像绿幕 mp4——脚本会在编码后校验透明像素，全不透明则失败。

ffmpeg 解析顺序（缺则自动安装，禁止 Agent 因 which 失败直接改走合图）：
  1. PATH 中已有且含 libvpx-vp9 的 ffmpeg
  2. 已装 imageio-ffmpeg / 缓存静态二进制
  3. pip install imageio-ffmpeg
  4. 最后才 brew install ffmpeg

用法:
  # 仅确保可用（Phase 0 / 路径解析后建议先跑）
  python encode_action_webm.py --ensure-only

  # 透明 GIF → stacked .mov（创建宠默认）
  python encode_action_webm.py --input idle.gif -o idle.mov

  # 多段：各段须已是透明 GIF（先 chroma_key_to_gif）
  python encode_action_webm.py --input hold.gif -o ./out --segments ... --names ...

  # 额外产出 WebM（可选回退）
  python encode_action_webm.py --input idle.gif -o idle.mov --also-webm

  # 仅 WebM（旧路径 / 调试）
  python encode_action_webm.py --input idle.gif -o idle.webm --webm-only

  # 同时产出轻量回退图集（默认关闭）
  python encode_action_webm.py --input a.gif -o a.mov --also-spritesheet \\
    --spritesheet-dir "{workspace}/_build/fail" --frame-size 128

字段写入 video_manifest：默认仅 `videoHevc` + `videoAlphaLayout: stacked`；
`--also-webm` / `--webm-only` 时另写 `video`。
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_CRF = 32
DEFAULT_SAMPLE_FPS = 24
# Mac stacked 伴生：桌宠显示边长通常 128，过大只浪费解码/上传带宽
DEFAULT_MAC_STACKED_MAX_EDGE = 256

# 编码后透明验收：至少约 1% 像素 alpha<16（防止「有 alpha 平面但全不透明」绿幕烤进 RGB）
MIN_TRANSPARENT_RATIO = 0.01
MIN_TRANSPARENT_PIXELS = 64
# WebM / stacked 上半：透明区 RGB 均值须近黑（预乘后），否则 Win/Mac 合成会出白边
MAX_STACKED_TRANSPARENT_RGB_MEAN = 24.0

# imageio-binaries 静态包（绕过 brew/pip 失败时的兜底）
_STATIC_FFMPEG_BASE = (
    "https://raw.githubusercontent.com/imageio/imageio-binaries/master/ffmpeg/"
)
_STATIC_FFMPEG_NAMES = {
    ("darwin", "arm64"): "ffmpeg-macos-aarch64-v7.1",
    ("darwin", "aarch64"): "ffmpeg-macos-aarch64-v7.1",
    ("darwin", "x86_64"): "ffmpeg-macos-x86_64-v7.1",
    ("linux", "x86_64"): "ffmpeg-linux-x86_64-v7.0.2",
    ("linux", "aarch64"): "ffmpeg-linux-aarch64-v7.0.2",
    ("linux", "arm64"): "ffmpeg-linux-aarch64-v7.0.2",
    ("win32", "amd64"): "ffmpeg-win-x86_64-v7.1.exe",
    ("win32", "x86_64"): "ffmpeg-win-x86_64-v7.1.exe",
}

# 缓存本进程解析到的 ffmpeg，避免重复 brew/pip
_FFMPEG_EXE: str | None = None


def _ffmpeg_cache_dir() -> Path:
    override = os.environ.get("LINGXI_FFMPEG_CACHE", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".cache" / "lingxi-pet" / "ffmpeg"


def ffmpeg_has_vp9(ffmpeg: str) -> bool:
    try:
        proc = subprocess.run(
            [ffmpeg, "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return proc.returncode == 0 and "libvpx-vp9" in (proc.stdout or "")


def _try_path_ffmpeg() -> str | None:
    for key in ("LINGXI_FFMPEG", "IMAGEIO_FFMPEG_EXE", "FFMPEG_BINARY"):
        env = os.environ.get(key, "").strip()
        if env and Path(env).is_file() and ffmpeg_has_vp9(env):
            return env
    path = shutil.which("ffmpeg")
    if path and ffmpeg_has_vp9(path):
        return path
    return None


def _try_brew_install() -> str | None:
    brew = shutil.which("brew")
    if not brew:
        return None
    print("未找到可用 ffmpeg，正在执行: brew install ffmpeg …", flush=True)
    proc = subprocess.run(
        [brew, "install", "ffmpeg"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        print(f"brew install ffmpeg 失败:\n{err[-1500:]}", flush=True)
        return None
    # brew 后刷新 which
    path = shutil.which("ffmpeg")
    if path and ffmpeg_has_vp9(path):
        print(f"已通过 brew 安装 ffmpeg: {path}", flush=True)
        return path
    print("brew 声称成功但未找到含 libvpx-vp9 的 ffmpeg", flush=True)
    return None


def _pip_install_imageio_ffmpeg() -> bool:
    print("正在 pip 安装 imageio-ffmpeg（捆绑静态 ffmpeg）…", flush=True)
    # 先常规安装；证书异常时再试 trusted-host（部分公司/旧 macOS Python）
    attempts = [
        [sys.executable, "-m", "pip", "install", "--user", "imageio-ffmpeg"],
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--user",
            "imageio-ffmpeg",
            "--trusted-host",
            "pypi.org",
            "--trusted-host",
            "files.pythonhosted.org",
        ],
    ]
    last_err = ""
    for cmd in attempts:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            return True
        last_err = (proc.stderr or proc.stdout or "").strip()
    print(f"pip 安装 imageio-ffmpeg 失败:\n{last_err[-1500:]}", flush=True)
    return False


def _try_imageio_ffmpeg(*, allow_pip: bool = True) -> str | None:
    try:
        import imageio_ffmpeg  # type: ignore
    except ImportError:
        if not allow_pip or not _pip_install_imageio_ffmpeg():
            return None
        try:
            import imageio_ffmpeg  # type: ignore
        except ImportError:
            return None
    try:
        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as e:  # noqa: BLE001 — 捆绑下载失败时给出明确路径
        print(f"imageio_ffmpeg.get_ffmpeg_exe 失败: {e}", flush=True)
        return None
    if not exe or not Path(exe).is_file():
        return None
    if not ffmpeg_has_vp9(exe):
        print(
            f"imageio-ffmpeg 二进制不含 libvpx-vp9: {exe}\n"
            "请改用 brew install ffmpeg",
            flush=True,
        )
        return None
    print(f"使用 imageio-ffmpeg 捆绑二进制: {exe}", flush=True)
    return exe


def _static_ffmpeg_asset_name() -> str | None:
    system = sys.platform  # darwin / linux / win32
    machine = platform.machine().lower()
    return _STATIC_FFMPEG_NAMES.get((system, machine))


def _try_download_static_ffmpeg() -> str | None:
    """从 imageio-binaries 下载静态 ffmpeg 到用户缓存目录。"""
    name = _static_ffmpeg_asset_name()
    if not name:
        print(
            f"当前平台无预置静态 ffmpeg: {sys.platform}/{platform.machine()}",
            flush=True,
        )
        return None

    cache = _ffmpeg_cache_dir()
    cache.mkdir(parents=True, exist_ok=True)
    dest = cache / name
    if dest.is_file() and dest.stat().st_size > 1_000_000 and ffmpeg_has_vp9(str(dest)):
        print(f"使用缓存静态 ffmpeg: {dest}", flush=True)
        return str(dest)

    url = _STATIC_FFMPEG_BASE + name
    tmp = dest.with_suffix(dest.suffix + ".partial")
    print(f"正在下载静态 ffmpeg（约 50MB）:\n  {url}", flush=True)
    try:
        # curl 对大文件更稳；失败再 urllib
        curl = shutil.which("curl")
        if curl:
            proc = subprocess.run(
                [curl, "-fL", "--retry", "3", "-o", str(tmp), url],
                capture_output=True,
                text=True,
            )
            if proc.returncode != 0:
                raise RuntimeError((proc.stderr or proc.stdout or "curl failed")[-800:])
        else:
            urllib.request.urlretrieve(url, tmp)  # noqa: S310 — 固定官方 raw URL
        tmp.replace(dest)
        dest.chmod(dest.stat().st_mode | 0o111)
    except Exception as e:  # noqa: BLE001
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        print(f"下载静态 ffmpeg 失败: {e}", flush=True)
        return None

    if not ffmpeg_has_vp9(str(dest)):
        print(f"下载的 ffmpeg 不含 libvpx-vp9: {dest}", flush=True)
        return None
    print(f"已安装静态 ffmpeg: {dest}", flush=True)
    return str(dest)


def ensure_ffmpeg(*, auto_install: bool = True) -> str:
    """
    返回可用 ffmpeg 路径（须含 libvpx-vp9）。
    auto_install=True 时依次尝试 brew / imageio-ffmpeg / 静态下载。
    """
    global _FFMPEG_EXE
    if _FFMPEG_EXE and Path(_FFMPEG_EXE).is_file() and ffmpeg_has_vp9(_FFMPEG_EXE):
        return _FFMPEG_EXE

    found = _try_path_ffmpeg()
    if found:
        _FFMPEG_EXE = found
        return found

    if auto_install:
        # 优先快路径：已装 imageio → 下载静态包 → pip → 最后才 brew（慢且易因 shallow clone 失败）
        found = (
            _try_imageio_ffmpeg(allow_pip=False)
            or _try_download_static_ffmpeg()
            or _try_imageio_ffmpeg(allow_pip=True)
            or _try_brew_install()
        )
        if found:
            _FFMPEG_EXE = found
            return found

    raise SystemExit(
        "无法获得可用的 ffmpeg（需 libvpx-vp9 以编码透明 WebM）。\n"
        "已尝试：PATH / imageio-ffmpeg / 静态下载 / brew install。\n"
        "请手动安装后重试：\n"
        "  python -m pip install --user imageio-ffmpeg\n"
        "或：\n"
        "  brew install ffmpeg\n"
        "禁止因缺少 ffmpeg 静默改走 spritesheet；安装失败须告知用户。",
    )


def require_ffmpeg() -> str:
    """兼容旧名：等同 ensure_ffmpeg(auto_install=True)。"""
    return ensure_ffmpeg(auto_install=True)


def parse_segments(spec: str) -> list[tuple[float, float]]:
    """'0:2,2:6.5,6:9' → [(0,2), (2,6.5), (6,9)]"""
    out: list[tuple[float, float]] = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" not in part:
            raise SystemExit(f"非法 segment（需要 start:end）: {part!r}")
        a, b = part.split(":", 1)
        start, end = float(a), float(b)
        if end <= start:
            raise SystemExit(f"segment 结束须大于开始: {part!r}")
        out.append((start, end))
    if not out:
        raise SystemExit("--segments 为空")
    return out


def encode_webm(
    input_path: Path,
    output_path: Path,
    *,
    ss: float | None = None,
    to: float | None = None,
    crf: int = DEFAULT_CRF,
    fps: int | None = DEFAULT_SAMPLE_FPS,
    ffmpeg: str | None = None,
    verify_alpha: bool = True,
) -> None:
    """已抠像 GIF/视频 → VP9 + yuva420p WebM（无音轨）；默认校验透明像素。

    指定 ``fps`` 时写入恒定输出帧率（``-r``），避免跟 GIF 40ms delay 滚成 25fps，
    使时长贴近「帧数 / sample_fps」。

    HARD：编码前 ``premultiply=inplace=1``。透明区若残留白底 RGB，Win/WebView2
    上 Pixi ``premultiplied-alpha`` + LINEAR 缩小时会出现一圈白边。
    """
    ffmpeg = ffmpeg or require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.resolve() == input_path.resolve():
        raise SystemExit(f"encode_webm 禁止原地覆盖输入: {output_path}")
    cmd: list[str] = [ffmpeg, "-y"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    # VP9+alpha WebM 必须显式 libvpx，否则抽不到 alpha
    if input_path.suffix.lower() == ".webm":
        cmd += ["-c:v", "libvpx-vp9"]
    cmd += ["-i", str(input_path)]
    if ss is not None and to is not None:
        cmd += ["-t", str(max(0.01, to - ss))]
    elif to is not None:
        cmd += ["-to", str(to)]
    if fps is not None and fps > 0:
        cmd += ["-r", str(int(fps))]
    # 预乘后再进 yuva：与引擎 VideoSource alphaMode=premultiplied-alpha 对齐
    cmd += [
        "-vf",
        "format=rgba,premultiply=inplace=1",
        "-c:v",
        "libvpx-vp9",
        "-pix_fmt",
        "yuva420p",
        "-auto-alt-ref",
        "0",
        "-an",
        "-b:v",
        "0",
        "-crf",
        str(crf),
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(f"ffmpeg 编码失败 ({output_path.name}):\n{err[-2000:]}")
    if verify_alpha:
        verify_webm_transparency(output_path, ffmpeg=ffmpeg)


def verify_webm_transparency(
    webm_path: Path,
    *,
    ffmpeg: str | None = None,
    min_ratio: float = MIN_TRANSPARENT_RATIO,
    min_pixels: int = MIN_TRANSPARENT_PIXELS,
) -> dict[str, Any]:
    """
    用 libvpx 解一帧 RGBA，统计 alpha<16 像素。

    HARD：禁止把「ffprobe 报 yuv420p + alpha_mode:1」当成无 alpha；
    必须以 libvpx 解码后的透明像素为准。imageio-ffmpeg 静态包可写真实 alpha，
    禁止归咎编码器 bug 去 brew / 改走 spritesheet。
    """
    from PIL import Image  # 延迟导入：ensure-only 路径不需要

    ffmpeg = ffmpeg or require_ffmpeg()
    tmp_png = webm_path.with_suffix(".alpha_probe.png")
    try:
        # 必须 -c:v libvpx-vp9，否则默认解码器常报 yuv420p 且抽不到 alpha
        cmd = [
            ffmpeg,
            "-y",
            "-c:v",
            "libvpx-vp9",
            "-i",
            str(webm_path),
            "-frames:v",
            "1",
            "-pix_fmt",
            "rgba",
            "-update",
            "1",
            str(tmp_png),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not tmp_png.is_file():
            err = (proc.stderr or proc.stdout or "").strip()
            raise SystemExit(
                f"WebM 透明校验失败（无法用 libvpx 抽帧）: {webm_path.name}\n{err[-1500:]}",
            )
        im = Image.open(tmp_png).convert("RGBA")
        alpha = im.getchannel("A")
        vals = list(alpha.getdata())
        rgba = list(im.getdata())
        n = len(vals) or 1
        transparent = sum(1 for v in vals if v < 16)
        opaque = sum(1 for v in vals if v > 240)
        ratio = transparent / n
        stats = {
            "width": im.width,
            "height": im.height,
            "transparent": transparent,
            "opaque": opaque,
            "ratio": ratio,
            "alpha_min": min(vals) if vals else 0,
            "alpha_max": max(vals) if vals else 0,
        }
        if transparent < min_pixels or ratio < min_ratio:
            raise SystemExit(
                f"WebM 透明校验失败: {webm_path.name}\n"
                f"  透明像素(alpha<16)={transparent}/{n} ({ratio:.1%})，"
                f"要求 ≥{min_pixels} 且 ≥{min_ratio:.0%}\n"
                f"  alpha min/max={stats['alpha_min']}/{stats['alpha_max']}\n"
                "常见原因（按序排查，禁止跑偏）：\n"
                "  1) 输入是未抠像绿幕 mp4/mov，绿幕被烤进 RGB、alpha 全 255\n"
                "  2) 未使用 chroma_key_to_gif 的透明 GIF，却直接 encode\n"
                "  3) GIF 本身不透明（先 view_image / 抽帧确认源 GIF）\n"
                "禁止结论：imageio-ffmpeg / 静态 ffmpeg「写不进 alpha」"
                "（已证实可写；ffprobe 报 yuv420p+alpha_mode 不等于无 alpha）。\n"
                "禁止因此 brew 换 ffmpeg 或静默改走 spritesheet；应重做抠像后重编。",
            )
        # 透明区 RGB 须近黑（预乘）；白底 + Win LINEAR/预乘混合 → 一圈白边
        tr_rgb = [rgba[i][:3] for i, v in enumerate(vals) if v < 16]
        if tr_rgb:
            mean_r = sum(p[0] for p in tr_rgb) / len(tr_rgb)
            mean_g = sum(p[1] for p in tr_rgb) / len(tr_rgb)
            mean_b = sum(p[2] for p in tr_rgb) / len(tr_rgb)
            mean_lum = (mean_r + mean_g + mean_b) / 3.0
            if mean_lum > MAX_STACKED_TRANSPARENT_RGB_MEAN:
                raise SystemExit(
                    f"WebM 透明校验失败: {webm_path.name}\n"
                    f"  透明区 RGB 均值=({mean_r:.1f},{mean_g:.1f},{mean_b:.1f}) "
                    f"亮度={mean_lum:.1f} > {MAX_STACKED_TRANSPARENT_RGB_MEAN}\n"
                    "  说明未预乘、透明区残留白底；Win 桌宠缩小后会出现一圈白边。\n"
                    "  须在 libvpx 编码前做 format=rgba,premultiply=inplace=1。",
                )
        else:
            mean_r = mean_g = mean_b = 0.0
        stats["transparent_rgb_mean"] = (mean_r, mean_g, mean_b)
        print(
            f"透明校验通过 {webm_path.name}: "
            f"transparent={transparent}/{n} ({ratio:.1%}) "
            f"alpha={stats['alpha_min']}-{stats['alpha_max']} "
            f"tr_rgb_mean=({mean_r:.1f},{mean_g:.1f},{mean_b:.1f})",
            flush=True,
        )
        return stats
    finally:
        try:
            tmp_png.unlink(missing_ok=True)
        except OSError:
            pass


def resolve_ffprobe(ffmpeg: str | None = None) -> str | None:
    """PATH / 环境变量 / 与 ffmpeg 同目录推导。"""
    for key in ("LINGXI_FFPROBE", "FFPROBE_BINARY"):
        env = os.environ.get(key, "").strip()
        if env and Path(env).is_file():
            return env
    which = shutil.which("ffprobe")
    if which:
        return which
    ffmpeg = ffmpeg or _try_path_ffmpeg() or _FFMPEG_EXE
    if not ffmpeg:
        return None
    p = Path(ffmpeg)
    name = p.name
    # ffmpeg.exe → ffprobe.exe；ffmpeg-win-x86_64-v7.1.exe → ffprobe-win-...
    lower = name.lower()
    if "ffmpeg" not in lower:
        return None
    probe_name = name.replace("ffmpeg", "ffprobe").replace("FFMPEG", "ffprobe")
    candidate = p.with_name(probe_name)
    if candidate.is_file():
        return str(candidate)
    return None


def probe_gif(path: Path, *, fps_hint: int | None = None) -> dict[str, Any]:
    """用 PIL 数 GIF 帧；fps_hint 优先（与 chroma_key sample_fps 对齐）。"""
    from PIL import Image as PILImage

    with PILImage.open(path) as img:
        frames = 0
        total_ms = 0
        try:
            while True:
                d = img.info.get("duration")
                total_ms += int(d) if d is not None else 0
                frames += 1
                img.seek(frames)
        except EOFError:
            pass
        width, height = img.size

    if frames < 1:
        raise SystemExit(f"无法读取 GIF 帧: {path}")

    if fps_hint and fps_hint > 0:
        fps = int(fps_hint)
        duration = frames / float(fps)
    elif total_ms > 0:
        duration = total_ms / 1000.0
        fps = max(1, int(round(frames / duration)))
    else:
        fps = DEFAULT_SAMPLE_FPS
        duration = frames / float(fps)

    return {
        "fps": fps,
        "frames": frames,
        "width": int(width),
        "height": int(height),
        "duration": float(duration),
    }


def _parse_fps_rate(rate: str | None, default: float = float(DEFAULT_SAMPLE_FPS)) -> float:
    if not rate or not isinstance(rate, str):
        return default
    if "/" in rate:
        num, den = rate.split("/", 1)
        try:
            return float(num) / max(float(den), 1e-6)
        except ValueError:
            return default
    try:
        return float(rate)
    except ValueError:
        return default


def probe_via_ffprobe(path: Path, ffprobe: str) -> dict[str, Any] | None:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,r_frame_rate,nb_frames,duration",
        "-of",
        "json",
        str(path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return None
    streams = data.get("streams") or [{}]
    st = streams[0] if streams else {}
    fps = _parse_fps_rate(st.get("r_frame_rate"))
    duration = float(st.get("duration") or 0) or 0.0
    nb = st.get("nb_frames")
    try:
        frames = int(nb) if nb and str(nb).isdigit() else 0
    except (TypeError, ValueError):
        frames = 0
    if frames < 1 and duration > 0:
        frames = max(1, int(round(duration * fps)))
    if frames < 1:
        return None
    if duration <= 0:
        duration = frames / max(fps, 1e-6)
    return {
        "fps": int(round(fps)) or DEFAULT_SAMPLE_FPS,
        "frames": frames,
        "width": int(st.get("width") or 128),
        "height": int(st.get("height") or 128),
        "duration": float(duration),
    }


def probe_via_ffmpeg(path: Path, ffmpeg: str) -> dict[str, Any] | None:
    """无 ffprobe 时解析 ``ffmpeg -i`` stderr。"""
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True,
        text=True,
    )
    text = (proc.stderr or "") + "\n" + (proc.stdout or "")
    dur_m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    fps_m = re.search(r"(\d+(?:\.\d+)?)\s*fps", text)
    wh_m = re.search(r"(\d{2,5})x(\d{2,5})", text)
    if not dur_m:
        return None
    hours, minutes, seconds = dur_m.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    fps = float(fps_m.group(1)) if fps_m else float(DEFAULT_SAMPLE_FPS)
    frames = max(1, int(round(duration * fps)))
    width = int(wh_m.group(1)) if wh_m else 128
    height = int(wh_m.group(2)) if wh_m else 128
    if frames < 1 or duration <= 0:
        return None
    return {
        "fps": int(round(fps)) or DEFAULT_SAMPLE_FPS,
        "frames": frames,
        "width": width,
        "height": height,
        "duration": float(duration),
    }


def probe_media(
    path: Path,
    *,
    fps_hint: int | None = None,
    frames_hint: int | None = None,
    ffmpeg: str | None = None,
) -> dict[str, Any]:
    """探测媒体帧数/时长。

    HARD：禁止在探测失败时静默返回 ``frames=1``（会污染 pet.patch，导致序列调度约 42ms）。
    优先 ``frames_hint``（源 GIF 帧数）+ ``fps_hint``；其次 GIF/PIL、ffprobe、ffmpeg -i。
    """
    ffmpeg = ffmpeg or _FFMPEG_EXE or _try_path_ffmpeg()

    # 1) 调用方已知帧数（主路径：GIF 源）
    if frames_hint is not None and frames_hint >= 2:
        fps = int(fps_hint) if fps_hint and fps_hint > 0 else DEFAULT_SAMPLE_FPS
        width, height = 128, 128
        # 尽量补尺寸
        if path.suffix.lower() == ".gif":
            try:
                g = probe_gif(path, fps_hint=fps)
                width, height = g["width"], g["height"]
            except SystemExit:
                pass
        else:
            ffprobe = resolve_ffprobe(ffmpeg)
            dim = (
                probe_via_ffprobe(path, ffprobe)
                if ffprobe
                else (probe_via_ffmpeg(path, ffmpeg) if ffmpeg else None)
            )
            if dim:
                width, height = dim["width"], dim["height"]
        return {
            "fps": fps,
            "frames": int(frames_hint),
            "width": width,
            "height": height,
            "duration": int(frames_hint) / float(fps),
        }

    # 2) 源/产物是 GIF → PIL
    if path.suffix.lower() == ".gif":
        return probe_gif(path, fps_hint=fps_hint)

    # 3) ffprobe
    ffprobe = resolve_ffprobe(ffmpeg)
    if ffprobe:
        got = probe_via_ffprobe(path, ffprobe)
        if got and got["frames"] >= 2:
            if fps_hint and fps_hint > 0:
                got = {
                    **got,
                    "fps": int(fps_hint),
                    "duration": got["frames"] / float(fps_hint),
                }
            return got

    # 4) ffmpeg -i
    if ffmpeg:
        got = probe_via_ffmpeg(path, ffmpeg)
        if got and got["frames"] >= 2:
            if fps_hint and fps_hint > 0:
                got = {
                    **got,
                    "fps": int(fps_hint),
                    "duration": got["frames"] / float(fps_hint),
                }
            return got

    raise SystemExit(
        f"无法探测媒体帧数（禁止写入 frames=1）: {path}\n"
        "请安装 ffprobe，或对透明 GIF 输入编码（脚本可 PIL 数帧），"
        "或传入已知 frames_hint。",
    )


def timing_from_segment(
    *,
    start: float,
    end: float,
    fps: int,
    width: int = 128,
    height: int = 128,
) -> dict[str, Any]:
    """按时间段 × sample_fps 估算帧数（多段从视频切时）。"""
    dur = max(0.01, end - start)
    frames = max(2, int(round(dur * fps)))
    return {
        "fps": int(fps),
        "frames": frames,
        "width": width,
        "height": height,
        "duration": frames / float(fps),
    }


def encode_stacked_mac_video(
    input_path: Path,
    output_path: Path,
    *,
    ss: float | None = None,
    to: float | None = None,
    crf: int = 18,
    max_edge: int = DEFAULT_MAC_STACKED_MAX_EDGE,
    ffmpeg: str | None = None,
    verify: bool = True,
) -> None:
    """
    透明 GIF/视频 → stacked-alpha .mov（H.264）。

    布局：上半 RGB、下半灰度 alpha。WKWebView 可播，前端 WebGL 合成透明。
    （本机 hevc_videotoolbox 常编不出真 HEVC+alpha，故 Mac 伴生默认走 stacked。）
    输出单帧边长默认 ≤256，避免前端每帧上传 720p 贴图。

    HARD：上半在丢 alpha 前必须 premultiply。直接 format=yuv420p 会把透明区
    RGB 烤成白底；H.264 + GL LINEAR 软边再乘 alpha → 桌宠一圈白晕/白噪点。
    """
    ffmpeg = ffmpeg or require_ffmpeg()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.suffix.lower() not in {".mov", ".mp4"}:
        output_path = output_path.with_suffix(".mov")
    edge = max(32, int(max_edge))
    cmd: list[str] = [ffmpeg, "-y"]
    if ss is not None:
        cmd += ["-ss", str(ss)]
    # VP9+alpha WebM 必须显式 libvpx，否则抽不到 alpha
    if input_path.suffix.lower() == ".webm":
        cmd += ["-c:v", "libvpx-vp9"]
    cmd += ["-i", str(input_path)]
    if ss is not None and to is not None:
        cmd += ["-t", str(max(0.01, to - ss))]
    elif to is not None:
        cmd += ["-to", str(to)]
    # 先 format=rgba 再 split；上半 premultiply 再 yuv420p（防透明白底白边）；
    # scale 分别做在 rgb/alpha 上（先 scale 再 alphaextract 会丢透明平面）
    cmd += [
        "-filter_complex",
        (
            "[0:v]format=rgba,split[rgb][a];"
            f"[rgb]premultiply=inplace=1,scale={edge}:-2,format=yuv420p[color];"
            f"[a]alphaextract,scale={edge}:-2,format=yuv420p[alpha];"
            "[color][alpha]vstack=inputs=2"
        ),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        str(crf),
        "-an",
        "-movflags",
        "+faststart",
        str(output_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "").strip()
        raise SystemExit(f"Mac stacked-alpha 编码失败 ({output_path.name}):\n{err[-2000:]}")
    if verify:
        verify_stacked_mac_video(output_path, ffmpeg=ffmpeg)


def verify_stacked_mac_video(
    mov_path: Path,
    *,
    ffmpeg: str | None = None,
    min_ratio: float = MIN_TRANSPARENT_RATIO,
    min_pixels: int = MIN_TRANSPARENT_PIXELS,
) -> dict[str, Any]:
    """抽一帧，检查下半 matte 透明/实体，且上半透明区 RGB 近黑（防白底白边）。"""
    from PIL import Image

    ffmpeg = ffmpeg or require_ffmpeg()
    tmp_png = mov_path.with_suffix(".stacked_probe.png")
    try:
        cmd = [
            ffmpeg,
            "-y",
            "-i",
            str(mov_path),
            "-frames:v",
            "1",
            "-update",
            "1",
            str(tmp_png),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0 or not tmp_png.is_file():
            err = (proc.stderr or proc.stdout or "").strip()
            raise SystemExit(
                f"Mac stacked 校验失败（无法抽帧）: {mov_path.name}\n{err[-1500:]}",
            )
        im = Image.open(tmp_png).convert("RGB")
        if im.height < 4 or im.height % 2 != 0:
            raise SystemExit(
                f"Mac stacked 校验失败: {mov_path.name} 高度异常 {im.width}x{im.height}（应为偶数且为 2×帧高）",
            )
        half = im.height // 2
        color = im.crop((0, 0, im.width, half))
        matte = im.crop((0, half, im.width, im.height)).convert("L")
        vals = list(matte.getdata())
        n = len(vals) or 1
        transparent = sum(1 for v in vals if v < 16)
        opaque = sum(1 for v in vals if v > 240)
        ratio = transparent / n
        if transparent < min_pixels or ratio < min_ratio or opaque < min_pixels:
            raise SystemExit(
                f"Mac stacked 校验失败: {mov_path.name}\n"
                f"  matte 暗像素(alpha≈0)={transparent}/{n} ({ratio:.1%})，亮像素={opaque}\n"
                f"  要求暗≥{min_pixels} 且 ≥{min_ratio:.0%}，且亮≥{min_pixels}\n"
                "请确认输入为已抠像透明 GIF。",
            )
        # 透明区 RGB 若仍近白，GL `color*a` 软边会炸出白晕（桌宠常见故障）
        color_px = list(color.getdata())
        tr_rgb = [color_px[i] for i, v in enumerate(vals) if v < 16]
        if tr_rgb:
            mean_r = sum(p[0] for p in tr_rgb) / len(tr_rgb)
            mean_g = sum(p[1] for p in tr_rgb) / len(tr_rgb)
            mean_b = sum(p[2] for p in tr_rgb) / len(tr_rgb)
            mean_lum = (mean_r + mean_g + mean_b) / 3.0
            if mean_lum > MAX_STACKED_TRANSPARENT_RGB_MEAN:
                raise SystemExit(
                    f"Mac stacked 校验失败: {mov_path.name}\n"
                    f"  透明区上半 RGB 均值=({mean_r:.1f},{mean_g:.1f},{mean_b:.1f}) "
                    f"亮度={mean_lum:.1f} > {MAX_STACKED_TRANSPARENT_RGB_MEAN}\n"
                    "  说明编码未预乘、透明区被烤成白底；Mac 合成会出现一圈白边噪点。\n"
                    "  须在 format=yuv420p 前对 RGB 做 premultiply=inplace=1。",
                )
        else:
            mean_r = mean_g = mean_b = mean_lum = 0.0
        print(
            f"Mac stacked 校验通过 {mov_path.name}: "
            f"matte_dark={transparent}/{n} ({ratio:.1%}) bright={opaque} "
            f"tr_rgb_mean=({mean_r:.1f},{mean_g:.1f},{mean_b:.1f})",
            flush=True,
        )
        return {
            "width": im.width,
            "height": half,
            "stacked_height": im.height,
            "transparent_rgb_mean": (mean_r, mean_g, mean_b),
            "transparent": transparent,
            "opaque": opaque,
            "ratio": ratio,
        }
    finally:
        try:
            tmp_png.unlink(missing_ok=True)
        except OSError:
            pass


def maybe_encode_mac_companion(
    input_path: Path,
    webm_path: Path,
    *,
    ss: float | None = None,
    to: float | None = None,
    ffmpeg: str | None = None,
    enabled: bool = True,
) -> str | None:
    """编码 `{stem}.mov` stacked-alpha；返回文件名或 None。"""
    if not enabled:
        return None
    mov = webm_path.with_suffix(".mov")
    encode_stacked_mac_video(
        input_path,
        mov,
        ss=ss,
        to=to,
        ffmpeg=ffmpeg,
    )
    print(f"已编码 Mac 伴生 {mov}", flush=True)
    return mov.name


def write_video_manifest(
    out_dir: Path,
    prefix: str,
    clips: list[dict[str, Any]],
) -> Path:
    """供 build_pet_json 识别的轻量 manifest。"""
    rows: list[dict[str, Any]] = []
    for i, c in enumerate(clips):
        frames = int(c.get("frames") or 0)
        fps = int(c.get("fps") or 0)
        if frames < 2:
            raise SystemExit(
                f"video manifest 拒绝 frames<2（疑似探测失败占位）: id={c.get('id')!r} frames={frames}",
            )
        if fps < 1:
            raise SystemExit(f"video manifest 拒绝非法 fps: id={c.get('id')!r} fps={fps}")
        row: dict[str, Any] = {
            "id": c["id"],
            "name": c["id"],
            "row": i,
            "frames": frames,
            "fps": fps,
            "kind": c.get("kind"),
        }
        if c.get("video"):
            row["video"] = c["video"]
        if c.get("videoHevc"):
            row["videoHevc"] = c["videoHevc"]
            row["videoAlphaLayout"] = c.get("videoAlphaLayout") or "stacked"
        if not row.get("video") and not row.get("videoHevc"):
            raise SystemExit(
                f"video manifest 行缺少 video 与 videoHevc: id={c.get('id')!r}",
            )
        rows.append(row)
    manifest = {
        "format": "video_webm",
        "prefix": prefix,
        "fps": clips[0]["fps"] if clips else 24,
        "frame_width": clips[0].get("width", 128) if clips else 128,
        "frame_height": clips[0].get("height", 128) if clips else 128,
        "rows": rows,
    }
    path = out_dir / f"{prefix}_video_manifest.json"
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def maybe_also_spritesheet(
    gifs: list[Path],
    names: list[str],
    spritesheet_dir: Path,
    prefix: str,
    frame_size: int,
    fps: int,
) -> None:
    script_dir = Path(__file__).resolve().parent
    make_ss = script_dir / "make_spritesheet.py"
    if not make_ss.is_file():
        raise SystemExit(f"找不到 make_spritesheet.py: {make_ss}")
    cmd = [
        sys.executable,
        str(make_ss),
        "-o",
        str(spritesheet_dir),
        "--prefix",
        prefix,
        "--names",
        ",".join(names),
        "--fps",
        str(fps),
        "--frame-size",
        str(frame_size),
        *[str(g) for g in gifs],
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(
            f"--also-spritesheet 失败:\n{(proc.stderr or proc.stdout or '')[-2000:]}",
        )


def infer_kind(action_id: str, index: int, total: int) -> str:
    if total == 3:
        return "atomic" if index == 1 else "transition"
    if "_to_" in action_id:
        return "transition"
    return "atomic"


def _clip_frame_size_from_probe(
    probe: dict[str, Any],
    *,
    stacked: bool,
) -> tuple[int, int]:
    w = int(probe.get("width") or 128)
    h = int(probe.get("height") or 128)
    if stacked and h >= 2:
        h = max(1, h // 2)
    return w, h


def encode_action_clip(
    input_path: Path,
    out_dir: Path,
    name: str,
    *,
    ss: float | None,
    to: float | None,
    crf: int,
    fps: int,
    ffmpeg: str,
    want_mov: bool,
    want_webm: bool,
    frames_hint: int | None,
    kind: str,
) -> dict[str, Any]:
    """编码单 clip：默认 mov；可选 webm。返回 manifest 行字段。"""
    if not want_mov and not want_webm:
        raise SystemExit("内部错误：want_mov 与 want_webm 均为 False")

    mov_path = out_dir / f"{name}.mov"
    webm_path = out_dir / f"{name}.webm"
    probe: dict[str, Any] | None = None
    stacked = False

    if want_mov:
        encode_stacked_mac_video(
            input_path,
            mov_path,
            ss=ss,
            to=to,
            ffmpeg=ffmpeg,
        )
        print(f"已编码 stacked mov {mov_path}", flush=True)
        probe = probe_media(
            mov_path,
            fps_hint=fps,
            frames_hint=frames_hint,
            ffmpeg=ffmpeg,
        )
        stacked = True

    if want_webm:
        encode_webm(
            input_path,
            webm_path,
            ss=ss,
            to=to,
            crf=crf,
            fps=fps,
            ffmpeg=ffmpeg,
        )
        print(f"已编码 webm {webm_path}", flush=True)
        if probe is None:
            probe = probe_media(
                webm_path,
                fps_hint=fps,
                frames_hint=frames_hint,
                ffmpeg=ffmpeg,
            )
            stacked = False

    assert probe is not None
    if frames_hint is not None and frames_hint >= 2:
        probe = {**probe, "frames": frames_hint, "fps": fps}
    w, h = _clip_frame_size_from_probe(probe, stacked=stacked)
    meta: dict[str, Any] = {
        "id": name,
        "kind": kind,
        "frames": int(probe["frames"]),
        "fps": int(probe["fps"]),
        "width": w,
        "height": h,
    }
    if want_webm:
        meta["video"] = webm_path.name
    if want_mov:
        meta["videoHevc"] = mov_path.name
        meta["videoAlphaLayout"] = "stacked"
    return meta


def main() -> None:
    parser = argparse.ArgumentParser(
        description="已抠像 GIF/视频 → stacked .mov（默认）/ 可选 WebM",
    )
    parser.add_argument(
        "--ensure-only",
        action="store_true",
        help="仅自动安装/探测 ffmpeg（含 libvpx-vp9），成功打印路径后退出",
    )
    parser.add_argument(
        "--no-auto-install",
        action="store_true",
        help="禁止 brew/pip 自动安装，仅使用 PATH 已有 ffmpeg",
    )
    parser.add_argument("--input", type=Path, help="源 GIF 或 mp4/mov")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="输出 .mov/.webm 文件，或多段时的输出目录",
    )
    parser.add_argument("--ss", type=float, help="开始秒（单段）")
    parser.add_argument("--to", type=float, help="结束秒（单段，绝对时间）")
    parser.add_argument("--segments", help="多段 start:end,start:end")
    parser.add_argument("--names", help="多段动作 id，逗号分隔，与 segments 一一对应")
    parser.add_argument("--crf", type=int, default=DEFAULT_CRF)
    parser.add_argument(
        "--also-spritesheet",
        action="store_true",
        help="额外调用 make_spritesheet（默认关闭；WebKit 回退时建议较小 --frame-size）",
    )
    parser.add_argument(
        "--spritesheet-dir",
        type=Path,
        help="--also-spritesheet 输出目录（默认与 -o 目录相同）",
    )
    parser.add_argument(
        "--also-webm",
        action="store_true",
        help="额外产出 VP9+alpha .webm（创建宠默认不生成；引擎仍可播旧 webm）",
    )
    parser.add_argument(
        "--webm-only",
        action="store_true",
        help="仅产出 .webm（旧路径/调试；与默认 stacked mov 互斥）",
    )
    parser.add_argument(
        "--no-mac-video",
        action="store_true",
        help="已弃用：等价于 --webm-only",
    )
    parser.add_argument("--frame-size", type=int, default=128, help="回退合图格尺寸")
    parser.add_argument(
        "--fps",
        type=int,
        default=DEFAULT_SAMPLE_FPS,
        help="采样/输出帧率（写入 manifest，并传给 ffmpeg -r；默认 24）",
    )
    parser.add_argument("--prefix", default="", help="video_manifest / 合图前缀")
    args = parser.parse_args()

    if args.no_mac_video:
        args.webm_only = True
    if args.webm_only and args.also_webm:
        raise SystemExit("--webm-only 与 --also-webm 互斥")
    want_mov = not args.webm_only
    want_webm = bool(args.also_webm or args.webm_only)
    sample_fps = int(args.fps) if args.fps and args.fps > 0 else DEFAULT_SAMPLE_FPS

    auto_install = not args.no_auto_install
    if args.ensure_only:
        path = ensure_ffmpeg(auto_install=auto_install)
        print(path)
        return

    if args.input is None or args.output is None:
        raise SystemExit("编码需要 --input 与 -o/--output；仅探测请用 --ensure-only")
    if not args.input.is_file():
        raise SystemExit(f"输入不存在: {args.input}")

    ffmpeg = ensure_ffmpeg(auto_install=auto_install)
    clips_meta: list[dict[str, Any]] = []

    if args.segments:
        if not args.names:
            raise SystemExit("多段编码需要 --names")
        segs = parse_segments(args.segments)
        names = [n.strip() for n in args.names.split(",") if n.strip()]
        if len(names) != len(segs):
            raise SystemExit(f"--names 数量 ({len(names)}) 与 --segments ({len(segs)}) 不一致")
        out_dir = args.output
        if out_dir.suffix.lower() in {".webm", ".mov", ".mp4"}:
            out_dir = out_dir.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        if args.prefix:
            prefix = args.prefix
        elif len(names) == 3:
            prefix = names[1]
        else:
            prefix = names[0]

        for i, ((start, end), name) in enumerate(zip(segs, names)):
            seg_gif = out_dir / f"{name}.gif"
            if not seg_gif.is_file():
                seg_gif = args.input.parent / f"{name}.gif"
            if seg_gif.is_file():
                frames_hint = probe_gif(seg_gif, fps_hint=sample_fps)["frames"]
            else:
                frames_hint = timing_from_segment(
                    start=start, end=end, fps=sample_fps
                )["frames"]
            meta = encode_action_clip(
                args.input,
                out_dir,
                name,
                ss=start,
                to=end,
                crf=args.crf,
                fps=sample_fps,
                ffmpeg=ffmpeg,
                want_mov=want_mov,
                want_webm=want_webm,
                frames_hint=frames_hint,
                kind=infer_kind(name, i, len(names)),
            )
            clips_meta.append(meta)
            print(
                f"已编码 {name} ({meta['frames']}f @ {meta['fps']}fps) "
                f"mov={bool(meta.get('videoHevc'))} webm={bool(meta.get('video'))}",
            )

        write_video_manifest(out_dir, prefix, clips_meta)

        if args.also_spritesheet:
            gifs = [out_dir / f"{n}.gif" for n in names]
            missing = [str(g) for g in gifs if not g.is_file()]
            if missing:
                gifs = [args.input.parent / f"{n}.gif" for n in names]
                missing = [str(g) for g in gifs if not g.is_file()]
            if missing:
                raise SystemExit(
                    "--also-spritesheet 需要各段 GIF（chroma_key 产物），缺失: "
                    + ", ".join(missing),
                )
            ss_dir = args.spritesheet_dir or out_dir
            maybe_also_spritesheet(gifs, names, ss_dir, prefix, args.frame_size, sample_fps)
            print(f"已额外合图 → {ss_dir}")
        return

    # 单段
    out = args.output
    if out.is_dir() or not out.suffix:
        out_dir = Path(out)
        out_dir.mkdir(parents=True, exist_ok=True)
        name = args.input.stem
    else:
        out_dir = out.parent
        out_dir.mkdir(parents=True, exist_ok=True)
        name = out.stem

    frames_hint: int | None = None
    if args.input.suffix.lower() == ".gif" and args.ss is None and args.to is None:
        frames_hint = probe_gif(args.input, fps_hint=sample_fps)["frames"]
    elif args.ss is not None and args.to is not None:
        frames_hint = timing_from_segment(
            start=args.ss, end=args.to, fps=sample_fps
        )["frames"]

    meta = encode_action_clip(
        args.input,
        out_dir,
        name,
        ss=args.ss,
        to=args.to,
        crf=args.crf,
        fps=sample_fps,
        ffmpeg=ffmpeg,
        want_mov=want_mov,
        want_webm=want_webm,
        frames_hint=frames_hint,
        kind=infer_kind(name, 0, 1),
    )
    print(
        f"已编码 {name} ({meta['frames']}f @ {meta['fps']}fps) "
        f"mov={bool(meta.get('videoHevc'))} webm={bool(meta.get('video'))}",
    )
    prefix = args.prefix or name
    write_video_manifest(out_dir, prefix, [meta])

    if args.also_spritesheet:
        gif = args.input if args.input.suffix.lower() == ".gif" else out_dir / f"{name}.gif"
        if not gif.is_file():
            raise SystemExit(f"--also-spritesheet 需要 GIF: {gif}")
        ss_dir = args.spritesheet_dir or out_dir
        maybe_also_spritesheet([gif], [name], ss_dir, prefix, args.frame_size, sample_fps)
        print(f"已额外合图 → {ss_dir}")


if __name__ == "__main__":
    main()
