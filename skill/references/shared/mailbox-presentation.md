# 信箱相关配置（lingxi-pet）

桌宠侧「信箱」有两层能力；本技能**只负责配置与文案**，不实现运行时队列 / notify。


| 层             | 用户感知                   | 技能是否支持                        | 落盘位置                                                   |
| ------------- | ---------------------- | ----------------------------- | ------------------------------------------------------ |
| **A. 闲时未读提示** | 闲时气泡提一句「信箱还有未读」        | ✅ 已支持                         | `baseModes.actions[].bubble.texts` 含 `{mailboxUnread}` |
| **B. 离家信箱表现** | 久无交互后猫离开，主窗显示信箱图；可双击召唤 | ⚠️ 按需填写 `mailboxPresentation` | `pet.patch.json` → `mailboxPresentation`               |


产品契约见桌宠 PRD：[2026-07-03-mailbox-presentation.md](../../../docs/prd/2026-07-03-mailbox-presentation.md) §9.1（v2.1 信箱图内置兜底）。

---

## A. 闲时未读提示（已有脚本）

- 脚本：`fill_base_mode_bubbles.py` / `base_mode_bubble.ensure_mailbox_unread_tip`
- 规则：**整池恰好一条**含 `{mailboxUnread}` 的文案；已有则跳过；排除 sleep / hold
- Agent 润色时**必须保留** `{userName}` / `{mailboxUnread}`
- 细则：[character-design.md](character-design.md)「baseModes.bubble」

**创建 / 角色配置收尾时务必跑一遍 `fill_base_mode_bubbles.py`（除非用户跳过人设且无 baseModes）。**

---

## B. mailboxPresentation（离家表现）

### 何时写


| 情况                                  | 建议                                       |
| ----------------------------------- | ---------------------------------------- |
| 普通自定义宠（无离场/回归序列素材）                  | **enrich 仍自动写时长**；不挂 sequence；Away 图用**程序内置兜底** |
| 用户只要改「多久离家 / 多久自动回来」                | enrich 已写默认；可再 `merge_patch` 覆盖时长                      |
| 已有 `away_`* / `return_*` 等 sequence | 再挂 `awaySequence` / `readLetterSequence` |
| 用户提供了自定义信箱图并已放入 `user/`             | 才写 `mailboxImage`                        |


### 推荐填写示例

**仅时长（最常见，无需 mailbox.png）：**

```json
"mailboxPresentation": {
  "disappearAfterSec": 1800,
  "disappearAwaySec": 300
}
```

**有离场 / 读信序列时（对齐三花语义，id 必须已存在）：**

```json
"mailboxPresentation": {
  "disappearAfterSec": 1800,
  "disappearAwaySec": 300,
  "awaySequence": "away_disappear_play",
  "readLetterSequence": "return_appear_play"
}
```

**可选布局（无需换图文件）：**

```json
"mailboxPresentation": {
  "disappearAfterSec": 1800,
  "disappearAwaySec": 300,
  "mailboxImageScale": 1,
  "mailboxImageFit": "contain",
  "mailboxImageOffsetY": 0
}
```

**仅当用户自带信箱图时覆盖（相对宠物素材根目录）：**

```json
"mailboxPresentation": {
  "mailboxImage": "mailbox.png"
}
```

并把 `mailbox.png` 写入 `user/`（白名单已允许 `.png`），热生效后合并进 runtime。

### 硬约束（与引擎 v2.1 对齐）

- **默认不要写 `mailboxImage`** — 未配置时桌宠使用程序内置信箱图；各宠不必自带 `mailbox.png`
- **禁止编造** `awaySequence` / `readLetterSequence` id；无对应 sequence 就省略字段
- **对照三花**：只对齐字段语义；无 walk / disappear 素材时**不要**硬抄三花的 away 序列名
- 布局字段（`mailboxImageScale` / Width / Height / Fit / Offset*）可写，与是否配置 `mailboxImage` 无关

### enrich 策略

`enrich_pet_patch.py` 在角色配置阶段**自动写入** `mailboxPresentation`（幂等，只补缺失键）：

| 自动写入 | 条件 |
|----------|------|
| `disappearAfterSec: 1800` | 尚未配置该键 |
| `disappearAwaySec: 300` | 尚未配置该键 |
| `awaySequence` | 尚未配置，且已有候选 sequence（如 `away_disappear_play`） |
| `readLetterSequence` | 尚未配置，且已有候选 sequence（如 `return_appear_play`） |
| `mailboxImage` | **永不自动写**（程序内置兜底；仅用户自带图时由 Agent 另写） |

已有字段不覆盖。无离场/读信序列时仍会写时长，Away 图走内置兜底。

---

## 与用户话术对照


| 用户说          | 技能动作                                |
| ------------ | ----------------------------------- |
| 「信箱里提醒我还有未读」 | 层 A：`fill_base_mode_bubbles`（已有）    |
| 「多久不理我就离家」   | 层 B：写 `disappearAfterSec`           |
| 「离家后多久自己回来」  | 层 B：写 `disappearAwaySec`            |
| 「离家动画用某某组合」  | 层 B：确认 sequence 存在后写 `awaySequence` |
| 「回归读信用某某组合」  | 层 B：写 `readLetterSequence`          |
| 「信箱换成我这张图」   | 层 B：落盘 png + 写 `mailboxImage`       |
| 「信箱图标」但未给图   | **不要**写 `mailboxImage`；说明将用程序内置兜底   |


