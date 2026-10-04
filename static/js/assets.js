const assetSearch = document.querySelector("#asset-search");
const assetTiles = Array.from(document.querySelectorAll(".asset-tile"));
const filterButtons = document.querySelectorAll("[data-asset-filter]");
const filterDrawer = document.querySelector(".asset-filter-drawer");
const filterOpenButton = document.querySelector("[data-filter-open]");
const batchToggleButton = document.querySelector("[data-batch-toggle]");
const batchClearButton = document.querySelector("[data-batch-clear]");
const batchBar = document.querySelector(".asset-batchbar");
const selectedCount = document.querySelector("[data-selected-count]");
const assetEmptyState = document.querySelector("[data-asset-empty]");
const bulkButtons = document.querySelectorAll("[data-bulk-favorite], [data-bulk-unfavorite], [data-bulk-download], [data-bulk-delete]");
let CSRF_TOKEN = "";

document.querySelectorAll("[data-asset-media] img, [data-asset-media] video, [data-asset-media] audio").forEach((mediaElement) => {
  const media = mediaElement.closest("[data-asset-media]");
  const status = media?.querySelector("[data-asset-media-status]");
  const setState = (state) => {
    media?.setAttribute("data-state", state);
    if (status) status.textContent = state === "error" ? "媒体加载失败" : "";
  };
  mediaElement.addEventListener("loadeddata", () => setState("ready"));
  mediaElement.addEventListener("loadedmetadata", () => setState("ready"));
  mediaElement.addEventListener("canplay", () => setState("ready"));
  mediaElement.addEventListener("load", () => setState("ready"));
  mediaElement.addEventListener("error", () => setState("error"));
  if (mediaElement.tagName === "IMG" && mediaElement.complete) setState(mediaElement.naturalWidth > 0 ? "ready" : "error");
  if (mediaElement.tagName !== "IMG" && mediaElement.readyState >= 1) setState('ready');
});

fetch("/api/csrf-token")
  .then((response) => response.json())
  .then((payload) => {
    CSRF_TOKEN = payload.csrf_token || "";
  })
  .catch(() => {});


function csrfHeaders(accept) {
  const token = CSRF_TOKEN || document.querySelector('[name="csrf_token"]')?.value || "";
  const headers = {
    "Content-Type": "application/json",
    "X-Requested-With": "fetch",
    Accept: accept,
  };
  if (token) {
    headers["X-CSRF-Token"] = token;
  }
  return headers;
}

(function initLazyLoad() {
  if (!("IntersectionObserver" in window)) return;
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          const tile = entry.target;
          const img = tile.querySelector("img");
          if (img && img.dataset.src) {
            img.src = img.dataset.src;
            img.removeAttribute("data-src");
          }
          observer.unobserve(tile);
        }
      });
    },
    { rootMargin: "300px" },
  );
  document.querySelectorAll(".asset-tile").forEach((tile) => {
    const img = tile.querySelector("img");
    if (img && img.src && !img.hasAttribute("loading")) {
      img.dataset.src = img.src;
      img.removeAttribute("src");
      observer.observe(tile);
    }
  });
})();

function selectedIds() {
  return Array.from(document.querySelectorAll(".asset-select:checked")).map((item) => item.value);
}

function setBatchMode(enabled) {
  document.body.classList.toggle("asset-batch-mode", enabled);
  batchToggleButton?.setAttribute("aria-pressed", enabled ? "true" : "false");
  if (batchToggleButton) batchToggleButton.textContent = enabled ? "完成" : "批量操作";
  if (!enabled) {
    document.querySelectorAll(".asset-select:checked").forEach((item) => {
      item.checked = false;
    });
  }
  updateBatchBar();
}

function updateBatchBar() {
  const count = selectedIds().length;
  if (selectedCount) selectedCount.textContent = `已选择 ${count} 张`;
  if (batchBar) batchBar.hidden = !document.body.classList.contains("asset-batch-mode");
  bulkButtons.forEach((button) => {
    button.disabled = count === 0;
  });
}

function matchesTime(tile, value) {
  if (!value) return true;
  const created = new Date(tile.dataset.createdAt || "");
  if (Number.isNaN(created.getTime())) return true;
  const days = value === "today" ? 1 : Number(value);
  const diff = Date.now() - created.getTime();
  return diff <= days * 24 * 60 * 60 * 1000;
}

function matchesDateRange(tile, fromValue, toValue) {
  if (!fromValue && !toValue) return true;
  const created = new Date(tile.dataset.createdAt || "");
  if (Number.isNaN(created.getTime())) return true;
  const from = fromValue ? new Date(`${fromValue}T00:00:00`) : null;
  const to = toValue ? new Date(`${toValue}T23:59:59.999`) : null;
  return (!from || created >= from) && (!to || created <= to);
}

