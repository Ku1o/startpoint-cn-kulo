"""Deterministic layout search using the existing no-rotation MaxRects packer."""
import math
import hashlib
import json
from pathlib import Path
from PIL import Image
from wf_battle_atlas_repack import Rect, pack_regions


def layout(images):
    regions=[Rect(i,0,im.width,im.height) for i,im in enumerate(images)]
    minimum=max(im.width+2 for im in images)
    area=sum((im.width+2)*(im.height+2) for im in images)
    maximum=min(4094,max(minimum,2*math.ceil(math.sqrt(area))))
    widths=sorted(set(range(minimum,maximum+1))|{x for x in (128,256,512,768,1024) if minimum<=x<=4094})
    best=None;attempts=0
    for mode in ('height','area'):
        for width in widths:
            minheight=max(max(im.height+2 for im in images),math.ceil(area/width))
            heights=sorted({4094,*[min(4094,math.ceil(minheight*x)) for x in (1,1.05,1.125,1.25,1.5,2)]})
            for height in heights:
                attempts+=1
                try:
                    placed,size=pack_regions(regions,target_width=width,max_height=height,gap=2,sort_mode=mode)
                except ValueError:
                    continue
                if max(size)>4094:continue
                score=((size[0]+2)*(size[1]+2),max(size),size[0],size[1],mode,width,height)
                if best is None or score<best[0]:best=(score,placed,size,mode,width)
    if best is None:raise ValueError('No MaxRects layout fits4094 bounds')
    score,placed,size,mode,width=best
    # Existing packer uses leading2/no trailing gutter. Shift cells by-1 to retain
    # compiler's one-pixel leading/trailing gutters, same2 total separation.
    locations={i:(placed[region].x-1,placed[region].y-1) for i,region in enumerate(regions)}
    rectangles=[(locations[i][0]-1,locations[i][1]-1,im.width+2,im.height+2) for i,im in enumerate(images)]
    for i,(x,y,w,h) in enumerate(rectangles):
        assert x>=0 and y>=0 and x+w<=size[0] and y+h<=size[1]
        for xx,yy,ww,hh in rectangles[i+1:]:assert x+w<=xx or xx+ww<=x or y+h<=yy or yy+hh<=y
    return size,locations,{'method':'existing deterministic MaxRects short-side, no rotation','sortMode':mode,'searchWidth':width,'attempts':attempts,'sheetSize':list(size),'paddedSheetPixels':score[0],'padding':'Eachcell1pixel all sides,2 total between adjacent contents; plus native sheet margin2 total','gutterRectanglesNonoverlapping':True}


def pack_images(images):
    here=Path(__file__).resolve().parent
    frozen=here/'packing-layout-v7.json'
    if frozen.exists():
        plan=json.loads(frozen.read_text('utf8'))
        assert hashlib.sha256((here.parent/'art/composition-spec.json').read_bytes()).hexdigest()==plan['specSha256'],'Frozen layout spec mismatch'
        signature=[list(im.size) for im in images]
        matches=[g for g in plan['groups'] if g['imageSizes']==signature]
        assert len(matches)==1,'No unique frozen shape/order layout'
        row=matches[0]
        assert [hashlib.sha256(im.tobytes()).hexdigest() for im in images]==row['imageRgbaSha256'],'Frozen layout source pixel drift'
        size=tuple(row['sheetSize']);locations={int(i):tuple(xy) for i,xy in row['locations'].items()}
    else:
        size,locations,proof=layout(images)
    sheet=Image.new('RGBA',size)
    for i,im in enumerate(images):sheet.paste(im,locations[i])
    for i,im in enumerate(images):
        x,y=locations[i];assert sheet.crop((x,y,x+im.width,y+im.height)).tobytes()==im.tobytes()
    return sheet,locations
