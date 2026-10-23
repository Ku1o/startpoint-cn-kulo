#!/usr/bin/env node
'use strict'

/**
 * Persistence boundary guard (协作确认单 #13 / #15).
 *
 * Ordinary files retain the added-lines rules below. The reviewed operations
 * in nine content/clock files are checked in full, including callback bodies,
 * guards and execution chains; their files are not blanket exceptions.
 *
 *   1. `.transaction(` in any `src/**\/*.ts` file outside the allowlist in
 *      `tools/persistence-boundary-allowlist.json`. New writes must go through
 *      `await runPersistenceTransaction({ domain, playerId, operation }, ...)`.
 *   2. `runPersistenceTransactionSync(` in `src/routes/**`. New routes must not
 *      add synchronous persistence entry points.
 *
 * Usage:
 *   node tools/check-persistence-boundary.cjs                     # diff vs origin/main
 *   node tools/check-persistence-boundary.cjs --base <ref>        # another base
 *   node tools/check-persistence-boundary.cjs --staged            # staged changes only
 *
 * The script never modifies files.
 */

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')
const { createHash } = require('node:crypto')

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

function parseAllowlist(raw) {
    if (!raw || !Array.isArray(raw.transaction)) throw new Error('Invalid transaction allowlist')
    const result = { transaction: raw.transaction.map(entry => globToRegExp(entry.path)), reviewedOperations: [] }
    const files = new Set()
    for (const entry of raw.reviewedOperations || []) {
        if (!entry || !/^src\/[a-zA-Z0-9_/-]+\.ts$/.test(entry.path) || entry.path.split('/').includes('..')
            || files.has(entry.path) || result.transaction.some(pattern => pattern.test(entry.path))
            || !Array.isArray(entry.operations) || !entry.operations.length
            || entry.contexts !== undefined && !Array.isArray(entry.contexts)) {
            throw new Error('Invalid or blanket-covered reviewed-operation file')
        }
        files.add(entry.path)
        const names = new Set()
        for (const [kind, spans] of [['operation', entry.operations], ['context', entry.contexts || []]]) {
            for (const span of spans) {
                if (!span || typeof span.name !== 'string' || !span.name.trim() || names.has(span.name)
                    || typeof span.startLine !== 'string' || !span.startLine.trim() || /[\r\n]/.test(span.startLine)
                    || typeof span.endLine !== 'string' || !/^\s*}\s*;?$/.test(span.endLine) || /[\r\n]/.test(span.endLine)
                    || !/^[a-f0-9]{64}$/.test(span.sha256) || kind === 'operation' && span.transactions !== 1) {
                    throw new Error('Invalid reviewed-operation anchor, identity or count')
                }
                names.add(span.name)
            }
        }
        result.reviewedOperations.push(entry)
    }
    return result
}

function loadAllowlist(file = allowlistPath) {
    return parseAllowlist(JSON.parse(fs.readFileSync(file, 'utf8')))
}

function fingerprintSource(text) {
    return createHash('sha256').update(text.replace(/\r\n/g, '\n')).digest('hex')
}

// Anchors are complete, uniquely named declaration lines, not line numbers.
// The closing line uses the declaration's indentation. A changed or premature
// close changes the whole-owner identity and fails; it cannot bless a prefix.
function extractReviewedSpan(source, rule) {
    const text = source.replace(/\r\n/g, '\n'), lines = text.split('\n')
    const starts = []
    for (let index = 0; index < lines.length; index++) if (lines[index] === rule.startLine) starts.push(index)
    if (starts.length !== 1) throw new Error('声明锚点缺失或重复')
    const first = starts[0], last = lines.findIndex((line, index) => index > first && line === rule.endLine)
    if (last < 0) throw new Error('声明结束边界缺失')
    const start = lines.slice(0, first).reduce((sum, line) => sum + line.length + 1, 0)
    const body = lines.slice(first, last + 1).join('\n')
    return { start, end: start + body.length, text: body, line: first + 1 }
}

// Deliberately conservative source matching, not a complete TypeScript parser.
// Match the property, including comment/newline separators, so extracting a
// reference or wrapping the call in parentheses does not avoid this boundary.
function transactionReferences(source) {
    const gap = '(?:\\s|/\\*[\\s\\S]*?\\*/|//[^\\n]*(?:\\n|$))*'
    return [...source.matchAll(new RegExp('\\.' + gap + 'transaction\\b', 'g'))]
}

