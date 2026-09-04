#!/usr/bin/env python3
"""
检查 pet.patch.json / runtime pet.json 的 actions 是否满足「默认四态 + 可选扩展态」门禁，再生成 sequences。

默认批次（无人描述时也须完成）：
  - idle：1 段 → atomic idle
  - working / fail / happy：各 3 段 → atomic + idle 往返 transition
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# 默认四视频对应的原子态（idle 单段，其余三段合图）
DEFAULT_BATCH_ATOMICS = ("idle", "working", "fail", "happy")

# 三段态须具备的往返边（相对 defaultActivity）
DEFAULT_ROUNDTRIP_ATOMICS = ("working", "fail", "happy")
MEDIA_KEYS = ("spritesheet", "video", "videoHevc")
MIN_ACTION_FRAMES = 2


@dataclass
class ReadinessResult:
    ready: bool
    home: str
    missing_atomics: list[str] = field(default_factory=list)
    missing_transitions: list[str] = field(default_factory=list)
    extra_missing_atomics: list[str] = field(default_factory=list)
    extra_missing_transitions: list[str] = field(default_factory=list)
    missing_media: list[str] = field(default_factory=list)
    invalid_frame_counts: list[str] = field(default_factory=list)
    missing_media_files: list[str] = field(default_factory=list)

    def message(self) -> str:
        lines = [f"defaultActivity={self.home!r}"]
        if self.missing_atomics:
            lines.append(f"缺 atomic: {', '.join(self.missing_atomics)}")
        if self.missing_transitions:
            lines.append(f"缺 transition: {', '.join(self.missing_transitions)}")
        if self.extra_missing_atomics:
            lines.append(f"缺扩展 atomic: {', '.join(self.extra_missing_atomics)}")
        if self.extra_missing_transitions:
            lines.append(f"缺扩展 transition: {', '.join(self.extra_missing_transitions)}")
        if self.missing_media:
            lines.append(f"缺动作媒体引用: {', '.join(self.missing_media)}")
        if self.invalid_frame_counts:
            lines.append(
                f"动作帧数不足（至少 {MIN_ACTION_FRAMES} 帧）: "
                f"{', '.join(self.invalid_frame_counts)}"
            )
        if self.missing_media_files:
            lines.append(f"动作媒体文件缺失或为空: {', '.join(self.missing_media_files)}")
        if self.ready:
            lines.append("actions 已齐，可生成 sequences。")
        else:
            lines.append("actions 未齐，请继续 merge 素材批次后再生成 sequences。")
        return "\n".join(lines)


def _actions(pet: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    actions = pet.get("actions", {})
    return actions.get("atomic", {}), actions.get("transition", {})


def transitions_for_roundtrip(home: str, atomic_id: str) -> tuple[str, str]:
    return f"{home}_to_{atomic_id}", f"{atomic_id}_to_{home}"


def _required_action_entries(
    pet: dict[str, Any],
    *,
    extra_roundtrip_atomics: list[str] | None,
    skip_default_batch: bool,
) -> list[tuple[str, str, dict[str, Any] | None]]:
    """列出创建自定义宠必须实际可播放的 action。"""
    home = str(pet.get("defaultActivity") or "idle")
    atomics, transitions = _actions(pet)
    required: list[tuple[str, str, dict[str, Any] | None]] = []

    if not skip_default_batch:
        required.extend(
            ("atomic", aid, atomics.get(aid) if isinstance(atomics.get(aid), dict) else None)
            for aid in DEFAULT_BATCH_ATOMICS
        )
        for aid in DEFAULT_ROUNDTRIP_ATOMICS:
            enter_id, leave_id = transitions_for_roundtrip(home, aid)
            required.extend(
                (
                    ("transition", enter_id, transitions.get(enter_id)
                     if isinstance(transitions.get(enter_id), dict) else None),
                    ("transition", leave_id, transitions.get(leave_id)
                     if isinstance(transitions.get(leave_id), dict) else None),
                )
            )

    for aid in extra_roundtrip_atomics or []:
        if aid in DEFAULT_BATCH_ATOMICS:
            continue
        required.append(
            ("atomic", aid, atomics.get(aid) if isinstance(atomics.get(aid), dict) else None)
        )
        enter_id, leave_id = transitions_for_roundtrip(home, aid)
        required.extend(
            (
                ("transition", enter_id, transitions.get(enter_id)
                 if isinstance(transitions.get(enter_id), dict) else None),
                ("transition", leave_id, transitions.get(leave_id)
                 if isinstance(transitions.get(leave_id), dict) else None),
            )
        )
    return required


def _validate_action_media(
    result: ReadinessResult,
    action_id: str,
    entry: dict[str, Any] | None,
    *,
    media_root: Path | None,
) -> None:
    """动作不仅要有 id，还必须引用可用且多帧的媒体。"""
    if not isinstance(entry, dict):
        return

    refs = [
        entry.get(key)
        for key in MEDIA_KEYS
        if isinstance(entry.get(key), str) and entry[key].strip()
    ]
    if not refs:
        result.missing_media.append(action_id)
        return

    frames = entry.get("frames")
    if not isinstance(frames, int) or isinstance(frames, bool) or frames < MIN_ACTION_FRAMES:
        result.invalid_frame_counts.append(action_id)

    if media_root is None:
        return
    try:
        root = media_root.resolve(strict=True)
    except OSError:
        result.missing_media_files.extend(f"{action_id}:{ref}" for ref in refs)
        return

    for ref in refs:
        candidate = root / ref
        try:
            resolved = candidate.resolve(strict=True)
            resolved.relative_to(root)
        except (OSError, ValueError):
            result.missing_media_files.append(f"{action_id}:{ref}")
            continue
        if not resolved.is_file() or resolved.stat().st_size <= 0:
            result.missing_media_files.append(f"{action_id}:{ref}")


def check_actions_ready(
    pet: dict[str, Any],
    *,
    extra_roundtrip_atomics: list[str] | None = None,
    skip_default_batch: bool = False,
    media_root: Path | None = None,
) -> ReadinessResult:
    """
    检查是否可进入 sequences 阶段。

    extra_roundtrip_atomics: 用户额外要求的状态（须有三段往返边，如 sleep）
    skip_default_batch: 仅检查扩展态（极少用）
    """
    home = pet.get("defaultActivity", "idle")
    atomics, transitions = _actions(pet)
    result = ReadinessResult(ready=True, home=home)

    if not skip_default_batch:
        for aid in DEFAULT_BATCH_ATOMICS:
            if aid not in atomics:
                result.missing_atomics.append(aid)
        for aid in DEFAULT_ROUNDTRIP_ATOMICS:
            enter_id, leave_id = transitions_for_roundtrip(home, aid)
            if enter_id not in transitions:
                result.missing_transitions.append(enter_id)
            if leave_id not in transitions:
                result.missing_transitions.append(leave_id)

    for aid in extra_roundtrip_atomics or []:
        if aid in DEFAULT_BATCH_ATOMICS:
            continue
        if aid not in atomics:
            result.extra_missing_atomics.append(aid)
        enter_id, leave_id = transitions_for_roundtrip(home, aid)
        if enter_id not in transitions:
            result.extra_missing_transitions.append(enter_id)
        if leave_id not in transitions:
            result.extra_missing_transitions.append(leave_id)

    for _kind, action_id, entry in _required_action_entries(
        pet,
        extra_roundtrip_atomics=extra_roundtrip_atomics,
        skip_default_batch=skip_default_batch,
    ):
        _validate_action_media(result, action_id, entry, media_root=media_root)

    result.ready = not (
        result.missing_atomics
        or result.missing_transitions
        or result.extra_missing_atomics
        or result.extra_missing_transitions
        or result.missing_media
        or result.invalid_frame_counts
        or result.missing_media_files
    )
    return result


def main() -> None:
    import argparse
    import json
    from pathlib import Path

    parser = argparse.ArgumentParser(description="检查 pet.patch.json actions 是否可生成 sequences")
    parser.add_argument("--pet", type=Path, required=True)
    parser.add_argument(
        "--media-root",
        type=Path,
        default=None,
        help="动作媒体根目录；提供后校验 spritesheet/video/videoHevc 均存在、非空且不越界",
    )
    parser.add_argument(
        "--extra",
        nargs="*",
        default=[],
        metavar="ATOMIC",
        help="用户额外要求的状态 id（须含往返 transition）",
    )
    parser.add_argument("--quiet", action="store_true", help="仅 exit code，不打印")
    args = parser.parse_args()

    pet = json.loads(args.pet.read_text(encoding="utf-8"))
    result = check_actions_ready(
        pet,
        extra_roundtrip_atomics=args.extra,
        media_root=args.media_root,
    )
    if not args.quiet:
        print(result.message())
    raise SystemExit(0 if result.ready else 1)


if __name__ == "__main__":
    main()
