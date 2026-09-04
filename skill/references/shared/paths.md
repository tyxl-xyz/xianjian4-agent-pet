# 路径与落盘（唯一真相）

## 根目录

桌宠数据根目录（唯一）：


| 平台      | `{petRoot}`                                 |
| ------- | ------------------------------------------- |
| Windows | `%APPDATA%\desktop-pet`                     |
| macOS   | `~/Library/Application Support/desktop-pet` |


## 分层（账号隔离 · 2026-07 起）

```text
{petRoot}/
├── pets/{petId}/
│   └── official/              # 全机共享官方包；skill 禁止写入
├── accounts/{accountId}/
│   ├── prefs.json             # 该账号桌宠偏好（musa 读写）
│   ├── data/                  # 账号级：信箱 DB 等
│   └── pets/{petId}/
│       ├── user/              # skill 唯一写盘（白名单）
│       │   ├── reference.png|webp
│       │   ├── pet.patch.json
│       │   ├── soul.json
│       │   └── *.webp|*.png   # 仅动作 spritesheet 成品
│       └── runtime/           # official ⊕ user 合并结果；skill 只读
│           ├── pet.json
│           ├── soul.json
│           └── *.webp
├── binary/                    # 桌宠二进制缓存（勿写）
└── runtime/                   # 进程级 MCP：mcp-port / mcp-auth（勿当素材目录）
```

**HARD：** 只写 `{petRoot}/accounts/{accountId}/pets/{petId}/user/`，不要写到其它目录。

**废弃（新逻辑不读不写）：** `{petRoot}/pets/{petId}/user`、`{petRoot}/pets/{petId}/runtime`（无账号前缀的旧布局）。

## accountId 解析

创建/定制桌宠默认落在**当前登录账号**。`scripts/paths.py` 自动解析，优先级：

1. CLI `--account-id`
2. 环境变量 `DESKTOP_PET_ACCOUNT_ID` / `LINGXI_PET_ACCOUNT_ID`
3. **`wps-collab.get_me()` → 当前登录 userid**（推荐主路径；不要求桌宠已启动）
4. `accounts/` 下仅有一个账号 → 用之
5. 多个账号：优先含 `pets/{petId}/runtime|user` 的；再按 `prefs.selectedPetId == petId`
6. 仍歧义 → 报错

拿到登录 userid 后：

- 本地已有 `accounts/{accountId}/` → 在该账号下写/新增宠
- 尚无该目录 → `--ensure-user`（或 `ensure_user_dir`）会创建 `accounts/{accountId}/` 与 `user/`

任务开始推荐：

```bash
python scripts/paths.py --pet-id <id> --ensure-user --print
```

**不要**让用户手填数字 ID（除非开发排障）。勿翻 `cloudlog-pending-logs.json` 旁路取 uid。

## user/ 白名单（HARD GATE）


| 允许                                 | 禁止（放 `{workspace}/`，勿进 user）                             |
| ---------------------------------- | -------------------------------------------------------- |
| `reference.png` / `reference.webp` | `.gif`、`.mp4`、`.m4v`、`.mov`、`video_`*                    |
| 动作合图 `*.webp` / `*.png`            | `_build/`、`_preview/`、任意子目录                              |
| 动作短视频 `*.mov`（stacked；默认）/ 可选 `*.webm` | 未编码的绿幕源、中间 GIF                                         |
| `pet.patch.json`、`soul.json`       | `_test_`*、`generated`*、合图 `*_manifest.json`、contactsheet |


中间产物（抠图 GIF、绿幕视频、`make_spritesheet -o` / `encode_action_webm -o` 工作目录）**必须**写在会话工作区；落盘到 `user/` 的仅限最终合图（`.webp` / 超限 `.png`）和/或每 clip 的 `{id}.mov`（及可选 `{id}.webm`）。  
多批次合图须使用唯一文件名（`--prefix` / `_build/<batch>`）；禁止多批都产出 `sprite.webp` 覆盖 `user/` 成品。  
WebP 超限产生的 `*_partN.webp` 不得拷入 `user/`（见 [material-pipeline.md](material-pipeline.md)）。  
原因：热生效会把 `user/` 几乎全部拷进 `runtime/`；中间文件会让热重载变卡甚至 EBUSY。


