import cv2
import numpy as np
from PIL import Image
import sys
sys.path.insert(0, r"D:\TOOL\20260831-14-46-47-666\lingxi-pet")
from _disconn_test import chroma_key_remove, remove_isolated_disconnected

def center_square(rgba):
    src_h = rgba.shape[0]
    scale = 720 / src_h
    new_w = max(1, int(round(rgba.shape[1] * scale)))
    resized = cv2.resize(rgba, (new_w, 720), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((720, 720, 4), dtype=np.uint8)
    x0 = (720 - new_w) // 2
    canvas[:, x0:x0 + new_w] = resized
    return canvas

jobs = [
    ("mengli", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4", 60),
    ("ziying", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4", 60),
    ("lingsha", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/菱纱_20260831_165425_80bb1170.mp4", 30),
    ("tianhe", "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4", 90),
]
for label, video, fi in jobs:
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    alpha = chroma_key_remove(frame)
    alpha, _ = remove_isolated_disconnected(alpha)
    rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
    rgba[:, :, 3] = alpha
    canvas = center_square(rgba)
    Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa3/{label}_disconn.png")
    print(f"{label} f{fi}: done")
