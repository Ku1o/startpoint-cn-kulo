"""Append an independent town helper and graft exactly two R10 method bodies."""
import argparse, copy, hashlib, json, struct, subprocess, sys, zlib
from pathlib import Path
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'content-operations'))
import build_bridge as b
from build_exchange_repair import qname,physical_labels
R10='8e07d004a850e8ee830e01548cc07619499078174399f7d12c76fbf376f7792e'
RESPONSE='pinball.remote.common::ResponseData/<ctor>'
SELECT='pinball.common.data.town::TownContentRepository/getTownContentByTime|1'
def sha(v):return hashlib.sha256(v).hexdigest()
def build(work,source,sdk,java):
 work.mkdir(parents=True,exist_ok=True)
 raw=source.read_bytes();assert sha(raw)==R10,'requires exact cumulative R10 SWF'
 swc=work/'town-theme-state.swc'
 cmd=[str(java),'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/compc-cli.jar'),'+configname=air','-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=false','-compiler.source-path='+str(HERE/'src'),'-include-classes=cn.town.TownThemeState','-output='+str(swc)]
 r=subprocess.run(cmd,capture_output=True,timeout=120);(work/'compile-helper.log').write_bytes(r.stdout+r.stderr)
 if r.returncode:raise RuntimeError((r.stdout+r.stderr).decode('utf8','replace'))
 helper=b.sc.helper_abc(swc)
 for body in helper.bodies:physical_labels(helper,body)
 (work/'town-theme-helper.abc').write_bytes(helper.serialize())
 version,header,tags=b.sc.parts(source);originals=[bytes(t[1]) for t in tags]
 tag,=[t for t in tags if t[3] and any(t[3].mn_name(i[0])=='pinball.context.remote::RequestQueue' for i in t[3].instances)]
 a=tag[3];old=copy.deepcopy(a);target=b.view(a);ov=b.view(old);pool=b.PoolEditor(a);q=lambda ns,n:qname(a,pool,ns,n)
 state=q('cn.town','TownThemeState');edits=[]
 def graft(label,code):
  index,=target.by_label[label];body=a.bodies[index];before=copy.deepcopy(body);at=2
  block=b.p.asm.assemble(code);body[5],body[6],_=b.p.asm.splice(body,at,block,b.p.asm.ENTER);body[1]+=4
  assert b.p.asm.unsplice(body[5],at,len(block))==before[5]
  origins=list(range(len(b.p.asm.decode(before[5]))));origins[at:at]=[None]*len(block)
  rows=b.p.asm.decode(body[5]);dest=set()
  for x in rows:
   if x.target is not None:dest.add(x.target)
   if x.cases is not None:dest.update([x.default]+x.cases)
  missing=[i for i in dest if i==len(rows) or rows[i].op!=9]
  for i in sorted(missing,reverse=True):
   body[5],body[6],_=b.p.asm.splice(body,i,[b.p.asm.Instruction(9)],b.p.asm.ENTER);origins[i:i]=[None]
  physical_labels(a,body);spans=[];pos=0;source_at=0
  while pos<len(origins):
   if origins[pos] is None:
    begin=pos
    while pos<len(origins) and origins[pos] is None:pos+=1
    spans.append({'at':source_at,'instructions':pos-begin})
   else:assert origins[pos]==source_at;source_at+=1;pos+=1
  proof=b.p.insertion_proof(ov.normalized(index),b.view(a).normalized(index),spans)
  edits.append({'label':label,'body':index,'method':body[0],'inputCodeSha256':sha(before[5]),'candidateCodeSha256':sha(body[5]),'insertionProof':proof,'inverseOriginalCodeExact':True,'physicalLabelsAdded':len(missing)})
 graft(RESPONSE,[('getlex',state),('getlocal_1',),('callpropvoid',q('','captureResponse'),1)])
 graft(SELECT,[('getlex',state),('getlocal_0',),('callproperty',q('','select'),1),('dup',),('pushnull',),('ifeq','OLD'),('coerce',q('pinball.common.data.town','TownContentLogic')),('returnvalue',),('label','OLD'),('pop',)])
 changed={e['body'] for e in edits};assert len(changed)==2
 for i,body in enumerate(old.bodies):
  if i not in changed:assert b.p.freeze(body)==b.p.freeze(a.bodies[i]),i
 abi={k:b.p.freeze(getattr(old,k))==b.p.freeze(getattr(a,k)) for k in ['methods','instances','classes','scripts','metadata']};assert all(abi.values())
 pools={k:b.p.freeze(getattr(old,k))==b.p.freeze(getattr(a,k)[:len(getattr(old,k))]) for k in ['strings','ints','uints','doubles','namespaces','ns_sets','multinames']};assert all(pools.values())
 data=tag[2]+b.sc.serialize(a,tag[4]);tag[1]=struct.pack('<HI',(82<<6)|63,len(data))+data
 payload=struct.pack('<I',1)+b'town_theme_login\0'+helper.serialize();extra=struct.pack('<HI',(82<<6)|63,len(payload))+payload
 old_index=tags.index(tag);tagbytes=[t[1] for t in tags];tagbytes.insert(old_index,extra);out=header+b''.join(tagbytes)
 output=work/'town-theme-android.swf';output.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(out)+8)+zlib.compress(out))
 final=b.sc.parts(output)[2];assert len(final)==len(tags)+1
 for i,t in enumerate(tags):
  if i!=old_index:assert bytes(final[i+(i>=old_index)][1])==originals[i],i
 assert final[old_index+1][3].serialize()==a.serialize() and final[old_index][3].serialize()==helper.serialize()
 helper_receipts=[]
 for owner,filename in [('cn.content::ContentOperationsState','production-helper.abc'),('cn.profile::PlayerHistoryState','player-history-helper.abc')]:
  prior,=[t[3] for t in tags if t[3] and any(t[3].mn_name(i[0])==owner for i in t[3].instances)]
  (work/filename).write_bytes(prior.serialize());helper_receipts.append({'owner':owner,'sha256':sha(prior.serialize()),'bodies':len(prior.bodies),'byteExact':True})
 assert helper_receipts[0]['bodies']==85
 record={'schema':'town-theme-client/v1','inputSwf':str(source),'inputSwfSha256':sha(raw),'candidateSwf':str(output),'candidateSwfSha256':sha(output.read_bytes()),'edits':edits,'changedNativeBodies':2,'nonTargetMethodsPreserved':True,'nativeAbiPreserved':abi,'appendOnlyPools':pools,'nonTargetTagsByteExact':True,'existingHelpers':helper_receipts,'finalReadbackExact':True,'packaged':False,'deviceTested':False}
 (work/'cumulative-method-preservation.json').write_text(json.dumps(record,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
 print(json.dumps({'candidate':str(output),'sha256':record['candidateSwfSha256'],'changedNativeBodies':2}))
def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['work','source','sdk','java']:p.add_argument('--'+n,type=Path,required=True)
 a=p.parse_args();build(a.work,a.source,a.sdk,a.java)
if __name__=='__main__':main()
