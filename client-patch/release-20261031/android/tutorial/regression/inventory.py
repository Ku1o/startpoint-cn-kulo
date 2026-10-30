"""Run only under task run_bounded; bounded method inventory, no build."""
from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import input_path,runtime,repo_path,work_path,tool_root
import abc_tools as a
cfg=runtime()
a.configure({**cfg,'repo':str(repo_path()),'swf':str(input_path('settings_swf')),'swf_sha256':'3c56f08c8b30ae75ae71908a699e703764dcfca0bc64d1fb91d866e2c61bfaef','tool_root':str(tool_root()),'run_root':str(work_path('tutorial'))})
b,abc,v,identity=a.load_current(('pinball.scene.gacha.top.common::GachaSceneViewBase',))
owners=[abc.mn_name(x[0]) for x in abc.instances if 'TutorialGachaLogic' in abc.mn_name(x[0])]+['pinball.common.data.gacha::TutorialGachaFeatureContentLogic','pinball.common.data.gacha::GachaLogic','pinball.scene.gacha.top.common::GachaSceneViewBase']
result={'identity':identity,'owners':{}}
for owner in owners:
 row=next(x for x in abc.instances if abc.mn_name(x[0])==owner)
 data={'instance':str(row[:6]),'slotTypes':{abc.mn_name(t.name):abc.mn_name(t.data[2]) for t in row[6] if t.data[0]=='slot'},'traits':[{'name':abc.mn_name(t.name),'data':str(t.data)} for t in row[6]],'methods':[]}
 for label,indices in v.by_label.items():
  if label.startswith(owner+'/') or label.startswith(owner+'$/'):
   if 'Tutorial' not in owner and not any('/'+n+'|' in label for n in ('setupText','get_showPeriod','isComeback','isStarsGacha')):continue
   for bi in indices:
    body=abc.bodies[bi];data['methods'].append({'label':label,'mid':body[0],'info':str(abc.methods[body[0]]),'header':body[:5],'sha':a.sha(body[5]),'rows':v.normalized(bi)})
 result['owners'][owner]=data
work_path('tutorial').mkdir(parents=True,exist_ok=True);(work_path('tutorial/inventory.json')).write_text(json.dumps(result,indent=2)+'\n','utf-8')
print(json.dumps({'owners':list(result['owners']),'output':str(work_path('tutorial/inventory.json'))}))
