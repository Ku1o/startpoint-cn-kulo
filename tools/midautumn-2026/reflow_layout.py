"""Append holiday layout and odds changes; preserve published artwork."""
import argparse, copy, io, json, math, sys, zipfile, zlib
from fractions import Fraction
from pathlib import Path
import build_content as b
from PIL import Image
import wf_flatomo_preview_render as render

p = b.p
BASE_VERSION, TARGET_VERSION = '1.4.118', '1.4.119'
PATCH_ID = 'midautumn-layout-odds'
ARCHIVE = 'pinball-1.4.118-1.4.119-1-midautumn-layout-odds.zip'
LOGICAL = b.MOVIE + '.movie.amf3.deflate'
OLD = [(0,0,1440),(150,0,630),(690,40,660),(40,365,780),(650,365,730),(220,700,1000)]
# Normalized face-feature regions, excluding props, ears and decorative effects.
FACE = {1:(.425,.10,.665,.215),2:(.54,.105,.775,.26),
        3:(.455,.175,.66,.28),4:(.345,.125,.61,.26)}

def decode(data):
    return b.wf_dsl.parse_dsl(zlib.decompress(data,-15))['tree']

def reflow(movie, atlas, layout):
    result = copy.deepcopy(movie)
    matrices, lookup = [], {}
    def intern(value):
        key = tuple(value[k] for k in ('a','b','c','d','x','y'))
        if key not in lookup:
            lookup[key] = len(matrices); matrices.append(value)
        return lookup[key]
    for segment in result['g'][0]['s']:
        image_id = segment['i']
        name = result['i'][image_id]['p'].rsplit('/',1)[-1]
        old_x,old_y,old_width = OLD[image_id]
        new_x,new_y,new_width = layout.get(name,OLD[image_id])
        ratio = new_width / old_width
        for key in segment['l']:
            packed = key['m']; matrix = copy.deepcopy(movie['t'][packed >> 12])
            for field in ('a','b','c','d'):
                matrix[field] = round(matrix[field]*ratio)
            matrix['x'] = round(new_x*4096 + (matrix['x']-old_x*4096)*ratio)
            matrix['y'] = round(new_y*4096 + (matrix['y']-old_y*4096)*ratio)
            key['m'] = (intern(matrix)<<12) | (packed & 4095)
    result['t'] = matrices
    return result

def bounds(rect, matrix):
    a,bb,c,d,x,y = matrix
    points=[(a*u+c*v+x,bb*u+d*v+y) for u in (rect[0],rect[2]) for v in (rect[1],rect[3])]
    return [min(v[0] for v in points),min(v[1] for v in points),max(v[0] for v in points),max(v[1] for v in points)]

def validate_layout(movie,cells):
    frames=render._build_frames(movie); failures=[]; faces={}; title=[]
    # Native wrapper origin (-180,60), viewport 1080 wide. Carousel ends near
    # scene y=280; retain extra room for its shadow and the idle motion.
    for frame in range(61,302):
        commands=render._flatten(frames,0,frame,(1,0,0,1,0,0),1)
        for i,matrix,alpha in commands:
            if i in FACE:
                w,h=cells[i].image.size
                region=bounds(tuple(v*(w if n%2==0 else h) for n,v in enumerate(FACE[i])),matrix)
                faces.setdefault(str(i),[]).append(region)
                if not (region[0]>=375 and region[2]<=1240 and region[1]>=310 and region[3]<=980):
                    failures.append({'frame':frame,'image':i,'face':region})
            elif i==5:
                region=bounds(cells[i].image.getbbox(),matrix);title.append(region)
                if not (region[0]>=270 and region[2]<=1170 and region[1]>=1000 and region[3]<=1400):
                    failures.append({'frame':frame,'title':region})
    return {'failures':failures,'stable_frames':241,
            'face_bounds':{i:[round(min(v[0] for v in rows),2),round(min(v[1] for v in rows),2),round(max(v[2] for v in rows),2),round(max(v[3] for v in rows),2)] for i,rows in faces.items()},
            'title_bounds':[round(min(v[0] for v in title),2),round(min(v[1] for v in title),2),round(max(v[2] for v in title),2),round(max(v[3] for v in title),2)]}

