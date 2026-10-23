'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), ts = require('typescript'), Sqlite = require('better-sqlite3')
// Source-only, synthetic databases. No service, workspace DB, generated out/ or resource edits.
require.extensions['.ts'] = (module, file) => module._compile(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true }, fileName: file,
}).outputText, file)
const { TownThemeCatalog, townThemeHash } = require('../src/lib/town-theme-catalog.ts')
const { TownThemeStore, TownThemeConflict } = require('../src/lib/town-theme-store.ts')
const { validAnnualDate, beijingAnnualTime } = require('../src/lib/town-theme-calendar.ts')
const at = value => Date.parse(value + '+08:00')
const now = at('2026-12-20T12:00:00')
const annual = (themeId = 'christmas', start = '12-16 12:00:00', end = '12-31 23:59:59') => ({ themeId, start, end })
function catalog(options = {}) {
    const meta = options.meta ?? 'original', rows = [], resources = new Map()
    const names = { normal: '日常', christmas: '圣诞', new_year: '新年', spring: '春樱' }
    const ids = options.ids ?? Object.keys(names)
    for (let index = 0; index < ids.length; index++) {
        const id = ids[index], row = Array(20).fill('')
        row[0] = id; row[1] = id === 'normal' ? '0' : '1'; row[6] = `town/background/${id}/a`; row[7] = `town/background/${id}/b`; row[8] = row[9] = '(None)'; row[19] = `bgm/common/${id}`
        rows.push({ id, name: (names[id] ?? id) + (options.rename && id === 'christmas' ? '新名称' : ''), description: meta,
            nativeTownContentId: index + 1, nativeRow: row, resourceVersion: '1.4.258', thumbnail: { file: 'a'.repeat(64) + '.webp', sha256: 'a'.repeat(64), width: 64, height: 64 } })
        resources.set(id, [{ path: row[6] + '.png', sha256: options.changed === id ? 'b'.repeat(64) : 'c'.repeat(64), size: 10 }])
    }
    return new TownThemeCatalog(townThemeHash(JSON.stringify({ ids, meta, changed: options.changed, rename: options.rename })), rows, new Map(), null, resources)
}
function fixture(t, cat = catalog()) {
    const db = new Sqlite(':memory:'); t.after(() => db.close())
    db.exec(`CREATE TABLE players(id INTEGER PRIMARY KEY,progress TEXT); INSERT INTO players VALUES(1,'keep');
        CREATE TABLE players_options(player_id INTEGER,value TEXT); INSERT INTO players_options VALUES(1,'keep-bgm');
        CREATE TABLE players_items(player_id INTEGER,id INTEGER,stock INTEGER); INSERT INTO players_items VALUES(1,9,77);
        CREATE TABLE players_active_quests(player_id INTEGER,play_id TEXT); INSERT INTO players_active_quests VALUES(1,'old-battle');
        CREATE TABLE content_operations_meta(id INTEGER PRIMARY KEY,revision INTEGER); INSERT INTO content_operations_meta VALUES(1,19);
        CREATE TABLE content_client_reload_meta(id INTEGER PRIMARY KEY,epoch INTEGER); INSERT INTO content_client_reload_meta VALUES(1,23);
        CREATE TABLE server_clock_state(id INTEGER PRIMARY KEY,value TEXT); INSERT INTO server_clock_state VALUES(1,'real-no-offset-change')`)
    const store = new TownThemeStore(db, cat)
    const body = (extra = {}) => ({ expectedRevision: store.status(now).revision, catalogDigest: cat.digest, mode: 'auto', themeId: null, confirmation: 'APPLY_TOWN_THEME', ...extra })
    const preserved = () => ['players', 'players_options', 'players_items', 'players_active_quests', 'content_operations_meta', 'content_client_reload_meta', 'server_clock_state']
        .map(table => db.prepare(`SELECT * FROM ${table}`).all())
    return { db, cat, store, body, preserved }
}
test('strict non-leap boundaries and Beijing real clock formatting are independent of local timezone or business offset', () => {
    for (const value of ['01-01 00:00:00', '02-28 23:59:59', '04-30 12:34:56', '12-31 23:59:59']) assert.equal(validAnnualDate(value), true)
    for (const value of ['02-29 00:00:00', '02-30 00:00:00', '04-31 00:00:00', '00-01 00:00:00', '13-01 00:00:00', '01-00 00:00:00',
        '1-01 00:00:00', '01-1 00:00:00', '01-01 24:00:00', '01-01 00:60:00', '01-01 00:00:60', '01-01 0:00:00', '2026-01-01 00:00:00', '01-01 00:00:00Z', '', null, 123])
        assert.equal(validAnnualDate(value), false, String(value))
    assert.equal(beijingAnnualTime(Date.parse('2026-12-31T16:00:00.999Z')), '01-01 00:00:00')
    assert.equal(beijingAnnualTime(Date.parse('2028-02-29T04:00:00Z')), '02-29 12:00:00')
    assert.throws(() => beijingAnnualTime(NaN)); assert.throws(() => beijingAnnualTime(-1))
})
test('legacy seven-field state reads without migration and missing annual field requests preserve existing annual settings', t => {
    const { db, cat, store, body } = fixture(t)
    assert.deepEqual(store.status(now).annualSchedules, []); assert.deepEqual(store.status(now).annualWarnings, [])
    assert.equal(store.status(now).activeAnnualThemeId, null)
    assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='town_presentation_state'").get(), undefined)
    store.update(body({ mode: 'manual', themeId: 'christmas' }), now)
    const old = JSON.parse(db.prepare('SELECT value_json FROM town_presentation_state').get().value_json)
    delete old.annualSchedules
    assert.equal(Object.keys(old).length, 7)
    db.prepare('UPDATE town_presentation_state SET value_json=?').run(JSON.stringify(old))
    const raw = db.prepare('SELECT * FROM town_presentation_state').get(), changes = db.prepare('SELECT total_changes() n').get().n
    assert.equal(store.status(now).mode, 'manual'); assert.deepEqual(store.status(now).annualSchedules, [])
    assert.equal(store.snapshot(now).theme_id, 'christmas')
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), raw)
    assert.equal(db.prepare('SELECT total_changes() n').get().n, changes)
    store.update(body({ annualSchedules: [annual()] }), now)
    assert.equal(store.status(now).mode, 'auto'); assert.equal(store.status(now).activeAnnualThemeId, 'christmas')
    const before = store.status(now).annualSchedules
    store.update(body({ mode: 'manual', themeId: 'new_year' }), now)
    assert.deepEqual(store.status(now).annualSchedules, before)
    store.update(body(), now)
    assert.deepEqual(store.status(now).annualSchedules, before, 'old five-field auto request cannot erase annual settings')
    store.update(body({ annualSchedules: [] }), now)
    assert.deepEqual(store.status(now).annualSchedules, []); assert.equal(store.snapshot(now).mode, 'auto')
})
test('annual runtime selection is inclusive to the full final second, crosses years, and does not persist when time advances', t => {
    const { db, cat, store, body, preserved } = fixture(t), before = preserved()
    const config = annual('christmas', '12-20 12:00:00', '01-05 23:59:59')
    store.update(body({ annualSchedules: [config] }), now)
    const raw = db.prepare('SELECT * FROM town_presentation_state').get(), audit = db.prepare('SELECT * FROM town_presentation_audit').all()
    for (const [when, matched] of [['2026-12-20T11:59:59', false], ['2026-12-20T12:00:00', true], ['2026-12-31T23:59:59', true],
        ['2027-01-01T00:00:00', true], ['2027-01-05T23:59:59.999', true], ['2027-01-06T00:00:00', false]]) {
        const stamp = at(when), status = store.status(stamp), snap = store.snapshot(stamp)
        assert.equal(status.mode, 'auto'); assert.equal(status.themeId, null)
        assert.equal(status.activeAnnualThemeId, matched ? 'christmas' : null, when)
        assert.equal(snap.mode, matched ? 'manual' : 'auto'); assert.equal(snap.theme_id, matched ? 'christmas' : null)
        assert.equal(snap.town_content_id, matched ? cat.find('christmas').nativeTownContentId : null)
    }
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), raw)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_audit').all(), audit)
    assert.deepEqual(preserved(), before)
})
test('same start/end is one second; leap days keep natural order and do not advance March 1 to February 29', t => {
    const { store, body } = fixture(t)
    store.update(body({ annualSchedules: [annual('spring', '03-01 00:00:00', '03-01 00:00:00')] }), now)
    assert.equal(store.snapshot(at('2028-02-29T00:00:00')).mode, 'auto')
    assert.equal(store.snapshot(at('2028-03-01T00:00:00.999')).theme_id, 'spring')
    assert.equal(store.snapshot(at('2028-03-01T00:00:01')).mode, 'auto')
    store.update(body({ annualSchedules: [annual('spring', '02-28 00:00:00', '03-01 23:59:59')] }), now)
    assert.equal(store.snapshot(at('2028-02-29T12:00:00')).theme_id, 'spring')
    assert.equal(store.snapshot(at('2027-03-02T00:00:00')).mode, 'auto')
})
test('manual always wins while auto resolves annual to the existing R11 manual wire format', t => {
    const { store, body } = fixture(t)
    store.update(body({ mode: 'manual', themeId: 'new_year', annualSchedules: [annual()] }), now)
    assert.equal(store.status(now).mode, 'manual'); assert.equal(store.status(now).activeAnnualThemeId, null)
    assert.equal(store.snapshot(now).theme_id, 'new_year')
    const next = store.update(body(), now)
    assert.equal(next.mode, 'auto'); assert.equal(next.activeAnnualThemeId, 'christmas')
    assert.deepEqual(Object.keys(store.snapshot(now)).sort(), ['schema_version', 'revision', 'mode', 'theme_id', 'town_content_id', 'catalog_digest'].sort())
    assert.equal(store.snapshot(now).mode, 'manual'); assert.equal(store.snapshot(now).theme_id, 'christmas')
})
test('duplicate, overlap, invalid dates, normal, unknown and unknown fields fail atomically with Chinese theme labels', t => {
    const { db, store, body } = fixture(t)
    const bad = [null, {}, 'bad', [annual('normal')], [annual('missing')], [annual('christmas', '02-29 00:00:00', '03-01 00:00:00')],
        [{ ...annual(), themeDigest: 'a'.repeat(64) }], [annual(), annual('christmas', '02-01 00:00:00', '02-02 00:00:00')],
        [annual('christmas', '12-20 00:00:00', '01-05 23:59:59'), annual('new_year', '01-05 23:59:59', '01-10 00:00:00')],
        [annual('christmas', '01-01 00:00:00', '12-31 23:59:59'), annual('spring', '03-01 00:00:00', '03-01 00:00:00')],
        Array(101).fill(annual())]
    for (const annualSchedules of bad) {
        assert.throws(() => store.update(body({ annualSchedules }), now), error => error.statusCode === 400)
        assert.equal(store.status(now).revision, 0)
    }
    assert.throws(() => store.update(body({ annualSchedules: [annual(), annual('new_year', '12-31 23:59:59', '01-05 23:59:59')] }), now), /圣诞.*新年.*重叠/)
    assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='town_presentation_state'").get(), undefined)
    assert.doesNotThrow(() => store.update(body({ annualSchedules: [annual(), annual('new_year', '01-01 00:00:00', '01-15 12:00:00')] }), now))
})
test('CAS, audit rollback, no-op and restart preserve annual identities and every player/clock/epoch table', t => {
    const { db, cat, store, body, preserved } = fixture(t), before = preserved()
    const request = body({ annualSchedules: [annual()] })
    store.update(request, now); assert.throws(() => store.update(request, now), TownThemeConflict)
    store.update(body({ annualSchedules: [annual()] }), now)
    assert.equal(store.status(now).revision, 1, 'same annual policy is a no-op')
    const original = db.prepare('SELECT * FROM town_presentation_state').get()
    db.exec("CREATE TRIGGER fail_annual_audit BEFORE INSERT ON town_presentation_audit BEGIN SELECT RAISE(ABORT,'annual audit failure'); END")
    assert.throws(() => store.update(body({ annualSchedules: [] }), now), /annual audit failure/)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), original)
    assert.equal(db.prepare('SELECT count(*) n FROM town_presentation_audit').get().n, 1)
    const copy = new Sqlite(db.serialize()); t.after(() => copy.close())
    const reopened = new TownThemeStore(copy, cat)
    assert.equal(reopened.snapshot(now).theme_id, 'christmas')
    assert.deepEqual(reopened.status(now).annualSchedules, [annual()])
    assert.deepEqual(preserved(), before)
    const stored = JSON.parse(original.value_json)
    assert.equal(stored.annualSchedules[0].themeDigest, cat.themeDigest('christmas'))
    assert.equal(Object.prototype.hasOwnProperty.call(store.status(now).annualSchedules[0], 'themeDigest'), false)
})
test('catalog additions/display changes preserve schedules; missing/changed themes remain visible with warnings until explicit repair', t => {
    const { db, store, body } = fixture(t)
    store.update(body({ annualSchedules: [annual(), annual('spring', '03-01 00:00:00', '03-31 23:59:59')] }), now)
    const raw = db.prepare('SELECT * FROM town_presentation_state').get()
    const expanded = catalog({ ids: ['normal', 'christmas', 'new_year', 'spring', 'sixth'], meta: 'new metadata', rename: true })
    const added = new TownThemeStore(db, expanded)
    assert.equal(added.snapshot(now).theme_id, 'christmas'); assert.deepEqual(added.status(now).annualWarnings, [])
    const changedCat = catalog({ changed: 'christmas' }), changed = new TownThemeStore(db, changedCat)
    assert.equal(changed.snapshot(now).mode, 'auto'); assert.equal(changed.status(now).annualWarnings[0].themeId, 'christmas')
    assert.equal(changed.status(now).annualSchedules.length, 2, 'invalid semantic bindings stay visible in the draft')
    assert.equal(changed.snapshot(at('2026-03-10T12:00:00')).theme_id, 'spring', 'unrelated valid entries still apply')
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), raw)
    const repaired = changed.update({ ...body(), catalogDigest: changedCat.digest, annualSchedules: changed.status(now).annualSchedules }, now)
    assert.deepEqual(repaired.annualWarnings, []); assert.equal(changed.snapshot(now).theme_id, 'christmas')
    const removedCat = catalog({ ids: ['normal', 'new_year', 'spring'] }), removed = new TownThemeStore(db, removedCat)
    assert.equal(removed.status(now).annualSchedules.length, 2); assert.equal(removed.status(now).annualWarnings[0].themeId, 'christmas')
    assert.match(removed.status(now).annualWarnings[0].message, /已失效主题/)
    assert.doesNotMatch(removed.status(now).annualWarnings[0].message, /christmas/)
    assert.throws(() => removed.update({ ...body(), expectedRevision: 2, catalogDigest: removedCat.digest, annualSchedules: removed.status(now).annualSchedules }), /未登记/)
    removed.update({ ...body(), expectedRevision: 2, catalogDigest: removedCat.digest, annualSchedules: [annual('spring', '03-01 00:00:00', '03-31 23:59:59')] }, now)
    assert.deepEqual(removed.status(now).annualWarnings, [])
})
test('malformed stored annual arrays safely degrade without an implicit repair', t => {
    const { db, store, body } = fixture(t)
    store.update(body({ annualSchedules: [annual()] }), now)
    const parsed = JSON.parse(db.prepare('SELECT value_json FROM town_presentation_state').get().value_json)
    parsed.annualSchedules[0].start = '02-29 00:00:00'
    db.prepare('UPDATE town_presentation_state SET value_json=?').run(JSON.stringify(parsed))
    const raw = db.prepare('SELECT * FROM town_presentation_state').get()
    assert.equal(store.snapshot(now).mode, 'auto'); assert.equal(store.status(now).degradedReason, 'town_theme_state_invalid')
    assert.throws(() => store.update(body({ annualSchedules: [] }), now), /持久状态/)
    assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), raw)
})
test('legacy selection-only requests preserve stale annual bindings and cannot implicitly reapprove changed resources', t => {
    const { db, store, body } = fixture(t)
    store.update(body({ annualSchedules: [annual()] }), now)
    const originalDigest = JSON.parse(db.prepare('SELECT value_json FROM town_presentation_state').get().value_json).annualSchedules[0].themeDigest
    const changedCat = catalog({ changed: 'christmas' }), changed = new TownThemeStore(db, changedCat)
    const request = extra => ({ ...body(), expectedRevision: changed.status(now).revision, catalogDigest: changedCat.digest, ...extra })
    changed.update(request({ mode: 'manual', themeId: 'new_year' }), now)
    assert.equal(changed.status(now).annualWarnings.length, 1)
    assert.equal(changed.snapshot(now).theme_id, 'new_year')
    assert.equal(JSON.parse(db.prepare('SELECT value_json FROM town_presentation_state').get().value_json).annualSchedules[0].themeDigest, originalDigest)
    changed.update(request({}), now)
    assert.equal(changed.snapshot(now).mode, 'auto'); assert.equal(changed.status(now).annualWarnings.length, 1)
    assert.deepEqual(changed.status(now).annualSchedules, [annual()])
    changed.update(request({ annualSchedules: [annual()] }), now)
    assert.equal(changed.status(now).annualWarnings.length, 0); assert.equal(changed.snapshot(now).theme_id, 'christmas')
    assert.equal(changed.status(now).revision, 4)
})
test('actual authenticated route accepts a bounded 100-window payload beyond 2 KiB and retains old request semantics', async t => {
    const ids = Array.from({ length: 100 }, (_, index) => 'theme_' + index), { db, store, body } = fixture(t, catalog({ ids }))
    const app = require('fastify')({ logger: false }); t.after(() => app.close())
    const previous = process.env.ADMIN_PANEL_PASSWORD; process.env.ADMIN_PANEL_PASSWORD = 'synthetic-calendar'
    require('../src/lib/management-auth.ts').installManagementAuth(app)
    if (previous === undefined) delete process.env.ADMIN_PANEL_PASSWORD; else process.env.ADMIN_PANEL_PASSWORD = previous
    await app.register(require('../src/routes/web_api/town-theme.ts').createTownThemeRoutes({ store: () => store, transaction: async fn => db.transaction(fn).immediate() }), { prefix: '/town' })
    const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: 'synthetic-calendar' } })
    const headers = { cookie: login.headers['set-cookie'].split(';')[0] }
    const schedules = ids.map((id, index) => { const time = `01-01 00:${String(Math.floor(index / 60)).padStart(2, '0')}:${String(index % 60).padStart(2, '0')}`; return annual(id, time, time) })
    assert.ok(JSON.stringify(schedules).length > 2048)
    const saved = await app.inject({ method: 'POST', url: '/town', headers, payload: body({ annualSchedules: schedules }) })
    assert.equal(saved.statusCode, 200, saved.body); assert.equal(saved.json().annualSchedules.length, 100)
    const kept = await app.inject({ method: 'POST', url: '/town', headers, payload: body({ mode: 'manual', themeId: ids[0] }) })
    assert.equal(kept.statusCode, 200); assert.equal(kept.json().annualSchedules.length, 100)
    const stale = await app.inject({ method: 'POST', url: '/town', headers, payload: body({ expectedRevision: 0, annualSchedules: [] }) })
    assert.equal(stale.statusCode, 409)
})
