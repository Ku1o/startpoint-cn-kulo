#!/usr/bin/env node
'use strict'

/**
 * Persistence boundary guard (协作确认单 #13 / #15).
 *
 * Ordinary files retain the added-lines rules below. The reviewed operations
 * in ten content/clock/maintenance files retain bounded transaction checks;
 * ordinary callback/signature changes do not require re-signing whole functions.
 * Atomicity, rollback and data preservation are covered by behavior tests.
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
            || !Array.isArray(entry.operations) || !entry.operations.length) {
            throw new Error('Invalid or blanket-covered reviewed-operation file')
        }
        files.add(entry.path)
        const names = new Set()
        for (const op of entry.operations) {
            if (!op || !/^[a-zA-Z_$][\w$]*$/.test(op.name) || names.has(op.name)
                || !/^[a-zA-Z_$][\w$]*(?:\.[a-zA-Z_$][\w$]*)*$/.test(op.receiver)
                || !['deferred', 'immediate', 'exclusive', 'async'].includes(op.mode) || op.transactions !== 1
                || op.requiredCalls && (!Array.isArray(op.requiredCalls) || op.requiredCalls.some(name => !/^[a-zA-Z_$][\w$]*$/.test(name)))) {
                throw new Error('Invalid reviewed-operation name, receiver, mode or count')
            }
            names.add(op.name)
        }
        result.reviewedOperations.push(entry)
    }
    return result
}

function loadAllowlist(file = allowlistPath) {
    return parseAllowlist(JSON.parse(fs.readFileSync(file, 'utf8')))
}

// Keep offsets/newlines while ignoring comments and quoted text. This remains
// a bounded source check, not a TypeScript parser or business-logic proof.
function maskNonCode(source) {
    return source.replace(/\/\*[\s\S]*?\*\/|\/\/[^\n]*|"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`/g,
        value => value.replace(/[^\n]/g, ' '))
}

// Locate the existing named declaration, allowing return-type/signature edits.
// These reviewed functions use an unambiguous closing line at their own indent.
function extractReviewedSpan(source, rule) {
    const text = source.replace(/\r\n/g, '\n'), code = maskNonCode(text), lines = code.split('\n')
    const declaration = new RegExp('^([ \\t]*)(?:(?:export|async|private|public|protected|static)\\s+)*(?:function\\s+)?'
        + rule.name + '\\s*(?:<[^\\n]*>)?\\s*\\(')
    const starts = []
    for (let index = 0; index < lines.length; index++) {
        const line = lines[index]
        if (declaration.test(line) && (line.includes('{')
            || (line.match(/\(/g) || []).length > (line.match(/\)/g) || []).length
            || /^\s*{/.test(lines[index + 1] || ''))) starts.push(index)
    }
    if (starts.length !== 1) throw new Error('声明锚点缺失或重复')
    const first = starts[0], indent = declaration.exec(lines[first])[1]
    const closing = new RegExp('^' + indent + '}\\s*;?\\s*$')
    const last = lines.findIndex((line, index) => index > first && closing.test(line))
    if (last < 0) throw new Error('声明结束边界缺失')
    const start = lines.slice(0, first).reduce((sum, line) => sum + line.length + 1, 0)
    const end = start + lines.slice(first, last + 1).join('\n').length
    return { start, end, text: text.slice(start, end), code: code.slice(start, end), line: first + 1 }
}

function transactionReferences(code) {
    return [...code.matchAll(/\.\s*transaction\b/g)]
}

function transactionMatches(code, match, op) {
    const receiver = code.slice(0, match.index).match(/[\w$]+(?:\s*\.\s*[\w$]+)*\s*$/)
    if (receiver?.[0].replace(/\s/g, '') !== op.receiver) return false
    const tail = match.index + match[0].length
    const opening = /^\s*\(/.exec(code.slice(tail))
    if (!opening) return false // a reference or parenthesized property is not the approved call
    const first = tail + opening[0].length - 1
    let depth = 1, end = first + 1
    for (; end < code.length && depth; end++) {
        if (code[end] === '(') depth++
        else if (code[end] === ')') depth--
    }
    if (depth) return false
    if (op.mode === 'async') return /\bawait\s+$/.test(code.slice(0, receiver.index))
    const invocation = op.mode === 'deferred' ? /^\s*\(\s*\)/ : new RegExp('^\\s*\\.\\s*' + op.mode + '\\s*\\(\\s*\\)')
    return invocation.test(code.slice(end))
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
        const code = maskNonCode(source), references = transactionReferences(code), approved = []
        for (const op of entry.operations) {
            let range
            try { range = extractReviewedSpan(source, op) }
            catch (error) { report(1, `${op.name}: ${error.message}`); continue }
            const calls = references.filter(match => match.index >= range.start && match.index < range.end)
            if (calls.length !== op.transactions || !calls.every(match => transactionMatches(code, match, op))) {
                report(range.line, `${op.name}: 事务数量、连接对象或执行方式已改变`)
                continue
            }
            if (op.reentrant && !range.code.replace(/\s/g, '').includes(op.receiver + '.inTransaction')
                || op.internal && /^\s*export\b/.test(range.code)
                || (op.requiredCalls || []).some(name => !new RegExp('\\b' + name + '\\s*\\(').test(range.code))) {
                report(range.line, `${op.name}: 必要的现有事务或离线保护入口已移除`)
                continue
            }
            approved.push(range)
        }
        // The injected async route must keep its default queued persistence entry.
        if (entry.path === 'src/routes/web_api/town-theme.ts' && !/\.\s*runPersistenceTransaction\s*\(/.test(code)) {
            report(1, '主城外观默认依赖缺少异步持久化入口')
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
        console.log(`[持久化边界] 通过：新增代码符合边界，${count} 项已有事务的结构匹配。`)
        return 0
    }
    for (const v of violations) {
        console.log(`  ✖ ${v.file}:${v.line}  ${v.message}`)
        console.log(`      ${v.text.trim()}`)
        if (process.env.GITHUB_ACTIONS === 'true') {
            console.log(`::error file=${v.file},line=${v.line}::${v.message}`)
        }
    }
    console.log(`[持久化边界] 发现 ${violations.length} 处问题。请核对事务入口、连接和执行方式，不得扩大为整文件放行。`)
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
    extractReviewedSpan, checkBoundary, readGitSnapshotSource }
