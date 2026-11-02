"""Actual registered-client callbacks in a cmd-only carrier; no ADL side effects."""
from __future__ import annotations
from pathlib import Path
import hashlib,json,shutil,subprocess,time
import abc_tools as abc
import common

def _save(path,value):
 path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def _label(source,view,owner,name):
 indices=[i for i,r in enumerate(source.instances) if source.mn_name(r[0])==owner]
 if len(indices)!=1:raise ValueError('Required owner missing or ambiguous: '+owner)
 ci=indices[0];row=source.instances[ci]
 if name in ('<ctor>','<init>'):mid=row[5]
 else:
  traits=[t for t in [*row[6],*source.classes[ci][1]] if t.data[0]=='method' and source.mn_name(t.name).rsplit('::',1)[-1]==name]
  if len(traits)!=1:raise ValueError('Required method missing or ambiguous: '+owner+'.'+name)
  mid=traits[0].data[2]
 return view.labels[mid]

def _build(ctx,out,entry):
 out=abc.output_directory(ctx,out);out.mkdir(parents=True,exist_ok=True)
 shared=common.prepare_sources(ctx,out/'common')
 template_root=Path(ctx['tool_root'])/'templates/flows';src=out/'src';src.mkdir(parents=True,exist_ok=True)
 for path in template_root.rglob('*.as'):
  if path.name in ('FlowHarness.as','ExHarness.as') and path.stem!=entry:continue
  target=src/path.relative_to(template_root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
 includes=list(shared['includes'])
 includes += [str(p.relative_to(src)).replace('\\','/').removesuffix('.as').replace('/','.') for p in src.rglob('*.as') if p.stem!=entry]
 includes=list(dict.fromkeys(includes))
 command=[str(ctx['java']),'-Xmx1g','-Dflexlib='+str(Path(ctx['sdk'])/'frameworks'),'-jar',str(Path(ctx['sdk'])/'lib/mxmlc-cli.jar'),'+configname=air','-compiler.float=false','-swf-version=44','-target-player=32.0','-debug=true','-compress=false','-compiler.source-path='+str(src)+','+str(shared['source_dir']),'-includes='+','.join(includes),'-output='+str(out/'template.swf'),str(src/(entry+'.as'))]
 started=time.perf_counter();run=subprocess.run(command,cwd=out,capture_output=True,timeout=120)
 (out/'compile.log').write_bytes(run.stdout+run.stderr)
 fingerprints={str(p):abc.sha(p.read_bytes()) for root in (src,Path(shared['source_dir'])) for p in root.rglob('*.as')}
 _save(out/'compile-receipt.json',{'command':command,'exit_code':run.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3),'source_sha256':fingerprints})
 if run.returncode:raise RuntimeError('Compiler failed: '+str(out/'compile.log'))
 builder,source,sv,identity=abc.load_current();template=(out/'template.swf').read_bytes();units=list(abc.raw_units(template))
 if len(units)!=1:raise ValueError('Expected exactly one compiled carrier ABC')
 target=builder.abcfmt.ABC(units[0][1]);tv=abc.view(target)
 required=json.loads((template_root/'selections.json').read_text(encoding='utf-8'))
 selections=list(shared['selections'])+[_label(source,sv,r['owner'],r['name']) for r in required]
 # Every declared selection is required and linked. No omit-on-missing path.
 for spec in selections:
  label=spec if isinstance(spec,str) else spec.get('target',spec['source'])
  if label not in tv.by_label:raise ValueError('Required carrier target missing: '+label)
 mapping=abc.graft(target,source,selections);payload=abc.replace_abc(template,target)
 swf=out/'Harness.swf';swf.write_bytes(payload)
 parsed=builder.abcfmt.ABC(list(abc.raw_units(payload))[0][1]);proof=abc.verify_grafts(parsed,source,mapping)
 proof_path=out/'proof.json'
 _save(proof_path,{'suite':'ex' if entry=='ExHarness' else 'flows','identity':identity,'real_methods':proof,'execution_swf_sha256':abc.sha(payload),'missing_required_methods':[],'external_boundaries':['Typed recording dispatcher, configuration application, account storage and login analytics.','Flash global mathematical functions provide the Haxe Math aliases; actual integer conversion algorithm remains grafted.','Town/content response capture is recorded here; gacha-entry uses the actual complete operations helper in a separate carrier.','This general callback carrier does not validate EX reward presentation; the dedicated mail-ex suite covers actual difference and per-mail grouping.']})
 application=out/'application.xml'
 application.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.clientair.'+entry.lower()+'</id><versionNumber>1.0.0</versionNumber><filename>client-air-test</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
 return {'application':application,'swf':swf,'proof':proof_path,'required_case_ids':[],'required_step_ids':[]}

def build(ctx,out:Path):return _build(ctx,out,'FlowHarness')
