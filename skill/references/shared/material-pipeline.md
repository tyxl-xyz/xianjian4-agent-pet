# 素材流水线（绿幕视频主路径）

本文件自包含：Phase 0 基准图 → `generate_video` → 抠图 → 合图 → merge actions。

**落盘隔离（HARD）：** GIF / 视频 / `_build` 只写 `{workspace}/`；`{userDir}/` 仅收 `reference.png|webp`、动作 `*.webp|*.png`、`pet.patch.json`、`soul.json`（见 [paths.md](paths.md)；`{userDir}` 现为 `accounts/{accountId}/pets/{petId}/user`）。

**Tool 可用性：** 本流水线依赖 `generate_image` / `generate_video`。环境缺少 `generate_video` 时：创建宠场景改走 [../scenarios/import-assets.md](../scenarios/import-assets.md)；组合定制仅在「现成/近义不够」时进入 [../scenarios/fill-action-gap.md](../scenarios/fill-action-gap.md)——有视频则拍，无视频则告知现成不足，**禁止**空等。

## 默认四批


| 批次      | 视频段     | 产出 action ids                                   |
| ------- | ------- | ----------------------------------------------- |
| idle    | 1 段循环姿态 | `idle`（atomic）                                  |
| working | 3 段     | `idle_to_working`, `working`, `working_to_idle` |
| fail    | 3 段     | `idle_to_fail`, `fail`, `fail_to_idle`          |
| happy   | 3 段     | `idle_to_happy`, `happy`, `happy_to_idle`       |


`defaultActivity` 通常为 `idle`。用户扩展态（如 sleep）同样建议三段往返。

四批可并行生成视频，但 **每批独立完成抠图→合图→merge→热生效**，不要等全部视频做完再一次写 patch。

---

## Phase 0 — 角色基准图

**HARD GATE：** 未完成 Phase 0 并取得基准图前，**禁止**调用 `generate_video`。

### 0.1 撰写 `generate_image` 提示词（必须先写）

调用前 Agent **必须先输出**完整提示词（可向用户展示），固定包含：


| #   | 要素 | 要求 |
| --- | --- | --- |
| 1   | **背景颜色** | 纯色平涂，供 HSV 色键。背景色相须与角色主体**明显区分** |
| 2   | **幕布铺满（HARD）** | 幕布 **edge-to-edge** 铺满到四边；**禁止**白边 / 圆角内框 / inset framing。只写 `Solid green background` **不够** |
| 3   | **满画面构图（HARD）** | 用**包围盒边距百分比**约束，禁止只写「居中」「靠近」「大一点」。模型默认会把角色缩到画面中心 25%～40% |
| 4   | **图片比例** | **1:1** 正方形 |
| 5   | **角色状态** | 摄影机固定、**全身**可见、**正面**、自然站立/轻微待机；**禁止裁切**头顶/脚/四肢 |
| 6   | **用户描述** | 外观、物种、配色、服饰、风格等，原样融入 |


**否定空间 + 定量构图（HARD — 不可省略）：**

- 幕布：至少含 `edge-to-edge`、`zero margin`、`no white borders`、`no rounded corners`、`no inset framing`
- 幕布均匀（HARD — 正向约束，勿只写 `no gradients`）：须含 `EXACTLY uniform` / `identical shade`、具体 RGB 锚点、`paint bucket` 类比、`no light falloff`；扩散模型易出顶深底浅渐变，负向指令往往只能减弱不能消灭
- 构图用**包围盒**说话（不要写「主体占画面面积 75%～85%」——剪影像素面积达不到，且与边距互相矛盾）：


| 指标 | 目标区间 | 说明 |
| --- | --- | --- |
| 脚底 → 底边 | **3%～12%** 画面高度 | 贴底防悬浮；过贴易裁脚 |
| 头顶 → 顶边 | **8%～22%** 画面高度 | 防裁耳/顶；也防头顶留白 30%+ |
| 左 / 右幕布 | 各 **≤14%**，且 \|L−R\| **≤8%** | 水平饱满且对称 |
| 包围盒宽 / 高 | 宽 **≥78%**，高 **≥72%** | 桌宠小窗可辨；视频会继承此比例 |


**幕布色选取（与 chroma_key 对齐，HARD）：**

**任意有色点缀**（眼睛、鼻头、服饰主色、配件等）只要色相与候选幕布过近，即禁用该幕布——不要求「大面积」绿色才换色。黑 / 白 / 灰（低饱和）可忽略。

固定色板（OpenCV H **0–179**；禁止写 200–260 当蓝幕）：

