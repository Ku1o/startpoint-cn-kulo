#!/usr/bin/env python3
"""Capture exact native parent/Box relationships and verify server pool semantics.

Sparse read-only CDN inputs. Writes only the explicit small asset/report paths.
The artifact describes relationships; it never changes content availability.
"""
import argparse,hashlib,importlib.util,json,re,sys
from pathlib import Path
sys.dont_write_bytecode=True
PARENTS={'world_story_event':('master/quest/event/world_story_event.orderedmap',14,2,41),
         'raid_event':('master/quest/event/raid_event.orderedmap',18,1,7)}
BOX='master/box_gacha/box_gacha.orderedmap'
STAGES='master/box_gacha/box.orderedmap'
REWARDS='master/box_gacha/box_reward.orderedmap'
SERVER_SOURCES=['assets/box_gacha.json','assets/box_reward.json','assets/box_gacha_1001_settings.json','src/lib/assets.ts']
def sha(raw):return hashlib.sha256(raw).hexdigest()
def stable(value):return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
def digest(value):return sha(stable(value).encode('utf-8'))
def load(path):return json.loads(path.read_bytes())

def capture(repo,resource_root,exporter):
    spec=importlib.util.spec_from_file_location('box_association_exporter',exporter);exp=importlib.util.module_from_spec(spec);spec.loader.exec_module(exp)
    catalog_raw=(repo/'assets/content_catalog.json').read_bytes();catalog=json.loads(catalog_raw);bykey={r['key']:r for r in catalog['rows']}
    logicals=[p[0] for p in PARENTS.values()]+[BOX,STAGES,REWARDS]
    inputs,source=exp.resolve(resource_root,logicals)
    if set(inputs)!=set(logicals):raise ValueError(('missing native association master',set(logicals)-set(inputs)))
    for logical,(raw,_) in inputs.items():
        if catalog['resources'].get(logical,{}).get('sha256')!=sha(raw):raise ValueError(('catalog native master provenance differs',logical))
    flat={};raw_rows={}
    for logical in [p[0] for p in PARENTS.values()]+[BOX]:
        raw=inputs[logical][0];flat[logical]=exp.parse_rows(raw,logical)
        table=exp.core.read_orderedmap_bytes(raw,logical);raw_rows[logical]=dict(zip(table.keys,table.rows))
    stages=exp.nested_rows(inputs[STAGES][0],STAGES,2);rewards=exp.nested_rows(inputs[REWARDS][0],REWARDS,3)
    server_boxes=load(repo/'assets/box_gacha.json');server_rewards=load(repo/'assets/box_reward.json')
    settings=load(repo/'assets/box_gacha_1001_settings.json')
    loader=(repo/'src/lib/assets.ts').read_text(encoding='utf-8')
    for contract in ['const redeemItemData = (boxGacha as RawBoxGachas)[idString]','const boxes = (boxReward as RawBoxRewards)[idString]']:
        if contract not in loader:raise ValueError('getBoxGachaSync winning source changed; review generator')
    rows=[];seen_boxes={};counts={};referenced=set()
    for typ,(logical,column,name_column,expected_count) in PARENTS.items():
        count=0
        for ident,cells in flat[logical].items():
            if len(cells)!=1:raise ValueError(('ambiguous native parent',typ,ident))
            raw=cells[0];box_id=raw[column]
            if box_id in ('','(None)'):continue
            if not re.fullmatch('[1-9][0-9]*',box_id):raise ValueError(('malformed native box reference',typ,ident,box_id))
            parent_key=typ+':'+ident;box_key='box_gacha:'+box_id;parent=bykey.get(parent_key);box=bykey.get(box_key)
            if box_id in seen_boxes:raise ValueError(('shared box reference requires explicit design',box_key,seen_boxes[box_id],parent_key))
            seen_boxes[box_id]=parent_key;referenced.add(box_id);count+=1
            if not parent or not box:raise ValueError(('association catalog row absent',parent_key,box_key))
            box_cells=flat[BOX].get(box_id)
            if not box_cells or len(box_cells)!=1:raise ValueError(('native box row missing/ambiguous',box_key))
            box_raw=box_cells[0]
            for row,key,data,path in [(parent,parent_key,raw,logical),(box,box_key,box_raw,BOX)]:
                if row['definitionDigest']!=digest(data) or row['source']!=path:raise ValueError(('catalog native row identity mismatch',key))
            server=server_boxes.get(box_id);pool=server_rewards.get(box_id)
            if not server or not pool or not stages.get(box_id) or not rewards.get(box_id):raise ValueError(('server/native box pools missing',box_key))
            if box_raw[1]!='3' or server['itemId']!=int(box_raw[2]) or server['count']!=int(box_raw[3]):raise ValueError(('box cost item/count differs',box_key))
            projected={stage:{v[0][0]:{'type':int(v[0][2]),**({'id':int(v[0][3])} if v[0][3].isdigit() else {}),'count':int(v[0][4]),'available':int(v[0][5]),'tier':int(v[0][6])} for v in values.values()} for stage,values in rewards[box_id].items()}
            rules={}
            for stage,values in stages[box_id].items():
                v=values[0];rules[stage]={'requiredBoxId':None if v[3]=='(None)' else int(v[3]),'resetKind':int(v[11]),'resetLimit':None if v[12]=='(None)' else int(v[12]),'availableFrom':v[13],'availableUntil':v[14],'closeKind':int(v[15])}
            if projected!=pool or set(rules)!=set(pool):raise ValueError(('box rewards/stages differ',box_key))
            if rules!=box.get('boxRules'):raise ValueError(('catalog box policies differ',box_key))
            counts_from_rewards={stage:sum(r['available'] for r in values.values()) for stage,values in pool.items()}
            if counts_from_rewards!=server['availableCounts']:raise ValueError(('box pool availableCounts differ',box_key))
            if box_id=='1001' and settings.get('boxSettings')!=rules:raise ValueError('1001 explicit policy differs')
            rows.append({'parentKey':parent_key,'boxKey':box_key,'description':raw[name_column]+'关联奖励箱',
                'parent':{'source':logical,'rowId':int(ident),'fieldIndex':column,'boxId':int(box_id),'rawSha256':sha(raw_rows[logical][ident]),'definitionDigest':digest(raw),'fields':raw},
                'box':{'source':BOX,'rowId':int(box_id),'rawSha256':sha(raw_rows[BOX][box_id]),'definitionDigest':digest(box_raw),'fields':box_raw},
                'serverBoxDigest':digest(server),'serverRewardsDigest':digest(pool),'nativeStagesDigest':digest(stages[box_id]),'nativeRewardsDigest':digest(rewards[box_id]),
                'stageCount':len(pool),'rewardCount':sum(len(v) for v in pool.values()),'costItemId':server['itemId'],'costCount':server['count']})
        if count!=expected_count:raise ValueError(('native association count changed; review scope',typ,count,expected_count))
        counts[typ]=count
    rows.sort(key=lambda r:(r['parentKey'].split(':')[0],int(r['parentKey'].split(':')[1])))
    if len(rows)!=48:raise ValueError('expected exactly the reviewed 48 native pairs')
    manifest_raw=(resource_root/'assets/asset-patch/manifest.json').read_bytes()
    if sha(manifest_raw)!=source['manifestSha256'] or (repo/'assets/asset-patch/manifest.json').read_bytes()!=manifest_raw:raise ValueError('repo/resource chain mismatch')
    artifact={'schemaVersion':1,'associationCount':48,'parentTypeCounts':counts,'catalogSha256':sha(catalog_raw),'manifestSha256':sha(manifest_raw),'assetVersion':source['assetVersion'],
        'serverSources':{p:sha((repo/p).read_bytes()) for p in SERVER_SOURCES},
        'nativeMasters':{logical:{**identity,'sha256':sha(raw)} for logical,(raw,identity) in sorted(inputs.items())},'associationsDigest':digest(rows),'associations':rows}
    report={'pairs':48,'parentTypeCounts':counts,'uniqueParentKeys':len({r['parentKey'] for r in rows}),'uniqueBoxKeys':len(seen_boxes),'unassociatedNativeBoxIds':sorted(set(flat[BOX])-referenced,key=int),
        'allPairReferencesMatch':True,'allCatalogRowsMatch':True,'allServerCostsRewardsStagesMatch':True,'catalogSha256':artifact['catalogSha256'],'manifestSha256':artifact['manifestSha256'],'scope':'relationship identity and exact static cost/pool/policy parity only; no new permissions, state changes or gameplay acceptance'}
    return artifact,report

def main():
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--resource-root',type=Path,required=True);p.add_argument('--exporter',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--report',type=Path,required=True);p.add_argument('--check',action='store_true');a=p.parse_args()
    for output in [a.output.resolve(),a.report.resolve()]:
        if any(output.is_relative_to((root/relative).resolve()) for root in [a.repo,a.resource_root] for relative in ['.cdn','assets/asset-patch']):
            raise ValueError('association outputs must not modify CDN inputs or patch chain')
    artifact,report=capture(a.repo.resolve(),a.resource_root.resolve(),a.exporter.resolve())
    if a.check:
        if load(a.output)!=artifact:raise ValueError('association artifact differs from current exact inputs')
    else:a.output.write_text(json.dumps(artifact,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
