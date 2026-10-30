# Cumulative iOS source recipe

Gameplay contribution source: [PR106](https://github.com/Ku1o/startpoint-cn-kulo/pull/106), frozen head `5f70aec391c011f8d3066d41021fe06f27c07f84`, Git author account `kuronzzhan-droid`. The adopted iOS portability and later repair recipes are recorded separately in `LINEAGE.json`.

This directory preserves the adopted cumulative iOS recipe and the later acceptance repairs. It is a source integration candidate; source checks do not establish carrier-recipe reconstruction, generic full-checkout imports, or native execution. Specific source-check results belong to external receipts. No package or acceptance registration is included.

`settings/` contains the adopted r3-derived cumulative recipe including HUD Number lowering, static sidecar/accessors, typed equipment resolver clone, exact equipment → five wrapper → typed resolver chain, live-frame draw bridge, scale hook, strict unwind and relocation verification. Its selective R11 preparation produces the settings cumulative carrier with 334 AOT methods. The removed shop presentation patch remains excluded.

`repairs/` consumes that current cumulative carrier and imports 17 business roots (12 existing and five new). The adopted actual build required 22 AOT methods after adding a unique wildcard sidecar's three initialization methods and two old-owner accessors; it did not replace the old 334 objects or apply the R11 equipment patch again. MethodInfo/body indices, old slots, flags, activation, complete bodies versus native return stubs, all active/legacy dispatch entries and wrapper bytes remain guarded.

`capabilities/` retains the original 26-state sidecar algorithm. The later wildcard ledger gets its own `cn.release::AcceptanceRepairsState20261031` storage, type `*`, default undefined and Atom ABI; it never adds storage to an old native class. `support/recipe-deps/` pins the adopted compiler/linker/HUD helpers where the archived file digest differs from the current common source. `REPOSITORY-DEPENDENCIES.json` identifies the unchanged common sources and data used by these recipes. `LINEAGE.json` records original adopted SHA-256 separately from relocated candidate SHA-256; relocated hashes are not presented as hashes used by the earlier package.

## Private inputs

Set `SP_CLIENT_INPUTS` to an ignored private JSON following `inputs.example.json`. Its top-level `work_dir` must be an absolute directory outside the repository. All private iOS keys are under `ios`. The template contains no local file paths, SDK, native bytes, ABC, IPA, build reports, account details or registration contents. `INPUT-PINS.json` supplies immutable known input digests; configurable path strings do not remove those checks. Use the repository-owned `report_rebind.py` and explicit private role map for historical report paths (see `REPORT-REBIND.md`). The adapter writes a new external report DAG and updates only allowed report-file SHA links, preserving all payload/ABI guards and original report hashes. Inspection uses independent full/native/link/package roles rather than an old directory layout. The large real DAG has not been replayed in this source-only stage.

The current repair base is IPA `b38629f65e8506720cc27200b4c87fd51613b78593899c0248a46ffc2e3a9d24`, full ABC `672757b40180eb960dde989b8f659b37cc32229a03a5c903b0bbdc3be6bc814e`, native `7d803626d4cd5debc00cb17b633bbfeec3a9d04ef6b7beed4f068d2e17b6215f`. The current Android donor is pinned to `83fc92d70d7457bb5e4b58d25d97663eeb80367ee366a947f4779a12075ff172`. R11-only preparation separately pins its original carrier. Inputs remain private and are not reconstructed from return stubs or substituted with a whole test client.

Required external tools are the existing Python 3.13 environment with lief/capstone, HARMAN AIR SDK 51.2.1.5, Java, 284 individually pinned ABC dependencies and the pinned runtime stub object. They are not vendored. Actual AOT output/previous object reports are private inputs or new work artifacts, never repository source.

## Controlled entry

After an exclusive engineering slot is allocated, use `invoke.ps1 -Entry <entry> -RunName <fresh-name> -StageArguments <CLI-arguments>`. This dispatches only whitelisted scripts through the included Windows Job and inactive-desktop wrappers. Memory is at most 1536 MiB, wall time at most 180 seconds, inner AOT timeout 165 seconds. A fresh receipt is mandatory; all child processes must be gone before another stage. `Local\Codex_TicketB_BoundedVerification` deliberately remains the original shared mutex. A candidate launcher does not itself grant a resource slot, and it must not replace the current coordinator's launcher during source validation.

Output and generated-artifact arguments must be beneath `work_dir/ios`; existing output is refused except the original pending-link finalization transition. These recipes do not write the repository, old carrier, registry, Git history, or a shared source archive.

Cumulative stages: `settings-prepare` → `settings-contract` → `settings-compile` → `settings-link` → `settings-platform` → `settings-finalize` → `settings-package` → `settings-check`/`settings-abi`/`settings-degree`. The `settings-platform` stage is for the R11-based new cumulative link only. It must not be applied to the already patched settings carrier.

Repair stages: `inspect` → `freeze` → `sidecar` → `prepare` → `native compile` → `native link` → `native finalize` → `native package` → `check` → `atom`. Each script retains its explicit CLI, available through its parser after a slot is allocated. Inspection uses the frozen full ABC plus sparse native reads; no IPA extraction or whole-native hash is required there. The actual-MID map, complete-source recovery for 11 old stubs and wildcard access restrictions gate preparation. Packaging and actual-IPA independent checks remain separate. The immutable generic check may retain Atom pending; a separate hash-bound actual Atom ABI report closes it without rewriting the earlier report.

## Validation boundary

The earlier adopted package was independently verified offline, including old 334 functions, nine protected native ranges, actual linked Atom getter/setter/callsite/lifecycle code, SDK field layout and seven destructive ABI controls. That evidence belongs to its exact previous source and package hashes. Source-check outcomes are recorded in external receipts and do not establish a carrier rebuild. The relocated carrier recipe and complete real report DAG have not been executed. The inherited draw wrapper compact-unwind FRAME limitation remains; new compiled methods' unwind checks do not claim to fix the older wrapper. Offline machine-code checks do not establish iOS device execution or observe the runtime initialized Atom value.

No accepted/admission state, title UI, rift behavior, deployment or package identity is changed by this source preparation.
