# Revision3 settings source

This directory contains the adopted implementation and its narrow validation recipes. Overlay `client-patch/release-20261031/settings` onto a complete source checkout alongside `release_config.py`; this directory alone is not a checkout. It does not contain or produce an APK/IPA, signatures or an accepted-registry update.

`ui/patch.py::build(editor)` installs the Boolean preference on the existing `ApplicationOptionLogic.applicationOption` object, uses the unchanged native `store()`, registers kind18 in the original owning script, and adds the row to the existing settings scene. A missing/non-Boolean value means visible. No second preference cache or settings file is introduced.

`render/patch.py::build(editor)` adds one stateless `cnTeammateEffectsVisibleFromBattle(Battle)` reader. It uses the real `battle.gear.absorb(GlobalLogic,null)` and public native `_getApplicationOption()` then the shared raw reader. Missing native context remains an error. P1/P2/P2b/P3/P4 use the common switch; visible retains every native setting and branch. P2 preserves all of `Battle.preparation` and gates the actual multiball reader dynamically. P5 remains independent of the teammate switch, including the original RNG draw. There is no in-battle settings route or reconstruction/replay of prior effects.

`degree_retraction.py` verifies the complete native R11 `EventItemExchangeShopScene/buttonClicked` and `ShopProductBuyDialog/beforePrepare` records and MethodInfo. It rejects any `cnDegreeShopId` string. `restore_native_shops(editor)` offers only exact two-body restoration when native MethodInfo layout still matches; it deliberately refuses an old helper-bearing core. Assembly starts from the explicit no-degree/no-old195 core+carry, then UI, then the revised render group. Historical degree/old195 groups and whole-package builders are excluded. Server degree grant semantics are not altered by this client source.

Private inputs

Copy `INPUTS.example.json` to an untracked private location and set `SP_CLIENT_INPUTS` to that file. Paths are relative to the private JSON. Do not commit private settings, SDK/runtime paths or binary inputs. Every input uses a full SHA-256. `settings.air_config` is a private JSON with the existing `sdk` and `java` fields. `settings.air_tools` pins the existing `lib/abc_tools.py`; that importer resolves the already-repository-owned `client-patch/lens0907-0908/build_swf.py` and its normal dependencies. No new package is installed.

The original source ZIP is a private, hash-guarded fixture input. Only fourteen whitelisted members are read, each independently hashed by `contracts/original-entries.json`. These declarations are fixture compilation inputs; selected production bodies are imported from the actual SWF and read back, rather than rebuilt from a model. No official whole decompilation, SDK, SWF/ABC/AOT or large carrier is included here.

Existing repository support is reused by relative path: `client-patch/pr43-port/support/{abcfmt,bodies,opwalk}.py`, pinned by `contracts/repository-support.json`. The tested differing assembler/SWF support and narrow handwritten editor/checker/anchor code remain in `support/`. Its historical PR195 `build` entry is removed, so this helper cannot accidentally apply the old unconditional module. The UI adapter contains only the required R11 editor surface, not the capabilities group loader.

Commands to validate after a separately allocated engineering slot

The variables below must point to the existing private interpreter, coordinator Windows Job wrapper and background wrapper. Keep stages serial. Use an external `$Work` matching the JSON's `work_dir`. Each example runs under1536MiB/180seconds; compiler/AIR descendants stay inside the same Job and background wrapper.

```powershell
$Settings = Join-Path $Repo 'client-patch/release-20261031/settings'
& $Python -B $Bounded --limit-mib 1536 --timeout 180 --cwd $Repo --receipt (Join-Path $Work 'settings-build-job.json') -- $Python -B (Join-Path $Settings 'build.py') --out (Join-Path $Work 'settings/build')
& $Python -B $Bounded --limit-mib 1536 --timeout 180 --cwd $Repo --receipt (Join-Path $Work 'render-air-job.json') -- $Python -B $Background --timeout 165 --cwd $Repo -- $Python -B (Join-Path $Settings 'render/run_air.py') --out (Join-Path $Work 'settings/render/air') --swf $Candidate --sha $CandidateSha
& $Python -B $Bounded --limit-mib 1536 --timeout 180 --cwd $Repo --receipt (Join-Path $Work 'ui-air-job.json') -- $Python -B $Background --timeout 165 --cwd $Repo -- $Python -B (Join-Path $Settings 'ui/run_air.py') --out (Join-Path $Work 'settings/ui/air15-linked') --real-storage
& $Python -B $Bounded --limit-mib 1536 --timeout 180 --cwd $Repo --receipt (Join-Path $Work 'storage-air-job.json') -- $Python -B $Background --timeout 165 --cwd $Repo -- $Python -B (Join-Path $Settings 'storage-validation/run_air.py') --out (Join-Path $Work 'settings/storage-validation/air')
```

The independent UI cold reader is `storage-validation/run_external_cold.py --harness <compiled storage air directory> --out <fresh work/settings directory> --app-config <work/settings/ui/air15-linked/application.xml> --input-sha256 <frozen application_option SHA> --expected-json <private expected raw JSON> --visible false`. It only accepts the dedicated existing `work_dir/settings/ui/storage-data/air15-linked`, copies the same app descriptor, and locks the source file bytes before/after. Never point this harness at real game settings. Run it under the same Job/background wrappers. Optional original tests are `render/run_controls.py`, `render/test_composition.py`, `ui/run_layout_air.py`; run each in its own bounded/background invocation, not in parallel.

Validation boundary

The original adopted sources previously passed790 render assertions (18 actual methods), four render negative controls, five composition checks,32 linked native UI assertions,362 storage assertions across four separate processes, and107 UI cold-read assertions. Raster checks cover the original embedded font and native text sizing, not the full GPU page. Store tests execute the real native JSON/compression/FileStream/startLoad/apply chain; Gear/transport/notification/diagnostic and GPU boundaries remain finite fixtures. See `contracts/validation-baseline.json` for scope.

The current source relocation has only been read and checked with PowerShell. No Python import/compile, source-relocated SWF build or AIR execution has been performed. Old validation establishes the unchanged adopted business implementation; it does not establish the new adapters or merged checkout. A bounded syntax/import check, deterministic UI/render rebuild and the affected fixture runs remain required before claiming this source candidate is executable. `SOURCE-LINEAGE.json` and `SOURCE-MANIFEST.json` distinguish original bytes from adapted files. All outputs belong outside the checkout; no cleanup of historical candidates/evidence is part of source import.

Upstream reference: [@kuronzzhan-droid](https://github.com/kuronzzhan-droid), [PR106](https://github.com/Ku1o/startpoint-cn-kulo/pull/106) at head5f70aec391c011f8d3066d41021fe06f27c07f84. Repository attribution and licenses remain in force; this source import does not change authorship.
