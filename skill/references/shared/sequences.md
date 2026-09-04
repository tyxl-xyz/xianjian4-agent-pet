# Sequences 编排

## 心智模型

- **atomic**：稳定姿态，默认 `loop: true`
- **transition**：切换过程，默认 `playOnce: true`；命名 `{from}_to_{to}`
- **sequence**：把已有 action 串成时间轴，挂 duration / move / before / after

播放：`group[0] enter→hold→leave` → … → `onComplete` / `onInterrupt` → `defaultActivity`

## ActionSequenceDef

```ts
{
  name: string
  groups: SequenceGroup[]
  playbackFpsScale?: number        // 0.1–3，默认 1
  onComplete?: { action: string }  // clip 或另一 sequence id
  onInterrupt?: { action: string }
}
```

### SequenceGroup


| 字段                          | 必填   | 说明                     |
| --------------------------- | ---- | ---------------------- |
| `enter`                     | 否    | `TransitionRef[]`      |
| `hold`                      | 是    | `HoldStep`             |
| `leave`                     | 否    | `TransitionRef[]`      |
| `playbackFpsScale` / `enter | hold | leavePlaybackFpsScale` |


### TransitionRef

```json
{ "action": "idle_to_happy", "playRange": [10, 20] }
```

### HoldStep


| 字段                 | 说明                                                         |
| ------------------ | ---------------------------------------------------------- |
| `action`           | 推荐 atomic id；特殊 `__hold_none__` 不切画面只跑副作用                  |
| `duration`         | `clip` / `once` / `{mode:"fixed",sec:n}` / `untilMoveDone` |
| `move`             | 位移（见下）                                                     |
| `before` / `after` | `StepEffect[]`：`move` / `hide` / `playSequence`            |
| `flip`             | 水平翻转                                                       |
| `playRange`        | 步骤级覆盖 action 定义                                            |


### duration.mode


| mode            | 语义                                                                                                   |
| --------------- | ---------------------------------------------------------------------------------------------------- |
| `clip`          | 按 `clipLoopRange`（默认 [2,10]）循环 hold 后再 leave；**要求 hold 素材首尾可无缝相接**（见 material-pipeline 段2 循环接缝 HARD） |
| `once`          | 播一遍结束                                                                                                |
| `fixed`         | 固定秒数                                                                                                 |
| `untilMoveDone` | 等到 move 完成                                                                                           |


### MoveEffect

```ts
{
  when?: "before" | "during"
  target:
    | { ref: "screenEdge", edge: "left"|"right"|"nearest"|"bottom", offsetPx?: number }
    | { ref: "fixed", x: number, y?: number }
    | { ref: "random", xRange: [number, number], y?: "current" | number }
    | { ref: "randomChoice" }
    | { ref: "activeWindow", anchor: "top" | "nearestEdge" }
  speed?: number
  path?: "arc" | "linear" | "gravity" | "verticalThrow" | "projectile"
}
```

`before` 里也可用 `{ "op": "move", ... }`。

## 硬约束

1. `hold.action` / enter / leave 引用的 id 必须存在于 runtime（或本次将写入的 actions）
2. 禁止覆盖已有 `seq_id`（skill 策略）
3. atomic + `duration:clip` + 无 leave → 会长时间循环；若只想播一次用 `once`
4. transition 作 hold 且无 leave → 用 `duration: once`
5. 链式 `onComplete.action` 指向另一 sequence 时，目标须已存在或同批落盘并说明预览限制

## 常见模式（摘要）

1. **情绪往返**：enter → hold clip → leave → onComplete idle
2. **常驻睡眠**：enter → hold clip（无 leave）→ onInterrupt 起床
3. **走到边缘**：hold + `move.when=during` + `untilMoveDone`
4. **闪现/趴窗**：两段 sequence + `onComplete` 链式
5. **定时**：`duration.fixed`

## P1 生成步骤

1. 建动作能力表（atomic / transition / 已有 sequences）
2. 解析用户意图 → 选状态与能力（关键词表见 [prompt-playbook.md](prompt-playbook.md)）
3. **缺口判定（HARD）：** 所需动作在能力表中不存在、且无近义可替代 → 进入 [../scenarios/fill-action-gap.md](../scenarios/fill-action-gap.md)：有 `generate_video` 则先补拍再继续；无则停止并告知用户现成不足（禁止编造 action id）
4. 组装 JSON → HARD GATE 自检（引用的 id 必须已存在或本批将写入）
5. 自检 → `merge_patch.py`（新 sequence **自动挂进 `baseModes.actions`**，默认三态与 walk/wander 除外）→ 热生效（**默认不**带 `play_sequence_id`）
6. 短庆祝/点缀动作 hold 用 `once`；无 leave 的 `clip` 会按 `clipLoopRange` 多轮循环，易被用户当成卡死

## P2

```bash
python scripts/generate_sequences.py \
  --pet "{runtime-or-patch}" \
  --count 3 --require-ready \
  --merge-out /tmp/seq_patch.json
# merge_patch.py 写入后：apply_user_changes.py --pet-id …（默认不要 --play-sequence）
```

对 runtime **不要**直接 `--merge-in` 写盘；只生成补丁再 `merge_patch` + 热生效。