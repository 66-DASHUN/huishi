const form = document.querySelector(".composer");
const HOME_PROMPT_DRAFT_KEY = "huishi.home.promptDraft";
const studioShell = document.querySelector(".studio-shell");
const estimate = document.querySelector("#estimate");
const ratioInput = document.querySelector("#ratio");
const resolutionInput = document.querySelector("#resolution");
const widthInput = document.querySelector("#width");
const heightInput = document.querySelector("#height");
const modeInput = document.querySelector("#mode");
const mediaTypeInput = document.querySelector("#media-type");
const modelInput = document.querySelector("#model");
const dialogueInput = document.querySelector("#dialogue-id");
const createDialogueInput = document.querySelector("#create-dialogue");
const referenceField = document.querySelector("#reference-field");
const referenceImages = document.querySelector("#reference-images");
const referencePreview = document.querySelector("#reference-preview");
const referenceClearButton = document.querySelector("[data-clear-reference]");
const referenceStack = document.querySelector("[data-reference-stack]");
const referenceAddButton = document.querySelector("[data-reference-add]");
const referencePathsInput = document.querySelector("#reference-paths");
const referencePreviewModal = document.querySelector("#reference-preview-modal");
const referencePreviewImage = referencePreviewModal?.querySelector("img");
const referencePreviewCaption = referencePreviewModal?.querySelector("[data-reference-preview-caption]");
const statusLine = document.querySelector("#generation-status");
const composerPrompt = form?.querySelector('[name="prompt"]');
const currentCanvas = document.querySelector("#current-canvas");
const ratioLabel = document.querySelector("#ratio-label");
const resolutionLabel = document.querySelector("#resolution-label");
const customWidthInput = document.querySelector("#custom-width");
const customHeightInput = document.querySelector("#custom-height");
const countInput = document.querySelector('[name="count"]');
const videoToolbar = document.querySelector("[data-video-toolbar]");
const videoRatioInput = document.querySelector("#video-ratio");
const videoResolutionInput = document.querySelector("#video-resolution");
const videoDurationInput = document.querySelector("#video-duration");
const videoReferenceModeInput = document.querySelector("#video-reference-mode");
const videoCountInput = document.querySelector("#video-count");
let selectedVideoSubjectId = document.querySelector("#subject-id")?.value || "";
const videoDurationSlider = document.querySelector("[data-video-duration-slider]");
const videoMediaReferences = document.querySelector("[data-video-media-references]");
const subjectImageInput = document.querySelector("[data-subject-image-input]");
const videoReferenceMaterials = document.querySelector("[data-video-reference-materials]");
const modelKindLabel = document.querySelector("[data-model-kind-label]");
const qualityInput = form?.querySelector('[name="quality"]');
const outputFormatInput = form?.querySelector('[name="output_format"]');
const promptStyle = document.querySelector("#prompt-style");
const optimizePromptButton = document.querySelector("[data-optimize-prompt]");
const promptCounter = document.querySelector("[data-prompt-counter]");
const expandPromptButton = document.querySelector("[data-expand-prompt]");
const taskRegion = document.querySelector("#generation-task-region");
const taskTemplate = document.querySelector("#generation-task-template");
const conversationToggle = document.querySelector("[data-conversation-toggle]");
const conversationSidebar = document.querySelector("#studio-conversations");
const maxGenerationCount = Number.parseInt(form?.dataset.maxGenerationCount || countInput?.max || "10", 10) || 10;
const maxReferenceImages = Number.parseInt(form?.dataset.maxReferenceImages || "16", 10) || 16;
const isWorkspaceComposerPage = Boolean(
  document.querySelector(".studio-shell")
  && form
  && currentCanvas
  && taskRegion
  && taskTemplate
);
let composerCollapseProtectedUntil = 0; // 提交生成后短暂保护，防止 scroll 触发折叠
const shortageModal = document.querySelector("#points-shortage-modal");
const shortageMessage = document.querySelector("[data-shortage-message]");
const regenerateModal = document.querySelector("#regenerate-confirm-modal");
const regenerateMessage = document.querySelector("[data-regenerate-message]");
const confirmRegenerateButton = document.querySelector("[data-confirm-regenerate]");
const cancelRegenerateButton = document.querySelector("[data-cancel-regenerate]");
const skipRegenerateConfirm = document.querySelector("[data-skip-regenerate-confirm]");
const imagePreviewModal = document.querySelector("#image-preview-modal");
const imagePreviewImage = imagePreviewModal?.querySelector("img");
const imagePreviewCaption = imagePreviewModal?.querySelector("[data-image-preview-caption]");
let lastImagePreviewTrigger = null;
const REGENERATE_SKIP_KEY = "huishi.skipRegenerateConfirm";
const CUSTOM_SIZE_RULES = {
  maxEdge: 3840,
  minAspectRatio: 1 / 3,
  maxAspectRatio: 3,
  minPixels: 655360,
  maxPixels: 8294400,
  experimentalPixels: 2560 * 1440,
};
let referenceTransfer = null;
let videoReferenceTransfer = null;
let referenceMaterials = [];
let estimateRefreshTimer = 0;
let estimateAbortController = null;
let activeEstimateParams = "";
let lastEstimateParams = "";
let estimateRequestSerial = 0;
let pendingPresetNormalizationNotice = "";
let lastPromptBeforeOptimization = "";
let restorePromptButton = null;
const MEDIA_TYPES = ["image", "video", "speech", "music"];
let selectedMediaType = MEDIA_TYPES.includes(mediaTypeInput?.value || "") ? mediaTypeInput.value : "image";
const selectedModelByMediaType = Object.fromEntries(MEDIA_TYPES.map((mediaType) => [mediaType, ""]));
selectedModelByMediaType[selectedMediaType] = modelInput?.value || "";
const MODEL_KIND_LABELS = { image: "图片模型", video: "视频模型", speech: "语音模型", music: "音乐模型" };
const generationModePicker = document.querySelector("[data-generation-mode-picker]");
const generationModeTrigger = generationModePicker?.querySelector("[data-generation-mode-trigger]");
const generationModeMenu = generationModePicker?.querySelector("[data-generation-mode-menu]");
const generationModeLabel = generationModePicker?.querySelector("[data-generation-mode-label]");
const generationModeIcon = generationModePicker?.querySelector("[data-generation-mode-icon]");

function syncSelectedVideoSubjectInput() {
  const input = document.querySelector("#subject-id");
  if (input) {
    input.value = selectedVideoSubjectId;
    input.defaultValue = selectedVideoSubjectId;
  }
  const subject = videoSubjectEntries().find(item => item.id === selectedVideoSubjectId);
  const name = subject?.fileName || subject?.name || '';
  const label = document.querySelector('.video-subject-label');
  if (label) {
    label.textContent = name;
    label.hidden = !name;
    label.title = name;
  }
  const trigger = document.querySelector('[data-subject-trigger]');
  if (trigger) {
    trigger.title = name ? `当前主体：${name}，点击选择已上传主体` : '选择已上传主体';
    trigger.setAttribute('aria-label', name ? `选择已上传主体，当前：${name}` : '选择已上传主体');
  }
}

function setGenerationModeMenuOpen(open) {
  if (!generationModePicker || !generationModeTrigger || !generationModeMenu) return;
  generationModeMenu.hidden = !open;
  generationModePicker.classList.toggle("is-open", open);
  generationModeTrigger.setAttribute("aria-expanded", String(open));
}

function syncGenerationModePicker() {
  const options = generationModePicker?.querySelectorAll('[role="option"]') || [];
  const selected = Array.from(options).find((option) => option.dataset.value === selectedMediaType) || options[0];
  if (!selected) return;
  const label = selected.dataset.label || selected.textContent.trim();
  if (generationModeLabel) generationModeLabel.textContent = label;
  if (generationModeIcon) generationModeIcon.innerHTML = selected.querySelector(".generation-mode-option-icon")?.innerHTML || "";
  if (generationModeTrigger) generationModeTrigger.setAttribute("aria-label", `选择创作类型，当前为${label}`);
  options.forEach((option) => {
    const active = option === selected;
    option.classList.toggle("is-active", active);
    option.setAttribute("aria-selected", String(active));
  });
}

function bindGenerationModePicker() {
  if (!generationModePicker || !generationModeTrigger || !generationModeMenu) return;
  generationModeTrigger.addEventListener("click", () => setGenerationModeMenuOpen(generationModeMenu.hidden));
  generationModeTrigger.addEventListener("keydown", (event) => {
    if (event.key === "ArrowDown" || event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      setGenerationModeMenuOpen(true);
      generationModePicker.querySelector('[role="option"][aria-selected="true"]')?.focus();
    }
  });
  generationModeMenu.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      setGenerationModeMenuOpen(false);
      generationModeTrigger.focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (!generationModePicker.contains(event.target)) setGenerationModeMenuOpen(false);
  });
}

function modelCatalogForMediaType(mediaType) {
  try {
    const parsed = JSON.parse(form?.dataset[`${mediaType}Models`] || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (_) {
    return [];
  }
}

function syncMediaType() {
  selectedMediaType = MEDIA_TYPES.includes(selectedMediaType) ? selectedMediaType : "image";
  if (mediaTypeInput) mediaTypeInput.value = selectedMediaType === "image" ? "" : selectedMediaType;
  syncGenerationModePicker();
  document.querySelectorAll(".image-only-control").forEach((element) => {
    const hidden = selectedMediaType !== "image";
    element.hidden = hidden;
    element.querySelectorAll("input, select, button").forEach((control) => { control.disabled = hidden; });
  });
  const audioOptions = document.querySelector("[data-audio-options]");
  const musicOptions = document.querySelector("[data-music-options]");
  if (audioOptions) {
    audioOptions.hidden = selectedMediaType !== "speech";
    audioOptions.querySelectorAll("input, select").forEach((control) => { control.disabled = selectedMediaType !== "speech"; });
  }
  if (musicOptions) {
    musicOptions.hidden = selectedMediaType !== "music";
    musicOptions.querySelectorAll("input, select").forEach((control) => { control.disabled = selectedMediaType !== "music"; });
  }
  if (modelInput) {
    const current = selectedModelByMediaType[selectedMediaType] || "";
    const options = modelCatalogForMediaType(selectedMediaType);
    modelInput.innerHTML = options.length ? options.map((option) => `<option value="${escapeAttribute(option.id)}">${escapeAttribute(option.label || option.id)}</option>`).join("") : '<option value="">暂无可用模型</option>';
    if (options.some((option) => option.id === current)) modelInput.value = current;
    selectedModelByMediaType[selectedMediaType] = modelInput.value;
    const kindLabel = MODEL_KIND_LABELS[selectedMediaType] || "模型";
    if (modelKindLabel) modelKindLabel.textContent = kindLabel;
    modelInput.setAttribute("aria-label", `选择${kindLabel}`);
    modelInput.title = modelInput.selectedOptions[0]?.textContent || kindLabel;
  }
  if (composerPrompt && selectedMediaType === "image") composerPrompt.maxLength = 1000;
  if (selectedMediaType !== "image") {
    if (modeInput) modeInput.value = "text";
  } else {
    syncReferenceField();
  }
  if (referencePreview) renderReferenceMaterials();
  syncSizeDisplay();
  syncVideoOptions();
  refreshEstimate();
}

function videoModelCapabilities() {
  return modelCatalogForMediaType("video").find((entry) => entry.id === modelInput?.value)?.capabilities || {};
}

const referenceTypeDefinitions = [
  { value: "reference", label: "全能参考", capability: "omni_reference" },
  { value: "keyframes", label: "首尾帧", capability: "keyframes" },
  { value: "multi_frame", label: "智能多帧", badge: "New", capability: "reference_images" },
  { value: "smart_edit", label: "智能编辑", badge: "Beta", capability: "smart_edit" },
  { value: "long_video", label: "超长视频", badge: "Beta", capability: "long_video" },
];

function setVideoOptionButtons(selector, values, currentValue, formatter = (value) => String(value), showUnsupported = false) {
  const buttons = Array.from(document.querySelectorAll(selector));
  const normalized = values.map((value) => String(value));
  buttons.forEach((button) => {
    const supported = normalized.includes(String(button.dataset.value));
    button.hidden = !supported && !showUnsupported;
    button.disabled = !supported;
    button.setAttribute("aria-disabled", supported ? "false" : "true");
    button.classList.toggle("is-disabled", !supported);
    if (!supported && showUnsupported) button.title = "当前模型不支持此选项";
    button.textContent = supported ? formatter(button.dataset.value) : button.textContent;
    button.classList.toggle("is-active", supported && String(button.dataset.value) === String(currentValue));
  });
  return buttons.filter((button) => !button.hidden && !button.disabled);
}

function ensureVideoOptionButtons(field, values, formatter = (value) => String(value)) {
  const group = document.querySelector(`[data-field="${field}"]`);
  if (!group) return;
  const known = new Set(Array.from(group.querySelectorAll("button[data-value]")).map((button) => String(button.dataset.value)));
  values.map(String).filter((value) => !known.has(value)).forEach((value) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.value = value;
    button.textContent = formatter(value);
    group.appendChild(button);
  });
}

function syncVideoToolbarLabels() {
  const ratio = videoRatioInput?.value || "16:9";
  const resolution = videoResolutionInput?.value || "720p";
  const duration = videoDurationInput?.value || "5";
  const count = videoCountInput?.value || "1";
  const ratioLabel = document.querySelector("[data-video-format-label]");
  const durationLabel = document.querySelector("[data-video-duration-label]");
  const durationOutput = document.querySelector("[data-video-duration-output]");
  if (ratioLabel) ratioLabel.textContent = `${ratio} · ${String(resolution).toUpperCase()}`;
  if (durationLabel) durationLabel.textContent = `${duration} 秒`;
  if (durationOutput) durationOutput.textContent = `${duration} 秒`;
  const referenceLabel = document.querySelector("[data-video-reference-label]");
  const referenceButton = document.querySelector(`[data-field="video-reference-mode"] button.is-active`);
  if (referenceLabel && referenceButton) referenceLabel.textContent = referenceButton.querySelector("span")?.textContent.trim() || referenceButton.textContent.trim();
  document.querySelectorAll('[data-field="video-ratio"] button').forEach((button) => button.classList.toggle("is-active", String(button.dataset.value) === String(ratio)));
  document.querySelectorAll('[data-field="video-resolution"] button').forEach((button) => button.classList.toggle("is-active", String(button.dataset.value).toLowerCase() === String(resolution).toLowerCase()));
  document.querySelectorAll('[data-field="video-count"] button').forEach((button) => button.classList.toggle("is-active", String(button.dataset.value) === String(count)));
}

function buildVideoDurationSliderModel(caps, current) {
  const range = caps.duration_range;
  if (range) {
    const min = Number(range.min), max = Number(range.max), step = Number(range.step || 1);
    if (Number.isInteger(min) && Number.isInteger(max) && Number.isInteger(step) && min > 0 && max >= min && step > 0) {
      const count = Math.floor((max - min) / step) + 1;
      const durations = Array.from({ length: count }, (_, index) => min + index * step);
      const requested = Number(current);
      const duration = durations.reduce((best, value) => Math.abs(value - requested) < Math.abs(best - requested) ? value : best, durations[0]);
      if (count === 1) return {kind: "fixed", min: 0, max: 0, step: 1, position: 0, duration, durations, disabled: true, marks: [{position: 0, label: `${duration} 秒`}]};
      const indexes = [...new Set([0, Math.floor((count - 1) / 2), count - 1])];
      return {kind: "continuous", min, max: durations.at(-1), step, position: duration, duration, durations, disabled: false, marks: indexes.map(index => ({position: durations[index], label: `${durations[index]} 秒`}))};
    }
  }
  const durations = [...new Set((Array.isArray(caps.durations) ? caps.durations : []).map(Number).filter(value => Number.isInteger(value) && value > 0))].sort((a, b) => a - b);
  if (!durations.length) return {kind: "fixed", min: 0, max: 0, step: 1, position: 0, duration: 6, durations: [6], disabled: true, marks: [{position: 0, label: "6 秒"}]};
  const requested = Number(current);
  const duration = durations.reduce((best, value) => Math.abs(value - requested) < Math.abs(best - requested) ? value : best, durations[0]);
  if (durations.length === 1) return {kind: "fixed", min: 0, max: 0, step: 1, position: 0, duration, durations, disabled: true, marks: [{position: 0, label: `${duration} 秒`}]};
  const continuous = durations.every((value, index) => index === 0 || value === durations[index - 1] + 1);
  if (continuous) {
    const indexes = [...new Set([0, Math.floor((durations.length - 1) / 2), durations.length - 1])];
    return {kind: "continuous", min: durations[0], max: durations.at(-1), step: 1, position: duration, duration, durations, disabled: false, marks: indexes.map(index => ({position: durations[index], label: `${durations[index]} 秒`}))};
  }
  const position = durations.indexOf(duration);
  return {kind: "discrete", min: 0, max: durations.length - 1, step: 1, position, duration, durations, disabled: false, marks: durations.map((value, index) => ({position: index, label: `${value} 秒`}))};
}

function videoDurationAtPosition(model, position) {
  if (model.kind === "fixed") return model.duration;
  if (model.kind === "discrete") return model.durations[Math.min(model.durations.length - 1, Math.max(0, Math.round(position)))];
  const value = Math.min(model.max, Math.max(model.min, Number(position)));
  return Math.min(model.max, model.min + Math.round((value - model.min) / model.step) * model.step);
}

function syncVideoCapabilityControls() {
  const caps = videoModelCapabilities();
  const resolutions = Array.isArray(caps.resolutions) ? caps.resolutions.map(String) : [];
  const ratios = Array.isArray(caps.ratios) ? caps.ratios.map(String) : [];
  const modes = new Set(Array.isArray(caps.modes) ? caps.modes : []);
  const referenceModes = referenceTypeDefinitions
    .filter((definition) => modes.has(definition.capability))
    .map((definition) => [definition.value, definition.label]);

  const durationModel = buildVideoDurationSliderModel(caps, videoDurationInput?.value || 6);
  if (videoDurationInput) videoDurationInput.value = String(durationModel.duration);
  if (videoDurationSlider) {
    videoDurationSlider.min = String(durationModel.min);
    videoDurationSlider.max = String(durationModel.max);
    videoDurationSlider.step = String(durationModel.step);
    videoDurationSlider.value = String(durationModel.position);
    videoDurationSlider.dataset.durationModel = JSON.stringify(durationModel);
    videoDurationSlider.disabled = durationModel.disabled;
  }
  const durationScale = document.querySelector("[data-video-duration-scale]");
  durationScale?.replaceChildren(...durationModel.marks.map((mark, index) => {
    const label = document.createElement("span");
    label.textContent = mark.label;
    label.className = index === 0 ? "is-start" : index === durationModel.marks.length - 1 ? "is-end" : "is-middle";
    return label;
  }));
  const currentResolution = String(videoResolutionInput?.value || resolutions[0] || "720p");
  const safeResolution = resolutions.find((value) => value.toLowerCase() === currentResolution.toLowerCase()) || resolutions[0] || currentResolution;
  if (videoResolutionInput) videoResolutionInput.value = safeResolution;
  const currentRatio = String(videoRatioInput?.value || ratios[0] || "16:9");
  const safeRatio = ratios.includes(currentRatio) ? currentRatio : ratios[0] || currentRatio;
  if (videoRatioInput) videoRatioInput.value = safeRatio;
  const maxCount = Math.min(Math.max(Number(caps.max_outputs || 1), 1), 4);
  const currentCount = Math.max(1, Math.min(Number(videoCountInput?.value || 1), maxCount));
  if (videoCountInput) videoCountInput.value = String(currentCount);

  ensureVideoOptionButtons("video-ratio", ratios);
  ensureVideoOptionButtons("video-resolution", resolutions, (value) => String(value).toUpperCase());
  setVideoOptionButtons('[data-field="video-ratio"] button', ratios, safeRatio, undefined, true);
  setVideoOptionButtons('[data-field="video-resolution"] button', resolutions, safeResolution, (value) => String(value).toUpperCase(), true);
  setVideoOptionButtons('[data-field="video-count"] button', [1, 2, 3, 4], currentCount);
  const countButtons = Array.from(document.querySelectorAll('[data-field="video-count"] button'));
  countButtons.forEach((button) => {
    const allowed = Number(button.dataset.value) <= maxCount;
    button.hidden = false;
    button.disabled = !allowed;
    button.setAttribute("aria-disabled", allowed ? "false" : "true");
    button.classList.toggle("is-disabled", !allowed);
    button.title = allowed ? "" : "当前视频接口单次只返回 1 条结果";
  });

  const oldReference = videoReferenceModeInput?.value || "";
  const referenceValue = referenceModes.some(([value]) => value === oldReference) ? oldReference : referenceModes[0]?.[0] || "";
  if (videoReferenceModeInput) videoReferenceModeInput.value = referenceValue;
  document.querySelectorAll('[data-field="video-reference-mode"] button').forEach((button) => {
    const definition = referenceTypeDefinitions.find((item) => item.value === button.dataset.value);
    const supported = modes.has(definition?.capability);
    const label = button.querySelector('span');
    if (label && definition?.capability === 'reference_images') label.textContent = Number(caps.max_reference_images || 1) > 1 ? '多图参考' : '单图参考';
    button.hidden = false;
    button.disabled = !supported;
    button.setAttribute("aria-disabled", supported ? "false" : "true");
    button.title = supported ? "" : "当前模型暂不支持此参考类型";
    button.classList.toggle("is-disabled", !supported);
    button.classList.toggle("is-active", supported && definition?.value === referenceValue);
    button.setAttribute("aria-selected", supported && definition?.value === referenceValue ? "true" : "false");
  });
  const referenceTrigger = document.querySelector('[data-video-reference-trigger]');
  if (referenceTrigger) referenceTrigger.disabled = !referenceModes.length;
  const referenceLabel = document.querySelector('[data-video-reference-label]');
  if (!referenceModes.length && referenceLabel) referenceLabel.textContent = '纯文本生成';
  if (videoMediaReferences) {
    videoMediaReferences.disabled = !referenceModes.length;
    videoMediaReferences.accept = modes.has("omni_reference") ? "image/*,video/*,audio/*" : "image/*";
  }
  const camera = document.querySelector("[data-video-camera]");
  const cameraValues = Array.isArray(caps.camera_movement) ? caps.camera_movement : [];
  if (camera) {
    camera.replaceChildren(...cameraValues.map((value) => new Option(String(value), String(value))));
    camera.disabled = !cameraValues.length;
    if (cameraValues.length) camera.value = cameraValues.includes(camera.value) ? camera.value : String(cameraValues[0]);
  }
  if (composerPrompt && selectedMediaType === "video") composerPrompt.maxLength = caps.max_prompt_chars || 7000;
  syncVideoToolbarLabels();
}

function syncVideoToolbar() {
  if (!videoToolbar) return;
  const visible = selectedMediaType === "video";
  videoToolbar.hidden = !visible;
  videoToolbar.querySelectorAll("input, select, button").forEach((control) => {
    if (!control.matches("[data-panel-trigger], [data-video-upload]")) control.disabled = !visible;
  });
  if (visible) syncVideoCapabilityControls();
  else closeParameterPanels();
}

function syncVideoOptions() {
  syncVideoToolbar();
}
modelInput?.addEventListener("change", () => {
  selectedModelByMediaType[selectedMediaType] = modelInput.value;
  modelInput.title = modelInput.selectedOptions[0]?.textContent || MODEL_KIND_LABELS[selectedMediaType] || "模型";
  syncVideoOptions();
});
videoToolbar?.addEventListener("change", refreshEstimate);

function setTaskState(card, state) {
  if (card) card.dataset.taskState = state;
}

function setConversationDrawer(open) {
  if (!conversationSidebar || !conversationToggle) return;
  conversationSidebar.classList.toggle("is-open", open);
  conversationToggle.setAttribute("aria-expanded", String(open));
  conversationToggle.setAttribute("aria-label", open ? "关闭历史对话" : "打开历史对话");
}

conversationToggle?.addEventListener("click", () => {
  setConversationDrawer(!conversationSidebar?.classList.contains("is-open"));
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && conversationSidebar?.classList.contains("is-open")) setConversationDrawer(false);
});
const PENDING_GENERATION_KEY = "huishi.pendingGeneration";
const PENDING_GENERATION_MAX_AGE_MS = 20 * 60 * 1000;
const PENDING_GENERATION_POLL_INTERVAL_MS = 5000;
const PENDING_GENERATION_HIDDEN_POLL_INTERVAL_MS = 30000;
const PENDING_GENERATION_MAX_POLL_INTERVAL_MS = 20000;
let pendingGenerationPollTimer = 0;
const generationTaskPollTimers = new Map();
const pendingVisibilityPolls = new Map();

