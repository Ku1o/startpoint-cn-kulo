"""Build a sparse 1033-to-1043 resource increment from the effective local chain."""
from __future__ import annotations
import argparse, concurrent.futures, copy, hashlib, importlib.util, io, json, sys, zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'tools/fantasy-gauntlet-mod-tools'))
import wf_assets, wf_atf, wf_dsl, wf_dsl_sig
from PIL import Image

VERSION='1.4.117'
ARCHIVE='pinball-1.4.116-1.4.117-1-author-1043-and-content-fixes.zip'
EXCHANGE_IDS={119993,119994,119995,129993,129994,129995,129996,129998,139996,149991,149992,149993,149994,159999,169993}
PROTECTED_IDS={119992,119991,119990,139992,139991,139990,149987,149986,159995,159994,169991,169988}
INAHO_PREFIX='battle/action/skill/action/rare5/cnmod_inaho_midautumn$cnmod_inaho_midautumn_'
sha=lambda b:hashlib.sha256(b).hexdigest()
def loadj(p):return json.loads(p.read_text(encoding='utf-8'))
def jsonb(v):return (json.dumps(v,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
def relative(logical):
    s=hashlib.sha1((logical+'K6R9T9Hz22OpeIGEWB0ui6c6PYFQnJGy').encode()).hexdigest()
    return s[:2]+'/'+s[2:]
def member(logical,root='upload'):return f'production/{root}/{relative(logical)}'
def semantic(v):
    if isinstance(v,dict):return {k:semantic(x) for k,x in v.items() if k!='raw'}
    if isinstance(v,list):return [semantic(x) for x in v]
    return v
def walk(v):
    if isinstance(v,list):
        yield v
        for x in v:yield from walk(x)
    elif isinstance(v,dict):
        for x in v.values():yield from walk(x)

def check_inaho(tree):
    nodes=[n for n in walk(tree) if n and n[0]=='DeleteCondition' and isinstance(n[2],list) and n[2][0]=='DCAll']
    assert len(nodes)==5
    assert sum(n[1]==5 and n[2]==['DCAll',2] for n in nodes)==4
    assert sum(n[1]==6 and n[2]==['DCAll',3] for n in nodes)==1
    assert all(n[3]==1 and n[4]==0 for n in nodes)

def repair_inaho(raw):
    original=wf_dsl.parse_dsl(wf_atf.inflate(raw))['tree'];tree=copy.deepcopy(original)
    nodes=[n for n in walk(tree) if n and n[0]=='DeleteCondition' and isinstance(n[2],list) and n[2][0]=='DCAll']
    assert len(nodes)==5
    before=[]
    for n in nodes:
        expected,new=(0,2) if n[1]==5 else (1,3)
        assert n[1] in (5,6) and n[2][1]==expected
        before.append(n[2][1]);n[2][1]=new
    check_inaho(tree);wf_dsl_sig.validate_action_dsl(tree)
    encoded=wf_atf.deflate(wf_dsl.encode_amf3(tree))
    readback=wf_dsl.parse_dsl(wf_atf.inflate(encoded))['tree']
    assert readback==tree;check_inaho(readback)
    restored=copy.deepcopy(tree)
    target=[n for n in walk(restored) if n and n[0]=='DeleteCondition' and isinstance(n[2],list) and n[2][0]=='DCAll']
    for n,value in zip(target,before):n[2][1]=value
    assert restored==original
    return encoded

def ios_one(job):
    logical,android,png=job
    decoded=wf_assets.png_decode_stored(png)
    a=wf_atf.inflate(android);i=wf_atf.build_cutin_atf_ios(decoded,ref_atf=a)
    proof=wf_atf.validate_cutin_platform_pair(a,i,decoded)
    return member(logical,'ios_upload'),wf_atf.deflate(i),proof

def build(donor,work):
    out=work/'candidate';before=work/'before'
    codec_path=donor/'receiver/wf_share_update_codec.py'
    spec=importlib.util.spec_from_file_location('codec1043',codec_path)
    codec=importlib.util.module_from_spec(spec);spec.loader.exec_module(codec)
    manifest_path=ROOT/'assets/asset-patch/manifest.json'
    manifest=loadj(manifest_path);assert manifest['cdn_version']=='1.4.116'
    current=loadj(donor/'tables/client_payload.json')
    base=loadj(donor/'baselines/1.4.1033/client_payload.json')
    assets=loadj(donor/'asset-manifest.json')['assets']
    gacha=[f'master/gacha_odds/cnmod_abyss_limited_gacha_character_{rank}.orderedmap' for rank in (5,4,3)]
    logicals=set(current['tables'])|set(gacha)|{INAHO_PREFIX+str(n)+'.action.dsl.amf3.deflate' for n in (1,2)}
    names={member(l) for l in logicals}|{a['member'] for a in assets}
    effective={};sources={};chain=[]
    for edge in manifest['patches']:
        if not edge.get('enabled',True):continue
        for name in edge.get('chain') or [edge['archive']]:
            p=ROOT/'assets/asset-patch/active'/name
            assert p.is_file(),p
            chain.append({'archive':name,'sha256':sha(p.read_bytes())})
            with zipfile.ZipFile(p) as z:
                for n in names.intersection(z.namelist()):
                    effective[n]=z.read(n);sources[n]=name
    assert all(member(l) in effective for l in logicals)
    payloads={};changed=[];preserved_degrees=0
    def encode(v):
        if 'children' in v:return codec.pack({k:encode(x) for k,x in v['children'].items()})
        return codec.leaf_raw(v)
    def update(rows,path,expected,after):
        key,*rest=path
        if rest:
            child=codec.unpack(rows[key]);update(child,rest,expected,after);rows[key]=codec.pack(child)
        else:
            observed=codec.node(rows[key]) if key in rows else None
            assert semantic(observed)==semantic(expected),('table conflict',path)
            rows[key]=encode(after)
    maps={l:codec.unpack(effective[member(l)]) for l in current['tables']}
    for logical,table in current['tables'].items():
        previous={tuple(op['path']):op for op in base['tables'][logical]['operations']}
        for op in table['operations']:
            # The selected baseline payload contains the migration *from* 1033
            # to the final donor; its preimage is the accepted 1033 value.
            prior=previous[tuple(op['path'])]['before']
            if logical=='master/degree/degree.orderedmap':
                assert semantic(prior)==semantic(op['after']);preserved_degrees+=1;continue
            if semantic(prior)==semantic(op['after']):continue
            update(maps[logical],op['path'],prior,op['after'])
            changed.append({'logical':logical,'path':op['path']})
        if any(row['logical']==logical for row in changed):payloads[member(logical)]=codec.pack(maps[logical])
    assert len(changed)==35 and preserved_degrees==27,(len(changed),preserved_degrees,changed)
    # Only exchange eligibility changes. All weights, native IDs and other pools remain intact.
    exchange_seen=set()
    for logical in gacha:
        root=codec.unpack(effective[member(logical)]);original=copy.deepcopy(root)
        for outer,raw in root.items():
            rows=codec.unpack(raw)
            for key,leaf in rows.items():
                csv=codec.csv_read(leaf);cid=int(csv[0][0])
                if cid in EXCHANGE_IDS:
                    assert csv[0][5]=='false';csv[0][5]='true';rows[key]=codec.csv_write(csv);exchange_seen.add(cid)
            root[outer]=codec.pack(rows)
        if root!=original:payloads[member(logical)]=codec.pack(root)
    assert exchange_seen==EXCHANGE_IDS
    media=[];ios_jobs=[];small_count=0
    media_by_logical={(a['root'],a['logical']):a for a in assets}
    with zipfile.ZipFile(donor/'assets/最终角色资源.zip') as z:
        for asset in assets:
            raw=z.read(asset['member']);assert sha(raw)==asset['sha256']
            if int(asset['source_version'].split('.')[-1])<=1033:
                assert effective.get(asset['member'])==raw,('unexpected pre-1033 drift',asset['logical']);continue
            if effective.get(asset['member'])==raw:continue
            payloads[asset['member']]=raw
            media.append({'logical':asset['logical'],'root':asset['root'],'sha256':sha(raw)})
            logical=asset['logical']
            if logical.endswith('.png'):
                png=wf_assets.png_decode_stored(raw)
                with Image.open(io.BytesIO(png)) as im:
                    im.load()
                    if asset['root']=='medium' and logical.startswith('character/') and '/ui/' in logical and '/ui/skill_cutin_' not in logical:
                        scaled=im.resize((int(im.width*.7),int(im.height*.7)),Image.Resampling.LANCZOS)
                        stream=io.BytesIO();scaled.save(stream,format='PNG')
                        payloads[member(logical,'small_upload')]=wf_assets.png_encode(stream.getvalue());small_count+=1
            if asset['root']=='android':
                assert logical.endswith('.atf.deflate')
                png_logical=logical.removesuffix('.atf.deflate')+'.png'
                png_asset=media_by_logical.get(('medium',png_logical)) or media_by_logical[('common',png_logical)]
                ios_jobs.append((logical,raw,z.read(png_asset['member'])))
    assert len(ios_jobs)==14
    ios_report=[]
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        for name,raw,proof in pool.map(ios_one,ios_jobs):
            payloads[name]=raw;ios_report.append({'member':name,'sha256':sha(raw),'pair':proof})
            print('ios_pair',len(ios_report),len(ios_jobs),flush=True)
    for n in (1,2):
        logical=INAHO_PREFIX+str(n)+'.action.dsl.amf3.deflate';old=effective[member(logical)]
        assert sha(old)=='22a566c867b96856fa3e52c9552d97c23c9df39769cefa0a5dcf2600400f0af3'
        payloads[member(logical)]=repair_inaho(old)
        p=before/('inaho-'+str(n)+'.dsl.deflate');p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(old)
    server={}
    for relative_path in ('assets/gacha.json','assets/gacha_cnmod.json'):
        original=loadj(ROOT/relative_path);value=copy.deepcopy(original);seen=set()
        for bucket in value['990001']['pool'].values():
            for row in bucket:
                if row['id'] in EXCHANGE_IDS:
                    assert row['isExchangeable'] is False;row['isExchangeable']=True;seen.add(row['id'])
                if row['id'] in PROTECTED_IDS:assert row['odds']==0
        assert seen==EXCHANGE_IDS
        server[relative_path]=jsonb(value)
    text_path='assets/cdndata/character_text.json';texts=loadj(ROOT/text_path)
    for cid in ('149987','129992'):
        texts[cid]=codec.node(maps['master/character/character_text.orderedmap'][cid])['csv']
    overrides=loadj(ROOT/'assets/cdndata/character_text_rank_p5b.json')
    assert not {'149987','129992'}&set(overrides)
    server[text_path]=jsonb(texts)
    archive_path=out/'assets/asset-patch/active'/ARCHIVE;archive_path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(archive_path,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(payloads.items()):
            assert name.startswith('production/') and '..' not in Path(name).parts
            info=zipfile.ZipInfo(name,(2026,9,24,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o100644<<16;z.writestr(info,raw)
    with zipfile.ZipFile(archive_path) as z:
        assert z.testzip() is None
        assert set(z.namelist())==set(payloads)
        for name,raw in payloads.items():assert z.read(name)==raw
    archive_hash=sha(archive_path.read_bytes())
    manifest['cdn_version']=VERSION
    manifest['patches'].append({'id':'author-1043-content-fixes-20260924','type':'patch',
        'name':'角色内容1043与稻穗及兑换修复','description':'角色数值、语音、立绘及双平台纹理；稻穗状态清除和15个旧MOD兑换修复。',
        'version':VERSION,'depends_on':'1.4.116','enabled':True,'local_test_only':True,
        'archive':ARCHIVE,'archive_size':archive_path.stat().st_size,
        'archive_integrity':[{'name':ARCHIVE,'size':archive_path.stat().st_size,'sha256':archive_hash,'members':len(payloads),'files':sorted(payloads)}],
        'files':sorted(payloads),'audit':{'directory':'assets/asset-patch/audit/author-content-1043-1.4.117'},
        'changes':['更新作者1033之后的35项表差异及对应媒体，保持本服铭牌映射。',
                   '保留本服旧角色和稻穗资源，修正两形态状态清除参数。',
                   '开放普通深渊池15个旧MOD角色兑换，保持抽取权重及新12角色原配置。',
                   '生成14个iOS平台纹理配对及缩小图像资源。']})
    server['assets/asset-patch/manifest.json']=jsonb(manifest)
    originals={}
    for name,raw in server.items():
        originals[name]=sha((ROOT/name).read_bytes())
        dst=before/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes((ROOT/name).read_bytes())
        dst=out/name;dst.parent.mkdir(parents=True,exist_ok=True);dst.write_bytes(raw)
    report={'status':'candidate_not_activated','baseline':'1.4.116','target':VERSION,'archive':ARCHIVE,
            'archive_sha256':archive_hash,'members':len(payloads),'tables':changed,'media':media,
            'ios':ios_report,'small_images':small_count,'degree_entries_preserved':27,
            'exchange_ids':sorted(EXCHANGE_IDS),'protected_zero_weight_ids':sorted(PROTECTED_IDS),
            'source_chain':chain,'before_files':originals,'server_files':{p:sha(b) for p,b in server.items()},
            'save_impact':'Existing IDs and persistence schema unchanged; exchange uses the existing transaction path.',
            'device_tested':False,'ios_client_included':False}
    (work/'resource-report.json').write_bytes(jsonb(report))
    print(json.dumps({k:report[k] for k in ('archive','archive_sha256','members','small_images')}),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--donor',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    args=p.parse_args();build(args.donor,args.work)
