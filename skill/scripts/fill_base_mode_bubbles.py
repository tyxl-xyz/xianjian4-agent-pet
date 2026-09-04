#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为已有 baseModes.actions 按人设/动作语义补齐 bubble.texts。

Phase C：write_soul_patch 之后调用；也可单独回填旧宠。
默认 only_missing（不覆盖 Agent 已润色文案）；--force 全量重生成。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from base_mode_bubble import ensure_bubbles_on_base_modes, load_json  # noqa: E402
from merge_patch import apply_patch_file  # noqa: E402
from paths import ensure_user_dir  # noqa: E402


def fill_bubbles(pet_id: str, *, force: bool = False) -> dict[str, Any]:
    info = ensure_user_dir(pet_id)
    patch_path = Path(info["patch"])
    soul_path = Path(info["soulJson"])
    patch = load_json(patch_path)
    if not patch:
        raise FileNotFoundError(f"缺少 pet.patch.json: {patch_path}")

    base_modes = patch.get("baseModes")
    if not isinstance(base_modes, dict) or not isinstance(base_modes.get("actions"), list):
        return {
            "ok": False,
            "err": "pet.patch.json 尚无 baseModes.actions，请先 enrich / merge_patch",
            "petId": pet_id,
        }

    soul = load_json(soul_path)
    updated, filled = ensure_bubbles_on_base_modes(
        base_modes,
        pet=patch,
        soul=soul,
        only_missing=not force,
    )
    if not filled and not force:
        return {
            "ok": True,
            "petId": pet_id,
            "bubblesFilled": [],
            "skipped": True,
            "hint": "所有 baseModes 条目已有 bubble；如需重写加 --force",
        }

    merge_report = apply_patch_file(
        pet_id,
        {"baseModes": updated},
        append_sequences_only=False,
    )
    return {
        "ok": True,
        "petId": pet_id,
        "bubblesFilled": filled,
        "soulLoaded": bool(soul),
        "merge": merge_report,
        "hint": "已写入 bubble；请热生效。Agent 可按角色口吻再润色 texts 后 merge",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="补齐 baseModes.actions[].bubble")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="覆盖已有 bubble.texts（默认只补缺失）",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.dry_run:
        info = ensure_user_dir(args.pet_id)
        patch = load_json(Path(info["patch"]))
        soul = load_json(Path(info["soulJson"]))
        bm = patch.get("baseModes") if isinstance(patch, dict) else {}
        updated, filled = ensure_bubbles_on_base_modes(
            bm if isinstance(bm, dict) else {},
            pet=patch if isinstance(patch, dict) else {},
            soul=soul,
            only_missing=not args.force,
        )
        print(
            json.dumps(
                {"ok": True, "bubblesFilled": filled, "baseModes": updated},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    report = fill_bubbles(args.pet_id, force=args.force)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
