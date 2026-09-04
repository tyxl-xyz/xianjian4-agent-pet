#!/usr/bin/env python3
"""
幕布色板 + 色键冲突（OpenCV H：0–179）
====================================
供 analyze_reference / suggest_screen_color 共用。
禁止角色高饱和点缀（眼睛等）落入幕布 hue 窗。
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence

import numpy as np

# 与 chroma_key_to_gif 默认 sat/val 对齐
KEY_SAT_MIN = 80
KEY_VAL_MIN = 80
# 角色有色簇与幕布中心 H 的最小安全环距（OpenCV H）
MIN_SAFE_HUE_DIST = 25
CHAR_DIST_THRESH = 45.0 * 0.85

# 固定可生成色板（RGB 锚点 + chroma --hue 窗，OpenCV H）
SCREEN_PALETTE: dict[str, dict[str, Any]] = {
    "green": {
        "rgb": (80, 220, 40),
        "hue_range": (35, 85),
        "prompt_name": "GREEN",
    },
    "cyan": {
        "rgb": (40, 200, 200),
        "hue_range": (75, 105),
        "prompt_name": "CYAN",
    },
    "blue": {
        "rgb": (50, 120, 200),
        "hue_range": (100, 130),
        "prompt_name": "BLUE",
    },
    "magenta": {
        "rgb": (220, 40, 180),
        "hue_range": (140, 170),
        "prompt_name": "MAGENTA",
    },
}


def rgb_to_opencv_hsv(rgb: Sequence[float]) -> tuple[int, int, int]:
    """RGB → OpenCV HSV（H 0–179，S/V 0–255）。"""
    r, g, b = [float(x) / 255.0 for x in rgb[:3]]
    mx, mn = max(r, g, b), min(r, g, b)
    df = mx - mn
    if df < 1e-9:
        h = 0.0
    elif mx == r:
        h = (60.0 * ((g - b) / df) + 360.0) % 360.0
    elif mx == g:
        h = 60.0 * ((b - r) / df) + 120.0
    else:
        h = 60.0 * ((r - g) / df) + 240.0
    s = 0.0 if mx < 1e-9 else df / mx
    v = mx
    return int(round(h / 2.0)) % 180, int(round(s * 255)), int(round(v * 255))


def hue_circular_distance(a: int, b: int) -> int:
    """OpenCV H 环距（0–90 最大）。"""
    d = abs(int(a) % 180 - int(b) % 180)
    return min(d, 180 - d)


def hue_in_range(h: int, hue_range: tuple[int, int]) -> bool:
    lo, hi = hue_range
    h = int(h) % 180
    if lo <= hi:
        return lo <= h <= hi
    return h >= lo or h <= hi


def screen_center_hue(family: str) -> int:
    entry = SCREEN_PALETTE[family]
    return rgb_to_opencv_hsv(entry["rgb"])[0]


def nearest_palette_family(screen_rgb: Sequence[float]) -> str:
    """按 RGB 欧氏距离匹配最近色板项。"""
    best = "green"
    best_d = float("inf")
    rgb = np.asarray(screen_rgb[:3], dtype=np.float64)
    for name, entry in SCREEN_PALETTE.items():
        d = float(np.linalg.norm(rgb - np.asarray(entry["rgb"], dtype=np.float64)))
        if d < best_d:
            best_d = d
            best = name
    return best


def min_distance_to_hues(center_h: int, subject_hues: Iterable[int]) -> int | None:
    hues = list(subject_hues)
    if not hues:
        return None
    return min(hue_circular_distance(center_h, h) for h in hues)


def suggest_screen_from_hues(subject_hues: Sequence[int]) -> dict[str, Any]:
    """
    在固定色板上选与 subject_hues 最小环距最大的幕布。
    无有色簇时默认 green。
    """
    cleaned = [int(h) % 180 for h in subject_hues if h is not None]
    if not cleaned:
        fam = "green"
        entry = SCREEN_PALETTE[fam]
        return {
            "family": fam,
            "rgb": list(entry["rgb"]),
            "hue_range": list(entry["hue_range"]),
            "prompt_name": entry["prompt_name"],
            "min_distance": None,
            "subject_hues": [],
            "chroma_hue_arg": f"{entry['hue_range'][0]}-{entry['hue_range'][1]}",
            "reason": "无高饱和有色簇，默认绿幕",
        }

    best_name = "green"
    best_score = -1
    best_min: int | None = None
    for name, entry in SCREEN_PALETTE.items():
        center = screen_center_hue(name)
        if any(hue_in_range(h, entry["hue_range"]) for h in cleaned):
            score = 0
            md = 0
        else:
            md = min_distance_to_hues(center, cleaned)
            score = int(md) if md is not None else 0
        if score > best_score:
            best_score = score
            best_name = name
            best_min = md if md is not None else 0

    entry = SCREEN_PALETTE[best_name]
    return {
        "family": best_name,
        "rgb": list(entry["rgb"]),
        "hue_range": list(entry["hue_range"]),
        "prompt_name": entry["prompt_name"],
        "min_distance": best_min,
        "subject_hues": cleaned,
        "chroma_hue_arg": f"{entry['hue_range'][0]}-{entry['hue_range'][1]}",
        "reason": (
            f"最大化相对有色簇的最小环距（min_dist={best_min}）；黑白灰已忽略"
        ),
    }


def extract_subject_hues(
    arr: np.ndarray,
    screen_rgb: Sequence[float],
    *,
    sat_min: int = KEY_SAT_MIN,
    val_min: int = KEY_VAL_MIN,
    char_dist_thresh: float = CHAR_DIST_THRESH,
    max_samples: int = 48,
) -> list[int]:
    """从非幕布高饱和像素提取代表性 OpenCV H（量化到约 5°）。"""
    flat = arr.reshape(-1, 3).astype(np.float64)
    screen = np.asarray(screen_rgb[:3], dtype=np.float64)
    dists = np.linalg.norm(flat - screen, axis=1)
    subject = flat[dists > char_dist_thresh]
    if subject.size == 0:
        return []

    hues: list[int] = []
    step = max(1, subject.shape[0] // 8000)
    for rgb in subject[::step]:
        h, s, v = rgb_to_opencv_hsv(rgb)
        if s >= sat_min and v >= val_min:
            hues.append(h)

    if not hues:
        return []

    buckets: dict[int, int] = {}
    for h in hues:
        key = (h // 5) * 5
        buckets[key] = buckets.get(key, 0) + 1
    ranked = sorted(buckets.items(), key=lambda kv: -kv[1])
    return [(key + 2) % 180 for key, _cnt in ranked[:max_samples]]


def key_conflict_report(
    arr: np.ndarray,
    screen_rgb: Sequence[float],
    *,
    screen_family: str | None = None,
) -> dict[str, Any]:
    """检测角色高饱和像素是否会落入幕布 chroma hue 窗。"""
    family = screen_family or nearest_palette_family(screen_rgb)
    if family not in SCREEN_PALETTE:
        family = nearest_palette_family(screen_rgb)
    entry = SCREEN_PALETTE[family]
    hue_range = tuple(entry["hue_range"])
    center_h = screen_center_hue(family)
    subject_hues = extract_subject_hues(arr, screen_rgb)
    min_dist = min_distance_to_hues(center_h, subject_hues)

    conflicting = [
        h
        for h in subject_hues
        if hue_in_range(h, hue_range)
        or hue_circular_distance(h, center_h) < MIN_SAFE_HUE_DIST
    ]
    ok = len(conflicting) == 0
    suggestion = suggest_screen_from_hues(subject_hues) if not ok else None

    errors: list[str] = []
    if not ok:
        sug = suggestion["family"] if suggestion else "cyan"
        sug_rgb = suggestion["rgb"] if suggestion else list(SCREEN_PALETTE["cyan"]["rgb"])
        sug_hue = (
            suggestion["chroma_hue_arg"]
            if suggestion
            else f"{SCREEN_PALETTE['cyan']['hue_range'][0]}-{SCREEN_PALETTE['cyan']['hue_range'][1]}"
        )
        errors.append(
            f"色键冲突：角色高饱和色相 {sorted(set(conflicting))} 与幕布 {family} "
            f"(H≈{center_h}, hue {hue_range[0]}–{hue_range[1]}) 过近"
            f"（min_dist={min_dist}，阈值 {MIN_SAFE_HUE_DIST}）。"
            f"眼睛/服饰等同色会被抠掉。请 redo-bg → 建议 {sug} "
            f"RGB{tuple(sug_rgb)} --hue {sug_hue}"
        )

    return {
        "ok": ok,
        "screen_family": family,
        "screen_hue": center_h,
        "hue_range": list(hue_range),
        "subject_hues": subject_hues,
        "conflicting_hues": sorted(set(conflicting)),
        "min_distance": min_dist,
        "suggested_family": suggestion["family"] if suggestion else None,
        "suggested": suggestion,
        "errors": errors,
    }
