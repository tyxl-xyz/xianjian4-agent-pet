#!/usr/bin/env python3
"""
根据 pet.patch.json（或只读 runtime/pet.json）的 actions 生成 sequences（P2 随机批量）。

默认：从可达 atomic 中随机选取 3 条互不重复、类型尽量多样的组合玩法。

路径见 scripts/paths.py（%APPDATA%/desktop-pet/accounts/{accountId}/pets/{petId}/…）。

用法:
  python generate_sequences.py --pet "%APPDATA%/desktop-pet/pets/my-cat/runtime/pet.json" --count 3 --merge-out seqs.json
  python generate_sequences.py --pet "{patch}" --count 3 --seed 42 --merge-out seqs.json
  # 落盘后：python merge_patch.py … && python apply_user_changes.py --pet-id my-cat（默认不要 --play-sequence）
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path
from typing import Any

TRANSITION_RE = re.compile(r"^(.+)_to_(.+)$")

def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def parse_edge(transition_id: str) -> tuple[str, str] | None:
    m = TRANSITION_RE.match(transition_id)
    if not m:
        return None
    return m.group(1), m.group(2)


def atomic_label(atomics: dict[str, Any], action_id: str) -> str:
    entry = atomics.get(action_id, {})
    name = entry.get("name")
    return str(name) if name else action_id


def build_capability(
    pet: dict[str, Any],
) -> dict[str, Any]:
    home = pet.get("defaultActivity", "idle")
    actions = pet.get("actions", {})
    atomics: dict[str, Any] = actions.get("atomic", {})
    transitions: dict[str, Any] = actions.get("transition", {})

    transition_ids = set(transitions.keys())
    roundtrip: list[str] = []
    sleep_like: list[str] = []
    walk_like: list[str] = []

    for atomic_id in atomics:
        if atomic_id == home:
            continue
        enter_id = f"{home}_to_{atomic_id}"
        leave_id = f"{atomic_id}_to_{home}"
        has_enter = enter_id in transition_ids
        has_leave = leave_id in transition_ids

        if has_enter and has_leave:
            roundtrip.append(atomic_id)
        elif has_enter and not has_leave:
            sleep_like.append(atomic_id)

        if atomic_id.startswith("walk") and has_enter and has_leave:
            walk_like.append(atomic_id)

    disappear_enter = [t for t in transition_ids if "disappear" in t and t.startswith(f"{home}_to_")]

    return {
        "home": home,
        "atomics": atomics,
        "transitions": transitions,
        "roundtrip": roundtrip,
        "sleep_like": sleep_like,
        "walk_like": walk_like,
        "disappear": disappear_enter,
    }


def tpl_roundtrip(
    cap: dict[str, Any],
    atomic_id: str,
    seq_suffix: str = "play",
) -> tuple[str, dict[str, Any]] | None:
    home = cap["home"]
    enter_id = f"{home}_to_{atomic_id}"
    leave_id = f"{atomic_id}_to_{home}"
    if enter_id not in cap["transitions"] or leave_id not in cap["transitions"]:
        return None
    label = atomic_label(cap["atomics"], atomic_id)
    seq_id = f"{atomic_id}_{seq_suffix}"
    return seq_id, {
        "name": f"{label}一下" if not label.endswith("一下") else label,
        "groups": [
            {
                "enter": [{"action": enter_id}],
                "hold": {"action": atomic_id, "duration": {"mode": "clip"}},
                "leave": [{"action": leave_id}],
            }
        ],
        "onComplete": {"action": home},
    }


def tpl_sleep_hold(
    cap: dict[str, Any],
    atomic_id: str,
) -> tuple[str, dict[str, Any]] | None:
    home = cap["home"]
    enter_id = f"{home}_to_{atomic_id}"
    leave_id = f"{atomic_id}_to_{home}"
    if enter_id not in cap["transitions"]:
        return None
    label = atomic_label(cap["atomics"], atomic_id)
    seq_id = f"{atomic_id}_enter"
    seq: dict[str, Any] = {
        "name": f"入睡（{label}）",
        "groups": [
            {
                "enter": [{"action": enter_id}],
                "hold": {"action": atomic_id, "duration": {"mode": "clip"}},
            }
        ],
    }
    if leave_id in cap["transitions"]:
        seq["onInterrupt"] = {"action": leave_id}
    return seq_id, seq


def tpl_walk_edge(
    cap: dict[str, Any],
    atomic_id: str,
    edge: str = "right",
) -> tuple[str, dict[str, Any]] | None:
    home = cap["home"]
    enter_id = f"{home}_to_{atomic_id}"
    leave_id = f"{atomic_id}_to_{home}"
    if enter_id not in cap["transitions"] or leave_id not in cap["transitions"]:
        return None
    label = atomic_label(cap["atomics"], atomic_id)
    edge_label = "右边" if edge == "right" else "左边"
    seq_id = f"{atomic_id}_play"
    return seq_id, {
        "name": f"散步到屏幕{edge_label}",
        "groups": [
            {
                "enter": [{"action": enter_id}],
                "hold": {
                    "action": atomic_id,
                    "duration": {"mode": "untilMoveDone"},
                    "move": {
                        "when": "during",
                        "target": {"ref": "screenEdge", "edge": edge},
                        "speed": 120,
                    },
                },
                "leave": [{"action": leave_id}],
            }
        ],
        "onComplete": {"action": home},
    }


def collect_candidates(cap: dict[str, Any]) -> list[tuple[str, str, tuple[str, dict[str, Any]]]]:
    """返回 (类型标签, 优先级, (seq_id, def))"""
    out: list[tuple[str, str, tuple[str, dict[str, Any]]]] = []
    used_atomic: set[str] = set()

    for aid in cap["walk_like"]:
        built = tpl_walk_edge(cap, aid)
        if built:
            out.append(("walk", aid, built))
            used_atomic.add(aid)

    for aid in cap["sleep_like"]:
        if aid in used_atomic:
            continue
        built = tpl_sleep_hold(cap, aid)
        if built:
            out.append(("sleep", aid, built))
            used_atomic.add(aid)

    for aid in cap["roundtrip"]:
        if aid in used_atomic:
            continue
        if aid.startswith("walk"):
            continue
        built = tpl_roundtrip(cap, aid)
        if not built:
            continue
        if "sleep" in aid:
            out.append(("sleep", aid, built))
        else:
            out.append(("emotion", aid, built))
        used_atomic.add(aid)

    return out


def pick_diverse(
    candidates: list[tuple[str, str, tuple[str, dict[str, Any]]]],
    count: int,
    rng: random.Random,
    existing_ids: set[str],
) -> list[tuple[str, dict[str, Any]]]:
    """优先每种类型各取 1 条，凑满 count。"""
    by_type: dict[str, list[tuple[str, str, tuple[str, dict[str, Any]]]]] = {}
    for item in candidates:
        by_type.setdefault(item[0], []).append(item)

    for key in by_type:
        rng.shuffle(by_type[key])

    picked: list[tuple[str, dict[str, Any]]] = []
    picked_atomic: set[str] = set()
    type_order = ["emotion", "sleep", "walk"]

    def try_add(pool: list[tuple[str, str, tuple[str, dict[str, Any]]]]) -> None:
        for typ, atomic_id, (seq_id, seq_def) in pool:
            if len(picked) >= count:
                return
            if seq_id in existing_ids:
                continue
            if atomic_id in picked_atomic:
                continue
            picked.append((seq_id, seq_def))
            picked_atomic.add(atomic_id)
            existing_ids.add(seq_id)

    for typ in type_order:
        if typ in by_type:
            try_add(by_type[typ])

    # 补足
    rest = [c for c in candidates if c[2][0] not in {p[0] for p in picked}]
    rng.shuffle(rest)
    try_add(rest)

    return picked[:count]


def merge_sequences_into_pet(
    pet: dict[str, Any],
    new_sequences: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    sequences = pet.setdefault("sequences", {})
    for seq_id, seq_def in new_sequences.items():
        sequences[seq_id] = seq_def

    seq_ids = sorted(sequences.keys())
    cats = pet.setdefault("categories", {})
    cats["sequence"] = {
        "name": cats.get("sequence", {}).get("name", "组合"),
        "states": seq_ids,
    }
    return pet


def generate_default_sequences(
    pet: dict[str, Any],
    count: int = 3,
    seed: int | None = None,
) -> dict[str, dict[str, Any]]:
    cap = build_capability(pet)
    candidates = collect_candidates(cap)
    if not candidates:
        return {}

    rng = random.Random(seed)
    existing = set(pet.get("sequences", {}).keys())
    picked = pick_diverse(candidates, count, rng, existing)
    return dict(picked)


def assert_enrich_before_random_sequences(pet: dict[str, Any]) -> None:
    """
    若已具备默认可 enrich 三态，则必须先有 enrich 产出的 *_play + behaviors。
    防止用本脚本代替 enrich_pet_patch（只会随机出 idle_play 等）。
    """
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from enrich_pet_patch import check_default_combo_complete

    report = check_default_combo_complete(pet)
    if not report.get("applicable"):
        return
    if report.get("ok"):
        return
    lines = [
        "禁止用 generate_sequences.py 代替 enrich_pet_patch.py。",
        "默认三态组合（working_play / fail_play / happy_play + behaviors）未齐。",
        "请先: python scripts/enrich_pet_patch.py --pet-id <id>",
        "本脚本仅用于 enrich 之后的 P2「随机追加」组合。",
    ]
    lines.extend(f"  - {e}" for e in report.get("errors") or [])
    raise SystemExit("\n".join(lines))


def _import_readiness():
    import sys

    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from action_readiness import check_actions_ready

    return check_actions_ready


def main() -> None:
    parser = argparse.ArgumentParser(
        description="P2：从 actions 随机追加 sequences（非创建宠默认三态主路径；主路径用 enrich_pet_patch）",
    )
    parser.add_argument("--pet", type=Path, required=True, help="pet.patch.json 或 runtime/pet.json（只读输入）")
    parser.add_argument("--count", type=int, default=3, help="生成条数（默认 3）")
    parser.add_argument("--seed", type=int, help="随机种子（可复现）")
    parser.add_argument("--merge-in", action="store_true", help="写回 pet.patch.json（禁止写 runtime/；预览优先流程不推荐）")
    parser.add_argument(
        "--merge-out",
        type=Path,
        help="仅写出新增 sequences 对象 JSON（再 merge_patch + 热生效）",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--require-ready",
        action="store_true",
        help="默认四态 actions 齐后才生成（流水线推荐）",
    )
    parser.add_argument(
        "--skip-enrich-check",
        action="store_true",
        help="跳过「须先 enrich」门禁（仅排障；正常流程禁止）",
    )
    parser.add_argument(
        "--extra",
        nargs="*",
        default=[],
        metavar="ATOMIC",
        help="用户额外要求的状态 id（与 action_readiness 一致）",
    )
    args = parser.parse_args()

    if not args.pet.is_file():
        raise SystemExit(f"文件不存在: {args.pet}")

    pet = load_json(args.pet)

    if args.require_ready:
        check_actions_ready = _import_readiness()
        readiness = check_actions_ready(pet, extra_roundtrip_atomics=args.extra)
        if not readiness.ready:
            raise SystemExit(readiness.message())

    if not args.skip_enrich_check:
        assert_enrich_before_random_sequences(pet)

    new_seqs = generate_default_sequences(pet, count=args.count, seed=args.seed)

    if not new_seqs:
        print("无可生成的 sequences（检查 actions 是否含 home 往返边）")
        return

    if args.dry_run:
        print(json.dumps(new_seqs, ensure_ascii=False, indent=2))
        return

    if args.merge_out:
        args.merge_out.parent.mkdir(parents=True, exist_ok=True)
        args.merge_out.write_text(
            json.dumps(new_seqs, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"已写出 sequences 补丁 {args.merge_out}，共 {len(new_seqs)} 条（请 merge_patch 后热生效）:")
        for sid in new_seqs:
            print(f"  - {sid}: {new_seqs[sid]['name']}")
        return

    pet = merge_sequences_into_pet(pet, new_seqs)
    text = json.dumps(pet, ensure_ascii=False, indent=2) + "\n"

    if args.merge_in:
        write_path = args.pet
        if args.pet.name == "pet.json" and args.pet.parent.name == "runtime":
            raise SystemExit("禁止 --merge-in 写入 runtime/；请 --pet 指向 user/pet.patch.json")
        write_path.write_text(text, encoding="utf-8")
        print(f"已写入 {write_path}，新增 {len(new_seqs)} 条 sequences:")
    else:
        print(text)
        return

    for sid in new_seqs:
        print(f"  - {sid}: {new_seqs[sid]['name']}")


if __name__ == "__main__":
    main()
