"""Compile scoped RGBA instances into native Flatomo and decode every emitted tick.

No asset-chain, service, database, SWF, or source-repository writes.
"""
from __future__ import annotations
import argparse
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import sys
import zlib

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ['STARPOINT_SUPPORT_ROOT']).resolve()
sys.path.insert(0, str(SOURCE / 'tools/fantasy-gauntlet-mod-tools'))
from PIL import Image
import wf_assets
import wf_character_gates as gates
import wf_dsl
import wf_flatomo_preview_render as replay

PREFIX = 'battle/effect/skill_unique/cnmod_inaho_halloween'
RES = 4096

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def readj(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def savej(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)

def vector(value, count, label):
    require(isinstance(value, list) and len(value) == count and all(numeric(x) for x in value), label)
    return value

def integer(value, minimum=0):
    return isinstance(value, int) and not isinstance(value, bool) and value >= minimum

def guarded_output(path):
    result = Path(path).resolve()
    require(result != HERE and result.is_relative_to(HERE), 'Output must be a new child of engineering')
    require(not result.exists(), 'Preserve existing output; choose a new directory')
    return result

def shelf_pack(images):
    # Deterministic shelf candidates; preserve all RGBA pixels, no trimming/rotation/resizing.
    ordered = sorted(range(len(images)), key=lambda i: (-images[i].height, -images[i].width, i))
    minimum = max(im.width + 2 for im in images)
    area = sum((im.width + 2) * (im.height + 2) for im in images)
    choices = sorted({minimum, max(minimum, math.ceil(math.sqrt(area))), *[x for x in (128,256,512,768,1024,1536,2048) if x >= minimum]})
    best = None
    for width in choices:
        x = y = row = used = 0
        locations = {}
        for i in ordered:
            w, h = images[i].width + 2, images[i].height + 2
            if x and x + w > width:
                y += row; x = row = 0
            locations[i] = (x + 1, y + 1)
            x += w; row = max(row, h); used = max(used, x)
        height = y + row
        if max(used, height) > 4094:
            continue
        score = (used * height, max(used, height), used)
        if best is None or score < best[0]:
            best = (score, used, height, locations)
    require(best is not None, 'Individual sheet cannot fit native 4094 bound; this is not whole-battle packing proof')
    _, width, height, locations = best
    sheet = Image.new('RGBA', (width, height))
    for i, im in enumerate(images):
        sheet.paste(im, locations[i])  # No mask: do not multiply soft alpha twice.
    return sheet, locations

def pack(images):
    # Task-scoped deterministic exact-pixel layout; any optional V7 plan is spec/hash bound.
    from packing_optimized import pack_images
    return pack_images(images)

def sample(instance, tick):
    keys = instance['keys']
    left = keys[0]
    right = None
    for key in keys[1:]:
        if key['tick'] > tick:
            right = key
            break
        left = key
    matrix = left['matrix'][:]
    alpha = left.get('alpha', 1)
    if right is not None and left.get('interpolation', 'hold') == 'linear':
        r = (tick - left['tick']) / (right['tick'] - left['tick'])
        matrix = [a + (b - a) * r for a, b in zip(matrix, right['matrix'])]
        alpha += (right.get('alpha', 1) - alpha) * r
    return matrix, alpha

def quantized(matrix, origin):
    a, b, c, d, x, y = matrix
    ox, oy = origin
    # Asset origin is in original image pixels; translations in the group's local units.
    values = [a, b, c, d, x - a * ox - c * oy, y - b * ox - d * oy]
    ints = [round(v * RES) for v in values]
    require(all(-2147483648 <= v <= 2147483647 for v in ints), 'Native IntMatrix overflow')
    return dict(zip(('a','b','c','d','x','y'), ints))

def compile_group(group, assets, output):
    gid = group['id']
    require(gid in ('caster','field','hit'), 'Only caster/field/hit groups are supported')
    duration = group['durationTicks']
    require(integer(duration,1) and duration <= 6000, 'Duration must be 1..6000 battle ticks')
    scale = group['partsScale']
    require(numeric(scale) and 0 < scale <= 64, 'Positive finite declared partsScale required')
    layer = group.get('layerZDepth', 'BacksideOfCharacter' if gid=='field' else 'ForesideOfCharacter')
    require(layer in ('BacksideOfCharacter','ForesideOfCharacter'), 'Explicit supported native scene layer required')
    instances = group['instances']
    require(isinstance(instances,list) and instances, 'At least one instance per group required')
    ids = set()
    for ins in instances:
        require(isinstance(ins.get('id'),str) and ins['id'] not in ids, 'Unique instance id required')
        ids.add(ins['id'])
        require(ins.get('asset') in assets, 'Unknown asset')
        require(integer(ins.get('start')) and integer(ins.get('end'),1) and ins['start'] < ins['end'] <= duration, 'Instance interval is [start,end) within duration')
        require(numeric(ins.get('z',0)), 'Finite z required')
        keys = ins.get('keys')
        require(isinstance(keys,list) and keys and keys[0].get('tick') == ins['start'], 'First key must begin at instance start')
        previous = -1
        for key in keys:
            require(integer(key.get('tick')) and previous < key['tick'] <= ins['end'], 'Strictly ordered absolute group ticks required')
            previous = key['tick']
            vector(key.get('matrix'),6,'matrix must be [a,b,c,d,tx,ty]')
            require(numeric(key.get('alpha',1)) and 0 <= key.get('alpha',1) <= 1, 'alpha must be 0..1')
            require(key.get('interpolation','hold') in ('hold','linear'), 'Only hold/linear interpolation supported')
        require(set(ins) <= {'id','asset','start','end','z','keys'}, 'Unknown instance field; transform must not be silently ignored')
    order = sorted(enumerate(instances), key=lambda pair:(pair[1].get('z',0),pair[0]))
    used_ids = list(dict.fromkeys(ins['asset'] for _,ins in order))
    root = f'{PREFIX}/{gid}'
    logical = root + '/effect'
    images = [assets[aid]['image'] for aid in used_ids]
    sheet, positions = pack(images)
    atlas = [{'n':f'{root}/.gen/{i}','x':positions[i][0],'y':positions[i][1],'w':im.width,'h':im.height} for i,im in enumerate(images)]
    matrices = [dict(a=RES,b=0,c=0,d=RES,x=0,y=0)]
    matrix_ids = {tuple(matrices[0].values()):0}
    segments = []; expected = [[] for _ in range(duration)]
    for _, ins in order:
        aid = ins['asset']; iid = used_ids.index(aid); origin = assets[aid]['origin']
        runs = []
        for tick in range(ins['start'], ins['end']):
            m, alpha = sample(ins,tick); native = quantized(m,origin); signature = tuple(native.values())
            if signature not in matrix_ids:
                matrix_ids[signature] = len(matrices); matrices.append(native)
            mid = matrix_ids[signature]
            require(mid < (1 << 19), 'Packed matrix index overflow')
            opacity = round(alpha * 255)
            expected[tick].append({'imageIndex':iid,'asset':aid,'matrixIndex':mid,'alphaByte':opacity,'instance':ins['id']})
            if runs and runs[-1][2:] == [mid,opacity]:
                runs[-1][1] += 1
            else:
                runs.append([tick,1,mid,opacity])
        for start, ticks, mid, opacity in runs:
            segments.append({'s':start,'i':iid,'l':[{'m':(mid << 12) | opacity,'t':ticks}]})
    pool = [max(sum(op['imageIndex']==i for op in frame) for frame in expected) for i in range(len(images))]
    parts = {'i':[{'s':False,'p':a['n']} for a in atlas],'g':[{'t':duration+1,'s':segments}],'m':[],'a':pool,'o':[],'t':matrices,'c':[],'s':scale}
    timeline = {'sequences':[{'begin':1,'end':duration+1,'name':'neutral','kind':'once'}], 'sounds':[],'points':[],'circles':[],'rectangles':[],'matrices':[]}
    stream = io.BytesIO(); sheet.save(stream,format='PNG',compress_level=9)
    enc = lambda value: zlib.compress(wf_dsl.encode_amf3(value),9,wbits=-15)
    resources = {root+'/'+gid+'.png':wf_assets.png_encode(stream.getvalue()),root+'/'+gid+'.atlas.amf3.deflate':enc(atlas),logical+'.parts.amf3.deflate':enc(parts),logical+'.timeline.amf3.deflate':enc(timeline)}
    entries=[]
    for name, raw in resources.items():
        target=output/'native'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(raw)
        entries.append({'root':'common','logical':name,'path':str(target),'sha256':sha(raw),'size':len(raw)})
    resources = {e['logical']:Path(e['path']).read_bytes() for e in entries}
    require(all(sha(resources[e['logical']])==e['sha256'] for e in entries),'Disk resource drift')
    decoded = gates.decode_amf3_deflate(resources[logical+'.parts.amf3.deflate'])
    require(decoded == parts,'Native parts AMF3 roundtrip mismatch')
    require(gates.decode_amf3_deflate(resources[logical+'.timeline.amf3.deflate']) == timeline,'Timeline AMF3 roundtrip mismatch')
    decoded_atlas = gates.decode_amf3_deflate(resources[root+'/'+gid+'.atlas.amf3.deflate'])
    restored = Image.open(io.BytesIO(wf_assets.png_decode_stored(resources[root+'/'+gid+'.png']))).convert('RGBA')
    for i,a in enumerate(decoded_atlas):
        crop = restored.crop((a['x'],a['y'],a['x']+a['w'],a['y']+a['h']))
        require(crop.tobytes() == images[i].tobytes(),'Encoded atlas RGBA mismatch')
    frames = replay._build_frames(decoded)
    ops=[]
    for tick in range(duration):
        commands=replay._flatten(frames,0,tick,(1,0,0,1,0,0),1)
        actual=[]
        for image_index,matrix,alpha in commands:
            actual.append({'imageIndex':image_index,'asset':used_ids[image_index], 'matrix':list(matrix),'alpha':alpha})
        require(len(actual)==len(expected[tick]),'Native command count mismatch')
        for a,e in zip(actual,expected[tick]):
            nm=matrices[e['matrixIndex']]
            require(a['imageIndex']==e['imageIndex'] and a['matrix']==[nm[k]/RES for k in ('a','b','c','d','x','y')] and a['alpha']==e['alphaByte']/255,'Native transform/order/alpha mismatch')
            a.update(matrixIndex=e['matrixIndex'],alphaByte=e['alphaByte'],instance=e['instance'])
        ops.append({'tick':tick,'ops':actual})
    profile=replay.flatomo_instance_profile(decoded)
    require(profile['per_image_peaks']==pool,'Native pool demand mismatch')
    require(not replay._flatten(frames,0,duration,(1,0,0,1,0,0),1),'Missing terminal blank frame')
    result={'id':gid,'logical':logical,'durationTicks':duration,'partsScale':scale,'layerZDepth':layer,'images':[{'index':i,'asset':aid,'source':str(assets[aid]['path']),'sourceSha256':assets[aid]['sha256'],'origin':assets[aid]['origin'],'size':list(images[i].size)} for i,aid in enumerate(used_ids)],'matrices':[[m[k]/RES for k in ('a','b','c','d','x','y')] for m in matrices],'frames':ops,'poolCapacity':pool,'poolSum':sum(pool),'maxImageCommandsPerTick':max(map(len,expected)),'sheetSize':list(sheet.size),'paddedSheetPixels':(sheet.width+2)*(sheet.height+2),'profile':profile,'normalBlendOnly':True,'decodedCommandsMatchQuantizedSource':True,'decodedAtlasRgbaExact':True}
    savej(output/'decoded'/f'{gid}.parts.json',decoded);savej(output/'decoded'/f'{gid}.timeline.json',timeline);savej(output/'decoded'/f'{gid}.atlas.json',decoded_atlas)
    return entries,result

def compile_spec(spec_path, output):
    spec_path=Path(spec_path).resolve(); spec=readj(spec_path)
    require(spec.get('format')==1,'Expected format 1')
    output=guarded_output(output)
    assets={}; asset_root=Path(spec.get('assetRoot',str(spec_path.parent)))
    if not asset_root.is_absolute():asset_root=spec_path.parent/asset_root
    for item in spec['assets']:
        aid=item['id'];require(isinstance(aid,str) and aid and aid not in assets,'Unique asset id required')
        p=Path(item['path']);p=p if p.is_absolute() else asset_root/p;p=p.resolve()
        raw=p.read_bytes()
        if item.get('sha256'):require(item['sha256']==sha(raw),'Input asset hash drift')
        with Image.open(io.BytesIO(raw)) as im:
            require(im.format=='PNG' and im.mode=='RGBA','Source must be explicit RGBA PNG')
            image=im.copy()
        require(image.width>0 and image.height>0 and max(image.size)<=4092,'Invalid image dimensions')
        origin=item.get('origin',[0,0]);vector(origin,2,'Explicit image-local origin required')
        assets[aid]={'image':image,'path':p,'sha256':sha(raw),'origin':origin}
    require(assets,'No assets');groups=spec['groups'];require(len(groups)==3 and {g['id'] for g in groups}=={'caster','field','hit'},'Exactly caster, field, hit groups required')
    # All validation failures may leave a clearly non-release output for diagnosis; never replace prior files.
    output.mkdir(parents=True)
    resources=[];results=[]
    for group in groups:
        entries,result=compile_group(group,assets,output);resources+=entries;results.append(result)
    render={'format':1,'status':'passed_native_decode_replay','specSha256':sha(spec_path.read_bytes()),'coordinateConvention':'tick0-based; end-exclusive; matrix maps PNG top-left to local group coordinates; world=anchor+partsScale*matrix*pixel; normal alpha','groups':results,'deviceVerified':False}
    savej(output/'render_ops.json',render)
    savej(output/'overlay.json',{'format':1,'resources':resources,'releaseReady':False,'scope':'native visual resources only; no mechanics or runtime publication'})
    savej(output/'verification.json',{'status':'passed_native_decode_replay','compilerSha256':sha(Path(__file__).read_bytes()),'specSha256':render['specSha256'],'renderOpsSha256':sha((output/'render_ops.json').read_bytes()),'toolchain':{name:sha((SOURCE/'tools/fantasy-gauntlet-mod-tools'/name).read_bytes()) for name in ('wf_dsl.py','wf_assets.py','wf_flatomo_preview_render.py')},'groups':[{k:g[k] for k in ('id','durationTicks','poolSum','maxImageCommandsPerTick','sheetSize','paddedSheetPixels','decodedCommandsMatchQuantizedSource','decodedAtlasRgbaExact')} for g in results],'quantization':'matrix nearest1/4096; alpha nearest1/255; linear keys sampled each native tick then encoded as step runs','soundRegistrationAdded':False,'gameIntegrated':False,'deviceVerified':False})
    return render

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--spec',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    result=compile_spec(a.spec,a.out)
    print(json.dumps({'output':str(a.out.resolve()),'status':result['status'],'groups':[{'id':g['id'],'ticks':g['durationTicks'],'images':len(g['images']),'pool':g['poolSum']} for g in result['groups']]}))

if __name__=='__main__':main()