function checkBoundary(addedLines, allowlist, readSource) {
    const reviewed = allowlist.reviewedOperations || [], files = new Set(reviewed.map(entry => entry.path))
    const violations = findViolations(addedLines, allowlist)
        .filter(entry => entry.rule !== 'direct-transaction' || !files.has(entry.file))
    for (const entry of reviewed) {
        let source
        const report = (line, message, text = '') => violations.push({ file: entry.path, line,
            rule: 'reviewed-operation', message, text })
        try {
            source = readSource(entry.path)
            if (typeof source !== 'string') throw new Error('missing source')
            source = source.replace(/\r\n/g, '\n')
        } catch {
            report(1, '无法读取被检查对象中的已核查文件')
            continue
        }
        const references = transactionReferences(source), approved = []
        for (const [kind, spans] of [['operation', entry.operations], ['context', entry.contexts || []]]) {
            for (const span of spans) {
                let range
                try { range = extractReviewedSpan(source, span) }
                catch (error) { report(1, `${span.name}: ${error.message}`); continue }
                if (fingerprintSource(range.text) !== span.sha256) {
                    report(range.line, `${span.name}: 已核查操作或必要上下文已改变，需重新核查`, span.startLine)
                    continue
                }
                if (kind === 'operation') {
                    const count = references.filter(match => match.index >= range.start && match.index < range.end).length
                    if (count !== span.transactions) report(range.line, `${span.name}: 事务操作数量不匹配`, span.startLine)
                    else approved.push(range)
                }
            }
        }
        for (const match of references) {
            if (approved.filter(range => match.index >= range.start && match.index < range.end).length !== 1) {
                const line = source.slice(0, match.index).split('\n').length
                report(line, '新增或变更的事务操作未在精确核查范围内', source.split('\n')[line - 1])
            }
        }
    }
    return violations
}

function readGitSnapshotSource(repo, relative, staged = false) {
    if (path.isAbsolute(relative) || relative.split('/').some(part => !part || part === '..')) throw new Error('Invalid snapshot path')
    return execFileSync('git', ['show', `${staged ? '' : 'HEAD'}:${relative}`], {
        cwd: repo, encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
        stdio: ['ignore', 'pipe', 'pipe'],
    })
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
    const staged = argv.includes('--staged')
    if (staged) {
        diff = gitDiff(['--cached'])
    } else {
        const index = argv.indexOf('--base')
        const base = index >= 0 ? argv[index + 1] : 'origin/main'
        if (!base) throw new Error('--base 需要一个 Git 引用')
        diff = gitDiff([`${base}...HEAD`])
    }
    // Configuration and all reviewed source come from the same HEAD/index as
    // the diff. Unstaged edits cannot hide a staged or committed violation.
    const allowlist = parseAllowlist(JSON.parse(readGitSnapshotSource(repoRoot,
        'tools/persistence-boundary-allowlist.json', staged)))
    const violations = checkBoundary(parseAddedLines(diff), allowlist,
        relative => readGitSnapshotSource(repoRoot, relative, staged))
    if (violations.length === 0) {
        const count = allowlist.reviewedOperations.reduce((total, entry) => total + entry.operations.length, 0)
        console.log(`[持久化边界] 通过：新增代码符合边界，${count} 项精确核查操作匹配。`)
        return 0
    }
    for (const v of violations) {
        console.log(`  ✖ ${v.file}:${v.line}  ${v.message}`)
        console.log(`      ${v.text.trim()}`)
        if (process.env.GITHUB_ACTIONS === 'true') {
            console.log(`::error file=${v.file},line=${v.line}::${v.message}`)
        }
    }
    console.log(`[持久化边界] 发现 ${violations.length} 处问题。请修复新增写入边界；特殊操作须重新核查，不得自动更新身份或扩大为整文件放行。`)
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

module.exports = { parseAddedLines, findViolations, loadAllowlist, parseAllowlist, globToRegExp,
    fingerprintSource, extractReviewedSpan, checkBoundary, readGitSnapshotSource }
