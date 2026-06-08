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

function applyAssetFilters(filter = document.querySelector("[data-asset-filter].is-active")?.dataset.assetFilter || "all") {
  const query = (assetSearch?.value || "").trim().toLowerCase();
  const mode = document.querySelector("[data-filter-mode]")?.value || "";
  const ratio = document.querySelector("[data-filter-ratio]")?.value || "";
  const resolution = document.querySelector("[data-filter-resolution]")?.value || "";
  const time = document.querySelector("[data-filter-time]")?.value || "";
  let visibleCount = 0;
  assetTiles.forEach((tile) => {
    const prompt = (tile.dataset.prompt || "").toLowerCase();
    const matchesSearch = !query || prompt.includes(query);
    const matchesQuick = filter === "all" || (filter === "favorite" && tile.dataset.favorite === "1");
    const matchesMode = !mode || tile.dataset.mode === mode;
    const matchesRatio = !ratio || tile.dataset.ratio === ratio;
    const matchesResolution = !resolution || tile.dataset.resolution === resolution;
    const isVisible = matchesSearch && matchesQuick && matchesMode && matchesRatio && matchesResolution && matchesTime(tile, time);
    tile.classList.toggle("is-hidden", !isVisible);
    if (isVisible) visibleCount += 1;
  });
  if (assetEmptyState) assetEmptyState.hidden = assetTiles.length === 0 || visibleCount > 0;
}

async function postBulk(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", "Accept": "application/json" },
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

document.querySelector("[data-filter-reset]")?.addEventListener("click", () => {
  document.querySelectorAll(".asset-filter-drawer select").forEach((select) => {
    select.value = "";
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
    headers: { "Content-Type": "application/json", "X-Requested-With": "fetch", "Accept": "application/zip" },
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
