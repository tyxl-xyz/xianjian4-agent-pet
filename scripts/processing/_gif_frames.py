from PIL import Image
gif = Image.open("lingxi-pet/_build/idle/idle_test.gif")
n = gif.n_frames
print("frames:", n)
for idx in [0, n//2, n-1]:
    gif.seek(idx)
    f = gif.convert("RGBA")
    f.save(f"lingxi-pet/_qa/idle_test_{idx}.png")
    print(f"saved {idx}")
