/**
 * MeshCore Web Client - Orquestador Principal (Composition Root)
 * Arquitectura Modular ES6 Nativa para SBCs e interfaces tácticas LoRa.
 */

import { eventBus, EVENTS } from "./core/eventbus.js";
import { MeshCoreStorage } from "./core/storage.js";
import { MeshCoreWebSocketClient } from "./core/websocket.js";
import { debounce, escapeHtml, buildMeshCoreContactUri } from "./core/utils.js";

import { SnifferModule } from "./modules/sniffer.js";
import { RepeaterModule } from "./modules/repeater.js";
import { MapModule } from "./modules/map.js";
import { SettingsModule } from "./modules/settings.js";
import { NodesModule } from "./modules/nodes.js";
import { ChatModule } from "./modules/chat.js";
import { AnalyticsModule } from "./modules/analytics.js";

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
    const self = this;
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
      closeRepeaterAdminModal: () => this.repeaterModule.closeRepeaterAdminModal(),
      openTracerouteModal: (pk, name) => this.mapModule.openTracerouteModal(pk, name),
      centerMapOnCoords: (lat, lon, zoom) => this.mapModule.centerMapOnCoords(lat, lon, zoom),
      centerOnLocalNode: (zoom, showToast) => this.mapModule.centerOnLocalNode(zoom, showToast),
      updateRadioBadge: (ok, port) => this.updateRadioBadge(ok, port),
      updateAirtimeBadge: (payload) => this.updateAirtimeBadge(payload),
      get activeChannelIdx() { return self.chatModule ? self.chatModule.activeChannelIdx : 0; },
      get activeDmTarget() { return self.chatModule ? self.chatModule.activeDmTarget : null; },
      get settingsModule() { return self.settingsModule; },
      get channelsList() { return self.settingsModule?.channelsList || []; },
      get localConfig() { return self.settingsModule?.cachedConfig || {}; },
      renderNodesDirectory: () => self.nodesModule?.renderNodesDirectory?.(),
      updateNodeInDom: (a, b) => self.nodesModule?.updateNodeInDom?.(a, b),
    };

    // Instanciación de módulos especializados
    this.snifferModule = new SnifferModule(this.context);
    this.repeaterModule = new RepeaterModule(this.context);
    this.mapModule = new MapModule(this.context);
    this.settingsModule = new SettingsModule(this.context);
    this.nodesModule = new NodesModule(this.context);
    this.chatModule = new ChatModule(this.context);
    this.analyticsModule = new AnalyticsModule(this.context);

    this.modules = {
      sniffer: this.snifferModule,
      repeater: this.repeaterModule,
      map: this.mapModule,
      settings: this.settingsModule,
      nodes: this.nodesModule,
      chat: this.chatModule,
      analytics: this.analyticsModule,
    };

    this.init();
  }

  init() {
    this._bindElements();
    this._initTheme();
    this._initNavigation();
    this._initSidebar();
    this._initCommandPalette();
    this._initVisibilityHandler();
    this._subscribeBus();

    // Inicializar subsistemas modulares
    this.snifferModule.init();
    this.repeaterModule.init();
    this.mapModule.init();
    this.settingsModule.init();
    this.nodesModule.init();
    this.chatModule.init();
    this.analyticsModule.init();

    // Renderizar iconos vectoriales Lucide en el DOM cargado
    if (window.initLucideIcons) window.initLucideIcons();

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
      radioStatus: document.getElementById("radio-status"),
      headerRxCount: document.getElementById("headerRxCount"),
      headerTxCount: document.getElementById("headerTxCount"),
      headerErrorRate: document.getElementById("headerErrorRate"),
      headerQueueDepth: document.getElementById("headerQueueDepth"),
      headerAirtimeChip: document.getElementById("headerAirtimeChip"),
      headerDutyCycle: document.getElementById("headerDutyCycle"),
      headerAirtimeFill: document.getElementById("headerAirtimeFill"),
    };
  }

  _initTheme() {
    const savedTheme = localStorage.getItem("meshcore_theme") || "dark";
    document.body.className = `${savedTheme}-theme`;
    this._updateThemeIcon(savedTheme);

    if (this.dom.themeToggleBtn) {
      this.dom.themeToggleBtn.addEventListener("click", () => {
        const isDark = document.body.classList.contains("dark-theme");
        const next = isDark ? "light" : "dark";
        document.body.className = `${next}-theme`;
        localStorage.setItem("meshcore_theme", next);
        this._updateThemeIcon(next);
      });
    }
    // i18n: wire language toggle button
    const langBtn = document.getElementById("langToggleBtn");
    if (langBtn && window.I18n) {
      langBtn.addEventListener("click", () => window.I18n.toggle());
    }
    window.addEventListener("mc:langchange", () => {
      this.updateRadioBadge(this._lastRadioConnected ?? false, this._lastRadioPort ?? "");
      const isDark = !document.body.classList.contains("light-theme");
      this._updateThemeIcon(isDark ? "dark" : "light");
      if (this.nodesModule) {
        if (typeof this.nodesModule.renderNodesDirectory === "function") this.nodesModule.renderNodesDirectory();
        if (typeof this.nodesModule.renderContactsGrid === "function") this.nodesModule.renderContactsGrid();
      }
      if (this.chatModule && typeof this.chatModule.renderCurrentConversation === "function") {
        this.chatModule.renderCurrentConversation();
      }
      if (this.analyticsModule && typeof this.analyticsModule.fetchAnalytics === "function") {
        this.analyticsModule.fetchAnalytics();
      }
    });
    // Apply translations on init (i18n.js auto-applies on DOMContentLoaded,
    // but calling again here ensures post-module-load elements are covered)
    if (window.I18n) window.I18n.apply();
  }

  _updateThemeIcon(theme) {
    if (!this.dom.themeToggleBtn) return;
    const isDark = theme === "dark";
    const iconName = isDark ? "sun" : "moon";
    if (window.getLucideIcon) {
      this.dom.themeToggleBtn.innerHTML = window.getLucideIcon(iconName, "", 16);
    } else {
      this.dom.themeToggleBtn.innerHTML = `<span data-lucide="${iconName}" data-size="16"></span>`;
    }
    this.dom.themeToggleBtn.title = isDark ? I18n.t('app.light_theme_title') : I18n.t('app.dark_theme_title');
    this.dom.themeToggleBtn.setAttribute("aria-label", isDark ? I18n.t('app.light_theme_title') : I18n.t('app.dark_theme_title'));
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
        document.querySelectorAll(".tab-pane, .tab-content").forEach((pane) => {
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

  _initVisibilityHandler() {
    document.addEventListener("visibilitychange", () => {
      const isVisible = !document.hidden;
      this.eventBus.emit(EVENTS.VISIBILITY_CHANGED, isVisible);
      if (isVisible && this.activeTabId) {
        // Al volver a la pestaña, refrescar el módulo activo inmediatamente
        this.eventBus.emit(EVENTS.TAB_CHANGED, this.activeTabId);
      }
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
    const { btnCommandPalette, commandPaletteModal, cmdPaletteInput, cmdPaletteResults } = this.dom;
    const filterCmdItems = (q) => {
      const query = (q || "").toLowerCase().trim();
      document.querySelectorAll("#cmdPaletteResults .cmd-item").forEach((item) => {
        const text = item.textContent.toLowerCase();
        item.style.display = (!query || text.includes(query)) ? "" : "none";
      });
    };

    if (btnCommandPalette && commandPaletteModal) {
      btnCommandPalette.addEventListener("click", () => {
        commandPaletteModal.classList.remove("hidden");
        if (cmdPaletteInput) {
          cmdPaletteInput.value = "";
          cmdPaletteInput.focus();
        }
        filterCmdItems("");
      });
    }
    if (commandPaletteModal) {
      commandPaletteModal.addEventListener("click", (e) => {
        if (e.target === commandPaletteModal) {
          commandPaletteModal.classList.add("hidden");
        }
      });
    }
    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        if (commandPaletteModal) {
          commandPaletteModal.classList.toggle("hidden");
          if (!commandPaletteModal.classList.contains("hidden") && cmdPaletteInput) {
            cmdPaletteInput.value = "";
            cmdPaletteInput.focus();
            filterCmdItems("");
          }
        }
      } else if (e.key === "Escape") {
        const openModals = Array.from(document.querySelectorAll(".modal-overlay:not(.hidden)"));
        if (openModals.length > 0) {
          const topModal = openModals[openModals.length - 1];
          // Close top modal via its close button or by adding hidden
          const closeBtn = topModal.querySelector(".modal-close");
          if (closeBtn) {
            closeBtn.click();
          } else {
            topModal.classList.add("hidden");
          }
        }
      }
    });

    // Cierre intuitivo al hacer clic en el backdrop de cualquier modal
    document.addEventListener("click", (e) => {
      if (e.target && e.target.classList && e.target.classList.contains("modal-overlay")) {
        const closeBtn = e.target.querySelector(".modal-close");
        if (closeBtn) {
          closeBtn.click();
        } else {
          e.target.classList.add("hidden");
        }
      }
    });

    if (cmdPaletteInput) {
      cmdPaletteInput.addEventListener("input", (e) => {
        filterCmdItems(e.target.value);
      });
    }

    if (cmdPaletteResults) {
      cmdPaletteResults.addEventListener("click", async (e) => {
        const item = e.target.closest(".cmd-item");
        if (!item) return;
        const action = item.getAttribute("data-action");
        if (!action) return;
        if (commandPaletteModal) commandPaletteModal.classList.add("hidden");

        if (action.startsWith("tab-")) {
          const navBtn = document.querySelector(`.nav-btn[data-tab="${action}"]`);
          if (navBtn) navBtn.click();
        } else if (action === "action-diag") {
          const navBtn = document.querySelector('.nav-btn[data-tab="tab-logs"]');
          if (navBtn) navBtn.click();
          try {
            const res = await fetch("/api/diagnostics/report", {
              headers: this.getAuthHeaders ? this.getAuthHeaders() : {},
            });
            const data = await res.json();
            this.showToast(data.status === "ok" ? "Auto-diagnóstico completado" : "Error en diagnóstico", data.status === "ok" ? "success" : "error");
          } catch (err) {
            this.showToast(`Error: ${err.message}`, "error");
          }
        } else if (action === "action-debug-toggle") {
          try {
            const res = await fetch("/api/system/logs/level", {
              method: "POST",
              headers: this.getAuthHeaders ? this.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ level: "DEBUG" }),
            });
            const data = await res.json();
            this.showToast(`Nivel de log: ${data.level || "DEBUG"}`, "info");
          } catch (err) {
            this.showToast(`Error: ${err.message}`, "error");
          }
        } else if (action === "action-advert-hop") {
          try {
            await fetch("/api/admin", {
              method: "POST",
              headers: this.getAuthHeaders ? this.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ action: "advert", hops: 0 }),
            });
            this.showToast("Baliza Advert (0 saltos) transmitida", "success");
          } catch (err) {
            this.showToast(`Error: ${err.message}`, "error");
          }
        } else if (action === "action-advert-flood") {
          try {
            await fetch("/api/admin", {
              method: "POST",
              headers: this.getAuthHeaders ? this.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ action: "advert", hops: 7 }),
            });
            this.showToast("Baliza Advert Flood transmitida", "success");
          } catch (err) {
            this.showToast(`Error: ${err.message}`, "error");
          }
        } else if (action === "action-advert-clipboard") {
          const localPk = this.localNodePubkey || (document.getElementById("localNodePubkey")?.value || "");
          if (localPk) {
            const localName = (document.getElementById("localNodeName")?.value || "").trim() || "MeshCore Base";
            const uri = buildMeshCoreContactUri(localName, localPk, "CLIENT");
            navigator.clipboard.writeText(uri);
            this.showToast("Enlace de nodo copiado al portapapeles", "success");
          } else {
            this.showToast("Clave de nodo local no disponible", "info");
          }
        }
      });
    }
  }

  _subscribeBus() {
    this.eventBus.on(EVENTS.WS_STATUS_CHANGE, (status) => {
      if (status === "connected") {
        if (this.modules?.settings?.fetchLocalNodeConfig) {
          this.modules.settings.fetchLocalNodeConfig();
        }
        if (this.modules?.nodes?.fetchNodes) {
          this.modules.nodes.fetchNodes();
        }
      }
    });

    this.eventBus.on(EVENTS.METRICS_UPDATE, (payload) => {
      if (!payload) return;
      if (this.dom.headerRxCount && payload.rx_count != null) {
        this.dom.headerRxCount.textContent = String(payload.rx_count);
      }
      if (this.dom.headerTxCount && payload.tx_count != null) {
        this.dom.headerTxCount.textContent = String(payload.tx_count);
      }
      if (this.dom.headerErrorRate && payload.error_rate != null) {
        this.dom.headerErrorRate.textContent = `${Number(payload.error_rate).toFixed(1)}%`;
      }
      if (this.dom.headerQueueDepth && payload.queue_depth != null) {
        this.dom.headerQueueDepth.textContent = String(payload.queue_depth);
      }
      if (payload.duty_cycle_pct != null || payload.hourly_duty_cycle_pct != null) {
        this.updateAirtimeBadge(payload);
      }
      if (payload.radio_connected != null) {
        this.updateRadioBadge(Boolean(payload.radio_connected), payload.radio_port || "");
      }
    });

    this.eventBus.on(EVENTS.DUTY_CYCLE_ALERT, (payload) => {
      if (payload) {
        this.updateAirtimeBadge(payload);
      }
    });

    this.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (!payload) return;
      const evType = String(payload.event || payload.event_type || payload.type || "").toLowerCase();
      if (evType === "self_info" || evType === "device_info") {
        if (this.modules?.settings?.populateLocalConfig) {
          this.modules.settings.populateLocalConfig(payload);
        }
      }
    });
  }

  updateAirtimeBadge(payload) {
    const chip = this.dom.headerAirtimeChip;
    const txt = this.dom.headerDutyCycle;
    const fill = this.dom.headerAirtimeFill || document.getElementById("headerAirtimeFill");
    if (!txt) return;

    const pct = Number(payload.duty_cycle_pct != null ? payload.duty_cycle_pct : (payload.hourly_duty_cycle_pct || 0.0));
    const limitPct = Number(payload.hourly_limit_pct || 1.0);
    const warnPct = Number(payload.warn_threshold_pct || 80.0);
    txt.textContent = `${pct.toFixed(1)}%`;

    const isCritical = Boolean(payload.is_critical || payload.level === "critical" || (pct >= limitPct));
    const isWarning = Boolean(payload.is_warning || payload.level === "warning" || (!isCritical && pct >= (limitPct * (warnPct / 100.0))));

    let newStatus = "normal";
    if (isCritical) newStatus = "critical";
    else if (isWarning) newStatus = "warning";

    // Cálculo proporcional de la barra de progreso (0% a 100% del presupuesto horario permitido)
    const fillPct = limitPct > 0 ? Math.max(0, Math.min(100, Math.round((pct / limitPct) * 100))) : 0;

    if (fill) {
      fill.style.width = `${fillPct}%`;
      fill.className = `header-airtime-fill ${newStatus === "critical" ? "danger" : newStatus}`;
    }

    if (chip) {
      chip.classList.toggle("warning", isWarning);
      chip.classList.toggle("danger", isCritical);
      chip.classList.toggle("normal", !isWarning && !isCritical);
      chip.title = isCritical
        ? `ALERTA CRÍTICA: Duty Cycle LoRa al ${pct.toFixed(1)}% (Límite horario ${limitPct}% superado. Transmisiones bloqueadas)`
        : (isWarning
          ? `ADVERTENCIA: Duty Cycle LoRa al ${pct.toFixed(1)}% (Supera el ${warnPct}% del cupo horario)`
          : `Presupuesto de Airtime LoRa y Duty Cycle (1h): ${pct.toFixed(1)}% / ${limitPct}%`);
    }

    if (this._lastAirtimeStatus && this._lastAirtimeStatus !== newStatus) {
      if (newStatus === "critical") {
        this.showToast(`⚠️ Alerta Crítica: Duty Cycle LoRa al ${pct.toFixed(1)}% (Límite alcanzado)`, "error");
      } else if (newStatus === "warning") {
        this.showToast(`⚠️ Advertencia: Consumo de Airtime al ${pct.toFixed(1)}%`, "warning");
      } else if (newStatus === "normal" && this._lastAirtimeStatus !== "normal") {
        this.showToast(`✅ Duty Cycle LoRa restablecido a normal (${pct.toFixed(1)}%)`, "info");
      }
    }
    this._lastAirtimeStatus = newStatus;
  }

  updateRadioBadge(connected, portName = "") {
    this._lastRadioConnected = connected;
    this._lastRadioPort = portName;
    const el = this.dom.radioStatus;
    if (!el) return;

    el.classList.toggle("radio-status--connected", connected);
    el.classList.toggle("radio-status--disconnected", !connected);

    const txtEl = el.querySelector(".status-text");
    const portClean = portName ? String(portName).trim() : "";

    let label = "";
    if (connected) {
      label = portClean
        ? I18n.t('app.radio_online').replace('{port}', portClean)
        : I18n.t('app.radio_online_fallback');
    } else {
      label = I18n.t('app.radio_offline');
    }

    if (txtEl) {
      txtEl.textContent = label;
    } else {
      el.textContent = label;
    }

    el.title = connected
      ? `Transceptor LoRa Conectado${portClean ? ` (${portClean})` : ""} - Enlace RF activo`
      : "Transceptor LoRa Desconectado - Verifique el puerto USB o adaptador serial";
  }

  showToast(message, type = "info", durationMs = 3500) {
    let container = document.getElementById("toastContainer");
    if (!container) {
      container = document.createElement("div");
      container.id = "toastContainer";
      container.className = "toast-container";
      container.setAttribute("aria-live", "polite");
      document.body.appendChild(container);
    }

    const icons = {
      success: `<svg class="toast-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
      info: `<svg class="toast-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`,
      warning: `<svg class="toast-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
      error: `<svg class="toast-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`,
    };
    const icon = icons[type] || icons.info;

    const toast = document.createElement("div");
    toast.className = `toast toast-item toast-${type}`;
    toast.setAttribute("role", "alert");
    toast.innerHTML = `
      <span class="toast-icon" aria-hidden="true">${icon}</span>
      <span class="toast-message">${escapeHtml(message)}</span>
      <button type="button" class="toast-close" aria-label="Cerrar notificación">&times;</button>
    `;

    let dismissed = false;
    const dismiss = () => {
      if (dismissed) return;
      dismissed = true;
      toast.classList.add("toast-fade-out");
      setTimeout(() => toast.remove(), 300);
    };

    const closeBtn = toast.querySelector(".toast-close");
    if (closeBtn) {
      closeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        dismiss();
      });
    }

    container.appendChild(toast);

    if (durationMs > 0) {
      setTimeout(dismiss, durationMs);
    }
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
