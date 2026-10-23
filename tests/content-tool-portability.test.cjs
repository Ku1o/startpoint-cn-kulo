'use strict'
const { test } = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), os = require('node:os'), { execFileSync, spawnSync } = require('node:child_process')
const repo = path.resolve(__dirname, '..')
const { assertDiscoveryOutput } = require('../tools/build-content-discovery.cjs')
const { assertExportOutput } = require('../tools/export-content-presentation-images.cjs')
const roots = execFileSync('git', ['-c', 'core.quotePath=false', 'worktree', 'list', '--porcelain'], { cwd: repo, encoding: 'utf8', windowsHide: true })
    .split(/\r?\n/).filter(line => line.startsWith('worktree ')).map(line => fs.realpathSync(line.slice(9)))
function temporary(t) {
    const parent = path.resolve(process.env.STARPOINT_TEST_TMP_ROOT || os.tmpdir())
    const directory = fs.mkdtempSync(path.join(parent, 'content-portability-'))
    t.after(() => { assert.equal(path.dirname(directory), parent); fs.rmSync(directory, { recursive: true }) })
    return directory
}
test('Git-discovered primary root and junction aliases stay protected while discovery remains worktree-only', t => {
    assert.ok(roots.length)
    const directory = temporary(t), alias = path.join(directory, 'primary-alias')
    fs.symlinkSync(roots[0], alias, process.platform === 'win32' ? 'junction' : 'dir')
    for (const root of [roots[0], alias]) {
        assert.throws(() => assertDiscoveryOutput(repo, path.join(root, 'assets/content_discovery.json')), /Protected source output/)
        assert.throws(() => assertExportOutput(repo, path.join(root, 'assets/unused-portable-export')), /outside code\/resource roots/)
    }
    if (fs.realpathSync(repo) !== roots[0]) assert.equal(assertDiscoveryOutput(repo, path.join(repo, 'assets/content_discovery.json')), path.join(repo, 'assets/content_discovery.json'))
    assert.throws(() => assertDiscoveryOutput(repo, path.join(directory, 'unapproved.json')), /worktree discovery index/)
    assert.equal(assertExportOutput(repo, path.join(directory, 'new-export')), path.join(directory, 'new-export'))
    fs.unlinkSync(alias)
})
test('portable Python guards discover real primary source, reject aliases/CDN/export overlap, and use bundled ASCII labels', t => {
    const directory = temporary(t)
    const script = String.raw`import importlib.util,pathlib,sys
sys.dont_write_bytecode=True
repo=pathlib.Path(sys.argv[1]).resolve();target=pathlib.Path(sys.argv[2]).resolve();primary=pathlib.Path(sys.argv[3]).resolve()
def load(name,file):
 spec=importlib.util.spec_from_file_location(name,repo/'tools'/file);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
gacha=load('portable_gacha','build-content-discovery-gacha.py');thumb=load('portable_thumb','build-content-thumbnails.py')
export=target/'source'/'source-exports.json';resource=target/'resources'
for module,call in [(gacha,lambda p:gacha.safe_output(p,resource,repo)),(thumb,lambda p:thumb.guarded_output(p,export))]:
 for p in [primary/'assets'/'must-not-write.json',target/'.cdn'/'must-not-write.json']:
  try:call(p)
  except ValueError:pass
  else:raise AssertionError('protected output accepted: '+str(p))
 assert call(target/'allowed-output')==target/'allowed-output'
assert gacha.safe_output(pathlib.Path(str(primary)+'-sibling')/'allowed.json',resource,repo)==pathlib.Path(str(primary)+'-sibling')/'allowed.json'
try:thumb.guarded_output(export.parent/'overwrite',export)
except ValueError:pass
else:raise AssertionError('source export overlap accepted')
image=thumb.Image.new('RGBA',(4,4),(10,20,30,255));source={'source':{},'rows':{k:{'sourcePngSha256':'fixture','sourceLogical':k} for k in ['gacha:3','gacha:1704','rush_event:700011']}}
originals={'fixture':{'image':image,'resized':image,'bytes':b'fixture'}}
report=thumb.compare_samples(source,originals,target/'comparison');assert len(report['samples'])==3
print('portable_guards_and_ascii_font_passed')`
    const run = spawnSync('python', ['-B', '-c', script, repo, directory, roots[0]], { cwd: repo, encoding: 'utf8' })
    assert.equal(run.status, 0, run.stderr); assert.match(run.stdout, /portable_guards_and_ascii_font_passed/)
})
