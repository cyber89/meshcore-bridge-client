/**
 * MeshCore Web Client - Orquestador Principal (Composition Root)
 * Arquitectura Modular ES6 Nativa para SBCs e interfaces tácticas LoRa.
 */

import { eventBus, EVENTS } from "./core/eventbus.js";
import { MeshCoreStorage } from "./core/storage.js";
import { MeshCoreWebSocketClient } from "./core/websocket.js";
import { debounce } from "./core/utils.js";

/**
 * Función de sanitización XSS estricta para escape en el DOM.
 * @param {string} str Cadena a sanitizar
 * @returns {string} Cadena sanitizada
 */
export function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}


import { SnifferModule } from "./modules/sniffer.js";
import { RepeaterModule } from "./modules/repeater.js";
import { MapModule } from "./modules/map.js";
import { SettingsModule } from "./modules/settings.js";
import { NodesModule } from "./modules/nodes.js";
import { ChatModule } from "./modules/chat.js";

class MeshCoreApp {
  constructor() {
    this.eventBus = eventBus;
    this.storage = new MeshCoreStorage();
    this.wsClient = new MeshCoreWebSocketClient(this.eventBus, "/ws");

    this.activeTabId = "tab-chat";
    this.knownNodes = new Map();
    this.localNodePubkey = "";
    this.dom = {};

    // Contexto compartido desacoplado
    this.context = {
      eventBus: this.eventBus,
      storage: this.storage,
      wsClient: this.wsClient,
      knownNodes: this.knownNodes,
      localNodePubkey: "",
      showToast: (msg, type, duration) => this.showToast(msg, type, duration),
      getAuthHeaders: (custom) => this.getAuthHeaders(custom),
      resolveCanonicalPubkey: (pk) => this.resolveCanonicalPubkey(pk),
      switchChannel: (idx) => this.chatModule.switchChannel(idx),
      setDmTarget: (pk, name) => this.chatModule.setDmTarget(pk, name),
      openDmConversation: (pk, name) => this.chatModule.openDmConversation(pk, name),
      openRepeaterAdminModal: (pk, name) => this.repeaterModule.openRepeaterAdminModal(pk, name),
      openTracerouteModal: (pk, name) => this.mapModule.openTracerouteModal(pk, name),
      updateRadioBadge: (ok, port) => this.updateRadioBadge(ok, port),
    };

    // Instanciación de módulos especializados
    this.snifferModule = new SnifferModule(this.context);
    this.repeaterModule = new RepeaterModule(this.context);
    this.mapModule = new MapModule(this.context);
    this.settingsModule = new SettingsModule(this.context);
    this.nodesModule = new NodesModule(this.context);
    this.chatModule = new ChatModule(this.context);

    this.init();
  }

  init() {
    this._bindElements();
    this._initTheme();
    this._initNavigation();
    this._initSidebar();
    this._initCommandPalette();
    this._subscribeBus();

    // Inicializar subsistemas modulares
    this.snifferModule.init();
    this.repeaterModule.init();
    this.mapModule.init();
    this.settingsModule.init();
    this.nodesModule.init();
    this.chatModule.init();

    // Conectar WebSocket
    this.wsClient.connect();
  }

  _bindElements() {
    this.dom = {
      themeToggleBtn: document.getElementById("themeToggleBtn"),
      appSidebar: document.getElementById("appSidebar"),
      btnToggleSidebar: document.getElementById("btnToggleSidebar"),
      btnCommandPalette: document.getElementById("btnCommandPalette"),
      commandPaletteModal: document.getElementById("commandPaletteModal"),
      cmdPaletteInput: document.getElementById("cmdPaletteInput"),
      cmdPaletteResults: document.getElementById("cmdPaletteResults"),
      btnCloseCmdPalette: document.getElementById("btnCloseCmdPalette"),
      radioStatus: document.getElementById("radio-status"),
      wsStatus: document.getElementById("ws-status"),
      headerRxCount: document.getElementById("headerRxCount"),
      headerTxCount: document.getElementById("headerTxCount"),
    };
  }

  _initTheme() {
    const savedTheme = localStorage.getItem("meshcore_theme") || "dark";
    document.body.className = `${savedTheme}-theme`;
    if (this.dom.themeToggleBtn) {
      this.dom.themeToggleBtn.addEventListener("click", () => {
        const isDark = document.body.classList.contains("dark-theme");
        const next = isDark ? "light" : "dark";
        document.body.className = `${next}-theme`;
        localStorage.setItem("meshcore_theme", next);
      });
    }
    // i18n: wire language toggle button
    const langBtn = document.getElementById("langToggleBtn");
    if (langBtn && window.I18n) {
      langBtn.addEventListener("click", () => window.I18n.toggle());
    }
    // Apply translations on init (i18n.js auto-applies on DOMContentLoaded,
    // but calling again here ensures post-module-load elements are covered)
    if (window.I18n) window.I18n.apply();
  }