let CSRF_TOKEN = "";
let SIZE_MATRIX = null;
let RESOLUTION_LABELS = null;
const DEFAULT_SIZE_MATRIX = {
  "21:9": {"1K": "1680x720", "2K": "3360x1440"},
  "1:1": {"1K": "1024x1024", "2K": "2048x2048"},
  "16:9": {"1K": "1536x864", "2K": "2560x1440", "4K": "3840x2160"},
  "9:16": {"1K": "864x1536", "2K": "1440x2560", "4K": "2160x3840"},
  "3:2": {"1K": "1536x1024", "2K": "2160x1440"},
  "2:3": {"1K": "1024x1536", "2K": "1440x2160"},
  "4:3": {"1K": "1365x1024", "2K": "2048x1536"},
  "3:4": {"1K": "1024x1365", "2K": "1536x2048"},
};

(function initConfig() {
  const rawMatrix = form?.dataset.sizeMatrix;
  const rawLabels = form?.dataset.resolutionLabels;
  try {
    SIZE_MATRIX = { ...DEFAULT_SIZE_MATRIX, ...(rawMatrix ? JSON.parse(rawMatrix) : {}) };
    RESOLUTION_LABELS = rawLabels ? JSON.parse(rawLabels) : {};
  } catch (_) {
    SIZE_MATRIX = { ...DEFAULT_SIZE_MATRIX };
    RESOLUTION_LABELS = {};
  }
  if (!Object.keys(SIZE_MATRIX).length) {
    SIZE_MATRIX = { ...DEFAULT_SIZE_MATRIX };
  }
  if (!Object.keys(RESOLUTION_LABELS).length) {
    RESOLUTION_LABELS = {"1K": "1K", "2K": "2K", "4K": "4K"};
  }

  fetch("/api/csrf-token")
    .then((r) => r.json())
    .then((data) => { CSRF_TOKEN = data.csrf_token || ""; })
    .catch(() => {});
})();

function csrfHeaders() {
  const token = CSRF_TOKEN || document.querySelector('[name="csrf_token"]')?.value || "";
  const headers = {
    "X-Requested-With": "fetch",
    "Accept": "application/json",
  };
  if (token) {
    headers["X-CSRF-Token"] = token;
  }
  return headers;
}

async function readJsonResponse(response, fallbackMessage) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  const text = await response.text().catch(() => "");
  if (response.redirected || response.url.includes("/login")) {
    throw new Error("登录状态已过期，请重新登录后再试。");
  }
  if (response.status === 403 && text.includes("CSRF")) {
    throw new Error("页面安全令牌已过期，请刷新页面后再试。");
  }
  if (response.status >= 500) {
    throw new Error("服务器暂时无法完成请求，请稍后重试。");
  }
  throw new Error(text.replace(/<[^>]+>/g, '').trim().slice(0, 120) || fallbackMessage);
}

function classifyPromptOptimizeError(error) {
  const message = String(error?.message || error || '');
  if (!message) return 'Prompt 优化失败，请稍后重试。';
  if (message.includes('暂未启用 Prompt 优化') || message.includes('缺少') || message.includes('未配置')) {
    return 'Prompt 优化未配置：请到设置页补充 Prompt Base URL、模型名和 API Key。';
  }
  if (message.includes('接口返回了网页内容') || message.includes('结果异常') || message.includes('返回异常')) {
    return 'Prompt 优化返回异常：请检查 Prompt Base URL、模型名和上游服务返回内容。';
  }
  if (
    message.includes('服务器暂时无法完成请求')
    || message.includes('503')
    || message.toLowerCase().includes('service temporarily unavailable')
    || message.toLowerCase().includes('service unavailable')
    || message.includes('上游')
    || message.includes('请求失败')
    || message.includes('Failed to fetch')
    || message.includes('NetworkError')
    || message.includes('Load failed')
    || message.includes('timeout')
  ) {
    return 'Prompt 优化上游请求失败：请检查网络、Base URL 和上游服务状态。';
  }
  return message;
}

function isBalanceShortageMessage(message) {
  const text = String(message || "");
  return text.includes("积分") || text.includes("余额");
}

function formatResolutionLabel(resolution, actualSize = "") {
  const value = resolution || resolutionInput?.value || "2K";
  const suffix = actualSize ? ` · ${actualSize}` : "";
  if (value === "1K") return `标准 1K${suffix}`;
  if (value === "2K") return `高清 2K${suffix}`;
  if (value === "4K") return `超清 4K${suffix}`;
  if (/^\d+x\d+$/.test(value) || /^\d+x\d+$/.test(actualSize)) {
    const ratioSizes = supportedSizesForRatio(ratioInput?.value || "16:9");
    for (const [label, size] of Object.entries(ratioSizes)) {
      if (size === value || size === actualSize) {
        const displayLabel = label === "1K" ? "标准 1K" : label === "2K" ? "高清 2K" : label === "4K" ? "超清 4K" : label;
        return `${displayLabel}${suffix}`;
      }
    }
  }
  return actualSize ? `自定义尺寸 · ${actualSize}` : "自定义尺寸";
}

function shortResolutionLabel(resolution, actualSize = "") {
  const full = formatResolutionLabel(resolution, actualSize);
  if (full.includes("1K")) return "1K";
  if (full.includes("2K")) return "2K";
  if (full.includes("4K")) return "4K";
  return "自定义";
}

function supportedSizesForRatio(ratio) {
  return SIZE_MATRIX[ratio] || SIZE_MATRIX["16:9"] || {};
}

function firstSupportedResolution(ratioSizes) {
  if (ratioSizes["2K"]) return "2K";
  if (ratioSizes["1K"]) return "1K";
  return Object.keys(ratioSizes)[0] || "2K";
}

function maybeNormalizePresetSelection(nextRatio, nextResolution) {
  if (!nextRatio) return { resolution: nextResolution, changed: false };
  const ratioSizes = supportedSizesForRatio(nextRatio);
  if (ratioSizes[nextResolution]) {
    return { resolution: nextResolution, changed: false };
  }
  const fallbackResolution = firstSupportedResolution(ratioSizes);
  return { resolution: fallbackResolution, changed: fallbackResolution !== nextResolution };
}

function customDimensionValues() {
  const width = Number.parseInt(customWidthInput?.value || "", 10);
  const height = Number.parseInt(customHeightInput?.value || "", 10);
  return {
    width: Number.isFinite(width) ? width : 0,
    height: Number.isFinite(height) ? height : 0,
  };
}

function parseFixedRatio(ratio) {
  if (!ratio || !Object.prototype.hasOwnProperty.call(SIZE_MATRIX || {}, ratio)) return null;
  const [ratioWidth, ratioHeight] = String(ratio).split(":").map((part) => Number.parseInt(part, 10));
  if (!Number.isFinite(ratioWidth) || !Number.isFinite(ratioHeight) || ratioWidth <= 0 || ratioHeight <= 0) return null;
  return { ratioWidth, ratioHeight };
}

function nearestLegalSizeForRatio(ratio, width, height) {
  const parsedRatio = parseFixedRatio(ratio);
  if (!parsedRatio) return "";
  const targetWidth = Math.max(1, Number.parseInt(String(width || 0), 10) || 1);
  const targetHeight = Math.max(1, Number.parseInt(String(height || 0), 10) || 1);
  const targetPixels = targetWidth * targetHeight;
  const maxUnit = Math.floor(CUSTOM_SIZE_RULES.maxEdge / Math.max(parsedRatio.ratioWidth, parsedRatio.ratioHeight));
  let bestSize = "";
  let bestScore = null;

  for (let unit = 1; unit <= maxUnit; unit += 1) {
    const candidateWidth = parsedRatio.ratioWidth * unit;
    const candidateHeight = parsedRatio.ratioHeight * unit;
    if (candidateWidth % 16 !== 0 || candidateHeight % 16 !== 0) continue;
    const pixels = candidateWidth * candidateHeight;
    if (pixels < CUSTOM_SIZE_RULES.minPixels || pixels > CUSTOM_SIZE_RULES.maxPixels) continue;
    const score = [
      Math.abs(candidateWidth - targetWidth) + Math.abs(candidateHeight - targetHeight),
      Math.abs(pixels - targetPixels),
      Math.abs(candidateWidth - targetWidth),
    ];
    if (!bestScore || score.some((value, index) => value < bestScore[index] && score.slice(0, index).every((item, priorIndex) => item === bestScore[priorIndex]))) {
      bestScore = score;
      bestSize = `${candidateWidth}x${candidateHeight}`;
    }
  }

  if (bestSize) return bestSize;
  const ratioSizes = Object.values(supportedSizesForRatio(ratio));
  return ratioSizes[0] || "";
}

function nearestLegalCustomSize(width, height) {
  const targetWidth = Math.max(1, Number.parseInt(String(width || 0), 10) || 1);
  const targetHeight = Math.max(1, Number.parseInt(String(height || 0), 10) || 1);
  const targetPixels = targetWidth * targetHeight;
  const targetIsLandscape = targetWidth >= targetHeight;
  let bestSize = "";
  let bestScore = null;

  for (let candidateWidth = 16; candidateWidth <= CUSTOM_SIZE_RULES.maxEdge; candidateWidth += 16) {
    for (let candidateHeight = 16; candidateHeight <= CUSTOM_SIZE_RULES.maxEdge; candidateHeight += 16) {
      const aspectRatio = candidateWidth / candidateHeight;
      if (aspectRatio < CUSTOM_SIZE_RULES.minAspectRatio || aspectRatio > CUSTOM_SIZE_RULES.maxAspectRatio) continue;
      const pixels = candidateWidth * candidateHeight;
      if (pixels < CUSTOM_SIZE_RULES.minPixels || pixels > CUSTOM_SIZE_RULES.maxPixels) continue;
      const orientationPenalty = (candidateWidth >= candidateHeight) === targetIsLandscape ? 0 : 1;
      const score = [
        Math.abs(candidateWidth - targetWidth) + Math.abs(candidateHeight - targetHeight),
        Math.abs(pixels - targetPixels),
        orientationPenalty,
        Math.abs(candidateWidth - targetWidth),
      ];
      if (!bestScore || score.some((value, index) => value < bestScore[index] && score.slice(0, index).every((item, priorIndex) => item === bestScore[priorIndex]))) {
        bestScore = score;
        bestSize = `${candidateWidth}x${candidateHeight}`;
      }
    }
  }

  return bestSize;
}

function customDimensionCorrection(message, width, height) {
  const nearest = nearestLegalCustomSize(width, height);
  return { nearest, message };
}

function applyNearestCustomDimensionCorrection(nearest) {
  if (!nearest || !nearest.includes("x")) return "";
  const [width, height] = nearest.split("x", 2);
  if (customWidthInput) customWidthInput.value = width;
  if (customHeightInput) customHeightInput.value = height;
  if (widthInput) widthInput.value = width;
  if (heightInput) heightInput.value = height;
  if (resolutionInput) resolutionInput.value = nearest;
  return nearest;
}

function correctCustomDimensions() {
  const { width, height } = customDimensionValues();
  if (!width || !height) return { ok: false, corrected: "", message: "请输入自定义宽度和高度" };
  let correction = null;
  if (width > CUSTOM_SIZE_RULES.maxEdge || height > CUSTOM_SIZE_RULES.maxEdge) {
    correction = customDimensionCorrection("自定义尺寸单边最大 3840px", width, height);
  } else if (width % 16 !== 0 || height % 16 !== 0) {
    correction = customDimensionCorrection("自定义尺寸宽高都必须是 16 的倍数", width, height);
  } else {
    const aspectRatio = width / height;
    if (aspectRatio < CUSTOM_SIZE_RULES.minAspectRatio || aspectRatio > CUSTOM_SIZE_RULES.maxAspectRatio) {
      correction = customDimensionCorrection("自定义尺寸宽高比必须在 1:3 到 3:1 之间", width, height);
    }
  }
  const pixels = width * height;
  if (!correction && pixels < CUSTOM_SIZE_RULES.minPixels) {
    correction = customDimensionCorrection("自定义尺寸总像素不能低于 655,360", width, height);
  }
  if (!correction && pixels > CUSTOM_SIZE_RULES.maxPixels) {
    correction = customDimensionCorrection("自定义尺寸总像素不能超过 8,294,400", width, height);
  }
  if (!correction) return { ok: true, corrected: "", message: "" };
  const corrected = applyNearestCustomDimensionCorrection(correction.nearest);
  return corrected ? { ok: true, corrected, message: "" } : { ok: false, corrected: "", message: correction.message };
}

function validateCustomDimensions() {
  const correction = correctCustomDimensions();
  return correction.ok ? "" : correction.message;
}

function syncCustomDimensionInputs({ normalize = false, writeVisible = false } = {}) {
  const { width, height } = customDimensionValues();
  const ratio = ratioInput?.value || "16:9";
  const resolution = width && height
    ? (normalize ? nearestLegalSizeForRatio(ratio, width, height) : `${width}x${height}`)
    : "";
  const [normalizedWidth, normalizedHeight] = resolution.includes("x") ? resolution.split("x", 2) : ["", ""];
  if (writeVisible && normalizedWidth && normalizedHeight) {
    if (customWidthInput) customWidthInput.value = normalizedWidth;
    if (customHeightInput) customHeightInput.value = normalizedHeight;
  }
  if ((writeVisible || normalize) && resolutionInput && resolution) resolutionInput.value = resolution;
  if (widthInput) widthInput.value = normalizedWidth || "";
  if (heightInput) heightInput.value = normalizedHeight || "";
  return resolution;
}

function clearTargetResolutionFields() {
  if (widthInput) widthInput.value = "";
  if (heightInput) heightInput.value = "";
}

function normalizedTargetResolution({ writeHidden = false, writeVisible = false } = {}) {
  const { width, height } = customDimensionValues();
  if (!width || !height) {
    return "";
  }
  const resolution = nearestLegalSizeForRatio(ratioInput?.value || "16:9", width, height);
  const [normalizedWidth, normalizedHeight] = resolution.includes("x") ? resolution.split("x", 2) : ["", ""];
  if (writeVisible && normalizedWidth && normalizedHeight) {
    if (customWidthInput) customWidthInput.value = normalizedWidth;
    if (customHeightInput) customHeightInput.value = normalizedHeight;
  }
  if (writeHidden && normalizedWidth && normalizedHeight) {
    if (widthInput) widthInput.value = normalizedWidth;
    if (heightInput) heightInput.value = normalizedHeight;
  }
  return resolution;
}

function setDimensionError(message = "") {
  [customWidthInput, customHeightInput].forEach((input) => {
    if (!input) return;
    input.classList.toggle("is-error", Boolean(message));
    input.setAttribute("aria-invalid", message ? "true" : "false");
  });
  if (message) setStatus(message, true);
}

function syncSizeDisplay() {
  let ratio = ratioInput?.value || "16:9";
  if (!SIZE_MATRIX[ratio]) {
    ratio = "16:9";
    if (ratioInput) ratioInput.value = ratio;
  }
  const ratioSizes = supportedSizesForRatio(ratio);
  let resolution = resolutionInput?.value || "2K";
  const isCustomResolution = /^\d+x\d+$/.test(resolution);
  if (!ratioSizes[resolution] && !isCustomResolution) {
    const normalized = maybeNormalizePresetSelection(ratio, resolution);
    resolution = normalized.resolution;
    if (resolutionInput) resolutionInput.value = resolution;
  }
  const size = isCustomResolution ? resolution : (ratioSizes[resolution] || Object.values(ratioSizes)[0] || "2560x1440");
  const [width, height] = size.split("x");
  if (!isCustomResolution) {
    if (customWidthInput) customWidthInput.value = width;
    if (customHeightInput) customHeightInput.value = height;
  }
  if (ratioLabel) ratioLabel.textContent = ratio;
  if (resolutionLabel) resolutionLabel.textContent = shortResolutionLabel(resolution, size);
  setDimensionError("");

  document.querySelectorAll('[data-field="ratio"] button').forEach((button) => {
    button.classList.toggle("is-active", button.dataset.value === ratio);
  });
  document.querySelectorAll('[data-field="resolution"] button').forEach((button) => {
    const supported = Boolean(ratioSizes[button.dataset.value]);
    button.disabled = !supported;
    button.setAttribute("aria-disabled", supported ? "false" : "true");
    button.classList.toggle("is-disabled", !supported);
    button.classList.toggle("is-active", button.dataset.value === resolution && supported);
  });
}

function syncReferenceField() {
  if (!modeInput) return;
  const hasReference = Boolean(visibleReferenceMaterials().length);
  if (selectedMediaType === "image") modeInput.value = hasReference ? "reference" : "text";
  form?.classList.toggle("has-reference", hasReference);
  if (referenceImages) referenceImages.required = false;
  syncModeButtons();
}

