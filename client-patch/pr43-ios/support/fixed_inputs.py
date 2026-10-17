"""Pinned reproduction metadata; changes require a new audited recipe."""
import hashlib, json
from pathlib import Path
HASHES = {'dependency-hashes.json': '77732231196d1adf13dee76bf49ed43adb8b39ec86cf93af6469afceb79b5a35', 'runtime-helper-map.json': 'cd85d5394ba0764bb4777a7f6c48902ffc97aa895a23d12eb8651962b693b406', 'additional-helper.json': 'c78a57cc90dc375f1470f564adfe24798f58500a80383fb901ec4d28697f28a9', 'runtime-extra-map.json': 'fc41536b67d9c6e56d8704bdc37176bc2ad468194cc1e1e1e78b2338e3e5cbbc', 'ios-method-map.json': 'b781c2a345737d25f8b74a04bb7084a3ea54cdb7e383bc06e435f15f244f3282', 'baseline-contract.json': 'fd6469eefd76d34c18d57161bb5d551223e147456bb61e1c67c48da1a74acf50'}

def fixed_json(name):
    raw=(Path(__file__).resolve().parent/name).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=HASHES[name]:
        raise ValueError("Recipe metadata hash mismatch: "+name)
    return json.loads(raw)


def check_dependencies(directory):
    directory=Path(directory)
    expected=fixed_json('dependency-hashes.json')
    found={p.name:p for p in directory.glob('*.abc') if not p.name.startswith('284-')}
    if set(found)!=set(expected):
        raise ValueError('Expected the fixed 284 private ABC dependencies')
    for name,digest in expected.items():
        if hashlib.sha256(found[name].read_bytes()).hexdigest()!=digest:
            raise ValueError('Dependency ABC identity mismatch: '+name)
    return [found[name] for name in sorted(found)]
