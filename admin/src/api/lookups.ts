import { useQuery } from "@tanstack/react-query"
import { apiGet } from "./client"

export interface LookupData {
    characters: Record<number, { name: string; title: string; rarity: string; element: string }>
    items: Record<number, string>
    equipment: Record<number, { name: string; rarity: string; category: string }>
    quests: Record<string, string>
    degrees: Record<number, { name: string; image: string }>
}
export type LookupKind = keyof LookupData

export function useLookup<K extends LookupKind>(kind: K, enabled = true) {
    return useQuery({
        queryKey: ["lookup", kind],
        queryFn: ({ signal }) => apiGet<LookupData[K]>(`/api/lookup/${kind}`, { signal }),
        enabled,
        staleTime: 5 * 60_000,
        gcTime: 30 * 60_000,
    })
}
