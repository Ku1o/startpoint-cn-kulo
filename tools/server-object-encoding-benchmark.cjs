// Input must be an isolated synthetic /load snapshot, never a production player response.
const fs=require('node:fs'),path=require('node:path')
const {deserialize}=require('node:v8')
const {performance}=require('node:perf_hooks')
const {setImmediate:tick,setTimeout:delay}=require('node:timers/promises')
const assert=require('node:assert/strict')
const root=path.resolve(process.env.PERF_MODULE_ROOT||path.join(__dirname,'..'))
const {CnResponseWorkerPool}=require(path.join(root,'out/lib/cn-response-worker-pool'))
const {encodeCnResponse}=require(path.join(root,'out/lib/cn-response-encoding'))
const {drainServerWorkPerformance}=require(path.join(root,'out/lib/server-work-performance'))
const input=deserialize(fs.readFileSync(process.argv[2]))
const pool=new CnResponseWorkerPool({size:2})
const count=1024,concurrency=8
async function main(){
    try{
        const expected=(await encodeCnResponse(input)).body
        await Promise.all(Array.from({length:concurrency},()=>pool.encode(input,{offloadObject:true})))
        drainServerWorkPerformance()
        const initial=pool.snapshot(),latencies=[],gaps=[]
        let previous=performance.now()
        const timer=setInterval(()=>{const now=performance.now();gaps.push(now-previous);previous=now},1)
        await delay(20);gaps.length=0;previous=performance.now()
        const elu=performance.eventLoopUtilization(),cpu=process.cpuUsage(),start=performance.now()
        for(let completed=0;completed<count;completed+=concurrency){
            await Promise.all(Array.from({length:concurrency},async()=>{
                const sent=performance.now(),result=await pool.encode(input,{offloadObject:true})
                latencies.push(performance.now()-sent);assert.deepEqual(result.body,expected)
            }))
            await tick()
        }
        const wallMs=performance.now()-start,cpuDelta=process.cpuUsage(cpu),loop=performance.eventLoopUtilization(elu)
        await delay(5);clearInterval(timer)
        latencies.sort((a,b)=>a-b)
        const state=pool.snapshot()
        const result={root,requests:count,concurrency,inputBytes:fs.statSync(process.argv[2]).size,wallMs,
            processCpuMs:(cpuDelta.user+cpuDelta.system)/1000,mainEluPct:loop.utilization*100,mainActiveMs:loop.active,
            latencyP95Ms:latencies[Math.ceil(count*.95)-1],timerMaxGapMs:Math.max(...gaps),
            workerCompleted:state.completed-initial.completed,workerObjectCompleted:(state.completedObjects||0)-(initial.completedObjects||0),
            fallback:state.fallback-initial.fallback,work:drainServerWorkPerformance(),equalResponses:count}
        fs.writeFileSync(process.argv[3],JSON.stringify(result,null,2))
        console.log(JSON.stringify(result))
    }finally{await pool.close()}
}
main().catch(error=>{console.error(error);process.exitCode=1})
