import cv2
import numpy as np

def bg(path, label):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    # 采样第0,60,120帧四角背景
    for fi in [0, 60, 120]:
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret: continue
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pts = {
            "TL": rgb[8, 8], "TR": rgb[8, w-8],
            "BL": rgb[h-8, 8], "BR": rgb[h-8, w-8],
            "CT": rgb[2, w//2], "CL": rgb[h//2, 2],
            "CR": rgb[h//2, w-2], "CB": rgb[h-2, w//2],
        }
        out = []
        for name, px in pts.items():
            hsv = cv2.cvtColor(np.uint8([[px]]), cv2.COLOR_RGB2HSV)[0][0]
            out.append(f"{name}=H{hsv[0]}S{hsv[1]}V{hsv[2]}")
        print(f"{label} f{fi}: " + " ".join(out))
    cap.release()
    print()

for name, path in [
    ("梦璃", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"),
    ("紫英", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"),
    ("菱纱", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4"),
    ("天河", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"),
]:
    bg(path, name)
