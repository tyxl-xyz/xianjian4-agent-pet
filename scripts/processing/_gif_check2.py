from PIL import Image
import os

build = "lingxi-pet/_build"
os.makedirs("lingxi-pet/_qa2", exist_ok=True)
for aid in ["idle", "working", "happy", "fail"]:
    gif_path = os.path.join(build, aid, f"{aid}.gif")
    gif = Image.open(gif_path)
    n = gif.n_frames
    gif.seek(n // 2)
    gif.convert("RGBA").save(f"lingxi-pet/_qa2/{aid}_mid.png")
    print(f"{aid}: frames={n}, size={gif.size}")
