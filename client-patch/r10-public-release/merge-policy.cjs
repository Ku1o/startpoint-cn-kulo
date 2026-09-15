// Produce a reviewed pair in a NEW directory; never edit live configuration.
const fs = require('node:fs'), path = require('node:path')
const ID = /^[A-Za-z0-9_-]{1,80}$/, HEX = /^[a-f0-9]{64}$/
function validate(config, keys) {
  if (!config || typeof config.enforce !== 'boolean' || !Array.isArray(config.builds)
      || config.builds.length > 256 || typeof config.updateMessage !== 'string'
      || !config.updateMessage.trim() || config.updateMessage.length > 500
      || Object.keys(config).some(k => !['enforce','builds','updateMessage'].includes(k))) throw Error('Invalid policy')
  if (!keys || Array.isArray(keys) || typeof keys !== 'object'
      || Object.entries(keys).some(([k,v]) => !ID.test(k) || typeof v !== 'string' || !HEX.test(v))) throw Error('Invalid private key table')
  const ids = new Set()
  for (const b of config.builds) {
    if (!b || typeof b.id !== 'string' || !ID.test(b.id) || ids.has(b.id)
        || typeof b.name !== 'string' || b.name.length > 100 || typeof b.enabled !== 'boolean'
        || (b.platform !== undefined && !['android','ios'].includes(b.platform))
        || Object.keys(b).some(k => !['id','name','platform','enabled','allowUntil'].includes(k))
        || !Object.hasOwn(keys,b.id)) throw Error('Invalid build or missing private pairing')
    if (b.allowUntil !== null && (typeof b.allowUntil !== 'string'
        || !/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)$/.test(b.allowUntil)
        || !Number.isFinite(Date.parse(b.allowUntil)))) throw Error('Invalid build expiry')
    ids.add(b.id)
  }
  if (Buffer.byteLength(JSON.stringify(config)) > 256*1024 || Buffer.byteLength(JSON.stringify(keys)) > 256*1024) throw Error('Pair exceeds server size limit')
}
function merge(existing, oldKeys, release, newKeys) {
  validate(existing,oldKeys);validate(release,newKeys)
  const policy = structuredClone(existing), keys = {...oldKeys}
  for (const build of release.builds) {
    const old = policy.builds.find(b => b.id === build.id)
    if (old && (old.platform ?? 'android') !== (build.platform ?? 'android')) throw Error('Existing ID platform conflict')
    if (Object.hasOwn(keys,build.id) && keys[build.id] !== newKeys[build.id]) throw Error('Existing ID key conflict; refusing rotation')
    if (!old) policy.builds.push(structuredClone(build))
    // For a re-run, preserve existing enabled/expiry/name and the current enforce/message.
    Object.defineProperty(keys,build.id,{value:newKeys[build.id],writable:true,enumerable:true,configurable:true})
  }
  validate(policy,keys)
  return {policy,keys}
}
module.exports = {merge,validate}
if (require.main === module) {
  try {
    const args = process.argv.slice(2)
    if (args.length !== 5) throw Error('Usage: node merge-policy.cjs existing-config existing-keys release-config release-keys NEW-output-directory')
    const read = file => JSON.parse(fs.readFileSync(file,'utf8').replace(/^\uFEFF/,''))
    const old = read(args[0]), oldKeys = fs.existsSync(args[1]) ? read(args[1]) : {}
    const result = merge(old,oldKeys,read(args[2]),read(args[3])), dir = path.resolve(args[4])
    if (dir.split(/[\\/]/).some(p => p.toLowerCase() === '.cdn')) throw Error('Read-only CDN boundary')
    fs.mkdirSync(dir,{mode:0o700})
    fs.writeFileSync(path.join(dir,'client-admission.keys.json'),JSON.stringify(result.keys,null,2)+'\n',{mode:0o600,flag:'wx'})
    fs.writeFileSync(path.join(dir,'client-admission.json'),JSON.stringify(result.policy,null,2)+'\n',{mode:0o600,flag:'wx'})
    console.log(JSON.stringify({output:dir,enforce:result.policy.enforce,allowedIds:result.policy.builds.map(b=>b.id),liveFilesModified:false}))
  } catch { console.error('Policy merge failed. Check arguments, policy validity, complete private pairing, ID conflicts and a new output directory. No live files were changed.');process.exitCode=1 }
}
