#!/usr/bin/env node
'use strict'

// The commit guard builds the actual index, not local src/ or historical out/.
// --worktree is explicitly a development check and is not commit evidence.
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const { buildRuntimeArtifact, selected } = require('./build-runtime-artifact.cjs')

function affectedComponents(paths, all = false) {
    if (all) return ['server', 'admin']
    const components = new Set()
    for (const name of paths) {
        if (['tools/runtime-build-policy.json', 'tools/build-runtime-artifact.cjs', 'tools/check-out-artifacts.cjs'].includes(name)) {
            components.add('server'); components.add('admin')
        } else if (selected(name)) components.add(name.startsWith('admin/') ? 'admin' : 'server')
    }
    return ['server', 'admin'].filter(name => components.has(name))
}

function checkOutArtifacts(options = {}) {
    const repo = path.resolve(options.repo || path.join(__dirname, '..'))
    const git = args => execFileSync('git', args, { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] })
    const mode = options.worktree ? 'worktree' : 'index'
    let base = 'HEAD'
    if (Object.prototype.hasOwnProperty.call(options, 'base')) {
        if (typeof options.base !== 'string' || !options.base.length || options.base.trim() !== options.base)
            throw new Error('Invalid --base: expected a nonempty ancestor commit')
        try {
            base = git(['rev-parse', '--verify', `${options.base}^{commit}`]).trim()
            git(['merge-base', '--is-ancestor', base, 'HEAD'])
        } catch { throw new Error('Invalid --base: expected an existing ancestor commit of HEAD') }
    }
    const changed = git(['diff', ...(options.worktree ? [base] : ['--cached', base]), '--name-only', '-z', '--']).split('\0').filter(Boolean)
    const trackedOut = git(['ls-files', '-z', '--', 'out/']).split('\0').filter(Boolean)
    if (trackedOut.length) throw new Error('Source-only runtime policy prohibits tracked out/ files; remove all generated out/ entries from the index')
    const components = affectedComponents(changed, options.all)
    if (!components.length) return { mode, skipped: true, components }
    const output = fs.mkdtempSync(path.join(os.tmpdir(), 'runtime-index-check-'))
    try {
        const artifact = buildRuntimeArtifact({ repo, inputMode: mode, output, dependencyRoot: options.dependencyRoot, components })
        return { mode, skipped: false, ...artifact }
    } finally { fs.rmSync(output, { recursive: true, force: true }) }
}
function main(argv = process.argv.slice(2)) {
    const options = {}
    for (let i = 0; i < argv.length; i++) {
        if (argv[i] === '--worktree') options.worktree = true
        else if (argv[i] === '--all') options.all = true
        else if (argv[i] === '--repo' && argv[i + 1]) options.repo = argv[++i]
        else if (argv[i] === '--dependency-root' && argv[i + 1]) options.dependencyRoot = argv[++i]
        else if (argv[i] === '--base' && argv[i + 1]) options.base = argv[++i]
        else if (argv[i] === '--help' || argv[i] === '-h') { console.log('Usage: node tools/check-out-artifacts.cjs [--base ANCESTOR_COMMIT] [--worktree] [--all] [--repo REPO] [--dependency-root LOCKED_INSTALL_DIR]\nDefault: build only affected server/admin inputs from the index. --base includes earlier functional commits in this task; --all explicitly builds both components. --worktree is development evidence only.'); return }
        else throw new Error(`Unknown or incomplete argument: ${argv[i]}`)
    }
    const result = checkOutArtifacts(options)
    console.log(`[runtime check] ${result.mode}${options.worktree ? ' (development only)' : ' (staged inputs)'}: ${result.skipped ? 'no affected build inputs' : `${result.components.join('+')}; ${result.files.length} emitted files; passed`}`)
}
module.exports = { checkOutArtifacts, affectedComponents }
if (require.main === module) { try { main() } catch (error) { console.error(`[runtime check] ${error.message}`); process.exitCode = 1 } }
