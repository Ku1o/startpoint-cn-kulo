"""竞速池四名玩家角色第一轮削弱；可由后续整合发布器复用。

patch_table(logical, raw) 在最新有效表上只替换已审核的 28 行/56 单元格。
完整行指纹保护触发器、对象、条件、冷却与其它字段；未知改动立即拒绝。
CLI 生成两份稀疏候选资源及审计回执，不修改 manifest、不发布或同步。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import zlib

import wf_mod_tool as core


SPEC_PATH = Path(__file__).with_name('race_character_nerf_v1.json')
SPEC = json.loads(SPEC_PATH.read_text(encoding='utf-8'))
TABLES = {entry['logical']: (name, entry) for name, entry in SPEC['tables'].items()}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def row_hash(row: list[str]) -> str:
    return sha256(core.write_csv_lines([row]).encode('utf-8'))


def patch_table(logical: str, raw: bytes) -> tuple[bytes, dict]:
    """Preserve unrelated stored row bytes; accept reviewed before/after rows only."""
    if logical not in TABLES:
        raise ValueError(f'Unsupported logical path: {logical}')
    name, contract = TABLES[logical]
    table = core.read_orderedmap_raw_rows_from_bytes(raw, logical)
    if len(table.keys) != len(set(table.keys)):
        raise ValueError(f'{logical}: duplicate keys')
    stored_before = dict(zip(table.keys, table.rows))
    changes = []
    changed_keys = []
    for key, key_contract in contract['keys'].items():
        if key not in stored_before:
            raise ValueError(f'{logical}: missing key {key}')
        rows = core.read_csv_lines(zlib.decompress(stored_before[key]).decode('utf-8'))
        if len(rows) != key_contract['row_count'] or any(
            len(row) != key_contract['column_count'] for row in rows
        ):
            raise ValueError(f'{logical}#{key}: row/column shape drift')
        old_rows = [list(row) for row in rows]
        for index_string, rule in key_contract['rows'].items():
            index = int(index_string)
            row = rows[index]
            edits = {int(col): values for col, values in rule['edits'].items()}
            normalized = list(row)
            for col, (before, _after) in edits.items():
                normalized[col] = before
            if row_hash(normalized) != rule['before_row_sha256']:
                raise ValueError(f'{logical}#{key} row {index}: unreviewed row drift')
            is_before = all(row[col] == values[0] for col, values in edits.items())
            is_after = all(row[col] == values[1] for col, values in edits.items())
            if not (is_before or is_after):
                raise ValueError(f'{logical}#{key} row {index}: unknown or partially applied values')
            for col, (before, after) in edits.items():
                changes.append({'key':key, 'row':index, 'column':col,
                                'before':before, 'after':after, 'changed':row[col] != after})
                row[col] = after
        if rows != old_rows:
            changed_keys.append(key)
            table.rows[table.keys.index(key)] = zlib.compress(core.write_csv_lines(rows).encode('utf-8'))
    output = core.build_orderedmap_raw_rows(table) if changed_keys else raw
    readback = core.read_orderedmap_raw_rows_from_bytes(output, logical)
    if readback.keys != table.keys or readback.rows != table.rows:
        raise AssertionError(f'{logical}: serialized table readback mismatch')
    for key, stored in zip(readback.keys, readback.rows):
        if key not in changed_keys and stored != stored_before[key]:
            raise AssertionError(f'{logical}: unrelated stored key changed: {key}')
    return output, {'table':name, 'logical':logical, 'input_sha256':sha256(raw),
                    'output_sha256':sha256(output), 'key_count':len(table.keys),
                    'changed_keys':changed_keys, 'changed_cells':sum(c['changed'] for c in changes),
                    'changes':changes, 'unrelated_stored_rows_unchanged':True,
                    'serialized_readback_verified':True}


def checked_output_dir(server_root: Path, output_dir: Path) -> Path:
    """Reject lexical, junction and symlink routes into the pristine CDN."""
    resolved = output_dir.resolve()
    baseline = (server_root / '.cdn').resolve()
    if (any(part.lower() == '.cdn' for part in output_dir.absolute().parts)
            or any(part.lower() == '.cdn' for part in resolved.parts)
            or resolved == baseline or baseline in resolved.parents):
        raise ValueError('Output must be outside the pristine .cdn baseline')
    return resolved


def build_candidate(server_root: Path, output_dir: Path) -> dict:
    """Resolve fresh effective resources and prepare an unpublished integration input."""
    import wf_live_cdn as live
    import wf_describe

    server_root = server_root.resolve()
    output_dir = checked_output_dir(server_root, output_dir)
    os.environ['WF_SERVER_DIR'] = str(server_root)
    os.environ['WF_CDN_DIR'] = str(server_root / '.cdn/cn')
    live.clear_cache()
    inputs = {logical: live.read_logical(logical) for logical in TABLES}
    if len({p.tail for p in inputs.values()}) != 1:
        raise ValueError('CDN chain changed during input reads; rerun against a stable tail')
    prepared = {}
    reports = []
    descriptions = {}
    for logical, payload in inputs.items():
        patched, report = patch_table(logical, payload.data)
        again, second = patch_table(logical, patched)
        if again != patched or second['changed_cells'] != 0:
            raise AssertionError('Patch is not byte-idempotent')
        report.update({'tail':payload.tail, 'root':payload.root, 'archive':str(payload.archive),
                       'member':payload.member, 'byte_idempotent':True})
        member = Path(payload.member)
        if member.is_absolute() or '..' in member.parts or member.parts[:2] != ('production','upload'):
            raise ValueError(f'Unexpected common master member: {payload.member}')
        prepared[logical] = (patched, report)
        reports.append(report)
        name, contract = TABLES[logical]
        before_rows = core.read_orderedmap_bytes(payload.data, logical).text_rows()
        after_rows = core.read_orderedmap_bytes(patched, logical).text_rows()
        descriptions[name] = {key: {
            'before':wf_describe.describe_rows(core.read_csv_lines(before_rows[key]), name),
            'after':wf_describe.describe_rows(core.read_csv_lines(after_rows[key]), name),
        } for key in contract['keys']}
    # Refuse to emit an already stale candidate if another task publishes while we prepare.
    live.clear_cache()
    for logical, original in inputs.items():
        current = live.read_logical(logical)
        if current.tail != original.tail or current.data != original.data:
            raise ValueError('CDN chain changed during generation; rerun against its new tail')
    receipt = {'id':SPEC['id'], 'status':'candidate_not_published',
               'server_root':str(server_root), 'source_tail':next(iter(inputs.values())).tail,
               'spec_sha256':sha256(SPEC_PATH.read_bytes()),
               'tables':reports, 'changed_cells':sum(r['changed_cells'] for r in reports),
               'delivery':'Apply patch_table to the latest terminal bytes before creating a sequential CDN edge. '
                          'These two common master resources are shared by Android and iOS.'}
    output_dir.mkdir(parents=True, exist_ok=True)
    for logical, (patched, report) in prepared.items():
        name, _contract = TABLES[logical]
        before_path = output_dir / 'before' / f'{name}.orderedmap'
        after_path = output_dir / report['member']
        before_path.parent.mkdir(parents=True, exist_ok=True)
        after_path.parent.mkdir(parents=True, exist_ok=True)
        before_path.write_bytes(inputs[logical].data)
        after_path.write_bytes(patched)
        if after_path.read_bytes() != patched:
            raise AssertionError(f'Output file readback mismatch: {after_path}')
    (output_dir / 'receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (output_dir / 'descriptions.json').write_text(json.dumps(descriptions,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server-root',type=Path,required=True)
    parser.add_argument('--output-dir',type=Path,required=True)
    args = parser.parse_args()
    receipt = build_candidate(args.server_root,args.output_dir)
    print(json.dumps({'source_tail':receipt['source_tail'], 'changed_cells':receipt['changed_cells'],
                      'receipt':str(args.output_dir / 'receipt.json'), 'status':receipt['status']}))


if __name__ == '__main__':
    main()
