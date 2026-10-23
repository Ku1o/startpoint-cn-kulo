'use strict'

// Explicitly offline: every database is newly synthesized under the supplied
// task directory. This is not a re-acceptance of any live player's old battles.
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawnSync } = require('node:child_process')
const out = process.env.STARPOINT_TEST_OUT_DIR || path.resolve(__dirname, '../out')
const taskRoot = path.resolve(process.env.TIME_CUTOVER_TEST_ROOT || path.join(require('node:os').tmpdir(), 'starpoint-cutover-preservation'))
fs.mkdirSync(taskRoot, { recursive: true })
const directory = fs.mkdtempSync(path.join(taskRoot, 'preservation-synthetic-'))
process.env.DATA_DIR = directory
process.env.TMP = directory
process.env.TEMP = directory
process.env.GAME_ROUTINE_LOGS = 'off'
delete process.env.CN_WRITER_THREAD
delete process.env.SQLITE_WRITER_EXTRA_COMMANDS
const load = name => require(path.join(out, name))
const clock = load('utils')
const originalOffset = clock.getLegacyTimeOffset()
// Transaction admission intentionally samples the real clock after queueing.
// Anchor this fixture to that real day/week instead of a historical calendar.
const realMs = Date.now()
const legacyMs = Date.parse('2023-11-13T06:30:00.000Z')
const offset = legacyMs - realMs
const atReal = callback => clock.withServerClock(realMs, callback, 0)
let db
const quote = value => '"' + value.replaceAll('"', '""') + '"'
function state(connection, exclude = []) {
    return Object.fromEntries(connection.prepare("SELECT name,sql FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
        .all().filter(row => !exclude.includes(row.name)).map(row => [row.name, {
            schema: row.sql, rows: connection.prepare(`SELECT * FROM ${quote(row.name)}`).all()
                .sort((a, b) => JSON.stringify(a).localeCompare(JSON.stringify(b))),
        }]))
}
const rows = table => db.prepare(`SELECT * FROM ${quote(table)} ORDER BY 1,2`).all()
const guard = () => ({ kind: 'approved-offline-file', databasePath: fs.realpathSync(db.name), allowedRoot: taskRoot })
const options = () => ({ cutoverRealMs: realMs, legacyOffsetMs: offset, offlineGuard: guard() })
const engine = () => load('lib/time-cutover-rehearsal')

test('nonempty offline cutover preserves maintenance, legacy registrations, receipts and V2 progress', async t => {
    t.after(() => { clock.setServerTimeOffset(originalOffset); if (db?.open) db.close() })
    clock.setServerTimeOffset(offset)
    db = load('data/db').getDb()
    assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
    const players = load('data/domains/player')
    const accounts = load('data/domains/account')
    const quests = load('data/domains/quest_active')
    const save = load('data/snapshots/player-snapshot')
    const persistence = load('lib/persistence-coordinator')
    const mail = load('lib/daily-vmoney-mail')
    const fixture = []
    clock.withServerClock(legacyMs, () => {
        for (let index = 0; index < 149; index++) {
            const account = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'synthetic-preservation',
                idpId: `synthetic-${index}`, status: 'normal' })
            const player = index < 4 ? players.insertDefaultPlayerSync(account.id)
                : players.insertPlayerSync(account.id, { ...players.getPlayerSync(fixture[0].id), id: undefined })
            const playerId = typeof player === 'number' ? player : player.id
            fixture.push({ id: playerId, accountId: account.id })
            players.updatePlayerSync({ id: playerId, expPool: 1234 + index, timeOffset: index === 1 ? null : offset,
                expPooledTime: new Date(legacyMs - 30000), lastLoginTime: new Date(legacyMs),
                boostPoint: 1, bossBoostPoint: 2, totalLoginDays: 27, totalStaminaUsed: 91 })
            const mode = index % 4
            quests.insertPlayerActiveQuestSync(playerId, { playerId, playId: `synthetic-old-${index}`,
                questId: mode === 2 ? 1099001001 : 1001001, category: 2, isMulti: mode === 1,
                isMultiHost: mode === 1, roomNumber: mode === 1 ? `room-${index}` : null,
                useBossBoostPoint: false, useBoostPoint: false, isAutoStartMode: false,
                continueCount: mode, startedAtMs: mode === 3 ? null : legacyMs - 60000, partySlot: 1 })
            db.prepare('UPDATE players_active_quests SET clock_version=0 WHERE player_id=?').run(playerId)
        }
    }, offset)
    db.exec(`CREATE TABLE player_time_state(player_id INTEGER PRIMARY KEY REFERENCES players(id),version INTEGER NOT NULL,
        cutover_real_ms INTEGER NOT NULL,day_anchor_ms INTEGER NOT NULL,week_anchor_ms INTEGER NOT NULL);
        CREATE TABLE player_time_migration_ledger(player_id INTEGER PRIMARY KEY REFERENCES players(id),version INTEGER NOT NULL,receipt TEXT NOT NULL)`)
    for (const p of fixture.slice(2, 4)) {
        db.prepare('INSERT INTO player_time_state VALUES(?,1,?,?,?)').run(p.id, realMs - 60000, realMs, realMs)
        db.prepare('INSERT INTO player_time_migration_ledger VALUES(?,1,?)').run(p.id, `existing-${p.id}`)
        players.updatePlayerSync({ id: p.id, expPooledTime: new Date(realMs - 30000), timeOffset: 0,
            lastLoginTime: new Date(realMs - 30000) })
    }
    for (const p of fixture.slice(0, 4)) {
        db.prepare('UPDATE players_periodic_snapshots SET quest_clears=12,stamina_used=77,login_days=26 WHERE player_id=?').run(p.id)
        for (const category of [2, 7, 10]) {
            db.prepare('INSERT OR REPLACE INTO players_category_missions(category,id,progress,player_id) VALUES(?,?,?,?)')
                .run(category, 990000 + category, 17, p.id)
            db.prepare('INSERT OR REPLACE INTO players_category_mission_stages(category,id,status,player_id,mission_id) VALUES(?,?,?,?,?)')
                .run(category, 1, 1, p.id, 990000 + category)
        }
        load('data/domains/quest').insertPlayerQuestProgressSync(p.id, 2, { questId: 1001001, finished: true,
            bestElapsedTimeMs: 45678, highScore: 123, clearRank: 5, leaderCharacterId: 1 })
        load('data/domains/item').givePlayerItemSync(p.id, 14040, 19)
    }
    db.prepare(`INSERT INTO five_boss_solo_runs(player_id,play_id,status,auto_used) VALUES(?,?,'active',1)`)
        .run(fixture[2].id, 'synthetic-old-2')
    db.prepare(`INSERT OR REPLACE INTO daily_vmoney_mail_config(id,enabled) VALUES(1,1)`).run()
    for (const bucket of ['2023-11-13', '2026-10-10']) db.prepare(`INSERT INTO daily_vmoney_mail_runs
        VALUES(?,?,?,'synthetic',150000,'historical only','no cross-year backfill',0)`).run(bucket, legacyMs, legacyMs)
    const markerBefore = rows('player_time_state')
    const legacyLedgerBefore = rows('player_time_migration_ledger')
    const before = state(db)
    let plan = engine().planTimeCutoverRehearsalSync(db, options())

    await t.test('preview digest rejects intervening business changes without applying partial migration', () => {
        db.prepare('UPDATE players SET name=? WHERE id=?').run('changed-after-plan',fixture[0].id)
        const drifted=state(db)
        assert.throws(()=>engine().applyTimeCutoverRehearsalSync(db,{...options(),expectedPlanDigest:plan.digest}),/digest|changed/i)
        assert.deepEqual(state(db),drifted)
        db.prepare('UPDATE players SET name=? WHERE id=?').run(before.players.rows.find(row=>row.id===fixture[0].id).name,fixture[0].id)
        assert.deepEqual(state(db),before)
    })
    await t.test('SQL transaction faults leave every business row and schema intact', () => {
        for (const faultAt of ['after-schema', 'after-player-update', 'before-ledger', 'after-ledger']) {
            assert.throws(() => engine().applyTimeCutoverRehearsalSync(db, { ...options(), expectedPlanDigest: plan.digest, faultAt }))
            assert.deepEqual(state(db), before, faultAt)
        }
    })
    await t.test('apply, duplicate, guarded rollback and restart are durable', () => {
        assert.equal(engine().applyTimeCutoverRehearsalSync(db, { ...options(), expectedPlanDigest: plan.digest }).status, 'applied')
        const applied = state(db)
        assert.equal(engine().applyTimeCutoverRehearsalSync(db, { ...options(), expectedPlanDigest: plan.digest }).status, 'already-applied')
        assert.deepEqual(state(db), applied)
        for (const faultAt of ['after-player-restore', 'before-ledger']) {
            assert.throws(() => engine().rollbackTimeCutoverRehearsalSync(db, { offlineGuard: guard(), expectedPlanDigest: plan.digest, faultAt }))
            assert.deepEqual(state(db), applied)
        }
        engine().rollbackTimeCutoverRehearsalSync(db, { offlineGuard: guard(), expectedPlanDigest: plan.digest })
        assert.deepEqual(state(db, ['time_cutover_rehearsal_ledger']), before)
        plan = engine().planTimeCutoverRehearsalSync(db, options())
        engine().applyTimeCutoverRehearsalSync(db, { ...options(), expectedPlanDigest: plan.digest })
        assert.equal(players.getPlayerSync(fixture[0].id).expPooledTime.getTime(),realMs-30000)
        assert.equal(players.getPlayerSync(fixture[1].id).expPooledTime.getTime(),realMs)
        assert.equal(players.getPlayerSync(fixture[1].id).expPool,1235)
        const after=state(db)
        for(const [name,table] of Object.entries(before)) if(!['players','player_time_state'].includes(name)) {
            assert.deepEqual(after[name],table,`unrelated table ${name}`)
        }
        const nonTime=row=>Object.fromEntries(Object.entries(row).filter(([key])=>!['exp_pooled_time','time_offset'].includes(key)))
        assert.deepEqual(after.players.rows.map(nonTime),before.players.rows.map(nonTime),'all non-EXP-time player columns')
        const childCode = `const assert=require('node:assert/strict');const db=new(require('better-sqlite3'))(process.env.OFFLINE_DATABASE);const engine=require(process.env.OFFLINE_ENGINE);const opts=JSON.parse(process.env.OFFLINE_OPTIONS);assert.equal(engine.applyTimeCutoverRehearsalSync(db,opts).status,'already-applied');db.close()`
        const child = spawnSync(process.execPath, ['-e', childCode], { cwd: path.resolve(__dirname, '..'), windowsHide: true,
            env: { ...process.env, OFFLINE_DATABASE: db.name, OFFLINE_ENGINE: path.join(out, 'lib/time-cutover-rehearsal.js'),
                OFFLINE_OPTIONS: JSON.stringify({ ...options(), expectedPlanDigest: plan.digest }) }, encoding: 'utf8', timeout: 30000 })
        assert.equal(child.status, 0, child.stdout + child.stderr)
        assert.deepEqual(rows('players_active_quests'), before.players_active_quests.rows.sort((a,b)=>a.player_id-b.player_id))
        assert.equal(rows('players_active_quests').length, 149)
        assert.deepEqual(rows('five_boss_solo_runs'), before.five_boss_solo_runs.rows)
        assert.deepEqual(rows('player_time_state').filter(row => fixture.slice(2,4).some(p=>p.id===row.player_id)), markerBefore)
        assert.deepEqual(rows('player_time_migration_ledger'), legacyLedgerBefore)
    })
    await t.test('first real-context maintenance preserves nonempty day/week progress without mail or EXP windfall', () => {
        const protectedTables = ['players_periodic_snapshots', 'players_category_missions', 'players_category_mission_stages',
            'players_quest_progress', 'players_items', 'players_mails', 'daily_vmoney_mail_grants', 'daily_vmoney_mail_runs']
        const protectedBefore = Object.fromEntries(protectedTables.map(name=>[name,rows(name)]))
        for (const p of fixture.slice(0,4)) atReal(() => persistence.runPersistenceTransactionSync({ domain:'player',playerId:p.id,operation:'offline_load_maintenance' }, () => {
            const current = players.getPlayerSync(p.id)
            assert.equal(mail.ensureDailyVmoneyMailForPlayerSync(p.id, clock.getRealServerDate().getTime()), false)
            assert.equal(players.dailyResetPlayerDataSync(current, clock.getServerDate()), false)
            players.collectPlayerDataPooledExpSync(current, clock.getServerDate())
            players.updatePlayerSync({ id:p.id,lastLoginTime:load('lib/player-time-compat').getPlayerBusinessDateSync(p.id,clock.getServerDate()) })
            assert.equal(players.getPlayerSync(p.id).expPool, 1234 + fixture.indexOf(p))
            assert.equal(players.getPlayerSync(p.id).boostPoint, 1)
            assert.equal(players.getPlayerSync(p.id).bossBoostPoint, 2)
            assert.equal(players.getPlayerSync(p.id).totalLoginDays, 27)
        }))
        assert.deepEqual(Object.fromEntries(protectedTables.map(name=>[name,rows(name)])), protectedBefore)
        assert.throws(()=>engine().rollbackTimeCutoverRehearsalSync(db,{offlineGuard:guard(),expectedPlanDigest:plan.digest}), /drift|changed|different|progress|状态|变化/i)
        const maintained = state(db)
        assert.equal(engine().applyTimeCutoverRehearsalSync(db,{...options(),expectedPlanDigest:plan.digest}).status,'already-applied')
        assert.deepEqual(state(db), maintained)
        assert.equal(clock.getLegacyTimeOffset(), offset)
    })
    await t.test('nonzero legacy-clock registration retains elapsed duration and actual finish receipt prevents duplicate reward', () => {
        const p=fixture[0], active=quests.getPlayerActiveQuestSync(p.id)
        assert.equal(atReal(()=>load('lib/battle-clock-compatibility').getBattleClockDate(0).getTime()-active.startedAtMs),60000)
        assert.equal(atReal(()=>load('lib/battle-clock-compatibility').getBattleClockDate(1).getTime()),realMs)
        // Negative control: clearing the legacy configuration destroys the old
        // coordinate even though the real context itself is valid.
        const negativeCode=`const a=require('node:assert/strict');const u=require(process.env.CLOCK_MODULE);const b=require(process.env.BATTLE_CLOCK_MODULE);const previous=u.getLegacyTimeOffset();try{u.setServerTimeOffset(0);const elapsed=u.withServerClock(${realMs},()=>b.getBattleClockDate(0).getTime()-${active.startedAtMs},0);a.notEqual(elapsed,60000);a.ok(elapsed>365*86400000)}finally{u.setServerTimeOffset(previous)}`
        const negative=spawnSync(process.execPath,['-e',negativeCode],{cwd:path.resolve(__dirname,'..'),windowsHide:true,
            env:{...process.env,CLOCK_MODULE:path.join(out,'utils.js'),BATTLE_CLOCK_MODULE:path.join(out,'lib/battle-clock-compatibility.js')},encoding:'utf8',timeout:30000})
        assert.equal(negative.status,0,negative.stdout+negative.stderr)
        const body={play_id:active.playId,quest_id:active.questId,category:active.category,elapsed_time_ms:60000,
            continue_count:0,score:100,add_mana:0,is_accomplished:true,is_restored:false,statistics:{clear_phase:1,max_combo_count:17,
                party:{characters:[{id:1},null,null],unison_characters:[null,null,null],equipments:[null,null,null],ability_soul_ids:[null,null,null]}}}
        const questData={...load('lib/assets').getQuestFromCategorySync(2,1001001),rankPointReward:14,characterExpReward:0,poolExpReward:26,
            manaReward:135,clearReward:undefined,sPlusReward:undefined,scoreRewardGroupId:undefined,scoreRewardGroup:undefined}
        const args={playerId:p.id,viewerId:880000000+p.id,questCategory:2,questId:1001001,questData,activeQuestData:active,body,
            clearTime:60000,clearRank:5,questAccomplished:true,fiveBossSoloQuest:false,registered:true,scoreAttackBorderTiers:[],
            manaObtained:135,displayMode15ManaAsFieldDrop:false,finishCacheKey:null,receiptPlayId:active.playId}
        const finish=()=>atReal(()=>persistence.runPersistenceTransactionSync({domain:'player',playerId:p.id,operation:'offline_single_finish'},()=>load('lib/quest/finish/single-finish-transaction').settleSingleQuestFinishInTransaction(args)))
        const balanceBefore=players.getPlayerSync(p.id)
        const result=finish();assert.ok(result.response)
        const balanceAfter=players.getPlayerSync(p.id)
        assert.equal(balanceAfter.rankPoint-balanceBefore.rankPoint,14)
        assert.equal(balanceAfter.expPool-balanceBefore.expPool,26)
        assert.equal(balanceAfter.freeMana-balanceBefore.freeMana,135)
        const paid=state(db)
        assert.deepEqual(finish().response,result.response)
        assert.deepEqual(state(db),paid)
        assert.equal(db.prepare("SELECT count(*) n FROM player_operation_receipts WHERE player_id=? AND operation='quest_finish.single'").get(p.id).n,1)
    })
    await t.test('actual old multiplayer finish pays once and replays its durable receipt', () => {
        const p=fixture[1],active=quests.getPlayerActiveQuestSync(p.id)
        assert.equal(active.clockVersion,0)
        assert.equal(atReal(()=>load('lib/battle-clock-compatibility').getBattleClockDate(0).getTime()-active.startedAtMs),60000)
        const questData={...load('lib/assets').getQuestFromCategorySync(2,1001001),rankPointReward:14,characterExpReward:0,
            poolExpReward:26,manaReward:135,clearReward:undefined,sPlusReward:undefined,scoreRewardGroupId:undefined,scoreRewardGroup:undefined}
        const body={play_id:active.playId,quest_id:active.questId,category:active.category,room_number:active.roomNumber,
            elapsed_time_ms:60000,continue_count:0,score:100,add_mana:0,is_accomplished:true,is_restored:false,mate_player_result:[],
            statistics:{clear_phase:1,max_combo_count:17,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],
                equipments:[null,null,null],ability_soul_ids:[null,null,null]}}}
        const args={playerId:p.id,viewerId:880000000+p.id,body,questCategory:2,questId:1001001,questData,activeQuestData:active,
            allowFrozenSnapshot:false,playId:active.playId,finishedAsHost:true,finishedAsRescueGuest:false,
            finishedAsRescueFragmentEligible:false,finishedAsNewbieRescueGuest:false,matePlayerResult:[],followInfo:[],evaluationTimeMs:realMs}
        const finish=()=>atReal(()=>persistence.runPersistenceTransactionSync({domain:'player',playerId:p.id,operation:'offline_multi_finish'},
            ()=>load('lib/quest/finish/multi-finish-transaction').settleMultiQuestFinishInTransaction(args)))
        const balanceBefore=players.getPlayerSync(p.id)
        const result=finish();assert.ok(result.response);assert.equal(result.applied,true)
        const balanceAfter=players.getPlayerSync(p.id)
        assert.equal(balanceAfter.rankPoint-balanceBefore.rankPoint,14)
        assert.equal(balanceAfter.expPool-balanceBefore.expPool,26)
        assert.equal(balanceAfter.freeMana-balanceBefore.freeMana,135)
        const paid=state(db),duplicate=finish()
        assert.equal(duplicate.applied,false);assert.deepEqual(duplicate.response,result.response);assert.deepEqual(state(db),paid)
        assert.equal(db.prepare("SELECT count(*) n FROM player_operation_receipts WHERE player_id=? AND operation='quest_finish.multi'").get(p.id).n,1)
    })
    await t.test('actual V2 export/import keeps portable nonempty progress and target-local markers', () => {
        atReal(()=>{
            const source=fixture[0],target=fixture[2]
            const exported=save.createPlayerSaveSnapshotV2Sync(source.id,db)
            const markers=rows('player_time_state'),ledgers=rows('player_time_migration_ledger')
            assert.ok(exported.data.tables.players_quest_progress.rows.length>0)
            assert.ok(exported.data.tables.players_category_missions.rows.length>0)
            assert.ok(exported.data.tables.players_items.rows.length>0)
            save.restorePlayerSaveSnapshotV2Sync(exported,target.id,{},db)
            assert.deepEqual(rows('player_time_state'),markers)
            assert.deepEqual(rows('player_time_migration_ledger'),ledgers)
            const restored=save.createPlayerSaveSnapshotV2Sync(target.id,db)
            for(const name of ['players_quest_progress','players_category_missions','players_items']) {
                const normalize=table=>table.rows.map(row=>row.map((v,i)=>table.columns[i]==='player_id'?0:v))
                assert.deepEqual(normalize(restored.data.tables[name]),normalize(exported.data.tables[name]),name)
            }
            assert.equal(players.getPlayerSync(target.id).expPool,players.getPlayerSync(source.id).expPool)
            assert.equal(players.getPlayerSync(target.id).expPooledTime.getTime(),realMs)
        })
        assert.equal(db.pragma('quick_check',{simple:true}),'ok')
        assert.deepEqual(db.pragma('foreign_key_check'),[])
    })
})
