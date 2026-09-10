"""Sparse, preimage-checked integration of Lens 0910 over the .111 test chain.

Writes only --work. Keeps the held source manifest and runtime unmodified.
Author tools are read-only inputs; local pool policies remain authoritative.
"""
from __future__ import annotations
import argparse, base64, copy, importlib.util, json, os, re, sys, zlib
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import prepare_content as p

R=p.REPO
def save(path,raw):path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
def deflate(raw):
    c=zlib.compressobj(level=9,wbits=-15);return c.compress(raw)+c.flush()
def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def build(work,package,server,pristine):
    assert not (work/'prepared.json').exists(),'prepared output already exists'
    assert not work.resolve().is_relative_to((R/'.cdn').resolve())
    expected_inputs={
        'asset-manifest.json':'09312d9be8f99501581905eefca0b2b9edd0f4f3497de5826d37e822d3adaeeb',
        'client-tables/client_tables_payload.json':'03b1bfd52d985c0a69973019f41c5dff6882d8cbac518719c5b92638f1a36b87',
        'server-data/server_rows_payload.json':'0fbc32c94f56ad699ba7dec5d0eeee8a4b3ad9191a5b157ecd3b09a1ef3578ed',
        'client-tables/graft_codec.py':'1e2f2ede2caeab78087de8c9722ce7838a95bd7e78d07323b4eb28a7d418655c',
        'server-data/server_graft.py':'528efb750afe9ae398da41782758fae93d702a00a110d5ef7ab6b17a13b1a3cc',
    }
    assert all(p.sha((package/k).read_bytes())==v for k,v in expected_inputs.items()),'reviewed package input drift'
    codec=module('lens0910_codec',package/'client-tables/graft_codec.py')
    sg=module('lens0910_server_codec',package/'server-data/server_graft.py')
    payload=p.readj(package/'client-tables/client_tables_payload.json')
    audit=p.readj(work/'assets-preflight.json')
    os.environ.update(WF_SERVER_DIR=str(server),WF_CDN_DIR=str(pristine),WF_LIVE_CDN='1')
    import wf_live_cdn as live
    assert live.describe()['tail']=='1.4.111'
    before={};outputs={};receipts=[];loose_overrides=[]
    reviewed_loose={
        'character/claude_wolf_assassin_ex/pixelart/special_sprite_sheet.png':'6413e50ccbc5aad46520d33cad434b00a14f7cedb8c23f871f6aaa8a502b08d2',
        'character/claude_wolf_assassin_ex/pixelart/sprite_sheet.png':'c34d7c68d65aa89c3497fdf20b8615c60657a5eb915cdc566cd2fe5324481026',
    }
    def read(root,logical):
        key=(root,logical)
        if key not in before:
            try:raw=live.read_relative(p.hrel(logical),roots=(root,)).data
            except live.LiveCdnEntryMissing:raw=None
            before[key]=raw
            if raw is not None:save(work/'before'/root/logical,raw)
            dest=Path('F:/startpoint-cn-main/assets/asset-patch')/p.member((root,p.hrel(logical)))
            if dest.exists() and dest.read_bytes()!=raw:
                actual=dest.read_bytes()
                assert root=='common' and p.sha(actual)==reviewed_loose.get(logical),('runtime loose drift',logical)
                # Both actual overrides are Rolf art explicitly replaced by
                # this author's new blue/white pixel set, not unrelated data.
                save(work/'runtime-loose-before'/root/logical,actual)
                loose_overrides.append(dict(root=root,logical=logical,member=p.member((root,p.hrel(logical))),before_sha256=p.sha(actual),resolution='replace_with_requested_author_rolf_art'))
        return before[key]
    for row in audit:
        root,logical=row['root'],row['logical'];old=read(root,logical)
        assert (p.sha(old) if old is not None else None)==row['current_sha256']
        raw=(work/'donor'/root/logical).read_bytes();assert p.sha(raw)==row['sha256']
        resolution='author_update'
        if logical.startswith('rich_text/'):
            text=zlib.decompress(old,-15).decode('utf8')
            if 'abyss_limited' in logical:
                anchor='    <p>・杰拉尔、稻穗两名新角色各自UP'
                assert text.count(anchor)==1
                text=text.replace(anchor,'    <p>・夏日白展示于★5角色列表首位，出现概率为0.000%，不会被抽出，且不可兑换。</p><br/>\n'+anchor)
            else:
                line='<p>・夏日白虎仅作角色预览展示，抽取权重为 0，不可抽取或兑换。</p>'
                assert text.count(line)==1;text=text.replace(line+'\n','')
            raw=deflate(text.encode());resolution='local_policy_note_plus_summer_migration'
        elif row['state']=='conflict':
            assert 'fox_oracle_autumn$' in logical or 'unicorn_lancer_rose/pixelart/sprite_sheet.' in logical
            resolution='reviewed_author_skill_fix' if 'fox_oracle' in logical else 'author_pixel_pair'
        outputs[(root,logical)]=raw
        receipts.append(dict(root=root,logical=logical,resolution=resolution))
    table_receipts=[]
    for logical,changes in payload.items():
        old=read('common',logical);rows=p.rawmap(old);original=dict(rows)
        for key,node in changes.items():
            if '/gacha_odds/' in logical:
                nested=p.rawmap(rows[key]);old_items=[p.csvrows(v)[0] for v in nested.values()]
                assert len({v[0] for v in old_items})==len(old_items)
                if 'abyss_limited' in logical:
                    assert len(old_items)==255 and not any(v[0]=='149990' for v in old_items)
                    newrow=p.csvrows(codec.decode(node['children']['0']['after']))[0]
                    assert newrow==['149990','5','0','false','true','false','false']
                    items=[newrow,*old_items]
                else:
                    assert len(old_items)==287
                    selected=[v for v in old_items if v[0]=='149990'];assert len(selected)==1 and selected[0][2]=='0'
                    items=[v for v in old_items if v[0]!='149990']
                assert [v for v in items if v[0]!='149990']==[v for v in old_items if v[0]!='149990']
                assert sum(int(v[2]) for v in items)==sum(int(v[2]) for v in old_items)
                # Only positional keys change; retain every unchanged compressed leaf.
                by_id={p.csvrows(v)[0][0]:v for v in nested.values()}
                rows[key]=p.packmap({str(i):by_id.get(v[0],p.packcsv([v])) for i,v in enumerate(items)})
            elif logical=='master/ability/leader_ability.orderedmap' and key=='139995':
                ours=p.csvrows(rows[key]);author_before=p.csvrows(codec.decode(node['before']));author_after=p.csvrows(codec.decode(node['after']))
                assert len(ours)==11 and len(author_before)==len(author_after)==12
                recovered=copy.deepcopy(author_before[:11]);recovered[2][108:110]=['0','']
                assert ours==recovered,'unknown local Kyubi fix'
                expected=copy.deepcopy(author_before);expected[9][49:51]=['-1000000','-1000000']
                assert author_after==expected,'author leader delta changed'
                ours[9][49:51]=['-1000000','-1000000'];rows[key]=p.packcsv(ours)
                # Keep the local self-only Fever gain and removal of duplicate stack row.
            elif logical=='master/string/custom_ability_string.orderedmap' and key=='desc_override_fox_oracle_autumn':
                assert p.sha(rows[key])=='f15bb47f80d721680349ffc424196df64c0e812c9da027fea67ecff829f655be'
                text=zlib.decompress(codec.decode(node['after'])).decode()
                assert text.count('雷属性角色的FEVER获得量提升40％')==1
                text=text.replace('雷属性角色的FEVER获得量提升40％','自身FEVER获得量提升40％')
                rows[key]=zlib.compress(text.encode())
            else:
                result=codec.apply(p.core,rows.get(key),node,logical+'|'+key)
                if result is None:rows.pop(key,None)
                else:rows[key]=result
        assert [k for k in rows if k in original]==[k for k in original if k in rows]
        assert all(rows[k]==v for k,v in original.items() if k not in changes)
        raw=p.packmap(rows);assert p.rawmap(raw)==rows
        outputs[('common',logical)]=raw
        table_receipts.append(dict(logical=logical,changed_keys=[k for k in rows if rows[k]!=original.get(k)],unrelated_keys_preserved=True,key_order_preserved=True))
    for (root,logical),raw in outputs.items():
        save(work/'after'/root/logical,raw)
        if logical.endswith('.png'):
            decoded=p.wf_assets.png_decode_stored(raw)
            from PIL import Image
            import io
            with Image.open(io.BytesIO(decoded)) as im:im.load()
    # Produce actual iOS texture pairs from the same six supplied PNGs. This
    # does not alter an IPA or claim the three client hooks have an iOS port.
    jobs=[]
    for (root,logical),raw in list(outputs.items()):
        if root!='android':continue
        png_name=logical.replace('.atf.deflate','.png')
        candidates=[outputs.get((r,png_name)) for r in ('medium','common')]
        png=next((x for x in candidates if x is not None),None)
        assert png is not None,('missing texture source',logical)
        read('ios',logical)
        jobs.append((logical,p.wf_assets.png_decode_stored(png),raw,str(work/'after/ios'/logical)))
    assert len(jobs)==6
    pairs=[];pending=[]
    for job in jobs:
        logical,png,android,output=job;path=Path(output)
        if path.exists():
            proof=p.wf_atf.validate_cutin_platform_pair(p.wf_atf.inflate(android),p.wf_atf.inflate(path.read_bytes()),png)
            pairs.append(dict(logical=logical,path=str(path),sha256=p.sha(path.read_bytes()),png_sha256=p.sha(png),pair=proof))
            outputs[('ios',logical)]=path.read_bytes()
        else:pending.append(job)
    with ProcessPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(p.ios_job,j) for j in pending]):
            row=future.result();pairs.append(row);outputs[('ios',row['logical'])]=Path(row['path']).read_bytes();print('iOS pair',row['logical'],flush=True)
    # Apply only declared cells to all existing mirrors. Migrate the pool by ID
    # against each winning local extension, never the author's whole pool.
    sp=p.readj(package/'server-data/server_rows_payload.json');server_raw={};server_new={}
    extensions={'cdndata/character.json':['cdndata/character_rank_p5b.json'],'cdndata/character_text.json':['cdndata/character_text_rank_p5b.json']}
    for base,changes in sp['files'].items():
        if base=='gacha.json':continue
        for rel in [base,*extensions.get(base,[])]:
            raw=(R/'assets'/rel).read_bytes();value=json.loads(raw);original=copy.deepcopy(value)
            for key,node in changes.items():
                if key in value:value[key]=sg.merge(value[key],node['operations'],rel+'|'+key)
            if value!=original:server_raw[rel]=raw;server_new[rel]=value
    for rel in ['gacha.json','gacha_cnmod.json','gacha_rank_p5b.json']:
        raw=(R/'assets'/rel).read_bytes();value=json.loads(raw);original=copy.deepcopy(value)
        for key in ['990001','990002']:
            if key not in value:continue
            old=value[key]['pool']['1'];donor=sp['files']['gacha.json'][key]['after']['pool']['1']
            if key=='990001':
                assert len(old)==255 and not any(v['id']==149990 for v in old)
                summer,=[v for v in donor if v['id']==149990];assert summer['odds']==0 and not summer['isExchangeable'] and not summer['trialReadingForced']
                new=[summer,*old]
            else:
                assert len(old)==287 and len([v for v in old if v['id']==149990])==1
                new=[v for v in old if v['id']!=149990]
            assert [v for v in new if v['id']!=149990]==[v for v in old if v['id']!=149990]
            assert sum(v['odds'] for v in new)==sum(v['odds'] for v in old)
            value[key]['pool']['1']=new
        if value!=original:server_raw[rel]=raw;server_new[rel]=value
    for rel,obj in server_new.items():
        raw=server_raw[rel];runtime_raw=(Path('F:/startpoint-cn-main/assets')/rel).read_bytes()
        assert json.loads(runtime_raw)==json.loads(raw),('runtime server drift',rel)
        save(work/'server-before/assets'/rel,raw)
        save(work/'runtime-server-before/assets'/rel,runtime_raw)
        newline='\r\n' if b'\r\n' in raw else '\n'
        save(work/'server-after/assets'/rel,(json.dumps(obj,ensure_ascii=False,indent=2)+'\n').replace('\n',newline).encode())
    manifest=p.readj(server/'assets/asset-patch/manifest.json');assert manifest['cdn_version']=='1.4.111'
    protected=p.readj(R/'assets/asset-patch/audit/five-boss-item-art-1.4.111-test/report.json')['protected_local_hold_sha256']
    assert all(p.sha((R/rel).read_bytes())==digest for rel,digest in protected.items())
    report=dict(status='prepared_static_candidate',base_version='1.4.111',target_version='1.4.112',resource_count=len(outputs),resources=[dict(root=r,logical=l,member=p.member((r,p.hrel(l))),before_sha256=p.sha(before[(r,l)]) if before.get((r,l)) is not None else None,sha256=p.sha(b),size=len(b)) for (r,l),b in sorted(outputs.items())],asset_resolutions=receipts,tables=table_receipts,ios_pairs=sorted(pairs,key=lambda x:x['logical']),server_files=list(server_new),runtime_loose_overrides=loose_overrides,protected_local_hold_sha256=protected,user_choices=dict(gerald_text='author',summer_ability6='unchanged_author_configuration'),preserved_kyubi_fixes=['self_only_fever_gain','single_afterglow_source'],desktop_air_run=False,device_tested=False)
    p.savej(work/'prepared.json',report);print(json.dumps({k:report[k] for k in ['status','resource_count','server_files']},ensure_ascii=False),flush=True)

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);ap.add_argument('--package',type=Path,required=True);ap.add_argument('--server',type=Path,required=True);ap.add_argument('--pristine',type=Path,required=True);a=ap.parse_args();build(a.work,a.package,a.server,a.pristine)
