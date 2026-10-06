from PIL import Image, ImageDraw, ImageFont, ImageFilter
import sys
F='C:/Windows/Fonts/msyhbd.ttc'
BOSSES={'queen_water':('青之女王','QUEEN OF BLUE',(40, 120, 230),'thumb_queen_water.png'),
        'queen_fire':('赤之女王','QUEEN OF CRIMSON',(220, 70, 40),'thumb_queen_fire.png'),
        'queen_wind':('碧之女王','QUEEN OF JADE',(50, 170, 80),'thumb_queen_wind.png'),
        'queen_light':('皓之女王','QUEEN OF RADIANCE',(200, 170, 60),'thumb_queen_light.png'),
        'queen_thunder':('金之女王','QUEEN OF GOLD',(220, 180, 40),'thumb_queen_thunder.png'),
        'queen_dark':('墨之女王','QUEEN OF INK',(120, 50, 190),'thumb_queen_dark.png'),
        'dragon_thunder':('伊尔考普斯','DISCARDED DRAGON',(220, 180, 40),'thumb_dragon_thunder.png'),
        'dragon_fire':('伊萨巴迪卡','DISCARDED DRAGON',(220, 70, 40),'thumb_dragon_fire.png'),
        'dragon_water':('伊劳德雷斯','DISCARDED DRAGON',(40, 120, 230),'thumb_dragon_water.png'),
        'dragon_wind':('伊尔格拉乌','DISCARDED DRAGON',(50, 170, 80),'thumb_dragon_wind.png'),
        'dragon_light':('伊尔梅塔雷','DISCARDED DRAGON',(200, 170, 60),'thumb_dragon_light.png'),
        'dragon_dark':('伊尔昂斯拉','DISCARDED DRAGON',(120, 50, 190),'thumb_dragon_dark.png'),
        'beast_fire':('火魔奥尔塔尼亚','SPIRIT BEAST',(220, 70, 40),'thumb_beast_fire.png'),
        'beast_water':('水鬼斯拉姆冈','SPIRIT BEAST',(40, 120, 230),'thumb_beast_water.png'),
        'beast_thunder':('雷龟普罗格雷奥','SPIRIT BEAST',(220, 180, 40),'thumb_beast_thunder.png'),
        'beast_wind':('风师亚特摩西亚','SPIRIT BEAST',(50, 170, 80),'thumb_beast_wind.png'),
        'beast_light':('光蛛杜梅欧','SPIRIT BEAST',(200, 170, 60),'thumb_beast_light.png'),
        'beast_dark':('暗凤希亚特利欧','SPIRIT BEAST',(120, 50, 190),'thumb_beast_dark.png'),
        'org':('丑王奥格','THE UGLY KING ORG',(150,40,200),'thumb_org.png'),
        'epu':('歼灭者','THE EPURATION',(70,110,220),'thumb_epu.png'),
        'maou2':('魔王','THE DEMON KING',(200,40,60),'thumb_maou2.png'),
        'high_epu':('上位歼灭者','HIGH EPURATION',(110,60,200),'thumb_high_epu.png'),
        'benzaiten':('形似弁天的魔物','DISTORTED WATER DEITY',(220,180,40),'thumb_benzaiten.png'),
        'variant_epu':('异形歼灭者','VARIANT EPURATION',(40,120,230),'thumb_variant_epu.png'),
        'star_devourer':('吞噬星辰之物','STAR DEVOURER',(120,50,190),'thumb_star_devourer.png'),
        'cursed_blade':('咒剑','THE CURSED BLADE',(150,30,90),'thumb_cursed_blade.png'),
        'origin_dragon':('终始之龙','DRAGON OF ORIGIN AND END',(90,60,210),'thumb_origin_dragon.png')}
def glow_text(base, xy, text, size, fill, glow, anchor='mm', stroke=6):
    f=ImageFont.truetype(F,size)
    layer=Image.new('RGBA',base.size,(0,0,0,0)); d=ImageDraw.Draw(layer)
    d.text(xy,text,font=f,fill=glow+(255,),anchor=anchor,stroke_width=stroke*2,stroke_fill=glow+(255,))
    layer=layer.filter(ImageFilter.GaussianBlur(stroke))
    base.alpha_composite(layer)
    d=ImageDraw.Draw(base)
    d.text(xy,text,font=f,fill=fill,anchor=anchor,stroke_width=stroke,stroke_fill=glow+(255,))
