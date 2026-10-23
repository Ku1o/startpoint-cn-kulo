// /load write-transaction budget and response stability.
//
// Each fixture runs in a child process with a frozen clock and a fresh
// database: a first /load initializes the save, the fixture then puts the
// save into a state that one of the load-time repairs handles, and the second
// /load is measured. The test asserts how many write transactions and COMMITs
// the second /load performs.
//
// Set CN_LOAD_BASELINE_ROOT to another build of this repository (a directory
// containing out/, assets/ and node_modules/) to additionally assert that the
// response bytes and the persisted player rows are identical to that build.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const crypto = require('node:crypto')
const { execFile } = require('node:child_process')
const { promisify } = require('node:util')
const { performance } = require('node:perf_hooks')

const FIXED_NOW = Date.parse('2026-10-10T04:00:00.000Z')
const FIXTURES = ['clean', 'daily', 'mana', 'abyss', 'mission', 'mission_closed', 'all']
const ABILITY_MISSION_ID = 11070

function freezeClock() {
    const RealDate = Date
    class FixedDate extends RealDate {
        constructor(...args) { if (args.length === 0) super(FIXED_NOW); else super(...args) }
        static now() { return FIXED_NOW }
    }
    global.Date = FixedDate
}

function countWrites(db) {
    const counts = { begins: 0, commits: 0, implicitWrites: 0, transactions: [] }
    let current = null
    const record = (sql, reader = false) => {
        const text = String(sql).trim().toUpperCase()
        if (text.startsWith('BEGIN')) {
            counts.begins++
            assert.equal(current, null, 'unexpected nested top-level transaction')
            current = { writeStatements: 0, tables: new Set() }
        } else if (text.startsWith('COMMIT')) {
            counts.commits++
            assert.ok(current, 'COMMIT without a measured BEGIN')
            counts.transactions.push({
                kind: current.writeStatements > 0 ? 'write' : 'read',
                writeStatements: current.writeStatements,
                tables: [...current.tables].sort(),
            })
            current = null
        } else if (!reader && !/^(SAVEPOINT|RELEASE|ROLLBACK)\b/.test(text)) {
            if (!db.inTransaction) counts.implicitWrites++
            else {
                assert.ok(current, 'write outside a measured transaction')
                current.writeStatements++
                const table = /^(?:INSERT(?: OR \w+)? INTO|UPDATE|DELETE FROM)\s+["`\[]?(\w+)/.exec(text)?.[1]
                if (table) current.tables.add(table)
            }
        }
    }
    const probe = db.prepare('SELECT 1')
    const proto = Object.getPrototypeOf(probe)
    const run = proto.run
    proto.run = function (...args) {
        record(this.source, this.reader)
        return run.apply(this, args)
    }
    const exec = db.exec
    db.exec = function (sql) {
        record(sql)
        return exec.call(this, sql)
    }
    return counts
}

function dumpPlayerRows(db, playerId) {
    const hash = crypto.createHash('sha256')
    const tables = db.prepare(`SELECT name FROM sqlite_master WHERE type='table' ORDER BY name`).all()
        .map(row => row.name)
    for (const table of tables) {
        const columns = db.prepare(`PRAGMA table_info("${table}")`).all().map(column => column.name)
        const owner = columns.includes('player_id') ? 'player_id' : (table === 'players' ? 'id' : null)
        if (owner === null) continue
        const order = columns.map(column => `"${column}"`).join(',')
        // SQLite's own clock (datetime('now')) is not frozen with the process clock.
        const rows = db.prepare(`SELECT * FROM "${table}" WHERE "${owner}"=? ORDER BY ${order}`).all(playerId)
            .map(row => { const copy = { ...row }; delete copy.updated_at; return copy })
        hash.update(table).update(JSON.stringify(rows))
        if (process.env.CN_LOAD_DUMP_DIR) {
            fs.appendFileSync(path.join(process.env.CN_LOAD_DUMP_DIR, 'rows.txt'), table + ' ' + JSON.stringify(rows) + '\n')
        }
    }
    return hash.digest('hex')
}

async function scenario(root, fixture) {
    freezeClock()
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'cn-load-writes-'))
    process.env.DATA_DIR = directory
    process.env.GACHA_SEED_DIR = path.join(directory, 'seeds')
    const out = name => require(path.join(root, 'out', name))
    const Fastify = require(path.join(root, 'node_modules', 'fastify'))
    const { pack } = require(path.join(root, 'node_modules', 'msgpackr'))
    const { getDb } = out('data/db')
    const players = out('data/domains/player')
    const characters = out('data/domains/character')
    const rush = out('data/domains/rushEvent')
    const account = out('data/domains/account').insertAccountSync({
        appId: 'wf_cn', idpAlias: '', idpCode: 'fixture', idpId: 'load-writes', status: 'normal',
    })
    const player = players.insertDefaultPlayerSync(account.id)
    out('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    const viewerId = 82000456
    const db = getDb()
    db.prepare('INSERT INTO sessions (token,account_id,expires,type) VALUES (?,?,?,2)')
        .run(String(viewerId), account.id, '2099-01-01T00:00:00Z')
    const ids = Object.keys(require(path.join(root, 'assets', 'character.json'))).map(Number)
        .slice(0, Number(process.env.CN_LOAD_CHARACTER_LIMIT || 40))
    db.transaction(() => {
        for (const id of ids) {
            if (!characters.playerOwnsCharacterSync(player.id, id)) characters.insertDefaultPlayerCharacterSync(player.id, id)
        }
    })()

    // Growth tasks have no comeback qualification. Explicitly open just this
    // original phase-one ability task in the synthetic operations store.
    const operations = out('lib/content-operations')
    const setMissionOpen = enabled => {
        const store = operations.contentOperations()
        const review = { readiness: 'verified', evidence: 'Synthetic original growth-task load repair', endsAtMs: null }
        store.update('active_mission_event:1', {
            expectedRevision: store.revision(), catalogDigest: store.digest,
            reason: 'Synthetic load write-budget fixture',
            actionOverrides: {
                visible: { ...review, enabled: true },
                enter: { ...review, enabled, missionKeys: [`0:${ABILITY_MISSION_ID}`] },
            },
        }, FIXED_NOW)
    }
    setMissionOpen(fixture !== 'mission_closed')
    const learnAbility = () => {
        const node = Object.entries(out('lib/assets').getCharacterManaNodesSync(ids[2], 1))
            .find(([, value]) => ['1', '2', '3'].includes(value.field6))
        assert.ok(node, 'fixture character needs an original ability node')
        return db.prepare('INSERT INTO players_characters_mana_nodes (value,character_id,player_id) VALUES (?,?,?)')
            .run(Number(node[0]), ids[2], player.id).changes
    }

    const app = Fastify({ logger: false })
    let captured = null
    app.addHook('onSend', async (_request, _reply, payload) => {
        captured = payload
        return typeof payload === 'object' && payload !== null && !Buffer.isBuffer(payload) ? JSON.stringify({}) : payload
    })
    await app.register(out('routes/cn/load').default, { prefix: '/api/index.php' })
    const load = async () => {
        captured = null
        const response = await app.inject({
            method: 'POST', url: '/api/index.php/load',
            headers: { 'content-type': 'application/json', res_ver: '1.4.117' },
            payload: JSON.stringify({ viewer_id: viewerId }),
        })
        assert.equal(response.statusCode, 200, response.body)
        return Buffer.from(pack(captured))
    }

    await load()
    // A save written by older code: every repair below has something to do.
    const applied = {}
    if (fixture === 'daily' || fixture === 'all') {
        db.prepare('UPDATE players SET last_login_time=? WHERE id=?')
            .run(new Date(FIXED_NOW - 36 * 3600 * 1000).toISOString(), player.id)
        applied.daily = 1
    }
    if (fixture === 'mana' || fixture === 'all') {
        applied.mana = db.prepare('DELETE FROM players_characters_bond_tokens WHERE player_id=? AND character_id IN (?,?)')
            .run(player.id, ids[0], ids[1]).changes
    }
    if (fixture === 'abyss' || fixture === 'all') {
        for (const eventId of [700099, 700100]) {
            if (rush.getPlayerRushEventSync(player.id, eventId) === null) {
                rush.insertPlayerRushEventSync(player.id, rush.getDefaultPlayerRushEventSync(eventId))
            }
        }
        applied.abyss = db.prepare('UPDATE players_rush_events SET tower_revision=NULL, active_rush_battle_folder_id=2 WHERE player_id=? AND event_id IN (700099,700100)')
            .run(player.id).changes
    }
    if (['mission', 'mission_closed', 'all'].includes(fixture)) applied.missionNode = learnAbility()
    if (fixture === 'units') {
        // Each repair helper used by /load, called on its own: no write
        // transaction when the save is current, exactly one when it is not.
        const progress = out('data/domains/abyss-tower-progress')
        const helpers = out('lib/character-helpers')
        const reconciliation = out('lib/mission/active-reconciliation')
        const { getContentSnapshot } = out('content/runtime/content-snapshot')
        const reconcile = () => reconciliation.reconcileActiveMissionFacts({
            playerId: player.id, repository: getContentSnapshot().repository, now: FIXED_NOW,
        })
        const calls = {
            abyss: () => progress.refreshPlayerAbyssTowersSync(player.id),
            mana: () => helpers.reconcilePlayerManaBoardCompletionSync(player.id),
            mission: reconcile,
        }
        const result = {}
        const counts = countWrites(db)
        const measure = (name, call) => {
            const begins = counts.begins
            const value = call()
            result[name] = counts.begins - begins
            return value
        }
        for (const [name, call] of Object.entries(calls)) measure(`${name}.clean`, call)
        for (const eventId of [700099, 700100]) {
            if (rush.getPlayerRushEventSync(player.id, eventId) === null) {
                rush.insertPlayerRushEventSync(player.id, rush.getDefaultPlayerRushEventSync(eventId))
            }
        }
        db.prepare('UPDATE players_rush_events SET tower_revision=NULL WHERE player_id=? AND event_id IN (700099,700100)').run(player.id)
        db.prepare('DELETE FROM players_characters_bond_tokens WHERE player_id=? AND character_id=?').run(player.id, ids[0])
        learnAbility()
        measure('abyss.repair', calls.abyss)
        measure('mana.repair', calls.mana)
        setMissionOpen(false)
        result.closedMissionDeltas = measure('mission.closed', calls.mission).length
        assert.equal(db.prepare('SELECT COUNT(*) AS n FROM players_active_missions WHERE player_id=? AND id=?')
            .get(player.id, ABILITY_MISSION_ID).n, 0, 'closed mission must not be resurrected')
        setMissionOpen(true)
        result.missionDeltas = measure('mission.repair', calls.mission).length
        for (const [name, call] of Object.entries(calls)) measure(`${name}.repaired`, call)
        result.towerRevisions = db.prepare('SELECT COUNT(*) AS n FROM players_rush_events WHERE player_id=? AND event_id IN (700099,700100) AND tower_revision IS NOT NULL').get(player.id).n
        result.abilityProgress = db.prepare('SELECT progress FROM players_active_missions WHERE player_id=? AND id=?')
            .get(player.id, ABILITY_MISSION_ID)?.progress ?? 0
        result.comebackRows = db.prepare('SELECT COUNT(*) AS n FROM players_active_missions WHERE player_id=? AND id=25002').get(player.id).n
        await app.close()
        db.close()
        return { fixture, units: result }
    }
    const before = dumpPlayerRows(db, player.id)

    const counts = countWrites(db)
    const startedAt = performance.now()
    const body = await load()
    const loadMs = performance.now() - startedAt
    const measured = { ...counts }
    const after = dumpPlayerRows(db, player.id)
    const abilityProgress = db.prepare('SELECT progress FROM players_active_missions WHERE player_id=? AND id=?')
        .get(player.id, ABILITY_MISSION_ID)?.progress ?? 0
    const comebackRows = db.prepare('SELECT COUNT(*) AS n FROM players_active_missions WHERE player_id=? AND id=25002').get(player.id).n
    await app.close()
    db.close()
    return {
        fixture, applied, counts: measured, abilityProgress, comebackRows,
        changed: before !== after,
        response: crypto.createHash('sha256').update(body).digest('hex'),
        rows: after,
        bytes: body.length,
        loadMs,
    }
}

