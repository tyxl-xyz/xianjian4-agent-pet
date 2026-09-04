#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Phase C：在 actions 门禁通过后补全 pet.patch.json（幂等，不覆盖已有键）。

补全：默认 sequences / categories.sequence / behaviors /
clipLoopRange / homeAction / mailboxPresentation（时长 + 可选离场/读信序列，不写 mailboxImage）；
atomic 动作缺失的 effect（粒子预设名）；
baseModes 挂自定义 sequence（排除默认三态与 walk）；有左右跑素材时自动补 run_*_play + wander。
禁止抹掉 actions 素材字段。

HARD：创建宠四态素材齐全后须跑本脚本生成 working_play/fail_play/happy_play；
禁止用 generate_sequences.py 代替。宣称完成前 --check。
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

from base_mode_bubble import ensure_bubbles_on_base_modes  # noqa: E402
from behaviors_format import (  # noqa: E402
    fill_missing_locomotion,
    sanitize_behaviors_map,
)
from locomotion_config import build_locomotion_enrichment, merge_wander_into_base_modes  # noqa: E402
from merge_patch import (  # noqa: E402
    _should_skip_base_mode_sequence as _should_skip_for_base,
    append_sequences_to_base_modes,
    apply_patch_file,
    load_json,
)
from paths import ensure_user_dir  # noqa: E402

DEFAULT_TRIPLETS = ("working", "fail", "happy")
# 默认三态 sequence 中文显示名（atomic.name 缺失时回退）
DEFAULT_TRIPLET_LABELS = {
    "working": "工作",
    "fail": "失败",
    "happy": "开心",
}
# behaviors 事件键 → sequence id（success 对应 happy_play）
DEFAULT_BEHAVIOR_SEQ = {
    "working": "working_play",
    "success": "happy_play",
    "fail": "fail_play",
}

# 离家信箱：与三花 pet.json 时长对齐；序列仅在已有 id 时挂上（禁止编造）
DEFAULT_DISAPPEAR_AFTER_SEC = 1800
DEFAULT_DISAPPEAR_AWAY_SEC = 300
AWAY_SEQUENCE_CANDIDATES = (
    "away_disappear_play",
    "walk_away_play",
    "away_play",
)
READ_LETTER_SEQUENCE_CANDIDATES = (
    "return_appear_play",
    "read_letter_play",
    "return_play",
)

# 粒子预设推断：按 action id / name 关键词（与 effects.md 对齐）；先匹配先生效
EFFECT_KEYWORD_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "sleep",
        ("sleep", "睡觉", "打盹", "打瞌睡", "入睡", "关机", "休眠", "shutdown"),
    ),
    (
        "love",
        ("love", "抚摸", "喜爱", "示爱", "求抱", "脸红", "求食", "讨好"),
    ),
    (
        "dizzy",
        (
            "dizzy",
            "hang",
            "falling",
            "fall",
            "悬垂",
            "自由落体",
            "被拎",
            "被甩",
            "撞墙",
            "晕",
            "触电",
            "爆炸",
            "警报",
            "死机",
        ),
    ),
    (
        "sad",
        ("sad", "fail", "难过", "害怕", "失败", "沮丧", "哭", "受伤", "生病", "报错", "受挫", "error"),
    ),
    (
        "happy",
        (
            "happy",
            "开心",
            "兴奋",
            "庆祝",
            "成功",
            "跳舞",
            "欢呼",
            "胜利",
            "得意",
            "喷火",
            "施法",
            "充能",
            "发光",
            "success",
        ),
    ),
    (
        "walking",
        ("walk", "walking", "跑", "移动", "飞行", "游泳", "滑行", "巡逻", "漫步", "fly"),
    ),
    (
        "playful",
        (
            "playful",
            "翻滚",
            "踢腿",
            "嬉闹",
            "撒娇",
            "打闹",
            "调皮",
            "打翻",
            "吃",
            "抓挠",
            "追逐",
            "belly",
            "roll",
        ),
    ),
    (
        "micro",
        (
            "wink",
            "wave",
            "blink",
            "tail",
            "yawn",
            "stretch",
            "眨眼",
            "摇尾巴",
            "招手",
            "点头",
            "摇头",
            "打哈欠",
            "伸懒腰",
            "抖耳朵",
            "打字",
            "阅读",
            "思考",
            "working",
            "compute",
        ),
    ),
    ("idle", ("idle", "发呆", "站立", "待机", "放松", "休息")),
]


