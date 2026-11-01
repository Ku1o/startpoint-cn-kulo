'use strict'

const assert = require('node:assert/strict')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const vm = require('node:vm')
const { createRequire } = require('node:module')
const { execFileSync, spawnSync } = require('node:child_process')
const { test, after } = require('node:test')
const { buildRuntimeArtifact } = require('../tools/build-runtime-artifact.cjs')
const { checkOutArtifacts } = require('../tools/check-out-artifacts.cjs')

const root = fs.mkdtempSync(path.join(os.tmpdir(), 'runtime-build-tests-'))
const repoRoot = path.resolve(__dirname, '..')
const dependencySource = process.env.STARPOINT_TEST_DEPENDENCY_ROOT || repoRoot
const tsSource = path.join(dependencySource, 'node_modules/typescript')
const tsLocked = JSON.parse(fs.readFileSync(path.join(repoRoot, 'package-lock.json'), 'utf8')).packages['node_modules/typescript']
const pkg = { name: 'runtime-fixture', version: '1.0.0', devDependencies: { typescript: tsLocked.version } }
const lock = { name: pkg.name, version: pkg.version, lockfileVersion: 3, requires: true, packages: { '': pkg, 'node_modules/typescript': tsLocked } }
const lockBytes = `${JSON.stringify(lock)}\n`
const dependencyRoot = path.join(root, 'dependencies')
fs.mkdirSync(path.join(dependencyRoot, 'node_modules'), { recursive: true })
fs.cpSync(tsSource, path.join(dependencyRoot, 'node_modules/typescript'), { recursive: true })
fs.writeFileSync(path.join(dependencyRoot, 'package-lock.json'), lockBytes)
fs.writeFileSync(path.join(dependencyRoot, 'node_modules/.package-lock.json'), JSON.stringify({ lockfileVersion: 3, packages: { 'node_modules/typescript': tsLocked } }))
after(() => fs.rmSync(root, { recursive: true, force: true }))

