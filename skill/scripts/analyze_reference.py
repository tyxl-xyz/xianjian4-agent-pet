#!/usr/bin/env python3
"""
基准图门禁：幕布铺满 + 满画面构图 + 色键冲突（HARD）
========================================
1) 幕布铺满：四角/四边为幕布色，无白边 / 渐变 / inset framing
2) 构图：仅在幕布均匀通过后计算；用各边局部幕布色估包围盒边距
3) 色键冲突：角色高饱和点缀不得落入幕布 hue 窗（防眼睛被抠）

依赖：Pillow、numpy

用法：
  python analyze_reference.py --input reference.png
  python analyze_reference.py --input reference.png --expected cyan --json
  python analyze_reference.py --input reference.png --out-dir ./qa
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

from screen_palette import key_conflict_report, nearest_palette_family

NEAR_WHITE_RGB = np.array([250, 250, 248], dtype=np.float64)
NEAR_WHITE_MAX_DIST = 28.0
CORNER_MAX_DIST = 45.0
CHAR_DIST_THRESH = CORNER_MAX_DIST * 0.85
MAX_NEAR_WHITE_RATIO = 0.12
PATCH = 12
# 边中采样用更薄条带，避免脚底/头顶合法小边距时采到角色
PATCH_EDGE = 4
# 某一行/列判定为「碰到角色」时，非幕布像素至少占该行/列的比例（滤零星噪点）
MIN_ROW_CHAR_FRAC = 0.15

MIN_BBOX_WIDTH = 0.78
MIN_BBOX_HEIGHT = 0.72
MAX_FOOT_GAP = 0.12
MIN_FOOT_GAP = 0.03
MAX_HEAD_GAP = 0.22
MIN_HEAD_GAP = 0.08
MAX_SIDE_ASYMMETRY = 0.08
MAX_SIDE_MARGIN = 0.14


def _mean_patch(arr: np.ndarray, y0: int, x0: int, size: int) -> np.ndarray:
    h, w = arr.shape[:2]
    y1 = min(h, y0 + size)
    x1 = min(w, x0 + size)
    patch = arr[y0:y1, x0:x1].astype(np.float64)
    return patch.reshape(-1, 3).mean(axis=0)


def _dist(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.linalg.norm(a - b))


def _is_near_white(rgb: np.ndarray) -> bool:
    return _dist(rgb, NEAR_WHITE_RGB) <= NEAR_WHITE_MAX_DIST or float(rgb.mean()) >= 245


def _hue_family(rgb: np.ndarray) -> str:
    r, g, b = (rgb / 255.0).tolist()
    mx, mn = max(r, g, b), min(r, g, b)
    if mx - mn < 1e-6:
        return "gray"
    if mx == r:
        h = 60 * (((g - b) / (mx - mn)) % 6)
    elif mx == g:
        h = 60 * (((b - r) / (mx - mn)) + 2)
    else:
        h = 60 * (((r - g) / (mx - mn)) + 4)
    if 35 <= h <= 150:
        return "green"
    if 150 < h < 200:
        return "cyan"
    if 200 <= h <= 270:
        return "blue"
    if h >= 280 or h <= 20:
        return "magenta"
    return "other"


def _rgb_list(rgb: np.ndarray) -> list[float]:
    return [round(float(x), 1) for x in rgb.tolist()]


def _screen_fill_report(arr: np.ndarray) -> dict:
    h, w = arr.shape[:2]
    samples_np = {
        "top_left": _mean_patch(arr, 0, 0, PATCH),
        "top_right": _mean_patch(arr, 0, w - PATCH, PATCH),
        "bottom_left": _mean_patch(arr, h - PATCH, 0, PATCH),
        "bottom_right": _mean_patch(arr, h - PATCH, w - PATCH, PATCH),
        "top_mid": _mean_patch(arr, 0, w // 2 - PATCH_EDGE // 2, PATCH_EDGE),
        "bottom_mid": _mean_patch(
            arr, h - PATCH_EDGE, w // 2 - PATCH_EDGE // 2, PATCH_EDGE
        ),
        "left_mid": _mean_patch(arr, h // 2 - PATCH_EDGE // 2, 0, PATCH_EDGE),
        "right_mid": _mean_patch(
            arr, h // 2 - PATCH_EDGE // 2, w - PATCH_EDGE, PATCH_EDGE
        ),
    }
    corner_keys = ("top_left", "top_right", "bottom_left", "bottom_right")
    edge_keys = ("top_mid", "bottom_mid", "left_mid", "right_mid")
    corners = [samples_np[k] for k in corner_keys]
    screen_rgb = np.mean(corners, axis=0)
    max_corner_pair = 0.0
    for i in range(len(corners)):
        for j in range(i + 1, len(corners)):
            max_corner_pair = max(max_corner_pair, _dist(corners[i], corners[j]))

    white_corners = [k for k in corner_keys if _is_near_white(samples_np[k])]
    # 边中仅抓近白 / 画布 inset；角色贴边时色差属构图问题，不在此误杀
    edge_mismatch = [k for k in edge_keys if _is_near_white(samples_np[k])]

    flat = arr.reshape(-1, 3).astype(np.float64)
    dists = np.linalg.norm(flat - screen_rgb, axis=1)
    screen_ratio = float((dists <= CORNER_MAX_DIST).mean())
    near_white_ratio = float(
        (
            (np.linalg.norm(flat - NEAR_WHITE_RGB, axis=1) <= NEAR_WHITE_MAX_DIST)
            | (flat.mean(axis=1) >= 245)
        ).mean()
    )

    uneven = max_corner_pair > CORNER_MAX_DIST
    errors: list[str] = []
    if white_corners:
        errors.append(
            f"四角近白/画布色（{', '.join(white_corners)}）：幕布未铺满，色键后会残留白框"
        )
    if uneven:
        errors.append(
            f"幕布四角色差过大（{max_corner_pair:.1f} > {CORNER_MAX_DIST}）："
            "存在亮度/色相渐变或不均匀幕布，色键不可用；"
            "请 redo-bg，强调 flat uniform color, no gradients, no vignette。"
            "构图边距已跳过，禁止按假性贴边加大留白。"
        )
    if edge_mismatch and not uneven:
        # 渐变时四边相对均值也常 mismatch，避免重复噪音；均匀幕布下的 inset 仍报
        errors.append(f"四边中点非幕布色（{', '.join(edge_mismatch)}）：存在白边/inset")
    if near_white_ratio > MAX_NEAR_WHITE_RATIO:
        errors.append(
            f"近白像素占比过高（{near_white_ratio:.1%} > {MAX_NEAR_WHITE_RATIO:.0%}）："
            "疑似白边画布或 inset framing"
        )

    return {
        "ok": len(errors) == 0,
        "uneven_screen": uneven,
        "screen_rgb": _rgb_list(screen_rgb),
        "screen_hue_family": _hue_family(screen_rgb),
        "max_corner_pair_dist": round(max_corner_pair, 2),
        "screen_pixel_ratio": round(screen_ratio, 4),
        "near_white_pixel_ratio": round(near_white_ratio, 4),
        "white_corners": white_corners,
        "edge_mismatch": edge_mismatch,
        "errors": errors,
        "_screen_rgb_np": screen_rgb,
        "_samples_np": samples_np,
    }


def _scan_char_from_bottom(arr: np.ndarray, screen_rgb: np.ndarray) -> int | None:
    h, w = arr.shape[:2]
    for y in range(h - 1, -1, -1):
        d = np.linalg.norm(arr[y].astype(np.float64) - screen_rgb, axis=1)
        if float((d > CHAR_DIST_THRESH).mean()) >= MIN_ROW_CHAR_FRAC:
            return y
    return None


def _scan_char_from_top(arr: np.ndarray, screen_rgb: np.ndarray) -> int | None:
    h, w = arr.shape[:2]
    for y in range(0, h):
        d = np.linalg.norm(arr[y].astype(np.float64) - screen_rgb, axis=1)
        if float((d > CHAR_DIST_THRESH).mean()) >= MIN_ROW_CHAR_FRAC:
            return y
    return None


def _scan_char_from_left(arr: np.ndarray, screen_rgb: np.ndarray) -> int | None:
    h, w = arr.shape[:2]
    for x in range(0, w):
        d = np.linalg.norm(arr[:, x].astype(np.float64) - screen_rgb, axis=1)
        if float((d > CHAR_DIST_THRESH).mean()) >= MIN_ROW_CHAR_FRAC:
            return x
    return None


def _scan_char_from_right(arr: np.ndarray, screen_rgb: np.ndarray) -> int | None:
    h, w = arr.shape[:2]
    for x in range(w - 1, -1, -1):
        d = np.linalg.norm(arr[:, x].astype(np.float64) - screen_rgb, axis=1)
        if float((d > CHAR_DIST_THRESH).mean()) >= MIN_ROW_CHAR_FRAC:
            return x
    return None


def _framing_report_local(arr: np.ndarray, samples_np: dict[str, np.ndarray]) -> dict:
    """幕布已均匀时：用四角局部幕布色扫描角色接触边（避免边中贴角色污染）。"""
    h, w = arr.shape[:2]
    top_screen = (samples_np["top_left"] + samples_np["top_right"]) / 2.0
    bottom_screen = (samples_np["bottom_left"] + samples_np["bottom_right"]) / 2.0
    left_screen = (samples_np["top_left"] + samples_np["bottom_left"]) / 2.0
    right_screen = (samples_np["top_right"] + samples_np["bottom_right"]) / 2.0

    y1 = _scan_char_from_bottom(arr, bottom_screen)
    y0 = _scan_char_from_top(arr, top_screen)
    x0 = _scan_char_from_left(arr, left_screen)
    x1 = _scan_char_from_right(arr, right_screen)

    if y0 is None or y1 is None or x0 is None or x1 is None or y1 < y0 or x1 < x0:
        return {
            "ok": False,
            "skipped": False,
            "errors": ["未检测到角色主体（相对局部幕布色）"],
            "bbox": None,
            "margins": None,
        }

    bbox_w = (x1 - x0 + 1) / float(w)
    bbox_h = (y1 - y0 + 1) / float(h)
    left = x0 / float(w)
    right = (w - 1 - x1) / float(w)
    top = y0 / float(h)
    foot = (h - 1 - y1) / float(h)
    asym = abs(left - right)

    errors: list[str] = []
    if bbox_w < MIN_BBOX_WIDTH:
        errors.append(
            f"角色包围盒过窄（宽 {bbox_w:.0%} < {MIN_BBOX_WIDTH:.0%}）：主体偏小，桌宠窗口难辨"
        )
    if bbox_h < MIN_BBOX_HEIGHT:
        errors.append(
            f"角色包围盒过矮（高 {bbox_h:.0%} < {MIN_BBOX_HEIGHT:.0%}）：上下留白过大"
        )
    if foot > MAX_FOOT_GAP:
        errors.append(
            f"脚底边距过大（{foot:.0%} > {MAX_FOOT_GAP:.0%}）：角色悬浮，应对齐底边"
        )
    if foot < MIN_FOOT_GAP:
        errors.append(
            f"脚底边距过小（{foot:.0%} < {MIN_FOOT_GAP:.0%}）：可能裁脚，略上移或减小角色"
        )
    if top > MAX_HEAD_GAP:
        errors.append(
            f"头顶边距过大（{top:.0%} > {MAX_HEAD_GAP:.0%}）：上半画幅浪费"
        )
    if top < MIN_HEAD_GAP:
        errors.append(
            f"头顶边距过小（{top:.0%} < {MIN_HEAD_GAP:.0%}）：可能裁头顶/耳朵"
        )
    if max(left, right) > MAX_SIDE_MARGIN:
        errors.append(
            f"左右幕布边距过大（L={left:.0%} R={right:.0%}，上限各 {MAX_SIDE_MARGIN:.0%}）"
        )
    if asym > MAX_SIDE_ASYMMETRY:
        errors.append(
            f"左右不对称（|L-R|={asym:.0%} > {MAX_SIDE_ASYMMETRY:.0%}）"
        )

    return {
        "ok": len(errors) == 0,
        "skipped": False,
        "bbox": {
            "x0": x0,
            "y0": y0,
            "x1": x1,
            "y1": y1,
            "width_ratio": round(bbox_w, 4),
            "height_ratio": round(bbox_h, 4),
            "area_ratio": round(bbox_w * bbox_h, 4),
        },
        "margins": {
            "left": round(left, 4),
            "right": round(right, 4),
            "top": round(top, 4),
            "foot": round(foot, 4),
            "side_asymmetry": round(asym, 4),
        },
        "local_screen_rgb": {
            "top": _rgb_list(top_screen),
            "bottom": _rgb_list(bottom_screen),
            "left": _rgb_list(left_screen),
            "right": _rgb_list(right_screen),
        },
        "thresholds": {
            "min_bbox_width": MIN_BBOX_WIDTH,
            "min_bbox_height": MIN_BBOX_HEIGHT,
            "foot_gap": [MIN_FOOT_GAP, MAX_FOOT_GAP],
            "head_gap": [MIN_HEAD_GAP, MAX_HEAD_GAP],
            "max_side_margin": MAX_SIDE_MARGIN,
            "max_side_asymmetry": MAX_SIDE_ASYMMETRY,
        },
        "errors": errors,
    }


def analyze(path: Path, *, expected: str | None = None) -> dict:
    im = Image.open(path).convert("RGB")
    arr = np.asarray(im)
    h, w = arr.shape[:2]
    if h < PATCH * 2 or w < PATCH * 2:
        return {
            "ok": False,
            "path": str(path),
            "errors": [f"图片过小: {w}x{h}"],
            "width": w,
            "height": h,
        }

    fill = _screen_fill_report(arr)
    samples_np = fill.pop("_samples_np")
    screen_rgb_np = fill.pop("_screen_rgb_np")

    framing_skipped = not fill["ok"]
    if framing_skipped:
        framing = {
            "ok": True,
            "skipped": True,
            "reason": "幕布铺满未通过（渐变/白边/不匀），构图边距不可信已跳过",
            "bbox": None,
            "margins": None,
            "errors": [],
        }
        key_conflict = {
            "ok": True,
            "skipped": True,
            "reason": "幕布铺满未通过，色键冲突检查已跳过",
            "errors": [],
        }
    else:
        framing = _framing_report_local(arr, samples_np)
        family = nearest_palette_family(screen_rgb_np)
        key_conflict = key_conflict_report(
            arr, screen_rgb_np, screen_family=family
        )

    errors = (
        list(fill.get("errors") or [])
        + list(framing.get("errors") or [])
        + list(key_conflict.get("errors") or [])
    )
    family = fill.get("screen_hue_family")
    if expected:
        allowed = {expected}
        if expected == "green":
            allowed |= {"green", "cyan"}
        if expected == "cyan":
            allowed |= {"cyan", "green", "blue"}
        # 以色板匹配为准：若 key_conflict 已识别 family，优先用之
        matched = key_conflict.get("screen_family") or family
        if matched not in allowed and family not in allowed:
            errors.append(f"幕布色相为 {matched or family}，期望 {expected}")

    ok = len(errors) == 0
    if ok:
        hint = "幕布铺满 + 满画面构图 + 色键冲突检查通过"
    elif framing_skipped or fill.get("uneven_screen"):
        hint = (
            "幕布不合格（渐变/白边/不匀）。使用 redo-bg / redo-border："
            "flat uniform color, no gradients, no vignette, edge-to-edge。"
            "禁止按裁脚/裁顶去加大留白。"
        )
    elif not key_conflict.get("ok", True) and not key_conflict.get("skipped"):
        sug = key_conflict.get("suggested_family") or "cyan"
        hint = (
            f"色键冲突（角色点缀与幕布同色相，眼睛等会被抠掉）。"
            f"redo-bg → 换 {sug} 幕布；可用 "
            f"suggest_screen_color.py --from-image。"
        )
    else:
        hint = (
            "构图未通过。加强 COMPOSITION 定量段后 redo-compose："
            "脚底 3–12%、头顶 8–22%、宽≥78%、高≥72%；禁止只写「居中」。"
        )

    return {
        "ok": ok,
        "path": str(path),
        "width": w,
        "height": h,
        "screen_fill": {k: v for k, v in fill.items() if k != "errors"},
        "framing": {k: v for k, v in framing.items() if k != "errors"},
        "key_conflict": {k: v for k, v in key_conflict.items() if k != "errors"},
        "errors": errors,
        "hint": hint,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="基准图幕布铺满 + 满画面构图 + 色键冲突门禁"
    )
    ap.add_argument("--input", "-i", required=True)
    ap.add_argument(
        "--expected",
        choices=("green", "cyan", "magenta", "blue"),
        default=None,
    )
    ap.add_argument("--out-dir", type=Path, default=None)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    path = Path(args.input)
    if not path.is_file():
        print(f"文件不存在: {path}", file=sys.stderr)
        return 2

    report = analyze(path, expected=args.expected)
    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        out = args.out_dir / "reference_compose.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        status = "PASS" if report["ok"] else "FAIL"
        print(f"[{status}] {path}")
        sf = report.get("screen_fill") or {}
        fr = report.get("framing") or {}
        kc = report.get("key_conflict") or {}
        m = fr.get("margins") or {}
        b = fr.get("bbox") or {}
        print(
            f"  screen={sf.get('screen_rgb')} family={sf.get('screen_hue_family')} "
            f"screen_ratio={sf.get('screen_pixel_ratio')}"
        )
        if fr.get("skipped"):
            print(f"  framing: skipped — {fr.get('reason')}")
        elif b:
            print(
                f"  bbox={b.get('width_ratio'):.0%}x{b.get('height_ratio'):.0%} "
                f"foot={m.get('foot'):.0%} top={m.get('top'):.0%} "
                f"L/R={m.get('left'):.0%}/{m.get('right'):.0%}"
            )
        if kc.get("skipped"):
            print(f"  key_conflict: skipped — {kc.get('reason')}")
        else:
            print(
                f"  key_conflict: ok={kc.get('ok')} "
                f"subject_hues={kc.get('subject_hues')} "
                f"min_dist={kc.get('min_distance')} "
                f"suggested={kc.get('suggested_family')}"
            )
        for err in report.get("errors") or []:
            print(f"  - {err}")
        print(f"  hint: {report.get('hint')}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
