'use strict'
// Read-only closure check of an explicit upgraded isolated DB. No application initialization.
const fs=require('node:fs'),path=require('node:path'),Sqlite=require('better-sqlite3'),{createHash}=require('node:crypto')
const args=process.argv.slice(2),value=name=>{const i=args.indexOf('--'+name);if(i<0||!args[i+1])throw Error('Missing --'+name);return args[i+1]}
const coverage=JSON.parse(fs.readFileSync(value('coverage'),'utf8'))
const {createContentOperationsStore}=require('../out/lib/content-operations')
const {julyContentPlan}=require('../out/lib/content-operations-bootstrap')
const db=new Sqlite(fs.realpathSync(value('database')),{readonly:true,fileMustExist:true})
try {
    db.pragma('query_only = ON')
    const store=createContentOperationsStore(db),now=Date.now(),records=[],failures=[]
    for(const row of coverage.rows.filter(row=>row.fixedDayCandidate)) {
        const capabilities=store.capabilities(store.rows.get(row.key)),runtime=store.runtimeDefinitions.get(row.key)
        const actions=Object.fromEntries(row.enabledActions.map(action=>[action,store.allowed(row.key,action,now)]))
        const failedActions=Object.entries(actions).filter(([,allowed])=>allowed!==true).map(([action])=>action)
        const questFailures=row.quests.filter(member=>store.scopedAllowed(row.key,'quest',member.key,'enter',now)!==member.fixedDayCandidate)
        const record={key:row.key,definitionReady:runtime.matchesCatalog,capabilities,actions,
            exchangeOnlyExistingRights:row.exchangeOnlyExistingRights,
            allowedQuestScopes:row.quests.filter(member=>member.fixedDayCandidate).length,
            excludedQuestScopes:row.quests.filter(member=>!member.fixedDayCandidate).length,
            failedActions,questFailures:questFailures.map(member=>member.key)}
        records.push(record)
        if(!record.definitionReady||failedActions.length||questFailures.length)failures.push(record)
    }
    const result={schemaVersion:1,referenceDate:coverage.referenceDate,readOnly:true,revision:store.revision(),catalogDigest:store.digest,
        planDigest:createHash('sha256').update(JSON.stringify(julyContentPlan)).digest('hex'),
        candidateCount:records.length,allowedQuestScopes:records.reduce((n,row)=>n+row.allowedQuestScopes,0),
        excludedQuestScopes:records.reduce((n,row)=>n+row.excludedQuestScopes,0),failures,records,
        limitation:'Action/mapping/definition closure; original player unlock, weekdays, tickets, quotas and real-device navigation require their business and device checks.'}
    fs.writeFileSync(path.resolve(value('output')),JSON.stringify(result,null,2)+'\n')
    console.log(JSON.stringify({candidateCount:result.candidateCount,allowedQuestScopes:result.allowedQuestScopes,
        excludedQuestScopes:result.excludedQuestScopes,failures:failures.map(row=>row.key)}))
    if(failures.length)process.exitCode=1
} finally {db.close()}
