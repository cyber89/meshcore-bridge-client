/**
 * ApiClient - Cliente HTTP tipado y estructurado para la API REST de MeshCore Bridge.
 * Encapsula la gestión de CSRF, credenciales same-origin, cancelación vía AbortSignal
 * y normalización de errores RFC 7807 (Problem Details).
 */

import { getAuthHeaders } from "./utils.js";

export class ProblemDetailsError extends Error {
  /**
   * @param {number} status
   * @param {string} title
   * @param {string} detail
   * @param {string} [errorCode]
   * @param {Record<string, any>} [extra]
   */
  constructor(status, title, detail, errorCode = "unknown_error", extra = {}) {
    super(detail || title || `HTTP error ${status}`);
    this.name = "ProblemDetailsError";
    this.status = status;
    this.title = title;
    this.detail = detail;
    this.errorCode = errorCode;
    this.extra = extra;
  }
}

export class ApiClient {
  /**
   * @param {object} [options]
   * @param {string} [options.baseUrl]
   */
  constructor(options = {}) {
    this.baseUrl = options.baseUrl || "";
  }

  /**
   * Ejecuta una petición HTTP con manejo automático de headers, CSRF y errores RFC 7807.
   * @param {string} path Ruta de endpoint (ej: '/api/channels').
   * @param {object} [init] Opciones de Fetch.
   * @returns {Promise<any>}
   */
  async request(path, init = {}) {
    const url = `${this.baseUrl}${path}`;
    const headers = getAuthHeaders(init.headers || {});

    let body = init.body;
    if (body && typeof body === "object" && !(body instanceof FormData) && !(body instanceof Blob)) {
      body = JSON.stringify(body);
    }

    const response = await fetch(url, {
      ...init,
      headers,
      body,
      credentials: "same-origin",
    });

    if (response.status === 204) {
      return {};
    }

    let data;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json") || contentType.includes("application/problem+json")) {
      try {
        data = await response.json();
      } catch (_) {
        data = null;
      }
    } else {
      data = await response.text();
    }

    if (!response.ok) {
      const errObj = (typeof data === "object" && data !== null) ? data : {};
      const status = response.status;
      const title = errObj.title || response.statusText || "Error";
      const detail = errObj.detail || errObj.message || (typeof data === "string" ? data : "Request failed");
      const errorCode = errObj.error || errObj.error_code || "http_error";
      throw new ProblemDetailsError(status, title, detail, errorCode, errObj);
    }

    return data;
  }

  // --- Canales (Channels) ---

  async getChannels() {
    return this.request("/api/channels", { method: "GET" });
  }

  async updateChannel(channelData) {
    return this.request("/api/channels", {
      method: "POST",
      body: channelData,
    });
  }

  async deleteChannel(index) {
    return this.request(`/api/channels/${index}`, {
      method: "DELETE",
    });
  }

  async exportChannels(index = null) {
    const path = index != null
      ? `/api/channels/export?index=${encodeURIComponent(index)}`
      : "/api/channels/export";
    return this.request(path, { method: "GET" });
  }

  async importChannels(payload) {
    return this.request("/api/channels/import", {
      method: "POST",
      body: typeof payload === "string" ? { payload } : payload,
    });
  }

  // --- Contactos (Contacts) ---

  async getContacts() {
    return this.request("/api/contacts", { method: "GET" });
  }

  async createOrUpdateContact(contactData) {
    return this.request("/api/contacts", {
      method: "POST",
      body: contactData,
    });
  }

  async deleteContact(pubkey) {
    return this.request(`/api/contacts/${encodeURIComponent(pubkey)}`, {
      method: "DELETE",
    });
  }

  async syncContacts() {
    return this.request("/api/contacts/sync", { method: "POST" });
  }

  async shareContact(pubkey) {
    return this.request("/api/contacts/share", {
      method: "POST",
      body: { public_key: pubkey },
    });
  }

  async exportContact(pubkey) {
    return this.request("/api/contacts/export", {
      method: "POST",
      body: { public_key: pubkey },
    });
  }

  async importContacts(payload) {
    return this.request("/api/contacts/import", {
      method: "POST",
      body: typeof payload === "string" ? { payload } : payload,
    });
  }

  // --- Mensajería y Chat (TX / History) ---

  async sendTx(txData, signal = null) {
    return this.request("/api/tx", {
      method: "POST",
      body: txData,
      signal,
    });
  }

  async getHistory({ channel = null, target = null, limit = 50, before = null, signal = null } = {}) {
    const params = new URLSearchParams();
    if (channel !== null) params.set("channel", String(channel));
    if (target) params.set("target", String(target));
    if (limit) params.set("limit", String(limit));
    if (before) params.set("before", String(before));
    const qs = params.toString();
    return this.request(`/api/history${qs ? `?${qs}` : ""}`, {
      method: "GET",
      signal,
    });
  }

  async getConversations(signal = null) {
    return this.request("/api/history/conversations", {
      method: "GET",
      signal,
    });
  }

  // --- Configuración y Estado de Estación ---

  async getConfig() {
    return this.request("/api/config", { method: "GET" });
  }

  async saveConfig(patch) {
    return this.request("/api/config", {
      method: "POST",
      body: patch,
    });
  }

  async getStatus() {
    return this.request("/api/status", { method: "GET" });
  }

  async executeAdminCommand(commandData) {
    return this.request("/api/admin/command", {
      method: "POST",
      body: commandData,
    });
  }

  // --- Servicios Integrados ---

  async getServicesStatus() {
    return this.request("/api/services", { method: "GET" });
  }

  async saveServicesConfig(patch) {
    return this.request("/api/services", {
      method: "POST",
      body: patch,
    });
  }
}

export const apiClient = new ApiClient();
