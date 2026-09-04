#!/usr/bin/env python3
"""
开跑脚手架（草案）
================
在会话工作区创建一批素材任务目录 + jobs.json，避免 Agent 手建散乱路径。
不写 user/；仅准备 workspace。落盘仍走 merge_patch / 白名单。

用法：
  python prepare_pet_run.py --workspace D:/tmp/pet-run --pet-id my-cat
  python prepare_pet_run.py --workspace D:/tmp/pet-run --pet-id my-cat --batches idle,happy
  python prepare_pet_run.py --workspace D:/tmp/pet-run --pet-id san-hua --mode gap --batches dance
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_CREATE_BATCHES = ("idle", "working", "fail", "happy")

# 默认四态：idle 单段；其余三段
BATCH_KIND = {
    "idle": "single",
    "working": "roundtrip",
    "fail": "roundtrip",
    "happy": "roundtrip",
}


def _batch_spec(batch_id: str) -> dict:
    kind = BATCH_KIND.get(batch_id, "roundtrip")
    if kind == "single":
        return {
            "id": batch_id,
            "kind": "single",
            "segments": ["loop"],
            "action_ids": [batch_id],
            "check_loop": True,
        }
    return {
        "id": batch_id,
        "kind": "roundtrip",
        "segments": ["enter", "hold", "leave"],
        "action_ids": [f"idle_to_{batch_id}", batch_id, f"{batch_id}_to_idle"],
        "check_loop": True,  # hold 段须接缝
    }


def prepare_pet_run(
    workspace: Path,
    *,
    pet_id: str,
    batches: list[str],
    mode: str,
) -> dict:
    workspace.mkdir(parents=True, exist_ok=True)
    qa = workspace / "qa"
    build = workspace / "_build"
    video = workspace / "video"
    gif = workspace / "gif"
    for d in (qa, build, video, gif):
        d.mkdir(parents=True, exist_ok=True)

    jobs = []
    for bid in batches:
        spec = _batch_spec(bid)
        batch_dir = workspace / "batches" / bid
        batch_dir.mkdir(parents=True, exist_ok=True)
        (batch_dir / "decoded").mkdir(exist_ok=True)
        jobs.append(
            {
                **spec,
                "paths": {
                    "batch_dir": str(batch_dir),
                    "video": str(video / f"{bid}.mp4"),
                    "gif_glob": str(gif / f"{bid}_*.gif"),
                    "build": str(build / bid),
                    "qa_review": str(qa / f"{bid}-review.json"),
                    "contact_sheet": str(qa / f"{bid}-contact-sheet.png"),
                },
                "status": "pending",
            }
        )

    manifest = {
        "version": 1,
        "draft": True,
        "mode": mode,
        "pet_id": pet_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": str(workspace.resolve()),
        "note": "中间产物仅在本 workspace；成品 webp + patch 再写入 accounts/.../user/",
        "qa": {
            "rubric": "references/shared/qa-rubric.md",
            "inspect": "scripts/inspect_frames.py",
            "contact_sheet": "scripts/make_contact_sheet.py",
        },
        "jobs": jobs,
    }
    out = workspace / "jobs.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser(description="Prepare lingxi-pet workspace run scaffold")
    ap.add_argument("--workspace", required=True, help="会话工作区目录（非 user/）")
    ap.add_argument("--pet-id", required=True)
    ap.add_argument(
        "--mode",
        choices=("create-custom", "gap", "import"),
        default="create-custom",
    )
    ap.add_argument(
        "--batches",
        default=",".join(DEFAULT_CREATE_BATCHES),
        help="逗号分隔批次 id，默认 idle,working,fail,happy",
    )
    args = ap.parse_args()
    batches = [b.strip() for b in args.batches.split(",") if b.strip()]
    if not batches:
        raise SystemExit("batches 为空")

    manifest = prepare_pet_run(
        Path(args.workspace),
        pet_id=args.pet_id,
        batches=batches,
        mode=args.mode,
    )
    print(json.dumps({"jobs_json": str(Path(args.workspace) / "jobs.json"), "batches": batches, "mode": args.mode}, ensure_ascii=False))
    print(f"jobs={len(manifest['jobs'])} workspace={manifest['workspace']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