def infer_effect_for_atomic(action_id: str, action: dict[str, Any] | None) -> str | None:
    """根据 atomic id / name 推断预设名；无法判断则 None（宁缺毋滥）。"""
    name = ""
    if isinstance(action, dict):
        n = action.get("name")
        if isinstance(n, str):
            name = n
    text = f"{action_id} {name}".lower()
    for preset, keywords in EFFECT_KEYWORD_RULES:
        for kw in keywords:
            if kw.lower() in text:
                return preset
    return None


def build_atomic_effect_add(patch: dict[str, Any]) -> dict[str, Any] | None:
    """
    为缺失 effect 的 atomic 生成增量（仅写 effect 字段，深合并不丢素材）。
    transition 不写。
    """
    actions = patch.get("actions")
    if not isinstance(actions, dict):
        return None
    atomic = actions.get("atomic")
    if not isinstance(atomic, dict) or not atomic:
        return None

    add_atomic: dict[str, Any] = {}
    for aid, raw in atomic.items():
        if not isinstance(aid, str):
            continue
        entry = raw if isinstance(raw, dict) else {}
        if entry.get("effect"):
            continue
        inferred = infer_effect_for_atomic(aid, entry if isinstance(raw, dict) else None)
        if inferred:
            add_atomic[aid] = {"effect": inferred}

    if not add_atomic:
        return None
    return {"atomic": add_atomic}


def _has_action(actions: dict[str, Any], kind: str, action_id: str) -> bool:
    bucket = (actions.get(kind) or {}) if isinstance(actions, dict) else {}
    return isinstance(bucket, dict) and action_id in bucket


def list_enrichable_default_triplets(patch: dict[str, Any]) -> list[str]:
    """素材已齐、可由 enrich 生成默认 *_play 的三态列表。"""
    actions = patch.get("actions") or {}
    if not isinstance(actions, dict):
        return []
    ready: list[str] = []
    for state in DEFAULT_TRIPLETS:
        enter_id = f"idle_to_{state}"
        leave_id = f"{state}_to_idle"
        if (
            _has_action(actions, "atomic", state)
            and _has_action(actions, "transition", enter_id)
            and _has_action(actions, "transition", leave_id)
        ):
            ready.append(state)
    return ready


