export const MAX_IMAGE_GENERATION_COUNT = 10;

export function normalizeImageGenerationCount(value: string | number | null | undefined, max = MAX_IMAGE_GENERATION_COUNT) {
    const numeric = Number(value);
    if (!Number.isFinite(numeric) || numeric < 1) return 1;
    return Math.max(1, Math.min(max, Math.floor(numeric)));
}
