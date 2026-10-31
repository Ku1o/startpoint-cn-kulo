"""Small source-only audit of the three later iOS repair closures."""
from pathlib import Path
import argparse, ast, hashlib, json, re
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[2]
NAMES=('release1031-ios-dispatch-fix-20261031','release1031-ios-battle-f1069-fix-20261031','release1031-ios-independent-party-fix-20261031')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--modules',nargs='+',choices=NAMES,default=NAMES)
    options=parser.parse_args()
    count=0
    for name in options.modules:
        root=REPO/'client-patch'/name
        manifest=json.loads((root/'SOURCE-MANIFEST.json').read_text('utf-8'))
        for row in manifest['files']+manifest['shared_sources']:
            path=(REPO/row['repository_path']).resolve()
            assert path.is_relative_to(REPO) and path.is_file(), row['repository_path']
            raw=path.read_bytes()
            assert hashlib.sha256(raw).hexdigest()==row['sha256'], row['repository_path']
            text=raw.decode('utf-8-sig')
            if path.suffix=='.py':ast.parse(text,filename=str(path))
            elif path.suffix=='.json':json.loads(text)
            # Historical repository dependencies retain their own fixed-input mains.
            # New recipes and the relocated cumulative adapters must be path-free.
            if path.is_relative_to(HERE) or path.is_relative_to(root):
                assert not re.search(r'(?<!\w)[A-Za-z]:[/\\]|/(?:Users|home)/',text), row['repository_path']
            count+=1
        actual={p.relative_to(REPO).as_posix() for p in root.rglob('*') if p.is_file() and p.name!='SOURCE-MANIFEST.json'}
        assert actual=={r['repository_path'] for r in manifest['files']}, 'Unlisted source or stale manifest: '+name
    if NAMES[0] in options.modules:
        plan=json.loads((REPO/'client-patch'/NAMES[0]/'native/unwind_plan.json').read_text('utf-8'))
        algorithm=REPO/'client-patch'/NAMES[0]/'audit/probe_unwind_payload_dedup.py'
        assert hashlib.sha256(algorithm.read_bytes()).hexdigest()==plan['algorithm_source_sha256']
    if NAMES[2] in options.modules:
        source=(REPO/'client-patch'/NAMES[2]/'prepare.py').read_text('utf-8')
        assert "fc.private('followup_party_input_record')" in source and 'ios-accepted.json' not in source
    print(json.dumps(dict(status='source_hash_syntax_and_dependency_contracts_passed',files_checked=count,
                         aot_rebuilt=False,ipa_created=False,device_tested=False)))


if __name__=='__main__':main()
