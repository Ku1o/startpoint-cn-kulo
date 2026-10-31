# Content operations, clocks and town themes

The authenticated management panel controls seasonal participation independently of the server clock. Operators can open reviewed activities, gacha pools and associated exchanges immediately, optionally set an end time, and close them without changing business time. The fixed 2025-07-20 UTC+8 reference selects the initial reviewed configuration; it is not the current server date or a repeating activation schedule.

## Publication and player refresh

`ContentOperationsStore` persists original instance IDs, per-action evidence/readiness, exact quest/mission scopes, revisions and audit reasons. Visibility, entry, claims and exchanges are separate permissions. No end time means no operations deadline; it does not grant a permission. Expiry closes the affected action even when a browser or client holds an older snapshot.

The management page groups native game names with authenticated thumbnails, series, character/reward search, filters and local favorites. Date sorting follows the selected date order. Publication switches require confirmation, and concurrent edits use revision/catalog checks. Details explain unavailable content and retained rights.

Publication does not change the clock or automatically disconnect players. The separate confirmed full-client-reload operation persists a new epoch and disconnects eligible sessions so the next login loads the configuration. Battle-protection records are captured before publication; an existing committed battle is not discarded when new participation closes. Failed realtime disconnection has an explicit retry path.

Compatible clients consume authenticated snapshots through the native pages. Existing native time fields can show the configured deadline or permanent availability. Pages without a time field do not receive an unconditional new label. The client does not give players a new activity-period control.

## Authorization and earned progress

Final writes revalidate permissions inside their persistence transaction. Earlier pages, queued requests and room preparations are not authorization. Missing, corrupt, expired or unknown seasonal controls cannot fall back to calendar auto-opening. Changed definitions or source identities block activation until reviewed. Core quests and established permanent products/missions retain explicit existing policies.

Closing and reopening one instance preserves inventory, progress, purchases and claim markers; it does not begin a new reward cycle. Historical passes and boxes keep separately qualified claims and saved exchanges. Saved box progress alone grants no new draw/reset/close. Parent activities and associated boxes/exchanges use explicit associations and atomic publication checks.

Historical adapters preserve the native product and quest fields consumed by the server, including prices, rewards, eligibility, fixed parties, stamina, limits and uniqueness. The added historical challenge limits charge after successful clears and allow failure retries; existing single-challenge rules remain. Rescue-request weekly objectives across 19 passes count completed rescue battles. The Everyone Picks participation objective completes after successful final character redemption.

Daily/weekly maintenance preserves existing progress and received stages. Closed tasks create no new fact baselines; claim-only paths use saved progress. Daily shop quotas retain lifetime totals. Old totals without dates conservatively reserve the explicit cutover's first business-day quota; the next 05:00 UTC+8 bucket starts normally. Missing cutover anchors grant no inferred policy.

Known limits stay explicit: return-training qualification is not invented; five Stars and five return-specific personal pools gain no new draw qualification. Existing progress/exchanges remain compatible. Their 604 star-fragment product IDs currently duplicate the restored ordinary scope at the same character versions, prices and rewards; ownership checks reject both directions of duplicate purchase. Revisit that comparison if products diverge. The nine deferred Deep Abyss exchange items gain no new drop sources.

## Real clock and saves

Persistent clock state restores before login maintenance and synchronizes with the SQLite writer and leaderboard worker. Real business time and the preserved legacy-battle coordinate are separate. Saved field provenance determines EXP/timestamp interpretation; offsets are not guessed or globally applied. Management clock-edit routes are retired.

Clock activation, rehearsal and rollback are explicit offline operations. Guards inspect the current Git worktree inventory, resolved aliases, attachments, temporary shadows and hard links before a write. A new checkout does not authorize a live database cutover. Rollback checks include complete affected state and reject blind reversal after newer progress.

Management save uploads retain V2 validation. Column-order-compatible archives preserve exact structured fingerprint checks; malformed archives fail before replacement. Internal V1 replacement is a separate compatibility path. Imports, automatic pre-import backups and rollback preserve destination identity, other players and explicitly classified server-local state. A player snapshot is not a whole-server backup.

