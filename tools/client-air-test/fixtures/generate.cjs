'use strict'
// Invoke actual source routes in a fresh isolated output directory. The only
// complete application response representation is cases[].steps[].response.
const fs = require('node:fs'), path = require('node:path'), assert = require('node:assert/strict')
const { createRequire } = require('node:module'), { randomUUID, createHash } = require('node:crypto')
const { spawnSync, execFileSync } = require('node:child_process')
const child = process.argv.includes('--child')
const supportedGroups = ['tutorial', 'mail', 'equipment', 'crazy', 'ex']
function options() {
    const values = {}
    for (let i = 2; i < process.argv.length; i++) {
        const key = process.argv[i]
        if (key === '--help') { console.log('node generate.cjs --repo <source repo> --out <new directory> [--groups tutorial,mail,equipment,crazy,ex]'); process.exit(0) }
        if (!['--repo', '--out', '--groups', '--child'].includes(key) || !process.argv[i+1] || process.argv[i+1].startsWith('--')) throw Error('Invalid argument: ' + key)
        if (values[key] !== undefined) throw Error('Duplicate argument: ' + key)
        values[key] = process.argv[++i]
    }
    if (!values['--repo'] || !values['--out']) throw Error('--repo and --out are required')
    return values
}
const args = options(), repo = fs.realpathSync(path.resolve(args['--repo'])), root = path.resolve(args['--out'])
const groups = [...new Set((args['--groups'] ?? supportedGroups.join(',')).split(',').map(x => x.trim()))]
if (!groups.length || groups.some(group => !supportedGroups.includes(group))) throw Error('Unknown or empty --groups; choose ' + supportedGroups.join(','))
const selected = group => groups.includes(group)
if (root === repo || root.startsWith(repo + path.sep)) throw Error('--out must be outside the business source tree')
if (!child) {
    if (fs.existsSync(root)) throw Error('--out already exists; use a fresh directory (no overwrite)')
    fs.mkdirSync(path.dirname(root), { recursive: true }); fs.mkdirSync(root)
} else if (!fs.existsSync(root)) throw Error('Child output directory is missing')
const realRoot = fs.realpathSync(root)
if (realRoot === repo || realRoot.startsWith(repo + path.sep)) throw Error('Resolved --out must be outside the business source tree')
const runDir = path.join(realRoot, 'runtime')
if (child && path.resolve(process.env.DATA_DIR ?? '') !== runDir) throw Error('Child DATA_DIR mismatch')
for (const sub of ['seeds', 'tmp', 'workers', 'responses']) fs.mkdirSync(path.join(runDir, sub), { recursive: true })
Object.assign(process.env, { DATA_DIR: runDir, TEMP: path.join(runDir, 'tmp'), TMP: path.join(runDir, 'tmp'),
    SQLITE_TMPDIR: path.join(runDir, 'tmp'), GACHA_SEED_DIR: path.join(runDir, 'seeds'),
    TS_NODE_PROJECT: path.join(repo, 'tsconfig.json'), CN_WRITER_THREAD: '0', CN_MULTICORE: '0',
    CN_RESPONSE_WORKERS: '0', SQLITE_CHECKPOINT_WORKER: '0', MULTI_REALTIME_PROCESS: '0',
    MULTI_REALTIME_OWNER_CHILD: '0', MULTI_BATTLE_RELAY_PROCESS: '0', GAME_VERBOSE_LOGS: 'false', GAME_ROUTINE_LOGS: 'off' })
