# pet.json / sequences — schema v3

本文件描述桌宠配置契约。编排细则另见 `sequences.md`。

## 引擎约定

- `schemaVersion`: `3`（推荐显式写出）
- `defaultActivity`: 锚点 atomic id，通常 `"idle"`
- 播放顺序：`groups[].enter → hold → leave`（逐组）→ `onComplete` / `onInterrupt` → 回 `defaultActivity`

## actions 与 sequences 的分工


| 区块                   | 职责                           |
| -------------------- | ---------------------------- |
| `actions.atomic`     | 可循环「状态」素材定义；可选 `"effect": "预设名"` 挂粒子 |
| `actions.transition` | 一次性「状态切换」素材定义（不加 effect）                |
| `sequences`          | 把上述 id **编排**成玩法（时长、位移、链式播放） |
| `effectOverrides`    | 可选；按预设名覆写 emoji 等（引擎内置 9 预设为底） |


**引用规则：**

- `hold.action` → **推荐** atomic id，或 `__hold_none__`（仅副作用、不切换画面）；**亦可** transition id（引擎按单次片段处理，常配 `duration: once`）
- `enter[]` / `leave[]` 的 `action` → **推荐** transition id
- `onComplete` / `onInterrupt` 的 `{ action }` → 任意已定义 id（常见：回 `defaultActivity` 的 atomic，或 transition）
- 所有 id 必须在 `actions` 中已定义（`__hold_none__` 除外）
- **引擎不校验 kind**；调试编排器 UI 对 enter/leave 仅展示 transition，hold 下拉还受 `categories` 过滤（见下）

## sequences 类型结构（JSON）

```typescript
// 逻辑类型，供生成时对照；不是 TypeScript 文件路径

interface ActionSequenceDef {
  name: string
  groups: SequenceGroup[]
  /** 整段组合播放倍速，默认 1.0，范围 0.1–3 */
  playbackFpsScale?: number
  /** 全部 group 正常播完后的收尾；单对象，非数组 */
  onComplete?: SequenceEndAction
  /** 用户打断时的收尾；单对象，非数组 */
  onInterrupt?: SequenceEndAction
}

/** 收尾动作：action 可为 clip（atomic/transition）或另一个 sequence id */
interface SequenceEndAction {
  action: string
}

interface SequenceGroup {
  enter?: TransitionRef[]
  hold: HoldStep
  leave?: TransitionRef[]
  playbackFpsScale?: number
  enterPlaybackFpsScale?: number
  holdPlaybackFpsScale?: number
  leavePlaybackFpsScale?: number
}

interface TransitionRef {
  action: string
  /** 步骤级帧范围覆盖（0-indexed，含两端） */
  playRange?: [number, number] | [number, number][]
}

interface HoldStep {
  action: string
  flip?: boolean
  duration?: DurationMode
  move?: MoveEffect
  before?: StepEffect[]
  after?: StepEffect[]
  playRange?: [number, number] | [number, number][]
}

type DurationMode =
  | { mode: 'clip' }
  | { mode: 'once' }
  | { mode: 'fixed'; sec: number }
  | { mode: 'untilMoveDone' }

type MoveTargetRef =
  | { ref: 'screenEdge'; edge: 'left' | 'right' | 'nearest' | 'bottom'; offsetPx?: number }
  | { ref: 'fixed'; x: number; y?: number }
  | { ref: 'random'; xRange: [number, number]; y?: 'current' | number }
  | { ref: 'randomChoice' }
  | { ref: 'activeWindow'; anchor: 'top' | 'nearestEdge' }

interface MoveEffect {
  when?: 'before' | 'during'
  target: MoveTargetRef
  speed?: number
  path?: 'arc' | 'linear' | 'gravity' | 'verticalThrow' | 'projectile'
}

type StepEffect =
  | ({ op: 'move' } & MoveEffect)
  | { op: 'hide'; mode?: 'sprite' | 'window'; durationSec?: number }
  | { op: 'playSequence'; id: string }
```

> `StepEffect` 仅用于 `hold.before` / `hold.after`，**不**用于 `onComplete` / `onInterrupt`。
> `clip` 循环次数受 manifest `clipLoopRange`（默认 `[2,10]`）控制。
> hold 特殊 id：`__hold_none__`（不切换 sprite，只跑副作用）。

