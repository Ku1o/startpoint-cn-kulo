"""Read-only final-state verification of the consolidated CDN and selected APK."""
import argparse,json,os,zipfile
from pathlib import Path
import prepare_content as p
import five_boss_art_contract as art

def verify(server,pristine,report_path,apk,out):
    report=p.readj(report_path);manifest=p.readj(server/'assets/asset-patch/manifest.json')
    assert manifest['cdn_version']=='1.4.104';art.validate_manifest(manifest)
    entries=[e for e in manifest['patches'] if e.get('enabled') and int(e['version'].split('.')[-1])>103]
    assert len(entries)==1 and entries[0]['depends_on']=='1.4.103'
    archive=server/'assets/asset-patch/active'/report['archive']['name']
    assert p.sha(archive.read_bytes())==report['archive']['sha256']
    os.environ.update(WF_SERVER_DIR=str(server),WF_CDN_DIR=str(pristine),WF_LIVE_CDN='1')
    import wf_live_cdn as live
    live.clear_cache();assert live.describe()['tail']=='1.4.104'
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        for row in report['resources']:assert p.sha(z.read(row['member']))==row['sha256']
    for row in report['final_inventory']:
        assert p.sha(live.read_relative(p.hrel(row['logical']),roots=(row['root'],)).data)==row['sha256'],row['logical']
        loose=server/'assets/asset-patch'/row['member']
        if loose.exists():assert p.sha(loose.read_bytes())==row['sha256'],('loose override drift',row['logical'])
    display=art.validate_display(lambda n:live.read_logical(n).data)
    assert p.sha(apk.read_bytes())=='fd42a417dc7231c8dbc421e4839ceeefcfb027f8c83d8bc418baa427dd0b969d'
    with zipfile.ZipFile(apk) as z:
        assert p.sha(z.read('assets/worldflipper_android_release.swf'))=='7e3f40fc17ac6fbbec52a0775c6a6357edd258874ed62d13d4ceb287d56d97d3'
    result=dict(status='passed',version='1.4.104',inventory_checked=len(report['final_inventory']),archive_members=len(report['resources']),archive_sha256=report['archive']['sha256'],all_final_payloads_preserved=True,display=display,apk_sha256=p.sha(apk.read_bytes()),apk_unchanged=True,desktop_air_run=False,device_tested=False)
    p.savej(out,result);print(json.dumps({k:result[k] for k in ['status','version','inventory_checked','archive_members','apk_unchanged']}))
if __name__=='__main__':
    ap=argparse.ArgumentParser()
    for n in ['server','pristine','report','apk','out']:ap.add_argument('--'+n,type=Path,required=True)
    a=ap.parse_args();verify(a.server,a.pristine,a.report,a.apk,a.out)
