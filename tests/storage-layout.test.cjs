require('ts-node/register/transpile-only')
const test = require('node:test')
const assert = require('node:assert/strict')
const Database = require('better-sqlite3')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { migrateStorageLayout, assertStorageLayout, writeCompactMissionCounter, getStorageSnapshotTableInfo } = require('../src/lib/storage-layout')

function fixture(filename = ':memory:') {
    const db = new Database(filename)
    db.pragma('foreign_keys=ON')
    db.exec(`
        CREATE TABLE players(id INTEGER PRIMARY KEY);
        CREATE TABLE players_characters(id INTEGER NOT NULL, player_id INTEGER NOT NULL, PRIMARY KEY(id,player_id), FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE);
        CREATE TABLE players_mission_counters(player_id INTEGER NOT NULL,counter_key TEXT NOT NULL,dimension TEXT NOT NULL,scope_type TEXT NOT NULL,scope_key TEXT NOT NULL,qualifier_json TEXT NOT NULL,value INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(player_id,counter_key),FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE);
        CREATE TABLE players_mission_counter_snapshots(player_id INTEGER NOT NULL,period_type TEXT NOT NULL,counter_key TEXT NOT NULL,value INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(player_id,period_type,counter_key),FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE);
        CREATE TABLE players_characters_mana_nodes(value INTEGER NOT NULL,awake_level INTEGER NOT NULL DEFAULT 0,character_id INTEGER NOT NULL,player_id INTEGER NOT NULL,PRIMARY KEY(value,character_id,player_id),FOREIGN KEY(character_id,player_id) REFERENCES players_characters(id,player_id) ON DELETE CASCADE,FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE);
        CREATE TABLE players_characters_bond_tokens(mana_board_index INTEGER NOT NULL,status INTEGER NOT NULL,player_id INTEGER NOT NULL,character_id INTEGER NOT NULL,PRIMARY KEY(mana_board_index,player_id,character_id),FOREIGN KEY(character_id,player_id) REFERENCES players_characters(id,player_id) ON DELETE CASCADE,FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE);
        CREATE INDEX idx_cleanup_fk_players_characters_mana_nodes_0 ON players_characters_mana_nodes(player_id);
        CREATE INDEX idx_cleanup_fk_players_characters_mana_nodes_1 ON players_characters_mana_nodes(character_id,player_id);
        INSERT INTO players VALUES(1),(2);
        INSERT INTO players_characters VALUES(100,1),(100,2);
        INSERT INTO players_characters_mana_nodes VALUES(0,0,100,1),(1,2,100,1),(2,0,100,2);
        INSERT INTO players_characters_bond_tokens VALUES(0,0,1,100),(1,1,1,100),(0,1,2,100);
        INSERT INTO players_mission_counters VALUES(1,'clear|lifetime|all|{}','clear','lifetime','all','{}',15,'2026-09-06'),(2,'clear|lifetime|all|{}','clear','lifetime','all','{}',21,'2026-09-07');
        INSERT INTO players_mission_counter_snapshots VALUES(1,'daily','clear|lifetime|all|{}',10,'2026-07-25');
    `)
    return db
}

