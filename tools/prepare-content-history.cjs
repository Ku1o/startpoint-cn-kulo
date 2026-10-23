'use strict'
// Explicit offline entry. It neither initializes a server nor obtains a default database.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const Sqlite = require('better-sqlite3')
const args = process.argv.slice(2)
function value(name) {
    const index = args.indexOf('--' + name)
    if (index < 0 || !args[index + 1] || args[index + 1].startsWith('--')) throw Error('Missing --' + name)
    return args[index + 1]
}
async function main() {
    const database = fs.realpathSync(value('database')), allowedRoot = fs.realpathSync(value('allowed-root'))
    const planPath = fs.realpathSync(value('plan')), plan = JSON.parse(fs.readFileSync(planPath, 'utf8'))
    const expectedRevision = Number(value('expected-revision')), expectedCatalog = value('expected-catalog')
    if (!Number.isSafeInteger(expectedRevision) || expectedRevision < 0) throw Error('Invalid expected revision')
    const { createContentOperationsStore } = require('../out/lib/content-operations')
    const { prepareReviewedHistoryOfflineSync, rebindReviewedContentIdentitiesOfflineSync, completeExistingHistoryReviewsOfflineSync } = require('../out/lib/content-history-bootstrap')
    const { assertTimeCutoverOfflineDatabaseSync } = require('../out/lib/time-cutover-rehearsal')
    const db = new Sqlite(database, { fileMustExist: true })
    try {
        const offlineGuard = { kind: 'approved-offline-file', databasePath: database, allowedRoot,
            protectedRoots: args.includes('--protect-root') ? [fs.realpathSync(value('protect-root'))] : [] }
        assertTimeCutoverOfflineDatabaseSync(db, offlineGuard)
        const store = createContentOperationsStore(db)
        if (store.digest !== expectedCatalog || plan.catalogDigest !== expectedCatalog || store.revision() !== expectedRevision)
            throw Error('Revision/catalog mismatch before backup')
        const requestedBackup = path.resolve(value('backup'))
        const backup = path.join(fs.realpathSync(path.dirname(requestedBackup)), path.basename(requestedBackup))
        const relative = path.relative(allowedRoot, backup)
        if (!relative || relative.startsWith('..') || path.isAbsolute(relative) || fs.existsSync(backup))
            throw Error('Backup must be a new path inside the approved offline root')
        const planDigest = crypto.createHash('sha256').update(JSON.stringify(plan)).digest('hex')
        const identityRebind = args.includes('--identity-rebind')
        const reviewCompletion = args.includes('--complete-existing-reviews')
        if (identityRebind && reviewCompletion) throw Error('Choose one explicit preparation mode')
        const mode = identityRebind ? 'reviewed-identity-rebind' : reviewCompletion ? 'existing-native-review-completion' : 'closed-history-preparation'
        if (!args.includes('--apply')) {
            console.log(JSON.stringify({ applied: false, database, backup, planPath, planDigest,
                mode,
                candidateCount: identityRebind ? plan.bindings?.length : reviewCompletion ? plan.upgrades?.length : plan.candidates?.length, revision: store.revision(), catalogDigest: store.digest,
                note: 'Review only. Stop all writers and add --apply for this explicitly isolated database.' }))
            return
        }
        await db.backup(backup)
        const apply = identityRebind ? rebindReviewedContentIdentitiesOfflineSync : reviewCompletion ? completeExistingHistoryReviewsOfflineSync : prepareReviewedHistoryOfflineSync
        const result = apply(store, plan, { expectedRevision, nowMs: Date.now(), offlineGuard })
        console.log(JSON.stringify({ ...result, database, backup, planPath }))
    } finally { db.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
