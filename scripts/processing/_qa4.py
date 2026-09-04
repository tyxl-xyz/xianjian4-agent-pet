from PIL import Image
import os
os.makedirs("lingxi-pet/_qa3", exist_ok=True)
for aid in ["mengli", "ziying", "lingsha", "tianhe"]:
    gif = Image.open(f"lingxi-pet/_build2/{aid}/{aid}.gif")
    n = gif.n_frames
    for idx in [n//2, n-1]:
        gif.seek(idx)
        gif.convert("RGBA").save(f"lingxi-pet/_qa3/{aid}_f{idx}.png")
    print(f"{aid}: frames={n}")
