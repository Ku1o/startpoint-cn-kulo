"""Package the native-only repair; the SWF and all other members stay exact."""
import sys as _followup_sys
from pathlib import Path as _FollowupPath
_followup_root = next(p for p in _FollowupPath(__file__).resolve().parents if (p / 'client-patch').is_dir())
_followup_sys.path.insert(0, str(_followup_root / 'client-patch/release-20261031/ios'))
import followup_config as fc
fc.bootstrap()
import argparse, copy, hashlib, plistlib, zipfile
from pathlib import Path
import common as c
NATIVE='Payload/worldflipper.app/worldflipper'
SWF='Payload/worldflipper.app/worldflipper_ios_release.swf'
def file_sha(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while data:=stream.read(1024*1024):digest.update(data)
    return digest.hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--linked',type=Path,required=True);ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();c.bounded_job();out=c.fresh(args.output);c.fresh(out.with_suffix('.json'))
    report=c.read(args.linked);previous=c.read(report['previous_package_report'])
    c.require(report['status']=='linked_native_not_executed' and report['unwind_finalized'],'Native not finalized')
    c.require(previous['ipa_sha256']==c.IPA_SHA and report['full_abc_sha256']==c.ABC_SHA,'Wrong cumulative input')
    native=Path(report['native_file']).read_bytes();swf=Path(report['swf_file']).read_bytes()
    c.require(c.sha(native)==report['native_sha256'] and c.sha(swf)==report['swf_sha256'],'Loose payload identity differs')
    c.require(report['swf_sha256']==previous['swf_sha256'],'Native-only repair unexpectedly changed SWF')
    source=Path(previous['ipa']);c.require(source.stat().st_size==previous['size_bytes'],'Verified source size changed')
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(source) as old,zipfile.ZipFile(out,'x',allowZip64=True) as new:
        c.require(len(old.namelist())==len(set(old.namelist())),'Duplicate source ZIP member')
        c.require(old.read(SWF)==swf,'Source SWF differs from linked unchanged SWF')
        new.comment=old.comment
        for info in old.infolist():new.writestr(copy.copy(info),native if info.filename==NATIVE else old.read(info))
    with zipfile.ZipFile(out) as new:
        c.require(new.testzip() is None,'Final ZIP CRC failure')
        identity=plistlib.loads(new.read('Payload/worldflipper.app/Info.plist'))
        c.require(tuple(identity[k] for k in ('CFBundleIdentifier','CFBundleShortVersionString','CFBundleVersion'))==
                  ('com.kulo.wf','1.8.4','1.8.46'),'Bundle identity differs')
    result=dict(status='unsigned_offline_candidate',ipa=str(out),ipa_sha256=file_sha(out),size_bytes=out.stat().st_size,
        link_report=str(args.linked.resolve()),native_sha256=c.sha(native),swf_sha256=c.sha(swf),
        full_abc_sha256=report['full_abc_sha256'],full_abc_sha1=report['full_abc_sha1'],
        runtime_abc_sha256=report['runtime_abc_sha256'],total_methods=report['total_methods'],
        changed_members=[NATIVE],original_members_retained=True,zip_crc_verified=True,package_metadata_preserved=True,
        signing='unsigned',native_executed=False,device_tested=False,accepted_registry_updated=False,
        admission_materials_unchanged=True,packaging_source_sha256=c.sha(Path(__file__).read_bytes()))
    c.dump(out.with_suffix('.json'),result);print(result['status'],result['ipa_sha256'])
if __name__=='__main__':main()
