"""Run the compiled candidate helper in an invisible, bounded desktop AIR harness."""
import argparse
import importlib.util
import json
import sys
from pathlib import Path
from patch_swf import s

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'tools/lens-integration'))
import prepare_content as p

spec = importlib.util.spec_from_file_location('shop_test_build', HERE.parent / 'startup-cache/build.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


def main(work, helper):
    assert not work.exists() and '.cdn' not in work.resolve().parts
    work.mkdir(parents=True)
    chain = p.Chain()
    blob = chain.get(('common', p.hrel('master/shop/event_item_shop.orderedmap')))
    products = []
    for ident, data in p.rawmap(blob).items():
        row = p.csvrows(data)[0]
        products.append({'id': int(ident), 'event': {'index': int(row[0]), 'params': [int(row[1])]}})
    (work / 'fixture.json').write_text(json.dumps({'products': products}), encoding='utf-8')
    (work / 'source-receipts.json').write_text(json.dumps({'version': chain.tail, 'reads': chain.reads}, indent=2), encoding='utf-8')
    b.run([b.JAVA, '-Dflexlib=' + str(b.SDK / 'frameworks'), '-Xmx512m', '-jar',
           b.SDK / 'lib/mxmlc-cli.jar', '+configname=air', '-swf-version=44', '-target-player=32.0',
           '-debug=false', '-omit-trace-statements=false', '-library-path+=' + str(helper), '-output=' + str(work / 'harness.swf'),
           HERE / 'tests/RuntimeHarness.as'], work, 'compile-harness')
    (work / 'harness-app.xml').write_text('''<?xml version="1.0" encoding="utf-8"?>
<application xmlns="http://ns.adobe.com/air/application/51.0">
 <id>cn.shop.firstopen.test</id><versionNumber>1.0.0</versionNumber><filename>ShopFirstOpenTest</filename>
 <initialWindow><content>harness.swf</content><visible>false</visible><width>1</width><height>1</height></initialWindow>
</application>''', encoding='utf-8')
    output = b.run([b.SDK / 'bin/adl.exe', '-profile', 'desktop', work / 'harness-app.xml'], work, 'air-runtime', timeout=60)
    reports = [line.removeprefix('SHOP_FIRST_OPEN_RESULT ') for line in output.splitlines()
               if line.startswith('SHOP_FIRST_OPEN_RESULT ')]
    assert len(reports) == 1, output
    result = json.loads(reports[0])
    result.update(helper_swc_sha256=b.sha(helper.read_bytes()),
                  helper_abc_sha256=b.sha(s.helper_abc(helper).serialize()),
                  helper_source_sha256=b.sha((HERE / 'src/cn/shop/ShopFirstOpen.as').read_bytes()),
                  harness_source_sha256=b.sha((HERE / 'tests/RuntimeHarness.as').read_bytes()))
    (work / 'air-results.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    assert result['passed'], result
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--helper', type=Path, required=True)
    args = parser.parse_args()
    main(args.work.resolve(), args.helper.resolve())
