"""Normalize the user-approved wide preview after explicit local-edit consent.

Only removes the neutral paper background, demattes the contour and performs
one proportional fit onto the native canvas. No glyph/ornament redrawing.
Requires Pillow and numpy (available in the bundled workspace Python).
"""
import argparse
import hashlib
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter

PREVIEW_SHA='91af3cc31e0cccdcfc50d3c11f660f5c1700c0aeaf1c2d1520da4beba63bbf29'


def prepare(source,output,work):
    raw=source.read_bytes()
    assert hashlib.sha256(raw).hexdigest()==PREVIEW_SHA
    im=Image.open(source).convert('RGB')
    rgb=np.asarray(im).astype(np.float32)
    neutral=(np.min(rgb,axis=2)>210)&(np.ptp(rgb,axis=2)<15)
    # The chosen title's letter faces are warm gold/cream. Neutral paper is
    # removed both outside and inside the knot loops; warm highlights remain.
    background=neutral
    mask=(~background).astype(np.uint8)*255
    inner=np.array(Image.fromarray(mask).filter(ImageFilter.MinFilter(7)))>0
    border=(mask>0)&~inner
    alpha=(mask/255).astype(np.float32)
    # The selected drawing has a dark outer stroke. For neutral antialias
    # pixels touching the paper, undo white matting rather than keep a halo.
    dematte=border&(np.ptp(rgb,axis=2)<32)&(np.min(rgb,axis=2)>25)
    alpha[dematte]=1-np.min(rgb,axis=2)[dematte]/255
    rgb[dematte]=np.clip((rgb[dematte]-255*(1-alpha[dematte,None]))/alpha[dematte,None],0,255)
    rgb[background]=0
    rgba=Image.fromarray(np.dstack([np.rint(rgb).astype(np.uint8),np.rint(alpha*255).astype(np.uint8)]))
    bbox=rgba.getchannel('A').getbbox()
    assert bbox and bbox[2]-bbox[0]>2000
    crop=rgba.crop(bbox)
    width=314
    height=round(crop.height*width/crop.width)
    assert height<=48 and height>=40
    # Resize in premultiplied alpha to avoid transparent-color fringes.
    resized=crop.convert('RGBa').resize((width,height),Image.Resampling.LANCZOS).convert('RGBA')
    final=Image.new('RGBA',(320,50),(0,0,0,0))
    xy=((320-width)//2,(50-height)//2)
    final.paste(resized,xy)
    assert final.getchannel('A').getextrema()==(0,255)
    visible=final.getchannel('A').getbbox()
    assert 310<=visible[2]-visible[0]<=316
    output.parent.mkdir(parents=True,exist_ok=True);work.mkdir(parents=True,exist_ok=True)
    final.save(output,optimize=True)
    rgba.save(work/'extracted-full-resolution.png',optimize=True)
    backgrounds=[('dark',(30,32,40)),('light',(244,243,240)),('blue',(78,106,139)),('pink',(189,144,163))]
    qa=Image.new('RGB',(640,400),(248,247,244))
    for i,(name,color) in enumerate(backgrounds):
        tile=Image.new('RGBA',(320,50),color+(255,));tile.alpha_composite(final)
        qa.paste(tile.convert('RGB').resize((640,100),Image.Resampling.NEAREST),(0,i*100))
    qa.save(work/'edge-check-2x.png')
    facts=dict(source=str(source),source_sha256=PREVIEW_SHA,method='user-authorized local background extraction and proportional fit',
        extracted_bbox=bbox,source_subject_size=crop.size,output_size=final.size,output_mode=final.mode,
        alpha_range=final.getchannel('A').getextrema(),visible_bbox=visible,fit_size=[width,height],
        scale_x=width/crop.width,scale_y=height/crop.height,background_method='neutral-paper-key plus contour dematting',
        glyphs_and_ornaments_redrawn=False,sha256=hashlib.sha256(output.read_bytes()).hexdigest())
    (work/'artwork-receipt.json').write_text(json.dumps(facts,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(facts,ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True);ap.add_argument('--output',type=Path,required=True);ap.add_argument('--work',type=Path,required=True)
    args=ap.parse_args();prepare(args.source,args.output,args.work)
