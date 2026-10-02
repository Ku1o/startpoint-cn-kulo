# Author 1043 Android integration

The current LAN candidate continues through [`author-unified-damage`](../author-unified-damage/README.md), which removes the legacy GenericDamage classification hooks while preserving this author port. This directory remains the pinned, reproducible integration stage; its original APK is retained for rollback.

This candidate ports the 1.4.1043 character package onto the accepted September 24 Android SET C8601 build. It preserves the accepted account, party, EX, Lens, GenericDamage, startup-cache and earlier MOD changes. The accepted artifact registry is unchanged; device acceptance is pending.

- Accepted APK SHA-256: `f24f469c1be0cb3d2d16520a739ace52b58055ce65621f5243404026beba6066`.
- Accepted SWF SHA-256: `1785d16b430ea7008e7d70cf1bca106f3f5410bbf86566063e83ad856d9a0a49`.
- Donor SWF SHA-256: `b113c90c3bccaf48eb0874512e862213dc91c9221882c061748fbe191478ad5e`.
- Integrated public-endpoint SWF SHA-256: `fce5aabaea98ffa84381de91e936a5adfd5991e955ed0c62fb804b7551c5a10c`.

`build_swf.py` adds ability 423/424 parsing, descriptions and runtime rules. Gauge provenance distinguishes opening and movement charge from restricted skill/ability sources. Damage reclassification includes native PF level and Environment evaluation. A separate local register preserves the existing GenericDamage decorator.

Three donor voice fragments extend Gerald, Tailcoat and Zantetsu ready-voice selection, voice-page lists and battle preloading. Their branch targets and pool references are remapped; the surrounding native methods remain intact. Unrelated donor methods are excluded. There are 29 changed original method bodies and six added helpers; 92,532 original main-ABC bodies and all other ABC tags are preserved.

`rules/baseline.json` locks the exact local method preimages. `rules/port-proof.json` records instruction-level compatibility with the reviewed author rules. The local tests execute generated AVM2 instructions, native PF calculation blocks and serialized final voice fragments, including missing-file fallbacks.

Build with Python 3 and the repository's bundled SWF tools:

```powershell
python -X utf8 -B client-patch/author-content-1043/build_swf.py --source <accepted-public.swf> --donor <reviewed-donor.swf> --output <new-integrated.swf>
$env:STARPOINT_LAN_HOST='<LAN_HOST>'
python -X utf8 -B client-patch/author-content-1043/package_android.py --swf <new-integrated.swf> --work <task-apk-work> --out <delivery-directory>
$env:STARPOINT_RULES_BASE_SWF='<accepted-public.swf>'
$env:STARPOINT_INTEGRATED_SWF='<task-apk-work>/android-lan.swf'
python -X utf8 -B -m unittest discover -s client-patch/author-content-1043/rules/tests -p 'test_*.py'
```

The packager uses the accepted APK, changes nine endpoint strings to `<LAN_HOST>:8001`, allocates a fresh AIR UUID and updates both native identity sites. It checks every other native class and APK member, then validates the persistent signing certificate, v1/v2 signatures, alignment and embedded SWF. The admission ID and key remain paired with the accepted release. No iOS IPA is built.

The paired resource edge is `1.4.116 → 1.4.117`, produced by `tools/author-integration-1043/build_resources.py` from the effective 1.4.116 chain. That builder intentionally rejects a different tail. `verify_resources.py` checks serialized changes, unchanged rows, image roots, voice closure, Inaho enum regressions and exchange flags. The archive retains independent iOS texture pairs as shared resource completeness; these do not constitute an iOS client release.
