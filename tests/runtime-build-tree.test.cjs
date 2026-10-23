'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync, spawnSync } = require('node:child_process')
const { test } = require('node:test')
const { buildRuntimeArtifact, resolveBuildInput, buildInputIdentity, sha256 } = require('../tools/build-runtime-artifact.cjs')

const helper = path.resolve(__dirname, '../tools/build-runtime-artifact.cjs')
function fixture(t) {
    const root = fs.mkdtempSync(path.join(os.tmpdir(), 'runtime-tree-test-'))
    t.after(() => fs.rmSync(root, { recursive: true, force: true }))
    const repo = path.join(root, 'repo')
    fs.mkdirSync(repo)
    const git = args => execFileSync('git', args, { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
    const write = (name, bytes) => {
        const filename = path.join(repo, name)
        fs.mkdirSync(path.dirname(filename), { recursive: true })
        fs.writeFileSync(filename, bytes)
    }
    const names = ['src/runtime.ts', 'src/removed.ts', 'package.json', 'package-lock.json', 'tsconfig.json', 'tools/runtime-build-policy.json', 'assets/asset-patch/manifest.json', 'docs/private.json']
    git(['init', '-q'])
    write(names[0], 'export const value = "anchor"\n')
    write(names[1], 'export const removed = true\n')
    write(names[2], '{"name":"anchor"}\n')
    write(names[3], '{"lockfileVersion":3,"name":"anchor-lock"}\n')
    write(names[4], '{"compilerOptions":{"outDir":"out"}}\n')
    write(names[5], '{"schema":1,"output_dir":"out","required_outputs":["out/runtime.js"],"toolchain":{}}\n')
    write(names[6], '{"cdn":"excluded"}\n')
    write(names[7], '{"private":"excluded"}\n')
    git(['add', '--', ...names])
    const anchorTree = git(['write-tree'])
    const source = git(['-c', 'user.name=Runtime Fixture', '-c', 'user.email=runtime-fixture@example.invalid', 'commit-tree', anchorTree, '-m', 'fixture'])
    const options = { repo, source, output: path.join(root, 'output') }
    return { root, repo, git, write, source, anchorTree, options, read: entry => git(['cat-file', 'blob', entry.oid]) }
}

test('explicit tree selects all build inputs from the recipe, preserving the commit anchor', t => {
    const f = fixture(t)
    f.write('src/runtime.ts', 'export const value = "recipe"\n')
    f.write('src/new.ts', 'export const added = true\n')
    f.write('package.json', '{"name":"recipe"}\n')
    f.write('package-lock.json', '{"name":"recipe-lock"}\n')
    f.write('tools/runtime-build-policy.json', '{"schema":999,"recipe":true}\n')
    f.git(['update-index', '--force-remove', '--', 'src/removed.ts'])
    f.git(['add', '--', 'src/runtime.ts', 'src/new.ts', 'package.json', 'package-lock.json', 'tools/runtime-build-policy.json'])
    const sourceTree = f.git(['write-tree'])
    // Neither dirty worktree bytes nor the current index may supplement the tree.
    f.write('src/runtime.ts', 'worktree poison')
    f.write('package-lock.json', 'lock poison')
    f.write('tools/runtime-build-policy.json', 'policy poison')
    f.git(['add', '--', 'src/runtime.ts', 'package-lock.json', 'tools/runtime-build-policy.json'])
    const input = resolveBuildInput({ ...f.options, sourceTree })
    const entries = new Map(input.entries.map(entry => [entry.name, entry]))
    assert.equal(f.read(entries.get('src/runtime.ts')), 'export const value = "recipe"')
    assert.equal(f.read(entries.get('package-lock.json')), '{"name":"recipe-lock"}')
    assert.equal(f.read(entries.get('package.json')), '{"name":"recipe"}')
    assert.equal(f.read(entries.get('tools/runtime-build-policy.json')), '{"schema":999,"recipe":true}')
    assert.equal(entries.has('src/new.ts'), true)
    assert.equal(entries.has('src/removed.ts'), false)
    assert.equal(entries.has('assets/asset-patch/manifest.json'), false)
    assert.equal(entries.has('docs/private.json'), false)
    assert.deepEqual(buildInputIdentity(input), { source_commit: f.source, source_tree: sourceTree })
    // Exercise the real export path, stopping at policy validation before npm/tsc.
    assert.throws(() => buildRuntimeArtifact({ ...f.options, sourceTree }), /Invalid runtime build policy/)
    assert.deepEqual(fs.readdirSync(f.options.output), [])
    const cli = spawnSync(process.execPath, [helper, '--repo', f.repo, '--source', f.source, '--source-tree', sourceTree, '--output', path.join(f.root, 'cli-output')], { encoding: 'utf8' })
    assert.equal(cli.status, 1)
    assert.match(cli.stderr, /Invalid runtime build policy/)
    assert.equal(cli.stdout, '')
})

test('default commit selection and identity retain the legacy contract', t => {
    const f = fixture(t)
    f.write('src/runtime.ts', 'dirty/staged poison')
    f.git(['add', '--', 'src/runtime.ts'])
    const input = resolveBuildInput(f.options)
    assert.equal(input.sourceTree, null)
    assert.equal(f.read(input.entries.find(entry => entry.name === 'src/runtime.ts')), 'export const value = "anchor"')
    assert.deepEqual(buildInputIdentity(input), { source_commit: f.source })
    // An explicitly selected anchor tree still declares its distinct identity.
    assert.deepEqual(buildInputIdentity(resolveBuildInput({ ...f.options, sourceTree: f.anchorTree })), { source_commit: f.source, source_tree: f.anchorTree })
})

test('index and worktree identities remain byte-compatible when no tree is supplied', t => {
    const f = fixture(t)
    for (const inputMode of ['index', 'worktree']) {
        const input = resolveBuildInput({ ...f.options, inputMode })
        const expected = `${inputMode}:${sha256(Buffer.from(input.entries.map(e => `${e.name}\0${e.oid || sha256(fs.readFileSync(path.join(f.repo, e.name)))}`).sort().join('\n')))}`
        assert.deepEqual(buildInputIdentity(input, f.repo), { source_commit: expected })
    }
})

test('tree override rejects non-commit modes, abbreviated IDs, refs and expressions', t => {
    const f = fixture(t)
    for (const inputMode of ['index', 'worktree']) {
        assert.throws(() => buildRuntimeArtifact({ ...f.options, inputMode, sourceTree: f.anchorTree }), /only supported in commit input mode/)
    }
    for (const sourceTree of ['', null, 42, f.anchorTree.slice(0, 12), 'HEAD', `${f.source}^{tree}`, 'a'.repeat(41), 'a'.repeat(63)]) {
        assert.throws(() => buildRuntimeArtifact({ ...f.options, sourceTree }), /requires a full Git tree object ID/)
    }
    assert.equal(fs.existsSync(f.options.output), false)
})

test('full IDs must exist and identify trees rather than commits or blobs', t => {
    const f = fixture(t)
    const blob = f.git(['rev-parse', `${f.source}:src/runtime.ts`])
    for (const sourceTree of [f.source, blob]) {
        assert.throws(() => buildRuntimeArtifact({ ...f.options, sourceTree }), /must identify a Git tree object/)
    }
    assert.throws(() => buildRuntimeArtifact({ ...f.options, sourceTree: '0'.repeat(f.anchorTree.length) }), /cat-file/)
    assert.throws(() => buildRuntimeArtifact({ ...f.options, source: '0'.repeat(f.source.length), sourceTree: f.anchorTree }), /rev-parse/)
    assert.equal(fs.existsSync(f.options.output), false)
})

test('CLI reports invalid or missing tree arguments without creating outputs', t => {
    const f = fixture(t)
    for (const extra of [['--source-tree', f.source], ['--source-tree', 'HEAD'], ['--source-tree']]) {
        const cli = spawnSync(process.execPath, [helper, '--repo', f.repo, '--source', f.source, '--output', f.options.output, ...extra], { encoding: 'utf8' })
        assert.equal(cli.status, 1)
        assert.match(cli.stderr, /(?:Git tree object|full Git tree object ID|incomplete argument)/)
        assert.equal(cli.stdout, '')
    }
    assert.equal(fs.existsSync(f.options.output), false)
})
