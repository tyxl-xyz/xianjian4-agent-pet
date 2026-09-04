# 多行合图（共享 spritesheet + row）

用户带来的素材若是**一张大图上按行排多个动作**（固定列数 × 多行、每格等宽等高），按本规范导入。  
引擎已支持 `actions.*.row` + `cellWidth` / `cellHeight`（见 [schema.md](schema.md)），**主路径禁止把每一行裁成独立 webp**。

## 如何识别

同时满足多项即可判定为多行合图：


| 信号    | 说明                                                                              |
| ----- | ------------------------------------------------------------------------------- |
| 单文件大图 | 一个 `.webp` / `.png`，宽高明显大于单角色格                                                  |
| 行列规整  | 宽÷列、高÷行得整数格（常见 8 列 × N 行）                                                       |
| 旁路小清单 | 仅有 `id` / `displayName` / `description` + 指向该合图的路径字段，**没有**灵犀式 `actions.atomic` |
| 用户说法  | 「整表导入」「按行是不同动作」「一行一个动画」                                                         |
| Codex 指纹 | 图片尺寸恰好 **1536×1872**（8列×9行×192×208），或来自 `~/.codex/pets/` 目录 → 用 `--preset codex` |


**不是**多行合图时：继续用帧目录 / 单 GIF / 单行动作条 → [import-assets.md](import-assets.md) 的 `import_frames.py`。

## 正确落盘（HARD）

```text
user/
├── spritesheet.webp          # 仅此一张（或保留原文件名，全动作共用）
└── pet.patch.json            # 各 atomic 指向同一 spritesheet + 不同 row
```

每个动作示例字段（`columns=8` 时 idle 未指定 fps → `fps=4`）：

```json
{
  "name": "待机",
  "spritesheet": "spritesheet.webp",
  "row": 0,
  "frames": 6,
  "columns": 8,
  "fps": 4,
  "cellWidth": 192,
  "cellHeight": 208,
  "loop": true,
  "showInMenu": true
}
```


| 规则      | 要求                                                                    |
| ------- | --------------------------------------------------------------------- |
| 共用文件    | 所有行动作的 `spritesheet` **同名**                                           |
| 用 `row` | `row` = 0-based 行号；**禁止**默认裁成 `idle.webp` / `wave.webp`…              |
| 格尺寸     | `cellWidth` / `cellHeight` = 原格像素（用图宽÷列、图高÷行），**禁止**一律写成 256          |
| 显示尺寸    | `displayWidth` / `displayHeight` **默认 128**（桌面可读）；绿幕主路径 cell 默认 720，**禁止**把 display 写成与 cell 相同 |
| 列数      | `columns` = 合图列数（整行格数），不是「只用了几帧就写几」时的误用——`frames` 才是该行动画帧数            |
| idle fps | 用户未指定时 `fps = max(1, floor(columns / 2))`；显式写入则以用户为准（仅 import-assets） |
| 旁路清单    | 可映射 `id`→`petId`、`displayName`、`description`；**丢弃**仅宿主私有、灵犀不消费的路径别名字段 |


## 禁止（HARD）

- 默认把每一行导出为独立 webp 再 `columns=帧数` 的单行条（易错位、体积大、显示过大）
- 将格强行居中贴到 256×256「标准化」后再当唯一真相
- 导入后仅热生效就宣称「完全导入」——若 `sequences` 仍为空 / 无 `baseModes`，必须继续编排或明确告知用户尚未做组合

仅当用户**明确要求**「拆成多个文件」或下游工具不支持 `row` 时，才允许拆行（须说明副作用）。

## Codex 格式自动识别

当素材来自 Codex 桌宠生态（如 `~/.codex/pets/*/spritesheet.webp`）或 Codex 社区下载时，
脚本可通过 `--preset codex` **自动检测格式并填充 rows-spec**，无需手动指定每行对应什么动作。

### 支持的 Codex 版本

| 版本 | 格式 | 状态 |
|------|------|------|
| Codex v1 | 8列 × 9行 × 192×208 = 1536×1872 | 已支持 |
| Codex v2+ | 预留（如 11 行等新规格） | 追加预设即可 |

### 自动识别原理

脚本内置一个版本化的预设表 `CODEX_PRESETS`，key 为 `(cols, rows, cell_w, cell_h)`。
当 `--preset codex` 指定时，脚本用图片实际像素尺寸去匹配预设表：

- **命中** → 自动生成 `rows-spec`，自动填充 `columns`/`cell_w`/`cell_h`
- **未命中** → 报错并列出所有已知预设，提示用户手动 `--rows-spec`

### Codex v1 行映射

