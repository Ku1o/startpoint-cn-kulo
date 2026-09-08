// Runs a disposable Windows server fixture, never the source/runtime service.
const test=require('node:test')
const assert=require('node:assert/strict')
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),net=require('node:net')
const {spawn}=require('node:child_process')
const {createHash}=require('node:crypto')
const D=require('better-sqlite3')
const root=path.resolve(__dirname,'..')

function run(exe,args,options){
    return new Promise((resolve,reject)=>{
        const p=spawn(exe,args,{...options,windowsHide:true,stdio:['ignore','pipe','pipe']})
        let output=''
        p.stdout.on('data',v=>{output+=v});p.stderr.on('data',v=>{output+=v})
        const timer=setTimeout(()=>{p.kill();reject(Error('Fixture command timed out: '+output))},120000)
        p.on('error',e=>{clearTimeout(timer);reject(e)})
        p.on('exit',code=>{clearTimeout(timer);resolve({code,output})})
    })
}
function freePort(){return new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',reject);s.listen(0,'127.0.0.1',()=>{const p=s.address().port;s.close(()=>resolve(p))})})}

for(const injectedFailure of [false,true]) {
test(injectedFailure?'Windows ZIP failure restores the original program and database through the recovery entry':'Windows production-script entry stops only its fixture, upgrades and preserves progress during startup recovery',{skip:process.platform!=='win32'},async()=>{
    const project=fs.mkdtempSync(path.join(os.tmpdir(),'sp-windows-maintenance-'))
    const data=path.join(project,'.database');fs.mkdirSync(data)
    const env={...process.env,DATA_DIR:data,NODE_PATH:path.join(root,'node_modules')}
    let fixturePid
    try {
        const setup=await run(process.execPath,['-r','ts-node/register/transpile-only','-e',`
            const db=require('./src/data/db').getDb();
            const a=require('./src/data/domains/account').insertAccountSync({appId:'wf_cn',idpAlias:'',idpCode:'windows-test',idpId:'fixture',status:'normal'});
            const p=require('./src/data/domains/player').insertDefaultPlayerSync(a.id);
            require('./src/lib/mission/counters').addMissionCounterSync(p.id,{dimension:'clear',scopeType:'lifetime',scopeKey:'all'},123);
            db.close();
        `],{cwd:root,env})
        assert.equal(setup.code,0,setup.output)
        const files=['scripts/maintain-cn.ps1','scripts/start-cn-logged.ps1','scripts/set-cn-temp.ps1','out/storage-maintenance.js','out/lib/storage-layout.js','out/lib/maintenance-state.js','out/lib/receive-history-retention.js','out/lib/atomic-json-file.js']
        for(const f of files){const target=path.join(project,f);fs.mkdirSync(path.dirname(target),{recursive:true});fs.copyFileSync(path.join(root,f),target)}
        fs.writeFileSync(path.join(project,'out/cn-server.js'),`
            const fs=require('node:fs'),path=require('node:path'),http=require('node:http');
            const D=require('better-sqlite3');const db=new D(path.resolve(process.env.DATA_DIR,'wdfp_data.db'));db.pragma('journal_mode=WAL');
            const port=Number(process.env.CN_LISTEN_PORT);
            const server=http.createServer((req,res)=>res.end('fixture'));
            server.listen(port,'127.0.0.1',()=>{
                fs.writeFileSync(path.resolve(__dirname,'../.logs/cn-server-ready.json'),JSON.stringify({pid:process.pid,readyAt:new Date().toISOString(),port,database:path.resolve(db.name),storageLayoutVersion:require('./lib/storage-layout').getStorageLayoutVersion(db)}));
            });
        `)
        const port=await freePort()
        fs.writeFileSync(path.join(project,'.env'),`CN_LISTEN_PORT=${port}\n`)
        const scriptArgs=['-NoProfile','-ExecutionPolicy','Bypass','-File']
        const startup=await run('powershell.exe',[...scriptArgs,path.join(project,'scripts/start-cn-logged.ps1'),'-RetentionDays','7'],{cwd:project,env})
        assert.equal(startup.code,0,startup.output)
        const currentFile=path.join(project,'.logs/cn-server-current.json')
        const receipt=()=>JSON.parse(fs.readFileSync(currentFile,'utf8').replace(/^\uFEFF/,''))
        fixturePid=receipt().pid
        const originalPid=fixturePid
        // A real ZIP update exercises staging, hash checks, atomic replacement,
        // and the independent maintenance runtime used for recovery.
        const payload=path.join(project,'test-payload')
        const releaseFiles=[...new Set([...files,'out/cn-server.js','out/data/index.js','out/data/initializers/wdfpData.js','out/data/snapshots/player-snapshot.js','out/lib/mission/counters.js','out/lib/quest/recommended-party-history.js','out/routes/api/quest.js','out/lib/mode15.js','out/lib/mode15-optional.js'])]
        const manifest={format:1,files:[]}
        for(const f of releaseFiles){
            const target=path.join(payload,f);fs.mkdirSync(path.dirname(target),{recursive:true})
            const source=f==='out/cn-server.js'?path.join(project,f):path.join(root,f)
            let bytes=fs.readFileSync(source)
            if(f==='out/cn-server.js')bytes=Buffer.concat([bytes,Buffer.from('\n// Updated mock release.\n')])
            if(injectedFailure&&f==='out/storage-maintenance.js'){
                const original=bytes.toString('utf8')
                const changed=original.replace('checkpoint("backup-verified");','throw new Error("injected ZIP failure");')
                assert.notEqual(changed,original,'failure injection must be present')
                bytes=Buffer.from(changed)
            }
            fs.writeFileSync(target,bytes)
            manifest.files.push({path:f,sha256:createHash('sha256').update(bytes).digest('hex')})
        }
        fs.mkdirSync(path.join(payload,'_maintenance'));fs.writeFileSync(path.join(payload,'_maintenance/manifest.json'),JSON.stringify(manifest))
        const archive=path.join(project,'storage-update.zip')
        const psQuote=s=>"'"+s.replace(/'/g,"''")+"'"
        const zipped=await run('powershell.exe',['-NoProfile','-Command',`
            Add-Type -AssemblyName System.IO.Compression.FileSystem
            Add-Type -AssemblyName System.IO.Compression
            $payloadPath=${psQuote(payload)}
            $zip=[IO.Compression.ZipFile]::Open(${psQuote(archive)},[IO.Compression.ZipArchiveMode]::Create)
            try { Get-ChildItem -LiteralPath $payloadPath -Recurse -File | ForEach-Object {
                $member=$_.FullName.Substring($payloadPath.Length+1).Replace('\\','/')
                [IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip,$_.FullName,$member) | Out-Null
            } } finally { $zip.Dispose() }
        `],{cwd:project,env})
        assert.equal(zipped.code,0,zipped.output)
        // First installation has only the bootstrap scripts and update ZIP.
        // Preview must load its runtime from the ZIP without applying the update.
        fs.unlinkSync(path.join(project,'out/storage-maintenance.js'))
        const preview=await run('powershell.exe',[...scriptArgs,path.join(project,'scripts/maintain-cn.ps1'),'-Mode','Preview'],{cwd:project,env})
        assert.equal(preview.code,0,preview.output)
        assert.match(preview.output,/Storage layout: 0/)
        assert.equal(receipt().pid,originalPid)
        process.kill(originalPid,0)
        assert.equal(fs.existsSync(path.join(project,'out/storage-maintenance.js')),false)
        assert.doesNotMatch(fs.readFileSync(path.join(project,'out/cn-server.js'),'utf8'),/Updated mock release/)
        assert.equal(fs.existsSync(path.join(project,'.storage-maintenance/controller.json')),false)
        assert.equal(fs.existsSync(path.join(data,'storage-maintenance-state.json')),false)
        const previewCheck=new D(path.join(data,'wdfp_data.db'),{readonly:true})
        try {
            assert.equal(previewCheck.prepare("SELECT type FROM sqlite_master WHERE name='players_mission_counters'").get().type,'table')
            assert.equal(previewCheck.prepare('SELECT value FROM players_mission_counters').get().value,123)
        } finally {previewCheck.close()}
        const apply=await run('powershell.exe',[...scriptArgs,path.join(project,'scripts/maintain-cn.ps1'),'-Mode','Apply'],{cwd:project,env})
        fixturePid=receipt().pid
        if(injectedFailure){
            assert.notEqual(apply.code,0)
            assert.match(apply.output,/injected ZIP failure/)
            assert.match(fs.readFileSync(path.join(project,'out/cn-server.js'),'utf8'),/Updated mock release/)
            const recovered=await run('powershell.exe',[...scriptArgs,path.join(project,'scripts/maintain-cn.ps1'),'-Mode','Recover'],{cwd:project,env})
            fixturePid=receipt().pid
            assert.equal(recovered.code,0,recovered.output.slice(-7000))
            assert.doesNotMatch(fs.readFileSync(path.join(project,'out/cn-server.js'),'utf8'),/Updated mock release/)
            const check=new D(path.join(data,'wdfp_data.db'),{readonly:true})
            try{
                assert.equal(check.prepare("SELECT type FROM sqlite_master WHERE name='players_mission_counters'").get().type,'table')
                assert.equal(check.prepare('SELECT value FROM players_mission_counters').get().value,123)
            }finally{check.close()}
            assert.equal(JSON.parse(fs.readFileSync(path.join(data,'storage-maintenance-state.json'),'utf8')).phase,'rolled-back')
            return
        }
        assert.equal(apply.code,0,apply.output.slice(-7000))
        assert.notEqual(fixturePid,originalPid)
        assert.match(fs.readFileSync(path.join(project,'out/cn-server.js'),'utf8'),/Updated mock release/)
        const controller=JSON.parse(fs.readFileSync(path.join(project,'.storage-maintenance/controller.json'),'utf8'))
        assert.doesNotMatch(fs.readFileSync(path.join(controller.programBackup,'out/cn-server.js'),'utf8'),/Updated mock release/)
        const db=new D(path.join(data,'wdfp_data.db'))
        try {
            assert.equal(db.prepare("SELECT type FROM sqlite_master WHERE name='players_mission_counters'").get().type,'view')
            db.prepare('UPDATE players SET total_stamina_used=999').run()
        } finally {db.close()}
        const statePath=path.join(data,'storage-maintenance-state.json')
        const state=JSON.parse(fs.readFileSync(statePath,'utf8'));state.phase='service-starting';fs.writeFileSync(statePath,JSON.stringify(state))
        fs.writeFileSync(path.join(project,'.storage-maintenance/active.lock'),'')
        const recover=await run('powershell.exe',[...scriptArgs,path.join(project,'scripts/maintain-cn.ps1'),'-Mode','Recover'],{cwd:project,env})
        fixturePid=receipt().pid
        assert.equal(recover.code,0,recover.output)
        const check=new D(path.join(data,'wdfp_data.db'),{readonly:true})
        try {assert.equal(check.prepare('SELECT total_stamina_used FROM players').get().total_stamina_used,999)}finally{check.close()}
        assert.equal(JSON.parse(fs.readFileSync(statePath,'utf8')).phase,'completed')
        assert.equal(fs.existsSync(path.join(project,'.storage-maintenance/active.lock')),false)
    } finally {
        const currentFile=path.join(project,'.logs/cn-server-current.json')
        if(fs.existsSync(currentFile))fixturePid=JSON.parse(fs.readFileSync(currentFile,'utf8').replace(/^\uFEFF/,'')).pid
        if(fixturePid){try{process.kill(fixturePid)}catch{}}
        await new Promise(resolve=>setTimeout(resolve,600))
        fs.rmSync(project,{recursive:true,force:true,maxRetries:3,retryDelay:100})
    }
})
}
