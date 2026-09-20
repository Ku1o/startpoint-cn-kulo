"""Read actual client proof constants and compare rejected originals with repaired public handshakes."""
import concurrent.futures, hashlib, hmac, json, urllib.request, zipfile
from pathlib import Path
import repair_admission_prefix as fix

MASTER = Path('F:/codex/.codex/secrets/starpoint-client-admission')

def actual_constants(artifact, platform):
    with zipfile.ZipFile(artifact) as z:
        if platform == 'android':
            abcs=[]
            for kind, content, _ in fix.swf_tags(z.read(fix.lan.SWF_MEMBER))[1]:
                if kind != 82: continue
                end=content.index(b'\0',4)
                if content[4:end].startswith(b'cn/admission/'):
                    abcs.append(fix.lan.s.m.abcfmt.ABC(content[end+1:]))
        else:
            native=z.read('Payload/worldflipper.app/worldflipper');off,size=fix.abc_range(native)
            abcs=[fix.lan.s.m.abcfmt.ABC(native[off:off+size])]
    const=fix.lan.constants([[82,None,None,a] for a in abcs])
    prefixes=[value for a in abcs for value in a.strings if value.startswith(b'SP-ADMISSION-1\n')]
    assert len(prefixes)==1
    return const,prefixes[0]

def probe(artifact,platform,repaired,keys):
    const,prefix=actual_constants(artifact,platform)
    build=fix.IDS[platform][1]
    assert const['ID']==build and const['KEY']==keys[build], 'Actual artifact is not paired with master'
    expected=('SP-ADMISSION-1\n'+build+'\n').encode()
    assert (prefix==expected)==repaired, 'Negative or positive client fixture no longer represents the expected bug'
    assert const['ORIGIN']==('http://175.178.160.158:8001' if platform=='android' else 'http://175.178.160.158')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def post(route,body):
        req=urllib.request.Request(const['ORIGIN']+route,data=json.dumps(body).encode(),headers={'Content-Type':'application/json'},method='POST')
        with opener.open(req,timeout=10) as r:return json.load(r)
    c=post('/client-admission/challenge',{'protocol':1,'build':const['ID'],'platform':platform})
    assert c.get('ok') is True, 'Public challenge rejected the currently allowed build'
    d=c['data'];message=prefix+d['challenge'].encode()+b'\n'+d['nonce'].encode()
    proof=hmac.new(bytes.fromhex(const['KEY']),message,hashlib.sha256).hexdigest()
    result=post('/client-admission/prove',{'challenge':d['challenge'],'proof':proof})
    assert result.get('ok') is repaired, 'Actual client proof did not match the expected server result'
    if not repaired:assert result.get('code')=='CLIENT_NOT_ALLOWED'
    return {'platform':platform,'artifact':str(artifact),'sha256':fix.sha(artifact.read_bytes()),'build_id':build,'repaired':repaired,
            'proof_prefix_matches_build_id':prefix==expected,'challenge_ok':True,'prove_ok':result.get('ok'),'code':result.get('code'),
            'actual_artifact_constants':True,'account_login_attempted':False}

def main():
    keys=fix.read(MASTER/'config/client-admission.keys.json')
    a=fix.read(fix.OUT/'android-repair.json');i=fix.read(fix.OUT/'ios-repair.json')
    jobs=[(Path(a['source']),'android',False),(Path(a['apk']),'android',True),(Path(i['source']),'ios',False),(Path(i['ipa']),'ios',True)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows=list(pool.map(lambda row:probe(*row,keys),jobs))
    report={'passed':True,'public_protocol_test':True,'real_device_test':False,'server_configuration_changed':False,'admission_ids_and_keys_changed':False,'results':rows}
    fix.dump(fix.OUT/'public-admission-verification.json',report)
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