function syncModeButtons() {
  document.querySelectorAll('[data-field="generation-mode"] [data-value]').forEach((button) => {
    button.classList.toggle("is-active", button.dataset.value === selectedMediaType);
  });
  syncGenerationModePicker();
}

function getEditSeed() {
  const raw = studioShell?.dataset.editSeed || "";
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch (error) {
    return null;
  }
}

function applySeedToComposer(seed) {
  if (!form || !seed) return;
  const promptInput = form.querySelector('[name="prompt"]');
  const countInput = form.querySelector('[name="count"]');
  if (promptInput) promptInput.value = seed.prompt || "";
  const seedMediaType = MEDIA_TYPES.includes(seed.media_type || seed.mediaType || seed.mode) ? (seed.media_type || seed.mediaType || seed.mode) : "image";
  selectedMediaType = seedMediaType;
  if (mediaTypeInput) mediaTypeInput.value = seedMediaType === "image" ? "" : seedMediaType;
  if (modeInput) modeInput.value = seedMediaType === "image" ? (seed.mode || "text") : "text";
  if (ratioInput) ratioInput.value = seed.ratio || "16:9";
  if (resolutionInput) resolutionInput.value = seed.resolution || "2K";
  if (qualityInput) qualityInput.value = seed.quality || "auto";
  if (outputFormatInput) outputFormatInput.value = seed.output_format || "png";
  if (countInput) countInput.value = seed.count || 1;
  if (seed.actual_size && /^\d+x\d+$/.test(seed.actual_size)) {
    const [seedWidth, seedHeight] = seed.actual_size.split("x");
    if (customWidthInput) customWidthInput.value = seedWidth;
    if (customHeightInput) customHeightInput.value = seedHeight;
    if (widthInput) widthInput.value = seedWidth;
    if (heightInput) heightInput.value = seedHeight;
  }
  clearReferenceImages();
  (seed.reference_paths || []).forEach((path) => addReferencePath(path));
  syncModeButtons();
  syncMediaType();
  if (modelInput && seed.model && Array.from(modelInput.options).some((option) => option.value === String(seed.model))) {
    modelInput.value = String(seed.model);
    selectedModelByMediaType[selectedMediaType] = modelInput.value;
  }
  syncReferenceField();
  syncSizeDisplay();
  refreshEstimate();
  autosizePrompt();
}

function isImageFile(file) {
  return /^image\/(png|jpe?g|webp)$/i.test(file?.type || "");
}

function isVideoReferenceFile(file) {
  return /^(image|video|audio)\//i.test(file?.type || "")
    || /\.(png|jpe?g|webp|gif|avif|mp4|webm|mov|m4v|mp3|wav|m4a|ogg|aac|flac)$/i.test(file?.name || "");
}

function materialMediaType(item) {
  if (item?.mediaType) return item.mediaType;
  if (item?.type === "path") return "image";
  return item?.file && isImageFile(item.file) ? "image" : "video";
}

function visibleReferenceMaterials() {
  return referenceMaterials.filter((item) => {
    if (selectedMediaType === "video") return materialMediaType(item) === "video";
    return materialMediaType(item) === "image";
  });
}

function maxReferenceBytes() {
  const configured = Number(form?.dataset.maxReferenceBytes || 0);
  return Number.isFinite(configured) && configured > 0 ? configured : 12 * 1024 * 1024;
}

function formatByteLimit(bytes) {
  if (bytes >= 1024 * 1024) return `${Math.round(bytes / (1024 * 1024))}MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)}KB`;
  return `${bytes}B`;
}

function isReferenceFileTooLarge(file) {
  return Number(file?.size || 0) > maxReferenceBytes();
}

function getReferenceFileMaterials(mediaType = "") {
  return referenceMaterials.filter((item) => item.type === "file" && item.file && (!mediaType || materialMediaType(item) === mediaType));
}

function getReferencePathMaterials() {
  return referenceMaterials.filter((item) => item.type === "path" && item.path);
}

function rebuildReferenceFileInput() {
  parseReferencePathList(referencePathsInput?.value || "").forEach((path) => addReferencePath(path));
  if (referenceImages && typeof DataTransfer === "function") {
    referenceTransfer = new DataTransfer();
    getReferenceFileMaterials("image").forEach((item) => referenceTransfer.items.add(item.file));
    referenceImages.files = referenceTransfer.files;
  }
  if (videoMediaReferences && typeof DataTransfer === "function") {
    videoReferenceTransfer = new DataTransfer();
    getReferenceFileMaterials("video").forEach((item) => videoReferenceTransfer.items.add(item.file));
    videoMediaReferences.files = videoReferenceTransfer.files;
  }
  if (referencePathsInput) {
    referencePathsInput.value = getReferencePathMaterials().map((item) => item.path).join(",");
  }
}

function syncReferenceFieldSource() {
  if (!referencePathsInput) return;
  referencePathsInput.value = getReferencePathMaterials().map((item) => item.path).join(",");
}

function parseReferencePathList(value) {
  if (Array.isArray(value)) {
    return value.map((item) => String(item || "").trim()).filter(Boolean);
  }
  const raw = String(value || "").trim();
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.map((item) => String(item || "").trim()).filter(Boolean);
    }
  } catch (_) {}
  return raw.split(",").map((item) => item.trim()).filter(Boolean);
}

function materialDisplayName(item) {
  if (item.name) return item.name;
  if (item.file?.name) return item.file.name;
  if (item.path) return item.path.split(/[\\/]/).pop() || item.path;
  return "参考图";
}

function applyComposerSeed(seed, submitImmediately = false) {
  if (!form || !seed) return;
  const prompt = String(seed.prompt || "");
  const promptInput = form.querySelector('[name="prompt"]');
  if (promptInput) promptInput.value = prompt;
  const seedMediaType = MEDIA_TYPES.includes(seed.mode) ? seed.mode : "image";
  selectedMediaType = seedMediaType;
  if (mediaTypeInput) mediaTypeInput.value = seedMediaType === "image" ? "" : seedMediaType;
  if (modeInput) modeInput.value = seedMediaType === "image" ? (seed.mode || "text") : "text";
  if (createDialogueInput) createDialogueInput.value = seed.dialogue_id ? "0" : (createDialogueInput.value || "0");
  if (ratioInput && seed.ratio) ratioInput.value = seed.ratio;
  if (resolutionInput && seed.resolution) resolutionInput.value = seed.resolution;
  if (qualityInput && seed.quality) qualityInput.value = seed.quality;
  if (outputFormatInput && seed.output_format) outputFormatInput.value = seed.output_format;
  if (countInput && seed.count) countInput.value = String(seed.count);
  if (seed.actualSize && /^\d+x\d+$/.test(seed.actualSize)) {
    const [seedWidth, seedHeight] = String(seed.actualSize).split("x");
    if (customWidthInput) customWidthInput.value = seedWidth;
    if (customHeightInput) customHeightInput.value = seedHeight;
    if (widthInput) widthInput.value = seedWidth;
    if (heightInput) heightInput.value = seedHeight;
  }
  clearReferenceImages();
  parseReferencePathList(seed.referencePaths || seed.reference_paths).forEach((path) => addReferencePath(path));
  syncModeButtons();
  syncMediaType();
  syncReferenceField();
  syncSizeDisplay();
  refreshEstimate();
  form.scrollIntoView({ behavior: "smooth", block: "center" });
  form.querySelector('[name="prompt"]')?.focus();
  autosizePrompt();
  if (!submitImmediately) return;
  const hasSavedReferences = getReferencePathMaterials().length > 0;
  const hasUploadedReferences = getReferenceFileMaterials().length > 0;
  if (modeInput?.value !== "reference" || hasSavedReferences || hasUploadedReferences) {
    form.requestSubmit();
    return;
  }
  if (modeInput?.value === "reference") {
    setStatus("参考图编辑需要重新上传参考图后再生成。", true);
  }
}

function addReferenceFiles(files) {
  return addReferenceFilesForMode(files, "image");
}

function addVideoReferenceFiles(files) {
  return addReferenceFilesForMode(files, "video");
}

function addSelectedReferenceFiles(files) {
  return selectedMediaType === "video" ? addVideoReferenceFiles(files) : addReferenceFiles(files);
}

function addReferenceFilesForMode(files, mediaType) {
  const incoming = Array.from(files || []).filter(Boolean);
  if (!incoming.length) return false;
  const invalid = incoming.find((file) => mediaType === "image" ? !isImageFile(file) : !isVideoReferenceFile(file));
  if (invalid) {
    setStatus(mediaType === "image" ? "参考图格式仅支持 PNG、JPG、JPEG、WEBP" : "视频参考支持图片、视频和音频文件", true);
    return false;
  }
  const oversized = incoming.find((file) => isReferenceFileTooLarge(file));
  if (oversized) {
    setStatus(`参考图大小不能超过 ${formatByteLimit(maxReferenceBytes())}`, true);
    return false;
  }
  const available = Math.max(0, maxReferenceImages - visibleReferenceMaterials().length);
  if (!available) {
    setStatus(`参考素材最多支持 ${maxReferenceImages} 项`, true);
    return false;
  }
  if (incoming.length > available) {
    setStatus(`参考素材最多支持 ${maxReferenceImages} 项`, true);
    return false;
  }
  incoming.slice(0, available).forEach((file) => {
    referenceMaterials.push({
      id: `file-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      type: "file",
      mediaType,
      file,
      name: file.name,
      src: URL.createObjectURL(file),
    });
  });
  renderReferenceMaterials();
  refreshEstimate();
  setStatus("");
  return true;
}

function addReferencePath(path, name) {
  const referencePath = (path || "").trim();
  if (!referencePath) return false;
  if (referenceMaterials.some((item) => item.type === "path" && item.path === referencePath)) return false;
  if (referenceMaterials.length >= maxReferenceImages) return false;
  referenceMaterials.push({
    id: `path-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    type: "path",
    mediaType: selectedMediaType === "video" ? "video" : "image",
    path: referencePath,
    name: name || materialDisplayName({ path: referencePath }),
    src: referencePath,
  });
  renderReferenceMaterials();
  refreshEstimate();
  return true;
}

function materialFileKind(item) {
  const type = String(item?.file?.type || "").toLowerCase();
  if (type.startsWith("video/")) return "video";
  if (type.startsWith("audio/")) return "audio";
  return "image";
}

function appendMaterialPreview(container, item) {
  const kind = materialFileKind(item);
  if (kind === "video") {
    const video = document.createElement("video");
    video.src = item.src;
    video.muted = true;
    video.playsInline = true;
    video.preload = "metadata";
    video.setAttribute("aria-label", materialDisplayName(item));
    container.appendChild(video);
    return;
  }
  if (kind === "audio") {
    const audio = document.createElement("span");
    audio.className = "reference-media-placeholder reference-media-placeholder-audio";
    audio.setAttribute("aria-hidden", "true");
    audio.textContent = "♫";
    container.appendChild(audio);
    return;
  }
  const image = document.createElement("img");
  image.src = item.src;
  image.alt = materialDisplayName(item);
  image.loading = "lazy";
  container.appendChild(image);
}

function renderVideoReferenceSummary(materials) {
  if (!videoReferenceMaterials) return;
  // Uploaded files stay in the thumbnail stack and picker. The @ control
  // displays the selected subject instead of an unrelated list of all files.
  videoReferenceMaterials.replaceChildren();
  videoReferenceMaterials.hidden = true;
}

function renderReferenceMaterials() {
  const materials = visibleReferenceMaterials();
  if (referencePreview) {
    referencePreview.innerHTML = "";
    materials.forEach((item, index) => {
      const tile = document.createElement("div");
      tile.className = "reference-material-tile";
      tile.dataset.referenceId = item.id;
      tile.draggable = true;
      tile.style.setProperty("--stack-index", String(index));
      tile.setAttribute("role", "button");
      tile.tabIndex = 0;
      if (item.path) tile.dataset.referencePath = item.path;
      tile.dataset.referenceName = materialDisplayName(item);
      tile.setAttribute("aria-label", `预览参考素材：${materialDisplayName(item)}`);
      appendMaterialPreview(tile, item);
      const name = document.createElement("span");
      name.className = "reference-material-name";
      name.textContent = materialDisplayName(item);
      tile.appendChild(name);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "reference-remove";
      remove.setAttribute("aria-label", `移除参考图：${materialDisplayName(item)}`);
      remove.textContent = "×";
      tile.appendChild(remove);

      referencePreview.appendChild(tile);
    });
  }
  const hasReference = Boolean(materials.length);
  const collapsedSpace = Math.max(materials.length - 1, 0) * 4 + 70;
  referenceStack?.style.setProperty("--reference-count", String(materials.length || 1));
  referenceStack?.style.setProperty("--reference-expanded-width", `${Math.max(materials.length - 1, 0) * 52 + 36}px`);
  form?.style.setProperty("--reference-collapsed-space", `${hasReference ? collapsedSpace : 76}px`);
  referenceStack?.classList.toggle("has-materials", hasReference);
  referenceStack?.classList.toggle("is-empty", !hasReference);
  if (!hasReference) referenceStack?.classList.remove("is-expanded");
  referencePreview?.classList.toggle("is-visible", hasReference);
  referenceField?.classList.toggle("is-visible", hasReference);
  if (referenceClearButton) referenceClearButton.hidden = !hasReference;
  renderVideoReferenceSummary(selectedMediaType === "video" ? materials : []);
  if (selectedMediaType === "video") renderVideoSubjects();
  rebuildReferenceFileInput();
  syncReferenceField();
}

function removeReferenceMaterial(id) {
  const item = referenceMaterials.find((material) => material.id === id);
  if (!item) return;
  if (item.type === "file" && item.src) URL.revokeObjectURL(item.src);
  referenceMaterials = referenceMaterials.filter((material) => material.id !== id);
  if (selectedVideoSubjectId === `material-${id}`) {
    selectedVideoSubjectId = "";
    syncSelectedVideoSubjectInput();
  }
  syncReferenceFieldSource();
  renderReferenceMaterials();
  refreshEstimate();
}

function openReferencePreview(item) {
  if (!item?.src || !referencePreviewModal || !referencePreviewImage) return;
  if (materialFileKind(item) !== "image") {
    setStatus(`已添加${materialFileKind(item) === "audio" ? "音频" : "视频"}参考：${materialDisplayName(item)}`);
    return;
  }
  referencePreviewImage.src = item.src;
  referencePreviewImage.alt = materialDisplayName(item);
  if (referencePreviewCaption) referencePreviewCaption.textContent = materialDisplayName(item);
  if (referencePreviewModal.showModal) {
    referencePreviewModal.showModal();
  }
}

function closeReferencePreview() {
  if (!referencePreviewModal) return;
  referencePreviewModal.close();
  if (referencePreviewImage) {
    referencePreviewImage.src = "";
    referencePreviewImage.alt = "";
  }
  if (referencePreviewCaption) referencePreviewCaption.textContent = "";
}

function renderReferencePreview() {
  if (!addReferenceFiles(referenceImages?.files || [])) {
    renderReferenceMaterials();
  }
}

function setReferenceFiles(files) {
  return addReferenceFiles(files);
}

function clearReferenceImages() {
  if (referenceImages) referenceImages.value = "";
  if (videoMediaReferences) videoMediaReferences.value = "";
  if (referencePathsInput) referencePathsInput.value = "";
  referenceTransfer = null;
  videoReferenceTransfer = null;
  referenceMaterials.forEach((item) => {
    if (item.type === "file" && item.src) URL.revokeObjectURL(item.src);
  });
  referenceMaterials = [];
  selectedVideoSubjectId = "";
  syncSelectedVideoSubjectInput();
  renderReferenceMaterials();
  refreshEstimate();
}

function setStatus(message, isError = false) {
  if (!statusLine) {
    if (isError && message) window.alert(message);
    return;
  }
  statusLine.textContent = message || "";
  statusLine.classList.toggle("is-error", isError);
}

function showPromptError(message = "请输入提示词") {
  if (!composerPrompt) {
    setStatus(message, true);
    return;
  }
  setStatus("");
  composerPrompt.classList.add("is-error");
  composerPrompt.setAttribute("aria-invalid", "true");
  composerPrompt.dataset.defaultPlaceholder ||= composerPrompt.getAttribute("placeholder") || "";
  composerPrompt.setAttribute("placeholder", message);
  composerPrompt.focus();
}

function clearPromptError() {
  if (!composerPrompt?.classList.contains("is-error")) return;
  composerPrompt.classList.remove("is-error");
  composerPrompt.removeAttribute("aria-invalid");
  composerPrompt.setAttribute(
    "placeholder",
    composerPrompt.dataset.defaultPlaceholder || `上传最多${maxReferenceImages}个参考素材，输入文字或参考内容，定义精彩互动。`
  );
}

function updateComposerPromptState() {
  if (!form || !composerPrompt) return;
  form.classList.toggle("has-prompt", Boolean(composerPrompt.value.trim()));
}

function ensureRestorePromptButton() {
  if (restorePromptButton && !restorePromptButton.isConnected) {
    restorePromptButton = null;
  }
  if (restorePromptButton || !optimizePromptButton) return restorePromptButton;
  restorePromptButton = document.createElement("button");
  restorePromptButton.type = "button";
  restorePromptButton.dataset.restorePrompt = "1";
  restorePromptButton.className = "restore-prompt-button";
  restorePromptButton.textContent = "恢复原提示词";
  restorePromptButton.hidden = true;
  optimizePromptButton.insertAdjacentElement("afterend", restorePromptButton);
  restorePromptButton.addEventListener("click", () => {
    if (!composerPrompt || !lastPromptBeforeOptimization) return;
    composerPrompt.value = lastPromptBeforeOptimization;
    const cursorPosition = composerPrompt.value.length;
    composerPrompt.setSelectionRange(cursorPosition, cursorPosition);
    composerPrompt.focus();
    autosizePrompt();
    setStatus("已恢复原提示词");
    lastPromptBeforeOptimization = "";
    restorePromptButton.hidden = true;
  });
  return restorePromptButton;
}

async function runPromptOptimization() {
  const prompt = (composerPrompt?.value || "").trim();
  if (!prompt) {
    showPromptError();
    return;
  }
  if (optimizePromptButton) {
    optimizePromptButton.disabled = true;
    optimizePromptButton.classList.add("is-optimizing");
    optimizePromptButton.setAttribute("aria-busy", "true");
  }
  try {
    const response = await fetch("/api/prompt/optimize", {
      method: "POST",
      headers: {
        ...csrfHeaders(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ prompt, style: promptStyle?.value || "通用增强" }),
    });
    const result = await readJsonResponse(response, "优化失败");
    if (!response.ok || !result.ok) throw new Error(result.error || "优化失败");
    const optimizedPrompt = String(result.optimized_prompt || prompt).trim();
    if (looksLikeAbnormalOptimizedPrompt(optimizedPrompt)) {
      throw new Error("Prompt 优化返回异常：请检查 Prompt Base URL、模型名和上游服务返回内容。");
    }
    if (composerPrompt) {
      lastPromptBeforeOptimization = composerPrompt.value;
      composerPrompt.value = optimizedPrompt || prompt;
      const cursorPosition = composerPrompt.value.length;
      composerPrompt.setSelectionRange(cursorPosition, cursorPosition);
      const restoreButton = ensureRestorePromptButton();
      if (restoreButton) restoreButton.hidden = false;
    }
    clearPromptError();
    setStatus("提示词已优化");
    autosizePrompt();
    composerPrompt?.focus();
  } catch (error) {
    setStatus(classifyPromptOptimizeError(error), true);
  } finally {
    if (optimizePromptButton) {
      optimizePromptButton.disabled = false;
      optimizePromptButton.classList.remove("is-optimizing");
      optimizePromptButton.removeAttribute("aria-busy");
    }
  }
}

function looksLikeAbnormalOptimizedPrompt(text) {
  const value = String(text || "").trim();
  if (!value) return true;
  if (value.length > 5000) return true;
  const compact = value.replace(/\s+/g, "");
  if (compact.length >= 256 && compact.length % 4 === 0 && /^[A-Za-z0-9+/=]+$/.test(compact)) return true;
  const lowered = value.toLowerCase();
  if ((lowered.startsWith("{") || lowered.startsWith("[")) && [
    "\"api_key\"",
    "\"base_url\"",
    "\"site_subtitle\"",
    "\"home_content\"",
    "\"hide_css_import\"",
    "\"content_info\"",
  ].some((key) => lowered.includes(key))) {
    return true;
  }
  return false;
}

function shouldConfirmRegenerate() {
  return localStorage.getItem(REGENERATE_SKIP_KEY) !== "1";
}

function setSkipRegenerateConfirm(skip) {
  localStorage.setItem(REGENERATE_SKIP_KEY, skip ? "1" : "0");
}

async function confirmRegenerate(cost) {
  if (!shouldConfirmRegenerate()) return true;
  if (!regenerateModal?.showModal) {
    return window.confirm(`再次生成会消耗 ${cost || "-"} 点，确认继续？`);
  }
  if (regenerateMessage) regenerateMessage.textContent = `再次生成会消耗 ${cost || "-"} 点，确认继续？`;
  regenerateModal.showModal();
  return new Promise((resolve) => {
    confirmRegenerateButton.onclick = () => {
      setSkipRegenerateConfirm(Boolean(skipRegenerateConfirm?.checked));
      regenerateModal.close();
      resolve(true);
    };
    cancelRegenerateButton.onclick = () => {
      regenerateModal.close();
      resolve(false);
    };
  });
}

function showShortage(message) {
  if (shortageMessage) shortageMessage.textContent = message || "当前积分不足，无法开始生成。";
  if (shortageModal?.showModal) shortageModal.showModal();
}

function modeText(mode) {
  return mode === "reference" ? "参考图编辑" : "文生图";
}

function recordMediaType(record) {
  const explicit = String(record?.media_type || "").trim().toLowerCase();
  if (["image", "video", "speech", "music", "audio"].includes(explicit)) return explicit;
  const source = String(record?.asset_source || "").trim().toLowerCase();
  if (["video", "audio"].includes(source)) return source;
  const mode = String(record?.mode || "").trim().toLowerCase();
  return ["video", "speech", "music"].includes(mode) ? mode : "image";
}

function mediaModeText(mode, mediaType) {
  const type = String(mediaType || "").trim().toLowerCase();
  if (type === "video") return "视频生成";
  if (type === "speech" || type === "audio") return "语音合成";
  if (type === "music") return "音乐生成";
  return modeText(mode);
}

function simplifyGenerationError(message) {
  const raw = message || "";
  if (raw.includes("Upstream request failed") || raw.includes("upstream_error")) {
    return "接口请求失败，请检查接口配置或稍后重试。";
  }
  return raw.replace(/^生成失败：?/, "") || "生成失败，请稍后重试。";
}

function closeParameterPanels(exceptId = "") {
  document.querySelectorAll(".parameter-popover").forEach((panel) => {
    if (panel.id !== exceptId) {
      panel.hidden = true;
      delete panel.dataset.mentionOpen;
    }
  });
  document.querySelectorAll("[data-panel-trigger]").forEach((button) => {
    const panel = document.querySelector(`#${button.dataset.panelTrigger}`);
    button.setAttribute("aria-expanded", panel && !panel.hidden ? "true" : "false");
  });
}

function bindParameterControls() {
  document.querySelectorAll("[data-panel-trigger]").forEach((button) => {
    button.addEventListener("click", () => {
      const panel = document.querySelector(`#${button.dataset.panelTrigger}`);
      if (!panel) return;
      const willOpen = panel.hidden;
      closeParameterPanels(panel.id);
      if (willOpen && panel.id === 'subject-panel') renderVideoSubjects(false);
      panel.hidden = !willOpen;
      button.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
      if (willOpen) positionParameterPanel(button, panel);
    });
  });

  document.querySelectorAll("[data-field] button[data-value]").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.closest("[data-field]");
      const field = group?.dataset.field;
      if (field === "generation-mode") {
        if (modelInput) selectedModelByMediaType[selectedMediaType] = modelInput.value;
        selectedMediaType = button.dataset.value || "image";
        syncMediaType();
        setGenerationModeMenuOpen(false);
        closeParameterPanels();
        return;
      }
      const input = field ? document.querySelector(`#${field}`) : null;
      if (!input || button.disabled) return;
      input.value = button.dataset.value || input.value;
      if (field?.startsWith("video-")) {
        if (field === "video-ratio") videoRatioInput.value = button.dataset.value || videoRatioInput.value;
        if (field === "video-resolution") videoResolutionInput.value = button.dataset.value || videoResolutionInput.value;
        if (field === "video-count") videoCountInput.value = button.dataset.value || videoCountInput.value;
        if (field === "video-reference-mode") videoReferenceModeInput.value = button.dataset.value || videoReferenceModeInput.value;
        syncVideoCapabilityControls();
        refreshEstimate();
        closeParameterPanels();
        document.querySelector(`[data-panel-trigger="${group.closest(".parameter-popover")?.id}"]`)?.focus();
        return;
      }
      if (field === "resolution") {
        const ratioSizes = supportedSizesForRatio(ratioInput?.value || "16:9");
        const size = ratioSizes[button.dataset.value || ""] || "";
        if (size.includes("x")) {
          const [presetWidth, presetHeight] = size.split("x", 2);
          if (customWidthInput) customWidthInput.value = presetWidth;
          if (customHeightInput) customHeightInput.value = presetHeight;
        }
        clearTargetResolutionFields();
      }
      group.querySelectorAll("button").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      if (field === "ratio") {
        const previousResolution = resolutionInput?.value || "2K";
        const normalized = maybeNormalizePresetSelection(button.dataset.value, previousResolution);
        if (normalized.changed) {
          if (resolutionInput) resolutionInput.value = normalized.resolution;
        }
        const ratioSizes = supportedSizesForRatio(button.dataset.value || "16:9");
        const size = ratioSizes[resolutionInput?.value || "2K"] || "";
        if (size.includes("x")) {
          const [presetWidth, presetHeight] = size.split("x", 2);
          if (customWidthInput) customWidthInput.value = presetWidth;
          if (customHeightInput) customHeightInput.value = presetHeight;
        }
        clearTargetResolutionFields();
        syncSizeDisplay();
        syncReferenceField();
        refreshEstimate();
        return;
      }
      if (field === "resolution") {
        setStatus("");
        syncSizeDisplay();
        syncReferenceField();
        refreshEstimate();
        return;
      }
      syncReferenceField();
      syncSizeDisplay();
      refreshEstimate();
      closeParameterPanels();
      document.querySelector(`[data-panel-trigger="${group.closest(".parameter-popover")?.id}"]`)?.focus();
    });
  });

  function applyCustomDimensions() {
    clearTargetResolutionFields();
    const { width, height } = customDimensionValues();
    if (resolutionInput && width && height) resolutionInput.value = `${width}x${height}`;
    setDimensionError("");
    syncSizeDisplay();
    refreshEstimate();
  }

  if (customWidthInput) customWidthInput.addEventListener("input", applyCustomDimensions);
  if (customHeightInput) customHeightInput.addEventListener("input", applyCustomDimensions);
  if (customWidthInput) customWidthInput.addEventListener("blur", refreshEstimate);
  if (customHeightInput) customHeightInput.addEventListener("blur", refreshEstimate);

  document.addEventListener("click", (event) => {
    if (event.target === composerPrompt && selectedMediaType === 'video' && activeSubjectMention()) return;
    if (!event.target.closest(".parameter-popover") && !event.target.closest("[data-panel-trigger]")) {
      closeParameterPanels();
    }
  });
}

