'use strict'
// Read-only explicit target preview; application uses the existing stopped-service maintenance CLI.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const Sqlite = require('better-sqlite3')
const { withReadOnlyContentContext } = require('./prepare-content-release.cjs')
const sha = value => crypto.createHash('sha256').update(value).digest('hex')
function main(args = process.argv.slice(2)) {
    const options = {}, allowed = new Set(['database', 'output', 'evidence', 'previous-source'])
    while (args.length) {
        const key = args.shift().replace(/^--/, '')
        if (!allowed.has(key) || options[key] !== undefined || !args[0] || args[0].startsWith('--')) throw Error('Invalid preview argument')
        options[key] = args.shift()
    }
    if (![...allowed].every(key => options[key])) throw Error('Use --database <physical-file> --output <new-plan> --evidence <review-sha256> --previous-source <fixed-old-root>')
    const root = path.resolve(__dirname, '..'), database = fs.realpathSync(options.database), output = path.resolve(options.output)
    const same = (a, b) => process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b
    if (!same(database, path.resolve(options.database)) || fs.statSync(database).nlink !== 1
        || /(^|[\\/])(\.cdn|config)([\\/]|$)/i.test(database) || same(database, output)
        || /\.(?:db|sqlite|sqlite3)(?:-(?:wal|shm))?$/i.test(output)
        || /(^|[\\/])(\.cdn|config)([\\/]|$)/i.test(output) || fs.existsSync(output) || fs.existsSync(output + '.summary.json')) throw Error('Use safe physical input and new private plan outputs')
    const producer = require('./content-release-capture.cjs'), capture = producer.createReleaseCaptureSession({ previousSource: options['previous-source'], currentSource: root })
    const modulePath = path.join(root, 'out/lib/content-gacha-revision.js'), api = require(modulePath)
    const db = new Sqlite(database, { readonly: true, fileMustExist: true })
    try {
        db.pragma('query_only=ON')
        const plan = db.transaction(() => withReadOnlyContentContext(root, () => api.buildGachaRevisionPlanSync(require('../out/lib/content-operations').createContentOperationsStore(db), options.evidence, capture)))()
        const envelope = { format: 1, kind: 'reviewed-gacha-business-revision', targetDatabase: database,
            captureProducerSha256: producer.PRODUCER_SHA256, previousSource: capture.previousSourceRoot,
            sourceModuleSha256: sha(fs.readFileSync(modulePath)), plan }
        const bytes = JSON.stringify(envelope) + '\n'
        if (Buffer.byteLength(bytes) > 40 * 1024 * 1024) throw Error('Target plan exceeds 40 MiB; no plan written')
        fs.writeFileSync(output, bytes, { flag: 'wx' })
        const summary = { applied: false, revisionId: plan.revisionId, planDigest: plan.digest, source: plan.source,
            catalogDigest: plan.catalogDigest, existingControls: plan.existingKeys.length, identityBindings: plan.bindings.length,
            expectedRevision: plan.expectedRevision, output, note: 'Only identity bindings change. Existing publication, review, deadlines and all player progress remain authoritative.' }
        fs.writeFileSync(output + '.summary.json', JSON.stringify(summary, null, 2) + '\n', { flag: 'wx' })
        console.log(JSON.stringify(summary)); return envelope
    } finally { db.close() }
}
module.exports = { main }
if (require.main === module) try { main() } catch (error) { console.error(error.message); process.exitCode = 1 }
