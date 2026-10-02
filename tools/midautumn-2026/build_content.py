"""Build a sparse holiday-gacha candidate from the verified effective CDN chain.

Writes only --work; apply.py installs preimage-checked candidates separately.
PNG resampling here is texture compilation; source illustrations are immutable.
"""
from __future__ import annotations
import argparse, copy, io, json, math, sys, zipfile, zlib
from fractions import Fraction
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'tools/lens-integration'))
import prepare_content as p
import wf_assets, wf_dsl
from wf_abyss_ticket_compile import TicketSpec, compile_item_assets
from wf_abyss_gacha_contract import NON_GACHA_CHARACTER_IDS
from PIL import Image

GID, IID = '990003', '999019'
CODE = 'cnmod_midautumn_national_2026'
TITLE = '中秋·国庆限定扭蛋'
MODS = [119992,119990,169988,169991,149987,159995,119991,139992,139991,149986,139990,159994]
MOON_SHA = '584b87753f21348683e192c682738b9900754ae0bdb28d68a254e06f0fa85dc4'
MOVIE = f'gacha/feature_movie/{CODE}/top/feature'
GACHA_T = 'master/gacha/gacha.orderedmap'
FEATURE_T = 'master/gacha/gacha_feature_content.orderedmap'
ITEM_T = 'master/item/item.orderedmap'

def rawdef(b):
    c=zlib.compressobj(9,wbits=-15); return c.compress(b)+c.flush()
def amf(obj): return rawdef(wf_dsl.encode_amf3(obj))
def png(im):
    out=io.BytesIO();im.save(out,format='PNG',compress_level=9)
    return wf_assets.png_encode(out.getvalue())
def decode(b):
    try: return p.csvrows(b)
    except zlib.error: return {k:decode(v) for k,v in p.rawmap(b).items()}
def encode(obj):
    if isinstance(obj,dict): return p.packmap({k:encode(v) for k,v in obj.items()})
    return p.packcsv(obj)
def jsonbytes(obj): return (json.dumps(obj,ensure_ascii=False,indent=2)+'\n').encode('utf-8')

def pool_from_native(donor, characters):
    pool={}
    for bucket,rank in [('1',5),('2',4),('3',3)]:
        entries=donor['pool'][bucket]
        assert all(e['isLimited'] is False and e['id'] not in NON_GACHA_CHARACTER_IDS for e in entries)
        assert len({e['id'] for e in entries})==len(entries)
        assert all(characters[str(e['id'])]['rarity']==rank for e in entries)
        pool[bucket]=[{**e,'odds':1,'isRateUp':False,'isLimited':False,'isExchangeable':False,'trialReadingForced':False} for e in entries]
    n=len(pool['1'])
    for e in pool['1']:e['odds']=12
    pool['1']=[{'id':i,'rank':5,'odds':4*n,'isRateUp':True,'isLimited':True,'isExchangeable':True,'trialReadingForced':False} for i in MODS]+pool['1']
    divisor=math.gcd(*(e['odds'] for e in pool['1']))
    for e in pool['1']:e['odds']//=divisor
    for entries in pool.values():
        weight=sum(e['odds'] for e in entries)
        for e in entries:e['rarity']=1000*e['odds']/weight
    total=sum(e['odds'] for e in pool['1'])
    assert Fraction(5,100)*Fraction(pool['1'][0]['odds'],total)==Fraction(1,300)
    return pool

