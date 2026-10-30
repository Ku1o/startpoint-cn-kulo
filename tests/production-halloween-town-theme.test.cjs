'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { spawnSync } = require('node:child_process')
const { randomUUID } = require('node:crypto')
const { unpack } = require('msgpackr')
const repository = path.resolve(__dirname, '..')
const out = process.env.STARPOINT_TEST_OUT_DIR || path.join(repository, 'out')
const load = name => require(path.join(out, name))
const historicalFixture = path.join(__dirname, 'fixtures/town-theme-1.4.258')
const HALLOWEEN = 'halloween2026', NATIVE = 103
const BGM = 'bgm/common/worldflipper_town_quest_spring'
const originalPeriod = { nativeTownContentId: NATIVE, kind: 'event', start: '2026-10-31 00:00:00', end: '2026-10-31 23:59:59' }

test('frozen Halloween town catalog keeps historical bindings and reaches real authenticated administration and ordinary load', { timeout: 45000 }, async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'production-halloween-town-'))
    Object.assign(process.env, { DATA_DIR: directory, ADMIN_PANEL_PASSWORD: 'production-halloween-town-fixture',
        CN_WRITER_THREAD: '0', MULTI_REALTIME_PROCESS: '0', MULTI_REALTIME_OWNER_CHILD: '0',
        MULTI_BATTLE_RELAY_PROCESS: '0', GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false',
        GACHA_SEED_DIR: path.join(directory, 'seeds') })
    fs.mkdirSync(process.env.GACHA_SEED_DIR)
    let db, app
    const timers = []
    try {
        const catalogApi = load('lib/town-theme-catalog')
        const { TownThemeStore } = load('lib/town-theme-store')
        const catalog = load('lib/town-theme').townThemeCatalog()
        assert.equal(catalog.degradedReason, null, 'run only after real frozen catalog, receipt and manifest have been copied together')
        const listing = catalog.listing()
        assert.equal(listing.length, 6)
        assert.equal(listing[5].id, HALLOWEEN, 'new theme is the sixth dynamic catalog entry')
        const halloween = catalog.find(HALLOWEEN)
        assert.equal(halloween.nativeTownContentId, NATIVE)
        assert.equal(halloween.name, '万圣节主城')
        assert.equal(halloween.description, '南瓜烟花、散落糖果与蝙蝠；默认播放春季／樱花主题曲')
        assert.equal(halloween.nativeRow[1], '1', 'keep native Event, not a newly invented manual-only kind')
        assert.equal(halloween.nativeRow[2], originalPeriod.start); assert.equal(halloween.nativeRow[3], originalPeriod.end)
        assert.deepEqual(halloween.originalPeriods, [originalPeriod], 'original Event metadata must not become an annual schedule')
        assert.equal(listing[5].annualEligible, true)
        assert.match(halloween.nativeRow[6], /^town\/background\//)
        assert.match(halloween.nativeRow[7], /^town\/background\//)
        assert.match(halloween.nativeRow[9], /^town\/particle\//)
        assert.equal(halloween.nativeRow[19], BGM)
        const receipt = JSON.parse(fs.readFileSync(path.join(repository, 'assets/town_theme_resource_receipt.json')))
        const evidence = receipt.themes.find(row => row.id === HALLOWEEN)
        assert.ok(evidence?.verified)
        const requiredResources = [halloween.nativeRow[6] + '.png', halloween.nativeRow[7] + '.png',
            halloween.nativeRow[9] + '.parts.amf3.deflate', halloween.nativeRow[9] + '.timeline.amf3.deflate', BGM + '.mp3']
        if (halloween.nativeRow[8] !== '(None)') requiredResources.push(halloween.nativeRow[8] + '.png')
        for (const resource of requiredResources) assert.ok(evidence.resources.some(row => row.path === resource), resource)

        // Build a valid historical catalog from exact preserved bytes. Do not
        // fabricate hashes or accept an invalid legacy loader just to compare IDs.
        const oldRoot = path.join(directory, 'old-assets')
        fs.mkdirSync(path.join(oldRoot, 'asset-patch'), { recursive: true })
        fs.mkdirSync(path.join(oldRoot, 'town_theme_thumbnails'))
        for (const name of ['town_themes.json', 'town_theme_resource_receipt.json'])
            fs.copyFileSync(path.join(historicalFixture, name), path.join(oldRoot, name))
        fs.copyFileSync(path.join(historicalFixture, 'manifest.json'), path.join(oldRoot, 'asset-patch/manifest.json'))
        const oldMetadata = JSON.parse(fs.readFileSync(path.join(oldRoot, 'town_themes.json')))
        assert.equal(oldMetadata.themes.length, 5)
        for (const theme of oldMetadata.themes) fs.copyFileSync(path.join(repository, 'assets/town_theme_thumbnails', theme.thumbnail.file),
            path.join(oldRoot, 'town_theme_thumbnails', theme.thumbnail.file))
        const oldCatalog = catalogApi.loadTownThemeCatalog(oldRoot)
        assert.equal(oldCatalog.degradedReason, null, 'historical 258 catalog must pass actual receipt and thumbnail validation')
        for (const old of oldMetadata.themes) {
            const current = catalog.find(old.id)
            assert.ok(current)
            assert.equal(catalog.themeDigest(old.id), oldCatalog.themeDigest(old.id), `unchanged semantic binding: ${old.id}`)
            for (const field of ['name', 'description', 'nativeTownContentId', 'nativeRow', 'originalPeriods', 'thumbnail'])
                assert.deepEqual(current[field], oldCatalog.find(old.id)[field], `old theme preserved: ${old.id}.${field}`)
        }

        db = load('data/db').getDb()
        assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
        const accounts = load('data/domains/account'), players = load('data/domains/player')
        const a = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'production-town', idpId: randomUUID(), status: 'normal' })
        const player = players.insertDefaultPlayerSync(a.id), viewer = 885000000 + player.id
        load('data/activeAccount').saveAccountDefaultPlayer(a.id, player.id)
        db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), a.id, '2099-01-01T00:00:00Z')
        const currentDay = load('lib/town-theme-calendar').beijingAnnualTime(Date.now()).slice(0, 5)
        const spareDays = ['01-02', '01-03', '01-04'].filter(day => day !== currentDay)
        const annual = (themeId, day) => ({ themeId, start: day + ' 00:00:00', end: day + ' 23:59:59' })
        const oldAnnual = annual('spring', spareDays[0])
        const oldStore = new TownThemeStore(db, oldCatalog)
        oldStore.update({ expectedRevision: 0, catalogDigest: oldCatalog.digest, mode: 'manual', themeId: 'christmas',
            confirmation: 'APPLY_TOWN_THEME', annualSchedules: [oldAnnual] })
        const historicalState = db.prepare('SELECT * FROM town_presentation_state').get()
        const historicalAudit = db.prepare('SELECT * FROM town_presentation_audit ORDER BY revision').all()

        let loadRoutes
        const originalInterval = global.setInterval
        try {
            global.setInterval = (...args) => { const timer = originalInterval(...args); timers.push(timer); return timer }
            loadRoutes = load('routes/cn/load').default
        } finally { global.setInterval = originalInterval }
        app = require('fastify')({ logger: false })
        load('lib/management-auth').installManagementAuth(app)
        load('lib/persistence-http-errors').installPersistenceHttpErrors(app)
        const { CnResponseWorkerPool } = load('lib/cn-response-worker-pool')
        load('lib/cn-response-hook').installCnResponseEncoding(app, { pool: new CnResponseWorkerPool({ size: 0 }), compression: { mode: 'off' } })
        await app.register(load('routes/web_api/town-theme').default, { prefix: '/api/server/town-theme' })
        await app.register(loadRoutes, { prefix: '/cn' })
        await app.ready()
        const endpoint = '/api/server/town-theme'
        assert.equal((await app.inject({ url: endpoint })).statusCode, 401)
        assert.equal((await app.inject({ method: 'POST', url: endpoint, payload: {} })).statusCode, 401)
        const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
        assert.equal(login.statusCode, 200, login.body)
        const headers = { cookie: login.headers['set-cookie'].split(';')[0] }
        const status = async () => {
            const response = await app.inject({ url: endpoint, headers })
            assert.equal(response.statusCode, 200, response.body)
            return response.json()
        }
        const nonThemeState = () => Object.fromEntries(db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' AND name NOT IN('town_presentation_state','town_presentation_audit') ORDER BY name")
            .all().map(({ name }) => [name, db.prepare(`SELECT * FROM "${name.replaceAll('"', '""')}"`).all()
                .sort((left, right) => JSON.stringify(left).localeCompare(JSON.stringify(right)))]))
        const post = async (payload, code = 200) => {
            const before = nonThemeState(), response = await app.inject({ method: 'POST', url: endpoint, headers, payload })
            assert.equal(response.statusCode, code, response.body)
            assert.deepEqual(nonThemeState(), before, 'admin theme update cannot touch player, clock, activity, save or reload-epoch state')
            return response.json()
        }
        const payload = (state, overrides = {}) => ({ expectedRevision: state.revision, catalogDigest: state.catalogDigest,
            mode: state.mode, themeId: state.themeId, confirmation: 'APPLY_TOWN_THEME', ...overrides })
        const normalLoad = async expected => {
            const response = await app.inject({ method: 'POST', url: '/cn/load', payload: { viewer_id: viewer }, headers: { device: 'android' } })
            assert.equal(response.statusCode, 200, response.body)
            const decoded = unpack(Buffer.from(response.body, 'base64'))
            assert.equal(decoded.data_headers.result_code, 1)
            const data = decoded.data
            assert.equal(data.town_presentation_load, true)
            assert.equal(data.town_presentation.theme_id, expected)
            assert.equal(data.town_presentation.catalog_digest, catalog.digest)
            assert.deepEqual(Object.keys(data.town_presentation).sort(),
                ['schema_version', 'revision', 'mode', 'theme_id', 'town_content_id', 'catalog_digest'].sort(), 'preserve the scalar snapshot protocol')
            assert.equal(data.town_presentation.town_content_id, expected === null ? null : catalog.find(expected).nativeTownContentId)
            if (expected === HALLOWEEN) {
                assert.equal(data.town_presentation.town_content_id, NATIVE)
                assert.equal(catalog.find(expected).nativeRow[19], BGM, 'the load native ID resolves the real frozen default curve')
            }
            return data
        }

        let state = await status()
        assert.equal(state.themes.length, 6); assert.equal(state.mode, 'manual'); assert.equal(state.themeId, 'christmas')
        assert.deepEqual(state.annualSchedules, [oldAnnual]); assert.deepEqual(state.annualWarnings, [])
        assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), historicalState)
        assert.deepEqual(db.prepare('SELECT * FROM town_presentation_audit ORDER BY revision').all(), historicalAudit)
        await normalLoad('christmas')
        assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), historicalState, 'ordinary load cannot silently rebind the historical catalog digest')
        const imageUrl = state.themes.find(row => row.id === HALLOWEEN).thumbnailUrl
        assert.equal((await app.inject({ url: imageUrl })).statusCode, 401)
        const thumbnail = await app.inject({ url: imageUrl, headers })
        assert.equal(thumbnail.statusCode, 200, thumbnail.body)
        assert.deepEqual(thumbnail.rawPayload, catalog.thumbnail(halloween.thumbnail.sha256))

        const request = payload(state, { mode: 'manual', themeId: HALLOWEEN })
        const beforeConcurrent = nonThemeState()
        const concurrent = await Promise.all([1, 2].map(() => app.inject({ method: 'POST', url: endpoint, headers, payload: request })))
        assert.deepEqual(concurrent.map(response => response.statusCode).sort(), [200, 409])
        assert.deepEqual(nonThemeState(), beforeConcurrent)
        state = await status(); assert.deepEqual(state.annualSchedules, [oldAnnual])
        await normalLoad(HALLOWEEN)
        await post(payload(state, { catalogDigest: '0'.repeat(64), mode: 'manual', themeId: 'spring' }), 409)
        state = await post(payload(state, { mode: 'manual', themeId: 'spring' }))
        await normalLoad('spring')
        state = await post(payload(state, { mode: 'auto', themeId: null }))
        assert.deepEqual(state.annualSchedules, [oldAnnual])
        await normalLoad(null)

        state = await post(payload(state, { annualSchedules: [oldAnnual, annual(HALLOWEEN, currentDay)] }))
        assert.equal(state.mode, 'auto'); assert.equal(state.activeAnnualThemeId, HALLOWEEN)
        await normalLoad(HALLOWEEN)
        state = await post(payload(state, { annualSchedules: [oldAnnual, annual(HALLOWEEN, spareDays[1])] }))
        assert.equal(state.activeAnnualThemeId, null)
        await normalLoad(null)

        const annualHalloween = annual(HALLOWEEN, '10-31')
        state = await post(payload(state, { annualSchedules: [oldAnnual, annualHalloween] }))
        assert.deepEqual(state.themes.find(row => row.id === HALLOWEEN).originalPeriods, [originalPeriod])
        const store = load('lib/town-theme').townThemeStore()
        const boundary = [
            ['2026-10-30T23:59:59+08:00', null], ['2026-10-31T00:00:00+08:00', HALLOWEEN],
            ['2026-10-31T23:59:59.999+08:00', HALLOWEEN], ['2026-11-01T00:00:00+08:00', null],
        ]
        for (const [time, expected] of boundary) assert.equal(store.snapshot(Date.parse(time)).theme_id, expected)
        const persisted = db.prepare('SELECT * FROM town_presentation_state').get()
        const reopened = spawnSync(process.execPath, ['-e', `
            const assert=require('node:assert/strict'),path=require('node:path');
            const load=name=>require(path.join(${JSON.stringify(path.resolve(out))},name));
            const db=load('data/db').getDb(),theme=load('lib/town-theme');
            assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(),${JSON.stringify(persisted)});
            const status=theme.townThemeStore().status();assert.equal(status.mode,'auto');
            assert.deepEqual(status.annualSchedules,${JSON.stringify([oldAnnual, annualHalloween].sort((a, b) => a.themeId.localeCompare(b.themeId)))});
            assert.deepEqual(status.annualWarnings,[]);
            assert.equal(theme.townThemeLoginSnapshot(Date.parse('2026-10-31T12:00:00+08:00')).theme_id,${JSON.stringify(HALLOWEEN)});
            assert.equal(theme.townThemeLoginSnapshot(Date.parse('2026-11-01T00:00:00+08:00')).theme_id,null);
            db.close();console.log('TOWN_POLICY_REOPENED_WITHOUT_REBIND');
        `], { cwd: repository, env: process.env, encoding: 'utf8', timeout: 15000, windowsHide: true })
        assert.equal(reopened.error, undefined); assert.equal(reopened.status, 0, reopened.stderr + reopened.stdout)
        assert.match(reopened.stdout, /TOWN_POLICY_REOPENED_WITHOUT_REBIND/)
        assert.deepEqual(db.prepare('SELECT * FROM town_presentation_state').get(), persisted)
        assert.equal(db.pragma('integrity_check', { simple: true }), 'ok'); assert.deepEqual(db.pragma('foreign_key_check'), [])
    } finally {
        if (app) await app.close()
        for (const timer of timers) clearInterval(timer)
        if (db) {
            await load('multi/npc/player-party-pool').stopQuestNpcPartyPoolWorker()
            await load('lib/seed-validator').default.close()
            if (db.open) db.close()
        }
        assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
        assert.ok(path.basename(directory).startsWith('production-halloween-town-'))
        fs.rmSync(directory, { recursive: true })
    }
})
