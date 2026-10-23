'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict'), net = require('node:net')
const { privateHost, reserve } = require('../tools/isolated-content-runtime-lan.cjs')
test('LAN host selection rejects public, loopback, wildcard and non-local addresses without binding', () => {
    const interfaces = { fixture: [{ family: 'IPv4', internal: false, address: '10.23.90.10' }] }
    assert.equal(privateHost('10.23.90.10', interfaces), '10.23.90.10')
    for (const host of ['0.0.0.0', '127.0.0.1', '8.8.8.8', '26.0.0.1', '::', '10.23.90.11']) assert.throws(() => privateHost(host, interfaces))
})
test('occupied-port preflight rejects without stopping its existing listener', async () => {
    const server = net.createServer(socket => socket.destroy())
    await new Promise(resolve => server.listen({ host: '127.0.0.1', port: 0 }, resolve))
    try { await assert.rejects(reserve('127.0.0.1', server.address().port), /occupied or unavailable/); assert.equal(server.listening, true) }
    finally { await new Promise(resolve => server.close(resolve)) }
})
