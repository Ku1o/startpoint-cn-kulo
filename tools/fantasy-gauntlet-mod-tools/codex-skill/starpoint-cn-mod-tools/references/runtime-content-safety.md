# Runtime content safety

Use these gates when changing ActionDSL or generating Deep Abyss content. They address failures where data remains parseable but the client interprets it incorrectly at runtime.

## ActionDSL edits

- Resolve the official command/event signature before editing. Record each positional parameter's semantic role, not only its broad value type.
- Declare which 1-based parameter positions the requested patch may change. Reject every undeclared positional change. Identifier parameters must remain stable unless changing that identity is the explicit task.
- Validate the complete edited DSL against official signatures, enums, and static value types, serialize it, read it back, and validate the readback again.
- A value being an integer or number is insufficient evidence. For example, changing an object-ID integer while intending to change a ratio remains a semantic failure.

## Boss and terrain mixing

- Derive terrain requirements from the Boss's actual ActionDSL/ESDL reference closure and run the established compatibility checker for every selected Boss/terrain pair.
- Cover named positions such as `p0`, `p1`, and `p2`, funnel counts, active layers, and slot/group topology. Slot counts or historical allowlists are candidate filters, not runtime compatibility proof.
- Fail closed when evidence is missing. For an unpinned random choice, a verified native-field fallback is acceptable; an explicitly pinned incompatible pair must fail with the exact incompatibility reason.

## Boss quest covers

- Resolve a Boss-floor cover from the actual runtime Boss tuple, never from the terrain donor or copied template.
- Prefer exact Boss-ID tuple equality. Where official single/multi/tower aliases use different IDs for the same visible Boss, match only a stable visual identity that combines the official display name and model root.
- Treat `floor_host_quest` as diagnostic metadata only. It proves that a field belonged to a floor, not that the floor's image depicts the selected Boss. Reject it as final cover evidence.
- Verify that the selected quest thumbnail exists in the effective client-visible asset chain and retain static provenance. Do not call static evidence gameplay or UI verification.

## Boss damage trials (visible red bars)

- Treat a damage trial as a native Boss mechanism, not as a separately scheduled generic floor modifier. Preserve it only when the selected Boss's real state data contains one.
- Recognize the two runtime representations independently: Standard Enemy `au[form].g[state].m` is the Trial union and its `T2` is DamageCheck; General Boss uses `general_boss_state.c16`. Standard state `e` is an animation ID, not a trial kind: animation 0 can have a real damage trial. Do not scan unrelated packed `T2` values or General `next_state` kind `9`. Standard DamageCheck payload `a` is the percentage; payload `h` can supply a script threshold and must fail closed during HP scaling unless that script has an independent HP-dependency proof.
- When Boss HP changes, reverse-scale only the trial percentage against the final runtime HP, including any HP curse multiplier, so the official absolute damage threshold stays unchanged. Preserve the time window, success/failure branches, state topology, and every unrelated field.
- For a General Boss, materialize a private state routine, repoint only the selected clone's `general_boss.c42`, and preserve required `general_enemy_watch` aliases. Do not mutate a shared official routine in place.
- Fail closed if the source HP is only a proxy, the payload or state reference is malformed, the adjusted percentage leaves `(0, 100]`, or an absolute-threshold receipt cannot be proved. Record per-floor contracts; static proof is not gameplay verification.

## Regression discipline

For every demonstrated runtime failure, add a focused regression that recreates the former bad case and proves the new gate rejects or repairs it. Repairing one generated tower without strengthening the generator is incomplete.

- Standard Funnel reverse references live in ESDL as well as master CSV. `bG` is `damage_share_target_boss_id`, and form `h` watches can name the original Boss ID. Renaming only a Standard Boss HP clone breaks these links without throwing a missing-asset error. Index every effective funnel/level for the identity gate. Either retain the native identity or clone the complete reachable actor/ActionDSL family under private IDs, rewriting all spawn, damage-share and watch references. Prove callback/resource closure and inverse identity replay; keep HP, trials, timers and unrelated parameters unchanged for an identity repair. General watch-table aliases alone cannot repair Standard ESDL watches.

