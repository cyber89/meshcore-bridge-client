/** Begin the cookie check independently of the station's application modules. */
(() => {
  // auth.init claims this slot too, so a late script cannot issue a second GET.
  if (Object.hasOwn(window, "meshcoreSessionStartup")) return;
  window.meshcoreSessionStartup = fetch("/api/auth/session", {
    credentials: "same-origin",
    cache: "no-store",
  }).catch(() => null);
})();
