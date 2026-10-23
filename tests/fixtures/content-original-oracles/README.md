# Original server-source comparison fixtures

These five exact server-source preimages preserve the implementations used before discovery prepared caching, scoped management-page captures, and management snapshot reads. They are independent comparison inputs, not copies of the implementation being tested. `manifest.json` binds their exact bytes. Tests transpile only the necessary original modules and use controlled data/readiness/discovery dependencies; no full runtime tree, resource archive, database, or local task report is included.

The separate archived product HTTP-proof test requires `STARPOINT_PRODUCT_PROOF_ARCHIVE`. That archive includes original complete source identities and HTTP logs and is intentionally not replaced by reduced or re-signed evidence. Without it, only that archival test is skipped explicitly; standalone synthetic proof-contract checks continue to run.