const req = createRequire(path.join(repo, 'package.json'))
req('ts-node/register/transpile-only')
const load = name => req(path.join(repo, 'src', name))
const clone = value => JSON.parse(JSON.stringify(value))
// EX's existing dedicated select receipt returns current state and fresh display
// update_time. Compare its business fields only; preserve raw fixtures untouched.
const exSelectBusiness = value => { const c = clone(value); for (const row of c.character_list ?? []) delete row.update_time; return c }
const hash = value => createHash('sha256').update(value).digest('hex')
const timers = [], interval = global.setInterval
let loadRoutes
try { global.setInterval = (...args) => { const t = interval(...args); timers.push(t); return t }; loadRoutes = load('routes/cn/load').default }
finally { global.setInterval = interval }
const players = load('data/domains/player'), items = load('data/domains/item'), chars = load('data/domains/character')
const equipment = load('data/domains/equipment'), mails = load('data/domains/mail'), assets = load('lib/assets')
const identities = load('lib/gameplay-request-identity'), pending = load('data/domains/ex-boost-pending')
const crazy = load('data/domains/crazy_gacha')
// Independent rule verified against the captured native acquisition master.
// Do not derive expected quantities from the shared grant's returned payload.
const duplicateItemsPerCharacter = Object.freeze({ 3: 1, 4: 1, 5: 3 })
function expectedDuplicateItemCount(characterId) {
    const rarity = Number(assets.getCharacterDataSync(characterId).rarity)
    if (!Object.hasOwn(duplicateItemsPerCharacter, rarity)) throw Error('No verified EX compensation rule for rarity ' + rarity)
    return duplicateItemsPerCharacter[rarity]
}
let app, db, checks = 0
const check = (condition, label) => { checks++; assert.ok(condition, label) }
const equal = (actual, expected, label) => { checks++; assert.deepEqual(actual, expected, label) }
async function start() {
    load('data').initializeDatabase(); db = load('data/db').getDb()
    identities.initializeGameplayRequestIdentitySchemaSync(db)
    equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(runDir), 'database stays inside isolated run')
    app = req('fastify')({ logger: false })
    load('lib/cn-response-hook').installCnResponseEncoding(app, {
        pool: new (load('lib/cn-response-worker-pool').CnResponseWorkerPool)({ size: 0, workerPath: path.join(runDir, 'workers', 'disabled.js') }),
        compression: load('lib/cn-load-http-compression').getCnLoadHttpCompressionConfig({ CN_LOAD_HTTP_COMPRESSION: 'off' }),
    })
    if (selected('ex') || selected('crazy')) await app.register(loadRoutes, { prefix: '/api/index.php' })
    const names = [...(selected('tutorial') ? ['tutorial'] : []), ...(selected('mail') ? ['mail'] : []),
        ...(selected('equipment') ? ['equipment', 'sell'] : []), ...(selected('crazy') ? ['gacha'] : []), ...(selected('ex') ? ['exBoost'] : [])]
    for (const name of names)
        await app.register(load('routes/api/' + name).default, { prefix: '/api/index.php/' + (name === 'sell' ? 'equipment' : name) })
    await app.ready()
}
async function close() {
    await app?.close(); await load('lib/seed-validator').default.close()
    timers.forEach(clearInterval)
    if (db?.open) db.close()
}
function login(p) {
    p.token = db.transaction(() => identities.issueGameplayLoginTokenSync(db, {
        accountId: p.accountId, viewerId: p.viewer, udid: 'synthetic-runtime-' + p.viewer, expiresAt: Date.now() + 86400000,
    }))(); p.count = 0; return p
}
function fixture() {
    const a = load('data/domains/account').insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'synthetic-client-runtime', idpId: randomUUID(), status: 'normal' })
    const player = players.insertDefaultPlayerSync(a.id), p = { id: player.id, accountId: a.id, viewer: 880000000 + player.id }
    load('data/activeAccount').saveAccountDefaultPlayer(a.id, player.id)
    db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(p.viewer), a.id, '2099-01-01T00:00:00Z')
    // A nonempty unrelated inventory key makes replacement-vs-merge mistakes visible.
    items.setPlayerItemSync(p.id, 101, 7)
    players.updatePlayerSync({ id: p.id, freeVmoney: 1234, vmoney: 50, freeMana: 456, paidMana: 12 })
    return login(p)
}
function projection(p) {
    const player = players.getPlayerSync(p.id), characterMap = chars.getPlayerCharactersSync(p.id)
    return clone({ items: Object.fromEntries(Object.entries(items.getPlayerItemsSync(p.id)).filter(([,v]) => v > 0)),
        equipments: Object.fromEntries(Object.entries(equipment.getPlayerEquipmentListSync(p.id)).map(([id, value]) => [id, { equipmentId: Number(id), ...value }])),
        userInfo: { free_vmoney: player.freeVmoney, vmoney: player.vmoney, free_mana: player.freeMana, paid_mana: player.paidMana, pooled_exp: player.expPool },
        characters: Object.fromEntries(Object.entries(characterMap).map(([id,c]) => [id, { characterId: Number(id), exp: c.exp, stack: c.stack,
            overLimitStep: c.overLimitStep, evolutionLevel: c.evolutionLevel, protection: c.protection, exBoost: c.exBoost ?? null }])),
        crazyGachaResultList: crazy.getCrazyGachaRecoverySync(p.id).crazy_gacha_result_list })
}
function serverState(p) {
    const player = players.getPlayerSync(p.id)
    const result = { player: { id: p.id, tutorialStep: player.tutorialStep, tutorialSkipFlag: player.tutorialSkipFlag,
        freeVmoney: player.freeVmoney, vmoney: player.vmoney, freeMana: player.freeMana, paidMana: player.paidMana, expPool: player.expPool } }
    for (const table of ['players_characters', 'players_items', 'players_equipment', 'players_mails', 'players_receive_history', 'players_ex_boost_pending_draws', 'players_crazy_gacha'])
        result[table] = db.prepare(`SELECT * FROM ${table} WHERE player_id=? ORDER BY rowid`).all(p.id)
    result.receipts = db.prepare('SELECT operation,request_key,response_json FROM player_operation_receipts WHERE player_id=? ORDER BY operation,request_key').all(p.id)
    return clone(result)
}
function body(p, fields = {}, count = ++p.count) { return { viewer_id: p.viewer, api_count: count, ...fields } }
async function invoke(p, route, payload) {
    const response = await app.inject({ method: 'POST', url: '/api/index.php/' + route, headers: { login_token: p.token, device: 'android' }, payload })
    const packed = String(response.headers['content-type']).includes('application/x-msgpack')
    let decoded = packed ? req('msgpackr').unpack(Buffer.from(response.body, 'base64')) : JSON.parse(response.body)
    if (typeof decoded === 'string') decoded = JSON.parse(decoded)
    return { httpStatus: response.statusCode, response: decoded, wire: response.body, contentType: response.headers['content-type'] }
}
const output = { schemaVersion: 2, generatedAt: new Date().toISOString(), groups, source: { root: repo, mode: 'src/ts-node/transpile-only', outUsed: false },
    environment: { dataDirectory: runDir, seedDirectory: process.env.GACHA_SEED_DIR, tempDirectory: process.env.TMP, responseWorkers: 0,
        transport: 'Fastify.inject; real cn-response-hook base64(MessagePack); no listening socket', syntheticOnly: true }, cases: [] }
