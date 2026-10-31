# Later cumulative iOS repair sources

The three later repairs are retained in separate source directories:

1. [Dispatch repair](../../release1031-ios-dispatch-fix-20261031/README.md): move the 25 reviewed instance helpers into an append-only static helper class, retain the old class/field layout and recompile the audited caller closure.
2. [Battle F1069 repair](../../release1031-ios-battle-f1069-fix-20261031/README.md): append the real `getTotalDashParameter(index:int):Number` getter and bind its native function.
3. [Independent party repair](../../release1031-ios-independent-party-fix-20261031/README.md): bind three original native entries to their existing independent-party ABC bodies.

Each source manifest records the adopted source hash and the pre-relocation source hash. Machine paths and source lookup wiring are adapted; gameplay bodies and native algorithms retain the adopted implementation. The dispatch unwind plan pins the relocated algorithm source and retains its original source hash. No package, SDK, private receipt, compiled object or original game decompilation is included.

## Private inputs

Merge `followups-inputs.example.json` into the existing `SP_CLIENT_INPUTS` configuration described by [inputs.example.json](inputs.example.json). Existing `libraries`, SDK, dependency, runtime stub and cumulative input roles remain required by the shared adapters. New receipt roles require an explicit SHA-256. `followup_party_input_record` is a frozen F1069 registration snapshot, not the mutable current `ios-accepted.json`; the preparation stage also checks its IPA and complete ABC identities.

The historical artifact graph is expected below `work_dir/ios/followups/`, retaining these data-only directory names: `revision-settings/ios`, `revision-ios-acceptance-repairs`, `revision-public-admission-20261031`, `revision-ios-dispatch-fix-20261031`, `revision-ios-battle-f1069-fix-20261031`, and `lite195/input/r11.swf`. Their JSON links must refer to the corresponding retained artifacts. Use [report_rebind.py](report_rebind.py) for declared report/artifact mappings; do not substitute an old payload just to satisfy a path. New output names must be fresh. Python scripts, grouped linker, finalizer, signing models and the bounded guard are always loaded from repository sources, never from those artifact directories.

## Stage entry and evidence

Run each stage in a separately allocated Windows Job of at most 1536 MiB and 180 seconds, using `support/process/run_bounded.py`; compiler/ADL stages also use `support/process/run_background.py`. These retain the cumulative recipe's shared mutex and background-desktop requirements. The recipes do not allocate an engineering slot or install dependencies.

Dispatch stages are `prepare/relocate_helpers.py`, `native/run_stage.py` (`compile`, `link`, `finalize`, `package`), and `verify/verify_final.py`. Audit scripts retain the exact body-availability and caller-selection logic. Battle stages are `prepare/prepare_getter.py`, `prepare/air_getter_fixture.py`, `native/run_stage.py` and `verify/verify_final.py`. Independent-party stages are `prepare.py`, `native_stage.py` (`compile`, `link`, `finalize`), the dedicated native-only `package.py`, `verify_final.py`, `verify_abi.py` and `air_fixture.py`. Use each entry's argument parser and the retained local stage reports for the exact frozen invocation. Independent-party packaging uses `package.py`, which preserves every non-native compressed member.

Relocated source imports, syntax, manifests and dependency selection can be checked without AOT or package creation using `check_followup_sources.py`. These checks do not replay the full report graph or establish a newly rebuilt IPA. Historical compiler/native/AIR results apply to their original exact inputs and package identities; source relocation is separate evidence. Recompiled source-dependent reports, including signing model source hashes, must be regenerated rather than relabeling old receipts.

The registered independent-party IPA is unsigned and accepted offline only. iOS native execution, re-signing, installation, public login and device battle retests remain pending. The measured 2,114,521-byte IPA increase from F1069 is retained as a known size issue; this source export does not rebuild or slim the IPA.
