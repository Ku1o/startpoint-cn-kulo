'use strict'
// Explicit offline correction. No default database, server startup or player writes.
const fs = require('node:fs'), path = require('node:path'), { execFileSync } = require('node:child_process')
const Sqlite = require('better-sqlite3')
const args = process.argv.slice(2)
function value(name) {
    const index = args.indexOf('--' + name)
    if (index < 0 || !args[index + 1] || args[index + 1].startsWith('--')) throw Error('Missing --' + name)
    return args[index + 1]
}
function within(root, target) {
    const suffix = path.relative(root, target)
    return suffix !== '' && !path.isAbsolute(suffix) && suffix !== '..' && !suffix.startsWith('..' + path.sep)
}
function offlineTarget() {
    const database = fs.realpathSync(value('database')), allowedRoot = fs.realpathSync(value('allowed-root'))
    if (!within(allowedRoot, database) || fs.statSync(database).nlink !== 1
        || /(^|[\\/])(\.database|\.cdn|config)([\\/]|$)/i.test(database)) throw Error('Database outside approved offline scope')
    const inventory = execFileSync('git', ['-c', 'core.quotePath=false', 'worktree', 'list', '--porcelain'],
        { cwd: path.resolve(__dirname, '..'), encoding: 'utf8', windowsHide: true })
    const roots = inventory.split(/\r?\n/).filter(line => line.startsWith('worktree ')).map(line => fs.realpathSync(line.slice(9)))
    if (!roots.length || roots.some(root => within(root, database))) throw Error('Protected source/worktree database')
    return { database, allowedRoot }
}
function newOutput(filename, root) {
    const requested = path.resolve(filename), parent = fs.realpathSync(path.dirname(requested))
    const target = path.join(parent, path.basename(requested))
    if (!within(root, target) || fs.existsSync(target)) throw Error('Output must be a new file inside the approved offline root')
    return target
}
async function main() {
    const { database, allowedRoot } = offlineTarget(), apply = args.includes('--apply')
    const { createContentOperationsStore } = require('../out/lib/content-operations')
    const { buildReportedContentRepairPlanSync, applyReportedContentRepairOfflineSync } = require('../out/lib/reported-content-repair')
    const db = new Sqlite(database, { readonly: !apply, fileMustExist: true })
    try {
        if (!apply) db.pragma('query_only=ON')
        const store = createContentOperationsStore(db)
        if (!apply) {
            const output = newOutput(value('plan'), allowedRoot), plan = buildReportedContentRepairPlanSync(store, Date.now())
            fs.writeFileSync(output, JSON.stringify(plan, null, 2) + '\n', { flag: 'wx' })
            console.log(JSON.stringify({ applied: false, plan: output, digest: plan.digest, expectedRevision: plan.expectedRevision,
                changedKeys: plan.changes.map(change => change.key), note: 'Offline preview only. No database mutation.' }))
            return
        }
        if (!args.includes('--writers-stopped')) throw Error('Stop every writer before explicit offline apply')
        const plan = JSON.parse(fs.readFileSync(fs.realpathSync(value('plan')), 'utf8'))
        const expectedPlanDigest = value('expected-plan')
        // Validate before spending time on a backup. Apply rechecks after obtaining its write lock.
        if (JSON.stringify(buildReportedContentRepairPlanSync(store, plan.createdAtMs)) !== JSON.stringify(plan)
            || plan.digest !== expectedPlanDigest) throw Error('Plan/state mismatch; preview again')
        const backup = newOutput(value('backup'), allowedRoot)
        await db.backup(backup)
        const result = applyReportedContentRepairOfflineSync(store, plan, { expectedPlanDigest, nowMs: Date.now(),
            offlineGuard: { kind: 'approved-offline-file', databasePath: database, allowedRoot } })
        console.log(JSON.stringify({ ...result, database, backup }))
    } finally { db.close() }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