def render_frame(movie,cells,frame,scale=.5):
    canvas=Image.new('RGBA',(round(1080*scale),round(1920*scale)),(250,248,242,255))
    frames=render._build_frames(movie)
    for i,matrix,alpha in render._flatten(frames,0,frame,(1,0,0,1,-180,60),1):
        patch=render._warp_cell(cells[i],matrix,alpha,scale,(0,0))
        if patch:canvas.alpha_composite(*patch)
    return canvas

def rebalance(get,work):
    relative='assets/gacha_midautumn_2026.json'
    before=(b.REPO/relative).read_bytes();server=json.loads(before)
    old=copy.deepcopy(server);pool=server[b.GID]['pool']['1']
    mods=[e for e in pool if e['isLimited']];permanent=[e for e in pool if not e['isLimited']]
    assert [e['id'] for e in mods]==b.MODS and len(permanent)==110
    old_total=sum(e['odds'] for e in pool)
    assert Fraction(sum(e['odds'] for e in mods),old_total)*Fraction(5,100)==Fraction(4,100)
    divisor=math.gcd(len(permanent),4*len(mods))
    for e in pool:e['odds']=(len(permanent) if e['isLimited'] else 4*len(mods))//divisor
    total=sum(e['odds'] for e in pool)
    for e in pool:e['rarity']=1000*e['odds']/total
    assert all(Fraction(e['odds'],total)*Fraction(5,100)==Fraction(1,1200) for e in mods)
    assert Fraction(sum(e['odds'] for e in permanent),total)*Fraction(5,100)==Fraction(4,100)
    restored=copy.deepcopy(server)
    for a,z in zip(restored[b.GID]['pool']['1'],old[b.GID]['pool']['1']):
        a['odds']=z['odds'];a['rarity']=z['rarity']
    assert restored==old
    code=f'{b.CODE}_character_5';logical=f'master/gacha_odds/{code}.orderedmap'
    raw_before=get(logical);table=b.decode(raw_before)
    assert len(table[code])==len(pool)
    for i,(e,z) in enumerate(zip(pool,old[b.GID]['pool']['1'])):
        row=table[code][str(i)][0]
        assert list(map(int,row[:3]))==[z['id'],z['rank'],z['odds']]
        row[2]=str(e['odds'])
    raw_after=b.encode(table);assert b.decode(raw_after)==table
    note_logical=f'rich_text/{b.CODE}_note.html.deflate'
    old_note=zlib.decompress(get(note_logical),-15).decode('utf-8')
    old_line='12位MOD角色合计出现概率4%，每位为1/3%（约0.3333%）；常驻★5合计1%'
    new_line='12位MOD角色合计出现概率1%，每位为1/12%（约0.08333%）；常驻★5合计4%'
    assert old_note.count(old_line)==1
    new_note=old_note.replace(old_line,new_line)
    p.savej(work/'files'/relative,server)
    return {logical:raw_after,note_logical:b.rawdef(new_note.encode('utf-8'))},{'file':relative,'before_sha256':p.sha(before),'after_sha256':p.sha((work/'files'/relative).read_bytes()),'five_star_total':'5%','mod_total':'1%','mod_each':'1/1200','permanent_five_total':'4%','mod_weight':mods[0]['odds'],'permanent_weight':permanent[0]['odds'],'five_star_weight_sum':total}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True)
    ap.add_argument('--layout',type=Path,default=Path(__file__).with_name('layout-v2.json'))
    args=ap.parse_args();work=args.work.resolve()
    assert not work.is_relative_to((b.REPO/'.cdn').resolve());work.mkdir(parents=True,exist_ok=True)
    chain=p.Chain();assert chain.tail==BASE_VERSION,chain.tail
    def get(logical):
        data=chain.get(('common',p.hrel(logical)));assert data is not None;return data
    before=get(LOGICAL);movie=decode(before)
    atlas_bytes=get(b.MOVIE.rsplit('/',1)[0]+'/sprite_sheet.atlas.amf3.deflate')
    sheet_bytes=get(b.MOVIE.rsplit('/',1)[0]+'/sprite_sheet.png')
    timeline_bytes=get(b.MOVIE+'.timeline.amf3.deflate')
    atlas=decode(atlas_bytes)
    sheet=Image.open(io.BytesIO(b.wf_assets.png_decode_stored(sheet_bytes))).convert('RGBA')
    cells=render._load_cells(sheet,atlas,movie)
    assert [x['p'].rsplit('/',1)[-1] for x in movie['i']]==['background','hibiki','black','fluffy','mia','title']
    layout=p.readj(args.layout);result=reflow(movie,atlas,layout)
    after=b.amf(result);assert decode(after)==result
    assert result['l']==movie['l']==decode(timeline_bytes)
    for field in ('i','a','m','o','c','s'):assert result[field]==movie[field]
    assert render.flatomo_instance_profile(result)==render.flatomo_instance_profile(movie)
    for old_segment,new_segment in zip(movie['g'][0]['s'],result['g'][0]['s']):
        assert old_segment.keys()==new_segment.keys()
        for old_key,new_key in zip(old_segment['l'],new_segment['l']):
            assert old_key['t']==new_key['t'] and old_key['m']&4095==new_key['m']&4095
    original_check=validate_layout(movie,cells);assert original_check['failures']
    check=validate_layout(result,cells)
    p.savej(work/'layout-check.json',check)
    render_frame(movie,cells,90).save(work/'before-frame.png')
    render_frame(result,cells,90).save(work/'after-frame.png')
    p.savej(work/'movie.json',result)
    assert not check['failures'],str(check['failures'][:2])
    odds_assets,odds_report=rebalance(get,work)
    payloads={LOGICAL:after,**odds_assets}
    archive=work/'files/assets/asset-patch/active'/ARCHIVE;archive.parent.mkdir(parents=True,exist_ok=True)
    members={p.member(('common',p.hrel(logical))):data for logical,data in payloads.items()}
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for member,data in sorted(members.items()):
            info=zipfile.ZipInfo(member,date_time=(2026,9,25,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;z.writestr(info,data)
    with zipfile.ZipFile(archive) as z:assert {n:z.read(n) for n in z.namelist()}==members and z.testzip() is None
    manifest=copy.deepcopy(chain.manifest)
    patch={'id':PATCH_ID,'type':'patch','name':'中秋国庆卡池排版与概率调整','description':'四角色面部避开顶部轮播横幅，标题缩小下移；12位MOD合计1%，常驻五星合计4%。','version':TARGET_VERSION,'depends_on':BASE_VERSION,'enabled':True,'archive':ARCHIVE,'archive_size':archive.stat().st_size,'archive_integrity':[{'name':ARCHIVE,'size':archive.stat().st_size,'sha256':p.sha(archive.read_bytes()),'members':len(members)}],'files':sorted(members),'chain':[ARCHIVE],'created_at':'2026-09-25','audit':{'directory':'assets/asset-patch/audit/midautumn-layout-odds'},'changes':['调整四角色位置与标题比例，保留图集及动画时序。','12位MOD等权合计1%，五星总概率保持5%；同步客户端概率和说明。']}
    manifest['cdn_version']=TARGET_VERSION;manifest['patches'].append(patch)
    p.savej(work/'files/assets/asset-patch/manifest.json',manifest)
    sources={key:{**v,'archive':str(Path(v['archive']).relative_to(b.REPO)).replace('\\','/')} for key,v in chain.reads.items()}
    p.savej(work/'report.json',{'base_version':BASE_VERSION,'version':TARGET_VERSION,'manifest_preimage_sha256':p.sha(chain.manifest_bytes),'archive':patch,'assets':[{'logical':logical,'member':p.member(('common',p.hrel(logical))),'sha256':p.sha(data)} for logical,data in payloads.items()],'movie_before_sha256':p.sha(before),'asset_sources':sources,'layout':layout,'layout_validation':check,'old_layout_rejected':True,'odds':odds_report,'unchanged':['sprite_sheet PNG/atlas','timeline','rarity odds','item and exchange settings','save IDs and data'],'device_acceptance':'pending'})
    print(json.dumps({'archive':ARCHIVE,'bytes':archive.stat().st_size,'layout_validation':check,'odds':odds_report},ensure_ascii=False))

if __name__=='__main__':main()