| 幕布 | 提示词名 | RGB 锚点 | `chroma_key --hue` |
| --- | --- | --- | --- |
| 绿 | GREEN | `80, 220, 40` | `35-85`（默认） |
| 青 | CYAN | `40, 200, 200` | `75-105` |
| 蓝 | BLUE | `50, 120, 200` | `100-130` |
| 品红 | MAGENTA | `220, 40, 180` | `140-170` |

**选色步骤（写 prompt 前必做）：**

1. 从用户描述列出有色部位 → 估 OpenCV H 簇（例：绿眼睛≈55，粉鼻子≈150–165）
2. 可跑：`python scripts/suggest_screen_color.py --hues 55,160`（或生成后 `--from-image`）
3. 对上表 4 候选算相对各簇的**最小环距**，取最大者；落入某候选 hue 窗的直接淘汰
4. prompt 与后续 `chroma_key_to_gif --hue` **必须同一色板项**

例：黑白奶牛猫 + 绿眼 + 粉鼻 → **禁止绿幕**（眼）与**慎用品红**（鼻）；优先 **青 / 蓝**。


**提示词模板（英文更稳，可中英混写）：**

```text
[用户描述：物种、外观、配色、风格、服饰等]

Solid [GREEN / CYAN / BLUE / MAGENTA] screen background that fills the ENTIRE image
edge-to-edge with zero margin.
EXACTLY uniform color: every background pixel must be the identical shade
([GREEN: RGB 80,220,40] / [CYAN: RGB 40,200,200] / [BLUE: RGB 50,120,200] / [MAGENTA: RGB 220,40,180]).
The background color must NOT vary from top to bottom or left to right.
Flat digital fill, like a paint bucket tool, NOT a photographed backdrop.
No studio lighting on the background, no light falloff, no brightness gradient,
no vignette, no shadows on backdrop.
No white borders, no rounded corners, no inset framing.
1:1 square aspect ratio.

COMPOSITION (bounding box — MUST FOLLOW):
- Character bounding box is LARGE: width >= 78% and height >= 72% of the frame
- Feet/contact point near the bottom edge: gap 3%-12% of frame height
  (NOT floating; NOT vertically centered in the middle of the frame)
- Head clearance 8%-22% of frame height; ears/head NOT cropped
- Left and right screen margins each <= 14% and nearly symmetric (|L-R| <= 8%)
- Full body visible, front-facing, neutral standing pose, fixed camera
- Do NOT shrink the character into the center with large empty backdrop

No text, no watermark, no multiple characters.
```

**redo** 时必须保留 edge-to-edge、幕布均匀（EXACTLY uniform / paint bucket / no light falloff）**与** COMPOSITION 定量段，不得缩回「character centered with small margin」或仅写 `no gradients`。  
`analyze_reference` 报四角色差过大 / 渐变 / **色键冲突**时优先 `redo-bg`，禁止按裁脚去做 `redo-compose`。

### 0.2 生成基准图

```python
generate_image(
    prompt="<0.1 完整提示词>",
    # 若工具支持尺寸，指定 1:1，如 1024x1024
)
```

- 保存到 `{userDir}/reference.png`（或 `reference.webp`）；**仅此基准图**进入 user，生成过程的其它临时图留在 `{workspace}/`
- **必须**双轨自检（默认 HARD）——视觉 + 像素，缺一不可：

**A. `view_image`（辅证；禁止用模糊词代替定量项）：**

  1. 全身、正面、自然站立/待机；头顶/脚未被裁切
  2. **幕布铺满：** 四角均为幕布色；无白边/圆角内框（白边 → 色键残留白框 → **FAIL**；禁止「白色也是纯色」放行）
  3. **满画面：** 角色明显偏大、脚底贴近底边、非垂直居中悬空；左右大致对称
  4. 幕布色与角色对比足够
  5. 单角色、无文字水印

**B. 像素门禁（HARD，`adopt` 前必跑）：**

