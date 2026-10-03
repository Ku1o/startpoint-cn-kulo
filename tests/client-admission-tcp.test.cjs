const assert = require('node:assert/strict'), fs = require('node:fs'), path = require('node:path'), os = require('node:os'), net = require('node:net'), crypto = require('node:crypto')
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'sp-admission-tcp-'))
process.env.DATA_DIR=path.join(dir,'data');process.env.SESSION_HOST='127.0.0.1'
process.env.CLIENT_ADMISSION_CONFIG=path.join(dir,'config.json');process.env.CLIENT_ADMISSION_KEYS=path.join(dir,'keys.json')
const key=crypto.randomBytes(32).toString('hex'), iosKey=crypto.randomBytes(32).toString('hex'), policy={enforce:true,updateMessage:'请到群聊更新。',builds:[{id:'tcp-build',platform:'android',name:'TCP test',enabled:true,allowUntil:null},{id:'ios-build',platform:'ios',name:'iOS test',enabled:true,allowUntil:null}]}
const save=()=>fs.writeFileSync(process.env.CLIENT_ADMISSION_CONFIG,JSON.stringify(policy))
save();fs.writeFileSync(process.env.CLIENT_ADMISSION_KEYS,JSON.stringify({'tcp-build':key,'ios-build':iosKey}))
require('ts-node/register/transpile-only')
const prefix=process.env.ADMISSION_TEST_BUILT==='1'?'../out/':'../src/'
const {clientAdmission,proofMessage}=require(prefix+'lib/client-admission')
const {sessionManager}=require(prefix+'multi/state/SessionManager')
const indexedSockets=new WeakSet();let delayedHandshake=false,closedHandshakeStarted,closedHandshakeSocket,dispatched=0,checks=0
const check=(v,m)=>{assert.ok(v,m);checks++}
async function main(){
  const reserve=net.createServer();await new Promise(r=>reserve.listen(0,'127.0.0.1',r));const port=reserve.address().port;await new Promise(r=>reserve.close(r));process.env.SESSION_PORT=String(port)
  // Real wire parser and admission checks; only game room handlers are replaced
  // so no unrelated combat state is required for this protocol-boundary test.
  require(prefix+'multi/tcp/handshake').handleHandshake=async (socket,data)=>{
    if(data.close_during_handshake){
      closedHandshakeSocket=socket;closedHandshakeStarted?.()
      await new Promise(resolve=>setTimeout(resolve,25))
      const client=sessionManager.createClient(socket,999,'closed-handshake-room','closed-handshake-cid',999)
      sessionManager.addClientToRoom(client)
      return
    }
    if(delayedHandshake)await new Promise(resolve=>setImmediate(resolve))
    indexedSockets.add(socket);socket.write('[0]\0')
  }
  require(prefix+'multi/tcp/battle').handleBattleMessage=socket=>{
    if(!indexedSockets.has(socket))return
    dispatched++;socket.write('[99]\0')
  }
  const server=require(prefix+'multi/tcp/server');await server.startSessionServer()
  const gate=clientAdmission();let now=Date.now();gate.now=()=>now
  const c=gate.challenge({build:'tcp-build',protocol:1},'local').data
  const proof=crypto.createHmac('sha256',Buffer.from(key,'hex')).update(proofMessage('tcp-build',c.challenge,c.nonce)).digest('hex')
  const ticket=gate.prove({challenge:c.challenge,proof},'local').data.token;gate.bind(ticket,'tcp-account-session')
  function connect(frame){return new Promise((resolve,reject)=>{const socket=net.connect(port,'127.0.0.1',()=>socket.write(JSON.stringify(frame)+'\0'));socket.setTimeout(3000,()=>{socket.destroy();reject(Error('timeout'))});socket.once('error',reject);socket.once('data',buf=>resolve({socket,data:JSON.parse(buf.toString().split('\0')[0])}))})}
  let r=await connect({socklet:'cooperation_battle',sp_session:'tcp-account-session'});check(r.data[0]===1&&r.data[1]==='CLIENT_ADMISSION_REQUIRED','missing ticket rejected at real TCP boundary');r.socket.destroy()
  r=await connect({socklet:'cooperation_battle',sp_session:'wrong',sp_admission:ticket});check(r.data[0]===1,'session substitution rejected');r.socket.destroy()
  r=await connect({socklet:'cooperation_battle',sp_session:'tcp-account-session',sp_admission:ticket});check(r.data[0]===0,'valid ticket reaches room handshake')
  delayedHandshake=true
  const coalesced=await new Promise((resolve,reject)=>{
    const frames=[],socket=net.connect(port,'127.0.0.1',()=>{
      socket.write(JSON.stringify({socklet:'cooperation_battle',sp_session:'tcp-account-session',sp_admission:ticket})+'\0[0]\0')
    })
    const timer=setTimeout(()=>{socket.destroy();reject(Error('coalesced handshake timeout'))},3000)
    socket.on('data',buf=>{
      for(const raw of buf.toString().split('\0').filter(Boolean))frames.push(JSON.parse(raw))
      if(frames.some(frame=>frame[0]===99)){clearTimeout(timer);resolve({socket,frames})}
    })
    socket.once('error',reject)
  })
  check(coalesced.frames.some(frame=>frame[0]===0)&&coalesced.frames.some(frame=>frame[0]===99),
    'coalesced post-handshake frame waits for async socket indexing')
  coalesced.socket.destroy();delayedHandshake=false
  const handshakeStarted=new Promise(resolve=>{closedHandshakeStarted=resolve})
  const closing=net.connect(port,'127.0.0.1',()=>closing.write(JSON.stringify({
    socklet:'cooperation_battle',sp_session:'tcp-account-session',sp_admission:ticket,
    close_during_handshake:true,
  })+'\0'))
  await handshakeStarted;closing.destroy()
  await new Promise(resolve=>setTimeout(resolve,60))
  check(sessionManager.findClientBySocket(closedHandshakeSocket)===undefined
      && sessionManager.getClient(999,'closed-handshake-room')===undefined,
    'peer close during async handshake cannot leave a stale indexed client')
  const ic=gate.challenge({build:'ios-build',platform:'ios',protocol:1},'local').data
  const iproof=crypto.createHmac('sha256',Buffer.from(iosKey,'hex')).update(proofMessage('ios-build',ic.challenge,ic.nonce)).digest('hex')
  const iticket=gate.prove({challenge:ic.challenge,proof:iproof},'local').data.token;gate.bind(iticket,'ios-session')
  const ir=await connect({socklet:'cooperation_battle',sp_session:'ios-session',sp_admission:iticket});check(ir.data[0]===0,'iOS uses same protected TCP boundary')
  async function ping(socket){const received=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('ping timeout')),2000);socket.once('data',buf=>{clearTimeout(timer);resolve(JSON.parse(buf.toString().split('\0')[0]))})});socket.write('[0]\0');check((await received)[0]===99,'valid post-handshake traffic dispatched')}
  // Advance only the injected admission clock: real sockets stay open for three simulated hours.
  // No HTTP or explicit renewal is made while both platforms are actively sending frames.
  const dispatchedBeforePings=dispatched
  for(let i=0;i<12;i++){now+=15*60000;await ping(r.socket);await ping(ir.socket)}
  check(dispatched-dispatchedBeforePings===24,'both platforms survive repeated 30-minute boundaries without explicit renew')
  now+=2*60000;const renewed=gate.renew(iticket,'ios-session','local')
  check(renewed.ok&&renewed.data.token===iticket,'short network gap and renewal preserve TCP token')
  await ping(ir.socket)
  const before=dispatched
  policy.builds[0].enabled=false;save();await new Promise(r=>setTimeout(r,2300))
  const closed=new Promise(resolve=>r.socket.once('close',resolve));r.socket.write('[0]\0');await closed
  check(dispatched===before,'file reload revokes already-connected TCP before next message')
  await ping(ir.socket)
  now+=31*60000
  const idleClosed=new Promise(resolve=>ir.socket.once('close',resolve));ir.socket.write('[0]\0');await idleClosed
  check(dispatched===before+1,'long-idle expired connection cannot execute gameplay during grace')
  check(gate.renew(iticket,'ios-session','local').ok,'bound iOS token can renew within grace')
  const reconnected=await connect({socklet:'cooperation_battle',sp_session:'ios-session',sp_admission:iticket})
  check(reconnected.data[0]===0,'renewed iOS ticket permits reconnect');reconnected.socket.destroy()
  await server.stopSessionServer();gate.close();console.log(JSON.stringify({passed:true,checks,realTcp:true,simulatedHours:3,platforms:['android','ios'],gameHandlersStubbed:true}))
}
main().catch(e=>{console.error(e);process.exitCode=1}).finally(()=>setImmediate(()=>process.exit(process.exitCode||0)))
