"""Append missing administrator funnel anchors from its effective native field."""
import argparse
import copy
from pathlib import Path
import prepare_content as p
import wf_dsl


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True)
    w=ap.parse_args().work.resolve();chain=p.Chain()
    inventory=p.readj(w/'resources.json')
    native_logical='battle/terrain/event_quest/expert_single/expert_admiinstrator_80.amf3.deflate'
    blob=chain.get(('common',p.hrel(native_logical)))
    native=wf_dsl.parse_dsl(p.wf_atf.inflate(blob))['tree']
    objects=native['layers'][0]['objects']
    source_bounds=next(o for o in objects if o['type']=='BOUNDS')
    plans={'expert_white_tiger_100_coffin9':{'0':[6,7,8]},
           'desert_bonds_01_big_boss_single_hell_coffin9':{'0':[7],'1':[7]}}
    receipt={'native_logical':native_logical,'native_sha256':p.sha(blob),'changes':[]}
    for name,layers in plans.items():
        logical=f'battle/terrain/mod/five_boss/{name}.amf3.deflate';rel=p.hrel(logical)
        row=next(r for r in inventory if r['root']=='common' and r['rel']==rel)
        path=w/'resources/upload'/rel;before=path.read_bytes();assert p.sha(before)==row['sha256']
        tree=wf_dsl.parse_dsl(p.wf_atf.inflate(before))['tree'];old=copy.deepcopy(tree)
        ident=max(o['id'] for layer in tree['layers'] for o in layer['objects'])
        additions=[]
        for layer in tree['layers']:
            if layer['name'] not in layers:continue
            bounds=next(o for o in layer['objects'] if o['type']=='BOUNDS')
            assert (bounds['width'],bounds['height'])==(source_bounds['width'],source_bounds['height'])
            for group in layers[layer['name']]:
                typ=f'FUNNEL_SPAWN{group}'
                assert not any(o['type']==typ for o in layer['objects']), 'already repaired or rebase needed'
                donors=[o for o in objects if o['type']==typ];assert donors
                for donor in donors:
                    o=copy.deepcopy(donor);ident+=1;o['id']=ident
                    o['x']+=bounds['x']-source_bounds['x'];o['y']+=bounds['y']-source_bounds['y']
                    layer['objects'].append(o);additions.append({'layer':layer['name'],'object':o,'source_object_id':donor['id']})
        for a,b in zip(old['layers'],tree['layers']):
            assert b['objects'][:len(a['objects'])]==a['objects']
            assert {k:v for k,v in a.items() if k!='objects'}=={k:v for k,v in b.items() if k!='objects'}
        assert {k:v for k,v in old.items() if k!='layers'}=={k:v for k,v in tree.items() if k!='layers'}
        output=p.wf_atf.deflate(wf_dsl.encode_amf3(tree))
        assert wf_dsl.parse_dsl(p.wf_atf.inflate(output))['tree']==tree
        backup=w/'terrain-fix-before'/rel;backup.parent.mkdir(parents=True,exist_ok=True)
        assert not backup.exists();backup.write_bytes(before);path.write_bytes(output)
        receipt['changes'].append({'logical':logical,'rel':rel,'before_sha256':p.sha(before),
            'sha256':p.sha(output),'additions':additions})
        row['sha256']=p.sha(output);row['bytes']=len(output)
    p.savej(w/'resources.json',inventory);p.savej(w/'terrain-fix-receipt.json',receipt)
    print('Repaired 2 terrains, appended',sum(len(r['additions']) for r in receipt['changes']),'anchors; all previous objects preserved')


if __name__=='__main__':main()
