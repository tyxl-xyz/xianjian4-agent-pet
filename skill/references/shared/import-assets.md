# 上传素材导入（帧 / GIF / webp）

当用户已有序列帧或**单行动作**合图时，跳过视频生成，用 `import_frames.py`。用户上传来源必须先完成 [asset-safety-review.md](asset-safety-review.md)，并把通过的 `--review-manifest` 传给导入脚本。`--source` 只能填写该清单 `stagedDir` 下已经按**原始格式**审核过的文件或目录，不能改用外部副本。

**若是一张图上多行动作：** 不要用本文件拆行；改走 [multi-row-atlas.md](multi-row-atlas.md) + `import_atlas_sheet.py`。

## 支持输入


| 来源                   | 说明                                                            |
| -------------------- | ------------------------------------------------------------- |
| 帧目录                  | 按文件名排序的 png/webp/jpg                                          |
| 单 GIF                | 透明或将被当序列读入                                                    |
| 单 webp 动画（至少两帧且有画面变化） | 逐帧展开后再合图                                             |
| 已有**单行** spritesheet | 配合 `--frames` `--columns` `--row` 或 sidecar `*_manifest.json` |
| 多行大图合图               | → [multi-row-atlas.md](multi-row-atlas.md)，禁止默认逐行裁切           |


## CLI

```bash
# 帧目录 → atomic happy
python scripts/import_frames.py \
  --pet-id my-cat \
  --action-id happy \
  --kind atomic \
  --source "{workspace}/_asset-review/staged/happy_frames" \
  --review-manifest "{workspace}/_asset-review/review-manifest.json" \
  --fps 24 --frame-size 720 \
  --display-name "开心"

# 三段 GIF → 往返 transition + atomic
python scripts/import_frames.py \
  --pet-id my-cat \
  --batch-roundtrip happy \
  --home idle \
  --sources "{workspace}/_asset-review/staged/idle_to_happy.gif,{workspace}/_asset-review/staged/happy.gif,{workspace}/_asset-review/staged/happy_to_idle.gif" \
  --review-manifest "{workspace}/_asset-review/review-manifest.json"

# 已有合图 webp（idle：省略 --fps → fps = columns//2，此处 61→30）
python scripts/import_frames.py \
  --pet-id my-cat \
  --action-id idle \
  --kind atomic \
  --source "{workspace}/_asset-review/staged/idle.webp" \
  --spritesheet-ready \
  --review-manifest "{workspace}/_asset-review/review-manifest.json" \
  --frames 61 --columns 61 \
  --play-range 2,60
```

## idle fps（HARD，仅 import-assets）

| 条件 | 行为 |
|------|------|
| `--action-id idle` 且**未**传 `--fps` | 落盘 `fps = max(1, floor(columns / 2))` |
| 显式 `--fps N` | 以 N 为准 |
| 非 idle 且未传 `--fps` | 默认 `24` |
| `--batch-roundtrip` | 默认 `24`（不受 idle 公式影响） |

## 规则

- **仅**把审核通过后构建的 spritesheet（或用户提供的现成 png/webp 合图，保留原扩展名）与更新后的 `pet.patch.json` 写入 `{userDir}/`
- 上传的源 GIF / 帧目录留在原路径或 `{workspace}/`，**禁止**复制进 `user/`
- `spritesheet` 字段只写**文件名**（如 `happy.webp`），不写绝对路径
- `official-overlay` 只追加/覆盖用户自定义 action id，勿无故覆盖官方同名 id（用户明确要求覆写除外）
- transition 命名惯例：`{from}_to_{to}`
- **禁止**对 idle 无脑填 `--fps 24`（除非用户明确要求）
- **禁止**把单张 PNG/JPEG/WebP、单帧 GIF/WebP 或各帧完全一致的素材导入为 action；它们只能作为 `reference`。`import_frames.py` 会拒绝这类输入。

## 与视频路径混用

可先 `import_frames` 导入 idle，再对其他态走绿幕批次；每次 merge 进同一 `{patch}`。  
导入后同样调用热生效（见 [../scenarios/apply-hot-reload.md](../scenarios/apply-hot-reload.md)）。场景入口：[../scenarios/import-assets.md](../scenarios/import-assets.md)。
