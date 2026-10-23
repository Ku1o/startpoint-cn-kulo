import { Gacha, GachaPoolItem, GachaType } from "./types";

/** Original comeback/stars periods are not currently persisted; operations cannot grant them. */
export function isDeferredPersonalPeriodGacha(gachaId: number): boolean {
    return Number.isSafeInteger(gachaId) && ((gachaId >= 700000 && gachaId <= 700004)
        || (gachaId >= 80000 && gachaId <= 80004))
}

export const GACHA_PAYMENT_TYPES = {
    FREE_VMONEY: 1,
    VMONEY: 2,
    TICKET: 3,
    CAMPAIGN: 4,
} as const;

export const GACHA_EXEC_TYPES = {
    VMONEY_SINGLE: 1,
    VMONEY_MULTI: 2,
    CONFIGURED_SINGLE_TICKET: 3,
    CONFIGURED_MULTI_TICKET: 4,
    DAILY_SINGLE: 5,
    CAMPAIGN_SINGLE: 7,
    CAMPAIGN_MULTI: 8,
    WILDCARD_CHARACTER_MULTI_TICKET: 9,
    WILDCARD_CHARACTER_SINGLE_TICKET: 10,
    WILDCARD_EQUIPMENT_SINGLE_TICKET: 12,
    WILDCARD_EQUIPMENT_MULTI_TICKET: 13,
} as const;

export const GACHA_PAGE_KINDS = {
    NORMAL: 0,
    TEN_TIMES_PER_ACCOUNT: 1,
    TICKET_ONLY: 2,
    ONE_TIME_TICKET_ONLY: 3,
    TEN_TIMES_TICKET_ONLY: 4,
    CRAZY_TEN_TIMES_TICKET_ONLY: 5,
    ONE_TIME: 6,
    TEN_TIMES: 7,
    WITHOUT_DAILY: 8,
} as const;

export type TicketDrawKind = "single" | "multi";

export function getTicketDrawKind(type: number): TicketDrawKind | null {
    switch (type) {
        case GACHA_EXEC_TYPES.CONFIGURED_SINGLE_TICKET:
        case GACHA_EXEC_TYPES.WILDCARD_CHARACTER_SINGLE_TICKET:
        case GACHA_EXEC_TYPES.WILDCARD_EQUIPMENT_SINGLE_TICKET:
            return "single";
        case GACHA_EXEC_TYPES.CONFIGURED_MULTI_TICKET:
        case GACHA_EXEC_TYPES.WILDCARD_CHARACTER_MULTI_TICKET:
        case GACHA_EXEC_TYPES.WILDCARD_EQUIPMENT_MULTI_TICKET:
            return "multi";
        default:
            return null;
    }
}

export function ticketExecMatchesGachaType(type: number, gacha: Pick<Gacha, "type">): boolean {
    if (
        type === GACHA_EXEC_TYPES.CONFIGURED_SINGLE_TICKET ||
        type === GACHA_EXEC_TYPES.CONFIGURED_MULTI_TICKET
    ) {
        return true;
    }
    if (gacha.type === GachaType.WEAPON) {
        return type === GACHA_EXEC_TYPES.WILDCARD_EQUIPMENT_SINGLE_TICKET ||
            type === GACHA_EXEC_TYPES.WILDCARD_EQUIPMENT_MULTI_TICKET;
    }
    return type === GACHA_EXEC_TYPES.WILDCARD_CHARACTER_SINGLE_TICKET ||
        type === GACHA_EXEC_TYPES.WILDCARD_CHARACTER_MULTI_TICKET;
}

function ticketAllowedByPageKind(pageKind: number | undefined, drawKind: TicketDrawKind): boolean {
    switch (pageKind) {
        case GACHA_PAGE_KINDS.ONE_TIME_TICKET_ONLY:
            return drawKind === "single";
        case GACHA_PAGE_KINDS.TEN_TIMES_TICKET_ONLY:
        case GACHA_PAGE_KINDS.CRAZY_TEN_TIMES_TICKET_ONLY:
        case GACHA_PAGE_KINDS.TEN_TIMES_PER_ACCOUNT:
            return drawKind === "multi";
        default:
            return true;
    }
}

export function isGachaExecAllowed(gacha: Gacha, paymentType: number, execType: number): boolean {
    const pageKind = gacha.pageKind ?? GACHA_PAGE_KINDS.NORMAL;
    const ticketDrawKind = getTicketDrawKind(execType);

    // Payment and execution are independent request fields. A page's allowed
    // draw size must never turn a paid daily single into an account-only ten.
    if (paymentType === GACHA_PAYMENT_TYPES.FREE_VMONEY) {
        if (execType !== GACHA_EXEC_TYPES.VMONEY_SINGLE && execType !== GACHA_EXEC_TYPES.VMONEY_MULTI) return false;
    } else if (paymentType === GACHA_PAYMENT_TYPES.VMONEY) {
        if (execType !== GACHA_EXEC_TYPES.DAILY_SINGLE) return false;
    } else if (paymentType === GACHA_PAYMENT_TYPES.CAMPAIGN) {
        if (execType !== GACHA_EXEC_TYPES.CAMPAIGN_SINGLE && execType !== GACHA_EXEC_TYPES.CAMPAIGN_MULTI) return false;
    } else if (paymentType !== GACHA_PAYMENT_TYPES.TICKET) return false;

    if (paymentType === GACHA_PAYMENT_TYPES.TICKET) {
        return ticketDrawKind !== null &&
            ticketExecMatchesGachaType(execType, gacha) &&
            ticketAllowedByPageKind(pageKind, ticketDrawKind);
    }

    switch (pageKind) {
        case GACHA_PAGE_KINDS.TICKET_ONLY:
        case GACHA_PAGE_KINDS.ONE_TIME_TICKET_ONLY:
        case GACHA_PAGE_KINDS.TEN_TIMES_TICKET_ONLY:
        case GACHA_PAGE_KINDS.CRAZY_TEN_TIMES_TICKET_ONLY:
            return false;
        case GACHA_PAGE_KINDS.WITHOUT_DAILY:
            return paymentType !== GACHA_PAYMENT_TYPES.VMONEY;
        case GACHA_PAGE_KINDS.ONE_TIME:
            return execType === GACHA_EXEC_TYPES.VMONEY_SINGLE ||
                execType === GACHA_EXEC_TYPES.CAMPAIGN_SINGLE;
        case GACHA_PAGE_KINDS.TEN_TIMES:
        case GACHA_PAGE_KINDS.TEN_TIMES_PER_ACCOUNT:
            return execType === GACHA_EXEC_TYPES.VMONEY_MULTI ||
                execType === GACHA_EXEC_TYPES.CAMPAIGN_MULTI;
        default:
            return true;
    }
}

export function getGachaPoolItem(gacha: Gacha, itemId: number): GachaPoolItem | null {
    for (const pool of Object.values(gacha.pool || {})) {
        const item = pool.find((candidate) => candidate.id === itemId);
        if (item) return item;
    }
    return null;
}

export function getExchangeableGachaItem(gacha: Gacha, itemId: number): GachaPoolItem | null {
    const item = getGachaPoolItem(gacha, itemId);
    return item?.isExchangeable ? item : null;
}
