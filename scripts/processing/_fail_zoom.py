from PIL import Image
import numpy as np

gif = Image.open("lingxi-pet/_build/fail/fail.gif")
gif.seek(60)
arr = np.array(gif.convert("RGBA"))
h, w = arr.shape[:2]
# 右下角 30% 区域放大
crop = arr[int(h*0.7):, int(w*0.7):]
Image.fromarray(crop).save("lingxi-pet/_qa2/fail_f60_br.png")
# 也检查这个区域 alpha 分布
a = crop[:, :, 3]
print("BR区域 alpha>16 像素:", int((a > 16).sum()), "| alpha>128:", int((a > 128).sum()))
# 全图 alpha>16 但 <200 的像素位置（半透明残留）
semi = (arr[:, :, 3] > 16) & (arr[:, :, 3] < 200)
ys, xs = np.where(semi)
print("半透明像素总数:", semi.sum())
if len(xs):
    print("  位置范围 x:", xs.min(), "-", xs.max(), "y:", ys.min(), "-", ys.max())
