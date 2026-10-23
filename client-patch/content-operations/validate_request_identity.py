"""Independent readback validation of an isolated request-identity candidate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
import build_bridge as bridge


def validate(work, native_entries=False):
    old_tags = bridge.sc.parts(work / 'R6-input.swf')[2]
    new_tags = bridge.sc.parts(work / 'content-operations-android.swf')[2]
    assert len(old_tags) == len(new_tags)
    changed_tags = [i for i, (old, new) in enumerate(zip(old_tags, new_tags)) if old[1] != new[1]]
    assert len(changed_tags) == 2

    def find(tags, name):
        return next(t[3] for t in tags if t[3] and any(t[3].mn_name(i[0]) == name for i in t[3].instances))

    old = find(old_tags, 'pinball.context.remote::RequestQueue')
    new = find(new_tags, 'pinball.context.remote::RequestQueue')
    assert len(old.bodies) == len(new.bodies)
    changed_bodies = [i for i, (o, n) in enumerate(zip(old.bodies, new.bodies)) if bridge.p.freeze(o) != bridge.p.freeze(n)]
    native_labels = ['pinball.context.remote::RequestQueue/startRequest|1']
    if native_entries:
        native_labels += ['pinball.common.data.event::EventListLogic/<ctor>',
                          'pinball.common.data.bossBattle::BossBattleHeaderBannerResolver$/resolve|1',
                          'pinball.scene.boxGacha::BoxGachaScene/buttonClicked|1']
    old_view, new_view = bridge.view(old), bridge.view(new)
    expected = sorted(old_view.by_label[label][0] for label in native_labels)
    assert changed_bodies == expected
    native_proofs = {label: bridge.p.insertion_proof(old_view.normalized(old_view.by_label[label][0]),
                     new_view.normalized(new_view.by_label[label][0])) for label in native_labels}
    for field in ['instances', 'classes', 'methods', 'scripts', 'metadata']:
        assert bridge.p.freeze(getattr(old, field)) == bridge.p.freeze(getattr(new, field)), field
    for field in ['strings', 'ints', 'uints', 'doubles', 'namespaces', 'ns_sets', 'multinames']:
        assert getattr(new, field)[:len(getattr(old, field))] == getattr(old, field), field
    old_helper = find(old_tags, 'cn.content::ContentOperationsState')
    new_helper = find(new_tags, 'cn.content::ContentOperationsState')
    assert new_helper.serialize() == (work / 'production-helper.abc').read_bytes()
    before, after = bridge.view(old_helper), bridge.view(new_helper)
    label = 'cn.content::ContentOperationsState$/<cinit>'
    old_init, = before.by_label[label]
    new_init, = after.by_label[label]
    cinit_proof = bridge.p.insertion_proof(before.normalized(old_init), after.normalized(new_init))
    unchanged_helper = 0
    for name, indices in before.by_label.items():
        if name == label:
            continue
        oi, = indices
        ni, = after.by_label[name]
        assert before.normalized(oi) == after.normalized(ni), name
        unchanged_helper += 1

    def fields(value):
        result = {}
        for trait in value.classes[0][1]:
            if trait.kind in (0, 6):
                result[value.mn_name(trait.name)] = {'kind': trait.kind, 'slot': trait.data[1], 'fieldOrder': len(result) + 1, 'type': value.mn_name(trait.data[2])}
        return result

    old_fields, new_fields = fields(old_helper), fields(new_helper)
    assert all(new_fields.get(name) == value for name, value in old_fields.items())
    additions = {name: value for name, value in new_fields.items() if name not in old_fields}
    assert set(additions) == {'cn.content:ContentOperationsState::requestIdentities'}
    return {'parsedOutputChangedTagIndices': changed_tags, 'parsedOutputTotalTags': len(old_tags),
            'parsedOutputChangedNativeBodies': changed_bodies, 'changedNativeLabels': native_labels,
            'nativeInsertionProofs': native_proofs, 'unchangedNativeBodies': len(old.bodies) - len(changed_bodies),
            'nativeExistingAbiAndConstantPoolPrefixUnchanged': True, 'helperCinitInsertionProof': cinit_proof,
            'unchangedExistingHelperMethods': unchanged_helper, 'existingHelperStaticFieldSlots': old_fields,
            'newHelperStaticFields': additions, 'productionHelperBytesMatchSwf': True,
            'sourceSwfSha256': hashlib.sha256((work / 'R6-input.swf').read_bytes()).hexdigest(),
            'candidateSwfSha256': hashlib.sha256((work / 'content-operations-android.swf').read_bytes()).hexdigest()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--production-work', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    parser.add_argument('--native-entries', action='store_true')
    args = parser.parse_args()
    result = validate(args.production_work, args.native_entries)
    args.report.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({name: value for name, value in result.items() if name not in ['existingHelperStaticFieldSlots', 'newHelperStaticFields']}))
