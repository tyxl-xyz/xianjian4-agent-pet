import cv2
import numpy as np

def detect_watermark(path, label):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"=== {label} === total={total}frames")
    for i in range(total):
        ret, frame = cap.read()
        if not ret:
            break
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        green = cv2.inRange(hsv, (30, 30, 60), (95, 255, 255))
        regions = {
            "TL": rgb[0:int(h*0.2), 0:int(w*0.2)],
            "TR": rgb[0:int(h*0.2), int(w*0.8):w],
            "BL": rgb[int(h*0.8):h, 0:int(w*0.2)],
            "BR": rgb[int(h*0.8):h, int(w*0.8):w],
        }
        found = []
        for rname, reg in regions.items():
            hsv_r = cv2.cvtColor(reg, cv2.COLOR_RGB2HSV)
            gmask = cv2.inRange(hsv_r, (30, 30, 60), (95, 255, 255))
            nong = ~gmask
            dark = reg.mean(axis=2) < 160
            cand = nong & dark
            cnt = int(cand.sum())
            if cnt > 200:
                ys, xs = np.where(cand)
                found.append(f"{rname}({cnt}px)")
        if found:
            print(f"  f{i}: watermark {' '.join(found)}")
    cap.release()

for name in ["待机", "工作", "开心", "难过"]:
    detect_watermark(f"C:/Users/13544/Desktop/新建文件夹/{name}.mp4", name)
