const form = document.querySelector(".composer");
const studioShell = document.querySelector(".studio-shell");
const estimate = document.querySelector("#estimate");
const ratioInput = document.querySelector("#ratio");
const widthInput = document.querySelector("#width");
const heightInput = document.querySelector("#height");
const modeInput = document.querySelector("#mode");
const dialogueInput = document.querySelector("#dialogue-id");
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
const customWidthInput = document.querySelector("#custom-width");
const customHeightInput = document.querySelector("#custom-height");
const countInput = document.querySelector('[name="count"]');
const promptStyle = document.querySelector("#prompt-style");
const optimizePromptButton = document.querySelector("[data-optimize-prompt]");
const promptCounter = document.querySelector("[data-prompt-counter]");
const expandPromptButton = document.querySelector("[data-expand-prompt]");
const taskRegion = document.querySelector("#generation-task-region");
const taskTemplate = document.querySelector("#generation-task-template");
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
let referenceTransfer = null;
let referenceMaterials = [];

let CSRF_TOKEN = "";
let SIZE_MATRIX = null;
let RESOLUTION_LABELS = null;

(function initConfig() {
  const rawMatrix = form?.dataset.sizeMatrix;
  const rawLabels = form?.dataset.resolutionLabels;
  try {
    SIZE_MATRIX = rawMatrix ? JSON.parse(rawMatrix) : {};
    RESOLUTION_LABELS = rawLabels ? JSON.parse(rawLabels) : {};
  } catch (_) {
    SIZE_MATRIX = {};
    RESOLUTION_LABELS = {};
  }
  if (!Object.keys(SIZE_MATRIX).length) {
    SIZE_MATRIX = {
      "1:1": {"1K": "1024x1024", "2K": "2048x2048"},
      "16:9": {"1K": "1536x864", "2K": "2560x1440", "4K": "3840x2160"},
      "9:16": {"1K": "864x1536", "2K": "1440x2560", "4K": "2160x3840"},
      "3:2": {"1K": "1536x1024", "2K": "2160x1440"},
      "2:3": {"1K": "1024x1536", "2K": "1440x2160"},
      "4:3": {"1K": "1365x1024", "2K": "2048x1536"},
      "3:4": {"1K": "1024x1365", "2K": "1536x2048"},
    };
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
  const headers = {
    "X-Requested-With": "fetch",
    "Accept": "application/json",
  };
  if (CSRF_TOKEN) {
    headers["X-CSRF-Token"] = CSRF_TOKEN;
  }
  return headers;
}

function syncSizeDisplay() {
  const ratio = ratioInput?.value || "16:9";
  if (ratio === "自定义") {
    if (ratioLabel) ratioLabel.textContent = "自定义";
    if (widthInput) widthInput.value = customWidthInput?.value || "";
    if (heightInput) heightInput.value = customHeightInput?.value || "";
    document.querySelectorAll('[data-field="ratio"] button').forEach((button) => {
      button.classList.toggle("is-active", button.dataset.value === "自定义");
    });
    return;
  }
  const ratioSizes = SIZE_MATRIX[ratio] || SIZE_MATRIX["16:9"];
  // Use 2K as default resolution for preset ratios
  const size = ratioSizes["2K"] || Object.values(ratioSizes)[0] || "2560x1440";
  const [width, height] = size.split("x");
  if (customWidthInput) customWidthInput.value = width;
  if (customHeightInput) customHeightInput.value = height;
  if (widthInput) widthInput.value = width;
  if (heightInput) heightInput.value = height;
  if (ratioLabel) ratioLabel.textContent = ratio;

  document.querySelectorAll('[data-field="ratio"] button').forEach((button) => {
    button.classList.toggle("is-active", button.dataset.value === ratio);
  });
}

function syncReferenceField() {
  if (!modeInput) return;
  const hasReference = Boolean(referenceMaterials.length);
  modeInput.value = hasReference ? "reference" : "text";
  form?.classList.toggle("has-reference", hasReference);
  if (referenceImages) referenceImages.required = false;
  syncModeButtons();
}

function syncModeButtons() {
  document.querySelectorAll('[data-field="mode"] button').forEach((button) => {
    button.classList.toggle("is-active", button.dataset.value === modeInput?.value);
  });
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
  const qualityInput = form.querySelector('[name="quality"]');
  const outputFormatInput = form.querySelector('[name="output_format"]');
  if (promptInput) promptInput.value = seed.prompt || "";
  if (modeInput) modeInput.value = seed.mode || "text";
  if (ratioInput) ratioInput.value = seed.ratio || "16:9";
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
  syncReferenceField();
  if (!seed.actual_size) syncSizeDisplay();
  refreshEstimate();
  autosizePrompt();
}

function isImageFile(file) {
  return /^image\/(png|jpe?g|webp)$/i.test(file?.type || "");
}

function getReferenceFileMaterials() {
  return referenceMaterials.filter((item) => item.type === "file" && item.file);
}

function getReferencePathMaterials() {
  return referenceMaterials.filter((item) => item.type === "path" && item.path);
}

function rebuildReferenceFileInput() {
  if (referenceImages) {
    referenceTransfer = new DataTransfer();
    getReferenceFileMaterials().forEach((item) => referenceTransfer.items.add(item.file));
    referenceImages.files = referenceTransfer.files;
  }
  if (referencePathsInput) {
    referencePathsInput.value = getReferencePathMaterials().map((item) => item.path).join(",");
  }
}

function materialDisplayName(item) {
  if (item.name) return item.name;
  if (item.file?.name) return item.file.name;
  if (item.path) return item.path.split(/[\\/]/).pop() || item.path;
  return "参考图";
}

function addReferenceFiles(files) {
  const images = Array.from(files || []).filter(isImageFile);
  if (!images.length) return false;
  const available = Math.max(0, 16 - referenceMaterials.length);
  if (!available) return false;
  images.slice(0, available).forEach((file) => {
    referenceMaterials.push({
      id: `file-${Date.now()}-${Math.random().toString(36).slice(2)}`,
      type: "file",
      file,
      name: file.name,
      src: URL.createObjectURL(file),
    });
  });
  renderReferenceMaterials();
  refreshEstimate();
  return true;
}

function addReferencePath(path, name) {
  const referencePath = (path || "").trim();
  if (!referencePath) return false;
  if (referenceMaterials.some((item) => item.type === "path" && item.path === referencePath)) return false;
  if (referenceMaterials.length >= 16) return false;
  referenceMaterials.push({
    id: `path-${Date.now()}-${Math.random().toString(36).slice(2)}`,
    type: "path",
    path: referencePath,
    name: name || materialDisplayName({ path: referencePath }),
    src: referencePath,
  });
  renderReferenceMaterials();
  refreshEstimate();
  return true;
}

function renderReferenceMaterials() {
  if (referencePreview) {
    referencePreview.innerHTML = "";
    referenceMaterials.forEach((item) => {
      const tile = document.createElement("div");
      tile.className = "reference-material-tile";
      tile.dataset.referenceId = item.id;
      tile.draggable = true;
      tile.setAttribute("role", "button");
      tile.tabIndex = 0;
      if (item.path) tile.dataset.referencePath = item.path;
      tile.setAttribute("aria-label", `预览参考图：${materialDisplayName(item)}`);

      const image = document.createElement("img");
      image.src = item.src;
      image.alt = materialDisplayName(item);
      image.loading = "lazy";
      tile.appendChild(image);

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "reference-remove";
      remove.setAttribute("aria-label", `移除参考图：${materialDisplayName(item)}`);
      remove.textContent = "×";
      tile.appendChild(remove);

      referencePreview.appendChild(tile);
    });
  }
  const hasReference = Boolean(referenceMaterials.length);
  referenceStack?.classList.toggle("has-materials", hasReference);
  referenceStack?.classList.toggle("is-empty", !hasReference);
  if (!hasReference) referenceStack?.classList.remove("is-expanded");
  referencePreview?.classList.toggle("is-visible", hasReference);
  referenceField?.classList.toggle("is-visible", hasReference);
  if (referenceClearButton) referenceClearButton.hidden = !hasReference;
  rebuildReferenceFileInput();
  syncReferenceField();
}

function removeReferenceMaterial(id) {
  const item = referenceMaterials.find((material) => material.id === id);
  if (!item) return;
  if (item.type === "file" && item.src) URL.revokeObjectURL(item.src);
  referenceMaterials = referenceMaterials.filter((material) => material.id !== id);
  renderReferenceMaterials();
  refreshEstimate();
}

function openReferencePreview(item) {
  if (!item?.src || !referencePreviewModal || !referencePreviewImage) return;
  referencePreviewImage.src = item.src;
  referencePreviewImage.alt = materialDisplayName(item);
  if (referencePreviewCaption) referencePreviewCaption.textContent = materialDisplayName(item);
  if (referencePreviewModal.showModal) {
    referencePreviewModal.showModal();
  } else {
    window.open(item.src, "_blank", "noopener");
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
  if (referencePathsInput) referencePathsInput.value = "";
  referenceTransfer = null;
  referenceMaterials.forEach((item) => {
    if (item.type === "file" && item.src) URL.revokeObjectURL(item.src);
  });
  referenceMaterials = [];
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

function showPromptError(message = "请先输入提示词") {
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
  composerPrompt.setAttribute("placeholder", composerPrompt.dataset.defaultPlaceholder || "输入你想生成的画面");
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
      body: JSON.stringify({ prompt, style: promptStyle?.value || "通用" }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.error || "优化失败");
    if (composerPrompt) composerPrompt.value = result.optimized_prompt || prompt;
    clearPromptError();
    setPromptOptimizeStatus("");
    autosizePrompt();
    composerPrompt?.focus();
  } catch (error) {
    setStatus(error.message || "优化失败", true);
  } finally {
    if (optimizePromptButton) {
      optimizePromptButton.disabled = false;
      optimizePromptButton.classList.remove("is-optimizing");
      optimizePromptButton.removeAttribute("aria-busy");
    }
  }
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
    return window.confirm(`再次生成消耗 ${cost || "-"}，确认继续？`);
  }
  if (regenerateMessage) regenerateMessage.textContent = `再次生成消耗 ${cost || "-"}，确认继续？`;
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
  return mode === "reference" ? "参考图编辑" : "图片生成";
}

function simplifyGenerationError(message) {
  const raw = message || "";
  if (raw.includes("Upstream request failed") || raw.includes("upstream_error")) {
    return "接口请求失败，请检查接口配置或稍后重试。";
  }
  return raw.replace(/^生成失败：/, "") || "生成失败，请稍后重试。";
}

function closeParameterPanels(exceptId = "") {
  document.querySelectorAll(".parameter-popover").forEach((panel) => {
    if (panel.id !== exceptId) panel.hidden = true;
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
      panel.hidden = !willOpen;
      button.setAttribute("aria-expanded", panel.hidden ? "false" : "true");
      if (willOpen) positionParameterPanel(button, panel);
    });
  });

  document.querySelectorAll("[data-field] button[data-value]").forEach((button) => {
    button.addEventListener("click", () => {
      const group = button.closest("[data-field]");
      const field = group?.dataset.field;
      const input = field ? document.querySelector(`#${field}`) : null;
      if (!input || button.disabled) return;
      input.value = button.dataset.value || input.value;
      group.querySelectorAll("button").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
      if (field === "ratio" && button.dataset.value !== "自定义") {
        // Preset ratio: clear custom inputs then let syncSizeDisplay fill them
        if (customWidthInput) customWidthInput.value = "";
        if (customHeightInput) customHeightInput.value = "";
        syncSizeDisplay();
        syncReferenceField();
        refreshEstimate();
        closeParameterPanels();
        return;
      }
      if (field === "ratio" && button.dataset.value === "自定义") {
        if (customWidthInput) { customWidthInput.value = ""; customWidthInput.focus(); }
        if (customHeightInput) customHeightInput.value = "";
        if (ratioLabel) ratioLabel.textContent = "自定义";
        syncReferenceField();
        syncSizeDisplay();
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
    const w = parseInt(customWidthInput?.value, 10) || 0;
    const h = parseInt(customHeightInput?.value, 10) || 0;
    if (!w && !h) return;
    if (ratioInput) ratioInput.value = "自定义";
    if (widthInput) widthInput.value = w || "";
    if (heightInput) heightInput.value = h || "";
    syncSizeDisplay();
  }

  if (customWidthInput) customWidthInput.addEventListener("input", applyCustomDimensions);
  if (customHeightInput) customHeightInput.addEventListener("input", applyCustomDimensions);
  if (customWidthInput) customWidthInput.addEventListener("blur", refreshEstimate);
  if (customHeightInput) customHeightInput.addEventListener("blur", refreshEstimate);

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".parameter-popover") && !event.target.closest("[data-panel-trigger]")) {
      closeParameterPanels();
    }
  });
}

