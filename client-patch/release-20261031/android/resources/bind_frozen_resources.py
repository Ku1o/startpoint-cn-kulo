"""Bind the requested embedded dependencies and shared tables to the frozen chain."""
from pathlib import Path
import argparse,hashlib,json,sys,zipfile
ROOT=Path(__file__).resolve().parent
import resource_inputs as R
R.repository_tools()
import wf_mod_tool as C
def sha(b):return hashlib.sha256(b).hexdigest()
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path,required=True);args=ap.parse_args();output=R.output_path(args.output)
    frozen_file=R.input_path('frozen_resource');freeze=read(frozen_file);declared=R.source_contract('shared-inputs344.json')
    path=R.input_path('frozen_manifest');raw=path.read_bytes()
    assert sha(raw)==freeze['manifestSha256']==declared['manifestSha256']
    manifest=json.loads(raw);assert manifest['cdn_version']==freeze['targetVersion']=='1.4.344'
    active=R.input_directory('candidate_active_dir')
    index={}
    for record in freeze['archives']:
        archive=active/record['name']
        assert archive.stat().st_size==record['size']
        with zipfile.ZipFile(archive) as z:
            assert len(z.namelist())==record['members']
            for member in z.namelist():
                if member in index:raise ValueError('duplicate terminal candidate member')
                index[member]=archive
    original=read(R.input_path('shared_resolution'))
    baseline_names={n for e in manifest['patches'] if e.get('enabled') for n in (e.get('chain') or [e.get('archive')]) if n}
    prefixes={'common':'upload','android':'android_upload','ios':'ios_upload','medium':'medium_upload','small':'small_upload'}
    winners=[]
    for row in original['sharedDefinitionWinners']:
        h=C.sha1_path(row['logical']);member='production/'+prefixes[row['root']]+'/'+h[:2]+'/'+h[2:]
        candidate=index.get(member)
        if candidate is None:
            candidate=R.input_directory('baseline_active_dir')/Path(row['archive']).name
            assert candidate.name in baseline_names,'baseline archive is not part of frozen chain'
        with zipfile.ZipFile(candidate) as z:data=z.read(member)
        assert sha(data)==row['actualSHA256'],('shared definition changed after semantic review',row['logical'])
        winners.append(dict(root=row['root'],logical=row['logical'],archive=str(candidate),member=member,sha256=sha(data),
                            sameBytesAsSemanticallyReviewedWinner=True))
    expected={(r['root'],r['logical']):r['sha256'] for r in declared['entries']}
    assert len(winners)==len(expected)==declared['count']==8 and {(r['root'],r['logical']):r['sha256'] for r in winners}==expected
    bundle_list=R.input_path('bundle67_source_contract')
    bundle=read(bundle_list);assert bundle['count']==67
    result=dict(status='shared_inputs_bound_to_actual_frozen_manifest',frozenResource=str(frozen_file),
                frozenManifest=str(path),manifestSha256=sha(raw),targetVersion=freeze['targetVersion'],
                sourceSemanticReviewManifestSha256=original['manifestSHA256'],
                provenanceNote='The earlier dependency review had a prior manifest hash. Each shared winning payload is read from the frozen chain and proven unchanged here.',
                sharedDefinitionWinners=winners,bundle67Contract=str(bundle_list),bundle67ContractSha256=sha(bundle_list.read_bytes()),
                baselinePlatformReadback=str(R.input_path('baseline_decoder_report')),
                finalCarrierReadback='pending final APK/IPA',completeGameplayClosureProven=False,deviceTested=False)
    output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({'status':result['status'],'manifestSha256':result['manifestSha256'],'sharedTables':len(winners),'bundleEntries':67}))
if __name__=='__main__':main()
