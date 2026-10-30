'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), os = require('node:os'), path = require('node:path')
const { createHash, randomUUID } = require('node:crypto')
const { spawnSync } = require('node:child_process')
const out = process.env.STARPOINT_TEST_OUT_DIR
if (!out) throw new Error('Use STARPOINT_TEST_OUT_DIR for the current combined build')
const load = name => require(path.join(out, name))

test('production cleanup and real backup workers preserve surviving water Gerald entitlements in the fully initialized schema', { timeout: 30000 }, async () => {
    const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'production-cleanup-water-'))
    Object.assign(process.env, { DATA_DIR: directory, ADMIN_PANEL_PASSWORD: 'production-cleanup-water-fixture',
        CN_WRITER_THREAD: '0', MULTI_REALTIME_PROCESS: '0', MULTI_REALTIME_OWNER_CHILD: '0',
        MULTI_BATTLE_RELAY_PROCESS: '0', GAME_ROUTINE_LOGS: 'off', GAME_VERBOSE_LOGS: 'false',
        GACHA_SEED_DIR: path.join(directory, 'seeds') })
    fs.mkdirSync(process.env.GACHA_SEED_DIR)
    let app, db, backup
    try {
        db = load('data/db').getDb()
        assert.equal(path.dirname(fs.realpathSync(db.name)), fs.realpathSync(directory))
        const accounts = load('data/domains/account'), players = load('data/domains/player')
        const characters = load('data/domains/character'), claims = load('data/domains/water-gerald-claim')
        const initializer = load('data/initializers/water-gerald-claim').initializeWaterGeraldClaim
        const cleanup = load('lib/admin-account-cleanup'), active = load('data/activeAccount')
        const snapshots = load('data/snapshots/player-snapshot')
        load('lib/player-login').initializePlayerLogin()
        function account(note) {
            const a = accounts.insertAccountSync({ appId: 'wf_cn', idpAlias: '', idpCode: 'production-cleanup-water',
                idpId: randomUUID(), status: 'normal' })
            accounts.updateAccountSync({ id: a.id, adminNote: note })
            return a
        }
        function claimedPlayer(a) {
            const p = players.insertDefaultPlayerSync(a.id)
            const reward = load('lib/quest/finish/water-gerald-reward').grantWaterGeraldEx30Sync({ playerId: p.id,
                questCategory: 24, questId: 700100030, questAccomplished: true,
                questData: { rushEventId: 700100, rushEventFolderId: 1, rushEventRound: 30 } })
            assert.ok(reward.character_list.some(row => row.character_id === 129989))
            assert.equal(claims.getWaterGeraldClaimsSync(p.id).length, 1)
            return p
        }
        const removedAccount = account(' \t\u3000 '), retainedAccount = account('保留其水杰角色与永久领取权益')
        const removedPlayers = [claimedPlayer(removedAccount), claimedPlayer(removedAccount)]
        const retained = claimedPlayer(retainedAccount)
        active.saveAccountDefaultPlayer(removedAccount.id, removedPlayers[0].id)
        active.saveAccountDefaultPlayer(retainedAccount.id, retained.id)
        active.setSelectedAccountId(retainedAccount.id); active.setActivePlayerId(retained.id)
        characters.updatePlayerCharacterSync(retained.id, 129989, { exp: 1234, evolutionLevel: 1, overLimitStep: 2, stack: 3 })
        characters.insertPlayerCharacterManaNodesSync(retained.id, 129989, [259978201])
        characters.updatePlayerCharacterManaNodeAwakeLevelSync(retained.id, 129989, 259978201, 1)
        const retainedBefore = snapshots.createPlayerSaveSnapshotV2Sync(retained.id).data.tables
        const claimsBefore = db.prepare('SELECT * FROM players_water_gerald_claims ORDER BY player_id').all()
        const schema = () => db.prepare('SELECT type,name,tbl_name,sql FROM sqlite_schema ORDER BY type,name').all()
        const originalSchema = schema(), schemaVersion = db.pragma('schema_version', { simple: true })
        assert.deepEqual(cleanup.findMissingCascadeDeleteIndexes(db), [], 'full initialized schema must pass real cleanup admission')
        assert.deepEqual(schema(), originalSchema, 'online preflight is read-only')
        assert.equal(db.prepare('PRAGMA index_list(players_water_gerald_claims)').all().length, 0,
            'claim INTEGER PRIMARY KEY supports cleanup without a redundant index')
        assert.equal(cleanup.ensureCascadeDeleteIndexes(db), 0, 'new database initialization already supplied all needed indexes')
        initializer(db); initializer(db)
        assert.deepEqual(schema(), originalSchema); assert.equal(db.pragma('schema_version', { simple: true }), schemaVersion)
        assert.deepEqual(db.prepare('SELECT * FROM players_water_gerald_claims ORDER BY player_id').all(), claimsBefore)
        assert.throws(() => db.prepare('INSERT INTO players_water_gerald_claims(player_id,claimed_at) VALUES(?,?)')
            .run(retained.id, Date.now()), /UNIQUE constraint failed/)
        assert.throws(() => db.prepare('INSERT INTO players_water_gerald_claims(player_id,claimed_at) VALUES(?,?)')
            .run(999999999, Date.now()), /FOREIGN KEY constraint failed/)

        app = require('fastify')({ logger: false })
        load('lib/management-auth').installManagementAuth(app)
        await app.register(load('routes/web_api/server').default, { prefix: '/api/server' })
        await app.ready()
        const login = await app.inject({ method: 'POST', url: '/admin-login', payload: { password: process.env.ADMIN_PANEL_PASSWORD } })
        assert.equal(login.statusCode, 200, login.body)
        const headers = { cookie: login.headers['set-cookie'].split(';')[0] }
        const started = await app.inject({ method: 'POST', url: '/api/server/deleteUnnotedAccounts', headers,
            payload: { confirm: 'DELETE_UNNOTED_ACCOUNTS' } })
        assert.equal(started.statusCode, 202, started.body)
        let job = started.json()
        const deadline = Date.now() + 20000
        while (job.status === 'running' && Date.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 20))
            const response = await app.inject({ url: '/api/server/deleteUnnotedAccounts/status', headers })
            assert.equal(response.statusCode, 200, response.body)
            job = response.json()
        }
        assert.equal(job.status, 'completed', JSON.stringify(job))
        assert.equal(job.totalAccounts, 1); assert.equal(job.deletedAccounts, 1); assert.equal(job.deletedSaves, 2)
        assert.equal(job.createdIndexes, 0, 'actual cleanup must not create indexes')
        assert.equal(job.remainingAccounts, 0)
        assert.equal(db.prepare('SELECT id FROM accounts WHERE id=?').get(removedAccount.id), undefined)
        for (const p of removedPlayers) {
            assert.equal(db.prepare('SELECT id FROM players WHERE id=?').get(p.id), undefined)
            assert.deepEqual(claims.getWaterGeraldClaimsSync(p.id), [])
            assert.equal(characters.getPlayerCharacterSync(p.id, 129989), null)
        }
        assert.ok(db.prepare('SELECT id FROM accounts WHERE id=?').get(retainedAccount.id))
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(retained.id).data.tables, retainedBefore,
            'noted account retains exact inventory, claim, character, evolution, breakthrough, stack and mana nodes')
        assert.deepEqual(db.prepare('SELECT * FROM players_water_gerald_claims ORDER BY player_id').all(),
            claimsBefore.filter(row => row.player_id === retained.id))
        assert.equal(load('lib/quest/finish/water-gerald-reward').grantWaterGeraldEx30Sync({ playerId: retained.id,
            questCategory: 24, questId: 700100030, questAccomplished: true,
            questData: { rushEventId: 700100, rushEventFolderId: 1, rushEventRound: 30 } }), null)
        assert.deepEqual(schema(), originalSchema); assert.equal(db.pragma('schema_version', { simple: true }), schemaVersion)
        assert.equal(db.pragma('integrity_check', { simple: true }), 'ok'); assert.deepEqual(db.pragma('foreign_key_check'), [])

        const backupDirectory = path.resolve(directory, 'admin-backups', path.basename(job.backup.replaceAll('\\', '/')))
        assert.equal(path.dirname(backupDirectory), path.join(directory, 'admin-backups'))
        const info = JSON.parse(fs.readFileSync(path.join(backupDirectory, 'backup-info.json'), 'utf8'))
        assert.equal(info.status, 'completed'); assert.equal(info.verification.snapshot, true)
        assert.equal(info.verification.quickCheck, 'ok'); assert.equal(info.verification.sidecarValidated, true)
        assert.ok(info.verification.snapshotPinnedAt)
        assert.ok(fs.existsSync(path.join(backupDirectory, 'wdfp_data.db.version')))
        backup = new (require('better-sqlite3'))(path.join(backupDirectory, 'wdfp_data.db'), { readonly: true, fileMustExist: true })
        assert.deepEqual(backup.prepare('SELECT * FROM players_water_gerald_claims ORDER BY player_id').all(), claimsBefore,
            'real pinned backup retains both deleted and surviving entitlements')
        assert.equal(backup.prepare('SELECT COUNT(*) n FROM players_characters WHERE id=129989').get().n, 3)
        assert.deepEqual(backup.prepare('SELECT id FROM accounts ORDER BY id').all(),
            [{ id: removedAccount.id }, { id: retainedAccount.id }])
        const backedUpCharacters = backup.prepare('SELECT * FROM players_characters WHERE id=129989 ORDER BY player_id').all()
        assert.deepEqual(backup.pragma('foreign_key_check'), []); backup.close(); backup = null
        // Reopen a copy through actual application initialization, not just a
        // readonly SQLite inspection. Keep the completed backup untouched.
        const restoredDirectory = path.join(directory, 'restored-full-backup')
        fs.mkdirSync(restoredDirectory); fs.mkdirSync(path.join(restoredDirectory, 'seeds'))
        const restoredFiles = ['wdfp_data.db', 'wdfp_data.db.version', 'active_account.json']
            .filter(name => fs.existsSync(path.join(backupDirectory, name)))
        assert.ok(restoredFiles.includes('wdfp_data.db.version'))
        const digest = name => createHash('sha256').update(fs.readFileSync(path.join(backupDirectory, name))).digest('hex')
        const originalBackupDigests = Object.fromEntries(restoredFiles.map(name => [name, digest(name)]))
        for (const name of restoredFiles) fs.copyFileSync(path.join(backupDirectory, name), path.join(restoredDirectory, name))
        const reopened = spawnSync(process.execPath, ['-e', `
            const assert=require('node:assert/strict'),path=require('node:path');
            const out=${JSON.stringify(path.resolve(out))};
            const load=name=>require(path.join(out,name));
            const db=load('data/db').getDb();
            assert.equal(path.resolve(db.name),path.join(process.env.DATA_DIR,'wdfp_data.db'));
            assert.deepEqual(db.prepare('SELECT * FROM players_water_gerald_claims ORDER BY player_id').all(),${JSON.stringify(claimsBefore)});
            assert.deepEqual(db.prepare('SELECT * FROM players_characters WHERE id=129989 ORDER BY player_id').all(),${JSON.stringify(backedUpCharacters)});
            const claims=load('data/domains/water-gerald-claim');
            const grant=load('lib/quest/finish/water-gerald-reward').grantWaterGeraldEx30Sync;
            for(const playerId of ${JSON.stringify(claimsBefore.map(row => row.player_id))}) {
                assert.equal(claims.getWaterGeraldClaimsSync(playerId).length,1);
                assert.equal(grant({playerId,questCategory:24,questId:700100030,questAccomplished:true,
                    questData:{rushEventId:700100,rushEventFolderId:1,rushEventRound:30}}),null);
            }
            assert.deepEqual(db.prepare('SELECT * FROM players_characters WHERE id=129989 ORDER BY player_id').all(),${JSON.stringify(backedUpCharacters)});
            assert.deepEqual(db.pragma('foreign_key_check'),[]);
            load('lib/seed-validator').default.close().then(()=>{db.close();console.log('RESTORED_WATER_CLAIMS_CANNOT_REGRANT');})
                .catch(error=>{console.error(error);process.exitCode=1;});
        `], { cwd: path.resolve(__dirname, '..'), env: { ...process.env, DATA_DIR: restoredDirectory,
            GACHA_SEED_DIR: path.join(restoredDirectory, 'seeds') }, encoding: 'utf8', timeout: 20000, windowsHide: true })
        assert.equal(reopened.error, undefined)
        assert.equal(reopened.status, 0, reopened.stderr + reopened.stdout)
        assert.match(reopened.stdout, /RESTORED_WATER_CLAIMS_CANNOT_REGRANT/)
        assert.deepEqual(Object.fromEntries(restoredFiles.map(name => [name, digest(name)])), originalBackupDigests,
            'application initialization and duplicate-reward checks never mutate the retained completed backup')
        const result = JSON.parse(fs.readFileSync(path.join(backupDirectory, 'cleanup-result.json'), 'utf8'))
        assert.deepEqual(result.deletedAccountIds, [removedAccount.id])
        assert.deepEqual(result.deletedPlayerIds.sort((a, b) => a - b), removedPlayers.map(p => p.id).sort((a, b) => a - b))
        const empty = await app.inject({ method: 'POST', url: '/api/server/deleteUnnotedAccounts', headers,
            payload: { confirm: 'DELETE_UNNOTED_ACCOUNTS' } })
        assert.equal(empty.statusCode, 200, empty.body); assert.equal(empty.json().deletedAccounts, 0)
        assert.equal(empty.json().backup, null); assert.ok(fs.existsSync(path.join(backupDirectory, 'wdfp_data.db')))
        initializer(db)
        assert.deepEqual(snapshots.createPlayerSaveSnapshotV2Sync(retained.id).data.tables, retainedBefore)
    } finally {
        if (backup?.open) backup.close()
        if (app) await app.close()
        if (db) {
            await load('multi/npc/player-party-pool').stopQuestNpcPartyPoolWorker()
            await load('lib/admin-database-backup-worker').drainDatabaseBackups()
            await load('lib/seed-validator').default.close()
            if (db.open) db.close()
        }
        assert.equal(path.dirname(fs.realpathSync(directory)), fs.realpathSync(os.tmpdir()))
        assert.ok(path.basename(directory).startsWith('production-cleanup-water-'))
        fs.rmSync(directory, { recursive: true })
    }
})