function positionParameterPanel(button, panel) {
  const composerRect = form?.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  if (!composerRect) return;
  const panelWidth = Math.min(panel.offsetWidth || 360, window.innerWidth - 28, composerRect.width - 24);
  const buttonCenter = buttonRect.left - composerRect.left + buttonRect.width / 2;
  const left = Math.max(12, Math.min(buttonCenter - panelWidth / 2, composerRect.width - panelWidth - 12));
  const panelHeight = panel.offsetHeight || 170;
  const top = Math.max(8, buttonRect.top - composerRect.top - panelHeight - 8);
  panel.style.left = `${left}px`;
  panel.style.right = "auto";
  panel.style.top = `${top}px`;
  panel.style.bottom = "auto";
  panel.style.width = `${panelWidth}px`;
}

async function refreshEstimate() {
  if (!form || !estimate) return;
  syncSizeDisplay();
  syncReferenceField();
  const formData = new FormData(form);
  // Ensure width/height hidden fields are synced before sending
  if (widthInput && customWidthInput) widthInput.value = customWidthInput.value;
  if (heightInput && customHeightInput) heightInput.value = customHeightInput.value;
  const params = new URLSearchParams(formData);
  try {
    const response = await fetch(`/api/estimate?${params.toString()}`);
    const result = await response.json();
    estimate.textContent = result.ok ? `${result.cost} 点` : result.error;
  } catch (error) {
    estimate.textContent = "估价失败";
  }
}

