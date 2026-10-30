# Selected mechanism recipe

This is the adopted transactional R11 patch editor and its selected upstream source closure. It never calls the historical overall build. Each group uses a new editor, explicit input/anchor checks and complete non-target preservation; a failure discards that group's candidate. Unchanged old MethodInfo, pools, declarations and instance layouts remain guarded.

Gameplay source: [PR106](https://github.com/Ku1o/startpoint-cn-kulo/pull/106), head `5f70aec391c011f8d3066d41021fe06f27c07f84`, author account `kuronzzhan-droid`. The selective integration includes reviewed R11-specific compatibility adapters. The upstream snapshot contains only required patch code and small verification dependencies, not the original overall package/build or a decompiled game source tree.

Set `SP_CLIENT_INPUTS` using `INPUTS.example.json`. `r11_swf`, `r11_apk` and the fixed `donor_swf` are private payloads. The R11 APK is streamed against its frozen identity before reading the bundled PFA keys; a mutable accepted-registry pointer or a local validation receipt is not a substitute. All output goes beneath `work_dir/android/capabilities`.

```powershell
& $Python -B (Join-Path $Repo 'client-patch/release-20261031/android/capabilities/port_capabilities.py') --frozen-release-profile --run fresh-rebuild
```

Run that command only inside a separately authorized bounded Job with a sufficient reconstruction budget. The frozen profile uses the46 successful groups in their recorded construction order and checks each output SHA-256. It defers the final `wfxRunDashAction` insertion to the standalone final dash repair to preserve the frozen MethodInfo order. The normal donor selector retains the completeness fix for future compositions. No old163 or old unconditional195 module is adopted.

`../contracts/semantic-preimages.json` contains only21 exact method-level instruction/header contracts used by semantic hash relocation. Full resolved opcode/constant/branch/header equality remains mandatory; a historical hash is never accepted on its own. `helper-instructions.json` contains the two upstream-added custom helper implementations and the exact CT predecessor proof. The CT proof removes only its reviewed eight-instruction prologue and remaps the original branch indices. `leader-display-labels.json` replaces archive filename enumeration with the same explicit fixed-donor method selection. None of these files is an official class export or a broad decompilation archive.

Use `freeze_contract.py`, `verify_guard_board.py`, `verify_materials.py` and `verify_core_pf.py` after a successful external build. They consume generated reports under the external work directory; historical audit outputs are not static Git inputs. The interpreter checks do not establish AIR, GPU/device or iOS execution.

The other repository source dependency is `docs/client-apk-patches-v33/93-fever-items-leading-dsl/source/feveritems_patches.py`; the existing named importer comes from `client-patch/lens0907-0908/build_swf.py` and its pinned normal dependencies. Both are repository-relative. The differing upstream parser/editor sources are retained as narrow snapshots rather than silently replaced with a similarly named version.

This relocation has not rebuilt a carrier. Prior successful build/AIR/package results remain evidence for their original recipes and input identities. Source syntax/configuration checks are a separate verification layer.
