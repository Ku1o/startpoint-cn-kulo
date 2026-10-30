# 2026-10-31 CDN adopted sources

`tools/rebuild_production_20261031_cdn.py` is the source entry for the adopted
344–350 resource recipes. It calls repository WF codecs, orderedmap helpers and
the explicitly declared Character Studio compiler. It does not activate a
version, create ZIPs, edit a manifest, touch server data, run a service, publish
or change acceptance records. Existing released archives remain authoritative
byte records; running a source recipe produces a new, isolated resource folder.

| Recipe | Required effective baseline | Preserved implementation |
| --- | --- | --- |
| `release344.json` | 1.4.258 | PR cumulative filtering/continue rules, final gacha skill precedence, native reward/shop and ticket-v3 sources |
| `town345.json` | 1.4.344 | Theme103, prior18 compressed rows, original event dates, spring BGM, seven visual assets and480-frame particle loop |
| `art346347.json --phase 346` | 1.4.345 | Adopted portraits/crops, native motion and visual-only bindings |
| `art346347.json --phase 347` | 1.4.346 | Adopted mech/Lich FX,230-to60 sampling and fixed Lich Zone geometry |
| `ticket348.json` | 1.4.347 | Final B20×20 artwork, existing atlas cell(1,1965,20,20), all other pixels/metadata |
| `lich349.json` | 1.4.348 | Two0.5 inner drawing layouts, original frame/timeline/texture coordinates and nonvisual behavior |
| `town350.json` | 1.4.349 | Final700×900 PNG bytes, new maskRGB with349 alpha,350×450 native blur derivative |

The historical349 town05 draft is superseded by350 and is not an input to the
current art recipe. The existing349 archive retains its historical bytes. The
349 source recipe here reproduces the adopted Lich change only.

## Inputs and dependencies

Three small adopted PNG inputs are stored under `inputs/`: the final ticket B,
the final700×900 town image, and the nine-cell particle atlas. Particle parts,
atlas names and the timeline are editable source objects in `town345.json`.
Canonical character UI masks and small approved gacha/ticket seeds are embedded
in their exact specifications. Hash checks prevent silently selecting other art.

Large author archives, the historical approved town concept, fixed PR source
archives and private pristine CDN remain explicit external inputs. Full aliases,
size/hash contracts and the Character Studio eleven-file source contract are in
the recipes and the combined `external-inputs.json` index. This source set is
therefore not a self-contained asset distribution. `sources.json` records
technical origins; individual Git authorship must be established from the
corresponding upstream metadata, not inferred from artwork filenames.

Supply locations through a local JSON object such as
`{"author_149985":"<LOCAL_AUTHOR_ARCHIVE>","character_studio":"<LOCAL_COMPILER_DIRECTORY>"}`.
Use the aliases required by the selected recipe. Keep that location file outside
Git. No input discovery, download, account change or dependency installation is
performed. The original image pipeline used Python3.13 and Pillow12.3.0; use the
already configured project interpreter and codecs. Listed byte-identity checks
stop instead of accepting changed encoder output; their coverage is described
below.

## Validation and isolated generation

From the repository root, parse one recipe and verify its bundled small inputs:

```powershell
python -B tools/rebuild_production_20261031_cdn.py --spec assets/asset-patch/specs/production-20261031/town350.json --check-spec
python -B tools/rebuild_production_20261031_cdn.py --spec assets/asset-patch/specs/production-20261031/art346347.json --phase 347 --check-spec
```

`--check-spec` parses source/specifications and bundled-input identities only;
it reports declared external aliases without claiming to have verified absent
inputs. Add `--verify-external-inputs --external-inputs <LOCAL_LOCATIONS_JSON>`
to require all selected recipe dependencies and their exact hashes.

To reproduce one resource recipe, supply an explicit existing chain and a new
output directory outside the repository and every input root:

```powershell
python -B tools/rebuild_production_20261031_cdn.py --spec assets/asset-patch/specs/production-20261031/town350.json --manifest <LOCAL_MANIFEST> --active <LOCAL_ACTIVE_ARCHIVES> --baseline <PRISTINE_CN_DIRECTORY> --output <NEW_OUTPUT_DIRECTORY>
```

The manifest may be a later cumulative manifest containing the required
historical baseline. Reads stop at the recipe's `baseVersion`; resource preimage
hashes still have to match. `baselineManifestSha256` fields preserve the adopted
historical identity and do not force the input manifest to remain at that old
version. Only requested payloads are read. A pristine central-directory index is
created only when an asset has no active winner; no full-store extraction or
global payload CRC/hash audit occurs.

The345–350 recipes check the exact output set and byte identities listed for
their own scope:345's eight resources,346/347's respective declared art/FX sets,
348's two ticket images,349's two Lich parts layouts and350's three town PNGs.
The349 source scope excludes the superseded historical town05 artwork.

The344 recipe checks only identities and constraints explicitly consumed by its
implementation. Its `adoptedOutputIdentity` records the14 existing archive
identities and1293-member comparison target; the generator does not consume that
record to verify every final payload, and it does not establish full344 output
equality. A separate comparison with the adopted344 winners is required for that
claim. The source-closeout check reproduced only348–350's seven resources.

Optional `--resource root:logical` filters written outputs after generation; it
does not promise to reduce an art compiler's work. Split expensive validation by
recipe/phase under the caller's assigned process limits. The default output cap
is32MiB; this entry never writes version archives. Compare selected resources
with their existing adopted edge, without rebuilding or replacing the24 release
ZIPs.

`python -B tools/test_production_20261031_cdn.py` runs small standard-library
regressions for missing/corrupt enabled archives versus a genuinely absent
resource, plus source syntax parsing. It does not need private assets or rebuild
the release.

Source parsing, isolated resource equality, native device behavior and cloud
deployment are separate evidence. The seven compact historical audit files keep
their original offline/candidate status. Task receipts, private paths, previews,
screenshots, videos, rollback directories and chat records are not source inputs.
