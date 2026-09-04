import cv2
import numpy as np

mov = "C:/Users/13544/AppData/Roaming/desktop-pet/accounts/230581940/pets/han-ling-sha/user/idle.mov"
cap = cv2.VideoCapture(mov)
print("frames:", int(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
print("fps:", cap.get(cv2.CAP_PROP_FPS))
print("w:", int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), "h:", int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)))
# 抽第0帧
ret, frame = cap.read()
if ret:
    h, w = frame.shape[:2]
    # stacked: 上半是RGB下半是matte
    top = frame[:h//2]
    cv2.imwrite("lingxi-pet/_build/test/existing_idle_top.png", top)
cap.release()
print("saved top half")