test('migration preserves logical counters, zero states, foreign keys, and restart idempotency', () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(),'sp-storage-layout-'))
    const file = path.join(dir,'test.db')
    let db = fixture(file)
    try {
        const tables = ['players_mission_counters','players_characters_mana_nodes','players_characters_bond_tokens']
        const before = Object.fromEntries(tables.map(t=>[t, db.prepare(`SELECT * FROM ${t} ORDER BY player_id`).all()]))
        const schema = db.prepare('PRAGMA table_info(players_characters_mana_nodes)').all()
        const result = migrateStorageLayout(db)
        assert.equal(result.retiredSnapshotRows,1)
        assert.equal(result.preservedRows.players_mission_counters,2)
        for(const t of tables) assert.deepEqual(db.prepare(`SELECT * FROM ${t} ORDER BY player_id`).all(),before[t])
        assert.equal(db.prepare('SELECT COUNT(*) n FROM mission_counter_definitions').get().n,1)
        assert.equal(db.prepare('SELECT COUNT(*) n FROM players_mission_counter_snapshots').get().n,0)
        assert.deepEqual(getStorageSnapshotTableInfo(db,'players_characters_mana_nodes'),schema)
        assert.ok(result.removedIndexes.includes('idx_cleanup_fk_players_characters_mana_nodes_0'))
        assert.ok(db.prepare("SELECT 1 FROM sqlite_master WHERE name='idx_cleanup_fk_players_characters_mana_nodes_1'").get())
        assert.deepEqual(db.pragma('foreign_key_check'),[])
        assert.equal(db.pragma('integrity_check',{simple:true}),'ok')
        db.close(); db = new Database(file); db.pragma('foreign_keys=ON')
        assertStorageLayout(db)
        assert.equal(migrateStorageLayout(db).alreadyApplied,true)
        const def={key:'clear|lifetime|all|{}',dimension:'clear',scopeType:'lifetime',scopeKey:'all',qualifierJson:'{}'}
        assert.equal(writeCompactMissionCounter(db,1,def,2,'add'),17)
        assert.equal(writeCompactMissionCounter(db,1,def,9,'max'),17)
        assert.equal(writeCompactMissionCounter(db,1,def,20,'max'),20)
        assert.equal(writeCompactMissionCounter(db,1,def,5,'min'),5)
        assert.throws(()=>writeCompactMissionCounter(db,1,{...def,dimension:'wrong'},5,'add'),/冲突/)
        db.prepare('DELETE FROM players_mission_counters WHERE player_id=1').run()
        db.prepare(`INSERT INTO players_mission_counters VALUES(1,?,?,?,?,?,?,?)`).run(def.key,def.dimension,def.scopeType,def.scopeKey,def.qualifierJson,33,'restored')
        assert.equal(db.prepare('SELECT value FROM players_mission_counters WHERE player_id=1').get().value,33)
        db.prepare('DELETE FROM players WHERE id=1').run()
        assert.equal(db.prepare('SELECT COUNT(*) n FROM players_mission_counter_values WHERE player_id=1').get().n,0)
        assert.equal(db.prepare('SELECT COUNT(*) n FROM players_characters_mana_nodes WHERE player_id=1').get().n,0)
        assert.deepEqual(db.pragma('foreign_key_check'),[])
    } finally { db.close(); fs.rmSync(dir,{recursive:true,force:true}) }
})

test('an interrupted transaction restores original tables, values and migration marker', () => {
    for(const stage of ['counters-verified','character-details-verified','before-commit']) {
        const db=fixture()
        try {
            assert.throws(()=>migrateStorageLayout(db,current=>{if(current===stage)throw new Error('injected interruption')}),/injected/)
            assert.equal(db.prepare("SELECT type FROM sqlite_master WHERE name='players_mission_counters'").get().type,'table')
            assert.equal(db.prepare('SELECT value FROM players_mission_counters WHERE player_id=1').get().value,15)
            assert.equal(db.prepare('SELECT COUNT(*) n FROM players_mission_counter_snapshots').get().n,1)
            assert.equal(db.prepare("SELECT 1 FROM sqlite_master WHERE name='server_storage_migrations'").get(),undefined)
            assert.equal(db.pragma('foreign_keys',{simple:true}),1)
            assert.equal(migrateStorageLayout(db).alreadyApplied,false)
        } finally { db.close() }
    }
})

test('unknown layouts and conflicting shared definitions fail without changing data',()=>{
    const db=fixture()
    try {
        db.prepare("UPDATE players_mission_counters SET dimension='other' WHERE player_id=2").run()
        assert.throws(()=>migrateStorageLayout(db),/不同定义/)
        assert.equal(db.prepare("SELECT type FROM sqlite_master WHERE name='players_mission_counters'").get().type,'table')
        db.exec("CREATE TABLE server_storage_migrations(version INTEGER PRIMARY KEY); INSERT INTO server_storage_migrations VALUES(999)")
        assert.throws(()=>assertStorageLayout(db),/高于/)
    } finally {db.close()}
})