function savePartial() { fs.writeFileSync(path.join(root, 'fixtures.json'), JSON.stringify(output) + '\n') }
const originalStates = new WeakMap()
function diagnostics(state) {
    return { player: state.player, tableCounts: Object.fromEntries(Object.entries(state).filter(([,v]) => Array.isArray(v)).map(([key,v]) => [key,v.length])),
        pending: state.players_ex_boost_pending_draws.map(r => ({characterId:r.character_id,drawId:r.draw_id})),
        stateSha256: hash(JSON.stringify(state)) }
}
// Keep full state only in memory for the assertions, never repeat receipts or
// database rows in fixture JSON. WeakMap lets completed cases be collected.
function retainState(object, before, after) { originalStates.set(object, { before, after }); return object }
const states = object => originalStates.get(object)
const wireKinds = new Set()
function begin(id, group, p, notes) {
    const c = { id, group, notes, before: projection(p), expectedAfter: null, steps: [] }
    output.cases.push(c); return c
}
async function step(c, p, id, route, fields = {}, options = {}) {
    const payload = options.payload ?? body(p, fields)
    const before = projection(p), rawBefore = serverState(p)
    let result
    if (options.newProcess) {
        const input = path.join(runDir, 'responses', id + '-input.json'), target = path.join(runDir, 'responses', id + '-child.json')
        fs.writeFileSync(input, JSON.stringify({ p, route, payload, target }))
        const childRun = spawnSync(process.execPath, [__filename, '--repo', repo, '--out', root, '--groups', groups.join(','), '--child', input], { cwd: repo, env: process.env, encoding: 'utf8', windowsHide: true, timeout: 60000, maxBuffer: 8 * 1024 * 1024 })
        fs.writeFileSync(path.join(runDir, 'responses', id + '-child.log'), childRun.stdout + childRun.stderr)
        equal(childRun.status, 0, 'fresh process exit for ' + id + ': ' + childRun.stderr.slice(-2000))
        result = JSON.parse(fs.readFileSync(target, 'utf8'))
        // Successful child result is now owned by the single fixture response.
        fs.unlinkSync(target); fs.unlinkSync(input)
    } else result = await invoke(p, route, payload)
    const wireKind = route === 'load' ? 'load' : 'mutation'
    const wire = { contentType: result.contentType, bytes: Buffer.byteLength(result.wire), sha256: hash(result.wire) }
    if (!wireKinds.has(wireKind)) {
        const wirePath = path.join(runDir, 'responses', wireKind + '.body.txt')
        fs.writeFileSync(wirePath, result.wire); wire.path = path.relative(root,wirePath).replaceAll('\\','/'); wireKinds.add(wireKind)
    }
    const after = serverState(p)
    const s = { id, route: '/api/index.php/' + route, httpStatus: result.httpStatus, request: { body: payload, headers: { login_token: p.token, device: 'android' } },
        response: result.response, before, expectedAfter: projection(p), newProcess: options.newProcess === true,
        wire, diagnostics: { before: diagnostics(rawBefore), after: diagnostics(after) } }
    if (route === 'load') s.expectedRestoreState = c.expectedRestoreState
    if (options.recoveryPhase) s.recoveryPhase = options.recoveryPhase
    if (c.group === 'crazy') s.expectedLastCrazyGachaDrawResult = clone(crazy.getCrazyGachaRecoverySync(p.id).last_crazy_gacha_draw_result)
    c.steps.push(s); c.expectedAfter = s.expectedAfter
    retainState(s,rawBefore,after)
    // A failing route remains inspectable as a single step.response as well.
    equal(result.httpStatus, options.status ?? 200, id + ' HTTP status: ' + JSON.stringify(result.response).slice(0,500))
    if (result.httpStatus === 200) {
        equal(result.response.data_headers.result_code, 1, id + ' native result code')
        check(['force_update', 'asset_update', 'force_news', 'short_udid', 'viewer_id', 'servertime', 'result_code'].every(k => Object.hasOwn(result.response.data_headers, k)), id + ' complete common headers')
    }
    if (route === 'load') equal(result.response.data.user_tutorial === null, c.expectedRestoreState === 'None', id + ' tutorial profile matches required restore state')
    savePartial(); return s
}
function mail(p, type, typeId, number) {
    return mails.insertMailSync(p.id, { reason_id: 1, subject: 'Synthetic runtime fixture', description: 'Generated only in isolated validation database', type, type_id: typeId, number,
        receive_time: '0000-00-00 00:00:00', create_time: '2026-10-25 00:00:00', reward_period_limited: 0, reward_limit_time: null })
}
function grantExEligible(p) {
    load('lib/character').givePlayerCharacterSync(p.id, 111015)
    chars.updatePlayerCharacterSync(p.id, 111015, { overLimitStep: load('lib/character-overlimit').getCharacterMaxOverLimit(111015, assets.getCharacterDataSync(111015).rarity) })
    items.setPlayerItemSync(p.id, 10001, 10)
}
async function generateMailExFixtures() {
    // Calculate expectations from mail inputs and the verified rarity rule;
    // compare authoritative changes separately from response display metadata.
    const characterReward = load('lib/character')
    function prepare(id, attachments) {
        const p = fixture(), characterInputs = []
        for (const characterId of new Set(attachments.map(row=>row.characterId))) {
            characterReward.givePlayerCharacterSync(p.id,characterId)
            const itemId = characterReward.getCharacterDuplicateRewardItemId(characterId)
            check(Number.isInteger(itemId) && itemId >= 14001 && itemId <= 14018,'mail EX uses current 140xx duplicate compensation')
            items.setPlayerItemSync(p.id,itemId,0)
            const asset = assets.getCharacterDataSync(characterId)
            characterInputs.push({character_id:characterId,rarity:asset.rarity,element:asset.element,
                duplicate_item_id:itemId,duplicate_item_count:expectedDuplicateItemCount(characterId)})
        }
        const inputs = attachments.map(row=>({mail_id:mail(p,mails.MailType.CHARACTER,row.characterId,row.number),
            character_id:row.characterId,number:row.number,item_id:characterReward.getCharacterDuplicateRewardItemId(row.characterId),
            duplicate_item_count:expectedDuplicateItemCount(row.characterId)}))
        const c = begin(id,'mail',p,'Mail EX UI contract: characters already owned and compensation inventory starts at 0. Actual route responses are unchanged; expected compensation is independent of their display fields. Native retries retain the first request capture; a new identity captures current inventory.')
        c.clientScenario = 'mail-ex'
        c.setup = { mails:inputs, characters:characterInputs, captureAllExItemIdsIncludingZero:true,
            characterMetadataSource:'Character rarity/element from server assets; item ID from getCharacterDuplicateRewardItemId. Independent verified compensation rule: rarity 3/4 gives 1, rarity 5 gives 3 per duplicate. The AIR suite separately checks the captured native acquisition master.' }
        return {p,c,inputs}
    }
    function expectedGrant(s, inputs) {
        const totals = {}, copies = {}, batch = []
        for (const entry of inputs) {
            check(Boolean(s.before.characters[String(entry.character_id)]),'mail EX attachment character was owned before claim')
            const itemCount = entry.number * entry.duplicate_item_count
            totals[entry.item_id] = (totals[entry.item_id]??0)+itemCount
            copies[entry.character_id] = (copies[entry.character_id]??0)+entry.number
            batch.push({mail_id:entry.mail_id,item_id:entry.item_id,item_count:itemCount})
        }
        const single = Object.entries(totals).map(([id,count])=>{
            const actualIncrease = (s.expectedAfter.items[id]??0)-(s.before.items[id]??0)
            equal(actualIncrease,count,'mail EX actual compensation increase for '+id)
            return {id:Number(id),count}
        }).sort((a,b)=>a.id-b.id)
        for (const [id,count] of Object.entries(copies))
            equal(s.expectedAfter.characters[id].stack-s.before.characters[id].stack,count,'mail EX duplicate character stacks for '+id)
        return {single,batch}
    }
    function annotate(s, expected, bulk, snapshotStepId=s.id) {
        s.requestSnapshotStepId = snapshotStepId
        if (bulk) s.expectedBatchExItems = clone(expected.batch)
        else s.expectedSingleExItems = clone(expected.single)
    }
    function assertNoNewGrant(s) {
        for (const table of ['players_characters','players_items','players_equipment','players_mails','players_receive_history'])
            equal(states(s).after[table],states(s).before[table],'mail EX acknowledgement does not repeat grants: '+table)
        equal(s.expectedAfter,s.before,'mail EX acknowledgement preserves authoritative economic state')
    }
    const single = prepare('mail-ex-single-duplicate', [{characterId:111015,number:1},{characterId:111015,number:3}])
    for (const [index,entry] of single.inputs.entries()) {
        const label=index===0?'zero':'positive'
        const claimed = await step(single.c,single.p,'mail-ex-single-'+label,'mail/receive',{mail_id:entry.mail_id})
        const expected = expectedGrant(claimed,[entry]); annotate(claimed,expected,false)
        const replay = await step(single.c,single.p,'mail-ex-single-'+label+'-retry','mail/receive',{}, {payload:{...claimed.request.body,retry_count:1}})
        annotate(replay,expected,false,claimed.id)
        equal(replay.response.data,claimed.response.data,'mail EX same native request full single replay')
        equal(states(replay).after,states(claimed).after,'mail EX same native request single grant once')
        assertNoNewGrant(replay)
    }
    const acknowledged = await step(single.c,single.p,'mail-ex-single-new-identity','mail/receive',{mail_id:single.inputs[1].mail_id})
    annotate(acknowledged,{single:[],batch:[]},false); assertNoNewGrant(acknowledged)
    savePartial()
    for (const [label,attachments] of [
        ['same-character',[{characterId:111015,number:2},{characterId:111015,number:3}]],
        ['mixed-characters',[{characterId:111015,number:2},{characterId:121001,number:3}]],
    ]) {
        const batch = prepare('mail-ex-batch-'+label,attachments), ids=batch.inputs.map(row=>row.mail_id)
        const claimed = await step(batch.c,batch.p,'mail-ex-batch-'+label+'-claim','mail/receive_all',{mail_ids:ids})
        const expected=expectedGrant(claimed,batch.inputs); annotate(claimed,expected,true)
        const replay=await step(batch.c,batch.p,'mail-ex-batch-'+label+'-retry','mail/receive_all',{}, {payload:{...claimed.request.body,retry_count:1}})
        annotate(replay,expected,true,claimed.id)
        equal(replay.response.data,claimed.response.data,'mail EX same native request full batch replay')
        equal(states(replay).after,states(claimed).after,'mail EX same native request batch grant once')
        assertNoNewGrant(replay)
        const acknowledged=await step(batch.c,batch.p,'mail-ex-batch-'+label+'-new-identity','mail/receive_all',{mail_ids:ids})
        annotate(acknowledged,{single:[],batch:[]},true); assertNoNewGrant(acknowledged)
        savePartial()
    }
}
async function main() {
    const initialStatus = execFileSync('git', ['status', '--porcelain', '-uall'], { cwd: repo, encoding: 'utf8' })
    const dirtyPaths = initialStatus.trimEnd().split(/\r?\n/).filter(Boolean).map(line => line.slice(3))
    const sourcePaths = ['src/data/db.ts','src/lib/gameplay-request-identity.ts','src/lib/gameplay-mutation-receipt.ts',
        'src/lib/cn-response-hook.ts','src/lib/cn-response-encoding.ts','src/data/domains/player-operation-receipt.ts',
        ...groups.flatMap(group => ({tutorial:['src/routes/api/tutorial.ts','src/lib/start-tutorial-state.ts'],
            mail:['src/routes/api/mail.ts','src/data/domains/mail.ts','src/lib/character.ts','assets/character.json'],
            equipment:['src/routes/api/equipment.ts','src/routes/api/sell.ts','src/lib/equipment-rarity.ts','src/lib/equipment-dissolve.ts'],
            crazy:['src/routes/api/gacha.ts','src/lib/crazy-gacha.ts','src/data/domains/crazy_gacha.ts','src/lib/gacha.ts','src/lib/character.ts','src/data/codeMap.ts','src/routes/cn/load.ts','src/data/utils/client-player-snapshot.ts','src/lib/start-tutorial-state.ts'],
            ex:['src/routes/api/exBoost.ts','src/routes/cn/load.ts','src/lib/ex-boost-recovery.ts','src/data/domains/ex-boost-pending.ts','src/data/utils/client-player-snapshot.ts']})[group]),
        ...dirtyPaths.filter(file => /^(src|assets)\//.test(file) && Boolean(require.cache[path.join(repo,file)]))]
    const relevantPaths = [...new Set(sourcePaths)].sort()
    const changedFileManifest = () => relevantPaths.map(file => ({ path: file, dirty:dirtyPaths.includes(file), sha256: hash(fs.readFileSync(path.join(repo,file))) }))
    const initialFiles = changedFileManifest()
    output.source.head = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repo, encoding: 'utf8' }).trim()
    output.source.relatedFiles = initialFiles; output.source.dirtyStatus = initialStatus.trimEnd().split(/\r?\n/).filter(Boolean)
    await start()
    let tutorialPlayer
    if (selected('tutorial')) {
    tutorialPlayer = fixture()
    players.updatePlayerSync({ id: tutorialPlayer.id, tutorialStep: 15, tutorialSkipFlag: false })
    const tutorial = begin('tutorial-present', 'tutorial', tutorialPlayer, 'Present step 15: real character 243001 plus one 999012 ticket; same native identity replay.')
    const present = await step(tutorial, tutorialPlayer, 'tutorial-present-claim', 'tutorial/update_step', { step: 15, skip: false, statistics: {} })
    equal(present.response.data.item_list['999012'], 1, 'tutorial grants exact ticket')
    check(Boolean(chars.getPlayerCharacterSync(tutorialPlayer.id, 243001)), 'tutorial grants exact character')
    equal(players.getPlayerSync(tutorialPlayer.id).freeVmoney, 1234, 'tutorial no former currency reward')
    const presentRetry = await step(tutorial, tutorialPlayer, 'tutorial-present-retry', 'tutorial/update_step', {}, { payload: { ...present.request.body, retry_count: 1 } })
    equal(presentRetry.response.data, present.response.data, 'tutorial complete data replay')
    equal(states(presentRetry).after, states(present).after, 'tutorial retry does not grant twice')
    savePartial(); console.log('READY tutorial')
    }
    if (selected('mail')) {
    const mp = fixture(), singleId = mail(mp, mails.MailType.ITEM, 101, 2)
    const single = begin('mail-single', 'mail', mp, 'Single mail with native retry; item 101 initial 7, after 9.')
    const singleClaim = await step(single, mp, 'mail-single-claim', 'mail/receive', { mail_id: singleId })
    const singleRetry = await step(single, mp, 'mail-single-retry', 'mail/receive', {}, { payload: { ...singleClaim.request.body, retry_count: 1 } })
    equal(singleRetry.response.data, singleClaim.response.data, 'mail single complete data replay')
    equal(states(singleRetry).after, states(singleClaim).after, 'mail single no repeat grant')
    equal(items.getPlayerItemSync(mp.id, 101), 9, 'mail single adds quantity once')
    const batchIds = [mail(mp, mails.MailType.CHARACTER, 111015, 3), mail(mp, mails.MailType.FREE_VMONEY, null, 77), mail(mp, mails.MailType.EQUIPMENT, 5010005, 2)]
    const batch = begin('mail-batch-duplicate-character', 'mail', mp, 'Batch: one new character + two duplicate stacks and compensation, currency, equipment; native retry.')
    const batchClaim = await step(batch, mp, 'mail-batch-claim', 'mail/receive_all', { mail_ids: batchIds })
    const batchRetry = await step(batch, mp, 'mail-batch-retry', 'mail/receive_all', {}, { payload: { ...batchClaim.request.body, retry_count: 1 } })
    equal(batchRetry.response.data, batchClaim.response.data, 'mail batch complete data replay')
    equal(states(batchRetry).after, states(batchClaim).after, 'mail batch no repeat grant')
    equal(chars.getPlayerCharacterSync(mp.id, 111015).stack, 2, 'mail quantity grants two duplicate stacks')
    const compensationId = load('lib/character').getCharacterDuplicateRewardItemId(111015)
    equal(items.getPlayerItemSync(mp.id, compensationId), 2 * expectedDuplicateItemCount(111015), 'mail duplicate compensation exact quantity')
    // This case explicitly models an already-consumed old save; the real mail route supplies current state.
    const staleClient = projection(mp)
    chars.updatePlayerCharacterSync(mp.id, 111015, { stack: 0 })
    db.prepare('DELETE FROM players_items WHERE player_id=? AND id=?').run(mp.id, compensationId)
    players.updatePlayerSync({ id: mp.id, freeVmoney: 99 })
    const acknowledged = begin('mail-already-claimed-current-state', 'mail', mp,
        'Synthetic old-save setup: duplicate stack spent to 0, compensation inventory row absent, currency 99. before is stale client state; diagnostics.before reflects authoritative current state. No grant is fabricated.')
    acknowledged.before = staleClient
    const ack = await step(acknowledged, mp, 'mail-current-state-ack', 'mail/receive_all', { mail_ids: batchIds })
    ack.before = staleClient
    equal(ack.response.data.item_list[String(compensationId)], 0, 'mail absent compensation row sends explicit zero')
    equal(ack.response.data.user_info.free_vmoney, 99, 'mail new identity reports current currency')
    equal(chars.getPlayerCharacterSync(mp.id, 111015).stack, 0, 'mail new identity does not regrant duplicate')
    const crossMail = await step(acknowledged, mp, 'mail-current-state-restart', 'mail/receive_all', {}, { payload: ack.request.body, newProcess: true })
    equal(crossMail.response.data, ack.response.data, 'mail new process exact data replay')
    equal(states(crossMail).after, states(ack).after, 'mail cross process no grant')
    await generateMailExFixtures()
    savePartial(); console.log('READY mail')
    }
    if (selected('equipment')) {
    for (const id of [100013, 100023]) {
        const p = fixture(); equipment.insertPlayerEquipmentSync(p.id, id, { level: 1, enhancementLevel: 0, stack: 4, protection: false }); items.setPlayerItemSync(p.id, 100000, 25)
        const c = begin('equipment-' + id, 'equipment', p, 'True five-star fantasy equipment: upgrade costs 25; each dismantled duplicate returns 5; base record retained.')
        const upgrade = await step(c, p, id+'-upgrade', 'equipment/upgrade', { equipment_id: id, use_stack: true, upgrade_count: 1 })
        equal(items.getPlayerItemSync(p.id,100000), 0, 'fantasy upgrade consumes 25')
        equal(equipment.getPlayerEquipmentSync(p.id,id).level, 2, 'fantasy upgrade advances one')
        const retry = await step(c,p,id+'-upgrade-retry','equipment/upgrade',{}, {payload:upgrade.request.body})
        equal(retry.response.data,upgrade.response.data,'equipment full data replay'); equal(states(retry).after,states(upgrade).after,'equipment retry state')
        await step(c,p,id+'-sell-equipment','equipment/sell_equipment',{equipment_list:[{equipment_id:id}]})
        equal(items.getPlayerItemSync(p.id,100000),5,'sell equipment one duplicate returns 5')
        await step(c,p,id+'-sell-stack','equipment/sell_stack',{equipment_list:[{equipment_id:id,number:1}]})
        equal(items.getPlayerItemSync(p.id,100000),10,'sell stack one returns 5')
        await step(c,p,id+'-bulk-sell-stack','equipment/bulk_sell_stack',{equipment_ids:[id]})
        equal(items.getPlayerItemSync(p.id,100000),15,'bulk last stack returns 5'); equal(equipment.getPlayerEquipmentSync(p.id,id).stack,0,'base equipment retained at zero stack')
    }
    savePartial(); console.log('READY equipment fixtures')
    }
    if (selected('crazy')) {
    const operationStore = load('lib/content-operations').contentOperations(), review = { readiness: 'verified', evidence: 'Synthetic current native route response fixtures', endsAtMs: null, enabled: true }
    operationStore.update('gacha:100', { expectedRevision: operationStore.revision(), catalogDigest: operationStore.digest, reason: 'Isolated client runtime fixture',
        actionOverrides: { visible: review, enter: review, claim: review } }, Date.now())
    const cp = tutorialPlayer ?? fixture()
    if (!tutorialPlayer) items.setPlayerItemSync(cp.id,999012,1)
    players.updatePlayerSync({id:cp.id,tutorialStep:17,tutorialSkipFlag:false})
    const c = begin('crazy-gacha-100', 'crazy', cp, (tutorialPlayer ? 'Uses actual tutorial ticket.' : 'Standalone group: one synthetic initial ticket.') + ' Normal completed-tutorial profile; exec -> save slot 1 -> select slot 1, each followed by same-identity retry and independent source-process load; selected ten awarded only at selection.')
    c.profile = 'normal'; c.expectedRestoreState = 'None'
    c.setup = { tutorialStep:17, tutorialSkipFlag:false, source:'players.updatePlayerSync before case' }
    async function recoverCrazy(phase, expectedLast, expectedSlots) {
        const recovered = await step(c,cp,'crazy-load-'+phase,'load',{}, {newProcess:true,recoveryPhase:phase})
        equal(recovered.response.data.crazy_gacha_result_list,expectedSlots,'crazy '+phase+' fresh process restores exact slots')
        equal(recovered.response.data.last_crazy_gacha_draw_result,expectedLast,'crazy '+phase+' fresh process restores every last-draw field')
        equal(recovered.expectedLastCrazyGachaDrawResult,expectedLast,'crazy '+phase+' persisted last draw matches response')
        equal(recovered.expectedAfter.crazyGachaResultList,expectedSlots,'crazy '+phase+' persisted slots match response')
        equal(items.getPlayerItemSync(cp.id,999012),0,'crazy '+phase+' exhausted ticket is not restored or consumed again')
        equal(recovered.response.data.item_list['999012'] ?? 0,0,'crazy '+phase+' load carries exhausted ticket state')
        const storedCharacters = chars.getPlayerCharactersSync(cp.id)
        equal(Object.entries(recovered.response.data.user_character_list).map(([id,row])=>[Number(id),row.stack]).sort((a,b)=>a[0]-b[0]),
            Object.entries(storedCharacters).map(([id,row])=>[load('data/codeMap').kIdToBusinessCode(Number(id)),row.stack]).sort((a,b)=>a[0]-b[0]),'crazy '+phase+' load carries all owned character stacks')
        for (const table of ['players_characters','players_items','players_equipment','players_crazy_gacha','receipts'])
            equal(states(recovered).after[table],states(recovered).before[table],'crazy '+phase+' load does not alter reward or draw state: '+table)
        return recovered
    }
    const draw = await step(c,cp,'crazy-exec','gacha/exec',{gacha_id:100,payment_type:3,type:14,number_of_exec:1})
    equal(draw.response.data.draw.length,10,'crazy ten candidates'); equal(draw.response.data.character_list.length,0,'crazy no premature grant'); equal(items.getPlayerItemSync(cp.id,999012),0,'crazy consumes tutorial ticket')
    const drawAgain = await step(c,cp,'crazy-exec-retry','gacha/exec',{}, {payload: {...draw.request.body,retry_count:1}})
    equal(drawAgain.response.data.draw,draw.response.data.draw,'crazy exec retry keeps original ten movies and characters')
    equal(drawAgain.response.data.crazy_gacha_result_list,draw.response.data.crazy_gacha_result_list,'crazy exec retry keeps candidate slots')
    equal(states(drawAgain).after,states(draw).after,'crazy exec retry does not consume last ticket again or reroll')
    const candidateIds = draw.response.data.draw.map(row=>row.character_id)
    equal(draw.response.data.crazy_gacha_result_list,{'0':candidateIds,'1':[],'2':[]},'crazy first draw occupies only current slot')
    await recoverCrazy('after-exec',draw.response.data.draw,{'0':candidateIds,'1':[],'2':[]})
    const saved = await step(c,cp,'crazy-save','gacha/crazy_gacha_save',{index:1})
    const saveAgain = await step(c,cp,'crazy-save-retry','gacha/crazy_gacha_save',{}, {payload: {...saved.request.body,retry_count:1}})
    equal(saveAgain.response.data,saved.response.data,'crazy same identity save replay data')
    equal(states(saveAgain).after,states(saved).after,'crazy save retry does not duplicate immutable slot')
    await recoverCrazy('after-save',draw.response.data.draw,{'0':candidateIds,'1':candidateIds,'2':[]})
    equal(projection(cp).characters,c.before.characters,'crazy saved candidates remain ungranted after restart')
    const choice = await step(c,cp,'crazy-select','gacha/crazy_gacha_select',{gacha_id:100,index:1})
    equal(choice.response.data.crazy_gacha_result_list,{'0':[],'1':[],'2':[]},'crazy clears candidates after selection')
    equal(crazy.getLatestCrazyGachaStateSync(cp.id).state.status,'finalized','crazy persists finalization')
    const again = await step(c,cp,'crazy-select-retry','gacha/crazy_gacha_select',{}, {payload:choice.request.body})
    equal(again.response.data.crazy_gacha_result_list,choice.response.data.crazy_gacha_result_list,'crazy retry remains finalized')
    equal(states(again).after,states(choice).after,'crazy selected rewards once')
    const finalRecovery = await recoverCrazy('after-select',[],{'0':[],'1':[],'2':[]})
    const counts = {}; for (const id of candidateIds) counts[id]=(counts[id]??0)+1
    const expectedCompensation = {}
    for (const [id,count] of Object.entries(counts)) {
        const previous = c.before.characters[id]
        equal(finalRecovery.expectedAfter.characters[id].stack,(previous ? previous.stack : -1)+count,'crazy selected candidate count granted exactly once for '+id)
        const duplicates = count - (previous ? 0 : 1)
        if (duplicates > 0) {
            const itemId = load('lib/character').getCharacterDuplicateRewardItemId(Number(id))
            check(Number.isSafeInteger(itemId) && itemId >= 14001 && itemId <= 14018,'crazy duplicate uses a recognized compensation item')
            expectedCompensation[itemId] = (expectedCompensation[itemId] ?? 0) + duplicates * expectedDuplicateItemCount(Number(id))
        }
    }
    for (const [itemId,count] of Object.entries(expectedCompensation))
        equal((finalRecovery.expectedAfter.items[itemId] ?? 0) - (c.before.items[itemId] ?? 0),count,'crazy selected duplicate compensation follows verified rarity rule for '+itemId)
    c.notes += ' Dedicated completed-select returns current-state data, not byte-identical first response; both real responses are preserved.'
    savePartial(); console.log('READY crazy fixtures')
    }
    if (selected('ex')) for (const profile of ['tutorial','normal']) for (const confirm of [true,false]) {
        const p=fixture(); grantExEligible(p)
        if (profile === 'normal') players.updatePlayerSync({id:p.id,tutorialStep:17,tutorialSkipFlag:false})
        const action=confirm?'confirm':'discard', label=(profile==='normal'?'normal-':'')+action
        const c=begin('ex-'+(profile==='normal'?'normal-':'')+'last-material-'+action,'ex',p,'Profile '+profile+': real first_draw then last-material draw, login/load and fresh-process recovery, '+action+', same-identity and restart replay.')
        c.profile=profile; c.expectedRestoreState=profile==='normal'?'None':'Tutorial'
        const base=await step(c,p,'ex-'+label+'-first','exBoost/first_draw',{character_id:111015,cost_item_id:10001})
        const d=await step(c,p,'ex-'+label+'-draw','exBoost/draw',{character_id:111015,cost_item_id:10001})
        equal(items.getPlayerItemSync(p.id,10001),0,'EX last material consumed')
        const paid=clone(pending.getPendingExBoostDrawSync(p.id))
        check(Boolean(paid),'EX candidate persisted')
        const duplicate=await step(c,p,'ex-'+label+'-draw-retry','exBoost/draw',{}, {payload:d.request.body})
        equal(duplicate.response.data,d.response.data,'EX draw exactdata retry')
        login(p)
        const recovered=await step(c,p,'ex-'+label+'-load','load')
        equal(recovered.response.data.ex_boost_draw_result,{character_id:paid.characterId,draw_result:{status_id:paid.statusId,ability_id_list:paid.abilityIdList}},'load exact paid candidate')
        const fresh=await step(c,p,'ex-'+label+'-load-restart','load',{}, {newProcess:true})
        equal(fresh.response.data.ex_boost_draw_result,recovered.response.data.ex_boost_draw_result,'fresh process candidate unchanged')
        const s=await step(c,p,'ex-'+label+'-select','exBoost/select',{is_confirm:confirm})
        equal(pending.getPendingExBoostDrawSync(p.id),null,'EX choice clears pending')
        equal(chars.getPlayerCharacterSync(p.id,111015).exBoost,confirm?{statusId:paid.statusId,abilityIdList:paid.abilityIdList}:{statusId:base.response.data.character_list[0].ex_boost.status_id,abilityIdList:base.response.data.character_list[0].ex_boost.ability_id_list},'EX choice applies intended base or new candidate')
        const again=await step(c,p,'ex-'+label+'-select-retry','exBoost/select',{}, {payload:s.request.body})
        equal(exSelectBusiness(again.response.data),exSelectBusiness(s.response.data),'EX select business state replay')
        const restart=await step(c,p,'ex-'+label+'-select-restart','exBoost/select',{}, {payload:s.request.body,newProcess:true})
        equal(exSelectBusiness(restart.response.data),exSelectBusiness(s.response.data),'EX select business state survives fresh process')
        c.notes += ' Dedicated select retry acknowledges current character state; update_time is generated fresh and is not exact-data replay. Raw responses remain unchanged.'
        equal(states(restart).after,states(s).after,'EX repeat selections do not grant or consume')
        const cleared=await step(c,p,'ex-'+label+'-load-cleared','load')
        equal(cleared.response.data.ex_boost_draw_result,null,'later load no pending')
        equal(items.getPlayerItemSync(p.id,10001),0,'EX recovery no extra cost')
    }
    equal(execFileSync('git',['status','--porcelain','-uall'],{cwd:repo,encoding:'utf8'}),initialStatus,'business worktree status unchanged')
    equal(changedFileManifest(), initialFiles, 'business related source bytes unchanged')
    output.assertions=checks; output.completed=true
    savePartial()
    fs.writeFileSync(path.join(root,'execution-result.json'),JSON.stringify({success:true,assertions:checks,cases:output.cases.length,steps:output.cases.reduce((n,c)=>n+c.steps.length,0),sourceMode:output.source.mode,outUsed:false,runDir,command:{node:process.execPath,args:process.argv.slice(1)},fixturesSha256:hash(fs.readFileSync(path.join(root,'fixtures.json')))},null,2)+'\n')
    console.log('COMPLETE '+JSON.stringify({assertions:checks,cases:output.cases.length,steps:output.cases.reduce((n,c)=>n+c.steps.length,0)}))
}
;(async()=>{
    try {
        if(child){await start();const input=JSON.parse(fs.readFileSync(args['--child'],'utf8'));fs.writeFileSync(input.target,JSON.stringify(await invoke(input.p,input.route,input.payload)))}
        else await main()
    } catch(error){console.error(error.stack);if(!child){output.completed=false;output.failure=error.stack;output.assertions=checks;savePartial();fs.writeFileSync(path.join(root,'execution-result.json'),JSON.stringify({success:false,assertions:checks,failure:error.stack,command:{node:process.execPath,args:process.argv.slice(1)}},null,2)+'\n')}process.exitCode=1}
    finally{await close()}
})()
