# Portable client method contracts

These files contain metadata only. No original method bodies, full ABC data, decompiled source, private receipt, credentials or local input paths are included.

- `android-methods.json`:291 distinct final changed/added bodies, keyed by `(abc_tag, method_info)`, with exact semantic identity, added/changed flags, current header/signature/code hash and prior hash/header where available. The settings274 + tutorial1 + trigger15 + dash1 union was checked for collisions. The four external source-contract hash links are retained in `lineage.json`.
- `ios-repairs.json`: exact17 business and5 support methods,22 AOT targets, wildcard sidecar/accessor contract and preserved platform boundaries. Android and iOS raw code hashes are separate because constant-pool relocation changes instruction operands.
- `CONTRIBUTORS.md`: verified upstream account, PR link and fixed head; no personal email.

Header order is max_stack, local_count, init_scope_depth, max_scope_depth. MethodInfo IDs are carrier-specific and meaningful only with the bound ABC/SWF hashes. `<ctor>`, `<cinit>` and `script:.../<init>` identities are explicitly classified; script initializers are not represented as ordinary QName method traits.

Signatures retain return/parameter types, flags and optional constants. Debug method names and parameter-name strings are omitted from this minimal contract and must remain unchanged when reusing an existing MethodInfo. The first274 rows retain their normalized body/exception hash where available; later rows explicitly leave unavailable whole-body digests null rather than inventing them. This is a verification/input contract, not source sufficient to reconstruct a method from hashes.

The final Android SWF hash and iOS IPA/native hashes identify external retained carriers. Actual package/AIR/compiled-ABI evidence is preserved outside Git. Offline ABI verification does not mean iOS native methods or gameplay were executed. Contract extraction used PowerShell JSON/hash operations only; it did not start engineering processes or modify other modules.

Original instance/static storage layouts remain protected. The iOS ledger is `*`/type0 with declared undefined default, stored in a unique new class and exposed through two old-owner method traits. Runtime observation of the initialized Atom value is not claimed. Existing334 compiled functions and draw/scale/resolver wrapper chains remain preservation requirements.
