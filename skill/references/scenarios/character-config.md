# 场景：角色配置（character-config）

**何时进入：**

- [create-custom.md](create-custom.md) Phase B 通过后（HARD，除非用户跳过组合与人设）
- [import-assets.md](import-assets.md) 导入后 `{userDir}/soul.json` 仍不存在时（HARD，除非用户明确跳过人设）
- 用户单独要求「补人设 / 改 soul / 补 baseModes bubble」

**旧名：** Phase C。

## 步骤

```text
enrich_pet_patch.py          ← 默认三态组合主路径（禁止跳过）
  → working_play / fail_play / happy_play + behaviors
  → baseModes（仅自定义 sequence；三态不挂）/ clipLoopRange / homeAction / effect
enrich_pet_patch.py --check  （HARD：有可 enrich 三态时退出码须 0）
write_soul_patch.py --from-pet（再按角色润色；禁止手写精简 soul）
  → user/soul.json
write_soul_patch.py --check
fill_base_mode_bubbles.py    （无 baseModes 时可跳过，属正常）
→ 粒子润色 → [../shared/effects.md](../shared/effects.md)
→ [apply-hot-reload.md](apply-hot-reload.md)
```

```bash
python scripts/enrich_pet_patch.py --pet-id <id>
python scripts/enrich_pet_patch.py --pet-id <id> --check
python scripts/write_soul_patch.py --pet-id <id> --from-pet
python scripts/write_soul_patch.py --pet-id <id> --check
python scripts/fill_base_mode_bubbles.py --pet-id <id>
python scripts/apply_user_changes.py --pet-id <id>
```

**HARD：**
- 禁止只写精简 soul 冒充人设完成（见 soul `--check`）
- **禁止**用 `generate_sequences.py` 代替 `enrich_pet_patch.py`（前者仅 P2 追加；未 enrich 时脚本会拒绝）
- 默认三态组合齐 = 有 `*_play` + `behaviors`，**不**等于有 `baseModes`

完整字段规则、P1/P2/P3 玩法追加 → [../shared/character-design.md](../shared/character-design.md)  
契约 → [../shared/schema.md](../shared/schema.md)  
信箱两层（未读气泡 + 离家 `mailboxPresentation`）→ [../shared/mailbox-presentation.md](../shared/mailbox-presentation.md)

## 子模式（创建宠 enrich 之后）


| 子模式  | 触发                | 行为                                |
| ---- | ----------------- | --------------------------------- |
| P1   | 用户描述玩法            | 生成 1 条 sequence                   |
| P2   | 「随机 N 个」          | **enrich 之后** `generate_sequences.py --count N`（不可代替 enrich） |
| P3   | 「根据 actions 全量生成」 | 批量扫描                              |
| 跳过组合 | 「不要组合」            | 跳过 sequences / 依赖其的 baseModes     |
| 跳过人设 | 「不要人设」            | 跳过 soul.json                      |


编排硬约束 → [../shared/sequences.md](../shared/sequences.md)