  _initNavigation() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const tabId = btn.getAttribute("data-tab");
        if (!tabId) return;

        document.querySelectorAll(".nav-btn").forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
        });
        document.querySelectorAll(".tab-content").forEach((pane) => {
          pane.classList.remove("active");
          pane.setAttribute("hidden", "true");
        });

        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");

        const targetPane = document.getElementById(tabId);
        if (targetPane) {
          targetPane.classList.add("active");
          targetPane.removeAttribute("hidden");
        }

        this.activeTabId = tabId;
        this.eventBus.emit(EVENTS.TAB_CHANGED, tabId);
      });
    });
  }

  _initSidebar() {
    if (this.dom.btnToggleSidebar && this.dom.appSidebar) {
      this.dom.btnToggleSidebar.addEventListener("click", () => {
        this.dom.appSidebar.classList.toggle("collapsed");
      });
    }
  }

  _initCommandPalette() {
    const { btnCommandPalette, commandPaletteModal, cmdPaletteInput, btnCloseCmdPalette } = this.dom;
    if (btnCommandPalette && commandPaletteModal) {
      btnCommandPalette.addEventListener("click", () => {
        commandPaletteModal.classList.remove("hidden");
        if (cmdPaletteInput) cmdPaletteInput.focus();
      });
    }
    if (btnCloseCmdPalette && commandPaletteModal) {
      btnCloseCmdPalette.addEventListener("click", () => {
        commandPaletteModal.classList.add("hidden");
      });
    }
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        if (commandPaletteModal) {
          commandPaletteModal.classList.toggle("hidden");
          if (!commandPaletteModal.classList.contains("hidden") && cmdPaletteInput) {
            cmdPaletteInput.focus();
          }
        }
      }
    });
  }

  _subscribeBus() {
    this.eventBus.on(EVENTS.WS_STATUS_CHANGE, (status) => {
      if (!this.dom.wsStatus) return;
      if (status === "connected") {
        this.dom.wsStatus.className = "ws-badge ws-badge--connected";
        this.dom.wsStatus.textContent = "Web: Online";
      } else if (status === "connecting") {
        this.dom.wsStatus.className = "ws-badge ws-badge--connecting";
        this.dom.wsStatus.textContent = "Web: Conectando…";
      } else {
        this.dom.wsStatus.className = "ws-badge ws-badge--disconnected";
        this.dom.wsStatus.textContent = "Web: Desconectada";
      }
    });

    this.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (!payload) return;
      if (this.dom.headerRxCount && payload.rx_count != null) {
        this.dom.headerRxCount.textContent = String(payload.rx_count);
      }
      if (this.dom.headerTxCount && payload.tx_count != null) {
        this.dom.headerTxCount.textContent = String(payload.tx_count);
      }
      if (payload.radio_connected != null) {
        this.updateRadioBadge(Boolean(payload.radio_connected), payload.radio_port || "");
      }
    });
  }

  updateRadioBadge(connected, portName = "") {
    if (!this.dom.radioStatus) return;
    if (connected) {
      this.dom.radioStatus.className = "ws-badge ws-badge--connected";
      this.dom.radioStatus.textContent = `Radio: ${portName || "Online"}`;
    } else {
      this.dom.radioStatus.className = "ws-badge ws-badge--disconnected";
      this.dom.radioStatus.textContent = "Radio: Desconectada";
    }
  }

  showToast(message, type = "info", durationMs = 3500) {
    let container = document.getElementById("toastContainer");
    if (!container) {
      container = document.createElement("div");
      container.id = "toastContainer";
      container.className = "toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `<span class="toast-message">${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("toast-fade-out");
      setTimeout(() => toast.remove(), 300);
    }, durationMs);
  }

  getAuthHeaders(customHeaders = {}) {
    const headers = { "Content-Type": "application/json", ...customHeaders };
    const apiKey = (localStorage.getItem("meshcore_bridge_api_key") || "").trim();
    if (apiKey) {
      headers["X-Api-Key"] = apiKey;
    }
    return headers;
  }

  resolveCanonicalPubkey(pubkey) {
    return this.nodesModule.resolveCanonicalPubkey(pubkey);
  }
}

// Arranque de la aplicación cuando el DOM esté listo
document.addEventListener("DOMContentLoaded", () => {
  new MeshCoreApp();
});
