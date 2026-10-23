if (!process.env.STARPOINT_TEST_COMPILED_ROOT) require("ts-node/register/transpile-only")
const test = require("node:test"), assert = require("node:assert/strict")
const fs = require("node:fs"), os = require("node:os"), path = require("node:path")
const Fastify = require("fastify"), { pack, unpack } = require("msgpackr")
const compiledRoot = process.env.STARPOINT_TEST_COMPILED_ROOT
const load = name => require(compiledRoot ? path.join(compiledRoot, name) : path.resolve(__dirname, "../src", name))
const asset = name => require(path.resolve(compiledRoot ? path.dirname(compiledRoot) : path.resolve(__dirname, ".."), "assets", name))
const directory = fs.mkdtempSync(path.join(os.tmpdir(), "player-history-permanent-"))
process.env.DATA_DIR = directory
process.env.CN_WRITER_THREAD = "0"
const { initializeDatabase } = load("data")
const { getDb } = load("data/db")
const { insertAccountSync } = load("data/domains/account")
const { insertDefaultPlayerSync } = load("data/domains/player")
const { grantPlayerDegreeSync } = load("data/domains/degree")
const { givePlayerCharacterSync } = load("lib/character")
const { getPlayerHistoryCatalog, PLAYER_HISTORY_START_MS } = load("lib/player-history-catalog")
const { formatPlayerHistoryJstDate } = load("lib/player-history-aggregates")
const routes = load("routes/api/playerHistory").default
initializeDatabase()
const db = getDb(), now = Date.now()
assert.equal(path.dirname(fs.realpathSync(db.name)),fs.realpathSync(directory))
const clockOptions = {cutoverRealMs:now,legacyOffsetMs:0,readiness:"scenario-only",
    offlineGuard:{kind:"approved-offline-file",databasePath:fs.realpathSync(db.name),allowedRoot:directory}}
const clock = load("lib/server-clock-state")
const clockPlan = load("lib/time-cutover-rehearsal").planTimeCutoverRehearsalSync(db,clockOptions)
clock.activateRealServerClockOfflineSync(db,{...clockOptions,expectedPlanDigest:clockPlan.digest})
clock.restoreServerClockStateSync(db)
function player(suffix, withSave = true) {
    const account = insertAccountSync({appId:"wf_cn",idpAlias:"",idpCode:"test",idpId:`history-permanent-${suffix}`,status:"normal"})
    const saved = withSave ? insertDefaultPlayerSync(account.id) : null
    const viewerId = 770000000 + account.id
    db.prepare("INSERT INTO sessions(token,account_id,expires,type) VALUES(?,?,?,2)")
        .run(String(viewerId),account.id,"2099-12-31T00:00:00.000Z")
    return {account,saved,viewerId}
}
async function app() {
    const server = Fastify()
    server.addHook("onSend", (_req,reply,payload,done) => done(null,
        reply.getHeader("content-type") === "application/x-msgpack" ? pack(payload) : payload))
    await server.register(routes,{prefix:"/player_history"})
    await server.ready()
    return server
}
function decoded(response) { assert.equal(response.statusCode,200,response.body);return unpack(response.rawPayload) }
const request = (server, method, payload) => server.inject({method:"POST",url:`/player_history/${method}`,payload})
const settings = id => db.prepare("SELECT * FROM players_player_history_settings WHERE player_id=?").get(id)
test.after(() => {
    if(db.open) db.close()
    assert.equal(path.dirname(directory),os.tmpdir());fs.rmSync(directory,{recursive:true,force:true})
    if(compiledRoot) {
        const sourceRoot = path.resolve(__dirname,"../src") + path.sep
        assert.equal(Object.keys(require.cache).some(file=>file.startsWith(sourceRoot)),false,"compiled run must not load source modules")
        console.log(`COMPILED_PROFILE_ROOT ${path.resolve(compiledRoot)}`)
    }
})

test("permanent catalog only accepts id1, finite time and the retained start boundary", () => {
    assert.equal(getPlayerHistoryCatalog(PLAYER_HISTORY_START_MS-1),null)
    assert.equal(getPlayerHistoryCatalog(PLAYER_HISTORY_START_MS).playerHistoryId,1)
    assert.equal(getPlayerHistoryCatalog(Date.parse("2200-01-01T00:00:00Z")).playerHistoryId,1)
    for(const time of [NaN,Infinity,-Infinity]) assert.equal(getPlayerHistoryCatalog(time),null)
    for(const id of [NaN,Infinity,0,-1,2,1.5,"1",null]) assert.equal(getPlayerHistoryCatalog(now,id),null)
    assert.equal(formatPlayerHistoryJstDate(new Date(NaN),0),null)
})

