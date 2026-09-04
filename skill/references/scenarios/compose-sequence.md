# 场景：现成组合编排（compose-sequence）

**何时进入：** 已有宠 + 「定制组合动作」/ 设置页「定制」；且准备用 **现成或近义** actions 编 sequence。

**别名：** 旧文档中的 `customize-action` 默认路径。

## 决策（先做）

```text
读 runtime actions
  → 解析用户意图，列出所需 atomic / transition
  → 精确匹配或近义可替代？
        全部能匹配 → 本场景编 sequence → 热生效
        有缺口 → 离开本场景，进入 [fill-action-gap.md](fill-action-gap.md)
```

## 步骤

1. 提取 `petId`
2. `python scripts/paths.py --pet-id {petId} --ensure-user --print` → 绑定当前登录账号，确认账号侧 `{runtime}` 含 `actions`
3. 读 `{runtimePetJson}` 的 `actions.atomic` / `actions.transition`
4. 匹配：精确 id → 近义替代（见下）；不确定时先向用户说明拟替代项
5. 组装 sequences → 细则 [../shared/sequences.md](../shared/sequences.md)、关键词 [../shared/prompt-playbook.md](../shared/prompt-playbook.md)
6. `python scripts/merge_patch.py --pet-id <id> --patch-json <file>`
  - **自动**挂 `baseModes.actions` + bubble（**排除** `working_play` / `fail_play` / `happy_play` 与 walk/wander）
7. [apply-hot-reload.md](apply-hot-reload.md)（**默认不带** `--play-sequence`）
8. 汇报：「已写入 patch 并热生效；请在右键组合菜单手动点播验证」
  - **禁止**说「正在表演 XXX」

## 近义替代

- **可替代：** 语义同族、观感接近（「欢呼」≈ `happy`，「趴下休息」≈ `sleep` / `lie`）
- **不可替代：** 点名具体动作库中无对应姿态（「弹吉他」「转圈踢腿」而只有 idle/happy）→ [fill-action-gap.md](fill-action-gap.md)
- **禁止**编造不存在的 action id

## 多行合图导入后的编排（常见）

`import-assets` 刚导入的共享合图宠往往**只有 atomic、没有 transition**。此时：

- 不要等 `working`/`fail`/`happy` 三态齐套再编
- 直接用现有 atomic（如挥手、坐下、开心待机）做 sequence：`hold` 用对应 atomic，短动作优先 `duration.mode=once`
- `merge_patch` 后会挂 `baseModes`；这是组合菜单有内容的主路径

## 本场景不做

- 不默认调用 `generate_video` / 绿幕抠图（那是缺口场景）
- 不跑 enrich/soul（除非用户明确要求补人设 → [character-config.md](character-config.md)）
- **默认**不改已有 actions 的 spritesheet/frames（缺口补拍除外）；**勿**把多行合图再拆成多文件

## Prompt 对齐

设置页模板 → [../shared/prompt-templates.md](../shared/prompt-templates.md)