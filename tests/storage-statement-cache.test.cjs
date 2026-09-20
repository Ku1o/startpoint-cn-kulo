require('ts-node/register/transpile-only')
const test = require('node:test')
const assert = require('node:assert/strict')
const Database = require('better-sqlite3')
const { getStorageLayoutVersion, isCompactStorage, writeCompactMissionCounter } = require('../src/lib/storage-layout')

function compact() {
    const db = new Database(':memory:')
    db.pragma('foreign_keys=ON')
    db.exec(`
        CREATE TABLE server_storage_migrations(version INTEGER PRIMARY KEY);
        INSERT INTO server_storage_migrations VALUES(1);
        CREATE TABLE players(id INTEGER PRIMARY KEY);
        INSERT INTO players VALUES(1),(2);
        CREATE TABLE mission_counter_definitions(id INTEGER PRIMARY KEY,counter_key TEXT NOT NULL UNIQUE,
            dimension TEXT NOT NULL,scope_type TEXT NOT NULL,scope_key TEXT NOT NULL,qualifier_json TEXT NOT NULL);
        CREATE TABLE players_mission_counter_values(player_id INTEGER NOT NULL,counter_id INTEGER NOT NULL,
            value INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL,PRIMARY KEY(player_id,counter_id),
            FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE,
            FOREIGN KEY(counter_id) REFERENCES mission_counter_definitions(id)) WITHOUT ROWID;
    `)
    return db
}
const definition = { key:'battle|lifetime|all|{}', dimension:'battle', scopeType:'lifetime', scopeKey:'all', qualifierJson:'{}' }
const read = db => db.prepare('SELECT player_id,value FROM players_mission_counter_values ORDER BY player_id').all()

test('repeated compact counter writes reuse compilation while keeping player bindings and operation semantics', () => {
    const db = compact(), original = db.prepare
    let prepares = 0
    db.prepare = function(sql) { prepares++; return original.call(this, sql) }
    try {
        for (let i=0; i<1000; i++) {
            assert.equal(isCompactStorage(db), true)
            const player=1+i%2
            assert.equal(writeCompactMissionCounter(db,player,definition,2,'add'),2)
            assert.equal(writeCompactMissionCounter(db,player,definition,9,'max'),9)
            assert.equal(writeCompactMissionCounter(db,player,definition,0,'min'),0)
        }
        assert.equal(prepares,6, 'two layout queries, one definition insert, and three update operations')
        assert.deepEqual(read(db), [{player_id:1,value:0},{player_id:2,value:0}])
    } finally { db.close() }
})

test('cached layout queries observe new tables, rollback, changed versions and recreated tables', () => {
    const db = new Database(':memory:')
    try {
        assert.equal(getStorageLayoutVersion(db),0)
        db.exec('CREATE TABLE server_storage_migrations(version INTEGER PRIMARY KEY)')
        assert.equal(getStorageLayoutVersion(db),0)
        assert.throws(()=>db.transaction(()=>{
            db.exec('INSERT INTO server_storage_migrations VALUES(1)')
            assert.equal(isCompactStorage(db),true)
            throw Error('rollback')
        })(),/rollback/)
        assert.equal(getStorageLayoutVersion(db),0)
        db.exec('INSERT INTO server_storage_migrations VALUES(999)')
        assert.throws(()=>getStorageLayoutVersion(db),/高于/)
        db.exec('DROP TABLE server_storage_migrations')
        assert.equal(getStorageLayoutVersion(db),0)
        db.exec('CREATE TABLE server_storage_migrations(version INTEGER PRIMARY KEY); INSERT INTO server_storage_migrations VALUES(1)')
        assert.equal(isCompactStorage(db),true)
    } finally { db.close() }
})

test('cached compact statements isolate connections and preserve nested rollback and failure atomicity', () => {
    const first=compact(), second=compact()
    try {
        assert.equal(writeCompactMissionCounter(first,1,definition,4,'add'),4)
        assert.equal(writeCompactMissionCounter(second,2,definition,7,'add'),7)
        assert.throws(()=>first.transaction(()=>{
            writeCompactMissionCounter(first,1,definition,10,'add')
            writeCompactMissionCounter(first,2,definition,20,'add')
            throw Error('outer rollback')
        })(),/outer rollback/)
        assert.deepEqual(read(first),[{player_id:1,value:4}])
        assert.throws(()=>writeCompactMissionCounter(first,1,{...definition,dimension:'conflict'},1,'add'),/冲突/)
        assert.throws(()=>writeCompactMissionCounter(first,99,{...definition,key:'failed-new-definition'},1,'add'),/FOREIGN KEY/)
        assert.equal(first.prepare('SELECT COUNT(*) n FROM mission_counter_definitions').get().n,1)
        assert.equal(writeCompactMissionCounter(first,2,definition,3,'add'),3)
        first.close()
        assert.equal(writeCompactMissionCounter(second,2,definition,2,'add'),9)
        assert.deepEqual(read(second),[{player_id:2,value:9}])
        assert.deepEqual(second.pragma('foreign_key_check'),[])
    } finally { if(first.open)first.close(); second.close() }
})