```bash
# 先按描述估 hue，或生成后对图建议幕布：
# python scripts/suggest_screen_color.py --hues 55,160
python scripts/analyze_reference.py --input {reference} --expected cyan
# --expected 与选用色板一致：green|cyan|blue|magenta；可选 --out-dir {workspace}/qa
```

  - 退出码非 0 → **不得**普通 `adopt`；按 `errors` / `hint` redo
  - `view_image` 口头提到白边或「角色很小」但未判 FAIL → **以脚本为准**
  - 脚本顺序：**先**幕布铺满（四角均匀 / 无白边 / 无渐变），**再**构图边距，**再**色键冲突（角色高饱和点缀 vs 幕布 hue）
  - **幕布渐变 / 四角色差过大 → `redo-bg`**（强调 `flat uniform color, no gradients`）。此时脚本会 `framing.skipped=true`，**禁止**把报告里的「裁脚/裁顶」当真——渐变时全局幕布色不可信，边距未计算
  - **色键冲突（眼睛等同色被抠风险）→ `redo-bg`**，按 `key_conflict.suggested` 换色板；不可用 `redo-compose` 糊弄
  - 仅当幕布均匀通过后，才用各边**局部幕布色**估脚底/头顶/左右；不通过项才走 `redo-compose`

- **默认：** 任一项不通过 → 不得普通 `adopt`；须 `redo-*` / 换图 / 重生成
- **用户覆盖：** 用户明确坚持特殊构图时：
  1. 先说明风险（视频继承小比例 → 128px 窗口难看清；白边 → 不透明白框；裁切 → 合图不稳）
  2. AskQuestion 增加 `adopt-anyway`
  3. **白边默认不可 `adopt-anyway`**（除非用户书面接受白框）；「角色偏小」可覆盖但须记风险
- 未覆盖不通过 → 加强 COMPOSITION 定量段 / edge-to-edge 后重跑 `generate_image`

### 0.3 用户确认（HARD GATE）

**先露图、再提问（HARD — 禁止「只问不看」）：**

1. AskQuestion **之前**，必须在**对用户可见的回复**中展示待确认基准图（最终 `{reference}`，如 `reference.png`）
2. 展示方式按宿主能力择一（优先靠前）：
   - 回复中嵌入图片（markdown `![基准图]({reference绝对或可访问路径})`，或平台等价的媒体/附件写法）
   - 若宿主不支持气泡出图：明确写出可读路径，并说明「请打开该文件查看后再选」
3. **禁止**仅依赖工具折叠摘要（如「生成了 N 张图片」）代替展示——用户看不见图时不得发起确认
4. 中间失败/重试图留在 `{workspace}/`，**不要**全部刷进对话；确认区只放**当前待 adopt** 的一张
5. `view_image` 仅供 Agent 自检，**不等于**已向用户展示

未完成上述露图步骤 → **禁止**调用下方 AskQuestion。

AskQuestion：

- `title`: `基准图确认`
- `id`: `pet-reference-adopt`
- `prompt`：须假定用户**已看到**上方附图；可简述门禁结果，但不可用「已通过」代替出图
- `options`:
  - `adopt` — 确认采用（`view_image` + `analyze_reference.py` 均已通过，**且用户已见附图**）
  - `redo-prompt` — 调整角色描述后重生成
  - `redo-bg` — 更换幕布色 / **消除渐变·vignette·不均匀** / **色键冲突（眼睛等点缀与幕布同色相）** 后重生成（`analyze_reference` 报四角色差过大或 `key_conflict` 时优先此项）
  - `redo-border` — 白边 / 幕布未铺满，加强 edge-to-edge 后重生成
  - `redo-compose` — **仅幕布已通过时**：角色过小 / 脚底悬浮 / 头顶留白过大 / 左右偏，加强 COMPOSITION 定量段后重生成（幕布渐变时勿选此项当裁脚处理）
  - `adopt-anyway` — **仅当自检未过且用户坚持**：已知风险仍采用（白边默认不用）
  - `replace` — 用户提供新参考图

用户未选 **adopt** / **adopt-anyway** 前禁止进入 Phase A。  
用户**已上传**参考图：跳过 0.1～0.2 生成，但仍须 `view_image` + `analyze_reference.py` + **向用户展示该图** + 0.3 确认。

基准图路径记为 `{reference}`，后续**每一批** `generate_video` 的 `input_reference` 均用该图。  
**视频会继承基准图比例**——基准图角色过小，则所有动作在桌宠窗口中都偏小。

---

## Phase A — 单批次步骤

### 1. generate_video（参数与提示词）

**时长按批次选择（HARD：禁止四批一律 `seconds=8`）：**


| 批次                                 | 段数  | `seconds` | 理由                                               |
| ---------------------------------- | --- | --------- | ------------------------------------------------ |
| **idle**                           | 1   | **4**     | 只需一小段循环呼吸/眨眼，过长浪费生成且合图帧过多                        |
| **working** / **fail** / **happy** | 3   | **8**     | 需切出 enter / hold / leave；不够切可升到 **10**，禁止默认超过 10 |


### 自定义 / 扩展动作时长怎么判（HARD）

