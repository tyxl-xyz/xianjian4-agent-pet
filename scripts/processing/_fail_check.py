from PIL import Image
import numpy as np

# 检查 fail GIF 各帧角色边界
gif = Image.open("lingxi-pet/_build/fail/fail.gif")
print("frames:", gif.n_frames, "size:", gif.size)
for idx in [0, 20, 40, 60, 80, 100, 120]:
    gif.seek(idx)
    arr = np.array(gif.convert("RGBA"))
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha > 128)
    if len(xs) == 0:
        print(f"  f{idx}: empty")
        continue
    h, w = alpha.shape
    print(f"  f{idx}: bbox x={xs.min()}-{xs.max()} y={ys.min()}-{ys.max()} "
          f"top={ys.min()/h*100:.0f}% bottom={(h-1-ys.max())/h*100:.0f}% "
          f"left={xs.min()/w*100:.0f}% right={(w-1-xs.max())/w*100:.0f}%")
