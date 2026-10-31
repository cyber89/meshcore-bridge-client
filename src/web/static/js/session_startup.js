/** Begin the cookie check independently of the station's application modules. */
(() => {
  try {
    document.documentElement.classList.add("density-compact");
    var t = localStorage.getItem("meshcore_theme");
    if (!t && window.matchMedia && window.matchMedia('(prefers-color-scheme: light)').matches) {
      t = "light";
    }
    if (t === "light") {
      document.documentElement.setAttribute("data-bs-theme", "light");
      var m = document.querySelector('meta[name="theme-color"]');
      if (m) m.setAttribute("content", "#eef3f9");
      var l = document.getElementById("themeStylesheet");
      if (l) l.href = "/css/bootstrap-zephyr.local.min.css";
    }
  } catch (_) {}
  // auth.init claims this slot too, so a late script cannot issue a second GET.
  if (Object.hasOwn(window, "meshcoreSessionStartup")) return;
  window.meshcoreSessionStartup = fetch("/api/auth/session", {
    credentials: "same-origin",
    cache: "no-store",
  }).catch(() => null);
})();