function positionParameterPanel(button, panel) {
  const composerRect = form?.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  if (!composerRect) return;
  const desiredWidth = panel.dataset.popoverWidth ? parseInt(panel.dataset.popoverWidth, 10) : 540;
  const panelWidth = Math.min(desiredWidth || 540, window.innerWidth - 28);
  const viewportLeft = Math.max(14, Math.min(buttonRect.left + buttonRect.width / 2 - panelWidth / 2, window.innerWidth - panelWidth - 14));
  const left = viewportLeft - composerRect.left;
  const panelHeight = panel.offsetHeight || 340;
  const preferredTop = buttonRect.top - panelHeight - 12;
  const viewportTop = Math.max(14, Math.min(preferredTop, window.innerHeight - panelHeight - 14));
  const top = viewportTop - composerRect.top;
  panel.style.left = `${left}px`;
  panel.style.right = "auto";
  panel.style.top = `${top}px`;
  panel.style.bottom = "auto";
  panel.style.width = `${panelWidth}px`;
}

function videoSubjectEntries() {
  return visibleReferenceMaterials()
    .filter((item) => materialFileKind(item) === "image")
    .map((item) => ({
      id: `material-${item.id}`,
      name: materialDisplayName(item),
      fileId: item.id,
      fileName: materialDisplayName(item),
      originalName: materialDisplayName(item),
      fileType: item.file?.type || "",
    }));
}

function selectedVideoSubjectMaterial() {
  const subject = videoSubjectEntries().find((entry) => entry.id === selectedVideoSubjectId);
  if (!subject) return null;
  const material = referenceMaterials.find((item) => item.id === subject.fileId);
  return material && materialFileKind(material) === "image" ? material : null;
}

function selectedSubjectFileIndex() {
  const subject = selectedVideoSubjectMaterial();
  if (!subject) return -1;
  return getReferenceFileMaterials("video").findIndex((item) => item.id === subject.id);
}

function orderedVideoReferenceMaterials() {
  const materials = getReferenceFileMaterials("video");
  const subject = selectedVideoSubjectMaterial();
  if (!subject) return materials;
  return [subject, ...materials.filter((item) => item.id !== subject.id)];
}

function renderVideoSubjects(filterMention = true) {
  const empty = document.querySelector("[data-subject-empty]");
  const list = document.querySelector("[data-subject-list]");
  if (!empty || !list) return;
  const allSubjects = videoSubjectEntries();
  const query = filterMention ? activeSubjectMention()?.query.toLocaleLowerCase() || '' : '';
  const subjects = allSubjects.filter(subject => !query || subject.fileName.toLocaleLowerCase().includes(query));
  if (selectedVideoSubjectId && !allSubjects.some((subject) => subject.id === selectedVideoSubjectId)) {
    selectedVideoSubjectId = "";
  }
  syncSelectedVideoSubjectInput();
  empty.hidden = subjects.length > 0;
  const emptyMessage = document.querySelector('[data-subject-empty] p');
  if (emptyMessage) emptyMessage.textContent = allSubjects.length ? '没有匹配的主体，请修改 @ 后的名称' : '请先上传主体图片';
  const upload = document.querySelector('[data-add-subject-image]');
  if (upload) upload.hidden = allSubjects.length > 0;
  list.hidden = subjects.length === 0;
  list.replaceChildren(...subjects.map((subject) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "subject-item";
    button.dataset.subjectId = subject.id;
    button.dataset.subjectFile = subject.fileName || subject.originalName || "";
    button.title = subject.fileName || subject.originalName || subject.name;
    const material = referenceMaterials.find((item) => item.id === subject.fileId)
      || referenceMaterials.find((item) => materialDisplayName(item) === (subject.fileName || subject.originalName));
    if (material) {
      const preview = document.createElement("span");
      preview.className = "subject-file-preview";
      appendMaterialPreview(preview, material);
      button.appendChild(preview);
    } else {
      const preview = document.createElement("span");
      preview.className = "subject-file-preview subject-file-preview-placeholder";
      preview.textContent = String(subject.fileType || "").startsWith("audio/") ? "♫" : "@";
      button.appendChild(preview);
    }
    const copy = document.createElement("span");
    copy.className = "subject-item-copy";
    const name = document.createElement("strong");
    name.className = "subject-file-name";
    name.textContent = subject.fileName || subject.originalName || subject.name;
    copy.appendChild(name);
    button.appendChild(copy);
    button.classList.toggle("is-active", subject.id === selectedVideoSubjectId);
    return button;
  }));
}

function insertSubjectMention(subject) {
  if (!composerPrompt || !subject) return;
  const label = String(subject.fileName || subject.originalName || subject.name || "").trim();
  if (!label) return;
  const mention = `@${label}`;
  const value = composerPrompt.value || "";
  const activeMention = activeSubjectMention();
  const start = activeMention ? activeMention.start - 1 : Number.isFinite(composerPrompt.selectionStart) ? composerPrompt.selectionStart : value.length;
  const end = Number.isFinite(composerPrompt.selectionEnd) ? composerPrompt.selectionEnd : start;
  const prefix = start > 0 && !/\s$/.test(value.slice(0, start)) ? " " : "";
  const suffix = " ";
  composerPrompt.value = `${value.slice(0, start)}${prefix}${mention}${suffix}${value.slice(end)}`;
  const cursorPosition = start + prefix.length + mention.length + suffix.length;
  composerPrompt.setSelectionRange(cursorPosition, cursorPosition);
  composerPrompt.dispatchEvent(new Event("input", { bubbles: true }));
  composerPrompt.focus();
}

function syncSubjectMentionMenu() {
  if (selectedMediaType !== 'video') return;
  const panel = document.querySelector('#subject-panel');
  const trigger = document.querySelector('[data-subject-trigger]');
  if (!panel || !trigger) return;
  if (activeSubjectMention()) {
    renderVideoSubjects();
    closeParameterPanels(panel.id);
    panel.hidden = false;
    panel.dataset.mentionOpen = '1';
    trigger.setAttribute('aria-expanded', 'true');
    positionParameterPanel(trigger, panel);
  } else if (panel.dataset.mentionOpen) {
    delete panel.dataset.mentionOpen;
    panel.hidden = true;
    trigger.setAttribute('aria-expanded', 'false');
  }
}

function bindVideoWorkbenchControls() {
  composerPrompt?.addEventListener('input', syncSubjectMentionMenu);
  composerPrompt?.addEventListener('click', syncSubjectMentionMenu);
  composerPrompt?.addEventListener('keyup', event => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) syncSubjectMentionMenu();
  });
  composerPrompt?.addEventListener('keydown', event => {
    const panel = document.querySelector('#subject-panel');
    if (!panel || panel.hidden) return;
    if (event.key === 'Escape') { closeParameterPanels(); event.preventDefault(); }
    if (event.key === 'ArrowDown') { panel.querySelector('.subject-item')?.focus(); event.preventDefault(); }
  });
  document.querySelector('[data-subject-list]')?.addEventListener('keydown', event => {
    const entries = Array.from(document.querySelectorAll('[data-subject-list] .subject-item'));
    const index = entries.indexOf(event.target);
    if (event.key === 'Escape') { closeParameterPanels(); composerPrompt?.focus(); }
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      entries[(index + (event.key === 'ArrowDown' ? 1 : -1) + entries.length) % entries.length]?.focus();
    }
  });
  // Keep the textarea's insertion point when choosing a subject with a mouse.
  document.querySelector('[data-subject-list]')?.addEventListener('mousedown', event => {
    if (event.target.closest('[data-subject-id]')) event.preventDefault();
  });
  videoDurationSlider?.addEventListener("input", () => {
    let model;
    try { model = JSON.parse(videoDurationSlider.dataset.durationModel || "null"); } catch (_) { return; }
    if (!model) return;
    const value = videoDurationAtPosition(model, Number(videoDurationSlider.value));
    videoDurationSlider.value = String(model.kind === "discrete" ? model.durations.indexOf(value) : model.kind === "fixed" ? 0 : value);
    videoDurationSlider.setAttribute("aria-valuetext", `${value} 秒`);
    if (videoDurationInput) videoDurationInput.value = String(value);
    syncVideoToolbarLabels();
    refreshEstimate();
  });
  videoMediaReferences?.addEventListener("change", () => {
    if (!addVideoReferenceFiles(videoMediaReferences.files || [])) renderReferenceMaterials();
    syncReferenceField();
  });
  document.querySelector("[data-add-subject-image]")?.addEventListener("click", () => {
    subjectImageInput?.click();
  });
  subjectImageInput?.addEventListener("change", () => {
    const previousIds = new Set(referenceMaterials.map((item) => item.id));
    const added = addVideoReferenceFiles(subjectImageInput.files || []);
    subjectImageInput.value = "";
    if (added) {
      const uploadedSubject = [...referenceMaterials].reverse().find((item) =>
        !previousIds.has(item.id) && materialFileKind(item) === "image"
      );
      if (uploadedSubject) {
        selectedVideoSubjectId = `material-${uploadedSubject.id}`;
        syncSelectedVideoSubjectInput();
      }
    }
    if (!added) renderReferenceMaterials();
    syncReferenceField();
    renderVideoSubjects(false);
  });
  document.querySelector("[data-subject-list]")?.addEventListener("click", (event) => {
    const item = event.target.closest("[data-subject-id]");
    if (!item) return;
    selectedVideoSubjectId = item.dataset.subjectId || "";
    syncSelectedVideoSubjectInput();
    const subject = videoSubjectEntries().find((entry) => entry.id === item.dataset.subjectId);
    insertSubjectMention(subject);
    renderVideoSubjects();
    closeParameterPanels();
  });
  renderVideoSubjects();
}

async function legacyRefreshEstimate() {
  if (!form || !estimate) return;
  syncSizeDisplay();
  syncReferenceField();
  const resolution = normalizedTargetResolution({ writeHidden: false, writeVisible: false });
  const formData = new FormData(form);
  const params = new URLSearchParams(formData);
  if (resolution.includes("x")) {
    const [width, height] = resolution.split("x", 2);
    params.set("width", width);
    params.set("height", height);
    params.set("resolution", resolution);
  }
  try {
    const response = await fetch(`/api/estimate?${params.toString()}`);
    const result = await readJsonResponse(response, "估价失败");
    estimate.textContent = result.ok ? `${result.cost} 点` : result.error;
  } catch (error) {
    estimate.textContent = "估价失败";
  }
}

function buildEstimateParams() {
  if (!form || !estimate) return "";
  syncSizeDisplay();
  syncReferenceField();
  const resolution = normalizedTargetResolution({ writeHidden: false, writeVisible: false });
  const formData = new FormData(form);
  const params = new URLSearchParams(formData);
  if (selectedMediaType === "video") {
    const selectedVideoModel = modelCatalogForMediaType("video").find((entry) => entry.id === modelInput?.value);
    const videoCaps = selectedVideoModel?.capabilities || {};
    const selectedResolution = formData.get("video_resolution") || videoCaps.resolutions?.[0] || "";
    const selectedDuration = formData.get("duration_seconds") || videoCaps.durations?.[0] || videoCaps.duration_range?.min || "";
    const selectedRatio = formData.get("video_ratio") || videoCaps.ratios?.[0] || "";
    if (selectedResolution) params.set("resolution", selectedResolution);
    if (selectedDuration) params.set("duration_seconds", selectedDuration);
    if (selectedRatio) params.set("ratio", selectedRatio);
    params.set("count", "1");
    params.delete("media_references");
    return params.toString();
  }
  if (resolution.includes("x")) {
    const [width, height] = resolution.split("x", 2);
    params.set("width", width);
    params.set("height", height);
    params.set("resolution", resolution);
  }
  return params.toString();
}

async function requestEstimateRefresh() {
  const params = buildEstimateParams();
  if (!params) {
    activeEstimateParams = "";
    estimateAbortController?.abort();
    estimateAbortController = null;
    return;
  }
  if (params === lastEstimateParams || params === activeEstimateParams) return;
  estimateAbortController?.abort();
  const controller = new AbortController();
  estimateAbortController = controller;
  activeEstimateParams = params;
  const requestSerial = ++estimateRequestSerial;
  try {
    const response = await fetch(`/api/estimate?${params}`, { signal: controller.signal });
    const result = await readJsonResponse(response, "估价失败");
    if (requestSerial !== estimateRequestSerial) return;
    estimate.textContent = result.ok ? `${result.cost} 点` : result.error;
    lastEstimateParams = params;
  } catch (error) {
    if (error?.name === "AbortError") return;
    if (requestSerial !== estimateRequestSerial) return;
    estimate.textContent = "估价失败";
    lastEstimateParams = "";
  } finally {
    if (estimateAbortController === controller) estimateAbortController = null;
    if (activeEstimateParams === params) activeEstimateParams = "";
  }
}

function refreshEstimate() {
  if (!form || !estimate) return;
  if (estimateRefreshTimer) window.clearTimeout(estimateRefreshTimer);
  estimateRefreshTimer = window.setTimeout(() => {
    estimateRefreshTimer = 0;
    void requestEstimateRefresh();
  }, 120);
}

function recordsForDisplay(record) {
  const records = Array.isArray(record?.records) && record.records.length ? record.records : [record].filter(Boolean);
  return [...records].sort((left, right) => {
    const leftIndex = Number.parseInt(String(left?.group_index ?? 0), 10) || 0;
    const rightIndex = Number.parseInt(String(right?.group_index ?? 0), 10) || 0;
    if (leftIndex !== rightIndex) return leftIndex - rightIndex;
    return (Number.parseInt(String(left?.id || 0), 10) || 0) - (Number.parseInt(String(right?.id || 0), 10) || 0);
  });
}

