# 场景：上传导入素材（import-assets）

**何时进入：** 用户提供 ZIP、帧目录 / GIF / 动画 webp / 合图；或创建宠/缺口场景因无视频生成而降级。**单张 reference / 抠图不是动作素材，不得进入本场景作为 action 导入。**

## 0. 上传素材安全预检（HARD）

### 审核失败即结束本次导入（最高优先级）

任一原始文件的 `view_image` 返回拒答、错误、空结果、无关结果、未呈现图片或无法判断时：**立即执行 `--reject` 并结束本次桌宠创建/导入任务。** 用户可见回复只能是：**「素材审核失败，无法使用当前素材创建桌宠。请重新上传素材。」** 不得重试审核，不得读取或生成 PNG、缩略图、转码副本、抽帧或 contact sheet，也不得继续导入、写入 `user/` 或生成 JSON。禁止向用户输出「不安全」、具体审核结论、素材文件名、内部命令或「重新安全审查」。用户说「我确认安全」或要求改用旧 PNG 也不能绕过；只接受下一次新上传的原始素材重新开启流程。

用户上传的 ZIP / 素材目录先走 [素材安全与元数据门禁](../shared/asset-safety-review.md)：

```bash
python scripts/preflight_asset_bundle.py \
  --input <上传的zip或目录> \
  --out-dir "{workspace}/_asset-review"
```

Agent 必须对 `review-manifest.json` 中每个 asset 的 `reviewPaths` **逐个**调用 `view_image`。每个路径就是安全解包后的**原始上传文件本身**：PNG/WebP/JPEG/GIF 分别按其原格式直接审核；不得生成或使用缩略图、重编码副本、抽帧或 contact sheet。原格式无法可靠呈现时也属于审核失败，不能改用其他格式。**`view_image` 若返回拒答（如“无法提供相应解答”）、无关文本、工具错误、空结果或无法判断，均是审核失败：立即执行 `--reject`，禁止用“没看到违规内容”代替通过。**只有每一张都获得可用的视觉结论且判定安全，才可执行：

```bash
python scripts/preflight_asset_bundle.py \
  --manifest "{workspace}/_asset-review/review-manifest.json" \
  --approve
```

发生上述失败时改为：

```bash
python scripts/preflight_asset_bundle.py \
  --manifest "{workspace}/_asset-review/review-manifest.json" \
  --reject
```

随后只使用 `stagedDir` 下的素材，并将 `--review-manifest` 传给导入脚本。预检、审核或哈希校验失败时，禁止导入、写入 `user/` 或生成最终 JSON。

> `reviewPaths` 只由图片文件生成；ZIP 中的视频、音频、文本等非图片不送给 `view_image`，仅由预检保留在 `nonVisualFiles` 做完整性记录。

## 0.5 动作真实性门禁（HARD）

- 单张 PNG/JPEG/WebP、单帧 GIF/WebP，或各帧画面完全相同的重复帧，**不是 action**；只能作为 `reference`，不得调用 `import_frames.py`、不得写入 `actions`。
- 已有 spritesheet 必须声明 `frames >= 2`，且该 action 覆盖的格子至少有两格画面不同；不能把一张抠图复制多格伪装成动作。
- 创建自定义宠且无 `generate_video` 时，若上传包不含上述真实动作，立即停止创建：禁止写空 `pet.patch.json` / `soul.json`，禁止调用 `pet_apply_user_changes` 或 `apply_user_changes.py`。对用户说明目前仅有动作参考图，尚未创建可运行桌宠。

## 0. 先判定素材形态（HARD）


| 形态                  | 特征                          | 走法                                                                                                             |
| ------------------- | --------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **多行合图**            | 单张大图、多行动作、格规整；或旁路小清单只指向一张合图 | **主路径** → [../shared/multi-row-atlas.md](../shared/multi-row-atlas.md) + `import_atlas_sheet.py`（共享文件 + `row`） |
| 序列帧 / 单 GIF / 单行动作条 | 一动作一序列或已裁单行条                | `import_frames.py`                                                                                             |


**禁止**对多行合图默认「逐行裁成多个 webp + 256 居中」。引擎支持 `row`，拆图会导致错位、过大、难点选。

### idle fps（HARD）

仅本场景（用户已有素材导入）适用：


| 条件                                     | `idle.fps`                                        |
| -------------------------------------- | ------------------------------------------------- |
| 用户**未**显式指定 idle 的 fps                 | `max(1, floor(columns / 2))`（例：`columns=8` → `4`） |
| 用户在 rows-spec / `--fps` 中写了 idle 的 fps | 以用户为准                                             |
| 其它 atomic / transition                 | 默认不变（合图未写 fps → 8；`import_frames` 未写 → 24）        |


Agent 写 rows-spec 时：若用户没给 idle 帧率，应省略 idle 的 fps 段（让脚本按公式填），或主动写入 `columns//2`。**禁止**对 idle 无脑填 24。

## 1. 多行合图步骤

