// Generates metadata for an explicitly materialized release tree. It does not
// commit, deploy, or create an overlay archive.
const fs=require('node:fs')
const path=require('node:path')
const {createHash}=require('node:crypto')

async function main(){
    const [releaseRoot,fileList]=process.argv.slice(2)
    if(!releaseRoot||!fileList)throw Error('Usage: node tools/storage_update_manifest.cjs <release-tree> <explicit-files.json>')
    const root=fs.realpathSync(releaseRoot)
    const files=JSON.parse(fs.readFileSync(fileList,'utf8'))
    if(!Array.isArray(files)||files.length===0)throw Error('Expected a non-empty explicit relative file list')
    const seen=new Set(),manifest={format:1,files:[]}
    for(const relative of files){
        if(typeof relative!=='string'||!/^[A-Za-z0-9_./-]+$/.test(relative)||relative.split('/').some(p=>!p||p==='.'||p==='..'))throw Error('Unsafe member path')
        if(/^(\.cdn|\.database|\.env[^/]*|\.git[^/]*|\.codex[^/]*|\.storage-maintenance|node_modules|logs|\.logs|tmp|work)(\/|$)/i.test(relative))throw Error('Protected member path: '+relative)
        if(seen.has(relative.toLowerCase()))throw Error('Duplicate member path: '+relative)
        seen.add(relative.toLowerCase())
        const file=path.resolve(root,relative)
        const resolved=fs.realpathSync(file)
        if(resolved!==file||!file.startsWith(root+path.sep)||!fs.statSync(file).isFile())throw Error('Member crosses a junction or is not a file: '+relative)
        const hash=createHash('sha256');for await(const chunk of fs.createReadStream(file))hash.update(chunk)
        manifest.files.push({path:relative,sha256:hash.digest('hex')})
    }
    const directory=path.join(root,'_maintenance')
    if(fs.existsSync(directory)&&fs.realpathSync(directory)!==directory)throw Error('Manifest directory crosses a junction')
    fs.mkdirSync(directory,{recursive:true})
    fs.writeFileSync(path.join(directory,'manifest.json'),JSON.stringify(manifest,null,2))
    console.log(`Manifest contains ${manifest.files.length} verified release files.`)
}
main().catch(error=>{console.error(error.message);process.exitCode=1})