function escapeAttribute(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function imagePathsForRecordEditing(records) {
  return records
    .map((item) => item?.image_path || (Array.isArray(item?.images) ? item.images[0] : ""))
    .map((path) => String(path || "").trim())
    .filter(Boolean);
}

function workspaceReturnUrlForDialogue(dialogueId) {
  const id = String(dialogueId || "").trim();
  return id ? `/workspace?dialogue=${encodeURIComponent(id)}` : "/workspace";
}

function _buildImageGrid(records, prompt, returnUrl = "/workspace") {
  const encodedReturnUrl = encodeURIComponent(returnUrl || "/workspace");
  return records.map((item, index) => {
    const imagePath = item?.image_path || (Array.isArray(item?.images) ? item.images[0] : "");
    const mediaType = recordMediaType(item);
    const safePath = escapeAttribute(imagePath);
    const safePrompt = escapeAttribute(prompt || "");
    const media = mediaType === "video"
      ? `<video ${index === 0 ? 'id="current-video"' : ""} class="creation-media-video" src="${safePath}" controls preload="metadata" aria-label="${safePrompt}"></video>`
      : mediaType === "speech" || mediaType === "music" || mediaType === "audio"
        ? `<audio ${index === 0 ? 'id="current-audio"' : ""} class="creation-media-audio" src="${safePath}" controls preload="metadata" aria-label="${safePrompt}"></audio>`
        : `<img ${index === 0 ? 'id="current-image"' : ""} src="${safePath}" alt="${safePrompt}" loading="lazy" draggable="true" data-reference-path="${safePath}">`;
    return `
        <figure class="creation-image-wrap" data-media-type="${escapeAttribute(mediaType)}">
          <a class="creation-image-link" href="/assets/${item?.id}?from=workspace&next=${encodedReturnUrl}" data-detail-link aria-label="查看参数">
            ${media}
          </a>
        </figure>
  `;
  }).join("");
}

function findExistingCreationRecord(record) {
  if (!currentCanvas || !record) return null;
  const recordId = String(record.id || "").trim();
  if (recordId) {
    const existingRecord = currentCanvas.querySelector(`.creation-item[data-record-id="${CSS.escape(recordId)}"]`);
    if (existingRecord) return existingRecord;
  }
  const groupId = String(record.generation_group_id || "").trim();
  if (groupId) {
    return currentCanvas.querySelector(`.creation-item[data-generation-group-id="${CSS.escape(groupId)}"]`);
  }
  return null;
}

function renderCurrentRecord(record, replaceElement = null) {
  if (!isWorkspaceComposerPage || !currentCanvas || !record) return;
  replaceElement ||= findExistingCreationRecord(record);
  const mediaType = recordMediaType(record);
  const wasEmpty = currentCanvas.classList.contains("empty-creation-stage");
  currentCanvas.classList.remove("empty-creation-stage");
  currentCanvas.classList.add("creation-stream");
  if (wasEmpty) currentCanvas.innerHTML = "";
  const existingFeatured = currentCanvas.querySelector(".creation-item.is-featured");
  existingFeatured?.classList.remove("is-featured");
  existingFeatured?.classList.add("is-previous");
  const displayRecords = recordsForDisplay(record);
  const returnUrl = workspaceReturnUrlForDialogue(record.dialogue_id || currentDialogueId());
  const imageGrid = _buildImageGrid(displayRecords, record.prompt, returnUrl);
  const editImagePaths = JSON.stringify(imagePathsForRecordEditing(displayRecords));
  const metaItems = [mediaModeText(record.mode, mediaType), record.model_source || "", record.ratio || ratioInput?.value || "16:9", formatResolutionLabel(record.resolution, record.actual_size)].filter(Boolean);
  const referenceList = parseReferencePathList(record.reference_paths || []);
  const referencePaths = JSON.stringify(referenceList);
  const article = document.createElement("article");
  article.className = "creation-item is-featured";
  setTaskState(article, "success");
  article.dataset.recordId = record.id;
  article.dataset.generationGroupId = record.generation_group_id || "";
  article.dataset.createdAt = record.created_at || "";
  article.dataset.mediaType = mediaType;
  article.dataset.model = record.model_source || "";
  const canEditImages = displayRecords.some((item) => recordMediaType(item) === "image");
  article.innerHTML = `
      <div class="creation-record-head">
      <div class="creation-reference-strip reference-material-stack" data-record-references ${referenceList.length ? "" : "hidden"}>
        <div class="reference-material-list"></div>
      </div>
      <p class="creation-prompt" tabindex="0"></p>
      </div>
      <div class="creation-result-frame">
      <div class="creation-image-grid" data-image-count="${displayRecords.length}">
        ${imageGrid}
      </div>
      <div class="creation-toolbar">
        <div class="creation-action-group">
          <button type="button" data-refill-record data-prompt="" data-mode="${escapeAttribute(record.mode)}" data-media-type="${escapeAttribute(mediaType)}" data-model="${escapeAttribute(record.model_source || "")}" data-ratio="${escapeAttribute(record.ratio)}" data-resolution="${escapeAttribute(record.resolution)}" data-actual-size="${escapeAttribute(record.actual_size || "")}">重新编辑</button>
          ${canEditImages ? `<button type="button" data-edit-record-images data-prompt="" data-mode="${escapeAttribute(record.mode)}" data-media-type="${escapeAttribute(mediaType)}" data-model="${escapeAttribute(record.model_source || "")}" data-ratio="${escapeAttribute(record.ratio)}" data-resolution="${escapeAttribute(record.resolution)}" data-actual-size="${escapeAttribute(record.actual_size || "")}" data-edit-image-paths="${escapeAttribute(editImagePaths)}">编辑图片</button>` : ""}
          <button type="button" data-regenerate-record data-prompt="" data-mode="${escapeAttribute(record.mode)}" data-media-type="${escapeAttribute(mediaType)}" data-model="${escapeAttribute(record.model_source || "")}" data-ratio="${escapeAttribute(record.ratio)}" data-resolution="${escapeAttribute(record.resolution)}" data-actual-size="${escapeAttribute(record.actual_size || "")}">再次生成</button>
          <form method="post" action="/assets/bulk/delete" data-confirm-delete="删除后不可恢复，确认删除这组图片？">
            ${displayRecords.map((item) => `<input type="hidden" name="ids" value="${item.id}">`).join("")}
            <input type="hidden" name="from" value="workspace">
            <input type="hidden" name="next" value="${window.location.pathname}${window.location.search}">
            <button type="submit" class="action-delete">删除</button>
          </form>
        </div>
        <footer class="creation-meta" id="current-meta" aria-label="生成参数">
          ${metaItems.map((item) => `<span>${item}</span>`).join("")}
        </footer>
      </div>
      </div>
  `;
  article.querySelector(".creation-prompt").textContent = record.prompt;
  article.querySelector(".creation-prompt").title = record.prompt;
  const referenceStrip = article.querySelector("[data-record-references]");
  if (referenceStrip && referenceList.length) {
    const list = referenceStrip.querySelector(".reference-material-list");
    if (list) list.innerHTML = renderReferenceStackItems(referenceList);
    referenceStrip.style.setProperty("--reference-expanded-width", `${Math.max(referenceList.length - 1, 0) * 52 + 36}px`);
    referenceStrip.hidden = false;
  }
  article.classList.toggle("has-reference", Boolean(referenceList.length));
  article.querySelectorAll("img").forEach((image) => {
    if (!image.closest("[data-record-references]")) image.alt = record.prompt;
  });
  article.querySelectorAll("[data-prompt]").forEach((button) => {
    button.dataset.prompt = record.prompt;
    button.dataset.mediaType = mediaType;
    button.dataset.model = record.model_source || "";
    button.dataset.referencePaths = referencePaths;
  });
  article.querySelectorAll("[data-edit-record-images]").forEach((button) => {
    button.dataset.prompt = record.prompt;
    button.dataset.editImagePaths = editImagePaths;
  });
  if (replaceElement?.isConnected) {
    replaceElement.replaceWith(article);
  } else {
    currentCanvas.appendChild(article);
  }
  appendCreationElementBySubmittedTime(article);
  if (dialogueInput && record.dialogue_id) dialogueInput.value = record.dialogue_id;
  scrollCreationIntoView(article, "smooth");
  bindRecordActionButtons();
  bindDetailReturnLinks(article);
  bindConfirmDeleteForms(article);
  setComposerCollapsed(true);
}

function taskReferencePreviewFromFormData(formData) {
  const savedPath = parseReferencePathList(formData.getAll("reference_paths"))[0] || "";
  if (savedPath) return savedPath;
  const activeMaterial = referenceMaterials.find((item) => item?.src || item?.path);
  return activeMaterial?.src || activeMaterial?.path || "";
}

function taskReferencePreviewsFromFormData(formData) {
  const savedPaths = parseReferencePathList(formData.getAll("reference_paths"));
  if (savedPaths.length) return savedPaths;
  return referenceMaterials.map((item) => item?.src || item?.path).filter(Boolean);
}

function renderReferenceStackItems(paths) {
  return parseReferencePathList(paths).map((path, index) => `
      <button type="button" class="reference-material-tile" data-reference-preview-path="${escapeAttribute(path)}" aria-label="查看参考图" style="--stack-index: ${index};">
        <img src="${escapeAttribute(path)}" alt="参考图" loading="lazy" draggable="false">
      </button>
    `).join("");
}

function creationSortValue(element) {
  const rawCreatedAt = String(element?.dataset?.createdAt || "").trim();
  const timestamp = rawCreatedAt ? Date.parse(rawCreatedAt) : Number.NaN;
  if (Number.isFinite(timestamp)) return timestamp;
  const index = Number(element?.dataset?.createdIndex || 0);
  return Number.isFinite(index) ? index : 0;
}

function creationTaskPriority(element) {
  const state = String(element?.dataset?.taskState || "").trim();
  const phase = String(element?.dataset?.taskPhase || "").trim();
  if (state === "failed") return 2;
  if (phase === "needs_reconciliation" || state === "recovering") return -1;
  if (element?.dataset?.serverTaskId || state === "queued" || state === "running") return 0;
  return 1;
}

function compareCreationElements(left, right) {
  const priorityDifference = creationTaskPriority(left) - creationTaskPriority(right);
  if (priorityDifference) return priorityDifference;
  const timeDifference = creationSortValue(left) - creationSortValue(right);
  if (timeDifference) return timeDifference;
  return Number(left?.dataset?.createdIndex || 0) - Number(right?.dataset?.createdIndex || 0);
}

function appendCreationElementBySubmittedTime(element) {
  if (!currentCanvas || !element) return;
  const siblings = Array.from(currentCanvas.children).filter((child) => child !== element);
  const next = siblings.find((child) => compareCreationElements(element, child) < 0);
  if (next) {
    currentCanvas.insertBefore(element, next);
    return;
  }
  currentCanvas.appendChild(element);
}

function setTaskReferencePreview(card, previewPaths) {
  const reference = card?.querySelector("[data-task-reference]");
  if (!card || !reference) return;
  const paths = parseReferencePathList(previewPaths);
  const list = reference.querySelector("[data-task-reference-list]");
  card.classList.toggle("has-reference", Boolean(paths.length));
  if (paths.length && list) {
    list.innerHTML = renderReferenceStackItems(paths);
    reference.style.setProperty("--reference-expanded-width", `${Math.max(paths.length - 1, 0) * 52 + 36}px`);
    reference.hidden = false;
    return;
  }
  if (list) list.innerHTML = "";
  reference.hidden = true;
}

function rebuildTaskCardSummary(card) {
  if (!card) return {};
  card.innerHTML = `
    <div class="generation-task-summary" data-task-summary>
      <figure class="generation-reference-stack reference-material-stack" data-task-reference hidden>
        <div class="reference-material-list" data-task-reference-list></div>
      </figure>
      <div class="generation-task-copy">
        <p class="generation-task-prompt creation-prompt" data-task-prompt tabindex="0"></p>
        <footer class="generation-task-params creation-meta" data-task-params aria-label="生成参数"></footer>
        <div class="generation-progress-pill">
          <span data-task-progress></span>
          <span class="task-spinner" aria-hidden="true"></span>
        </div>
      </div>
    </div>
  `;
  return {
    taskPrompt: card.querySelector("[data-task-prompt]"),
    params: card.querySelector("[data-task-params]"),
    progress: card.querySelector("[data-task-progress]"),
    reference: card.querySelector("[data-task-reference]"),
  };
}

function formatTaskParameterText({ mode, mediaType, model, ratio, resolution, actualSize, count, referencePaths }) {
  const parts = [];
  parts.push(mediaModeText(mode, mediaType));
  if (model) parts.push(model);
  const ratioText = String(ratio || "").trim();
  if (ratioText && (!mediaType || mediaType === "image")) parts.push(ratioText);
  const resolutionText = formatResolutionLabel(resolution, actualSize);
  if (resolutionText && (!mediaType || mediaType === "image")) parts.push(shortResolutionLabel(resolution, actualSize));
  if ((!mediaType || mediaType === "image") && count && String(count) !== "1") parts.push(`${count} 张`);
  if ((!mediaType || mediaType === "image") && Array.isArray(referencePaths) && referencePaths.length) parts.push(`参考图 ${referencePaths.length}`);
  return parts.filter(Boolean);
}

function renderTaskCard(formData) {
  if (!isWorkspaceComposerPage || !taskRegion || !taskTemplate) return null;
  if (currentCanvas?.classList.contains("empty-creation-stage")) {
    currentCanvas.innerHTML = "";
  }
  if (currentCanvas) {
    currentCanvas.classList.remove("empty-creation-stage");
    currentCanvas.classList.add("creation-stream", "is-awaiting-result");
  }
  const clone = taskTemplate.content.cloneNode(true);
  const card = clone.querySelector(".generation-task-card");
  setTaskState(card, "queued");
  const prompt = formData.get("prompt") || "";
  const mode = formData.get("mode") || "text";
  const mediaType = formData.get("media_type") || (mode === "video" ? "video" : mode === "speech" ? "speech" : mode === "music" ? "music" : "image");
  const ratio = formData.get("ratio") || "";
  const formWidth = String(formData.get("width") || "");
  const formHeight = String(formData.get("height") || "");
  const fallbackResolution = String(formData.get("resolution") || "");
  const count = formData.get("count") || "1";
  const cost = estimate?.textContent || "";
  const referencePaths = parseReferencePathList(formData.getAll("reference_paths"));
  const referencePreviews = taskReferencePreviewsFromFormData(formData);
  card.dataset.prompt = String(prompt);
  card.dataset.mode = String(mode);
  card.dataset.mediaType = String(mediaType);
  card.dataset.model = String(formData.get("model") || "");
  card.dataset.ratio = String(ratio);
  card.dataset.resolution = String(formData.get("resolution") || "");
  card.dataset.count = String(count);
  card.dataset.cost = cost;
  card.dataset.referencePaths = JSON.stringify(referencePaths);
  card.dataset.createdAt = String(formData.get("created_at") || Date.now());
  card.classList.toggle("has-reference", Boolean(referencePreviews.length));
  const { taskPrompt, params, progress, reference } = rebuildTaskCardSummary(card);
  if (taskPrompt) {
    const fullPrompt = String(prompt);
    taskPrompt.textContent = fullPrompt;
    taskPrompt.dataset.fullPrompt = fullPrompt;
    taskPrompt.title = fullPrompt;
    taskPrompt.setAttribute("aria-label", fullPrompt);
    taskPrompt.setAttribute("tabindex", "0");
  }
  const sizeText = formWidth && formHeight
    ? `${formWidth}x${formHeight}`
    : (fallbackResolution.includes("x") ? fallbackResolution : (customWidthInput?.value && customHeightInput?.value ? `${customWidthInput.value}x${customHeightInput.value}` : fallbackResolution));
  card.dataset.actualSize = sizeText;
  if (params) {
    params.textContent = "";
    const paramItems = formatTaskParameterText({
      mode,
      mediaType,
      model: formData.get("model") || "",
      ratio,
      resolution: card.dataset.resolution || fallbackResolution,
      actualSize: sizeText,
      count,
      referencePaths,
    });
    params.replaceChildren(...paramItems.map((item) => {
      const span = document.createElement("span");
      span.textContent = item;
      return span;
    }));
  }
  if (reference) setTaskReferencePreview(card, referencePreviews);
  if (progress) progress.textContent = "绘世正在生成";
  currentCanvas?.appendChild(clone);
  scrollCreationIntoView(card, "smooth"); // block:nearest，减少不必要的大幅滚动
  return card;
}

function renderTaskCardFromTask(task) {
  const formData = new FormData();
  formData.set("prompt", task?.prompt || "");
  formData.set("mode", task?.mode || "text");
  formData.set("media_type", task?.media_type || "");
  formData.set("model", task?.model || "");
  formData.set("ratio", task?.ratio || "");
  formData.set("resolution", task?.actual_size || task?.resolution || "");
  const actualSize = String(task?.actual_size || task?.resolution || "");
  if (actualSize.includes("x")) {
    const [width, height] = actualSize.split("x", 2);
    formData.set("width", width || "");
    formData.set("height", height || "");
  }
  formData.set("count", String(task?.count || "1"));
  formData.set("created_at", task?.created_at || "");
  parseReferencePathList(task?.reference_paths || []).forEach((path) => formData.append("reference_paths", path));
  const previousEstimate = estimate?.textContent || "";
  if (estimate && task?.cost) estimate.textContent = `${task.cost} 点`;
  const card = renderTaskCard(formData);
  if (estimate) estimate.textContent = previousEstimate;
  if (!card) return null;
  card.dataset.serverTaskId = String(task?.id || "");
  card.dataset.dialogueId = String(task?.dialogue_id || "");
  card.dataset.resolution = task?.resolution || "";
  card.dataset.actualSize = task?.actual_size || task?.resolution || "";
  card.dataset.createdAt = task?.created_at || card.dataset.createdAt || "";
  card.dataset.taskPhase = task?.phase || "";
  card.dataset.taskStatus = task?.status || "";
  card.dataset.referencePaths = JSON.stringify(parseReferencePathList(task?.reference_paths || []));
  appendCreationElementBySubmittedTime(card);
  return card;
}

function latestRenderedRecordId() {
  const featured = currentCanvas?.querySelector(".creation-item.is-featured[data-record-id]");
  return featured?.dataset.recordId || "";
}

function currentDialogueId() {
  return String(dialogueInput?.value || "").trim();
}

function syncWorkspaceUrlToDialogue(dialogueId) {
  const id = String(dialogueId || "").trim();
  if (!id || window.location.pathname.replace(/\/+$/, "") !== "/workspace") return;
  const nextUrl = new URL(window.location.href);
  nextUrl.search = "";
  nextUrl.searchParams.set("dialogue", id);
  window.history.replaceState(window.history.state, "", `${nextUrl.pathname}${nextUrl.search}`);
}

function upsertDialogueInSidebar(dialogue) {
  const id = String(dialogue?.id || "").trim();
  const title = String(dialogue?.title || "").trim();
  const list = document.querySelector(".dialogue-list");
  if (!id || !title || !list) return;
  list.querySelector(".sidebar-empty")?.remove();
  let row = list.querySelector(`[data-dialogue-row][data-dialogue-id="${CSS.escape(id)}"]`);
  if (!row) {
    row = document.createElement("div");
    row.className = "dialogue-row";
    row.dataset.dialogueRow = "";
    row.dataset.dialogueId = id;
    row.innerHTML = `
      <a class="dialogue-link" href="/workspace?dialogue=${encodeURIComponent(id)}">
        <span></span>
      </a>
      <div class="dialogue-menu" data-dialogue-menu>
        <button type="button" class="dialogue-menu-trigger" data-dialogue-menu-trigger aria-label="对话操作" title="对话操作">...</button>
        <div class="dialogue-menu-panel" data-dialogue-menu-panel hidden>
          <button type="button" data-delete-dialogue>删除</button>
        </div>
      </div>
    `;
  }
  const link = row.querySelector(".dialogue-link");
  if (link) {
    link.href = `/workspace?dialogue=${encodeURIComponent(id)}`;
    link.querySelector("span").textContent = title;
  }
  list.prepend(row);
  bindDialogueMenus(row);
  setActiveDialogueInSidebar(id);
}

function syncDialogue(dialogue) {
  const id = String(dialogue?.id || "").trim();
  if (!id) return;
  upsertDialogueInSidebar(dialogue);
  if (dialogueInput) dialogueInput.value = id;
  if (createDialogueInput) createDialogueInput.value = "0";
  syncWorkspaceUrlToDialogue(id);
  setActiveDialogueInSidebar(id);
}

function setActiveDialogueInSidebar(dialogueId) {
  const id = String(dialogueId || "").trim();
  document.querySelectorAll(".dialogue-link.active").forEach((link) => link.classList.remove("active"));
  if (!id) return;
  document.querySelector(`[data-dialogue-row][data-dialogue-id="${CSS.escape(id)}"] .dialogue-link`)?.classList.add("active");
}

function belongsToCurrentDialogue(dialogueId) {
  const current = currentDialogueId();
  const candidate = String(dialogueId || "").trim();
  // Historical video submissions had no dialogue. Keep their outcome visible.
  if (!candidate) return true;
  if (current) return candidate === current;
  return !candidate;
}

function pendingSnapshotFromForm(formData) {
  const width = String(formData.get("width") || "");
  const height = String(formData.get("height") || "");
  return {
    id: `client-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    prompt: String(formData.get("prompt") || ""),
    mode: String(formData.get("media_type") || formData.get("mode") || "text"),
    mediaType: String(formData.get("media_type") || ""),
    model: String(formData.get("model") || ""),
    ratio: String(formData.get("ratio") || ""),
    resolution: String(formData.get("resolution") || ""),
    actualSize: width && height ? `${width}x${height}` : String(formData.get("resolution") || ""),
    count: String(formData.get("count") || "1"),
    cost: estimate?.textContent || "",
    dialogueId: String(formData.get("dialogue_id") || ""),
    referencePaths: formData.getAll("reference_paths").map((item) => String(item || "")).filter(Boolean),
    latestRecordId: latestRenderedRecordId(),
    createdAt: Date.now(),
  };
}

function storePendingGeneration(snapshot) {
  try {
    window.sessionStorage?.setItem(PENDING_GENERATION_KEY, JSON.stringify(snapshot));
  } catch (_) {}
}

function clearPendingGeneration() {
  try {
    window.sessionStorage?.removeItem(PENDING_GENERATION_KEY);
  } catch (_) {}
  if (pendingGenerationPollTimer) {
    window.clearTimeout(pendingGenerationPollTimer);
    pendingGenerationPollTimer = 0;
  }
}

function clearTaskPoll(taskId) {
  const key = String(taskId || "");
  const timer = generationTaskPollTimers.get(key);
  if (timer) window.clearTimeout(timer);
  generationTaskPollTimers.delete(key);
  pendingVisibilityPolls.delete(key);
}

function isDocumentHidden() {
  return typeof document !== "undefined" && document.visibilityState === "hidden";
}

function nextPollDelay(attempt = 0) {
  const multiplier = Math.min(Math.max(Number(attempt) || 0, 0), 2) + 1;
  return Math.min(PENDING_GENERATION_POLL_INTERVAL_MS * multiplier, PENDING_GENERATION_MAX_POLL_INTERVAL_MS);
}

function mergeServerTaskIntoPending(task) {
  if (!task?.id) return;
  const current = readPendingGeneration() || {};
  storePendingGeneration({
    ...current,
    id: current.id || `server-${task.id}`,
    serverTaskId: String(task.id),
    prompt: task.prompt || current.prompt || "",
    mode: task.mode || current.mode || "text",
    mediaType: task.media_type || current.mediaType || "",
    model: task.model || current.model || "",
    ratio: task.ratio || current.ratio || "",
    resolution: task.resolution || current.resolution || "",
    actualSize: task.actual_size || task.resolution || current.actualSize || "",
    count: String(task.count || current.count || "1"),
    cost: task.cost ? `${task.cost} 点` : (current.cost || ""),
    dialogueId: task.dialogue_id ? String(task.dialogue_id) : (current.dialogueId || ""),
    referencePaths: parseReferencePathList(task.reference_paths || current.referencePaths || []),
    latestRecordId: current.latestRecordId || latestRenderedRecordId(),
    createdAt: current.createdAt || Date.now(),
  });
}

function syncDialogueFromTask(task) {
  if (!task?.dialogue_id || !dialogueInput) return;
  dialogueInput.value = String(task.dialogue_id);
  if (createDialogueInput) createDialogueInput.value = "0";
  syncWorkspaceUrlToDialogue(task.dialogue_id);
  setActiveDialogueInSidebar(task.dialogue_id);
}

function readPendingGeneration() {
  try {
    const raw = window.sessionStorage?.getItem(PENDING_GENERATION_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch (_) {
    clearPendingGeneration();
    return null;
  }
}

function renderRestoredPendingGeneration(snapshot) {
  if (!belongsToCurrentDialogue(snapshot.dialogueId)) {
    clearPendingGeneration();
    return;
  }
  const formData = new FormData();
  formData.set("prompt", snapshot.prompt || "");
  formData.set("mode", snapshot.mode || "text");
  formData.set("media_type", snapshot.mediaType || "");
  formData.set("model", snapshot.model || "");
  formData.set("ratio", snapshot.ratio || "");
  formData.set("resolution", snapshot.resolution || snapshot.actualSize || "");
  formData.set("count", snapshot.count || "1");
  parseReferencePathList(snapshot.referencePaths || []).forEach((path) => formData.append("reference_paths", path));
  const previousEstimate = estimate?.textContent || "";
  if (estimate && snapshot.cost) estimate.textContent = snapshot.cost;
  const card = renderTaskCard(formData);
  if (estimate) estimate.textContent = previousEstimate;
  if (!card) return;
  card.dataset.clientTaskId = snapshot.id || "";
  if (snapshot.serverTaskId) card.dataset.serverTaskId = String(snapshot.serverTaskId);
  card.dataset.latestRecordId = snapshot.latestRecordId || "";
  card.dataset.dialogueId = snapshot.dialogueId || "";
  const progress = card.querySelector("[data-task-progress]");
  if (progress) progress.textContent = "绘世正在生成";
  void reconcileRestoredPendingGeneration(card, snapshot);
}

function handleTaskResult(card, task) {
  if (!task) return false;
  if (card) {
    card.dataset.taskPhase = task.phase || "";
    card.dataset.taskStatus = task.status || "";
  }
  if (task.dialogue && !currentDialogueId()) syncDialogue(task.dialogue);
  if (!belongsToCurrentDialogue(task.dialogue_id)) {
    clearTaskPoll(task.id);
    card?.remove();
    return true;
  }
  if (card) card.dataset.billingMessage = task.billing_message || '';
  if (task.status === "succeeded" && task.record) {
    setTaskState(card, "success");
    clearTaskPoll(task.id);
    clearPendingGeneration();
    if (Array.isArray(task.records) && task.records.length) task.record.records = task.records;
    renderCurrentRecord(task.record, card);
    return true;
  }
  if (task.status === "failed") {
    setTaskState(card, "failed");
    clearTaskPoll(task.id);
    clearPendingGeneration();
    markTaskFailed(card, task.error_message || "生成失败");
    appendCreationElementBySubmittedTime(card);
    return true;
  }
  if (task.status === "running" || task.status === "queued") {
    setTaskState(card, task.status);
    mergeServerTaskIntoPending(task);
    syncDialogueFromTask(task);
    const progress = card?.querySelector("[data-task-progress]");
    const paused = task.phase === 'needs_reconciliation';
    const recovering = Boolean(task.recovery_error);
    card?.classList.toggle('is-recovering', recovering || paused);
    if (paused) clearTaskPoll(task.id);
    if (progress) {
      const phases = { submitting: "正在提交", polling: "正在生成", persisting: "正在保存", settling: "正在入库", needs_reconciliation: "等待管理员核对" };
      const title = document.createElement('strong');
      title.textContent = paused ? '任务已暂停，等待管理员核对' : recovering ? '渠道暂时不可用，等待恢复' : phases[task.phase] || '正在生成';
      const detail = document.createElement('span');
      const attempts = Number(task.recovery_attempts || 0);
      detail.textContent = paused
        ? `${task.provider_task_id ? '原任务已保留' : '上游是否受理尚未确认'}，请管理员核对。不会自动重试或重复提交。`
        : recovering ? `已暂停等待管理员核对（第 ${attempts || 1} 次异常），不会自动重试或重复提交。` : `任务 #${task.id}`;
      const fee = document.createElement('span');
      fee.textContent = task.billing_message || '';
      progress.replaceChildren(title, detail, fee);
      if (recovering) {
        const error = document.createElement('details');
        const summary = document.createElement('summary');
        summary.textContent = `查看原因 · 任务 #${task.id}`;
        const text = document.createElement('span');
        text.textContent = task.recovery_error;
        error.append(summary, text);
        progress.append(error);
      }
    }
    appendCreationElementBySubmittedTime(card);
    return true;
  }
  return false;
}

