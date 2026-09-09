/* Isolated, real HTTP workload plus a TCP event-loop probe. No production data.
 * node tools/bench-five-boss-concurrency.cjs --report <json> [--baseline <dir>] [--single-core]
 * Baseline directory contains only the prior committed out/ modules being changed;
 * all other modules and game masters are shared with the current build.
 */
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const assert = require('node:assert/strict')
const net = require('node:net')
const { fork, execFileSync } = require('node:child_process')
const { performance, monitorEventLoopDelay } = require('node:perf_hooks')
const repo = path.resolve(__dirname, '..')
const arg = name => process.argv[process.argv.indexOf(name) + 1]
const has = name => process.argv.includes(name)

function percentile(values, p) {
    if (!values.length) return null
    const sorted = [...values].sort((a, b) => a - b)
    return +sorted[Math.min(sorted.length - 1, Math.ceil(sorted.length * p) - 1)].toFixed(3)
}
function stats(values) {
    return { count: values.length, p50Ms: percentile(values, .5), p95Ms: percentile(values, .95),
        p99Ms: percentile(values, .99), maxMs: values.length ? +Math.max(...values).toFixed(3) : null }
}

async function worker() {
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-perf-'))
    process.env.DATA_DIR = dataDir
    process.env.ROUTE_PERF_SUMMARY = 'false'
    if (has('--baseline')) {
        const Module = require('node:module')
        const previous = Module._extensions['.js']
        const root = path.resolve(arg('--baseline'))
        Module._extensions['.js'] = (module, filename) => {
            const relative = path.relative(repo, filename)
            const old = path.join(root, relative)
            if (relative.startsWith('out' + path.sep) && fs.existsSync(old)) {
                module._compile(fs.readFileSync(old, 'utf8'), filename)
            } else previous(module, filename)
        }
    }
    // Domain imports have idle maintenance timers; they must not keep the
    // temporary harness alive after its HTTP listener has closed.
    const interval = global.setInterval
    global.setInterval = (...args) => { const timer = interval(...args); timer.unref(); return timer }
    const load = name => require(path.join(repo, 'out', name))
    const { getDb } = load('data/db')
    const db = getDb()
    const players = load('data/domains/player'), accounts = load('data/domains/account')
    const items = load('data/domains/item'), active = load('data/domains/quest_active')
    const ledger = load('data/domains/fiveBossGauntletRun'), options = load('data/domains/option')
    const { createRoom } = load('multi/room/manager')
    const { FIVE_BOSS_GAUNTLET: mode } = load('multi/five-boss/contract')
    const battle = load('multi/five-boss/battle-runtime')
    const singleRoutes = load('routes/api/singleBattleQuest').default
    const multiRoutes = load('multi/http/battle').registerBattleRoutes
    const optionRoutes = load('routes/api/option').default
    global.setInterval = interval
    let sequence = 0
    async function player() {
        const n = ++sequence
        const a = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'test', idpId: `perf-${n}`, status: 'normal' })
        const p = players.insertDefaultPlayerSync(a.id)
        load('data/activeAccount').saveAccountDefaultPlayer(a.id, p.id)
        players.updatePlayerSync({ id: p.id, stamina: 100, staminaHealTime: new Date() })
        items.setPlayerItemSync(p.id, mode.ticketItemId, 2)
        load('lib/character').givePlayerCharacterSync(p.id, 111001)
        const result = { id: p.id, accountId: a.id, viewerId: 781000000 + n, playId: `perf-play-${n}` }
        await load('data/domains/session').insertSessionWithToken({ token: String(result.viewerId), accountId: a.id,
            expires: new Date(Date.now() + 86400000), type: 2 })
        return result
    }
    const payload = p => ({ viewer_id: p.viewerId, play_id: p.playId, quest_id: mode.visibleQuestId,
        category: mode.category, is_accomplished: true, elapsed_time_ms: 30000, score: 100,
        statistics: { clear_phase: 1, max_combo_count: 0, party: { characters: [{ id: 111001 }],
            unison_characters: [], equipments: [], ability_soul_ids: [] } },
        add_mana: 0, continue_count: 0, api_count: 1,
        mate_player_result: (p.mateViewerIds ?? []).map(viewer_id => ({ viewer_id })) })
    const solos = [], finishers = [], failures = [], entrants = []
    for (let i = 0; i < 24; i++) {
        const p = await player(); solos.push(p)
        options.updatePlayerOptionsSync(p.id, { auto_play: false, sound: false })
        load('multi/five-boss/solo-runtime').startFiveBossSoloSync(p.id, p.playId, () =>
            active.insertPlayerActiveQuestSync(p.id, { playerId: p.id, playId: p.playId,
                category: mode.category, questId: mode.visibleQuestId, isMulti: false,
                continueCount: 0, startedAtMs: Date.now() }))
    }
    const historyRowsPerPlayer = has('--history') ? Number(arg('--history')) : 6000
    assert.ok(Number.isSafeInteger(historyRowsPerPlayer) && historyRowsPerPlayer >= 0 && historyRowsPerPlayer <= 10000)
    const insert = db.prepare(`INSERT INTO five_boss_solo_runs (player_id,play_id,status,auto_at_start,auto_used)
        VALUES (?,?,'settled',0,0)`)
    db.transaction(() => {
        for (const p of solos) for (let i = 0; i < historyRowsPerPlayer; i++) insert.run(p.id, `history-${i}`)
    })()
    for (let i = 0; i < 12; i++) {
        const members = [await player(), await player(), await player()]
        const host = members[0]
        const room = createRoom(host.viewerId, host.id, 1, mode.category, mode.visibleQuestId, 0, 111001)
        room.raising_state = 4
        room.mates = members.map(p => ({ viewer_id: p.viewerId, player_id: p.id, com_id: 0 }))
        room.member_viewer_ids = members.map(p => p.viewerId)
        room.member_player_ids = Object.fromEntries(members.map(p => [p.viewerId, p.id]))
        room.five_boss_runtime = { runId: `perf-run-${i}`, expectedRealPlayerIds: members.map(p => p.id),
            autoplayModeByPlayerId: Object.fromEntries(members.map(p => [p.id, true])),
            partyCharacterIdsByPlayerId: Object.fromEntries(members.map(p => [p.id, [111001]])), battleIdentityByViewerId: {} }
        for (const p of members) {
            p.mateViewerIds = members.filter(other => other !== p).map(other => other.viewerId)
            const identity = { playerId: p.id, clientPlayId: p.playId, requestRoomNumber: room.room_number,
                requestCategory: mode.category, requestQuestId: mode.visibleQuestId }
            const body = { ...payload(p), room_number: room.room_number, party_id: 1,
                use_boost_point: false, use_boss_boost_point: false, is_auto_start_mode: true,
                mate_player_ids: [], mate_party_ids: [], combat_power: 1 }
            if (i < 4) entrants.push({ p, body })
            else {
                battle.startFiveBossBattle({ ...identity, room, useBoostPoint: false, useBossBoostPoint: false })
                if (i < 8) {
                    for (const signal of ['level_next', 'finalize']) ledger.recordMemberBattleSignalSync({
                        runId: room.five_boss_runtime.runId, playerId: p.id, roomNumber: room.room_number, signal })
                    finishers.push(p)
                } else failures.push(p)
            }
        }
    }
    const app = require('fastify')({ logger: false })
    const { pack } = require('msgpackr')
    // Extract this pure function without booting the production server or its
    // schedulers. Include its CPU cost in both sides of the comparison.
    const serverCode = fs.readFileSync(path.join(repo, 'out/cn-server.js'), 'utf8')
    const serializerStart = serverCode.indexOf('function fixUint32Tags(')
    const serializerEnd = serverCode.indexOf('function appendVaryAcceptEncoding(', serializerStart)
    assert.ok(serializerStart >= 0 && serializerEnd > serializerStart)
    const fixUint32Tags = new Function('Buffer', serverCode.slice(serializerStart, serializerEnd)
        + '\nreturn fixUint32Tags;')(Buffer)
    app.addHook('onSend', (_req, reply, body, done) => {
        if (String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object') {
            const packed = pack(body)
            done(null, fixUint32Tags(packed).toString('base64'))
        } else done(null, body)
    })
    await app.register(singleRoutes, { prefix: '/solo' })
    await app.register(async scoped => { multiRoutes(scoped) }, { prefix: '/multi' })
    await app.register(optionRoutes, { prefix: '/option' })
    app.get('/probe', async () => ({ ok: true }))
    const address = await app.listen({ port: 0, host: '127.0.0.1' })
    const tcp = net.createServer(socket => socket.on('data', data => socket.write(data)))
    await new Promise(resolve => tcp.listen(0, '127.0.0.1', resolve))
    let measuring = false, prepares = 0, diagnosticReads = 0, logLines = 0
    const prepare = db.prepare
    db.prepare = function (sql) {
        if (measuring) {
            prepares++
            if (/SELECT started_at, aborted_at, level_next_at, finalized_at/.test(sql)) diagnosticReads++
        }
        return prepare.call(this, sql)
    }
    for (const method of ['log', 'warn', 'error']) {
        const write = console[method].bind(console)
        console[method] = (...args) => { if (measuring) logLines++; write(...args) }
    }
    const monitor = monitorEventLoopDelay({ resolution: 10 })
    let cpuStart, eluStart, startTime
    process.on('message', async message => {
        if (message === 'begin') {
            monitor.enable(); monitor.reset()
            cpuStart = process.cpuUsage(); eluStart = performance.eventLoopUtilization(); startTime = performance.now()
            measuring = true
            process.send({ type: 'begun' })
        } else if (message === 'end') {
            const cpu = process.cpuUsage(cpuStart), elu = performance.eventLoopUtilization(eluStart)
            const metrics = { wallMs: performance.now() - startTime, cpuMs: (cpu.user + cpu.system) / 1000,
                eventLoopUtilization: elu.utilization, loopP99Ms: monitor.percentile(99) / 1e6,
                loopMaxMs: monitor.max / 1e6, prepares, diagnosticReads, logLines }
            measuring = false; monitor.disable()
            for (const p of solos) assert.equal(load('multi/five-boss/solo-runtime').getFiveBossSoloRewardMultiplierSync(p.id, p.playId), 1)
            for (const p of finishers) assert.equal(items.getPlayerItemSync(p.id, 10000145), 5)
            for (const p of failures) assert.equal(items.getPlayerItemSync(p.id, 10000145), null)
            for (const { p } of entrants) assert.ok(active.getPlayerActiveQuestSync(p.id)?.isMulti)
            process.send({ type: 'metrics', metrics })
        } else if (message === 'stop') {
            await app.close()
            tcp.close()
            db.close()
            const resolved = path.resolve(dataDir)
            assert.ok(resolved.startsWith(path.resolve(os.tmpdir()) + path.sep) && path.basename(resolved).startsWith('starpoint-perf-'))
            fs.rmSync(resolved, { recursive: true, force: true })
            process.exit(0)
        }
    })
    const tasks = []
    for (let round = 0; round < 16; round++) {
        for (const p of solos) tasks.push({ kind: 'option', url: '/option/update_in_battle', status: 200,
            body: { viewer_id: p.viewerId, api_count: round + 1, option_params: { auto_play: 1, sound: 0 } } })
        for (const p of finishers) tasks.push({ kind: 'finish', url: '/multi/finish', status: 200, body: payload(p) })
        for (const p of failures) tasks.push({ kind: 'rejected_finish', url: '/multi/finish', status: 400, body: payload(p) })
        for (const { body } of entrants) tasks.push({ kind: 'start', url: '/multi/start', status: 200, body })
    }
    process.send({ type: 'ready', address, tcpPort: tcp.address().port, tasks, dataDir,
        fixture: { soloPlayers: solos.length, historyRowsPerPlayer, historicalRows: solos.length * historyRowsPerPlayer,
            rooms: 12, roomMembers: 3, requests: tasks.length } })
}

