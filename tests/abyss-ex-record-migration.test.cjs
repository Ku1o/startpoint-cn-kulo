const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'abyss-ex-record-migration-'))
process.env.DATA_DIR = temp
const { getDb } = require('../out/data/db'), db = getDb()
const { initializeAbyssRecords } = require('../out/data/initializers/abyss-records')
const legacySql = `CREATE TABLE abyss_floor_records (
 revision TEXT NOT NULL,
 quest_id INTEGER NOT NULL CHECK (quest_id BETWEEN 700099001 AND 700099098),
 elapsed_time_ms INTEGER NOT NULL CHECK (elapsed_time_ms > 0),
 viewer_id INTEGER NOT NULL, recorded_at_ms INTEGER NOT NULL,
 PRIMARY KEY (revision, quest_id)) WITHOUT ROWID`
test.after(() => db.close())

test('old database rejects EX finish; migration preserves history and retry settles exactly once', async () => {
 const finish = require('../out/routes/api/singleBattleQuest')
 const accounts = require('../out/data/domains/account'), players = require('../out/data/domains/player')
 const { getServerTime } = require('../out/utils')
 const { getAbyssTimeRevision } = require('../out/lib/abyss-time-revision')
 const { canStartAbyssQuestSync } = require('../out/data/domains/abyss-tower-progress')
 const { pack, unpack } = require('msgpackr')
 db.exec('DROP TABLE abyss_floor_records')
 db.exec(legacySql)
 db.prepare('INSERT INTO abyss_floor_records VALUES (?,700099001,45000,123,1000)').run('a'.repeat(64))
 db.exec('CREATE INDEX abyss_record_holder_fixture ON abyss_floor_records(viewer_id)')
 const old = db.prepare('SELECT * FROM abyss_floor_records').all()
 const snapshots = require('../out/data/snapshots/player-snapshot')
 const account = accounts.insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'test',idpId:'',status:'normal'})
 const player = players.insertDefaultPlayerSync(account.id), viewer = 850000000 + player.id
 db.prepare('INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)').run(String(viewer),account.id,'2099-01-01T00:00:00.000Z')
 db.prepare('INSERT INTO players_rush_events_cleared_folders(player_id,event_id,folder_id) VALUES (?,700099,1)').run(player.id)
 const fingerprint = snapshots.createPlayerSaveSnapshotV2Sync(player.id).schemaFingerprint
 const app = require('fastify')()
 app.addHook('onSend',(_req,reply,payload,done)=>done(null,reply.getHeader('content-type')==='application/x-msgpack'?pack(payload).toString('base64'):payload))
 await app.register(finish.default,{prefix:'/single_battle_quest'})
 const currentVersion = require('../assets/asset-patch/manifest.json').cdn_version
 const request = {method:'POST',url:'/single_battle_quest/finish',headers:{res_ver:currentVersion},payload:{
  viewer_id:viewer,category:24,quest_id:700100001,play_id:'ex-migration-recovery',continue_count:0,
  elapsed_time_ms:60000,score:12345,add_mana:0,is_accomplished:true,is_restored:false,api_count:1,
  statistics:{clear_phase:1,party:{characters:[{id:1},null,null],unison_characters:[null,null,null],
   equipments:[null,null,null],ability_soul_ids:[null,null,null]},zones:[]}}}
 const inventory = () => db.prepare('SELECT * FROM players_items WHERE player_id=? ORDER BY id').all(player.id)
 const progress = () => db.prepare('SELECT * FROM players_quest_progress WHERE player_id=? AND quest_id=700100001').get(player.id)
 const parties = () => db.prepare('SELECT * FROM players_rush_events_played_parties WHERE player_id=? AND event_id=700100').all(player.id)
 finish.insertActiveQuest(player.id,{category:24,questId:700100001,playId:request.payload.play_id,isMulti:false,
  useBoostPoint:false,useBossBoostPoint:false,isAutoStartMode:false,continueCount:0,startedAtMs:getServerTime()*1000-180000})
 const before = inventory()
 try {
  const failed = await app.inject(request)
  assert.equal(failed.statusCode,500)
  assert.match(failed.body,/CHECK constraint failed/)
  assert.deepEqual(inventory(),before)
  assert.equal(progress(),undefined)
  assert.deepEqual(parties(),[])
  assert.ok(db.prepare('SELECT 1 FROM players_active_quests WHERE player_id=?').get(player.id))
  initializeAbyssRecords(db)
  initializeAbyssRecords(db)
  assert.deepEqual(db.prepare('SELECT * FROM abyss_floor_records').all(),old)
  assert.ok(db.prepare("SELECT 1 FROM sqlite_master WHERE name='abyss_record_holder_fixture'").get())
  assert.equal(snapshots.createPlayerSaveSnapshotV2Sync(player.id).schemaFingerprint,fingerprint)
  delete finish.activeQuests[player.id] // Restart recovery must use the persisted registration.
  const success = await app.inject(request)
  assert.equal(success.statusCode,200,success.body)
  assert.equal(unpack(Buffer.from(success.body,'base64')).data_headers.result_code,1)
  assert.equal(progress().finished,1)
  assert.equal(progress().best_elapsed_time_ms,60000)
  assert.deepEqual(parties().map(p=>p.round),[700100001])
  assert.equal(canStartAbyssQuestSync(player.id,24,700100002),true)
  assert.equal(db.prepare('SELECT elapsed_time_ms FROM abyss_floor_records WHERE revision=? AND quest_id=700100001').get(getAbyssTimeRevision(700100)).elapsed_time_ms,60000)
  const credited = inventory()
  assert.notDeepEqual(credited,before,'actual EX reward inventory must increase')
  const repeat = await app.inject(request)
  assert.equal(repeat.statusCode,200)
  assert.equal(repeat.body,success.body)
  assert.deepEqual(inventory(),credited)
  assert.equal(parties().length,1)
 } finally { await app.close() }
})

test('fresh schema accepts both finite ranges and rejects endless or unrelated quests', () => {
 const isolated = new (require('better-sqlite3'))(':memory:')
 try {
  initializeAbyssRecords(isolated)
  const insert = isolated.prepare('INSERT INTO abyss_floor_records VALUES (?,?,1,1,1)')
  for (const id of [700099001,700099098,700100001,700100030]) insert.run('revision',id)
  for (const id of [700099000,700099099,700100000,700100031,700100099,700101001])
   assert.throws(()=>insert.run('revision',id),/CHECK constraint failed/)
 } finally { isolated.close() }
})
