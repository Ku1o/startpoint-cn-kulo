#!/usr/bin/env node
'use strict'

/**
 * Persistence boundary guard (协作确认单 #13 / #15).
 *
 * Only lines *added* by this change set are inspected, so existing code is
 * never reported. Two patterns fail the check:
 *
 *   1. `.transaction(` in any `src/**\/*.ts` file outside the allowlist in
 *      `tools/persistence-boundary-allowlist.json`. New writes must go through
 *      `await runPersistenceTransaction({ domain, playerId, operation }, ...)`.
 *   2. `runPersistenceTransactionSync(` in `src/routes/**`. New routes must not
 *      add synchronous persistence entry points.
 *
 * Usage:
 *   node tools/check-persistence-boundary.cjs                     # diff vs origin/staging
 *   node tools/check-persistence-boundary.cjs --base origin/main  # another base
 *   node tools/check-persistence-boundary.cjs --staged            # staged changes only
 *
 * The script never modifies files.
 */

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const repoRoot = path.resolve(__dirname, '..')
const allowlistPath = path.join(__dirname, 'persistence-boundary-allowlist.json')

const RULES = [
    {
        id: 'direct-transaction',
        pattern: /\.transaction\s*\(/,
        applies: file => /^src\/.*\.ts$/.test(file),
        allowlistKey: 'transaction',
        message: '新增直接 transaction()：请改用 await runPersistenceTransaction({ domain, playerId, operation }, …)',
    },
    {
        id: 'route-sync-transaction',
        pattern: /\brunPersistenceTransactionSync\s*\(/,
        applies: file => /^src\/routes\/.*\.ts$/.test(file),
        allowlistKey: null,
        message: '路由新增 runPersistenceTransactionSync()：新路由请使用异步的 runPersistenceTransaction()',
    },
]

function globToRegExp(glob) {
    let source = ''
    for (let i = 0; i < glob.length; i += 1) {
        const char = glob[i]
        if (char === '*' && glob[i + 1] === '*') {
            source += '.*'
            i += 1
        } else if (char === '*') {
            source += '[^/]*'
        } else {
            source += char.replace(/[.+?^${}()|[\]\\]/g, '\\$&')
        }
    }
    return new RegExp(`^${source}$`)
}

function loadAllowlist(file = allowlistPath) {
    const raw = JSON.parse(fs.readFileSync(file, 'utf8'))
    const result = {}
    for (const [key, entries] of Object.entries(raw)) {
        if (!Array.isArray(entries)) continue
        result[key] = entries.map(entry => globToRegExp(entry.path))
    }
    return result
}

/** Parse `git diff --unified=0` output into added lines with file and line number. */
function parseAddedLines(diff) {
    const added = []
    let file = null
    let line = 0
    for (const text of diff.split(/\r?\n/)) {
        if (text.startsWith('+++ ')) {
            const target = text.slice(4)
            file = target === '/dev/null' ? null : target.replace(/^b\//, '')
            continue
        }
        const hunk = /^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@/.exec(text)
        if (hunk) {
            line = Number(hunk[1])
            continue
        }
        if (file === null) continue
        if (text.startsWith('+')) {
            added.push({ file, line, text: text.slice(1) })
            line += 1
        }
    }
    return added
}

function isCommentLine(text) {
    const trimmed = text.trim()
    return trimmed.startsWith('//') || trimmed.startsWith('*') || trimmed.startsWith('/*')
}

function findViolations(addedLines, allowlist) {
    const violations = []
    for (const entry of addedLines) {
        if (isCommentLine(entry.text)) continue
        for (const rule of RULES) {
            if (!rule.applies(entry.file) || !rule.pattern.test(entry.text)) continue
            const allowed = rule.allowlistKey
                ? (allowlist[rule.allowlistKey] || []).some(re => re.test(entry.file))
                : false
            if (!allowed) violations.push({ ...entry, rule: rule.id, message: rule.message })
        }
    }
    return violations
}

function gitDiff(args) {
    return execFileSync('git', ['diff', '--unified=0', '--no-color', '--no-ext-diff', ...args, '--', 'src'], {
        cwd: repoRoot,
        encoding: 'utf8',
        maxBuffer: 256 * 1024 * 1024,
    })
}

function main(argv) {
    if (argv.includes('--help') || argv.includes('-h')) {
        console.log('用法: node tools/check-persistence-boundary.cjs [--base <ref>] [--staged]')
        return 0
    }
    let diff
    if (argv.includes('--staged')) {
        diff = gitDiff(['--cached'])
    } else {
        const index = argv.indexOf('--base')
        const base = index >= 0 ? argv[index + 1] : 'origin/staging'
        if (!base) throw new Error('--base 需要一个 Git 引用')
        diff = gitDiff([`${base}...HEAD`])
    }
    const violations = findViolations(parseAddedLines(diff), loadAllowlist())
    if (violations.length === 0) {
        console.log('[持久化边界] 通过：新增代码没有绕过 runPersistenceTransaction。')
        return 0
    }
    for (const v of violations) {
        console.log(`  ✖ ${v.file}:${v.line}  ${v.message}`)
        console.log(`      ${v.text.trim()}`)
        if (process.env.GITHUB_ACTIONS === 'true') {
            console.log(`::error file=${v.file},line=${v.line}::${v.message}`)
        }
    }
    console.log(`[持久化边界] 发现 ${violations.length} 处问题。确属基础设施/迁移/快照/worker 的，请与所有者确认后加入 tools/persistence-boundary-allowlist.json。`)
    return 1
}

if (require.main === module) {
    try {
        process.exit(main(process.argv.slice(2)))
    } catch (error) {
        console.error(`[持久化边界] 错误：${error.message}`)
        process.exit(2)
    }
}

module.exports = { parseAddedLines, findViolations, loadAllowlist, globToRegExp }
