#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
为 baseModes.actions 生成配对气泡 bubble.texts（对齐三花字段）。

输入：sequence id + 可选 soul.json + pet.patch 元信息（displayName）。
占位符保留 {userName} / {mailboxUnread}（引擎侧解析）。
全池恰好一条含 {mailboxUnread} 的信箱未读提示（ensure_mailbox_unread_tip）。
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

DEFAULT_DWELL = [4.0, 7.0]

# 引擎侧：含 {mailboxUnread} 且未读为 0 时跳过该条文案
MAILBOX_UNREAD_TIP = "{userName}，信箱里还有{mailboxUnread}条新消息没看哦"
MAILBOX_UNREAD_TOKEN = "{mailboxUnread}"


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def infer_semantic_key(seq_id: str) -> str:
    """从 sequence id 推断情绪语义，供文案模板选用。"""
    s = (seq_id or "").lower()
    stem = s[: -len("_play")] if s.endswith("_play") else s
    for key in (
        "clapping",
        "applaud",
        "happy",
        "success",
        "cheer",
        "working",
        "work",
        "busy",
        "fail",
        "sad",
        "error",
        "sleep",
        "walk",
        "wander",
        "wave",
        "wink",
    ):
        if key in stem:
            if key in ("applaud",):
                return "clapping"
            if key in ("success", "cheer"):
                return "happy"
            if key in ("work", "busy"):
                return "working"
            if key in ("sad", "error"):
                return "fail"
            if key in ("walk", "wander"):
                return "wander"
            return key
    return "generic"


def _pick_reaction(soul: dict[str, Any], key: str, limit: int = 2) -> list[str]:
    reactions = soul.get("reactions") if isinstance(soul.get("reactions"), dict) else {}
    lines = reactions.get(key) if isinstance(reactions, dict) else None
    if not isinstance(lines, list):
        return []
    out: list[str] = []
    for line in lines:
        if isinstance(line, str) and line.strip():
            out.append(line.strip())
        if len(out) >= limit:
            break
    return out


def _display_name(pet: dict[str, Any], soul: dict[str, Any]) -> str:
    for src in (pet, soul):
        name = src.get("displayName") if isinstance(src, dict) else None
        if isinstance(name, str) and name.strip():
            return name.strip()
    # soul 无人设名时用 backstory 前缀过短则退回「我」
    return "我"


def _like_snippet(soul: dict[str, Any]) -> str | None:
    likes = soul.get("likes")
    if not isinstance(likes, list):
        return None
    for item in likes:
        if isinstance(item, str) and item.strip() and "{userName}" not in item:
            # 截断过长喜好
            text = item.strip()
            return text if len(text) <= 24 else text[:24] + "…"
    return None


