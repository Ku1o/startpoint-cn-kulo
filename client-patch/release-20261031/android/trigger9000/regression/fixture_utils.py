"""Pure fixture-source helpers. Do not execute outside run_bounded after slot assignment."""
from pathlib import Path
import json

def write_sources(root,files):
    root=Path(root).resolve()
    for name,source in files.items():
        target=(root/name).resolve()
        if not target.is_relative_to(root):
            raise ValueError('Fixture source escapes owned source root: '+str(target))
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(source,encoding='utf-8')

def pinned_json(path,expected_sha256,sha):
    raw=Path(path).read_bytes()
    if sha(raw)!=expected_sha256:
        raise ValueError('Frozen row/contract identity differs: '+str(path))
    return json.loads(raw)

def finish_result(root,result):
    path=Path(root).resolve()/'result.json'
    if path.exists():
        raise FileExistsError('A new run must use a fresh output directory')
    path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
