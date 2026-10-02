const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const diagnostics = require('../out/lib/realtime-diagnostics.js')

test('realtime diagnostics stays basic until a bounded room trace is requested', () => {
    diagnostics.configureRealtimeDiagnostics({ mode: 'basic' })
    diagnostics.recordRealtimeDiagnostic('room-a', 'ignored')
    assert.equal(diagnostics.getRealtimeDiagnostics().bufferedEvents, 0)

    const configured = diagnostics.configureRealtimeDiagnostics({
        mode: 'room-trace', roomNumber: 'room-a', ttlMs: 30_000, maxEvents: 16,
    })
    assert.equal(configured.mode, 'room-trace')
    diagnostics.recordRealtimeDiagnostic('room-b', 'ignored')
    diagnostics.recordRealtimeDiagnostic('room-a', 'relay', { recipients: 2 })
    diagnostics.recordRealtimeDiagnostic('room-a', 'barrier', { ready: 3 })
    for (let i = 0; i < 15; i++) diagnostics.recordRealtimeDiagnostic('room-a', `event-${i}`)
    diagnostics.recordRealtimeDiagnostic('room-a', 'overflow')

    const sample = diagnostics.getRealtimeDiagnostics()
    assert.equal(sample.bufferedEvents, 16)
    assert.equal(sample.droppedEvents, 2)
    assert.deepEqual(sample.events.slice(0, 2).map(event => event.event), ['relay', 'barrier'])

    const stopped = diagnostics.configureRealtimeDiagnostics({ mode: 'basic' })
    assert.equal(stopped.mode, 'basic')
    assert.equal(stopped.bufferedEvents, 0)
})

test('TCP realtime handlers do not gain direct SQLite ownership', () => {
    const tcpRoot = path.resolve(__dirname, '..', 'src', 'multi', 'tcp')
    for (const name of fs.readdirSync(tcpRoot)) {
        if (!name.endsWith('.ts')) continue
        const source = fs.readFileSync(path.join(tcpRoot, name), 'utf8')
        assert.doesNotMatch(source, /\bgetDb\s*\(|\bdb\s*\.\s*transaction\s*\(/,
            `${name} must keep database ownership outside the TCP callback`)
    }
})

test('five-boss TCP proof signals queue persistence after realtime handling', () => {
    const source = fs.readFileSync(path.resolve(__dirname, '..', 'src', 'multi', 'five-boss', 'lobby-runtime.ts'), 'utf8')
    assert.match(source, /void runPersistenceTransaction\(/)
    assert.match(source, /level_next_queued/)
    assert.match(source, /finalize_queued/)
    assert.match(source, /recordMemberBattleSignalSync\(\{ runId, playerId, roomNumber, signal \}\)/)
})

test('activity and scheduled writes declare persistence ownership', () => {
    for (const name of [
        'raidEvent.ts', 'rushEvent.ts', 'character.ts', 'exchange.ts', 'boxGacha.ts', 'equipment.ts', 'questUnlock.ts',
        'item.ts', 'exBoost.ts', 'sell.ts', 'storyQuest.ts', 'tutorial.ts',
        'profile.ts', 'playerHistory.ts', 'payment.ts', 'partyGroup.ts', 'carnivalEvent.ts',
    ]) {
        const source = fs.readFileSync(path.resolve(__dirname, '..', 'src', 'routes', 'api', name), 'utf8')
        assert.match(source, /runPersistenceTransaction(?:Sync)?\(/, `${name} must use the persistence coordinator`)
    }
    assert.match(
        fs.readFileSync(path.resolve(__dirname, '..', 'src', 'routes', 'api', 'character', 'bond.ts'), 'utf8'),
        /runPersistenceTransaction\(/,
        'character/bond.ts must use the persistence coordinator',
    )
    const leaderboard = fs.readFileSync(path.resolve(__dirname, '..', 'src', 'lib', 'leaderboard', 'settlement.ts'), 'utf8')
    assert.match(leaderboard, /operation: `scheduler:\$\{competition\.key\}`/)
    const dailyMail = fs.readFileSync(path.resolve(__dirname, '..', 'src', 'lib', 'daily-vmoney-mail.ts'), 'utf8')
    assert.match(dailyMail, /daily_vmoney_mail_scheduler/)
    const adminPlayer = fs.readFileSync(path.resolve(__dirname, '..', 'src', 'routes', 'web_api', 'player.ts'), 'utf8')
    assert.match(adminPlayer, /runPersistenceTransactionSync\(/, 'web_api/player.ts must use the persistence coordinator for admin writes')
})
