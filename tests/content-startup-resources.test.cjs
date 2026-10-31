'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict'), fs = require('node:fs')
const path = require('node:path'), os = require('node:os'), crypto = require('node:crypto'), { spawnSync } = require('node:child_process')
const Sqlite = require('better-sqlite3'), root = path.resolve(__dirname, '..')
const canonical = v => Array.isArray(v) ? '[' + v.map(canonical).join(',') + ']' : v && typeof v === 'object'
    ? '{' + Object.keys(v).sort().map(k => JSON.stringify(k) + ':' + canonical(v[k])).join(',') + '}' : JSON.stringify(v)
const hash = v => crypto.createHash('sha256').update(typeof v === 'string' || Buffer.isBuffer(v) ? v : canonical(v)).digest('hex')

test('current startup verify is read-only and optional admin files cannot block preserved controls and player facts', t => {
    const base = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir()), directory = fs.mkdtempSync(path.join(base, 'content-startup-'))
    t.after(() => { assert.equal(path.dirname(directory), base); fs.rmSync(directory, { recursive: true }) })
    const database = path.join(directory, 'wdfp_data.db'), db = new Sqlite(database)
    const storeApi = require('../out/lib/content-operations-store'), release = require('../out/lib/content-release-supplement')
    storeApi.initializeContentOperationsSchema(db)
    const store = require('../out/lib/content-operations').createContentOperationsStore(db)
    // A synthetic already-migrated current release, never the local player DB.
    const keys = [...new Set([...release.readContentDeploymentRequiredKeysSync(), release.CONTENT_RELEASE_PARENT,
        ...release.CONTENT_RELEASE_PRODUCTS, release.CONTENT_RELEASE_GACHA])].sort()
    const invalid = keys.filter(key => store.runtimeDefinitions.get(key)?.matchesCatalog !== true)
    assert.deepEqual(invalid, [], 'the fixture uses the real current definition environment')
    const write = db.prepare('INSERT INTO content_operations_state VALUES(?,?)')
    db.transaction(() => { for (const key of keys) write.run(key, JSON.stringify({ key, instanceId: key + ':original', controlled: true,
        published: false, readiness: 'verified', evidence: 'isolated already-migrated test fixture',
        flags: { visible: false, enter: false, claim: false, exchange: false }, endsAtMs: 1700000000000,
        revision: 42, catalogDigest: store.digest, contentDigest: store.contentDigests.get(key) })) })()
    db.prepare('UPDATE content_operations_meta SET revision=42').run()
    const tables = ['content_operations_initialization', 'content_operations_deployment', 'content_box_exchange_deployment']
    for (const table of tables) db.exec(`CREATE TABLE ${table}(id INTEGER PRIMARY KEY, fact TEXT); INSERT INTO ${table} VALUES(1,'retained original marker')`)
    const baseline = hash(tables.map(table => [table, db.prepare(`SELECT * FROM ${table} ORDER BY id`).all()]))
    db.exec(`CREATE TABLE content_release_supplements(release_id TEXT PRIMARY KEY,plan_digest TEXT,catalog_digest TEXT,
        applied_revision INTEGER,keys_json TEXT,baseline_sha256 TEXT,source_sha256 TEXT)`)
    db.prepare('INSERT INTO content_release_supplements VALUES(?,?,?,?,?,?,?)').run(release.CONTENT_RELEASE_ID, 'f'.repeat(64),
        store.digest, 42, JSON.stringify(keys), baseline, release.readContentReleaseSourceSync().manifestSha256)
    db.exec(`CREATE TABLE server_clock_state(id INTEGER PRIMARY KEY,version INTEGER,mode TEXT,business_offset_ms INTEGER,
        legacy_battle_offset_ms INTEGER,cutover_real_ms INTEGER,day_anchor_ms INTEGER,week_anchor_ms INTEGER,
        revision INTEGER,readiness TEXT,plan_digest TEXT)`)
    db.prepare('INSERT INTO server_clock_state VALUES(1,1,\'real\',0,0,?,?,?,?,\'maintenance-approved\',?)')
        .run(1793404800000, 1793491200000, 1794009600000, 1, 'e'.repeat(64))
    db.exec("CREATE TABLE retained_player_facts(id INTEGER PRIMARY KEY,balance INTEGER,claimed INTEGER,stock INTEGER); INSERT INTO retained_player_facts VALUES(1,13579,1,17)")
    db.close()
    fs.writeFileSync(database + '.version', String(require('../out/lib/storage-layout').WDFP_DATA_VERSION))
    const before = fs.readFileSync(database), env = { ...process.env, DATA_DIR: directory }
    for (const mode of ['missing', 'corrupt']) {
        const code = `const fs=require('node:fs'),read=fs.readFileSync;
            fs.readFileSync=function(file,...args){
                if(/content_discovery(?:_runtime)?\\.json$|content_presentation\\.json$|content_thumbnails[\\\\/]index\\.json$/.test(String(file))) {
                    if(${JSON.stringify(mode)}==='corrupt')return Buffer.from('{broken');
                    const error=Error('Missing optional admin data');error.code='ENOENT';throw error;
                } return read.call(this,file,...args);
            };
            require('./scripts/time-content-deployment.cjs').main(['verify','--project',process.cwd()])
                .catch(e=>{console.error(e.stack);process.exitCode=1});`
        const result = spawnSync(process.execPath, ['-e', code], { cwd: root, env, encoding: 'utf8' })
        assert.equal(result.status, 0, result.stdout + result.stderr)
        assert.match(result.stdout, /"ready": true/)
        assert.deepEqual(fs.readFileSync(database), before, 'verification cannot change controls, receipts or player progress')
    }
})
