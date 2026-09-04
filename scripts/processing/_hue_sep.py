import cv2
import numpy as np

def load_orig(video, fi=60):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def hue_stats(region):
    hsv = cv2.cvtColor(region, cv2.COLOR_RGB2HSV)
    h = hsv[:, :, 0].astype(float)
    s = hsv[:, :, 1].astype(float)
    return h.mean(), h.min(), h.max(), s.mean(), s.min(), s.max()

# 梦璃：竖琴 vs 背景
orig = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4")
print("梦璃 背景(TL 20x20):", hue_stats(orig[0:20, 0:20]))
print("梦璃 竖琴(650:950,280:440):", hue_stats(orig[650:950, 280:440]))
print("梦璃 竖琴中心(700:800,300:380):", hue_stats(orig[700:800, 300:380]))

# 紫英：剑 vs 背景
orig = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4")
print("\n紫英 背景(TL 20x20):", hue_stats(orig[0:20, 0:20]))
print("紫英 剑(550:950,250:500):", hue_stats(orig[550:950, 250:500]))
print("紫英 剑中心(600:750,300:420):", hue_stats(orig[600:750, 300:420]))

# 天河：弓 vs 背景（弓是红色应该没问题，验证）
orig = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4")
print("\n天河 背景(TL 20x20):", hue_stats(orig[0:20, 0:20]))
print("天河 弓区域(500:900,300:420):", hue_stats(orig[500:900, 300:420]))

# 菱纱：衣物红色 vs 背景
orig = load_orig("C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4")
print("\n菱纱 背景(TL 20x20):", hue_stats(orig[0:20, 0:20]))
print("菱纱 衣物红色(400:700,350:400):", hue_stats(orig[400:700, 350:400]))
