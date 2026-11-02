"""Read-only production input and existing AVM2 importer; no import-time writes."""
from __future__ import annotations
import hashlib,importlib.util,struct,sys,types,zlib
from pathlib import Path
from functools import lru_cache
sys.dont_write_bytecode=True
_CONFIG={}
builder=None
swftags=None
REPO=None
SWF=None
EXPECTED=None
DEFAULT_ANCHORS=('pinball.remote.common::ResponseData','pinball.context.remote.real::RealRemoteService','pinball.common.data.player::PlayerLogic')

def configure(ctx):
 """Configure one explicit repository/toolchain/input; never choose a historical input."""
 global _CONFIG,builder,swftags,REPO,SWF,EXPECTED
 if not __debug__:raise RuntimeError('Run without Python -O; proof assertions are required')
 required=('repo','swf','swf_sha256','sdk','java','tool_root','run_root')
 missing=[k for k in required if k not in ctx]
 if missing:raise ValueError('Missing context keys: '+', '.join(missing))
 configured={k:str(ctx[k]) for k in required}
 for key in required:
  if key!='swf_sha256' and not Path(configured[key]).is_absolute():raise ValueError('Context path must be absolute: '+key)
 digest=configured['swf_sha256'].lower()
 if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('swf_sha256 must be a full SHA-256')
 configured['swf_sha256']=digest
 repo=Path(configured['repo']).resolve()
 if builder is not None and repo!=REPO:raise RuntimeError('Use a new process when switching the importer repository')
 if builder is None:
  importer=repo/'client-patch/lens0907-0908/build_swf.py'
  if not importer.is_file():raise FileNotFoundError('Existing repository importer missing: '+str(importer))
  sys.path.insert(0,str(importer.parent))
  spec=importlib.util.spec_from_file_location('client_air_existing_importer',importer)
  module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
  builder=module
  from swfabc import swftags as existing_tags
  swftags=existing_tags
 if _CONFIG!=configured:_load_current.cache_clear()
 _CONFIG=configured;REPO=repo;SWF=Path(configured['swf']);EXPECTED=digest
 return dict(_CONFIG)

def output_directory(ctx,out):
 configure(ctx)
 path=Path(out).resolve();root=Path(ctx['run_root']).resolve()
 if not path.is_relative_to(root):raise ValueError('Suite output is outside run_root: '+str(path))
 return path

def sha(raw):return hashlib.sha256(raw).hexdigest()
def view(abc):
 if builder is None:raise RuntimeError('Call abc_tools.configure(ctx) first')
 return builder.View(types.SimpleNamespace(abc=abc),builder.asm)
def raw_units(raw):
 if swftags is None:raise RuntimeError('Call abc_tools.configure(ctx) first')
 if raw[:3] not in (b'CWS',b'FWS'):raise ValueError('Only FWS/CWS SWF inputs are supported')
 body=zlib.decompress(raw[8:]) if raw[:3]==b'CWS' else raw[8:]
 for code,at,header,size in swftags.iter_tags(body):
  if code==82:
   p=body[at+header:at+header+size];end=p.index(b'\0',4)
   yield p[4:end].decode('utf-8'),p[end+1:]
def replace_abc(raw,abc):
 if raw[:3] not in (b'CWS',b'FWS'):raise ValueError('Only FWS/CWS SWF templates are supported')
 body=zlib.decompress(raw[8:]) if raw[:3]==b'CWS' else raw[8:]
 tags=[(c,a,h,n) for c,a,h,n in swftags.iter_tags(body) if c==82]
 assert len(tags)==1,'Expected one compiled target DoABC'
 _,at,header,size=tags[0];p=body[at+header:at+header+size];end=p.index(b'\0',4)
 payload=p[:end+1]+abc.serialize();tag=struct.pack('<HI',(82<<6)|63,len(payload))+payload
 final=body[:at]+tag+body[at+header+size:]
 return b'FWS'+raw[3:4]+struct.pack('<I',len(final)+8)+final
def load_current(anchor_classes=None):
 if builder is None:raise RuntimeError('Call abc_tools.configure(ctx) first')
 if isinstance(anchor_classes,str):raise ValueError('anchor_classes must be a nonempty sequence of QNames')
 anchors=DEFAULT_ANCHORS if anchor_classes is None else tuple(anchor_classes)
 if not anchors or any(not isinstance(q,str) or not q for q in anchors):raise ValueError('anchor_classes must be a nonempty sequence of QNames')
 return _load_current(anchors)
