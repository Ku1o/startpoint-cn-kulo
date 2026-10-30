"""UI-first partial composition; explicit pinned core+carry input, no package build."""
from pathlib import Path
import argparse, copy, json
import bootstrap
from input_config import input_path, input_sha, require_output
import editor as p
import patch

def build(source, expected, out):
    source = Path(source).resolve(); out = require_output(out)
    if p.digest(source.read_bytes()) != expected: raise ValueError('UI input SHA mismatch')
    from degree_retraction import verify
    verify(source)
    e = p.R11Editor(source); old = copy.deepcopy(e.abc); report = patch.build(e)
    for i, (a, b) in enumerate(zip(old.instances, e.abc.instances)):
        assert a[:6] == b[:6]
        assert p.body_bytes([0,0,0,0,0,b'',[],a[6]]) == p.body_bytes([0,0,0,0,0,b'',[],b[6][:len(a[6])]])
        assert not any(t.kind in (0,6) for t in b[6][len(a[6]):])
        assert not any(t.kind in (0,6) for t in e.abc.classes[i][1][len(old.classes[i][1]):])
    out.mkdir(parents=True); target = out/'core-ui.partial.swf'; target.write_bytes(p.compose(e))
    read = p.SwfAbc(target); assert len(read.abc.methods) == len(old.methods)+8
    verify(target)
    report.update(input_sha256=expected, output_sha256=p.digest(target.read_bytes()),
                  output=str(target), status='static_candidate_not_revalidated_after_path_adaptation',
                  patches=e.report, old_instances_unchanged=True)
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return report

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--out',required=True); args=ap.parse_args()
    print(json.dumps(build(input_path('corecarry'), input_sha('corecarry'), args.out),ensure_ascii=False))
if __name__ == '__main__': main()
