from PIL import Image
import os

build = "lingxi-pet/_build"
os.makedirs("lingxi-pet/_qa", exist_ok=True)
for aid in ["idle", "working", "happy", "fail"]:
    gif_path = os.path.join(build, aid, f"{aid}.gif")
    gif = Image.open(gif_path)
    n = gif.n_frames
    # 抽第0, 中, 末帧
    for idx in [0, n//2, n-1]:
        gif.seek(idx)
        gif.convert("RGBA").save(f"lingxi-pet/_qa/{aid}_f{idx}.png")
    print(f"{aid}: frames={n}, size={gif.size}")