def build_semantic_texts(seq_id: str, pet: dict[str, Any], soul: dict[str, Any]) -> list[str]:
    """按动作语义 + 人设拼 2～3 条文案（可含人设 reactions）。"""
    semantic = infer_semantic_key(seq_id)
    name = _display_name(pet, soul)
    like = _like_snippet(soul)
    texts: list[str] = []

    if semantic == "happy":
        texts.extend(_pick_reaction(soul, "onSuccess", 2))
        texts.extend(
            [
                f"嘿嘿～{name}今天状态绝佳！",
                "{userName}看我～心情好到要起飞！",
            ]
        )
    elif semantic == "working":
        texts.extend(_pick_reaction(soul, "onWorking", 2))
        texts.extend(
            [
                f"{name}开工啦，稍等一下下～",
                "专心处理中…马上好！",
            ]
        )
    elif semantic == "fail":
        texts.extend(_pick_reaction(soul, "onFail", 2))
        texts.extend(
            [
                "唔…翻车了，再试一次就好。",
                "{userName}别担心，失败是成功的垫脚石～",
            ]
        )
    elif semantic == "clapping":
        texts.extend(_pick_reaction(soul, "onSuccess", 1))
        texts.extend(
            [
                "啪啪啪！为{userName}鼓掌！",
                f"{name}给你疯狂打 call～",
                "漂亮！这一波必须鼓掌！",
            ]
        )
    elif semantic == "wander":
        texts.extend(
            [
                f"{name}去溜达一圈，马上回来～",
                "巡视领地中！跟紧点哦",
            ]
        )
    elif semantic == "wave":
        texts.extend(
            [
                "嗨{userName}！跟你打个招呼～",
                f"{name}向你挥挥手！",
            ]
        )
    elif semantic == "wink":
        texts.extend(
            [
                "看懂这个眼神了吗？",
                "悄悄眨一下～{userName}有没有接住？",
            ]
        )
    elif semantic == "sleep":
        texts.extend(
            [
                "困困…让我眯一会儿…",
                "Zzz…别吵，充电中",
            ]
        )
    else:
        greets = soul.get("greetings") if isinstance(soul.get("greetings"), list) else []
        for g in greets[:1]:
            if isinstance(g, str) and g.strip():
                texts.append(g.strip())
        texts.extend(
            [
                f"{name}在这儿陪着你～",
                "{userName}，找我有事吗？",
            ]
        )

    if like and semantic in ("happy", "generic", "clapping"):
        texts.append(f"最喜欢{like}了！")

    # 去重保序，最多 3 条（对齐三花常见 2 条，多留 1 条变化）
    seen: set[str] = set()
    unique: list[str] = []
    for t in texts:
        if t in seen:
            continue
        seen.add(t)
        unique.append(t)
        if len(unique) >= 3:
            break
    return unique or [f"{name}来啦～"]


def build_bubble_for_sequence(
    seq_id: str,
    *,
    pet: dict[str, Any] | None = None,
    soul: dict[str, Any] | None = None,
    dwell_sec: list[float] | None = None,
) -> dict[str, Any]:
    pet = pet or {}
    soul = soul or {}
    return {
        "texts": build_semantic_texts(seq_id, pet, soul),
        "dwellSec": list(dwell_sec or DEFAULT_DWELL),
    }


def _action_seq_ref(entry: dict[str, Any]) -> str:
    seq = entry.get("sequence")
    if isinstance(seq, str) and seq.strip():
        return seq
    left = entry.get("sequenceLeft")
    if isinstance(left, str) and left.strip():
        return left
    aid = entry.get("id")
    return aid if isinstance(aid, str) else "generic"


def _action_key(entry: dict[str, Any]) -> str:
    aid = entry.get("id")
    if isinstance(aid, str) and aid.strip():
        return aid
    return _action_seq_ref(entry)


def _bubble_texts(entry: dict[str, Any]) -> list[Any] | None:
    bubble = entry.get("bubble")
    if not isinstance(bubble, dict):
        return None
    texts = bubble.get("texts")
    return texts if isinstance(texts, list) else None


def pool_has_mailbox_unread(base_modes: dict[str, Any]) -> bool:
    """整份 baseModes 是否已有含 {mailboxUnread} 的气泡文案。"""
    actions = base_modes.get("actions") if isinstance(base_modes, dict) else None
    if not isinstance(actions, list):
        return False
    for item in actions:
        if not isinstance(item, dict):
            continue
        texts = _bubble_texts(item)
        if not texts:
            continue
        for t in texts:
            if isinstance(t, str) and MAILBOX_UNREAD_TOKEN in t:
                return True
    return False


def _is_eligible_for_mailbox_tip(entry: dict[str, Any]) -> bool:
    texts = _bubble_texts(entry)
    if not texts or not any(isinstance(t, str) and t.strip() for t in texts):
        return False
    if any(isinstance(t, str) and MAILBOX_UNREAD_TOKEN in t for t in texts):
        return False
    mode = entry.get("mode")
    if isinstance(mode, str) and mode.lower() == "hold":
        return False
    if infer_semantic_key(_action_seq_ref(entry)) == "sleep":
        return False
    return True