@lru_cache(maxsize=2)
def _load_current(anchors):
 raw=SWF.read_bytes()
 if sha(raw)!=EXPECTED:raise ValueError('SWF does not match the explicitly selected SHA-256: '+str(SWF))
 matches=[]
 for ordinal,(name,unit) in enumerate(raw_units(raw)):
  parsed=builder.abcfmt.ABC(unit)
  classes={parsed.mn_name(i[0]) for i in parsed.instances}
  if set(anchors)<=classes:matches.append((ordinal,name,unit,parsed))
 if len(matches)!=1:raise ValueError('Required classes must locate exactly one ABC; matches='+str([(i,n) for i,n,_,_ in matches]))
 ordinal,name,main,abc=matches[0]
 dependency_files=[Path(builder.__file__),Path(builder.asm.__file__),Path(builder.abcfmt.__file__),Path(swftags.__file__),Path(sys.modules[builder.View.__module__].__file__)]
 return builder,abc,view(abc),{'swf':str(SWF),'swf_sha256':EXPECTED,'main_abc_sha256':sha(main),'main_label':name,'main_abc_ordinal':ordinal,'anchor_classes':list(anchors),'main_method_bodies':len(abc.bodies),'importer':str(REPO/'client-patch/lens0907-0908/build_swf.py'),'importer_dependency_sha256':{str(p.resolve()):sha(p.read_bytes()) for p in dependency_files}}
def body_index(abc,mid):
 hit,=[i for i,b in enumerate(abc.bodies) if b[0]==mid];return hit
def graft(target,source,selections):
 """Selections are source-label strings or {'source':label,'target':label}.
 Same owner names recommended. Appends only actual nested method/closure bodies.
 """
 sv,tv=view(source),view(target);imp=builder.Importer(tv,sv);selected=[]
 source_bodies={b[0]:i for i,b in enumerate(source.bodies)}
 for spec in selections:
  sl=spec if isinstance(spec,str) else spec['source'];tl=spec if isinstance(spec,str) else spec.get('target',sl)
  assert len(sv.by_label[sl])==1,('source',sl)
  assert len(tv.by_label[tl])==1,('target not uniquely linked',tl)
  si,=sv.by_label[sl];ti,=tv.by_label[tl];sm,tm=source.bodies[si][0],target.bodies[ti][0]
  imp.methods[sm]=tm;selected.append((sm,tm,sl,tl))
 # Keep compiled interface/private namespaces aligned with the exact donor trait.
 for sm,tm,sl,tl in selected:
  st=[t for row in source.instances for t in row[6] if t.data[0]=='method' and t.data[2]==sm]+[t for row in source.classes for t in row[1] if t.data[0]=='method' and t.data[2]==sm]
  tt=[t for row in target.instances for t in row[6] if t.data[0]=='method' and t.data[2]==tm]+[t for row in target.classes for t in row[1] if t.data[0]=='method' and t.data[2]==tm]
  if st and tt:
   assert len(st)==len(tt)==1
   tt[0].name=imp.pool('multinames',st[0].name)
 pending=list(selected);seen=set();all_methods=[]
 while pending:
  sm,tm,sl,tl=pending.pop(0)
  if sm in seen:continue
  seen.add(sm);all_methods.append((sm,tm,sl,tl))
  for ins in builder.asm.decode(source.bodies[source_bodies[sm]][5]):
   if ins.op in (0x40,0x44):
    child=ins.args[0]
    if imp.methods.get(child) is None:
     imp.methods[child]=len(target.methods);target.methods.append([0,[],0,0,None,None])
     target.bodies.append([imp.methods[child],1,1,0,0,b'\x47',[],[]])
    pending.append((child,imp.methods[child],sv.labels[child],sv.labels[child]))
 for sm,tm,sl,tl in all_methods:
  si=source_bodies[sm];ti=body_index(target,tm)
  target.methods[tm]=imp.info(sm)
  target.bodies[ti]=imp.body(si,tm)
  builder.check_body(target.bodies[ti],target)
 # Reparse on disk separately via verify_grafts. Normalized operands retain branches,
 # exceptions, original instruction order, flags, activation and MethodInfo defaults.
 return [{'source_label':sl,'target_label':tl,'source_mid':sm,'target_mid':tm,'source_code_sha256':sha(source.bodies[source_bodies[sm]][5])} for sm,tm,sl,tl in all_methods]
def verify_grafts(target,source,mapping):
 sv,tv=view(source),view(target);imp=builder.Importer(tv,sv);proof=[]
 for row in mapping:
  sm,tm=row['source_mid'],row['target_mid'];si=body_index(source,sm);ti=body_index(target,tm)
  assert source.bodies[si][1:5]==target.bodies[ti][1:5],row['source_label']
  assert tv.normalized(ti)==sv.normalized(si),row['source_label']
  assert target.methods[tm]==imp.info(sm),row['source_label']
  expected_traits=[imp.trait(t,append=False) for t in source.bodies[si][7]]
  assert builder.freeze(expected_traits)==builder.freeze(target.bodies[ti][7]),row['source_label']
  proof.append({**row,'target_code_sha256':sha(target.bodies[ti][5]),'normalized_code_exceptions_equal':True,'method_info_flags_defaults_exact':True,'stack_locals_scope_exact':True,'activation_traits_exact_after_pool_mapping':True,'source_activation_traits':len(source.bodies[si][7]),'target_activation_traits':len(target.bodies[ti][7])})
 return proof
