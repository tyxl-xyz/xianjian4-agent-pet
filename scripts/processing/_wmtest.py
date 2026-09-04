import cv2
import numpy as np

# 读取一帧确认水印位置，测试 inpaint 去水印
cap = cv2.VideoCapture("C:/Users/13544/Desktop/新建文件夹/待机.mp4")
for fi in [40, 80, 120]:
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    if not ret:
        continue
    cv2.imwrite(f"lingxi-pet/_build/test/wm_f{fi}_orig.png", frame)
cap.release()
print("saved")

# 逐帧做水印检测+inpaint 的效果评估（测一帧看水印文字区域）
frame = cv2.imread("lingxi-pet/_build/test/wm_f40_orig.png")
h, w = frame.shape[:2]
rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
green = cv2.inRange(hsv, (30, 30, 60), (95, 255, 255))
# 水印文字：非绿 + 与背景差异明显。背景绿带渐变，用局部中值差分
reg = rgb[int(h*0.75):, int(w*0.7):]
gh, gw = reg.shape[:2]
reg_hsv = cv2.cvtColor(reg, cv2.COLOR_RGB2HSV)
reg_green = cv2.inRange(reg_hsv, (30, 30, 60), (95, 255, 255))
gray = reg.mean(axis=2)
bg = np.median(gray[reg_green > 0])
diff = np.abs(gray - bg)
text_mask = (diff > 28) & (reg_green == 0)
text_mask = text_mask.astype(np.uint8) * 255
text_mask = cv2.morphologyEx(text_mask, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
cnt = int((text_mask > 0).sum())
print(f"BR region: green_px={(reg_green>0).sum()}, text_px={cnt}")
cv2.imwrite("lingxi-pet/_build/test/br_textmask.png", text_mask)
# inpaint 测试（用整帧 mask，需构建全帧 mask）
full_mask = np.zeros((h, w), np.uint8)
full_mask[int(h*0.75):, int(w*0.7):] = text_mask
inpaint = cv2.inpaint(frame, full_mask, 3, cv2.INPAINT_TELEA)
cv2.imwrite("lingxi-pet/_build/test/wm_f40_inpaint.png", inpaint)
print("inpaint done")
