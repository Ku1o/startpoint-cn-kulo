"""Preserve the reviewed seed-46454236 tower and add the verified quest channel.

Writes a new sparse candidate only. The combined archive builder consumes its
receipts afterward; runtime activation remains a separate exact-file operation.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import zipfile
import zlib

ROOT=Path(__file__).resolve().parents[2]
INPUT_HASHES={
    'floor-details.json':'6e6397d437e3cb2b96adaddbd40157e3af6dd668ccdb3e594b6fa75d3a1c48b0',
    'tower-resource-inventory.json':'f50bd5f32a6ee3accb8885ea15ce8b51b1edee153adfb80f1e74ef4274c01c98',
    'hp-audit.json':'e13aedfd6fb4e0ce2fc9a626dbde963340b26535ccb6a4c3c602caf75a6a893a',
}

def sha(data):return hashlib.sha256(data).hexdigest()
def readj(path):return json.loads(path.read_text('utf8'))
def savej(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def main(donor,work):
    donor=donor.resolve();work=work.resolve()
    cdn=(ROOT/'.cdn').resolve()
    assert not work.exists() and not work.is_relative_to(cdn)
    for name,digest in INPUT_HASHES.items():assert sha((donor/name).read_bytes())==digest,name
    client=readj(ROOT/'outputs/quest-element-channel-test-20260910/verification-report.json')
    assert client['swf_sha256']=='20aef6d02b5bf72c1a0b4628d4bc51df6c0646b96584058aa82314b39c945226'
    assert sha(Path(client['apk']).read_bytes())==client['apk_sha256']
    assert client['desktop_air_test_passed'] and client['desktop_air_checks']==351
    original=readj(donor/'floor-details.json'); assert [f['r'] for f in original]==list(range(1,31))
    assert readj(donor/'source-state.json')['seed']==46454236
    work.mkdir(parents=True)
    server=work/'candidate-server'
    for base,pattern in [(donor/'pristine-read-links','**/*.zip'),(donor/'candidate-server/assets/asset-patch/active','*.zip')]:
        for source in base.glob(pattern):
            target=(work/'pristine-read-links'/source.relative_to(base) if base.name=='pristine-read-links'
                    else server/'assets/asset-patch/active'/source.name)
            target.parent.mkdir(parents=True,exist_ok=True);os.link(source,target)
    for rel in ['assets/asset-patch/manifest.json','server/assets/rush_event_quest.json','server/assets/rush_event_quest_folder.json']:
        target=server/rel;target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes((donor/'candidate-server'/rel).read_bytes())
    for name in ['source-state.json','source-manifest-before.json','baseline-inventory.json','signature-validation.json','hp-audit.json','hp-report.md']:
        shutil.copy2(donor/name,work/name)
    assert readj(server/'assets/asset-patch/manifest.json')['cdn_version']=='1.4.103'
    inventory=readj(donor/'tower-resource-inventory.json')
    payloads={};items={}
    for item in inventory:
        raw=(donor/'candidate-server/assets/asset-patch'/item['member']).read_bytes()
        assert sha(raw)==item['sha256'],item['logical']
        payloads[item['logical']]=raw;items[item['logical']]=item
    os.environ.update(WF_SERVER_DIR=str(server),WF_CDN_DIR=str(work/'pristine-read-links/cn'),
                      WF_TARGET_STORE=str(server/'assets/asset-patch/production/upload'),WF_LIVE_CDN='1')
    import wf_rogue_build as rb
    import wf_rogue_element_channel as channel
    import publish_sponsor_special_thanks as sponsor
    p=sponsor.p
    final=copy.deepcopy(original);receipts=[];replacements={};removed=set();new_programs={}
    for before,after in zip(original,final):
        curse,block,receipt=channel.finalize_curse(before['curse'],46454236,before['r'])
        after['curse']=curse
        # Retain the exact original label text; the new block carries all merged
        # element strength once. The supplementary card remains in the receipt.
        assert channel.PREFIX not in before['row'][3]
        after['row'][3]=before['row'][3]+' '+block
        receipt.update(round=before['r'],quest_id=before['row'][0],original_subtitle=before['row'][3],final_subtitle=after['row'][3])
        receipts.append(receipt)
        replacement=channel.replacement_program(before['curse'])
        if replacement:
            old,old_tree,new,new_tree=replacement
            logical=old+'.action.dsl.amf3.deflate'
            assert rb.wf_dsl.parse_dsl(zlib.decompress(payloads[logical],-15))['tree']==old_tree,logical
            assert old not in replacements or replacements[old]==new
            replacements[old]=new;removed.add(logical)
            if new is not None:
                new_programs[new+'.action.dsl.amf3.deflate']=rb.build_immunity_dsl_blob(new_tree)
    rows_by_id={f['row'][0]:(b['row'],f['row']) for b,f in zip(original,final)}
    row_changes=[];carrier_changes=[]
    def transform(raw,callback,path=()):
        try:children=p.rawmap(raw)
        except Exception:
            rows=p.csvrows(raw);new=callback(copy.deepcopy(rows),path)
            return raw if new==rows else p.packcsv(new)
        updated={k:transform(value,callback,path+(k,)) for k,value in children.items()}
        return raw if updated==children else p.packmap(updated)
    def quest_rows(rows,path):
        for i,row in enumerate(rows):
            if row and row[0] in rows_by_id:
                before,after=rows_by_id[row[0]]
                assert row==before,(row[0],'reviewed quest preimage changed')
                rows[i]=after;row_changes.append(row[0])
        return rows
    quest='master/quest/event/rush_event_quest.orderedmap'
    payloads[quest]=transform(payloads[quest],quest_rows)
    assert sorted(row_changes)==sorted(rows_by_id) and len(row_changes)==30
    def carrier_rows(rows,path):
        for row in rows:
            if len(row)<=109:continue
            programs=[] if row[109] == '' else row[109].split(',')
            if not any(x in replacements for x in programs):continue
            assert path[0].startswith('mod_rogue_'),('native carrier modification forbidden',path)
            old=row[109];row[109]=channel.rewrite_pre_action_programs(old,replacements)
            carrier_changes.append({'path':list(path),'before':old,'after':row[109],
                                    'removed_generated_programs':[x for x in programs if x in replacements]})
        return rows
    general='master/battle/boss/general_boss.orderedmap'
    payloads[general]=transform(payloads[general],carrier_rows)
    found={name for item in carrier_changes for name in item['removed_generated_programs']}
    assert found==set(replacements),(found,set(replacements))
    for logical in removed:del payloads[logical]
    for logical,raw in new_programs.items():
        assert logical not in payloads or payloads[logical]==raw
        payloads[logical]=raw
    # No old generated element call can remain anywhere in the transformed
    # General Boss table. Native programs and c110+ are left unchanged.
    def audit_carrier(rows,path):
        for row in rows:
            if path[0].startswith('mod_rogue_') and len(row)>109:
                channel.pre_action_programs(row[109])
            for cell in row:
                assert not any(prog in cell.split(',') for prog in replacements),(path,cell)
        return rows
    assert transform(payloads[general],audit_carrier)==payloads[general]
    output=[]
    for logical,raw in sorted(payloads.items()):
        member='production/upload/'+rb.q.hashed_rel(logical)
        path=server/'assets/asset-patch'/member;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        output.append({'logical':logical,'member':member,'size':len(raw),'sha256':sha(raw)})
    validated=[]
    for logical,raw in payloads.items():
        if logical.startswith('battle/action/enemy/action/mod_rogue/immunity_'):
            tree=rb.wf_dsl.parse_dsl(zlib.decompress(raw,-15))['tree']
            assert 'ACToleranceOfElement' not in json.dumps(tree)
            assert rb.build_immunity_dsl_blob(tree)==raw
            validated.append(logical)
    shutil.copy2(work/'signature-validation.json',work/'signature-validation-original.json')
    savej(work/'signature-validation.json',dict(generated_immunity_programs=len(validated),programs=sorted(validated),
        before_and_after_serialization_checked=True,no_element_conditions_in_generated_dsl=True,otherwise_strict=True))
    for old,new in zip(original,final):
        assert old['pick']==new['pick'] and old['row'][:3]==new['row'][:3] and old['row'][4:]==new['row'][4:]
    savej(work/'tower-resource-inventory.json',output);savej(work/'floor-details.json',final)
    savej(work/'element-channel-receipt.json',dict(schema='abyss-element-channel-finalization/v1',seed=46454236,
        rounds=30,input_sha256=INPUT_HASHES,client_swf_sha256=client['swf_sha256'],
        minimum=2,maximum=5,original_bosses_fields_and_non_element_curses_preserved=True,
        original_hp_audit_sha256=INPUT_HASHES['hp-audit.json'],rows=receipts,
        generated_program_replacements=replacements,carrier_changes=carrier_changes,
        generated_element_dsl_removed=True,android_gameplay_verified=False))
    print(json.dumps({'status':'sparse_tower_finalized','rounds':30,'ban_counts':[len(x['final_banned']) for x in receipts],
                      'carrier_rows_migrated':len(carrier_changes),'resources':len(output)},ensure_ascii=False))

if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--donor',type=Path,required=True);ap.add_argument('--work',type=Path,required=True)
    args=ap.parse_args();main(args.donor,args.work)
