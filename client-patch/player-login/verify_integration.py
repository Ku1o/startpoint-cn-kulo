"""Read-only comparison of the complete login integration and its build/runtime copies."""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def verify(build: Path, runtime: Path) -> dict:
    manifest = json.loads(Path(__file__).with_name('integration-files.json').read_text('utf8'))
    sources = manifest['server_sources'] + manifest['admin_sources']
    paths = sources + ['out/' + p[4:-3] + '.js' for p in manifest['server_sources']]
    entry = 'web/dist/index.html'
    html = (build / entry).read_text('utf8')
    assets = re.findall(r'(?:src|href)="/admin/(assets/[^"?#]+\.(?:js|css))"', html)
    if not assets or len(assets) != len(set(assets)):
        raise ValueError('admin entry must name unique built assets')
    paths += [entry] + ['web/dist/' + p for p in assets]
    failures = []
    hashes = {}
    for rel in paths:
        if Path(rel).is_absolute() or '..' in Path(rel).parts:
            raise ValueError('invalid integration path')
        digests = {}
        for label, base in [('source', ROOT), ('build', build), ('runtime', runtime)]:
            path = base / rel
            digests[label] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        if None in digests.values() or len(set(digests.values())) != 1:
            failures.append({'path': rel, 'digests': digests})
        hashes[rel] = digests['build']
    for rel, expected in [(manifest['client']['apk'], manifest['client']['apk_sha256']),
                          (manifest['client']['helper_source'], manifest['client']['helper_source_sha256'])]:
        path = ROOT / rel
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            failures.append({'path': rel, 'reason': 'client identity differs from reviewed integration'})
    cdn = Path('assets/asset-patch/manifest.json')
    # Git and the local runtime use different line endings for the same JSON.
    if json.loads((ROOT / cdn).read_bytes()) != json.loads((runtime / cdn).read_bytes()):
        failures.append({'path': cdn.as_posix(), 'reason': 'source/runtime CDN configuration differs'})
    return {'status': 'failed' if failures else 'passed', 'files_checked': len(paths),
            'source_task': manifest['source_task'], 'failures': failures, 'build_sha256': hashes,
            'note': '文件一致性检查；不能替代接口回归、签名或手机验收。'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-tree', required=True, type=Path)
    parser.add_argument('--runtime', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = verify(args.build_tree.resolve(), args.runtime.resolve())
    if args.report:
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps({k: v for k, v in result.items() if k != 'build_sha256'}, ensure_ascii=False))
    raise SystemExit(result['status'] != 'passed')
