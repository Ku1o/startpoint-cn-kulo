/* Exercise the actual server protocol with the complete private release pair. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto'),assert=require('node:assert/strict')
const root=path.resolve(__dirname,'../..'),pair='F:/codex/.codex/secrets/starpoint-client-admission/releases/author-1043-public-20260924'
const work='F:/codex/work/author-public-release-20260924/protocol'
fs.mkdirSync(work,{recursive:true});process.env.DATA_DIR=path.join(work,'data')
const {ClientAdmission,installClientAdmission,proofMessage}=require(path.join(root,'out/lib/client-admission'))
const Fastify=require(path.join(root,'node_modules/fastify'))
const config=path.join(work,'isolated-policy.json'),keyFile=path.join(pair,'config/client-admission.keys.json')
const policyBytes=fs.readFileSync(path.join(pair,'config/client-admission.json'))
const keys=JSON.parse(fs.readFileSync(keyFile,'utf8')),policy=JSON.parse(policyBytes)
const ids={android:'android-181-author-1043-20260924',ios:'ios-184-author-1043-20260924'}
const previous={android:'android-181-independent-party-20260923',ios:'ios-184-independent-party-20260923'}
const checks=[];let now=Date.now();const check=(value,name)=>{assert.ok(value,name);checks.push(name)}
const save=()=>fs.writeFileSync(config,JSON.stringify(policy));save()
const gate=new ClientAdmission(config,keyFile,()=>now,()=>{});check(gate.reload(),'complete pair loads')
const app=Fastify({logger:false});installClientAdmission(app,gate)
app.post('/player-auth/login',async()=>({ok:true,data:{token:'isolated-session'}}))
const post=(url,payload={},headers={})=>app.inject({method:'POST',url,payload,headers}).then(r=>r.json())
async function exchange(id,platform,key=keys[id]) {
 const challenge=await post('/client-admission/challenge',{protocol:1,build:id,platform})
 if(!challenge.ok)return challenge
 const proof=crypto.createHmac('sha256',Buffer.from(key,'hex')).update(proofMessage(id,challenge.data.challenge,challenge.data.nonce)).digest('hex')
 return post('/client-admission/prove',{challenge:challenge.data.challenge,proof})
}
async function main(){
 check(policy.enforce===true,'strict policy remains enabled')
 check(policy.builds.length===4,'two existing and two new builds retained')
 const grants={}
 for(const [platform,id] of Object.entries(ids)){
  const other=platform==='ios'?'android':'ios'
  check(!(await exchange(id,other)).ok,platform+' rejects wrong platform')
  check(!(await exchange(id,platform,keys[ids[other]])).ok,platform+' rejects other platform key')
  const grant=await exchange(id,platform)
  check(grant.ok&&grant.data.platform===platform,platform+' new formal proof passes')
  grants[platform]=grant.data.token
  check((await post('/player-auth/login',{}, {'x-sp-admission':grant.data.token})).ok,platform+' admitted login path passes')
  check(gate.check(grant.data.token,'isolated-session',true).ok,platform+' login response binds grant')
  check((await exchange(previous[platform],platform)).ok,platform+' previous formal build remains allowed')
 }
 now+=25*60000
 for(const platform of Object.keys(ids))check((await post('/client-admission/renew',{}, {'x-sp-admission':grants[platform],'x-sp-session':'isolated-session'})).ok,platform+' simulated-time renewal passes')
 for(const platform of Object.keys(ids)){
  const other=platform==='ios'?'android':'ios'
  policy.builds.find(r=>r.id===ids[platform]).enabled=false;save();check(gate.reload(),platform+' isolated policy reload')
  check(!(await exchange(ids[platform],platform)).ok,platform+' disabled build is rejected')
  check((await exchange(ids[other],other)).ok,platform+' revocation leaves other platform allowed')
  check((await exchange(previous[platform],platform)).ok,platform+' revocation leaves previous build allowed')
  policy.builds.find(r=>r.id===ids[platform]).enabled=true;save();gate.reload()
 }
 check(fs.readFileSync(path.join(pair,'config/client-admission.json')).equals(policyBytes),'release policy unchanged by tests')
 const result={passed:true,assertions:checks.length,checks,ids,previous,isolated_http_injection:true,simulated_time:true,device_tested:false,cloud_touched:false}
 fs.writeFileSync(path.join(work,'report.json'),JSON.stringify(result,null,2)+'\n')
 console.log(JSON.stringify({passed:true,assertions:checks.length,ids,cloud_touched:false}))
 await app.close()
}
main().catch(()=>{console.error('Release protocol verification failed; no keys or tickets are logged.');process.exitCode=1;gate.close()})