| 变量                 | 值                                             |
| ------------------ | --------------------------------------------- |
| `{petsBase}`       | `{petRoot}/pets`                              |
| `{petHome}`        | `{petsBase}/{petId}`（含 `official/`）           |
| `{accountPetHome}` | `{petRoot}/accounts/{accountId}/pets/{petId}` |
| `{userDir}`        | `{accountPetHome}/user`                       |
| `{patch}`          | `{userDir}/pet.patch.json`                    |
| `{soulJson}`       | `{userDir}/soul.json`                         |
| `{runtime}`        | `{accountPetHome}/runtime/pet.json`           |
| `{runtimeSoul}`    | `{accountPetHome}/runtime/soul.json`          |
| `{processRuntime}` | `{petRoot}/runtime`（MCP port/auth，非素材）        |


`petId` 正则：`^[a-zA-Z0-9_-]{1,64}$`，且与 manifest `"id"` 一致。  
`accountId` 正则：`^[a-zA-Z0-9_-]{1,128}$`。

## 模式与 patch 语义


| 条件                                      | mode               | `pet.patch.json` | `soul.json`                        |
| --------------------------------------- | ------------------ | ---------------- | ---------------------------------- |
| 无 `official/`（或不存在 `official/pet.json`） | `user-only`        | **完整** manifest  | **完整**人设                           |
| 有 `official/`                           | `official-overlay` | **增量**           | **增量**（覆盖 official/soul.json 同名字段） |


引擎读 user soul：标准 `soul.json`；若仅有遗留 `soul.patch.json` 则回退读取（skill 写入时会迁移）。

## 合并规则

将 `user/pet.patch.json` 合并进官方配置时：

- 普通对象：递归合并；patch 同名字段覆盖
- `actions.atomic` / `actions.transition`：按 **key** 合并
- `sequences`：按 **key** 合并（patch 同名会覆盖引擎侧；**skill 策略仍禁止覆盖已有 seq_id**）
- `categories.sequence.states`：字符串数组 **并集追加**
- `baseModes.actions`：按元素 `id` 合并

将 `user/soul.json` 合并进官方 soul 时：

- 顶层字段：user 覆盖
- `timeGreetings` / `reactions`：二级对象合并（只改 `lateNight` 不丢 `morning`）
- 合并结果写入 `**runtime/soul.json`**（热生效 / 启动时）

skill 落盘策略（比引擎更严）：


| 字段                           | 策略                                                                                                                |
| ---------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `sequences`                  | 仅追加新 id；冲突跳过并报告                                                                                                   |
| `categories.sequence.states` | 仅追加新 id                                                                                                           |
| `actions`（素材）                | create 可 merge；compose-sequence **默认**不改 spritesheet/frames；**仅** fill-action-gap 补拍 / 用户明确加素材时允许 merge 新 actions |
| `actions.*.effect`           | 允许追加                                                                                                              |
| `behaviors`                  | **值必须为 string**（sequence/atomic id）；`merge_patch` 会把误写的 `{actions:[…]}` 规范成字符串，无法规范则拒绝写入；仅追加/覆盖事件键 |
| `baseModes`                  | 按 `actions[].id` 合并（对象数组）；**追加 sequence 时 `merge_patch` 同步挂 baseModes**（排除默认三态与 walk/wander）               |
| `soul.json`                  | 深合并已有；可用 `--replace` 整份替换；**缺契约字段拒绝写入**；收尾须 `--check`                                                                 |


## 读写摘要


| 阶段               | 读                                              | 写                                       |
| ---------------- | ---------------------------------------------- | --------------------------------------- |
| create Phase A   | 已有 `{patch}`（若有）                               | `{userDir}/*.webp` + `{patch}` actions  |
| create Phase B   | `user-only`→`{patch}`；`overlay`→优先 `{runtime}` | —                                       |
| character-config | `{patch}` + 可选 `{runtime}`                     | `{patch}` 补全 + `{soulJson}`             |
| compose-sequence | `{runtime}`（优先）+ `{patch}`                     | `{patch}` sequences（追加）                 |
| fill-action-gap  | `{runtime}` + `{patch}`                        | 另写 actions + `user/*.webp`，再编 sequences |


落盘后调用热生效（见 `apply-changes.md`）；热生效失败时再提示用户重启。

## CLI

```bash
python scripts/paths.py --pet-id san-hua --print
python scripts/paths.py --pet-id my-cat --account-id 250006921 --ensure-user
```

