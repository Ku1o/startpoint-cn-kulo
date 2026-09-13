"""Independent parser/decompiler readback and original awakening failure replay."""
import argparse
import json
import sys
from pathlib import Path

from patch_swf import module, s

HERE = Path(__file__).resolve().parent
b = module('shop_verify_build', HERE.parent / 'startup-cache/build.py')
awake_test = module('shop_awake_test', HERE.parent / 'awake-page-refresh/test_bytecode.py')
CLASSES = [
    'cn.shop.ShopFirstOpen',
    'pinball.common.data.shop.ShopProductRepository',
    'pinball.scene.shop.shopTop.ShopTopScene',
    'pinball.scene.eventItemExchange.top.EventItemExchangeTopScene',
    'pinball.scene.characterAwake.CharacterAwakeScene',
]


def main(source, candidate, work):
    assert not work.exists() and '.cdn' not in work.parts
    work.mkdir(parents=True)
    ffdec = Path('F:/codex/tools/ffdec_26.2.1/ffdec.jar')
    classes = work / 'java'
    classes.mkdir()
    b.run([b.JAVA.with_name('javac.exe'), '-cp', ffdec, '-d', classes, HERE / 'CompareBodies.java'],
          work, 'compile-verifier')
    independent = b.run([b.JAVA, '-Xmx2g', '-cp', str(classes) + ';' + str(ffdec),
                         'CompareBodies', source, candidate], work, 'independent-parser')
    assert independent.startswith('PASS original_bodies=96535 added_bodies=8')
    # Replay the actual final callback, whose main ABC moved past the helper.
    original = [t[3] for t in s.parts(source)[2] if t[0] == 82][290]
    patched = [t[3] for t in s.parts(candidate)[2] if t[0] == 82][291]
    broken = awake_test.Scene(0, 1)
    broken.save.map = {1: 1}
    awake_test.run(original, 67327, broken, {9: ['completed']})
    assert broken.boardAwakeLevel == 0 and 2 in broken.tabGroup.disabledTabButtons
    cases = []
    for old, new, tab in [(0, 1, 1), (0, 0, 1), (1, 1, 1), (1, 1, 2), (0, 2, 1)]:
        scene = awake_test.Scene(old, tab)
        scene.save.map = {1: new}
        missions = {9: ['server progress']}
        for repeat in range(3):
            awake_test.run(patched, 67327, scene, missions)
            assert scene.targetCharacter.getManaBoardAwakeLevel(1) == scene.boardAwakeLevel == new
            assert scene.currentTabKind == tab and scene.missionMap is missions and scene.hasRequestMissionList
            assert scene.reloads == repeat + 1
            assert (2 in scene.tabGroup.disabledTabButtons) == (new == 0)
            assert scene.tabGroup.states[2] == (4 if new == 0 else (2 if tab == 2 else 1))
        cases.append({'old': old, 'new': new, 'tab': tab, 'replays': 3})
    b.run([b.JAVA, '-Xmx4g', '-jar', ffdec, '-config', 'parallelSpeedUp=false',
           '-onerror', 'abort', '-timeout', '30', '-exportTimeout', '150',
           '-selectclass', ','.join(CLASSES), '-export', 'script', work / 'decompiled', candidate],
          work, 'decompile-selected', timeout=180)
    for cls in CLASSES:
        file = work / 'decompiled/scripts' / (cls.replace('.', '/') + '.as')
        assert file.is_file() and file.stat().st_size > 100, cls
    shop = (work / 'decompiled/scripts/pinball/common/data/shop/ShopProductRepository.as').read_text('utf-8')
    assert shop.count('ShopFirstOpen.productIds(') == 2
    top = (work / 'decompiled/scripts/pinball/scene/shop/shopTop/ShopTopScene.as').read_text('utf-8')
    assert top.count('ShopFirstOpen.shopTopExists(globalLogic)') == 1
    folder = (work / 'decompiled/scripts/pinball/scene/eventItemExchange/top/EventItemExchangeTopScene.as').read_text('utf-8')
    assert folder.count('ShopFirstOpen.sideStoryExists(') == 1
    assert '.getSideStoryEventList().getExchangeableEvents(' in folder  # Real folder list remains complete.
    report = {'passed': True, 'candidate_swf_sha256': s.sha(candidate.read_bytes()),
              'independent_parser': independent.strip(), 'decompiled_classes': CLASSES,
              'original_awake_bug_reproduced': True, 'final_awake_cases': cases,
              'validation_scope': 'actual SWF parser, narrow decompiler, bounded callback instruction replay',
              'device_tested': False}
    (work / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('candidate', type=Path)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    main(args.source.resolve(), args.candidate.resolve(), args.work.resolve())