## Town themes and music

The panel displays original dated theme periods and allows separately configured annual start/end dates, including year-end crossings in UTC+8. Automatic following uses those configured rules with an explicit fallback; historical dated periods are not guessed into yearly recurrences.

Manual changes and automatic transitions use the same theme protocol. A published selection contains its corresponding music and revision so compatible clients follow them together. Players can subsequently choose music through existing behavior. Future themes/music must register native identifiers, actual resources and supported client catalog entries; a panel label cannot add missing game/audio assets.

## Runtime indexes and administrative cost

Complete catalog, definition/readiness evidence and native rules remain available. Compact runtime summaries are deterministic, bounded projections with strict source identities and coverage checks. They reduce repeated administrative allocation without removing gameplay checks or silently falling back to an unbounded full-report parse.

The native identity index preserves original full keys, digests and order. Business adapters still read complete shop and quest rules. Source anchors bind actual original bytes, including deliberately preserved line endings. Source changes require explicit regeneration and verification, never automatic re-signing in a management GET.

Administrative reads use bounded shared work, scoped captures and compact card projections. Matching requests can share one result while cancellation and queue limits remain bounded. Prepared search identities compare actual used fields. This adds no new worker or replacement gameplay scheduler. Withdrawn cold-field compression, cards decode-cache and later cooperative-scan experiments are excluded.

The wider panel loads pages/lists on demand, paginates accounts/seeds, separates player-detail sections and caches suitable static status/lookups. Authentication recovery and edit guards preserve drafts/pending actions. News HTML checks run on the server as well as in the editor. Frontend builds include gzip/Brotli sidecars; player data is not public cache content.

## Explicit 350 release supplement

The Halloween supplement is separate from the original fixed-July initialization.
It does not rewrite initialization, deployment or reward-box markers, and does not
replay the old migration. Persistent real time must already be active. The terminal
`assets/asset-patch/manifest.json` must be 1.4.350; the catalog's original master
export is a separate identity and can remain older.
The original reviewed 9599-key set must remain complete before preview/application
and during later verification; a new receipt cannot absorb missing old controls.

The exact new scope is `advent_event:300097`, its 31 reviewed products
`9730001, 9730007, 9730008, 9730010, 9730011, 9730101–9730126`, the parent entry's
ten quest members `7/8:300097001–300097005`, and `gacha:990005`. Quest members are
scopes, not additional control rows. Omitted products and other events are not
added. New products receive reviewed visible/exchange actions, with no `published`
field. The new pool receives visible/enter and an explicit disabled exchange;
existing pool rights are preserved. No claim action, inventory, stock, player
progress, town or clock change belongs to this supplement.

Every existing control takes precedence, including unverified/disabled actions,
manual publication closes, finite or expired deadlines, instances and custom
member scopes. Preview lists their saved settings and observed effective flags,
even when closed. Application does not promise that all content is open. A receipt
means the migration was applied and identities match; later operator changes
remain authoritative. Existing unsupported publication markers require a separate
reviewed repair and are not silently removed here.

Build the final source and dependent indexes before preparing a target plan:

```powershell
node tools/prepare-content-release.cjs --database <physical-target-file> --output <new-local-plan.json> --evidence <review-sha256> --previous-source <pinned-old-source-root>
node scripts/time-content-deployment.cjs preview --project <service-root> --supplement <local-plan.json> --plan-digest <reviewed-plan-digest>
node scripts/time-content-deployment.cjs apply --project <service-root> --supplement <local-plan.json> --plan-digest <reviewed-plan-digest>
node scripts/time-content-deployment.cjs verify --project <service-root>
node scripts/time-content-deployment.cjs release --project <service-root>
```

Preview opens only the explicit database read-only. Apply reuses strict stopped
process/port checks, maintenance locks, SQLite backup verification, the exclusive
transaction and recovery journal. It keeps the service stopped until normal
verify/release completes. A changed target requires a fresh preview. Do not invoke
the ordinary initialization Apply as a substitute for explicit supplement args.

