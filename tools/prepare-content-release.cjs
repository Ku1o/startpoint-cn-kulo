'use strict'
// Read-only target preview. Application belongs to the stopped-service CLI.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const Module = require('node:module')
const Sqlite = require('better-sqlite3')
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex')
/** Scope the existing domain import, not the global database implementation.
 * Some default-data initializers mkdir on import even without getDb(). */
function withReadOnlyContentContext(root, callback) {
    const dbModule = path.join(root, 'out/data/db.js'), initializer = path.join(root, 'out/data/index.js')
    if (require.cache[dbModule] || require.cache[initializer]) throw Error('Read-only preview requires a fresh context without default database modules')
    const originalLoad = Module._load, blocked = () => { throw Error('Default database access is forbidden in a read-only release preview') }
    const facade = Object.freeze({ getDb: blocked, setDbOverride: blocked })
    Module._load = function (request, parent, isMain) {
        const resolved = Module._resolveFilename(request, parent, isMain)
        if (resolved === dbModule) return facade
        if (resolved === initializer) throw Error('Default database initializer import is forbidden in a read-only release preview')
        return originalLoad.call(this, request, parent, isMain)
    }
    try {
        const result = callback()
        if (result && typeof result.then === 'function') throw Error('Read-only release preview context must be synchronous')
        return result
    } finally { Module._load = originalLoad }
}
function main(args) {
    const options = {}, supported = new Set(['database', 'output', 'evidence', 'previous-source'])
    while (args.length) {
        const key = args.shift().replace(/^--/, '')
        if (!supported.has(key) || options[key] !== undefined || !args[0] || args[0].startsWith('--')) throw Error('Invalid or repeated preview argument')
        options[key] = args.shift()
    }
    if (!['database', 'output', 'evidence'].every(key => options[key]))
        throw Error('Usage: node tools/prepare-content-release.cjs --database <explicit-file> --output <new-local-plan.json> --evidence <review-sha256> [--previous-source <pinned-old-source-root>]')
    const database = fs.realpathSync(options.database), requested = path.resolve(options.database)
    const equal = (a, b) => process.platform === 'win32' ? a.toLowerCase() === b.toLowerCase() : a === b
    if (!equal(database, requested) || fs.statSync(database).nlink !== 1 || /(^|[\\/])(\.cdn|config)([\\/]|$)/i.test(database))
        throw Error('Use a physical, unaliased explicit database outside CDN/config')
    const output = path.resolve(options.output)
    if (equal(output, database) || /\.(db|sqlite|sqlite3)(-(wal|shm))?$/i.test(output)
        || /(^|[\\/])(\.cdn|config)([\\/]|$)/i.test(output)) throw Error('Unsafe plan output path')
    const modulePath = path.resolve(__dirname, '../out/lib/content-release-supplement.js')
    const { buildContentReleasePlanSync } = require(modulePath)
    const producer = require('./content-release-capture.cjs')
    const capture = options['previous-source'] ? producer.createReleaseCaptureSession({
        previousSource: options['previous-source'], currentSource: path.resolve(__dirname, '..') }) : undefined
    const db = new Sqlite(database, { readonly: true, fileMustExist: true })
    try {
        db.pragma('query_only=ON')
        const plan = withReadOnlyContentContext(path.resolve(__dirname, '..'), () => {
            const { createContentOperationsStore } = require('../out/lib/content-operations')
            return buildContentReleasePlanSync(createContentOperationsStore(db), options.evidence, capture)
        })
        const envelope = { format: 1, kind: 'reviewed-content-release-supplement', targetDatabase: database,
            captureProducerSha256: producer.PRODUCER_SHA256, previousSource: capture?.previousSourceRoot,
            sourceModuleSha256: sha(fs.readFileSync(modulePath)), plan }
        fs.writeFileSync(output, JSON.stringify(envelope, null, 2) + '\n', { flag: 'wx' })
        console.log(JSON.stringify({ applied: false, planDigest: plan.digest, catalogDigest: plan.catalogDigest,
            source: plan.source, newControls: plan.createKeys.length, preservedControls: plan.preservedKeys.length,
            preservedKeys: plan.preservedKeys, preservedSettings: plan.preservedControls,
            identityBindings: plan.bindings.length, output,
            note: 'Local target-specific review material. Existing closes/deadlines remain authoritative; application does not promise all content is open. No database writes.' }))
        return envelope
    } finally { db.close() }
}
module.exports = { main, withReadOnlyContentContext }
if (require.main === module) { try { main(process.argv.slice(2)) } catch (error) {
    console.error(JSON.stringify({ error: error.message, pendingIdentityReviews: error.pendingIdentityReviews || [] }))
    process.exitCode = 1
} }
