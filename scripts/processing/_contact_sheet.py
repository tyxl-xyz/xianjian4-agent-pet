from PIL import Image, ImageDraw

build = "lingxi-pet/_build"
labels = [("idle", "待机"), ("working", "工作"), ("happy", "开心"), ("fail", "难过")]
cells = []
for aid, _ in labels:
    gif = Image.open(f"{build}/{aid}/{aid}.gif")
    gif.seek(gif.n_frames // 2)
    cells.append(gif.convert("RGBA").resize((360, 360), Image.LANCZOS))

W = 360 * 4 + 60
H = 360 + 70
sheet = Image.new("RGBA", (W, H), (255, 255, 255, 255))
draw = ImageDraw.Draw(sheet)
for i, (cell, (aid, cn)) in enumerate(zip(cells, labels)):
    x = 15 + i * 370
    sheet.paste(cell, (x, 15), cell)
    draw.text((x, 385), f"{cn} ({aid})", fill=(40, 40, 40))
sheet.convert("RGB").save("lingxi-pet/_qa2/han-ling-sha_4states_preview.png")
print("saved preview")
