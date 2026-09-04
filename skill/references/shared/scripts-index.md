# 脚本索引（优先执行，勿手写等价逻辑）

在 skill 根目录下执行（或把路径换成绝对路径）。


| 脚本 | 用途 |
|------|------|
| `scripts/paths.py` | 解析 petRoot / accountId / official / user / runtime / patch / soul |
| `scripts/merge_patch.py` | 安全合并写入 `user/pet.patch.json`；**校验/规范 behaviors 为 string 映射** |
| `scripts/enrich_pet_patch.py` | **创建宠默认三态组合主路径**：`*_play` + behaviors + 左右跑时 `run_*_play` + `wander` baseMode + effect 等；`--check` 收尾门禁 |
| `scripts/locomotion_config.py` | 左右跑素材 → `run_left_play`/`run_right_play` + directional `baseModes.wander`（由 enrich 调用） |
| `scripts/behaviors_format.py` | behaviors 契约：coerce `{actions:[…]}`→string、补 `walking`/`dragging_*` |
| `scripts/write_soul_patch.py` | 写入 `user/soul.json`；缺契约字段拒绝落盘；`--check` 收尾门禁 |
| `scripts/fill_base_mode_bubbles.py` | 按人设/语义补齐 `baseModes.*.bubble`（含整池恰好一条 `{mailboxUnread}`） |
| `scripts/import_frames.py` | 上传帧/GIF/单行条 → webp + merge actions |
| `scripts/import_atlas_sheet.py` | 多行合图：单文件 + `row` 写入 patch（禁止默认拆行） |
| `scripts/preflight_asset_bundle.py` | 上传 ZIP/目录安全解包、真实元数据、原始上传文件的 `view_image` 审核清单（不生成审核预览） |
| `scripts/chroma_key_to_gif.py` | 绿幕视频 → 透明 GIF；背景 mask **dilate** 切绿边（`--dilate`，默认 2） |
| `scripts/encode_action_webm.py` | **已抠像** GIF → **默认** stacked-alpha `.mov`（`videoHevc`）；可选 `--also-webm` 产 VP9+alpha `.webm`；`--webm-only` 仅 WebM；**manifest 写真实 frames+fps**；透明/matte 校验；`--ensure-only` |
| `scripts/analyze_reference.py` | **Phase 0 HARD**：幕布铺满 → 构图边距 → **色键冲突**（点缀色 vs 幕布 hue）；`adopt` 前必跑 |
| `scripts/suggest_screen_color.py` | 按 `--hues` 或 `--from-image` 在绿/青/蓝/品红色板中建议幕布与 `--hue` |
| `scripts/screen_palette.py` | 色板常量 + 环距 / 冲突检测（供上两者共用） |
| `scripts/make_spritesheet.py` | GIF → lossless webp 合图（仅 ffmpeg 安装失败或用户明确回退）；未传 `--prefix` 时用 `-o` 目录名 |
| `scripts/build_pet_json.py` | manifest / `.mov` / `.webm` → actions 写入 patch；拷贝 mov/webm/webp/png |
| `scripts/action_readiness.py` | actions 配置门禁 |
| `scripts/inspect_frames.py` | 帧/GIF 视觉门禁 → `qa/review.json`（草案） |
| `scripts/make_contact_sheet.py` | 总览 contact sheet（草案） |
| `scripts/prepare_pet_run.py` | 会话工作区批次脚手架 + `jobs.json`（草案） |
| `scripts/generate_sequences.py` | **仅 P2** 随机追加 sequences；不可代替 enrich；未 enrich 时默认拒绝 |
| `scripts/apply_user_changes.py` | 落盘后 MCP 热重载 |

信箱两层填写（未读气泡 / 离家 `mailboxPresentation`，默认不写 `mailboxImage`）→ [mailbox-presentation.md](mailbox-presentation.md)（文档约定，无专用脚本）。

验收量规：[qa-rubric.md](qa-rubric.md) · 交付契约：[delivery-contract.md](delivery-contract.md)

Python 依赖：`Pillow`、`numpy`；视频抠图另需 `opencv-python`、`moviepy`。  
透明视频编码：PATH → imageio-ffmpeg / 缓存静态包 → pip → 最后 brew；**输入须透明 GIF**。默认产出 stacked `.mov`；透明校验失败不是「该换 brew ffmpeg」。