function applyAssetFilters(filter = document.querySelector("[data-asset-filter].is-active")?.dataset.assetFilter || "all") {
  const query = (assetSearch?.value || "").trim().toLowerCase();
  const mode = document.querySelector("[data-filter-mode]")?.value || "";
  const ratio = document.querySelector("[data-filter-ratio]")?.value || "";
  const time = document.querySelector("[data-filter-time]")?.value || "";
  const dateFrom = document.querySelector("[data-filter-date-from]")?.value || "";
  const dateTo = document.querySelector("[data-filter-date-to]")?.value || "";
  let visibleCount = 0;
  assetTiles.forEach((tile) => {
    const prompt = (tile.dataset.prompt || "").toLowerCase();
    const matchesSearch = !query || prompt.includes(query);
    const source = tile.dataset.assetSource || "image";
    const media = tile.dataset.mediaType || source;
    const matchesQuick = filter === "all" || (filter === "favorite" && tile.dataset.favorite === "1") || (filter === "image" && media === "image") || (filter === "video" && media === "video") || (filter === "audio" && ["audio", "speech", "music"].includes(media)) || (filter === "canvas" && source === "canvas");
    const matchesMode = !mode || tile.dataset.mode === mode;
    const matchesRatio = !ratio || tile.dataset.ratio === ratio;
    const isVisible = matchesSearch && matchesQuick && matchesMode && matchesRatio && matchesTime(tile, time) && matchesDateRange(tile, dateFrom, dateTo);
    tile.classList.toggle("is-hidden", !isVisible);
    if (isVisible) visibleCount += 1;
  });
  if (assetEmptyState) assetEmptyState.hidden = assetTiles.length === 0 || visibleCount > 0;
}

async function postBulk(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: csrfHeaders("application/json"),
    body: JSON.stringify(payload),
  });
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.error || "批量操作失败");
  return result;
}

filterButtons.forEach((button) => {
  button.addEventListener("click", () => {
    filterButtons.forEach((item) => item.classList.remove("is-active"));
    button.classList.add("is-active");
    applyAssetFilters(button.dataset.assetFilter);
  });
});

assetSearch?.addEventListener("input", () => applyAssetFilters());

filterOpenButton?.addEventListener("click", () => {
  if (!filterDrawer) return;
  filterDrawer.hidden = !filterDrawer.hidden;
  filterOpenButton.setAttribute("aria-expanded", filterDrawer.hidden ? "false" : "true");
});

document.querySelector("[data-filter-apply]")?.addEventListener("click", () => {
  applyAssetFilters();
  if (filterDrawer) filterDrawer.hidden = true;
  filterOpenButton?.setAttribute("aria-expanded", "false");
});

// 顶栏时间筛选 select 实时生效
document.querySelector("[data-filter-time]")?.addEventListener("change", () => {
  applyAssetFilters();
});

document.querySelector("[data-filter-reset]")?.addEventListener("click", () => {
  document.querySelectorAll(".asset-filter-drawer select, .asset-filter-drawer input").forEach((control) => {
    control.value = "";
  });
  applyAssetFilters();
});

batchToggleButton?.addEventListener("click", () => setBatchMode(!document.body.classList.contains("asset-batch-mode")));
batchClearButton?.addEventListener("click", () => setBatchMode(false));

document.querySelectorAll(".asset-select").forEach((input) => {
  input.addEventListener("change", updateBatchBar);
});

document.querySelector("[data-bulk-favorite]")?.addEventListener("click", () => {
  postBulk("/assets/bulk/favorite", { ids: selectedIds(), favorite: true }).then(() => location.reload());
});

document.querySelector("[data-bulk-unfavorite]")?.addEventListener("click", () => {
  postBulk("/assets/bulk/favorite", { ids: selectedIds(), favorite: false }).then(() => location.reload());
});

document.querySelector("[data-bulk-delete]")?.addEventListener("click", () => {
  const ids = selectedIds();
  if (!ids.length || !window.confirm(`确认删除选中的 ${ids.length} 张图片？删除后不可恢复。`)) return;
  postBulk("/assets/bulk/delete", { ids }).then(() => location.reload());
});

document.querySelector("[data-bulk-download]")?.addEventListener("click", async () => {
  const ids = selectedIds();
  if (!ids.length) return;
  const response = await fetch("/assets/bulk/download", {
    method: "POST",
    headers: csrfHeaders("application/zip"),
    body: JSON.stringify({ ids }),
  });
  if (!response.ok) {
    window.alert("批量下载失败");
    return;
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `huishi-assets-${new Date().toISOString().slice(0, 10)}.zip`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
});

applyAssetFilters();
updateBatchBar();
