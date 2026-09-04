#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解析灵犀桌宠分层目录（账号隔离：%APPDATA%/desktop-pet/…）。

布局（与 desktop-pet pet_bundle::paths / PRD 对齐）：

  {petRoot}/
    pets/{petId}/official/                      # 共享官方包；skill 禁止写入
    accounts/{accountId}/
      prefs.json
      pets/{petId}/
        user/                                   # skill 唯一写盘
        runtime/                                # official ⊕ user 合并结果
    runtime/                                    # 进程级 MCP（mcp-port / mcp-auth）
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
from pathlib import Path

PET_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
ACCOUNT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,128}$")


def get_pet_root() -> Path:
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if not appdata:
            raise RuntimeError("APPDATA 未设置")
        return Path(appdata) / "desktop-pet"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "desktop-pet"
    # linux 兜底
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / "desktop-pet"
    return Path.home() / ".local" / "share" / "desktop-pet"


def assert_pet_id(pet_id: str) -> str:
    if not PET_ID_RE.match(pet_id):
        raise ValueError(f"无效 petId: {pet_id!r}（须匹配 ^[a-zA-Z0-9_-]{{1,64}}$）")
    return pet_id


def assert_account_id(account_id: str) -> str:
    if not ACCOUNT_ID_RE.match(account_id):
        raise ValueError(
            f"无效 accountId: {account_id!r}（须匹配 ^[a-zA-Z0-9_-]{{1,128}}$）"
        )
    return account_id


