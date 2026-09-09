"""Readback and rendered-frame gates for the 0909 completion patch."""
import argparse, io, json, zlib
from pathlib import Path
import prepare_content as p
import optimize_battle_atlases as opt
import wf_battle_atlas_repack as a
import wf_dsl
from PIL import Image

def render(im, frame):
    # Separate reconstruction, following SubTexture's rotated dimensions and frame offset.
    x,y,w,h=[frame[k] for k in ('x','y','w','h')]
    cut=im.crop((x,y,x+w,y+h))
    if frame.get('r'):cut=cut.rotate(90,expand=True)
    has_frame=all(k in frame for k in ('fx','fy','fw','fh')) and frame['fw']>0 and frame['fh']>0
    size=(frame['fw'],frame['fh']) if has_frame else cut.size
    position=(-frame['fx'],-frame['fy']) if has_frame else (0,0)
    out=Image.new('RGBA',size);out.alpha_composite(cut,position)
    return out

def verify_pair(before_png,before_atlas,after_png,after_atlas):
    assert after_png.startswith(p.wf_assets.PNG_FAKE), 'stored PNG signature'
    p.wf_assets.png_decode_stored(after_png)
    old,new=a.decode_atlas(before_atlas),a.decode_atlas(after_atlas)
    assert [f['n'] for f in old]==[f['n'] for f in new], 'frame names/order changed'
    source,target=a.decode_png(before_png),a.decode_png(after_png)
    assert opt.visible_signature(source,old)==opt.visible_signature(target,new), 'frame semantics changed'
    for left,right in zip(old,new):
        opt.crop_frame(source,left);opt.crop_frame(target,right)
        x,y=render(source,left),render(target,right)
        assert x.size==y.size and x.tobytes()==y.tobytes(),left['n']
    return len(old)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--work',type=Path,required=True)
    w=parser.parse_args().work;c=p.Chain();report=p.readj(w/'prepare-report.json')
    assert c.tail==report['baseline']=='1.4.103' and p.sha(c.manifest_bytes)==report['manifest_sha256']
    inventory=p.readj(w/'resources.json');index={r['logical']:r for r in inventory}
    assert len(index)==len(inventory)==51
    def after(n):return (w/'resources/upload'/index[n]['rel']).read_bytes()
    def before(n):return (w/'before/upload'/index[n]['rel']).read_bytes()
    for row in inventory:
        assert p.hrel(row['logical'])==row['rel']
        assert p.sha(before(row['logical']))==row['before_sha256']==p.sha(c.get(('common',row['rel'])))
        assert p.sha(after(row['logical']))==row['sha256']
        assert row['root']=='common'
    frames=0
    for n in index:
        if not n.endswith('.atlas.amf3.deflate'):continue
        png=n.replace('.atlas.amf3.deflate','.png')
        if '/wave_arc120_' not in n:
            frames+=verify_pair(before(png),before(n),after(png),after(n))
            continue
        assert a.decode_atlas(after(n))==[]
        assert after(png).startswith(p.wf_assets.PNG_FAKE)
        blank=a.decode_png(after(png));assert blank.size==(8,8) and blank.getchannel('A').getbbox() is None
        fast=n.replace('wave_arc120_middle','wave_arc120_fast').replace('wave_arc120_slow','wave_arc120_fast')
        fast_atlas=c.get(('common',p.hrel(fast)))
        fast_png=c.get(('common',p.hrel(fast.replace('.atlas.amf3.deflate','.png'))))
        own=a.decode_atlas(before(n));shared={f['n']:f for f in a.decode_atlas(fast_atlas)}
        for frame in own:
            alias=frame['n'].replace('wave_arc120_middle','wave_arc120_fast').replace('wave_arc120_slow','wave_arc120_fast')
            target=dict(shared[alias]);target['n']=frame['n']
            assert opt.visible_signature(a.decode_png(before(png)),[frame])==opt.visible_signature(a.decode_png(fast_png),[target])
            assert render(a.decode_png(before(png)),frame).tobytes()==render(a.decode_png(fast_png),target).tobytes()
            frames+=1
        parts=n.replace('.atlas.amf3.deflate','.parts.amf3.deflate')
        old=wf_dsl.parse_dsl(zlib.decompress(before(parts),-15))['tree']
        new=wf_dsl.parse_dsl(zlib.decompress(after(parts),-15))['tree']
        for entry in old['i']:
            entry['p']=entry['p'].replace('wave_arc120_middle','wave_arc120_fast').replace('wave_arc120_slow','wave_arc120_fast')
            assert entry['p'] in shared
        assert old==new, 'wind animation timing/geometry changed'
    allowed={'master/item/item.orderedmap':{'10000143'},'master/string/ui_string.orderedmap':{'quest_start_out_of_period_error'}}
    for n,keys in allowed.items():
        old,new=p.rawmap(before(n)),p.rawmap(after(n));assert old.keys()==new.keys()
        assert {key for key in old if old[key]!=new[key]}==keys
        if n.startswith('master/item'):
            x,y=p.csvrows(old['10000143'])[0],p.csvrows(new['10000143'])[0]
            assert {i for i in range(len(x)) if x[i]!=y[i]}=={5}
    # The 49 deferred visual files have all been considered; donor pool notes remain excluded.
    deferred=p.readj(p.REPO/'assets/asset-patch/audit/lens0909-1.4.103/resource-decisions.json')['deferred']
    assert {n for n in deferred if not n.startswith('rich_text/')}==set(index)-set(allowed)
    # Both wind skill variants preload fast/middle/slow into the same scene cache.
    wind=[]
    for number in (1,2):
        n=f'battle/action/skill/action/rare5/land_dragon_wind_playable$land_dragon_wind_playable_{number}.action.dsl.amf3.deflate'
        raw=c.get(('common',p.hrel(n)));tree=wf_dsl.parse_dsl(zlib.decompress(raw,-15))['tree']
        text=json.dumps(tree)
        for speed in ('fast','middle','slow'):
            family=f'battle/effect/skill_unique/land_dragon_wind_playable/wave_arc120_{speed}/wave_arc120_{speed}'
            assert '"'+family+'"' in text
        wind.append({'logical':n,'sha256':p.sha(raw),'preloads_all_three':True})
    atlases=p.readj(w/'atlas-report.json')
    result={'status':'passed','resources':len(inventory),'atlas_pairs':len(atlases),'rendered_frames':frames,
        'before_area':sum(r['before_area'] for r in atlases),'after_area':sum(r['after_area'] for r in atlases),
        'changed_atlas_pairs':sum(r['changed'] for r in atlases),'wind_preload_proof':wind,
        'inventory_sha256':p.sha((w/'resources.json').read_bytes()),
        'limitations':'静态渲染与载入链校验；真机帧率、多人装箱极限和完整 UI 操作仍待验收。'}
    p.savej(w/'acceptance-report.json',result);print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':main()