def check_default_combo_complete(patch: dict[str, Any]) -> dict[str, Any]:
    """
    检查默认三态组合是否已由 enrich 落盘。

    - actions 为空：ok=False。reference 图 / 空 patch 不能进入角色配置或热生效。
    - applicable=False：已有部分 atomic、但无可 enrich 三态（如仅导入 atomic）→ ok=True，不挡“仅素材导入”收尾
    - applicable=True：须具备对应 *_play sequences 与 behaviors 映射
    """
    actions = patch.get("actions") if isinstance(patch.get("actions"), dict) else {}
    atomics = actions.get("atomic") if isinstance(actions.get("atomic"), dict) else {}
    transitions = (
        actions.get("transition") if isinstance(actions.get("transition"), dict) else {}
    )
    if not atomics and not transitions:
        return {
            "ok": False,
            "applicable": True,
            "enrichable": [],
            "errors": ["actions 为空：基准图不是动作素材，禁止 enrich 或热生效"],
            "hint": "先生成或导入通过动作门禁的素材；无 generate_video 时请上传动作帧/GIF/WebP",
        }

    enrichable = list_enrichable_default_triplets(patch)
    seqs = patch.get("sequences") if isinstance(patch.get("sequences"), dict) else {}
    behaviors, _ = sanitize_behaviors_map(patch.get("behaviors"), strict=False)
    errors: list[str] = []

    if not enrichable:
        return {
            "ok": True,
            "applicable": False,
            "enrichable": [],
            "errors": [],
            "hint": "无可 enrich 的默认三态；组合请走 compose-sequence / merge_patch",
        }

    for state in enrichable:
        seq_id = f"{state}_play"
        if seq_id not in seqs:
            errors.append(
                f"缺少 sequence: {seq_id}（请先 python scripts/enrich_pet_patch.py --pet-id <id>）",
            )

    state_to_beh = {"working": "working", "fail": "fail", "happy": "success"}
    for state in enrichable:
        beh_key = state_to_beh[state]
        seq_id = DEFAULT_BEHAVIOR_SEQ[beh_key]
        if beh_key not in behaviors:
            errors.append(f"behaviors 缺少 {beh_key}→{seq_id}（请先 enrich）")
        elif behaviors.get(beh_key) != seq_id:
            errors.append(
                f"behaviors.{beh_key}={behaviors.get(beh_key)!r}，期望 {seq_id!r}",
            )

    return {
        "ok": not errors,
        "applicable": True,
        "enrichable": enrichable,
        "errors": errors,
        "hint": (
            "默认三态组合已齐（走 behaviors，不一定出现在 baseModes）"
            if not errors
            else "禁止用 generate_sequences.py 代替 enrich_pet_patch.py"
        ),
    }


def check_enrich_file(patch_path: Path) -> dict[str, Any]:
    if not patch_path.is_file():
        return {
            "ok": False,
            "applicable": False,
            "patch": str(patch_path),
            "errors": [f"缺少 pet.patch.json: {patch_path}"],
        }
    patch = load_json(patch_path)
    report = check_default_combo_complete(patch)
    report["patch"] = str(patch_path)
    return report


def _triplet_label(actions: dict[str, Any], state: str) -> str:
    """优先用 atomic 中文 name，否则回退 DEFAULT_TRIPLET_LABELS。"""
    atomic_block = actions.get("atomic")
    entry = atomic_block.get(state) if isinstance(atomic_block, dict) else None
    if isinstance(entry, dict):
        name = entry.get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()
    return DEFAULT_TRIPLET_LABELS.get(state, state)


def _make_roundtrip_sequence(state: str, *, label: str | None = None) -> dict[str, Any]:
    display = (label or DEFAULT_TRIPLET_LABELS.get(state, state)).strip() or state
    if not display.endswith("一下"):
        display = f"{display}一下"
    return {
        "name": display,
        "groups": [
            {
                "enter": [{"action": f"idle_to_{state}"}],
                "hold": {"action": state, "duration": {"mode": "clip"}},
                "leave": [{"action": f"{state}_to_idle"}],
            }
        ],
        "onComplete": {"action": "idle"},
    }


def build_mailbox_presentation_add(
    patch: dict[str, Any],
    available_seqs: set[str],
) -> dict[str, Any] | None:
    """
    生成 mailboxPresentation 增量（仅缺失键）。
    始终可补时长；away/readLetter 仅当候选 sequence 已存在时写入；
    永不写入 mailboxImage（程序内置兜底）。
    """
    existing = patch.get("mailboxPresentation")
    if not isinstance(existing, dict):
        existing = {}

    add: dict[str, Any] = {}
    if "disappearAfterSec" not in existing:
        add["disappearAfterSec"] = DEFAULT_DISAPPEAR_AFTER_SEC
    if "disappearAwaySec" not in existing:
        add["disappearAwaySec"] = DEFAULT_DISAPPEAR_AWAY_SEC

    if "awaySequence" not in existing:
        for cand in AWAY_SEQUENCE_CANDIDATES:
            if cand in available_seqs:
                add["awaySequence"] = cand
                break

    if "readLetterSequence" not in existing:
        for cand in READ_LETTER_SEQUENCE_CANDIDATES:
            if cand in available_seqs:
                add["readLetterSequence"] = cand
                break

    return add or None