function shouldPollGenerationTask(task) {
  return Boolean(task && (task.status === "running" || task.status === "queued") && task.phase !== "needs_reconciliation");
}

function activeSubjectMention() {
  if (!composerPrompt) return null;
  const cursor = Number.isFinite(composerPrompt.selectionStart) ? composerPrompt.selectionStart : (composerPrompt.value || "").length;
  if (Number.isFinite(composerPrompt.selectionEnd) && composerPrompt.selectionEnd !== cursor) return null;
  const prefix = (composerPrompt.value || "").slice(0, cursor);
  const at = prefix.lastIndexOf('@');
  if (at < 0) return null;
  const query = prefix.slice(at + 1);
  if (/[\r\n]/.test(query)) return null;
  // Spaces may be part of the original filename, but the space after a
  // completed mention must close the picker instead of searching forever.
  if (/\s/.test(query) && !videoSubjectEntries().some(subject =>
    subject.fileName.toLocaleLowerCase().startsWith(query.toLocaleLowerCase()))) return null;
  return { start: at + 1, query };
}

async function pollGenerationTask(card, taskId, attempt = 0) {
  if (!taskId) return;
  try {
    const response = await fetch(`/api/generation/tasks/${encodeURIComponent(taskId)}`, { headers: { "Accept": "application/json" } });
    const result = await readJsonResponse(response, "检查生成任务失败");
    if (response.ok && result.ok && handleTaskResult(card, result.task)) {
      if (shouldPollGenerationTask(result.task)) {
        scheduleGenerationTaskPoll(card, taskId, 0);
      }
    } else {
      const progress = card?.querySelector('[data-task-progress]');
      if (progress) {
        progress.textContent = '任务状态查询失败，已停止自动查询；请手动刷新，切勿重复提交';
        addManualTaskRefresh(progress, card, taskId);
      }
    }
  } catch (_) {
    const progress = card?.querySelector('[data-task-progress]');
    if (progress) {
      progress.textContent = '任务状态查询失败，已停止自动查询；请手动刷新，切勿重复提交';
      addManualTaskRefresh(progress, card, taskId);
    }
  }
}

function addManualTaskRefresh(progress, card, taskId) {
  if (!progress) return;
  const existing = progress.querySelector('[data-task-refresh]');
  if (existing) {
    existing.disabled = false;
    return;
  }
  const refresh = document.createElement('button');
  refresh.type = 'button';
  refresh.dataset.taskRefresh = '1';
  refresh.textContent = '刷新状态';
  refresh.addEventListener('click', () => {
    refresh.disabled = true;
    void pollGenerationTask(card, taskId, 0);
  });
  progress.append(refresh);
}

function scheduleGenerationTaskPoll(card, taskId, attempt = 0) {
  const key = String(taskId || "");
  if (!key || generationTaskPollTimers.has(key) || pendingVisibilityPolls.has(key)) return;
  if (attempt >= 8) {
    const progress = card?.querySelector('[data-task-progress]');
    if (progress) {
      progress.textContent = '暂时无法获取状态，已暂停自动查询。后台任务保留，请勿重新提交。';
      addManualTaskRefresh(progress, card, key);
    }
    card?.classList.add('is-recovering');
    return;
  }
  if (isDocumentHidden()) {
    pendingVisibilityPolls.set(key, { card, taskId: key, attempt });
    return;
  }
  const timer = window.setTimeout(() => {
    generationTaskPollTimers.delete(key);
    void pollGenerationTask(card, key, attempt);
  }, nextPollDelay(attempt));
  generationTaskPollTimers.set(key, timer);
}

async function reconcileRestoredPendingGeneration(card, snapshot) {
  if (snapshot.serverTaskId) {
    try {
      const response = await fetch(`/api/generation/tasks/${encodeURIComponent(snapshot.serverTaskId)}`, { headers: { "Accept": "application/json" } });
      const result = await readJsonResponse(response, "检查生成任务失败");
      if (response.ok && result.ok && handleTaskResult(card, result.task)) {
        if (result.task?.status === "running" || result.task?.status === "queued") {
          schedulePendingGenerationPoll(card, snapshot);
        }
        return;
      }
    } catch (_) {
      // Fall back to latest-record reconciliation below.
    }
  }
  const params = new URLSearchParams();
  if (snapshot.latestRecordId) params.set("after", String(snapshot.latestRecordId));
  if (snapshot.dialogueId) params.set("dialogue_id", String(snapshot.dialogueId));
  if (snapshot.prompt) params.set("prompt", String(snapshot.prompt));
  if (snapshot.ratio) params.set("ratio", String(snapshot.ratio));
  if (snapshot.actualSize) params.set("actual_size", String(snapshot.actualSize));
  try {
    const response = await fetch(`/api/generation/latest?${params.toString()}`, { headers: { "Accept": "application/json" } });
    const result = await readJsonResponse(response, "检查生成结果失败");
    if (response.ok && result.ok && result.record) {
      clearPendingGeneration();
      card.remove();
      syncDialogue(result.dialogue);
      renderCurrentRecord(result.record);
      return;
    }
  } catch (_) {
    // Keep polling until the local generation window expires.
  }
  if (Date.now() - Number(snapshot.createdAt || 0) < PENDING_GENERATION_MAX_AGE_MS) {
    const progress = card.querySelector("[data-task-progress]");
    if (progress) progress.textContent = "绘世正在生成";
    schedulePendingGenerationPoll(card, snapshot);
    return;
  }
  markTaskUnresolved(card);
  clearPendingGeneration();
}

function schedulePendingGenerationPoll(card, snapshot) {
  if (pendingGenerationPollTimer) return;
  pendingGenerationPollTimer = window.setTimeout(() => {
    pendingGenerationPollTimer = 0;
    void reconcileRestoredPendingGeneration(card, readPendingGeneration() || snapshot);
  }, PENDING_GENERATION_POLL_INTERVAL_MS);
}

function markTaskUnresolved(card) {
  if (!card) return;
  card.classList.remove("is-generating");
  card.classList.add("is-unresolved");
  const progress = card.querySelector("[data-task-progress]");
  if (progress) progress.textContent = "未检测到新的生成结果。这不是后台任务进度，可能已中断；可到资产库查看或重新生成。";
  const actions = document.createElement("div");
  actions.className = "task-actions";
  actions.innerHTML = `
    <a href="/assets">查看资产库</a>
    <button type="button" data-task-retry>重新生成</button>
  `;
  card.appendChild(actions);
  actions.querySelector("[data-task-retry]")?.addEventListener("click", () => {
    card.remove();
    form?.requestSubmit();
  });
}

function hasServerTask(card) {
  return Boolean(card?.dataset.serverTaskId || "");
}

async function dismissFailedTaskWindow(card) {
  const taskId = card?.dataset.serverTaskId || "";
  if (!taskId) return true;
  try {
    const response = await fetch(`/api/generation/tasks/${encodeURIComponent(taskId)}/dismiss`, {
      method: "POST",
      headers: csrfHeaders(),
    });
    const result = await readJsonResponse(response, "关闭失败窗口失败");
    return response.ok && result.ok;
  } catch (_) {
    return false;
  }
}

function formDataFromTaskCard(card) {
  const formData = new FormData();
  formData.set("prompt", card?.dataset.prompt || "");
  formData.set("mode", card?.dataset.mode || "text");
  formData.set("media_type", card?.dataset.mediaType || "");
  formData.set("model", card?.dataset.model || "");
  formData.set("ratio", card?.dataset.ratio || "");
  formData.set("resolution", card?.dataset.resolution || card?.dataset.actualSize || "");
  const actualSize = card?.dataset.actualSize || "";
  if (actualSize.includes("x")) {
    const [width, height] = actualSize.split("x", 2);
    formData.set("width", width || "");
    formData.set("height", height || "");
  }
  formData.set("quality", qualityInput?.value || "auto");
  formData.set("output_format", outputFormatInput?.value || "png");
  formData.set("count", card?.dataset.count || "1");
  formData.set("created_at", card?.dataset.createdAt || String(Date.now()));
  if (card?.dataset.dialogueId) formData.set("dialogue_id", card.dataset.dialogueId);
  parseReferencePathList(card?.dataset.referencePaths || "").forEach((path) => formData.append("reference_paths", path));
  return formData;
}

async function retryFailedTask(card) {
  if (!form) return;
  if (!(await dismissFailedTaskWindow(card))) return;
  const formData = formDataFromTaskCard(card);
  clearPendingGeneration();
  if (card) card.hidden = true;
  storePendingGeneration(pendingSnapshotFromForm(formData));
  const taskCard = renderTaskCard(formData);
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: formData,
      headers: csrfHeaders(),
    });
    const result = await readJsonResponse(response, "生成失败");
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "生成失败");
    }
    if (result.task) {
      if (result.record && !result.task.record) result.task.record = result.record;
      if (Array.isArray(result.records) && result.records.length && result.task.record) result.task.records = result.records;
      syncDialogue(result.dialogue);
      mergeServerTaskIntoPending(result.task);
        syncDialogueFromTask(result.task);
        if (taskCard) taskCard.dataset.serverTaskId = String(result.task.id || "");
        const progress = taskCard?.querySelector("[data-task-progress]");
        if (progress) progress.textContent = "绘世正在生成";
      handleTaskResult(taskCard, result.task);
      if (shouldPollGenerationTask(result.task)) {
        scheduleGenerationTaskPoll(taskCard, result.task.id);
      }
    } else if (result.record) {
      clearPendingGeneration();
      syncDialogue(result.dialogue);
      if (Array.isArray(result.records) && result.records.length) result.record.records = result.records;
      renderCurrentRecord(result.record, taskCard);
    }
  } catch (error) {
    taskCard?.remove();
    if (card) card.hidden = false;
    _handleGenerationError(error, taskCard);
  }
}

function restorePendingGeneration() {
  if (!isWorkspaceComposerPage) return;
  const snapshot = readPendingGeneration();
  if (!snapshot) return;
  const createdAt = Number(snapshot.createdAt || 0);
  if (!createdAt) {
    clearPendingGeneration();
    return;
  }
  const existingCard = findExistingCardForPendingSnapshot(snapshot);
  if (
    existingCard
    && (
      (snapshot.id && existingCard.dataset.clientTaskId === snapshot.id)
      || (snapshot.serverTaskId && existingCard.dataset.serverTaskId === snapshot.serverTaskId)
    )
  ) {
    return;
  }
  renderRestoredPendingGeneration(snapshot);
}

function normalizeTaskSizeValue(value) {
  return String(value || "").trim();
}

function cardMatchesServerTask(card, task, snapshot = null) {
  if (!card || !task) return false;
  const taskSize = normalizeTaskSizeValue(task.actual_size || task.resolution);
  const cardSize = normalizeTaskSizeValue(card.dataset.actualSize || card.dataset.resolution);
  const expectedSize = normalizeTaskSizeValue(snapshot?.actualSize || snapshot?.resolution || taskSize);
  const taskDialogueId = String(task.dialogue_id || "");
  const cardDialogueId = String(card.dataset.dialogueId || snapshot?.dialogueId || "");
  if (taskDialogueId && cardDialogueId && taskDialogueId !== cardDialogueId) return false;
  return String(card.dataset.prompt || "") === String(task.prompt || snapshot?.prompt || "")
    && String(card.dataset.mode || "text") === String(task.mode || snapshot?.mode || "text")
    && String(card.dataset.ratio || "") === String(task.ratio || snapshot?.ratio || "")
    && String(card.dataset.count || "1") === String(task.count || snapshot?.count || "1")
    && (!taskSize || !cardSize || cardSize === taskSize || cardSize === expectedSize);
}

function findExistingCardForPendingSnapshot(snapshot) {
  if (!snapshot) return null;
  const cards = Array.from(document.querySelectorAll(".generation-task-card"));
  return cards.find((card) => (
    (snapshot.id && card.dataset.clientTaskId === snapshot.id)
    || (snapshot.serverTaskId && card.dataset.serverTaskId === String(snapshot.serverTaskId))
  )) || null;
}

function findExistingCardForServerTask(task) {
  const taskId = String(task?.id || "");
  if (taskId) {
    const existing = document.querySelector(`.generation-task-card[data-server-task-id="${taskId}"]`);
    if (existing) return existing;
  }
  const snapshot = readPendingGeneration();
  if (!snapshot || (snapshot.serverTaskId && String(snapshot.serverTaskId) !== taskId)) return null;
  const pendingCard = findExistingCardForPendingSnapshot(snapshot);
  if (!pendingCard || pendingCard.dataset.serverTaskId) return null;
  return cardMatchesServerTask(pendingCard, task, snapshot) ? pendingCard : null;
}

