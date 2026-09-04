import cv2
import numpy as np

def analyze_watermark(path, label):
    cap = cv2.VideoCapture(path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    print(f"=== {label} ===")
    wm_frames = []
    for i in range(total):
        ret, frame = cap.read()
        if not ret:
            break
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        corners = {
            "TL": (0, 0, int(h*0.22), int(w*0.22)),
            "TR": (0, int(w*0.78), int(h*0.22), w),
            "BL": (int(h*0.78), 0, h, int(w*0.22)),
            "BR": (int(h*0.78), int(w*0.78), h, w),
        }
        found = []
        for rn, (y0, x0, y1, x1) in corners.items():
            reg = rgb[y0:y1, x0:x1]
            gh, gw = reg.shape[:2]
            if gh < 10 or gw < 10:
                continue
            gray = reg.mean(axis=2)
            bg = np.median(gray)
            diff = np.abs(gray - bg)
            mask = diff > 30
            mask = cv2.morphologyEx(mask.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
            cnt = int(mask.sum())
            if 60 < cnt < 4000:
                found.append(rn)
        if found:
            wm_frames.append((i, found))
    if not wm_frames:
        print("  无显著水印")
        return
    ranges = []
    start = wm_frames[0][0]
    prev = wm_frames[0][0]
    pos = set(wm_frames[0][1])
    for i, (fi, ps) in enumerate(wm_frames[1:], 1):
        if fi - prev <= 2 and set(ps) == pos:
            prev = fi
        else:
            ranges.append((start, prev, sorted(pos)))
            start = fi
            prev = fi
            pos = set(ps)
    ranges.append((start, prev, sorted(pos)))
    for s, e, ps in ranges:
        print(f"  帧{s}-{e} ({s/24:.1f}s-{e/24:.1f}s): {ps}")

for name in ["待机", "工作", "开心", "难过"]:
    analyze_watermark(f"C:/Users/13544/Desktop/新建文件夹/{name}.mp4", name)
