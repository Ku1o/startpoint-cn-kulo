// Deterministic synthetic settlement workload. Always owns an isolated database.
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { createHash } = require('node:crypto')
const { performance, monitorEventLoopDelay } = require('node:perf_hooks')
const output = process.argv[2]
const iterations = Number(process.env.PERF_ITERATIONS || 150)
const targetRps = Number(process.env.PERF_TARGET_RPS || 0)
const responseHash = createHash('sha256')
const root = path.resolve(process.argv[3] || process.env.PERF_MODULE_ROOT || path.join(__dirname, '..'))
const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-perf-fixture-'))
process.env.DATA_DIR = directory
process.env.GACHA_SEED_DIR = path.join(directory, 'seeds')
process.env.PROCESS_MEMORY_DIAGNOSTICS = 'false'
process.chdir(root)
const load = file => require(path.join(root, 'out', file))
const { getDb } = load('data/db')
const { insertAccountSync } = load('data/domains/account')
const players = load('data/domains/player')
const characters = load('data/domains/character')
const quests = load('data/domains/quest')
const facts = load('lib/mission/battle-facts')
const { settleMissionCategories } = load('lib/mission/settlement')
const { reconcileActiveMissionFacts } = load('lib/mission/active-reconciliation')
const { getContentSnapshot } = load('content/runtime/content-snapshot')
const db = getDb()
async function main() {
try {
const subject = players.insertDefaultPlayerSync(insertAccountSync({
    appId: 'wf_cn', idpAlias: '', idpCode: 'perf-fixture', idpId: 'synthetic', status: 'normal',
}).id)
const ids = Object.keys(require(path.join(root, 'assets/character.json'))).map(Number).slice(0, 600)
db.transaction(() => {
    for (const id of ids) if (!characters.playerOwnsCharacterSync(subject.id, id)) characters.insertDefaultPlayerCharacterSync(subject.id, id)
    for (let id = 1000001; id < 1001001; id++) if (!quests.getPlayerSingleQuestProgressSync(subject.id, 1, id)) quests.insertPlayerQuestProgressSync(subject.id, 1, {
        questId: id, finished: true, clearRank: 5, multiClearCount: 3, leaderCharacterId: ids[0],
    })
})()
const party = { characters: ids.slice(0, 3).map(id => ({ id })),
    unison_characters: ids.slice(3, 6).map(id => ({ id })), equipments: [] }
const when = new Date('2025-07-23T12:00:00.000Z')
const ctx = { playerId: subject.id, questCategory: 2, questId: 1030004,
    questAccomplished: true, clearTime: 45000, clearRank: 5, party,
    statistics: { clear_phase: 1, party, zones: [{ use_power_flip_count: 3, use_dash_count: 4 }] },
    player: players.getPlayerSync(subject.id), questPreviouslyCompleted: true, questProgress: { clearRank: 5 },
    isMulti: false }
const timings = { facts: [], mission: [], active: [], transaction: [] }
let prepareCalls = 0
const prepare = db.prepare
db.prepare = function(...args) { prepareCalls++; return prepare.apply(this, args) }
const measure = (name, fn, record) => {
    const start = performance.now(); const result = fn()
    if (record) timings[name].push(performance.now() - start)
    return result
}
function run(record) {
    return measure('transaction', () => db.transaction(() => {
        const recorded = measure('facts', () => facts.recordMissionBattleFacts(ctx, when), record)
        const scope = facts.buildBattleMissionSettlementScopes(recorded, [], [], ids.slice(0, 6))
        const mission = measure('mission', () => settleMissionCategories(subject.id, scope, when), record)
        const active = measure('active', () => reconcileActiveMissionFacts({ playerId: subject.id,
            repository: getContentSnapshot().repository, now: when,
            patterns: facts.getBattleActiveMissionPatterns(2) }), record)
        const result = { mission, active }
        responseHash.update(JSON.stringify(result))
        return result
    })(), record)
}
const describe = a => {
    const sorted = [...a].sort((a, b) => a - b)
    return { n: a.length, avgMs: a.reduce((x, y) => x + y, 0) / a.length,
        p50Ms: sorted[Math.ceil(a.length * .5) - 1], p95Ms: sorted[Math.ceil(a.length * .95) - 1], maxMs: sorted.at(-1) }
}
    for (let i = 0; i < 20; i++) run(false)
    prepareCalls = 0
    const arrivals = []
    const loop = monitorEventLoopDelay({resolution: 10})
    loop.enable()
    await new Promise(resolve => setTimeout(resolve, 30))
    const elu = performance.eventLoopUtilization()
    const start = performance.now(), cpu = process.cpuUsage()
    if (targetRps > 0) {
        await Promise.all(Array.from({length: iterations}, (_, i) => new Promise((resolve, reject) => {
            const due = start + i * 1000 / targetRps
            setTimeout(() => {
                try { run(true); arrivals.push(performance.now() - due); resolve() } catch (error) { reject(error) }
            }, Math.max(0, due - performance.now()))
        })))
    } else for (let i = 0; i < iterations; i++) run(true)
    const used = process.cpuUsage(cpu)
    const utilization = performance.eventLoopUtilization(elu).utilization
    loop.disable()
    const report = { runtime: process.version, fixture: { characters: ids.length, questRows: 1000 }, iterations,
        elapsedMs: performance.now() - start, cpuMs: (used.user + used.system) / 1000, prepareCalls,
        stages: Object.fromEntries(Object.entries(timings).map(([name, values]) => [name, describe(values)])) }
    if (targetRps > 0) report.load = { targetRps, arrivalLatency: describe(arrivals),
        eventLoopUtilization: utilization, eventLoopP99Ms: loop.percentile(99) / 1e6, eventLoopMaxMs: loop.max / 1e6 }
    const tables = ['players_category_missions', 'players_category_mission_stages', 'players_active_missions',
        'players_active_missions_stages', 'players_character_quest_clears', 'players_items', 'players_degrees',
        'players_mission_battle_counters', 'players_mission_counters', 'players_active_mission_battle_facts',
        'players_active_mission_battle_condition_facts']
    const available = new Set(db.prepare("SELECT name FROM sqlite_master WHERE type = 'table'").all().map(row => row.name))
    const state = Object.fromEntries(tables.filter(table => available.has(table)).map(table => [table,
        db.prepare(`SELECT * FROM ${table}`).all().map(row => Object.fromEntries(Object.entries(row)
            .filter(([key]) => !['created_at', 'updated_at', 'acquired_at'].includes(key)))).sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
    ]))
    report.correctness = {responseSha256: responseHash.digest('hex'),
        stateSha256: createHash('sha256').update(JSON.stringify(state)).digest('hex'),
        rows: Object.fromEntries(Object.entries(state).map(([table, rows]) => [table, rows.length]))}
    if (process.env.PERF_STATE_OUTPUT) fs.writeFileSync(process.env.PERF_STATE_OUTPUT, JSON.stringify(state, null, 2))
    if (output) fs.writeFileSync(output, JSON.stringify(report, null, 2))
    console.log(JSON.stringify(report, null, 2))
} finally {
    db.close()
    if (path.dirname(fs.realpathSync(directory)) !== fs.realpathSync(os.tmpdir())) throw Error('Invalid fixture cleanup boundary')
    fs.rmSync(directory, { recursive: true })
}
}
main().catch(error => { console.error(error); process.exitCode = 1 })
