#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
合并 user 层并热重载（MCP apply_user_changes）。

当 Client tool `pet_apply_user_changes` 不可用时，skill 可通过 shell_exec 调用本脚本。

依赖：Python 3.9+ 标准库；桌宠已启动且 %APPDATA%/desktop-pet/runtime/mcp-port 存在。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from action_readiness import check_actions_ready  # noqa: E402
from paths import ensure_user_dir  # noqa: E402

PROTOCOL_VERSION = "2024-11-05"
CLIENT_NAME = "lingxi-pet"
CLIENT_VERSION = "1.0.0"
DEFAULT_TIMEOUT_SEC = 60


def assert_user_only_pet_ready(pet_id: str) -> None:
    """自定义宠热生效前必须有完整、可播放的默认动作包。"""
    info = ensure_user_dir(pet_id)
    if info["mode"] != "user-only":
        # 官方宠增量定制可复用 official actions；不在这里要求 user 层重放整包。
        return

    patch_path = Path(str(info["patch"]))
    if not patch_path.is_file():
        raise RuntimeError(f"自定义宠动作门禁失败：缺少 {patch_path}")
    try:
        patch = json.loads(patch_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise RuntimeError(f"自定义宠动作门禁失败：无法读取 {patch_path}: {err}") from err
    if not isinstance(patch, dict):
        raise RuntimeError("自定义宠动作门禁失败：pet.patch.json 根须为 object")

    report = check_actions_ready(
        patch,
        media_root=Path(str(info["userDir"])),
    )
    if not report.ready:
        raise RuntimeError(
            "自定义宠动作门禁失败，禁止热生效。\n"
            f"{report.message()}\n"
            "当前只有 reference 图时只能作为后续动作生成的基准图；"
            "请先生成或上传完整动作素材。"
        )


def default_runtime_dir() -> Path:
    """与 musa-desktop getMcpRuntimeDir / desktop-pet runtime_dir 对齐。"""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        return base / "desktop-pet" / "runtime"
    if sys.platform == "darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "desktop-pet"
            / "runtime"
        )
    return Path.home() / ".local" / "share" / "desktop-pet" / "runtime"


def read_runtime_endpoint(runtime_dir: Path) -> tuple[int, str]:
    port_file = runtime_dir / "mcp-port"
    auth_file = runtime_dir / "mcp-auth"

    if not port_file.is_file():
        raise RuntimeError(
            f"桌宠 MCP 未就绪：找不到 {port_file}。请先在灵犀设置页启动桌宠。"
        )
    if not auth_file.is_file():
        raise RuntimeError(f"桌宠 MCP 鉴权文件缺失：{auth_file}。")

    port_text = port_file.read_text(encoding="utf-8").strip()
    auth_token = auth_file.read_text(encoding="utf-8").strip()
    if not port_text.isdigit() or int(port_text) <= 0:
        raise RuntimeError(f"mcp-port 内容无效：{port_text!r}")
    if not auth_token:
        raise RuntimeError("mcp-auth 为空")
    return int(port_text), auth_token


def parse_json_rpc_payload(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if not raw:
        raise RuntimeError("MCP 响应体为空")
    if raw.startswith("{"):
        data = json.loads(raw)
        if "result" in data or "error" in data:
            return data
        return {"result": data}
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                return json.loads(payload)
    raise RuntimeError(f"无法解析 MCP 响应：{raw[:300]}")


class McpStreamableClient:
    def __init__(self, port: int, auth_token: str, timeout_sec: int = DEFAULT_TIMEOUT_SEC):
        self.base_url = f"http://127.0.0.1:{port}/mcp"
        self.timeout_sec = timeout_sec
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {auth_token}",
        }
        self.session_id: str | None = None
        self._next_id = 1

    def _request(
        self, body: dict[str, Any] | None, *, notification: bool = False
    ) -> dict[str, Any] | None:
        headers = dict(self.headers)
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(self.base_url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_sec) as resp:
                if not self.session_id:
                    sid = resp.headers.get("Mcp-Session-Id") or resp.headers.get("mcp-session-id")
                    if sid:
                        self.session_id = sid.strip()
                raw = resp.read().decode("utf-8")
                if notification or not raw.strip():
                    return None
                return parse_json_rpc_payload(raw)
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"MCP HTTP {err.code}: {detail[:500]}") from err
        except urllib.error.URLError as err:
            raise RuntimeError(f"无法连接桌宠 MCP ({self.base_url})：{err}") from err

    def _rpc(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        msg_id = self._next_id
        self._next_id += 1
        body: dict[str, Any] = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params is not None:
            body["params"] = params
        result = self._request(body)
        if result is None:
            raise RuntimeError(f"MCP 方法 {method} 无响应")
        if "error" in result:
            raise RuntimeError(f"MCP {method} 失败：{result['error']}")
        return result.get("result", {})

    def initialize(self) -> None:
        self._rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION},
            },
        )
        self._request(
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            notification=True,
        )

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = self._rpc("tools/call", {"name": name, "arguments": arguments})
        content = result.get("content")
        if isinstance(content, list) and content:
            first = content[0]
            if isinstance(first, dict) and isinstance(first.get("text"), str):
                try:
                    return json.loads(first["text"])
                except json.JSONDecodeError:
                    return {"ok": True, "raw": first["text"]}
        return result if isinstance(result, dict) else {"ok": True, "result": result}


def emit(result: dict[str, Any], exit_code: int = 0) -> None:
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(exit_code)


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP apply_user_changes：合并 user 并热重载")
    parser.add_argument("--pet-id", required=True)
    parser.add_argument("--play-sequence", default=None, help="热重载后播放的 sequence id")
    parser.add_argument("--runtime-dir", default=None)
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT_SEC)
    args = parser.parse_args()

    try:
        assert_user_only_pet_ready(args.pet_id)
        runtime_dir = (
            Path(args.runtime_dir).expanduser() if args.runtime_dir else default_runtime_dir()
        )
        port, auth_token = read_runtime_endpoint(runtime_dir)
        tool_args: dict[str, Any] = {"pet_id": args.pet_id.strip()}
        if args.play_sequence and args.play_sequence.strip():
            tool_args["play_sequence_id"] = args.play_sequence.strip()

        client = McpStreamableClient(port, auth_token, timeout_sec=args.timeout)
        client.initialize()
        tool_result = client.call_tool("apply_user_changes", tool_args)
        ok = bool(tool_result.get("ok", True))
        emit(
            {
                "ok": ok,
                "pet_id": args.pet_id,
                "mcp": tool_result,
                "hint": tool_result.get("hint")
                or "已触发热重载，请观察桌宠；无需重启",
            },
            0 if ok else 1,
        )
    except SystemExit:
        raise
    except Exception as err:  # noqa: BLE001
        emit(
            {
                "ok": False,
                "err": str(err),
                "hint": "若桌宠未运行请先启动；变更已在 user/ 时重启桌宠仍可生效",
            },
            1,
        )


if __name__ == "__main__":
    main()
