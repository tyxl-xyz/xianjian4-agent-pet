# Phase C — 角色配置设计（pet.patch + soul.json）

基准 **actions 门禁（Phase B）通过后必须执行**（除非用户明确说「不要组合」且「不要人设」）。

目标：把「能播的动作」升级成「有玩法 + 有人设」的完整自定义宠，并热生效同步到 `runtime/`。

## 流程

```text
Phase B OK
    ↓
enrich_pet_patch.py     → 默认三态 *_play + behaviors（主路径；禁止跳过）
enrich_pet_patch.py --check
write_soul_patch.py     → 写入完备 user/soul.json
write_soul_patch.py --check
fill_base_mode_bubbles.py → 有 baseModes 时补 bubble（三态可不挂 baseModes）
（可选）Agent 润色 bubble 后 merge_patch
    ↓
热生效 apply_user_changes
```

```bash
python scripts/enrich_pet_patch.py --pet-id <id>
python scripts/enrich_pet_patch.py --pet-id <id> --check
python scripts/write_soul_patch.py --pet-id <id> --from-pet
python scripts/write_soul_patch.py --pet-id <id> --check

python scripts/fill_base_mode_bubbles.py --pet-id <id>
python scripts/apply_user_changes.py --pet-id <id>
```

**HARD：** 默认三态组合只由 `enrich_pet_patch.py` 生成。**禁止**素材齐后直接 `generate_sequences.py`（常只出 `idle_play`，漏掉 `working_play` 等）。`generate_sequences` 仅 enrich 之后的 P2 追加。

Agent 在 `--from-pet` 默认模板之上，应用角色设定润色 `soul.json`（喜恶、backstory、reactions），再 `--replace` 或深合并写回。  
润色 `soul` 后执行 `fill_base_mode_bubbles`；可用角色口吻改写 `baseModes.actions[].bubble.texts`（保留 `{userName}` / `{mailboxUnread}`）。

## A. 补全 `user/pet.patch.json`

在已有 `actions` 上 **merge**，**禁止**抹掉 `spritesheet` / `frames` / `columns` 等素材字段。

幂等：已有键不覆盖（`enrich_pet_patch.py`）。


| 字段                           | 默认四态（idle / working / fail / happy）规则                                                                                                 |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `sequences`                  | 若缺则生成 `working_play` / `fail_play` / `happy_play`（enter→hold→leave→`onComplete: idle`）                                                |
| `categories.sequence.states` | 同步追加上述 id                                                                                                                             |
| `behaviors`                  | `working`→`working_play`，`success`→`happy_play`，`fail`→`fail_play`；有 `running_right`/`running_left`（或 `run_*`/`walk_*`）时 enrich 自动补 `walking`/`walking_flip`/`dragging_*` + `run_left_play`/`run_right_play` + `baseModes.wander`；有 `hang` 则 `dragging=hang`，否则 `dragging=idle`。**值必须为 string** |
| `baseModes`                  | 闲时随机。**不自动挂** `working_play` / `fail_play` / `happy_play`（三态走 `behaviors`）；**不单独挂** `run_*_play`（走 directional `wander`）。有左右跑素材时 enrich 写一条 `wander`；其它自定义 sequence 自动挂入并带 `bubble` |
| `clipLoopRange`              | `[2, 10]`（若缺失）                                                                                                                        |
| `homeAction`                 | `"idle"`（若缺失）                                                                                                                         |
| `mailboxPresentation`        | **enrich 自动写入**（幂等）：补 `disappearAfterSec` / `disappearAwaySec`；若已有候选 away/return 序列再挂对应字段；**永不自动写 `mailboxImage`**。见 [mailbox-presentation.md](mailbox-presentation.md) |


对照三花只对齐字段语义，不照搬 walk / sleep / 缺素材的 away 序列；**不要**为对齐三花而给每个自定义宠塞 `mailboxImage: "mailbox.png"`。

### baseModes.bubble（对齐三花）

每条 `baseModes.actions[]` 应含：

```json
"bubble": {
  "texts": ["文案1", "文案2（可含 {userName}）"],
  "dwellSec": [4, 7]
}
```

生成规则（`base_mode_bubble.py` / `fill_base_mode_bubbles.py`）：


| 来源                      | 用法                                                          |
| ----------------------- | ----------------------------------------------------------- |
| sequence id 语义          | `happy` / `working` / `fail` / `clapping` / `wander`… → 选模板 |
| `soul.reactions`        | `onSuccess` / `onWorking` / `onFail` 优先拼进对应语义               |
| `displayName` / `likes` | 融入口吻；占位符保留 `{userName}`、`{mailboxUnread}`                   |
| 信箱未读提示                  | 生成/补齐后**整池恰好一条**闲时动作追加含 `{mailboxUnread}` 的文案；已有则跳过；排除 `sleep` / `hold`；稳定哈希选取 |
| 已有 bubble               | 默认不覆盖语义文案（`only_missing`）；若全池仍无信箱提示仍会补一条；`--force` 重写后同样再保证一条 |


