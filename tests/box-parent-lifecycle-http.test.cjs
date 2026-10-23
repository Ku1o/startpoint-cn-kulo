'use strict'
const { test, before, after } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { randomUUID } = require('node:crypto')
const temporaryRoot = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(temporaryRoot, { recursive: true })
const directory = fs.mkdtempSync(path.join(temporaryRoot, 'box-parent-lifecycle-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
const compiledRoot = path.resolve(process.env.STARPOINT_TEST_COMPILED_ROOT || path.join(__dirname, '../out'))
if (!compiled) {
    const ts = require('typescript')
    require.extensions['.ts'] = (module, filename) => module._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
        compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true }, fileName: filename,
    }).outputText, filename)
}
const load = name => require(compiled ? path.join(compiledRoot, name + '.js') : path.join(__dirname, '../src', name + '.ts'))
const operations = load('lib/content-operations'), assets = load('lib/assets')
const associations = load('lib/content-box-associations')
const players = load('data/domains/player'), boxes = load('data/domains/boxGacha'), items = load('data/domains/item')
const active = load('data/domains/quest_active'), coordinator = load('lib/persistence-coordinator')
const originalTransaction = coordinator.runPersistenceTransaction, originalNow = Date.now
const WORLD = { parentKey: 'world_story_event:100407', boxKey: 'box_gacha:11' }
const RAID = { parentKey: 'raid_event:7', boxKey: 'box_gacha:28' }
let db, store, app, viewerSequence = 89148000
const idOf = key => Number(key.split(':')[1])
const review = enabled => ({ enabled, endsAtMs: null, readiness: 'verified', evidence: 'Real native box/parent definitions; isolated transaction and old-progress lifecycle regression' })
function reviewKey(key) {
    const row = store.rows.get(key)
    assert.ok(row, key)
    const scope = { ...(store.questMembers.get(key)?.size ? { questKeys: null } : {}),
        ...(store.missionMembers.get(key)?.size ? { missionKeys: null } : {}) }
    const actionOverrides = Object.fromEntries(store.capabilities(row).map(action => [action,
        { ...review(true), ...(['enter', 'claim'].includes(action) ? scope : {}) }]))
    return store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Prepare real reviewed actions in a disposable database only', actionOverrides }, Date.now())
}
function publish(key, published) {
    if ((store.state(key)?.published !== false) === published) return store.state(key)
    return store.setPublished(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Synthetic lifecycle publication without player progress changes', published }, Date.now())
}
function preparePair(pair) {
    reviewKey(pair.parentKey); reviewKey(pair.boxKey)
    publish(pair.parentKey, true); publish(pair.boxKey, true)
}
function deadline(key, endsAtMs) {
    return store.setDeadline(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
        reason: 'Synthetic shared lifecycle deadline boundary', endsAtMs }, Date.now())
}
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'box-parent-lifecycle', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = viewerSequence++
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    db.transaction(() => load('lib/server-clock-state').ensurePlayerClockStateForLoadSync(player.id, db))()
    return { id: player.id, accountId: account.id, viewer }
}
const post = (player, url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: player.viewer, api_count: 1, ...body } })
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
function data(result) { return response(result).data }
const body = (pair, boxId = 1) => ({ box_gacha_id: idOf(pair.boxKey), box_id: boxId, number: 1, stop_on_featured_rewards: false })
function portable(player) {
    return { tables: load('data/snapshots/player-snapshot').createPlayerSaveSnapshotV2Sync(player.id, db).data.tables,
        active: active.getPlayerActiveQuestSync(player.id) }
}
function boxFacts(player) {
    return Object.fromEntries(['players_box_gacha', 'players_box_gacha_drawn_rewards', 'players_items'].map(table => [table,
        db.prepare(`SELECT * FROM ${table} WHERE player_id=?`).all(player.id).map(row => JSON.stringify(row)).sort()]))
}
function credit(player, pair) { const master = assets.getBoxGachaSync(idOf(pair.boxKey)); items.setPlayerItemSync(player.id, master.redeemItemId, 100000); return master }
function seedFinishedBox(player, pair, boxId, resets = 0) {
    const rewards = assets.getBoxGachaSync(idOf(pair.boxKey)).boxes[boxId]
    boxes.insertPlayerBoxGachaSync(player.id, idOf(pair.boxKey), { boxId, resetTimes: resets, remainingNumber: 0, isClosed: true })
    for (const [id, reward] of Object.entries(rewards)) if (reward.available)
        boxes.insertPlayerBoxGachaDrawnRewardSync(player.id, idOf(pair.boxKey), boxId, { id: Number(id), number: reward.available })
}
async function rejectedUnchanged(player, url, payload) {
    const before = portable(player), result = await post(player, url, payload)
    assert.equal(result.statusCode, 400, result.body)
    assert.deepEqual(portable(player), before, 'denied new participation cannot change currency, rewards, inventory, old boxes or active battle')
}
async function afterAdmission(operation, change, request) {
    let reached = false
    coordinator.runPersistenceTransaction = async (context, callback, options) => {
        if (context.operation === operation) { reached = true; change() }
        return originalTransaction(context, callback, options)
    }
    try { const result = await request(); assert.equal(reached, true, operation); return result }
    finally { coordinator.runPersistenceTransaction = originalTransaction }
}
function snapshotState(snapshot, key) { const value = snapshot.states.find(row => row.key === key); assert.ok(value, key); return value }
function assertPair(snapshot, pair, enabled) {
    for (const [key, actions] of [[pair.parentKey, ['visible', 'enter', 'exchange']], [pair.boxKey, ['visible', 'enter', 'claim']]]) {
        const value = snapshotState(snapshot, key)
        for (const action of actions) {
            assert.equal(value[action], enabled, `${key}.${action}`)
            assert.equal(value.actions[action]?.enabled, enabled, `${key}.actions.${action}`)
        }
    }
}
before(async () => {
    db = load('data/db').getDb(); store = operations.contentOperations()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_request, reply, value, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof value === 'object' ? JSON.stringify(value) : value))
    for (const [name, prefix] of [['boxGacha', '/box'], ['raidEvent', '/raid'], ['singleBattleQuest', '/single'], ['shop', '/shop']])
        await app.register(load(`routes/api/${name}`).default, { prefix })
    await app.register(load('routes/cn/load').default, { prefix: '/cn' })
    await app.ready()
})
after(async () => {
    Date.now = originalNow; coordinator.runPersistenceTransaction = originalTransaction
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), temporaryRoot)
    fs.rmSync(directory, { recursive: true })
})

