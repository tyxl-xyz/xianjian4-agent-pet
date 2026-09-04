# 场景：热生效（apply-hot-reload）

**何时进入：** 任意场景写入 `user/pet.patch.json` / `user/soul.json` / 动作 webp 之后；或用户只要求「重新加载用户改动」。

## 步骤

1. 确认桌宠进程在跑（设置页已启动）
2. **新建 `user-only` 宠必须先验证动作交付：**

```bash
python scripts/action_readiness.py \
  --pet "{userDir}/pet.patch.json" \
  --media-root "{userDir}"
```

   退出码非 0 时立即停止；不得调用 Client tool、不得调用本脚本，也不得向用户宣称已创建桌宠。`reference.png`、空 `actions`、缺媒体或单帧 action 都不通过。
3. 仅在上述门禁通过后，优先 Client tool：`pet_apply_user_changes`；否则：

```bash
python scripts/apply_user_changes.py --pet-id <id>
```

4. 失败时：说明文件已落盘，请用户启动/重启桌宠一次

## HARD

- **定制组合 / 日常业务落盘：默认不要** `--play-sequence`
- 禁止对用户说「正在表演 XXX」；应请用户在右键组合菜单手动点播
- 仅用户明确要求「立刻播一下」时才加 `--play-sequence`
- **Client tool 不得绕过动作门禁**：对新建 `user-only` 宠，先跑步骤 2 再调用 `pet_apply_user_changes`；不能以「已写入 reference / soul」为由提前热生效

完整 MCP / payload → [../shared/apply-changes.md](../shared/apply-changes.md)
