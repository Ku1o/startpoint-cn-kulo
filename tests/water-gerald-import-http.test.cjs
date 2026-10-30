'use strict'
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { createHash, randomUUID } = require('node:crypto')
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'water-gerald-http-'))
Object.assign(process.env, { DATA_DIR: directory, CN_WRITER_THREAD: '0', MULTI_REALTIME_OWNER_CHILD: '0',
    MULTI_REALTIME_PROCESS: '0', GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false',
    GACHA_SEED_DIR: path.join(directory, 'seeds'), ADMIN_PANEL_PASSWORD: 'water-gerald-isolated-http-fixture' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const db = load('data/db').getDb(), saves = load('data/snapshots/player-snapshot')
const characters = load('data/domains/character'), claims = load('data/domains/water-gerald-claim')
const grant = load('lib/quest/finish/water-gerald-reward').grantWaterGeraldEx30Sync
const CHAR = 129989
let app, cookie
function player() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '',
        idpCode: 'water-gerald-http', idpId: randomUUID(), status: 'normal' })
    return load('data/domains/player').insertDefaultPlayerSync(account.id)
}
function award(p) {
    return grant({ playerId: p.id, questCategory: 24, questId: 700100030, questAccomplished: true,
        questData: { rushEventId: 700100, rushEventFolderId: 1, rushEventRound: 30 } })
}
function snapshot(p) { return saves.createPlayerSaveSnapshotV2Sync(p.id) }
function state(p) {
    return { tables: snapshot(p).data.tables,
        claims: claims.getWaterGeraldClaimsSync(p.id),
        character: characters.getPlayerCharacterSync(p.id, CHAR),
        wallet: db.prepare('SELECT free_mana,paid_mana,free_vmoney,vmoney,exp_pool FROM players WHERE id=?').get(p.id),
        progress: db.prepare('SELECT * FROM players_quest_progress WHERE player_id=? ORDER BY section,quest_id').all(p.id) }
}
function upload(p, archive, authenticated = true) {
    const boundary = `water-gerald-${randomUUID()}`
    return app.inject({ method: 'POST', url: `/api/player/save?id=${p.id}`,
        headers: { accept: 'application/json', 'content-type': `multipart/form-data; boundary=${boundary}`,
            ...(authenticated ? { cookie } : {}) },
        payload: Buffer.from(`--${boundary}\r\nContent-Disposition: form-data; name="file"; filename="water-gerald-save.json"\r\nContent-Type: application/json\r\n\r\n${JSON.stringify(archive)}\r\n--${boundary}--\r\n`) })
}
function oldV2(archive) {
    const copy = structuredClone(archive)
    delete copy.data.tables.players_water_gerald_claims
    const tables = saves.PLAYER_SNAPSHOT_V2_TABLES.filter(table => table !== 'players_water_gerald_claims')
    copy.schemaFingerprint = createHash('sha256').update(JSON.stringify(tables.map(table => ({ table,
        columns: db.prepare(`PRAGMA table_info("${table}")`).all().map(column => ({ name: column.name,
            type: column.type, notnull: column.notnull, defaultValue: column.dflt_value, pk: column.pk })) })))).digest('hex')
    copy.summary.includedTableCount = tables.length
    copy.summary.rowCount = Object.values(copy.data.tables).reduce((total, table) => total + table.rows.length, 0)
    return copy
}
before(async () => {
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    load('lib/management-auth').installManagementAuth(app)
    await app.register(require('@fastify/multipart'), { limits: { fileSize: 64 * 1024 * 1024, files: 1 } })
    await app.register(load('routes/web_api/player').default, { prefix: '/api/player' })
    await app.ready()
    const login = await app.inject({ method: 'POST', url: '/admin-login',
        payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
    assert.equal(login.statusCode, 200, login.body)
    cookie = login.headers['set-cookie'].split(';')[0]
})
after(async () => {
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db.open) db.close()
    assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
    fs.rmSync(directory, { recursive: true })
})

test('authenticated V2 upload rejects pre-claim archives with HTTP 400 and leaves character, claim, wallet and progress unchanged', async () => {
    const p = player(), preClaim = snapshot(p), old = oldV2(preClaim)
    assert.ok(award(p))
    db.prepare('UPDATE players SET free_vmoney=44444,free_mana=55555 WHERE id=?').run(p.id)
    load('data/domains/quest').insertPlayerQuestProgressSync(p.id, 24, { questId: 700100030,
        finished: true, bestElapsedTimeMs: 123, highScore: 999, clearRank: 5, leaderCharacterId: 1 })
    const before = state(p)
    const unauthenticated = await upload(p, preClaim, false)
    assert.equal(unauthenticated.statusCode, 401, unauthenticated.body)
    assert.deepEqual(state(p), before)
    for (const archive of [preClaim, old]) {
        const result = await upload(p, archive)
        assert.equal(result.statusCode, 400, result.body)
        assert.match(result.json().error, /水杰.*129989/)
        assert.match(result.json().error, /拒绝覆盖.*包含水杰的存档/)
        assert.deepEqual(state(p), before)
        assert.equal(award(p), null)
    }
})

test('a character-containing authenticated V2 archive restores normally without reopening the permanent reward', async () => {
    const p = player(); award(p)
    characters.updatePlayerCharacterSync(p.id, CHAR, { exp: 1234, overLimitStep: 2, evolutionLevel: 1, stack: 3 })
    characters.insertPlayerCharacterManaNodesSync(p.id, CHAR, [259978201])
    const archive = snapshot(p), claim = claims.getWaterGeraldClaimsSync(p.id)
    characters.updatePlayerCharacterSync(p.id, CHAR, { exp: 9999, overLimitStep: 4, stack: 7 })
    const result = await upload(p, archive)
    assert.equal(result.statusCode, 200, result.body)
    assert.equal(result.json().snapshotVersion, 2)
    const restored = characters.getPlayerCharacterSync(p.id, CHAR)
    assert.equal(restored.exp, 1234); assert.equal(restored.overLimitStep, 2)
    assert.equal(restored.evolutionLevel, 1); assert.equal(restored.stack, 3)
    assert.deepEqual(characters.getPlayerCharactersManaNodesSync(p.id)[CHAR], [259978201])
    assert.deepEqual(claims.getWaterGeraldClaimsSync(p.id), claim)
    assert.equal(award(p), null)
})

test('a spent source claim without its character is rejected for a fresh target and HTTP V1 remains unsupported', async () => {
    const source = player(), target = player(); award(source)
    const malformed = snapshot(source), table = malformed.data.tables.players_characters
    table.rows = table.rows.filter(row => row[table.columns.indexOf('id')] !== CHAR)
    malformed.summary.rowCount = Object.values(malformed.data.tables).reduce((total, entry) => total + entry.rows.length, 0)
    const before = state(target), result = await upload(target, malformed)
    assert.equal(result.statusCode, 400, result.body); assert.match(result.json().error, /水杰/)
    assert.deepEqual(state(target), before)
    const v1 = await upload(target, { schema: 'starpoint-cn-save', version: 1, data: {} })
    assert.equal(v1.statusCode, 400, v1.body); assert.match(v1.json().error, /仅支持 V2/)
    assert.deepEqual(state(target), before)
})
