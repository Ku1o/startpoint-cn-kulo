"""Read and execute the accepted, unmodified native short-voice reader."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace as Obj

import inspect_client as client
import prepare as m

PREFIX = 'character/lion_swordman_reborn/voice/'
FORMAL = (0, 1, 4, 5, 6)


class Array(list):
    def push(self, value): self.append(value); return len(self)


def execute(code, abc, instance, args=()):
    instructions = client.asm.decode(code); registers = {0: instance, **{i: x for i, x in enumerate(args, 1)}}
    stack, pc = [], 0
    def name(i): return abc.mn_name(i).split('::')[-1]
    for _ in range(25000):
        ins = instructions[pc]; pc += 1; op, arg = ins.name, ins.args
        if op.startswith('getlocal_'): stack.append(registers[int(op[-1])])
        elif op.startswith('setlocal_'): registers[int(op[-1])] = stack.pop()
        elif op == 'getlocal': stack.append(registers[arg[0]])
        elif op == 'setlocal': registers[arg[0]] = stack.pop()
        elif op == 'pushscope': stack.pop()
        elif op == 'findproperty': stack.append(instance)
        elif op == 'getproperty': stack.append(getattr(stack.pop(), name(arg[0])))
        elif op == 'getlex':
            assert name(arg[0]) == 'Option'
            stack.append(Obj(Some=lambda path: Obj(index=0, params=[path]), **{'None': Obj(index=1, params=[])}))
        elif op in ('callproperty', 'callpropvoid'):
            values = [stack.pop() for _ in range(arg[1])][::-1]
            result = getattr(stack.pop(), name(arg[0]))(*values)
            if op == 'callproperty': stack.append(result)
        elif op == 'pushstring': stack.append(abc.strings[arg[0]].decode('utf-8'))
        elif op == 'pushint': stack.append(abc.ints[arg[0]])
        elif op == 'pushbyte': stack.append(arg[0])
        elif op == 'pushnull': stack.append(None)
        elif op in ('coerce', 'astype', 'op_09'): pass
        elif op == 'convert_i': stack.append(int(stack.pop()))
        elif op == 'convert_b': stack.append(bool(stack.pop()))
        elif op == 'newarray': assert arg == [0]; stack.append(Array())
        elif op == 'inclocal_i': registers[arg[0]] += 1
        elif op == 'add':
            b, a = stack.pop(), stack.pop(); stack.append(str(a) + str(b) if isinstance(a, str) or isinstance(b, str) else a + b)
        elif op == 'jump': pc = ins.target
        elif op == 'iflt':
            b, a = stack.pop(), stack.pop()
            if a < b: pc = ins.target
        elif op == 'iffalse':
            if not stack.pop(): pc = ins.target
        elif op == 'returnvalue':
            value = stack.pop(); assert not stack; return value
        else: raise AssertionError(op)
    raise AssertionError('native reader did not terminate')


def verify(work, effective):
    inspection = m.readj(work / 'client/inspection.json')
    swf = client.SwfAbc(work / 'client/accepted.swf'); abc = swf.abc
    assert client.sha(swf.path.read_bytes()) == inspection['swf_sha256']
    registry = m.readj(m.REPO / 'client-patch/android-accepted.json')['variants']['public']
    assert registry['swf_sha256'] == inspection['swf_sha256']
    names = ['CharacterShortVoiceLogic/' + x for x in ('generateVoicePaths', 'get_skillVoicePaths',
              'get_skillReadyVoicePath', 'get_switchedSkillReadyVoicePath')]
    methods = {name: abc.bodies[client.bodies.resolve(abc, name)][5] for name in names}
    def run(name, present):
        instance = Obj(character=Obj(resolveVoicePath=lambda path: PREFIX + path),
                       logicAssets=Obj(existsVoiceFileReader=lambda path: path in present))
        instance.generateVoicePaths = lambda prefix: execute(methods[names[0]], abc, instance, [prefix])
        return execute(methods[name], abc, instance)
    present = {PREFIX + f'battle/skill_{i}' for i in range(512)
               if effective('common', PREFIX + f'battle/skill_{i}.mp3') is not None}
    final = run(names[1], present)
    assert final == [PREFIX + f'battle/skill_{i}' for i in range(5)], final
    assert not present - set(final), 'unreachable numbered skill audio'
    mapping = m.readj(work / 'native-voice-mapping.json')
    for row in mapping['mapping']:
        assert m.sha(effective('common', row['logical'])) == row['sha256']
    # Negative case: a gap at 2 really stops the original reader before 3/4.
    assert run(names[1], present - {PREFIX + 'battle/skill_2'}) == final[:2]
    assert run(names[1], set()) == []
    assert len(run(names[1], {PREFIX + f'battle/skill_{i}' for i in range(513)})) == 512
    ready = {PREFIX + 'battle/' + x for x in ('skill_ready', 'matched_skill_ready',
                                             'skill_ready_alt_1', 'matched_skill_ready_alt_1')}
    assert all(effective('common', x + '.mp3') is not None for x in ready)
    for name, leaf in ((names[2], 'skill_ready'), (names[3], 'matched_skill_ready')):
        target = PREFIX + 'battle/' + leaf
        value = run(name, ready); assert value.index == 0 and value.params == [target]
        assert run(name, ready - {target}).index == 1, 'an alternate must not be described as natively selected'
    result = {'status': 'passed', 'prepared_sha256': m.sha((work / 'prepared.json').read_bytes()),
        'accepted_swf_sha256': inspection['swf_sha256'],
        'actual_native_reader_executed': True, 'formal_recordings': 5, 'native_suffixes': list(range(5)),
        'donor_formal_suffixes': list(FORMAL), 'trial_recordings_in_native_pool': 0,
        'gap_stops_scan_negative_case': True, 'native_scan_limit': 512,
        'native_ready_paths': [PREFIX + 'battle/' + x for x in ('skill_ready', 'matched_skill_ready')],
        'extra_ready_alternation_enabled': False, 'extra_ready_recordings_retained': True,
        'apk_required': False, 'apk_registry_unchanged': True, 'device_tested': False,
        'methods': {name: client.sha(raw) for name, raw in methods.items()}}
    m.writej(work / 'native-voice-verification.json', result)
    return result
