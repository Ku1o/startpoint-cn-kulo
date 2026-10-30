"""Compile only the unique wildcard sidecar after actual Stage1 inspection.

Future bounded stage. The Java compiler is also hidden by run_background and
remains inside the outer Windows Job. No existing iOS ABC/native is changed.
"""
import sys as _release_sys
from pathlib import Path as _ReleasePath
_release_sys.path.insert(0, str(next(p for p in _ReleasePath(__file__).resolve().parents if (p / 'input_config.py').is_file())))
import input_config as cfg
cfg.bootstrap()
from pathlib import Path
import argparse,json,shutil,subprocess,sys,zipfile
import repair_common as c
import storage_adapter as storage

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--inspection',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    job=c.bounded_job();inspection=c.read(args.inspection);out=c.fresh(args.output)
    c.require(inspection['previousIdentityEvidenceReused']['fullAbcSha256']==c.ABC_SHA,'Wrong inspection baseline')
    c.require(inspection['ledger']['proposedNewSidecar']==storage.STATE and
              not inspection['ledger']['proposedNewSidecarExists'],'Sidecar QName is not available')
    c.require(not inspection['ledger']['currentTraits'],'Existing ledger requires another adapter')
    java=shutil.which('java');c.require(java is not None,'Existing Java toolchain not found')
    out.mkdir(parents=True)
    source=out/'src/cn/release'/f'{storage.STATE_CLASS}.as';source.parent.mkdir(parents=True)
    source_text=storage.source_text([dict(type='*',source_type=0,sidecar_field='hpLossLedger')])
    source.write_text(source_text,'utf-8');swc=out/'storage.swc'
    compiler=[java,'-Xmx640m','-Dflexlib='+str(c.SDK/'frameworks'),'-jar',str(c.SDK/'lib/compc-cli.jar'),
        '+configname=air','-swf-version=44','-target-player=32.0','-compiler.float=false','-debug=false',
        '-compiler.source-path='+str(out/'src'),'-include-classes='+storage.STATE.replace('::','.'),'-output='+str(swc)]
    command=[sys.executable,'-B',str(c.BACKGROUND),'--timeout','110','--cwd',str(out),'--',*compiler]
    with (out/'compc.log').open('xb') as log:
        process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120,check=False)
    c.require(process.returncode==0,'Sidecar compc failed; inspect log, no retry/fallback')
    with zipfile.ZipFile(swc) as z:
        library=z.read('library.swf')
    swf=out/'library.swf';swf.write_bytes(library)
    p=c.framework();tags=p.asm.load_abc_module('swftags');_,_,_,body=tags.load_swf(str(swf));found=[]
    for kind,at,header,size in tags.iter_tags(body):
        if kind!=82:continue
        payload=body[at+header:at+header+size];end=payload.index(b'\0',4);found.append(payload[end+1:])
    c.require(len(found)==1,'Exactly one sidecar ABC required')
    raw,=found;a=p.abcfmt.ABC(raw)
    c.require([a.mn_name(r[0]) for r in a.instances]==[storage.STATE],'Unexpected runtime sidecar class')
    field,=[t for t in a.classes[0][1] if t.kind==0]
    c.require(a.mn_name(field.name)=='hpLossLedger' and field.data[2:]==[0,0,None],'Wildcard/default mismatch')
    scripts=[(i,mid) for i,(mid,traits) in enumerate(a.scripts) if any(t.kind==4 and t.data[2]==0 for t in traits)]
    c.require(len(scripts)==1,'Sidecar owning script initializer ambiguous')
    lifecycles={a.instances[0][5],a.classes[0][0],scripts[0][1]}
    c.require(lifecycles=={b[0] for b in a.bodies},'Unexpected sidecar methods require review')
    abc=out/'sidecar.abc';abc.write_bytes(raw)
    report=dict(status='wildcard_sidecar_compc_only_not_arm64_atom_verified',abc=str(abc),abc_sha256=c.sha(raw),
        state_qname=storage.STATE,source=str(source),source_sha256=c.sha(source_text.encode()),
        source_lifecycle_ids=sorted(lifecycles),owning_script=scripts[0][0],slot_type_index=0,
        slot_default='undefined',eager_dictionary_allocation=False,compiler_command=compiler,
        inspection_report=str(args.inspection.resolve()),inspection_sha256=c.sha(args.inspection.read_bytes()),
        atom_native_abi_verified=False,jobAtEntry=job,native_executed=False)
    c.dump(out/'sidecar-report.json',report)
    print(json.dumps(dict(status=report['status'],source_lifecycles=len(lifecycles),abc_sha256=c.sha(raw))))

if __name__=='__main__':main()
