'use strict'
// Compare compiled server rules with the six exact current CDN master tables.
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),Module=require('node:module'),ts=require('typescript')
const args=process.argv.slice(2),get=name=>args[args.indexOf('--'+name)+1]
for(const name of ['repo','master','sources','output'])if(!args.includes('--'+name))throw Error('missing --'+name)
const root=path.resolve(get('repo')),read=file=>JSON.parse(fs.readFileSync(file,'utf8'))
const sha=x=>crypto.createHash('sha256').update(x).digest('hex')
const loadTs=file=>{const filename=path.join(root,file),instance=new Module(filename,module)
    instance._compile(ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2020,esModuleInterop:true}}).outputText,filename)
    return instance.exports}
const stable=value=>value===undefined?'null':Array.isArray(value)?`[${value.map(stable).join(',')}]`:
    value!==null&&typeof value==='object'?`{${Object.keys(value).sort().map(key=>`${JSON.stringify(key)}:${stable(value[key])}`).join(',')}}`:JSON.stringify(value)
const hash=value=>sha(stable(value))
const catalog=read(path.join(root,'assets/content_catalog.json')),master=read(get('master')),sources=read(get('sources'))
if(!sources.allRowsMatched||sources.manifestSha256!==sha(fs.readFileSync(path.join(root,'assets/asset-patch/manifest.json'))))throw Error('current effective chain changed')
for(const [logical,table] of Object.entries(master))if(sources.masterSources[logical]?.sha256!==table.sha256)throw Error('unbound source: '+logical)
const defs=loadTs('src/lib/exchange-campaign-definitions.ts')
const logical={special:'master/campaign/special_exchange/special_exchange_campaign.orderedmap',
    character:'master/campaign/special_exchange/special_exchange_campaign_character.orderedmap',
    equipment:'master/campaign/special_exchange/special_exchange_campaign_equipment.orderedmap',
    start:'master/campaign/start_dash_exchange/start_dash_exchange_campaign.orderedmap',
    term:'master/campaign/start_dash_exchange/start_dash_exchange_campaign_term.orderedmap',
    exclude:'master/campaign/start_dash_exchange/start_dash_exchange_campaign_exclude_character.orderedmap'}
const records=[]
for(const row of catalog.rows.filter(r=>['special_exchange_campaign','start_dash_exchange_campaign'].includes(r.type))){
    const id=String(row.id),special=row.type==='special_exchange_campaign'
    const primary=master[special?logical.special:logical.start].rows[id]?.[0]
    if(!primary||sha(JSON.stringify(primary))!==row.definitionDigest)throw Error('client master row differs: '+row.key)
    let expected,required
    if(special){
        const rewardType=Number(primary[3]),member=rewardType===0?logical.character:rewardType===1?logical.equipment:null
        if(!member)throw Error('unsupported reward type: '+row.key)
        required=[logical.special,member]
        expected={ticketItemId:Number(primary[9]),rewardType,rewardIds:(master[member].rows[id]??[]).map(value=>Number(value[0]))}
    }else{
        required=[logical.start,logical.term,logical.exclude]
        const terms=master[logical.term].rows[id]??{},exclude=master[logical.exclude].rows[id]??{}
        expected={ticketItemId:Number(primary[6]),terms:Object.keys(terms).map(Number),
            exclude:Object.fromEntries(Object.entries(exclude).map(([term,values])=>[term,values.map(value=>Number(value[0]))]))}
    }
    const actual=special?defs.SPECIAL_EXCHANGE_DEFINITIONS[id]:defs.START_DASH_EXCHANGE_DEFINITIONS[id]
    if(stable(actual)!==stable(expected))throw Error('server exchange rules differ from CDN master: '+row.key)
    const receipt={schemaVersion:1,key:row.key,clientDefinitionDigest:row.definitionDigest,
        runtimeDigest:hash({key:row.key,definition:actual}),manifestSha256:sources.manifestSha256,
        currentMasterSources:Object.fromEntries(required.map(source=>[source,master[source].sha256])),
        currentMasterArchives:Object.fromEntries(required.map(source=>[source,sources.masterSources[source].archive]))}
    row.campaignDefinitionEvidence=receipt
    row.definitionEvidence={status:'matched',serverSources:[],clientQuestMappings:0,serverQuestMatches:0,missingQuestKeys:[],issues:[]}
    records.push({key:row.key,clientMasterRowDigest:row.definitionDigest,ruleDigest:receipt.runtimeDigest,
        currentMasterSources:receipt.currentMasterSources,currentMasterArchives:receipt.currentMasterArchives})
}
if(records.length!==Object.keys(defs.SPECIAL_EXCHANGE_DEFINITIONS).length+Object.keys(defs.START_DASH_EXCHANGE_DEFINITIONS).length)
    throw Error('server/campaign key sets differ')
const result={schemaVersion:1,manifestSha256:sources.manifestSha256,records,allMatched:true,
    scope:'current CDN six-table parity and exchange-only runtime definition; no ticket purchase, entitlement, device or activation acceptance'}
fs.writeFileSync(get('output'),JSON.stringify(result,null,2)+'\n')
if(args.includes('--apply'))fs.writeFileSync(path.join(root,'assets/content_catalog.json'),JSON.stringify(catalog,null,2)+'\n')
console.log(JSON.stringify({campaigns:records.length,allMatched:true,applied:args.includes('--apply')}))
