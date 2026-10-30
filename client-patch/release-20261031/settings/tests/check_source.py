"""Read-only syntax/source-contract check. No imports, compilers, SWFs or subprocesses."""
from pathlib import Path
import argparse, ast, hashlib, json, re
ROOT=Path(__file__).resolve().parents[1]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repository',required=True)
    ap.add_argument('--output');args=ap.parse_args();repo=Path(args.repository).resolve()
    manifest=json.loads((ROOT/'SOURCE-MANIFEST.json').read_text(encoding='utf-8'))
    files=[];python=[];contracts=[]
    for row in manifest['files']:
        path=(ROOT/row['path']).resolve()
        assert path.is_relative_to(ROOT) and path.is_file(),row['path']
        assert sha(path)==row['sha256'],('source hash differs',row['path'])
        text=path.read_text(encoding='utf-8-sig')
        if path.suffix=='.py':ast.parse(text,filename=row['path']);python.append(row['path'])
        if path.suffix=='.json':json.loads(text);contracts.append(row['path'])
        assert not re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]',text),('absolute machine path',row['path'])
        files.append(row['path'])
    lineage=json.loads((ROOT/'SOURCE-LINEAGE.json').read_text(encoding='utf-8'))
    sources={row['path']:row for row in lineage['files']}
    for relative in ('ui/patch.py','render/patch.py','render/air_harness.as',
                     'storage-validation/air_harness.as','storage-validation/Launcher.as'):
        assert sha(ROOT/relative)==sources[relative]['adapted_sha256'],('adopted current business source changed',relative)
    anchors=ast.parse((ROOT/'support/selected_patch.py').read_text(encoding='utf-8-sig'))
    assert not any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name=='build' for n in anchors.body)
    support=json.loads((ROOT/'contracts/repository-support.json').read_text())
    for name,digest in support.items():
        assert sha(repo/'client-patch/pr43-port/support'/name)==digest,('repository support drift',name)
    assert (repo/'client-patch/lens0907-0908/build_swf.py').is_file(),'repository native importer missing'
    result={'status':'passed_source_syntax_and_contract_only','files':len(files),
            'python_ast':len(python),'json_contracts':len(contracts),
            'current_business_and_AS_hashes':5,'repository_support_files':len(support),
            'executed_business_methods':0,'compiled_or_launched':False,
            'limits':['No Python business module import','No SWF build/graft/AIR','No device acceptance']}
    if args.output:
        output=Path(args.output).resolve()
        assert not output.exists() and not output.is_relative_to(ROOT) and not output.is_relative_to(repo)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
