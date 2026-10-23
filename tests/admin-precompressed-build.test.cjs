'use strict'
const { test } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const zlib = require('node:zlib')

test('every final emitted HTML/large JS/CSS has byte-identical gzip and brotli sidecars', () => {
    const directory = process.env.ADMIN_PLATFORM_BUILD_DIR
    assert.ok(directory && path.isAbsolute(directory), 'Pass explicit staged ADMIN_PLATFORM_BUILD_DIR; never builds or modifies live dist')
    const walk = root => fs.readdirSync(root, { withFileTypes: true }).flatMap(entry => entry.isDirectory() ? walk(path.join(root, entry.name)) : [path.join(root, entry.name)])
    const files = walk(directory).filter(file => /\.(js|css|html)$/.test(file))
    const pages = ['Dashboard', 'Accounts', 'PlayerDetail', 'Mail', 'Seeds', 'TimeControl', 'Leaderboards', 'News', 'ContentOperations']
    for (const page of pages) assert.ok(files.some(file => new RegExp(`^${page}-.+\\.js$`).test(path.basename(file))), page)
    let compared = 0
    for (const file of files) {
        const original = fs.readFileSync(file)
        if (original.length < 1024 && !file.endsWith('.html')) continue
        assert.equal(original.includes('__VITE_PRELOAD__'), false, file)
        for (const extension of ['gz', 'br']) {
            const encoded = fs.readFileSync(`${file}.${extension}`)
            const decoded = extension === 'gz' ? zlib.gunzipSync(encoded) : zlib.brotliDecompressSync(encoded)
            assert.deepEqual(decoded, original, `${file}.${extension}`)
            compared++
        }
    }
    assert.ok(compared >= 22)
    console.log(JSON.stringify({ sourceFiles: files.length, sidecarsCompared: compared, pageChunks: pages.length, htmlCompared: true }))
})
