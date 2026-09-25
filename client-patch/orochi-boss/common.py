from pathlib import Path
import hashlib

HERE = Path(r"F:/codex/startpoint-cn-private-clean/client-patch/ios-cumulative-login")
ROOT = Path(r"F:/codex/startpoint-cn-private-clean")
WORK = Path(r"F:/codex/work/client-public-20260926/build/ios-boss")
OUT = Path(r"F:/codex/outputs/orochi-boss-public-20260926")
PRIVATE = Path(r"F:/codex/.codex/secrets/starpoint-client-admission")
PAIR = PRIVATE / "releases/orochi-boss-public-20260926"
OLD_IDS = {"ios": "ios-184-author-1043-20260924"}
IDS = {"ios": "ios-184-author-1047-20260925"}
sha = lambda data: hashlib.sha256(data).hexdigest()

def load(name, path):
    import importlib.util
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
