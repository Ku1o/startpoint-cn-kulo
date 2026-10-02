"""Verify serialized candidate assets and preservation against the prior chain."""
from __future__ import annotations
import argparse, copy, importlib.util, io, json, zipfile
from pathlib import Path
import build_resources as b
from PIL import Image

def verify(donor,work):
    spec=importlib.util.spec_from_file_location('codec1043_verify',donor/'receiver/wf_share_update_codec.py')
    c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)
    report=b.loadj(work/'resource-report.json');old=b.loadj(work/'before/assets/asset-patch/manifest.json')
    new=b.loadj(work/'candidate/assets/asset-patch/manifest.json')
    restored=copy.deepcopy(new);restored['patches'].pop();restored['cdn_version']=old['cdn_version']
    assert restored==old
    package=work/'candidate/assets/asset-patch/active'/b.ARCHIVE
    assert b.sha(package.read_bytes())==report['archive_sha256']
    with zipfile.ZipFile(package) as z:
        payload={n:z.read(n) for n in z.namelist()}
        assert len(payload)==len(z.namelist())==report['members']
    assert set(new['patches'][-1]['files'])==set(payload)
    assert new['patches'][-1]['depends_on']==old['cdn_version']
    donor_tables=b.loadj(donor/'tables/client_payload.json')['tables']
    assets=b.loadj(donor/'asset-manifest.json')['assets']
    voice_paths=[]
    for char,tails in [('unicorn_lancer_rose',['skill_ready']+['skill_ready_alt_'+str(i) for i in range(1,6)]),
                       ('super_robot_tailcoat',['skill_ready','matched_skill_ready','skill_ready_alt_2']),
                       ('samurai_robot_plum',['skill_ready','matched_skill_ready','skill_ready_alt_2','skill_ready_alt_3'])]:
        voice_paths.extend(f'character/{char}/voice/battle/{tail}.mp3' for tail in tails)
    required=set(payload)|{b.member(p) for p in donor_tables}|{a['member'] for a in assets}|{b.member(p) for p in voice_paths}
    original={}
    for row in report['source_chain']:
        p=b.ROOT/'assets/asset-patch/active'/row['archive']
        assert b.sha(p.read_bytes())==row['sha256'],p
        with zipfile.ZipFile(p) as z:
            for n in required.intersection(z.namelist()):original[n]=z.read(n)
    effective={**original,**payload}
    changed={}
    for row in report['tables']:changed.setdefault(row['logical'],[]).append(row['path'])
    def assign(tree,path,value):
        for key in path[:-1]:tree=tree['children'][key]
        tree['children'][path[-1]]=b.semantic(value)
    for logical,table in donor_tables.items():
        name=b.member(logical);expected=b.semantic(c.node(original[name]))
        if logical=='master/degree/degree.orderedmap':assert name not in payload
        else:
            for op in table['operations']:
                if op['path'] in changed.get(logical,[]):assign(expected,op['path'],op['after'])
        assert b.semantic(c.node(effective[name]))==expected,logical
    client_exchange=set()
    for rank in (5,4,3):
        name=b.member(f'master/gacha_odds/cnmod_abyss_limited_gacha_character_{rank}.orderedmap')
        # All these tables were resolved during building; load unchanged tables
        # from their terminal chain too, independently of candidate membership.
        if name not in original:
            for row in report['source_chain']:
                with zipfile.ZipFile(b.ROOT/'assets/asset-patch/active'/row['archive']) as z:
                    if name in z.namelist():original[name]=z.read(name)
        pre=b.semantic(c.node(original[name]));post=b.semantic(c.node(payload.get(name,original[name])))
        expected=copy.deepcopy(pre)
        for bucket in expected['children'].values():
            for node in bucket['children'].values():
                row=node['csv'][0];cid=int(row[0])
                if cid in b.EXCHANGE_IDS:
                    assert row[5]=='false';row[5]='true';client_exchange.add(cid)
        assert post==expected,('gacha client preservation',rank)
    assert client_exchange==b.EXCHANGE_IDS
    for relative in ('assets/gacha.json','assets/gacha_cnmod.json'):
        pre=b.loadj(work/'before'/relative);post=b.loadj(work/'candidate'/relative);restored=copy.deepcopy(post)
        seen=set()
        for bucket in restored['990001']['pool'].values():
            for row in bucket:
                if row['id'] in b.EXCHANGE_IDS:
                    assert row['isExchangeable'] is True;row['isExchangeable']=False;seen.add(row['id'])
        assert seen==b.EXCHANGE_IDS and restored==pre,relative
    text_path='assets/cdndata/character_text.json'
    pre=b.loadj(work/'before'/text_path);post=b.loadj(work/'candidate'/text_path)
    expected=copy.deepcopy(pre);table=c.unpack(effective[b.member('master/character/character_text.orderedmap')])
    for cid in ('149987','129992'):expected[cid]=c.node(table[cid])['csv']
    assert post==expected
    png_count=0;dsl_count=0;small_count=0
    with zipfile.ZipFile(donor/'assets/最终角色资源.zip') as z:
        for asset in assets:
            assert effective[asset['member']]==z.read(asset['member']),asset['logical']
            if asset['member'] not in payload:continue
            logical=asset['logical'];raw=payload[asset['member']]
            if logical.endswith('.png'):
                decoded=b.wf_assets.png_decode_stored(raw)
                with Image.open(io.BytesIO(decoded)) as im:
                    im.load();png_count+=1
                    if asset['root']=='medium' and logical.startswith('character/') and '/ui/' in logical and '/ui/skill_cutin_' not in logical:
                        small=b.wf_assets.png_decode_stored(payload[b.member(logical,'small_upload')])
                        with Image.open(io.BytesIO(small)) as actual:
                            expected=im.resize((int(im.width*.7),int(im.height*.7)),Image.Resampling.LANCZOS)
                            assert actual.size==expected.size and actual.mode==expected.mode
                            assert actual.tobytes()==expected.tobytes(),logical
                        small_count+=1
            if logical.endswith('.action.dsl.amf3.deflate'):
                b.wf_dsl_sig.validate_action_dsl(b.wf_dsl.parse_dsl(b.wf_atf.inflate(raw))['tree']);dsl_count+=1
    assert small_count==report['small_images']==972
    # Probe the original serialized defect and both forms after repair, then
    # inject both invalid and valid-but-wrong enum values into the final tree.
    rejected=0
    for n in (1,2):
        name=b.member(b.INAHO_PREFIX+str(n)+'.action.dsl.amf3.deflate')
        before=b.wf_dsl.parse_dsl(b.wf_atf.inflate(original[name]))['tree']
        tree=b.wf_dsl.parse_dsl(b.wf_atf.inflate(payload[name]))['tree']
        b.check_inaho(tree);b.wf_dsl_sig.validate_action_dsl(tree)
        try:b.check_inaho(before)
        except AssertionError:rejected+=1
        else:raise AssertionError('real F1009 preimage was accepted')
        for target,value in ((5,0),(6,1)):
            bad=copy.deepcopy(tree)
            node=next(x for x in b.walk(bad) if x and x[0]=='DeleteCondition' and x[1]==target and x[2][0]=='DCAll')
            node[2][1]=value
            serialized=b.wf_atf.deflate(b.wf_dsl.encode_amf3(bad))
            try:b.check_inaho(b.wf_dsl.parse_dsl(b.wf_atf.inflate(serialized))['tree'])
            except AssertionError:rejected+=1
            else:raise AssertionError(('wrong DCAll accepted',target,value))
    assert rejected==6
    # Actual extra voice paths referenced by the port must resolve in the
    # final effective archive chain, including existing 1033 base recordings.
    for logical in voice_paths:
        name=b.member(logical)
        assert name in effective,logical
        assert len(effective[name])>1000,logical
    for row in report['ios']:
        assert b.sha(payload[row['member']])==row['sha256']
        assert row['member'].startswith('production/ios_upload/')
    result={'status':'passed','serialized_table_changes':len(report['tables']),
            'all_other_table_keys_preserved':True,'degree_table_unchanged':True,
            'donor_media_verified':len(assets),'changed_media':len(report['media']),
            'changed_png_decodes':png_count,'small_png_pixel_pairs':small_count,
            'author_action_signatures':dsl_count,'inaho_forms':2,'negative_inaho_cases':rejected,
            'exchange_ids':sorted(client_exchange),'other_server_fields_unchanged':True,
            'ready_voice_paths':voice_paths,'ios_pairs':len(report['ios']),'device_tested':False}
    (work/'resource-verification.json').write_bytes(b.jsonb(result));print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--donor',type=Path,required=True);p.add_argument('--work',type=Path,required=True)
    a=p.parse_args();verify(a.donor,a.work)
