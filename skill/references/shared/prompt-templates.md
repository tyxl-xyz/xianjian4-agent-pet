# Prompt 模板（与设置页对齐）

## 定制组合动作（已有）

设置页「定制」预填示例：

```text
使用 lingxi-pet 技能，帮我为桌宠「{displayName}」（id: {petId}）添加组合动作：
```

Agent 须：

1. 场景 → [../scenarios/compose-sequence.md](../scenarios/compose-sequence.md)（旧称 `customize-action`）
2. 用 `paths.py --pet-id {petId}` 定位账号侧 `user/` / `runtime/`（勿写旧布局 `pets/{petId}/user`）
3. 读 `{runtimePetJson}` 的 actions，按用户描述匹配现成 / 近义可替代动作
4. **能编则编** sequence；**缺动作且无近义替代** → [../scenarios/fill-action-gap.md](../scenarios/fill-action-gap.md)（有 `generate_video` 则补拍，无则告知现成不足；禁止空等、禁止编造 action id）
5. `merge_patch` 后 → [../scenarios/apply-hot-reload.md](../scenarios/apply-hot-reload.md)（**不要**默认 `--play-sequence`；禁止说「正在表演」）
6. 请用户在右键组合菜单手动点播验证

## 创建自己的宠物（待接 UI）

```text
使用 lingxi-pet 技能，场景 create-custom，创建一个桌宠：
```

→ [../scenarios/create-custom.md](../scenarios/create-custom.md)

可选追加：

```text
【petId】my-cat
【外貌】橘白猫，圆脸，绿幕背景
【素材】默认四态 / 或用户已上传帧路径 …
【组合】随机 3 个 / 按描述 / 先不要组合
【档位】guided | quick
```

## 上传素材补丁

```text
使用 lingxi-pet，场景 import-assets，为 petId={petId} 导入素材：
action-id=happy，来源文件夹/文件：{path}
```

→ [../scenarios/import-assets.md](../scenarios/import-assets.md)

## 仅随机组合

```text
使用 lingxi-pet，场景 compose-sequence，petId={petId}，随机生成 3 个组合动作并热生效。
```

