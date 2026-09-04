# 改造前后对照（旧 Phase / 文件 → 新场景）

**语义不变：** 仅 skill 文档组成调整；产品行为（含「缺口才拍视频」）不变。

## 场景映射


| 旧说法                                   | 新场景模块                                                                |
| ------------------------------------- | -------------------------------------------------------------------- |
| `create-custom` 全流程 / Phase 0–D       | [../scenarios/create-custom.md](../scenarios/create-custom.md)       |
| `customize-action` 默认路径（现成编 sequence） | [../scenarios/compose-sequence.md](../scenarios/compose-sequence.md) |
| `customize-action` 素材缺口分支             | [../scenarios/fill-action-gap.md](../scenarios/fill-action-gap.md)   |
| Phase A 上传路径 / `import-assets`        | [../scenarios/import-assets.md](../scenarios/import-assets.md)       |
| 多行大图合图（共享 sheet + row）              | [multi-row-atlas.md](multi-row-atlas.md) + `import_atlas_sheet.py`   |
| Phase C / character-design            | [../scenarios/character-config.md](../scenarios/character-config.md) |
| 热生效 / apply-changes                   | [../scenarios/apply-hot-reload.md](../scenarios/apply-hot-reload.md) |
| Phase 0 + 绿幕视频细则                      | [material-pipeline.md](material-pipeline.md)（shared）                 |
| Phase B 门禁                            | 仍在 create-custom 步骤内；脚本 `action_readiness.py`                        |
| Phase D 粒子                            | [effects.md](effects.md)（shared）                                     |
| `references/modes.md`                 | **已删除**；内容拆入 create-custom / compose-sequence / fill-action-gap      |


## 文件移动


| 旧路径 `references/X` | 新路径               |
| ------------------ | ----------------- |
| `paths.md` 等契约/细则  | `shared/`         |
| （新）场景入口            | `scenarios/*.md`  |
| `SKILL.md` 长流程正文   | 薄路由；步骤在 scenarios |


## Agent 加载建议

1. 读根 `SKILL.md` 判定场景
2. **只打开**对应 `scenarios/*.md`
3. 按需再打开 `shared/` 中被链接的文件（不要默认通读全部 shared）