"""Prepare (without deploying) a paired server admission overlay for the new APK."""
import hashlib, json, secrets, zipfile
from pathlib import Path

SOURCE = Path(r'F:\codex\.codex\secrets\starpoint-client-admission\config')
PRIVATE_RELEASE = Path(r'F:\codex\.codex\secrets\starpoint-client-admission\releases\independent-party-20260923')
OUTPUT = Path(r'F:\codex\outputs\server-overlays\independent-party-20260923')
BUILD_ID = 'android-181-independent-party-20260923'


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main():
    policy = json.loads((SOURCE / 'client-admission.json').read_text(encoding='utf8'))
    keys = json.loads((SOURCE / 'client-admission.keys.json').read_text(encoding='utf8'))
    existing = next((row for row in policy['builds'] if row['id'] == BUILD_ID), None)
    if existing is None:
        policy['builds'].append({
            'id': BUILD_ID,
            'name': 'StarPoint CN 独立连战编队 Android',
            'platform': 'android',
            'enabled': True,
            'allowUntil': None,
        })
        # Keep the secret only in the private local release snapshot and overlay.
        keys[BUILD_ID] = secrets.token_hex(32)
    else:
        assert BUILD_ID in keys, 'existing independent-party build is missing its key'

    for root in (PRIVATE_RELEASE, OUTPUT):
        (root / 'config').mkdir(parents=True, exist_ok=True)
        (root / 'config/client-admission.json').write_text(
            json.dumps(policy, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        (root / 'config/client-admission.keys.json').write_text(
            json.dumps(keys, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

    members = {
        'config/client-admission.json': (OUTPUT / 'config/client-admission.json').read_bytes(),
        'config/client-admission.keys.json': (OUTPUT / 'config/client-admission.keys.json').read_bytes(),
    }
    archive = OUTPUT / 'startpoint-cn-cloud-overlay-independent-party-20260923.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, data in members.items():
            z.writestr(name, data)
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == set(members)
        assert z.testzip() is None
        for name, data in members.items():
            assert z.read(name) == data
    manifest = {
        'build_id': BUILD_ID,
        'status': 'prepared_not_deployed',
        'cloud_deployed': False,
        'members': {name: {'bytes': len(data), 'sha256': sha(data)} for name, data in members.items()},
        'archive': str(archive),
        'archive_sha256': sha(archive.read_bytes()),
        'source_master_unchanged': True,
        'scope': 'Android admission pair for the independent Rush party-set candidate',
    }
    (OUTPUT / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    (PRIVATE_RELEASE / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    report = Path(r'F:\codex\outputs\independent-formations-public-8001-20260923\package-report.json')
    data = json.loads(report.read_text(encoding='utf8'))
    data.update({
        'server_admission_pair_prepared': True,
        'server_admission_pair_status': 'prepared_not_deployed',
        'server_admission_pair': str(archive),
        'server_admission_pair_sha256': manifest['archive_sha256'],
        'server_admission_master_updated': False,
    })
    report.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({
        'build_id': BUILD_ID,
        'archive': str(archive),
        'archive_sha256': manifest['archive_sha256'],
        'status': 'prepared_not_deployed',
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
