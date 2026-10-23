'use strict'

// All fixtures are synthesized. The same module registers commands inside the
// actual production writer worker; worker imports must never run node:test.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const { isMainThread, threadId } = require('node:worker_threads')
const sourceRoot = path.resolve(process.env.SERVER_CLOCK_TEST_SOURCE || path.resolve(__dirname, '..'))
const taskRoot = path.resolve(process.env.SERVER_CLOCK_TEST_ROOT || path.join(require('node:os').tmpdir(), 'starpoint-clock-integration'))
const out = path.resolve(process.env.STARPOINT_TEST_OUT_DIR || path.join(sourceRoot, 'out'))
const load = name => require(path.join(out, name))
const legacyOffset = -920 * 86400000 - 12345
const quote = value => '"' + value.replaceAll('"', '""') + '"'
function state(db) {
    return Object.fromEntries(db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name").all()
        .map(({name}) => [name, db.prepare(`SELECT * FROM ${quote(name)}`).all().sort((a,b)=>JSON.stringify(a).localeCompare(JSON.stringify(b)))]))
}
function probe() {
    const clock = load('utils')
    const battle = load('lib/battle-clock-compatibility')
    return { thread: isMainThread ? 'main' : 'worker', threadId, snapshot: clock.getServerClockSnapshot(),
        now: clock.getServerDate().getTime(), real: clock.getRealServerDate().getTime(), offset: clock.getTimeOffset(),
        legacy: clock.getLegacyTimeOffset(), oldBattle: battle.getBattleClockDate(0).getTime(),
        newBattle: battle.getBattleClockDate(1).getTime(), transaction: load('data/db').getDb().inTransaction }
}
function registerCommands() {
    const { registerWriterCommand } = load('lib/persistence/command-registry')
    registerWriterCommand('clock.integration.probe', probe)
    registerWriterCommand('clock.integration.slow', args => {
        fs.writeFileSync(args.signal, 'entered')
        const until = Date.now() + args.ms
        while (Date.now() < until) { /* hold the genuine worker transaction */ }
        return probe()
    })
    registerWriterCommand('clock.integration.fail', args => {
        load('data/db').getDb().prepare('UPDATE players SET free_mana=free_mana+1000 WHERE id=?').run(args.playerId)
        throw new Error('clock integration deliberate transaction fault')
    })
}
if (!isMainThread) registerCommands()
else if (process.argv[2] === '--child') {
    runScenario(process.argv[3]).then(result => { console.log('CLOCK_RESULT ' + JSON.stringify(result)); process.exit(0) }, error => {
        console.error(error); process.exit(1)
    })
} else {
    const test = require('node:test')
    for (const scenario of ['startup', 'loads', 'writer']) test(`isolated server clock integration: ${scenario}`, {timeout:90000}, () => {
        fs.mkdirSync(taskRoot, {recursive:true})
        const directory = fs.mkdtempSync(path.join(taskRoot, `clock-${scenario}-`))
        const child = childProcess(scenario, directory)
        assert.equal(child.status, 0, child.stdout + child.stderr)
        const result = child.stdout.split(/\r?\n/).find(line => line.startsWith('CLOCK_RESULT '))
        assert.ok(result, child.stdout + child.stderr)
        console.log(result)
    })
}
function childProcess(scenario, directory, extra = {}) {
    return spawnSync(process.execPath, ['--preserve-symlinks', '--preserve-symlinks-main', __filename, '--child', scenario], {
        cwd:sourceRoot, windowsHide:true, timeout:80000, encoding:'utf8', maxBuffer:2000000,
        env:{...process.env, DATA_DIR:directory, TMP:directory, TEMP:directory,
            GACHA_SEED_DIR:path.join(directory, 'seeds'), SERVER_CLOCK_TEST_SOURCE:sourceRoot,
            SERVER_CLOCK_TEST_ROOT:taskRoot, STARPOINT_TEST_OUT_DIR:out,
            CN_WRITER_THREAD:'0', SQLITE_WRITER_EXTRA_COMMANDS:__filename, GAME_ROUTINE_LOGS:'off', ...extra},
    })
}
function assertProbe(value, expected) {
    assert.equal(value.transaction, true)
    assert.deepEqual(value.snapshot, expected)
    assert.equal(value.legacy, expected.legacyBattleOffsetMs)
    assert.equal(value.now-value.real, expected.businessOffsetMs ?? 0)
    assert.equal(value.oldBattle-value.real, expected.legacyBattleOffsetMs ?? 0)
    assert.equal(value.newBattle, value.real)
    assert.equal(value.offset, expected.businessOffsetMs ?? 0)
}
async function waitFor(predicate) {
    const deadline = Date.now() + 10000
    while (!predicate()) {
        assert.ok(Date.now()<deadline, 'fixture condition did not become ready')
        await new Promise(resolve=>setTimeout(resolve,5))
    }
}
function seed(db, clock) {
    const players = load('data/domains/player'), accounts = load('data/domains/account')
    const realMs = Date.now(), oldMs = realMs + legacyOffset, fixture = []
    clock.setServerTimeOffset(legacyOffset)
    clock.withServerClock(oldMs, () => {
        for(let index=0;index<4;index++) {
            const account=accounts.insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'clock-offline',idpId:`fixture-${index}`,status:'normal'})
            const player=players.insertDefaultPlayerSync(account.id)
            load('data/activeAccount').saveAccountDefaultPlayer(account.id,player.id)
            const viewerId=86000000+player.id, zat=`offline-zat-${player.id}`
            db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewerId),account.id,'2099-01-01T00:00:00Z')
            db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,0)').run(zat,account.id,'2099-01-01T00:00:00Z')
            players.updatePlayerSync({id:player.id,expPool:1234+index,timeOffset:index===1?null:legacyOffset,
                expPooledTime:new Date(oldMs-5000),lastLoginTime:new Date(oldMs),boostPoint:1,bossBoostPoint:2,totalLoginDays:27})
            for(const category of [2,7,10]) {
                db.prepare('INSERT OR REPLACE INTO players_category_missions(category,id,progress,player_id) VALUES(?,?,17,?)').run(category,990000+category,player.id)
                db.prepare('INSERT OR REPLACE INTO players_category_mission_stages(category,id,status,player_id,mission_id) VALUES(?,1,1,?,?)').run(category,player.id,990000+category)
            }
            db.prepare('UPDATE players_periodic_snapshots SET quest_clears=12,stamina_used=77,login_days=26 WHERE player_id=?').run(player.id)
            load('data/domains/item').givePlayerItemSync(player.id,14040,19)
            load('data/domains/quest').insertPlayerQuestProgressSync(player.id,2,{questId:1001001,finished:true,bestElapsedTimeMs:45678,highScore:123,clearRank:5,leaderCharacterId:1})
            load('data/domains/quest_active').insertPlayerActiveQuestSync(player.id,{playerId:player.id,playId:`old-clock-${index}`,
                questId:1001001,category:2,isMulti:false,isMultiHost:false,roomNumber:null,useBoostPoint:false,useBossBoostPoint:false,
                isAutoStartMode:false,continueCount:0,startedAtMs:index===3?null:oldMs-60000,partySlot:1})
            db.prepare('UPDATE players_active_quests SET clock_version=0 WHERE player_id=?').run(player.id)
            fixture.push({id:player.id,accountId:account.id,viewerId,zat})
        }
    },legacyOffset)
    db.exec(`CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY REFERENCES players(id),version INTEGER NOT NULL,
        cutover_real_ms INTEGER NOT NULL,day_anchor_ms INTEGER NOT NULL,week_anchor_ms INTEGER NOT NULL)`)
    for(const p of fixture.slice(2)) {
        db.prepare('INSERT INTO player_time_state VALUES(?,1,?,?,?)').run(p.id,realMs-60000,realMs,realMs)
        players.updatePlayerSync({id:p.id,timeOffset:0,expPooledTime:new Date(realMs-5000),lastLoginTime:new Date(realMs-5000)})
    }
    const markers=db.prepare('SELECT * FROM player_time_state ORDER BY player_id').all()
    return {fixture,realMs,markers,oldMs}
}
function activate(db, realMs, extra = {}) {
    const offlineGuard={kind:'approved-offline-file',databasePath:fs.realpathSync(db.name),allowedRoot:taskRoot}
    const options={cutoverRealMs:realMs,legacyOffsetMs:legacyOffset,offlineGuard}
    const plan=load('lib/time-cutover-rehearsal').planTimeCutoverRehearsalSync(db,options)
    load('lib/server-clock-state').activateRealServerClockOfflineSync(db,{...options,expectedPlanDigest:plan.digest,readiness:'scenario-only',...extra})
    return plan
}
async function runScenario(scenario) {
    const clock=load('utils'), clockState=load('lib/server-clock-state')
    if(scenario==='restore'||scenario==='invalid') {
        const db=new(require('better-sqlite3'))(process.env.CLOCK_DATABASE)
        const before=state(db)
        if(scenario==='invalid') {
            assert.throws(()=>load('data/activeAccount').restoreTimeOffset(db),/clock|real/i)
            assert.deepEqual(state(db),before,'invalid persisted state must fail without fallback mutation')
            assert.equal(clock.getServerClockSnapshot().mode,'legacy')
            db.close();return {scenario,rejected:true}
        }
        load('data/activeAccount').restoreTimeOffset(db)
        assert.deepEqual(state(db),before,'startup restore is read-only')
        const actual=clock.getServerClockSnapshot()
        assert.equal(actual.mode,'real');assert.equal(actual.businessOffsetMs,0);assert.equal(actual.legacyBattleOffsetMs,legacyOffset)
        assert.ok(Math.abs(clock.getServerTime()-Math.floor(Date.now()/1000))<=1)
        db.close();return {scenario,snapshot:actual}
    }
    const db=load('data/db').getDb(), players=load('data/domains/player')
    assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(process.env.DATA_DIR))
    const timers=[], originalInterval=global.setInterval
    try {
        if(scenario==='startup') {
            load('data/activeAccount').restoreTimeOffset(db)
            assert.equal(clock.getServerClockSnapshot().mode,'legacy')
            assert.ok(Math.abs(clock.getServerDate().getTime()-Date.parse('2024-08-14T12:00:00Z'))<1000)
        }
        const fixture=seed(db,clock)
        if(scenario==='startup') {
            const before=state(db)
            for(const faultAt of ['after-player-migration','after-clock-state']) {
                assert.throws(()=>activate(db,fixture.realMs,{faultAt}),/fault|inject/i)
                assert.deepEqual(state(db),before,faultAt)
                assert.equal(clock.getServerClockSnapshot().mode,'legacy')
            }
            const plan=activate(db,fixture.realMs)
            assert.equal(clock.getServerClockSnapshot().mode,'legacy','activation persists only; explicit restore publishes')
            const activated=state(db)
            load('data/activeAccount').restoreTimeOffset(db)
            assert.deepEqual(state(db),activated)
            assert.equal(clock.getServerClockSnapshot().mode,'real')
            assert.equal(clock.getLegacyTimeOffset(),legacyOffset)
            const child=childProcess('restore',process.env.DATA_DIR,{CLOCK_DATABASE:db.name})
            assert.equal(child.status,0,child.stdout+child.stderr)
            assert.deepEqual(state(db),activated)
            activate(db,fixture.realMs,{expectedPlanDigest:plan.digest})
            assert.deepEqual(state(db),activated,'repeat activation is durable no-op')
            for(const setter of [()=>clock.setServerTimeOffset(null),()=>clock.setServerTimeOffset(0),()=>clock.setServerTime(null)]) assert.throws(setter)
            assert.equal(clockState.readServerClockStateSync(db).planDigest,plan.digest)
            const admin = require('fastify')({logger:false})
            try {
                await admin.register(load('routes/web_api/server').default)
                const current = await admin.inject({method:'GET',url:'/currentTime'})
                assert.equal(current.statusCode,200)
                assert.equal(current.json().clockMode,'real')
                assert.equal(current.json().isCustom,false)
                for(const url of ['/resetTime','/time?time=2025-07-20T00:00:00Z']) {
                    const rejected = await admin.inject({method:'GET',url})
                    assert.equal(rejected.statusCode,409)
                    assert.equal(rejected.json().error,'服务器时间不可修改；请使用全员重新登录刷新运营配置。')
                }
                assert.deepEqual(state(db),activated,'legacy admin setters cannot mutate real DB state')
            } finally { await admin.close() }

            const corruptPath=path.join(process.env.DATA_DIR,'corrupt-synthetic.db')
            await db.backup(corruptPath)
            const corrupt=new(require('better-sqlite3'))(corruptPath)
            corrupt.pragma('ignore_check_constraints=ON')
            corrupt.prepare('UPDATE server_clock_state SET business_offset_ms=1').run()
            corrupt.close()
            const invalid=childProcess('invalid',process.env.DATA_DIR,{CLOCK_DATABASE:corruptPath})
            assert.equal(invalid.status,0,invalid.stdout+invalid.stderr)
            assert.deepEqual(state(db),activated,'invalid fixture cannot change the accepted synthetic DB')
            return {scenario,checks:9,players:4,restart:true,invalidPersistentStateRejected:true,legacyOffset,productionCutover:'no_go'}
        }
        if(scenario==='loads') return await loadScenario(db,clock,fixture,timers,originalInterval)
        return await writerScenario(db,clock,fixture)
    } finally { global.setInterval=originalInterval;for(const timer of timers)clearInterval(timer);if(db.open)db.close() }
}

