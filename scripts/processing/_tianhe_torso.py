import cv2
import numpy as np
from PIL import Image
from collections import Counter

video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/天河_20260831_165425_222d101e.mp4"
cap = cv2.VideoCapture(video)
cap.set(cv2.CAP_PROP_POS_FRAMES, 60)
ret, frame = cap.read()
cap.release()
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

# 天河角色bbox: 约 (58,220)-(720,1108)。上衣躯干区域
# 上身: x 250-450, y 350-600（胸部到腰腹）
torso = rgb[350:600, 250:450]
hsv = cv2.cvtColor(torso, cv2.COLOR_RGB2HSV)
H, S, V = hsv[:,:,0], hsv[:,:,1], hsv[:,:,2]
# 与背景(79-90)同色相的像素占比
same_as_bg = ((H>=76)&(H<=93)&(S>25)&(V>60))
print(f"上衣躯干区域: 总px={torso.shape[0]*torso.shape[1]}, 与背景同色相px={int(same_as_bg.sum())} ({same_as_bg.mean()*100:.0f}%)")
# 上衣主色
px = torso.reshape(-1,3)
q = (px//32).astype(int)
cnt = Counter([tuple(c) for c in q])
print("上衣躯干Top6颜色:")
for k,c in cnt.most_common(6):
    v = (np.array(k)*32+16).astype(int)
    hh = cv2.cvtColor(np.uint8([[v]]), cv2.COLOR_RGB2HSV)[0][0]
    print(f"  RGB{tuple(v)} H{hh[0]} S{hh[1]} V{hh[2]}: {c}")
Image.fromarray(torso).save("lingxi-pet/_qa5/tianhe_torso_src.png")
print("saved torso src")
