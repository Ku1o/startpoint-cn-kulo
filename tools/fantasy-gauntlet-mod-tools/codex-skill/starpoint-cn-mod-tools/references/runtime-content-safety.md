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
- Recognize the two runtime representations independently: Standard Enemy state kind `13` with its `T2` percentage payload, and General Boss `general_boss_state.c16`. Never reinterpret other packed `T2` states or General `next_state` kind `9` as the visible red bar.
- When Boss HP changes, reverse-scale only the trial percentage against the final runtime HP, including any HP curse multiplier, so the official absolute damage threshold stays unchanged. Preserve the time window, success/failure branches, state topology, and every unrelated field.
- For a General Boss, materialize a private state routine, repoint only the selected clone's `general_boss.c42`, and preserve required `general_enemy_watch` aliases. Do not mutate a shared official routine in place.
- Fail closed if the source HP is only a proxy, the payload or state reference is malformed, the adjusted percentage leaves `(0, 100]`, or an absolute-threshold receipt cannot be proved. Record per-floor contracts; static proof is not gameplay verification.

## Regression discipline

For every demonstrated runtime failure, add a focused regression that recreates the former bad case and proves the new gate rejects or repairs it. Repairing one generated tower without strengthening the generator is incomplete.
