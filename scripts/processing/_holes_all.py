import cv2
import numpy as np
from PIL import Image
import sys
sys.path.insert(0, r"D:\TOOL\20260831-14-46-47-666\lingxi-pet")
from _fix_leg_test import chroma_key_remove_narrow, remove_isolated_disconnected_v2

base = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/"
fnames = {
    "mengli": ("梦璃_20260831_165425_cdf44267.mp4", (55, 74)),
    "ziying": ("紫英_20260831_165425_a6fd9aa4.mp4", (62, 74)),
    "lingsha": ("菱纱_20260831_165425_80bb1170.mp4", (57, 68)),
    "tianhe": ("天河_20260831_165425_222d101e.mp4", (79, 90)),
}

for label, (fname, hue) in fnames.items():
    cap = cv2.VideoCapture(base + fname)
    frames = []
    for i in range(121):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if ret:
            frames.append(frame)
    cap.release()
    max_hole = 0
    max_hole_frame = -1
    for i in range(121):
        rgb = cv2.cvtColor(frames[i], cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        H, S, V = hsv[:, :, 0], hsv[:, :, 1], hsv[:, :, 2]
        green = ((H >= hue[0]-3) & (H <= hue[1]+3) & (S > 25) & (V > 60))
        char_region = ~green
        alpha = chroma_key_remove_narrow(frames[i], hue)
        alpha2, _ = remove_isolated_disconnected_v2(alpha)
        holes = int((char_region & (alpha2 <= 16)).sum())
        if holes > max_hole:
            max_hole = holes
            max_hole_frame = i
    print(f"{label}: 最大内部误删px={max_hole} (帧{max_hole_frame})")
