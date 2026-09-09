"""Lossless visible-frame compaction, preserving every CN name and animation endpoint.

AMF atlases use physical w/h and clockwise-packed r; fx/fy position the
unrotated crop within fw/fh (SpriteSheetHandler -> Starling SubTexture).
Only fully transparent pixels may be trimmed. No resampling or frame deletion.
"""
from __future__ import annotations
import copy, hashlib, json, math
import prepare_content as p
import wf_battle_atlas_repack as a
from PIL import Image

GEOMETRY = {'x','y','w','h','fx','fy','fw','fh'}

def crop_frame(im, f):
    x,y,w,h=(f[k] for k in ('x','y','w','h'))
    assert all(isinstance(v,int) for v in (x,y,w,h))
    assert x>=0 and y>=0 and w>0 and h>0 and x+w<=im.width and y+h<=im.height
    crop=im.crop((x,y,x+w,y+h))
    return crop.transpose(Image.Transpose.ROTATE_90) if f.get('r') else crop

def geometry(f, crop):
    framed=all(k in f for k in ('fx','fy','fw','fh')) and f['fw']>0 and f['fh']>0
    return (f['fx'],f['fy'],f['fw'],f['fh']) if framed else (0,0,*crop.size)

def visible_signature(im, frames):
    digest=hashlib.sha256()
    for f in frames:
        crop=crop_frame(im,f);fx,fy,fw,fh=geometry(f,crop)
        box=crop.getchannel('A').getbbox()
        visible=None
        if box:
            cut=crop.crop(box)
            # Ignore invisible RGB, but never round or drop faint alpha.
            rgba=bytearray(cut.tobytes())
            for i in range(0,len(rgba),4):
                if rgba[i+3]==0:rgba[i:i+3]=b'\0\0\0'
            visible=[box[0]-fx,box[1]-fy,*cut.size,hashlib.sha256(rgba).hexdigest()]
        digest.update(json.dumps([{k:v for k,v in f.items() if k not in GEOMETRY},fw,fh,visible],
            sort_keys=True,separators=(',',':')).encode())
    return digest.hexdigest()

def optimize(png, atlas):
    im=a.decode_png(png);before=a.decode_atlas(atlas)
    assert len({f['n'] for f in before})==len(before)
    frames=copy.deepcopy(before);unique={};images=[];indices=[]
    for f in frames:
        crop=crop_frame(im,f);fx,fy,fw,fh=geometry(f,crop)
        box=crop.getchannel('A').getbbox() or (0,0,1,1)
        cut=crop.crop(box)
        f.update(fx=fx-box[0],fy=fy-box[1],fw=fw,fh=fh)
        physical=cut.transpose(Image.Transpose.ROTATE_270) if f.get('r') else cut
        key=(*physical.size,hashlib.sha256(physical.tobytes()).digest())
        if key not in unique:unique[key]=len(images);images.append(physical)
        indices.append(unique[key]);f.update(w=physical.width,h=physical.height)
    # Coordinates here are unique identities, not source image locations.
    regions=[a.Rect(i,0,im.width,im.height) for i,im in enumerate(images)]
    area=sum((r.w+2)*(r.h+2) for r in regions)
    side=max(max(r.w+2 for r in regions),math.ceil(math.sqrt(area)/32)*32)
    candidates=[]
    for width in sorted({side,max(side,256),max(side,512),max(side,768),max(r.w+2 for r in regions),
                         max(max(r.w+2 for r in regions),side//2)}):
        if width>4096:continue
        for mode in ('height','area'):
            try:
                places,size=a.pack_regions(regions,target_width=width,max_height=4096,gap=2,sort_mode=mode)
                candidates.append((size[0]*size[1],max(size),size,places))
            except ValueError:pass
    assert candidates,'No atlas layout fits'
    # Very long strips fragment the client's shared 4096-square atlas even
    # when their raw area is small. Prefer a compact shape with modest padding.
    _,_,size,places=min(candidates,key=lambda v:(v[0]*(1+0.15*(max(v[2])/min(v[2])-1)),v[:3]))
    out=Image.new('RGBA',size)
    for i,cut in enumerate(images):
        r=places[regions[i]];out.paste(cut,(r.x,r.y))
    for f,i in zip(frames,indices):
        r=places[regions[i]];f.update(x=r.x,y=r.y)
    # A tiny existing sheet can already be denser than a layout with gutters.
    # Keep its original placements if compaction would increase its area.
    improves_shape=max(out.size)<=max(im.size)*0.75 and out.width*out.height<=im.width*im.height*1.35
    if out.width*out.height>=im.width*im.height and not improves_shape:
        out,frames=im,before
    result_png=a.encode_png(out);result_atlas=a.encode_atlas(frames)
    assert result_png.startswith(p.wf_assets.PNG_FAKE)
    verified=a.decode_png(p.wf_assets.png_encode(p.wf_assets.png_decode_stored(result_png)))
    readback=a.decode_atlas(result_atlas)
    signature=visible_signature(im,before)
    assert visible_signature(verified,readback)==signature
    assert [f['n'] for f in before]==[f['n'] for f in readback]
    return result_png,result_atlas,{'before_size':list(im.size),'after_size':list(out.size),
        'frames':len(before),'unique_pixel_regions':len(images),'visible_signature':signature,
        'before_area':im.width*im.height,'after_area':out.width*out.height,
        'compact_shape_repack':improves_shape,'changed':frames!=before or out.size!=im.size}
