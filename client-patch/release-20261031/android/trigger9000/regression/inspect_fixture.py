"""One bounded read after slot assignment; no compile, no candidate mutation."""
from pathlib import Path
import argparse,json,sys
ROOT=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
import bootstrap
from input_config import input_path,input_sha,runtime,repo_path,work_path,tool_root
import abc_tools as a

def main():
 p=argparse.ArgumentParser();p.add_argument('--swf',required=True);p.add_argument('--sha',required=True);p.add_argument('--out',required=True);args=p.parse_args()
 out=Path(args.out).resolve()
 if not out.is_relative_to(work_path()) or out.exists():raise ValueError('fresh owned output required')
 cfg=runtime()
 a.configure({**cfg,'repo':str(repo_path()),'swf':args.swf,'swf_sha256':args.sha,'tool_root':str(tool_root()),'run_root':str(work_path('trigger9000'))})
 b,abc,v,identity=a.load_current(('pinball.master.generated::LeaderAbilityValues',))
 wanted={'MemberImpl','ActionExecutor','PrecontentMagnification','AbilityPowerValue','LeaderAbilityValues','AbilityValues','InstantAbilityTriggerMasterValue','InstantAbilityTriggerPullerMasterValue','InstantBattleAbilityTriggerKind','InstantAbilityTriggerKind','InstantAbilityTriggerMasterValueTools','InstantAbility','HealthPointGaugeImpl','BarrierHpGaugeImpl','Decimal100ClosedInterval','ClientError','SipoError','AbilityPrecondition_Impl_'}
 # Include the actual debug-handler class and native error superclass rather
 # than guessing their names or using a no-op/count replacement.
 by_name={abc.mn_name(row[0]):(i,row) for i,row in enumerate(abc.instances)}
 for q,(i,row) in by_name.items():
  if q.split('::')[-1] not in wanted:continue
  for t in row[6]:
   if t.data[0]=='slot' and abc.mn_name(t.name).split('::')[-1]=='handlerForDebug':
    wanted.add(abc.mn_name(t.data[2]).split('::')[-1])
  if q.endswith('::ClientError') and '::' in abc.mn_name(row[1]):wanted.add(abc.mn_name(row[1]).split('::')[-1])
 result={'identity':identity,'classes':{}}
 for q,(ci,row) in by_name.items():
  if q.split('::')[-1] not in wanted:continue
  def traits(items):
   return [{'name':abc.mn_name(t.name),'data':str(t.data),'slotType':abc.mn_name(t.data[2]) if t.data[0]=='slot' else None} for t in items]
  methods=[]
  for label,indices in v.by_label.items():
   if not (label.startswith(q+'/') or label.startswith(q+'$/')):continue
   method=label.rsplit('/',1)[-1].split('|')[0]
   selected=(q.split('::')[-1] in ('AbilityPowerValue','ClientError','SipoError') or method in ('<ctor>','<cinit>','countHandler','isActive','HpLow','Image','Some','Count','Battle') or method.startswith('wfx') or q.endswith('::LeaderAbilityValues') and method in ('parseAt26','parseAt28','parseAt29','parseAt30','parseAt31','parseAt32','parseAt33') or q.endswith('::AbilityValues') and method in ('parseAt28','parseAt30','parseAt31','parseAt32','parseAt33','parseAt34','parseAt35') or q.endswith('::AbilityTriggerHandler') and method in ('update','resetCooltime','getCountProgress','getCooltimeProgress','isReachedTriggerLimit') or q.endswith('::InstantAbility') and method in ('get_cooltime','get_triggerLimit','get_precontent','invokePrecontent','addCooltimeHandler','markAsReachingLimit','addReachingLimitCount') or q.endswith('::MemberImpl') and method in ('getRealMaximumHealthPoint','isDisposed','isDead','dispose'))
   if not selected:continue
   bi,=indices;body=abc.bodies[bi];info=abc.methods[body[0]]
   methods.append({'label':label,'header':body[:5],'signature':{'return':abc.mn_name(info[0]) if info[0] else '*','args':[abc.mn_name(n) if n else '*' for n in info[1]],'flags':info[3],'options':info[4]},'codeSha256':a.sha(body[5]),'listing':b.sc.listing(abc,body[5]) if hasattr(b,'sc') and hasattr(b.sc,'listing') else v.normalized(bi)})
  result['classes'][q]={'super':abc.mn_name(row[1]),'flags':row[2],'instanceTraits':traits(row[6]),'staticTraits':traits(abc.classes[ci][1]),'methods':methods}
 out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf-8');print(json.dumps({'output':str(out),'classes':list(result['classes'])}))
if __name__=='__main__':main()
