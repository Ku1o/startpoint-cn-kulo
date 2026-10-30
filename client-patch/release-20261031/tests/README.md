# Source-stage checks

Run each check in a separately allocated Windows Job of at most 512 MiB and 60 seconds, using the existing coordinator launcher and serial mutex. The scripts do not acquire a resource slot. Keep Python bytecode writing disabled with `-B` and do not use optimization (`-O`). No third-party dependency is needed.

`check_source_stage.py` accepts `--candidate` as either the sparse overlay's repository root or its `client-patch/release-20261031` directory. `--repository` is the existing complete source checkout, read-only. It parses candidate Python AST and strict JSON; refuses binary client/tool payloads, key files/private-key blocks, personal machine paths, chat links, symlinks/junctions and unexpected non-source files; verifies selected settings/iOS source manifests and their small repository source dependencies. It never opens an SDK, IPA, SWF, ABC, AOT object or native carrier.

Use `--modules settings ios shared` for a frozen partial candidate. Only the named source directories, shared loader and these tests are scanned in this mode. Use `--modules all` only after every source owner freezes their candidate. The checker does not generate or update a whole-tree manifest. Its report states which groups were checked.

`test_release_config.py` imports only the shared loader and selected settings/iOS private-loader wrappers. Small temporary text and JSON fixtures verify relative path resolution, `{path, sha256}` roles, the separate `air_tools.path`/`files` structure, correct work namespaces, hash rejection, missing/malformed configuration, path traversal and existing-output rejection. Fixtures stay under the external report parent and are removed. It does not import build modules or generic repository dependencies, and cannot establish that the sparse overlay is a complete checkout. The settings loader resolves outer role paths relative to the private JSON; its nested AIR runtime `sdk`/`java` still require the existing absolute values. The iOS loader deliberately requires absolute private role/work paths.

Example after the coordinator grants a slot (variables must already contain explicit paths):

```powershell
$Check = Join-Path $Candidate 'client-patch/release-20261031/tests/check_source_stage.py'
& $Python -B $Bounded --limit-mib 512 --timeout 60 --cwd $Task --receipt $FreshReceipt -- `
    $Python -B $Check --candidate $Candidate --repository $Repository `
    --modules settings ios shared --output $FreshExternalReport
```

The standalone loader test uses the same arguments plus `--modules settings ios`; it need not be repeated when the combined source checker has already run that suite. `--output` is mandatory, must have an existing parent outside both candidate and real repository, and refuses an existing file. A failed check writes a fresh failure report then exits nonzero; no retry or resource increase is automatic.

`check_android_source.py` uses the same explicit `--candidate`, `--repository` and `--output` arguments. It separately verifies the Android source manifests, pinned upstream closure, narrow instruction/helper contracts and frozen group order. Its tiny import fixtures guard against carrier reads and subprocesses; only the selected editor/composition/framework APIs are imported, without constructing a SWF editor or invoking a business patch.

`../ios/report_rebind.py --self-test --repository <read-only-checkout> --output <fresh-external-JSON>` runs synthetic report-path and protected-value controls. See `../ios/REPORT-REBIND.md`; it does not replay the real private report graph.

Keep execution status and measured budgets in external task receipts. This budget covers syntax, small source/configuration contracts, import fixtures and source hashes, not full carrier reconstruction. It does not run AIR, AOT, linking, signing, packaging, device tests, deployment, Git or registration changes. Static source checks and small loader contracts do not replace future complete-checkout imports, deterministic reconstruction or business/runtime validation.
