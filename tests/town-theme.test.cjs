'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const Sqlite = require('better-sqlite3'), ts = require('typescript'), Fastify = require('fastify')
// Source-only tests. No out/, game startup, runtime databases or effective CDN writes.
require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true }, fileName: filename,
}).outputText, filename)
const { loadTownThemeCatalog, townThemeHash, TownThemeCatalog } = require('../src/lib/town-theme-catalog.ts')
const { TownThemeStore, TownThemeConflict } = require('../src/lib/town-theme-store.ts')
const { createTownThemeRoutes } = require('../src/routes/web_api/town-theme.ts')
test('deployed catalog and real thumbnails match the verified receipt, native rows and current manifest', () => {
    const catalog = loadTownThemeCatalog()
    assert.equal(catalog.degradedReason, null)
    assert.ok(catalog.listing().length >= 1)
    assert.match(catalog.digest, /^[a-f0-9]{64}$/)
    for (const row of catalog.listing()) {
        const sha = row.thumbnailUrl.match(/\/([a-f0-9]{64})\.webp$/)[1]
        assert.equal(townThemeHash(catalog.thumbnail(sha)), sha)
        assert.equal(catalog.find(row.id).nativeTownContentId, row.nativeTownContentId)
    }
})
function assets(t, count = 6) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'town-theme-'))
    t.after(() => fs.rmSync(root, { recursive: true }))
    fs.mkdirSync(path.join(root, 'town_theme_thumbnails')); fs.mkdirSync(path.join(root, 'asset-patch'))
    // Minimal bounded WebP container header used only to test parser identity/dimensions.
    const thumbnail = Buffer.alloc(30)
    thumbnail.write('RIFF'); thumbnail.writeUInt32LE(22, 4); thumbnail.write('WEBPVP8X', 8); thumbnail.writeUInt32LE(10, 16)
    thumbnail.writeUIntLE(63, 24, 3); thumbnail.writeUIntLE(47, 27, 3)
    const sha = townThemeHash(thumbnail), file = `${sha}.webp`
    fs.writeFileSync(path.join(root, 'town_theme_thumbnails', file), thumbnail)
    const manifest = JSON.stringify({ cdn_version: '1.4.258' })
    fs.writeFileSync(path.join(root, 'asset-patch/manifest.json'), manifest)
    const themes = Array.from({ length: count }, (_, index) => {
        const row = Array(20).fill('')
        row[0] = `theme_${index + 1}`; row[1] = '1'
        row[6] = `town/background/custom_${index + 1}/background`; row[7] = `${row[6]}_blur`
        row[8] = row[9] = '(None)'; row[19] = `bgm/common/theme_${index + 1}`
        return { id: `theme_${index + 1}`, name: `主题 ${index + 1}`, description: '合成隔离目录，仅用于协议测试。', nativeTownContentId: index + 1,
            thumbnail: { file, sha256: sha, width: 64, height: 48 }, nativeRow: row, resourceVersion: '1.4.258' }
    })
    const receipt = { schemaVersion: 1, resourceVersion: '1.4.258', manifestSha256: townThemeHash(manifest), themes: themes.map(row => ({ id: row.id,
        nativeTownContentId: row.nativeTownContentId, nativeRowSha256: townThemeHash(JSON.stringify(row.nativeRow)), verified: true,
        resources: [6, 7, 19].map(index => ({ path: `${row.nativeRow[index]}.${index === 19 ? 'mp3' : 'png'}`, sha256: townThemeHash(row.nativeRow[index]), size: 100 })) })) }
    const receiptBytes = JSON.stringify(receipt)
    fs.writeFileSync(path.join(root, 'town_theme_resource_receipt.json'), receiptBytes)
    for (const row of themes) row.resourceEvidence = { schemaVersion: 1, receiptFile: 'town_theme_resource_receipt.json', receiptSha256: townThemeHash(receiptBytes) }
    const data = { schemaVersion: 1, themes }
    const save = () => fs.writeFileSync(path.join(root, 'town_themes.json'), JSON.stringify(data))
    save()
    return { root, data, receipt, thumbnail, sha, save }
}
function republish(a, requireValid = true) {
    a.receipt.themes = a.data.themes.map(row => {
        const previous = a.receipt.themes.find(entry => entry.id === row.id)
        return { ...previous, id: row.id, nativeTownContentId: row.nativeTownContentId,
            nativeRowSha256: townThemeHash(JSON.stringify(row.nativeRow)), verified: true,
            resources: previous?.resources ?? [6, 7, 19].map(index => ({ path: `${row.nativeRow[index]}.${index === 19 ? 'mp3' : 'png'}`,
                sha256: townThemeHash(row.nativeRow[index]), size: 100 })) }
    })
    const bytes = JSON.stringify(a.receipt)
    fs.writeFileSync(path.join(a.root, 'town_theme_resource_receipt.json'), bytes)
    for (const row of a.data.themes) row.resourceEvidence.receiptSha256 = townThemeHash(bytes)
    a.save()
    const catalog = loadTownThemeCatalog(a.root)
    if (requireValid) assert.equal(catalog.degradedReason, null, 'modified synthetic catalog must still have valid receipt/native/resource identities')
    return catalog
}
function fixture(t, count = 6) {
    const a = assets(t, count), db = new Sqlite(':memory:')
    t.after(() => db.close())
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,progress TEXT); INSERT INTO players VALUES(1,'keep');
        CREATE TABLE players_options(player_id INTEGER,value TEXT); INSERT INTO players_options VALUES(1,'local preference unchanged');
        CREATE TABLE content_operations_meta(id INTEGER PRIMARY KEY,revision INTEGER); INSERT INTO content_operations_meta VALUES(1,17);
        CREATE TABLE content_client_reload_meta(id INTEGER PRIMARY KEY,epoch INTEGER); INSERT INTO content_client_reload_meta VALUES(1,23);
        CREATE TABLE server_clock_state(id INTEGER PRIMARY KEY,value TEXT); INSERT INTO server_clock_state VALUES(1,'keep-clock');
        CREATE TABLE players_active_quests(player_id INTEGER,play_id TEXT); INSERT INTO players_active_quests VALUES(1,'keep-battle')`)
    const catalog = loadTownThemeCatalog(a.root), store = new TownThemeStore(db, catalog)
    assert.equal(catalog.degradedReason, null)
    const body = (extra = {}) => ({ expectedRevision: store.status().revision, catalogDigest: catalog.digest, mode: 'manual', themeId: `theme_${count}`, confirmation: 'APPLY_TOWN_THEME', ...extra })
    const untouched = () => ['players', 'players_options', 'content_operations_meta', 'content_client_reload_meta', 'server_clock_state', 'players_active_quests'].map(table => db.prepare(`SELECT * FROM ${table}`).all())
    return { ...a, db, catalog, store, body, untouched }
}

function publishPeriods(a, requireValid = true) {
    for (const row of a.data.themes) {
        const proof = a.receipt.themes.find(entry => entry.id === row.id)
        if (Object.hasOwn(row, 'originalPeriods')) proof.originalPeriodsSha256 = townThemeHash(JSON.stringify(row.originalPeriods))
    }
    return republish(a, requireValid)
}

test('original periods preserve all verified aliases and years while remaining separate from the selected theme identity', t => {
    const a = assets(t), selected = a.data.themes[0]
    selected.nativeRow[2] = '2024-07-25 12:00:00'; selected.nativeRow[3] = '2024-08-08 11:59:59'
    let catalog = republish(a), nativeIdentity = catalog.themeDigest(selected.id)
    assert.deepEqual(catalog.listing()[0].originalPeriods, [{ nativeTownContentId: 1, kind: 'event', start: selected.nativeRow[2], end: selected.nativeRow[3] }], 'old catalogs expose their captured canonical date without guessing an annual rule')
    selected.originalPeriods = [
        { nativeTownContentId: 1, kind: 'event', start: selected.nativeRow[2], end: selected.nativeRow[3] },
        { nativeTownContentId: 101, kind: 'event', start: '2022-11-03 12:00:00', end: '2022-11-17 11:59:59' },
    ]
    catalog = publishPeriods(a)
    assert.deepEqual(catalog.listing()[0].originalPeriods, selected.originalPeriods)
    assert.equal(catalog.themeDigest(selected.id), nativeIdentity, 'displaying additional source periods must not invalidate an existing manual or scheduled binding')
    const exposed = catalog.listing()[0].originalPeriods
    exposed[0].start = 'forged'; exposed.push({})
    assert.deepEqual(catalog.listing()[0].originalPeriods, selected.originalPeriods, 'public responses cannot mutate cached source metadata')
})

test('original period metadata rejects forged receipts, missing canonical rows, duplicate aliases and invalid dates', t => {
    for (const mutate of [
        a => { a.data.themes[0].originalPeriods[0].start = '2024-07-26 12:00:00' },
        a => { a.data.themes[0].originalPeriods = []; publishPeriods(a, false) },
        a => { a.data.themes[0].originalPeriods.push({ ...a.data.themes[0].originalPeriods[0] }); publishPeriods(a, false) },
        a => { a.data.themes[0].originalPeriods.push({ nativeTownContentId: 100, kind: 'event', start: '2023-02-29 00:00:00', end: '2023-03-01 00:00:00' }); publishPeriods(a, false) },
        a => { a.data.themes[0].originalPeriods.push({ nativeTownContentId: 100, kind: 'event', start: '2024-03-02 00:00:00', end: '2024-03-01 00:00:00' }); publishPeriods(a, false) },
    ]) {
        const a = assets(t), row = a.data.themes[0]
        row.nativeRow[2] = '2024-07-25 12:00:00'; row.nativeRow[3] = '2024-08-08 11:59:59'
        row.originalPeriods = [{ nativeTownContentId: 1, kind: 'event', start: row.nativeRow[2], end: row.nativeRow[3] }]
        publishPeriods(a)
        mutate(a)
        a.save()
        assert.ok(loadTownThemeCatalog(a.root).degradedReason)
    }
})

test('native Annual metadata is distinct from Event years, supports a cross-year source period and has no leap-day boundary', t => {
    const a = assets(t), row = a.data.themes[0]
    row.nativeRow[1] = '2'; row.nativeRow[4] = '12-20 12:00:00'; row.nativeRow[5] = '01-06 04:59:59'
    row.originalPeriods = [{ nativeTownContentId: 1, kind: 'annual', start: row.nativeRow[4], end: row.nativeRow[5] }]
    const catalog = publishPeriods(a)
    assert.equal(catalog.listing()[0].annualEligible, true)
    assert.deepEqual(catalog.listing()[0].originalPeriods, row.originalPeriods)
    row.nativeRow[4] = '02-29 00:00:00'; row.originalPeriods[0].start = row.nativeRow[4]
    assert.ok(publishPeriods(a, false).degradedReason)
})

test('the ordinary fallback theme has no original window and is not offered for a seasonal annual schedule', t => {
    const a = assets(t), row = a.data.themes[0]
    row.nativeRow[1] = '0'; row.originalPeriods = []
    const catalog = publishPeriods(a), listed = catalog.listing()[0]
    assert.equal(listed.annualEligible, false); assert.deepEqual(listed.originalPeriods, [])
})

test('new period-aware catalogs cannot use legacy empty-date compatibility for Event or Annual rows', t => {
    for (const kind of ['1', '2']) {
        const a = assets(t), row = a.data.themes[0]
        row.nativeRow[1] = kind
        assert.equal(republish(a).degradedReason, null, 'old catalogs remain read-compatible before period metadata is introduced')
        row.originalPeriods = []
        assert.ok(publishPeriods(a, false).degradedReason, 'new catalogs must capture a valid canonical source interval')
    }
})
test('missing singleton defaults auto without writes; extensible sixth theme, auto and no-op preserve all non-theme state', t => {
    const { db, store, body, untouched } = fixture(t), before = untouched(), tables = db.prepare('SELECT name FROM sqlite_master').all()
    assert.deepEqual(store.snapshot(), { schema_version: 1, revision: 0, mode: 'auto', theme_id: null, town_content_id: null, catalog_digest: store.catalog.digest })
    assert.equal(store.status().themes.length, 6)
    assert.deepEqual(db.prepare('SELECT name FROM sqlite_master').all(), tables, 'read-only/default must not create or migrate state')
    assert.equal(store.update(body({ mode: 'auto', themeId: null })).revision, 0)
    assert.deepEqual(db.prepare('SELECT name FROM sqlite_master').all(), tables)
    assert.equal(store.update(body(), 1234).revision, 1)
    assert.equal(store.snapshot().town_content_id, 6, 'sixth theme is accepted through catalog data, not a hardcoded set')
    store.update(body(), 1235); assert.equal(store.status().revision, 1, 'same target with fresh CAS is a no-op')
    assert.throws(() => store.update(body({ expectedRevision: 0 })), TownThemeConflict)
    store.update(body({ mode: 'auto', themeId: null }), 1236)
    assert.equal(store.status().revision, 2); assert.equal(store.snapshot().town_content_id, null)
    assert.equal(db.prepare('SELECT count(*) n FROM town_presentation_audit').get().n, 2)
    assert.deepEqual(untouched(), before)
    for (const table of ['town_presentation_state', 'town_presentation_audit']) assert.deepEqual(db.prepare(`PRAGMA foreign_key_list(${table})`).all(), [])
})
test('strict input validation refuses paths, unknown fields, wrong confirmation, unsafe numbers and impossible modes', t => {
    const { store, body, db } = fixture(t)
    for (const input of [null, [], {}, body({ arbitrary: '/secret' }), body({ confirmation: 'RELOAD_ALL_CLIENTS' }), body({ expectedRevision: -1 }),
        body({ expectedRevision: Number.MAX_SAFE_INTEGER }), body({ expectedRevision: '0' }), body({ themeId: '../normal' }), body({ mode: 'auto', themeId: 'theme_6' }),
        body({ mode: 'manual', themeId: null }), body({ mode: 'AUTO' }), body({ catalogDigest: 'x'.repeat(64) })])
        assert.throws(() => store.update(input), /请求无效/)
    assert.throws(() => store.update(body({ themeId: 'theme_100' })), /未登记/)
    assert.throws(() => store.update(body({ catalogDigest: '0'.repeat(64) })), TownThemeConflict)
    assert.equal(store.status().revision, 0)
    assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='town_presentation_state'").get(), undefined)
})
test('audit failures roll back state and revision; independent connection/restart and concurrent CAS see the current singleton', t => {
    const { db, store, body, catalog, untouched } = fixture(t), before = untouched()
    store.update(body(), 100)
    db.exec("CREATE TRIGGER fail_theme_audit BEFORE INSERT ON town_presentation_audit BEGIN SELECT RAISE(ABORT,'synthetic audit failure'); END")
    assert.throws(() => store.update(body({ mode: 'auto', themeId: null }), 101), /synthetic audit failure/)
    assert.equal(store.snapshot().revision, 1); assert.equal(store.snapshot().theme_id, 'theme_6')
    assert.equal(db.prepare('SELECT count(*) n FROM town_presentation_audit').get().n, 1)
    const restored = new Sqlite(db.serialize()); t.after(() => restored.close())
    assert.equal(new TownThemeStore(restored, catalog).snapshot().theme_id, 'theme_6')
    db.exec('DROP TRIGGER fail_theme_audit')
    const file = path.join(fs.mkdtempSync(path.join(os.tmpdir(), 'town-theme-db-')), 'synthetic.sqlite')
    const firstDb = new Sqlite(file), secondDb = new Sqlite(file)
    t.after(() => { firstDb.close(); secondDb.close(); fs.rmSync(path.dirname(file), { recursive: true }) })
    const first = new TownThemeStore(firstDb, catalog), second = new TownThemeStore(secondDb, catalog), same = body({ expectedRevision: 0 })
    first.update(same, 200)
    assert.equal(second.snapshot().revision, 1)
    assert.throws(() => second.update(same, 201), TownThemeConflict)
    second.update({ ...same, expectedRevision: 1, mode: 'auto', themeId: null }, 202)
    assert.equal(first.snapshot().mode, 'auto'); assert.equal(first.snapshot().revision, 2)
    assert.deepEqual(untouched(), before)
})
test('invalid persisted state and missing catalog safely auto without rewriting source records; display changes preserve manual', t => {
    const { db, store, body, root, save, data } = fixture(t)
    store.update(body(), 100)
    const original = db.prepare('SELECT * FROM town_presentation_state').get()
    data.themes[0].description += 'changed'; save()
    const stale = new TownThemeStore(db, loadTownThemeCatalog(root))
    assert.equal(stale.snapshot().mode, 'manual'); assert.equal(stale.status().degradedReason, null)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), original)
    fs.unlinkSync(path.join(root, 'town_themes.json'))
    const missing = new TownThemeStore(db, loadTownThemeCatalog(root))
    assert.equal(missing.snapshot().mode, 'auto'); assert.ok(missing.status().degradedReason)
    const unavailable = new TownThemeStore(db, new TownThemeCatalog(store.catalog.digest, [], new Map(), 'synthetic_invalid_evidence'))
    assert.throws(() => unavailable.update(body()), /资源证据不可用/)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), original)
    db.prepare('UPDATE town_presentation_state SET value_json=? WHERE id=1').run('{bad')
    const bad = db.prepare('SELECT * FROM town_presentation_state').get()
    assert.equal(store.snapshot().mode, 'auto'); assert.equal(store.snapshot().revision, 1); assert.ok(store.status().degradedReason)
    assert.throws(() => store.update(body()), /持久状态/)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), bad)
})
test('sixth theme addition, selected display/thumbnail edits and unrelated resource/version changes retain manual without state writes', t => {
    const a = fixture(t, 5), { db, store, body, untouched } = a, preserved = untouched()
    store.update(body(), 100)
    const original = db.prepare('SELECT * FROM town_presentation_state').get(), semantic = store.catalog.themeDigest('theme_5')
    const sixth = JSON.parse(JSON.stringify(a.data.themes[4]))
    sixth.id = 'theme_6'; sixth.nativeTownContentId = 6; sixth.nativeRow[0] = 'theme_6'
    sixth.nativeRow[6] = 'town/background/custom_6/background'; sixth.nativeRow[7] = sixth.nativeRow[6] + '_blur'; sixth.nativeRow[19] = 'bgm/common/theme_6'
    a.data.themes.push(sixth)
    let catalog = republish(a), current = new TownThemeStore(db, catalog)
    assert.notEqual(catalog.digest, store.catalog.digest); assert.equal(catalog.themeDigest('theme_5'), semantic)
    assert.equal(current.snapshot().mode, 'manual'); assert.equal(current.snapshot().theme_id, 'theme_5'); assert.equal(current.status().degradedReason, null)
    assert.throws(() => current.update(body()), TownThemeConflict, 'full catalog digest remains mandatory for management CAS')
    const selected = a.data.themes[4], image = Buffer.from(a.thumbnail)
    selected.name = '更清楚的中文名称'; selected.description = '只更新展示说明。'
    image.writeUIntLE(31, 24, 3)
    const imageHash = townThemeHash(image)
    fs.writeFileSync(path.join(a.root, 'town_theme_thumbnails', `${imageHash}.webp`), image)
    selected.thumbnail = { file: `${imageHash}.webp`, sha256: imageHash, width: 32, height: 48 }
    catalog = republish(a); current = new TownThemeStore(db, catalog)
    assert.equal(catalog.themeDigest('theme_5'), semantic); assert.equal(current.snapshot().mode, 'manual')
    const manifest = JSON.stringify({ cdn_version: '1.4.259', unrelated: true })
    fs.writeFileSync(path.join(a.root, 'asset-patch/manifest.json'), manifest)
    a.receipt.manifestSha256 = townThemeHash(manifest); a.receipt.resourceVersion = '1.4.259'
    for (const row of a.data.themes) row.resourceVersion = '1.4.259'
    a.receipt.themes.find(row => row.id === 'theme_5').resources.reverse()
    a.receipt.themes.find(row => row.id === 'theme_6').resources[0].sha256 = 'a'.repeat(64)
    catalog = republish(a); current = new TownThemeStore(db, catalog)
    assert.equal(catalog.themeDigest('theme_5'), semantic); assert.equal(current.snapshot().mode, 'manual')
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), original, 'read-time compatibility must not silently rebind persisted catalog metadata')
    assert.deepEqual(untouched(), preserved)
    const next = current.update({ ...body(), catalogDigest: catalog.digest, themeId: 'theme_6' }, 101)
    assert.equal(next.schemaVersion, 1); assert.equal(next.revision, 2); assert.equal(next.themeId, 'theme_6')
    assert.equal(Object.prototype.hasOwnProperty.call(next, 'themeDigest'), false, 'public API shape stays unchanged')
    assert.equal(Object.prototype.hasOwnProperty.call(current.snapshot(), 'themeDigest'), false)
    const audit = db.prepare('SELECT * FROM town_presentation_audit WHERE revision=2').get()
    assert.equal(JSON.parse(audit.before_json).themeDigest, semantic)
    assert.equal(JSON.parse(audit.after_json).themeDigest, catalog.themeDigest('theme_6'))
    current.update({ ...body(), expectedRevision: 2, catalogDigest: catalog.digest, mode: 'auto', themeId: null }, 102)
    assert.equal(JSON.parse(db.prepare('SELECT value_json FROM town_presentation_state').get().value_json).themeDigest, null)
})
for (const mutation of [
    { name: 'selected deletion', apply: a => { a.data.themes = a.data.themes.filter(row => row.id !== 'theme_6') }, removed: true },
    { name: 'selected native ID', apply: a => { a.data.themes[5].nativeTownContentId = 42 } },
    { name: 'selected native row', apply: a => { a.data.themes[5].nativeRow[0] = 'new_native_semantics' } },
    { name: 'selected resource SHA', apply: a => { a.receipt.themes[5].resources[0].sha256 = 'b'.repeat(64) } },
    { name: 'selected resource size', apply: a => { a.receipt.themes[5].resources[0].size++ } },
]) test(`${mutation.name} safely degrades until explicit fresh CAS rebind, with atomic semantic audit`, t => {
    const a = fixture(t), { store, db, body } = a
    store.update(body(), 100)
    const original = db.prepare('SELECT * FROM town_presentation_state').get()
    mutation.apply(a)
    const catalog = republish(a), changed = new TownThemeStore(db, catalog)
    assert.equal(changed.snapshot().mode, 'auto'); assert.equal(changed.snapshot().town_content_id, null)
    assert.equal(changed.status().degradedReason, 'town_theme_state_theme_mismatch')
    assert.equal(changed.snapshot().revision, 1)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), original)
    assert.throws(() => changed.update(body()), TownThemeConflict)
    if (mutation.removed) assert.throws(() => changed.update({ ...body(), catalogDigest: catalog.digest }), /未登记/)
    const themeId = mutation.removed ? 'theme_1' : 'theme_6'
    const next = changed.update({ ...body(), catalogDigest: catalog.digest, themeId }, 101)
    assert.equal(next.mode, 'manual'); assert.equal(next.themeId, themeId); assert.equal(next.revision, 2)
    assert.equal(changed.status().degradedReason, null)
    assert.equal(JSON.parse(db.prepare('SELECT after_json FROM town_presentation_audit WHERE revision=2').get().after_json).themeDigest, catalog.themeDigest(themeId))
})
test('unpublished records missing semantic identity stay invalid and cannot be silently repaired or supplied by an operator', t => {
    const { store, db, body } = fixture(t)
    store.update(body(), 100)
    const state = JSON.parse(db.prepare('SELECT value_json FROM town_presentation_state').get().value_json)
    delete state.themeDigest
    db.prepare('UPDATE town_presentation_state SET value_json=?').run(JSON.stringify(state))
    const invalid = db.prepare('SELECT * FROM town_presentation_state').get()
    assert.equal(store.snapshot().schema_version, 1); assert.equal(store.snapshot().mode, 'auto')
    assert.equal(store.status().degradedReason, 'town_theme_state_invalid')
    assert.throws(() => store.update(body()), /持久状态/)
    assert.throws(() => store.update(body({ themeDigest: store.catalog.themeDigest('theme_6') })), /请求无效/)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), invalid)
    assert.equal(db.prepare('SELECT count(*) n FROM town_presentation_audit').get().n, 1)
})
test('lost singleton with existing audit degrades to auto and cannot silently replace durable history', t => {
    const { store, body, db } = fixture(t)
    store.update(body(), 100)
    db.exec('DELETE FROM town_presentation_state')
    assert.equal(store.snapshot().mode, 'auto'); assert.equal(store.status().degradedReason, 'town_theme_state_missing')
    assert.throws(() => store.update(body()), /持久状态/)
    assert.equal(db.prepare('SELECT count(*) n FROM town_presentation_state').get().n, 0)
    assert.equal(db.prepare('SELECT count(*) n FROM town_presentation_audit').get().n, 1)
})
test('catalog rejects resource/row/thumbnail identity changes, arbitrary paths and duplicate IDs before serving', t => {
    const { root, sha } = assets(t)
    const catalogBytes = fs.readFileSync(path.join(root, 'town_themes.json')), receiptBytes = fs.readFileSync(path.join(root, 'town_theme_resource_receipt.json'))
    const check = mutate => { fs.writeFileSync(path.join(root, 'town_themes.json'), catalogBytes); fs.writeFileSync(path.join(root, 'town_theme_resource_receipt.json'), receiptBytes); mutate(); assert.ok(loadTownThemeCatalog(root).degradedReason) }
    check(() => { const v = JSON.parse(catalogBytes); v.themes[0].nativeRow[6] = 'town/background/forged/background'; fs.writeFileSync(path.join(root, 'town_themes.json'), JSON.stringify(v)) })
    check(() => { const v = JSON.parse(catalogBytes); v.themes[0].thumbnail.file = '../secret.webp'; fs.writeFileSync(path.join(root, 'town_themes.json'), JSON.stringify(v)) })
    check(() => { const v = JSON.parse(catalogBytes); v.themes[0].thumbnail.width = 65; fs.writeFileSync(path.join(root, 'town_themes.json'), JSON.stringify(v)) })
    check(() => { const v = JSON.parse(catalogBytes); v.themes[1].id = v.themes[0].id; fs.writeFileSync(path.join(root, 'town_themes.json'), JSON.stringify(v)) })
    check(() => { const v = JSON.parse(catalogBytes); v.themes[0].resourceEvidence = { path: 'some/arbitrary/resource.json' }; fs.writeFileSync(path.join(root, 'town_themes.json'), JSON.stringify(v)) })
    check(() => { const v = JSON.parse(receiptBytes); v.themes[0].verified = false; fs.writeFileSync(path.join(root, 'town_theme_resource_receipt.json'), JSON.stringify(v)) })
    check(() => fs.writeFileSync(path.join(root, 'asset-patch/manifest.json'), '{}'))
    fs.writeFileSync(path.join(root, 'asset-patch/manifest.json'), JSON.stringify({ cdn_version: '1.4.258' }))
    check(() => fs.writeFileSync(path.join(root, 'town_theme_thumbnails', `${sha}.webp`), 'corrupt'))
})
test('authenticated isolated HTTP preserves session guard, strict writes, concurrent CAS, thumbnail identity/cache and missing files', async t => {
    const { store, db, body, sha, thumbnail, untouched } = fixture(t), app = Fastify({ logger: false }), before = untouched()
    t.after(() => app.close())
    const auth = require('../src/lib/management-auth.ts'), previous = process.env.ADMIN_PANEL_PASSWORD
    process.env.ADMIN_PANEL_PASSWORD = 'synthetic-town-theme-only'
    auth.installManagementAuth(app)
    if (previous === undefined) delete process.env.ADMIN_PANEL_PASSWORD; else process.env.ADMIN_PANEL_PASSWORD = previous
    let writes = 0
    await app.register(createTownThemeRoutes({ store: () => store, transaction: async fn => { writes++; return db.transaction(fn).immediate() } }), { prefix: '/api/server/town-theme' })
    await app.ready()
    for (const method of ['GET', 'POST']) assert.equal((await app.inject({ method, url: '/api/server/town-theme', ...(method === 'POST' ? { payload: body() } : {}) })).statusCode, 401)
    assert.equal((await app.inject({ method: 'GET', url: `/api/server/town-theme/thumbnails/${sha}.webp` })).statusCode, 401)
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: 'synthetic-town-theme-only' } })
    assert.equal(login.statusCode, 200)
    const cookie = login.headers['set-cookie'].split(';')[0], headers = { cookie }, url = '/api/server/town-theme'
    const get = await app.inject({ method: 'GET', url, headers }); assert.equal(get.statusCode, 200); assert.equal(get.json().mode, 'auto'); assert.equal(get.headers['cache-control'], 'no-store')
    assert.equal((await app.inject({ method: 'POST', url, headers, payload: body({ sourcePath: '/secret' }) })).statusCode, 400)
    assert.equal(writes, 0, 'request validation occurs before write admission')
    const payload = body(), results = await Promise.all([1, 2].map(() => app.inject({ method: 'POST', url, headers, payload })))
    assert.deepEqual(results.map(r => r.statusCode).sort(), [200, 409]); assert.equal(store.status().revision, 1)
    const imageUrl = `${url}/thumbnails/${sha}.webp`, image = await app.inject({ method: 'GET', url: imageUrl, headers })
    assert.equal(image.statusCode, 200); assert.deepEqual(image.rawPayload, thumbnail); assert.equal(image.headers.etag, `"${sha}"`)
    assert.match(image.headers['cache-control'], /^private,.*immutable/)
    for (const conditional of [image.headers.etag, `W/${image.headers.etag}`, '*', `"other", ${image.headers.etag}`]) {
        const response = await app.inject({ method: 'GET', url: imageUrl, headers: { ...headers, 'if-none-match': conditional } })
        assert.equal(response.statusCode, 304); assert.equal(response.rawPayload.length, 0)
    }
    assert.equal((await app.inject({ method: 'GET', url: `${url}/thumbnails/${'0'.repeat(64)}.webp`, headers })).statusCode, 404)
    assert.equal((await app.inject({ method: 'GET', url: `${url}/thumbnails/%2e%2e%2fsecret.webp`, headers })).statusCode, 404)
    assert.equal((await app.inject({ method: 'GET', url: imageUrl, headers: { 'if-none-match': image.headers.etag } })).statusCode, 401, '304 must still require session')
    assert.deepEqual(untouched(), before)
})
test('plugin itself authenticates even without global guard and login captures the small snapshot only in successful load wrapper', async t => {
    const { store } = fixture(t), app = Fastify(); t.after(() => app.close())
    await app.register(createTownThemeRoutes({ store: () => store, transaction: async fn => fn() }), { prefix: '/standalone' })
    assert.equal((await app.inject({ method: 'GET', url: '/standalone' })).statusCode, 401)
    const load = fs.readFileSync(path.join(__dirname, '../src/routes/cn/load.ts'), 'utf8')
    assert.match(load, /function wrapOptionFields\([^]*?d\.town_presentation = townThemeLoginSnapshot\(\)/)
    assert.equal((load.match(/d\.town_presentation\s*=/g) || []).length, 1)
    assert.match(load, /d\.town_presentation_load = true/)
})
test('unknown HTTP write result is read back before another write; committed state and audit survive the transport failure', async t => {
    const { store, body, db } = fixture(t), app = Fastify({ logger: false }); t.after(() => app.close())
    const loginApp = Fastify(), previous = process.env.ADMIN_PANEL_PASSWORD
    process.env.ADMIN_PANEL_PASSWORD = 'synthetic-town-readback'
    require('../src/lib/management-auth.ts').installManagementAuth(loginApp)
    if (previous === undefined) delete process.env.ADMIN_PANEL_PASSWORD; else process.env.ADMIN_PANEL_PASSWORD = previous
    const login = await loginApp.inject({ method: 'POST', url: '/admin-login', payload: { password: 'synthetic-town-readback' } })
    await loginApp.close()
    const headers = { cookie: login.headers['set-cookie'].split(';')[0] }
    await app.register(createTownThemeRoutes({ store: () => store, transaction: async fn => { fn(); throw new Error('synthetic lost response after commit') } }), { prefix: '/town' })
    const response = await app.inject({ method: 'POST', url: '/town', headers, payload: body() })
    assert.equal(response.statusCode, 503); assert.match(response.json().error, /先刷新读取/)
    const readback = await app.inject({ method: 'GET', url: '/town', headers })
    assert.equal(readback.json().revision, 1); assert.equal(readback.json().themeId, 'theme_6')
    assert.equal(db.prepare('SELECT count(*) n FROM town_presentation_audit').get().n, 1)
})
