# iOS startup CDN download gate

This patch repairs the iOS `GlobalLoading.applyLoad` AOT path used when the
asset read kind is CDN (`2`). The local downloader state remains authoritative:
`isDownloaded(version)` still decides whether the normal download-choice path
is entered, and `isAssetComplete()` still decides whether recovery is needed.
The two `needsDownloadAsset()` results are discarded only at this loading
entrypoint, so an install with no local CDN state can reach the existing
download flow even when the tutorial state has not been advanced yet.

Non-CDN read kinds, full-package handling, download choice construction,
resume/recovery callbacks, loading completion, admission data, and the
previous Boss AOT methods are preserved.

The native repair is deliberately bounded to two ARM64 conditional branches
in method `41998` (`GlobalLoading.applyLoad`):

| virtual address | original | replacement |
| --- | --- | --- |
| `0x105376f68` | `cbz w0, 0x10537727c` | `nop` |
| `0x105377300` | `cbz w0, 0x1053773a4` | `nop` |

`prepare_full_abc.py` records the same semantic change in the complete
compiler ABC. `build_candidate.py` updates the AOT SHA-1 identity and the
embedded SWF identity, then packages only the native executable and main SWF
as changed IPA members. The scripts do not sign, install, deploy, or modify
the cloud server.

Static verification must cover the full ABC method count, runtime ABC and
AOT method-table preservation, exact native byte ranges, SWF identity,
LINKEDIT/ldid signature-tail layout, and the existing IPA bundle identity.
Physical iOS execution remains a separate acceptance step.