## duration.mode 播放语义


| mode            | 含义                                        |
| --------------- | ----------------------------------------- |
| `clip`          | 有 leave：播一轮 hold 后进 leave；无 leave：循环 hold |
| `once`          | hold 只播一轮                                 |
| `fixed`         | 固定 `sec` 秒后结束 hold                        |
| `untilMoveDone` | 循环 hold 直到位移到达（配合 `move.when: during`）    |


**注意：**

- transition 放在 `hold.action`：引擎视 `kind === 'transition'` 或 `playOnce` 为单次片段；无 leave 时建议显式 `duration: once`
- 无 leave + **atomic** + `clip` → hold 无限循环（睡眠常驻）；勿与「播一次」混淆

## onComplete / onInterrupt 收尾语义

两个字段均为**可选单对象** `{ "action": "<id>" }`（**不是数组**）。`action` 可引用 atomic、transition，或另一段 **sequence id**（引擎链式入队）。

### 触发时机


| 字段            | 触发条件                      | 典型用途                         |
| ------------- | ------------------------- | ---------------------------- |
| `onComplete`  | 所有 `groups` **正常播完**后执行   | 回到 `defaultActivity`、链式播放下一段 |
| `onInterrupt` | 用户交互（点击/拖拽等）**打断**当前序列时执行 | 从常驻状态唤醒、紧急回归待机               |


### 引擎回退链

```
用户打断 → onInterrupt 存在？
  ├─ 是 → 执行 onInterrupt 步骤
  └─ 否 → onComplete 存在？
        ├─ 是 → 退而执行 onComplete
        └─ 否 → 直接回 defaultActivity
```

无论走哪条路径，**最终**引擎都会回到 `defaultActivity`。

### 设计模式


| 序列类型      | onComplete                           | onInterrupt                               |
| --------- | ------------------------------------ | ----------------------------------------- |
| **往返型**   | `{ "action": "idle" }`               | 可省略（回退到 onComplete）                       |
| **常驻型**   | 通常不写（不会自然结束）                         | **必须**写，如 `{ "action": "sleep_to_idle" }` |
| **链式型**   | `{ "action": "<next_sequence_id>" }` | 可写回归动作，或省略走 onComplete 链播                 |
| **不可打断型** | 按需                                   | 故意不写 + 在生成说明中标注「不可打断」                     |


### 硬约束

- 常驻序列（无 leave + atomic + `clip` 循环）**必须**提供 `onInterrupt`，否则用户无法退出该状态（引擎虽会回退到 `defaultActivity`，但缺少过渡动画会造成画面跳切）
- `onInterrupt.action` 若填 sequence id，目标必须已存在
- `onInterrupt` 应尽量简短（单个 clip 或单段 sequence），让用户打断后快速回到待机

> 编排器可迁移旧版 `[{ "action": "..." }]` 或 `[{ "op": "playSequence", "id": "..." }]`；生成时须输出 `{ "action": "<id>" }` 格式。

## 特殊常量


| 值               | 含义                                 |
| --------------- | ---------------------------------- |
| `__hold_none__` | hold 不切换 sprite，仅执行 `before` / 时长等 |


## actions clip 媒体字段

每个 atomic / transition clip：

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `video` | 可选（与 `spritesheet` / `videoHevc` 至少一个） | 透明短视频，如 `"fail.webm"`（VP9 + yuva420p）；创建宠默认不生成，可用 `--also-webm` |
| `videoHevc` | 可选（与 `spritesheet` / `video` 至少一个；**创建宠默认**） | stacked-alpha，如 `"fail.mov"`（上 RGB 下 matte）；引擎优先于 `video` |
| `videoAlphaLayout` | 可选 | `stacked`（默认）或 `native`（真 HEVC+alpha） |
| `spritesheet` | 与 `video` / `videoHevc` 至少一个 | 精灵图集；视频解码失败时回退 |
| `fps` / `loop` / `playOnce` | 推荐 | 视频与图集共用；视频 `loop` 映射 `HTMLVideoElement.loop` |
| `frames` / `columns` / `cellWidth` / `cellHeight` | 图集必填；纯 video 可占位 | 纯 video 时 `build_pet_json` 用 `displaySize`(128) 填 cell，`frames` 可由 ffprobe 估时 |
| `playRange` | 可选 | **仅图集**；video clip **忽略**（MVP） |

