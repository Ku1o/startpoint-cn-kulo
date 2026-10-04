const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')

process.env.GAME_VERBOSE_LOGS = 'false'
process.env.PROCESS_MEMORY_DIAGNOSTICS = 'false'
const root = path.resolve(__dirname, '..')
const load = file => require(path.join(root, 'out', file))
const { multicoreConfig } = load('lib/multicore-config')
const { sqliteSettings } = load('lib/sqlite-settings')

test('four-core defaults reserve the main thread and remain explicitly reversible', () => {
    assert.deepEqual(multicoreConfig({}, 4), {
        enabled: true, responseWorkers: 0, checkpointWorker: true,
    })
    assert.deepEqual(multicoreConfig({ CN_MULTICORE: '0' }, 4), {
        enabled: false, responseWorkers: 0, checkpointWorker: false,
    })
    assert.deepEqual(multicoreConfig({
        CN_MULTICORE: '1', CN_RESPONSE_WORKERS: '1',
        SQLITE_CHECKPOINT_WORKER: '0',
    }, 4), {
        enabled: true, responseWorkers: 1, checkpointWorker: false,
    })
})

test('SQLite tuning preserves FULL durability and bounds memory settings', () => {
    assert.deepEqual(sqliteSettings({ CN_MULTICORE: '0' }), {
        synchronous: 'FULL', cacheKiB: 2048, mmapBytes: 0,
    })
    assert.deepEqual(sqliteSettings({ CN_MULTICORE: '1' }), {
        synchronous: 'FULL', cacheKiB: 65536, mmapBytes: 256 * 1024 * 1024,
    })
    assert.deepEqual(sqliteSettings({
        CN_MULTICORE: '0', SQLITE_SYNCHRONOUS: 'NORMAL',
        SQLITE_CACHE_KIB: '32768', SQLITE_MMAP_MIB: '64',
    }), {
        synchronous: 'NORMAL', cacheKiB: 32768, mmapBytes: 64 * 1024 * 1024,
    })
})

test('hot session and account lookups reuse prepared statements', () => {
    const { getDb } = load('data/db')
    const { insertAccountSync, getAccountPlayersSync } = load('data/domains/account')
    const { getSession } = load('data/domains/session')
    const players = load('data/domains/player')
    const db = getDb()
    const account = insertAccountSync({
        appId: 'wf_cn', idpAlias: '', idpCode: 'statement-cache',
        idpId: 'statement-cache', status: 'normal',
    })
    const player = players.insertDefaultPlayerSync(account.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)')
        .run('812345678', account.id, '2099-01-01T00:00:00Z')
    let prepares = 0
    const original = db.prepare
    db.prepare = function (...args) { prepares++; return original.apply(this, args) }
    return getSession('812345678').then(async first => {
        try {
            assert.equal(first.accountId, account.id)
            assert.deepEqual(getAccountPlayersSync(account.id), [player.id])
            const warmPrepares = prepares
            for (let index = 0; index < 100; index++) {
                assert.equal((await getSession('812345678')).accountId, account.id)
                assert.deepEqual(getAccountPlayersSync(account.id), [player.id])
            }
            assert.equal(prepares, warmPrepares)
        } finally {
            db.prepare = original
        }
    })
})

test('combined login access reads preserve legacy behavior before login schema initialization', () => {
    const { insertAccountSync } = load('data/domains/account')
    const players = load('data/domains/player')
    const sessions = load('data/domains/session')
    const login = load('lib/player-login')
    const account = insertAccountSync({
        appId: 'wf_cn', idpAlias: '', idpCode: 'uninitialized-login',
        idpId: 'uninitialized-login', status: 'normal',
    })
    players.insertDefaultPlayerSync(account.id)
    sessions.insertSessionWithTokenSync({
        token: '812345679', accountId: account.id,
        expires: new Date('2099-01-01T00:00:00Z'), type: 2,
    })
    sessions.insertDeviceBindingSync(991234, account.id)
    assert.deepEqual(login.readPlayerLoginViewerAccess('812345679'), {
        accountId: account.id, managed: false,
    })
    assert.deepEqual(login.readPlayerLoginDeviceAccess(991234), {
        accountId: account.id, managed: false,
    })
})

test('hot player resolution keeps active-account state in memory', () => {
    const fs = require('node:fs')
    const { insertAccountSync } = load('data/domains/account')
    const players = load('data/domains/player')
    const state = load('data/activeAccount')
    const account = insertAccountSync({
        appId: 'wf_cn', idpAlias: '', idpCode: 'state-cache',
        idpId: 'state-cache', status: 'normal',
    })
    const first = players.insertDefaultPlayerSync(account.id)
    const second = players.insertDefaultPlayerSync(account.id)
    state.saveAccountDefaultPlayer(account.id, second.id)
    let reads = 0
    const original = fs.readFileSync
    fs.readFileSync = function (...args) {
        if (String(args[0]).endsWith('active_account.json')) reads++
        return original.apply(this, args)
    }
    try {
        for (let index = 0; index < 100; index++) {
            assert.equal(state.resolvePlayerIdSync(account.id), second.id)
        }
        assert.equal(reads, 0)
        state.removeDeletedAccountFromState(account.id, [second.id])
        assert.equal(state.resolvePlayerIdSync(account.id), first.id)
        assert.equal(reads, 0)
        state.saveAccountDefaultPlayer(account.id, Number.MAX_SAFE_INTEGER)
        assert.equal(state.resolvePlayerIdSync(account.id), first.id)
    } finally {
        fs.readFileSync = original
    }
})
