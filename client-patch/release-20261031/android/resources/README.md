# Read-only embedded resource evidence recipes

These three adopted tools do not inject or replace a resource in an APK, IPA, SWF or ZIP. They only read resources and write offline JSON reports. They are repeatable validation recipes, not an omitted packaging step. The original cumulative baseline already carried all 67 required payloads; the proof compared the Android embedded bundle with iOS bundled assets. Later native/SWF-only client packaging preserves those unrelated ZIP members.

Adopted sources:
- `verify_bundle_dependencies.py`: salted logical path, strict raw-deflate AMF3 consumption, stored-PNG decoding and pixel identity, bounded nested orderedmap decoding, duplicate ZIP-member rejection and actual platform parity. The original 67 inputs comprise three orderedmaps, 49 AMF3 assets and 15 stored PNGs. Strict decoder bodies are unchanged.
- `bind_final_bundle67.py`: actual final carrier hashes and embedded bundle SHA1/SHA256, all 67 actual payload bytes and required hashes, plus exact prior decoder-evidence reuse only for identical data. It does not rerun a decoder or establish GPU/gameplay validity.
- `bind_frozen_resources.py`: eight shared table winners against a historical frozen resource chain, and the original small 67 input contract. It retains the exact 1.4.344 manifest guard; current resource targets must not be substituted.
- `resource_inputs.py`: `SP_CLIENT_INPUTS.android.resources`, repository-relative source imports and fresh `work_dir/android/resources` reports. No registry, historical carrier default, local task script, signing material or external handwritten build source is selected.

`bundle67.json` contains only logical paths, archive members, hashes, lengths and count. It was extracted from the matching baseline/final small records and compared with the original 67 contract. `shared-inputs344.json` contains eight historical logical winners, archive basenames and hashes, without machine paths or receipts. `contract-hashes.json` pins both data files. Original source SHA and adapted source SHA are separate in `SOURCE-LINEAGE.json`.

Private data roles

Merge `INPUTS.example.json` into the ignored private configuration. Relative paths resolve from that JSON through the shared loader. Carriers, archive directories and small original metadata stay external; no ZIP/PNG/ABC/SWF/APK/IPA/SDK or private execution report is included here. Current carrier paths/hashes may be supplied explicitly on the CLI; omitted baseline paths come only from explicit private roles, never an accepted registry.

`baseline_decoder_report`, `frozen_binding`, `bundle67_source_contract` and `shared_resolution` preserve the adopted small-evidence hash chain. Their original absolute archive/contract strings are not used to open files: explicit input roles select the actual small contract; shared archive selection uses its basename beneath `baseline_active_dir`. These private reports are read as data, not copied to Git or treated as source. The two active archive-directory roles are read-only; member counts/sizes and selected winning payload hashes are checked. Original binder semantics do not rehash every full resource ZIP; no full resource-chain scan is implied.

The historical `frozen_resource` and `frozen_manifest` roles must describe 1.4.344 with manifest SHA `ebbd881d0170bcf7295c032fb48be12308f7eb50c9b1c1bb20e1df7f4ce347e2`. The current mutable freeze was observed at a later target during source preparation, so it is deliberately not a valid replacement. Availability of the original historical freeze JSON at a new private location has not been established. This prevents replaying the optional historical binder until a matching private record is supplied; it does not require modifying or rebuilding any carrier.

Repository dependencies are the unchanged `tools/fantasy-gauntlet-mod-tools/{wf_mod_tool,wf_assets,wf_character_requirements}.py`, individually pinned in `REPOSITORY-DEPENDENCIES.json`. The strict PNG verifier uses the existing Pillow environment; no new dependency is installed. Overlay these files into a complete checkout; a sparse source overlay is not a runnable replacement for that checkout.

Commands after a separately allocated bounded Job

Set `$Resources` to `client-patch/release-20261031/android/resources` in the complete checkout. Each invocation below must be wrapped in the existing approved Windows Job launcher; a full-carrier proof may require the established 1536 MiB/180 second budget. The 512 MiB/60 second source check is only for AST/JSON/small loader contracts, not these payload reads. No automatic retry or budget increase is permitted.

```powershell
& $Python -B $Bounded --limit-mib 1536 --timeout 180 --cwd $Task --receipt $FreshReceipt -- `
    $Python -B (Join-Path $Resources 'verify_bundle_dependencies.py') `
    --android $Android --android-sha256 $AndroidSha --ios $Ios --ios-sha256 $IosSha `
    --stage final_candidate --output $FreshExternalReport
```

For historical shared-table binding, invoke `bind_frozen_resources.py --output <fresh work_dir/android/resources JSON>` with the matching 344 private roles. For final same-byte reuse, invoke `bind_final_bundle67.py --android <APK> --android-sha256 <SHA> --ios <IPA> --ios-sha256 <SHA> --output <fresh JSON>` under a separate bounded Job with the pinned decoder/binding inputs.

Validation boundary

Only PowerShell source preparation, exact original/adapted source hashes, 67 data-row comparisons, eight shared-hash comparisons and repository dependency hashes were checked for this relocation. No Python import, decoder run, carrier readback, AOT, packaging, registry, upload or device operation was executed. Earlier offline evidence belongs to its exact original inputs; this source adaptation is unexecuted. Complete gameplay closure, GPU behavior and current CDN terminal winner semantics are not established by these tools.