| Row | Codex 状态 | 灵犀 action_id | 帧数 | fps | 中文显示名 |
|:---:|-----------|---------------|:---:|:---:|----------|
| 0 | idle | `idle` | 6 | 公式 | 待机 |
| 1 | running-right | `running_right` | 8 | 12 | 向右跑 |
| 2 | running-left | `running_left` | 8 | 12 | 向左跑 |
| 3 | waving | `waving` | 4 | 8 | 挥手 |
| 4 | jumping | `jumping` | 5 | 8 | 跳跃 |
| 5 | failed | `failed` | 8 | 8 | 失败 |
| 6 | waiting | `waiting` | 6 | 8 | 等待 |
| 7 | running（处理中） | `working` | 6 | 10 | 工作中 |
| 8 | review | `review` | 6 | 8 | 审查 |

> Codex 的 `running`（row 7）含义是「处理中/工作中」，不是物理跑步；灵犀映射为 `working`。

### Codex → 灵犀 behaviors 映射建议

导入后编排组合时，`behaviors` **必须是字符串映射**（禁止 `{ actions: [...] }`）。

合图导入（`import_atlas_sheet`）与 `enrich_pet_patch` 会在存在对应 atomic 时**自动补**走路/拖拽：

```json
"behaviors": {
  "walking": "running_right",
  "walking_flip": "running_left",
  "moving_to_target": "running_right",
  "moving_to_target_flip": "running_left",
  "dragging_left": "running_left",
  "dragging_right": "running_right",
  "dragging": "idle"
}
```

事件类（有 `*_play` sequence 后再写）：

```json
"working": "working_play",
"fail": "fail_play",
"success": "happy_play"
```

| 灵犀 behaviors 事件 | Codex atomic | 说明 |
|---------------------|-------------|------|
| `working` | `working`（row 7） | 值写 **sequence id**（如 `working_play`），不是 atomic 名 |
| `success` | `jumping`→`waving` | 编 sequence 后映射到 `happy_play` |
| `fail` | `failed`（row 5） | 映射到 `fail_play` |
| `walking` / `walking_flip` | `running_right` / `running_left` | 导入脚本默认写入 |
| `dragging` | `idle`（row 0） | Codex 无专门拖拽态；有 `hang` 时优先 `hang` |

## 推荐脚本

```bash
# columns=8 → idle 省略 fps 时脚本写入 4；带显示名则写 idle:0:6:4:待机
python scripts/import_atlas_sheet.py \
  --pet-id <id> \
  --sheet "{workspace}/_asset-review/staged/spritesheet.webp" \
  --columns 8 \
  --rows-spec "idle:0:6:4:待机,running_right:1:8:12:向右跑,running_left:2:8:12:向左跑" \
  --review-manifest "{workspace}/_asset-review/review-manifest.json" \
  --display-size 128
```

```bash
# Codex 格式：自动检测 8x9x192x208，自动填充全部 9 行 rows-spec
python scripts/import_atlas_sheet.py \
  --pet-id <id> \
  --sheet "{workspace}/_asset-review/staged/spritesheet.webp" \
  --preset codex \
  --review-manifest "{workspace}/_asset-review/review-manifest.json" \
  --display-name "My Pet" \
  --description "从 Codex 导入的桌宠"
```

上述两例的原始目录/ZIP 均须先经过 `preflight_asset_bundle.py`；审核只对 `staged/` 内的原文件执行，`--sheet` 也必须使用该原文件路径。直接导入会保留源文件扩展名，不能把 PNG 内容仅改名为 `.webp`。

也可 `--infer-grid`（用图尺寸猜列/行/格）再配合 `--rows-spec`。  
`rows-spec` 单项：`action_id:row:frames[:fps[:display_name]]`；idle 未写 fps → `max(1, columns//2)`，其它未写 → `8`。  
细则 CLI 见脚本 `--help`。

## 导入后必做（HARD）

多行合图通常**只有 atomic、没有 transition**，默认四态门禁往往不过 → `enrich` 产不出 `working_play` 等。

因此导入并热生效后**必须**进入其一：

1. [../scenarios/compose-sequence.md](../scenarios/compose-sequence.md) — 用现有 atomic（挥手、坐下等）编 sequences，由 `merge_patch` 挂 `baseModes`（推荐）
2. [../scenarios/character-config.md](../scenarios/character-config.md) — 仅当已具备 enrich 所需 atomic+transition 时

禁止停在「只有 actions、组合菜单为空」。

## 背景色注意

若合图是**不透明纯色底**（黑/绿）而非透明：

- 播放时可能带色块；桌宠期望角色外透明  
- 可在工作区先做色键再导入，或接受现状并告知用户  
- **不要**为去黑底而默认裁成 256 居中条

## 对齐与命中

- 对齐：尊重原格 `cellWidth`×`cellHeight` + `row`，避免二次贴图  
- 显示过大：降低 `displayWidth`/`displayHeight`（或用户缩放），勿靠错误切割「缩小内容」  
- 缩小后难点选：格过大、主体占比小、opaque 命中变窄——优先修正 cell/display，而不是再切一刀
