'use strict'
// Offline/read-only by default. Capture writes a new candidate, never overwrites a reviewed source.
const fs = require('node:fs'), path = require('node:path')
function main(args = process.argv.slice(2)) {
    let root = path.resolve(__dirname, '..'), output
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--project' && args[i + 1]) root = path.resolve(args[++i])
        else if (args[i] === '--output' && args[i + 1]) output = path.resolve(args[++i])
        else throw Error('Use [--project <repo>] [--output <new-candidate.json>]; omit --output for read-only verification')
    }
    const api = require(path.join(root, 'out/lib/content-resource-source'))
    if (!output) { console.log(JSON.stringify({ verified: true, source: api.readContentResourceSourceSync(root) })); return }
    const relative = path.relative(root, output).replaceAll('\\', '/')
    if (/^(?:\.cdn|config|production|assets\/asset-patch)(?:\/|$)/.test(relative)) throw Error('Do not write candidates into resource or configuration roots')
    const candidate = api.captureContentResourceSourceSync(root)
    fs.writeFileSync(output, JSON.stringify(candidate, null, 2) + '\n', { flag: 'wx' })
    console.log(JSON.stringify({ output, resources: Object.keys(candidate.resources).length, source: candidate.source,
        status: 'candidate_requires_business_review_and_release_plan' }))
}
module.exports = { main }
if (require.main === module) { try { main() } catch (error) { console.error(error.message); process.exitCode = 1 } }