`compose-sequence` 经 `merge_patch` 追加 sequence 时同步生成 bubble；soul 更新后应再跑 `fill_base_mode_bubbles`。润色 `bubble.texts` 时须保留 `{userName}` / `{mailboxUnread}` 占位符（由引擎按未读数替换或跳过）。

用户说「不要组合」：跳过 sequences / baseModes 中依赖 sequence 的部分，仍可写 `clipLoopRange` / `homeAction`。

用户另行描述玩法（P1/P2/P3）：在 enrich 之后按 [sequences.md](sequences.md) / [prompt-playbook.md](prompt-playbook.md) **追加**更多 sequences（仍走 `merge_patch.py`，禁止覆盖已有 seq_id）。场景入口见 [../scenarios/character-config.md](../scenarios/character-config.md)。

## B. 写入 `user/soul.json`

文件名固定为 `**soul.json`**（与官方宠一致；勿再写 `soul.patch.json`）。

**HARD 落盘路径：**

1. 必须先 `write_soul_patch.py --from-pet`（由 pet 生成契约模板）  
2. 再按角色润色（可 `--soul-json` 深合并，或改完再写回）  
3. 宣称完成前 `write_soul_patch.py --check`（退出码 0）  
4. **禁止**手写仅含 `name` / `personality` / `appearance` / `creator` 的精简 JSON 冒充完成（脚本会拒绝不完备写入）

字段对齐 `SoulConfig` / 三花 soul（下列均为**必填**，空数组 / 空字符串不合格）：


| 字段                   | 说明                                                      |
| -------------------- | ------------------------------------------------------- |
| `userName`           | **按角色关系推断**（见下表）；可用 `--user-name` 或用户偏好覆盖               |
| `greetings`          | 通用问候（非空字符串数组）                                          |
| `timeGreetings`      | morning / noon / afternoon / dusk / evening / lateNight（各项非空数组） |
| `likes` / `dislikes` | 短列表（非空）                                                 |
| `backstory`          | 一句话人设，可用 `{userName}`                                   |
| `reactions`          | `onWorking` / `onAsk` / `onSuccess` / `onFail`（各项非空数组） |


`personality` / `appearance` 等可作为**额外**描述字段保留，但不能替代上表契约字段。

文案按 `displayName` / `description` 生成，占位符保留 `{userName}`。

### userName 关系推断（`infer_user_name_from_relationship`）


| 关系信号（displayName / description） | 默认称呼 | reason                   |
| ------------------------------- | ---- | ------------------------ |
| 猫狗/萌宠/宠物/兽耳等                    | `主人` | `pet-companion`          |
| 助手/秘书/管家                        | `老板` | `assistant-to-boss`      |
| 老师/导师/教练                        | `朋友` | `mentor-peer`            |
| 真人/名人/CEO/同事/搭档/科学家等            | `朋友` | `human-peer`（优先于「桌宠」产品词） |
| Q版人物立绘（无萌宠词）                    | `朋友` | `stylized-human`         |
| 其它兜底                            | `主人` | `default-pet`            |


> 注意：不要用单独的「宠」做萌宠判定（会误伤「桌宠」）；用「萌宠」「宠物」等完整词。

Agent 润色人设时：若用户说出「叫我 XX」，必须写入 `userName`；未指定则保留推断结果，**不要**对名人/真人角色改回「主人」。

若目录里仍有遗留 `soul.patch.json`，`write_soul_patch.py` 会读入后迁移为 `soul.json` 并删除 patch。

用户说「不要人设」：跳过本步（不写 soul.json）。

## C. 热生效与 runtime

落盘后必须调用热生效（见 [../scenarios/apply-hot-reload.md](../scenarios/apply-hot-reload.md) / [apply-changes.md](apply-changes.md)）。

客户端 `build_runtime_layer`：

- `user/pet.patch.json` → 合并写出 `runtime/pet.json`
- `user/soul.json` ⊕ official → 写出 `runtime/soul.json`
- **禁止**把 `pet.patch.json` / 遗留 `soul.patch.json` 原样拷进 runtime

skill **禁止**手写 `runtime/`。

## HARD GATE

- Phase B 未通过不得进入本阶段
- 只写账号侧 `user/`（见 [paths.md](paths.md) 账号隔离布局）
- enrich / soul / fill_base_mode_bubbles 落盘后必须热生效（桌宠未运行时可说明下次启动生效）
- `baseModes.actions[]` 应有 `bubble.texts`（对齐三花；缺则跑 `fill_base_mode_bubbles.py`）
- 告知用户：账号侧 `runtime/pet.json` 与 `runtime/soul.json` 已由客户端同步