默认四批以外（鼓掌、睡觉、跳舞、演讲、用户口述新动作等）：**段结构定区间，动作复杂度取秒数**。禁止一律 8。

```text
用户要的新动作
    ↓
1) 判定段结构 → 得到秒数区间
    ↓
2) 判定复杂度（简 / 中 / 繁）→ 在区间内取具体 seconds
    ↓
3) prompt 里写明同样秒数（与 seconds= 一致）
```

#### Step 1 — 段结构 → 区间


| 段结构         | 何时用                       | 秒数区间     | 切分预期                            |
| ----------- | ------------------------- | -------- | ------------------------------- |
| **单段循环**    | 姿态微调、持续循环、无进出场（类似 idle）   | **4～6**  | 整段 → 1 个 atomic                 |
| **三段往返**    | 「从待机做出某动作再回去」（默认大多数自定义动作） | **6～10** | `idle_to_X` / `X` / `X_to_idle` |
| **双段 / 单向** | 只要进场或只要离场（少见）             | **4～6**  | 2 个 transition 或 1 转 + 1 atomic |
| **多拍叙事**    | 用户明确「先…再…最后…」≥4 拍         | **8～12** | 按切点多分段再合图                       |


#### Step 2 — 复杂度 → 区间内取值


| 复杂度   | 判据（肢体幅度 / 拍数 / 是否要看清细节）                | 三段往返取  | 单段取     |
| ----- | -------------------------------------- | ------ | ------- |
| **简** | 单一小动作、重复 1～2 下即可看清：鼓掌、点头、挥手、竖拇指、眨眼加强   | **6**  | **4**   |
| **中** | 有姿态变化或短循环 hold：睡觉躺下、吃东西、简单舞、工作/忙碌感     | **8**  | **4～6** |
| **繁** | 多步骤、大幅度、或需较长 hold 才切得开：演讲手势、复杂舞、连续道具交互 | **10** | **6**   |


**示例：**


| 动作  | 段结构  | 复杂度             | `seconds` |
| --- | ---- | --------------- | --------- |
| 鼓掌  | 三段往返 | 简（双手拍几下）        | **6**     |
| 睡觉  | 三段往返 | 中（躺下 + 呼吸 hold） | **8**     |
| 演讲  | 三段往返 | 繁（手势多拍）         | **10**    |
| 走路  | 单段循环 | 中               | **4～6**   |


**推断启发式（无用户明示时）：**

1. 含「一下 / 做个 X / 从待机」→ **三段往返**；再按上表定简/中/繁
2. 含「循环待机 / 轻微动 / 呼吸」且无进出场 → **单段·简**，`seconds=4`
3. 含「走路 / 移动」→ **单段**，`seconds=4`～`6`
4. 说不清复杂度时：三段默认按 **中=8**；用户说「短一点」→ 降一档（8→6）；说「切不开」→ 升一档（6→8→10），仍不够再问用户

**上限：** 单次默认不超过 **10**；仅用户明确要求更长或「多拍叙事·繁」才到 12，并说明成本。

```python
# idle 示例
generate_video(
    prompt="Exactly the same [角色] from reference. "
           "Start in the exact pose shown in reference image. "
           "[本批次动作描述]. "
           "End by returning to the exact same pose as reference image. "
           "Keep the SAME scale and footing as the reference: "
           "character stays large in frame, feet near bottom edge, "
           "do not zoom out or float upward. "
           "Solid [与基准图相同的幕布色] screen background that fills the ENTIRE frame "
           "edge-to-edge with zero margin, no white borders, no inset framing. "
           "1:1 square frame, fixed camera, 4 seconds",
    input_reference=[{"type": "path", "path": "{reference}"}],
    seconds=4,   # 见上方「默认四批」与「自定义时长」表
    size="720p",
)
```


| 参数                | 值                              |
| ----------------- | ------------------------------ |
| `input_reference` | Phase 0 确认的 `{reference}`      |
| `seconds`         | **按「默认四批」或「自定义时长」表**；禁止无依据一律 8 |
| `size`            | `720p`                         |
| 幕布色               | 与基准图一致                         |
| 构图                | **继承基准图比例**：same scale/footing；禁止中途缩小/上飘 |


**各批次「动作描述」：**


| 批次          | 段数  | prompt 侧重                      |
| ----------- | --- | ------------------------------ |
| **idle**    | 1   | 始终保持参考图姿态，轻微呼吸/眨眼即可            |
| **working** | 3   | idle → **可无缝循环**的工作表演 → 回 idle |
| **fail**    | 3   | idle → **可无缝循环**的失败表演 → 回 idle |
| **happy**   | 3   | idle → **可无缝循环**的开心表演 → 回 idle |


