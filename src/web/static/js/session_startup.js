/** Begin the cookie check independently of the station's application modules. */
(() => {
  try {
    if (localStorage.getItem("meshcore_ui_density") === "compact") {
      document.documentElement.classList.add("density-compact");
    }
  } catch (_) {}
  // auth.init claims this slot too, so a late script cannot issue a second GET.
  if (Object.hasOwn(window, "meshcoreSessionStartup")) return;
  window.meshcoreSessionStartup = fetch("/api/auth/session", {
    credentials: "same-origin",
    cache: "no-store",
  }).catch(() => null);
})();
