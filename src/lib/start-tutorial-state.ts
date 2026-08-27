export const SHORTENED_TUTORIAL_STEP_OFFSET = 11
export const TUTORIAL_END_EFFECTIVE_STEP = 17

export function getTutorialEffectiveStep(
    step: number,
    skip: boolean | null,
): number {
    return step + (skip ? SHORTENED_TUTORIAL_STEP_OFFSET : 0)
}

export function isStartTutorialActive(
    step: number | null,
    skip: boolean | null,
    hasFinishedMainQuest = false,
): boolean {
    return !hasFinishedMainQuest
        && step !== null
        && getTutorialEffectiveStep(step, skip) < TUTORIAL_END_EFFECTIVE_STEP
}