function bindServerTaskToCard(card, task) {
  if (!card || !task?.id) return card;
  const referencePaths = parseReferencePathList(task.reference_paths || card.dataset.referencePaths || []);
  card.dataset.serverTaskId = String(task.id);
  card.dataset.dialogueId = String(task.dialogue_id || "");
  card.dataset.resolution = task.resolution || card.dataset.resolution || "";
  card.dataset.actualSize = task.actual_size || task.resolution || card.dataset.actualSize || "";
  card.dataset.referencePaths = JSON.stringify(referencePaths);
  setTaskReferencePreview(card, referencePaths);
  if (task.cost) card.dataset.cost = `${task.cost} 点`;
  return card;
}

async function restoreServerGenerationTask() {
  if (!isWorkspaceComposerPage) return;
  const existingCard = document.querySelector(".generation-task-card");
  if (existingCard && existingCard.dataset.serverTaskId) return;
  const dialogueId = currentDialogueId();
  if (!dialogueId) return;
  try {
    const params = new URLSearchParams({ dialogue_id: dialogueId });
    const response = await fetch(`/api/generation/tasks/latest?${params.toString()}`, { headers: { "Accept": "application/json" } });
    const result = await readJsonResponse(response, "检查生成任务失败");
    if (!response.ok || !result.ok || !result.task) return;
    const task = result.task;
    if (!belongsToCurrentDialogue(task.dialogue_id)) return;
    const card = bindServerTaskToCard(findExistingCardForServerTask(task), task) || renderTaskCardFromTask(task);
    if (!card) return;
    mergeServerTaskIntoPending(task);
    if (handleTaskResult(card, task) && shouldPollGenerationTask(task)) {
      schedulePendingGenerationPoll(card, readPendingGeneration());
    }
  } catch (_) {}
}

async function restoreServerGenerationTasks() {
  if (!isWorkspaceComposerPage) return;
  const dialogueId = currentDialogueId();
  try {
    const params = new URLSearchParams({ include_unbound: '1' });
    if (dialogueId) params.set('dialogue_id', dialogueId);
    const response = await fetch(`/api/generation/tasks?${params.toString()}`, { headers: { "Accept": "application/json" } });
    const result = await readJsonResponse(response, "检查生成队列失败");
    if (!response.ok || !result.ok || !Array.isArray(result.tasks)) return;
    if (!result.tasks.length) {
      clearPendingGeneration();
      document.querySelectorAll(".generation-task-card:not([data-server-task-id])").forEach((card) => card.remove());
      return;
    }
    result.tasks.forEach((task) => {
      if (!belongsToCurrentDialogue(task.dialogue_id)) return;
      const existing = findExistingCardForServerTask(task);
      const card = bindServerTaskToCard(existing, task) || renderTaskCardFromTask(task);
      if (!card) return;
      handleTaskResult(card, task);
      if (shouldPollGenerationTask(task)) {
        mergeServerTaskIntoPending(task);
        const progress = card.querySelector("[data-task-progress]");
        if (progress && !progress.textContent) progress.textContent = "已加入生成队列，完成后会自动显示。";
        scheduleGenerationTaskPoll(card, task.id);
      }
    });
  } catch (_) {}
}

function markTaskFailed(card, message) {
  if (!card) return;
  setTaskState(card, "failed");
  card.classList.remove("is-generating");
  card.classList.add("is-failed");
  const summary = card.querySelector(".generation-task-summary");
  const skeletonGrid = card.querySelector("[data-task-skeletons]");
  if (skeletonGrid) skeletonGrid.hidden = true;
  card.querySelectorAll("img").forEach((img) => {
    img.removeAttribute("src");
    img.alt = "";
  });
  const progress = card.querySelector("[data-task-progress]");
  if (progress) progress.textContent = "";
  let failurePanel = card.querySelector(".task-failure-panel");
  if (!failurePanel) {
    failurePanel = document.createElement("div");
    failurePanel.className = "task-failure-panel";
    if (summary) {
      summary.replaceWith(failurePanel);
    } else {
      card.prepend(failurePanel);
    }
  }
  failurePanel.innerHTML = `
    <strong>生成失败</strong>
    <p class="task-error-message"></p>
    <dl class="task-failure-detail">
      <dt>提示词</dt><dd data-task-failure-prompt></dd>
      <dt>参数</dt><dd data-task-failure-params></dd>
      <dt>积分</dt><dd data-task-failure-cost></dd>
    </dl>
    <div class="task-actions">
      <button type="button" data-task-retry>重试</button>
      <button type="button" data-task-edit>重新编辑</button>
      <button type="button" data-task-close>关闭</button>
    </div>
  `;
  failurePanel.hidden = false;
  failurePanel.querySelector(".task-error-message").textContent = `${card.dataset.mediaType === 'video' && String(message).includes('内容审核成本') ? '上游返回（渠道费用不向本站用户收取）：' : ''}${simplifyGenerationError(message)}`;
  failurePanel.querySelector("[data-task-failure-prompt]").textContent = card.dataset.prompt || "-";
  failurePanel.querySelector("[data-task-failure-params]").textContent = formatTaskParameterText({ mode: card.dataset.mode, mediaType: card.dataset.mediaType, model: card.dataset.model, ratio: card.dataset.ratio, resolution: card.dataset.resolution, actualSize: card.dataset.actualSize, count: card.dataset.count, referencePaths: parseReferencePathList(card.dataset.referencePaths || "") }).join(" · ");
  failurePanel.querySelector("[data-task-failure-cost]").textContent = card.dataset.billingMessage || "未扣生成费用";
  failurePanel.querySelector("[data-task-retry]")?.addEventListener("click", () => {
    void retryFailedTask(card);
  });
  const editFailedTask = () => {
    clearPendingGeneration();
    applyComposerSeed({
      prompt: card.dataset.prompt || "",
      mode: card.dataset.mode || "text",
      media_type: card.dataset.mediaType || "",
      model: card.dataset.model || "",
      ratio: card.dataset.ratio || "",
      resolution: card.dataset.resolution || card.dataset.actualSize || "",
      actualSize: card.dataset.actualSize || "",
      referencePaths: parseReferencePathList(card.dataset.referencePaths || ""),
    });
    clearPromptError();
    updatePromptCounter();
    autosizePrompt();
    card.remove();
  };
  failurePanel.querySelector("[data-task-edit]")?.addEventListener("click", () => {
    if (!hasServerTask(card)) {
      editFailedTask();
      return;
    }
    void dismissFailedTaskWindow(card).then((dismissed) => {
      if (dismissed) editFailedTask();
    });
  });
  const closeFailedTask = () => {
    clearPendingGeneration();
    card.remove();
  };
  failurePanel.querySelector("[data-task-close]")?.addEventListener("click", () => {
    if (!hasServerTask(card)) {
      closeFailedTask();
      return;
    }
    void dismissFailedTaskWindow(card).then((dismissed) => {
      if (dismissed) closeFailedTask();
    });
  });
}

async function submitGeneration(event) {
  event.preventDefault();
  composerCollapseProtectedUntil = Date.now() + 800; // 提交后 800ms 内禁止 scroll 触发折叠
  if (!form) return;
  const submitButton = form.querySelector("button[type='submit']");
  if (!(composerPrompt?.value || "").trim()) {
    if (composerPrompt) {
      composerPrompt.dataset.defaultPlaceholder ||= composerPrompt.getAttribute("placeholder") || "";
      composerPrompt.setAttribute("placeholder", "请输入提示词");
      composerPrompt.classList.add("is-error");
      composerPrompt.setAttribute("aria-invalid", "true");
    }
    showPromptError();
    return;
  }
  const videoReferenceFiles = selectedMediaType === "video" ? getReferenceFileMaterials("video") : [];
  const selectedSubjectIndex = selectedMediaType === "video" ? selectedSubjectFileIndex() : -1;
  if (selectedMediaType === "video" && videoReferenceFiles.length && selectedSubjectIndex < 0) {
    setStatus("请先通过 @ 选择已上传的主体图片，再开始生成。", true);
    return;
  }
  rebuildReferenceFileInput();
  const isImageGeneration = selectedMediaType === "image";
  const imageModeReferences = referenceMaterials.filter((item) => materialMediaType(item) === "image");
  if (selectedMediaType === "video" && imageModeReferences.length) {
    setStatus("已保留图片模式的参考素材。请先移除这些素材，再通过视频参数中的参考素材上传，避免遗漏输入。", true);
    return;
  }
  const normalizedResolution = isImageGeneration ? normalizedTargetResolution({ writeHidden: true, writeVisible: true }) : "";
  if (isImageGeneration && !normalizedResolution) {
    setDimensionError("请输入宽度和高度");
    return;
  }
  setDimensionError("");
  if (form.classList.contains("is-submitting")) return;
  form.classList.add("is-submitting");
  if (submitButton) submitButton.disabled = true;
  if (modeInput) modeInput.value = isImageGeneration && visibleReferenceMaterials().length ? "reference" : "text";
  const submittedResolution = resolutionInput?.value || "2K";
  const formData = new FormData(form);
  const submittedRatio = ratioInput?.value || "16:9";
  const [submittedWidth, submittedHeight] = normalizedResolution.split("x", 2);
  formData.delete("reference_paths");
  getReferencePathMaterials().forEach((item) => formData.append("reference_paths", item.path));
  formData.set("mode", isImageGeneration ? (modeInput?.value || "text") : "text");
  formData.set("media_type", isImageGeneration ? "" : selectedMediaType);
  let videoRequestIdentity = "";
  if (selectedMediaType === "video") {
    const capabilities = videoModelCapabilities();
    // 兜底取服务端的全局上限（HUISHI_MAX_REFERENCE_IMAGES，默认 16）。
    // 原先这里兜底 99、settings.js 兜底 9，同一模型两个提示两个上限。
    const maxImages = Number(capabilities.max_reference_images || maxReferenceImages);
    const orderedMaterials = orderedVideoReferenceMaterials();
    const selectedSubject = selectedVideoSubjectMaterial();
    let submittedMaterials = orderedMaterials;
    if (maxImages === 1 && selectedSubject) submittedMaterials = [selectedSubject];
    formData.delete("media_references");
    submittedMaterials.forEach((item) => formData.append("media_references", item.file, item.file.name));
    formData.set("subject_index", selectedSubject ? "0" : "-1");
    videoRequestIdentity = JSON.stringify([...formData.entries()].filter(([key]) => key !== "csrf_token").map(([key,value]) => [key,value instanceof File ? [value.name,value.size,value.lastModified] : value]));
    let pending = {};
    try { pending = JSON.parse(sessionStorage.getItem("huishi:workbench-video-request") || "{}"); } catch (_) {}
    const requestKey = pending.identity === videoRequestIdentity ? pending.key : crypto.randomUUID();
    formData.set("request_key", requestKey);
    sessionStorage.setItem("huishi:workbench-video-request", JSON.stringify({identity:videoRequestIdentity,key:requestKey}));
  } else formData.set("request_key", crypto.randomUUID());
  if (!isImageGeneration) {
    formData.set("ratio", "auto");
    formData.set("resolution", "default");
    formData.set("width", "");
    formData.set("height", "");
    formData.set("quality", "auto");
    formData.set("output_format", formData.get("audio_format") || "mp3");
    formData.set("count", "1");
  }
  if (selectedMediaType === "video") {
    formData.set("ratio", formData.get("video_ratio") || "16:9");
    formData.set("resolution", formData.get("video_resolution") || "720p");
    formData.set("output_format", "mp4");
  }
  if (createDialogueInput) formData.set("create_dialogue", String(createDialogueInput.value || "0"));
  storePendingGeneration(pendingSnapshotFromForm(formData));
  const taskCard = renderTaskCard(formData);
  if (composerPrompt) {
    composerPrompt.value = "";
    updateComposerPromptState();
    updatePromptCounter();
    autosizePrompt();
  }
  setStatus("");

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: formData,
      headers: csrfHeaders(),
    });
    const result = await readJsonResponse(response, "生成失败");
    if (!response.ok || !result.ok) {
      if (videoRequestIdentity && response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429) sessionStorage.removeItem("huishi:workbench-video-request");
      throw new Error(result.error || "生成失败");
    }
    if (videoRequestIdentity) sessionStorage.removeItem("huishi:workbench-video-request");
    if (result.task) {
      if (result.record && !result.task.record) result.task.record = result.record;
      if (Array.isArray(result.records) && result.records.length && result.task.record) result.task.records = result.records;
      syncDialogue(result.dialogue);
      mergeServerTaskIntoPending(result.task);
      syncDialogueFromTask(result.task);
      taskCard.dataset.serverTaskId = String(result.task.id || "");
      const progress = taskCard?.querySelector("[data-task-progress]");
      if (progress) progress.textContent = "绘世正在生成";
      handleTaskResult(taskCard, result.task);
      if (shouldPollGenerationTask(result.task)) {
        scheduleGenerationTaskPoll(taskCard, result.task.id);
      }
    } else if (result.record) {
      clearPendingGeneration();
      syncDialogue(result.dialogue);
      if (Array.isArray(result.records) && result.records.length) result.record.records = result.records;
      renderCurrentRecord(result.record, taskCard);
    }
    form.classList.remove("is-empty-card", "empty-composer-card");
    form.classList.add("output-composer");
    setStatus("");
    if (composerPrompt) composerPrompt.value = "";
    updateComposerPromptState();
    // Keep model, media type and dialogue after submission so subsequent tasks
    // stay in this conversation instead of silently reverting to image mode.
    if (ratioInput) ratioInput.value = submittedRatio;
    if (resolutionInput) resolutionInput.value = submittedResolution;
    if (customWidthInput) customWidthInput.value = submittedWidth || "";
    if (customHeightInput) customHeightInput.value = submittedHeight || "";
    if (widthInput) widthInput.value = submittedWidth || "";
    if (heightInput) heightInput.value = submittedHeight || "";
    clearReferenceImages();
    syncModeButtons();
    syncMediaType();
    syncSizeDisplay();
    syncReferenceField();
    refreshEstimate();
    autosizePrompt();
  } catch (error) {
    if (videoRequestIdentity && composerPrompt) composerPrompt.value = String(formData.get("prompt") || "");
    let uncertainVideo = false;
    try { uncertainVideo = Boolean(videoRequestIdentity && JSON.parse(sessionStorage.getItem("huishi:workbench-video-request") || "{}").key); } catch (_) {}
    if (uncertainVideo) {
      const message = "尚未确认提交结果，正在查询。相同参数重试会沿用原请求，不会重复创建任务。";
      const progress = taskCard?.querySelector("[data-task-progress]");
      if (progress) progress.textContent = message;
      setStatus(message);
      const snapshot = readPendingGeneration();
      if (snapshot) schedulePendingGenerationPoll(taskCard, snapshot);
    } else _handleGenerationError(error, taskCard);
  } finally {
    if (submitButton) submitButton.disabled = false;
    form.classList.remove("is-submitting");
  }
}

function _handleGenerationError(error, taskCard) {
  clearPendingGeneration();
  markTaskFailed(taskCard, error.message || "生成失败");
  if (isBalanceShortageMessage(error.message)) {
    showShortage(error.message);
  }
  setStatus(error.message || "生成失败", true);
}

function applyRecordToComposer(button, submitImmediately = false) {
  if (!form || !button) return;
  const actualSize = button.dataset.actualSize || "";
  if (actualSize.includes("x")) {
    const [width, height] = actualSize.split("x", 2);
    if (customWidthInput) customWidthInput.value = width || "";
    if (customHeightInput) customHeightInput.value = height || "";
  }
  applyComposerSeed({
    prompt: button.dataset.prompt || "",
    mode: button.dataset.mode || "text",
    media_type: button.dataset.mediaType || "",
    model: button.dataset.model || "",
    ratio: button.dataset.ratio || "",
    resolution: button.dataset.resolution || "",
    actualSize,
    referencePaths: parseReferencePathList(button.dataset.referencePaths || ""),
  }, submitImmediately);
  syncSizeDisplay();
}

function applyRecordImagesToComposer(button) {
  if (!form || !button) return;
  const actualSize = button.dataset.actualSize || "";
  if (actualSize.includes("x")) {
    const [width, height] = actualSize.split("x", 2);
    if (customWidthInput) customWidthInput.value = width || "";
    if (customHeightInput) customHeightInput.value = height || "";
    if (widthInput) widthInput.value = width || "";
    if (heightInput) heightInput.value = height || "";
  }
  applyComposerSeed({
    prompt: "",
    mode: "reference",
    ratio: button.dataset.ratio || "",
    resolution: button.dataset.resolution || "",
    actualSize,
    referencePaths: parseReferencePathList(button.dataset.editImagePaths || ""),
  }, false);
  if (modeInput) modeInput.value = "reference";
  syncSizeDisplay();
  syncReferenceField();
  refreshEstimate();
}

function bindRecordActionButtons() {
  document.querySelectorAll("[data-refill-record]").forEach((button) => {
    button.onclick = () => applyRecordToComposer(button, false);
  });
  document.querySelectorAll("[data-edit-record-images]").forEach((button) => {
    button.onclick = () => applyRecordImagesToComposer(button);
  });
  document.querySelectorAll("[data-regenerate-record]").forEach((button) => {
    button.onclick = () => applyRecordToComposer(button, true);
  });
}

function bindAssetRegenerateButtons() {
  document.querySelectorAll("[data-regenerate-asset]").forEach((button) => {
    button.addEventListener("click", async () => {
      const id = button.dataset.regenerateAsset;
      if (!id || !(await confirmRegenerate(button.dataset.cost))) return;
      const originalText = button.textContent;
      button.disabled = true;
      button.classList.add("is-busy");
      button.setAttribute("aria-busy", "true");
      setStatus("正在再次生成图片，请稍候。");
      try {
        const response = await fetch(`/assets/${id}/regenerate`, {
          method: "POST",
          headers: csrfHeaders(),
        });
        const result = await readJsonResponse(response, "再次生成失败");
        if (!response.ok || !result.ok) {
          throw new Error(result.error || "再次生成失败");
        }
        const next = button.dataset.returnNext || "";
        const suffix = next ? `?next=${encodeURIComponent(next)}` : "";
        window.location.href = `/assets/${result.record.id}${suffix}`;
      } catch (error) {
        setStatus(error.message || "再次生成失败", true);
      } finally {
        button.disabled = false;
        button.classList.remove("is-busy");
        button.removeAttribute("aria-busy");
        button.textContent = originalText;
      }
    });
  });
}

function openImagePreview(trigger) {
  const src = trigger?.dataset.previewSrc || trigger?.querySelector("img")?.src;
  const alt = trigger?.dataset.previewAlt || trigger?.querySelector("img")?.alt || "";
  if (!src || !imagePreviewModal || !imagePreviewImage) return;
  lastImagePreviewTrigger = trigger;
  imagePreviewImage.src = src;
  imagePreviewImage.alt = alt;
  if (imagePreviewCaption) imagePreviewCaption.textContent = alt;
  if (imagePreviewModal.showModal) {
    imagePreviewModal.showModal();
  } else {
    window.open(src, "_blank", "noopener");
  }
}

function closeImagePreview() {
  if (!imagePreviewModal) return;
  imagePreviewModal.close();
  resetImagePreview();
}

function resetImagePreview() {
  if (imagePreviewImage) imagePreviewImage.src = "";
  if (imagePreviewCaption) imagePreviewCaption.textContent = "";
  lastImagePreviewTrigger?.focus?.();
  lastImagePreviewTrigger = null;
}

function isCompactWorkspaceViewport() {
  return window.matchMedia?.("(max-width: 760px)")?.matches || window.innerWidth <= 760;
}

function syncComposerPlaceholderForState() {
  if (!form || !composerPrompt || composerPrompt.classList.contains("is-error")) return;
  composerPrompt.dataset.defaultPlaceholder ||= composerPrompt.getAttribute("placeholder") || `上传最多${maxReferenceImages}个参考素材，输入文字或参考内容，定义精彩互动。`;
  const compactPlaceholder = "输入提示词，继续生成";
  const defaultPlaceholder = composerPrompt.dataset.defaultPlaceholder;
  const nextPlaceholder = form.classList.contains("output-composer") && form.classList.contains("is-collapsed") && isCompactWorkspaceViewport()
    ? compactPlaceholder
    : defaultPlaceholder;
  composerPrompt.setAttribute("placeholder", nextPlaceholder);
}

function setComposerCollapsed(collapsed) {
  if (!form || !form.classList.contains("output-composer")) return;
  form.classList.toggle("is-collapsed", collapsed);
  syncComposerPlaceholderForState();
}

function shouldKeepComposerExpanded() {
  return Boolean(getEditSeed() || referenceMaterials.length || form?.classList.contains("has-reference"));
}

