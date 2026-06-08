const THEME_KEY = "huishi.workspaceTheme";
const root = document.documentElement;

function applyTheme(theme) {
  const nextTheme = theme === "dark" ? "dark" : "light";
  root.dataset.workspaceTheme = nextTheme;
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.textContent = nextTheme === "dark" ? "白色主题" : "黑色主题";
    button.setAttribute("aria-label", nextTheme === "dark" ? "切换到白色主题" : "切换到黑色主题");
  });
}

function currentTheme() {
  return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
}

applyTheme(currentTheme());

document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
  button.addEventListener("click", () => {
    const nextTheme = currentTheme() === "dark" ? "light" : "dark";
    localStorage.setItem(THEME_KEY, nextTheme);
    applyTheme(nextTheme);
  });
});