**HARD：三段批视频必须产出「可循环的中段」，禁止纯情绪弧线。**  
`hold` + `duration.mode: clip` 会把段2 **首尾相接**重复播放；中段若不是闭合周期，循环必跳帧/闪切。

prompt 必须同时约束：

1. 全片：起止回到基准图 / idle 姿态（与上文一致）
2. **中段**：X 表演为 **seamless loop**——该循环段的**起始姿态 = 结束姿态**；至少完整 1 个周期；勿把「越来越激动再收住」拍成不可循环的弧线
3. **构图继承（HARD）：** `same scale and footing as reference`；全程角色保持大比例、脚底靠近底边；**禁止** zoom out / 垂直上飘 / 重新「安全居中缩小」
4. **幕布：** 与基准图同色，edge-to-edge 铺满

**三段批完整示例（happy）：**

```text
Exactly the same [角色] from the reference image.
Starts in the exact idle pose from the reference.
Then transitions into a happy playful action that forms a seamless loop:
the pose at the start of the looping section must match the pose at the end
of that same looping section (one full cycle, suitable for infinite repeat).
After at least one full loop cycle, returns to the exact same idle pose as reference.
Keep the SAME scale and footing as the reference throughout:
character remains large in frame, feet near the bottom edge,
do not zoom out, do not float upward, do not shrink into the center.
Solid [幕布色] screen background that fills the ENTIRE frame edge-to-edge
with zero margin, no white borders, no inset framing
— same color as the reference image background.
1:1 square frame, fixed camera, 8 seconds
```

时间轴约定（便于切三段）：

```text
[0%──────25%───────75%──────100%]
 idle→X      X 无缝循环      X→idle
  段1           段2            段3
```

约束：角色勿出画、勿大面积遮挡幕布；构图比例与基准图一致。

### 2. 三段语义与切点（working / fail / happy / 扩展态）

设锚点 `home` = `defaultActivity`（通常 `idle`），目标态 `X`：


| 段序  | action id       | kind       | 语义                                  |
| --- | --------------- | ---------- | ----------------------------------- |
| 段 1 | `{home}_to_{X}` | transition | idle → X                            |
| 段 2 | `{X}`           | atomic     | X **无缝循环**表演（`loop: true` + `clip`） |
| 段 3 | `{X}_to_{home}` | transition | X → idle                            |


**找切点（抠图前）：**

1. 抽帧预览（约每 0.5s）并 `view_image`
2. 切点 A：刚脱离 idle、**已进入**可重复的 X 姿态 → 段1|段2
3. 切点 B：X 完成**整数个**周期、**尚未**开始收回到 idle → 段2|段3
4. 段 1/3 含完整入/出，勿半路截断；段 2 **禁止**包含「开始回 idle」的过渡帧

#### HARD GATE — 段2 循环接缝（合图前必须通过）

对拟作 hold 的段2（GIF 或抽帧）：

1. `view_image` **第 0 帧**与**最后一帧**（或倒数第 1～2 帧）
2. **通过标准：** 姿态/朝向/四肢位置目视接近，接成循环时无明显跳变
3. **不通过 → 禁止** `make_spritesheet` / merge：
  - 优先 `redo-cut`：缩短或平移段2，使首尾落在同一周期相位
  - 切不出闭合周期 → `redo-video`（加强 seamless loop 文案后重生成）
4. **拒收信号：** 段2 首尾差很大；或 leave（段3）帧数远大于 hold（段2）且段2 明显含「收势」——多半切点 B 过晚或中段不是循环

**idle 只切 1 段**，不做三段；但 idle 自身若 `loop: true`，同样建议首尾姿态接近（呼吸循环）。

### 3. 抠图

GIF 输出到**会话工作区**（与视频同目录即可），**禁止**写到 `{userDir}`：

```bash
# idle 单段（默认 --size 720，贴齐 720p 源；勿再压到 480）
python scripts/chroma_key_to_gif.py input.mp4 -o "{workspace}/idle.gif"

# 三段（秒数按切点填写）
python scripts/chroma_key_to_gif.py input.mp4 \
  --segments 0:2,2:6,6:9 \
  -o "{workspace}/idle_to_happy.gif" "{workspace}/happy.gif" "{workspace}/happy_to_idle.gif"
```