## Reroll presentation and desktop AIR tests

- Keep client fixed-reward previews derived from the same server reward list; do not restore historical hardcoded preview amounts. When the effective tower already includes detail metadata, preserve that capability automatically and rebuild each floor's enemy/HP description from its final verified roll, not a copied label.
- Routine tower rerolls and resource-only checks do not need the desktop AIR runtime. The user reported disruptive repeated HARMAN splash screens on 2026-09-10. Prefer Python/static validation and exact-input cached runtime evidence; reserve desktop AIR launches for unresolved client-runtime questions, explain the possible splash before launching, and group necessary checks instead of repeatedly starting ADL.
- A hidden test application's main window does not establish that the runtime's splash is hidden. Keep desktop AIR opt-in in active builders. Bind reused runtime receipts to the exact SWF, test source, fixtures and driver; record skipped checks as not run, never as gameplay/device verification. Test the no-launch workflow with mocks, without starting AIR to verify that it stays off.

## Item display dimensions depend on the reader

- Five Boss .110 device feedback showed 20px material-bar frames were too small and a weapon enlarged to 40px on a 41px canvas overflowed its detail frame. Preserving donor dimensions alone is not UI validation.
- `DropItemContentsView` uses preloaded `smallVectorIconId` frames at native size. Use independent 40x40 nearest-neighbor material icons in `item_icon`, preload their names and change only the small-icon column; keep the item/shop thumbnail at 20x20. `ItemThumbnailView` already scales by 6 inside a 168px frame, so a 20px weapon displays at 120px while 40px overflows at 240px. Standalone weapon thumbnails also need the full `trimmed_image` frame `0,0,20,20` for alignment and safe texture lifetime.
- Validate effective rows, both size contracts, post-scale bounds, PNG storage and unchanged atlas pixels. The `five_boss_art_contract.py` regression rejects the real .110 resources, missing frames and regeneration that restores old sizes; it does not launch desktop AIR. Keep version variables separate from atlas-loop variables and reject non-version or discontinuous manifest dependencies before publication.

## Deep Abyss reroll time records

- On 2026-09-12 the user explicitly requested a standing rule: every Deep Abyss reroll must also invalidate the previous tower's personal best floor times. Changing floors alone is incomplete. Preserve completion, rewards, unrelated modes and the separate endless quest.
- Generate `quest_time_revisions["rush:700099"]` using `wf_quest_time_revision.quest_time_revisions` from the final effective `rush_event_quest.orderedmap` finite floors. Publish the marker on the same authorized version edge; do not invent a random marker or confuse the CDN version number with the tower revision. Merges/consolidation must carry the winning marker. The 2026-09-12 regression was a .104 tower whose merged manifest retained only the .96 marker.
- After reroll, consolidation or manifest editing, run `python -B tools/fantasy-gauntlet-mod-tools/wf_quest_time_revision.py` from the source root. It checks actual active-archive bytes against the marker resolved by the server, permits a later metadata-only repair, and rejects stale/missing markers. Run the focused Python revision tests and `tests/abyss-best-time-revision.test.js` for behavior changes. Verify the delivered runtime manifest, not only a generator report.
- Old personal times are cleared lazily on progress reads when the revision differs; do not directly wipe player databases. A first new clear establishes the new record, later slower clears preserve it. Old in-flight battles and old-resource clients must not seed the new tower. Warn in the delivery note when previously mixed old/new times must reset together.
- Whole-server floor records, when enabled, use the same tower revision and remain server-local history, outside V1/V2 player saves. Never backfill them from unversioned/mixed personal records or reset them on ordinary in-game restart. Client-only text/art changes must not get an arbitrary new tower marker merely to force a reset.
