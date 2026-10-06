"""领主武装强化页的横幅(1000x184)与页头(1440x556)：照诅咒武器那套构图——左标题、右侧武器图标阵列。"""
import os
from PIL import Image, ImageDraw, ImageFilter, ImageFont

F = 'C:/Windows/Fonts/msyhbd.ttc'
FL = 'C:/Windows/Fonts/msyh.ttc'
HERE = os.path.dirname(os.path.abspath(__file__))
ICONS = os.path.join(HERE, 'icons', 'weapons')
TITLE, SUB = '领主武装·觉醒', 'LORD ARMAMENT · AWAKENING'
GLOW = (230, 170, 60)


def background(w, h):
    top, bottom = (58, 34, 92), (12, 8, 22)
    bg = Image.new('RGBA', (w, h))
    d = ImageDraw.Draw(bg)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)) + (255,))
    stripes = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    sd = ImageDraw.Draw(stripes)
    for x0 in range(-h, w, w // 4):
        sd.polygon([(x0, h), (x0 + h, 0), (x0 + h + w // 14, 0), (x0 + w // 14, h)], fill=(255, 210, 120, 18))
    bg.alpha_composite(stripes)
    return bg


def glow_text(base, xy, text, size, font=F, anchor='lm', stroke=5):
    f = ImageFont.truetype(font, size)
    layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).text(xy, text, font=f, fill=GLOW + (255,), anchor=anchor, stroke_width=stroke * 2, stroke_fill=GLOW + (255,))
    base.alpha_composite(layer.filter(ImageFilter.GaussianBlur(stroke)))
    ImageDraw.Draw(base).text(xy, text, font=f, fill=(255, 250, 235), anchor=anchor, stroke_width=stroke, stroke_fill=(40, 20, 10))


def icon_grid(base, ids, x0, y0, cols, cell, scale):
    sparkle = ImageDraw.Draw(base)
    for i, wid in enumerate(ids):
        im = Image.open(os.path.join(ICONS, f'{wid}.png')).convert('RGBA')
        im = im.resize((im.width * scale, im.height * scale), Image.NEAREST)
        x = x0 + (i % cols) * cell + (cell - im.width) // 2
        y = y0 + (i // cols) * cell + (cell - im.height) // 2
        halo = Image.new('RGBA', base.size, (0, 0, 0, 0))
        halo.paste((255, 200, 90, 160), (x, y), im.split()[3])
        base.alpha_composite(halo.filter(ImageFilter.GaussianBlur(scale)))
        base.alpha_composite(im, (x, y))
        s = scale
        sparkle.rectangle([x - 2 * s, y + s, x - s, y + 2 * s], fill=(255, 220, 140, 255))


def main():
    ids = sorted(f[:-4] for f in os.listdir(ICONS) if f.endswith('.png') and '_' not in f)
    firsts = [i for i in ids if i.endswith('1')]  # 每个 boss 第一把，共 27
    hdr = background(1440, 556)
    # 游戏只显示页头中间约 x∈[200,1240]（诅咒页实测两侧被裁），内容全放安全区内
    glow_text(hdr, (235, 255), TITLE, 76, stroke=5)
    glow_text(hdr, (239, 325), SUB, 24, font=FL, stroke=2)
    icon_grid(hdr, firsts[:18], 800, 150, 6, 72, 3)
    hdr.save(os.path.join(HERE, 'enh_header.png'))
    ban = background(1000, 184)
    glow_text(ban, (36, 82), TITLE, 54, stroke=4)
    glow_text(ban, (40, 132), SUB, 18, font=FL, stroke=1)
    icon_grid(ban, firsts[:18], 520, 22, 9, 52, 2)
    ban.save(os.path.join(HERE, 'enh_banner.png'))
    print('ok')


if __name__ == '__main__':
    main()