function _buildImageGrid(imagePaths) {
  return imagePaths.map((imagePath, index) => `
        <figure class="creation-image-wrap">
          <button type="button" class="image-preview-trigger" data-preview-src="${imagePath}" data-preview-alt="" draggable="true" data-reference-path="${imagePath}" aria-label="全屏预览图片">
            <img ${index === 0 ? 'id="current-image"' : ""} src="${imagePath}" alt="" loading="lazy" draggable="true" data-reference-path="${imagePath}">
          </button>
        </figure>
  `).join("");
}

function renderCurrentRecord(record) {
  if (!currentCanvas || !record) return;
  const modeLabel = modeText(record.mode);
  const wasEmpty = currentCanvas.classList.contains("empty-creation-stage");
  currentCanvas.classList.remove("empty-creation-stage");
  currentCanvas.classList.add("creation-stream");
  if (wasEmpty) currentCanvas.innerHTML = "";
  const existingFeatured = currentCanvas.querySelector(".creation-item.is-featured");
  existingFeatured?.classList.remove("is-featured");
  existingFeatured?.classList.add("is-previous");
  const imagePaths = Array.isArray(record.images) && record.images.length ? record.images : [record.image_path];
  const imageGrid = _buildImageGrid(imagePaths);
  const article = document.createElement("article");
  article.className = "creation-item is-featured";
  article.dataset.recordId = record.id;
  article.innerHTML = `
      <p class="creation-prompt" tabindex="0"></p>
      <div class="creation-image-grid" data-image-count="${imagePaths.length}">
        ${imageGrid}
      </div>
      <div class="creation-toolbar">
        <div class="creation-action-group">
          <button type="button" data-refill-record data-prompt="" data-mode="${record.mode}" data-ratio="${record.ratio}" data-actual-size="${record.actual_size || ""}">重新编辑</button>
          <button type="button" data-regenerate-record data-prompt="" data-mode="${record.mode}" data-ratio="${record.ratio}" data-actual-size="${record.actual_size || ""}">再次生成</button>
          <a href="/assets/${record.id}?from=workspace" data-detail-link>查看参数</a>
        </div>
        <footer class="creation-meta" id="current-meta" aria-label="生成参数">
          <span>${record.ratio || ratioInput?.value || "16:9"}</span>
          <span>${record.actual_size || ""}</span>
          <span>${record.points_charged} 点</span>
        </footer>
      </div>
  `;
  article.querySelector(".creation-prompt").textContent = record.prompt;
  article.querySelector(".creation-prompt").title = record.prompt;
  article.querySelectorAll("img").forEach((image) => {
    image.alt = record.prompt;
  });
  article.querySelectorAll("[data-preview-alt]").forEach((button) => {
    button.dataset.previewAlt = record.prompt;
  });
  article.querySelectorAll("[data-prompt]").forEach((button) => {
    button.dataset.prompt = record.prompt;
  });
  currentCanvas.appendChild(article);
  if (dialogueInput && record.dialogue_id) dialogueInput.value = record.dialogue_id;
  article.scrollIntoView({ behavior: "smooth", block: "nearest" });
  bindRecordActionButtons();
  bindDetailReturnLinks(article);
  setComposerCollapsed(true);
}