绿幕主路径推荐每 clip 一条 `{id}.mov`（如 `idle_to_fail.mov` / `fail.mov` / `fail_to_idle.mov`），避免超宽 PNG 图集卡主线程。引擎仍可播放已有 `{id}.webm`。

## 最小可运行示例

```json
{
  "schemaVersion": 3,
  "defaultActivity": "idle",
  "actions": {
    "atomic": {
      "idle": { "name": "发呆", "spritesheet": "idle.webp", "frames": 10, "columns": 10, "fps": 12 },
      "happy": {
        "name": "开心",
        "videoHevc": "happy.mov",
        "videoAlphaLayout": "stacked",
        "spritesheet": "happy.webp",
        "frames": 20,
        "columns": 20,
        "fps": 24,
        "loop": true
      }
    },
    "transition": {
      "idle_to_happy": { "name": "变开心", "videoHevc": "idle_to_happy.mov", "videoAlphaLayout": "stacked", "frames": 8, "columns": 1, "fps": 24, "playOnce": true },
      "happy_to_idle": { "name": "回发呆", "videoHevc": "happy_to_idle.mov", "videoAlphaLayout": "stacked", "frames": 8, "columns": 1, "fps": 24, "playOnce": true }
    }
  },
  "sequences": {
    "happy_play": {
      "name": "开心一下",
      "groups": [{
        "enter": [{ "action": "idle_to_happy" }],
        "hold": { "action": "happy", "duration": { "mode": "clip" } },
        "leave": [{ "action": "happy_to_idle" }]
      }],
      "onComplete": { "action": "idle" }
    }
  },
  "categories": {
    "sequence": {
      "name": "组合",
      "states": ["happy_play"]
    }
  }
}
```

## categories

### `categories.sequence`（落盘 / 菜单）

生成每个 sequence 后，将其 id 写入：

```json
"categories": {
  "sequence": {
    "name": "组合",
    "states": ["<seq_id_1>", "<seq_id_2>"]
  }
}
```

右键菜单与分类展示依赖此项；**调试编排器执行预览不依赖 categories**。

### `categories.atomic` / `categories.transition`（编排器 UI 可选）

调试面板 hold 下拉 = 空动作 + 全部 atomic + 在 `categories.transition.states` 中登记的 transition。  
**引擎播放不读 categories 过滤**，仅 UI 选单用。生成 JSON 时 categories 与 actions 保持一致即可。

## 链式播放与趴窗（运行时）

`onComplete: { "action": "<sequence_id>" }` 链播下一段（`action` 填 sequence id）。


| 模式       | 条件                                                                                                  | 行为                                   |
| -------- | --------------------------------------------------------------------------------------------------- | ------------------------------------ |
| **普通链式** | `onComplete.action` 为 sequence id，且 `hold.before` 非 `activeWindow` 移动                               | 当前 sequence 播完 → enqueue 下一段         |
| **贴窗双段** | 某组 `hold.before` 含 `move` 且 `target.ref === "activeWindow"` **且** `onComplete.action` 为 sequence id | preSequence → 贴窗移动 → 再播链式目标 sequence |


第二段 sequence 的 hold 可为 transition + `duration: once`（如 `disappear_to_idle` 作出现动画）。

## 与调试编排器 / 热生效


| 阶段                               | Claw / skill                                   | 调试编排器                                  |
| -------------------------------- | ---------------------------------------------- | -------------------------------------- |
| **产品默认**                         | 落盘 → MCP `apply_user_changes` 热重载（可播 sequence） | —                                      |
| **本地调试**                         | —                                              | Tauri `debug_play_sequence`（仅调试面板，不写盘） |
| 菜单可见                             | 落盘 + 热生效后需 `categories.sequence`               | 「▶ 执行组合」不依赖 categories                 |
| `{ action }` 单对象；链式用 sequence id | 同左                                             | UI 为单个动作 id 下拉（含 sequence）             |


详见 `SKILL.md` §4.1、§4.2。

## 可选关联（非 sequences 本体）

### behaviors vs baseModes 格式差异（常见混淆点）

| 字段 | 类型 | 示例 |
|------|------|------|
| `behaviors` | `{ [event: string]: string }` | `{ "working": "working_play", "walking": "running_right" }` |
| `baseModes.actions` | `Array<{ id, weight, ... }>` | `[{ "id": "clapping", "weight": 15, "sequence": "…" }]` |

