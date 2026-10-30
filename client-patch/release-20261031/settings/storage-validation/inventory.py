from pathlib import Path
import sys,json
ROOT=Path(__file__).resolve().parent
import bootstrap
from input_config import input_path,input_sha,runtime,tool_root,repo_path,work_path
sys.dont_write_bytecode=True;sys.path.insert(0,str(tool_root()/'lib'));import abc_tools as a
SWF=input_path('final_swf');SHA=input_sha('final_swf')
def source():
 cfg=runtime();a.configure({**cfg,'repo':str(repo_path('.')),'swf':str(SWF),'swf_sha256':SHA,'tool_root':str(tool_root()),'run_root':str(work_path('storage-validation'))});return cfg,a.load_current(('pinball.context.localStore::LocalStore',))
GROUPS={
'pinball.common.data.localStore::ApplicationOptionLogic':['<ctor>','store','getTeammateEffectsVisible','setTeammateEffectsVisible','$cnTeammateEffectsVisibleFromRaw'],
'pinball.context.localStore::LocalStore':['saveApplicationOption','get_applicationOption'],
'pinball.context.localStore._ApplicationOptionLocalStore::ApplicationOptionLocalStore_Impl_':['$startLoad','$apply','$getDefault','$save','$getApplicationOptionDataFile'],
'pinball.remote.util::CompressUtil':['$compress','$compressStringUsingWriteUTF','$uncompress'],
'pinball.asset.file::FileUtil':['$readFileAsByteArray'],
'pinball.asset.file::FileStreamWithCounter':['<ctor>','open','writeBytes','_writeBytes','close','_close'],
'pinball.context::SectionCommand':['<ctor>','$LocalStoreLoad'],
'pinball.context.localStore::LocalStoreLoadInput':['<ctor>','$ApplicationOptionLoaded'],
'haxe.ds::Option':['<ctor>','$Some'],
'pinball.asset::WaitImpl':['<ctor>','dispose','executeComplete','addCompleteHandler','getCompleteDispatcherAddBehavior'],
'pinball.asset::WaitInOrderImpl':['<ctor>','getCompleteDispatcherAddBehavior'],
}
def selections(sv):
 out=[]
 for owner,names in GROUPS.items():
  for name in names:
   static=name.startswith('$');name=name.lstrip('$');prefix=owner+('$' if static else '')+'/'+name;hits=[l for l in sv.by_label if l==prefix or l.startswith(prefix+'|')]
   if len(hits)!=1:raise ValueError((prefix,hits))
   out.append(hits[0])
 return out

def main():
 cfg,(b,s,v,identity)=source();rows=[];work_path('storage-validation').mkdir(parents=True,exist_ok=True)
 for label in selections(v):
  bi,=v.by_label[label];body=s.bodies[bi];info=s.methods[body[0]];ops=[]
  for i,x in enumerate(b.asm.decode(body[5])):
   args=list(x.args)
   for j,val in enumerate(x.args):
    kind=b.asm.opwalk.KIND.get((x.op,j))
    if kind=='multiname':args[j]=s.mn_name(val)
    elif kind=='string':args[j]=s.strings[val].decode('utf-8',errors='replace')
    elif kind in ('int','uint','double'):args[j]=getattr(s,kind+'s')[val]
   row={'instruction':i,'op':x.name,'args':args,'target':x.target}
   if x.cases is not None:row.update(default=x.default,cases=x.cases)
   ops.append(row)
  rows.append({'label':label,'method':body[0],'body':bi,'code_sha256':a.sha(body[5]),'header':body[1:5],'return':s.mn_name(info[0]),'args':[s.mn_name(t) if t else '*' for t in info[1]],'flags':info[3],'instructions':ops})
 (work_path('storage-validation/METHODS.json')).write_text(json.dumps({'source':identity,'groups':GROUPS,'methods':rows},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps([{k:r[k] for k in ('label','code_sha256')} for r in rows],ensure_ascii=False))
if __name__=='__main__':main()
