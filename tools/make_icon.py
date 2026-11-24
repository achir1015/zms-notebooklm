"""產生程式圖示：assets/icon.png（1024）、packaging/icon.ico、assets/icon.ico。

資料助秘系列的深藍到青綠圓角方塊；左後方是一本筆記本（NotebookLM 的來源），
前方是一張簡報投影片（標題列＋長條圖＋重點），兩者之間有 MCP 連接線；右上角金幣寫「MCP」，左下角「資料助秘」標籤。
"""
import os

from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
S = 1024


def lerp(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def shadow(img, shape_fn, blur=18, offset=(10, 20), alpha=100):
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shape_fn(ImageDraw.Draw(sh), offset, (0, 0, 0, alpha))
    return Image.alpha_composite(img, sh.filter(ImageFilter.GaussianBlur(blur)))


def font(size, weight="Black"):
    try:
        f = ImageFont.truetype(os.path.join(HERE, "assets", "fonts", "NotoSansTC-VF.ttf"), size)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        return f
    except Exception:
        return ImageFont.load_default()


def main():
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    grad = Image.new("RGBA", (S, S))
    gd = ImageDraw.Draw(grad)
    c1, c2 = (15, 60, 110), (14, 150, 120)
    for y in range(S):
        gd.line([(0, y), (S, y)], fill=lerp(c1, c2, y / S) + (255,))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([40, 40, S - 40, S - 40], radius=220, fill=255)
    img.paste(grad, (0, 0), mask)
    gloss = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(gloss).ellipse([-200, -520, S + 200, 420], fill=(255, 255, 255, 34))
    img = Image.alpha_composite(img, Image.composite(gloss, Image.new("RGBA", (S, S)), mask))

    # 筆記本（左後方，略為傾斜的感覺用偏移表現）
    nb = [150, 250, 520, 760]
    img = shadow(img, lambda d, o, f: d.rounded_rectangle([nb[0] + o[0], nb[1] + o[1], nb[2] + o[0], nb[3] + o[1]],
                                                          radius=36, fill=f), alpha=110)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(nb, radius=36, fill=(250, 246, 235, 255))
    d.rounded_rectangle([nb[0], nb[1], nb[0] + 70, nb[3]], radius=36, fill=(224, 165, 38, 255))
    d.rectangle([nb[0] + 40, nb[1], nb[0] + 70, nb[3]], fill=(224, 165, 38, 255))
    for i in range(6):                                  # 線圈
        y = nb[1] + 60 + i * 80
        d.ellipse([nb[0] + 52, y, nb[0] + 88, y + 36], outline=(120, 90, 30, 255), width=8)
    for i in range(7):                                  # 文字線
        y = nb[1] + 90 + i * 62
        d.rounded_rectangle([nb[0] + 120, y, nb[2] - 50 - (i % 3) * 40, y + 16], radius=8, fill=(180, 190, 205, 255))

    # 簡報投影片（右前方）
    sl = [400, 390, 880, 750]
    img = shadow(img, lambda d, o, f: d.rounded_rectangle([sl[0] + o[0], sl[1] + o[1], sl[2] + o[0], sl[3] + o[1]],
                                                          radius=30, fill=f), alpha=130, blur=22)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(sl, radius=30, fill=(255, 255, 255, 255))
    d.rounded_rectangle([sl[0], sl[1], sl[2], sl[1] + 90], radius=30, fill=(30, 77, 140, 255))
    d.rectangle([sl[0], sl[1] + 60, sl[2], sl[1] + 90], fill=(30, 77, 140, 255))
    d.rectangle([sl[0], sl[1] + 90, sl[2], sl[1] + 100], fill=(224, 165, 38, 255))
    d.rounded_rectangle([sl[0] + 36, sl[1] + 30, sl[0] + 300, sl[1] + 58], radius=14, fill=(255, 255, 255, 230))
    # 長條圖
    bars = [(0.45, (15, 162, 148)), (0.7, (30, 77, 140)), (0.95, (224, 165, 38)), (0.6, (194, 24, 91))]
    bx, base = sl[0] + 50, sl[3] - 50
    for i, (h, col) in enumerate(bars):
        x = bx + i * 62
        d.rounded_rectangle([x, base - int(190 * h), x + 44, base], radius=8, fill=col + (255,))
    # 重點條列
    for i in range(3):
        y = sl[1] + 150 + i * 62
        d.ellipse([sl[0] + 300, y, sl[0] + 326, y + 26], fill=(15, 162, 148, 255))
        d.rounded_rectangle([sl[0] + 340, y + 4, sl[2] - 40 - i * 30, y + 22], radius=9, fill=(190, 200, 215, 255))

    # MCP 連接線（筆記本 → 簡報）
    d.line([(nb[2] - 20, 330), (610, 300), (690, 380)], fill=(255, 255, 255, 220), width=12, joint="curve")
    for x, y in ((nb[2] - 20, 330), (690, 380)):
        d.ellipse([x - 20, y - 20, x + 20, y + 20], fill=(255, 255, 255, 255), outline=(14, 150, 120, 255), width=8)

    # 右上角金幣「MCP」
    cx, cy, rr = 810, 215, 130
    img = shadow(img, lambda d, o, f: d.ellipse([cx - rr + o[0], cy - rr + o[1], cx + rr + o[0], cy + rr + o[1]],
                                                fill=f), blur=16, offset=(10, 18), alpha=110)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], fill=(240, 180, 40, 255), outline=(255, 226, 140, 255), width=14)
    d.ellipse([cx - rr + 28, cy - rr + 28, cx + rr - 28, cy + rr - 28], outline=(201, 138, 20, 255), width=6)
    d.text((cx, cy - 6), "MCP", font=font(84), fill=(20, 50, 92, 255), anchor="mm")
    # 左下角「資料助秘」小標籤
    d.rounded_rectangle([110, 860, 440, 940], radius=40, fill=(255, 255, 255, 235))
    d.text((275, 898), "資料助秘", font=font(52), fill=(30, 77, 140, 255), anchor="mm")
    img.putalpha(Image.composite(img.getchannel("A"), Image.new("L", (S, S), 0), mask))
    out = os.path.join(HERE, "assets", "icon.png")
    img.save(out)
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    for p in (os.path.join(HERE, "packaging", "icon.ico"), os.path.join(HERE, "assets", "icon.ico")):
        img.save(p, sizes=sizes)
    print("ok", out)


if __name__ == "__main__":
    main()
