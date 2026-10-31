"""Compare current356 bodies with the exact compiler-only inputs already used."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
from audit_instance_dispatch import load, CURRENT, p
from audit_recompile_closure import LINK_REPORTS, ROOT, REMOVE

def main():
    destination = ROOT / 'body-availability-run01.json'
    assert not destination.exists()
    current = load(CURRENT)
    cb = {b[0]: b for b in current.a.bodies}
    results, missing, differences, tiny, bodies = [], [], [], [], []
    for path in LINK_REPORTS:
        link = json.loads(path.read_text('utf8'))
        cp = Path(link['compiled_report'])
        report = json.loads(cp.read_text('utf8'))
        source = cp.parent / 'cumulative.abc'
        compiled = p.abcfmt.ABC(source.read_bytes())
        sb = {b[0]: b for b in compiled.bodies}
        wanted = {int(r['method']) for r in link['functions']}
        stub_count = report['stubbed_methods']
        for function in link['functions']:
            mid = int(function['method'])
            b, s = cb.get(mid), sb.get(mid)
            row = dict(method=mid, label=current.labels.get(mid, 'UNMAPPED'),
                current_body_available=b is not None, compiler_source_body_available=s is not None,
                compiler_source=str(source), native_function_bytes=function['size'],
                previous_compile_global_stub_count=stub_count,
                migrating_instance_helper=mid in REMOVE)
            if b is None or s is None:
                missing.append(row)
            else:
                row['current_code_bytes'] = len(b[5])
                row['previous_compiler_code_bytes'] = len(s[5])
                row['current_code_exact_previous_compiler_input'] = b[5] == s[5]
                row['current_header_exact_previous_compiler_input'] = b[:5] == s[:5]
                if b[5] != s[5]:
                    differences.append(row)
                if len(b[5]) <= 16:
                    row['tiny_code'] = b[5].hex()
                    row['tiny_opcodes'] = [hex(op) for op, _ in p.asm.opwalk.walk(b[5])]
                    tiny.append(row)
            bodies.append(row)
        results.append(dict(link_report=str(path), compile_report=str(cp), tracked_in_link=len(wanted),
            compiler_global_stub_count=stub_count))
    assert len(bodies) == 356
    value = dict(scope='Current356 body-availability audit; tiny functions are candidates, not automatically stubs',
        function_count=len(bodies), report_sources=results, missing=missing,
        code_differences_from_exact_previous_compiler_inputs=differences,
        tiny_bodies=tiny, all_functions=bodies)
    destination.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', 'utf8')
    print(json.dumps(dict(function_count=len(bodies), missing=len(missing),
        code_differences=len(differences), tiny_bodies=len(tiny),
        differences=[dict(method=r['method'], label=r['label'], current=r.get('current_code_bytes'), previous=r.get('previous_compiler_code_bytes')) for r in differences],
        tiny=[dict(method=r['method'], label=r['label'], code=r['tiny_code']) for r in tiny], output=str(destination)), ensure_ascii=False))

if __name__ == '__main__':
    main()
