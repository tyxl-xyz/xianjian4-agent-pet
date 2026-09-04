import cv2
import numpy as np
from PIL import Image

def load_orig(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def detect_watermark_text(rgb):
    """
    精准检测"豆包AI生成"半透明白色水印：
    - 白色文字：RGB 各通道都偏高且接近（饱和低）
    - 在绿色背景上（hue 30-120），文字使饱和度骤降
    - 形成小文字块
    """
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H, S, V = hsv[:, :, 0].astype(int), hsv[:, :, 1].astype(int), hsv[:, :, 2].astype(int)
    # 白色文字特征：V 高、S 低、H 落在背景绿附近(因叠加在绿幕上) 或 任意
    # 半透明白叠加绿 → 饱和度下降明显，但保持一定绿色倾向
    white_text = (V > 130) & (S < 60)
    # 必须在绿幕背景区域（排除角色白色服饰：角色服饰在画面中部，水印在边带）
    h, w = rgb.shape[:2]
    border = 0.22
    bh, bw = int(h*border), int(w*border)
    border_mask = np.zeros((h, w), bool)
    border_mask[:bh, :] = True
    border_mask[-bh:, :] = True
    border_mask[:, :bw] = True
    border_mask[:, -bw:] = True
    wm = white_text & border_mask
    wm = wm.astype(np.uint8) * 255
    # 文字块形状过滤：小面积连通块
    n, labels, stats, _ = cv2.connectedComponentsWithStats(wm, connectivity=8)
    keep = np.zeros_like(wm)
    for i in range(1, n):
        a = stats[i, cv2.CC_STAT_AREA]
        # 文字笔画块面积适中；太长太宽的排除
        bw_ = stats[i, cv2.CC_STAT_WIDTH]; bh_ = stats[i, cv2.CC_STAT_HEIGHT]
        if 20 <= a <= 2000 and bh_ <= 60 and bw_ <= 200:
            keep[labels == i] = 255
    return keep

# 测试：梦璃 f48（之前残留最大的帧）
rgb = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 48)
wm = detect_watermark_text(rgb)
vis = rgb.copy()
vis[wm > 0] = [255, 0, 0]
Image.fromarray(vis).save("lingxi-pet/_qa3/mengli_wm_text_detect_f48.png")
print(f"梦璃 f48: 检测水印块px={int((wm>0).sum())}")

# 紫英 f48
rgb = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 48)
wm = detect_watermark_text(rgb)
vis = rgb.copy()
vis[wm > 0] = [255, 0, 0]
Image.fromarray(vis).save("lingxi-pet/_qa3/ziying_wm_text_detect_f48.png")
print(f"紫英 f48: 检测水印块px={int((wm>0).sum())}")
