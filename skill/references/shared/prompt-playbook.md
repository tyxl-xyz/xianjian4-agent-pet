# Prompt 驱动 sequences 生成

随 **lingxi-pet** Phase C 使用。收到**用户自然语言 + actions** 时按本文件执行。  
字段合法性以 [schema.md](schema.md) / [sequences.md](sequences.md) 为准。落盘后走热生效（[../scenarios/apply-hot-reload.md](../scenarios/apply-hot-reload.md)）。

## 1. 输入清单


| 输入                   | 必填    | 说明           |
| -------------------- | ----- | ------------ |
| `actions.atomic`     | 是     | 可用稳定状态       |
| `actions.transition` | 是     | 可用切换边        |
| `defaultActivity`    | 是     | 锚点，默认 `idle` |
| **用户 prompt**        | P1 必填 | 描述想要什么组合玩法   |
| 已有 `sequences`       | 否     | 增量时避免重名      |


优先读 `{runtime}`（official-overlay）；user-only 可用 `{patch}`。

## 2. 整理「动作能力表」

### 2.1 状态节点（atomics）

对每个 atomic：`id`、`name`、语义标签（情绪 / 睡眠 / 移动 / 消失 / 拖拽 / 其他）。

### 2.2 过渡边（transitions）

解析 `{from}_to_{to}`，记录：

- 从 `home` 一步可达的 atomic
- 每个 atomic 能否回到 `home`
- 特殊链：`disappear` 相关边

### 2.3 可达性结论

对每个 atomic `X`（`X !== home`）：


| 标记     | 含义                                        |
| ------ | ----------------------------------------- |
| `✓ 往返` | 有 `home→X` 与 `X→home`，可做 enter+hold+leave |
| `✓ 进入` | 仅有 `home→X`，适合常驻 + onInterrupt            |
| `✓ 移动` | walk_* 且往返边齐全，可挂 untilMoveDone            |
| `✓ 闪现` | 存在 disappear 过渡链                          |
| `✗`    | 缺边，**不能**为该 prompt 硬编                     |


## 3. 解析用户 prompt


| 维度       | 问什么       | 关键词示例             | 默认           |
| -------- | --------- | ----------------- | ------------ |
| **目标状态** | 想表现什么？    | 开心、难过、睡觉、散步、闪现、趴窗 | 关键词匹配 atomic |
| **结构**   | 播完回来还是常驻？ | 一下、来回、一直、别吵我、入睡   | 往返           |
| **时长**   | 停多久？      | 3秒、一分钟、一会         | `clip`       |
| **位移**   | 动不动？去哪？   | 走到右边、趴窗口、随机闪      | 无位移          |
| **数量**   | 要几个？      | 随机来3个、多生成几个       | `1`          |
| **创造性**  | 指定还是随机？   | 随机、随便、你来定         | 按 prompt 指定  |


### 3.1 中文关键词 → atomic


| 用户词      | 优先匹配                              |
| -------- | --------------------------------- |
| 开心、高兴、快乐 | `happy`                           |
| 难过、伤心、失败 | `fail`                            |
| 睡、睡觉、入眠  | `sleep`                           |
| 走、散步、溜   | `walk`_*（有 `walk_right` 优先右）      |
| 闪、消失、传送  | 含 `disappear` 的 transition 链      |
| 趴窗、窗口    | `activeWindow` 位移 + disappear 链   |
| 呆、待机     | `defaultActivity`（作收尾，不作 hold 目标） |


无匹配 → 找最接近；仍无则报告「素材不支持」，**不写** sequences。

### 3.2 关键词 → 行为能力


| 用户词            | 配置                                           |
| -------------- | -------------------------------------------- |
| 一下、表演完回来       | enter + hold(clip) + leave + onComplete→home |
| 一直、持续、别叫醒      | enter + hold(clip)，无 leave + onInterrupt     |
| N秒、一分钟         | hold `fixed` + `sec`                         |
| 走到左/右边、溜到边缘    | hold `untilMoveDone` + move `screenEdge`     |
| 趴窗、到窗口上        | `before` move `activeWindow.top` 或链式闪现       |
| 随机位置闪          | `before` move `randomChoice`                 |
| 先…再…           | 多 `groups` 或 `onComplete` 链下一段 sequence      |
| 只播前半段/后半段、截取N帧 | 步骤层 `playRange`                              |


### 3.3 playRange


| 用户词          | 配置                                                         |
| ------------ | ---------------------------------------------------------- |
| 短版、快速版、只播前N帧 | `hold.playRange: [0, N-1]`                                 |
| 只播后半段        | `hold.playRange: [midFrame, lastFrame]`（查 action `frames`） |
| 跳过开头/结尾      | enter/leave 的 `playRange` 裁首尾                              |
| 拼接首尾、跳帧      | 多段 `[[0, 10], [40, 50]]`                                   |


`playRange` 为 0-indexed 含两端；须先读 action 的 `frames` 确认合法范围。

## 4. 三种工作模式


| 模式     | 触发                | 行为                                        |
| ------ | ----------------- | ----------------------------------------- |
| **P1** | 明确描述玩法            | 拼 1 条 → HARD GATE → merge → 热生效           |
| **P2** | 「随机 N 个」          | **enrich 之后** `generate_sequences.py --count N`（禁止代替 enrich） |
| **P3** | 「根据 actions 全量生成」 | 批量扫描                                      |


**P2 多样性：** 同批不要 2 条仅 hold 的 atomic 相同；尽量覆盖 ≥2 种结构；`seq_id` 用 `{语义}_play` / `{语义}_enter` 等，勿乱码。

优先级：有 prompt → P1 或 P2；否则 P3。

## 5. Prompt → JSON 示例

### A — 开心一下

```json
"happy_play": {
  "name": "开心一下",
  "groups": [{
    "enter": [{ "action": "idle_to_happy" }],
    "hold": { "action": "happy", "duration": { "mode": "clip" } },
    "leave": [{ "action": "happy_to_idle" }]
  }],
  "onComplete": { "action": "idle" }
}
```

### B — 难过一分钟

```json
"fail_sulk_60s": {
  "name": "难过一分钟",
  "groups": [{
    "enter": [{ "action": "idle_to_fail" }],
    "hold": { "action": "fail", "duration": { "mode": "fixed", "sec": 60 } },
    "leave": [{ "action": "fail_to_idle" }]
  }],
  "onComplete": { "action": "idle" }
}
```

### C — 素材不足

用户要「跳舞」但无 dance atomic → **不写盘**，输出缺失清单与已有状态建议。

## 6. 交付

成功：列出 `seq_id` / 菜单名 / 用到的状态；已追加 `categories.sequence.states`；已热生效。  
失败：只输出缺失清单，不写 `{patch}`。