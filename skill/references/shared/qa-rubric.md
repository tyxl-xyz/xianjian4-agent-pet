# QA 验收量规（lingxi-pet）

合图 / 导入 / 缺口补拍落盘前，按本清单验收。**任一项 FAIL → 禁止 merge 进 `user/` 或宣称完成**（除非用户明确 `adopt-anyway` 且已记录原因）。

配套脚本：

- `scripts/inspect_frames.py` → `qa/review.json`
- `scripts/make_contact_sheet.py` → `qa/contact-sheet.png`
- 配置门禁仍用 `scripts/action_readiness.py`

---

## 1. 落盘与路径

| 检查项 | 通过标准 |
|--------|----------|
| 写入根 | 仅 `accounts/{accountId}/pets/{petId}/user/` |
| 白名单 | 仅基准图、动作 webp/png、`pet.patch.json`、`soul.json` |
| 中间产物 | 视频 / GIF / `_build` / `_preview` 不在 `user/` |
| action id | 未编造 runtime/patch 中不存在的 id（本批将写入的除外） |
| seq id | 未覆盖已有 sequence id |
| 多行合图 | 共用同一 `spritesheet` + `row`；未默认拆成多 webp；`cell*` 为原格尺寸 |
| 跨批次合图文件名 | 各批次 `*.webp` 文件名互不冲突（如 `idle.webp` / `happy.webp`）；**禁止**多批都落成 `sprite.webp` 互相覆盖 |
| 导入收尾 | 若声称导入完成：`sequences` 非空或已明确告知「仅素材、组合未编」；有组合则 `baseModes` 已挂；**且** `write_soul_patch.py --check` 通过，或用户已明确跳过人设 |
| 人设完备 | `soul.json` 含契约必填字段（非仅 `name`/`personality`/`appearance`）；脚本缺字段会拒绝写入 |

## 1.1 上传素材安全门禁（HARD）

| 检查项 | 通过标准 |
|--------|----------|
| 预检 | 用户 ZIP / 素材目录已用 `preflight_asset_bundle.py` 安全解包到 workspace；未直接从 ZIP 写入 `user/` |
| 权威元数据 | `review-manifest.json.metadataStatus == "pass"`；尺寸、动画帧数、网格验证来自脚本读文件，非 `view_image` 口头结论 |
| 视觉审核 | 对 `assets[*].reviewPaths` 的每一张已调用 `view_image`，且每张与顶层 `review.decision` 均为 `pass`；每个路径必须是 staged 中的原始上传文件本身，禁止使用缩略图、转码副本、抽帧或 contact sheet |
| 拒答失败关闭 | `view_image` 返回拒答、无关文本、错误、空结果、未呈现图片或无法判断时，清单必须为 `reject`；禁止执行 `--approve` |
| 完整性 | 导入前哈希复核仍与清单一致；变化则重新预检和审核 |

未满足任意一项，`import_frames.py` / `import_atlas_sheet.py` 必须拒绝写入最终 `pet.patch.json` 或素材文件。

## 2. 基准图（Phase 0）

