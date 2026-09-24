const { test, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')

const outputDir = process.env.STARPOINT_TEST_OUT || path.join(__dirname, '..', 'out')
const fromBuild = relativePath => require(path.join(outputDir, relativePath))
const previousDataDir = process.env.DATA_DIR
const testDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'starpoint-online-presence-'))
process.env.DATA_DIR = testDataDir
after(() => {
    fromBuild('data/db.js').getDb().close()
    const resolved = fs.realpathSync(testDataDir)
    if (path.dirname(resolved) !== fs.realpathSync(os.tmpdir())
        || !path.basename(resolved).startsWith('starpoint-online-presence-')) {
        throw new Error(`Refusing to remove unexpected test directory: ${resolved}`)
    }
    fs.rmSync(resolved, { recursive: true })
    if (previousDataDir === undefined) delete process.env.DATA_DIR
    else process.env.DATA_DIR = previousDataDir
})
const {
    clearOnlinePlayers, getOnlinePlayerCount, markPlayerOnline, markPlayerOnlineFromTcp,
} = fromBuild('lib/online-presence.js')

const originalInterval = global.setInterval
global.setInterval = (...args) => {
    const timer = originalInterval(...args)
    timer.unref()
    return timer
}
let sessionManager, handleBattleMessage, embeddedMultiCoordinator, handleLobbyMessage, loungeState, handleLoungeMessage
try {
    ;({ sessionManager } = fromBuild('multi/state/SessionManager.js'))
    ;({ handleBattleMessage } = fromBuild('multi/tcp/battle.js'))
    ;({ embeddedMultiCoordinator } = fromBuild('multi/coordinator/embedded.js'))
    ;({ handleMessage: handleLobbyMessage } = fromBuild('multi/tcp/lobby.js'))
    loungeState = fromBuild('lounge/state.js')
    ;({ handleLoungeMessage } = fromBuild('lounge/tcp.js'))
} finally {
    global.setInterval = originalInterval
}

test('identified TCP activity joins HTTP activity by UID and expires after five minutes', () => {
    clearOnlinePlayers()
    const start = 1_000_000
    assert.equal(markPlayerOnline(101, start), true)
    assert.equal(markPlayerOnlineFromTcp(101, start), true)
    assert.equal(markPlayerOnlineFromTcp(202, start), true)
    assert.equal(markPlayerOnlineFromTcp(0, start), false)
    assert.equal(markPlayerOnlineFromTcp('invalid', start), false)
    assert.equal(getOnlinePlayerCount(start), 2)

    for (let elapsed = 30_000; elapsed <= 360_000; elapsed += 30_000) {
        markPlayerOnlineFromTcp(101, start + elapsed)
    }
    assert.equal(getOnlinePlayerCount(start + 360_000), 1)
    assert.equal(getOnlinePlayerCount(start + 660_001), 0)
    clearOnlinePlayers()
})

test('battle activity counts only an indexed current player', t => {
    clearOnlinePlayers()
    const socket = { destroyed: false, writable: true }
    const client = { socket, viewerId: 301, connectionId: 'presence-battle', roomNumber: '1', isBattle: true }
    let current = true
    t.mock.method(sessionManager, 'findClientBySocket', () => client)
    t.mock.method(sessionManager, 'isCurrentBattleClient', () => current)
    t.mock.method(sessionManager, 'noteBattleActivity', () => {})
    t.mock.method(sessionManager, 'sendJson', () => true)

    handleBattleMessage(socket, [0, [5]])
    assert.equal(getOnlinePlayerCount(), 1)

    clearOnlinePlayers()
    current = false
    handleBattleMessage(socket, [0, [5]])
    assert.equal(getOnlinePlayerCount(), 0)

    current = true
    client.viewerId = 0
    handleBattleMessage(socket, [0, [5]])
    assert.equal(getOnlinePlayerCount(), 0)

    client.viewerId = 301
    socket.destroyed = true
    handleBattleMessage(socket, [0, [5]])
    assert.equal(getOnlinePlayerCount(), 0)
    clearOnlinePlayers()
})

test('lobby heartbeat ignores a superseded or closed socket', async t => {
    clearOnlinePlayers()
    const socket = { destroyed: false, writable: true }
    const client = { socket, viewerId: 401, roomNumber: '1', connectionId: 'presence-lobby', superseded: false }
    let queued = Promise.resolve()
    t.mock.method(sessionManager, 'findClientBySocket', () => client)
    t.mock.method(sessionManager, 'sendJson', () => true)
    t.mock.method(embeddedMultiCoordinator, 'enqueueRoomCommand', (_room, command) => {
        queued = Promise.resolve().then(command)
        return queued
    })

    handleLobbyMessage(socket, [0, [4]])
    await queued
    assert.equal(getOnlinePlayerCount(), 1)

    clearOnlinePlayers()
    client.superseded = true
    handleLobbyMessage(socket, [0, [4]])
    await queued
    assert.equal(getOnlinePlayerCount(), 0)

    client.superseded = false
    socket.destroyed = true
    handleLobbyMessage(socket, [0, [4]])
    await queued
    assert.equal(getOnlinePlayerCount(), 0)
    clearOnlinePlayers()
})

test('lounge heartbeat counts its current member socket only', t => {
    clearOnlinePlayers()
    const socket = { destroyed: false }
    const context = { room: {}, viewerId: 501, member: { socket } }
    t.mock.method(loungeState, 'getLoungeSocketContext', () => context)
    t.mock.method(loungeState, 'touchLoungeActivity', () => {})
    t.mock.method(loungeState, 'sendLoungeFrame', () => true)

    handleLoungeMessage(socket, [0, [1]])
    assert.equal(getOnlinePlayerCount(), 1)

    clearOnlinePlayers()
    context.member.socket = {}
    handleLoungeMessage(socket, [0, [1]])
    assert.equal(getOnlinePlayerCount(), 0)
    clearOnlinePlayers()
})
