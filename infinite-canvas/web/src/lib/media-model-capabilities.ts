export type VideoCapabilities = {
    durations?: number[];
    duration_range?: VideoDurationRange;
    resolutions?: string[];
    ratios?: string[];
    modes?: string[];
    camera_movement?: string[];
    max_reference_images?: number;
    max_reference_videos?: number;
    max_reference_audios?: number;
    max_references?: number;
};
export type HostVideoModel = { id: string; label: string; api_format?: string; capabilities?: VideoCapabilities };
export type VideoDurationRange = { min: number; max: number; step?: number };

export type VideoDurationSliderModel = {
    kind: "continuous" | "discrete" | "fixed";
    min: number;
    max: number;
    step: number;
    value: number;
    disabled: boolean;
    durations: number[];
    marks: Array<{ position: number; label: string }>;
};

export function buildVideoDurationSliderModel(durations: number[] | undefined, current: string | number, durationRange?: VideoDurationRange): VideoDurationSliderModel {
    const range = normalizeDurationRange(durationRange);
    if (range) {
        const count = Math.floor((range.max - range.min) / range.step) + 1;
        const effectiveMax = range.min + (count - 1) * range.step;
        const requested = Number(current);
        const clamped = Math.min(effectiveMax, Math.max(range.min, Number.isFinite(requested) ? requested : range.min));
        const value = range.min + Math.round((clamped - range.min) / range.step) * range.step;
        const rangeValues = Array.from({ length: count }, (_, index) => range.min + index * range.step);
        if (count === 1) {
            return { kind: "fixed", min: 0, max: 0, step: 1, value: 0, disabled: true, durations: [range.min], marks: [{ position: 0, label: `${range.min}s` }] };
        }
        const markIndexes = [...new Set([0, Math.floor((count - 1) / 2), count - 1])];
        return {
            kind: "continuous",
            min: range.min,
            max: effectiveMax,
            step: range.step,
            value,
            disabled: false,
            durations: rangeValues,
            marks: markIndexes.map((index) => ({ position: rangeValues[index], label: `${rangeValues[index]}s` })),
        };
    }

    const values = [...new Set((durations || []).map(Number).filter((value) => Number.isInteger(value) && value > 0))].sort((a, b) => a - b);
    if (!values.length) {
        return { kind: "fixed", min: 0, max: 0, step: 1, value: 0, disabled: true, durations: [], marks: [] };
    }

    const requested = Number(current);
    const nearestIndex = values.reduce((best, value, index) =>
        Math.abs(value - requested) < Math.abs(values[best] - requested) ? index : best, 0);
    if (values.length === 1) {
        return { kind: "fixed", min: 0, max: 0, step: 1, value: 0, disabled: true, durations: values, marks: [{ position: 0, label: `${values[0]}s` }] };
    }

    const continuous = values.every((value, index) => index === 0 || value === values[index - 1] + 1);
    if (continuous) {
        const middleIndex = Math.floor((values.length - 1) / 2);
        const markIndexes = [...new Set([0, middleIndex, values.length - 1])];
        return {
            kind: "continuous",
            min: values[0],
            max: values[values.length - 1],
            step: 1,
            value: values[nearestIndex],
            disabled: false,
            durations: values,
            marks: markIndexes.map((index) => ({ position: values[index], label: `${values[index]}s` })),
        };
    }

    return {
        kind: "discrete",
        min: 0,
        max: values.length - 1,
        step: 1,
        value: nearestIndex,
        disabled: false,
        durations: values,
        marks: values.map((duration, position) => ({ position, label: `${duration}s` })),
    };
}

export function videoDurationFromSliderPosition(model: VideoDurationSliderModel, position: number) {
    if (!model.durations.length) return 1;
    if (model.kind === "fixed") return model.durations[0];
    if (model.kind === "continuous") {
        const clamped = Math.min(model.max, Math.max(model.min, position));
        return Math.min(model.max, model.min + Math.round((clamped - model.min) / model.step) * model.step);
    }
    const index = Math.min(model.durations.length - 1, Math.max(0, Math.round(position)));
    return model.durations[index];
}

export function validateVideoSelection(caps: VideoCapabilities, seconds: string, resolution: string, ratio: string) {
    const duration = Number(seconds);
    const range = normalizeDurationRange(caps.duration_range);
    const durationInRange = range && duration >= range.min && duration <= range.max && (duration - range.min) % range.step === 0;
    if (!Number.isInteger(duration) || duration < 1 || (range ? !durationInRange : caps.durations && !caps.durations.includes(duration))) throw new Error("请选择当前模型支持的视频时长");
    const selectedResolution = caps.resolutions?.find((value) => value.toLowerCase() === resolution.toLowerCase());
    if (caps.resolutions && !selectedResolution) throw new Error("请选择当前模型支持的分辨率");
    if (caps.ratios && !caps.ratios.includes(ratio)) throw new Error("请选择当前模型支持的画幅比例");
    return { duration_seconds: duration, resolution: selectedResolution || resolution, ratio };
}

function normalizeDurationRange(value?: VideoDurationRange) {
    if (!value) return null;
    const min = Number(value.min);
    const max = Number(value.max);
    const step = Number(value.step ?? 1);
    if (!Number.isInteger(min) || !Number.isInteger(max) || !Number.isInteger(step) || min < 1 || max < min || step < 1) return null;
    return { min, max, step };
}
