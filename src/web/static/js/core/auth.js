/** Single-user browser session. Passwords and automation tokens never enter storage. */
import { getAuthHeaders, setSessionCsrfToken } from "./utils.js";
import { FormFeedback } from "./form_feedback.js";
import { applyThemePreference, readThemePreference } from "./theme.js";

export class BrowserAuthentication {
  constructor(startApplication) {
    this.startApplication = startApplication;
    this.nativeFetch = window.fetch.bind(window);
    this.session = null;
    this.started = false;
    this.expired = false;
    this.dialog = document.getElementById("accountDialog");
    this.channel = typeof BroadcastChannel === "function" ? new BroadcastChannel("meshcore-auth") : null;
  }

  async init() {
    applyThemePreference(readThemePreference(), false);
    this._updateThemeButton();
    // Remove secrets saved by the former API-key login without migrating them.
    for (const storageName of ["localStorage", "sessionStorage"]) {
      try {
        for (const key of ["meshcore_bridge_api_key", "bridge_api_key"]) window[storageName].removeItem(key);
      } catch (_) { /* Authentication does not depend on Web Storage. */ }
    }
    this._bindForms();
    this._protectRequests();
    document.getElementById("authLanguageButton").addEventListener("click", () => window.I18n.toggle());
    document.getElementById("authThemeButton").addEventListener("click", () => {
      const next = document.documentElement.getAttribute("data-bs-theme") === "dark" ? "light" : "dark";
      applyThemePreference(next);
      this._updateThemeButton();
    });
    window.addEventListener("meshcore:auth_expired", () => this._expire());
    this.channel?.addEventListener("message", () => this._expire());
    try {
      const response = await this.nativeFetch("/api/auth/session", { credentials: "same-origin", cache: "no-store" });
      if (response.status === 401) { this._showLogin(); return; }
      if (!response.ok) throw new Error("Session unavailable");
      this._acceptSession(await response.json());
    } catch (_) {
      this._showLogin();
      this.loginFeedback.networkError();
    }
  }

  _bindForms() {
    this.loginForm = document.getElementById("loginForm");
    this.accountForm = document.getElementById("accountCredentialsForm");
    this.tokenForm = document.getElementById("automationTokenForm");
    this.loginFeedback = new FormFeedback(this.loginForm, {
      username: this.loginForm.elements.username,
      password: this.loginForm.elements.password,
    });
    this.accountFeedback = new FormFeedback(this.accountForm, {
      current_password: this.accountForm.elements.current_password,
      username: this.accountForm.elements.username,
      password: this.accountForm.elements.password,
      confirmation: this.accountForm.elements.confirmation,
    });
    this.tokenFeedback = new FormFeedback(this.tokenForm, { current_password: this.tokenForm.elements.current_password });
    this.loginForm.addEventListener("submit", (event) => this._login(event));
    document.getElementById("loginPasswordToggle").addEventListener("click", () => {
      this._setPasswordVisible(this.loginForm.elements.password.type === "password");
    });
    this.accountForm.addEventListener("submit", (event) => this._changeCredentials(event));
    this.tokenForm.addEventListener("submit", (event) => this._createToken(event));
    document.querySelectorAll("[data-open-account]").forEach((button) => {
      button.addEventListener("click", () => this._openAccount());
    });
    document.getElementById("accountCloseButton").addEventListener("click", () => {
      if (!this.requestBusy) this.dialog.close();
    });
    document.getElementById("accountLogoutButton").addEventListener("click", () => this._logout());
    document.getElementById("accountCopyTokenButton").addEventListener("click", async () => {
      const output = document.getElementById("accountTokenValue");
      try {
        await navigator.clipboard.writeText(output.value);
        I18n.setText(document.getElementById("accountTokenCopyStatus"), "auth.token_copied");
      } catch (_) {
        output.focus();
        output.select();
        I18n.setText(document.getElementById("accountTokenCopyStatus"), "auth.token_copy_manual");
      }
    });
    this.dialog.addEventListener("cancel", (event) => {
      if (this.session?.must_change_credentials || this.accountFeedback.busy || this.tokenFeedback.busy) event.preventDefault();
    });
    this.dialog.addEventListener("close", () => this._clearAccountSecrets());
  }

