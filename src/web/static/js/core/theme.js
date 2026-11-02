/** Shared visual preference; applying it never starts station modules or requests. */

let _themeMediaQuery = null;

export function readThemePreference() {
  try {
    const saved = localStorage.getItem("meshcore_theme");
    if (saved === "light" || saved === "dark" || saved === "auto") return saved;
  } catch (_) { /* Retain the preference in the DOM when storage is unavailable. */ }
  if (typeof document !== "undefined" && document.documentElement?.dataset?.themePreference) {
    const domPref = document.documentElement.dataset.themePreference;
    if (domPref === "light" || domPref === "dark" || domPref === "auto") return domPref;
  }
  if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return document.documentElement.getAttribute("data-bs-theme") === "light" ? "light" : "dark";
}

export function resolveEffectiveTheme(pref) {
  if (pref === "light" || pref === "dark") return pref;
  if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "dark";
  }
  if (typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches) {
    return "light";
  }
  return "dark";
}

export function applyThemePreference(theme, persist = true) {
  const pref = (theme === "light" || theme === "dark" || theme === "auto") ? theme : "dark";
  const effective = resolveEffectiveTheme(pref);
  const isDark = effective === "dark";
  const stylesheet = document.getElementById("themeStylesheet");
  const href = isDark ? "/css/bootstrap-slate.min.css" : "/css/bootstrap-zephyr.local.min.css";
  if (stylesheet && !stylesheet.getAttribute("href")?.endsWith(href)) stylesheet.setAttribute("href", href);
  document.body.classList.remove("dark-theme", "light-theme");
  document.body.classList.add(`${effective}-theme`);
  document.documentElement.setAttribute("data-bs-theme", effective);
  document.documentElement.dataset.themePreference = pref;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", isDark ? "#101b2e" : "#eef3f9");
  if (persist) {
    try { localStorage.setItem("meshcore_theme", pref); }
    catch (_) { /* The visual preference still applies when storage is unavailable. */ }
  }
}

export function setupAutoThemeListener(callback = null) {
  if (typeof window === "undefined" || !window.matchMedia) return;
  if (_themeMediaQuery) return;
  _themeMediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
  _themeMediaQuery.addEventListener("change", (e) => {
    const pref = readThemePreference();
    if (pref === "auto") {
      applyThemePreference("auto", false);
      if (typeof callback === "function") {
        callback(e.matches ? "dark" : "light");
      }
    }
  });
}

export function readDensityPreference() {
  try {
    const saved = localStorage.getItem("meshcore_ui_density");
    if (saved === "comfortable" || saved === "compact") return saved;
  } catch (_) {}
  return "compact";
}

export function applyDensityPreference(density = readDensityPreference(), persist = true) {
  const selected = density === "comfortable" ? "comfortable" : "compact";
  document.documentElement.classList.toggle("density-compact", selected === "compact");
  document.documentElement.classList.toggle("density-comfortable", selected === "comfortable");
  if (persist) {
    try { localStorage.setItem("meshcore_ui_density", selected); }
    catch (_) {}
  }
}
