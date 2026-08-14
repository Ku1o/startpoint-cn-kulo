# Private repository notes

This repository is a clean snapshot of the currently maintained private server code.

## Upstream references

- Original baseline: `https://github.com/dontbealarmed/startpoint-cn`
- Mode/content reference: `https://github.com/kuronzzhan-droid/startpoint-cn`

The repository history is based on the original upstream baseline. The current server state is imported as one reviewable snapshot commit; historical chat/task transcripts are intentionally not included.

## Local-only data

Runtime and sensitive data are deliberately excluded from Git, including:

- `.env` and local credentials;
- SQLite databases, player saves and migration backups;
- logs, caches, `node_modules` and build output;
- APKs, signing keys and generated release work directories;
- native `.cdn` data and local MOD production directories.

Create a local `.env` from `.env.example`, then install dependencies and build normally.

Client incremental patches that are part of the maintained server release chain remain under `assets/asset-patch/active` with their manifest.
