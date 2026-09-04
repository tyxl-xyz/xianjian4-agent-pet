# 落盘后热生效（免重启）

写入账号侧 `user/pet.patch.json`、`user/soul.json`（及 webp）后，调用热生效使桌宠立即加载，**无需重启进程**。

路径：`{petRoot}/accounts/{accountId}/pets/{petId}/user/` → 合并进同级 `runtime/`。

客户端会合并写出：

- `accounts/.../runtime/pet.json` ← `pets/{petId}/official` ⊕ `user/pet.patch.json`
- `accounts/.../runtime/soul.json` ← official/soul.json ⊕ `user/soul.json`

## 优先级

1. Client tool：`pet_apply_user_changes`（若有）
2. 否则：`python scripts/apply_user_changes.py --pet-id <id>`

前置：桌宠已在设置页**运行中**。MCP 鉴权文件在**进程级**目录：`{petRoot}/runtime/mcp-port` + `mcp-auth`（不是账号侧 runtime）。

## Payload / CLI

```json
{
  "pet_id": "san-hua"
}
```

```bash
python scripts/apply_user_changes.py --pet-id san-hua
```

### 不要默认自动播序列（HARD）

- **compose-sequence（定制组合）/ 日常落盘：不要传 `play_sequence_id` / `--play-sequence`。**
- MCP **没有**「一次性 JSON 预览并开播」工具；本地调试面板的 `debug_play_sequence` 不属于 skill 热生效路径。
- 向用户汇报时写「已热生效，请在组合菜单手动播放验证」，**禁止**写「正在表演 XXX」。
- 仅当用户**明确要求**「热生效后立刻播一下」时，才可加 `--play-sequence <seq>`。此时引擎会等皮肤重载完成（`finish_skin_reload`）后再播。

## 推荐流程

```text
enrich_pet_patch / merge_patch / write_soul_patch 写入 accounts/.../user/
        ↓
pet_apply_user_changes / apply_user_changes.py   # 默认不带 play
        ↓
桌宠热重载（合并 → accounts/.../runtime/）→ 前端重建 sprite
        ↓
告知用户：已生效；请手动点播新组合验证
```

## 何时调用


| 场景                                 | 调用时机                           |
| ---------------------------------- | ------------------------------ |
| create-custom 写入 actions/webp      | 该批 merge 完成后                   |
| character-config 补全 pet + soul     | enrich + write_soul 完成后        |
| compose-sequence / fill-action-gap | 落盘后立即调用；**默认不带** play_sequence |
| 粒子 effect                          | merge 完成后                      |


## 失败处理

- 桌宠未运行 → 提示先唤醒，变更已在账号侧 `user/`，下次启动仍会生效
- MCP 失败 → 说明已落盘，请用户重启桌宠一次
- 热重载后卡死/不动 → 先重启桌宠；确认 skill **未**默认 `--play-sequence`；组合 hold 避免无 leave 的长 `clip`

