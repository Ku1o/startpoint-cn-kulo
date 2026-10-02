"""Replay generated master-field parsers from the delivered APK, offline only.

Enum constructors are inert recording fixtures. Branches and recursive field
parsers execute the original bytecode. Unknown instructions/helpers fail closed.
"""
from pathlib import Path
import hashlib, json, math, sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'client-patch/author-content-1043/rules'))
from core import SwfAbc, bodies, asm


class ClientError(Exception):
    def __init__(self, code, message):
        super().__init__(f'C{code}: {message}')
        self.code = code


class EnumValue:
    def __init__(self, name, args=()): self.name, self.args = name, args
    def __call__(self, *args): return EnumValue(self.name, args)
    def __repr__(self): return f'{self.name}{self.args}'


class Namespace:
    def __init__(self, replay, name): self.replay, self.name = replay, name
    def __call__(self, *args):
        assert self.name.startswith('pinball.common.data.ability'), self.name
        return EnumValue(self.name, args)
    def field(self, name):
        if self.name == 'pinball.common.math._Decimal::Decimal_Impl_' and name == '_new':
            return lambda value: self.replay.run('Decimal_Impl_$/_new', value)
        if self.name in ('pinball.master.generated::AbilityValues', 'pinball.master.generated::LeaderAbilityValues'):
            assert name.startswith('parseAt'), name
            return lambda row: self.replay.run(self.name.split('::')[-1] + '$/' + name, row)
        if self.name.startswith('pinball.common.data.ability') or self.name == 'haxe.ds::Option':
            return EnumValue(self.name + '.' + name)
        raise AssertionError(('Unknown namespace', self.name, name))


class Replay:
    def __init__(self, swf):
        self.swf_sha = hashlib.sha256(swf.read_bytes()).hexdigest()
        assert self.swf_sha == '2e806d30ad3e2f9b71f63085e03ca3d41886bb81a7b8e01a19133eaea3828ed2'
        self.abc = SwfAbc(swf).abc
        self.cache, self.executed, self.boot = {}, {}, {}

    def lexical(self, name):
        if name == 'flash::Boot': return self.boot
        if name == 'Std': return {'parseInt': lambda s: int(s), 'parseFloat': lambda s: float(s)}
        if name == 'Math': return {'round': lambda value: math.floor(value + .5)}
        if name == 'Error': return {'Error': Exception}
        if name == 'pinball.error::ClientError': return {name: ClientError}
        return Namespace(self, name)

    def get(self, obj, key):
        if isinstance(obj, Namespace): return obj.field(key)
        if key == 'length': return len(obj)
        if isinstance(obj, str) and key == 'http://adobe.com/AS3/2006/builtin::split':
            return lambda sep: obj.split(sep)
        if isinstance(obj, list) and key == 'http://adobe.com/AS3/2006/builtin::push':
            return lambda value: obj.append(value)
        if isinstance(obj, dict): return obj[key]
        if isinstance(obj, list): return obj[key]
        raise AssertionError(('Unknown property', obj, key))

    def run(self, name, row):
        if name not in self.cache:
            index = bodies.resolve(self.abc, name)
            code = self.abc.bodies[index][5]
            self.cache[name] = asm.decode(code)
            self.executed[name] = {'body': index, 'sha256': hashlib.sha256(code).hexdigest()}
        ins, stack, regs, pc, steps = self.cache[name], [], {0: None, 1: row}, 0, 0
        while pc < len(ins):
            x = ins[pc]; pc += 1; steps += 1
            assert steps < 30000, name
            op, a = x.name, x.args
            sym = self.abc.mn_name(a[0]) if op in ('getproperty', 'setproperty', 'initproperty', 'getlex', 'findpropstrict', 'callproperty', 'callpropvoid', 'constructprop', 'astype') else None
            if op in ('nop', 'avm_label', 'coerce', 'coerce_a'): pass
            elif op.startswith('getlocal_'): stack.append(regs[int(op[-1])])
            elif op == 'getlocal': stack.append(regs[a[0]])
            elif op.startswith('setlocal_'): regs[int(op[-1])] = stack.pop()
            elif op == 'setlocal': regs[a[0]] = stack.pop()
            elif op == 'inclocal_i': regs[a[0]] += 1
            elif op in ('pushbyte', 'pushshort'): stack.append(a[0])
            elif op == 'pushint': stack.append(self.abc.ints[a[0]])
            elif op == 'pushstring': stack.append(self.abc.strings[a[0]].decode())
            elif op in ('pushtrue', 'pushfalse'): stack.append(op == 'pushtrue')
            elif op == 'pushnull': stack.append(None)
            elif op == 'dup': stack.append(stack[-1])
            elif op == 'pop': stack.pop()
            elif op == 'convert_i': stack.append(int(stack.pop() or 0))
            elif op == 'convert_d': stack.append(float(stack.pop() or 0))
            elif op == 'convert_b': stack.append(bool(stack.pop()))
            elif op == 'astype':
                value = stack.pop()
                assert value is None, ('Non-null cast needs a type fixture', sym)
                stack.append(None)
            elif op == 'getproperty':
                key = stack.pop() if sym == '<mn kind 0x1b>' else sym
                stack.append(self.get(stack.pop(), key))
            elif op in ('setproperty', 'initproperty'):
                value, obj = stack.pop(), stack.pop(); obj[sym] = value
            elif op in ('getlex', 'findpropstrict'): stack.append(self.lexical(sym))
            elif op in ('callproperty', 'callpropvoid', 'constructprop'):
                args = [stack.pop() for _ in range(a[1])][::-1]
                result = self.get(stack.pop(), sym)(*args)
                if op != 'callpropvoid': stack.append(result)
            elif op == 'construct':
                args = [stack.pop() for _ in range(a[0])][::-1]
                stack.append(stack.pop()(*args))
            elif op == 'newarray': stack.append([stack.pop() for _ in range(a[0])][::-1])
            elif op == 'newobject':
                obj = {}
                for _ in range(a[0]):
                    value, key = stack.pop(), stack.pop(); obj[key] = value
                stack.append(obj)
            elif op in ('ifne', 'ifeq', 'iflt', 'ifge'):
                right, left = stack.pop(), stack.pop()
                matched = {'ifne': lambda: left != right, 'ifeq': lambda: left == right,
                           'iflt': lambda: left < right, 'ifge': lambda: left >= right}[op]()
                if matched: pc = x.target
            elif op == 'jump': pc = x.target
            elif op == 'throw': raise stack.pop()
            elif op == 'returnvalue': return stack.pop()
            elif op == 'returnvoid': return None
            else: raise AssertionError(('Unsupported instruction', name, op))
        raise AssertionError(('Fell through', name))