def movie_assets(art, work):
    root=MOVIE.rsplit('/',1)[0]
    names=['background','hibiki','black','fluffy','mia','title']
    files=['animation-background.png','character-references/169988-1.png','character-references/139991-1.png','character-references/149987-1.png','character-references/119992-1.png','animation-title.png']
    images=[]; receipt=[]
    for name,file in zip(names,files):
        path=art/file; original=Image.open(path).convert('RGBA')
        receipt.append({'file':file,'sha256':p.sha(path.read_bytes()),'size':list(original.size)})
        if name=='background': size=(720,895)
        elif name=='title':size=(640,round(640*original.height/original.width))
        else:size=(round(original.width*700/original.height),700)
        images.append(original.resize(size,Image.Resampling.LANCZOS))
    sheet=Image.new('RGBA',(2048,2048))
    atlas=[];x=y=1;rowh=0
    for name,im in zip(names,images):
        if x+im.width+1>2048:x=1;y+=rowh+2;rowh=0
        assert y+im.height+1<=2048
        sheet.paste(im,(x,y))
        atlas.append({'n':f'{root}/.gen/feature/{name}','x':x,'y':y,'w':im.width,'h':im.height})
        x+=im.width+2;rowh=max(rowh,im.height)
    # Full-width scene coordinates; the native page clips the central 1080 px.
    # Keep faces and title in that safe region. No date labels are baked in.
    placements=[(0,0,1440), (150,0,630), (690,40,660), (40,365,780), (650,365,730), (220,700,1000)]
    matrices=[];segments=[]
    def matrix(im,x,y,width):
        s=width/im.width
        val={'a':round(s*4096),'b':0,'c':0,'d':round(s*4096),'x':round(x*4096),'y':round(y*4096)}
        if val not in matrices:matrices.append(val)
        return matrices.index(val)
    def key(im,x,y,width,alpha,duration):return {'m':(matrix(im,x,y,width)<<12)|round(alpha*255),'t':duration}
    total=302
    for i,(im,(x,y,w)) in enumerate(zip(images,placements)):
        frames=[]
        for t in range(total):
            delay=4+i*5
            progress=max(0,min(1,(t-delay)/22))
            ease=1-(1-progress)**3
            if i==0:xx,yy,ww,alpha=x,y,w,1
            elif i==5:
                scale=.87+.13*ease
                # Gentle two-second title breathing; exactly joins the loop.
                scale*=1+.008*math.sin(2*math.pi*(t-61)/240) if t>=61 else 1
                ww=w*scale;xx=x+(w-ww)/2;yy=y+(1-ease)*55;alpha=progress
            else:
                xx=x+(1-ease)*(-115 if i in (1,3) else 115)
                yy=y+(1-ease)*40
                if t>=61: yy+=5*math.sin(2*math.pi*(t-61)/240)
                ww=w;alpha=progress
            frames.append(key(im,xx,yy,ww,alpha,1))
        segments.append({'s':0,'i':i,'l':frames})
    timeline={'sequences':[{'begin':1,'end':61,'name':'start','kind':'pass'}, {'begin':62,'end':300,'name':'idle','kind':'pass'}, {'begin':301,'end':302,'name':'end','kind':'goto','target':'idle'}], 'sounds':[],'points':[],'circles':[],'rectangles':[],'matrices':[]}
    movie={'i':[{'s':True,'p':a['n']} for a in atlas], 'g':[{'t':total,'s':segments}], 'm':[],'a':[1]*len(images),'o':[],'t':matrices,'c':[],'s':1,'l':timeline}
    sheet.save(work/'animation-sheet.png');p.savej(work/'animation-atlas.json',atlas);p.savej(work/'animation-movie.json',movie)
    return {f'{root}/sprite_sheet.png':png(sheet), f'{root}/sprite_sheet.atlas.amf3.deflate':amf(atlas), f'{MOVIE}.movie.amf3.deflate':amf(movie), f'{MOVIE}.timeline.amf3.deflate':amf(timeline)},receipt

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--art-dir',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);args=ap.parse_args()
    work=args.work.resolve();assert not work.is_relative_to((REPO/'.cdn').resolve());work.mkdir(parents=True,exist_ok=True)
    c=p.Chain();assert c.tail=='1.4.117',f'rebase candidate first: {c.tail}'
    assets={};logicals={};server={};before={};source_art=[]
    def get(logical,root='common'):
        b=c.get((root,p.hrel(logical)));assert b is not None,(root,logical);return b
    def put(logical,b,root='common'):
        k=(root,p.hrel(logical));assets[k]=b;logicals[k]=logical
    def new(logical,b,root='common'):
        assert c.get((root,p.hrel(logical))) is None,f'occupied resource: {logical}'
        put(logical,b,root)
    def append(logical,key,value):
        old=get(logical);rows=p.rawmap(old);assert key not in rows,(logical,key)
        updated={**rows,key:value};packed=p.packmap(updated)
        assert p.rawmap(packed)==updated
        put(logical,packed)
    def server_write(rel,obj):
        path=REPO/rel;before[rel]=p.sha(path.read_bytes()) if path.exists() else None;server[rel]=jsonbytes(obj)
    def mirror_add(rel,key,value):
        obj=p.readj(REPO/rel);assert key not in obj;obj[key]=value;server_write(rel,obj)
    gachas={**p.readj(REPO/'assets/gacha.json'),**p.readj(REPO/'assets/gacha_cnmod.json'),**p.readj(REPO/'assets/gacha_rank_p5b.json')}
    assert GID not in gachas
    chars={**p.readj(REPO/'assets/character.json'),**p.readj(REPO/'assets/character_rank_p5b.json')}
    assert all(chars[str(i)]['rarity']==5 for i in MODS)
    donor=gachas['1675'];pool=pool_from_native(donor,chars)
    # Verify the chosen permanent donor against actual effective client odds.
    donor_row=p.csvrows(p.rawmap(get(GACHA_T))['1675'])[0]
    for index,bucket in [(16,'1'),(15,'2'),(14,'3')]:
        table=decode(get(f'master/gacha_odds/{donor_row[index]}.orderedmap'))[donor_row[index]]
        assert {int(v[0][0]) for v in table.values()}=={e['id'] for e in donor['pool'][bucket]}
        assert all(v[0][4]=='false' for v in table.values())
    row=copy.deepcopy(donor_row)
    changes={0:CODE,1:TITLE,2:'3',3:f'dynamic/gacha_list_banner/{CODE}',11:f'{CODE}_rarity',12:f'rich_text/{CODE}_note',14:f'{CODE}_character_3',15:f'{CODE}_character_4',16:f'{CODE}_character_5',27:'(None)',28:IID,29:'2020-12-31 12:00:00',30:'2199-12-31 23:59:59',44:'true'}
    for i,v in changes.items():row[i]=v
    assert row[4]=='4' and row[20]=='false' and len(row)==47
    append(GACHA_T,GID,p.packcsv([row]))
    feature=['0','',MOVIE,'','','','(None)','','']
    append(FEATURE_T,GID,encode({'1':[feature]}))
    runtime={k:copy.deepcopy(v) for k,v in donor.items() if k!='pool'}
    runtime.update(name=TITLE,pageKind=4,tenTicketItemId=int(IID),wildcardTicketAvailable=False,rarityOddsId=row[11],rankRates={'normal':[50,350,600],'multiGuarantee':[50,950]},startDate=row[29],endDate=row[30],pool=pool)
    runtime.pop('onceTicketItemId',None)
    server_write('assets/gacha_midautumn_2026.json',{GID:runtime})
    mirror_add('assets/cdndata/gacha.json',GID,[row]);mirror_add('assets/cdndata/gacha_feature_content.json',GID,{'1':[feature]})
    for rank,bucket in [(5,'1'),(4,'2'),(3,'3')]:
        code=f'{CODE}_character_{rank}'
        entries={str(n):[[str(e['id']),str(rank),str(e['odds']),*[str(e[k]).lower() for k in ['isRateUp','isLimited','isExchangeable','trialReadingForced']]]] for n,e in enumerate(pool[bucket])}
        new(f'master/gacha_odds/{code}.orderedmap',encode({code:entries}))
    new(f'master/gacha_odds/{CODE}_rarity.orderedmap',encode({f'{CODE}_rarity':{str(i):[[str(rank),str(weight)]] for i,(rank,weight) in enumerate([(5,50),(4,350),(3,600)])}}))
    note=f'rich_text/{CODE}_note';append('master/rich_text/rich_text_html.orderedmap',note,p.packcsv([['']]))
    html='''<!DOCTYPE html/><html lang="zh-CN"><head><meta charset="utf-8"/><title>中秋·国庆限定扭蛋注意事项</title><link rel="stylesheet" type="text/css" href="style.css"/></head><body class="body" style_id="1"><div class="container">
<p>・活动期间：现实北京时间 2026-09-25 12:00 至 2026-10-09 12:00。</p><br/>
<p>・1个月饼可进行1次角色10连抽取，仅接受本池专用月饼。</p><br/>
<p>・普通抽位：★5为5%，★4为35%，★3为60%。</p><br/>
<p>・每十连的第10位保证★4及以上：★5为5%，★4为95%。</p><br/>
<p>・12位MOD角色合计出现概率4%，每位为1/3%（约0.3333%）；常驻★5合计1%。保底位的★5分配相同。</p><br/>
<p>・每抽获得1点本池兑换点数。12位MOD角色均可各使用250点兑换；常驻陪跑角色不开放兑换。</p><br/>
<p>・重复获得角色时按现有游戏规则处理。</p></div></body></html>'''
    new(note+'.html.deflate',rawdef(html.encode('utf-8')))
    icon='item/spends/tickets/midautumn_mooncake_ten_ticket'
    item=p.csvrows(p.rawmap(get(ITEM_T))['999001'])[0]
    item[0]='midautumn_mooncake_ten_ticket';item[1]=IID;item[2]='中秋月饼';item[3]=icon;item[5]='可用于进行1次「中秋·国庆限定扭蛋」角色10连抽取的专用月饼';assert item[13]=='2'
    append(ITEM_T,IID,p.packcsv([item]))
    mirror_add('assets/item_lookup_cnmod.json',IID,item[2])
    item_ids=p.readj(REPO/'assets/item_ids.json');assert int(IID) not in item_ids and int(IID) not in p.readj(REPO/'assets/item_ids_rank_p5b.json')
    server_write('assets/item_ids.json',[*item_ids,int(IID)])
    # This registry uses unindented one-integer-per-line formatting.
    server['assets/item_ids.json']=('[\n'+',\n'.join(map(str,[*item_ids,int(IID)]))+'\n]\n').encode('utf-8')
    ticket=TicketSpec(IID,'999001',item[0],item[2],item[5],'2',icon,'midautumn-mooncake-ticket.png')
    compiled=compile_item_assets(get('item/sprite_sheet.png'),get('item/sprite_sheet.atlas.amf3.deflate'),args.art_dir,expected_sha256={ticket.source_name:MOON_SHA},specs=(ticket,))
    put('item/sprite_sheet.png',compiled.sheet_payload);put('item/sprite_sheet.atlas.amf3.deflate',compiled.atlas_payload)
    new(icon+'.png',wf_assets.png_encode((args.art_dir/ticket.source_name).read_bytes()))
    # List banners are unscaled; full main stills also supply the scaled medium root.
    for file,logical,size,roots in [('midautumn-list-v2.png',row[3],(510,180),['common']),('main-four-characters-v3.png',f'dynamic/gacha_banner/{CODE}',(1440,1789),['common','medium'])]:
        src=args.art_dir/file;im=Image.open(src).convert('RGBA');source_art.append({'file':file,'sha256':p.sha(src.read_bytes())})
        for root in roots:
            dest=size if root=='common' else (720,895)
            new(logical+'.png',png(im.resize(dest,Image.Resampling.LANCZOS)),root)
    movie,art_receipts=movie_assets(args.art_dir,work);source_art.extend(art_receipts)
    for logical,b in movie.items():new(logical,b)
    archive='pinball-1.4.117-1.4.118-1-midautumn-national-2026.zip'
    dest=work/'files/assets/asset-patch/active'/archive;dest.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(dest,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for k,b in sorted(assets.items()):
            entry=zipfile.ZipInfo(p.member(k),date_time=(2026,9,24,0,0,0));entry.compress_type=zipfile.ZIP_DEFLATED;z.writestr(entry,b)
    with zipfile.ZipFile(dest) as z:assert z.testzip() is None
    manifest=copy.deepcopy(c.manifest)
    patch={'id':'midautumn-national-2026','version':'1.4.118','depends_on':c.tail,'archive':archive,'enabled':True,'description':'中秋国庆独立月饼十连池与原生横幅动画','archive_integrity':[{'name':archive,'size':dest.stat().st_size,'sha256':p.sha(dest.read_bytes())}], 'affected_paths':[p.member(k) for k in sorted(assets)], 'audit':{'directory':'assets/asset-patch/audit/midautumn-national-2026'}, 'changes':['新增12位MOD与常驻陪跑池，五星5%，12位MOD可250点兑换。','新增独立月饼十连券、共享图标和无日期横幅动画。']}
    patch.update(type='patch',name='中秋·国庆月饼十连池',archive_size=dest.stat().st_size,files=patch.pop('affected_paths'),chain=[archive],created_at='2026-09-24')
    patch['archive_integrity'][0]['members']=len(assets)
    manifest['cdn_version']='1.4.118';manifest['patches'].append(patch)
    server_write('assets/asset-patch/manifest.json',manifest)
    for rel,b in server.items():
        dest=work/'files'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
    report={'base_version':c.tail,'version':'1.4.118','gacha_id':int(GID),'item_id':int(IID),'mod_ids':MODS,'permanent_donor':1675,'pool_counts':{k:len(v) for k,v in pool.items()},'rank_rates':runtime['rankRates'],'mod_each_rate':'1/300','exchange_cost':250,'asset_sources':c.reads,'art_sources':source_art,'assets':[{'root':k[0],'logical':logicals[k],'member':p.member(k),'sha256':p.sha(b)} for k,b in sorted(assets.items())],'server_preimages':before,'status':'offline candidate; device and runtime deployment not performed','save_impact':'Existing portable players_items and players_gacha_info tables; no schema change. Acquisition shop deferred; no source navigation invented.'}
    p.savej(work/'report.json',report)
    print(json.dumps({k:report[k] for k in ['version','gacha_id','item_id','pool_counts','rank_rates']},ensure_ascii=False))
    print('Assets:',len(assets),'Archive bytes:',(work/'files/assets/asset-patch/active'/archive).stat().st_size)

if __name__=='__main__':main()
