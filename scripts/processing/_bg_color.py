import cv2
import numpy as np

def bg(path, label):
    cap = cv2.VideoCapture(path)
    ret, frame = cap.read()
    cap.release()
    h, w = frame.shape[:2]
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    corners = {
        "tl": rgb[10,10], "tr": rgb[10,w-10],
        "bl": rgb[h-10,10], "br": rgb[h-10,w-10],
        "center_top": rgb[5, w//2], "center_left": rgb[h//2, 10],
        "mid_bg": rgb[h//2, w-15], "top_mid2": rgb[30,w//2],
    }
    print(f"=== {label} ===")
    for name, px in corners.items():
        r,g,b = px
        hsv = cv2.cvtColor(np.uint8([[px]]), cv2.COLOR_RGB2HSV)[0][0]
        print(f"  {name}: RGB=({r},{g},{b}) HSV=({hsv[0]},{hsv[1]},{hsv[2]})")

for name in ["待机","工作","开心","难过"]:
    bg(f"C:/Users/13544/Desktop/新建文件夹/{name}.mp4", name)