function renderTaskCard(formData) {
  if (!taskRegion || !taskTemplate) return null;
  const targetRegion = currentCanvas?.classList.contains("creation-stream") ? currentCanvas : taskRegion;
  if (currentCanvas?.classList.contains("empty-creation-stage")) {
    currentCanvas.innerHTML = "";
    currentCanvas.classList.remove("empty-creation-stage");
    currentCanvas.classList.add("creation-stream", "is-awaiting-result");
  }
  const clone = taskTemplate.content.cloneNode(true);
  const card = clone.querySelector(".generation-task-card");
  const prompt = formData.get("prompt") || "";
  const mode = formData.get("mode") || "text";
  const ratio = formData.get("ratio") || "";
  const count = formData.get("count") || "1";
  const cost = estimate?.textContent || "";
  card.dataset.prompt = String(prompt);
  card.dataset.mode = String(mode);
  card.dataset.ratio = String(ratio);
  card.dataset.count = String(count);
  card.dataset.cost = cost;
  clone.querySelector("[data-task-prompt]").textContent = String(prompt).slice(0, 80);
  const sizeText = customWidthInput?.value && customHeightInput?.value ? `${customWidthInput.value}x${customHeightInput.value}` : "";
  card.dataset.actualSize = sizeText;
  clone.querySelector("[data-task-params]").textContent = [ratio, sizeText].filter(Boolean).join(" · ");
  const skeletonCount = Math.max(1, Math.min(Number.parseInt(String(count), 10) || 1, 4));
  const skeletonGrid = clone.querySelector("[data-task-skeletons]");
  if (skeletonGrid) {
    skeletonGrid.dataset.imageCount = String(skeletonCount);
    skeletonGrid.innerHTML = Array.from({ length: skeletonCount }, () => "<div></div>").join("");
  }
  const progress = clone.querySelector("[data-task-progress]");
  if (progress) progress.textContent = "";
  targetRegion.appendChild(clone);
  card.scrollIntoView({ behavior: "smooth", block: "start" });
  return card;
}

