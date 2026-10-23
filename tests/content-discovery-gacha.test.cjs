const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawnSync } = require('node:child_process');

const repo = path.resolve(__dirname, '..');
const script = path.join(repo, 'tools/build-content-discovery-gacha.py');
function python(source) {
  const setup = `import importlib.util, sys\nfrom pathlib import Path\nsys.dont_write_bytecode=True\ns=importlib.util.spec_from_file_location('g',sys.argv[1]);g=importlib.util.module_from_spec(s);s.loader.exec_module(g)\n`;
  const result = spawnSync('python', ['-c', setup + source, script], { encoding: 'utf8' });
  assert.equal(result.status, 0, result.stderr || result.stdout);
}

test('UP requires explicit flag and a drawable entry; first-match exchange is preserved', () => {
  python(`p={'1':[{'id':1,'odds':10,'isRateUp':False,'isExchangeable':False}, {'id':2,'odds':10,'isRateUp':True}, {'id':3,'odds':0,'isRateUp':True,'isExchangeable':True}], '2':[{'id':1,'odds':10,'isExchangeable':True}]}\nr=g.pool_links(p)\nassert (1,'pool') in r and (1,'up') not in r and (1,'exchange') not in r\nassert (2,'up') in r and (3,'up') not in r and (3,'pool') not in r and (3,'exchange') in r\nassert (2,'up') not in g.pool_links(p, {'normal':[0,100], 'multiGuarantee':[0,100]})\nassert (4,'pool') in g.pool_links({'1':[{'id':4,'odds':0},{'id':5,'odds':0}]})\nassert (5,'pool') not in g.pool_links({'1':[{'id':4,'odds':0},{'id':5,'odds':0}]})`);
});

test('row order does not invent mismatches; game epithets distinguish variants; no invented translations', () => {
  python(`a=[{'id':1,'rank':5,'odds':10,'isRateUp':True},{'id':2,'rank':5,'odds':10,'isRateUp':False}]\nassert g.signature(a)==g.signature(list(reversed(a)))\na[1]['isRateUp']=True\nassert g.signature(a)!=g.signature([{'id':1,'rank':5,'odds':10,'isRateUp':True},{'id':2,'rank':5,'odds':10,'isRateUp':False}])\nt={'1':[['角色','roman','','原版称号']],'2':[['角色','roman','','换装称号']],'3':[['ユノ','roman','','風を操る天才魔道師']]}\nassert g.named_character(1,t)[0]!=g.named_character(2,t)[0]\nassert g.named_character(3,t)[1]=='ユノ'\ntry:g.named_character(4,t)\nexcept ValueError:pass\nelse:raise AssertionError('missing native name accepted')`);
});

test('output rejects source, resource root, .cdn and checkout', () => {
  python(`import tempfile\nroot=Path(tempfile.mkdtemp());repo=root/'repo';resource=root/'resource';repo.mkdir();resource.mkdir()\nprimary=Path(next(line[9:] for line in g.subprocess.run(['git','-c','core.quotePath=false','worktree','list','--porcelain'],cwd=Path(sys.argv[1]).resolve().parent.parent,check=True,encoding='utf8',stdout=g.subprocess.PIPE).stdout.splitlines() if line.startswith('worktree ')))\nfor p in [primary/'forbidden.json', resource/'forbidden.json', repo/'forbidden.json', root/'.cdn'/'forbidden.json']:\n try:g.safe_output(p,resource,repo)\n except ValueError:pass\n else:raise AssertionError(str(p))\nassert g.safe_output(root/'out'/'ok.json',resource,repo)==(root/'out'/'ok.json').resolve()\nimport shutil\nshutil.rmtree(root)`);
});

test('coverage and unavailable-state validation fail closed', () => {
  python(`p=[{'key':'gacha:1'}]\nr={'gacha:1':{'status':'verified','characters':[],'evidence':[{'source':'fixture'}]}}\ng.ensure_keys(r,p)\nfor value in [{}, {'gacha:1':{'status':'unavailable','characters':[{'id':1}],'evidence':[{}]}}]:\n try:g.ensure_keys(value,p)\n except ValueError:pass\n else:raise AssertionError('invalid coverage/state accepted')`);
});

