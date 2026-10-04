const assert = require('node:assert/strict')
const test = require('node:test')
const { parseAddedLines, findViolations, loadAllowlist, globToRegExp } = require('../tools/check-persistence-boundary.cjs')

const allowlist = loadAllowlist()

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
