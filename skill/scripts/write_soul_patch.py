#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
写入 user/soul.json（深合并已有文件）。

可从 --soul-json 读入完整人设，或根据 pet.patch 的 displayName/description
生成默认模板（--from-pet）。

HARD：落盘前校验 SoulConfig 必填字段；仅有 name/personality/appearance 等
精简手写稿会拒绝写入。宣称完成前请 --check。

兼容：若仅有遗留 soul.patch.json，读取后写入 soul.json 并删除 patch。
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

from paths import ensure_user_dir  # noqa: E402

SOUL_REQUIRED_KEYS = (
    "userName",
    "greetings",
    "timeGreetings",
    "likes",
    "dislikes",
    "backstory",
    "reactions",
)
SOUL_REACTION_KEYS = ("onWorking", "onAsk", "onSuccess", "onFail")
SOUL_TIME_GREETING_KEYS = (
    "morning",
    "noon",
    "afternoon",
    "dusk",
    "evening",
    "lateNight",
)
# 常见「精简手写」字段：允许作为额外元数据保留，但不能替代必填契约
SOUL_NON_CONTRACT_HINTS = ("personality", "appearance", "creator")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"JSON 根须为 object: {path}")
    return data


def deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in patch.items():
        if value is None:
            continue
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def infer_user_name_from_relationship(pet: dict[str, Any]) -> tuple[str, str]:
    """
    按角色关系推断桌宠称呼用户的默认名。

    返回 (userName, reason)。用户显式指定时勿调用本函数覆盖。
    """
    name = str(pet.get("displayName") or pet.get("id") or "")
    desc = str(pet.get("description") or "")
    blob = f"{name}\n{desc}".lower()
    # 中文关键词不做 lower 丢失，再拼一份原文
    blob_raw = f"{name}\n{desc}"

    def hit(*words: str) -> bool:
        return any(w.lower() in blob or w in blob_raw for w in words)

    # 1) 助理/管家/仆人设定 → 老板
    if hit("助手", "助理", "秘书", "管家", "仆人", "butler", "maid", "assistant", "secretary"):
        return "老板", "assistant-to-boss"

    # 2) 真人/名人/职业角色/搭档 → 朋友（优先于「桌宠」等产品词，避免误判）
    if hit(
        "ceo",
        "总裁",
        "创始人",
        "董事长",
        "真人",
        "名人",
        "明星",
        "演员",
        "歌手",
        "历史",
        "科学家",
        "工程师",
        "程序员",
        "同事",
        "伙伴",
        "搭档",
        "朋友",
        "黄仁勋",
        "jensen",
        "huang",
        "human",
        "celebrity",
        "founder",
        "scientist",
        "engineer",
    ):
        return "朋友", "human-peer"

    # 3) 导师/教练 → 朋友
    if hit("老师", "导师", "教练", "教授", "mentor", "teacher", "coach"):
        return "朋友", "mentor-peer"

    # 4) 经典宠物/萌物 → 主人（勿用单独「宠」，会误伤「桌宠」产品词）
    if hit(
        "猫",
        "狗",
        "萌宠",
        "宠物",
        "三花",
        "狐狸",
        "狼",
        "兔",
        "熊",
        "龙",
        "精灵",
        "兽耳",
        "爪",
        "喵",
        "汪",
        "hamster",
        "cat",
        "dog",
        "kitty",
        "puppy",
    ):
        return "主人", "pet-companion"

    # 5) Q 版真人常见描述（无萌宠关键词）→ 朋友
    if hit("q版", "卡通人", "立绘", "人物", "角色扮演") and not hit("猫", "狗", "萌宠", "宠物", "喵"):
        return "朋友", "stylized-human"

    # 6) 兜底：偏桌宠陪伴仍用主人（与三花一致）
    return "主人", "default-pet"


