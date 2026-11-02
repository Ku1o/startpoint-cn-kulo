"""Actual request identity/queue methods; transport and UI are recording dependencies."""
import json, shutil, subprocess, time
from pathlib import Path
import abc_tools as abc

def build(ctx, out):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    templates=Path(ctx['tool_root'])/'templates/queue';src=out/'src'
    shutil.copytree(templates,src)
    includes=[str(p.relative_to(src)).replace('\\','/').removesuffix('.as').replace('/','.') for p in src.rglob('*.as') if p.stem!='StateTest']
    sdk=Path(ctx['sdk']);repo=Path(ctx['repo']);template=out/'template.swf'
    command=[ctx['java'],'-Dflexlib='+str(sdk/'frameworks'),'-jar',str(sdk/'lib/mxmlc-cli.jar'),'+configname=air','-swf-version=44','-target-player=32.0','-compiler.float=false','-compress=false','-debug=true','-includes='+','.join(includes),'-compiler.source-path='+str(src),'-compiler.source-path+='+str(repo/'client-patch/content-operations/src'),'-output='+str(template),str(src/'StateTest.as')]
    started=time.perf_counter();process=subprocess.run(command,cwd=out,capture_output=True,timeout=120)
    (out/'compile.log').write_bytes(process.stdout+process.stderr)
    (out/'compile.json').write_text(json.dumps({'command':command,'exit_code':process.returncode,'elapsed_ms':round((time.perf_counter()-started)*1000,3)},indent=2),encoding='utf-8')
    if process.returncode:raise RuntimeError('queue compilation failed: '+str(out/'compile.log'))
    builder,main,main_view,identity=abc.load_current()
    helper_hits=[]
    for name,raw in abc.raw_units(Path(ctx['swf']).read_bytes()):
        if b'ContentOperationsState' not in raw:continue
        unit=builder.abcfmt.ABC(raw)
        if any(unit.mn_name(row[0])=='cn.content::ContentOperationsState' for row in unit.instances):helper_hits.append((name,unit))
    if len(helper_hits)!=1:raise ValueError('Expected exactly one ContentOperationsState definition')
    helper_name,helper=helper_hits[0]
    template_bytes=template.read_bytes();unit,=list(abc.raw_units(template_bytes))
    target=builder.abcfmt.ABC(unit[1])
    labels=json.loads((templates/'methods.json').read_text(encoding='utf-8'))
    groups=[]
    for source,label_set,unit_name in [(helper,labels['helper'],helper_name),(main,labels['main'],identity['main_label'])]:
        mapping=abc.graft(target,source,label_set);groups.append((source,mapping,unit_name))
    output=out/'Harness.swf';output.write_bytes(abc.replace_abc(template_bytes,target))
    final=builder.abcfmt.ABC(list(abc.raw_units(output.read_bytes()))[0][1]);proof=[]
    for source,mapping,unit_name in groups:
        proof.extend([{**row,'source_unit':unit_name} for row in abc.verify_grafts(final,source,mapping)])
    proof_path=out/'graft-proof.json'
    proof_path.write_text(json.dumps({'input':identity,'real_methods':proof,'execution_swf_sha256':abc.sha(output.read_bytes()),'limits':['8 actual RequestQueue methods and 5 factory/config/constructor methods; imported body count is not execution coverage.','Recording network, admission, activity, response parser and error classifier. Retry interval is zero for deterministic steps.']},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    application=out/'application.xml';application.write_text('<application xmlns="http://ns.adobe.com/air/application/51.2"><id>local.starpoint.air.queue</id><versionNumber>1.0.0</versionNumber><filename>queue</filename><initialWindow><content>Harness.swf</content><visible>false</visible></initialWindow></application>',encoding='utf-8')
    return {'application':application,'swf':output,'proof':proof_path,'required_case_ids':['request-identity'],'min_assertions':47}
