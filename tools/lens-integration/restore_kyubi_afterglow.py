"""Restore Kyubi's independent leader stack in 1.4.105 part 4.

Only writes a sparse work directory, this subpackage and its audit. The shared
manifest and loose source resource are integrated by the version coordinator.
"""
from __future__ import annotations

import argparse
import base64
import copy
import io
import json
from pathlib import Path
import sys
import zipfile

sys.dont_write_bytecode = True
import prepare_content as p
import wf_describe

REPO = p.REPO
LEADER = 'master/ability/leader_ability.orderedmap'
ABILITY = 'master/ability/ability.orderedmap'
TEXT = 'master/string/custom_ability_string.orderedmap'
CHARACTER = 'master/character/character.orderedmap'
KEY = '139995'
STATE = '1399952'
ARCHIVE = 'pinball-1.4.104-1.4.105-4-kyubi-afterglow.zip'
AUDIT = REPO/'assets/asset-patch/audit/kyubi-afterglow-1.4.105'
FIXTURE = Path(__file__).parent/'fixtures/kyubi-afterglow-before.json'


def member(logical):
    return p.member(('common', p.hrel(logical)))


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, ('existing output differs', str(path))
    else:
        with path.open('xb') as stream:
            stream.write(raw)


def jsonbytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf-8')


def fixture():
    data = p.readj(FIXTURE)
    decoded = {}
    for key, row in data['records'].items():
        raw = base64.b64decode(row['zlib_base64'], validate=True)
        assert p.sha(raw) == row['sha256'], ('fixture drift', key)
        decoded[key] = raw
    return data, decoded


def stack_rows(rows, kind):
    offset = 2 if kind == 'ability' else 0
    return [row for row in rows if
            row[3+offset] == '0' and row[25+offset] == '8'
            and row[45+offset] == '461' and row[66+offset] == STATE]


def validate_stacks(leader_rows, ability_rows):
    _, fixed = fixture()
    expected = p.csvrows(fixed['restored_leader_row'])[0]
    leaders = stack_rows(leader_rows, 'leader_ability')
    abilities = stack_rows(ability_rows, 'ability')
    assert leaders == [expected], 'leader must have exactly one Fever +1 source'
    assert len(abilities) == 1 and abilities[0][5:] == expected[3:], 'ability +1 source drift'
    # Same effect and state under two different ability owners is intentional.
    assert expected[4:10] == ['2', '', '', '600000', '600000', 'Yellow']
    assert expected[46] == '0' and expected[49:51] == ['100000', '100000']
    assert expected[57:59] == ['100000', '100000'] and expected[72] == '1'
    assert leader_rows[2][108:110] == ['0', ''], 'preserve self-only Fever gain'
    assert leader_rows[9][49:51] == ['-1000000', '-1000000'], 'preserve Lens0910 delta'


def restore(raw, ability_raw):
    _, fixed = fixture()
    table = p.rawmap(raw)
    old = p.csvrows(fixed['leader_before'])
    added = p.csvrows(fixed['restored_leader_row'])[0]
    rows = p.csvrows(table[KEY])
    abilities = p.csvrows(p.rawmap(ability_raw)['1399951'])
    if rows == old + [added]:
        validate_stacks(rows, abilities)
        return raw  # Idempotent even when the outer map uses another encoding.
    assert rows == old, 'unknown Kyubi preimage; do not overwrite new balance work'
    assert not stack_rows(rows, 'leader_ability')
    updated = copy.deepcopy(table)
    updated[KEY] = p.packcsv(rows + [added])
    result = p.packmap(updated)
    checked = p.rawmap(result)
    assert list(checked) == list(table)
    assert [k for k in table if checked[k] != table[k]] == [KEY]
    assert p.csvrows(checked[KEY])[:-1] == rows
    validate_stacks(p.csvrows(checked[KEY]), abilities)
    return result


def read_active(logicals):
    """Read only requested members from verified, enabled source archives."""
    path = REPO/'assets/asset-patch/manifest.json'
    manifest_raw = path.read_bytes()
    manifest = json.loads(manifest_raw)
    enabled = sorted((x for x in manifest['patches'] if x.get('enabled')),
                     key=lambda x: tuple(map(int, x['version'].split('.'))))
    archives, tail = [], '1.4.54'
    for entry in enabled:
        assert entry['depends_on'] == tail, 'non-contiguous active chain'
        tail = entry['version']
        archives.extend((entry, name) for name in entry.get('chain') or [entry['archive']])
    assert tail == manifest['cdn_version'] == '1.4.105'
    wanted = {member(logical): logical for logical in logicals}
    found, receipts = {}, {}
    for entry, name in reversed(archives):
        archive = REPO/'assets/asset-patch/active'/name
        assert archive.resolve().parent == (REPO/'assets/asset-patch/active').resolve()
        with zipfile.ZipFile(archive) as z:
            selected = set(wanted).intersection(z.namelist()) - set(found)
            if not selected:
                continue
            digest = next(x for x in entry['archive_integrity'] if x['name'] == name)
            assert archive.stat().st_size == digest['size'] and p.sha(archive.read_bytes()) == digest['sha256']
            for name in selected:
                found[name] = z.read(name)
                receipts[wanted[name]] = dict(archive=str(archive), member=name,
                    sha256=p.sha(found[name]), size=len(found[name]), version=entry['version'])
        if set(found) == set(wanted):
            break
    assert set(found) == set(wanted), 'required current resource missing'
    assert path.read_bytes() == manifest_raw, 'manifest changed during read'
    return {wanted[n]: raw for n, raw in found.items()}, receipts, manifest_raw


