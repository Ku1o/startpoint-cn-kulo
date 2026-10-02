const test=require('node:test')
const assert=require('node:assert/strict')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os')
const {serialize,deserialize}=require('node:v8')
const {CnResponseWorkerPool}=require('../out/lib/cn-response-worker-pool')
const {encodeCnResponse}=require('../out/lib/cn-response-encoding')
const {unpack}=require('msgpackr')

const make=()=>({number:0xffffffff,binary:Buffer.from([0xce,0xff,0,0xfe]),date:new Date('2026-09-25Z'),
    nested:{key:'before'},rows:Array.from({length:2000},(_,id)=>({id:id+65536,text:'真实响应测试',value:null}))})
for(const failure of [false,true]) test(`queued objects retain exact send-time values, including fallback (${failure})`,async()=>{
    const dir=fs.mkdtempSync(path.join(os.tmpdir(),'object-worker-'))
    const stalled=path.join(dir,'stall.cjs')
    fs.writeFileSync(stalled,'require("node:worker_threads").parentPort.on("message",()=>{})')
    const pool=new CnResponseWorkerPool({size:1,...(failure?{workerPath:stalled,timeoutMs:150}:{})})
    const values=[make(),make(),make()]
    const originals=values.map(value=>deserialize(serialize(value)))
    try {
        const promises=values.map(payload=>pool.encode({payload},{offloadObject:true}))
        for(const value of values){value.nested.key='changed';value.binary.fill(1);value.rows.length=0}
        const results=await Promise.all(promises)
        for(let i=0;i<results.length;i++){
            const expected=await encodeCnResponse({payload:originals[i]})
            assert.deepEqual(results[i].body,expected.body)
            assert.deepEqual(unpack(Buffer.from(results[i].body,'base64')),originals[i])
        }
        assert.equal(pool.snapshot().retainedBytes,0)
        assert.equal(failure?pool.snapshot().fallback:pool.snapshot().completedObjects,3)
    }finally{await pool.close()}
})

test('small, disabled and quota-exhausted object responses preserve local encoding',async()=>{
    for(const options of [{size:0},{size:1,minimumObjectBytes:1e9},{size:1,maxPendingBytes:1}]){
        const pool=new CnResponseWorkerPool(options),payload=make()
        try{
            assert.deepEqual((await pool.encode({payload},{offloadObject:true})).body,(await encodeCnResponse({payload})).body)
            assert.equal(pool.snapshot().completedObjects,0);assert.equal(pool.snapshot().retainedBytes,0)
        }finally{await pool.close()}
    }
})
