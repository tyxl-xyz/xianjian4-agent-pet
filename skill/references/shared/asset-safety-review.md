# 上传素材安全与元数据门禁

> 视觉审核对象仅限图片文件；ZIP 中的视频、音频、文本、压缩包等非图片不得进入 `reviewPaths`，也不得调用 `view_image`。

用户上传的 ZIP、素材目录、GIF、WebP、PNG 或帧序列必须先经过本门禁。门禁分为两个互不替代的部分：

1. **权威元数据预检**：脚本读取真实文件，计算 SHA-256、尺寸和动画帧数；这些值是后续 JSON 的唯一来源。
2. **视觉安全审核**：Agent 对清单的所有 `reviewPaths` 调用 `view_image`，判断是否包含黄暴等不允许内容。每个审核路径都必须是安全解包后的**原始上传文件**：PNG 审 PNG、GIF 审 GIF、WebP 审 WebP；禁止用缩略图、截图、转码副本、抽帧或 contact sheet 代替。原格式无法由 `view_image` 可靠呈现时，判 `reject`，不能转换格式绕过。只有工具实际呈现该原始文件并给出可用的视觉结论才可判 `pass`。

`view_image` 只负责视觉结论，禁止用它口头报告的尺寸、列数、行数或帧数填充 JSON。

本清单的 `assets` / `reviewPaths` 只包含图片扩展名（`asset_review.IMAGE_EXTS`）。视频、音频、文本、压缩包等非图片只记录在 `nonVisualFiles` 中，不调用 `view_image`，也不能作为本导入路径的图片 action。

## 拒答终止规则（最高优先级 HARD）

`view_image` 对任一原始审核路径拒答、报错、返回空/无关结果、未实际呈现图片或无法判断时，立即执行：

```bash
python scripts/preflight_asset_bundle.py \
  --manifest "{workspace}/_asset-review/review-manifest.json" \
  --reject
```

然后**结束本次生成桌宠流程**。对用户只回复：**「素材审核失败，无法使用当前素材创建桌宠。请重新上传素材。」** 禁止重试 `view_image`，禁止把原文件转成 PNG 或任何其它格式再审，禁止抽帧、生成 contact sheet、导入、写入 `user/` 或生成 `pet.patch.json`。禁止输出「不安全」、具体审核结论、素材文件名、内部命令或「重新安全审查」。没有人工确认、用户声明安全或历史派生文件的例外；新上传一份原始素材才是新的预检任务。

## 强制流程

```text
preflight_asset_bundle.py
  → 安全解包到 workspace/_asset-review/staged
  → 生成 review-manifest.json
  → 读取所有图片的真实 metadata
  → 每个素材只列出 staged/ 下的原始上传文件作为审核路径
  → Agent 对每个 assets[*].reviewPaths 调用 view_image
  → 上一步仅适用于图片 assets；不得将 nonVisualFiles 送给 view_image
  → --approve（仅每张图片都有可用视觉结论、全部安全且 metadataStatus=pass）
  → import_frames.py / import_atlas_sheet.py
  → 再次校验哈希与元数据
  → 才能写入 user/ 和生成最终 pet.patch.json
```

预检与导入示例：

```bash
python scripts/preflight_asset_bundle.py \
  --input /path/to/upload.zip \
  --out-dir "{workspace}/_asset-review"

# Agent 必须逐个 view_image 清单中的原始上传文件后才允许：
python scripts/preflight_asset_bundle.py \
  --manifest "{workspace}/_asset-review/review-manifest.json" \
  --approve

python scripts/import_atlas_sheet.py \
  --pet-id <id> \
  --sheet "{workspace}/_asset-review/staged/spritesheet.webp" \
  --preset codex \
  --review-manifest "{workspace}/_asset-review/review-manifest.json"
```

## 失败即停止

- `decision` 不是 `pass`、任一素材不是 `pass`、`metadataStatus` 不是 `pass`：禁止导入。
- **`view_image` 拒答或不可用也是拒绝，不是通过：** 返回“无法提供相应解答”等拒答、无关文字、工具报错、空结果、未实际呈现图片、或模型无法判断时，Agent 必须执行 `--reject`；绝不可执行 `--approve`，也不可自行假定素材安全。
- 原格式不支持、`view_image` 无法可靠呈现、哈希变化：进入 `reject`，禁止落盘；不得通过预览生成、转码或抽帧规避。
- `reviewPaths` 只允许图片扩展名；非图片只留在 `nonVisualFiles`，不做视觉审核。
- ZIP 路径穿越、软链接、嵌套压缩包、超大条目、异常压缩比：拒绝解包。
- Codex 图集仍由导入脚本根据实际图片尺寸匹配预设；不要接受模型口头提供的网格数字。
- 通用合图无法从像素可靠推断逻辑帧数时，必须提供 sidecar manifest 或人工确认；不得猜测。

审核清单和 staged 素材只存在 workspace。源 ZIP 不覆盖、不移动；审核通过后导入脚本会再次计算哈希，防止审核后替换文件。
