"""Create the unsigned iOS candidate using exactly six sparse replacements."""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
from pathlib import Path
import plistlib
import zipfile

from native_support import dump, sha
import overlimit_ios



def run(link_report, output, *, resources, output_root):
    report = json.loads(Path(link_report).read_text('utf8'))
    assert report['status'] == 'linked_native_not_executed'
    output = Path(output).resolve()
    root = Path(output_root).resolve()
    repo = Path(__file__).resolve().parents[2]
    assert not root.is_relative_to(repo) and output.is_relative_to(root), 'Output must stay inside an external output root'
    assert not output.exists(), 'Fresh output path required'
    reg = report['source_ipa']
    source = Path(reg['ipa'])
    assert sha(source.read_bytes()) == reg['ipa_sha256']
    native = Path(report['native_file']).read_bytes()
    swf = Path(report['swf_file']).read_bytes()
    assert sha(native) == report['native_sha256'] and sha(swf) == report['swf_sha256']
    with zipfile.ZipFile(source) as archive:
        assert len(archive.namelist()) == len(set(archive.namelist()))
        replacements = overlimit_ios.resource_replacements(Path(resources), archive.read)
        replacements.update({reg['native_member']: native, reg['swf_member']: swf})
        assert len(replacements) == 6 and set(replacements) <= set(archive.namelist())
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, 'w', allowZip64=True) as result:
            result.comment = archive.comment
            for info in archive.infolist():
                result.writestr(copy.copy(info), replacements.get(info.filename, archive.read(info)))
    # Read the actual carrier, preserving all original package metadata/member
    # order and ensuring unrelated payloads are equal byte for byte.
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(output) as new:
        assert old.namelist() == new.namelist() and old.comment == new.comment
        assert new.testzip() is None
        changed = []
        for a, b in zip(old.infolist(), new.infolist()):
            for key in ('filename', 'date_time', 'compress_type', 'comment', 'extra', 'create_system', 'external_attr'):
                assert getattr(a, key) == getattr(b, key), (a.filename, key)
            if old.read(a) != new.read(b):
                changed.append(a.filename)
        assert set(changed) == set(replacements)
        identity = plistlib.loads(new.read('Payload/worldflipper.app/Info.plist'))
        assert (identity['CFBundleIdentifier'], identity['CFBundleShortVersionString'], identity['CFBundleVersion']) == ('com.kulo.wf', '1.8.4', '1.8.46')
    result = dict(status='unsigned_offline_candidate', ipa=str(output), ipa_sha256=sha(output.read_bytes()),
                  size_bytes=output.stat().st_size, source_ipa=reg,
                  link_report=str(Path(link_report).resolve()), native_sha256=sha(native), swf_sha256=sha(swf),
                  changed_members=changed, original_members_retained=True, zip_crc_verified=True,
                  package_metadata_preserved=True, total_methods=report['total_methods'],
                  full_abc_sha256=report['full_abc_sha256'], runtime_abc_sha256=report['runtime_abc_sha256'],
                  signing='unsigned', device_tested=False, accepted_registry_updated=False)
    dump(output.with_suffix('.json'), result)
    print(json.dumps({k: result[k] for k in ('status', 'ipa', 'ipa_sha256', 'size_bytes')}))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--linked', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resources', type=Path, required=True)
    parser.add_argument('--output-root', type=Path, required=True)
    args = parser.parse_args()
    run(args.linked, args.output, resources=args.resources, output_root=args.output_root)


if __name__ == '__main__':
    main()