test('the real index binds exactly 41 WorldStory and 7 Raid parents to 48 unique native boxes', () => {
    const pairs = associations.getContentBoxAssociations()
    assert.equal(pairs.length, 48)
    assert.equal(new Set(pairs.map(row => row.parentKey)).size, 48)
    assert.equal(new Set(pairs.map(row => row.boxKey)).size, 48)
    assert.equal(pairs.filter(row => row.parentKey.startsWith('world_story_event:')).length, 41)
    assert.equal(pairs.filter(row => row.parentKey.startsWith('raid_event:')).length, 7)
    for (const pair of pairs) {
        assert.equal(pair.relationshipMatches, true, pair.parentKey)
        assert.deepEqual(associations.getContentBoxAssociation(pair.parentKey), pair)
        assert.deepEqual(associations.getContentBoxAssociation(pair.boxKey), pair)
        assert.ok(assets.getBoxGachaSync(idOf(pair.boxKey)))
    }
    assert.equal(associations.getContentBoxAssociation('box_gacha:999999999'), undefined)
})

test('all 48 real pairs require both local publications and snapshots report the same effective gates', () => {
    for (const pair of associations.getContentBoxAssociations()) {
        assert.ok(store.capabilities(store.rows.get(pair.parentKey)).includes('exchange'), pair.parentKey)
        preparePair(pair)
        assertPair(store.snapshot(Date.now()), pair, true)
        publish(pair.parentKey, false)
        for (const action of ['visible', 'enter', 'claim']) assert.equal(store.allowed(pair.boxKey, action, Date.now()), false)
        assertPair(store.snapshot(Date.now()), pair, false)
        publish(pair.parentKey, true); publish(pair.boxKey, false)
        assertPair(store.snapshot(Date.now()), pair, false)
        publish(pair.boxKey, true)
        assertPair(store.snapshot(Date.now()), pair, true)
    }
})

