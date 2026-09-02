import { getAccountNewsReceiptIdsSync, hasAccountNewsReceiptSync } from "../data/domains/news"
import {
    getActivePopupNews,
    getPublishedNews,
    loadNewsConfig,
    NewsItem,
} from "./news-config"

export interface NewsDeliveryState {
    activePopup: NewsItem | null
    forceNews: boolean
    hasUnreadNews: boolean
}

/**
 * Maps the server-side delivery state to the client's startup interrupt flag.
 *
 * The CN client interprets `force_news=1` as a forced detail popup and
 * `force_news=2` as the regular announcement list.  A null value means that
 * there is no announcement interrupt to process.  Sending `0` is not
 * equivalent to omitting the flag: the client stores it as `Some(0)` and it
 * can survive navigation as stale state.
 */
export function getNewsInterruptFlag(
    state: Pick<NewsDeliveryState, "forceNews" | "hasUnreadNews">,
): 1 | 2 | null {
    if (state.forceNews) return 1
    if (state.hasUnreadNews) return 2
    return null
}

export function getNewsDeliveryState(
    accountId: number,
    now: Date = new Date(),
): NewsDeliveryState {
    const config = loadNewsConfig()
    const activePopup = getActivePopupNews(config, now)
    const forceNews = activePopup !== null && (
        config.popup.mode === "every_login"
        || !hasAccountNewsReceiptSync(accountId, activePopup.id, "popup")
    )
    const listReceipts = getAccountNewsReceiptIdsSync(accountId, "list")
    const hasUnreadNews = getPublishedNews(config).some(item => !listReceipts.has(item.id))
    return { activePopup, forceNews, hasUnreadNews }
}
