"""Reserve a paired release and prepare the current full ABC for AOT compilation."""
from release_common import *
import copy, secrets, shutil, struct, zipfile

def main():
    assert not WORK.exists(), 'Use a fresh release work directory.'
    a, i = registries()
    assert sha((ROOT/a['apk']).read_bytes()) == a['apk_sha256']
    assert sha((ROOT/i['ipa']).read_bytes()) == i['ipa_sha256']
    policy = read(PRIVATE/'config/client-admission.json')
    keys = read(PRIVATE/'config/client-admission.keys.json')
    assert all(keys.get(row['id']) for row in policy['builds'])
    if PAIR.exists():
        # A rebuild of this batch reuses its already reserved per-platform pair.
        state=read(PAIR/'release-state.json');assert state['ids']==IDS
        existing=read(PAIR/'config/client-admission.keys.json')
        assert all(len(existing[build_id])==64 for build_id in IDS.values())
        assert existing[a['build_id']]==keys[a['build_id']] and existing[i['build_id']]==keys[i['build_id']]
        del existing
    else:
        PAIR.mkdir(parents=True)
        (PAIR/'config').mkdir()
        (PAIR/'before').mkdir()
        for filename in ('client-admission.json', 'client-admission.keys.json'):
            shutil.copyfile(PRIVATE/'config'/filename, PAIR/'before'/filename)
        shutil.copyfile(PRIVATE/'registry.json', PAIR/'before/registry.json')
        for platform, build_id in IDS.items():
            assert build_id not in keys and all(row['id'] != build_id for row in policy['builds'])
            keys[build_id] = secrets.token_hex(32)
            policy['builds'].append(dict(id=build_id, name='StarPoint CN 深渊 EX '+platform,
                                         platform=platform, enabled=True, allowUntil=None))
        dump(PAIR/'config/client-admission.keys.json', keys)
        dump(PAIR/'config/client-admission.json', policy)
        dump(PAIR/'release-state.json', dict(status='reserved_building', ids=IDS,
             old_ids={'android':a['build_id'], 'ios':i['build_id']}, grace_seconds=86400,
             grace_starts='explicit_server_activation', cloud_deployed=False))
    del keys
    WORK.mkdir(parents=True)
    OUT.mkdir(parents=True, exist_ok=True)
    proof = read(PREP/'preparation.json')
    source = (PREP/'abyss-ex-ios-full.abc').read_bytes()
    assert sha(source) == proof['ios']['full_abc_sha256']
    full, changed = replace_abc(source, 'ios')
    assert len(changed) >= 2
    from compiler_context import add_context
    full, lifecycles = add_context(full, proof['ios']['methods'])
    (WORK/'abyss-ex-full.abc').write_bytes(full)
    with zipfile.ZipFile(ROOT/i['ipa']) as z:
        native = z.read(i['native_member']); swf = z.read(i['swf_member'])
    assert sha(native) == i['native_sha256'] and sha(swf) == i['swf_sha256']
    (WORK/'baseline-native').write_bytes(native)
    (WORK/'baseline.swf').write_bytes(swf)
    # build_native imports a module named prepare; provide only its helpers.
    sys.modules['prepare'] = p
    import build_native as link
    address, size = struct.unpack_from('<QQ', native, INFO_OFFSET+24)
    offset = link.file_offset(native, address, size)
    reg = copy.deepcopy(i); reg['ipa'] = str(ROOT/i['ipa'])
    methods = [dict(row, strategy='replace') for row in proof['ios']['methods']]
    assert {row['method_id'] for row in methods} == {101077,101194,26363}
    dump(WORK/'port.json', dict(source_ipa=reg, old_methods=OLD_COUNT, total_methods=OLD_COUNT,
         methods=methods, compiler_only_lifecycles=lifecycles, full_abc_file='abyss-ex-full.abc', full_abc_sha256=sha(full),
         full_abc_sha1=hashlib.sha1(full).hexdigest(), baseline_runtime_abc_sha256=sha(native[offset:offset+size]),
         admission_string_indices=changed, build_id=IDS['ios'], equipment=proof['ios']['equipment_helper']))
    print('Reserved two independent admission pairs; prepared 3 iOS methods and equipment helper.')

if __name__ == '__main__': main()
