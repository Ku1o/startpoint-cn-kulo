'use strict'
require('ts-node/register/transpile-only')
const assert = require('node:assert/strict')
const { test } = require('node:test')
const Database = require('better-sqlite3')
const { findMissingCascadeDeleteIndexes, ensureCascadeDeleteIndexes } = require('../src/lib/admin-account-cleanup')

function schema(db) {
    return db.prepare('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').all()
}

test('cascade index preflight only reads schema and excludes partial indexes', () => {
    const db = new Database(':memory:')
    try {
        db.exec(`
            CREATE TABLE parent(a INTEGER, b INTEGER, PRIMARY KEY(a,b));
            CREATE TABLE missing(a INTEGER,b INTEGER, FOREIGN KEY(a,b) REFERENCES parent(a,b) ON DELETE CASCADE);
            CREATE TABLE partial(a INTEGER,b INTEGER,flag INTEGER, FOREIGN KEY(a,b) REFERENCES parent(a,b) ON DELETE CASCADE);
            CREATE INDEX partial_key ON partial(a,b) WHERE flag=1;
            CREATE TABLE covered(a INTEGER,b INTEGER,extra INTEGER, FOREIGN KEY(a,b) REFERENCES parent(a,b) ON DELETE CASCADE);
            CREATE INDEX complete_prefix ON covered(a,b,extra);
            CREATE TABLE reversed(a INTEGER,b INTEGER, FOREIGN KEY(a,b) REFERENCES parent(a,b) ON DELETE CASCADE);
            CREATE INDEX wrong_prefix ON reversed(b,a);
            CREATE TABLE noncascade(a INTEGER,b INTEGER, FOREIGN KEY(a,b) REFERENCES parent(a,b));
        `)
        const before = schema(db)
        const missing = findMissingCascadeDeleteIndexes(db)
        assert.deepEqual(missing.map(value => value.table), ['missing', 'partial', 'reversed'])
        assert.deepEqual(missing.map(value => value.columns), [['a', 'b'], ['a', 'b'], ['a', 'b']])
        assert.ok(missing.every(value => value.indexName === `idx_cleanup_fk_${value.table}_0`))
        assert.deepEqual(schema(db), before, 'online preflight must not create indexes')
        assert.equal(ensureCascadeDeleteIndexes(db), 3)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db), [])
        const installed = schema(db)
        assert.equal(ensureCascadeDeleteIndexes(db), 0)
        assert.deepEqual(schema(db), installed, 'existing full-prefix indexes must not be duplicated')
    } finally { db.close() }
})

test('new database installs missing single-column and composite cascade indexes', () => {
    const db = new Database(':memory:')
    try {
        db.exec(`
            CREATE TABLE accounts(id INTEGER PRIMARY KEY);
            CREATE TABLE players(id INTEGER PRIMARY KEY,account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE);
            CREATE TABLE details(player_id INTEGER,character_id INTEGER, PRIMARY KEY(character_id,player_id),
                FOREIGN KEY(player_id) REFERENCES players(id) ON DELETE CASCADE);
        `)
        assert.equal(findMissingCascadeDeleteIndexes(db).length, 2)
        assert.equal(ensureCascadeDeleteIndexes(db), 2)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db), [])
        db.pragma('foreign_keys=ON')
        db.exec('INSERT INTO accounts VALUES(1); INSERT INTO players VALUES(2,1); INSERT INTO details VALUES(2,100); DELETE FROM accounts WHERE id=1;')
        assert.equal(db.prepare('SELECT count(*) AS count FROM details').get().count, 0)
        assert.deepEqual(db.pragma('foreign_key_check'), [])
    } finally { db.close() }
})

test('cascade index creation rejects an occupied name that does not support the foreign key', () => {
    const db = new Database(':memory:')
    try {
        db.exec(`
            CREATE TABLE parent(id INTEGER PRIMARY KEY);
            CREATE TABLE child(parent_id INTEGER REFERENCES parent(id) ON DELETE CASCADE);
            CREATE TABLE unrelated(value INTEGER);
            CREATE INDEX idx_cleanup_fk_child_0 ON unrelated(value);
        `)
        assert.throws(() => ensureCascadeDeleteIndexes(db), /child/)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db).map(index => index.table), ['child'])
    } finally { db.close() }
})

