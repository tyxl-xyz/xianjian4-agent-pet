import cv2
import numpy as np

def load_orig(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def bg_hue_range(video, label):
    """统计所有帧四角背景的色相分布"""
    cap = cv2.VideoCapture(video)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    hues = []
    for i in range(0, total, 10):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if not ret: break
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        # 四角 12% 区域（远离角色）
        corners = np.vstack([
            hsv[:int(h*0.12), :int(w*0.12)].reshape(-1,3),
            hsv[:int(h*0.12), int(w*0.88):].reshape(-1,3),
            hsv[int(h*0.88):, :int(w*0.12)].reshape(-1,3),
            hsv[int(h*0.88):, int(w*0.88):].reshape(-1,3),
        ])
        H = corners[:,0]; S = corners[:,1]; V = corners[:,2]
        # 只取明显的绿色背景像素（S>30, V>60）
        sel = (S > 30) & (V > 60)
        hues.extend(H[sel].tolist())
    cap.release()
    hues = np.array(hues)
    # 色相是环形，但要集中在绿色区
    h_center = (hues >= 30) & (hues <= 120)
    sel_h = hues[h_center]
    print(f"{label}: 绿色背景像素 {len(sel_h)}, H范围 [{sel_h.min():.0f}-{sel_h.max():.0f}], "
          f"均值 {sel_h.mean():.0f}±{sel_h.std():.0f}")
    # 分位数
    for p in [1, 5, 50, 95, 99]:
        print(f"    P{p}: {np.percentile(sel_h, p):.0f}")

for label, video in [
    ("梦璃", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("紫英", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
    ("菱纱", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4"),
    ("天河", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"),
]:
    bg_hue_range(video, label)
