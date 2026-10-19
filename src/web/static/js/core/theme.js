/** Shared visual preference; applying it never starts station modules or requests. */
export function readThemePreference() {
  try {
    const saved = localStorage.getItem("meshcore_theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch (_) { /* Retain the preference in the DOM when storage is unavailable. */ }
  return document.documentElement.getAttribute("data-bs-theme") === "light" ? "light" : "dark";
}

export function applyThemePreference(theme, persist = true) {
  const selected = theme === "light" ? "light" : "dark";
  const isDark = selected === "dark";
  const stylesheet = document.getElementById("themeStylesheet");
  const href = isDark ? "/css/bootstrap-slate.min.css" : "/css/bootstrap-zephyr.local.min.css";
  if (stylesheet && !stylesheet.getAttribute("href")?.endsWith(href)) stylesheet.setAttribute("href", href);
  document.body.classList.remove("dark-theme", "light-theme");
  document.body.classList.add(`${selected}-theme`);
  document.documentElement.setAttribute("data-bs-theme", selected);
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", isDark ? "#101b2e" : "#eef3f9");
  if (persist) {
    try { localStorage.setItem("meshcore_theme", selected); }
    catch (_) { /* The visual preference still applies when storage is unavailable. */ }
  }
}

export function readDensityPreference() {
  try {
    const saved = localStorage.getItem("meshcore_ui_density");
    if (saved === "compact" || saved === "normal") return saved;
  } catch (_) { /* Retain the preference in the DOM when storage is unavailable. */ }
  return document.documentElement.classList.contains("density-compact") ? "compact" : "normal";
}

export function applyDensityPreference(density, persist = true) {
  const selected = density === "compact" ? "compact" : "normal";
  const isCompact = selected === "compact";
  document.documentElement.classList.toggle("density-compact", isCompact);
  const btn = document.getElementById("densityToggleBtn");
  if (btn) {
    btn.setAttribute("aria-pressed", String(isCompact));
    btn.classList.toggle("active", isCompact);
  }
  if (persist) {
    try { localStorage.setItem("meshcore_ui_density", selected); }
    catch (_) {}
  }
}