test('constraints sharing a child key reuse the first installed index', () => {
    const db = new Database(':memory:')
    try {
        db.exec(`
            CREATE TABLE parents(id INTEGER PRIMARY KEY);
            CREATE TABLE child(parent_id INTEGER,
                FOREIGN KEY(parent_id) REFERENCES parents(id) ON DELETE CASCADE,
                FOREIGN KEY(parent_id) REFERENCES parents(id) ON DELETE CASCADE);
        `)
        assert.equal(findMissingCascadeDeleteIndexes(db).length, 2)
        assert.equal(ensureCascadeDeleteIndexes(db), 1)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db), [])
    } finally { db.close() }
})

test('rowid-alias primary keys are supported without redundant indexes', () => {
    const db = new Database(':memory:')
    try {
        db.exec(`
            CREATE TABLE accounts(id INTEGER PRIMARY KEY);
            CREATE TABLE credentials(account_id INTEGER PRIMARY KEY REFERENCES accounts(id) ON DELETE CASCADE);
            CREATE TABLE descending(account_id INTEGER PRIMARY KEY DESC REFERENCES accounts(id) ON DELETE CASCADE);
            CREATE TABLE ordinary(account_id INTEGER REFERENCES accounts(id) ON DELETE CASCADE);
        `)
        assert.equal(db.prepare('PRAGMA index_list(credentials)').all().length, 0)
        assert.ok(db.prepare('PRAGMA index_list(descending)').all().some(index => index.origin === 'pk'))
        assert.match(db.prepare('EXPLAIN QUERY PLAN SELECT rowid FROM credentials WHERE account_id=?').get(1).detail, /USING INTEGER PRIMARY KEY/)
        assert.match(db.prepare('EXPLAIN QUERY PLAN SELECT rowid FROM descending WHERE account_id=?').get(1).detail, /USING COVERING INDEX/)
        assert.match(db.prepare('EXPLAIN QUERY PLAN SELECT rowid FROM ordinary WHERE account_id=?').get(1).detail, /SCAN ordinary/)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db).map(index => index.table), ['ordinary'])
        assert.equal(ensureCascadeDeleteIndexes(db), 1)
        assert.equal(db.prepare('PRAGMA index_list(credentials)').all().length, 0)
        assert.deepEqual(findMissingCascadeDeleteIndexes(db), [])
    } finally { db.close() }
})

test('login schema indexes new tables but leaves existing tables for offline maintenance', () => {
    // Resolve domain imports without letting their lazy database opener create
    // a disk database. All initialization below is routed to :memory: fixtures.
    const previousDataDir = process.env.DATA_DIR
    process.env.DATA_DIR = require('node:os').tmpdir()
    let setDbOverride
    try { ({ setDbOverride } = require('../src/data/db')) }
    finally {
        if (previousDataDir === undefined) delete process.env.DATA_DIR
        else process.env.DATA_DIR = previousDataDir
    }
    const { initializePlayerLogin } = require('../src/lib/player-login')
    const fresh = new Database(':memory:')
    const existing = new Database(':memory:')
    const accountIndexes = ['idx_gameplay_login_sessions_account', 'idx_player_login_codes_account', 'idx_player_login_claims_account']
    try {
        fresh.exec('CREATE TABLE accounts(id INTEGER PRIMARY KEY,username TEXT)')
        setDbOverride(fresh)
        initializePlayerLogin()
        assert.deepEqual(findMissingCascadeDeleteIndexes(fresh), [])
        assert.equal(fresh.prepare('PRAGMA index_list(player_login_credentials)').all().length, 0)
        const statements = fresh.prepare("SELECT name,sql FROM sqlite_schema WHERE sql IS NOT NULL ORDER BY type DESC,name").all()
        for (const statement of statements) {
            if (!accountIndexes.includes(statement.name)) existing.exec(statement.sql)
        }
        const before = schema(existing)
        setDbOverride(existing)
        initializePlayerLogin()
        assert.deepEqual(findMissingCascadeDeleteIndexes(existing).map(index => index.table),
            ['gameplay_login_sessions', 'player_login_claims', 'player_login_codes'])
        assert.deepEqual(schema(existing), before, 'normal startup must not build missing indexes on existing tables')
    } finally {
        setDbOverride(null)
        fresh.close()
        existing.close()
    }
})
