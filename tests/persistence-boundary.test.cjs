const assert = require('node:assert/strict')
const test = require('node:test')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { execFileSync } = require('node:child_process')
const {
    parseAddedLines, findViolations, loadAllowlist, globToRegExp,
    parseAllowlist, checkBoundary, extractReviewedSpan, readGitSnapshotSource,
} = require('../tools/check-persistence-boundary.cjs')

const allowlist = loadAllowlist()
const repoRoot = path.resolve(__dirname, '..')
const rawAllowlist = JSON.parse(fs.readFileSync(path.join(repoRoot, 'tools/persistence-boundary-allowlist.json'), 'utf8'))

function reviewedSources() {
    return new Map(allowlist.reviewedOperations.map(entry => [entry.path, fs.readFileSync(path.join(repoRoot, entry.path), 'utf8')]))
}

function checkSources(sources, added = []) {
    return checkBoundary(added, allowlist, file => {
        assert.ok(sources.has(file), `Unexpected source read: ${file}`)
        return sources.get(file)
    })
}

function replaceOnce(source, before, after) {
    assert.ok(source.includes(before), `Mutation target missing: ${before}`)
    return source.replace(before, after)
}

function diffFor(file, lines, start = 10) {
    return [
        `diff --git a/${file} b/${file}`,
        `--- a/${file}`,
        `+++ b/${file}`,
        `@@ -${start},0 +${start},${lines.length} @@`,
        ...lines.map(line => `+${line}`),
    ].join('\n')
}

test('parses added lines with their target line numbers', () => {
    const diff = [
        diffFor('src/lib/a.ts', ['const x = 1', 'const y = 2'], 5),
        '@@ -20 +21,1 @@',
        '-old',
        '+const z = 3',
    ].join('\n')
    assert.deepEqual(parseAddedLines(diff).map(({ file, line }) => `${file}:${line}`),
        ['src/lib/a.ts:5', 'src/lib/a.ts:6', 'src/lib/a.ts:21'])
})

test('flags new direct transactions outside the allowlist', () => {
    const added = parseAddedLines(diffFor('src/lib/new-feature.ts', ['    db.transaction(() => {', '    database.transaction (fn)()']))
    const violations = findViolations(added, allowlist)
    assert.equal(violations.length, 2)
    assert.ok(violations.every(v => v.rule === 'direct-transaction'))
})

test('allows infrastructure, migrations, snapshots and workers', () => {
    for (const file of [
        'src/lib/persistence-coordinator.ts',
        'src/lib/sqlite-write-coordinator.ts',
        'src/data/updaters/wdfpData.ts',
        'src/data/snapshots/player-snapshot.ts',
        'src/workers/sqlite-persistence-worker.ts',
    ]) {
        assert.deepEqual(findViolations(parseAddedLines(diffFor(file, ['db.transaction(() => {})'])), allowlist), [], file)
    }
})

test('flags runPersistenceTransactionSync only in routes', () => {
    const route = parseAddedLines(diffFor('src/routes/api/foo.ts', ['runPersistenceTransactionSync(ctx, () => 1)']))
    assert.equal(findViolations(route, allowlist)[0].rule, 'route-sync-transaction')
    const domain = parseAddedLines(diffFor('src/data/domains/foo.ts', ['runPersistenceTransactionSync(ctx, () => 1)']))
    assert.deepEqual(findViolations(domain, allowlist), [])
})

test('ignores comments, removed lines, non-TS files and the async API', () => {
    const diff = [
        diffFor('src/lib/x.ts', ['// db.transaction( is forbidden', ' * db.transaction(', 'await runPersistenceTransaction(ctx, op)']),
        diffFor('docs/notes.md', ['db.transaction(']),
        'diff --git a/src/lib/y.ts b/src/lib/y.ts',
        '--- a/src/lib/y.ts',
        '+++ b/src/lib/y.ts',
        '@@ -3,1 +2,0 @@',
        '-db.transaction(() => {})',
    ].join('\n')
    assert.deepEqual(findViolations(parseAddedLines(diff), allowlist), [])
})

