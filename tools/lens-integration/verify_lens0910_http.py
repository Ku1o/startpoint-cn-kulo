"""Read the actual local asset API, advertised ZIP and platform resource URLs."""
import argparse,io,json,os,urllib.request,zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import prepare_content as p
import five_boss_art_contract as art
def verify(work,pristine,base_url):
    audit=p.REPO/'assets/asset-patch/audit/lens0910-1.4.112-test';runtime=Path('F:/startpoint-cn-main')
    report=p.readj(audit/'report.json');plan=p.readj(audit/'local-sync-report.json');inventory=p.readj(audit/'resource-inventory.json')
    checks=[];download=None
    def get(url):
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url,timeout=20) as r:return r.read()
    for device in ['Android','iOS']:
        for version in ['1.4.109','1.4.111','1.4.112']:
            request=urllib.request.Request(base_url+'/api/index.php/asset/get_path',data=b'{}',headers={'Content-Type':'application/json','Accept':'application/json','device':device,'res_ver':version})
            data=json.loads(get(request))['data'];assert data['info']['target_asset_version']=='1.4.112'
            entries=[r for edge in data['diff'] for r in edge['archive'] if r['location'].endswith('/'+report['archive']['name'])]
            assert len(entries)==(0 if version=='1.4.112' else 1)
            if entries and download is None:
                raw=get(entries[0]['location']);assert p.sha(raw)==report['archive']['sha256'];download=raw
            checks.append(dict(device=device,from_version=version,target='1.4.112',diffs=[x['version'] for x in data['diff']]))
    def verify_row(row):
        raw=get(base_url+'/patch/cn/dummy/download/'+row['member']);assert p.sha(raw)==row['sha256'],row['logical']
        return dict(root=row['root'],logical=row['logical'],sha256=p.sha(raw),size=len(raw))
    with zipfile.ZipFile(io.BytesIO(download)) as z:
        assert z.testzip() is None
        for row in report['resources']:assert p.sha(z.read(row['member']))==row['sha256']
    with ThreadPoolExecutor(max_workers=4) as pool:direct=list(pool.map(verify_row,report['resources']))
    os.environ.update(WF_SERVER_DIR=str(runtime),WF_CDN_DIR=str(pristine),WF_LIVE_CDN='1')
    import wf_live_cdn as live
    live.clear_cache();assert live.describe()['tail']=='1.4.112'
    for row in inventory:
        assert p.sha(live.read_relative(p.hrel(row['logical']),roots=(row['root'],)).data)==row['sha256']
        loose=runtime/'assets/asset-patch'/row['member']
        if loose.exists():assert p.sha(loose.read_bytes())==row['sha256'],('loose override differs',row['logical'])
    for row in plan['files']:assert p.sha((Path(row['root'])/row['path']).read_bytes())==row['sha256']
    stock_archive_reads=[]
    def icon_read(logical):
        try:raw=get(base_url+'/patch/cn/dummy/download/'+p.member(('common',p.hrel(logical))))
        except urllib.error.HTTPError as exc:
            assert exc.code==404 and not any(r['logical']==logical for r in report['resources'])
            # Unchanged native resources can live only in the base preload ZIP.
            stock_archive_reads.append(logical);return live.read_logical(logical).data
        assert raw==live.read_logical(logical).data;return raw
    display=art.validate_display(icon_read)
    for rel,h in report['protected_local_hold_sha256'].items():assert p.sha((p.REPO/rel).read_bytes())==h
    for name,h in report['previous_published_archives_preserved'].items():assert p.sha((runtime/'assets/asset-patch/active'/name).read_bytes())==h
    result=dict(status='passed',version='1.4.112',real_api_checks=checks,direct_resources=direct,unchanged_native_reads_from_preloaded_archives=stock_archive_reads,archive_sha256=report['archive']['sha256'],effective_inventory_checked=len(inventory),synced_files=len(plan['files']),icon_display=display,older_archives_unchanged=True,protected_source_preserved=True,desktop_air_run=False,device_tested=False)
    p.savej(audit/'local-http-verification.json',result);p.savej(work/'local-http-verification.json',result)
    print(json.dumps(dict(status='passed',version_checks=len(checks),direct_resources=len(direct),inventory=len(inventory),synced_files=len(plan['files']))))
if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--work',type=Path,required=True);ap.add_argument('--pristine',type=Path,required=True);ap.add_argument('--base-url',default='http://127.0.0.1:8001');a=ap.parse_args();verify(a.work,a.pristine,a.base_url)
