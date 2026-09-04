#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""安全合并写入 user/pet.patch.json（追加 sequences / 深合并 actions）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pathlib import Path as _PathForSys
import sys as _sys

_SCRIPT_DIR = _PathForSys(__file__).resolve().parent
if str(_SCRIPT_DIR) not in _sys.path:
    _sys.path.insert(0, str(_SCRIPT_DIR))

from paths import ensure_user_dir  # noqa: E402
from base_mode_bubble import (  # noqa: E402
    build_bubble_for_sequence,
    ensure_bubbles_on_base_modes,
)
from behaviors_format import sanitize_behaviors_map  # noqa: E402


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根须为 object: {path}")
    return data


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """对象深合并；dict 递归，其它类型 patch 覆盖。"""
    out = dict(base)
    for key, value in patch.items():
        if value is None:
            continue
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def merge_base_modes(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """合并 baseModes：标量深合并；actions 按条目 id 合并（保留已有、追加/覆盖同 id）。"""
    base_only = {k: v for k, v in base.items() if k != "actions"}
    patch_only = {k: v for k, v in patch.items() if k != "actions"}
    out = deep_merge(base_only, patch_only)

    base_actions = (
        list(base.get("actions") or []) if isinstance(base.get("actions"), list) else []
    )
    patch_actions = (
        list(patch.get("actions") or []) if isinstance(patch.get("actions"), list) else []
    )
    if not patch_actions:
        if base_actions:
            out["actions"] = base_actions
        return out

    actions: list[Any] = []
    index: dict[str, int] = {}
    for item in base_actions:
        if isinstance(item, dict):
            entry = dict(item)
            actions.append(entry)
            aid = entry.get("id")
            if isinstance(aid, str):
                index[aid] = len(actions) - 1
        else:
            actions.append(item)

    for item in patch_actions:
        if not isinstance(item, dict):
            actions.append(item)
            continue
        entry = dict(item)
        aid = entry.get("id")
        if isinstance(aid, str) and aid in index:
            existing_entry = actions[index[aid]]
            if isinstance(existing_entry, dict):
                actions[index[aid]] = deep_merge(existing_entry, entry)
            else:
                actions[index[aid]] = entry
        else:
            actions.append(entry)
            if isinstance(aid, str):
                index[aid] = len(actions) - 1

    out["actions"] = actions
    return out


def merge_string_list_unique(base: list[Any], extra: list[Any]) -> list[Any]:
    seen: set[str] = set()
    result: list[Any] = []
    for item in list(base) + list(extra):
        if not isinstance(item, str):
            continue
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def merge_sequences_append_only(
    existing_patch: dict[str, Any],
    runtime: dict[str, Any],
    new_sequences: dict[str, Any],
) -> tuple[dict[str, Any], list[str], list[str]]:
    """返回 (更新后的 sequences 片段, 已追加, 冲突跳过)。"""
    runtime_seqs = (runtime.get("sequences") or {}) if isinstance(runtime, dict) else {}
    patch_seqs = existing_patch.get("sequences") or {}
    if not isinstance(patch_seqs, dict):
        patch_seqs = {}
    added: list[str] = []
    skipped: list[str] = []
    result = dict(patch_seqs)
    for seq_id, definition in new_sequences.items():
        if seq_id in runtime_seqs or seq_id in patch_seqs:
            skipped.append(seq_id)
            continue
        result[seq_id] = definition
        added.append(seq_id)
    return result, added, skipped


_BASE_MODE_WEIGHTS = {
    "happy_play": 40,
    "working_play": 25,
    "fail_play": 10,
}

# 默认三态：只进 sequences / behaviors（事件触发），不自动进 baseModes 闲时随机
_BASE_MODE_SKIP_SEQ_IDS = frozenset({"working_play", "fail_play", "happy_play"})


def _should_skip_base_mode_sequence(seq_id: str) -> bool:
    """不自动挂进 baseModes：默认三态 + walk / wander 类。"""
    if seq_id in _BASE_MODE_SKIP_SEQ_IDS:
        return True
    return seq_id.startswith("sit_walk") or "wander" in seq_id or "walk_" in seq_id or seq_id in (
        "run_left_play",
        "run_right_play",
    )


def _base_mode_entry_id(seq_id: str) -> str:
    if seq_id.endswith("_play"):
        return seq_id[: -len("_play")] + "_micro"
    return seq_id


def append_sequences_to_base_modes(
    existing_patch: dict[str, Any],
    runtime: dict[str, Any],
    added_seq_ids: list[str],
    *,
    soul: dict[str, Any] | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """
    将新追加的 sequence 挂进 baseModes.actions（按 sequence id 去重），
    并按人设/动作语义生成 bubble.texts。
    返回 (完整 baseModes 对象或 None, 本次新挂上的 sequence id 列表)。
    """
    if not added_seq_ids:
        return None, []

    existing_bm = existing_patch.get("baseModes")
    if not isinstance(existing_bm, dict):
        runtime_bm = runtime.get("baseModes") if isinstance(runtime, dict) else None
        existing_bm = runtime_bm if isinstance(runtime_bm, dict) else {}

    actions = list(existing_bm.get("actions") or []) if isinstance(existing_bm.get("actions"), list) else []
    known_seqs: set[str] = set()
    known_ids: set[str] = set()
    for item in actions:
        if not isinstance(item, dict):
            continue
        seq = item.get("sequence")
        if isinstance(seq, str):
            known_seqs.add(seq)
        aid = item.get("id")
        if isinstance(aid, str):
            known_ids.add(aid)

    pet_meta = existing_patch if existing_patch else runtime
    soul = soul or {}

    attached: list[str] = []
    for seq_id in added_seq_ids:
        if _should_skip_base_mode_sequence(seq_id):
            continue
        if seq_id in known_seqs:
            continue
        entry_id = _base_mode_entry_id(seq_id)
        # id 冲突时加后缀，避免覆盖已有 micro
        if entry_id in known_ids:
            entry_id = f"{entry_id}_{seq_id}"
        entry = {
            "id": entry_id,
            "weight": _BASE_MODE_WEIGHTS.get(seq_id, 15),
            "mode": "once",
            "sequence": seq_id,
            "bubble": build_bubble_for_sequence(seq_id, pet=pet_meta, soul=soul),
        }
        actions.append(entry)
        known_seqs.add(seq_id)
        known_ids.add(entry_id)
        attached.append(seq_id)

    if not attached and existing_bm.get("actions"):
        return None, []

    # 无 baseModes 且本次有可挂条目 → 新建；已有但本次无新挂 → 上面已 return
    if not attached:
        return None, []

    home = existing_bm.get("homeActivity")
    if not isinstance(home, str) or not home:
        home = "idle"
        actions_block = existing_patch.get("actions") or runtime.get("actions") or {}
        atomic = actions_block.get("atomic") if isinstance(actions_block, dict) else {}
        if isinstance(atomic, dict) and atomic and "idle" not in atomic:
            home = next(iter(atomic))

    interval = existing_bm.get("scheduleIntervalSec")
    if not (isinstance(interval, list) and len(interval) == 2):
        interval = [30, 60]

    base_modes = {
        "enabled": bool(existing_bm.get("enabled", True)),
        "homeActivity": home,
        "scheduleIntervalSec": interval,
        "actions": actions,
    }
    return base_modes, attached


def apply_patch_file(
    pet_id: str,
    incoming: dict[str, Any],
    *,
    append_sequences_only: bool = False,
) -> dict[str, Any]:
    info = ensure_user_dir(pet_id)
    patch_path = Path(info["patch"])
    runtime_path = Path(info["runtimePetJson"])
    existing = load_json(patch_path)
    runtime = load_json(runtime_path)
    soul = load_json(Path(info["soulJson"]))

    report: dict[str, Any] = {
        "ok": True,
        "petId": pet_id,
        "accountId": info.get("accountId"),
        "patch": str(patch_path),
        "mode": info["mode"],
        "addedSequences": [],
        "skippedSequences": [],
        "baseModesAttached": [],
        "bubblesFilled": [],
        "behaviorsCoerced": [],
        "behaviorsDropped": [],
    }

    incoming = dict(incoming)
    if "behaviors" in incoming:
        # 入参严格：无法规范则直接失败，避免畸形 behaviors 流入 runtime
        incoming["behaviors"], coerced = sanitize_behaviors_map(
            incoming["behaviors"],
            strict=True,
        )
        report["behaviorsCoerced"] = list(coerced)

    if "sequences" in incoming and isinstance(incoming["sequences"], dict):
        seqs, added, skipped = merge_sequences_append_only(
            existing, runtime, incoming["sequences"]
        )
        report["addedSequences"] = added
        report["skippedSequences"] = skipped
        incoming["sequences"] = seqs

        # categories.sequence.states 并集
        cat = incoming.setdefault("categories", {})
        if not isinstance(cat, dict):
            cat = {}
            incoming["categories"] = cat
        seq_cat = cat.setdefault("sequence", {})
        if not isinstance(seq_cat, dict):
            seq_cat = {"name": "组合", "states": []}
            cat["sequence"] = seq_cat
        base_states = []
        existing_cat = (existing.get("categories") or {}).get("sequence") or {}
        if isinstance(existing_cat, dict):
            base_states = list(existing_cat.get("states") or [])
        seq_cat["states"] = merge_string_list_unique(
            base_states, list(seq_cat.get("states") or []) + added
        )
        if "name" not in seq_cat:
            seq_cat["name"] = existing_cat.get("name") if isinstance(existing_cat, dict) else "组合"
            seq_cat["name"] = seq_cat["name"] or "组合"

        # customize-action / 追加 sequence：自动挂进 baseModes（含 bubble）
        # 若调用方（如 enrich）已显式传入 baseModes，则不覆盖挂载结果，但仍补 bubble
        if "baseModes" not in incoming:
            base_modes, attached = append_sequences_to_base_modes(
                existing, runtime, added, soul=soul
            )
            if base_modes is not None:
                incoming["baseModes"] = base_modes
                report["baseModesAttached"] = attached
        else:
            report["baseModesAttached"] = added

    # 对即将写入的 baseModes 补齐缺失 bubble（enrich / 显式传入场景）
    if "baseModes" in incoming and isinstance(incoming["baseModes"], dict):
        filled_bm, filled_ids = ensure_bubbles_on_base_modes(
            incoming["baseModes"],
            pet=existing or incoming,
            soul=soul,
            only_missing=True,
        )
        incoming["baseModes"] = filled_bm
        report["bubblesFilled"] = filled_ids
        # 按 id 合并 actions，避免 deep_merge 整表覆盖丢掉已有条目
        existing_bm = (
            existing.get("baseModes") if isinstance(existing.get("baseModes"), dict) else {}
        )
        incoming["baseModes"] = merge_base_modes(existing_bm, incoming["baseModes"])

    if append_sequences_only:
        slim: dict[str, Any] = {
            "sequences": incoming.get("sequences", {}),
            "categories": incoming.get("categories", {}),
        }
        if "baseModes" in incoming:
            slim["baseModes"] = incoming["baseModes"]
        if "behaviors" in incoming:
            slim["behaviors"] = incoming["behaviors"]
        merged = deep_merge(existing, slim)
    else:
        merged = deep_merge(existing, incoming)

    # 落盘前再洗一遍：清掉历史事故残留的 object 形态 behaviors
    if isinstance(merged.get("behaviors"), dict) or "behaviors" in merged:
        clean, warns = sanitize_behaviors_map(merged.get("behaviors"), strict=False)
        merged["behaviors"] = clean
        for w in warns:
            if "已丢弃" in w:
                report["behaviorsDropped"].append(w)
            elif "自动规范" in w and w not in report["behaviorsCoerced"]:
                report["behaviorsCoerced"].append(w)

    # user-only 首写补齐 id
    if info["mode"] == "user-only":
        merged.setdefault("id", pet_id)
        merged.setdefault("schemaVersion", 3)

    patch_path.parent.mkdir(parents=True, exist_ok=True)
    with patch_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")

    report["hint"] = "请调用热生效（apply_user_changes）；失败时再重启桌宠"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="合并写入 user/pet.patch.json")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument(
        "--patch-json",
        help="完整 patch 片段 JSON 文件；或 - 表示 stdin",
    )
    parser.add_argument(
        "--sequences-json",
        help="仅 sequences 对象 JSON 文件（{seq_id: def}）",
    )
    parser.add_argument(
        "--append-sequences-only",
        action="store_true",
        help="只合并 sequences/categories，不触碰其它字段",
    )
    args = parser.parse_args()

    incoming: dict[str, Any] = {}
    if args.patch_json:
        raw = sys.stdin.read() if args.patch_json == "-" else Path(args.patch_json).read_text(
            encoding="utf-8"
        )
        incoming = json.loads(raw)
    if args.sequences_json:
        seq_raw = Path(args.sequences_json).read_text(encoding="utf-8")
        seqs = json.loads(seq_raw)
        if not isinstance(seqs, dict):
            raise ValueError("sequences-json 须为 object")
        incoming["sequences"] = seqs

    if not incoming:
        raise SystemExit("须提供 --patch-json 或 --sequences-json")

    report = apply_patch_file(
        args.pet_id,
        incoming,
        append_sequences_only=args.append_sequences_only or bool(args.sequences_json),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
