"""Read exact accepted Android methods for the author 858 compatibility audit."""
import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'client-patch/lens0907-0908/vendor/abcasm'))
import asm
import bodies
from swfabc import SwfAbc

def sha(raw): return hashlib.sha256(raw).hexdigest()

def listing(body, abc):
    lines = [f'header: {body[1:5]}']
    for i, x in enumerate(asm.decode(body[5])):
        note = ''
        if x.name in ('getproperty', 'setproperty', 'findproperty', 'findpropstrict', 'callproperty', 'callpropvoid', 'coerce', 'getlex', 'constructprop'):
            note = abc.mn_name(x.args[0])
        elif x.name == 'pushint': note = str(abc.ints[x.args[0]])
        elif x.name == 'pushstring': note = abc.strings[x.args[0]].decode('utf-8')
        lines.append(f'{i:04d} {x.name} {x.args}' + (f' -> {x.target}' if x.target is not None else '') + ' ; ' + note)
    return '\n'.join(lines) + '\n'

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--work', type=Path, required=True)
    args = ap.parse_args(); work = args.work.resolve(); work.mkdir(parents=True, exist_ok=True)
    registry = json.loads((REPO / 'client-patch/android-accepted.json').read_text('utf-8-sig'))
    variant = registry['variants']['public']; apk = REPO / variant['apk']
    assert sha(apk.read_bytes()) == variant['apk_sha256']
    with zipfile.ZipFile(apk) as z: raw = z.read('assets/worldflipper_android_release.swf')
    assert sha(raw) == variant['swf_sha256']
    swf_path = work / 'accepted.swf'; swf_path.write_bytes(raw)
    swf = SwfAbc(swf_path); abc = swf.abc
    targets = ('CharacterShortVoiceLogic/get_skillVoicePaths', 'CharacterVoiceLogic/createVoicePathMap',
               'HudMemberStatus/update', 'BattleCharacterLogic/resolveFollowingPathCollection',
               'ActionEvaluator/evalCommand', 'ActiveSquadManager/getMultiballNumberWithDetail',
               'InactiveSquadManager/getMultiballNumberWithDetail', 'EctoplasmicSquadManager/getMultiballNumberWithDetail',
               'SquadImpl/matchMultiball', 'Environment$/createLocalEnvironmentDetail', 'DamageOriginKindTools$/toString')
    rows = []
    for name in targets:
        try: index = bodies.resolve(abc, name)
        except Exception as error:
            rows.append({'name': name, 'error': str(error)}); continue
        body = abc.bodies[index]; out = work / (name.replace('/', '-') + '.pcode')
        out.write_text(listing(body, abc), 'utf-8')
        rows.append({'name': name, 'body_index': index, 'method_index': body[0],
                     'code_sha256': sha(body[5]), 'instructions': len(asm.decode(body[5])), 'listing': str(out)})
    strings = [x.decode('utf-8', 'replace') for x in abc.strings]
    result = {'apk': str(apk), 'apk_sha256': variant['apk_sha256'], 'swf_sha256': sha(raw),
              'main_abc_method_count': len(abc.bodies), 'methods': rows,
              'lion_router_markers': [s for s in strings if 'lionReady' in s],
              'baseline_registry_status': registry['status'], 'device_tested': False}
    (work / 'inspection.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == '__main__': main()