When persisted identities are old, `--previous-source` must name a fixed read-only
old program/resource tree whose computed identities match the saved controls.
`tools/content-release-capture.cjs` is the actual producer. It loads old/current
programs with separate module caches, blocks database/process/write access, and
calls their real effective shop, quest/clear/score/rare reward, gacha/payment,
mission, pass, box and exchange accessors. Parent shop-definition evidence is
always augmented with actual quest/reward closure. Captures include the complete
exported payment/execution matrix plus actual gacha
campaign assignment, including null. Missing payment support is a pending review,
not an assumed fallback. The preview domain import blocks the default database
module/initializer so it cannot implicitly create a default data directory.
The producer hashes itself
and the source inputs read; archives use the existing bounded member parser and
change detection, never whole-archive reads. Compiled `out/` accessors are used
when present. Source-only archives additionally need the existing TypeScript
toolchain; this does not authorize installing it on a target.

The plan embeds the produced old/current captures. Application re-captures both
program trees inside the maintenance transaction and compares them with the plan
and current store. External capture JSON is not an accepted input. Equal declared
hashes, omitted prices/rewards or an arbitrary capture-engine SHA cannot replace
actual accessors. Unsupported types or unresolved source/resource differences
are rejected and listed for review. Business fields, dependencies, capabilities
and members must compare exactly. Keep the fixed old program/resources available
through application; a successful receipt allows later verify/idempotent no-op
without reopening the old tree. Local plans use compact JSON with a 40 MiB limit:
the actual 9599-control preview required 35,251,205 bytes. This file-size allowance
does not change process memory budgets. The companion `.summary.json` contains the
review digest, counts and preserved settings without loading the complete plan.

The read-only old tree may be sparse: missing pristine/active ZIPs resolve only
through the current service's retained immutable archive chain. Program files and
master JSON never fall back to current bytes. Existing advent parents compare
their exact owned raw quest rows plus actual quest/reward/rare outputs; unrelated
new rows elsewhere in the shared table do not alter their identity evidence.
The two adopted 990001/990002 pool edits and the three default-closed Rush shop
additions have exact old/current getter or mapping hash pairs. Prices, unrelated
pool edits, payment/campaign rules and any other changed dependencies are rejected.

Identity-only writes change just catalog/content identities and revision, append
audits, and preserve all other saved fields. Player tables and old audits are
checked before and after. The durable receipt prevents replay: repeating the same
plan after player progress or later operator closes performs no business writes.
Target plans, backups, captures and logs remain private local maintenance material
and must not enter Git or player downloads. Synthetic tests do not establish
cloud adaptation or device acceptance.

## Build, verification and release

Build from the final integrated source and regenerate dependent indexes with the committed generators. Definition/native/runtime-index tools provide deterministic checks. Discovery fragments/merge bind the actual source tools. Offline image export/thumbnail generation preserve originals and reject protected source/CDN outputs.

Compile with `node node_modules/typescript/bin/tsc --incremental false` and build admin using its package scripts. Full application verification through `tools/isolated-content-runtime.cjs --root <dedicated-fixture-root> --verify` requires a root outside registered checkouts. It uses nonempty synthetic state, actual routes and guarded writer/normal-startup paths, not production data.

Original comparison tests ship five necessary hash-bound server modules in `tests/fixtures/content-original-oracles`. The archived product HTTP-proof comparison additionally requires `STARPOINT_PRODUCT_PROOF_ARCHIVE` with original complete source identities/logs. Set `STARPOINT_PRODUCT_PROOF_ORIGINALS` to a read-only root of the 19 frozen sources when current checkout bytes differ; every original hash remains mandatory. Without the archive only that comparison is explicitly skipped; synthetic scope/source/log contract checks still run. Synthetic checks are not historical HTTP or device acceptance.

Source integration, runtime adoption, client acceptance, cloud packaging and deployment are separate steps. Tests do not establish every activity's phone behavior, cloud capacity or production migration. A separately authorized deployment needs current consistent backups and checks of actual schema/progress/revisions/pending accounting. Never include private configuration, credentials, local reports, fixtures or player databases as production state.
