"""Read the requested 67 logical resources from actual platform carriers.

This verifies salted logical identity, platform roots, strict stored decoding
and Android/iOS payload correspondence. It is not GPU or gameplay acceptance.
"""
from pathlib import Path
import argparse,hashlib,io,json,sys,zipfile,zlib
ROOT=Path(__file__).resolve().parent
import resource_inputs as R
REPO=R.cfg.repo_path()
R.repository_tools()
import wf_mod_tool as C, wf_assets
from PIL import Image

def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))

def ordered(raw,depth=0):
    if depth>8:raise ValueError('nested orderedmap depth is excessive')
    keys,pairs,n=C.parse_index(raw)
    data=raw[4+n:]
    assert not pairs or pairs[-1][1]==len(data),'orderedmap payload tail mismatch'
    prev=0;leaves=0;maxdepth=depth
    for _,end in pairs:
        part=data[prev:end];prev=end
        if not part:continue
        try:plain=zlib.decompress(part)
        except zlib.error:
            nested=ordered(part,depth+1);leaves+=nested['leafRows'];maxdepth=max(maxdepth,nested['maxDepth'])
        else:
            try:plain.decode('utf-8')
            except UnicodeDecodeError:
                nested=ordered(plain,depth+1);leaves+=nested['leafRows'];maxdepth=max(maxdepth,nested['maxDepth'])
            else:leaves+=1
    return dict(outerKeys=len(keys),leafRows=leaves,maxDepth=maxdepth)

def decode(logical,data):
    if logical.endswith('.amf3.deflate'):
        plain=zlib.decompress(data,-15);reader=C.AMF3Reader(plain);value=reader.read_value()
        assert reader.pos==len(plain),'trailing AMF3 bytes'
        return dict(format='strict AMF3 raw-deflate',type=type(value).__name__,topKeys=sorted(value)[:20] if isinstance(value,dict) else None),value
    if logical.endswith('.png'):
        decoded=wf_assets.png_decode_stored(data)
        im=Image.open(io.BytesIO(decoded));im.load()
        return dict(format='strict stored PNG',size=list(im.size),mode=im.mode,pixelsSha256=sha(im.convert('RGBA').tobytes())),None
    if logical.endswith('.orderedmap'):
        return dict(format='orderedmap',**ordered(data)),None
    raise ValueError('unreviewed dependency format: '+logical)

def run(android,ios,stage):
    contract=R.source_contract('bundle67.json')
    entries=contract['entries'];assert len(entries)==len({x['logical'] for x in entries})==67
    with zipfile.ZipFile(android) as apk:
        bundle=apk.read('assets/bundle.zip')
        assert apk.read('assets/bundle.zip.sha1').strip().decode()==hashlib.sha1(bundle).hexdigest()
    results=[];platforms={}
    with zipfile.ZipFile(io.BytesIO(bundle)) as az,zipfile.ZipFile(ios) as iz:
        aset=set(az.namelist());iset=set(iz.namelist())
        assert len(aset)==len(az.namelist()) and len(iset)==len(iz.namelist())
        for entry in entries:
            logical=entry['logical'];h=C.sha1_path(logical);relative=h[:2]+'/'+h[2:]
            assert entry['member'].endswith(relative),'declared member does not match salted logical path'
            android_member=entry['member'];assert android_member in aset
            a=az.read(android_member);assert sha(a)==entry['sha256'],'current Android dependency differs from required binding'
            acheck,atree=decode(logical,a)
            choices=['Payload/worldflipper.app/asset/production/'+r+'/'+relative for r in ('ios_bundle','bundle','medium_bundle')]
            matches=[n for n in choices if n in iset]
            row=dict(logical=logical,androidMember=android_member,androidSha256=sha(a),androidDecoded=acheck,
                     iosMatches=matches)
            if not matches:
                row.update(status='ios_missing_requires_native_fallback_or_resource_supply');results.append(row);continue
            # Native non-scaled battle assets prefer platform bundle, then
            # shared bundle. medium_bundle is separately recorded and never
            # silently accepted as a normal battle-asset replacement.
            chosen=matches[0];b=iz.read(chosen);bcheck,btree=decode(logical,b)
            acceptable='/ios_bundle/' in chosen or '/bundle/' in chosen
            row.update(iosMember=chosen,iosSha256=sha(b),iosDecoded=bcheck,
                       bytesEqual=a==b,decodedTreeEqual=(atree==btree if atree is not None else None),
                       status='same_platform_bundle_payload' if acceptable and a==b else 'platform_difference_requires_review')
            results.append(row)
    unresolved=[r['logical'] for r in results if r['status']!='same_platform_bundle_payload']
    return dict(status='all67_actual_platform_bundle_payloads_and_decoders_match' if not unresolved else 'platform_bundle_review_required',
                stage=stage,androidCarrier=str(android),iosCarrier=str(ios),androidBundleSha256=sha(bundle),
                requiredContract=str(ROOT/'bundle67.json'),
                count=len(results),unresolved=unresolved,entries=results,
                interpretation='actual carrier resource identity/strict decoder/platform parity only; semantic producer and final CDN winners are separately bound by CDN dependency resolution',
                gpuOrDeviceTested=False,finalNativeGameplayValidated=False)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--android',type=Path);p.add_argument('--ios',type=Path)
    p.add_argument('--android-sha256');p.add_argument('--ios-sha256')
    p.add_argument('--stage',choices=['baseline','partial_candidate','final_candidate'],default='baseline')
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    android,android_sha=R.carrier(args.android,args.android_sha256,'android_carrier')
    ios,ios_sha=R.carrier(args.ios,args.ios_sha256,'ios_carrier')
    assert args.stage=='baseline' or (args.android is not None and args.ios is not None),'candidate stage needs explicit actual carriers'
    args.output=R.output_path(args.output)
    result=run(android,ios,args.stage)
    result.update(androidCarrierSha256=android_sha,iosCarrierSha256=ios_sha)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('status','stage','count','unresolved')}))

if __name__=='__main__':main()
