#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
behaviors 格式契约（与 desktop-pet CodexPetJson / PetManifest 对齐）：

  behaviors: { [event: string]: string }   # 值必须是 sequence / atomic id

禁止写成 baseModes 风格的 { actions: [{ id, weight }] }——会导致整份 pet.json
serde 失败，桌宠「活动中但主窗不 show」。
"""

from __future__ import annotations

from typing import Any


BEHAVIORS_FORMAT_HINT = (
    'behaviors 须为字符串映射，例如 {"working": "working_play", '
    '"walking": "running_right"}；'
    "不要写 {\"working\": {\"actions\": [...]}}（那是 baseModes 格式）。"
)


def coerce_behavior_value(val: Any) -> str | None:
    """
    将单个 behaviors 值规范为非空字符串 id。
    - 已是 str → strip
    - 误写成 {actions:[{id,weight}]} → 取权重最高的 id（兼容事故产物）
    - 其它类型 → None
    """
    if isinstance(val, str):
        s = val.strip()
        return s or None
    if isinstance(val, dict):
        actions = val.get("actions")
        if isinstance(actions, list) and actions:
            best_id: str | None = None
            best_w = -1
            for item in actions:
                if not isinstance(item, dict):
                    continue
                raw_id = item.get("id")
                if not isinstance(raw_id, str) or not raw_id.strip():
                    continue
                w = item.get("weight", 1)
                try:
                    w_i = int(w)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    w_i = 1
                if w_i >= best_w:
                    best_w = w_i
                    best_id = raw_id.strip()
            if best_id:
                return best_id
        raw = val.get("id")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return None


def sanitize_behaviors_map(
    behaviors: Any,
    *,
    strict: bool = False,
) -> tuple[dict[str, str], list[str]]:
    """
    清洗整表 behaviors。
    返回 (规范化后的 map, 警告列表)。
    strict=True 时遇到无法 coerce 的值抛 ValueError（用于 merge 入参）。
    """
    if behaviors is None:
        return {}, []
    if not isinstance(behaviors, dict):
        if strict:
            raise ValueError(
                f"behaviors 必须为 object，得到 {type(behaviors).__name__}。"
                f" {BEHAVIORS_FORMAT_HINT}"
            )
        return {}, [f"behaviors 非 object（{type(behaviors).__name__}），已丢弃"]

    out: dict[str, str] = {}
    warnings: list[str] = []
    for key, val in behaviors.items():
        if not isinstance(key, str) or not key.strip():
            warnings.append(f"跳过非法 behaviors 键: {key!r}")
            continue
        coerced = coerce_behavior_value(val)
        if coerced is None:
            msg = (
                f"behaviors.{key} 的值必须为字符串（sequence/atomic id），"
                f"得到 {type(val).__name__}。{BEHAVIORS_FORMAT_HINT}"
            )
            if strict:
                raise ValueError(msg)
            warnings.append(f"已丢弃非法 {msg}")
            continue
        if not isinstance(val, str):
            warnings.append(
                f"behaviors.{key} 已从 {type(val).__name__} 自动规范为 {coerced!r}"
            )
        out[key.strip()] = coerced
    return out, warnings


def _atomic_ids(actions: Any) -> set[str]:
    if not isinstance(actions, dict):
        return set()
    atomic = actions.get("atomic")
    if not isinstance(atomic, dict):
        return set()
    return {k for k in atomic if isinstance(k, str)}


def resolve_run_right_id(atomic_ids: set[str]) -> str | None:
    for cand in ("running_right", "run_right", "walk_right"):
        if cand in atomic_ids:
            return cand
    return None


def resolve_run_left_id(atomic_ids: set[str]) -> str | None:
    # little-meng 等用 running 表示向左跑；Codex 用 running_left
    for cand in ("running_left", "run_left", "walk_left", "running"):
        if cand in atomic_ids:
            return cand
    return None


def build_locomotion_behaviors(actions: Any) -> dict[str, str]:
    """
    按实际存在的 atomic 生成走路/拖拽 behaviors（仅返回应写入的键）。
    Codex 合图默认有 running_left / running_right。
    """
    ids = _atomic_ids(actions)
    right = resolve_run_right_id(ids)
    left = resolve_run_left_id(ids)
    out: dict[str, str] = {}
    if right:
        out["walking"] = right
        out["moving_to_target"] = right
        out["dragging_right"] = right
    if left:
        out["walking_flip"] = left
        out["moving_to_target_flip"] = left
        out["dragging_left"] = left
    if "hang" in ids:
        out["dragging"] = "hang"
    elif "idle" in ids:
        out["dragging"] = "idle"
    return out


def fill_missing_locomotion(
    behaviors: dict[str, str],
    actions: Any,
) -> dict[str, str]:
    """仅追加缺失的 locomotion 键，不覆盖已有。"""
    out = dict(behaviors)
    for key, val in build_locomotion_behaviors(actions).items():
        out.setdefault(key, val)
    return out
