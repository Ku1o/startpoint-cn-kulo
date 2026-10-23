# Login-scoped town presentation

This is the R11 source increment on the exact cumulative R10 input, following
the operations, native period/exchange and personal-history changes described
in the [content-operations lineage](../content-operations/README.md#cumulative-source-and-client-compatibility).
The R10 constant below is a historical reproduction guard, not the current
accepted-package selector. New client work must first inspect its platform's
accepted registry and preserve all cumulative methods; do not substitute a
different SWF or relax the historical input assertion.

Merging this source does not rebuild or distribute the existing isolated R11
APK, promote it in an accepted registry, change admission settings, or produce
an iOS client. Client binaries, signing inputs and local verification reports
remain outside Git. A compatible client payload is required to consume the
server's login-scoped town policy; server source integration alone does not
add these hooks to an already installed older client.

`TownThemeState` captures only a successful full login load, independently of
content operations and the real clock. `data.town_presentation_load === true`
is the current load marker; `data_headers.result_code` must be exactly `1`.
A new successful load clears the previous theme before validating its optional
`town_presentation` snapshot. Legacy successful loads are recognized only when
the marker is absent and all four native load records (`user_info`,
`user_option`, `user_character_list`, `user_party_group_list`) are present as
objects. Such legacy loads reset to automatic selection. Partial API replies,
explicit false markers, malformed response containers and error responses do
not update or reset an active policy.

The snapshot uses schema version 1, a safe nonnegative integer revision,
`auto` or `manual`, a stable `theme_id`, positive native `town_content_id`, and
a 64-character lowercase hex `catalog_digest`. The server verifies the catalog
and its actual resources. The client validates the native master row's presence
and supported background, blur, BGM, mask and particle fields before constructing
the native content. It stores only the scalar native ID, so later mutation of a
response cannot change an in-progress asset load. Ordinary responses cannot
hot-switch the theme.

There is no list of five theme names or native IDs in the helper. A future
catalog entry can use any compatible positive native ID already delivered in
the master/resources. Invalid or unavailable rows fall through to the original
complete `getTownContentByTime` algorithm. The existing selected-ID asset group
preload, background/particle consumers and local custom BGM preference remain
in place.

`build_town_theme.py` requires the exact cumulative R10 SWF SHA specified by
`R10`. It appends the `town_theme_login` DoABC and inserts calls into exactly
`ResponseData.<ctor>` and `TownContentRepository.getTownContentByTime`. It proves
inverse insertion equivalence, existing-body preservation, original native
traits/signatures, append-only constants, old helper preservation and exact
non-target SWF tags. It creates no APK or platform admission change.

Build with `--work`, `--source`, `--sdk`, `--java`. Run
`native_runtime_fixtures.py` with `--work`, `--candidate`, `--baseline` (the exact
R10), `--sdk`, `--java`, using the workspace's outer background launcher for the
whole AIR command. The fixture imports the candidate's complete helper and
native selector/getter bodies, compares automatic results directly with the
complete R10 selector, and executes the actual constructor capture prologue.
It exercises invalid snapshots and native fields, ordinary/error responses,
legacy/new sessions, native BGM preference reads, a future ID 42 and a real
Timer boundary.

The fixture table and asset storage are controlled substitutes. The constructor
test covers its exact eight-instruction prologue, not the full response parser.
Annual-period selection executes the native period body with a bounded clock
conversion fixture. These checks do not execute the full game, GPU rendering,
resource downloading, package signing or device installation. APK verification
and device acceptance remain separate.
