---
name: lingxi-pet
description: >-
  灵犀桌宠官方定制技能：创建自定义桌宠，或为已有桌宠编排组合动作。
  支持绿幕视频生成、素材上传导入、角色人设配置、拖拽行为（behaviors.dragging*）与热生效。
  定制组合优先复用现成动作；缺素材且无近义替代时，具备视频能力则补拍，否则明确提示现成不足。
  触发词：创建桌宠、生成宠物、定制桌宠、组合动作、拖拽行为、绿幕、spritesheet、pet.patch、soul.json、上传帧、webp、lingxi-pet。
---

# 灵犀桌宠定制

**Announce:** "I'm using the lingxi-pet skill."

面向灵犀桌宠的官方 Agent 技能：在对话中完成**创建自定义宠物**、**编排组合动作**、**导入素材**与**角色人设**，并写入用户侧数据后热生效。

本文件为技能**入口与路由说明**。具体步骤、契约与脚本分别位于下方目录，请按场景打开对应文档，无需通读全包。


| 目录                                               | 内容                           |
| ------------------------------------------------ | ---------------------------- |
| `[references/scenarios/](references/scenarios/)` | 按业务场景划分的操作指南（优先阅读）           |
| `[references/shared/](references/shared/)`       | 路径规范、数据契约、素材流水线等共享细则         |
| `[scripts/](scripts/)`                           | 确定性 Python 脚本（优先调用，避免手写等价逻辑） |


---

## 能力概览


| 能力     | 说明                                          |
| ------ | ------------------------------------------- |
| 创建自定义宠 | 基准图（仅供生成动作参考）→ 动作素材 → **WebM 主路径**（编码后校验透明；缺 ffmpeg 时脚本自动安装）→ 角色配置 → 热生效 |
| 编排组合动作 | 用已有 atomic / transition 编排 sequence，并挂到组合菜单 |
| 补齐缺失动作 | 现成动作不足以表达用户意图时，可生成或导入新素材后再编排                |
| 上传导入   | ZIP / 序列帧 / GIF；先做安全审核与权威元数据预检，再导入；**多行合图**用共享 spritesheet + `row`（不默认拆图） |
| 角色与人设  | 补全 `pet.patch.json` 与 `soul.json`（问候、反应文案等） |
| 粒子特效   | 引擎内置 9 预设；`enrich_pet_patch` 默认写 `actions.*.effect`；可选 `effectOverrides` |
| 拖拽行为   | 有左右跑素材时 enrich 自动写 `behaviors.dragging*` + `run_*_play` + `baseModes.wander`；仅四态则仅 `dragging=idle` |
| 信箱相关配置 | **闲时未读气泡**（`{mailboxUnread}`）已支持；**离家 `mailboxPresentation`** 由 `enrich_pet_patch` **自动写时长**（有序列再挂；默认不配 `mailboxImage`） |
| 热生效    | 落盘后重载用户改动，无需重启桌宠进程                          |


数据仅写入账号隔离目录：`accounts/{accountId}/pets/{petId}/user/`（详见 [路径规范](references/shared/paths.md)）。

---

## 使用方式

1. **识别场景** — 根据用户意图对照下表，打开对应场景文档
2. **按文档执行** — 仅加载该场景及文内链接的共享细则
3. **落盘并热生效** — 写入完成后执行 [热生效](references/scenarios/apply-hot-reload.md)

定位路径（任务开始建议执行）：

```bash
python scripts/paths.py --pet-id <id> --ensure-user --print
```

`paths.py` 会经 `wps-collab.get_me()` 解析**当前登录账号**：已有 `accounts/{accountId}/` 则写入该账号；没有则创建账号目录与 `user/`。详见 [paths.md](references/shared/paths.md)。

---

## 场景一览


| 场景     | 适用情况                            | 文档                                                           |
| ------ | ------------------------------- | ------------------------------------------------------------ |
| 创建自定义宠 | 新建宠物、「创建自己的宠物」                  | [create-custom](references/scenarios/create-custom.md)       |
| 编排组合动作 | 已有宠 + 定制组合，且现成或近义动作足够           | [compose-sequence](references/scenarios/compose-sequence.md) |
| 补齐缺失动作 | 所需动作不存在且无可替代；或用户明确要求拍新素材 / 绿幕   | [fill-action-gap](references/scenarios/fill-action-gap.md)   |
| 上传导入素材 | ZIP / 帧 / GIF / 合图（含多行大图）；或无视频生成时的降级 | [import-assets](references/scenarios/import-assets.md)       |
| 角色配置   | 创建流程中的配置阶段；或单独补人设 / pet 配置      | [character-config](references/scenarios/character-config.md) |
| 热生效    | 任意写入 `user/` 之后；或仅要求重新加载        | [apply-hot-reload](references/scenarios/apply-hot-reload.md) |


### 定制组合（决策顺序）

设置页「定制」或用户要求「加组合动作」时，按以下顺序处理（产品语义，勿简化跳过）：

