const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto')
const root = path.resolve(__dirname, '../..'), dir = path.join(root, 'outputs/client-admission-private')
const config = path.join(dir, 'client-admission.json'), action = process.argv[2]
const write = p => { const temp = config + '.next'; fs.writeFileSync(temp, JSON.stringify(p, null, 2)); fs.renameSync(temp, config) }
async function main() {
  const policy = JSON.parse(fs.readFileSync(config, 'utf8'))
  if (action === 'disable' || action === 'enable') { policy.builds[0].enabled = action === 'enable'; write(policy); console.log(action); return }
  if (action === 'strict' || action === 'compat') { policy.enforce = action === 'strict'; write(policy); console.log(action); return }
  if (action === 'bad-config') { fs.writeFileSync(config, '{'); console.log('invalid config written for retained-policy test'); return }
  const post = async (p,b,h={}) => (await fetch('http://127.0.0.1:8002'+p,{ method:'POST', headers:{'Content-Type':'application/json',...h},body:JSON.stringify(b)})).json()
  const keys=JSON.parse(fs.readFileSync(path.join(dir,'client-admission.keys.json'),'utf8')),build=policy.builds[0].id
  const c=await post('/client-admission/challenge',{build,protocol:1}); if(!c.ok)throw Error(c.code)
  const proof=crypto.createHmac('sha256',Buffer.from(keys[build],'hex')).update(`SP-ADMISSION-1\n${build}\n${c.data.challenge}\n${c.data.nonce}`).digest('hex')
  const p=await post('/client-admission/prove',{challenge:c.data.challenge,proof});if(!p.ok)throw Error(p.code)
  const result=await post('/player-auth/register',{username:'AdmissionQA01',password:'LocalTrial123',remember:false},{'X-SP-ADMISSION':p.data.token})
  console.log(JSON.stringify({ok:result.ok,code:result.code,viewer:result.data?.profile?.viewer_id}))
}
main().catch(e=>{console.error(e.message);process.exitCode=1})