1. `paths.py --pet-id <id> --ensure-user --print`（当前登录账号；无目录则创建）
2. 解析行列：用户说明 / 图尺寸推断（`--infer-grid`）/ 显式 `--columns --cell-w --cell-h`
3. 为每一行确定 `action_id`、`row`、`frames`、`fps`、显示名（可对照旁路清单的 id/displayName）；**idle 的 fps 遵循上方 HARD**
4. 执行：

```bash
# columns=8 → idle 用公式 fps=4（须写入数字段才能带显示名）
python scripts/import_atlas_sheet.py \
  --pet-id <id> \
  --sheet "{workspace}/_asset-review/staged/<合图原文件名>.webp" \
  --infer-grid \
  --rows-spec "idle:0:6:4:待机,<id>:<row>:<frames>:<fps>:<名>,..." \
  --review-manifest "{workspace}/_asset-review/review-manifest.json" \
  --display-size 128 \
  --display-name "<名>" \
  --description "<简介>"
```

> rows-spec：`id:row:frames[:fps[:name]]`。省略 fps 仅当无 name（如 `idle:0:6`）时由脚本填 `columns//2`；要带显示名则先算公式再写（如 `idle:0:6:4:待机`）。**禁止**写 `idle:0:6:待机`（第三段会被当成 fps，解析失败）。

1. **收尾 A（HARD）— 组合：** 进入 [compose-sequence.md](compose-sequence.md)，用已导入 atomic 编至少若干 sequences 并挂 `baseModes`
  - 此类素材通常**无 transition**，勿指望 `enrich` 自动生成 `working_play`  
  - **禁止**在 `sequences` 仍为空、无 `baseModes` 时向用户宣称「完全导入」
2. **收尾 B（HARD）— 人设：** 若 `{userDir}/soul.json` 不存在或不完备，必须进入 [character-config.md](character-config.md)（至少 `write_soul_patch.py --from-pet`，再按角色润色；建议接着 `fill_base_mode_bubbles.py`）
  - 宣称完成前：`python scripts/write_soul_patch.py --pet-id <id> --check`（退出码 0）  
  - **唯一豁免：** 用户明确说「不要人设 / 跳过 soul」  
  - **禁止**未写完备 `soul.json`（且用户未跳过）却宣称「导入完成 / 可用」  
  - **禁止**手写精简稿（仅 `name`/`personality`/`appearance` 等）冒充人设完成
3. [apply-hot-reload.md](apply-hot-reload.md)（组合与人设都落盘后再热生效；中途调试可多次热生效）

```text
import_atlas_sheet → compose-sequence（sequences + baseModes）
                  → character-config（完备 soul.json + --check，除非用户跳过）
                  → apply-hot-reload
```

## 2. 帧 / GIF / 单行条步骤

1. `paths.py --pet-id <id> --ensure-user --print`（当前登录账号；无目录则创建）
2. `import_frames.py`（CLI → [../shared/import-assets.md](../shared/import-assets.md)）
3. **若本次导入是在建新宠 / 该宠尚无完整配置（HARD）：**
  - 组合：→ [compose-sequence.md](compose-sequence.md)（或用户明确只要单动作、不要组合）  
  - 人设：若无完备 `soul.json`（`--check` 未通过）→ [character-config.md](character-config.md)（除非用户跳过人设）
4. 若只是给**已有官方/自定义宠**追加单个动作素材，且该宠 `--check` 已通过：可只热生效，不必重走人设
5. [apply-hot-reload.md](apply-hot-reload.md)

> 新建 `user-only` 宠在进入热生效前，必须通过：`python scripts/action_readiness.py --pet "{userDir}/pet.patch.json" --media-root "{userDir}"`。失败则停止；导入了部分素材不等于已经创建桌宠。

```bash
# 非 idle：可省略 --fps（默认 24）或显式传入
python scripts/import_frames.py \
  --pet-id <id> --action-id <atomic_or_transition_id> \
  --source "{workspace}/_asset-review/staged/<dir-or-gif-or-webp>" \
  --review-manifest "{workspace}/_asset-review/review-manifest.json" \
  [--kind atomic|transition] [--fps 24]

# idle：省略 --fps 时，落盘 fps = max(1, columns//2)
python scripts/import_frames.py \
  --pet-id <id> --action-id idle --kind atomic \
  --source "{workspace}/_asset-review/staged/idle.webp" --spritesheet-ready \
  --review-manifest "{workspace}/_asset-review/review-manifest.json" \
  --frames 6 --columns 8
```

## 3. 汇报话术

- 审核失败时仅回复：「素材审核失败，无法使用当前素材创建桌宠。请重新上传素材。」
- ✅「已写入共享合图与 atomic（row=…）；正在编排组合动作与人设…」→ compose + soul 完成后再说可用  
- ✅「仅导入了动作素材，组合菜单仍空 / 尚无人设，需要继续…」  
- ❌「已完全导入 / 导入完成」但：`sequences` 空、无 `baseModes`、或无完备 `soul.json` / `--check` 未通过（且用户未跳过人设）
