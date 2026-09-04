import cv2
import numpy as np
from PIL import Image

def load_orig_frame(video, fi):
    cap = cv2.VideoCapture(video)
    cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
    ret, frame = cap.read()
    cap.release()
    return cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

def load_proc_frame(gif_path, fi):
    gif = Image.open(gif_path)
    gif.seek(fi)
    return gif.convert("RGBA")

# 1. 水印残留检查：梦璃/紫英
for aid, vname in [("mengli", "梦璃"), ("ziying", "紫英")]:
    video = f"C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/{vname}_20260831_165425_cdf44267.mp4" if aid == "mengli" else f"C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/{vname}_20260831_165425_a6fd9aa4.mp4"
    gif_path = f"lingxi-pet/_build2/{aid}/{aid}.gif"
    # 找原始带水印帧
    cap = cv2.VideoCapture(video)
    for fi in range(121):
        cap.set(cv2.CAP_PROP_POS_FRAMES, fi)
        ret, frame = cap.read()
        if not ret: break
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        # 右下角检查深色文字
        reg = rgb[int(h*0.75):, int(w*0.7):]
        gray = reg.mean(axis=2)
        bg = np.median(gray)
        diff = np.abs(gray - bg)
        dark_cnt = int((diff > 40).sum())
        if dark_cnt > 300:
            cap.release()
            print(f"{aid}: 原始帧{fi}右下角疑似水印 dark_cnt={dark_cnt}")
            # 对应处理帧的同一位置
            proc = load_proc_frame(gif_path, fi)
            arr = np.array(proc)
            ph, pw = arr.shape[:2]
            pr = arr[int(ph*0.75):, int(pw*0.7):]
            pa = pr[:, :, 3]
            semi = int(((pa > 16) & (pa < 200)).sum())
            opaque = int((pa > 128).sum())
            print(f"   处理帧{fi}右下角: alpha半透明={semi}, alpha不透明={opaque}")
            break
    else:
        print(f"{aid}: 原始未见明显水印")
    cap.release()

# 2. 道具误抠分析：梦璃竖琴颜色 vs 背景绿
print("\n=== 梦璃竖琴 vs 背景色相 ===")
video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/梦璃_20260831_165425_cdf44267.mp4"
orig = load_orig_frame(video, 60)
hsv = cv2.cvtColor(orig, cv2.COLOR_RGB2HSV)
# 竖琴在角色怀中，大约 x 280-440, y 650-950
harp = orig[650:950, 280:440]
harp_hsv = cv2.cvtColor(harp, cv2.COLOR_RGB2HSV)
green_harp = cv2.inRange(harp_hsv, (30, 30, 60), (95, 255, 255))
total = harp_hsv.shape[0] * harp_hsv.shape[1]
print(f"  竖琴区域: 总像素{total}, 判为绿幕的像素{int(green_harp.sum())} ({green_harp.sum()/total*100:.0f}%)")
# 竖琴平均色
if green_harp.sum() > 0:
    px = harp[green_harp > 0]
    print(f"  竖琴被判绿像素 RGB均值={px.reshape(-1,3).mean(axis=0).round(1)}")

# 3. 紫英剑颜色分析
print("\n=== 紫英剑 vs 背景色相 ===")
video = "C:/Users/13544/AppData/Roaming/WPS 灵犀/paste/紫英_20260831_165425_a6fd9aa4.mp4"
orig = load_orig_frame(video, 60)
hsv = cv2.cvtColor(orig, cv2.COLOR_RGB2HSV)
# 剑在手中，大约 x 250-500, y 550-950
sword = orig[550:950, 250:500]
sword_hsv = cv2.cvtColor(sword, cv2.COLOR_RGB2HSV)
green_sw = cv2.inRange(sword_hsv, (30, 30, 60), (95, 255, 255))
total = sword_hsv.shape[0] * sword_hsv.shape[1]
print(f"  剑区域: 总像素{total}, 判为绿幕的像素{int(green_sw.sum())} ({green_sw.sum()/total*100:.0f}%)")
if green_sw.sum() > 0:
    px = sword[green_sw > 0]
    print(f"  剑被判绿像素 RGB均值={px.reshape(-1,3).mean(axis=0).round(1)}")
