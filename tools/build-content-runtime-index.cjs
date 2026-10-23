'use strict'
// Offline projection only. Canonical catalogs, audit evidence and their digests
// remain untouched; the server never rebuilds these projections on a request.
const fs = require('node:fs'), path = require('node:path'), { createHash } = require('node:crypto')
const characterLabels = { up: 'UP角色', pool: '池内可获得角色', exchange: '可兑换角色', reward: '奖励角色' }
const rewardLabels = { up: 'UP装备', pool: '池内可获得装备', drop: '关卡掉落', firstClear: '首次通关奖励', mission: '任务奖励', box: '箱池奖励', exchange: '兑换奖励', ranking: '排行奖励', overall: '全体奖励', pass: '通行证奖励' }
const normalize = value => value.normalize('NFKC').toLocaleLowerCase().replace(/[\p{P}\p{S}\s]/gu, '')
function digest(file) {
    const hash = createHash('sha256'), buffer = Buffer.allocUnsafe(64 * 1024), fd = fs.openSync(file, 'r')
    try { let count; while ((count = fs.readSync(fd, buffer, 0, buffer.length, null))) hash.update(buffer.subarray(0, count)) }
    finally { fs.closeSync(fd) }
    return hash.digest('hex')
}
function historyProjection(document, canonicalSha256) {
    if (document.schemaVersion !== 1 || !Array.isArray(document.rows)) throw new Error('Invalid readiness source')
    const keys = new Set()
    const rows = document.rows.map(row => {
        if (typeof row.key !== 'string' || keys.has(row.key)) throw new Error('Duplicate readiness parent')
        keys.add(row.key)
        const actions = Object.fromEntries(Object.entries(row.actions || {}).map(([action, review]) => [action, {
            ...(review.status === undefined ? {} : { status: review.status }),
            ...(review.blockers === undefined ? {} : { blockers: review.blockers.map(blocker => typeof blocker.message === 'string' ? { message: blocker.message } : {}) }),
        }]))
        return { key: row.key, actions, ...(row.nativePage ? { nativePage: row.nativePage } : {}),
            ...(row.dependencies?.boxGachaKeys ? { dependencies: { boxGachaKeys: row.dependencies.boxGachaKeys } } : {}) }
    })
    return { schemaVersion: 1, canonicalSha256, rows }
}
function discoveryProjection(document, canonicalSha256) {
    if (document.schemaVersion !== 1 || !document.rows || !document.sourceInputs) throw new Error('Invalid discovery source')
    const characters = [], rewards = [], charMap = new Map(), rewardMap = new Map(), rows = {}
    function reference(entity, dictionary, map, labels, character) {
        const identity = JSON.stringify(entity)
        if (!map.has(identity)) {
            const reason = `${labels[entity.relation] || '关联奖励'}：${entity.name}`
            map.set(identity, dictionary.length)
            dictionary.push({ entity, fields: [entity.name, ...(entity.aliases || [])].map(name => ({
                text: normalize(name), reason, weight: character ? entity.relation === 'up' ? 80 : 50 : 55,
            })) })
        }
        return map.get(identity)
    }
    for (const [key, row] of Object.entries(document.rows)) {
        const highlights = []
        for (const relation of ['up', 'pool', 'reward', 'exchange']) {
            const entities = row.characters.filter(entity => entity.relation === relation)
            if (entities.length) highlights.push({ label: characterLabels[relation], names: [...new Set(entities.map(entity => entity.name))].slice(0, 8), total: entities.length })
        }
        const groups = new Map()
        for (const entity of row.rewards) {
            const label = rewardLabels[entity.relation] || '关联奖励'
            if (!groups.has(label)) groups.set(label, [])
            groups.get(label).push(entity)
        }
        for (const [label, entities] of groups) highlights.push({ label, names: [...new Set(entities.map(entity => entity.name))].slice(0, 8), total: entities.length })
        rows[key] = { characters: row.characters.map(entity => reference(entity, characters, charMap, characterLabels, true)),
            rewards: row.rewards.map(entity => reference(entity, rewards, rewardMap, rewardLabels, false)),
            aliases: row.aliases, ...(row.editionLabel === undefined ? {} : { editionLabel: row.editionLabel }),
            publicNotes: row.publicNotes || [], status: row.status, highlights }
    }
    return { schemaVersion: 2, canonicalSha256, source: document.source, sourceInputs: document.sourceInputs, characters, rewards, rows }
}
function build(root) {
    const project = path.resolve(root), read = name => JSON.parse(fs.readFileSync(path.join(project, 'assets', name), 'utf8'))
    const history = historyProjection(read('content_history_readiness.json'), digest(path.join(project, 'assets/content_history_readiness.json')))
    const discovery = discoveryProjection(read('content_discovery.json'), digest(path.join(project, 'assets/content_discovery.json')))
    const parentKeys = Object.keys(read('content_presentation.json').rows).sort()
    if (JSON.stringify(history.rows.map(row => row.key).sort()) !== JSON.stringify(parentKeys)
        || JSON.stringify(Object.keys(discovery.rows).sort()) !== JSON.stringify(parentKeys)) throw new Error('Parent coverage mismatch')
    const outputs = { 'content_history_readiness_runtime.json': history, 'content_discovery_runtime.json': discovery }, sizes = {}
    for (const [name, value] of Object.entries(outputs)) {
        const bytes = JSON.stringify(value) + '\n', destination = path.join(project, 'assets', name)
        fs.writeFileSync(destination, bytes); sizes[name] = Buffer.byteLength(bytes)
    }
    return { parents: parentKeys.length, relations: Object.values(discovery.rows).reduce((sum, row) => sum + row.characters.length + row.rewards.length, 0),
        characterDictionary: discovery.characters.length, rewardDictionary: discovery.rewards.length, sizes }
}
module.exports = { historyProjection, discoveryProjection, build, digest }
if (require.main === module) console.log(JSON.stringify(build(process.argv[2] || path.resolve(__dirname, '..'))))
