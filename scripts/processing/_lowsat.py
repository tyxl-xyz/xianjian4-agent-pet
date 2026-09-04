import cv2
import numpy as np
from PIL import Image

def load_orig(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def detect_wm_by_low_sat(rgb):
    """水印=半透明白色文字叠加在绿幕上→使该处饱和度显著低于周边绿幕"""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    H = hsv[:, :, 0].astype(int)
    S = hsv[:, :, 1].astype(int)
    V = hsv[:, :, 2].astype(int)
    # 绿幕范围（宽）
    green = cv2.inRange(hsv, (30, 20, 60), (95, 255, 255))
    # 在绿幕区域内，S 显著低的像素 = 白色文字
    # 绿幕本体 S 通常 80-120；文字处 S 掉到 20-60
    wm = (green > 0) & (S < 55) & (V > 120)
    # 排除角色：角色服饰饱和度低的白色部分？角色在画面中部，水印在角落——用位置限制更稳
    return wm

# 测试梦璃 f60
for label, video, fi in [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60),
]:
    rgb = load_orig(video, fi)
    h, w = rgb.shape[:2]
    wm = detect_wm_by_low_sat(rgb)
    ys, xs = np.where(wm)
    print(f"{label} f{fi}: 低饱和水印候选={wm.sum()} px")
    if len(xs):
        print(f"  位置 x:{xs.min()}-{xs.max()} y:{ys.min()}-{ys.max()}")
        # 按角落/边缘分区
        for rn, (x0,x1,y0,y1) in {
            "右下": (int(w*0.6), w, int(h*0.7), h),
            "左下": (0, int(w*0.4), int(h*0.7), h),
            "右上": (int(w*0.6), w, 0, int(h*0.3)),
            "左上": (0, int(w*0.4), 0, int(h*0.3)),
        }.items():
            cnt = int(wm[y0:y1, x0:x1].sum())
            if cnt > 100:
                print(f"    {rn}: {cnt}px")
    # 可视化
    vis = rgb.copy()
    vis[wm > 0] = [255, 0, 0]
    Image.fromarray(vis).save(f"lingxi-pet/_qa3/{label}_lowsat_wm.png")
    print("saved")