| 检查项 | 通过标准 |
|--------|----------|
| 姿态 | 全身、正面、站姿；头顶/脚/四肢未被裁切 |
| 幕布铺满（HARD） | 纯色幕布填满到四边；**四角均为幕布色且色差小**；无白边/圆角内框/**渐变·vignette**（与「角色轮廓无绿溢」是不同项） |
| 满画面构图（HARD） | **仅幕布通过后计**。包围盒：宽 ≥78%、高 ≥72%；脚底 3%～12%；头顶 8%～22%；左右各 ≤14% 且大致对称。禁止只写「居中」却角色仅占中心一小块 |
| 对比 | 幕布色相与角色明显区分 |
| 色键冲突（HARD） | `analyze_reference.key_conflict.ok`；角色高饱和点缀（眼睛等）不得落入幕布 hue 窗；FAIL → `redo-bg`（可用 `suggest_screen_color.py`） |
| 像素门禁 | `analyze_reference.py` 退出码 0；未跑或 FAIL → 禁止普通 adopt |
| 用户可见附图（HARD） | AskQuestion 前已在对话中展示待确认基准图；仅工具折叠摘要 ≠ 已展示 |
| 确认 | 用户已 adopt；未确认禁止 `generate_video` |

**语义禁令：** 不得用「背景纯色 / 边缘干净 / 看起来居中」代替幕布铺满与包围盒定量项。  
`view_image` 估百分比仅辅证；以 `analyze_reference.py` 为准。  
**渐变假阳性：** 四角色差过大 → 走 `redo-bg`；`framing.skipped` 时**禁止**按裁脚/裁顶加大留白。

## 3. 透明 GIF / 合图几何

| 检查项 | 通过标准 |
|--------|----------|
| 透明度 | 角色外为透明；无明显绿幕/蓝幕残留色块 |
| 帧非空 | 无整帧全透明或近空 |
| 尺寸稳定 | 同批帧主体尺度无明显跳动（preview 无 size pop） |
| 合图引用 | `spritesheet` / `frames` / `columns` / `row` 与文件一致 |
| video frames（HARD） | 有 `video` 时 `frames ≥ 2`；`frames/fps` 与 WebM 观感时长大致匹配（误差建议 <15%）。**禁止** `frames=1`（多为 ffprobe 缺失占位，会导致序列调度约 42ms） |

## 4. 三段批循环接缝（HARD：以目视为准）

适用于 `idle_to_X` / `X` / `X_to_idle` 中段 hold（`duration: clip` 依赖）：

| 检查项 | 通过标准 |
|--------|----------|
| seamless loop | 段 2 首帧与尾帧姿态接近，可无缝循环（**目视**） |
| prompt | 生成时已要求中段 loop |
| 失败处理 | 目视接缝差 → `redo-cut` 或 `redo-video`，禁止带着坏循环 merge |

`inspect_frames.py --check-loop` 量化仅辅助（默认偏松，**不照搬 hatch-pet 阈值**）：

| `loop.status` | 默认分数带 | 退出码影响 |
|---------------|------------|------------|
| `ok` | `< 0.15` | 不挡 |
| `warn` | `0.15 ≤ score < 0.28` | **不挡** `ok`；须目视后再 adopt |
| `fail` | `≥ 0.28` | 失败；仍可目视后 `adopt-anyway`，但默认应 redo |

可用 `--loop-warn` / `--loop-error` 覆盖阈值。**最终以 contact sheet / 首尾目视为准。**

## 5. 角色一致性

| 检查项 | 通过标准 |
|--------|----------|
| 身份 | 与基准图同一角色（配色、剪影、五官语言） |
| 风格 | 同批动作风格一致，无串戏道具/新角色 |
| 可读 | 桌宠缩放后姿态可辨，无过细碎装饰抢戏 |

## 6. 组合编排（compose-sequence）

| 检查项 | 通过标准 |
|--------|----------|
| 引用存在 | hold/enter/leave 的 action 均存在 |
| 近义替代 | 替代项语义接近；不确定已向用户确认 |
| 缺口 | 无可替代时走 fill-action-gap，未硬编 |
| hold 时长 | 短庆祝优先 `once`；无 leave 的长 `clip` 已自觉风险 |
| 热生效 | 默认不 `--play-sequence`；汇报不说「正在表演」 |

## 7. 角色配置（character-config）

| 检查项 | 通过标准 |
|--------|----------|
| enrich | 可 enrich 三态时已有 `*_play` + behaviors；`enrich_pet_patch.py --check` 通过；**未**用 generate_sequences 顶替 |
| baseModes | 三态可不挂（走 behaviors）；自定义 sequence 才挂菜单 |
| soul | 已写或用户明确跳过人设 |
| bubble | 需要时已 `fill_base_mode_bubbles` |

## 8. 修复策略（从小到大）

1. 单帧 / 切点重切（`redo-cut`）
2. 单批重生成视频（`redo-video`）
3. 重做基准图后再全量（仅基准错误时）

---

## Agent 用法

```text
每批 GIF 确认前：
  inspect_frames.py → 读 qa/review.json
  make_contact_sheet.py → 展示 qa/contact-sheet.png
  对照本量规勾选 → 通过再 make_spritesheet / merge
```

创建宠四态门禁：`action_readiness.py` 退出码 0 + 本量规视觉项通过，方可进 character-config。
