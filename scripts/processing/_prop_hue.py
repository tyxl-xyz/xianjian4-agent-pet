import cv2
import numpy as np

def load_orig(video, fi=60):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def bg_hue(rgb):
    """用四角背景估计背景H范围"""
    h, w = rgb.shape[:2]
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    corners = np.vstack([hsv[0:15,0:15].reshape(-1,3), hsv[0:15,w-15:w].reshape(-1,3),
                         hsv[h-15:h,0:15].reshape(-1,3), hsv[h-15:h,w-15:w].reshape(-1,3)])
    hh = corners[:,0]; ss = corners[:,1]; vv = corners[:,2]
    return (hh.min(), hh.max(), ss.min(), ss.max(), vv.min(), vv.max())

def analyze_prop(video, label, y0,y1,x0,x1):
    rgb = load_orig(video)
    reg = rgb[y0:y1, x0:x1]
    hsv = cv2.cvtColor(reg, cv2.COLOR_RGB2HSV)
    H = hsv[:,:,0].astype(np.int32)
    S = hsv[:,:,1].astype(np.int32)
    V = hsv[:,:,2].astype(np.int32)
    # 用均值聚类近似：对每个像素，算它与背景色的距离
    bg_min_h, bg_max_h = bg_hue(rgb)[0], bg_hue(rgb)[1]
    # 背景色带: 角度距离
    h_dist = np.minimum(np.abs(H-bg_min_h), 180-np.abs(H-bg_min_h))
    bg_mask = h_dist <= 25  # 接近背景
    fg = ~bg_mask
    fgpx = hsv[fg]
    print(f"{label}: 道具区总px={reg.shape[0]*reg.shape[1]}, 背景px={(bg_mask).sum()}, 前景px={fg.sum()}")
    if fg.sum() > 0:
        # 前景色相分布
        hist = np.bincount(fgpx[:,0], minlength=180)
        top = np.argsort(hist)[::-1][:8]
        print(f"  前景色相Top8: {[(int(t), int(hist[t])) for t in top if hist[t]>0]}")
        print(f"  前景色相均值={fgpx[:,0].mean():.0f}, S均值={fgpx[:,1].mean():.0f}, V均值={fgpx[:,2].mean():.0f}")
    print(f"  背景H范围: {bg_min_h}-{bg_max_h}")

analyze_prop("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", "梦璃竖琴", 700, 900, 300, 400)
analyze_prop("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", "紫英剑", 600, 850, 300, 420)
analyze_prop("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4", "天河弓", 550, 900, 280, 420)
