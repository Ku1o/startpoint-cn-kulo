# Android adopted source and tests

The six sibling groups carry163/tutorial/trigger9000/dash/packaging/test-support are an overlay for a complete repository checkout. They depend on the release's `release_config.py`, `android/capabilities`, `android/upstream`, and the repository's existing native importer/packaging sources. They contain no compiled client, SDK, credentials, full official decompilation, generated attempt/src or local execution receipts.

Private inputs and outputs

Merge `INPUTS.example.json` into an untracked `SP_CLIENT_INPUTS` JSON. Shared roles are under `android.inputs.<role>={path,sha256}`; paths resolve relative to the private JSON. Every adopted carrier and fixture is pinned again in `input-hashes.json`. `work_dir` is external to the checkout; all generated source, logs, SWF/ABC/SWC/APK and receipts go under its `android` child. `air_config` contains the existing `sdk` and `java` fields, both absolute existing private paths. No environment installation or fallback runtime is selected. No SDK is copied here.

`abc_tools.py` is the exact original handwritten test loader snapshot. It configures the repository-relative `client-patch/lens0907-0908/build_swf.py` and normal importer dependencies. The carrier binaries, native declaration metadata and SDK remain external inputs. Actual production methods are grafted and read back with code/exceptions, MethodInfo flags/defaults, stack/locals/scope and activation checks. That is distinct from executing every imported method and from a full game/device test.

Support is reused from `../settings/support` and `client-patch/pr43-port/support`; identical framework/checker files are not copied twice. `capability_module()` temporarily binds the capabilities bootstrap when loading its generic modules to prevent a calling group's `bootstrap` from being mistaken for the capabilities output/input boundary. This new loader adapter still requires a separately scheduled syntax/import check in a complete merged checkout.

Execution recipes after slot allocation

Never run these commands during a read-only/paused stage. All interpreter/compiler/AIR descendants require the existing outer Windows Job wrapper, at most1536MiB/180seconds, with a fresh external receipt. Compiler/AIR additionally use the existing background wrapper. `$Python`, `$Bounded`, `$Background`, `$Repo`, `$Work` must be private configured existing paths. Keep stages serial and stop on the first failed phase. Do not package just to validate source.

```powershell
$Android = Join-Path $Repo 'client-patch/release-20261031/android'
# Source-only check, no business imports or binary reads: 512MiB/60seconds.
& $Python -B $Bounded --limit-mib 512 --timeout 60 --cwd $Repo --receipt (Join-Path $Work 'android-source-job.json') -- $Python -B (Join-Path $Android 'test-support/check_source.py') --repository $Repo --output (Join-Path $Work 'android-source.json')
# Example core HP phase; repeat for prepare, compile, graft, before, after separately.
& $Python -B $Bounded --limit-mib 1536 --timeout 180 --cwd $Repo --receipt (Join-Path $Work 'hp-prepare-job.json') -- $Python -B $Background --timeout 165 --cwd $Repo -- $Python -B (Join-Path $Android 'trigger9000/regression/prepare_native.py') --attempt core01
& $Python -B $Bounded --limit-mib 1536 --timeout 180 --cwd $Repo --receipt (Join-Path $Work 'hp-compile-job.json') -- $Python -B $Background --timeout 165 --cwd $Repo -- $Python -B (Join-Path $Android 'trigger9000/regression/run.py') compile --attempt core01
```

The Stage0 continuation uses the same runner with `graft`, `before`, `after`. The independent lifecycle increment is `prepare_native.py --attempt life01 --lifecycle`, then compile/graft/after only. It does not need to rerun core62 merely for report creation. The current source adaptation has executed none of these phases.

See each group's README and small `contract.json` for adopted behavior, exact before/after inputs and preserved boundaries. Historical test counts describe the original source/input runs. They do not certify this relocated adapter, a new compiled candidate, iOS IDs/AOT/Atom ABI, full device behavior, registry acceptance or deployment. No cleanup of old evidence or candidates is included.

Upstream reference: [@kuronzzhan-droid](https://github.com/kuronzzhan-droid), [PR106](https://github.com/Ku1o/startpoint-cn-kulo/pull/106) at5f70aec391c011f8d3066d41021fe06f27c07f84. Repository attribution and licenses remain applicable.
