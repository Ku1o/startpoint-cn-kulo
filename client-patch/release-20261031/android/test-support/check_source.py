"""Source-only syntax and identity check; no business imports or binary reads."""
from pathlib import Path
import argparse,ast,hashlib,json,re
ROOT=Path(__file__).resolve().parent
ANDROID=ROOT.parent
GROUPS=('carry163','tutorial','trigger9000','dash','packaging','test-support')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--repository',required=True);ap.add_argument('--output')
    args=ap.parse_args();repo=Path(args.repository).resolve()
    manifest=json.loads((ROOT/'SOURCE-MANIFEST.json').read_text(encoding='utf-8'))
    python=[];contracts=[];unchanged=[]
    for row in manifest['files']:
        path=(ANDROID/row['path']).resolve()
        assert path.is_relative_to(ANDROID) and path.parts[len(ANDROID.parts)] in GROUPS
        assert path.is_file() and sha(path)==row['sha256'],row['path']
        text=path.read_text(encoding='utf-8-sig')
        if path.suffix=='.py':ast.parse(text,filename=row['path']);python.append(row['path'])
        if path.suffix=='.json':json.loads(text);contracts.append(row['path'])
        assert not re.search(r'(?<![A-Za-z])[A-Za-z]:[\\/]',text),('machine path',row['path'])
    lineage=json.loads((ROOT/'SOURCE-LINEAGE.json').read_text(encoding='utf-8'))
    for row in lineage:
        if row['path'].endswith('.as') or row['path']=='test-support/abc_tools.py':
            assert sha(ANDROID/row['path'])==row['adapted_sha256'],('adopted current body source drift',row['path'])
            unchanged.append(row['path'])
    required=('client-patch/pr43-port/package_android.py','client-patch/pr43-port/x86_port.py',
              'client-patch/pr43-port/support/apk_manifest.py','client-patch/lens0907-0908/build_swf.py',
              'client-patch/content-operations/build_bridge.py','client-patch/content-operations/src/cn/content/ContentOperationsState.as',
              'client-patch/abyss-autostart/sign_apk.ps1')
    for name in required:assert (repo/name).is_file(),('repository dependency missing',name)
    deps=json.loads((ROOT/'DEPENDENCIES.json').read_text())
    for row in deps['repository_files']:
        assert sha(repo/row['path'])==row['sha256'],('repository dependency drift',row['path'])
    for row in deps['release_source_files']:
        assert sha(ANDROID.parent/row['path'])==row['sha256'],('release source dependency drift',row['path'])
    assert (ANDROID.parent/'settings/support/framework.py').is_file()
    assert (ANDROID/'capabilities/bootstrap.py').is_file()
    result={'status':'passed_source_syntax_contract_only','files':len(manifest['files']),
            'python_ast':len(python),'json_contracts':len(contracts),'current_AS_and_test_loader_hashes':len(unchanged),
            'repository_entries':len(required),'executed_business_methods':0,
            'compiled_or_launched':False,'binary_payload_read':False}
    if args.output:
        output=Path(args.output).resolve()
        assert not output.exists() and not output.is_relative_to(ANDROID) and not output.is_relative_to(repo)
        output.parent.mkdir(parents=True,exist_ok=True)
        output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
if __name__=='__main__':main()
