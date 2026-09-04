# 仙剑四 Agent 动态桌宠

基于豆包 AI 生成绿幕素材 + [lingxi-pet 技能](skill/)（灵犀桌宠官方定制技能）打造的四角色动态桌宠 **han-ling-sha**。支持仙剑四主角团四人切换、角色专属台词气泡（游戏原文）、闲时随机发言。

## 项目亮点

- **四角色一体**：韩菱纱（红衣双髻）、云天河（拉弓）、柳梦璃（抱竖琴）、慕容紫英（持剑），单个桌宠内随时切换登场
- **台词来自仙剑四游戏原文**：每角色 10 句原文台词池，闲时随机弹出一句；台词按角色区分（梦璃温婉通透、紫英冷峻守诺、菱纱爽朗机敏、天河憨直赤诚）
- **闲时随机发言**：静置 1-3 分钟自动弹一句角色台词（`scheduleIntervalSec: [60, 180]`）
- **气泡停留优化**：气泡单行宽度限制 ≤17 字符，长台词已按原文标点拆分为短句，完整显示不截断；`dwellSec: [10, 14]` 秒
- **完整素材管线**：绿幕抠图 → 水印清除 → 竖屏方形化 → 透明编码，全程脚本化可复现

## 目录结构

```
xianjian4-agent-pet/
├── README.md               # 本说明
├── pet/                    # 桌宠本体（运行时数据）
│   ├── assets/             # 8 个动作动画 .mov（idle/working/happy/fail + 四角色登场）
│   ├── reference.png       # 角色基准图（生成动作参考）
│   ├── pet.patch.json      # 桌宠配置（actions/sequences/baseModes/bubble）
│   └── soul.json           # 人设（问候/时间问候/喜好/反应）
├── skill/                  # lingxi-pet 技能完整源码（灵犀桌宠官方定制技能）
│   ├── SKILL.md            # 技能入口与路由说明
│   ├── references/         # 场景指南 + 共享规范（schema/素材管线/热生效等）
│   └── scripts/            # 44 个确定性脚本（建宠/抠图/编码/合并/热生效）
├── scripts/processing/     # 自研素材处理脚本（绿幕抠图、水印清除、腿部修复）
└── docs/preview/           # 处理过程 QA 预览图（四态/四角色/修复前后对比）
```

## 桌宠配置一览

### 动作与登场

| 素材 | 动作 | 说明 |
|------|------|------|
| idle/working/happy/fail | 四态基础动作 | 默认行为（behaviors: working/success/fail 映射） |
| mengli/ziying/lingsha/tianhe | 四角色登场 | baseModes 注册，登场弹各自台词 |

### 台词池（仙剑四游戏原文）

| 角色 | 池规模 | 台词风格 |
|------|--------|----------|
| 柳梦璃 | 14 段 | 温婉通透（"梦影雾花，皆是虚空"） |
| 慕容紫英 | 17 段 | 冷峻守诺（"承君此诺，必守一生"） |
| 韩菱纱 | 17 段（含信箱提示） | 爽朗机敏（"生尽欢，死无憾"） |
| 云天河 | 16 段 | 憨直赤诚（"我命由我，不由天"） |

台词均取自游戏原文，经游民星空、17173、晋江、CSDN、豆瓣多来源交叉验证；长句按原文标点拆分为 ≤17 字符短句以适配气泡单行显示。

### 运行时参数

- `scheduleIntervalSec: [60, 180]` — 闲时随机发言间隔 1-3 分钟
- `dwellSec: [10, 14]` — 气泡停留 10-14 秒
- 交互：点击桌宠为引擎原生交互事件（不触发台词）；登场角色切换触发对应台词

## 快速开始

### 环境要求

- Python 3.9+（numpy / opencv-python / Pillow）
- ffmpeg（[imageio-ffmpeg](https://pypi.org/project/imageio-ffmpeg/) 捆绑版本即可）
- 灵犀桌宠客户端（desktop-pet），账号目录 `accounts/{accountId}/pets/{petId}/user/`

### 使用 lingxi-pet 技能

1. 将 `skill/` 目录安装为灵犀技能（或直接按 `skill/SKILL.md` 路由使用）
2. 桌宠数据写入账号隔离目录：
   ```
   accounts/{accountId}/pets/han-ling-sha/user/
   ├── *.mov            # 动作动画（stacked 透明视频）
   ├── reference.png    # 角色基准图
   ├── pet.patch.json   # 桌宠配置
   └── soul.json        # 人设
   ```
3. 热生效（无需重启桌宠进程）：
   ```bash
   python skill/scripts/apply_user_changes.py --pet-id han-ling-sha
   ```

### 素材处理管线（复现）

原始绿幕视频 → 透明 GIF/MOV，入口脚本：

```bash
python scripts/processing/_process_videos_fix.py   # 四角色绿幕抠图修复版
python skill/scripts/encode_action_webm.py --ensure-only   # 初始化 ffmpeg
```

管线要点（详见脚本注释与 [material-pipeline.md](skill/references/shared/material-pipeline.md)）：

1. **绿幕抠图**：HSV 色键，逐视频收窄 hue 范围（如天河 79-90）解决道具撞绿幕
2. **水印清除**：形态学闭运算重连四肢 + 仅删贴边 16% 内小孤立块（min_area 40 ~ max_area 6000）
3. **颜色通道**：必须 BGR→RGBA（否则蓝紫变红棕）
4. **竖屏方形化**：等比缩放居中到 720×720
5. **编码**：stacked .mov（256×512，121 帧 @24fps）

## 已知限制与踩坑记录

- **点击桌宠不弹台词**：引擎原生点击事件仅记录交互（防打扰），不支持"点击=换一句台词"；当前以"闲时随机发言 + 登场弹词"替代
- **气泡宽度限制**：单行 ≤17 字符（含中文标点），超长自动截断显示"…"；`dwellSec` 只影响停留时长，无法解决截断——必须拆句
- **merge_patch 覆盖陷阱**：改 `bubble` 任意字段时 patch 必须携带完整 `texts`，否则 `ensure_bubbles_on_base_modes` 会用默认模板（"嗨，{userName}！我韩菱纱来啦~"）覆盖已配置台词
- **动作门禁**：热生效可能因缺过渡段（transition）被动作门禁拦截，可接受"无过渡直接切换"后重启桌宠生效

## 技术栈

- 素材来源：豆包 AI 绿幕视频生成
- 处理工具：OpenCV（HSV 色键 / 形态学）、Pillow、imageio-ffmpeg
- 桌宠引擎：灵犀桌宠（desktop-pet），`pet.patch.json` + `soul.json` 数据契约
- 定制框架：lingxi-pet 技能（SKILL.md + 44 脚本 + 文档体系）

## License

仅供个人学习与桌宠定制参考。仙剑四角色、台词版权归原作者（上海软星/大宇资讯）所有；桌宠素材由豆包 AI 生成，版权归生成者所有。
