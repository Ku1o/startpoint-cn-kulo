export type ContentView = "cards" | "compact" | "series"
export interface DiscoveryPreferences { version: 1; view: ContentView; favorites: string[]; recent: string[] }
export interface PreferenceStorage { getItem(key: string): string | null; setItem(key: string, value: string): void }
export const DISCOVERY_STORAGE_KEY = "starpoint-content-discovery:v1"
export const FAVORITES_LIMIT = 200
export const RECENT_LIMIT = 30
const parentTypes = new Set(["active_mission_event", "advent_event", "box_gacha", "carnival_event", "challenge_dungeon_event", "collect_item_event", "daily_exp_mana_event", "daily_week_event", "expert_single_event", "gacha", "hard_multi_event", "multi_special_exchange_campaign", "pass_card_event", "raid_event", "ranking_event", "rush_event", "score_attack_event", "solo_time_attack_event", "special_exchange_campaign", "start_dash_exchange_campaign", "story_event", "tower_dungeon_event", "world_story_event"])
export function isContentParentKey(value: unknown): value is string {
    if (typeof value !== "string" || value.length > 80) return false
    const match = /^([a-z_]+):(0|[1-9]\d{0,15})$/.exec(value)
    return !!match && parentTypes.has(match[1]) && Number.isSafeInteger(Number(match[2]))
}
const cleanKeys = (value: unknown, limit: number): string[] => Array.isArray(value) ? [...new Set(value.filter(isContentParentKey))].slice(0, limit) : []
export function normalizeDiscoveryPreferences(value: unknown): DiscoveryPreferences {
    const input = value && typeof value === "object" ? value as Partial<DiscoveryPreferences> : {}
    if (input.version !== 1) return { version: 1, view: "cards", favorites: [], recent: [] }
    return { version: 1, view: input.view === "compact" || input.view === "series" ? input.view : "cards", favorites: cleanKeys(input.favorites, FAVORITES_LIMIT), recent: cleanKeys(input.recent, RECENT_LIMIT) }
}
export function browserPreferenceStorage(): PreferenceStorage | undefined {
    try { return typeof window === "undefined" ? undefined : window.localStorage } catch { return undefined }
}
export function readDiscoveryPreferences(storage?: PreferenceStorage): { preferences: DiscoveryPreferences; persistent: boolean } {
    const fallback = normalizeDiscoveryPreferences(undefined)
    if (!storage) return { preferences: fallback, persistent: false }
    try {
        const saved = storage.getItem(DISCOVERY_STORAGE_KEY)
        if (saved === null) return { preferences: fallback, persistent: true }
        if (saved.length > 64_000) return { preferences: fallback, persistent: false }
        const value = JSON.parse(saved)
        if (!value || value.version !== 1) return { preferences: fallback, persistent: false }
        return { preferences: normalizeDiscoveryPreferences(value), persistent: true }
    } catch { return { preferences: fallback, persistent: false } }
}
export function writeDiscoveryPreferences(value: DiscoveryPreferences, storage?: PreferenceStorage): boolean {
    if (!storage) return false
    try { storage.setItem(DISCOVERY_STORAGE_KEY, JSON.stringify(normalizeDiscoveryPreferences(value))); return true } catch { return false }
}
export function favoritePreference(value: DiscoveryPreferences, key: string): DiscoveryPreferences {
    const current = normalizeDiscoveryPreferences(value)
    if (!isContentParentKey(key)) return current
    return { ...current, favorites: current.favorites.includes(key) ? current.favorites.filter(item => item !== key) : current.favorites.length < FAVORITES_LIMIT ? [key, ...current.favorites] : current.favorites }
}
export function recentPreference(value: DiscoveryPreferences, key: string): DiscoveryPreferences {
    const current = normalizeDiscoveryPreferences(value)
    return isContentParentKey(key) ? { ...current, recent: [key, ...current.recent.filter(item => item !== key)].slice(0, RECENT_LIMIT) } : current
}
