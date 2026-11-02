'use strict'
// Source-bound purchase responses for sequential native common-response replay.
// All balances below are calculated before invocation, never from a response.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict')
const { createRequire, Module } = require('node:module')
const { randomUUID, createHash } = require('node:crypto')
const { execFileSync, spawnSync } = require('node:child_process')
function options() {
    const result = {}
    for (let i = 2; i < process.argv.length; i++) {
        const key = process.argv[i]
        if (key === '--help') { console.log('node purchases.cjs --repo <source repo> --out <new directory> [--groups purchases]'); process.exit(0) }
        if (!['--repo', '--out', '--groups', '--child'].includes(key) || result[key] !== undefined
            || !process.argv[i + 1] || process.argv[i + 1].startsWith('--')) throw Error('Invalid or repeated argument: ' + key)
        result[key] = process.argv[++i]
    }
    if (!result['--repo'] || !result['--out']) throw Error('--repo and --out are required')
    if (result['--groups'] !== undefined && result['--groups'] !== 'purchases') throw Error('Only --groups purchases is supported')
    return result
}
const args = options(), child = Boolean(args['--child'])
const repo = fs.realpathSync(path.resolve(args['--repo'])), target = path.resolve(args['--out'])
const inside = (parent, candidate) => candidate === parent || candidate.startsWith(parent + path.sep)
if (inside(repo, target)) throw Error('--out must be outside the business source tree')
if (!child) {
    if (fs.existsSync(target)) throw Error('--out already exists; use a new directory')
    fs.mkdirSync(path.dirname(target), { recursive: true }); fs.mkdirSync(target)
}
const root = fs.realpathSync(target), runtime = path.join(root, 'runtime')
if (inside(repo, root)) throw Error('Resolved --out must be outside the business source tree')
if (child && path.resolve(process.env.DATA_DIR ?? '') !== runtime) throw Error('Child DATA_DIR mismatch')
for (const sub of ['tmp', 'seeds', 'responses', 'workers']) fs.mkdirSync(path.join(runtime, sub), { recursive: true })
Object.assign(process.env, { DATA_DIR: runtime, TEMP: path.join(runtime, 'tmp'), TMP: path.join(runtime, 'tmp'),
    SQLITE_TMPDIR: path.join(runtime, 'tmp'), GACHA_SEED_DIR: path.join(runtime, 'seeds'),
    TS_NODE_PROJECT: path.join(repo, 'tsconfig.json'), CN_WRITER_THREAD: '0', CN_MULTICORE: '0',
    CN_RESPONSE_WORKERS: '0', SQLITE_CHECKPOINT_WORKER: '0', MULTI_REALTIME_PROCESS: '0',
    MULTI_REALTIME_OWNER_CHILD: '0', MULTI_BATTLE_RELAY_PROCESS: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
const req = createRequire(path.join(repo, 'package.json')), hash = value => createHash('sha256').update(value).digest('hex')
req('ts-node/register/transpile-only')
// Hash every source/asset module before it executes, including lazy imports.
const sourceFiles = new Map()
for (const extension of ['.ts', '.json']) {
    const original = Module._extensions[extension]
    Module._extensions[extension] = (module, filename) => {
        if (inside(path.join(repo, 'src'), filename) || inside(path.join(repo, 'assets'), filename)) {
            const relative = path.relative(repo, filename).replaceAll('\\', '/')
            const digest = hash(fs.readFileSync(filename))
            if (sourceFiles.has(relative) && sourceFiles.get(relative) !== digest) throw Error('Source changed during run: ' + relative)
            sourceFiles.set(relative, digest)
        }
        return original(module, filename)
    }
}
for (const file of ['package.json', 'tsconfig.json']) sourceFiles.set(file, hash(fs.readFileSync(path.join(repo, file))))
const load = name => req(path.join(repo, 'src', name)), clone = value => JSON.parse(JSON.stringify(value))
const players = load('data/domains/player'), items = load('data/domains/item'), characters = load('data/domains/character')
const equipment = load('data/domains/equipment'), assets = load('lib/assets'), identities = load('lib/gameplay-request-identity')
let app, db, checks = 0, ownedTables
const equal = (actual, expected, label) => { checks++; assert.deepEqual(actual, expected, label) }
const check = (value, label) => { checks++; assert.ok(value, label) }
const quote = name => '"' + name.replaceAll('"', '""') + '"'
async function start() {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    identities.initializeGameplayRequestIdentitySchemaSync(db)
    equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(runtime), 'database is isolated')
    ownedTables = db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").all()
        .filter(({name}) => name !== 'players' && db.prepare(`PRAGMA table_info(${quote(name)})`).all().some(row => row.name === 'player_id'))
        .map(row => row.name).sort()
    app = req('fastify')({ logger: false })
    load('lib/cn-response-hook').installCnResponseEncoding(app, {
        pool: new (load('lib/cn-response-worker-pool').CnResponseWorkerPool)({ size: 0, workerPath: path.join(runtime, 'workers', 'disabled.js') }),
        compression: load('lib/cn-load-http-compression').getCnLoadHttpCompressionConfig({ CN_LOAD_HTTP_COMPRESSION: 'off' }),
    })
    for (const [file, prefix] of [['shop', 'shop'], ['expod', 'expod'], ['boxGacha', 'box_gacha'], ['character/mana', 'character']])
        await app.register(load('routes/api/' + file).default, { prefix: '/api/index.php/' + prefix })
    await app.ready()
}
async function close() { await app?.close(); await load('lib/seed-validator').default.close(); if (db?.open) db.close() }
function fixture() {
    const account = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'air-purchases', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(account.id), p = { id: player.id, accountId: account.id, viewer: 891000000 + player.id }
    load('data/activeAccount').saveAccountDefaultPlayer(account.id, p.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(p.viewer), account.id, '2099-01-01T00:00:00Z')
    p.token = db.transaction(() => identities.issueGameplayLoginTokenSync(db, {
        accountId: account.id, viewerId: p.viewer, udid: 'air-purchases-' + p.viewer, expiresAt: Date.now() + 86400000,
    }))()
    // Nonempty unrelated inventory and paid balances expose replacement errors.
    items.setPlayerItemSync(p.id, 101, 7)
    players.updatePlayerSync({ id: p.id, freeMana: 100, paidMana: 12, freeVmoney: 50, vmoney: 17,
        expPool: 0, expPooledTime: new Date(), stamina: 0, staminaHealTime: new Date() })
    return p
}
function projection(p) {
    const v = players.getPlayerSync(p.id)
    return clone({ items: Object.fromEntries(Object.entries(items.getPlayerItemsSync(p.id)).filter(([,count]) => count > 0)),
        equipments: Object.fromEntries(Object.entries(equipment.getPlayerEquipmentListSync(p.id)).map(([id,e]) => [id, { equipmentId: Number(id), ...e }])),
        userInfo: { free_vmoney: v.freeVmoney, vmoney: v.vmoney, free_mana: v.freeMana, paid_mana: v.paidMana, pooled_exp: v.expPool, stamina: v.stamina },
        characters: Object.fromEntries(Object.entries(characters.getPlayerCharactersSync(p.id)).map(([id,c]) => [id, {
            characterId: Number(id), exp: c.exp, stack: c.stack, overLimitStep: c.overLimitStep,
            evolutionLevel: c.evolutionLevel, protection: c.protection, exBoost: c.exBoost ?? null,
        }])), crazyGachaResultList: {} })
}
function manaNodes(p, characterId) {
    return { [characterId]: Object.entries(characters.getPlayerCharacterManaNodeAwakeLevelsSync(p.id, characterId))
        .map(([id,level]) => ({ multiplied_id: Number(id), awake_level: level })).sort((a,b) => a.multiplied_id - b.multiplied_id) }
}
function snapshot(p) {
    return clone({ player: players.getPlayerSync(p.id), ...Object.fromEntries(ownedTables.map(table => [table,
        db.prepare(`SELECT * FROM ${quote(table)} WHERE player_id=?`).all(p.id).sort((a,b) => JSON.stringify(a).localeCompare(JSON.stringify(b)))])) })
}
function diagnostics(state) { return { player: { freeMana: state.player.freeMana, paidMana: state.player.paidMana,
    freeVmoney: state.player.freeVmoney, vmoney: state.player.vmoney, expPool: state.player.expPool, stamina: state.player.stamina },
    tableCounts: Object.fromEntries(Object.entries(state).filter(([,v]) => Array.isArray(v)).map(([k,v]) => [k,v.length])), stateSha256: hash(JSON.stringify(state)) } }
async function invoke(p, route, body) {
    const result = await app.inject({ method: 'POST', url: route, headers: { login_token: p.token, device: 'android' }, payload: body })
    const contentType = String(result.headers['content-type'])
    let response = contentType.includes('application/x-msgpack') ? req('msgpackr').unpack(Buffer.from(result.body, 'base64')) : JSON.parse(result.body)
    if (typeof response === 'string') response = JSON.parse(response)
    return { httpStatus: result.statusCode, response, wire: result.body, contentType }
}
const output = { schemaVersion: 2, generatedAt: new Date().toISOString(), groups: ['purchases'], completed: false,
    source: { root: repo, mode: 'src/ts-node/transpile-only', outUsed: false }, environment: {
        dataDirectory: runtime, seedDirectory: process.env.GACHA_SEED_DIR, tempDirectory: process.env.TMP,
        responseWorkers: 0, transport: 'Fastify.inject; real cn-response-hook base64(MessagePack); no listening socket', syntheticOnly: true,
    }, cases: [] }
const save = () => fs.writeFileSync(path.join(root, 'fixtures.json'), JSON.stringify(output) + '\n')
async function runCase(id, operation, route, prepare, expect, verify, receipt = true) {
    const p = fixture(), setup = prepare(p), before = projection(p)
    // Freeze expectations from fixture inputs BEFORE the first route invocation.
    const expected = clone(before); expect(expected, setup)
    const expectedNodes = setup.expectedManaNodes
    const c = { id, group: 'purchases', operation, notes: receipt
        ? 'Real success then same native request in a fresh source process; durable receipt replays identical business data without another debit or grant.'
        : 'Real success then same request; persisted node ownership returns a current-state refresh with no second debit. Its item_list is intentionally empty.',
        setup: setup.description, before, expectedAfter: expected, steps: [] }
    if (expectedNodes) { c.beforeManaNodes = manaNodes(p, setup.characterId); c.expectedManaNodes = clone(expectedNodes) }
    output.cases.push(c)
    const body = { viewer_id: p.viewer, api_count: 1, ...setup.body }
    let paidState, firstData
    for (const phase of ['success', 'retry']) {
        const stepId = id + '/' + phase, beforeState = snapshot(p), beforeProjection = projection(p)
        const payload = phase === 'success' ? body : { ...body, retry_count: 1 }
        let result
        if (phase === 'retry' && receipt) {
            const inputPath = path.join(runtime, 'responses', id + '-input.json'), resultPath = path.join(runtime, 'responses', id + '-child.json')
            fs.writeFileSync(inputPath, JSON.stringify({ p, route, body: payload, resultPath }))
            const processResult = spawnSync(process.execPath, [__filename, '--repo', repo, '--out', root, '--child', inputPath],
                { cwd: repo, env: process.env, encoding: 'utf8', windowsHide: true, timeout: 60000, maxBuffer: 4 * 1024 * 1024 })
            fs.writeFileSync(path.join(runtime, 'responses', id + '-child.log'), processResult.stdout + processResult.stderr)
            equal(processResult.status, 0, stepId + ' fresh source process: ' + processResult.stderr.slice(-1000))
            result = JSON.parse(fs.readFileSync(resultPath, 'utf8')); fs.unlinkSync(resultPath); fs.unlinkSync(inputPath)
        } else result = await invoke(p, route, payload)
        const afterState = snapshot(p), wire = { contentType: result.contentType, bytes: Buffer.byteLength(result.wire), sha256: hash(result.wire) }
        if (id === 'source-shop-buy' && phase === 'success') {
            const file = path.join(runtime, 'responses', 'mutation.body.txt'); fs.writeFileSync(file, result.wire)
            wire.path = path.relative(root, file).replaceAll('\\', '/')
        }
        const step = { id: stepId, route, httpStatus: result.httpStatus, request: { body: payload, headers: { login_token: p.token, device: 'android' } },
            response: result.response, before: beforeProjection, expectedAfter: clone(expected), newProcess: phase === 'retry' && receipt,
            wire, diagnostics: { before: diagnostics(beforeState), after: diagnostics(afterState) } }
        if (expectedNodes) step.expectedManaNodes = clone(expectedNodes)
        c.steps.push(step); save()
        equal(result.httpStatus, 200, stepId + ' HTTP success: ' + JSON.stringify(result.response).slice(0,400))
        check(result.contentType.includes('application/x-msgpack'), stepId + ' production codec')
        equal(result.response.data_headers.result_code, 1, stepId + ' native result code')
        check(['force_update','asset_update','force_news','short_udid','viewer_id','servertime','result_code'].every(key => Object.hasOwn(result.response.data_headers,key)), stepId + ' complete headers')
        equal(projection(p), expected, stepId + ' independent economic/character expectation')
        if (expectedNodes) {
            equal(manaNodes(p, setup.characterId), expectedNodes, stepId + ' persisted nodes')
            equal(result.response.data.user_character_mana_node_list, expectedNodes, stepId + ' authoritative response nodes')
        }
        verify(p, result.response.data, setup, phase)
        if (phase === 'success') {
            firstData = clone(result.response.data); paidState = afterState
            if (receipt) {
                const rows = db.prepare("SELECT response_json FROM player_operation_receipts WHERE player_id=? AND operation='gameplay_mutation.v1'").all(p.id)
                equal(rows.length, 1, id + ' exactly one persisted mutation receipt')
                equal(JSON.parse(rows[0].response_json).response, firstData, id + ' receipt stores complete business data')
            }
        } else {
            equal(afterState, paidState, id + ' retry leaves ALL owned tables and player unchanged')
            if (receipt) equal(result.response.data, firstData, id + ' durable exact business response')
            else equal(result.response.data.item_list, {}, id + ' existing-node retry preserves refresh semantics')
        }
    }
    equal(c.steps[1].before, c.steps[0].expectedAfter, id + ' client replay is sequential, without resetting state')
    save()
}
function boxControl() {
    const store = load('lib/content-operations').contentOperations()
    for (const key of ['world_story_event:200103', 'box_gacha:1001']) store.update(key, {
        expectedRevision: store.revision(), catalogDigest: store.digest, reason: 'Isolated AIR box purchase fixture', readiness: 'verified', evidence: 'Synthetic test only',
        flags: key.startsWith('box_') ? { visible: true, enter: true, claim: true } : { visible: true, enter: true, exchange: true }, endsAtMs: null,
    }, Date.now())
}
async function main() {
    const git = (...args) => execFileSync('git', args, { cwd: repo, encoding: 'utf8' }).trimEnd()
    const initialStatus = git('status', '--porcelain', '-uall'), initialHead = git('rev-parse', 'HEAD')
    output.source.head = initialHead; output.source.dirtyStatus = initialStatus.split(/\r?\n/).filter(Boolean)
    output.generator = { path: __filename, sha256: hash(fs.readFileSync(__filename)) }
    await start()
    await runCase('source-shop-buy', 'shop.buy', '/api/index.php/shop/buy', p => {
        const master = assets.getShopItemSync(2, 200070)
        equal(master.userCost, { type: 1, amount: 100 }, 'pinned shop cost')
        equal(master.rewards, [{ type: 0, id: 2, count: 1 }], 'pinned shop item')
        items.setPlayerItemSync(p.id, 2, 4)
        return { body: { shop_type: 2, shop_item_id: 200070, number: 1 }, description: { item: 2, before: 4, grant: 1, manaCost: 100 } }
    }, e => { e.userInfo.free_mana = 0; e.items['2'] = 5 }, (p,data) => {
        equal(data.item_list['2'], 5, 'shop absolute item amount'); equal(data.user_info.free_mana, 0, 'shop last free mana')
        equal(load('data/domains/shopPurchase').getPlayerShopPurchaseCountSync(p.id, load('lib/shop-sales').getShopPurchaseKey(2,200070)), 1, 'shop once-only stock')
    })
    await runCase('source-recover-stamina', 'shop.recover_stamina', '/api/index.php/shop/recover_stamina', p => {
        equal(assets.getConfigSync().stamina_recovery_virtual_money, 50, 'pinned stamina bead cost')
        equal(assets.getConfigSync().stamina_recovery_value, 100, 'pinned stamina recovery')
        return { body: {}, description: { staminaBefore: 0, staminaAfter: 100, beadCost: 50, paidStonesPreserved: 17 } }
    }, e => { e.userInfo.free_vmoney = 0; e.userInfo.stamina = 100 }, (_p,data) => {
        equal(data.user_info.stamina, 100, 'stamina exact grant'); equal(data.user_info.free_vmoney, 0, 'stamina spends free stones first')
        equal(data.user_info.vmoney, 17, 'stamina preserves paid stones')
    })
    await runCase('source-inject-exp', 'expod.inject_exp', '/api/index.php/expod/inject_exp', p => {
        players.updatePlayerSync({ id: p.id, expPool: 100, expPooledTime: new Date() }); characters.insertDefaultPlayerCharacterSync(p.id,243001)
        return { body: { character_id: 243001, exp: 100 }, description: { characterId: 243001, expBefore: 0, expGrant: 100, poolBefore: 100 } }
    }, e => { e.userInfo.pooled_exp = 0; e.characters['243001'].exp = 100 }, (_p,data) => {
        equal(data.user_info.exp_pool, 0, 'EXP pool emptied'); equal(data.character_list.find(c => c.character_id === 243001).exp, 100, 'absolute character EXP')
    })
    await runCase('source-box-exec', 'boxGacha.exec', '/api/index.php/box_gacha/exec', p => {
        boxControl(); const master = assets.getBoxGachaSync(1001), box = load('data/domains/boxGacha'), rewardId = 1100101005
        equal([master.redeemItemId,master.redeemItemCount], [70017,10], 'pinned box currency')
        equal(master.boxes[1][rewardId], { type: 0, count: 1, available: 150, tier: 0, id: 9 }, 'pinned final box reward')
        // Real draw algorithm sees only one remaining unit; no RNG replacement.
        for (const [id,reward] of Object.entries(master.boxes[1])) box.insertPlayerBoxGachaDrawnRewardSync(p.id,1001,1,
            { id: Number(id), number: reward.available - (Number(id) === rewardId ? 1 : 0) })
        const writeBox = box.getPlayerBoxGachaSync(p.id,1001,1) ? box.updatePlayerBoxGachaSync : box.insertPlayerBoxGachaSync
        writeBox(p.id,1001,{ boxId: 1, isClosed: false, remainingNumber: 1, resetTimes: 0 })
        items.setPlayerItemSync(p.id,70017,10); items.setPlayerItemSync(p.id,9,4)
        return { body: { box_gacha_id: 1001, box_id: 1, number: 1, stop_on_featured_rewards: false },
            description: { syntheticPriorDraws: 399, remaining: 1, rewardId, itemId: 9, grant: 1, currency: 70017, cost: 10 } }
    }, e => { delete e.items['70017']; e.items['9'] = 5 }, (p,data) => {
        equal(data.drawn_reward_list,[{reward_id:1100101005,number:1}],'box deterministic real draw')
        equal(data.item_list['70017'],0,'box zero currency is explicit'); equal(data.item_list['9'],5,'box absolute reward inventory')
        equal(load('data/domains/boxGacha').getPlayerBoxGachaSync(p.id,1001,1), {boxId:1,isClosed:true,remainingNumber:0,resetTimes:0}, 'box persisted closed after last draw')
        equal(load('data/domains/boxGacha').getPlayerBoxGachaDrawnRewardsSync(p.id,1001,1).reduce((sum,r)=>sum+r.number,0),400,'box one additional persisted draw')
    })
    await runCase('source-mana-learn', 'mana.learn', '/api/index.php/character/learn_mana_node', p => {
        characters.insertDefaultPlayerCharacterSync(p.id,243001); players.updatePlayerSync({id:p.id,freeMana:50,paidMana:10})
        const node = assets.getCharacterManaNodesSync(243001,1)[486002201]
        equal({mana:node.manaCost,items:node.items},{mana:60,items:{13:3}},'pinned learn cost'); items.setPlayerItemSync(p.id,13,3)
        return { body: {character_id:243001,mana_node_multiplied_id_list:[486002201]}, characterId:243001,
            expectedManaNodes:{243001:[{multiplied_id:486002201,awake_level:0}]}, description:{characterId:243001,nodeId:486002201,manaCost:60,materials:{13:3}} }
    }, e => { e.userInfo.free_mana=0; e.userInfo.paid_mana=0; delete e.items['13'] }, (_p,data,_setup,phase) => {
        equal(data.user_info,{free_mana:0,paid_mana:0},'learn spends free then paid mana')
        equal(data.item_list,phase==='success'?{13:0}:{},'learn exact materials/refresh response')
    }, false)
    await runCase('source-mana-awake', 'mana.awake', '/api/index.php/character/awake_mana_node', p => {
        const id=341005,nodeId=682010219,board=assets.getCharacterManaNodesSync(id,1),boardIds=Object.keys(board).map(Number).sort((a,b)=>a-b)
        equal(boardIds,Array.from({length:23},(_,i)=>682010201+i),'pinned complete base board')
        equal(assets.getManaNodeAwakeCost(id,nodeId,assets.getCharacterDataSync(id).rarity),{manaAmount:3000,items:{99:2,70047:40}},'pinned awake cost')
        characters.insertDefaultPlayerCharacterSync(p.id,id); characters.updatePlayerCharacterSync(p.id,id,{evolutionLevel:1,manaBoardIndex:1})
        characters.insertPlayerCharacterManaNodesSync(p.id,id,boardIds); load('data/domains/character_awake').upsertPlayerCharacterAwakeUnlockSync(p.id,id,1,1)
        players.updatePlayerSync({id:p.id,freeMana:2000,paidMana:1000}); items.setPlayerItemSync(p.id,99,2); items.setPlayerItemSync(p.id,70047,40)
        return {body:{character_id:id,mana_node_multiplied_id_list:[nodeId],awake_level:1},characterId:id,
            expectedManaNodes:{[id]:boardIds.map(value=>({multiplied_id:value,awake_level:value===nodeId?1:0}))},
            description:{characterId:id,nodeId,baseBoardComplete:true,persistedUnlockLevel:1,manaCost:3000,materials:{99:2,70047:40},evolutionBefore:1,evolutionAfter:2}}
    }, e => {e.userInfo.free_mana=0;e.userInfo.paid_mana=0;delete e.items['99'];delete e.items['70047'];e.characters['341005'].evolutionLevel=2}, (_p,data,_setup,phase)=>{
        equal(data.user_info,{free_mana:0,paid_mana:0},'awake spends free then paid mana')
        equal(data.item_list,phase==='success'?{99:0,70047:0}:{},'awake exact materials/refresh response')
        equal(data.character_list.find(c=>c.character_id===341005).evolution_level,2,'awake evolution persisted and returned')
    }, false)
    equal(git('rev-parse','HEAD'),initialHead,'business HEAD unchanged'); equal(git('status','--porcelain','-uall'),initialStatus,'business status unchanged')
    output.source.relatedFiles = [...sourceFiles].sort(([a],[b])=>a.localeCompare(b)).map(([file,sha256])=>{
        equal(hash(fs.readFileSync(path.join(repo,file))),sha256,'source bytes unchanged: '+file);return {path:file,sha256}
    })
    equal(hash(fs.readFileSync(__filename)),output.generator.sha256,'generator bytes unchanged')
    equal(output.cases.length,6,'six required operations'); equal(output.cases.reduce((n,c)=>n+c.steps.length,0),12,'twelve required steps')
    output.assertions=checks;output.completed=true;save()
    fs.writeFileSync(path.join(root,'execution-result.json'),JSON.stringify({success:true,assertions:checks,cases:6,steps:12,sourceMode:output.source.mode,outUsed:false,
        command:{node:process.execPath,args:process.argv.slice(1)},fixturesSha256:hash(fs.readFileSync(path.join(root,'fixtures.json')))},null,2)+'\n')
    console.log('COMPLETE '+JSON.stringify({cases:6,steps:12,assertions:checks}))
}
;(async()=>{
    try {
        if(child){await start();const input=JSON.parse(fs.readFileSync(args['--child'],'utf8'));fs.writeFileSync(input.resultPath,JSON.stringify(await invoke(input.p,input.route,input.body)))}
        else await main()
    } catch(error){
        console.error(error.stack);process.exitCode=1
        if(!child){output.completed=false;output.assertions=checks;output.failure=error.stack;save();fs.writeFileSync(path.join(root,'execution-result.json'),JSON.stringify({success:false,assertions:checks,failure:error.stack},null,2)+'\n')}
    } finally {await close()}
})()