**口诀：behaviors 是简单字符串映射，baseModes 是带权数组。**  
写成 `{ "working": { "actions": [...] } }` 会导致桌宠 Rust 整份 `pet.json` 解析失败（「活动中但看不见」）。

```json
"behaviors": {
  "success": "<sequence_or_action_id>",
  "fail": "<sequence_or_action_id>",
  "working": "<sequence_or_action_id>",
  "walking": "<atomic_id>",
  "walking_flip": "<atomic_id>",
  "dragging": "<atomic_id>",
  "dragging_left": "<atomic_id>",
  "dragging_right": "<atomic_id>",
  "dragging_prepare": "<transition_id>",
  "dragging_release": "<transition_id>"
},
"baseModes": {
  "enabled": true,
  "homeActivity": "idle",
  "scheduleIntervalSec": [30, 60],
  "actions": [
    {
      "id": "clapping_micro",
      "weight": 15,
      "mode": "once",
      "sequence": "clapping_play",
      "bubble": {
        "texts": ["啪啪啪！为{userName}鼓掌～", "干得漂亮！"],
        "dwellSec": [4, 7]
      }
    }
  ]
},
"clipLoopRange": [2, 10],
"homeAction": "idle"
```

角色配置场景（[../scenarios/character-config.md](../scenarios/character-config.md) / [character-design.md](character-design.md)）在默认四态就绪后由 `enrich_pet_patch.py` 补齐 sequences / **behaviors**；`baseModes` **不自动**挂 `working_play` / `fail_play` / `happy_play`（三态由 behaviors 事件触发），仅自定义 sequence 自动挂入。walk/wander 不挂。无 walk 素材时不要写 wander。

## mailboxPresentation（enrich 自动补全 · 离家信箱）

角色配置跑 `enrich_pet_patch.py` 时**自动写入缺失键**。未配置 `mailboxImage` 时引擎使用程序内置兜底图。

```json
"mailboxPresentation": {
  "disappearAfterSec": 1800,
  "disappearAwaySec": 300,
  "awaySequence": "away_disappear_play",
  "readLetterSequence": "return_appear_play"
}
```

| 字段 | enrich 行为 | 说明 |
|------|-------------|------|
| `disappearAfterSec` | 缺失则写 `1800` | 无有效交互多久后离家（秒） |
| `disappearAwaySec` | 缺失则写 `300` | 离家后多久自动回归（秒） |
| `awaySequence` | 缺失且候选 sequence 已存在才写 | 离场序列 id |
| `readLetterSequence` | 缺失且候选 sequence 已存在才写 | 回归读信序列 id |
| `mailboxImage` | **永不自动写** | 仅用户自带图时由 Agent 另写 |
| `mailboxImageScale` 等布局 | 不自动写 | 可选手调 |

填写决策与话术 → [mailbox-presentation.md](mailbox-presentation.md)。

## soul.json

人设独立文件（user 层），热生效后合并为 `runtime/soul.json`。

**必填契约（HARD）：** `userName`、`greetings`、`timeGreetings`（含 morning/noon/afternoon/dusk/evening/lateNight）、`likes`、`dislikes`、`backstory`、`reactions`（含 onWorking/onAsk/onSuccess/onFail）。空字符串/空数组不合格。

```json
{
  "userName": "朋友",
  "greetings": ["嗨，{userName}！"],
  "timeGreetings": {
    "morning": ["早上好~"],
    "noon": ["中午好~"],
    "afternoon": ["下午好~"],
    "dusk": ["傍晚好~"],
    "evening": ["晚上好~"],
    "lateNight": ["早点休息~"]
  },
  "likes": ["被关注"],
  "dislikes": ["被冷落"],
  "backstory": "……",
  "reactions": {
    "onWorking": ["开工啦~"],
    "onAsk": ["需要你确认~"],
    "onSuccess": ["搞定啦！"],
    "onFail": ["呜…搞砸了…"]
  }
}
```

**必须**用 `write_soul_patch.py --from-pet` 落盘（再润色）；宣称完成前 `--check`。  
**禁止**只写 `name`/`personality`/`appearance` 精简稿；不要手写 `runtime/soul.json`。