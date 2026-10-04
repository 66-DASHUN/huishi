import { describe, expect, test } from "bun:test";

import { defaultConfig, filterModelsByCapability, modelMatchesCapability } from "./use-config-store";

describe("speech and music model configuration", () => {
    test("keeps separate defaults and option lists for speech and music", () => {
        expect(defaultConfig.speechModel).toBe("default::speech-2.8-hd");
        expect(defaultConfig.musicModel).toBe("default::music-3.0");
        expect(defaultConfig.speechModels).toContain("default::speech-2.8-hd");
        expect(defaultConfig.musicModels).toContain("default::music-3.0");
    });

    test("filters speech and music models without mixing them", () => {
        const models = ["speech-2.8-hd", "music-3.0", "gpt-image-2"];
        expect(modelMatchesCapability("speech-2.8-hd", "speech")).toBe(true);
        expect(modelMatchesCapability("music-3.0", "music")).toBe(true);
        expect(filterModelsByCapability(models, "speech")).toEqual(["speech-2.8-hd"]);
        expect(filterModelsByCapability(models, "music")).toEqual(["music-3.0"]);
    });
});
