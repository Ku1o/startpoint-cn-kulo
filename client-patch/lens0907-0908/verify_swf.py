"""Independent FFDec readback; exit code alone does not prove export completion."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
CLASSES = [
    'pinball.scene.battle.battle.BothBossTool',
    'pinball.scene.battle.BattleScene',
    'pinball.dialog.battlePauseMenu.BattlePauseMenu',
    'pinball.scene.battle.battle.ability.BattleAbilityTotalizerImpl',
    'pinball.common.data.ability.AbilityLogic',
]


def run(command, log):
    with log.open('w', encoding='utf-8') as stream:
        proc = subprocess.Popen(list(map(str, command)), stdout=stream, stderr=subprocess.STDOUT)
        try:
            if proc.wait(timeout=180):
                raise RuntimeError(f'command failed: {log}')
        finally:
            if proc.poll() is None:
                subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], check=False, capture_output=True)
                proc.wait(timeout=15)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--base', type=Path, required=True)
    p.add_argument('--swf', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--ffdec', type=Path, required=True)
    a = p.parse_args()
    a.out.mkdir(parents=True, exist_ok=False)
    classes = a.out/'java'; classes.mkdir()
    run(['javac', '-cp', a.ffdec, '-d', classes, HERE/'CompareLensBodies.java'], a.out/'javac.log')
    run(['java', '-cp', f'{classes};{a.ffdec}', 'CompareLensBodies', a.base, a.swf, HERE/'expected-bodies.txt'], a.out/'bodies.log')
    exports = {}
    for cls in CLASSES:
        print('Independent export:', cls, flush=True)
        run(['java', '-Xmx2g', '-jar', a.ffdec, '-selectclass', cls, '-export', 'script', a.out/'as', a.swf], a.out/f'{cls}.log')
        path = a.out/'as/scripts'/Path(cls.replace('.', '/')+'.as')
        content = path.read_text('utf-8')
        # FFDec may return zero after a partial export (e.g. malformed defaults).
        assert content.rstrip().endswith('}'), f'truncated export: {cls}'
        assert content.count('{') == content.count('}'), f'incomplete export: {cls}'
        assert 'Decompilation error' not in content, cls
        exports[cls.rsplit('.', 1)[1]] = content
    boss = exports['BothBossTool']
    assert 'param4:String = ""' in boss and 'param2:int, param3:int) : int' in boss
    assert 'param2,_loc10_.roomNumber)' in boss
    for name in ('mapSeed', 'singleMapSeed', 'randomIndex', 'pickCandidate', 'isRandomMapQuest', 'isConditionalRow'):
        assert f'function {name}(' in boss, name
    assert '1099001' in boss and '1099099' in boss
    scene = exports['BattleScene']
    assert 'public var fiveBossManualAutoLock:Boolean;' in scene
    assert 'this.fiveBossManualAutoLock = false;' in scene
    assert 'this.questId.index == 1' in scene
    assert '>= 1099001' in scene and '<= 1099003' in scene
    assert 'this.fiveBossManualAutoLock = !this.myBattle.autoplayData.autoButtonMode;' in scene
    guard = scene.split('public function changeAutoplayMode(', 1)[1].split('public function ', 1)[0]
    assert 'if(param1)' in guard and 'if(this.fiveBossManualAutoLock)' in guard
    assert guard.index('system_lock_auto_play') < guard.index('return;')
    assert 'pinball.context.scene.instantMessage.InstantMessagePosition;' in scene
    assert 'get_isTutorial() || !get_autoPlayUnlocked() || this.battleScene.fiveBossManualAutoLock' in exports['BattlePauseMenu']
    assert 'get_isTutorial() || !get_attentionUnlocked()' in exports['BattlePauseMenu']
    assert 'public function getTotalDashParameter(param1:int) : Number' in exports['BattleAbilityTotalizerImpl']
    sha = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
    result = {'status': 'passed_static_readback', 'base_swf_sha256': sha(a.base),
              'swf_sha256': sha(a.swf), 'independent_parser': 'FFDec',
              'existing_body_total': 96397, 'changed_existing_bodies': 32, 'added_bodies': 7,
              'exports': CLASSES, 'device_tested': False}
    (a.out/'verification.json').write_text(json.dumps(result, indent=2)+'\n', 'utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
