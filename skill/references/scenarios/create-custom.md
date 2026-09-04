# 场景：创建自定义宠（create-custom）

**何时进入：** 新建宠 / 无 official / 「创建自己的宠物」/ 设置页创建入口。

**不要**默认走本场景去处理「给已有宠加组合」——那是 [compose-sequence.md](compose-sequence.md)。

## 步骤

1. 解析或生成 `petId`（`^[a-zA-Z0-9_-]{1,64}$`）
2. `python scripts/paths.py --pet-id <id> --ensure-user --print` → 绑定**当前登录账号**（无本地目录则创建），判定 `user-only` / `official-overlay`
3. 路径与白名单 → [../shared/paths.md](../shared/paths.md)
4. **Phase 0** 基准图 → [../shared/material-pipeline.md](../shared/material-pipeline.md) §Phase 0
  - 无参考图 → `generate_image`（须含 edge-to-edge + **包围盒定量构图**，禁止只写「居中」）  
  - **HARD：** `view_image` + `analyze_reference.py`（幕布铺满 + 满画面）均通过后才可普通 adopt；未确认前禁止 `generate_video`  
  - **HARD：** AskQuestion「基准图确认」**之前**必须在对话中向用户展示待确认图（见 material-pipeline §0.3）；禁止只靠工具摘要「生成了 N 张图」
5. **Phase A** 素材
  - 可选：`python scripts/prepare_pet_run.py --workspace <ws> --pet-id <id> --mode create-custom`  
  - 有 `generate_video` → 绿幕视频主路径（同 material-pipeline）  
  - 无视频 tool → **仅当用户已上传真实动作素材时**才进入 [import-assets.md](import-assets.md)；若只有 `reference` / 抠图，则停止创建，提示上传动作帧/GIF/动画 WebP/合图；**禁止空等、禁止写空 patch、禁止热生效**
  - 每批 GIF 确认前：`inspect_frames.py` + `make_contact_sheet.py`，对照 [../shared/qa-rubric.md](../shared/qa-rubric.md)  
  - overlay 且用户只要官方动作 → 可跳过合图，直接角色配置
6. **Phase B** 门禁：`python scripts/action_readiness.py --pet "{userDir}/pet.patch.json" --media-root "{userDir}"`（退出码 0）+ QA 量规通过；未通过即为本次创建终点，禁止进入 Phase C/D、写 soul 或热生效
7. **Phase C** → [character-config.md](character-config.md)（HARD，除非用户明确跳过组合与人设）  
   - **必须先** `enrich_pet_patch.py`（默认三态 `*_play` + `behaviors` + effect）；**禁止**用 `generate_sequences.py` 顶替  
   - 宣称完成前：`enrich_pet_patch.py --check` 与 `write_soul_patch.py --check`（若未跳过人设）  
   - 详见 [../shared/effects.md](../shared/effects.md)
8. **Phase D**（默认）粒子润色 → [../shared/effects.md](../shared/effects.md)  
   - 校对 enrich 写入的 `effect`；按角色风格补 `effectOverrides`  
   - 仅当用户明确要求「不要粒子 / 极简」时可跳过覆写（`effect` 绑定仍可由 enrich 保留）
9. 每次落盘后 → [apply-hot-reload.md](apply-hot-reload.md)

## generate_video 可用性


| 情况                 | 行为                         |
| ------------------ | -------------------------- |
| 有 `generate_video` | 默认 `source=video`          |
| 无该 tool，且已有通过审核的动作素材 | `source=upload` |
| 无该 tool，且只有基准图或无动作素材 | 停止创建；仅保留动作参考图并提示上传，禁止写 patch / 热生效 |
| overlay + 只要现有官方动作 | 跳过合图，直接 character-config   |


## 交互档位


| 档位           | 行为              |
| ------------ | --------------- |
| `guided`（默认） | 基准图确认、每批 GIF 确认 |
| `quick`      | 少打断；落盘后仍须热生效    |


## 旧 Phase 别名

`Phase 0/A/B/C/D` 即本场景步骤 4–8；映射表见 [../shared/migration.md](../shared/migration.md)。
