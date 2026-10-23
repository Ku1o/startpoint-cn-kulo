"""R6 -> isolated R7: freeze existing request identity fields; never package an APK."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import zlib

sys.dont_write_bytecode = True
import build_bridge as bridge

R6_SWF_SHA256 = 'f1b57e0afeded1ceea433790a04dc8bb35b48f7c26d04fdd602e949970f588af'
R6_HELPER_SHA256 = 'acb85e681a5702ee7448666a91d421928fde8bf548a2aca129aa56a4d023c048'
QUEUE = 'pinball.context.remote::RequestQueue'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def label_helper_targets(helper):
    before = copy.deepcopy(helper)
    proofs = []
    for index, body in enumerate(helper.bodies):
        instructions = bridge.p.asm.decode(body[5])
        targets = set()
        for ins in instructions:
            if ins.target is not None:
                targets.add(ins.target)
            if ins.cases is not None:
                targets.update([ins.default] + ins.cases)
        missing = [i for i in targets if i == len(instructions) or instructions[i].op != 0x09]
        for at in sorted(missing, reverse=True):
            body[5], body[6], _ = bridge.p.asm.splice(body, at, [bridge.p.asm.Instruction(0x09)], bridge.p.asm.ENTER)
        bridge.p.check_body(body, helper)
        proofs.append(bridge.p.insertion_proof(bridge.view(before).normalized(index), bridge.view(helper).normalized(index)))
    return proofs


def patch(work, source, sdk, java, native_entries=False):
    raw = source.read_bytes()
    if sha(raw) != R6_SWF_SHA256:
        raise ValueError('request identity patch requires the exact selected R6 SWF')
    work.mkdir(parents=True, exist_ok=True)
    (work / 'R6-input.swf').write_bytes(raw)
    version, header, tags = bridge.sc.parts(source)
    helper_tag, = [tag for tag in tags if tag[3] and any(tag[3].mn_name(i[0]) == 'cn.content::ContentOperationsState' for i in tag[3].instances)]
    original_helper = helper_tag[3]
    if sha(original_helper.serialize()) != R6_HELPER_SHA256:
        raise ValueError('selected R6 helper identity differs')
    helper = bridge.compile_helper(work, sdk, java)
    helper_labels = label_helper_targets(helper)
    before_helper, after_helper = bridge.view(original_helper), bridge.view(helper)
    preserved = []
    for label, bodies in before_helper.by_label.items():
        if label.endswith('/<cinit>'):
            continue
        if len(bodies) != 1 or len(after_helper.by_label.get(label, [])) != 1:
            raise ValueError(('existing helper method identity changed', label))
        old_index, = bodies
        new_index, = after_helper.by_label[label]
        if before_helper.normalized(old_index) != after_helper.normalized(new_index):
            raise ValueError(('unrelated existing helper method changed', label))
        preserved.append(label)
    cinit_label = 'cn.content::ContentOperationsState$/<cinit>'
    old_cinit, = before_helper.by_label[cinit_label]
    new_cinit, = after_helper.by_label[cinit_label]
    cinit_proof = bridge.p.insertion_proof(before_helper.normalized(old_cinit), after_helper.normalized(new_cinit))
    def field_layout(value):
        fields = {}
        for trait in value.classes[0][1]:
            if trait.kind in (0, 6):
                data = trait.data
                fields[value.mn_name(trait.name)] = {'kind': trait.kind, 'slot': data[1], 'fieldOrder': len(fields) + 1, 'type': value.mn_name(data[2])}
        return fields
    old_fields, new_fields = field_layout(original_helper), field_layout(helper)
    if any(new_fields.get(name) != definition for name, definition in old_fields.items()):
        raise ValueError('existing helper static field/slot layout changed')
    if set(new_fields) - set(old_fields) != {'cn.content:ContentOperationsState::requestIdentities'}:
        raise ValueError(('unexpected new helper static fields', set(new_fields) - set(old_fields)))
    (work / 'production-helper.abc').write_bytes(helper.serialize())
    (work / 'helper-label-proof.json').write_text(json.dumps(helper_labels, indent=2), encoding='utf-8')
    main_tag, = [tag for tag in tags if tag[3] and any(tag[3].mn_name(i[0]) == QUEUE for i in tag[3].instances)]
    abc = main_tag[3]
    old = copy.deepcopy(abc)
    view = bridge.view(abc)
    label, = [name for name in view.by_label if name.startswith(QUEUE + '/') and '/startRequest|' in name]
    body_index, = view.by_label[label]
    body = abc.bodies[body_index]
    instructions = bridge.p.asm.decode(body[5])
    pool = bridge.PoolEditor(abc)
    def qname(namespace, name):
        for index, value in enumerate(abc.multinames):
            if value[0] == 7 and abc.s(value[2]) == name and abc.namespaces[value[1]][0] == 22 and abc.ns_name(value[1]) == namespace and abc.namespaces[value[1]][1] != 0:
                return index
        if namespace:
            string_index = pool.string(namespace)
        else:
            string_index = next((index for index, value in enumerate(abc.strings) if index > 0 and value == b''), None)
            if string_index is None:
                abc.strings.append(b'')
                string_index = len(abc.strings) - 1
        abc.namespaces.append((22, string_index))
        abc.multinames.append((7, len(abc.namespaces) - 1, pool.string(name)))
        return len(abc.multinames) - 1
    state = qname('cn.content', 'ContentOperationsState')
    getters = {name: qname('', name) for name in ['frozenLoginToken', 'frozenApiCount']}
    sites = []
    for at, ins in enumerate(instructions):
        if ins.op != 0x66:
            continue
        name = abc.mn_name(ins.args[0]).rsplit('::', 1)[-1]
        if name not in ['accessCount', 'loginToken']:
            continue
        producer = instructions[at - 1]
        if name == 'accessCount' and (producer.op != 0x5e or producer.args != ins.args):
            raise ValueError('unexpected R6 accessCount expression')
        if name == 'loginToken' and (producer.op != 0x60 or abc.mn_name(producer.args[0]) != 'pinball.config.core::DevConfig'):
            raise ValueError('unexpected R6 loginToken expression')
        sites.append((at - 1, at + 1, 'frozenApiCount' if name == 'accessCount' else 'frozenLoginToken'))
    if [name for _, _, name in sites] != ['frozenApiCount', 'frozenLoginToken', 'frozenLoginToken']:
        raise ValueError(('R6 request identity expressions changed', sites))
    additions = []
    for begin, end, name in sites:
        additions.extend([(begin, bridge.p.asm.assemble([('getlex', state), ('getlocal_1',)])),
                          (end, bridge.p.asm.assemble([('callproperty', getters[name], 2)]))])
    origins = list(range(len(instructions)))
    for at, block in sorted(additions, key=lambda item: item[0], reverse=True):
        body[5], body[6], _ = bridge.p.asm.splice(body, at, copy.deepcopy(block), bridge.p.asm.ENTER)
        origins[at:at] = [None] * len(block)
    # AIR requires physical labels at patched control-flow targets.
    instructions = bridge.p.asm.decode(body[5])
    targets = set()
    for ins in instructions:
        if ins.target is not None:
            targets.add(ins.target)
        if ins.cases is not None:
            targets.update([ins.default] + ins.cases)
    missing = [i for i in targets if i == len(instructions) or instructions[i].op != 0x09]
    for at in sorted(missing, reverse=True):
        body[5], body[6], _ = bridge.p.asm.splice(body, at, [bridge.p.asm.Instruction(0x09)], bridge.p.asm.ENTER)
        origins[at:at] = [None]
    body[1] += 4
    bridge.p.check_body(body, abc)
    spans = []
    at = source_at = 0
    while at < len(origins):
        if origins[at] is None:
            start = at
            while at < len(origins) and origins[at] is None:
                at += 1
            spans.append({'at': source_at, 'instructions': at - start})
        else:
            if origins[at] != source_at:
                raise ValueError('original request instruction removed or reordered')
            source_at += 1
            at += 1
    insertion_proof = bridge.p.insertion_proof(bridge.view(old).normalized(body_index), bridge.view(abc).normalized(body_index), spans)
    allowed_bodies = {body_index}
    entry_grafts = []
    if native_entries:
        def entry_graft(label, at, block):
            index, = bridge.view(abc).by_label[label]
            target = abc.bodies[index]
            original_count = len(bridge.p.asm.decode(target[5]))
            origins = list(range(original_count))
            target[5], target[6], _ = bridge.p.asm.splice(target, at, block, bridge.p.asm.ENTER)
            origins[at:at] = [None] * len(block)
            decoded = bridge.p.asm.decode(target[5])
            targets = set()
            for instruction in decoded:
                if instruction.target is not None:
                    targets.add(instruction.target)
                if instruction.cases is not None:
                    targets.update([instruction.default] + instruction.cases)
            for position in sorted([i for i in targets if i == len(decoded) or decoded[i].op != 0x09], reverse=True):
                target[5], target[6], _ = bridge.p.asm.splice(target, position, [bridge.p.asm.Instruction(0x09)], bridge.p.asm.ENTER)
                origins[position:position] = [None]
            target[1] += 4
            bridge.p.check_body(target, abc)
            additions, position, source_position = [], 0, 0
            while position < len(origins):
                if origins[position] is None:
                    start = position
                    while position < len(origins) and origins[position] is None:
                        position += 1
                    additions.append({'at': source_position, 'instructions': position - start})
                else:
                    assert origins[position] == source_position
                    position += 1
                    source_position += 1
            proof = bridge.p.insertion_proof(bridge.view(old).normalized(index), bridge.view(abc).normalized(index), additions)
            allowed_bodies.add(index)
            entry_grafts.append({'label': label, 'sourceCodeSha256': sha(old.bodies[index][5]),
                                 'candidateCodeSha256': sha(target[5]), 'insertionProof': proof})

        label = 'pinball.common.data.event::EventListLogic/<ctor>'
        index, = bridge.view(abc).by_label[label]
        decoded = bridge.p.asm.decode(abc.bodies[index][5])
        assert decoded[-1].op == 0x47
        entry_graft(label, len(decoded) - 1, bridge.p.asm.assemble([
            ('getlex', state), ('getlocal_0',), ('callpropvoid', qname('', 'restoreRushEventList'), 1)]))
        label = 'pinball.common.data.bossBattle::BossBattleHeaderBannerResolver$/resolve|1'
        index, = bridge.view(abc).by_label[label]
        decoded = bridge.p.asm.decode(abc.bodies[index][5])
        site, = [i for i, instruction in enumerate(decoded) if instruction.op == 0x46 and instruction.args[1] == 0
                 and abc.mn_name(instruction.args[0]) == 'getAllEventIds']
        entry_graft(label, site + 1, bridge.p.asm.assemble([
            ('getlex', state), ('swap',), ('callproperty', qname('', 'bossBattleHeaderIds'), 1)]))
        label = 'pinball.scene.boxGacha::BoxGachaScene/buttonClicked|1'
        index, = bridge.view(abc).by_label[label]
        decoded = bridge.p.asm.decode(abc.bodies[index][5])
        site, = [i for i, instruction in enumerate(decoded) if instruction.op in (0x5d, 0x5e)
                 and abc.mn_name(instruction.args[0]) == 'changeSceneWithPushBackScene']
        # The original mission-button branch is reached only after its native
        # carousel/animation guards. All other branches remain original code.
        entry_graft(label, site, bridge.p.asm.assemble([
            ('getlex', state), ('getlocal_0',), ('callproperty', qname('', 'routeAssociatedBoxQuest'), 1),
            ('iffalse', 'ORIGINAL_MISSION'), ('returnvoid',), ('label', 'ORIGINAL_MISSION')]))
    for index, original in enumerate(old.bodies):
        if index not in allowed_bodies and bridge.p.freeze(original) != bridge.p.freeze(abc.bodies[index]):
            raise ValueError(('unrelated native method changed', index))
    for field in ['instances', 'classes', 'methods', 'scripts', 'metadata']:
        if bridge.p.freeze(getattr(old, field)) != bridge.p.freeze(getattr(abc, field)):
            raise ValueError(('existing native ABI changed', field))
    for tag, replacement in [(main_tag, bridge.sc.serialize(abc, main_tag[4])), (helper_tag, helper.serialize())]:
        tag[1] = struct.pack('<HI', (82 << 6) | 63, len(tag[2]) + len(replacement)) + tag[2] + replacement
    payload = header + b''.join(tag[1] for tag in tags)
    result = b'CWS' + bytes([version]) + struct.pack('<I', len(payload) + 8) + zlib.compress(payload)
    output = work / 'content-operations-android.swf'
    output.write_bytes(result)
    report = {'inputSha256': sha(raw), 'outputSha256': sha(result), 'inputHelperAbcSha256': R6_HELPER_SHA256,
              'outputHelperAbcSha256': sha(helper.serialize()), 'helperBodies': len(helper.bodies),
              'helperSourceSha256': sha((bridge.HERE / 'src/cn/content/ContentOperationsState.as').read_bytes()),
              'requestMethod': QUEUE + '/startRequest|1', 'originalCodeSha256': sha(old.bodies[body_index][5]), 'candidateCodeSha256': sha(body[5]),
              'expressionSites': sites, 'insertionSpans': spans, 'originalInstructionCfgInsertionProof': insertion_proof,
              'unchangedExistingHelperMethods': preserved, 'helperCinitInsertionProof': cinit_proof, 'existingHelperStaticFieldSlots': old_fields,
              'newHelperStaticFields': {name: value for name, value in new_fields.items() if name not in old_fields},
              'nativeEntryGrafts': entry_grafts, 'changedNativeBodyCount': len(allowed_bodies),
              'unrelatedNativeBodiesUnchanged': True, 'existingNativeAbiUnchanged': True,
              'dateMethodsChanged': False, 'packaged': False, 'deviceTested': False, 'acceptedRegistryChanged': False}
    (work / 'request-identity-bridge-report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    parser.add_argument('--source-swf', type=Path, required=True)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--native-entries', action='store_true', help='Also restore controlled Advent/Rush entries and the nine associated Box mission-button routes')
    args = parser.parse_args()
    report = patch(args.work, args.source_swf, args.sdk, args.java, args.native_entries)
    print(json.dumps({key: report[key] for key in ['inputSha256', 'outputSha256', 'outputHelperAbcSha256', 'helperBodies', 'requestMethod', 'unrelatedNativeBodiesUnchanged', 'existingNativeAbiUnchanged']}, indent=2))