async function main() {
    assert.ok(has('--report'), '--report is required')
    const destination = path.resolve(arg('--report'))
    fs.mkdirSync(path.dirname(destination), { recursive: true })
    const results = []
    const versions = has('--baseline') ? ['before', 'after'] : ['after']
    if (has('--reverse')) versions.reverse()
    for (const version of versions) {
        const output = fs.openSync(destination + '.' + version + '.log', 'w')
        const args = ['--worker', ...(has('--history') ? ['--history', arg('--history')] : []),
            ...(version === 'before' ? ['--baseline', path.resolve(arg('--baseline'))] : [])]
        const child = fork(__filename, args, { cwd: repo, stdio: ['ignore', output, output, 'ipc'], windowsHide: true })
        const messages = [], waiting = new Map()
        child.on('message', m => { const callback = waiting.get(m.type); if (callback) { waiting.delete(m.type); callback.resolve(m) } else messages.push(m) })
        child.on('exit', code => {
            if (code !== 0) for (const callback of waiting.values()) callback.reject(new Error(`worker exited ${code}; see ${destination}.${version}.log`))
        })
        const message = type => {
            const index = messages.findIndex(m => m.type === type)
            if (index >= 0) return Promise.resolve(messages.splice(index, 1)[0])
            return new Promise((resolve, reject) => {
                const timeout = setTimeout(() => reject(new Error(`worker timeout waiting for ${type}`)), 60000)
                waiting.set(type, { resolve: value => { clearTimeout(timeout); resolve(value) },
                    reject: error => { clearTimeout(timeout); reject(error) } })
            })
        }
        let affinity = null, socket, timer
        try {
            if (has('--single-core')) {
                assert.equal(process.platform, 'win32', 'single-core mode currently supports Windows')
                affinity = execFileSync('powershell.exe', ['-NoProfile', '-Command',
                    `$benchProcess = Get-Process -Id ${child.pid}; $benchMask = [int64]$benchProcess.ProcessorAffinity; $benchCore = $benchMask -band (-$benchMask); $benchProcess.ProcessorAffinity = [IntPtr]$benchCore; $benchProcess.ProcessorAffinity.ToInt64()`],
                { encoding: 'utf8', windowsHide: true }).trim()
            }
            const ready = await message('ready')
            // Warm up transport/serialization without changing the measured players.
            for (let i = 0; i < 20; i++) await (await fetch(ready.address + '/probe')).arrayBuffer()
            socket = net.connect(ready.tcpPort, '127.0.0.1')
            socket.setNoDelay(true)
            await new Promise(resolve => socket.once('connect', resolve))
            const probe = [], pending = new Map(), latencies = {}
            let seq = 0, buffered = ''
            socket.on('data', data => {
                buffered += data.toString()
                let end
                while ((end = buffered.indexOf('\n')) >= 0) {
                    const id = Number(buffered.slice(0, end)); buffered = buffered.slice(end + 1)
                    if (pending.has(id)) { probe.push(performance.now() - pending.get(id)); pending.delete(id) }
                }
            })
            child.send('begin'); await message('begun')
            timer = setInterval(() => { const id = ++seq; pending.set(id, performance.now()); socket.write(id + '\n') }, 10)
            let cursor = 0
            await Promise.all(Array.from({ length: 24 }, async () => {
                while (cursor < ready.tasks.length) {
                    const task = ready.tasks[cursor++], start = performance.now()
                    const response = await fetch(ready.address + task.url, { method: 'POST',
                        headers: { 'content-type': 'application/json' }, body: JSON.stringify(task.body) })
                    const body = await response.text()
                    assert.equal(response.status, task.status, task.kind + ': ' + body)
                    ;(latencies[task.kind] ??= []).push(performance.now() - start)
                }
            }))
            clearInterval(timer)
            await new Promise(resolve => setTimeout(resolve, 30))
            assert.equal(pending.size, 0, 'TCP probe responses must all return')
            child.send('end')
            const { metrics } = await message('metrics')
            socket.destroy()
            child.send('stop')
            await new Promise((resolve, reject) => child.once('exit', code => code === 0 ? resolve() : reject(new Error(`worker exited ${code}`))))
            results.push({ version, affinity, fixture: ready.fixture, concurrency: 24, ...metrics,
                http: Object.fromEntries(Object.entries(latencies).map(([key, values]) => [key, stats(values)])), tcpProbe: stats(probe) })
        } finally {
            clearInterval(timer); socket?.destroy()
            if (child.exitCode === null) child.kill()
            fs.closeSync(output)
        }
    }
    const report = { platform: process.platform, node: process.version, cpu: os.cpus()[0].model,
        limitations: ['Synthetic local fixture, not a cloud capacity claim.',
            'TCP echo measures shared event-loop responsiveness, not full game client protocol.',
            'Historical rows and error retries are deliberately concentrated.'], results }
    fs.writeFileSync(destination, JSON.stringify(report, null, 2) + '\n')
    console.log(JSON.stringify(report, null, 2))
}

;(has('--worker') ? worker() : main()).catch(error => { console.error(error); process.exit(1) })