function markTaskFailed(card, message) {
  if (!card) return;
  card.classList.add("is-failed");
  card.innerHTML = `
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
    </div>
  `;
  card.querySelector(".task-error-message").textContent = simplifyGenerationError(message);
  card.querySelector("[data-task-failure-prompt]").textContent = card.dataset.prompt || "-";
  card.querySelector("[data-task-failure-params]").textContent = `${modeText(card.dataset.mode)} · ${card.dataset.ratio || "-"} · ${card.dataset.actualSize || "-"} · ${card.dataset.count || "1"} 张`;
  card.querySelector("[data-task-failure-cost]").textContent = card.dataset.cost || "-";
  card.querySelector("[data-task-retry]")?.addEventListener("click", () => form?.requestSubmit());
  card.querySelector("[data-task-edit]")?.addEventListener("click", () => {
    form?.querySelector('[name="prompt"]')?.focus();
    card.remove();
  });
}

async function submitGeneration(event) {
  event.preventDefault();
  if (!form) return;
  const submitButton = form.querySelector("button[type='submit']");
  if (!(composerPrompt?.value || "").trim()) {
    showPromptError();
    return;
  }
  rebuildReferenceFileInput();
  const formData = new FormData(form);
  formData.delete("reference_paths");
  getReferencePathMaterials().forEach((item) => formData.append("reference_paths", item.path));
  if (modeInput) modeInput.value = referenceMaterials.length ? "reference" : "text";
  formData.set("mode", modeInput?.value || "text");
  // Sync width/height hidden fields from custom inputs
  if (widthInput) widthInput.value = customWidthInput?.value || "";
  if (heightInput) heightInput.value = customHeightInput?.value || "";
  const taskCard = renderTaskCard(formData);
  submitButton.disabled = true;
  form.classList.add("is-submitting");
  setStatus("");

  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: formData,
      headers: csrfHeaders(),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) {
      throw new Error(result.error || "生成失败");
    }
    taskCard?.remove();
    renderCurrentRecord(result.record);
    form.classList.remove("is-empty-card", "empty-composer-card");
    form.classList.add("output-composer");
    setStatus("");
    form.reset();
    if (modeInput) modeInput.value = "text";
    if (ratioInput) ratioInput.value = "16:9";
    if (customWidthInput) customWidthInput.value = "2560";
    if (customHeightInput) customHeightInput.value = "1440";
    if (widthInput) widthInput.value = "2560";
    if (heightInput) heightInput.value = "1440";
    clearReferenceImages();
    syncModeButtons();
    syncSizeDisplay();
    syncReferenceField();
    refreshEstimate();
    autosizePrompt();
  } catch (error) {
    _handleGenerationError(error, taskCard);
  } finally {
    submitButton.disabled = false;
    form.classList.remove("is-submitting");
  }
}

