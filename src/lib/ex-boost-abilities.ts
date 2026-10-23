import orderedExAbility from "../../assets/ex_ability.json"

// ---- A/B group classification from orderedmap ability names ----

const A_PREFIXES = ['atk_self_', 'skilldamage_self_', 'directdamage_self_',
    'abilitydamage_self_', 'abilitydagame_self_',
    'atk_party_', 'skilldamage_party_', 'directdamage_party_',
    'abilitydamage_party_', 'abilitydagame_party_',
    'powerflipdamage_', 'hp_self_']

// These match A_PREFIXES but are actually B-group (buff extend/duration)
const B_OVERRIDES = ['powerflipdamage_buffextend_']

export interface AbilityInfo { id: number, name: string, group: 'A' | 'B', rarity: number }

function classifyAbilities(data: Record<string, string[][]>): AbilityInfo[] {
    const list: AbilityInfo[] = []
    for (const [id, raw] of Object.entries(data)) {
        const name = raw[0]?.[0] || ''
        const isBOverride = B_OVERRIDES.some(p => name.startsWith(p))
        const isA = !isBOverride && A_PREFIXES.some(p => name.startsWith(p))
        let rarity = 1 // brown
        if (name.endsWith('_r5')) rarity = 3
        else if (name.endsWith('_r4')) rarity = 2
        list.push({ id: Number(id), name, group: isA ? 'A' : 'B', rarity })
    }
    return list
}

export const ALL_ABILITIES = classifyAbilities(orderedExAbility as Record<string, string[][]>)
