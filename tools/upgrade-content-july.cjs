'use strict'
// Explicit offline entry: no default database, server initialization, listener or player writes.
const fs = require('node:fs'), path = require('node:path'), Sqlite = require('better-sqlite3')
const args = process.argv.slice(2), value = name => {
    const index = args.indexOf('--' + name)
    if (index < 0 || !args[index + 1] || args[index + 1].startsWith('--')) throw Error('Missing --' + name)
    return args[index + 1]
}
async function main() {
    const database = fs.realpathSync(value('database')), allowedRoot = fs.realpathSync(value('allowed-root'))
    const expectedRevision = Number(value('expected-revision')), expectedCatalogDigest = value('expected-catalog')
    if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 0) throw Error('Invalid revision')
    const {createContentOperationsStore} = require('../out/lib/content-operations')
    const {upgradeJulyContentPlanOfflineSync} = require('../out/lib/content-operations-bootstrap')
    const {assertTimeCutoverOfflineDatabaseSync} = require('../out/lib/time-cutover-rehearsal')
    const db = new Sqlite(database, {fileMustExist: true})
    try {
        const offlineGuard = {kind: 'approved-offline-file', databasePath: database, allowedRoot,
            protectedRoots: args.includes('--protect-root') ? [fs.realpathSync(value('protect-root'))] : []}
        assertTimeCutoverOfflineDatabaseSync(db, offlineGuard)
        const store = createContentOperationsStore(db)
        if (store.revision() !== expectedRevision || store.digest !== expectedCatalogDigest) throw Error('Revision/catalog mismatch before backup')
        const requestedBackup = path.resolve(value('backup'))
        const backup = path.join(fs.realpathSync(path.dirname(requestedBackup)), path.basename(requestedBackup))
        const relative = path.relative(allowedRoot, backup)
        if (!relative || relative.startsWith('..') || path.isAbsolute(relative) || fs.existsSync(backup)) throw Error('Backup must be a new path inside the approved root')
        if (!args.includes('--apply')) {
            console.log(JSON.stringify({database, revision: store.revision(), catalogDigest: store.digest, backup,
                applied: false, note: 'Review only. Add --apply after stopping every writer to this explicitly isolated database.'}))
            return
        }
        // SQLite backup API includes committed WAL state and leaves the source intact.
        await db.backup(backup)
        const result = upgradeJulyContentPlanOfflineSync(store, {expectedRevision, expectedCatalogDigest, nowMs: Date.now(), offlineGuard})
        console.log(JSON.stringify({...result, database, backup}))
    } finally { db.close() }
}
main().catch(error => {console.error(error); process.exitCode = 1})