function _handleGenerationError(error, taskCard) {
  markTaskFailed(taskCard, error.message || "生成失败");
  if ((error.message || "").includes("积分") || (error.message || "").includes("余额")) {
    showShortage(error.message);
  }
  setStatus(error.message || "生成失败", true);
}

function applyRecordToComposer(button, submitImmediately = false) {
  if (!form || !button) return;
  const prompt = button.dataset.prompt || "";
  const promptInput = form.querySelector('[name="prompt"]');
  if (promptInput) promptInput.value = prompt;
  if (modeInput && button.dataset.mode) modeInput.value = button.dataset.mode;
  // Restore ratio from record, syncSizeDisplay will fill width/height from SIZE_MATRIX
  if (ratioInput && button.dataset.ratio) ratioInput.value = button.dataset.ratio;
  if (button.dataset.actualSize && /^\d+x\d+$/.test(button.dataset.actualSize)) {
    const [recordWidth, recordHeight] = button.dataset.actualSize.split("x");
    if (customWidthInput) customWidthInput.value = recordWidth;
    if (customHeightInput) customHeightInput.value = recordHeight;
    if (widthInput) widthInput.value = recordWidth;
    if (heightInput) heightInput.value = recordHeight;
  }
  syncModeButtons();
  syncReferenceField();
  if (!button.dataset.actualSize) syncSizeDisplay();
  refreshEstimate();
  form.scrollIntoView({ behavior: "smooth", block: "center" });
  form.querySelector('[name="prompt"]')?.focus();
  autosizePrompt();
  if (submitImmediately && modeInput?.value !== "reference") form.requestSubmit();
  if (submitImmediately && modeInput?.value === "reference") {
    setStatus("参考图编辑需要重新上传参考图后再生成。", true);
  }
}

