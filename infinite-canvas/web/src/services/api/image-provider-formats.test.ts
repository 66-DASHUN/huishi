import { expect, test } from "bun:test";

import { buildGrokImageRequest } from "./image";
import { createModelChannel, defaultBaseUrlForApiFormat } from "../../stores/use-config-store";

test("Grok channels keep their protocol and official default URL", () => {
    const channel = createModelChannel({ apiFormat: "grok" });

    expect(channel.apiFormat).toBe("grok");
    expect(channel.baseUrl).toBe("https://api.x.ai/v1");
    expect(defaultBaseUrlForApiFormat("grok")).toBe("https://api.x.ai/v1");
});

test("Grok generation maps canvas controls to official parameters", () => {
    expect(buildGrokImageRequest("grok-imagine-image-2.0", "city", 2, "2048x1152", "high")).toEqual({
        model: "grok-imagine-image-2.0",
        prompt: "city",
        n: 2,
        response_format: "b64_json",
        aspect_ratio: "16:9",
        resolution: "2k",
        quality: "medium",
    });
});

test("Grok rejects a 4K canvas request instead of silently downgrading it", () => {
    expect(() => buildGrokImageRequest("grok-imagine-image-2.0", "city", 1, "3840x2160", "high")).toThrow("Grok 官方生图仅支持 1K 或 2K");
});