function bindComposerCollapse() {
  if (!form) return;
  setComposerCollapsed(form.classList.contains("output-composer") && !shouldKeepComposerExpanded());

  form.addEventListener("pointerdown", (event) => {
    if (event.target.closest(".generate-button")) return;
    setComposerCollapsed(false);
  });
  form.addEventListener("focusin", () => setComposerCollapsed(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && form.classList.contains("output-composer")) {
      if (shouldKeepComposerExpanded()) return;
      setComposerCollapsed(true);
      closeParameterPanels();
      form.querySelector('[name="prompt"]')?.blur();
    }
  });
  window.addEventListener("scroll", () => {
    if (!form.classList.contains("output-composer")) return;
    if (shouldKeepComposerExpanded()) {
      setComposerCollapsed(false);
      return;
    }
    if (document.activeElement && form.contains(document.activeElement)) return;
    if (Date.now() < composerCollapseProtectedUntil) return; // 刚提交，保护期内不折叠
    setComposerCollapsed(window.scrollY > 24);
  }, { passive: true });
  window.addEventListener("resize", syncComposerPlaceholderForState, { passive: true });
}

function bindImagePreview() {
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-preview-src]");
    if (!trigger) return;
    openImagePreview(trigger);
  });
  document.querySelector("[data-close-image-preview]")?.addEventListener("click", closeImagePreview);
  imagePreviewModal?.addEventListener("click", (event) => {
    if (event.target === imagePreviewModal) closeImagePreview();
  });
  imagePreviewModal?.addEventListener("cancel", resetImagePreview);
}

function bindDetailReturnLinks(scope = document) {
  const currentPath = `${window.location.pathname}${window.location.search}${window.location.hash}`;
  scope.querySelectorAll("[data-detail-link]").forEach((link) => {
    const url = new URL(link.getAttribute("href"), window.location.origin);
    if (url.searchParams.get("next")) return;
    url.searchParams.set("next", currentPath);
    link.href = `${url.pathname}${url.search}`;
  });
}

function bindConfirmDeleteForms(scope = document) {
  scope.querySelectorAll("form[data-confirm-delete]").forEach((formEl) => {
    if (formEl.dataset.boundConfirmDelete === "1") return;
    formEl.dataset.boundConfirmDelete = "1";
    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = formEl.dataset.confirmDelete || "确认删除？";
      if (!window.confirm(message)) return;
      const submitButton = formEl.querySelector("button[type='submit']");
      if (submitButton) submitButton.disabled = true;
      try {
        const response = await fetch(formEl.action, {
          method: "POST",
          body: new FormData(formEl),
          headers: csrfHeaders(),
        });
        const result = await readJsonResponse(response, "删除失败");
        if (!response.ok || !result.ok) throw new Error(result.error || "删除失败");
        const item = formEl.closest(".creation-item") || formEl.closest("[data-record-id]");
        item?.remove();
        if (item) {
          if (!currentCanvas?.querySelector(".creation-item")) {
            currentCanvas?.classList.remove("creation-stream");
            currentCanvas?.classList.add("empty-creation-stage");
            if (currentCanvas) currentCanvas.innerHTML = "<h1>你好，想创作什么？</h1>";
          }
          setStatus("");
          return;
        }
        const redirectUrl = typeof result.redirect_url === "string" ? result.redirect_url : "";
        if (redirectUrl && redirectUrl.startsWith("/")) {
          window.location.href = redirectUrl;
          return;
        }
        formEl.closest(".detail-panel")?.classList.add("is-record-deleted");
        if (submitButton) submitButton.textContent = "已删除";
        setStatus("图片已删除。");
      } catch (error) {
        setStatus(error.message || "删除失败", true);
        if (submitButton) submitButton.disabled = false;
      }
    });
  });
}

function closeAllDialogueMenus() {
  document.querySelectorAll("[data-dialogue-menu-panel]").forEach((panel) => {
    panel.hidden = true;
  });
  document.querySelectorAll("[data-dialogue-menu-trigger].is-open").forEach((button) => {
    button.classList.remove("is-open");
  });
}

async function deleteDialogue(dialogueId, row) {
  if (!dialogueId) return;
  if (!window.confirm("删除后不可恢复，确认删除这个对话？")) return;
  try {
    const response = await fetch(`/api/dialogues/${encodeURIComponent(dialogueId)}/delete`, {
      method: "POST",
      headers: csrfHeaders(),
    });
    const result = await readJsonResponse(response, "删除对话失败");
    if (!response.ok || !result.ok) throw new Error(result.error || "删除对话失败");
    row?.remove();
    if (!document.querySelector(".dialogue-row")) {
      const list = document.querySelector(".dialogue-list");
      if (list) list.innerHTML = '<span class="sidebar-empty">暂无历史对话</span>';
    }
    if (dialogueInput && String(dialogueInput.value || "") === String(dialogueId)) {
      dialogueInput.value = "";
      if (createDialogueInput) createDialogueInput.value = "1";
      window.location.href = result.redirect_url || "/workspace?new=1";
      return;
    }
    setStatus("对话已删除。");
  } catch (error) {
    setStatus(error.message || "删除对话失败", true);
  }
}

function bindDialogueMenus(scope = document) {
  scope.querySelectorAll("[data-dialogue-row]").forEach((row) => {
    if (row.dataset.boundDialogueMenu === "1") return;
    row.dataset.boundDialogueMenu = "1";
    const trigger = row.querySelector("[data-dialogue-menu-trigger]");
    const panel = row.querySelector("[data-dialogue-menu-panel]");
    const deleteButton = row.querySelector("[data-delete-dialogue]");
    trigger?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      const isOpen = !panel?.hidden;
      closeAllDialogueMenus();
      if (panel && !isOpen) {
        panel.hidden = false;
        trigger.classList.add("is-open");
      }
    });
    deleteButton?.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      closeAllDialogueMenus();
      void deleteDialogue(row.dataset.dialogueId || "", row);
    });
  });
}

function bindFavoriteForms(scope = document) {
  scope.querySelectorAll("form[data-toggle-favorite]").forEach((formEl) => {
    if (formEl.dataset.boundFavorite === "1") return;
    formEl.dataset.boundFavorite = "1";
    formEl.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = formEl.querySelector("button[type='submit']");
      if (button) button.disabled = true;
      try {
        const response = await fetch(formEl.action, {
          method: "POST",
          body: new FormData(formEl),
          headers: csrfHeaders(),
        });
        const result = await readJsonResponse(response, "收藏失败");
        if (!response.ok || !result.ok) throw new Error(result.error || "收藏失败");
        const active = Boolean(result.favorite);
        button?.classList.toggle("is-favorite", active);
        button?.setAttribute("aria-pressed", active ? "true" : "false");
        const label = button?.querySelector("[data-favorite-label]");
        if (label) label.textContent = active ? "已收藏" : "收藏";
        setStatus(active ? "已收藏" : "已取消收藏");
      } catch (error) {
        setStatus(error.message || "收藏失败", true);
      } finally {
        if (button) button.disabled = false;
      }
    });
  });
}

function bindCountStepper() {
  if (!countInput) return;
  countInput.max = String(maxGenerationCount);
  const normalizeCount = () => {
    const min = Number(countInput.min || 1);
    const max = Number(countInput.max || 10);
    const parsed = Number.parseInt(countInput.value, 10);
    countInput.value = String(Math.max(min, Math.min(max, Number.isNaN(parsed) ? min : parsed)));
  };
  document.querySelectorAll("[data-count-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const step = Number(button.dataset.countStep || 0);
      const min = Number(countInput.min || 1);
      const max = Number(countInput.max || 10);
      const current = Number(countInput.value || min);
      countInput.value = String(Math.max(min, Math.min(max, current + step)));
      countInput.dispatchEvent(new Event("change", { bubbles: true }));
    });
  });
  countInput.addEventListener("change", normalizeCount);
  countInput.addEventListener("blur", normalizeCount);
}

function bindReferenceDrop() {
  if (!studioShell) return;
  let dragDepth = 0;
  const addDragging = () => studioShell.classList.add("is-dragging-reference");
  const removeDragging = () => {
    dragDepth = 0;
    studioShell.classList.remove("is-dragging-reference");
  };

  document.addEventListener("dragstart", (event) => {
    const trigger = event.target.closest("[data-reference-path]");
    const path = trigger?.dataset.referencePath;
    if (!path || !event.dataTransfer) return;
    event.dataTransfer.setData("text/huishi-reference-path", path);
    event.dataTransfer.effectAllowed = "copy";
    addDragging();
  });

  document.addEventListener("dragend", removeDragging);

  ["dragenter", "dragover"].forEach((eventName) => {
    studioShell.addEventListener(eventName, (event) => {
      event.preventDefault();
      if (eventName === "dragenter") dragDepth += 1;
      if (event.dataTransfer) event.dataTransfer.dropEffect = "copy";
      addDragging();
    });
  });

  studioShell.addEventListener("dragleave", (event) => {
    event.preventDefault();
    dragDepth = Math.max(0, dragDepth - 1);
    if (!dragDepth) studioShell.classList.remove("is-dragging-reference");
  });

  studioShell.addEventListener("drop", (event) => {
    event.preventDefault();
    removeDragging();
    const path = event.dataTransfer?.getData("text/huishi-reference-path");
    if (path && addReferencePath(path)) {
      setStatus("");
      return;
    }
    if (addSelectedReferenceFiles(event.dataTransfer?.files)) {
      setStatus("");
      return;
    }
      setStatus(selectedMediaType === "video" ? "请拖入图片、视频或音频参考素材。" : "请拖入 PNG、JPG、JPEG 或 WEBP 图片。", true);
  });

  composerPrompt?.addEventListener("paste", (event) => {
    const files = Array.from(event.clipboardData?.files || []);
    if (files.length && addSelectedReferenceFiles(files)) {
      event.preventDefault();
      setStatus("");
    }
  });
}

function bindReferenceStack() {
  function isReferenceStackExpanded() {
    return Boolean(referenceStack?.classList.contains("is-expanded") || referenceStack?.matches(":hover"));
  }

  referenceAddButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    if (selectedMediaType === "video") {
      if (videoMediaReferences?.showPicker) {
        try { videoMediaReferences.showPicker(); } catch (_) { videoMediaReferences.click(); }
      } else {
        videoMediaReferences?.click();
      }
      return;
    }
    referenceImages?.click();
  });
  referencePreview?.addEventListener("click", (event) => {
    if (referenceStack && !isReferenceStackExpanded()) return;
    const tile = event.target.closest(".reference-material-tile");
    if (!tile) return;
    const id = tile.dataset.referenceId;
    if (event.target.closest(".reference-remove")) {
      event.preventDefault();
      event.stopPropagation();
      removeReferenceMaterial(id);
      return;
    }
    const item = referenceMaterials.find((material) => material.id === id);
    if (item) openReferencePreview(item);
  });
  referencePreview?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    if (event.target.closest(".reference-remove")) return;
    const tile = event.target.closest(".reference-material-tile");
    if (!tile) return;
    event.preventDefault();
    if (!isReferenceStackExpanded()) {
      referenceStack?.classList.add("is-expanded");
      return;
    }
    const item = referenceMaterials.find((material) => material.id === tile.dataset.referenceId);
    if (item) openReferencePreview(item);
  });
  referencePreview?.addEventListener("dragstart", (event) => {
    const tile = event.target.closest("[data-reference-path]");
    const path = tile?.dataset.referencePath;
    if (!path || !event.dataTransfer) return;
    event.dataTransfer.setData("text/huishi-reference-path", path);
    event.dataTransfer.effectAllowed = "copy";
  });
  referenceStack?.addEventListener("click", (event) => {
    if (!referenceMaterials.length) return;
    if (event.target.closest(".reference-material-tile")) {
      if (!isReferenceStackExpanded()) {
        event.preventDefault();
        referenceStack.classList.add("is-expanded");
      }
      return;
    }
    if (event.target.closest("[data-reference-add]")) return;
    referenceStack.classList.toggle("is-expanded");
    if (referenceStack.classList.contains("is-expanded")) {
      event.preventDefault();
    }
  });
  currentCanvas?.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-reference-preview-path]");
    if (!trigger) return;
    const path = trigger.dataset.referencePreviewPath || "";
    if (!path) return;
    event.preventDefault();
    openReferencePreview({ src: path, name: "参考图" });
  });
  document.querySelector("[data-close-reference-preview]")?.addEventListener("click", closeReferencePreview);
  referencePreviewModal?.addEventListener("click", (event) => {
    if (event.target === referencePreviewModal) closeReferencePreview();
  });
  referencePreviewModal?.addEventListener("cancel", () => {
    if (referencePreviewImage) referencePreviewImage.src = "";
    if (referencePreviewCaption) referencePreviewCaption.textContent = "";
  });
}

function bindReferencePreviewDelegates(scope) {
  scope?.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-reference-preview-path]");
    if (!trigger) return;
    const path = trigger.dataset.referencePreviewPath || "";
    if (!path) return;
    event.preventDefault();
    openReferencePreview({ src: path, name: "参考图" });
  });
}

function updatePromptCounter() {
  if (!composerPrompt || !promptCounter) return;
  const max = composerPrompt.getAttribute("maxlength") || "1000";
  promptCounter.textContent = `${composerPrompt.value.length} / ${max}`;
}

function autosizePrompt() {
  const promptInput = form?.querySelector('[name="prompt"]');
  if (!promptInput) return;
  updatePromptCounter();
  if (form?.classList.contains("is-prompt-expanded")) {
    promptInput.style.height = "240px";
    promptInput.style.overflowY = "auto";
    return;
  }
  promptInput.style.height = "auto";
  const maxHeight = form.classList.contains("output-composer") ? 120 : 140;
  const nextHeight = Math.min(Math.max(promptInput.scrollHeight, 100), maxHeight);
  promptInput.style.height = `${nextHeight}px`;
  promptInput.style.overflowY = promptInput.scrollHeight > maxHeight ? "auto" : "hidden";
}

function closeFilterMenus(except = null) {
  document.querySelectorAll(".filter-menu[open]").forEach((menu) => {
    if (menu !== except) menu.removeAttribute("open");
  });
}

function bindWorkspaceFilterbar() {
  const stream = document.querySelector(".creation-stream");
  const items = Array.from(stream?.querySelectorAll(".creation-item") || []);
  if (!stream || !items.length) return;

  document.querySelectorAll(".filter-menu").forEach((menu) => {
    menu.addEventListener("toggle", () => {
      if (menu.open) closeFilterMenus(menu);
    });
  });

  document.querySelector("[data-workspace-search]")?.addEventListener("input", (event) => {
    const keyword = event.target.value.trim().toLowerCase();
    items.forEach((item) => {
      item.hidden = keyword && !item.textContent.toLowerCase().includes(keyword);
    });
  });

  document.querySelectorAll("[data-workspace-sort]").forEach((button) => {
    button.addEventListener("click", () => {
      const children = Array.from(stream.children);
      const ordered = [...items].sort((a, b) => {
        const left = creationSortValue(a);
        const right = creationSortValue(b);
        return button.dataset.workspaceSort === "oldest" ? right - left : left - right;
      });
      let nextRecordIndex = 0;
      children.forEach((child) => {
        stream.appendChild(child.classList.contains("creation-item") ? ordered[nextRecordIndex++] : child);
      });
      closeFilterMenus();
    });
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".filter-menu")) closeFilterMenus();
  });
}

function focusLatestCreation() {
  if (location.hash || !currentCanvas?.classList.contains("creation-stream")) return;
  const latest = currentCanvas.querySelector(".creation-item.is-featured");
  if (!latest) return;
  const scheduleFocus = () => requestAnimationFrame(() => scrollCreationIntoView(latest));
  requestAnimationFrame(() => {
    scrollCreationIntoView(latest);
    requestAnimationFrame(() => scrollCreationIntoView(latest));
  });
  latest.querySelectorAll("img").forEach((image) => {
    if (image.complete) return;
    image.addEventListener("load", scheduleFocus, { once: true });
  });
}

function scrollCreationIntoView(element, behavior = "auto") {
  if (!element) return;
  if (isCompactWorkspaceViewport()) {
    const rail = document.querySelector(".studio-rail");
    const composer = document.querySelector(".output-composer");
    const railHeight = rail ? rail.getBoundingClientRect().height : 0;
    const composerTop = composer ? composer.getBoundingClientRect().top : window.innerHeight;
    const elementRect = element.getBoundingClientRect();
    const offset = Math.max(84, railHeight + 10);
    const availableHeight = Math.max(0, composerTop - offset - 12);
    const centeredTop = availableHeight > elementRect.height
      ? offset + Math.min(72, Math.max(0, (availableHeight - elementRect.height) / 2))
      : offset;
    const targetTop = Math.max(0, elementRect.top + window.scrollY - centeredTop);
    window.scrollTo({ top: targetTop, behavior });
    return;
  }
  element.scrollIntoView({ behavior, block: "nearest" });
}

function consumeHomePromptDraft() {
  if (!composerPrompt || composerPrompt.value.trim()) return;
  try {
    const draft = sessionStorage.getItem(HOME_PROMPT_DRAFT_KEY)?.trim();
    sessionStorage.removeItem(HOME_PROMPT_DRAFT_KEY);
    if (!draft) return;
    composerPrompt.value = draft;
    composerPrompt.dispatchEvent(new Event("input", { bubbles: true }));
  } catch (error) {
    // The workspace remains usable when session storage is unavailable.
  }
}

if (isWorkspaceComposerPage && form) {
  form.addEventListener("change", refreshEstimate);
  form.addEventListener("submit", submitGeneration);
  composerPrompt?.addEventListener("input", () => {
    clearPromptError();
    updateComposerPromptState();
    autosizePrompt();
  });
  expandPromptButton?.addEventListener("click", () => {
    form.classList.toggle("is-prompt-expanded");
    expandPromptButton.setAttribute("aria-label", form.classList.contains("is-prompt-expanded") ? "收起提示词输入框" : "展开提示词输入框");
    autosizePrompt();
  });
  if (referenceImages) referenceImages.addEventListener("change", renderReferencePreview);
  referenceClearButton?.addEventListener("click", clearReferenceImages);
  bindReferenceDrop();
  bindReferenceStack();
  bindReferencePreviewDelegates(currentCanvas);
  bindReferencePreviewDelegates(taskRegion);
  bindGenerationModePicker();
  bindParameterControls();
  bindVideoWorkbenchControls();
  bindRecordActionButtons();
  applySeedToComposer(getEditSeed());
  consumeHomePromptDraft();
  syncMediaType();
  syncSizeDisplay();
  syncReferenceField();
  restorePendingGeneration();
  void restoreServerGenerationTasks();
  refreshEstimate();
  focusLatestCreation();
  bindComposerCollapse();
  bindCountStepper();
  updateComposerPromptState();
  autosizePrompt();
}

const handleGenerationVisibilityChange = () => {
  if (isDocumentHidden()) return;
  const entries = Array.from(pendingVisibilityPolls.values());
  pendingVisibilityPolls.clear();
  const resumedTaskIds = new Set(entries.map(({ taskId }) => String(taskId || "")).filter(Boolean));
  entries.forEach(({ card, taskId, attempt }) => {
    void pollGenerationTask(card, taskId, attempt);
  });
  const snapshot = readPendingGeneration();
  if (snapshot) {
    const card = findExistingCardForPendingSnapshot(snapshot);
    const snapshotTaskId = String(snapshot.serverTaskId || "");
    if (card && (!snapshotTaskId || !resumedTaskIds.has(snapshotTaskId))) {
      void reconcileRestoredPendingGeneration(card, snapshot);
    }
  }
};

if (window.__huishiWorkspaceVisibilityHandler) {
  document.removeEventListener("visibilitychange", window.__huishiWorkspaceVisibilityHandler);
}
window.__huishiWorkspaceVisibilityHandler = handleGenerationVisibilityChange;
document.addEventListener("visibilitychange", handleGenerationVisibilityChange);

document.querySelectorAll("[data-copy-prompt]").forEach((button) => {
  button.addEventListener("click", async () => {
    const originalText = button.textContent;
    try {
      await navigator.clipboard.writeText(button.dataset.copyPrompt || "");
      button.textContent = "已复制";
    } catch (error) {
      button.textContent = "复制失败";
    }
    window.setTimeout(() => {
      button.textContent = originalText;
    }, 1600);
  });
});

bindAssetRegenerateButtons();
bindWorkspaceFilterbar();
bindConfirmDeleteForms();
bindFavoriteForms();
bindDialogueMenus();

if (optimizePromptButton) optimizePromptButton.addEventListener("click", runPromptOptimization);
document.querySelector("[data-close-shortage]")?.addEventListener("click", () => shortageModal?.close());
bindImagePreview();
bindDetailReturnLinks();
document.addEventListener("click", (event) => {
  if (!event.target?.closest?.("[data-dialogue-menu]")) closeAllDialogueMenus();
});
