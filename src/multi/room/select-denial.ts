export const SELECT_ROOM_FILLED_STATE = 3
export const SELECT_ROOM_BATTLE_STATE = 4
export const SELECT_ROOM_DISBANDED_STATE = 9

export interface SelectRoomDenialContext {
    battleStarted: boolean
    roomFull: boolean
}

/**
 * Map a rejected room selection to the legacy client's native raising state.
 * The client already has dedicated dialogs for Filled (3) and Battle (4);
 * Disbanded (9) is only the fallback for missing or otherwise stale rooms.
 */
export function getSelectRoomDenialRaisingState(
    context: SelectRoomDenialContext,
): 3 | 4 | 9 {
    if (context.battleStarted) return SELECT_ROOM_BATTLE_STATE
    if (context.roomFull) return SELECT_ROOM_FILLED_STATE
    return SELECT_ROOM_DISBANDED_STATE
}