def build_enrichment(
    patch: dict[str, Any],
    *,
    soul: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """根据已有 actions 生成待 merge 的增量（仅缺失项）。"""
    actions = patch.get("actions") or {}
    if not isinstance(actions, dict):
        actions = {}

    existing_seqs = patch.get("sequences") or {}
    if not isinstance(existing_seqs, dict):
        existing_seqs = {}

    new_sequences: dict[str, Any] = {}
    seq_states: list[str] = []
    soul = soul or {}

    for state in DEFAULT_TRIPLETS:
        seq_id = f"{state}_play"
        enter_id = f"idle_to_{state}"
        leave_id = f"{state}_to_idle"
        if not (
            _has_action(actions, "atomic", state)
            and _has_action(actions, "transition", enter_id)
            and _has_action(actions, "transition", leave_id)
        ):
            continue
        if seq_id in existing_seqs:
            seq_states.append(seq_id)
            continue
        new_sequences[seq_id] = _make_roundtrip_sequence(
            state,
            label=_triplet_label(actions, state),
        )
        seq_states.append(seq_id)

    loco_incoming = build_locomotion_enrichment(
        {**patch, "sequences": {**existing_seqs, **new_sequences}},
        existing_seq_ids=set(existing_seqs) | set(new_sequences),
        soul=soul,
    )
    loco_seqs = loco_incoming.get("sequences") if isinstance(loco_incoming.get("sequences"), dict) else {}
    if loco_seqs:
        new_sequences.update(loco_seqs)
        for sid in loco_seqs:
            if sid not in seq_states:
                seq_states.append(sid)

    for sid in existing_seqs:
        if sid not in seq_states:
            seq_states.append(sid)

    incoming: dict[str, Any] = {}
    if new_sequences:
        incoming["sequences"] = new_sequences
        incoming["categories"] = {
            "sequence": {
                "name": "组合",
                "states": list(new_sequences.keys()),
            }
        }

    behaviors_raw = patch.get("behaviors")
    behaviors, _beh_warns = sanitize_behaviors_map(behaviors_raw, strict=False)
    available = set(existing_seqs) | set(new_sequences)
    filled = fill_missing_locomotion(behaviors, actions)
    for key, seq_id in (
        ("working", "working_play"),
        ("success", "happy_play"),
        ("fail", "fail_play"),
    ):
        if key not in filled and seq_id in available:
            filled[key] = seq_id

    # 写回：补 locomotion / 三态映射，或把历史 object 形态规范成 string
    if filled != behaviors_raw:
        incoming["behaviors"] = filled

    if "clipLoopRange" not in patch:
        incoming["clipLoopRange"] = [2, 10]
    if "homeAction" not in patch and _has_action(actions, "atomic", "idle"):
        incoming["homeAction"] = "idle"

    mp_add = build_mailbox_presentation_add(patch, available)
    if mp_add:
        incoming["mailboxPresentation"] = mp_add

    effect_add = build_atomic_effect_add(patch)
    if effect_add:
        incoming["actions"] = effect_add

    candidates = [s for s in seq_states if not _should_skip_for_base(s)]
    if "baseModes" not in patch:
        base_modes, _attached = append_sequences_to_base_modes(
            {}, {}, candidates, soul=soul
        )
        if base_modes is not None:
            if _has_action(actions, "atomic", "idle"):
                base_modes["homeActivity"] = "idle"
            elif isinstance(actions.get("atomic"), dict) and actions["atomic"]:
                base_modes["homeActivity"] = next(iter(actions["atomic"]))
            base_modes, _ = ensure_bubbles_on_base_modes(
                base_modes, pet=patch, soul=soul, only_missing=True
            )
            incoming["baseModes"] = base_modes
    else:
        base_modes, attached = append_sequences_to_base_modes(
            patch, {}, candidates, soul=soul
        )
        if base_modes is not None and attached:
            base_modes, _ = ensure_bubbles_on_base_modes(
                base_modes, pet=patch, soul=soul, only_missing=True
            )
            incoming["baseModes"] = base_modes
        else:
            filled_bm, filled_ids = ensure_bubbles_on_base_modes(
                patch["baseModes"],
                pet=patch,
                soul=soul,
                only_missing=True,
            )
            if filled_ids:
                incoming["baseModes"] = filled_bm

    patch_for_wander = {**patch, "sequences": {**existing_seqs, **new_sequences}}
    wander_bm = merge_wander_into_base_modes(
        patch_for_wander,
        soul,
        existing_base_modes=incoming.get("baseModes")
        if isinstance(incoming.get("baseModes"), dict)
        else (patch.get("baseModes") if isinstance(patch.get("baseModes"), dict) else None),
    )
    if wander_bm:
        incoming["baseModes"] = wander_bm

    return incoming


def enrich_pet(pet_id: str) -> dict[str, Any]:
    info = ensure_user_dir(pet_id)
    patch_path = Path(info["patch"])
    patch = load_json(patch_path)
    if not patch:
        raise FileNotFoundError(f"缺少 pet.patch.json: {patch_path}")

    actions = patch.get("actions") if isinstance(patch.get("actions"), dict) else {}
    atomics = actions.get("atomic") if isinstance(actions.get("atomic"), dict) else {}
    transitions = (
        actions.get("transition") if isinstance(actions.get("transition"), dict) else {}
    )
    if not atomics and not transitions:
        raise ValueError(
            "actions 为空：reference 图只能作为后续动作生成的基准图，"
            "请先生成或导入动作素材，禁止继续 enrich。"
        )

    soul = load_json(Path(info["soulJson"]))
    incoming = build_enrichment(patch, soul=soul)
    report: dict[str, Any] = {
        "ok": True,
        "petId": pet_id,
        "patch": str(patch_path),
        "enrichedKeys": sorted(incoming.keys()),
        "skipped": incoming == {},
    }
    if not incoming:
        report["hint"] = "无需补全（字段已齐或缺少可用四态）"
        return report

    merge_report = apply_patch_file(pet_id, incoming, append_sequences_only=False)
    report["merge"] = merge_report
    report["hint"] = (
        "已补全 pet.patch；请 write_soul_patch.py --from-pet，再 --check，然后 fill_base_mode_bubbles.py，"
        "再用角色口吻润色 bubble 并热生效"
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="补全 user/pet.patch.json（Phase C）")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将写入的增量，不落盘",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查默认三态组合（*_play + behaviors）是否已 enrich（收尾 HARD）",
    )
    args = parser.parse_args()

    if args.check:
        info = ensure_user_dir(args.pet_id)
        report = check_enrich_file(Path(info["patch"]))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["ok"]:
            print(
                "默认三态组合未齐，禁止宣称创建/角色配置完成。"
                f"请: python scripts/enrich_pet_patch.py --pet-id {args.pet_id}",
                file=sys.stderr,
            )
            for e in report.get("errors") or []:
                print(f"  - {e}", file=sys.stderr)
            return 1
        return 0

    if args.dry_run:
        info = ensure_user_dir(args.pet_id)
        patch = load_json(Path(info["patch"]))
        soul = load_json(Path(info["soulJson"]))
        incoming = build_enrichment(patch, soul=soul)
        print(json.dumps({"ok": True, "incoming": incoming}, ensure_ascii=False, indent=2))
        return 0

    report = enrich_pet(args.pet_id)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
