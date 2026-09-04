# 灵犀桌宠 · 技能交付契约（草案）

一页纸说明：本技能包产出什么、写到哪里、宿主如何消费。细则见 [schema.md](schema.md) / [paths.md](paths.md)。

## 技能包

| 项 | 约定 |
|----|------|
| 包名 | `lingxi-pet` |
| 入口 | `SKILL.md` |
| 场景步骤 | `references/scenarios/` |
| 共享规范 | `references/shared/` |
| 确定性工具 | `scripts/*.py` |

## 写入位置（唯一）

```text
{petRoot}/accounts/{accountId}/pets/{petId}/user/
```

| 平台 | `{petRoot}` |
|------|-------------|
| Windows | `%APPDATA%\desktop-pet` |
| macOS | `~/Library/Application Support/desktop-pet` |

**禁止**写入：`pets/{petId}/official/`、账号侧 `runtime/`、无账号前缀旧 `user/`。

## user/ 允许文件

| 文件 | 用途 |
|------|------|
| `reference.png` / `reference.webp` | 角色基准图 |
| `*.webp` / `*.png` | 动作 spritesheet（被 patch 引用） |
| `pet.patch.json` | actions / sequences / 角色增量配置 |
| `soul.json` | 人设与反应文案 |

视频、GIF、构建缓存只存在会话工作区，不进入 `user/`。

## 宿主合并结果

热生效或启动后，宿主将 official ⊕ user 合并为：

```text
accounts/{accountId}/pets/{petId}/runtime/pet.json
accounts/{accountId}/pets/{petId}/runtime/soul.json
```

技能侧通过 `pet_apply_user_changes` 或 `scripts/apply_user_changes.py` 触发重载。

## 对外能力边界

| 会做 | 不做 |
|------|------|
| 创建自定义宠素材与配置 | 改官方 `official/` 包 |
| 用现成动作编组合；缺口时补拍或提示上传 | 无视频能力时静默卡住 |
| 导入素材后编排组合 + 写入完备 `soul.json`（`--from-pet` + `--check`；除非用户跳过人设） | 只落盘 webp/patch，或手写精简 soul 就宣称「导入完成」 |
| 落盘后热生效 | 默认自动播新组合（须用户菜单点播） |

## 验收

视觉与落盘： [qa-rubric.md](qa-rubric.md)  
配置齐套： `scripts/action_readiness.py`