for key,(name,eng,col,thumb) in BOSSES.items():
    t=Image.open(thumb).convert('RGBA')
    # list banner 1000x184: blurred thumb background + crisp thumb on right + title left
    W,H=1000,184
    bg=t.resize((W, int(W*t.height/t.width)),Image.NEAREST).crop((0,140,W,140+H)).filter(ImageFilter.GaussianBlur(6))
    dark=Image.new('RGBA',(W,H),(10,10,20,150)); bg.alpha_composite(dark)
    core=t.crop((8,8,t.width-8,t.height-8))
    art=core.resize((core.width*2,core.height*2),Image.NEAREST)
    top=(art.height-H)//2; art=art.crop((0,top,art.width,top+H))
    ramp=Image.linear_gradient('L').rotate(90).resize((art.width,H))
    ramp=Image.eval(ramp,lambda v:min(255,v*3))
    bg.paste(art,(W-art.width,0),ramp)
    glow_text(bg,(330,52),'共同决战',30,(255,255,255),col,stroke=3)
    glow_text(bg,(330,110),name,min(74,int(560/max(1,len(name)))),(255,255,255),col,stroke=6)
    glow_text(bg,(330,158),eng,18,(255,255,255),col,stroke=2)
    bg.convert('RGB').save(f'banner_{key}.png')
    # logo 1440x1262 transparent, title centred near top like the mech one
    L=Image.new('RGBA',(1440,1262),(0,0,0,0))
    glow_text(L,(720,205),'共同决战',44,(255,255,255),col,stroke=4)
    glow_text(L,(720,300),name,min(130,int(1200/max(1,len(name)))),(255,255,255),col,stroke=10)
    glow_text(L,(720,375),eng,30,(255,255,255),col,stroke=3)
    L.save(f'logo_{key}.png')
    # bossbattle banner 377x199
    bb=t.resize((377,int(377*t.height/t.width)),Image.NEAREST).crop((0,40,377,239))
    glow_text(bb,(188,165),name,min(40,int(340/max(1,len(name)))),(255,255,255),col,stroke=4)
    bb.convert('RGB').save(f'bb_{key}.png')
print('ok')


# 领主战页头 1440x556：照官方 boss_battle_<x>.png 构图——属性色斜条 + 场景虚化底 + 居中 boss + 发光标题「- 领主战 -」。
MAIN = ['org', 'epu', 'maou2', 'high_epu', 'benzaiten', 'variant_epu', 'star_devourer', 'cursed_blade', 'origin_dragon']


def header(key):
    name, eng, col, thumb = BOSSES[key]
    t = Image.open(thumb).convert('RGBA')
    W, H = 1440, 556
    bg = t.resize((W, int(W * t.height / t.width)), Image.NEAREST)
    top = (bg.height - H) // 2
    bg = bg.crop((0, top, W, top + H)).filter(ImageFilter.GaussianBlur(10))
    bg.alpha_composite(Image.new('RGBA', (W, H), (8, 8, 16, 170)))
    stripes = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(stripes)
    light = tuple(min(255, c + 70) for c in col)
    d.polygon([(0, 0), (W * 0.62, 0), (0, H * 0.42)], fill=col + (235,))
    d.polygon([(0, H * 0.46), (W * 0.66, 0), (W * 0.70, 0), (0, H * 0.52)], fill=light + (200,))
    d.polygon([(W, H), (W * 0.30, H), (W, H * 0.58)], fill=col + (235,))
    d.polygon([(W, H * 0.52), (W * 0.26, H), (W * 0.22, H), (W, H * 0.46)], fill=light + (200,))
    for i in range(14):  # 官方右上角的像素方块
        s = 44 + (i % 3) * 18
        x = W - 70 - (i * 53) % 330 - s
        y = 20 + (i * 71) % 260
        d.rectangle([x, y, x + s, y + s], fill=col + (150 + (i % 4) * 25,))
    bg.alpha_composite(stripes)
    core = t.crop((10, 6, t.width - 10, t.height - 6))
    art = core.resize((core.width * 2, core.height * 2), Image.NEAREST)
    mask = Image.new('L', art.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, art.width, art.height], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(28))
    bg.paste(art, ((W - art.width) // 2, (H - art.height) // 2 - 40), mask)
    glow_text(bg, (720, 345), name, min(100, int(1000 / max(1, len(name)))), (255, 255, 255), col, stroke=8)
    glow_text(bg, (720, 420), '-  领主战  -', 34, (255, 255, 255), col, stroke=3)
    bg.save(f'hdr_{key}.png')


if __name__ == '__main__' and len(sys.argv) > 1 and sys.argv[1] == 'header':
    for k in MAIN:
        header(k)
    print('headers ok')
