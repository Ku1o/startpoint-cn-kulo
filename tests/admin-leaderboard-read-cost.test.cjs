const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), test = require('node:test'), ts = require('typescript')
const sandbox = path.resolve(__dirname, '../tmp') + path.sep
for (const key of ['DATA_DIR','GACHA_SEED_DIR']) assert.ok(process.env[key] && path.resolve(process.env[key]).startsWith(sandbox), 'Use tools/run-isolated-check.cjs')
require.extensions['.ts'] = (module, file) => module._compile(ts.transpileModule(fs.readFileSync(file,'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true }}).outputText,file)
const Fastify = require('fastify'), db = require('../src/data/db.ts').getDb()
const competition = require('../src/lib/leaderboard/competition.ts').getLeaderboardCompetition('rush:700099:1')
const competitions = require('../src/lib/leaderboard/competition.ts')
const service = require('../src/lib/leaderboard/service.ts'), settlement = require('../src/lib/leaderboard/settlement.ts')
const app = Fastify(); app.register(require('../src/routes/web_api/leaderboards.ts').default, {prefix:'/api/leaderboards'})
const party = Object.fromEntries(['characterIds','unisonCharacterIds','equipmentIds','abilitySoulIds','evolutionImgLevels','unisonEvolutionImgLevels'].map(k=>[k,[null,null,null]]))
function player(name,idpCode='leiting') { const account=require('../src/data/domains/account.ts').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode,idpId:'',status:'normal'}); const p=require('../src/data/domains/player.ts').insertDefaultPlayerSync(account.id); require('../src/data/domains/player.ts').updatePlayerSync({id:p.id,name});return p.id }
let clock=1000000
function complete(id,ms) { for(let round=1;round<=2;round++){ const quest={category:competition.category,eventId:competition.eventId,folderId:competition.folderId,round,questId:700099000+round,totalRounds:2};assert.ok(service.startLeaderboardQuestSync(id,quest,clock));clock+=10000;service.finishLeaderboardQuestSync({playerId:id,quest,accomplished:true,clientBattleMs:ms,party,finishedAtMs:clock}) }}
const a=player('A'),b=player('B'),bot=player('Bot','rushbot');complete(a,1000);complete(a,2000);complete(b,500);complete(bot,200)
let countQueries=0;const prepare=db.prepare;db.prepare=function(sql){if(/^SELECT COUNT\(DISTINCT r\.player_id\)/.test(sql.trim()))countQueries++;return prepare.call(this,sql)}
test.after(async()=>{db.prepare=prepare;await app.close();db.close()})
test('summary omits rank scans, legacy list remains complete, detail reuses the same nonempty reward count',async()=>{
 await app.ready();await app.inject({url:'/api/leaderboards/'})
 countQueries=0;const summary=await app.inject({url:'/api/leaderboards/?summary=1'});assert.equal(summary.statusCode,200);const rows=summary.json();assert.equal(rows.length,competitions.getLeaderboardCompetitions().length);assert.ok(rows.every(r=>!('overview' in r)));assert.equal(countQueries,0)
 const old=await app.inject({url:'/api/leaderboards/'});assert.equal(old.statusCode,200);assert.ok(old.json().every(r=>r.overview.config && Array.isArray(r.overview.history)))
 countQueries=0;const detail=await app.inject({url:'/api/leaderboards/'+encodeURIComponent(competition.key)});assert.equal(detail.statusCode,200);const data=detail.json();assert.equal(countQueries,1);assert.equal(data.total,2);assert.equal(data.overview.total,data.total);assert.equal(data.rows.length,2);assert.deepEqual(data.rows.map(r=>r.displayName),['B','A']);assert.equal(data.rows[1].clearCount,2)
 assert.equal((await app.inject({url:'/api/leaderboards/?summary=bad'})).statusCode,400)
})
test('prepared overview is request-scoped and a later completed run updates the next request',async()=>{
 complete(b,300);countQueries=0;const response=await app.inject({url:'/api/leaderboards/'+encodeURIComponent(competition.key)});assert.equal(response.statusCode,200);const data=response.json();assert.equal(countQueries,1);assert.equal(data.rows[0].clearCount,2);assert.equal(data.rows[0].clientBattleMs,600)
 const season=competitions.getLeaderboardCompetitionSeasonSync(competition.key),view=settlement.getLeaderboardSeasonRewardViewSync(competition.key,season);assert.deepEqual(settlement.getLeaderboardSettlementOverviewSync(competition.key,{season,view}),settlement.getLeaderboardSettlementOverviewSync(competition.key))
})