test("real-clock HTTP defaults, rights checks and persisted old toggles survive app/session reload", async () => {
    let server = await app()
    const owner = player("settings"), empty = player("no-save",false)
    try {
        for(const method of ["index","edit"]) {
            for(const viewer of [0,1.5,"770000001",null,999999999,empty.viewerId])
                assert.equal((await request(server,method,{viewer_id:viewer,background_card_id:1002})).statusCode,400)
        }
        const initial = decoded(await request(server,"index",{viewer_id:owner.viewerId})).data
        assert.equal(initial.player_history_id,1)
        assert.equal(Object.keys(initial.player_history_topic_list).length,27)
        assert(Object.values(initial.player_history_topic_list).every(topic=>topic.is_visible))
        assert.equal(settings(owner.saved.id),undefined,"opening the page does not persist defaults")
        for(const method of ["index","edit"]) for(const id of [0,-1,2,1.5,"1",null])
            assert.equal((await request(server,method,{viewer_id:owner.viewerId,player_history_id:id,background_card_id:1002})).statusCode,400)
        const invalid = [
            {party_info:{character_ids:[999999999,null,null],unison_character_ids:[null,null,null]}},
            {degree_id:999999999},{background_card_id:999999999},{player_history_topic_visible:{28:true}},
            {player_history_topic_visible:{1:"false"}},{background_card_id:1002,degree_id:1},
        ]
        for(const fields of invalid) assert.equal((await request(server,"edit",{viewer_id:owner.viewerId,...fields})).statusCode,400)
        assert.equal(settings(owner.saved.id),undefined)
        grantPlayerDegreeSync(owner.saved.id,57020,Date.parse("2025-06-01T00:00:00Z"))
        for(const fields of [{background_card_id:1002},{degree_id:57020},
            {party_info:{character_ids:[1,null,null],unison_character_ids:[null,1,null]}},
            {player_history_topic_visible:{1:false,27:false}}])
            decoded(await request(server,"edit",{viewer_id:owner.viewerId,...fields}))
        const before = settings(owner.saved.id)
        assert.deepEqual(JSON.parse(before.topic_visibility),{1:false,27:false})
        // A new app plus a new viewer token exercises persisted state rather than request-local objects.
        await server.close();server = await app()
        db.prepare("UPDATE sessions SET token=? WHERE token=?").run(String(owner.viewerId+10000),String(owner.viewerId))
        const reloaded = decoded(await request(server,"index",{viewer_id:owner.viewerId+10000})).data
        assert.equal(reloaded.background_card_id,1002);assert.equal(reloaded.degree_id,57020)
        assert.deepEqual(reloaded.favorite_character.unison_character_ids,[null,1,null])
        assert.equal(reloaded.player_history_topic_list[1].is_visible,false)
        assert.equal(reloaded.player_history_topic_list[27].is_visible,false)
        assert.equal(reloaded.player_history_topic_list[26].is_visible,true)
        assert.deepEqual(settings(owner.saved.id),before,"index does not overwrite partial old settings")
    } finally { await server.close() }
})

test("authoritative completion survives unknown dates and known acquisition dates stay exact", async () => {
    const server = await app(), owner = player("dates")
    const index = async()=>decoded(await request(server,"index",{viewer_id:owner.viewerId})).data.player_history_topic_list
    try {
        const fresh = await index()
        assert.deepEqual(fresh[3].value_list.int_values,[0,0,0,0,0,0])
        assert.deepEqual(fresh[5].value_list.int_values,[0])
        assert.deepEqual(fresh[5].value_list.character_id_values,[null])
        assert.deepEqual(fresh[8].value_list.int_values,[0]);assert.deepEqual(fresh[9].value_list.int_values,[0])
        const registered = "2024-01-02T03:04:05.000Z"
        db.prepare("UPDATE accounts SET first_login_time=? WHERE id=?").run(registered,owner.account.id)
        db.prepare("UPDATE players SET rank_point=? WHERE id=?").run(Number(asset("cdndata/player_rank_full.json")[100][0][1]),owner.saved.id)
        db.transaction(()=>{
            const chars=Object.keys(load("lib/content-master").serverCharacters).map(Number).sort((a,b)=>a-b).slice(0,100)
            for(const id of chars) assert(givePlayerCharacterSync(owner.saved.id,id))
            db.prepare("UPDATE players_characters_bond_tokens SET status=2 WHERE player_id=? AND character_id=1 AND mana_board_index=2").run(owner.saved.id)
            const insert = db.prepare("INSERT INTO players_quest_progress(section,quest_id,finished,host_finished,unlocked,player_id) VALUES(1,?,1,0,1,?)")
            for(const id of Object.keys(asset("main_quest.json")).map(Number).filter(id=>Math.floor(id/1000000)===1)) insert.run(id,owner.saved.id)
        })()
        const acquired = Date.parse("2025-06-01T01:02:03.000Z")
        grantPlayerDegreeSync(owner.saved.id,57020,acquired)
        const complete = await index()
        assert.deepEqual(complete[1].value_list.date_values,["2024-01-02 12:04:05"])
        assert.deepEqual(complete[3].value_list.int_values,[1,0,0,0,0,0])
        for(const topic of [3,4,5,8,9]) assert(complete[topic].value_list.date_values.every(value=>value===null))
        for(const topic of [5,8,9]) assert.deepEqual(complete[topic].value_list.int_values,[1])
        assert.deepEqual(complete[5].value_list.character_id_values,[1])
        assert.deepEqual(complete[18].value_list.boss_id_values,[1])
        assert.deepEqual(complete[18].value_list.int_values,[1])
        assert.deepEqual(complete[18].value_list.date_values,["2025-06-01 10:02:03"])
        // A legacy imported degree may prove ownership without knowing when it was obtained.
        db.prepare("UPDATE players_degrees SET acquired_at=0 WHERE player_id=? AND degree_id=57020").run(owner.saved.id)
        db.prepare("UPDATE accounts SET first_login_time='unknown' WHERE id=?").run(owner.account.id)
        const legacy = await index()
        assert.deepEqual(legacy[18].value_list.date_values,[null]);assert.deepEqual(legacy[18].value_list.int_values,[1])
        assert.deepEqual(legacy[18].value_list.boss_id_values,[1])
        assert.deepEqual(legacy[1].value_list.date_values,[null]);assert.deepEqual(legacy[1].value_list.int_values,[null])
    } finally { await server.close() }
})