蓝幕示例：`--hue 100-130`（OpenCV H；勿写 200–260）。显式指定尺寸：`--size 720`。  
边缘绿溢：默认对**背景 mask 膨胀**切绿边（`--dilate`，默认 2）；**禁止**对背景 mask 做 erode（会把绿边包进角色）。

### 4. GIF 确认（guided）

对本批次每段 GIF `view_image`。**三段批必须先做「段2 循环接缝」检查（见上 HARD GATE）**。

**先露图、再提问（HARD，同 §0.3）：** AskQuestion 前须在对话中展示待确认素材（优先 `make_contact_sheet` 产出的 contact-sheet，或 GIF 路径嵌入）；禁止仅依赖工具摘要。未露图不得发起 `pet-gif-adopt`。

再 AskQuestion（`id: pet-gif-adopt`）：

推荐机器辅助（对照 [qa-rubric.md](qa-rubric.md)）：

```bash
# 段2 hold：接缝量化 + 总览图（仍须目视）
python scripts/inspect_frames.py --input "{workspace}/happy.gif" --out-dir "{workspace}/qa" --check-loop
python scripts/make_contact_sheet.py --input "{workspace}/happy.gif" --out "{workspace}/qa/happy-contact-sheet.png"
```

prompt 须写明：段2 首尾是否可无缝循环；若否不得选 adopt。

- `adopt` — 段2 接缝已通过，继续合图
- `redo-cut` — 重切点再抠图（仅三段批；接缝失败时优先）
- `redo-chroma` — 调 hue 再抠
- `redo-video` — 中段无法切成循环，重跑 `generate_video`

`quick` 档可跳过向用户提问，但 **Agent 仍必须自检段2 首尾**；不通过则自行 `redo-cut` / `redo-video`，禁止带着坏循环合图落盘。

### 5. 编码 stacked `.mov`（主路径）+ 可选 WebM / 合图回退

绿幕主路径：**每 clip 默认一条** `{id}.mov`（stacked-alpha：上半 RGB、下半灰度 matte），写入 `videoHevc` + `videoAlphaLayout: "stacked"`，避免超宽 PNG 图集卡主线程。**创建宠默认不生成** `{id}.webm`；需要兼容旧素材或显式要 VP9 时加 `--also-webm`。

**Mac / Win 透明视频（HARD）：** WKWebView **不支持** WebM alpha。引擎 **优先** 播 `videoHevc`（Mac 与 Win 对齐，同一 stacked-GL 合成）；缺文件或解码失败再回退已有 WebM / 合图。禁止因 Mac 黑底改回优先 spritesheet。仅在明确只要 WebM、不要 stacked 时用 `--webm-only`（旧旗标 `--no-mac-video` 等价，已弃用）。

**白边 / 预乘（HARD）：**
- **Stacked `.mov`（默认）：** 上半 RGB 须先 `premultiply=inplace=1` 再 `format=yuv420p`。`verify_stacked_mac_video` 拒绝透明区上半 RGB 过亮。
- **WebM（可选 `--also-webm`）：** `encode_webm` 须 `format=rgba,premultiply=inplace=1` 再进 `yuva420p`。透明区残留白底 RGB 时，WebView2 + Pixi `premultiplied-alpha` + LINEAR 缩小会出现一圈白边。`verify_webm_transparency` 拒绝透明区 RGB 过亮。

**输入契约（HARD）— 防跑偏：**

1. 编码输入必须是**已抠像**素材：优先 `chroma_key_to_gif` 产出的透明 GIF；**禁止**直接把未抠像绿幕 `mp4/mov` 丢给 `encode_action_webm`。
2. 编码成功后脚本会抽帧校验透明/matte（stacked 或 WebM）。失败则整批失败，须重做抠像，**禁止**宣称视频已交付。
3. **禁止误诊（常见幻觉，一律否决）：**
   - 「ffprobe / 日志里是 `yuv420p` + `alpha_mode:1` ⇒ 没编进 alpha」——VP9 透明 WebM 默认探测常长这样；必须以 `ffmpeg -c:v libvpx-vp9` 解码后的透明像素为准。
   - 「imageio-ffmpeg / 静态 ffmpeg 的 libvpx 有 bug、写不进 alpha ⇒ 必须 brew 换 ffmpeg」——本流水线使用的静态包**可以**写真实 alpha；绿幕不透明是输入未抠像，不是编码器卡点。
   - 「视频不透明 ⇒ 改走 spritesheet / 只合图」——**禁止**因此静默降级；仅 ffmpeg **自动安装彻底失败**或用户明确要求合图回退时才可 `make_spritesheet`。

**ffmpeg（HARD）：**

