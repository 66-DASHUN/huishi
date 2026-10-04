export const SEEDANCE_RESOLUTIONS = ["720p"] as const;
export const SEEDANCE_RATIOS = ["1:1", "3:4", "4:3", "9:16", "16:9", "21:9"] as const;
export const SEEDANCE_CAMERA_MOVEMENTS = ["auto", "fixed"] as const;

export type SeedanceModelFamily = "2.5" | "2.0" | "2.0fast" | "2.0mini";

export type SeedanceCapabilities = {
    family: SeedanceModelFamily;
    durations: readonly number[];
    maxImageReferences: number;
    resolutions: readonly (typeof SEEDANCE_RESOLUTIONS)[number][];
    ratios: readonly (typeof SEEDANCE_RATIOS)[number][];
    cameraMovements: readonly (typeof SEEDANCE_CAMERA_MOVEMENTS)[number][];
};

const MODEL_CAPABILITIES: Record<SeedanceModelFamily, SeedanceCapabilities> = {
    "2.5": { family: "2.5", durations: [30], maxImageReferences: 30, resolutions: SEEDANCE_RESOLUTIONS, ratios: SEEDANCE_RATIOS, cameraMovements: SEEDANCE_CAMERA_MOVEMENTS },
    "2.0": { family: "2.0", durations: [5, 10, 15], maxImageReferences: 9, resolutions: SEEDANCE_RESOLUTIONS, ratios: SEEDANCE_RATIOS, cameraMovements: SEEDANCE_CAMERA_MOVEMENTS },
    "2.0fast": { family: "2.0fast", durations: [5, 10, 15], maxImageReferences: 9, resolutions: SEEDANCE_RESOLUTIONS, ratios: SEEDANCE_RATIOS, cameraMovements: SEEDANCE_CAMERA_MOVEMENTS },
    "2.0mini": { family: "2.0mini", durations: [5, 10], maxImageReferences: 9, resolutions: SEEDANCE_RESOLUTIONS, ratios: SEEDANCE_RATIOS, cameraMovements: SEEDANCE_CAMERA_MOVEMENTS },
};

export function seedanceCapabilitiesForModel(model: string): SeedanceCapabilities {
    const normalized = model.toLowerCase().split("::").pop() || "";
    const family: SeedanceModelFamily = normalized.includes("2.5") ? "2.5" : normalized.includes("2.0mini") || normalized.includes("mini") ? "2.0mini" : normalized.includes("2.0fast") || normalized.includes("fast") ? "2.0fast" : "2.0";
    return MODEL_CAPABILITIES[family];
}

export function seedanceDurationOptionsForModel(model: string) {
    return [...seedanceCapabilitiesForModel(model).durations];
}

export function seedanceImageReferenceLimit(model: string) {
    return seedanceCapabilitiesForModel(model).maxImageReferences;
}

export function seedanceImageReferenceError(model: string, count: number) {
    const limit = seedanceImageReferenceLimit(model);
    return count > limit ? `当前模型最多支持 ${limit} 张参考图，请减少后再生成` : "";
}

export function normalizeSeedanceDuration(value: string | number, model = "") {
    const options = seedanceDurationOptionsForModel(model);
    const requested = Number(value);
    if (!Number.isFinite(requested)) return options[0];
    return options.reduce((best, candidate) => (Math.abs(candidate - requested) < Math.abs(best - requested) ? candidate : best), options[0]);
}

export function normalizeSeedanceResolution(_value: string, _model = "") {
    return "720p" as const;
}

export function normalizeSeedanceRatio(value: string) {
    if (SEEDANCE_RATIOS.includes(value as (typeof SEEDANCE_RATIOS)[number])) return value as (typeof SEEDANCE_RATIOS)[number];
    const match = String(value || "").match(/^(\d+)[:x](\d+)$/);
    const width = Number(match?.[1]);
    const height = Number(match?.[2]);
    if (!width || !height) return "16:9" as const;
    const requested = width / height;
    const ratioValues = SEEDANCE_RATIOS.map((ratio) => {
        const [ratioWidth, ratioHeight] = ratio.split(":").map(Number);
        return { ratio, value: ratioWidth / ratioHeight };
    });
    return ratioValues.reduce((best, candidate) => (Math.abs(candidate.value - requested) < Math.abs(best.value - requested) ? candidate : best), ratioValues[0]).ratio;
}

export function normalizeSeedanceCameraMovement(value: string) {
    return value === "fixed" ? "fixed" : "auto";
}
