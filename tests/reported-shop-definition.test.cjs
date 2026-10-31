'use strict'
// Forward evidence for the three restored original Five Boss products.
const test = require('node:test'), assert = require('node:assert/strict')
const fs = require('node:fs'), path = require('node:path'), Module = require('node:module'), ts = require('typescript')
const root = path.resolve(__dirname, '..'), catalog = require('../assets/content_catalog.json')
const history = require('../assets/content_history_definition_evidence.json')
function helper(overrides = {}) {
    const filename = path.join(root, 'src/lib/content-definition-evidence.ts'), instance = new Module(filename, module)
    instance.filename = filename; instance.paths = Module._nodeModulePaths(path.dirname(filename))
    const original = instance.require.bind(instance)
    instance.require = name => name === 'node:fs' ? { ...fs,
        readFileSync: (file, ...args) => Object.hasOwn(overrides, path.resolve(file)) ? overrides[path.resolve(file)] : fs.readFileSync(file, ...args) }
        : name === './exchange-campaign-definitions' ? require('../out/lib/exchange-campaign-definitions') : original(name)
    instance._compile(ts.transpileModule(fs.readFileSync(filename, 'utf8'), { compilerOptions: {
        module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, esModuleInterop: true } }).outputText, filename)
    return instance.exports
}
function altered(file, mutate) {
    const value = JSON.parse(fs.readFileSync(path.join(root, file), 'utf8')); mutate(value)
    return { [path.join(root, file)]: JSON.stringify(value) }
}
for (const id of [990099002, 990099032, 990099033]) test(`Five Boss ${id} accepts reviewed exact dependencies and rejects price or category changes`, () => {
    const key = 'boss_coin_shop:' + id, original = catalog.rows.find(row => row.key === key), proof = history.rows[key]
    assert.ok(proof, key + ' forward receipt is present')
    const reviewed = { ...original, exactDefinitionEvidence: proof }
    assert.equal(helper().matchExactDefinition(reviewed, root).matchesCatalog, true)
    const Database = require('better-sqlite3'), db = new Database(':memory:')
    try {
        const store = require('../out/lib/content-operations').createContentOperationsStore(db)
        assert.equal(store.runtimeDefinitions.get(key).matchesCatalog, true, 'real runtime accepts the precise evidence')
        assert.equal(require('../assets/boss_coin_shop_item_category_map.json')[id], 99)
        assert.deepEqual(require('../out/lib/assets').getShopItemSync(7, id), require('../assets/boss_coin_shop.json')['99'][id])
    } finally { db.close() }
    const changedCost = helper(altered('assets/boss_coin_shop.json', value => { value['99'][id].costs[0].amount++ }))
    assert.equal(changedCost.matchExactDefinition(reviewed, root).matchesCatalog, false, 'changed price is rejected')
    const changedMapping = helper(altered('assets/boss_coin_shop_item_category_map.json', value => { value[id] = 98 }))
    assert.equal(changedMapping.matchExactDefinition(reviewed, root).matchesCatalog, false, 'changed category is rejected')
    const unrelated = helper(altered('assets/boss_coin_shop.json', value => { value['99']['990099034'].stock++ }))
    assert.equal(unrelated.matchExactDefinition(reviewed, root).matchesCatalog, true, 'unrelated product does not invalidate this receipt')
})
