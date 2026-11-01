"""Bounded tutorial and independent-party equipment fixes; no APK or registry writes."""
import argparse,copy,hashlib,importlib.util,json,struct,sys,zipfile,zlib
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.insert(0,str(HERE.parent/'lens0907-0908'))
import build_swf as p
from swfabc import PoolEditor
spec=importlib.util.spec_from_file_location('c8601_startup_swf',HERE.parent/'startup-cache/build_swf.py')
sc=importlib.util.module_from_spec(spec);spec.loader.exec_module(sc)
TUTORIAL='pinball.common.data.tutorial::TutorialQuestLogic'
INPUT_APK='ca180d7d6707e2969aef12a88dd623d567affc05cde7bc8c382172225c65abf8'
INPUT_SWF='a4f73ebfef424d724cf4f47eb73396b8361fa41b083f1a29bde2cf1518d9bd43'
def sha(raw):return hashlib.sha256(raw).hexdigest()

def source_entry(record):
 entry=json.loads(record.read_text('utf8'))['variants']['public']
 if entry['apk_sha256']!=INPUT_APK or entry['swf_sha256']!=INPUT_SWF:
  raise ValueError('This historical delta requires the frozen release1031 input record; do not replay it on the repaired baseline')
 return entry

def patch(swf:Path,output:Path):
 version,header,tags=sc.parts(swf);edits=[]
 for owner,method in [('cn.content::ContentOperationsState$','questDecision'),('pinball.scene.equipmentList::EquipmentSellableStatusResolver','reasonToUiString'),('pinball.scene.equipmentList::EquipmentSellableStatusResolver','getPartyCategoryPriority')]:
  label=owner+'/'+method+'|1'
  matches=[]
  for tag in tags:
   if tag[0]!=82:continue
   a=tag[3]
   if not any(a.mn_name(i[0])==owner.rstrip('$') for i in a.instances):continue
   view=p.View(SimpleNamespace(abc=a),p.asm)
   if label in view.by_label:matches.append((tag,view))
  if len(matches)!=1:raise ValueError(('ambiguous target',label,len(matches)))
  tag,view=matches[0];a=tag[3];before=copy.deepcopy(a);oldview=p.View(SimpleNamespace(abc=before),p.asm)
  index,=view.by_label[label];body=a.bodies[index];pool=PoolEditor(a)
  rows=view.normalized(index)[0]
  if method=='questDecision':
   if TUTORIAL.encode() in a.strings:raise ValueError('tutorial patch already present')
   mn=next(i for i in range(1,len(a.multinames)) if a.mn_name(i)=='flash.utils::getQualifiedClassName')
   at=2
   block=p.asm.assemble([('findpropstrict',mn),('getlocal_1',),('callproperty',mn,1),('pushstring',pool.string(TUTORIAL)),('ifne','OLD'),('pushbyte',255),('returnvalue',),('label','OLD')])
  elif method=='reasonToUiString':
   switches=[i for i,row in enumerate(rows) if row[0]==0x1b]
   assert len(switches)==2
   at=switches[1]
   assert rows[at-1][0]==0x73
   assert all(rows[at][4][category]==rows[at][3] or rows[at][4][category]==rows[at][4][0] for category in (5,6,7))
   block=p.asm.assemble([('dup',),('pushbyte',5),('iflt','OLD'),('dup',),('pushbyte',7),('ifgt','OLD'),('pop',),('pushbyte',4),('label','OLD')])
  else:
   at=0
   block=p.asm.assemble([('getlocal_1',),('pushbyte',5),('iflt','OLD'),('getlocal_1',),('pushbyte',7),('ifgt','OLD'),('pushbyte',4),('setlocal_1',),('label','OLD')])
  origins=list(range(len(rows)))
  body[5],body[6],_=p.asm.splice(body,at,block,p.asm.ENTER);origins[at:at]=[None]*len(block)
  decoded=p.asm.decode(body[5]);destinations=set()
  for ins in decoded:
   if ins.target is not None:destinations.add(ins.target)
   if ins.cases is not None:destinations.update([ins.default]+ins.cases)
  for site in sorted([i for i in destinations if i==len(decoded) or decoded[i].op!=0x09],reverse=True):
   body[5],body[6],_=p.asm.splice(body,site,[p.asm.Instruction(0x09)],p.asm.ENTER);origins[site:site]=[None]
  body[1]+=4;p.check_body(body,a)
  spans=[];site=oldsite=0
  while site<len(origins):
   if origins[site] is None:
    start=site
    while site<len(origins) and origins[site] is None:site+=1
    spans.append({'at':oldsite,'instructions':site-start})
   else:
    assert origins[site]==oldsite
    oldsite+=1;site+=1
  proof=p.insertion_proof(oldview.normalized(index),view.normalized(index),spans)
  for i,b in enumerate(a.bodies):
   if i!=index:assert p.freeze(b)==p.freeze(before.bodies[i]),(label,i)
  for field in ('instances','classes','methods','scripts','metadata'):
   assert p.freeze(getattr(a,field))==p.freeze(getattr(before,field)),(label,field)
  for field in ('ints','uints','doubles','strings','namespaces','ns_sets','multinames'):
   prefix=getattr(before,field);assert p.freeze(getattr(a,field)[:len(prefix)])==p.freeze(prefix)
  edits.append({'label':label,'method':body[0],'body':index,'before':sha(before.bodies[index][5]),'after':sha(body[5]),'insertionProof':proof})
  payload=tag[2]+sc.serialize(a,tag[4]);tag[1]=struct.pack('<HI',(82<<6)|63,len(payload))+payload
 # After a second edit in one ABC, preserve the previous insertion in its serialised bytes.
 raw=header+b''.join(t[1] for t in tags)
 output.write_bytes(b'CWS'+bytes([version])+struct.pack('<I',len(raw)+8)+zlib.compress(raw))
 report={'inputSwf':str(swf),'inputSha256':sha(swf.read_bytes()),'outputSwf':str(output),'outputSha256':sha(output.read_bytes()),'edits':edits,'unchangedLayouts':True,'scope':'three method bodies only; no resource, save, admission or endpoint changes','deviceTested':False}
 (output.parent/'patch-report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
 return report

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--apk',type=Path,required=True);ap.add_argument('--work',type=Path,required=True);ap.add_argument('--record',type=Path,default=ROOT/'client-patch/android-accepted.json');args=ap.parse_args()
 entry=source_entry(args.record)
 assert sha(args.apk.read_bytes())==entry['apk_sha256'],'input must match the registered public APK'
 args.work.mkdir(parents=True,exist_ok=False)
 with zipfile.ZipFile(args.apk) as z:raw=z.read('assets/worldflipper_android_release.swf')
 assert sha(raw)==entry['swf_sha256']
 source=args.work/'baseline.swf';source.write_bytes(raw)
 report=patch(source,args.work/'fixed.swf')
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