  _protectRequests() {
    // Existing modules share fetch: enforce the cookie/CSRF contract centrally.
    window.fetch = async (input, init = {}) => {
      const url = new URL(typeof input === "string" || input instanceof URL ? input : input.url, location.href);
      if (url.origin !== location.origin || !url.pathname.startsWith("/api/")) return this.nativeFetch(input, init);
      const headers = new Headers(init.headers || (input instanceof Request ? input.headers : undefined));
      headers.delete("X-Api-Key");
      const csrf = getAuthHeaders()["X-CSRF-Token"];
      if (csrf) headers.set("X-CSRF-Token", csrf);
      const response = await this.nativeFetch(input, { ...init, headers, credentials: "same-origin" });
      if (!url.pathname.startsWith("/api/auth/")) {
        let credentialsRequired = false;
        if (response.status === 403) {
          const data = await response.clone().json().catch(() => null);
          credentialsRequired = ["credentials_change_required", "csrf_failed"].includes(data?.error || data?.code);
        }
        if (response.status === 401 || credentialsRequired) this._expire();
      }
      return response;
    };
  }

  _showLogin() {
    document.getElementById("authLoading").hidden = true;
    this.loginForm.hidden = false;
    this.loginForm.elements.username.focus();
  }

  _updateThemeButton() {
    const button = document.getElementById("authThemeButton");
    const isDark = document.documentElement.getAttribute("data-bs-theme") === "dark";
    const key = isDark ? "app.dark_theme_title" : "app.light_theme_title";
    button.setAttribute("data-i18n-aria-label", key);
    button.setAttribute("aria-label", I18n.t(key));
    button.querySelector(".bi").className = `bi ${isDark ? "bi-sun" : "bi-moon"}`;
  }

  _setPasswordVisible(visible) {
    const button = document.getElementById("loginPasswordToggle");
    this.loginForm.elements.password.type = visible ? "text" : "password";
    button.setAttribute("aria-pressed", String(visible));
    const key = visible ? "auth.hide_password" : "auth.show_password";
    button.setAttribute("data-i18n-aria-label", key);
    button.setAttribute("aria-label", I18n.t(key));
    button.querySelector(".bi").className = `bi ${visible ? "bi-eye-slash" : "bi-eye"}`;
  }

  _acceptSession(session) {
    if (!session.authenticated) { this._showLogin(); return; }
    this.session = session;
    setSessionCsrfToken(session.csrf_token);
    this.loginForm.reset();
    this._setPasswordVisible(false);
    document.getElementById("authLoading").hidden = true;
    this.loginForm.hidden = true;
    if (session.must_change_credentials) { this._openAccount(); return; }
    this.dialog.open && this.dialog.close();
    document.body.classList.remove("auth-pending");
    document.getElementById("authGate").hidden = true;
    if (!this.started) {
      this.started = true;
      this.startApplication();
    }
  }

  _openAccount() {
    this._clearAccountSecrets();
    this.accountFeedback.clear();
    this.tokenFeedback.clear();
    const forced = Boolean(this.session?.must_change_credentials);
    document.getElementById("accountRequiredNotice").hidden = !forced;
    document.getElementById("accountCloseButton").hidden = forced;
    document.getElementById("accountAutomationSection").hidden = forced;
    this.accountForm.elements.username.value = this.session?.username || "";
    if (!this.dialog.open) this.dialog.showModal();
    this.accountForm.elements.current_password.focus();
  }

  _clearAccountSecrets() {
    this.accountForm.reset();
    this.tokenForm.reset();
    document.getElementById("accountTokenResult").hidden = true;
    document.getElementById("accountTokenValue").value = "";
    document.getElementById("accountTokenCopyStatus").textContent = "";
  }