- 路径解析完成后、进入 Phase A 素材编码前，Agent **必须**先跑：
  ```bash
  python scripts/encode_action_webm.py --ensure-only
  ```
- 脚本会自动：PATH → 已装 `imageio-ffmpeg` → 下载静态二进制到 `~/.cache/lingxi-pet/ffmpeg/` → `pip install imageio-ffmpeg` → 最后 `brew install ffmpeg`。
- **禁止**因 `which ffmpeg` 为空就改走 spritesheet；只有 `--ensure-only` / 编码步骤在自动安装后仍失败，才可告知用户后临时合图回退。
- **禁止**把「透明校验失败」当成「该 brew 安装另一个 ffmpeg」。

中间产物目录必须在**会话工作区**，禁止写到 `{userDir}`：

```bash
# 正确顺序：绿幕视频 → 透明 GIF → stacked .mov（创建宠默认）
python scripts/chroma_key_to_gif.py --input "{workspace}/video.mp4" \
  --segments 0:2,2:6,6:9 \
  --names idle_to_happy,happy,happy_to_idle \
  -o "{workspace}/_build/happy"

python scripts/encode_action_webm.py --input "{workspace}/_build/happy/happy.gif" \
  -o "{workspace}/_build/happy/happy.mov"
# 各段同理；脚本会打印「透明校验通过」；默认无 .webm

# 可选：额外产出 VP9+alpha .webm（引擎仍可播；创建宠默认不加）
python scripts/encode_action_webm.py --input "{workspace}/_build/happy/happy.gif" \
  -o "{workspace}/_build/happy/happy.mov" --also-webm

# 可选：同时产轻量 spritesheet 作回退（默认关闭；建议较小 frame-size）
python scripts/encode_action_webm.py --input "{workspace}/_build/happy/happy.gif" \
  -o "{workspace}/_build/happy/happy.mov" \
  --also-spritesheet --frame-size 128
```

`encode_action_webm` 会写 `{prefix}_video_manifest.json`；`build_pet_json` 识别后写入 `actions.*.videoHevc`（及可选 `video`），并拷贝 `.mov`（及可选 `.webm`）→ `user/`。

**frames / 时长（HARD）：**

- manifest / patch 中 `frames` 必须来自源 GIF 帧数（或 `时段 × sample_fps`），**禁止** `frames=1`（无 ffprobe 时旧版会写占位，导致序列调度约 42ms）。
- 编码使用 `--fps`（默认 24）写入 ffmpeg `-r`，与 `chroma_key` 抽帧率对齐；不要用 GIF 40ms delay 反推权威时长。
- 落盘后对照 [qa-rubric.md](qa-rubric.md)「video frames」项；已污染的宠须重跑 encode 或手改 patch 后热生效。

**旧路径（可选回退合图）：** 仅当 ffmpeg **自动安装失败**或需兼容旧宠时，才可用 `make_spritesheet`：

```bash
python scripts/make_spritesheet.py -o "{workspace}/_build/happy" \
  --prefix happy \
  --names idle_to_happy,happy,happy_to_idle \
  --fps 24 --frame-size 720 \
  idle_to_happy.gif happy.gif happy_to_idle.gif
```

**HARD：** 每批次前缀必须唯一（推荐 `--prefix` / 目录名 = 批次 atomic id）。  
有 `video` / `videoHevc` 时引擎优先播视频（WebKit 优先 `videoHevc`）；解码失败且同 clip 有 `spritesheet` 则自动回退。

**分辨率契约（HARD）：**

| 字段 | 默认 | 含义 |
| --- | --- | --- |
| chroma `--size` / 合图 `--frame-size` | **720** | 纹理格像素（`cellWidth`/`cellHeight`）；纯 video 可用 display 占位 |
| `displayWidth` / `displayHeight` | **128** | 默认窗口逻辑边长；与 cell 解耦 |
| WebM（可选） | 源分辨率 | `--also-webm`；流式解码，不进超宽图集 |
| stacked `.mov` | 源分辨率×2 高 | 默认主路径；引擎按半高合成 |

`build_pet_json` 默认 `--display-size 128`；引擎对图集 `scale = display / cell`，对 video 同理按视频固有尺寸缩放。

**WebP 16383 宽限制（仅合图回退路径）：**