async function loadScenario(db,clock,fixture,timers,originalInterval) {
    activate(db,fixture.realMs)
    load('data/activeAccount').restoreTimeOffset(db)
    // Synthesize missed old rows after the atomic activation so the actual
    // load hook, rather than the offline bulk operation, must migrate them.
    const players=load('data/domains/player')
    for(const [index,p] of fixture.fixture.slice(0,2).entries()) {
        db.prepare('DELETE FROM player_time_state WHERE player_id=?').run(p.id)
        players.updatePlayerSync({id:p.id,timeOffset:index===1?null:legacyOffset,
            expPooledTime:new Date(fixture.oldMs-5000),lastLoginTime:new Date(fixture.oldMs)})
    }
    const protectedNames=['players_category_missions','players_category_mission_stages','players_periodic_snapshots',
        'players_items','players_quest_progress','players_active_quests','players_mails','daily_vmoney_mail_grants','daily_vmoney_mail_runs']
    const before=state(db), mail=load('lib/daily-vmoney-mail'), originalMail=mail.ensureDailyVmoneyMailForPlayerSync
    const seen=[]
    mail.ensureDailyVmoneyMailForPlayerSync=(id,...args)=>{
        assert.equal(db.inTransaction,true)
        const marker=load('lib/player-time-compat').getExistingPlayerTimeStateSync(id,db)
        assert.ok(marker,'actual load hook must migrate before the first mail maintenance call')
        assert.equal(clock.getConfiguredBusinessTimeOffset(),0)
        assert.equal(clock.getTimeOffset(),0)
        const migrated=players.getPlayerSync(id)
        assert.equal(migrated.timeOffset,0)
        if(id===fixture.fixture[0].id) assert.equal(migrated.expPooledTime.getTime(),fixture.realMs-5000)
        if(id===fixture.fixture[1].id) assert.equal(migrated.expPooledTime.getTime(),fixture.realMs)
        seen.push(id)
        return originalMail(id,...args)
    }
    const apps=[]
    try {
        global.setInterval=(...args)=>{const timer=originalInterval(...args);timers.push(timer);return timer}
        const cn=load('routes/cn/load').default, legacy=load('routes/api').default
        global.setInterval=originalInterval
        for(const [route,prefix] of [[cn,'/cn'],[legacy,'/legacy']]) {
            const app=require('fastify')({logger:false})
            app.addHook('onSend',(_req,reply,payload,done)=>reply.getHeader('content-type')==='application/x-msgpack'
                ?done(null,require('msgpackr').pack(payload).toString('base64')):done(null,payload))
            await app.register(route,{prefix});await app.ready();apps.push(app)
        }
        for(let repeat=0;repeat<2;repeat++) for(let index=0;index<fixture.fixture.length;index++) {
            const p=fixture.fixture[index],cn=index%2===0,app=apps[cn?0:1]
            const response=await app.inject({method:'POST',url:cn?'/cn/load':'/legacy/load',
                payload:{viewer_id:p.viewerId,...(!cn?{access_token:p.zat}:{})},headers:{device:'android'}})
            assert.equal(response.statusCode,200,response.body)
            const decoded=require('msgpackr').unpack(Buffer.from(response.body,'base64'))
            assert.ok(Math.abs(decoded.data_headers.servertime-Math.floor(Date.now()/1000))<=2)
            const current=players.getPlayerSync(p.id)
            assert.equal(current.expPool,1234+index)
            assert.equal(current.boostPoint,1);assert.equal(current.bossBoostPoint,2);assert.equal(current.totalLoginDays,27)
        }
        assert.equal(seen.length,8)
        const after=state(db)
        for(const name of protectedNames)assert.deepEqual(after[name],before[name],`load preservation: ${name}`)
        assert.deepEqual(db.prepare('SELECT * FROM player_time_state WHERE player_id IN (?,?) ORDER BY player_id').all(...fixture.fixture.slice(2).map(p=>p.id)),fixture.markers)
        assert.equal(db.pragma('quick_check',{simple:true}),'ok');assert.deepEqual(db.pragma('foreign_key_check'),[])
        return {scenario:'loads',players:4,cnLoads:4,legacyLoads:4,maintenanceOrder:true,protectedTables:protectedNames.length,
            existingMarkersPreserved:2,quickCheck:'ok',productionCutover:'no_go'}
    } finally {mail.ensureDailyVmoneyMailForPlayerSync=originalMail;for(const app of apps)await app.close()}
}
async function writerScenario(db,clock,fixture) {
    registerCommands()
    const writer=load('lib/persistence/writer-client'), persistence=load('lib/persistence-coordinator')
    const run=(name,args={},playerId)=>persistence.runWriterCommand(name,args,{domain:'player',playerId,operation:name})
    process.env.CN_WRITER_THREAD='1'
    process.env.SQLITE_WRITER_MAX_IN_FLIGHT='1'
    process.env.SQLITE_GROUP_COMMIT_WINDOW_MS='5'
    process.env.SQLITE_WRITER_COMMAND_TIMEOUT_MS='0'
    process.env.SQLITE_WRITER_BUSY_TIMEOUT_MS='0'
    assert.equal(writer.startSqliteWriter(db.name),true)
    assert.equal(await writer.waitForSqliteWriterReady(30000),true)
    try {
        let expected=clock.getServerClockSnapshot()
        const initial=await run('clock.integration.probe');assertProbe(initial,expected);assert.equal(initial.thread,'worker')
        // Main player queue delays dispatch. Its caller's ALS clock must not
        // determine a later transaction's captured time or offset.
        let release,entered
        const gate=new Promise(resolve=>{release=resolve}),ready=new Promise(resolve=>{entered=resolve})
        const blocker=load('lib/sqlite-write-coordinator').withPlayerWriteQueue(fixture.fixture[0].id,async()=>{entered();await gate})
        await ready
        const queued=clock.withServerClock(Date.now()+legacyOffset,()=>run('clock.integration.probe',{},fixture.fixture[0].id),legacyOffset)
        clock.setServerTimeOffset(legacyOffset+86400000)
        expected=clock.getServerClockSnapshot();release();await blocker
        assertProbe(await queued,expected)
        const signal=path.join(process.env.DATA_DIR,'writer-entered.signal')
        const runningSnapshot=expected,slow=run('clock.integration.slow',{ms:120,signal})
        await waitFor(()=>fs.existsSync(signal))
        clock.setServerTimeOffset(legacyOffset)
        expected=clock.getServerClockSnapshot()
        const afterMessage=run('clock.integration.probe')
        assertProbe(await slow,runningSnapshot)
        assertProbe(await afterMessage,expected)
        await writer.stopSqliteWriter()
        // The real mode is persisted first; a fresh worker gets all fields.
        activate(db,fixture.realMs)
        load('data/activeAccount').restoreTimeOffset(db)
        expected=clock.getServerClockSnapshot()
        process.env.SQLITE_WRITER_MAX_IN_FLIGHT='16'
        process.env.SQLITE_GROUP_COMMIT_WINDOW_MS='20'
        assert.equal(writer.startSqliteWriter(db.name),true)
        assert.equal(await writer.waitForSqliteWriterReady(30000),true)
        const real=await run('clock.integration.probe');assertProbe(real,expected)
        assert.equal(real.now,real.real);assert.equal(real.oldBattle-real.real,legacyOffset)
        const beforeFault=state(db)
        const batch=await Promise.allSettled([
            run('clock.integration.fail',{playerId:fixture.fixture[0].id},fixture.fixture[0].id),
            run('clock.integration.probe',{},fixture.fixture[1].id),
        ])
        assert.equal(batch[0].status,'rejected');assert.match(String(batch[0].reason),/deliberate transaction fault/)
        assert.equal(batch[1].status,'fulfilled');assertProbe(batch[1].value,expected)
        assert.ok(writer.sqliteWriterStats().maxBatchSize>=2,'fault and succeeding command must share a real writer batch')
        assert.deepEqual(state(db),beforeFault)
        assertProbe(await run('clock.integration.probe'),expected)
        const p=fixture.fixture[0],active=load('data/domains/quest_active').getPlayerActiveQuestSync(p.id)
        const questData={...load('lib/assets').getQuestFromCategorySync(2,1001001),rankPointReward:14,characterExpReward:0,
            poolExpReward:26,manaReward:135,clearReward:undefined,sPlusReward:undefined,scoreRewardGroupId:undefined,scoreRewardGroup:undefined}
        const body={play_id:active.playId,quest_id:1001001,category:2,elapsed_time_ms:60000,continue_count:0,score:100,
            add_mana:0,is_accomplished:true,is_restored:false,statistics:{clear_phase:1,max_combo_count:17,
                party:{characters:[{id:1},null,null],unison_characters:[null,null,null],equipments:[null,null,null],ability_soul_ids:[null,null,null]}}}
        const args={playerId:p.id,viewerId:p.viewerId,questCategory:2,questId:1001001,questData,activeQuestData:active,body,
            clearTime:60000,clearRank:5,questAccomplished:true,fiveBossSoloQuest:false,registered:true,scoreAttackBorderTiers:[],
            manaObtained:135,displayMode15ManaAsFieldDrop:false,finishCacheKey:null,receiptPlayId:active.playId}
        const players=load('data/domains/player'),before=players.getPlayerSync(p.id)
        const paid=await run('single.settle_finish',args,p.id);assert.ok(paid.response)
        const after=players.getPlayerSync(p.id)
        assert.equal(after.rankPoint-before.rankPoint,14);assert.equal(after.expPool-before.expPool,26);assert.equal(after.freeMana-before.freeMana,135)
        const once=state(db),retry=await run('single.settle_finish',args,p.id)
        assert.deepEqual(retry.response,paid.response);assert.deepEqual(state(db),once)
        assert.equal(db.prepare("SELECT count(*) n FROM player_operation_receipts WHERE player_id=? AND operation='quest_finish.single'").get(p.id).n,1)
        await writer.stopSqliteWriter();assert.equal(writer.startSqliteWriter(db.name),true)
        assert.equal(await writer.waitForSqliteWriterReady(30000),true)
        assertProbe(await run('clock.integration.probe'),expected)
        assert.deepEqual((await run('single.settle_finish',args,p.id)).response,paid.response)
        assert.deepEqual(state(db),once)
        const stats=writer.sqliteWriterStats()
        assert.ok(stats.savepointRollbacks>=1)
        assert.equal(db.pragma('quick_check',{simple:true}),'ok')
        return {scenario:'writer',thread:'worker',threadId:real.threadId,mainQueueIsolation:true,messageOrder:true,
            capturedTransactionUnchanged:true,realSnapshot:expected,receiptPayments:1,restartReceiptReplay:true,
            savepointRollbacks:stats.savepointRollbacks,quickCheck:'ok',productionCutover:'no_go'}
    } finally {await writer.stopSqliteWriter()}
}
