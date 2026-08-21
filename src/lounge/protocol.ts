export const LOUNGE_DISBANDED_STATE = 99
export const LOUNGE_DISMISSED_MESSAGE = "multibattle_room_dismissed"

/**
 * Build the normal client response for a lounge that no longer exists.
 *
 * The CN client handles raising_state=99 by leaving the lounge and deleting
 * its persisted lounge_restore_data. Returning an HTTP error here leaves that
 * client-side state behind and makes every subsequent login retry A4511.
 */
export function buildLoungeDisbandedConnectionData(loungeNumber = ""): {
    application_update_url: string
    ip_address: string
    lounge_number: string
    port: number
    raising_state: number
} {
    return {
        application_update_url: "",
        ip_address: "",
        lounge_number: loungeNumber,
        port: 0,
        raising_state: LOUNGE_DISBANDED_STATE,
    }
}
