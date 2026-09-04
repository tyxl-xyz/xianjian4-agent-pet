import cv2
import numpy as np
from PIL import Image

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

# 修复版处理
def chroma_key_remove_narrow(img_bgr, hue_range=(79, 90), sat_min=30, val_min=60, dilate_iter=1):
    rgbx = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    hsv = cv2.cvtColor(rgbx, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, (hue_range[0], sat_min, val_min), (hue_range[1], 255, 255))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.dilate(mask, kernel, iterations=dilate_iter)
    mask_f = mask.astype(np.float32) / 255.0
    mask_f = cv2.GaussianBlur(mask_f, (5, 5), 0)
    alpha = ((1.0 - mask_f) * 255).clip(0, 255).astype(np.uint8)
    return alpha

def remove_isolated_disconnected_v2(alpha, min_area=40, max_area=6000, fg_thresh=40, border=0.16):
    h, w = alpha.shape
    fg = (alpha > fg_thresh).astype(np.uint8)
    close_k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    fg = cv2.morphologyEx(fg, cv2.MORPH_CLOSE, close_k)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(fg, connectivity=8)
    if n <= 1:
        return alpha, 0
    areas = stats[1:, cv2.CC_STAT_AREA]
    main_id = np.argmax(areas) + 1
    max_area_main = areas[np.argmax(areas)]
    bh, bw = int(h * border), int(w * border)
    remove = np.zeros((h, w), np.uint8)
    removed_cnt = 0
    for i in range(1, n):
        if i == main_id:
            continue
        a = stats[i, cv2.CC_STAT_AREA]
        if a < min_area or a > max_area or a > max_area_main * 0.5:
            continue
        x_c, y_c = centroids[i]
        near_edge = (x_c < bw or x_c > w - bw) or (y_c < bh or y_c > h - bh)
        if not near_edge:
            continue
        blob = (labels == i)
        remove[blob] = 1
        removed_cnt += int(a)
    alpha[remove > 0] = 0
    return alpha, removed_cnt

alpha = chroma_key_remove_narrow(frame)
alpha2, _ = remove_isolated_disconnected_v2(alpha)

# 躯干区域（原图坐标）
regions = {
    "躯干上(250-450, 400-550)": (250, 400, 450, 550),
    "躯干中(250-450, 500-650)": (250, 500, 450, 650),
    "腰腹(200-500, 600-750)": (200, 600, 500, 750),
    "左侧衣摆(150-350, 700-900)": (150, 700, 350, 900),
}
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
for name, (x0, y0, x1, y1) in regions.items():
    # 源中非背景像素（角色内容）
    green = ((H >= 76) & (H <= 93) & (S > 25) & (V > 60))
    src_content = int((~green)[y0:y1, x0:x1].sum())
    # 处理后保留
    kept = int((alpha2 > 128)[y0:y1, x0:x1].sum())
    print(f"{name}: 源内容px={src_content}, 处理后保留={kept}, 保留率={kept/max(src_content,1)*100:.0f}%")

# 保存躯干区域对比
scale = 720 / 1280
x0g = int(157 + 150*scale); x1g = int(157 + 500*scale)
y0g = int(400*scale); y1g = int(900*scale)
arr = np.array(Image.open("lingxi-pet/_qa5/tianhe_fixed_f60.png").convert("RGBA"))
Image.fromarray(arr[y0g:y1g, x0g:x1g]).save("lingxi-pet/_qa5/tianhe_torso_proc.png")
print("saved proc torso")