test('real WorldStory and Raid boxes draw under reviewed gates and preserve acquired progress through parent closure', async () => {
    for (const pair of [WORLD, RAID]) {
        preparePair(pair)
        const player = fixture(), foreign = fixture(), master = credit(player, pair), other = portable(foreign)
        data(await post(player, '/box/get_box_list', body(pair)))
        const beforeCurrency = items.getPlayerItemSync(player.id, master.redeemItemId)
        const result = data(await post(player, '/box/exec', body(pair)))
        assert.equal(result.drawn_reward_list.reduce((n, row) => n + row.number, 0), 1)
        assert.equal(items.getPlayerItemSync(player.id, master.redeemItemId), beforeCurrency - master.redeemItemCount)
        assert.equal(boxes.getPlayerBoxGachaDrawnRewardsSync(player.id, idOf(pair.boxKey), 1).reduce((n, row) => n + row.number, 0), 1)
        const acquired = portable(player), oldFacts = boxFacts(player)
        publish(pair.parentKey, false)
        await rejectedUnchanged(player, '/box/exec', body(pair))
        data(await post(player, '/box/get_box_list', body(pair)))
        const retained = data(await post(player, '/box/get_retained_box_gachas')).retained_box_gacha_list.find(row => row.box_gacha_id === idOf(pair.boxKey))
        assert.ok(retained); assert.equal(retained.participation_enabled, false)
        assert.deepEqual(boxFacts(player), oldFacts)
        publish(pair.parentKey, true)
        assert.deepEqual(portable(player), acquired)
        assert.deepEqual(portable(foreign), other)
        data(await post(player, '/box/exec', body(pair)))
        assert.equal(boxes.getPlayerBoxGachaDrawnRewardsSync(player.id, idOf(pair.boxKey), 1).reduce((n, row) => n + row.number, 0), 2)
    }
})

test('fresh direct box listing/draw cannot bypass either a closed parent or a closed independent box', async () => {
    preparePair(WORLD)
    const player = fixture(); credit(player, WORLD)
    for (const key of [WORLD.parentKey, WORLD.boxKey]) {
        publish(key, false)
        await rejectedUnchanged(player, '/box/get_box_list', body(WORLD))
        await rejectedUnchanged(player, '/box/exec', body(WORLD))
        publish(key, true)
    }
})

test('real final-box reset obeys parent lifecycle without clearing previous boxes or increasing stock while closed', async () => {
    preparePair(RAID)
    const player = fixture(), master = credit(player, RAID)
    const ids = Object.keys(master.boxes).map(Number).sort((a, b) => a - b), last = ids.at(-1)
    assert.equal(store.rows.get(RAID.boxKey).boxRules[last].resetKind, 2)
    for (const id of ids) seedFinishedBox(player, RAID, id, id === last ? 2 : 0)
    const prior = ids.slice(0, -1).map(id => ({ box: boxes.getPlayerBoxGachaSync(player.id, 28, id), facts: boxes.getPlayerBoxGachaDrawnRewardsSync(player.id, 28, id) }))
    publish(RAID.parentKey, false)
    await rejectedUnchanged(player, '/box/reset', body(RAID, last))
    publish(RAID.parentKey, true)
    data(await post(player, '/box/reset', body(RAID, last)))
    const reset = boxes.getPlayerBoxGachaSync(player.id, 28, last)
    assert.equal(reset.resetTimes, 3); assert.equal(reset.isClosed, false)
    assert.equal(reset.remainingNumber, Object.values(master.boxes[last]).reduce((n, row) => n + row.available, 0))
    assert.deepEqual(ids.slice(0, -1).map(id => ({ box: boxes.getPlayerBoxGachaSync(player.id, 28, id), facts: boxes.getPlayerBoxGachaDrawnRewardsSync(player.id, 28, id) })), prior)
})

