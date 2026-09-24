"""Pinned inputs and non-secret metadata for the 1043 public client release."""
from pathlib import Path
import hashlib, importlib.util, json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
WORK = Path('F:/codex/work/author-public-release-20260924')
OUT = Path('F:/codex/outputs/author-public-release-20260924')
PRIVATE = Path('F:/codex/.codex/secrets/starpoint-client-admission')
PAIR = PRIVATE / 'releases/author-1043-public-20260924'
APK = Path('F:/codex/outputs/author-unified-damage-lan-20260924/StarPoint-CN-1.8.1-author-unified-damage-lan-20260924-eac4a37d.apk')
APK_SHA = 'de89cf79f4d101eae28a95175f490e2ff79040dc61ab374064fb08d60c014b09'
ANDROID_SWF_SHA = '2e806d30ad3e2f9b71f63085e03ca3d41886bb81a7b8e01a19133eaea3828ed2'
ANDROID_UUID = 'eac4a37d-aeaa-4d43-8594-fe504a495a75'
IPA = Path('F:/codex/outputs/set-edit-c8601-ios-public-20260924/StarPoint-iOS-1.8.4-independent-formations-set-edit-c8601-public-20260924-unsigned.ipa')
IPA_SHA = '64edf9ada1c0cb1dd8ebff00978394907b93174b519f0106fd41b55f2949917a'
IOS_FULL = IPA.parent / 'formal-set-edit-full.abc'
IOS_FULL_SHA = '79dcca2a2936e8d0476bf42d701d4e0e6b10b206b18230909a7fec228561a10c'
IOS_NATIVE_SHA = '0b23e0362ee69b6ddd1367df383e1b270eeff255bffbbb3543804b69c6a8ec9a'
IOS_SWF_SHA = 'e2033cd4a3dfaf79f413ff89e7f3cf6a38c0c6bb543afd62ade8fb3fe7516b0a'
OLD_IDS = {'android': 'android-181-independent-party-20260923', 'ios': 'ios-184-independent-party-20260923'}
IDS = {'android': 'android-181-author-1043-20260924', 'ios': 'ios-184-author-1043-20260924'}
sha = lambda data: hashlib.sha256(data).hexdigest()

def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def pair():
    keys = json.loads((PAIR/'config/client-admission.keys.json').read_text('utf-8-sig'))
    policy = json.loads((PAIR/'config/client-admission.json').read_text('utf-8-sig'))
    assert len({r['id'] for r in policy['builds']}) == len(policy['builds'])
    for platform, build in IDS.items():
        row, = [r for r in policy['builds'] if r['id'] == build]
        assert row['platform'] == platform and row['enabled'] is True
        assert isinstance(keys[build], str) and len(keys[build]) >= 32
    return policy, keys
