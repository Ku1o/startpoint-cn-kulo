const test = require('node:test')
const assert = require('node:assert/strict')
const net = require('node:net')
const path = require('node:path')
const { execFile } = require('node:child_process')
const { promisify } = require('node:util')

test('TCP session startup rejects a busy port without publishing a live server', async () => {
    const occupied = net.createServer()
    await new Promise((resolve, reject) => {
        occupied.once('error', reject)
        occupied.listen(0, '127.0.0.1', resolve)
    })
    const port = occupied.address().port
    try {
        const source = `
            process.env.SESSION_HOST = '127.0.0.1';
            process.env.SESSION_PORT = ${JSON.stringify(String(port))};
            const sessions = require('./out/multi/tcp/server');
            sessions.startSessionServer().then(
                () => { console.error('unexpected listen success'); process.exit(2); },
                error => {
                    if (error?.code !== 'EADDRINUSE') {
                        console.error(error);
                        process.exit(3);
                    }
                    process.stdout.write('EADDRINUSE');
                    process.exit(0);
                },
            );
        `
        const { stdout } = await promisify(execFile)(process.execPath, ['-e', source], {
            cwd: path.resolve(__dirname, '..'),
            timeout: 10_000,
            windowsHide: true,
        })
        assert.ok(stdout.endsWith('EADDRINUSE'), stdout)
    } finally {
        await new Promise(resolve => occupied.close(resolve))
    }
})
