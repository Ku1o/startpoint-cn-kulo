#!/usr/bin/env node
'use strict'

/**
 * Guard for the compiled artifacts that must travel with a commit.
 *
 * `.gitignore` excludes the `out` directory while the runtime (and the cloud
 * service) executes from `out/`, so a subset of compiled files is tracked on
 * purpose. A compiled file that is new or ignored is invisible to a plain
 * `git add`: forgetting `git add -f` ships a commit that is missing a module.
 *
 * The check is deliberately scoped to this change set so it stays actionable:
 * for every changed TypeScript source under `src/`, the matching `.js` under
 * `out/` must exist, must be tracked, and (in staged mode) must be part of the
 * commit. Pre-existing untracked files elsewhere in `out/` are not reported.
 *
 * Usage:
 *   node tools/check-out-artifacts.cjs              # staged set (default)
 *   node tools/check-out-artifacts.cjs --worktree   # everything changed vs HEAD
 *
 * Exit code 1 means the commit would be incomplete. The script never modifies
 * files, never stages anything and never runs the build.
 */

const { execFileSync } = require('node:child_process')
const fs = require('node:fs')
const path = require('node:path')

const repoRoot = path.resolve(__dirname, '..')
const flags = new Set(process.argv.slice(2))
const mode = flags.has('--worktree') ? 'worktree' : 'staged'

if (flags.has('--help') || flags.has('-h')) {
    console.log('用法: node tools/check-out-artifacts.cjs [--worktree]')
    console.log('  默认检查已暂存（将要提交）的文件集合；--worktree 检查相对 HEAD 的全部改动。')
    process.exit(0)
}

function gitLines(...gitArgs) {
    const output = execFileSync('git', gitArgs, { cwd: repoRoot, encoding: 'utf8' }).trim()
    return output === '' ? [] : output.split(/\r?\n/)
}

function isTracked(relativePath) {
    try {
        execFileSync('git', ['ls-files', '--error-unmatch', '--', relativePath], {
            cwd: repoRoot,
            stdio: 'ignore',
        })
        return true
    } catch {
        return false
    }
}

function differsFromHead(relativePath) {
    return gitLines('diff', '--name-only', 'HEAD', '--', relativePath).length > 0
}

function compiledPathFor(sourcePath) {
    return `out/${sourcePath.slice('src/'.length).replace(/\.ts$/, '.js')}`
}

function changedFiles() {
    if (mode === 'staged') {
        return new Set(gitLines('diff', '--cached', '--name-only', '--diff-filter=ACMR'))
    }
    return new Set([
        ...gitLines('diff', 'HEAD', '--name-only', '--diff-filter=ACMR'),
        ...gitLines('ls-files', '--others', '--exclude-standard'),
    ])
}

const changed = changedFiles()
if (changed.size === 0) {
    console.log(`[out 检查] 模式=${mode}：没有检测到待检查的改动。`)
    process.exit(0)
}

const problems = []
const warnings = []
const rows = []

for (const sourcePath of changed) {
    if (!/^src\/.*\.ts$/.test(sourcePath)) continue
    const compiledPath = compiledPathFor(sourcePath)
    const absolute = path.join(repoRoot, compiledPath)
    rows.push(compiledPath)

    if (!fs.existsSync(absolute)) {
        problems.push(`${compiledPath} 不存在：请先运行 npm run build（对应 ${sourcePath}）`)
        continue
    }
    if (!isTracked(compiledPath)) {
        problems.push(`${compiledPath} 未被 Git 跟踪，提交时必须显式加入：git add -f ${compiledPath}`)
        continue
    }
    if (mode === 'staged') {
        if (differsFromHead(compiledPath) && !changed.has(compiledPath)) {
            problems.push(`${compiledPath} 内容已变化但没有加入本次提交：git add ${compiledPath}`)
        }
        continue
    }
    if (differsFromHead(compiledPath)) {
        warnings.push(`${compiledPath} 与 HEAD 不同，提交前记得加入`)
    }
    try {
        const sourceStat = fs.statSync(path.join(repoRoot, sourcePath))
        const compiledStat = fs.statSync(absolute)
        if (compiledStat.mtimeMs + 1_000 < sourceStat.mtimeMs) {
            warnings.push(`${compiledPath} 比源码旧，可能没有重新构建`)
        }
    } catch {
        // Timestamps are advisory only.
    }
}

console.log(`[out 检查] 模式=${mode}，改动文件 ${changed.size} 个，涉及编译产物 ${rows.length} 个。`)
for (const warning of warnings) console.log(`  ⚠ ${warning}`)
for (const problem of problems) console.log(`  ✖ ${problem}`)

if (problems.length > 0) {
    console.log(`[out 检查] 发现 ${problems.length} 项问题：按上面的提示补齐后再提交。`)
    process.exit(1)
}
console.log('[out 检查] 通过：本次改动涉及的编译产物都已纳入。')
