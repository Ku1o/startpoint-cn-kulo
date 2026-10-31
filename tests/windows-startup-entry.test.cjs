'use strict'
// Direct invocation also uses native node:test: node this-file --repo <checkout> --scratch <external-directory>.
// Only three launchers and their temp helper are copied. Never execute the real project or database.
const { test, before } = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os')
const { spawnSync } = require('node:child_process')
const value = name => { const i = process.argv.indexOf(name); return i < 0 ? undefined : process.argv[i + 1] }
const repo = path.resolve(value('--repo') || process.env.STARPOINT_STARTUP_TEST_REPO || path.join(__dirname, '..'))
const scratch = path.resolve(value('--scratch') || process.env.STARPOINT_STARTUP_TEST_ROOT || path.join(os.tmpdir(), 'starpoint-startup-fixtures'))
const relative = (base, child) => { const p = path.relative(base, child); return p !== '' && !path.isAbsolute(p) && p !== '..' && !p.startsWith('..' + path.sep) }
const win = process.platform === 'win32'
const sources = ['start-cn-console.bat', 'start-cn-production.bat', 'scripts/start-cn-logged.ps1', 'scripts/set-cn-temp.ps1']
before(() => {
  if (!win) return
  assert(!relative(repo, scratch) && scratch !== repo, 'Fixture root must be outside the source checkout')
  for (const file of sources) assert(fs.statSync(path.join(repo, file)).isFile(), 'Launcher input missing: ' + file)
  assert.match(process.versions.node, /^24\./, 'Use the configured Node24 test runner')
  assert.equal(process.versions.modules, '137')
  fs.mkdirSync(scratch, { recursive: true })
})
function fixture(t, options = {}) {
  const root = fs.mkdtempSync(path.join(scratch, 'startup path with spaces '))
  assert(relative(scratch, root) && !relative(repo, root))
  t.after(() => { assert(relative(scratch, root)); fs.rmSync(root, { recursive: true, force: true }) })
  fs.mkdirSync(path.join(root, 'scripts')); fs.mkdirSync(path.join(root, 'out'))
  for (const file of sources) fs.copyFileSync(path.join(repo, file), path.join(root, file))
  fs.writeFileSync(path.join(root, '.env'), 'CN_LISTEN_PORT=65534\n')
  fs.writeFileSync(path.join(root, 'scripts/time-content-deployment.cjs'), `
    const fs=require('node:fs'),path=require('node:path');
    const root=path.resolve(__dirname,'..');
    if(process.argv[2]!=='verify'||process.argv[3]!=='--project'||path.resolve(process.argv[4])!==root)throw Error('Wrong fake verify invocation');
    fs.appendFileSync(path.join(root,'events.jsonl'),JSON.stringify({event:'verify',root,execPath:process.execPath})+'\\n');
    if(process.env.STARTUP_FIXTURE_VERIFY_FAIL==='1'){console.error('FIXTURE_MIGRATION_DENIED');process.exitCode=19}
  `)
  fs.writeFileSync(path.join(root, 'out/cn-server.js'), `
    const fs=require('node:fs'),path=require('node:path');
    const root=path.resolve(__dirname,'..');
    fs.appendFileSync(path.join(root,'events.jsonl'),JSON.stringify({event:'server',cwd:process.cwd(),root,execPath:process.execPath})+'\\n');
    console.log('FIXTURE_SERVER_REACHED');process.exitCode=Number(process.env.STARTUP_FIXTURE_EXIT||0);
  `)
  fs.writeFileSync(path.join(root, 'scripts/run-cn-logged.cjs'), `
    const fs=require('node:fs'),path=require('node:path');
    fs.appendFileSync(path.join(__dirname,'../events.jsonl'),JSON.stringify({event:'logger'})+'\\n');
    throw Error('FORBIDDEN_LOGGER_REACHED');
  `)
  const env = { ...process.env, NODE_OPTIONS: '--max-old-space-size=768', STARTUP_FIXTURE_EXIT: String(options.exit || 0), STARTUP_FIXTURE_VERIFY_FAIL: options.deny ? '1' : '0' }
  for (const key of Object.keys(env)) if (['starpoint_node24', 'node_path', 'data_dir'].includes(key.toLowerCase())) delete env[key]
  const pathKey = Object.keys(env).find(k => k.toLowerCase() === 'path') || 'PATH'
  // Resolve node through this runner's directory, then Windows system tools; never a foreign node on inherited PATH.
  const windows = env.SystemRoot || 'C:\\Windows'
  env[pathKey] = [...(options.omitPathNode ? [] : [path.dirname(process.execPath)]), path.join(windows, 'System32'), path.join(windows, 'System32/WindowsPowerShell/v1.0'), windows].join(path.delimiter)
  if (options.nodeRoot !== undefined) env.STARPOINT_NODE24 = options.nodeRoot
  const readEvents = () => fs.existsSync(path.join(root, 'events.jsonl')) ? fs.readFileSync(path.join(root, 'events.jsonl'), 'utf8').trim().split(/\r?\n/).filter(Boolean).map(JSON.parse) : []
  return { root, events: readEvents, run(entry) {
    const result = spawnSync(env.ComSpec || path.join(windows, 'System32/cmd.exe'), ['/d', '/c', 'call ' + entry], {
      cwd: root, env, input: '\r\n', encoding: 'utf8', windowsHide: true, timeout: 30000,
    })
    assert.ifError(result.error)
    return { ...result, output: result.stdout + '\n' + result.stderr }
  } }
}
function reached(result, f, exit) {
  assert.equal(result.status, exit, result.output)
  assert.match(result.output, /FIXTURE_SERVER_REACHED/)
  const events = f.events()
  assert.deepEqual(events.map(x => x.event), ['verify', 'server'])
  assert.equal(events[1].cwd.toLowerCase(), f.root.toLowerCase())
  for (const row of events) assert.equal(row.execPath.toLowerCase(), process.execPath.toLowerCase())
}
test('console reaches only the fake foreground entry from a spaced script path via PATH when portable Node is absent', { skip: !win }, t => {
  const f = fixture(t)
  assert(!fs.existsSync(path.join(f.root, 'tools/node24/node.exe')))
  reached(f.run('start-cn-console.bat'), f, 0)
})
test('console preserves fake service exit7 across PowerShell, BAT and pause', { skip: !win }, t => {
  const f = fixture(t, { exit: 7 })
  reached(f.run('start-cn-console.bat'), f, 7)
})
test('production migration refusal preserves failure and never reaches the logger or service', { skip: !win }, t => {
  const f = fixture(t, { deny: true }), result = f.run('start-cn-production.bat')
  assert.equal(result.status, 1, result.output)
  assert.match(result.output, /FIXTURE_MIGRATION_DENIED/)
  assert.deepEqual(f.events().map(x => x.event), ['verify'])
})
test('console shares the same migration refusal before reaching its fake service', { skip: !win }, t => {
  const f = fixture(t, { deny: true }), result = f.run('start-cn-console.bat')
  assert.equal(result.status, 1, result.output)
  assert.match(result.output, /FIXTURE_MIGRATION_DENIED/)
  assert.deepEqual(f.events().map(x => x.event), ['verify'])
})
test('explicit missing Node override is rejected instead of silently falling back to valid PATH', { skip: !win }, t => {
  const f = fixture(t, { nodeRoot: path.join(scratch, 'explicit missing node with spaces') }), result = f.run('start-cn-console.bat')
  assert.equal(result.status, 1, result.output)
  assert.match(result.output, /Node\.js runtime not found/)
  assert.deepEqual(f.events(), [])
})
test('a valid explicit Node override takes priority and still reaches only the fake entry', { skip: !win }, t => {
  const f = fixture(t, { nodeRoot: path.dirname(process.execPath), omitPathNode: true })
  reached(f.run('start-cn-console.bat'), f, 0)
})
test('both BAT routes refuse a fixture maintenance lock before verify/logger/server execution', { skip: !win }, t => {
  const f = fixture(t)
  fs.mkdirSync(path.join(f.root, '.storage-maintenance')); fs.writeFileSync(path.join(f.root, '.storage-maintenance/active.lock'), 'synthetic')
  for (const entry of ['start-cn-console.bat', 'start-cn-production.bat']) {
    const result = f.run(entry)
    assert.equal(result.status, 1, result.output)
    assert.match(result.output, /Storage maintenance is still active/)
  }
  assert.deepEqual(f.events(), [])
})