- 横条宽度 = `帧数 × frame_size`。`frame-size 720` 时约 **22 帧**（~0.9s@24fps）即超限。
- 超限时 `make_spritesheet` **主交付**为 `{prefix}.png`，并写入 `manifest.sprite` / `spritesheet`（须与文件一致）。
- `build_pet_json` 按 manifest 拷贝该 PNG 进 `user/`；引擎可加载 png，超宽时由 `stripAtlas` 折行上 GPU。
- `{prefix}_partN.webp` **仅工作区调试**，禁止写入 `user/`、禁止写进 `actions.*.spritesheet`。
- 合图后若 `user/` 缺图或仍指向不存在的 `.webp` → 视为失败，须重跑合图 / merge。

**P1 候选 — 编码期折行（未实施，评估结论）：**

| 项 | 结论 |
| --- | --- |
| 动机 | 720 格下 ≥1s@24fps 几乎必超 WebP；PNG 主路径可用但体积/解码/GPU 折行成本更高 |
| 做法 | `make_spritesheet` 按 `max_cols = min(16383, 8192) // frame_size` 把**同一动作**帧折成多行网格，整张仍输出 **WebP** |
| 引擎 | `createGridAnimSprite` 已支持 `frameIndex → (col=i%columns, localRow=⌊i/columns⌋)`；多动作时 `row` = 该动作起始行 |
| 720 格 | `max_cols≈11`（GPU 8192）或 `22`（仅 WebP）；96 帧 → 约 9 行 / 5 行 |
| 风险 | contactsheet 变高；旧「一行一动作且 columns=帧数」素材不受影响；须单测折行坐标 |
| 时机 | **P0 已验证后再做**；优先保交付正确，再优化格式 |

`sources` / `--names` **必须**按 段1→段2→段3 顺序（对应 webp row 0/1/2）。

### 6. 写入 patch（仅 actions）

```bash
python scripts/build_pet_json.py \
  --manifest-dir "{workspace}/_build/happy" \
  --out "{userDir}" \
  --pet-id my-cat \
  --display-name "我的猫" \
  --default-activity idle \
  --merge "{userDir}/pet.patch.json"
```

`--out` 指向 `{userDir}` 时脚本会把成品 `{id}.mov`（及可选 `{id}.webm`）和/或合图（`.webp` / 超限 `.png`）拷进 user；**仅允许留下媒体成品 + pet.patch.json**（及已有的 reference / soul）。  
**禁止**把 GIF、绿幕源 mp4、`_build`、manifest、contactsheet、`*_partN.webp` 留在 `user/`。  
**禁止**对本步使用 `--auto-sequences`。

### 7. 热生效

每批 merge 后调用热生效（见 [../scenarios/apply-hot-reload.md](../scenarios/apply-hot-reload.md) / [apply-changes.md](apply-changes.md)）。

### 验收（透明视频）

1. 脚本冒烟：短 GIF → `encode_action_webm` → 默认产出 `.mov`（无 `.webm`）；`--also-webm` 才有伴生 WebM。
2. 手测：点互动序列时日志出现 `loading "<clip>" video path=*.mov layout=stacked`；accept→enqueue 应亚秒级（不再等 60MB+ PNG 解码）。
3. **WebKit / Mac / Win**：日志应出现 `path=*.mov layout=stacked` / `via=stacked-alpha`。禁止优先合图。仅 `videoHevc` 解码失败时才 `falling back to spritesheet`（或已有 WebM）。

---

## 用户扩展状态


| 用户说 | 追加批次                   | 门禁 `--extra`        |
| --- | ---------------------- | ------------------- |
| 加睡觉 | sleep 三段               | `--extra sleep`     |
| 加散步 | walk_left / walk_right | `--extra walk_left` |


规则同 working：默认 **三段往返**，再按复杂度取秒（睡觉偏中=`8`，走路偏单段=`4`～`6`）；只 merge actions，再热生效。  
其它口述新动作：按上文「段结构 × 复杂度」定秒数（如鼓掌=三段·简 → `6`）。

---

## user-only 首批必填字段

```json
{
  "id": "my-cat",
  "displayName": "我的猫",
  "schemaVersion": 3,
  "defaultActivity": "idle",
  "cellWidth": 720,
  "cellHeight": 720,
  "displayWidth": 128,
  "displayHeight": 128,
  "actions": { "atomic": {}, "transition": {} },
  "sequences": {},
  "categories": { "sequence": { "name": "组合", "states": [] } },
  "behaviors": {}
}
```

`behaviors` 在引擎类型中为必填；user-only 至少给 `{}`，或按需映射系统行为。  
`official-overlay` 只写增量 actions / sequences，勿重复 official 已有项。

## 验收

每批 GIF 建议用户看一眼（guided）。合图后抽查 webp 透明度与脚底对齐。