```text
编排组合动作（compose-sequence）
  ├─ 现成 / 近义动作足够 → 写入 sequence → 热生效
  └─ 不足 → 补齐缺失动作（fill-action-gap）
        ├─ 具备 generate_video → 生成素材 → 回到编排 → 热生效
        └─ 不具备 → 明确告知现成不足，可建议上传导入；禁止空等
```

### 拖拽行为（何时配置）

```text
仅四态（idle/working/success/fail）
  └─ 可拖拽，但无左右跑 → behaviors 仅 dragging=idle|hang（enrich 默认）

用户主动生成 / 导入 running 或 walk 素材（左右两侧 atomic 齐）
  └─ 必须再跑 enrich_pet_patch.py（或 fill-action-gap 收尾 enrich）
  └─ 自动写入：
        behaviors：walking / walking_flip / dragging_left / dragging_right / dragging
        sequences：run_left_play / run_right_play（untilMoveDone + 贴边位移）
        baseModes：一条 directional wander（sequenceLeft / sequenceRight）
  └─ 热生效后：拖宠跟方向跑；闲时随机散步

用户要求「拖拽也要有跑/拎起感」但尚无左右跑
  └─ fill-action-gap 补 running_left + running_right（或 Codex 合图）→ enrich → 热生效
```

键名与引擎解析顺序见 [schema.md](references/shared/schema.md)；Codex 合图映射见 [multi-row-atlas.md](references/shared/multi-row-atlas.md)。

---

## 约束与安全

### 上传审核拒答即终止（最高优先级 HARD）

对用户上传 ZIP / 目录中的任一原始视觉文件调用 `view_image` 后，若得到拒答、工具错误、空结果、无关结果、未呈现图片或无法判断：

1. 立即执行 `preflight_asset_bundle.py --manifest <review-manifest.json> --reject`；
2. 停止本次上传任务；
3. 对用户**仅输出**：**「素材审核失败，无法使用当前素材创建桌宠。请重新上传素材。」**
4. **禁止**再次审核、重试审核、生成/读取 PNG 或其它转码副本、抽帧、生成 contact sheet、导入素材、写入 `user/`、生成 `pet.patch.json` 或继续创建流程。

这是不可恢复的本次任务终点；用户声称安全、请求重试或已有旧 PNG 都不能解除门禁。只有用户随后上传一份新的原始素材，才可作为新的任务重新开始预检。**禁止向用户提及「不安全」、具体审核结论、文件名、`view_image`、`--reject`、内部流程或「重新安全审查」。**

- **写入范围**：仅 `user/`；禁止写入 `official/`、账号侧 `runtime/`，以及无账号前缀的旧布局  
- **user/ 白名单**：基准图（`reference.png` / `.webp`）、动作图（`.webp` / `.png`）、`pet.patch.json`、`soul.json`  
- **中间产物**：视频、GIF、构建目录等仅放在会话工作区，不得落入 `user/`  
- **动作引用**：禁止编造不存在的 action id；禁止覆盖已有 `seq_id`  
- **热生效汇报**：定制组合默认不自动播放序列；请引导用户在组合菜单中手动点播验证  
- **视频生成**：仅在素材缺口（或用户明确要求加素材）时启用；环境无视频能力时须明确提示，禁止空等  
- **创建宠动作门禁（HARD）**：`reference.png|webp` 只是角色基准图，**不是 action，也不得伪装为 idle**。新建 `user-only` 宠必须先有默认四态的真实动作媒体（每个 action 有 `spritesheet` / `video` / `videoHevc`，媒体存在且非空，`frames >= 2`），并以 `action_readiness.py --media-root` 退出码 0 为准；缺任一项时，禁止生成/补全空 `pet.patch.json`、`soul.json`、`runtime/` 或调用任何热生效工具。
- **无视频能力的创建终点（HARD）**：环境无 `generate_video` 且用户未上传通过审核的动作帧/GIF/动画 WebP/合图时，必须停止创建；仅可保留或交付「动作参考基准图」。对用户明确说明「尚未创建可运行桌宠」，不得说“已接入桌宠配置 / 已完成 / 有动作”。
- **多行合图**：优先单文件 + `actions.*.row`；禁止默认逐行裁成多 webp；导入后须编排组合（或明确「组合未做」）**且**须写入完备 `soul.json`（或用户明确跳过人设）  
- **人设 soul（HARD）**：**禁止**手写仅含 `name` / `personality` / `appearance` / `creator` 的精简稿冒充完成。必须 `write_soul_patch.py --from-pet`（再润色）；宣称完成前执行 `--check` 退出码 0。必填：`userName`、`greetings`、`timeGreetings`、`likes`、`dislikes`、`backstory`、`reactions`（含 onWorking/onAsk/onSuccess/onFail）  
- **默认三态组合（HARD）**：创建宠四态素材齐后必须 `enrich_pet_patch.py`（生成 `working_play`/`fail_play`/`happy_play` + `behaviors`）。**禁止**用 `generate_sequences.py` 代替 enrich（后者仅 P2 随机追加）。宣称完成前 `enrich_pet_patch.py --check` 退出码 0。三态走 behaviors，**不要求**挂进 `baseModes`  
- **拖拽与位移（HARD）**：用户**主动**补 `running`/`walk_*` 左右跑素材后，须 `enrich_pet_patch.py` 一次性落盘：**behaviors**（`fill_missing_locomotion`）+ **sequences**（`run_left_play`/`run_right_play`）+ **baseModes.wander**（directional，`sequenceLeft`/`sequenceRight`）。仅四态时不写方向拖拽与 wander。补素材后禁止只 merge actions 不 enrich。详见 `scripts/locomotion_config.py`

