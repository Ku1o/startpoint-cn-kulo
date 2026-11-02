"""Independently re-open stored native resources and verify emitted render_ops.

Uses decoded parts only for placement/opacity; never re-samples author keyframes.
"""
import argparse
import io
from pathlib import Path
import compile_parts as c
from PIL import Image

def verify(directory):
    directory=Path(directory).resolve();manifest=c.readj(directory/'overlay.json')
    proof=c.readj(directory/'verification.json');ops_raw=(directory/'render_ops.json').read_bytes()
    c.require(c.sha(ops_raw)==proof['renderOpsSha256'],'render_ops drift')
    ops=c.readj(directory/'render_ops.json');resources={}
    for e in manifest['resources']:
        p=Path(e['path']);p=p if p.is_absolute() else directory/p;raw=p.read_bytes()
        c.require(c.sha(raw)==e['sha256'],'Stored resource hash drift: '+e['logical']);resources[e['logical']]=raw
    rows=[]
    for group in ops['groups']:
        layout=group['logical'];root=layout.rsplit('/',1)[0];name=root.rsplit('/',1)[1]
        parts=c.gates.decode_amf3_deflate(resources[layout+'.parts.amf3.deflate'])
        timeline=c.gates.decode_amf3_deflate(resources[layout+'.timeline.amf3.deflate'])
        atlas=c.gates.decode_amf3_deflate(resources[root+'/'+name+'.atlas.amf3.deflate'])
        sheet=Image.open(io.BytesIO(c.wf_assets.png_decode_stored(resources[root+'/'+name+'.png']))).convert('RGBA')
        c.require(parts['s']==group['partsScale'],'Container scale mismatch')
        c.require(timeline['sequences']==[{'begin':1,'end':group['durationTicks']+1,'name':'neutral','kind':'once'}],'Native timeline boundary drift')
        c.require(not timeline['sounds'],'Unexpected dynamic sounds')
        cells={e['n']:e for e in atlas}
        for item in group['images']:
            p=Path(item['source']);c.require(c.sha(p.read_bytes())==item['sourceSha256'],'Source identity drift')
            source=Image.open(p).convert('RGBA');entry=cells[parts['i'][item['index']]['p']]
            actual=sheet.crop((entry['x'],entry['y'],entry['x']+entry['w'],entry['y']+entry['h']))
            c.require(source.size==actual.size and source.tobytes()==actual.tobytes(),'Decoded source RGBA mismatch')
        frames=c.replay._build_frames(parts)
        for frame in group['frames']:
            decoded=c.replay._flatten(frames,0,frame['tick'],(1,0,0,1,0,0),1)
            c.require(len(decoded)==len(frame['ops']),'Stored native op count mismatch')
            for (iid,matrix,alpha),expected in zip(decoded,frame['ops']):
                c.require(iid==expected['imageIndex'] and list(matrix)==expected['matrix'] and alpha==expected['alpha'],'Stored native op mismatch')
                mid=expected['matrixIndex'];record=parts['t'][mid]
                c.require(expected['matrix']==[record[k]/4096 for k in ('a','b','c','d','x','y')],'Native matrix index mismatch')
        c.require(not c.replay._flatten(frames,0,group['durationTicks'],(1,0,0,1,0,0),1),'Terminal frame not blank')
        profile=c.replay.flatomo_instance_profile(parts)
        c.require(parts['a']==profile['per_image_peaks']==group['poolCapacity'],'Pool capacity mismatch')
        rows.append({'id':group['id'],'nativeTicksChecked':group['durationTicks'],'sourceImagesRgbaExact':len(group['images']),'poolCapacityExact':True,'terminalBlank':True})
    return {'status':'passed_disk_native_replay','directory':str(directory),'renderOpsSha256':c.sha(ops_raw),'groups':rows,'deviceVerified':False}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--compiled',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    target=a.out.resolve();c.require(target.is_relative_to(c.HERE) and target!=c.HERE and not target.exists(),'Readback report must be a new engineering file')
    result=verify(a.compiled);c.savej(target,result);print(result)

if __name__=='__main__':main()