test('glob matching distinguishes * and **', () => {
    assert.ok(globToRegExp('src/lib/sqlite-*').test('src/lib/sqlite-writer.ts'))
    assert.ok(!globToRegExp('src/lib/sqlite-*').test('src/lib/sqlite-x/nested.ts'))
    assert.ok(globToRegExp('src/workers/**').test('src/workers/a/b.ts'))
})

test('current policy retains ten infrastructure entries and approves exactly 23 operations in nine files', () => {
    assert.equal(rawAllowlist.transaction.length, 10)
    assert.equal(allowlist.reviewedOperations.length, 9)
    assert.equal(allowlist.reviewedOperations.reduce((count, entry) => count + entry.operations.length, 0), 23)
    for (const entry of allowlist.reviewedOperations) {
        assert.ok(!allowlist.transaction.some(pattern => pattern.test(entry.path)), entry.path)
        assert.ok(entry.operations.every(operation => operation.transactions === 1), entry.path)
    }
    const sources = reviewedSources()
    const added = [...sources].flatMap(([file, source]) => parseAddedLines(diffFor(file, source.split(/\r?\n/), 1)))
    assert.deepEqual(checkSources(sources, added), [])
})

test('ordinary edits outside approved owners and CRLF conversion remain allowed', () => {
    const sources = reviewedSources()
    for (const [file, source] of sources) {
        sources.set(file, (`\nconst unrelatedBoundaryFixture = 1\n\n${source}\nfunction unrelatedBoundaryHelper() { return 1 }\n`).replace(/\r?\n/g, '\r\n'))
    }
    assert.deepEqual(checkSources(sources), [])
})

test('a new transaction is rejected in each formerly whole-file exception', () => {
    for (const entry of allowlist.reviewedOperations) {
        const sources = reviewedSources()
        sources.set(entry.path, `${sources.get(entry.path)}\ndb.transaction(() => 1)()\n`)
        assert.ok(checkSources(sources).length > 0, entry.path)
    }
})

test('new multiline, comment-separated, parenthesized and referenced transaction properties are rejected', () => {
    const file = 'src/lib/content-client-reload.ts'
    for (const addition of [
        'const extra = db\n    .\n    transaction\n    (() => 1)()',
        'const extra = db. /* separator */ transaction /* separator */ (() => 1)()',
        'const extra = db.\n// separator\ntransaction(() => 1)()',
        'const extra = (db.transaction)(() => 1)()',
        'const extra = db.transaction',
    ]) {
        const sources = reviewedSources()
        sources.set(file, `${sources.get(file)}\n${addition}\n`)
        assert.ok(checkSources(sources).length > 0, addition)
    }
})

test('duplicating an approved owner or its unchanged transaction does not reuse approval', () => {
    const entry = allowlist.reviewedOperations.find(entry => entry.path === 'src/lib/content-client-reload.ts')
    const original = reviewedSources().get(entry.path)
    const owner = extractReviewedSpan(original, entry.operations[0]).text
    for (const addition of [owner, 'this.db.transaction(apply).immediate()']) {
        const sources = reviewedSources()
        sources.set(entry.path, `${original}\n${addition}\n`)
        assert.ok(checkSources(sources).length > 0, addition)
    }
})

test('changing an approved callback, named apply, offline guard or execution mode requires review', () => {
    for (const [file, before, after] of [
        ['src/lib/content-client-reload.ts', '.run(next.epoch, nowMs, CONTENT_CLIENT_RELOAD_MESSAGE)', '.run(next.epoch, nowMs + 1, CONTENT_CLIENT_RELOAD_MESSAGE)'],
        ['src/lib/town-theme-store.ts', 'const current = this.read()', 'const current = this.read(); void 0'],
        ['src/lib/content-history-bootstrap.ts', '    assertTimeCutoverOfflineDatabaseSync(store.db, options.offlineGuard)', '    void options.offlineGuard'],
        ['src/lib/content-history-bootstrap.ts', '    }).immediate()', '    })()'],
    ]) {
        const sources = reviewedSources()
        sources.set(file, replaceOnce(sources.get(file), before, after))
        assert.ok(checkSources(sources).length > 0, `${file}: ${before}`)
    }
})

