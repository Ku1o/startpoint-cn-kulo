# iOS resource closure 1.4.351

The iOS character-detail ability text references two new inline icons that were
present only in the Android tutorial atlas update. Opening that detail page
therefore reaches `ViewAssetContainer.getImage` with an absent subtexture and
raises C8004. The shared atlas image and index are now supplied in `ios_upload`.

The effective-chain review also found three stale iOS cut-ins: both
`land_dragon_wind_playable` variants and `samurai_robot_plum/skill_cutin_0`.
Their winning source PNGs changed after the last iOS payload. Each replacement
is encoded independently as ETC2 RGBA in slot 3 from that winning source;
Android payloads remain byte-for-byte unchanged.

## Scope and evidence

- Incremental edge: 1.4.350 -> 1.4.351; one archive, five iOS-only members.
- Audit coverage: 206 effective custom platform resources: 203 ATF pairs and
  three shared tutorial assets. Replay includes legacy iOS archives and the
  current registered IPA, avoiding false missing-pair reports for older assets.
- Pre-repair audit finds precisely five affected files; the overlay audit
  finds none in this scope.
- Final archive readback validates CRC, unique members, stored PNG format,
  three ETC1/ETC2 pairs with 11 mips each, and all alpha blocks against an
  independent Khronos-derived decoder.
- All 89 existing atlas entries retain their metadata and rendered RGBA
  crops. The new atlas has 91 entries, including `wfx_round_ability_any` and
  `wfx_round_main`.
- Six focused audit regressions and seven independent EAC specification
  tests pass. Offline evidence does not establish iOS native, device, UI or
  cloud acceptance.

## Reproduce the coverage check

```powershell
python -B tools/fantasy-gauntlet-mod-tools/wf_ios_resource_audit.py --server-root <server-root> --report <report.json>
python -B -m unittest discover -s tools/fantasy-gauntlet-mod-tools/tests -p test_ios_resource_audit.py
```

The runtime delivery consists of the new active ZIP and the cumulative
manifest. Existing archives must be retained. There are no server-code,
database, character-stat, APK, IPA or admission changes. Signing, deployment
and device verification are separate operations.
