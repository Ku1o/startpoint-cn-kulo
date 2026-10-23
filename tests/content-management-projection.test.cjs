'use strict'
require('ts-node/register/transpile-only')
const { test } = require('node:test')
const assert = require('node:assert/strict')
const { projectContentManagementCard, projectContentManagementCards } = require('../src/lib/content-management-projection')

test('cards retain full action state, scopes and user-visible fields without technical source metadata', () => {
    const state = { flags: { visible: true }, readiness: 'verified', evidence: 'reviewed', revision: 9,
        questKeys: ['2:100'], missionKeys: [], catalogDigest: 'nested-catalog', contentDigest: 'nested-content',
        actionOverrides: { exchange: { enabled: true, readiness: 'verified', evidence: 'unchanged', endsAtMs: null,
            questKeys: null, missionKeys: ['7:44'], catalogDigest: 'nested-catalog', contentDigest: 'nested-content' } } }
    const row = { key: 'gacha:1', type: 'gacha', id: 1, name: 'game name', state, originalStartMs: null, originalEndMs: 7,
        effectiveFlags: { exchange: true }, presentation: { title: 'game name' }, primaryControl: { kind: 'exchange', canToggle: true },
        limitations: ['keep condition'], rightsNotice: 'keep right', linkedActivity: { description: 'keep link' },
        deadlineControl: { canEdit: true, hasMixedDeadlines: true }, discovery: { notes: ['keep note'] },
        definitionEvidence: { huge: 'source-only' }, questSources: ['private/technical'], missionKeys: ['top-level-technical'] }
    const projected = projectContentManagementCard(row)
    assert.equal(projected.state, state)
    assert.deepEqual(projected.state.actionOverrides, state.actionOverrides)
    for (const field of ['definitionEvidence', 'questSources', 'missionKeys']) assert.equal(Object.hasOwn(projected, field), false)
    for (const field of ['limitations', 'rightsNotice', 'linkedActivity', 'deadlineControl', 'discovery']) assert.deepEqual(projected[field], row[field])
    assert.equal(Object.hasOwn(projectContentManagementCard({ key: 'gacha:2', state: null }), 'discovery'), false)
    assert.deepEqual(projectContentManagementCard({ key: 'gacha:2', state: { actionOverrides: {} } }).state.actionOverrides, {})
})

test('series retain counts and complete listing metadata used by UI but omit unused preview', () => {
    const listing = { revision: 3, catalogDigest: 'digest', total: 1, rows: [], view: 'series', contentTotal: 120,
        seriesGroups: [{ key: 'series', title: 'series title', total: 120, enabled: 20, disabled: 100,
            pending: 0, blocked: 0, firstStartMs: 1, lastStartMs: 2, preview: { state: { large: 'unused' } } }],
        groups: [{ key: 'all', total: 120 }], typeOptions: [{ value: 'gacha', label: '扭蛋' }], statusCounts: { enabled: 20 },
        searchInfo: { query: 'test', terms: ['test'] }, source: { technical: 'omit' }, types: ['gacha'], missing: ['omit'] }
    const result = projectContentManagementCards(listing)
    const { source, types, missing, ...expected } = listing
    expected.seriesGroups = expected.seriesGroups.map(({ preview, ...group }) => group)
    assert.deepEqual(result, expected)
    assert.equal(listing.seriesGroups[0].preview.state.large, 'unused')
})
