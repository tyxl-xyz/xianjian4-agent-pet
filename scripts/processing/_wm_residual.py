import numpy as np
from PIL import Image

def detect_residual_watermark(gif_path, label):
    gif = Image.open(gif_path)
    n = gif.n_frames
    # 在四角区域检测透明区里的非全透明小文字块（水印残留是 alpha 半透明的浅色块）
    hits = 0
    total_px = 0
    for idx in range(0, n, 4):
        gif.seek(idx)
        arr = np.array(gif.convert("RGBA"))
        h, w = arr.shape[:2]
        # 角落区域（22%）
        regions = {
            "TL": (0, 0, int(h*0.22), int(w*0.22)),
            "TR": (0, int(w*0.78), int(h*0.22), w),
            "BL": (int(h*0.78), 0, h, int(w*0.22)),
            "BR": (int(h*0.78), int(w*0.78), h, w),
        }
        for rn, (y0, x0, y1, x1) in regions.items():
            reg = arr[y0:y1, x0:x1]
            a = reg[:, :, 3]
            # 半透明像素（alpha 16-200），接近透明但仍有内容 => 疑似水印残留
            semi = ((a > 16) & (a < 200)).sum()
            total_px += int(semi)
            if semi > 80:
                hits += 1
    print(f"{label}: 采样帧={n//4+1}, 四角半透明残留累计像素={total_px}, 命中帧/区域计数={hits}")

for aid in ["idle", "working", "happy", "fail"]:
    detect_residual_watermark(f"lingxi-pet/_build/{aid}/{aid}.gif", aid)
