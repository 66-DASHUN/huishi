const assert = require("node:assert/strict");
const models = require("../static/js/settings.js");

const catalog = models.parseImageProviderCatalog(JSON.stringify({
  catalog: {
    openai: [{ id: "gpt-image-2", label: "GPT Image 2" }, { id: "gpt-image-1", label: "GPT Image 1" }],
    grok: [{ id: "grok-imagine-image-2.0", label: "grok-imagine 2.0" }],
  },
  metadata: {
    openai: { default_base_url: "https://api.openai.com/v1", resolutions: ["1K", "2K", "4K"] },
    grok: { default_base_url: "https://api.x.ai/v1", resolutions: ["1K", "2K"] },
  },
}));

assert.ok(catalog, "valid catalog enables enhancement");
assert.equal(models.parseImageProviderCatalog("not json"), null, "invalid JSON safely disables enhancement");
assert.equal(models.parseImageProviderCatalog(""), null, "missing catalog safely disables enhancement");
let enhanced = false;
assert.equal(models.enhance({
  getElementById: () => ({ textContent: "not json" }),
  querySelectorAll: () => { enhanced = true; return []; },
}), false, "invalid JSON skips all DOM enhancement");
assert.equal(enhanced, false, "safe fallback leaves server-rendered form untouched");

const state = {};
models.rememberProtocolState(state, "openai", "gpt-image-1", { "1K": true, "2K": true, "4K": true });
const grok = models.protocolStateFor(catalog, state, "grok", { model: "gpt-image-1", resolutions: { "1K": true, "2K": true, "4K": true } });
assert.equal(grok.model, "grok-imagine-image-2.0");
assert.deepEqual(grok.resolutions, { "1K": true, "2K": true, "4K": false });
models.rememberProtocolState(state, "grok", grok.model, grok.resolutions);
const openai = models.protocolStateFor(catalog, state, "openai", grok);
assert.equal(openai.model, "gpt-image-1", "round-trip restores each protocol model");
assert.equal(openai.resolutions["4K"], true, "round-trip restores each protocol resolution");

const secondFormState = {};
models.rememberProtocolState(secondFormState, "openai", "gpt-image-2", { "1K": true, "2K": false, "4K": false });
assert.equal(models.protocolStateFor(catalog, secondFormState, "openai", null).model, "gpt-image-2", "separate forms keep separate protocol state");
assert.equal(models.defaultUrlFor(catalog, "grok", "https://gateway.example/v1"), "https://gateway.example/v1", "protocol changes never overwrite a custom URL");
assert.equal(models.defaultUrlFor(catalog, "grok", ""), "https://api.x.ai/v1", "an empty URL gets the selected protocol default");
assert.equal(models.defaultUrlFor(catalog, "grok", "https://gateway.example/v1", true), "https://api.x.ai/v1", "restore default explicitly replaces a custom URL");
assert.equal(models.testImageUrl("/static/uploads/test.png", { baseURI: "https://example.com/admin/config/settings" }), "https://example.com/static/uploads/test.png");
assert.equal(models.testImageUrl("javascript:alert(1)", { baseURI: "https://example.com/admin/config/settings" }), "");
assert.deepEqual(
  models.modelEntryFromValues("speech-2.8-hd", "MiniMax Speech", true, "speech"),
  { id: "speech-2.8-hd", label: "MiniMax Speech", enabled: true, media_type: "speech" },
  "audio model rows keep their capability when saved",
);
assert.deepEqual(
  models.modelEntryFromValues("gpt-image-2", "GPT Image 2", true, ""),
  { id: "gpt-image-2", label: "GPT Image 2", enabled: true },
  "non-audio model rows stay compact",
);
assert.deepEqual(
  models.mergeFetchedModels(
    [{ id: "gpt-image-2", label: "已有名称", enabled: true }],
    [{ id: "gpt-image-2", label: "远程名称" }, { id: "gpt-image-2.5-flare", label: "GPT Image 2.5 Flare" }],
  ),
  [
    { id: "gpt-image-2", label: "已有名称", enabled: true },
    { id: "gpt-image-2.5-flare", label: "GPT Image 2.5 Flare", enabled: true },
  ],
  "fetched models append without replacing configured rows",
);

console.log("settings model behavior checks passed");