def check_row(replay, table, row):
    offset = 2 if table == 'ability' else 0
    kind = 'AbilityValues' if offset else 'LeaderAbilityValues'
    trigger = row[3 + offset]
    roots = {'0': (4, 11, 18, 25, 37, 44, 45), '1': (4, 11, 18, 83, 95, 106, 107), '2': (121,)}
    assert trigger in roots, trigger
    return {str(col + offset): repr(replay.run(f'{kind}$/parseAt{col + offset}', row))
            for col in roots[trigger]}


if __name__ == '__main__':
    import argparse, zipfile
    import build_redesign_118 as base
    import fix_leader_target_119 as fix
    parser = argparse.ArgumentParser()
    parser.add_argument('--swf', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--repaired-archive', type=Path, required=True)
    parser.add_argument('--preimage', type=Path,
                        default=Path(__file__).parent/'fixtures/leader-empty-target.orderedmap')
    args = parser.parse_args()
    r = Replay(args.swf)
    preimage = args.preimage.read_bytes()
    receipt = json.loads(args.preimage.with_suffix('.orderedmap.json').read_text('utf-8'))
    assert base.sha(preimage) == receipt['sha256']
    assert receipt['source_archive_sha256'] == fix.PREVIOUS_ARCHIVE_SHA
    data = {}
    with zipfile.ZipFile(args.repaired_archive) as z:
        for table, logical, keys in [('ability', base.ABILITY, [str(1599910+n) for n in range(1,7)]+['1499872']), ('leader_ability', base.LEADER, ['159991'])]:
            source = preimage if table == 'leader_ability' else z.read(base.member(logical))
            _, raw_rows = base.raw_map(source, logical)
            data[table] = {key: base.core.read_csv_lines(base.ql.parse_node(raw_rows[key])) for key in keys}
    bad = data['leader_ability']['159991'][15]
    try: r.run('LeaderAbilityValues$/parseAt45', bad)
    except ClientError as error:
        assert error.code == 7050
        before = str(error)
    else: raise AssertionError('Published empty target did not reproduce C7050')
    with zipfile.ZipFile(args.repaired_archive) as z:
        _, raw_rows = base.raw_map(z.read(base.member(base.LEADER)), base.LEADER)
        corrected = base.core.read_csv_lines(base.ql.parse_node(raw_rows['159991']))
    data['leader_ability']['159991'] = corrected
    after = r.run('LeaderAbilityValues$/parseAt45', corrected[15])
    assert after.name.endswith('.SkillGauge') and '.Myself' in repr(after.args), after
    result = {'before': before, 'after': repr(after), 'rows': []}
    for table, keys in data.items():
        for key, rows in keys.items():
            for index, row in enumerate(rows):
                try: parsed = check_row(r, table, row)
                except Exception as e:
                    print(json.dumps({'failed': [table, key, index], 'error': str(e)}, ensure_ascii=False))
                    raise
                result['rows'].append({'table': table, 'key': key, 'row': index, 'parsed': parsed})
    result.update(swf_sha256=r.swf_sha, methods=r.executed, device_tested=False,
                  limitation='Original generated parser bytecode with inert enum factories; not a full client or battle execution.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'before': before, 'after': repr(after), 'rows_passed': len(result['rows']), 'methods': len(r.executed)}, ensure_ascii=False))