test('already closed boxes remain idempotently readable after parent shutdown and new close requests cannot bypass it', async () => {
    preparePair(WORLD)
    const player = fixture(); credit(player, WORLD); seedFinishedBox(player, WORLD, 1)
    const before = portable(player)
    publish(WORLD.parentKey, false)
    data(await post(player, '/box/close', body(WORLD)))
    assert.deepEqual(portable(player), before)
    const unfinished = fixture(); credit(unfinished, WORLD)
    boxes.insertPlayerBoxGachaSync(unfinished.id, 11, { boxId: 1, resetTimes: 0, remainingNumber: 1, isClosed: false })
    await rejectedUnchanged(unfinished, '/box/close', body(WORLD))
})

test('queued draw, reset, close and listing recheck the actual parent inside the final transaction', async () => {
    for (const [operation, endpoint] of [['box_exec', '/box/exec'], ['box_reset', '/box/reset'], ['box_close', '/box/close'], ['box_list', '/box/get_box_list']]) {
        preparePair(RAID)
        const player = fixture(); credit(player, RAID)
        let boxId = 1
        if (operation === 'box_reset') {
            const ids = Object.keys(assets.getBoxGachaSync(28).boxes).map(Number); boxId = Math.max(...ids)
            for (const id of ids) seedFinishedBox(player, RAID, id)
        }
        if (operation === 'box_close') {
            seedFinishedBox(player, RAID, 1)
            boxes.updatePlayerBoxGachaSync(player.id, 28, { boxId: 1, isClosed: false, remainingNumber: 0 })
        }
        const before = portable(player)
        const result = await afterAdmission(operation, () => publish(RAID.parentKey, false), () => post(player, endpoint, body(RAID, boxId)))
        assert.equal(result.statusCode, 400, result.body)
        assert.deepEqual(portable(player), before)
    }
})

test('a disabled reviewed parent exchange or child draw action closes the group despite published entrances', () => {
    for (const [key, action] of [[WORLD.parentKey, 'exchange'], [WORLD.boxKey, 'enter']]) {
        preparePair(WORLD)
        store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest,
            reason: 'Synthetic explicit local action closure', actionOverrides: { [action]: review(false) } }, Date.now())
        assert.notEqual(store.state(WORLD.parentKey).published, false)
        assert.notEqual(store.state(WORLD.boxKey).published, false)
        assertPair(store.snapshot(Date.now()), WORLD, false)
    }
})

test('a real draw failure after charge and reward processing rolls back every player write and retry grants once', async () => {
    preparePair(WORLD)
    const player = fixture(), master = credit(player, WORLD), before = portable(player)
    db.exec(`CREATE TRIGGER box_lifecycle_fail_history BEFORE INSERT ON players_box_gacha_drawn_rewards
        WHEN NEW.player_id=${player.id} BEGIN SELECT RAISE(ABORT,'box lifecycle injected history failure'); END`)
    try {
        const failed = await post(player, '/box/exec', body(WORLD))
        assert.equal(failed.statusCode, 500, failed.body)
        assert.deepEqual(portable(player), before)
    } finally { db.exec('DROP TRIGGER box_lifecycle_fail_history') }
    data(await post(player, '/box/exec', body(WORLD)))
    assert.equal(items.getPlayerItemSync(player.id, master.redeemItemId), 100000 - master.redeemItemCount)
    assert.equal(boxes.getPlayerBoxGachaDrawnRewardsSync(player.id, 11, 1).reduce((n, row) => n + row.number, 0), 1)
})

test('parent and independent box deadlines apply at the exact boundary and are rechecked after queue admission', async () => {
    for (const key of [WORLD.parentKey, WORLD.boxKey]) {
        preparePair(WORLD)
        const player = fixture(); credit(player, WORLD)
        const end = originalNow() + 60000; deadline(key, end)
        try {
            // Existing content deadlines include their final millisecond.
            Date.now = () => end
            assertPair(store.snapshot(Date.now()), WORLD, true)
            const before = portable(player)
            const result = await afterAdmission('box_exec', () => { Date.now = () => end + 1 }, () => post(player, '/box/exec', body(WORLD)))
            assert.equal(result.statusCode, 400, result.body)
            assert.deepEqual(portable(player), before)
            assertPair(store.snapshot(Date.now()), WORLD, false)
        } finally { Date.now = originalNow }
    }
})