def build(work):
    work = work.resolve()
    assert work.is_relative_to(Path('F:/codex/work').resolve())
    assert not work.is_relative_to((REPO/'.cdn').resolve())
    output = REPO/'assets/asset-patch/active'/ARCHIVE
    assert not output.exists(), 'never replace an existing subpackage'
    current, sources, manifest_raw = read_active([LEADER, ABILITY, TEXT, CHARACTER])
    after = restore(current[LEADER], current[ABILITY])
    assert after != current[LEADER]
    assert restore(after, current[ABILITY]) == after
    old_map, new_map = p.rawmap(current[LEADER]), p.rawmap(after)
    old_rows, new_rows = p.csvrows(old_map[KEY]), p.csvrows(new_map[KEY])
    assert len(old_rows) == 11 and len(new_rows) == 12
    assert p.csvrows(p.rawmap(current[CHARACTER])[KEY])[0][17] == KEY
    description = wf_describe.describe_line(new_rows[-1], 'leader_ability')
    assert '固有状态等级+ 1' in description
    n = member(LEADER)
    siblings = []
    for sibling in sorted(output.parent.glob('pinball-1.4.104-1.4.105-*.zip')):
        with zipfile.ZipFile(sibling) as z:
            assert n not in z.namelist(), ('sibling resource overlap', str(sibling))
        siblings.append(dict(name=sibling.name, size=sibling.stat().st_size, sha256=p.sha(sibling.read_bytes())))
    loose = REPO/'assets/asset-patch'/n
    loose_before = loose.read_bytes() if loose.exists() else None
    if loose_before is not None:
        save(work/'source-loose-before'/n, loose_before)
    for logical, raw in current.items():
        save(work/'before'/logical, raw)
    save(work/'after'/LEADER, after)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        info = zipfile.ZipInfo(n, (2026, 9, 11, 0, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        z.writestr(info, after)
    archive = buffer.getvalue()
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        assert z.namelist() == [n] and z.testzip() is None and z.read(n) == after
        validate_stacks(p.csvrows(p.rawmap(z.read(n))[KEY]), p.csvrows(p.rawmap(current[ABILITY])['1399951']))
    latest, _, _ = read_active([LEADER, ABILITY, TEXT, CHARACTER])
    assert latest == current, 'target resource changed during preparation'
    assert (loose.read_bytes() if loose.exists() else None) == loose_before, 'source loose preimage changed'
    integrity = dict(name=ARCHIVE, size=len(archive), sha256=p.sha(archive), members=1, files=[n])
    report = dict(base_version='1.4.104', version='1.4.105', archive_sequence=4, archive=integrity,
        source_manifest_sha256=p.sha(manifest_raw), sources=sources,
        files=[dict(logical=LEADER, root='common', member=n, before_sha256=p.sha(current[LEADER]),
                    sha256=p.sha(after), size=len(after))],
        character_id=KEY, unique_condition_id=STATE, before_rows=11, after_rows=12,
        changed_top_level_keys=[KEY], unrelated_records_preserved=len(old_map)-1,
        outer_order_preserved=True, original_eleven_rows_preserved=True,
        target_leaf_before_sha256=p.sha(old_map[KEY]), target_leaf_after_sha256=p.sha(new_map[KEY]),
        added_row_zero_based=11, added_row_nonempty={str(i):v for i,v in enumerate(new_rows[-1]) if v},
        added_row_description=description, independent_fever_stack_sources=dict(leader=1, ability1=1),
        expected_behavior='雷共鸣且担任队长：每次进入 Fever 两个独立来源各 +1 层，合计 +2；非队长仍由能力 1 加 1 层。',
        idempotent=True, sibling_archives_preserved=siblings,
        source_loose=dict(path=str(loose), before_sha256=p.sha(loose_before) if loose_before else None,
                          matches_active_before=loose_before == current[LEADER],
                          after_sha256=p.sha(after), integration_action='replace this exact source loose resource from part 4'),
        sparse_work=str(work), source_backup=str(work/'source-loose-before'),
        server_files=[], save_impact='仅恢复现有战斗能力行，不改变持久化结构、角色或状态 ID、养成进度及存档导入导出兼容性。',
        platforms=['Android', 'iOS'], client_binary_changes=False,
        source_manifest_modified=False, source_loose_modified=False, runtime_modified=False,
        device_tested=False, desktop_air_run=False, published=False)
    save(output, archive)
    save(AUDIT/'report.json', jsonbytes(report))
    save(AUDIT/'archive-integrity.json', jsonbytes(integrity))
    save(work/'report.json', jsonbytes(report))
    print(json.dumps(dict(archive=str(output), **integrity), ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--work', type=Path, required=True)
    build(parser.parse_args().work)