def pick_mailbox_tip_action_index(actions: list[Any]) -> int | None:
    """从合格 actions 中稳定选取一条下标；无可选则 None。"""
    eligible: list[tuple[int, str]] = []
    for i, item in enumerate(actions):
        if isinstance(item, dict) and _is_eligible_for_mailbox_tip(item):
            eligible.append((i, _action_key(item)))
    if not eligible:
        return None
    eligible.sort(key=lambda x: x[1])
    joined = "\0".join(key for _, key in eligible)
    digest = hashlib.md5(joined.encode("utf-8")).hexdigest()
    chosen = int(digest[:8], 16) % len(eligible)
    return eligible[chosen][0]


def ensure_mailbox_unread_tip(
    base_modes: dict[str, Any],
) -> tuple[dict[str, Any], str | None]:
    """
    保证整池恰好一条含 {mailboxUnread} 的文案（已有则跳过）。
    返回 (更新后的 baseModes, 被追加的 action id 或 None)。
    """
    if not isinstance(base_modes, dict):
        return base_modes, None
    if pool_has_mailbox_unread(base_modes):
        return base_modes, None
    actions = base_modes.get("actions")
    if not isinstance(actions, list):
        return base_modes, None
    pick = pick_mailbox_tip_action_index(actions)
    if pick is None:
        return base_modes, None

    new_actions = list(actions)
    entry = dict(new_actions[pick])
    bubble = dict(entry["bubble"]) if isinstance(entry.get("bubble"), dict) else {}
    texts = list(bubble.get("texts") or [])
    texts.append(MAILBOX_UNREAD_TIP)
    bubble["texts"] = texts
    entry["bubble"] = bubble
    new_actions[pick] = entry

    out = dict(base_modes)
    out["actions"] = new_actions
    return out, _action_key(entry)


def ensure_bubbles_on_base_modes(
    base_modes: dict[str, Any],
    *,
    pet: dict[str, Any] | None = None,
    soul: dict[str, Any] | None = None,
    only_missing: bool = True,
) -> tuple[dict[str, Any], list[str]]:
    """
    为 baseModes.actions 补齐 bubble，并保证全池恰好一条信箱未读提示。
    only_missing=True：已有 bubble.texts 的条目不覆盖（Agent 润色后保留）。
    返回 (更新后的 baseModes, 本次补齐/追加 tip 的 action id 列表)。
    """
    if not isinstance(base_modes, dict):
        return base_modes, []
    actions = base_modes.get("actions")
    if not isinstance(actions, list):
        return base_modes, []

    filled: list[str] = []
    new_actions: list[Any] = []
    for item in actions:
        if not isinstance(item, dict):
            new_actions.append(item)
            continue
        entry = dict(item)
        existing_bubble = entry.get("bubble")
        has_texts = (
            isinstance(existing_bubble, dict)
            and isinstance(existing_bubble.get("texts"), list)
            and any(isinstance(t, str) and t.strip() for t in existing_bubble["texts"])
        )
        if only_missing and has_texts:
            new_actions.append(entry)
            continue

        seq_id = entry.get("sequence")
        if not isinstance(seq_id, str) or not seq_id.strip():
            # directional wander 等用 sequenceLeft 作语义参考
            left = entry.get("sequenceLeft")
            seq_id = left if isinstance(left, str) else str(entry.get("id") or "generic")

        entry["bubble"] = build_bubble_for_sequence(seq_id, pet=pet, soul=soul)
        aid = entry.get("id")
        filled.append(aid if isinstance(aid, str) else seq_id)
        new_actions.append(entry)

    out = dict(base_modes)
    out["actions"] = new_actions
    out, tip_id = ensure_mailbox_unread_tip(out)
    if tip_id and tip_id not in filled:
        filled.append(tip_id)
    return out, filled