function bindRecordActionButtons() {
  document.querySelectorAll("[data-refill-record]").forEach((button) => {
    button.onclick = () => applyRecordToComposer(button, false);
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
        const result = await response.json();
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

function setComposerCollapsed(collapsed) {
  if (!form || !form.classList.contains("output-composer")) return;
  form.classList.toggle("is-collapsed", collapsed);
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
    setComposerCollapsed(window.scrollY > 24);
  }, { passive: true });
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
    url.searchParams.set("next", currentPath);
    link.href = `${url.pathname}${url.search}`;
  });
}

function bindCountStepper() {
  if (!countInput) return;
  const normalizeCount = () => {
    const min = Number(countInput.min || 1);
    const max = Number(countInput.max || 8);
    const parsed = Number.parseInt(countInput.value, 10);
    countInput.value = String(Math.max(min, Math.min(max, Number.isNaN(parsed) ? min : parsed)));
  };
  document.querySelectorAll("[data-count-step]").forEach((button) => {
    button.addEventListener("click", () => {
      const step = Number(button.dataset.countStep || 0);
      const min = Number(countInput.min || 1);
      const max = Number(countInput.max || 8);
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
    if (addReferenceFiles(event.dataTransfer?.files)) {
      setStatus("");
      return;
    }
    setStatus("请拖入 PNG、JPG 或 WEBP 图片。", true);
  });

  composerPrompt?.addEventListener("paste", (event) => {
    const files = Array.from(event.clipboardData?.files || []);
    if (files.length && addReferenceFiles(files)) {
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
  document.querySelector("[data-close-reference-preview]")?.addEventListener("click", closeReferencePreview);
  referencePreviewModal?.addEventListener("click", (event) => {
    if (event.target === referencePreviewModal) closeReferencePreview();
  });
  referencePreviewModal?.addEventListener("cancel", () => {
    if (referencePreviewImage) referencePreviewImage.src = "";
    if (referencePreviewCaption) referencePreviewCaption.textContent = "";
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
      const ordered = [...items].sort((a, b) => {
        const left = Number(a.dataset.createdIndex || 0);
        const right = Number(b.dataset.createdIndex || 0);
        return button.dataset.workspaceSort === "oldest" ? right - left : left - right;
      });
      ordered.forEach((item) => stream.appendChild(item));
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
  requestAnimationFrame(() => {
    latest.scrollIntoView({ block: "start" });
  });
}

if (form) {
  form.addEventListener("change", refreshEstimate);
  form.addEventListener("submit", submitGeneration);
  composerPrompt?.addEventListener("input", () => {
    clearPromptError();
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
  bindParameterControls();
  bindRecordActionButtons();
  applySeedToComposer(getEditSeed());
  syncSizeDisplay();
  syncReferenceField();
  refreshEstimate();
  focusLatestCreation();
  bindComposerCollapse();
  bindCountStepper();
  autosizePrompt();
}

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

if (optimizePromptButton) optimizePromptButton.addEventListener("click", runPromptOptimization);
document.querySelector("[data-close-shortage]")?.addEventListener("click", () => shortageModal?.close());
bindImagePreview();
bindDetailReturnLinks();
