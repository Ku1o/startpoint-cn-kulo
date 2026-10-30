"""Read final carriers and reuse strict decoding only for byte-identical payloads."""
from pathlib import Path
import argparse
import hashlib
import io
import json
import zipfile
import resource_inputs as R

ROOT = Path(__file__).resolve().parent


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--android', type=Path, required=True)
    parser.add_argument('--android-sha256', required=True)
    parser.add_argument('--ios', type=Path, required=True)
    parser.add_argument('--ios-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = R.output_path(args.output)
    assert output.is_relative_to(R.cfg.work_path("android/resources")) and not output.exists()
    for path, digest in ((args.android,args.android_sha256),(args.ios,args.ios_sha256)):
        assert path.is_file() and sha(path.read_bytes()) == digest
    evidence = R.input_path('baseline_decoder_report')
    baseline = json.loads(evidence.read_text(encoding='utf-8'))
    assert baseline['status'] == 'all67_actual_platform_bundle_payloads_and_decoders_match'
    assert baseline['count'] == len(baseline['entries']) == 67 and not baseline['unresolved']
    binding = json.loads(R.input_path('frozen_binding').read_text(encoding='utf-8-sig'))
    contract_file = R.input_path('bundle67_source_contract')
    assert sha(contract_file.read_bytes()) == binding['bundle67ContractSha256']
    contract = json.loads(contract_file.read_text(encoding='utf-8'))
    required = {row['logical']:row['sha256'] for row in contract['entries']}
    declared = R.source_contract('bundle67.json')
    assert len(required) == declared['count'] == 67
    assert required == {row['logical']: row['sha256'] for row in declared['entries']}
    assert baseline['androidBundleSha256'] == declared['androidBundleSha256']
    rows = []
    with zipfile.ZipFile(args.android) as apk, zipfile.ZipFile(args.ios) as ipa:
        assert len(ipa.namelist()) == len(set(ipa.namelist()))
        bundle = apk.read('assets/bundle.zip')
        assert apk.read('assets/bundle.zip.sha1').strip().decode() == hashlib.sha1(bundle).hexdigest()
        assert sha(bundle) == baseline['androidBundleSha256']
        with zipfile.ZipFile(io.BytesIO(bundle)) as embedded:
            assert len(embedded.namelist()) == len(set(embedded.namelist()))
            for old in baseline['entries']:
                logical = old['logical']
                assert old['status'] == 'same_platform_bundle_payload'
                left = embedded.read(old['androidMember'])
                right = ipa.read(old['iosMember'])
                digest = sha(left)
                assert left == right and digest == old['androidSha256'] == old['iosSha256'] == required[logical]
                assert old['androidDecoded'] == old['iosDecoded']
                rows.append(dict(logical=logical,androidMember=old['androidMember'],iosMember=old['iosMember'],
                                 sha256=digest,bytes=len(left),strictDecoderEvidenceReusedByExactPayloadHash=True))
    result = dict(status='all67_final_carrier_payloads_exact_and_strict_decode_evidence_reused',stage='final_candidate',
                  androidCarrier=str(args.android.resolve()),androidCarrierSha256=args.android_sha256,
                  iosCarrier=str(args.ios.resolve()),iosCarrierSha256=args.ios_sha256,
                  androidBundleSha256=sha(bundle),count=len(rows),unresolved=[],entries=rows,
                  strictDecoderEvidence=str(evidence),strictDecoderEvidenceSha256=sha(evidence.read_bytes()),
                  requiredContract=str(contract_file),requiredContractSha256=sha(contract_file.read_bytes()),
                  frozenManifestSha256=binding['manifestSha256'],
                  gpuOrDeviceTested=False,finalNativeGameplayValidated=False,
                  interpretation='Actual final APK/IPA and all67 payloads were read. Identical bytes reuse the existing strict AMF/orderedmap/PNG checks; no new decode or gameplay claim.')
    output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:result[key] for key in ('status','count','androidCarrierSha256','iosCarrierSha256')}))


if __name__ == '__main__':
    main()