test('real refresh and relogin load snapshots preserve old box facts and report shared closure and deadline', async () => {
    preparePair(RAID)
    const player = fixture(); credit(player, RAID)
    data(await post(player, '/box/exec', body(RAID)))
    // First load performs unrelated normal save maintenance before the progress baseline.
    data(await post(player, '/cn/load'))
    const saved = boxFacts(player)
    publish(RAID.parentKey, false)
    assertPair(data(await post(player, '/cn/content_operations')).content_operations, RAID, false)
    // A newly authenticated session for the same saved player simulates relogin.
    const relogin = { ...player, viewer: viewerSequence++ }
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(relogin.viewer), player.accountId, '2099-01-01T00:00:00Z')
    assertPair(data(await post(relogin, '/cn/load')).content_operations, RAID, false)
    assert.deepEqual(boxFacts(player), saved)
    publish(RAID.parentKey, true)
    const end = originalNow() + 60000; deadline(RAID.parentKey, end)
    try {
        Date.now = () => end + 1
        assertPair(data(await post(relogin, '/cn/content_operations')).content_operations, RAID, false)
        assert.deepEqual(boxFacts(player), saved)
    } finally { Date.now = originalNow }
})

const finishBody = (quest, play) => ({ category: 23, quest_id: quest, play_id: play, continue_count: 0, elapsed_time_ms: 1000,
    score: 12345, add_mana: 0, is_accomplished: true, is_restored: false,
    statistics: { clear_phase: 1, party: { characters: [{ id: 1 }, null, null], unison_characters: [null, null, null],
        equipments: [null, null, null], ability_soul_ids: [null, null, null] }, zones: [] } })
test('a Raid run registered before closure or expiry can settle exactly once while new runs remain denied', async () => {
    for (const expire of [false, true]) {
        preparePair(RAID)
        const player = fixture(), play = randomUUID(), quest = 7001
        response(await post(player, '/raid/summary', { event_id: 7 }))
        assert.equal(response(await post(player, '/raid/battle/start', { event_id: 7, quest_id: quest, party_group_id: 1, play_id: play,
            use_auto_start_point: false, is_auto_start_mode: false })).data_headers.result_code, 1)
        assert.equal(active.getPlayerActiveQuestSync(player.id).playId, play)
        const end = originalNow() + 60000
        if (expire) deadline(RAID.parentKey, end); else publish(RAID.parentKey, false)
        try {
            if (expire) Date.now = () => end + 1
            const registered = portable(player)
            assert.equal(response(await post(player, '/raid/battle/start', { event_id: 7, quest_id: quest, party_group_id: 1,
                play_id: randomUUID(), use_auto_start_point: false, is_auto_start_mode: false })).data_headers.result_code, 4050)
            assert.deepEqual(portable(player), registered)
            assert.equal(response(await post(player, '/single/finish', finishBody(quest, play))).data_headers.result_code, 1)
            const settled = portable(player)
            assert.equal(response(await post(player, '/single/finish', finishBody(quest, play))).data_headers.result_code, 1)
            assert.deepEqual(portable(player), settled)
        } finally { Date.now = originalNow }
    }
})

test('native Raid7 remains unbounded; excluded abyss items stay closed and veteran title exchange stays valid', async () => {
    assert.equal(store.rows.get(RAID.parentKey).originalEndMs, null)
    assert.equal(store.rows.get(RAID.boxKey).originalEndMs, null)
    for (let id = 9700121; id <= 9700129; id++) assert.equal(operations.contentDecision('event_item_shop', id, 'exchange', Date.now()), false)
    reviewKey('rush_event:700099'); publish('rush_event:700099', true); reviewKey('event_item_shop:9700118')
    const player = fixture(); players.updatePlayerSync({ id: player.id, freeVmoney: 5000000, vmoney: 0 })
    data(await post(player, '/shop/buy', { shop_type: 4, shop_item_id: 9700118, number: 1 }))
    assert.equal(players.getPlayerSync(player.id).freeVmoney, 0)
    assert.equal(load('data/domains/degree').hasPlayerDegreeSync(player.id, 9900006), true)
})
