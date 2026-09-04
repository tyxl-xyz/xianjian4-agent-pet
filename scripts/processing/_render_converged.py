import cv2
import numpy as np
from PIL import Image
import sys
sys.path.insert(0, r"D:\TOOL\20260831-14-46-47-666\lingxi-pet")
from _narrow_test import VIDEO_PARAMS, chroma_key_remove_narrow
from _lowpat_test import remove_isolated_disconnected

def center_square(rgba):
    src_h = rgba.shape[0]
    scale = 720 / src_h
    new_w = max(1, int(round(rgba.shape[1] * scale)))
    resized = cv2.resize(rgba, (new_w, 720), interpolation=cv2.INTER_LANCZOS4)
    canvas = np.zeros((720, 720, 4), dtype=np.uint8)
    x0 = (720 - new_w) // 2
    canvas[:, x0:x0 + new_w] = resized
    return canvas

base = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/"
fnames = {
    "mengli": "梦璃_20260831_165425_cdf44267.mp4",
    "ziying": "紫英_20260831_165425_a6fd9aa4.mp4",
    "lingsha": "菱纱_20260831_165425_80bb1170.mp4",
    "tianhe": "天河_20260831_165425_222d101e.mp4",
}
for label in ["mengli", "ziying", "lingsha", "tianhe"]:
    cap = cv2.VideoCapture(base + fnames[label])
    frames = []
    for i in range(0, 121, 30):
        cap.set(cv2.CAP_PROP_POS_FRAMES, i)
        ret, frame = cap.read()
        if ret: frames.append(frame)
    cap.release()
    hr0, hr1 = VIDEO_PARAMS[label]
    for frame in frames:
        alpha = chroma_key_remove_narrow(frame, (hr0, hr1))
        alpha, _ = remove_isolated_disconnected(alpha)
        rgba = cv2.cvtColor(frame, cv2.COLOR_BGR2RGBA)
        rgba[:, :, 3] = alpha
        canvas = center_square(rgba)
        Image.fromarray(canvas, mode="RGBA").save(f"lingxi-pet/_qa3/{label}_converged.png")
        break
    print(f"{label}: saved")
