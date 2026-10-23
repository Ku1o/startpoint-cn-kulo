'use strict'
const compiled = process.env.STARPOINT_TEST_COMPILED === '1'
if (!compiled) require('ts-node/register/transpile-only')
const load = name => require(`../${compiled ? 'out' : 'src'}/${name}`)
const { test, before, after } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), { randomUUID, createHash } = require('node:crypto')
const root = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
fs.mkdirSync(root, { recursive: true })
const directory = fs.mkdtempSync(path.join(root, 'history-active69-'))
Object.assign(process.env, { DATA_DIR: directory, TEMP: directory, TMP: directory, SQLITE_TMPDIR: directory,
    GACHA_SEED_DIR: path.join(directory, 'seeds'), CN_WRITER_THREAD: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
fs.mkdirSync(process.env.GACHA_SEED_DIR)
const campaigns = load('data/domains/campaign'), inventory = load('data/domains/item'), characters = load('data/domains/character')
const players = load('data/domains/player'), missions = load('data/domains/mission'), operations = load('lib/content-operations')
const facts = load('lib/mission/active-reconciliation'), snapshot = load('content/runtime/content-snapshot')
const coordinator = load('lib/persistence-coordinator'), originalTransaction = coordinator.runPersistenceTransaction
const table = require('../assets/multi_special_exchange_campaign_character.json'), native = require('../assets/mission_active.json')
const selected = table['980004'][0], missionId = 21030
const digest = value => createHash('sha256').update(JSON.stringify(value)).digest('hex')
let db, app
function fixture(status = 1, id = 2) {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'active69-http', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), viewer = 880000000 + player.id
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer), account.id, '2099-01-01T00:00:00Z')
    campaigns.updatePlayerMultiSpecialExchangeCampaignSync(player.id, { campaignId: id, status, ticketItemId: null })
    return { id: player.id, viewer }
}
function control(key, actions) {
    const store = operations.contentOperations(), actionOverrides = {}
    for (const [action, enabled] of Object.entries(actions)) actionOverrides[action] = {
        enabled, readiness: 'verified', evidence: 'Native69 campaign2 final-selection facts and synthetic registered HTTP', endsAtMs: null,
        ...(key === 'active_mission_event:3' && ['enter', 'claim'].includes(action) ? { missionKeys: ['0:21030'] } : {}),
    }
    store.update(key, { expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Synthetic active69 final exchange', actionOverrides }, Date.now())
}
function open() {
    control('active_mission_event:3', { visible: true, enter: true, claim: true })
    control('multi_special_exchange_campaign:2', { visible: true, enter: true, exchange: true })
}
const post = (p, url, body = {}) => app.inject({ method: 'POST', url, payload: { viewer_id: p.viewer, api_count: 1, ...body } })
const draw = (p, multi = false, id = 2) => post(p, '/special/' + (multi ? 'multi_draw_ticket' : 'single_draw_ticket'), { campaign_id: id })
const exchange = (p, extra = {}) => post(p, '/special/exchange_character', { campaign_id: 2, ticket_item_id: 980004, character_id: selected, ...extra })
function response(result) { assert.equal(result.statusCode, 200, result.body); return result.json() }
const code = result => response(result).data_headers.result_code
const mission = p => missions.getPlayerActiveMissionsSync(p.id)[missionId]
const campaign = (p, id = 2) => campaigns.getPlayerMultiSpecialExchangeCampaignsSync(p.id).find(row => row.campaignId === id)
const reconcile = p => facts.reconcileActiveMissionFacts({ playerId: p.id, repository: snapshot.getContentSnapshot().repository, now: Date.now(), patterns: [69] })
function state(p) { return { player: players.getPlayerSync(p.id), mission: mission(p), campaign: campaign(p),
    characters: characters.getPlayerCharactersSync(p.id), items: inventory.getPlayerItemsSync(p.id) } }
before(async () => {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    app = require('fastify')({ logger: false })
    app.addHook('onSend', (_q, reply, body, done) => done(null,
        String(reply.getHeader('content-type')).startsWith('application/x-msgpack') && typeof body === 'object' ? JSON.stringify(body) : body))
    await app.register(load('routes/api/multiSpecialExchange').default, { prefix: '/special' })
    await app.register(load('routes/api/activeMission').default, { prefix: '/active' })
    await app.register(load('routes/cn/load').default, { prefix: '/cn' }); await app.ready()
})
after(async () => {
    coordinator.runPersistenceTransaction = originalTransaction
    if (app) await app.close()
    await load('lib/seed-validator').default.close()
    if (db?.open) db.close()
    assert.equal(path.dirname(directory), root); fs.rmSync(directory, { recursive: true })
})

test('only native69 MultiSpecial kind2/campaign2 uses final-status facts; the ordinary pattern83 counter remains separate', () => {
    assert.equal(native[missionId][0][29], '69'); assert.equal(native[missionId][0][44], '2'); assert.equal(native[missionId][0][45], '2')
    assert.equal(Object.values(native).filter(rows => rows[0]?.[29] === '69').length, 1)
    const row = native[missionId][0], base = { totalGachaCampaignCount: 99999, finalizedMultiSpecialCampaignIds: new Set([1, 3]) }
    assert.equal(facts.computeActiveMissionFactProgress(69, row, base, missionId), 0)
    assert.equal(facts.computeActiveMissionFactProgress(83, row, base, missionId), 99999)
    assert.equal(facts.computeActiveMissionFactProgress(69, row, { ...base, finalizedMultiSpecialCampaignIds: new Set([2]) }, missionId), 1)
    const other = [...row]; other[45] = '3'
    assert.equal(facts.computeActiveMissionFactProgress(69, other, { ...base, finalizedMultiSpecialCampaignIds: new Set([3]) }, missionId), null)
})

test('both real draw routes and their retries only produce the candidate ticket; status1/2/3 and ordinary gacha counters never complete69', async () => {
    open()
    for (const initial of [1, 2]) {
        const p = fixture(initial)
        load('data/domains/active_mission_counters').incrementActiveMissionGachaCampaignCountSync(p.id)
        reconcile(p); assert.equal(mission(p), undefined)
        assert.equal(code(await draw(p, initial === 2)), 1)
        assert.equal(campaign(p).status, 3); assert.equal(inventory.getPlayerItemSync(p.id, 980004), 1)
        assert.equal(code(await draw(p, initial !== 2)), 1)
        assert.equal(inventory.getPlayerItemSync(p.id, 980004), 1)
        reconcile(p); assert.equal(mission(p), undefined); assert.equal(characters.getPlayerCharacterSync(p.id, selected), null)
        const loaded = response(await post(p, '/cn/load')).data
        assert.equal(loaded.all_active_mission_list[missionId], undefined)
    }
})

test('final campaign2 character exchange completes active69 in the same transaction and concurrent/repeated exchanges grant only once', async () => {
    open(); const p = fixture(); assert.equal(code(await draw(p)), 1)
    const results = await Promise.all([exchange(p), exchange(p)])
    for (const result of results) assert.equal(code(result), 1)
    const deltas = results.flatMap(result => response(result).data.active_mission_list)
    assert.equal(deltas.filter(row => row.mission_id === missionId && row.progress_value === 1).length, 1)
    assert.equal(campaign(p).status, 4); assert.equal(inventory.getPlayerItemSync(p.id, 980004), 0)
    assert.equal(mission(p).progress, 1); assert.equal(mission(p).stages['1'], false)
    const owned = characters.getPlayerCharacterSync(p.id, selected)
    assert.equal(owned.entryCount, 1); assert.equal(owned.stack, 0)
    const settled = digest(state(p)); assert.equal(code(await exchange(p)), 1); assert.equal(digest(state(p)), settled)
})

test('wrong character/ticket, false campaign identity, closed campaign and queue-time closure do not create final facts or mission progress', async () => {
    open(); const p = fixture(); response(await draw(p)); const frozen = digest(state(p))
    assert.equal(code(await exchange(p, { character_id: 2147483647 })), 4902)
    assert.equal(code(await exchange(p, { ticket_item_id: 980005 })), 4901)
    assert.equal(code(await exchange(p, { campaign_id: false })), 4901)
    assert.equal(digest(state(p)), frozen)
    control('multi_special_exchange_campaign:2', { exchange: false })
    assert.equal(code(await exchange(p)), 4902); assert.equal(digest(state(p)), frozen)
    control('multi_special_exchange_campaign:2', { exchange: true })
    let closed = false
    coordinator.runPersistenceTransaction = (context, callback, options) => {
        if (context.playerId === p.id && context.domain === 'event' && context.operation === 'exchange_character' && !closed) {
            closed = true; control('multi_special_exchange_campaign:2', { exchange: false })
        }
        return originalTransaction(context, callback, options)
    }
    try { assert.equal(code(await exchange(p)), 4902) }
    finally { coordinator.runPersistenceTransaction = originalTransaction }
    assert.equal(closed, true); assert.equal(digest(state(p)), frozen)
    const fresh = fixture(); control('multi_special_exchange_campaign:2', { enter: false })
    const before = digest(state(fresh)); assert.equal(code(await draw(fresh)), 4902); assert.equal(digest(state(fresh)), before)
})

test('other campaigns can finish their own exchanges without completing69, and the mission enter scope can defer existing final facts', async () => {
    open(); const other = fixture(1, 3)
    control('multi_special_exchange_campaign:3', { visible: true, enter: true, exchange: true })
    assert.equal(code(await draw(other, false, 3)), 1)
    assert.equal(code(await exchange(other, { campaign_id: 3, ticket_item_id: 980005, character_id: table['980005'][0] })), 1)
    reconcile(other); assert.equal(mission(other), undefined)
    const p = fixture(); response(await draw(p))
    control('active_mission_event:3', { enter: false })
    assert.equal(code(await exchange(p)), 1); assert.equal(campaign(p).status, 4); assert.equal(mission(p), undefined)
    const awarded = digest(characters.getPlayerCharactersSync(p.id))
    control('active_mission_event:3', { enter: true })
    const loaded = response(await post(p, '/cn/load')).data
    assert.equal(loaded.all_active_mission_list[missionId].progress, 1)
    assert.equal(digest(characters.getPlayerCharactersSync(p.id)), awarded)
})

test('existing finalized archives reconcile on normal load without a new character, while claimed stages and old higher progress remain intact', async () => {
    open(); const completed = fixture(4), before = digest(characters.getPlayerCharactersSync(completed.id))
    const loaded = response(await post(completed, '/cn/load')).data
    assert.equal(mission(completed).progress, 1); assert.equal(mission(completed).stages['1'], false)
    assert.equal(loaded.all_active_mission_list[missionId].progress, 1)
    assert.equal(digest(characters.getPlayerCharactersSync(completed.id)), before)
    const old = fixture(); missions.insertPlayerActiveMissionsSync(old.id, { [missionId]: { progress: 7, stages: { '1': true } } })
    response(await draw(old)); response(await exchange(old))
    assert.equal(mission(old).progress, 7); assert.equal(mission(old).stages['1'], true)
    assert.deepEqual(reconcile(old), [])
    const frozen = digest(state(old)); const denied = await post(old, '/active/receive', { active_mission_list: [{ mission_id: missionId, stages: [1] }] })
    assert.equal(code(denied), 1); assert.deepEqual(response(denied).data.active_mission_list, [])
    assert.equal(digest(state(old)), frozen)
})

test('claim retains its original stage receipt and can be collected once after mission entry is closed', async () => {
    open(); const p = fixture(); response(await draw(p)); response(await exchange(p))
    control('active_mission_event:3', { enter: false, claim: true })
    const claimed = await post(p, '/active/receive', { active_mission_list: [{ mission_id: missionId, stages: [1] }] })
    assert.equal(code(claimed), 1); assert.equal(mission(p).stages['1'], true)
    const frozen = digest(state(p))
    const retry = await post(p, '/active/receive', { active_mission_list: [{ mission_id: missionId, stages: [1] }] })
    assert.equal(code(retry), 1); assert.deepEqual(response(retry).data.active_mission_list, [])
    assert.equal(code(await exchange(p)), 1); assert.equal(digest(state(p)), frozen)
})

test('a real SQLite active-mission failure rolls back character grant, consumed ticket and final campaign status together', async () => {
    open(); const p = fixture(); response(await draw(p)); const before = digest(state(p))
    db.exec(`CREATE TRIGGER fail_active69 BEFORE INSERT ON players_active_missions WHEN NEW.player_id=${p.id} AND NEW.id=21030 BEGIN SELECT RAISE(ABORT,'synthetic active69 failure'); END`)
    assert.equal((await exchange(p)).statusCode, 500); assert.equal(digest(state(p)), before)
    db.exec('DROP TRIGGER fail_active69')
    assert.equal(code(await exchange(p)), 1); assert.equal(mission(p).progress, 1)
    assert.equal(campaign(p).status, 4); assert.equal(inventory.getPlayerItemSync(p.id, 980004), 0)
    const frozen = digest(state(p)); assert.equal(code(await exchange(p)), 1); assert.equal(digest(state(p)), frozen)
})
