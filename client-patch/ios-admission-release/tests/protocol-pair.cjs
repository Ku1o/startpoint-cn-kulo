/* Real release pair + real account routes, isolated database and HTTP injection. */
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto')
const root=path.resolve(__dirname,'../../..'),[policyFile,keyFile,work]=process.argv.slice(2)
assert(policyFile&&keyFile&&work,'policy, private pairing and fresh work directory required')
assert(!fs.existsSync(work),'fresh test directory required');fs.mkdirSync(work,{recursive:true,mode:0o700})
process.env.DATA_DIR=path.join(work,'data')
require(path.join(root,'node_modules/ts-node/register/transpile-only'))
const {ClientAdmission,installClientAdmission,proofMessage}=require(path.join(root,'src/lib/client-admission'))
const auth=require(path.join(root,'src/lib/player-login')),routes=require(path.join(root,'src/routes/cn/playerLogin'))
auth.initializePlayerLogin()
const account=auth.registerPlayerLogin('IosAdmissionPairQA','IsolatedFixture123',true),session=account.token
const {pack,unpack}=require(path.join(root,'node_modules/msgpackr')),Fastify=require(path.join(root,'node_modules/fastify'))
const keys=JSON.parse(fs.readFileSync(keyFile,'utf8').replace(/^\uFEFF/,'')),policy=JSON.parse(fs.readFileSync(policyFile,'utf8').replace(/^\uFEFF/,''))
const ids={android:'android-181-r10-20260915',ios:'ios-184-admission-20260915'},checkNames=[]
function check(value,name){assert.ok(value,name);checkNames.push(name)}
check(policy.enforce===false,'delivery policy preserves transition mode')
check(Object.keys(keys).length===2&&Object.values(ids).every(id=>keys[id]),'both formal private pairings are present')
check(policy.builds.length===2&&Object.entries(ids).every(([platform,id])=>policy.builds.some(b=>b.id===id&&b.platform===platform&&b.enabled&&b.allowUntil===null)),'delivery policy permits both independent formal builds')
policy.enforce=true // Only the isolated candidate used below is made strict.
const config=path.join(work,'config.json');let now=Date.parse('2026-09-15T00:00:00Z'),mutations=0
const save=()=>fs.writeFileSync(config,JSON.stringify(policy));save()
let gate=new ClientAdmission(config,path.resolve(keyFile),()=>now,()=>{});gate.reload()
const proxy=new Proxy({},{get:(_o,name)=>typeof gate[name]==='function'?gate[name].bind(gate):gate[name]})
const app=Fastify({logger:false});installClientAdmission(app,proxy);routes.installPlayerLoginGuard(app);app.register(routes.default)
app.addHook('onSend',async(_req,reply,payload)=>reply.getHeader('content-type')==='application/x-msgpack'&&typeof payload==='object'?pack(payload):payload)
app.post('/api/index.php/qa-load',async()=>{mutations++;return {loaded:true}})
const post=(url,payload={},headers={})=>app.inject({method:'POST',url,payload,headers})
const headers=grant=>({'x-sp-admission':grant,'x-sp-session':session})
async function exchange(platform,key=keys[ids[platform]]){
 const c=(await post('/client-admission/challenge',{protocol:1,platform,build:ids[platform]})).json()
 if(!c.ok)return c
 const proof=crypto.createHmac('sha256',Buffer.from(key,'hex')).update(proofMessage(ids[platform],c.data.challenge,c.data.nonce)).digest('hex')
 return (await post('/client-admission/prove',{challenge:c.data.challenge,proof})).json()
}
const resume=grant=>post('/player-auth/resume',{token:session},headers(grant)).then(r=>r.json())
const renew=grant=>post('/client-admission/renew',{},headers(grant)).then(r=>r.json())
async function main(){
 for(const platform of Object.keys(ids)){
  const other=platform==='ios'?'android':'ios'
  check(!(await post('/client-admission/challenge',{protocol:1,platform:other,build:ids[platform]})).json().ok,platform+' rejects wrong platform')
  check(!(await exchange(platform,keys[ids[other]])).ok,platform+' rejects other platform key')
  const issued=await exchange(platform),grant=issued.data.token
  check(issued.ok&&issued.data.platform===platform&&issued.data.expires_in_ms===1800000,platform+' correct formal proof succeeds')
  check((await resume(grant)).ok,platform+' real account resume binds the grant')
  check((await post('/api/index.php/qa-load',{},headers(grant))).json().loaded,platform+' ordinary HTTP passes both guards')
  now+=1500000
  const renewed=await renew(grant)
  check(renewed.ok&&renewed.data.token===grant,platform+' proactive renewal preserves the grant')
  now+=31*60000
  const before=mutations,rejected=unpack((await post('/api/index.php/qa-load',{},headers(grant))).rawPayload).data_headers.client_admission
  check(rejected.action==='renew'&&mutations===before,platform+' expired business request is rejected before mutation')
  check((await renew(grant)).data.token===grant,platform+' authenticated late renewal recovers the same grant')
  now+=36*60000
  check((await renew(grant)).action==='handshake',platform+' long expiry requests a new handshake')
  const fresh=await exchange(platform);check(fresh.ok,platform+' new handshake after long expiry succeeds')
  const rebound=await resume(fresh.data.token)
  check(rebound.ok&&rebound.data.profile.viewer_id===account.profile.viewer_id,platform+' recovery preserves account identity')
 }
 const android=await exchange('android'),ios=await exchange('ios');await resume(android.data.token);await resume(ios.data.token)
 policy.builds.find(b=>b.id===ids.ios).enabled=false;save();gate.reload()
 check((await renew(ios.data.token)).action==='handshake','revoking iOS removes its grant and requires a fresh handshake')
 check((await exchange('ios')).action==='update','revoking iOS blocks a fresh proof')
 check((await renew(android.data.token)).ok,'revoking iOS leaves Android working')
 policy.builds.find(b=>b.id===ids.ios).enabled=true;save();gate.reload()
 const iosAgain=await exchange('ios');await resume(iosAgain.data.token)
 check(iosAgain.ok,'reenabling iOS permits a fresh grant')
 check((await renew(ios.data.token)).action==='handshake','reenabling iOS does not revive its revoked grant')
 policy.builds.find(b=>b.id===ids.android).enabled=false;save();gate.reload()
 check((await renew(android.data.token)).action==='handshake','revoking Android removes its own grant')
 check((await exchange('android')).action==='update','revoking Android blocks a fresh proof')
 check((await renew(iosAgain.data.token)).ok,'revoking Android leaves iOS working')
 policy.builds.find(b=>b.id===ids.android).enabled=true;save();gate.reload()
 gate=new ClientAdmission(config,path.resolve(keyFile),()=>now,()=>{});gate.reload()
 check((await renew(iosAgain.data.token)).action==='handshake','process restart asks for handshake instead of obsolete-build message')
 const restarted=await exchange('ios'),resumed=await resume(restarted.data.token)
 check(resumed.ok&&resumed.data.profile.viewer_id===account.profile.viewer_id,'restart handshake and resume preserve the account')
 check((await post('/api/index.php/qa-load',{},headers(restarted.data.token))).json().loaded,'ordinary request works after restart recovery')
 check(JSON.parse(fs.readFileSync(policyFile,'utf8').replace(/^\uFEFF/,'' )).enforce===false,'delivery policy remained unchanged during strict tests')
 const report={passed:true,assertions:checkNames.length,checks:checkNames,ids,real_account_routes:true,http_injected_not_device_test:true,business_handler:'isolated stub',cloud_touched:false}
 fs.writeFileSync(path.join(work,'protocol-results.json'),JSON.stringify(report,null,2)+'\n')
 console.log(JSON.stringify({passed:true,assertions:checkNames.length,ids,cloud_touched:false}))
 await app.close()
}
main().then(()=>process.exit(0),e=>{console.error(e?.stack||String(e));process.exit(1)})
