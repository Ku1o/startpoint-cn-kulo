const fs = require('node:fs')
const path = require('node:path')
const { performance } = require('node:perf_hooks')

const root = path.resolve(__dirname, '..')
const load = file => require(path.join(root, 'out', file))
const { getDb } = load('data/db')
const { insertAccountSync, getAccountPlayersSync } = load('data/domains/account')
const players = load('data/domains/player')
const state = load('data/activeAccount')
const db = getDb()
const account = insertAccountSync({
    appId: 'wf_cn', idpAlias: '', idpCode: 'active-account-benchmark',
    idpId: 'active-account-benchmark', status: 'normal',
})
const player = players.insertDefaultPlayerSync(account.id)
state.saveAccountDefaultPlayer(account.id, player.id)
const stateFile = path.join(process.env.DATA_DIR, 'active_account.json')
const iterations = Math.max(100, Number(process.env.PERF_ITERATIONS || 10000))

function oldResolve() {
    const ids = getAccountPlayersSync(account.id)
    const parsed = JSON.parse(fs.readFileSync(stateFile, 'utf8'))
    const preferred = parsed.defaultPlayers[account.id]
    return preferred && ids.includes(preferred) ? preferred : ids[0]
}
function run(operation) {
    const cpu = process.cpuUsage()
    const started = performance.now()
    for (let index = 0; index < iterations; index++) {
        if (operation() !== player.id) throw Error('Player resolution mismatch')
    }
    const used = process.cpuUsage(cpu)
    return {
        wallMs: performance.now() - started,
        cpuMs: (used.user + used.system) / 1000,
    }
}
oldResolve()
state.resolvePlayerIdSync(account.id)
const disk = run(oldResolve)
const memory = run(() => state.resolvePlayerIdSync(account.id))
console.log(JSON.stringify({
    iterations, disk, memory,
    cpuReductionPct: (1 - memory.cpuMs / disk.cpuMs) * 100,
    wallReductionPct: (1 - memory.wallMs / disk.wallMs) * 100,
}, null, 2))
db.close()
