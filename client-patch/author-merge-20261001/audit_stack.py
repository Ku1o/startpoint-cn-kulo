from __future__ import annotations
import argparse
import importlib.util, json, hashlib, sys, traceback
from pathlib import Path
parser=argparse.ArgumentParser(description='Audit the rebased seven-layer equipment SWF stack.')
parser.add_argument('--work-dir', type=Path, required=True)
root=Path(__file__).resolve().parent
work=parser.parse_args().work_dir.resolve()
sys.path.insert(0,str(root/'battle-rules')); sys.path.insert(0,str(root/'abcasm'))
spec=importlib.util.spec_from_file_location('core',root/'battle-rules/core.py'); core=importlib.util.module_from_spec(spec); sys.modules['core']=core; spec.loader.exec_module(core)
spec=importlib.util.spec_from_file_location('bodies',root/'abcasm/bodies.py'); bodies=importlib.util.module_from_spec(spec); sys.modules['bodies']=bodies; spec.loader.exec_module(bodies)
base=core.SwfAbc(work/'public-base.swf').abc; out=core.SwfAbc(work/'l7.swf').abc
bm=bodies.label_map(base); om=bodies.label_map(out)
def hashes(abc,lm): return {label:hashlib.sha256(abc.bodies[idx][5]).hexdigest() for idx,label in lm.items()}
bh=hashes(base,bm); oh=hashes(out,om)
changed=[label for label in sorted(set(bh)&set(oh)) if bh[label]!=oh[label]]
removed=sorted(set(bm.values())-set(om.values())); added=sorted(set(om.values())-set(bm.values()))
rows=[]
cases=[('L2','equipment-description-override','fallthrough_matrix'),('L3','equipment-enhanced-look','icon_matrix'),('L3-frame','equipment-enhanced-look','frame_matrix'),('L4','equipment-enhanced-party-frame','party_matrix'),('L4-icon','equipment-enhanced-party-frame','icon_matrix'),('L5','equipment-awakening-material','awaken_matrix'),('L6','equipment-sort-pin','sort_matrix'),('L7','item-rarity-frame-override','matrix'),('L7-v1','item-rarity-frame-override','v1_regression')]
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p); m=importlib.util.module_from_spec(s); sys.modules[n]=m; s.loader.exec_module(m); return m
for lid,d,fn in cases:
 try:
  mod=load('verify_'+lid.replace('-','_'),root/d/'verify.py'); val=getattr(mod,fn)(out); rows.append({'case':lid,'function':fn,'status':'ok','result':val})
 except Exception as ex:
  rows.append({'case':lid,'function':fn,'status':'error','type':type(ex).__name__,'error':str(ex),'traceback':traceback.format_exc()})
summary={'status':'static_and_semantic_audit','base':str(work/'public-base.swf'),'output':str(work/'l7.swf'),'base_sha256':hashlib.sha256((work/'public-base.swf').read_bytes()).hexdigest(),'output_sha256':hashlib.sha256((work/'l7.swf').read_bytes()).hexdigest(),'main_abc_body_count':{'base':len(base.bodies),'output':len(out.bodies)},'changed_existing_labels':changed,'changed_existing_count':len(changed),'added_labels':added,'added_count':len(added),'removed_labels':removed,'removed_count':len(removed),'runtime_matrices':rows,'expected_author_labels':['BattleCharacterLogic/getAvailableAbilities','BattleCharacterLogic/resolvePathCollection','EquipmentEnhancementAbilityValues$/parseAt109','AbilitySoulValues$/parseAt106','AbilitySoulAbilityLogic/getDescriptionsWithoutAdditional','AbilitySoulAbilityLogic/getDescriptionWithoutAdditional','EquipmentEnhancementAbilityLogic/getAllDescriptionsToMapForDialog','EquipmentEnhancementLogic/getPixelart','ItemThumbnailView/setRarity','PartyItemThumbnailView/updateEnhancedEffectAnimation','OwnedEquipmentLogic/getUseableAwakingCrystal','EquipmentListScene/compareByEquipmentStatus','EquipmentSelectThumbnailListRepository/sortByRarity','ItemThumbnailView/replace']}
def norm(v):
 if isinstance(v,dict): return {str(k):norm(x) for k,x in v.items()}
 if isinstance(v,(list,tuple)): return [norm(x) for x in v]
 return v
clean=norm(summary)
(work/'public-stack-audit.json').write_text(json.dumps(clean,ensure_ascii=False,indent=2,default=str)+'\n',encoding='utf8')
print(json.dumps(clean,ensure_ascii=False,indent=2,default=str))