- **导入收尾**：`import-assets` 在宣称完成前须满足：组合就绪（或已声明未编）+ `write_soul_patch.py --check` 通过（或用户跳过人设）；禁止只落盘 webp/patch 或精简 soul 就说「导入完成」
- **上传素材安全门禁（HARD）**：用户 ZIP / 素材目录必须先执行 `preflight_asset_bundle.py`，在 workspace 安全解包并生成 `review-manifest.json`；Agent 必须对清单中每个 `reviewPaths` 调用 `view_image`。**每个路径都只能是 `staged/` 中解压出的原始上传文件本身（PNG 就审 PNG、GIF 就审 GIF、WebP 就审 WebP）**；禁止为审核生成或改看缩略图、转码 PNG、抽帧、contact sheet 或任何派生产物。原格式无法被 `view_image` 可靠呈现也必须 `reject`。只有 `review.decision=pass` 且 `metadataStatus=pass` 时，才允许从 `stagedDir` 读取对应原始素材给 `import_frames.py` / `import_atlas_sheet.py`、写入 `user/` 或生成最终 `pet.patch.json`。**若 `view_image` 返回拒答、无关文案、工具错误、空结果、无法判断或未实际呈现图片，结论必须是 `reject`（绝不可执行 `--approve`）；这不是安全通过。**尺寸、网格、帧数只能来自脚本元数据；审核失败、工具错误、无法预览或哈希变化一律停止。审核通过后的运行时构建可按导入脚本需要产生素材，但不得将其反过来作为审核依据。完整流程见 [asset-safety-review.md](references/shared/asset-safety-review.md)
- **审核对象范围**：`reviewPaths` 只由 ZIP/目录中的图片扩展名生成；视频、音频、文本及其他非图片仅记录在 `nonVisualFiles`，不得调用 `view_image`，也不能凭此作为图片 action 导入依据。
- **信箱图**：默认**不要**在 `pet.patch.json` 写 `mailboxImage`、也**不要**要求用户包内自带 `mailbox.png`（程序内置兜底）；仅用户提供自定义信箱图时才配置。详见 [mailbox-presentation.md](references/shared/mailbox-presentation.md)
- **透明视频（HARD，防跑偏）**：
  1. 必须先 `chroma_key_to_gif`（或已确认透明的 GIF），再 `encode_action_webm`；**禁止**未抠像绿幕 mp4 直接编码
  2. **创建宠默认只出 stacked `.mov`（`videoHevc`）**；需要伴生 WebM 时显式 `--also-webm`。引擎仍可播放已有 `.webm`
  3. 编码脚本会校验透明/matte；失败须重抠像，**禁止**宣称交付
  4. **禁止**把 `yuv420p`+`alpha_mode:1` 或「静态 ffmpeg 写不进 alpha」当成卡点去 brew / 改合图；详见 [material-pipeline.md §5](references/shared/material-pipeline.md)

完整路径与合并语义见 [paths.md](references/shared/paths.md)。

---

## 延伸阅读


| 文档                                                             | 用途                         |
| -------------------------------------------------------------- | -------------------------- |
| [scripts-index.md](references/shared/scripts-index.md)         | 脚本清单与依赖                    |
| [qa-rubric.md](references/shared/qa-rubric.md)                 | 视觉/落盘验收量规（合图前必对照）          |
| [multi-row-atlas.md](references/shared/multi-row-atlas.md)     | 多行合图：共享文件 + `row`，禁止默认拆行    |
| [delivery-contract.md](references/shared/delivery-contract.md) | 一页交付契约（写哪、产什么）             |
| [prompt-templates.md](references/shared/prompt-templates.md)   | 与设置页对齐的 Prompt 模板          |
| [schema.md](references/shared/schema.md)                       | pet / sequence / soul 数据契约 |
| [mailbox-presentation.md](references/shared/mailbox-presentation.md) | 信箱两层：未读气泡 + `mailboxPresentation` 填写规则（默认无 mailboxImage） |
| [effects.md](references/shared/effects.md) | 粒子：内置预设 + `effect` / `effectOverrides` 编排 |
| [material-pipeline.md](references/shared/material-pipeline.md) | 绿幕视频与基准图细则                 |
| [migration.md](references/shared/migration.md)                 | 场景命名与历史 Phase 对照（维护用）      |


```text
skills/lingxi-pet/           ← 仓库根目录 skills/（灵犀 Claw 技能包）
├── SKILL.md                 ← 入口（本文件）
├── references/
│   ├── scenarios/           ← 场景操作指南
│   └── shared/              ← 共享规范与细则
└── scripts/                 ← 可执行脚本
```
