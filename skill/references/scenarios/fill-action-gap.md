# 场景：素材缺口处理（fill-action-gap）

**何时进入：**

1. 从 [compose-sequence.md](compose-sequence.md) 判定：所需动作不存在且无近义可替代；或
2. 用户明确要求「再拍新动作 / 加素材 / 绿幕」

**产品语义（HARD，勿改）：** 只有现成不够才补拍；有视频能力也不在「现成够用」时自动拍。

## 分支


| 判定                                     | 行为                                                   |
| -------------------------------------- | ---------------------------------------------------- |
| **有** `generate_video`（或等价 skill/tool） | 补拍缺失 atomic/transition → 回到编排 → 热生效                  |
| **无** `generate_video`                 | **停止编排**；告知现成不足；建议上传或换描述；**禁止空等**、**禁止编造 action id** |


## 有视频时的步骤

1. 确认 `{userDir}/reference.png|webp`；无则先做 Phase 0（[../shared/material-pipeline.md](../shared/material-pipeline.md)）
2. 可选：`prepare_pet_run.py --workspace <ws> --pet-id <id> --mode gap --batches <missing>`
3. 按缺口动作跑素材流水线（视频 → 抠图 → 合图 → merge actions）→ 同 material-pipeline
  - 只拍**缺失**批次，不必默认四态全跑  
  - 合图前：`inspect_frames.py --check-loop`（三段 hold）+ contact sheet，对照 [../shared/qa-rubric.md](../shared/qa-rubric.md)
4. `merge_patch` 写入新 actions（允许改 patch 的 actions；白名单见 [../shared/paths.md](../shared/paths.md)）
5. 若补的是 **running / walk 左右跑** → `python scripts/enrich_pet_patch.py --pet-id <id>`（自动写 behaviors + `run_*_play` + `baseModes.wander`）
6. 其它缺口 → 回到 [compose-sequence.md](compose-sequence.md) 编 sequence
7. [apply-hot-reload.md](apply-hot-reload.md)

## 无视频时的话术

> 现有动作里没有可表达「XXX」的素材（已查过近义替代），当前环境也无法生成视频。请上传相关帧/GIF/webp，或换一个能用现有动作表达的描述。

上传路径 → [import-assets.md](import-assets.md)

## 汇报

- 已补拍：「已生成缺失动作并编入组合，请点播验证。」
- 未补拍：用上节话术；不要假装已写入 sequence