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
// 已配置的行必须原样保留；新拉取的模型追加在后面。
// 注意新模型默认 enabled:false —— 这里的 enabled 决定的是"预览复选框是否预先勾选"，
// 只有上游显式返回 enabled:true 才预勾。默认不勾是有意的：自动上架未经核对的
// 上游模型会把没验证过的渠道暴露给用户。原先这条断言期望 enabled:true，
// 与实现不符且长期无人跑（该脚本需要 node，服务器与镜像里都没有）。
const mergedModels = models.mergeFetchedModels(
  [{ id: "gpt-image-2", label: "已有名称", enabled: true }],
  [{ id: "gpt-image-2", label: "远程名称" }, { id: "gpt-image-2.5-flare", label: "GPT Image 2.5 Flare" }],
);
assert.deepEqual(
  mergedModels.map((entry) => entry.id),
  ["gpt-image-2", "gpt-image-2.5-flare"],
  "fetched models append without replacing configured rows",
);
assert.equal(mergedModels[0].label, "已有名称", "an existing row keeps its local label");
assert.equal(mergedModels[1].enabled, false, "a newly fetched model is not pre-selected for import");
assert.equal(
  models.mergeFetchedModels([], [{ id: "x", enabled: true }])[0].enabled,
  true,
  "an upstream that explicitly enables a model is pre-selected",
);

// 参考素材提示语的数字必须来自 capabilities，不能写死某个模型的规格。
// 缺陷背景：这段文案原先硬编码 H3 的 9/3/3/12，对 H3 恰好正确，但对
// seedance_media（30 张）完全失真——管理员看到的是另一个模型的规格。
const h3Hint = models.describeTestReferenceHint({
  modes: ["text", "keyframes", "omni_reference"],
  max_reference_images: 9, max_reference_videos: 3, max_reference_audios: 3,
  max_references: 12, max_image_bytes: 30000000, max_video_bytes: 50000000, max_audio_bytes: 15000000,
});
assert.ok(h3Hint.includes("图片≤9") && h3Hint.includes("视频≤3") && h3Hint.includes("合计≤12"), "H3 limits come from caps");
assert.ok(h3Hint.includes("首尾帧与全能参考不可混用"), "keyframes + omni_reference warns about mixing");

const seedanceHint = models.describeTestReferenceHint({
  modes: ["text", "reference_images"],
  max_reference_images: 30, max_reference_videos: 0, max_reference_audios: 0,
  max_image_bytes: 12 * 1024 * 1024, max_images_total_bytes: 70 * 1024 * 1024,
});
assert.ok(seedanceHint.includes("最多30张"), "seedance image limit is not the H3 number");
assert.ok(seedanceHint.includes("12MiB") && seedanceHint.includes("70MiB"), "byte limits are surfaced");
assert.ok(!seedanceHint.includes("图片≤9"), "H3 numbers must not leak into a seedance channel");

// 只支持 omni_reference、没有首尾帧的渠道，不该收到互斥提醒。
const omniOnly = models.describeTestReferenceHint({ modes: ["text", "omni_reference"], max_reference_images: 30 });
assert.ok(!omniOnly.includes("首尾帧"), "no keyframes means no mixing warning");

// 没有能力声明时不得编造数字。
assert.equal(models.describeTestReferenceHint({}), "不上传即为文生视频。", "no caps means no invented limit");
assert.equal(models.describeTestReferenceHint(null), "不上传即为文生视频。", "null caps is safe");
assert.ok(!models.describeTestReferenceHint({ max_reference_images: 5 }).includes("1张"), "missing modes must not claim a 1-image limit");

console.log("settings model behavior checks passed");
