require('ts-node/register/transpile-only')
const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const { pathToFileURL } = require('node:url')
const { existsSync } = require('../src/lib/file-exists')

test('existence checks see creation, replacement and deletion without caching', t => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-file-exists-'))
    t.after(() => fs.rmSync(dir, { recursive: true }))
    const file = path.join(dir, '实时文件.json')
    assert.equal(existsSync(dir), true)
    assert.equal(existsSync(file), false)
    fs.writeFileSync(file, '{}')
    for (const input of [file, Buffer.from(file), pathToFileURL(file)]) assert.equal(existsSync(input), true)
    fs.renameSync(file, file + '.old')
    assert.equal(existsSync(file), false)
    fs.writeFileSync(file, 'replacement')
    assert.equal(existsSync(file), true)
    assert.equal(existsSync(path.join(file, 'child')), false)
    fs.unlinkSync(file)
    assert.equal(existsSync(file), false)
})

test('invalid paths and denied access retain the false-on-error contract', t => {
    for (const input of ['', '\0', null, undefined, 12, {}]) assert.equal(existsSync(input), false)
    if (process.platform !== 'win32') return
    t.mock.method(fs, 'statSync', () => { const error = new Error('denied'); error.code = 'EACCES'; throw error })
    assert.equal(existsSync(__filename), false)
})

test('Windows checks do not enter the leaking native existsSync binding', { skip: process.platform !== 'win32' }, t => {
    t.mock.method(fs, 'existsSync', () => { throw new Error('leaking binding called') })
    assert.equal(existsSync(__filename), true)
    assert.equal(existsSync(__filename + '.missing'), false)
})

test('directory links follow their targets and become missing when the target is removed', t => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-file-link-'))
    t.after(() => fs.rmSync(dir, { recursive: true }))
    const target = path.join(dir, 'target'), link = path.join(dir, 'link')
    fs.mkdirSync(target)
    fs.symlinkSync(target, link, process.platform === 'win32' ? 'junction' : 'dir')
    assert.equal(existsSync(link), true)
    fs.rmdirSync(target)
    assert.equal(existsSync(link), false)
})
