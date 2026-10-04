const THEME_KEY = "huishi.theme";
const LEGACY_THEME_KEY = "huishi.workspaceTheme";
const THEME_VALUES = new Set(["light", "dark"]);
const root = document.documentElement;
const systemTheme = matchMedia("(prefers-color-scheme: dark)");

function storedPreference() {
  try {
    const saved = localStorage.getItem(THEME_KEY);
    if (THEME_VALUES.has(saved)) return saved;
    if (saved === "system") return systemTheme.matches ? "dark" : "light";
    const legacy = localStorage.getItem(LEGACY_THEME_KEY);
    if (legacy === "light" || legacy === "dark") return legacy;
  } catch (error) {
    return "light";
  }
  return "light";
}

function resolveTheme(preference) {
  // Dark mode is retired from the product surface. The sun control remains
  // in the rail for layout continuity, while all pages stay light.
  return "light";
}

function updateThemeControls(_preference, resolved) {
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    const nextLabel = "浅色主题";
    button.setAttribute("aria-label", `切换到${nextLabel}`);
    button.setAttribute("title", `切换到${nextLabel}`);
  });
}

function applyTheme(preference) {
  const nextPreference = "light";
  const resolved = resolveTheme(nextPreference);
  root.dataset.themePreference = nextPreference;
  root.dataset.theme = resolved;
  root.dataset.workspaceTheme = resolved;
  root.style.colorScheme = resolved;
  updateThemeControls(nextPreference, resolved);
  window.dispatchEvent(new CustomEvent("huishi-theme-change", {
    detail: { preference: nextPreference, resolvedTheme: resolved },
  }));
}

function savePreference(preference) {
  try {
    localStorage.setItem(THEME_KEY, preference);
    localStorage.removeItem(LEGACY_THEME_KEY);
  } catch (error) {
    // The selected theme still applies for this page when storage is unavailable.
  }
  applyTheme(preference);
}

applyTheme(storedPreference());

document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    savePreference(resolveTheme(storedPreference()) === "dark" ? "light" : "dark");
  });
});