def default_soul_from_pet(pet: dict[str, Any]) -> dict[str, Any]:
    name = str(pet.get("displayName") or pet.get("id") or "桌宠")
    desc = str(pet.get("description") or f"{name}桌宠")
    user_name, _reason = infer_user_name_from_relationship(pet)
    return {
        "userName": user_name,
        "greetings": [
            f"嗨，{{userName}}！我是{name}~",
            f"又见面啦，{{userName}}！",
            f"{name}在这里陪你哦~",
            "今天也一起加油吧！",
        ],
        "timeGreetings": {
            "morning": [
                f"早上好呀{{userName}}~",
                f"{name}跟你说早安！",
                "新的一天开始了，加油~",
            ],
            "noon": [
                f"中午好，{{userName}}~",
                "记得吃饭哦~",
                f"{name}也休息一下~",
            ],
            "afternoon": [
                "下午好~",
                f"下午犯困了就看看{name}~",
                f"{name}下午也在陪你哦~",
            ],
            "dusk": [
                f"傍晚好呀{{userName}}~",
                "天色渐暗了，今天过得怎么样？",
                "歇一歇吧~",
            ],
            "evening": [
                f"{{userName}}晚上好~",
                "今天辛苦啦！",
                "晚上要好好休息哦~",
            ],
            "lateNight": [
                f"{{userName}}还不睡吗？",
                "都这么晚了…早点休息吧",
                "熬夜对身体不好哦~",
            ],
        },
        "likes": ["被关注", "顺利完成任务", "和你聊天"],
        "dislikes": ["被冷落", "连续失败", "熬夜"],
        "backstory": f"{desc}。跟着{{userName}}一起工作，喜欢在旁边打气、庆祝成功、安慰失败。",
        "reactions": {
            "onWorking": [
                f"{name}开工啦，别打扰我~",
                "认真处理中…",
                f"等{name}忙完就来找{{userName}}~",
                "专注专注…马上好！",
                "收到，正在处理~",
            ],
            "onAsk": [
                f"{{userName}}，这里要你来决定~",
                "我拿不准…你看看？",
                "需要你确认一下~",
                f"{name}卡住了，帮我选一下！",
            ],
            "onSuccess": [
                "搞定啦！夸我夸我~",
                "完美收工！",
                f"任务完成！{{userName}}快来看看~",
                "轻轻松松~ 还有什么要做的？",
            ],
            "onFail": [
                "呜…搞砸了…",
                f"对不起{{userName}}…",
                "失误了！下次一定行！",
                "好像哪里不太对…",
            ],
        },
    }


def _non_empty_str_list(value: Any) -> bool:
    return isinstance(value, list) and any(
        isinstance(x, str) and x.strip() for x in value
    )


def validate_soul_errors(soul: dict[str, Any]) -> list[str]:
    """返回完备性错误列表（空 = 可通过 HARD 门禁）。"""
    errors: list[str] = []
    if not isinstance(soul, dict) or not soul:
        return ["soul 根须为非空 object"]

    for key in SOUL_REQUIRED_KEYS:
        if key not in soul:
            errors.append(f"缺少必填字段: {key}")

    user_name = soul.get("userName")
    if "userName" in soul and (
        not isinstance(user_name, str) or not user_name.strip()
    ):
        errors.append("userName 须为非空字符串")

    if "greetings" in soul and not _non_empty_str_list(soul.get("greetings")):
        errors.append("greetings 须为非空字符串数组")

    for list_key in ("likes", "dislikes"):
        if list_key in soul and not _non_empty_str_list(soul.get(list_key)):
            errors.append(f"{list_key} 须为非空字符串数组")

    backstory = soul.get("backstory")
    if "backstory" in soul and (
        not isinstance(backstory, str) or not backstory.strip()
    ):
        errors.append("backstory 须为非空字符串")

    time_g = soul.get("timeGreetings")
    if "timeGreetings" in soul:
        if not isinstance(time_g, dict):
            errors.append("timeGreetings 须为 object")
        else:
            for tk in SOUL_TIME_GREETING_KEYS:
                if tk not in time_g:
                    errors.append(f"timeGreetings 缺少: {tk}")
                elif not _non_empty_str_list(time_g.get(tk)):
                    errors.append(f"timeGreetings.{tk} 须为非空字符串数组")

    reactions = soul.get("reactions")
    if "reactions" in soul:
        if not isinstance(reactions, dict):
            errors.append("reactions 须为 object")
        else:
            for rk in SOUL_REACTION_KEYS:
                if rk not in reactions:
                    errors.append(f"reactions 缺少: {rk}")
                elif not _non_empty_str_list(reactions.get(rk)):
                    errors.append(f"reactions.{rk} 须为非空字符串数组")

    # 仅有精简手写字段、无契约字段时给明确提示
    if errors and any(k in soul for k in SOUL_NON_CONTRACT_HINTS):
        if not any(k in soul for k in ("userName", "greetings", "reactions")):
            errors.append(
                "检测到 personality/appearance 等精简字段，但缺少 SoulConfig 契约；"
                "请先 write_soul_patch.py --from-pet，再按角色润色（禁止手写精简版冒充完成）",
            )
    return errors


