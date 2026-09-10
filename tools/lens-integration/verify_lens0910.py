"""Validate the integrated sparse assets and declared table/server deltas."""
import argparse,io,json,os,re,zlib
from pathlib import Path
import prepare_content as p
import fix_five_boss_icon_closure as closure
import wf_dsl,wf_dsl_sig
from wf_siete_balance import _normalize_for_signature
from PIL import Image

def strings(value):
    if isinstance(value,str):yield value
    elif isinstance(value,(list,tuple)):
        for v in value:yield from strings(v)
    elif isinstance(value,dict):
        for v in value.values():yield from strings(v)
def table_strings(raw):
    try:rows=p.rawmap(raw)
    except Exception:
        yield from strings(p.csvrows(raw))
    else:
        for row in rows.values():yield from table_strings(row)
def validate(work,server,pristine):
    report=p.readj(work/'prepared.json')
    os.environ.update(WF_SERVER_DIR=str(server),WF_CDN_DIR=str(pristine),WF_LIVE_CDN='1')
    import wf_live_cdn as live
    live.clear_cache();assert live.describe()['tail'] in ['1.4.111','1.4.112']
    resources={(r['root'],r['logical']):(work/'after'/r['root']/r['logical']).read_bytes() for r in report['resources']}
    for row in report['resources']:assert p.sha(resources[(row['root'],row['logical'])])==row['sha256']
    def read(logical,root='common'):
        if (root,logical) in resources:return resources[(root,logical)]
        return live.read_relative(p.hrel(logical),roots=(root,)).data
    refs=set();media=[];dsl=[];atlases=[]
    for (root,logical),raw in resources.items():
        if logical.endswith('.png'):
            with Image.open(io.BytesIO(p.wf_assets.png_decode_stored(raw))) as im:im.load();media.append(dict(root=root,logical=logical,size=list(im.size)))
        elif logical.endswith('.mp3'):
            probe=p.wf_assets.mp3_probe(raw,1023);assert probe['frames']>0 and probe['tail']<=512 and len(probe['bitrates'])==1;media.append(dict(root=root,logical=logical,frames=probe['frames']))
        elif logical.endswith('.action.dsl.amf3.deflate'):
            tree=wf_dsl.parse_dsl(zlib.decompress(raw,-15))['tree']
            wf_dsl_sig.validate_action_dsl(_normalize_for_signature(tree,logical))
            after=wf_dsl.parse_dsl(wf_dsl.encode_amf3(tree))['tree'];assert after==tree
            wf_dsl_sig.validate_action_dsl(_normalize_for_signature(after,logical));refs.update(strings(tree));dsl.append(logical)
        elif logical.endswith('.atlas.amf3.deflate'):
            rows=closure.codec.decode_atlas(raw);assert len({r['n'] for r in rows})==len(rows)
            png=logical.replace('.atlas.amf3.deflate','.png')
            with Image.open(io.BytesIO(p.wf_assets.png_decode_stored(read(png,root)))) as im:
                for r in rows:assert 0<=r['x']<r['x']+r['w']<=im.width and 0<=r['y']<r['y']+r['h']<=im.height,(logical,r)
            atlases.append(dict(root=root,logical=logical,frames=len(rows)))
        elif logical.endswith('.orderedmap'):
            rows=p.rawmap(raw)
            changed=next(t['changed_keys'] for t in report['tables'] if t['logical']==logical)
            for key in changed:refs.update(table_strings(rows[key]))
    paths=set()
    for value in refs:
        for logical in re.findall(r'battle/(?:action|terrain)/[A-Za-z0-9_/$.-]+',value):
            if logical.startswith('battle/action/'):
                if '$' not in logical:continue
                if not logical.endswith('.action.dsl.amf3.deflate'):logical+='.action.dsl.amf3.deflate'
            elif not logical.endswith('.amf3.deflate'):logical+='.amf3.deflate'
            read(logical);paths.add(logical)
    ability=p.rawmap(read('master/ability/ability.orderedmap'))
    leader=p.rawmap(read('master/ability/leader_ability.orderedmap'))
    text=p.rawmap(read('master/character/character_text.orderedmap'))
    native={rel:p.readj(work/'server-after/assets'/rel) for rel in report['server_files']}
    for rel,ids in [('cdndata/character.json',['129992']),('cdndata/character_text.json',['129992','149990','169994'])]:
        client=p.rawmap(read('master/character/'+Path(rel).name.replace('.json','.orderedmap')))
        for key in ids:
            assert p.csvrows(client[key])==native[rel][key],('client/server drift',rel,key)
    assert native['cdndata/character_text.json']['169994']==native['cdndata/character_text_rank_p5b.json']['169994']
    pool_receipts=[]
    for key,rel,code in [('990001','gacha_cnmod.json','cnmod_abyss_limited'),('990002','gacha_rank_p5b.json','cnmod_ashen_verdict')]:
        server_pool=native[rel][key]['pool']['1']
        logical='master/gacha_odds/'+code+'_gacha_character_5.orderedmap'
        client_pool=[p.csvrows(v)[0] for v in p.rawmap(next(iter(p.rawmap(read(logical)).values()))).values()]
        expected=[[str(v['id']),str(v['rank']),str(v['odds']),*[str(v[k]).lower() for k in ['isRateUp','isLimited','isExchangeable','trialReadingForced']]] for v in server_pool]
        assert client_pool==expected,(key,'client server pool mismatch')
        if key=='990001':
            assert server_pool[0]['id']==149990 and server_pool[0]['odds']==0 and not server_pool[0]['isExchangeable']
            assert native['gacha.json'][key]==native[rel][key]
            assert next(v for v in server_pool if v['id']==131182)['isExchangeable']
        else:assert not any(v['id']==149990 for v in server_pool)
        old=p.readj(work/'server-before/assets'/rel)[key]['pool']['1']
        assert [v for v in server_pool if v['id']!=149990]==[v for v in old if v['id']!=149990]
        pool_receipts.append(dict(id=key,count=len(server_pool),total=sum(v['odds'] for v in server_pool)))
    # Retain the existing fixed icon dimensions and all thirty tower resources.
    import five_boss_art_contract as art
    display=art.validate_display(read)
    previous=p.readj(p.REPO/'assets/asset-patch/audit/five-boss-item-art-1.4.111-test/resource-inventory.json')
    preserved=0
    for row in previous:
        key=('common',row['logical'])
        if key not in resources:assert p.sha(read(row['logical']))==row['sha256'];preserved+=1
    # The user's summer ability-6 choice is exact, and local Kyubi fixes survive.
    donor=p.readj(Path('F:/codex/work/audit-lens0910-20260910/wfshare-1.4.358-to-1.4.359-graft/client-tables/client_tables_payload.json'))
    import base64
    summer=donor['master/ability/ability.orderedmap']['1499906']
    assert p.csvrows(ability['1499906'])==p.csvrows(base64.b64decode(summer['after']))
    kyubi=p.csvrows(leader['139995']);assert len(kyubi)==11 and kyubi[2][108:110]==['0',''] and kyubi[9][49:51]==['-1000000','-1000000']
    result=dict(status='passed',resources=len(resources),dsl_count=len(dsl),dsl=dsl,media_count=len(media),atlas_checks=atlases,direct_references=sorted(paths),pool_checks=pool_receipts,previous_resources_preserved=preserved,icon_display=display,summer_ability6_author_exact=True,kyubi_existing_fixes_preserved=True,device_tested=False,desktop_air_run=False)
    p.savej(work/'resource-verification.json',result)
    print(json.dumps({k:result[k] for k in ['status','resources','dsl_count','media_count','pool_checks','previous_resources_preserved']},ensure_ascii=False))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);ap.add_argument('--server',type=Path,required=True);ap.add_argument('--pristine',type=Path,required=True);a=ap.parse_args();validate(a.work,a.server,a.pristine)