async function runChild(root, fixture) {
    const { stdout } = await promisify(execFile)(process.execPath, [__filename, '--child', root, fixture], {
        windowsHide: true, timeout: 120000, maxBuffer: 10_000_000,
    })
    const line = stdout.split('\n').find(text => text.startsWith('RESULT '))
    assert.ok(line, stdout)
    return JSON.parse(line.slice('RESULT '.length))
}

if (process.argv[2] === '--child') {
    scenario(process.argv[3], process.argv[4]).then(result => {
        console.log('RESULT ' + JSON.stringify(result))
        process.exit(0)
    }, error => { console.error(error); process.exit(1) })
} else {
    const root = path.resolve(__dirname, '..')
    const baseline = process.env.CN_LOAD_BASELINE_ROOT
    test('load repair helpers open a write transaction only when they write', { timeout: 300000 }, async () => {
        const { units } = await runChild(root, 'units')
        console.log('UNITS ' + JSON.stringify(units))
        assert.deepEqual(units, {
            'abyss.clean': 0, 'mana.clean': 0, 'mission.clean': 0,
            'abyss.repair': 1, 'mana.repair': 1, 'mission.closed': 0, closedMissionDeltas: 0,
            'mission.repair': 1, missionDeltas: units.missionDeltas,
            'abyss.repaired': 0, 'mana.repaired': 0, 'mission.repaired': 0,
            towerRevisions: 2, abilityProgress: 1, comebackRows: 0,
        })
        assert.ok(units.missionDeltas > 0)
    })
    for (const fixture of FIXTURES) {
        test(`load write transactions: ${fixture}`, { timeout: 300000 }, async () => {
            const current = await runChild(root, fixture)
            console.log('CURRENT ' + JSON.stringify(current))
            for (const [name, rows] of Object.entries(current.applied)) {
                assert.ok(rows > 0, `fixture ${name} must change the save`)
            }
            // Save maintenance and successful-load acknowledgement each own
            // one write transaction. The intervening operations snapshot owns
            // a consistent read transaction, which must not count as a write.
            assert.equal(current.counts.begins, 3)
            assert.equal(current.counts.commits, 3)
            assert.equal(current.counts.implicitWrites, 0)
            assert.deepEqual(current.counts.transactions.map(row => row.kind), ['write', 'read', 'write'])
            assert.ok(current.counts.transactions[0].tables.includes('PLAYERS'))
            assert.deepEqual(current.counts.transactions[2].tables, ['CONTENT_CLIENT_RELOAD_ACK', 'CONTENT_CLIENT_RELOAD_PLAYS'])
            assert.equal(current.abilityProgress, ['mission', 'all'].includes(fixture) ? 1 : 0)
            assert.equal(current.comebackRows, 0, 'load must not grant comeback eligibility')
            assert.equal(current.changed, !['clean', 'mission_closed'].includes(fixture))
            if (baseline) {
                const reference = await runChild(path.resolve(baseline), fixture)
                console.log('BASELINE ' + JSON.stringify(reference))
                assert.equal(current.response, reference.response, 'response bytes')
                assert.equal(current.bytes, reference.bytes)
                assert.equal(current.rows, reference.rows, 'persisted rows')
            }
        })
    }
}
