#!/usr/bin/env python3
"""Bind the six decoded exchange masters to the current effective CDN chain."""
import argparse, csv, hashlib, importlib.util, io, json, sys, zlib
from pathlib import Path

sys.dont_write_bytecode = True

def main():
    ap = argparse.ArgumentParser()
    for name in ('source', 'exporter', 'master', 'output'):
        ap.add_argument('--' + name, required=True)
    a = ap.parse_args()
    exporter = Path(a.exporter)
    sys.path.insert(0, str(exporter.parent))
    spec = importlib.util.spec_from_file_location('catalog_exporter', exporter)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    captured = json.loads(Path(a.master).read_text(encoding='utf8'))
    actual, source = mod.resolve(Path(a.source), sorted(captured))
    def decode(raw):
        try:
            return list(csv.reader(io.StringIO(zlib.decompress(raw).decode('utf8'))))
        except zlib.error:
            nested = mod.core.read_orderedmap_raw_rows_from_bytes(raw)
            return {key: decode(value) for key, value in zip(nested.keys, nested.rows)}
    checked = {}
    for logical, expected in captured.items():
        if logical not in actual:
            raise ValueError('current CDN master missing: ' + logical)
        raw, identity = actual[logical]
        if hashlib.sha256(raw).hexdigest() != expected['sha256'] or decode(raw) != expected['rows']:
            raise ValueError('current CDN master differs from reviewed rows: ' + logical)
        checked[logical] = identity
    result = {'schemaVersion': 1, 'manifestSha256': source['manifestSha256'],
              'assetVersion': source['assetVersion'], 'masterSources': checked,
              'allRowsMatched': True, 'scope': 'six current common/Android exchange masters; no client or transaction acceptance'}
    Path(a.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'tables': len(checked), 'assetVersion': source['assetVersion'],
                      'manifestSha256': source['manifestSha256'], 'allRowsMatched': True}))

if __name__ == '__main__':
    main()