let sequence = 0
function fixture(options = {}) {
    const repo = path.join(root, `repo-${++sequence}`)
    fs.mkdirSync(repo)
    const git = args => execFileSync('git', args, { cwd: repo, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim()
    const write = (name, bytes) => { const filename = path.join(repo, name); fs.mkdirSync(path.dirname(filename), { recursive: true }); fs.writeFileSync(filename, bytes) }
    git(['init', '-q'])
    git(['config', 'user.name', 'Runtime Fixture'])
    git(['config', 'user.email', 'runtime-fixture@example.invalid'])
    write('.gitignore', 'out/\nsrc/hidden.ts\n')
    write('package.json', JSON.stringify(pkg))
    write('package-lock.json', lockBytes)
    write('tsconfig.json', JSON.stringify({ compilerOptions: { target: 'es2020', module: 'commonjs', strict: true, rootDir: 'src', outDir: 'out', resolveJsonModule: true, esModuleInterop: true, incremental: true }, include: ['src/**/*.ts'] }))
    write('tools/runtime-build-policy.json', JSON.stringify({ schema: 1, output_dir: 'out', toolchain: { node: '24.19.0', npm: '11.17.0', typescript: '5.4.5' }, required_outputs: ['out/runtime.js', 'out/worker.js'] }))
    write('src/runtime.ts', 'export const value = 1\n')
    write('src/worker.ts', 'export const worker = true\n')
    const adminNames = options.admin ? ['admin/package.json', 'admin/package-lock.json', 'admin/index.html', 'admin/tsconfig.json', 'admin/vite.config.ts', 'admin/src/main.ts'] : []
    if (options.admin) {
        write(adminNames[0], JSON.stringify({ name: 'admin-fixture', version: '1.0.0', scripts: { build: 'tsc -b && vite build' } }))
        write(adminNames[1], JSON.stringify({ name: 'admin-fixture', lockfileVersion: 3, packages: { '': { name: 'admin-fixture', version: '1.0.0' } } }))
        write(adminNames[2], '<div id="root"></div>\n')
        write(adminNames[3], '{}\n')
        write(adminNames[4], 'export default {}\n')
        write(adminNames[5], 'export const label = "admin-committed"\n')
    }
    git(['add', '.gitignore', 'package.json', 'package-lock.json', 'tsconfig.json', 'tools/runtime-build-policy.json', 'src/runtime.ts', 'src/worker.ts', ...adminNames])
    git(['commit', '-qm', 'fixture'])
    const source = git(['rev-parse', 'HEAD'])
    const output = path.join(root, `output-${sequence}`)
    return { repo, git, write, source, output, build: extra => buildRuntimeArtifact({ repo, source, output, dependencyRoot, ...extra }), check: extra => checkOutArtifacts({ repo, dependencyRoot, ...extra }) }
}

// Observe npm at the existing child-process boundary. Git and the real compiler
// still run normally; no network install or global npm/PATH replacement is used.
function observedTools() {
    const calls = [], cache = new Map()
    function loadTool(name) {
        if (cache.has(name)) return cache.get(name)
        const filename = path.join(repoRoot, 'tools', name), localRequire = createRequire(filename)
        const loaded = { exports: {} }
        const requireTool = id => {
            if (id === './build-runtime-artifact.cjs') return loadTool('build-runtime-artifact.cjs')
            if (id !== 'node:child_process') return localRequire(id)
            return { ...localRequire(id), execFileSync(command, args, options) {
                const nodeNpm = command === process.execPath && /[\\/]npm-cli\.js$/.test(args[0] || '')
                const directNpm = /^npm(?:\.cmd)?$/i.test(path.basename(command))
                if (!nodeNpm && !directNpm) return execFileSync(command, args, options)
                const npmArgs = nodeNpm ? args.slice(1) : args
                if (npmArgs[0] === '--version') return '11.17.0\n'
                const component = path.basename(options.cwd) === 'admin' ? 'admin' : 'server'
                calls.push({ component, args: npmArgs })
                if (component !== 'admin') throw new Error('Unexpected server npm installation/build')
                if (npmArgs[0] === 'ci') return ''
                assert.deepEqual(npmArgs, ['run', 'build'])
                const source = fs.readFileSync(path.join(options.cwd, 'src/main.ts'), 'utf8')
                calls[calls.length - 1].source = source
                if (source.includes('ADMIN_BUILD_FAIL')) throw new Error('Fixture admin compilation failed')
                const dist = path.resolve(options.cwd, '../web/dist')
                fs.mkdirSync(dist, { recursive: true })
                fs.writeFileSync(path.join(dist, 'index.html'), source)
                return ''
            } }
        }
        const wrapper = vm.runInThisContext(`(function(exports, require, module, __filename, __dirname) {\n${fs.readFileSync(filename, 'utf8').replace(/^#![^\n]*\n/, '')}\n})`, { filename })
        wrapper(loaded.exports, requireTool, loaded, filename, path.dirname(filename))
        cache.set(name, loaded.exports)
        return loaded.exports
    }
    return { calls, build: loadTool('build-runtime-artifact.cjs').buildRuntimeArtifact,
        check: loadTool('check-out-artifacts.cjs').checkOutArtifacts }
}

test('fixed commit ignores dirty source and poisoned historical output; CLI emits only identity JSON', () => {
    const f = fixture()
    f.write('src/runtime.ts', 'invalid syntax !\n')
    f.write('out/runtime.js', 'poisoned historical runtime')
    const built = f.build()
    assert.equal(built.source_commit, f.source)
    assert.equal(built.dependency_source, 'trusted-local-install')
    assert.equal(built.root_dir, 'src')
    assert.deepEqual(built.files, ['out/runtime.js', 'out/worker.js'])
    assert.match(fs.readFileSync(path.join(f.output, 'out/runtime.js'), 'utf8'), /value = 1/)
    const cli = spawnSync(process.execPath, [path.join(repoRoot, 'tools/build-runtime-artifact.cjs'), '--repo', f.repo, '--source', f.source, '--output', path.join(root, 'cli-output'), '--dependency-root', dependencyRoot], { encoding: 'utf8' })
    assert.equal(cli.status, 0, cli.stderr)
    assert.equal(JSON.parse(cli.stdout).source_commit, f.source)
})

test('index compilation ignores an unstaged repair of staged invalid code', () => {
    const f = fixture()
    f.write('src/runtime.ts', 'export const value: number = "broken"\n')
    f.git(['add', 'src/runtime.ts'])
    f.write('src/runtime.ts', 'export const value = 2\n')
    assert.throws(() => f.check(), /TS2322/)
    assert.equal(f.check({ worktree: true }).mode, 'worktree')
})

test('index compilation ignores an unstaged broken edit of valid staged code', () => {
    const f = fixture()
    f.write('src/runtime.ts', 'export const value = 2\n')
    f.git(['add', 'src/runtime.ts'])
    f.write('src/runtime.ts', 'export const value: number = "broken"\n')
    assert.equal(f.check().skipped, false)
})

test('ignored and untracked dependencies cannot make a staged import pass', () => {
    const f = fixture()
    f.write('src/hidden.ts', 'export const hidden = 1\n')
    f.write('src/runtime.ts', 'import { hidden } from "./hidden"; export const value = hidden\n')
    f.git(['add', 'src/runtime.ts'])
    assert.throws(() => f.check(), /TS2307/)
    f.write('src/new.ts', 'export const fresh = 1\n')
    f.write('src/runtime.ts', 'import { fresh } from "./new"; export const value = fresh\n')
    f.git(['add', 'src/runtime.ts'])
    assert.throws(() => f.check(), /TS2307/)
    f.git(['add', 'src/new.ts'])
    assert.equal(f.check().files.includes('out/new.js'), true)
})

test('type declarations require no matching JS; JSON is inventoried from actual emit', () => {
    const f = fixture()
    f.write('src/types.d.ts', 'interface OnlyType { value: number }\n')
    f.write('src/payload.json', '{"value":3}\n')
    f.write('src/runtime.ts', 'import payload from "./payload.json"; export const value = payload.value\n')
    f.git(['add', 'src/types.d.ts', 'src/payload.json', 'src/runtime.ts'])
    const built = f.check()
    assert.equal(built.files.includes('out/types.d.js'), false)
    assert.equal(built.files.includes('out/payload.json'), true)
})

test('new or changed tracked outputs fail; removing all tracked outputs is legal', () => {
    const f = fixture()
    f.write('out/runtime.js', 'old generated bytes')
    f.git(['add', '-f', 'out/runtime.js'])
    assert.throws(() => f.check(), /prohibits tracked out/)
    f.git(['commit', '-qm', 'legacy-output'])
    f.write('out/runtime.js', 'changed generated bytes')
    f.git(['add', '-f', 'out/runtime.js'])
    assert.throws(() => f.check(), /prohibits tracked out/)
    f.git(['rm', '--cached', '-f', '--', 'out/runtime.js'])
    const removed = f.check()
    assert.equal(removed.skipped, true)
    assert.deepEqual(removed.components, [])
})

test('compile error and missing worker leave no plausible complete output', () => {
    const f = fixture()
    f.write('src/runtime.ts', 'export const value: number = "broken"\n')
    f.git(['add', 'src/runtime.ts'])
    assert.throws(() => f.build({ inputMode: 'index' }), /TS2322/)
    assert.deepEqual(fs.readdirSync(f.output), [])
    f.write('src/runtime.ts', 'export const value = 2\n')
    f.git(['add', 'src/runtime.ts'])
    f.git(['rm', '--', 'src/worker.ts'])
    assert.throws(() => f.build({ inputMode: 'index' }), /Missing required runtime output: out\/worker.js/)
    assert.deepEqual(fs.readdirSync(f.output), [])
})

test('output escape and missing string require fail instead of shipping a partial runtime', () => {
    const f = fixture()
    f.write('tsconfig.json', JSON.stringify({ compilerOptions: { rootDir: 'src', outDir: '../escaped' }, include: ['src/**/*.ts'] }))
    f.git(['add', 'tsconfig.json'])
    assert.throws(() => f.build({ inputMode: 'index' }), /output must remain inside out/)
    f.git(['restore', '--source=HEAD', '--staged', '--worktree', 'tsconfig.json'])
    f.write('src/runtime.ts', 'declare function require(name: string): unknown; export const value = require("./missing")\n')
    f.git(['add', 'src/runtime.ts'])
    assert.throws(() => f.build({ inputMode: 'index' }), /Missing relative runtime dependency/)
})

test('dependency override rejects mismatched original lock, installed lock and real TypeScript version', () => {
    const f = fixture()
    const badRoot = path.join(root, 'bad-dependencies')
    fs.cpSync(dependencyRoot, badRoot, { recursive: true })
    const build = () => f.build({ dependencyRoot: badRoot })
    fs.writeFileSync(path.join(badRoot, 'package-lock.json'), `${lockBytes} `)
    assert.throws(build, /lockfile does not match/)
    fs.writeFileSync(path.join(badRoot, 'package-lock.json'), lockBytes)
    fs.writeFileSync(path.join(badRoot, 'node_modules/.package-lock.json'), JSON.stringify({ packages: { 'node_modules/typescript': { ...tsLocked, version: '0.0.0' } } }))
    assert.throws(build, /Installed lock mismatch/)
    fs.writeFileSync(path.join(badRoot, 'node_modules/.package-lock.json'), JSON.stringify({ packages: { 'node_modules/typescript': tsLocked } }))
    fs.writeFileSync(path.join(badRoot, 'node_modules/typescript/lib/typescript.js'), 'module.exports = { version: "0.0.0" }\n')
    assert.throws(build, /TypeScript version/)
})

test('existing output content is rejected without deleting user files', () => {
    const f = fixture()
    fs.mkdirSync(f.output)
    fs.writeFileSync(path.join(f.output, 'keep.txt'), 'keep')
    assert.throws(() => f.build(), /must be empty/)
    assert.equal(fs.readFileSync(path.join(f.output, 'keep.txt'), 'utf8'), 'keep')
})

test('a dependency root with an unlisted package cannot satisfy hidden build imports', () => {
    const f = fixture()
    const extraRoot = path.join(root, 'extra-dependencies')
    fs.cpSync(dependencyRoot, extraRoot, { recursive: true })
    fs.mkdirSync(path.join(extraRoot, 'node_modules/unlisted'))
    fs.writeFileSync(path.join(extraRoot, 'node_modules/unlisted/index.d.ts'), 'export const secret: number\n')
    assert.throws(() => f.build({ dependencyRoot: extraRoot }), /Unlisted dependency entry/)
})

test('development worktree mode excludes a deleted optional module while index retains it', () => {
    const f = fixture()
    f.write('src/optional.ts', 'export const optional = 1\n')
    f.git(['add', 'src/optional.ts'])
    f.git(['commit', '-qm', 'optional-module'])
    fs.unlinkSync(path.join(f.repo, 'src/optional.ts'))
    assert.equal(f.check({ worktree: true }).files.includes('out/optional.js'), false)
    assert.equal(f.check({ all: true }).files.includes('out/optional.js'), true)
})

test('explicit generated character JSON is exported from staged input without widening docs access', () => {
    const f = fixture()
    f.write('docs/generated/character_table.json', '{"name":"committed"}\n')
    f.write('docs/private.json', '{"secret":true}\n')
    f.write('src/runtime.ts', 'import table from "../docs/generated/character_table.json"; export const value = table.name\n')
    f.git(['add', 'src/runtime.ts', 'docs/generated/character_table.json', 'docs/private.json'])
    assert.equal(f.check().files.includes('out/runtime.js'), true)
    f.git(['commit', '-qm', 'generated-character-json'])
    f.write('docs/generated/character_table.json', '{"name":"updated"}\n')
    f.git(['add', 'docs/generated/character_table.json'])
    f.write('docs/generated/character_table.json', 'invalid worktree JSON')
    assert.equal(f.check().skipped, false)
    f.write('src/runtime.ts', 'import table from "../docs/private.json"; export const value = table.secret\n')
    f.git(['add', 'src/runtime.ts'])
    assert.throws(() => f.check(), /TS2307/)
})

test('dependency override does not hide a source package manifest missing its lock update', () => {
    const f = fixture()
    f.write('package.json', JSON.stringify({ ...pkg, dependencies: { missing: '1.0.0' } }))
    f.git(['add', 'package.json'])
    assert.throws(() => f.check(), /Source package.json dependencies do not match/)
})

test('an absolute tsconfig root cannot read ambient declarations outside isolated inputs', () => {
    const f = fixture()
    const external = path.join(root, 'ambient-secret.d.ts')
    fs.writeFileSync(external, 'declare const enum AmbientValue { Number = 9 }\n')
    f.write('src/runtime.ts', 'export const value = AmbientValue.Number\n')
    f.write('tsconfig.json', JSON.stringify({ compilerOptions: { rootDir: 'src', outDir: 'out' }, files: ['src/runtime.ts', 'src/worker.ts', external] }))
    f.git(['add', 'src/runtime.ts', 'tsconfig.json'])
    assert.throws(() => f.check(), /Compiler input escapes isolated/)
})

test('server-only build emits real TypeScript outputs without any admin install or build', () => {
    const f = fixture({ admin: true }), observed = observedTools()
    const built = observed.build({ repo: f.repo, source: f.source, output: f.output, dependencyRoot, components: ['server'] })
    assert.deepEqual(built.components, ['server'])
    assert.deepEqual(built.files, ['out/runtime.js', 'out/worker.js'])
    assert.match(fs.readFileSync(path.join(f.output, 'out/runtime.js'), 'utf8'), /value = 1/)
    assert.equal(fs.existsSync(path.join(f.output, 'web')), false)
    assert.deepEqual(observed.calls, [])
})

test('admin-only build ignores broken server inputs and never resolves server dependencies', () => {
    const f = fixture({ admin: true }), observed = observedTools()
    f.write('src/runtime.ts', 'export const value: number = "server compile must not run"\n')
    f.write('tsconfig.json', 'invalid server tsconfig !\n')
    f.write('package.json', JSON.stringify({ ...pkg, dependencies: { unavailable: '0.0.0' } }))
    f.git(['add', 'src/runtime.ts', 'tsconfig.json', 'package.json'])
    const built = observed.build({ repo: f.repo, inputMode: 'index', output: f.output,
        dependencyRoot: path.join(root, 'server-dependencies-must-not-be-read'), components: ['admin'] })
    assert.deepEqual(built.components, ['admin'])
    assert.deepEqual(built.files, ['web/dist/index.html'])
    assert.equal(fs.existsSync(path.join(f.output, 'out')), false)
    assert.match(fs.readFileSync(path.join(f.output, 'web/dist/index.html'), 'utf8'), /admin-committed/)
    assert.deepEqual(observed.calls.map(call => [call.component, call.args[0]]), [['admin', 'ci'], ['admin', 'run']])
})

test('default build retains both complete server and admin artifacts', () => {
    const f = fixture({ admin: true }), observed = observedTools()
    const built = observed.build({ repo: f.repo, source: f.source, output: f.output, dependencyRoot })
    assert.deepEqual(built.files, ['out/runtime.js', 'out/worker.js', 'web/dist/index.html'])
    for (const file of built.files) assert.equal(fs.statSync(path.join(f.output, file)).isFile(), true)
    assert.deepEqual(observed.calls.map(call => [call.component, call.args[0]]), [['admin', 'ci'], ['admin', 'run']])
})

test('automatic checks select server or admin and skip docs, tests and CDN-only inputs', () => {
    for (const [filename, contents, expected] of [
        ['src/runtime.ts', 'export const value = 2\n', ['server']],
        ['admin/src/main.ts', 'export const label = "admin-staged"\n', ['admin']],
        ['docs/notes.md', 'documentation only\n', []],
        ['tests/example.test.cjs', 'throw new Error("not build input")\n', []],
        ['assets/asset-patch/manifest.json', '{"version":"fixture"}\n', []],
        ['assets/asset-patch/active/example.zip', 'CDN bytes\n', []],
    ]) {
        const f = fixture({ admin: true }), observed = observedTools()
        f.write(filename, contents); f.git(['add', filename])
        const result = observed.check({ repo: f.repo, dependencyRoot })
        assert.deepEqual(result.components, expected, filename)
        assert.equal(result.skipped, expected.length === 0, filename)
        assert.deepEqual(observed.calls.map(call => call.component), expected.includes('admin') ? ['admin', 'admin'] : [], filename)
        if (expected.length) assert.equal(result.files.some(file => file.startsWith('out/')), expected.includes('server'), filename)
    }
})

test('task base includes committed server changes and staged admin inputs without borrowing dirty worktree repairs', () => {
    const f = fixture({ admin: true }), observed = observedTools()
    f.write('src/runtime.ts', 'export const value = 7\n')
    f.git(['add', 'src/runtime.ts']); f.git(['commit', '-qm', 'first-task-change'])
    f.write('admin/src/main.ts', 'export const label = "admin-staged"\n')
    f.git(['add', 'admin/src/main.ts'])
    f.write('src/runtime.ts', 'export const value: number = "unstaged poison"\n')
    f.write('admin/src/main.ts', 'ADMIN_BUILD_FAIL\n')
    const result = observed.check({ repo: f.repo, dependencyRoot, base: f.source })
    assert.equal(result.mode, 'index')
    assert.equal(result.skipped, false)
    assert.deepEqual(result.components, ['server', 'admin'])
    assert.deepEqual(result.files, ['out/runtime.js', 'out/worker.js', 'web/dist/index.html'])
    assert.match(observed.calls.find(call => call.args[0] === 'run').source, /admin-staged/)
    assert.throws(() => observed.check({ repo: f.repo, dependencyRoot, base: f.source, worktree: true }), /TS2322|admin compilation failed/)
})

test('committed compile errors remain checked from the task base after the index becomes clean', () => {
    const f = fixture(), observed = observedTools()
    f.write('src/runtime.ts', 'export const value: number = "committed invalid code"\n')
    f.git(['add', 'src/runtime.ts']); f.git(['commit', '-qm', 'invalid-task-change'])
    f.write('src/runtime.ts', 'export const value = 9\n')
    assert.throws(() => observed.check({ repo: f.repo, dependencyRoot, base: f.source }), /TS2322/)
    const cli = spawnSync(process.execPath, [path.join(repoRoot, 'tools/check-out-artifacts.cjs'),
        '--repo', f.repo, '--dependency-root', dependencyRoot, '--base', f.source], { encoding: 'utf8' })
    assert.notEqual(cli.status, 0)
    assert.match(cli.stderr, /TS2322/)
})

test('invalid, empty, noncommit and unrelated bases cannot silently skip a docs-only check', () => {
    const f = fixture(), observed = observedTools()
    f.write('docs/notes.md', 'docs only\n'); f.git(['add', 'docs/notes.md'])
    const tree = f.git(['rev-parse', `${f.source}^{tree}`])
    const unrelated = f.git(['commit-tree', tree, '-m', 'unrelated-root'])
    for (const base of ['', ' ', null, 42, 'does-not-exist', '0'.repeat(40), tree, unrelated]) {
        assert.throws(() => observed.check({ repo: f.repo, dependencyRoot, base }), undefined, `must reject base ${JSON.stringify(base)}`)
    }
    assert.deepEqual(observed.calls, [])
    const cli = spawnSync(process.execPath, [path.join(repoRoot, 'tools/check-out-artifacts.cjs'), '--repo', f.repo, '--base'], { encoding: 'utf8' })
    assert.notEqual(cli.status, 0)
    assert.match(cli.stderr, /base|argument/i)
})

test('--all explicitly builds both components even when only documentation changed', () => {
    const f = fixture({ admin: true }), observed = observedTools()
    f.write('docs/notes.md', 'docs only\n'); f.git(['add', 'docs/notes.md'])
    const result = observed.check({ repo: f.repo, dependencyRoot, all: true })
    assert.equal(result.skipped, false)
    assert.deepEqual(result.components, ['server', 'admin'])
    assert.deepEqual(result.files, ['out/runtime.js', 'out/worker.js', 'web/dist/index.html'])
    assert.equal(observed.calls.some(call => call.component === 'admin' && call.args[0] === 'ci'), true)
})
