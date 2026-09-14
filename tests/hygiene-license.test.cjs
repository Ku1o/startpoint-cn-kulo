const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const assert = require('node:assert/strict')
const { spawnSync } = require('node:child_process')

const root = path.resolve(__dirname, '..')
const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'sp-hygiene-license-'))
const bash = process.argv[2] || 'bash'
function run(command, args) {
    const result = spawnSync(command, args, { cwd: fixture, encoding: 'utf8', windowsHide: true })
    if (result.error) throw result.error
    return result
}
function scan(expected, label) {
    const result = run(bash, ['scripts/check-hygiene.sh', '--all'])
    assert.equal(result.status, expected, label + '\n' + result.stdout + result.stderr)
}
try {
    assert.equal(run('git', ['init', '-q']).status, 0)
    fs.mkdirSync(path.join(fixture, 'scripts'), { recursive: true })
    fs.mkdirSync(path.join(fixture, 'tools/player-save-extractor'), { recursive: true })
    fs.copyFileSync(path.join(root, 'scripts/check-hygiene.sh'), path.join(fixture, 'scripts/check-hygiene.sh'))
    const licensePath = 'tools/player-save-extractor/NODE-LICENSE.txt'
    const original = fs.readFileSync(path.join(root, licensePath), 'utf8')
    const licenseTarget = path.join(fixture, licensePath)
    fs.writeFileSync(licenseTarget, original)
    assert.equal(run('git', ['add', '--', 'scripts/check-hygiene.sh', licensePath]).status, 0)
    scan(0, 'The unchanged upstream license must pass')

    // Construct synthetic addresses so the regression itself contains no private email.
    const address = ['hygiene-fixture', '@', 'gmail', '.com'].join('')
    for (const suffix of [address, address.toUpperCase()]) {
        fs.writeFileSync(licenseTarget, original + '\n' + suffix + '\n')
        scan(1, 'An additional email in the approved license must still fail')
    }
    fs.writeFileSync(licenseTarget, original)
    const copyrightLine = original.split(/\r?\n/).find(line => line.includes('Jean-Philippe Aumasson') && line.includes('@'))
    assert.ok(copyrightLine)
    fs.writeFileSync(path.join(fixture, 'unapproved.txt'), copyrightLine + '\n')
    assert.equal(run('git', ['add', '--', 'unapproved.txt']).status, 0)
    scan(1, 'The same line at another path must fail')
    fs.writeFileSync(path.join(fixture, 'unapproved.txt'), 'ordinary text\n')
    fs.writeFileSync(licenseTarget, original.replace(copyrightLine, copyrightLine + ' ' + address))
    scan(1, 'An altered attribution must not match the exception')
    fs.writeFileSync(licenseTarget, original)
    scan(0, 'The original license must pass after restoring the fixture')
    console.log('PASS: original license accepted; additional, uppercase, relocated and altered emails rejected')
} finally {
    const resolved = fs.realpathSync(fixture)
    assert.ok(resolved.startsWith(fs.realpathSync(os.tmpdir()) + path.sep))
    fs.rmSync(resolved, { recursive: true })
}