def validate_soul(soul: dict[str, Any]) -> list[str]:
    """兼容旧名：现为硬错误列表（非 warning）。"""
    return validate_soul_errors(soul)


def check_soul_file(soul_path: Path) -> dict[str, Any]:
    """检查已落盘 soul.json 是否完备（供收尾 HARD GATE）。"""
    if not soul_path.is_file():
        return {
            "ok": False,
            "soulJson": str(soul_path),
            "errors": ["soul.json 不存在"],
        }
    try:
        data = load_json(soul_path)
    except (OSError, ValueError) as err:
        return {
            "ok": False,
            "soulJson": str(soul_path),
            "errors": [f"无法读取 soul.json: {err}"],
        }
    errors = validate_soul_errors(data)
    return {
        "ok": not errors,
        "soulJson": str(soul_path),
        "errors": errors,
    }


def write_soul(pet_id: str, incoming: dict[str, Any], *, replace: bool = False) -> dict[str, Any]:
    info = ensure_user_dir(pet_id)
    soul_path = Path(info["soulJson"])
    legacy_patch = Path(info["userDir"]) / "soul.patch.json"

    existing: dict[str, Any] = {}
    if not replace:
        existing = load_json(soul_path)
        if not existing and legacy_patch.is_file():
            existing = load_json(legacy_patch)

    merged = incoming if replace else deep_merge(existing, incoming)
    errors = validate_soul_errors(merged)
    if errors:
        detail = "; ".join(errors[:12])
        more = f"（另有 {len(errors) - 12} 项）" if len(errors) > 12 else ""
        raise SystemExit(
            f"soul.json 不完备，拒绝写入。{detail}{more}。"
            f"请使用: python scripts/write_soul_patch.py --pet-id {pet_id} --from-pet",
        )

    soul_path.parent.mkdir(parents=True, exist_ok=True)
    with soul_path.open("w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")

    migrated = False
    if legacy_patch.is_file():
        legacy_patch.unlink()
        migrated = True

    return {
        "ok": True,
        "petId": pet_id,
        "soulJson": str(soul_path),
        "replace": replace,
        "migratedFromPatch": migrated,
        "warnings": [],
        "errors": [],
        "hint": "请调用热生效；客户端将合并写出 runtime/soul.json",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="写入 user/soul.json")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument(
        "--soul-json",
        help="完整 soul 对象 JSON 文件；或 - 表示 stdin",
    )
    parser.add_argument(
        "--from-pet",
        action="store_true",
        help="根据 pet.patch.json 的 displayName/description 生成默认人设",
    )
    parser.add_argument(
        "--user-name",
        default=None,
        help="显式指定 userName（覆盖关系推断 / 已有值）",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="整份替换（默认深合并已有 soul.json）",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="仅检查已落盘 soul.json 是否完备（收尾 HARD GATE；不写盘）",
    )
    args = parser.parse_args()

    if args.check:
        info = ensure_user_dir(args.pet_id)
        report = check_soul_file(Path(info["soulJson"]))
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if not report["ok"]:
            print(
                "soul.json 不完备，禁止宣称人设完成。"
                f"请: python scripts/write_soul_patch.py --pet-id {args.pet_id} --from-pet",
                file=sys.stderr,
            )
            for e in report.get("errors") or []:
                print(f"  - {e}", file=sys.stderr)
            return 1
        return 0

    incoming: dict[str, Any] = {}
    if args.soul_json:
        raw = sys.stdin.read() if args.soul_json == "-" else Path(args.soul_json).read_text(
            encoding="utf-8"
        )
        incoming = json.loads(raw)
        if not isinstance(incoming, dict):
            raise ValueError("soul-json 须为 object")

    inferred_reason = None
    if args.from_pet:
        info = ensure_user_dir(args.pet_id)
        pet = load_json(Path(info["patch"]))
        template = default_soul_from_pet(pet)
        _, inferred_reason = infer_user_name_from_relationship(pet)
        # 模板为底、手写增量为上：先补齐契约，再保留润色
        incoming = deep_merge(template, incoming) if incoming else template

    if args.user_name and str(args.user_name).strip():
        incoming["userName"] = str(args.user_name).strip()
        inferred_reason = "cli-override"

    if not incoming:
        raise SystemExit("须提供 --soul-json、--from-pet 或 --check")

    report = write_soul(args.pet_id, incoming, replace=args.replace)
    if inferred_reason:
        report["userName"] = incoming.get("userName")
        report["userNameReason"] = inferred_reason
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