def _read_prefs_selected_pet(account_dir: Path) -> str | None:
    prefs = account_dir / "prefs.json"
    if not prefs.is_file():
        return None
    try:
        data = json.loads(prefs.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    selected = data.get("selectedPetId") or data.get("selected_pet_id")
    return selected if isinstance(selected, str) and selected else None


def _list_account_ids(root: Path) -> list[str]:
    accounts = root / "accounts"
    if not accounts.is_dir():
        return []
    ids: list[str] = []
    for child in accounts.iterdir():
        if child.is_dir() and ACCOUNT_ID_RE.match(child.name):
            ids.append(child.name)
    return sorted(ids)


def _wps_collab_scripts_candidates() -> list[Path]:
    """定位官方技能 wps-collab/scripts（沙箱 SKILL_PATH 或本机灵犀安装目录）。"""
    candidates: list[Path] = []
    skill_path = os.environ.get("SKILL_PATH", "").strip()
    if skill_path:
        candidates.append(Path(skill_path) / "wps-collab" / "scripts")

    appdata = os.environ.get("APPDATA", "").strip()
    if appdata:
        lingxi = Path(appdata) / "WPS 灵犀"
        candidates.append(
            lingxi / "serverdir" / "official_skills" / "wps-collab" / "scripts"
        )
        candidates.append(
            lingxi / "serverdir" / "target_skills" / "wps-collab" / "scripts"
        )
        try:
            for child in sorted(lingxi.glob("sandbox_*/skills/wps-collab/scripts")):
                candidates.append(child)
        except OSError:
            pass

    seen: set[str] = set()
    out: list[Path] = []
    for path in candidates:
        try:
            if not path.is_dir():
                continue
            key = str(path.resolve())
        except OSError:
            continue
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _try_login_account_id_via_wps_collab() -> str | None:
    """通过 wps-collab.get_me() 取当前登录 userid；失败返回 None。"""
    for scripts_dir in _wps_collab_scripts_candidates():
        mod_file = scripts_dir / "wps_collab.py"
        if not mod_file.is_file():
            continue
        try:
            spec = importlib.util.spec_from_file_location(
                "lingxi_pet_wps_collab", mod_file
            )
            if spec is None or spec.loader is None:
                continue
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            get_me = getattr(mod, "get_me", None)
            if not callable(get_me):
                continue
            me = get_me()
            if not isinstance(me, dict) or not me.get("success"):
                continue
            data = me.get("data")
            if not isinstance(data, dict):
                continue
            uid = data.get("id")
            if uid is None:
                continue
            current_id = str(uid).strip()
            if current_id and ACCOUNT_ID_RE.match(current_id):
                return current_id
        except Exception:  # noqa: BLE001 — 登录态/依赖不可用时静默回退
            continue
    return None


def resolve_account_id(
    pet_id: str | None = None,
    *,
    explicit: str | None = None,
) -> str:
    """解析当前账号。

    创建/定制桌宠默认落在「当前登录账号」下：优先 wps-collab.get_me()。
    本地尚无 accounts/{id}/ 时仍返回该 id，由 ensure_user_dir 创建目录。

    优先级：
    1. 显式传入 / CLI --account-id
    2. 环境变量 DESKTOP_PET_ACCOUNT_ID / LINGXI_PET_ACCOUNT_ID
    3. wps-collab.get_me() → 当前登录 userid
    4. accounts/ 下仅有一个账号 → 用之
    5. 多个账号时：优先含 pets/{petId}/runtime 或 user 的；
       再按 prefs.selectedPetId == petId；仍歧义则报错
    """
    if explicit:
        return assert_account_id(explicit)

    for env_key in ("DESKTOP_PET_ACCOUNT_ID", "LINGXI_PET_ACCOUNT_ID"):
        env_val = os.environ.get(env_key, "").strip()
        if env_val:
            return assert_account_id(env_val)

    login_id = _try_login_account_id_via_wps_collab()
    if login_id:
        return assert_account_id(login_id)

    root = get_pet_root()
    ids = _list_account_ids(root)
    if not ids:
        raise RuntimeError(
            f"未找到账号目录：{root / 'accounts'}，且无法通过 wps-collab 获取当前登录账号。"
            "请先在灵犀登录，或用 --account-id 指定。"
        )
    if len(ids) == 1:
        return ids[0]

    if pet_id:
        pet_id = assert_pet_id(pet_id)
        with_pet: list[str] = []
        for aid in ids:
            account_pet = root / "accounts" / aid / "pets" / pet_id
            if (account_pet / "runtime").is_dir() or (account_pet / "user").is_dir():
                with_pet.append(aid)
        if len(with_pet) == 1:
            return with_pet[0]

        selected: list[str] = []
        for aid in ids:
            if _read_prefs_selected_pet(root / "accounts" / aid) == pet_id:
                selected.append(aid)
        if len(selected) == 1:
            return selected[0]

    raise RuntimeError(
        "存在多个账号，无法自动判定 accountId。"
        f"候选={ids}。请确认灵犀已登录（wps-collab.get_me），"
        "或传 --account-id / 设置环境变量 DESKTOP_PET_ACCOUNT_ID。"
    )


def resolve_paths(pet_id: str, account_id: str | None = None) -> dict[str, str | bool]:
    pet_id = assert_pet_id(pet_id)
    root = get_pet_root()
    aid = resolve_account_id(pet_id, explicit=account_id)
    account_home = root / "accounts" / aid
    account_exists = account_home.is_dir()

    # 共享官方层
    pets_base = root / "pets"
    pet_home_shared = pets_base / pet_id
    official = pet_home_shared / "official"

    # 账号×角色层
    account_pet_home = account_home / "pets" / pet_id
    user = account_pet_home / "user"
    runtime = account_pet_home / "runtime"

    has_official = False
    if official.is_dir():
        if (official / "pet.json").is_file():
            has_official = True
        else:
            has_official = any(p.is_file() for p in official.iterdir())
    mode = "official-overlay" if has_official else "user-only"
    return {
        "petId": pet_id,
        "accountId": aid,
        "petRoot": str(root),
        "petsBase": str(pets_base),
        "petHome": str(pet_home_shared),  # 含 official 的共享根
        "accountHome": str(account_home),
        "accountPetHome": str(account_pet_home),
        "officialDir": str(official),
        "userDir": str(user),
        "runtimeDir": str(runtime),
        "patch": str(user / "pet.patch.json"),
        "soulJson": str(user / "soul.json"),
        "runtimePetJson": str(runtime / "pet.json"),
        "runtimeSoulJson": str(runtime / "soul.json"),
        "processRuntimeDir": str(root / "runtime"),
        "mode": mode,
        "officialExists": has_official,
        "accountExists": account_exists,
    }


def ensure_user_dir(pet_id: str, account_id: str | None = None) -> dict[str, str | bool]:
    """确保当前账号目录与 user/ 存在（无账号目录则创建）。"""
    info = resolve_paths(pet_id, account_id=account_id)
    Path(str(info["accountHome"])).mkdir(parents=True, exist_ok=True)
    Path(str(info["userDir"])).mkdir(parents=True, exist_ok=True)
    info["accountExists"] = True
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description="灵犀桌宠路径解析（账号隔离）")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument(
        "--account-id",
        default=None,
        help="账号 id；省略则自动解析（当前登录 / 单账号 / 环境变量 / runtime 匹配）",
    )
    parser.add_argument("--print", action="store_true", help="打印 JSON 路径信息")
    parser.add_argument(
        "--ensure-user",
        action="store_true",
        help="确保 accounts/{accountId}/ 与 user/ 存在（无则创建）",
    )
    args = parser.parse_args()

    info = (
        ensure_user_dir(args.pet_id, account_id=args.account_id)
        if args.ensure_user
        else resolve_paths(args.pet_id, account_id=args.account_id)
    )
    if args.print or args.ensure_user:
        print(json.dumps(info, ensure_ascii=False, indent=2))
        return 0
    parser.error("请指定 --print 或 --ensure-user")
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(json.dumps({"ok": False, "err": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