test('stale presentation identity is rejected before native loading or writes', () => {
  python(`import tempfile,json,shutil,subprocess,hashlib\nr=Path(tempfile.mkdtemp());repo=r/'repo';resource=r/'resource';out=r/'out.json'\nfor b in [repo,resource]:(b/'assets/asset-patch').mkdir(parents=True);(b/'assets/asset-patch/manifest.json').write_text('{}')\n(repo/'assets/content_catalog.json').write_text(json.dumps({'source':{},'rows':[]}))\n(repo/'assets/content_presentation.json').write_text(json.dumps({'source':{'manifestSha256':'stale'},'rows':{}}))\np=subprocess.run([sys.executable,sys.argv[1],'--repo',str(repo),'--resource-root',str(resource),'--exporter','missing.py','--output',str(out),'--report',str(r/'report.json')],capture_output=True,text=True)\nassert p.returncode!=0 and 'presentation chain identity is stale' in p.stderr and not out.exists()\nshutil.rmtree(r)`);
});

const fixture = process.env.CONTENT_DISCOVERY_GACHA_FIXTURE;
test('full generated fixture matches every real consumer pool, campaign and native provenance', { skip: !fixture }, () => {
  const data = JSON.parse(fs.readFileSync(fixture, 'utf8'));
  const presentation = JSON.parse(fs.readFileSync(path.join(repo, 'assets/content_presentation.json'), 'utf8'));
  const types = new Set(['gacha','special_exchange_campaign','multi_special_exchange_campaign','start_dash_exchange_campaign']);
  const expected = Object.keys(presentation.rows).filter(k => types.has(presentation.rows[k].type));
  assert.deepEqual(Object.keys(data.rows).sort(), expected.sort());
  assert.equal(expected.length, 624);
  const merged = {};
  for (const file of ['gacha','gacha_cnmod','gacha_rank_p5b','gacha_midautumn_2026']) Object.assign(merged, JSON.parse(fs.readFileSync(path.join(repo, `assets/${file}.json`),'utf8')));
  let checked = 0;
  for (const key of expected) {
    const row = data.rows[key];
    assert.ok(row.evidence.length);
    assert.ok(Array.isArray(row.publicNotes));
    if (!key.startsWith('gacha:')) continue;
    const gacha = merged[key.split(':')[1]];
    const actual = (gacha.type===0 ? row.characters : row.rewards).map(c => `${c.id}:${c.relation}`).sort();
    const wanted = new Set(), first = new Map();
    const rates = gacha.rankRates || {normal:[50,250,700],multiGuarantee:[50,950]};
    const active = new Set();
    for (const weights of [rates.normal,rates.multiGuarantee]) {
      let positive = false;
      weights.forEach((v,i) => { if(v>0) {active.add(String(i+1)); positive=true;} });
      if(!positive) active.add('1');
    }
    for (const [bucket,items] of Object.entries(gacha.pool)) {
      for (const c of items) if(!first.has(c.id)) first.set(c.id,c);
      const positive = items.filter(c=>c.odds>0);
      if(active.has(bucket)) for(const c of positive.length ? positive : items.slice(0,1)) {
        wanted.add(`${c.id}:pool`);
        if(c.isRateUp===true) wanted.add(`${c.id}:up`);
      }
    }
    for (const c of first.values()) if(c.isExchangeable===true) wanted.add(`${c.id}:exchange`);
    assert.deepEqual(actual,[...wanted].sort(), key);
    assert.equal(row.status,'verified',key);
    checked++;
  }
  assert.equal(checked,588);
  assert.equal(data.rows['start_dash_exchange_campaign:1'].status,'unavailable');
  assert.equal(data.rows['start_dash_exchange_campaign:1'].characters.length,0);
  const conflict=data.rows['gacha:990004'];
  assert.ok(conflict.rewards.some(c=>c.id===5910101&&c.relation==='pool'));
  assert.ok(!conflict.rewards.some(c=>c.id===5910101&&c.relation==='up'));
  assert.ok(conflict.evidence.some(e=>e.kind==='native_server_rate_up_difference'));
  for(const row of Object.values(data.rows)) for(const c of [...row.characters,...row.rewards]) {
    assert.ok(c.name && !c.name.includes('\uFFFD'));
    assert.ok(['pool','up','exchange'].includes(c.relation));
  }
  const crypto=require('node:crypto');
  for(const [file,digest] of Object.entries(data.sourceInputs)) assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(repo,file))).digest('hex'),digest,file);
  assert.ok(data.resources.filter(r=>r.kind==='archive_member').every(r=>r.member&&r.archive&&/^[a-f0-9]{64}$/.test(r.sha256)));
});
