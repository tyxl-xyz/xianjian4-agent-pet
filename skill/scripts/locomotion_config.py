#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跑步/走路素材 → pet.patch 位移配置（behaviors 由 behaviors_format 补；本模块负责 sequence + wander baseMode）。

对齐官方 little-meng：
  - run_left_play / run_right_play（untilMoveDone + screenEdge）
  - baseModes.actions[] 一条 directional wander（sequenceLeft / sequenceRight）
"""

from __future__ import annotations

from typing import Any

from base_mode_bubble import build_bubble_for_sequence, ensure_bubbles_on_base_modes
from behaviors_format import (
    _atomic_ids,
    resolve_run_left_id,
    resolve_run_right_id,
)

RUN_LEFT_PLAY = "run_left_play"
RUN_RIGHT_PLAY = "run_right_play"
DEFAULT_RUN_SPEED = 180


def _atomic_label(actions: dict[str, Any], action_id: str) -> str:
    atomic = actions.get("atomic") if isinstance(actions.get("atomic"), dict) else {}
    entry = atomic.get(action_id) if isinstance(atomic, dict) else None
    if isinstance(entry, dict):
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return action_id


def build_run_edge_sequence(
    atomic_id: str,
    edge: str,
    *,
    label: str | None = None,
    speed: int = DEFAULT_RUN_SPEED,
) -> dict[str, Any]:
    edge_label = "左" if edge == "left" else "右"
    display = label or f"向屏幕{edge_label}边跑"
    return {
        "name": display,
        "groups": [
            {
                "hold": {
                    "action": atomic_id,
                    "duration": {"mode": "untilMoveDone"},
                    "move": {
                        "when": "during",
                        "target": {"ref": "screenEdge", "edge": edge},
                        "speed": speed,
                    },
                },
            }
        ],
    }


def resolve_locomotion_pair(actions: Any) -> tuple[str, str] | None:
    """左右跑步 atomic id；缺任一侧则无法配位移 wander。"""
    ids = _atomic_ids(actions)
    left = resolve_run_left_id(ids)
    right = resolve_run_right_id(ids)
    if not left or not right:
        return None
    return left, right


def build_locomotion_sequences(
    actions: dict[str, Any],
    existing_seqs: dict[str, Any],
) -> dict[str, Any]:
    """缺失时生成 run_left_play / run_right_play。"""
    pair = resolve_locomotion_pair(actions)
    if not pair:
        return {}
    left_id, right_id = pair
    out: dict[str, Any] = {}
    if RUN_LEFT_PLAY not in existing_seqs:
        out[RUN_LEFT_PLAY] = build_run_edge_sequence(
            left_id,
            "left",
            label=_atomic_label(actions, left_id),
        )
    if RUN_RIGHT_PLAY not in existing_seqs:
        out[RUN_RIGHT_PLAY] = build_run_edge_sequence(
            right_id,
            "right",
            label=_atomic_label(actions, right_id),
        )
    return out


def _base_modes_has_wander(base_modes: Any) -> bool:
    if not isinstance(base_modes, dict):
        return False
    actions = base_modes.get("actions")
    if not isinstance(actions, list):
        return False
    return any(
        isinstance(item, dict) and item.get("id") == "wander" for item in actions
    )


def build_wander_action_entry(
    *,
    pet: dict[str, Any],
    soul: dict[str, Any],
) -> dict[str, Any]:
    return {
        "id": "wander",
        "weight": 45,
        "mode": "once",
        "directional": True,
        "sequenceLeft": RUN_LEFT_PLAY,
        "sequenceRight": RUN_RIGHT_PLAY,
        "strollMinTravelRatio": 0.15,
        "strollDistanceRatio": [0.08, 0.22],
        "strollFullEdgeWeight": 0.15,
        "bubble": build_bubble_for_sequence("wander", pet=pet, soul=soul),
    }


def merge_wander_into_base_modes(
    patch: dict[str, Any],
    soul: dict[str, Any],
    *,
    existing_base_modes: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    在已有或新建 baseModes 上追加 directional wander（幂等）。
    返回完整 baseModes；无需变更时返回 None。
    """
    actions = patch.get("actions") or {}
    if not isinstance(actions, dict):
        return None
    pair = resolve_locomotion_pair(actions)
    if not pair:
        return None

    seqs = patch.get("sequences") if isinstance(patch.get("sequences"), dict) else {}
    if RUN_LEFT_PLAY not in seqs or RUN_RIGHT_PLAY not in seqs:
        return None

    bm = dict(existing_base_modes) if isinstance(existing_base_modes, dict) else {}
    if _base_modes_has_wander(bm if bm else patch.get("baseModes")):
        return None

    existing_bm = patch.get("baseModes")
    if isinstance(existing_bm, dict) and _base_modes_has_wander(existing_bm):
        return None

    if not bm and isinstance(existing_bm, dict):
        bm = dict(existing_bm)

    action_list = list(bm.get("actions") or []) if isinstance(bm.get("actions"), list) else []
    if isinstance(existing_bm, dict) and not action_list:
        action_list = list(existing_bm.get("actions") or [])

    action_list.append(build_wander_action_entry(pet=patch, soul=soul))
    bm["actions"] = action_list
    bm["enabled"] = bool(bm.get("enabled", True))

    home = bm.get("homeActivity")
    if not isinstance(home, str) or not home.strip():
        home = patch.get("homeAction") or patch.get("defaultActivity") or "idle"
        bm["homeActivity"] = home

    interval = bm.get("scheduleIntervalSec")
    if not (isinstance(interval, list) and len(interval) == 2):
        if isinstance(existing_bm, dict) and isinstance(existing_bm.get("scheduleIntervalSec"), list):
            bm["scheduleIntervalSec"] = existing_bm["scheduleIntervalSec"]
        else:
            bm["scheduleIntervalSec"] = [30, 60]

    bm, _ = ensure_bubbles_on_base_modes(bm, pet=patch, soul=soul, only_missing=True)
    return bm


def build_locomotion_enrichment(
    patch: dict[str, Any],
    *,
    existing_seq_ids: set[str],
    soul: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    返回待 merge 的 sequences 增量（run_left_play / run_right_play）。
    baseModes.wander 由 merge_wander_into_base_modes 在 enrich 收尾单独合并。
    """
    actions = patch.get("actions") or {}
    if not isinstance(actions, dict):
        return {}

    all_seqs = dict(patch.get("sequences") or {}) if isinstance(patch.get("sequences"), dict) else {}
    new_seqs = build_locomotion_sequences(actions, all_seqs)
    if not new_seqs:
        return {}
    return {"sequences": new_seqs}