test('missing owner anchors and a changed town-theme dependency wrapper fail closed', () => {
    const entry = allowlist.reviewedOperations.find(entry => entry.path === 'src/lib/content-client-reload.ts')
    const sources = reviewedSources()
    sources.set(entry.path, replaceOnce(sources.get(entry.path), entry.operations[0].startLine, '    renamedBoundaryOwner() {'))
    assert.ok(checkSources(sources).length > 0)

    const townFile = 'src/routes/web_api/town-theme.ts'
    const townSources = reviewedSources()
    townSources.set(townFile, replaceOnce(townSources.get(townFile),
        '.runPersistenceTransaction({ domain: "admin", operation: "apply_town_theme" }, operation)', 'operation()'))
    assert.ok(checkSources(townSources).length > 0)
})

test('the existing route-sync rule also applies outside approved owners in a reviewed file', () => {
    const file = 'src/routes/web_api/town-theme.ts'
    const line = 'runPersistenceTransactionSync(ctx, () => 1)'
    const sources = reviewedSources()
    sources.set(file, `${sources.get(file)}\n${line}\n`)
    const violations = checkSources(sources, parseAddedLines(diffFor(file, [line], 1000)))
    assert.ok(violations.some(violation => violation.rule === 'route-sync-transaction'))
})

test('HEAD and index scans cannot be hidden by a clean unstaged working-tree source', t => {
    const fixtureParent = path.resolve(process.env.PERSISTENCE_BOUNDARY_TEST_ROOT || os.tmpdir())
    fs.mkdirSync(fixtureParent, { recursive: true })
    const fixtureRoot = fs.mkdtempSync(path.join(fixtureParent, 'persistence-boundary-'))
    t.after(() => {
        const target = fs.realpathSync(fixtureRoot)
        const relative = path.relative(fs.realpathSync(fixtureParent), target)
        assert.ok(relative && !relative.startsWith('..') && !path.isAbsolute(relative), `Unsafe fixture cleanup: ${target}`)
        fs.rmSync(target, { recursive: true })
    })
    const git = args => execFileSync('git', args, { cwd: fixtureRoot, encoding: 'utf8', stdio: 'pipe' })
    const entry = rawAllowlist.reviewedOperations.find(entry => entry.path === 'src/lib/content-client-reload.ts')
    const source = reviewedSources().get(entry.path)
    const fixtureFile = path.join(fixtureRoot, entry.path)
    fs.mkdirSync(path.dirname(fixtureFile), { recursive: true })
    fs.writeFileSync(fixtureFile, source)
    git(['init', '--quiet'])
    git(['add', '--', entry.path])
    git(['-c', 'user.name=Persistence boundary fixture', '-c', 'user.email=fixture@example.invalid', '-c', 'commit.gpgsign=false', 'commit', '--quiet', '--no-verify', '-m', 'fixture'])
    fs.writeFileSync(fixtureFile, `${source}\ndb.transaction(() => 1)()\n`)
    git(['add', '--', entry.path])
    fs.writeFileSync(fixtureFile, source)

    const fixturePolicy = parseAllowlist({ transaction: [], reviewedOperations: [entry] })
    assert.deepEqual(checkBoundary([], fixturePolicy, file => readGitSnapshotSource(fixtureRoot, file, false)), [])
    assert.ok(checkBoundary([], fixturePolicy, file => readGitSnapshotSource(fixtureRoot, file, true)).length > 0)
    assert.ok(!readGitSnapshotSource(fixtureRoot, entry.path, false).includes('db.transaction(() => 1)()'))
    assert.ok(readGitSnapshotSource(fixtureRoot, entry.path, true).includes('db.transaction(() => 1)()'))
})