  async _submit(path, method, payload, feedback) {
    this.requestBusy = true;
    feedback.setBusy(true);
    const controls = [...this.dialog.querySelectorAll("button")].map((button) => [button, button.disabled]);
    for (const [button] of controls) button.disabled = true;
    try {
      const response = await this.nativeFetch(path, {
        method, credentials: "same-origin", cache: "no-store",
        headers: getAuthHeaders(), body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        if (path !== "/api/auth/login" && ["auth_required", "credentials_change_required", "csrf_failed"].includes(data?.error)) {
          this._expire();
          return null;
        }
        const key = response.status === 429 ? "auth.too_many_attempts" : response.status === 401 ? "auth.invalid_credentials" : null;
        if (key) feedback.serverError({ message: I18n.t(key) });
        else feedback.serverError(data);
        return null;
      }
      return data;
    } catch (_) {
      feedback.networkError();
      return null;
    } finally {
      for (const [button, disabled] of controls) button.disabled = disabled;
      feedback.setBusy(false);
      this.requestBusy = false;
    }
  }

  async _login(event) {
    event.preventDefault();
    if (this.requestBusy || !this.loginFeedback.validate()) return;
    const fields = this.loginForm.elements;
    const data = await this._submit("/api/auth/login", "POST", {
      username: fields.username.value, password: fields.password.value, remember: fields.remember.checked,
    }, this.loginFeedback);
    fields.password.value = "";
    this._setPasswordVisible(false);
    if (data) this._acceptSession(data);
  }

  async _changeCredentials(event) {
    event.preventDefault();
    const fields = this.accountForm.elements;
    const errors = {};
    if (fields.password.value !== fields.confirmation.value) errors.confirmation = "auth.password_mismatch";
    const length = Array.from(fields.password.value).length;
    if (length < 15 || length > 128 || new TextEncoder().encode(fields.password.value).length > 1024) errors.password = "auth.password_length";
    if (this.requestBusy || !this.accountFeedback.validate(errors)) return;
    const forced = this.session?.must_change_credentials;
    const data = await this._submit("/api/auth/credentials", "PUT", {
      current_password: fields.current_password.value, username: fields.username.value, password: fields.password.value,
    }, this.accountFeedback);
    if (!data) return;
    this._clearAccountSecrets();
    this.channel?.postMessage("credentials-changed");
    window.dispatchEvent(new CustomEvent("meshcore:credentials_changed"));
    if (forced) this._acceptSession(data);
    else location.reload();
  }

  async _createToken(event) {
    event.preventDefault();
    if (this.requestBusy || !this.tokenFeedback.validate()) return;
    document.getElementById("accountTokenResult").hidden = true;
    document.getElementById("accountTokenValue").value = "";
    const data = await this._submit("/api/auth/api-token", "POST", {
      current_password: this.tokenForm.elements.current_password.value,
    }, this.tokenFeedback);
    this.tokenForm.elements.current_password.value = "";
    if (data?.token) {
      document.getElementById("accountTokenValue").value = data.token;
      document.getElementById("accountTokenResult").hidden = false;
    }
  }

  async _logout() {
    const button = document.getElementById("accountLogoutButton");
    if (this.requestBusy || button.disabled) return;
    button.disabled = true;
    const data = await this._submit("/api/auth/logout", "POST", {}, this.accountFeedback);
    button.disabled = false;
    if (data) {
      this.channel?.postMessage("logout");
      this._expire();
    }
  }

  _expire() {
    if (this.expired) return;
    this.expired = true;
    setSessionCsrfToken("");
    window.dispatchEvent(new CustomEvent("meshcore:auth_expired"));
    window.dispatchEvent(new CustomEvent("meshcore:credentials_changed"));
    document.body.classList.add("auth-pending");
    this._clearAccountSecrets();
    location.reload();
  }
}
