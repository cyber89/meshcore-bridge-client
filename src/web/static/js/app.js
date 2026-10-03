/**
 * MeshCore Web Client - Orquestador Principal (Composition Root)
 * Arquitectura Modular ES6 Nativa para SBCs e interfaces tácticas LoRa.
 */

import { eventBus, EVENTS } from "./core/eventbus.js";
import { MeshCoreStorage } from "./core/storage.js";
import { MeshCoreWebSocketClient } from "./core/websocket.js";
import { escapeHtml, buildMeshCoreContactUri } from "./core/utils.js";

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
      showConfirm: (msg, opts) => this.showConfirm(msg, opts),
      showAlert: (msg, opts) => this.showAlert(msg, opts),
      showPrompt: (msg, defVal, opts) => this.showPrompt(msg, defVal, opts),
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
    document.getElementById("btnSelectImportFile")?.addEventListener("click", () => document.getElementById("importFileInput")?.click());
    this._initCommandPalette();
    this._initModalFocus();
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

    // Exponer helpers globales de diálogos del sistema
    window.showConfirm = (msg, opts) => this.showConfirm(msg, opts);
    window.showAlert = (msg, opts) => this.showAlert(msg, opts);
    window.showPrompt = (msg, defVal, opts) => this.showPrompt(msg, defVal, opts);

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
    const savedTheme = localStorage.getItem("meshcore_theme") === "light" ? "light" : "dark";
    document.body.classList.remove("dark-theme", "light-theme");
    document.body.classList.add(`${savedTheme}-theme`);
    this._updateThemeIcon(savedTheme);

    if (this.dom.themeToggleBtn) {
      this.dom.themeToggleBtn.addEventListener("click", () => {
        const isDark = document.body.classList.contains("dark-theme");
        const next = isDark ? "light" : "dark";
        document.body.classList.remove("dark-theme", "light-theme");
        document.body.classList.add(`${next}-theme`);
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
      this._updateSidebarState();
      if (this._lastAirtimePayload) this.updateAirtimeBadge(this._lastAirtimePayload);
      Object.values(this.modules).forEach((module) => module.onLanguageChange?.());
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
    const label = I18n.t(isDark ? 'app.dark_theme_title' : 'app.light_theme_title');
    this.dom.themeToggleBtn.title = label;
    this.dom.themeToggleBtn.setAttribute("aria-label", label);
    const canvasColor = getComputedStyle(document.body).getPropertyValue("--bg-canvas").trim();
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", canvasColor || (isDark ? "#070b14" : "#f8fafc"));
  }

  _initNavigation() {
    const tabs = Array.from(document.querySelectorAll(".nav-btn"));
    tabs.forEach((btn, index) => {
      btn.addEventListener("click", () => {
        const tabId = btn.getAttribute("data-tab");
        if (!tabId) return;

        document.querySelectorAll(".nav-btn").forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
          b.tabIndex = -1;
        });
        document.querySelectorAll(".tab-pane, .tab-content").forEach((pane) => {
          pane.classList.remove("active");
          pane.setAttribute("hidden", "true");
        });

        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        btn.tabIndex = 0;

        const targetPane = document.getElementById(tabId);
        if (targetPane) {
          targetPane.classList.add("active");
          targetPane.removeAttribute("hidden");
        }

        this.activeTabId = tabId;
        this.eventBus.emit(EVENTS.TAB_CHANGED, tabId);
      });
      btn.addEventListener("keydown", (event) => {
        let nextIndex;
        if (event.key === "ArrowDown" || event.key === "ArrowRight") nextIndex = (index + 1) % tabs.length;
        else if (event.key === "ArrowUp" || event.key === "ArrowLeft") nextIndex = (index - 1 + tabs.length) % tabs.length;
        else if (event.key === "Home") nextIndex = 0;
        else if (event.key === "End") nextIndex = tabs.length - 1;
        else return;
        event.preventDefault();
        tabs[nextIndex].focus();
        tabs[nextIndex].click();
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
        this._updateSidebarState();
      });
      this._updateSidebarState();
    }
  }

  _initModalFocus() {
    const modals = Array.from(document.querySelectorAll('.modal-overlay[role="dialog"]'));
    const focusable = (modal) => Array.from(modal.querySelectorAll(
      'button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])'
    )).filter((element) => element.getClientRects().length > 0 && !element.closest('[hidden], .hidden'));
    const isOpen = (modal) => !modal.classList.contains("hidden") && !modal.hidden;
    let lastOutsideFocus = document.activeElement;
    document.addEventListener("focusin", (event) => {
      if (!modals.some((modal) => modal.contains(event.target))) lastOutsideFocus = event.target;
    });
    const previousFocus = new WeakMap();
    const previousState = new WeakMap(modals.map((modal) => [modal, isOpen(modal)]));
    modals.forEach((modal) => {
      // Modules own dialog actions; observe visibility to provide consistent focus.
      new MutationObserver(() => {
        const open = isOpen(modal);
        if (open === previousState.get(modal)) return;
        previousState.set(modal, open);
        if (open) {
          previousFocus.set(modal, modal.contains(document.activeElement) ? lastOutsideFocus : document.activeElement);
          if (!modal.contains(document.activeElement)) {
            const target = focusable(modal).find((element) => !element.matches(".modal-close")) || focusable(modal)[0];
            if (target) target.focus();
            else {
              modal.tabIndex = -1;
              modal.focus();
            }
          }
        } else {
          const target = previousFocus.get(modal);
          if (target?.isConnected && target.getClientRects().length > 0) target.focus();
        }
      }).observe(modal, { attributes: true, attributeFilter: ["class", "hidden"] });
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      const modal = modals.filter(isOpen).at(-1);
      if (!modal || modal === this.dom.commandPaletteModal) return;
      const items = focusable(modal);
      const first = items[0];
      const last = items[items.length - 1];
      if (!first) {
        event.preventDefault();
        modal.focus();
      } else if (!modal.contains(document.activeElement) || (event.shiftKey && document.activeElement === first)) {
        event.preventDefault();
        (event.shiftKey ? last : first).focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    });
  }

  _updateSidebarState() {
    const btn = this.dom.btnToggleSidebar;
    if (!btn || !this.dom.appSidebar) return;
    const collapsed = this.dom.appSidebar.classList.contains("collapsed");
    btn.setAttribute("aria-expanded", String(!collapsed));
    const label = I18n.t(collapsed ? "nav.expand" : "nav.collapse");
    btn.title = label;
    btn.setAttribute("aria-label", label);
    const text = btn.querySelector(".sidebar-toggle-label");
    if (text) text.textContent = label;
  }

  _initCommandPalette() {
    const { btnCommandPalette, commandPaletteModal, cmdPaletteInput, cmdPaletteResults } = this.dom;
    let lastActiveElement = null;
    let selectedIdx = -1;

    const getVisibleItems = () => {
      if (!cmdPaletteResults) return [];
      return Array.from(cmdPaletteResults.querySelectorAll(".cmd-item")).filter((item) => item.style.display !== "none");
    };

    const updateSelection = (newIdx) => {
      const visible = getVisibleItems();
      visible.forEach((it) => {
        it.classList.remove("is-selected");
        it.setAttribute("aria-selected", "false");
      });
      if (visible.length === 0) {
        selectedIdx = -1;
        return;
      }
      selectedIdx = (newIdx + visible.length) % visible.length;
      const target = visible[selectedIdx];
      target.classList.add("is-selected");
      target.setAttribute("aria-selected", "true");
      target.focus();
      target.scrollIntoView({ block: "nearest" });
    };

    const filterCmdItems = (q) => {
      const query = (q || "").toLowerCase().trim();
      selectedIdx = -1;

      // 1. Limpiar nodos dinámicos previos
      document.querySelectorAll("#cmdPaletteResults .cmd-node-match").forEach((el) => el.remove());

      // 2. Filtrar comandos estáticos
      document.querySelectorAll("#cmdPaletteResults .cmd-item:not(.cmd-node-match)").forEach((item) => {
        const text = item.textContent.toLowerCase();
        item.style.display = (!query || text.includes(query)) ? "" : "none";
        item.classList.remove("is-selected");
        item.setAttribute("aria-selected", "false");
      });

      // 3. Buscar y agregar nodos coincidentes (FE-11)
      if (query.length >= 2) {
        const matchedNodes = [];
        const knownNodes = this.context.knownNodes;
        if (knownNodes instanceof Map) {
          for (const [k, n] of knownNodes.entries()) {
            const name = String(n.name || "").toLowerCase();
            const pk = String(n.public_key || k).toLowerCase();
            const role = String(n.role || "CLIENT").toLowerCase();
            const translatedRole = I18n.role(n.role || "CLIENT").toLowerCase();
            if (name.includes(query) || pk.includes(query) || role.includes(query) || translatedRole.includes(query)) {
              matchedNodes.push(n);
              if (matchedNodes.length >= 8) break;
            }
          }
        }

        matchedNodes.forEach((node) => {
          const item = document.createElement("div");
          item.className = "cmd-item cmd-node-match";
          item.setAttribute("role", "option");
          item.setAttribute("tabindex", "0");
          item.setAttribute("aria-selected", "false");
          item.setAttribute("data-action", "select-node");
          item.setAttribute("data-pubkey", node.public_key || "");
          const name = node.name || (node.public_key ? node.public_key.slice(0, 8) : I18n.t("app.node_fallback"));
          item.setAttribute("data-name", name);
          const role = String(node.role || "CLIENT").toUpperCase().replace(/^ROUTER$/, "REPEATER");
          const roleKey = "node.role_" + (["CLIENT", "REPEATER", "ROOM", "SENSOR", "LOCAL"].includes(role) ? role.toLowerCase() : "unknown");
          item.innerHTML = `<span data-lucide="radio" data-size="14" aria-hidden="true"></span> <span data-i18n="app.node_match">${escapeHtml(I18n.t("app.node_match"))}</span>: <strong>${escapeHtml(name)}</strong> [<span data-i18n="${roleKey}">${escapeHtml(I18n.t(roleKey))}</span>]`;
          cmdPaletteResults.appendChild(item);
        });
        if (window.lucide && typeof window.lucide.createIcons === "function") {
          window.lucide.createIcons();
        }
      }
    };

    window.addEventListener("mc:langchange", () => {
      if (!commandPaletteModal || commandPaletteModal.classList.contains("hidden")) return;
      const focused = document.activeElement;
      const focusedItem = focused?.closest(".cmd-item");
      const action = focusedItem?.getAttribute("data-action");
      const pubkey = focusedItem?.getAttribute("data-pubkey");
      filterCmdItems(cmdPaletteInput?.value || "");
      if (focusedItem) {
        const items = getVisibleItems();
        const index = items.findIndex((item) => item.getAttribute("data-action") === action && item.getAttribute("data-pubkey") === pubkey);
        if (index >= 0) updateSelection(index);
        else cmdPaletteInput?.focus();
      }
    });

    const openPalette = () => {
      if (!commandPaletteModal) return;
      lastActiveElement = document.activeElement;
      commandPaletteModal.classList.remove("hidden");
      if (cmdPaletteInput) {
        cmdPaletteInput.value = "";
        cmdPaletteInput.focus();
      }
      filterCmdItems("");
    };

    const closePalette = () => {
      if (!commandPaletteModal) return;
      commandPaletteModal.classList.add("hidden");
      if (lastActiveElement && typeof lastActiveElement.focus === "function") {
        lastActiveElement.focus();
      }
    };

    if (btnCommandPalette && commandPaletteModal) {
      btnCommandPalette.addEventListener("click", openPalette);
    }
    if (commandPaletteModal) {
      commandPaletteModal.addEventListener("click", (e) => {
        if (e.target === commandPaletteModal) {
          closePalette();
        }
      });
    }

    window.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (commandPaletteModal) {
          if (commandPaletteModal.classList.contains("hidden")) {
            openPalette();
          } else {
            closePalette();
          }
        }
      } else if (e.key === "Escape") {
        if (commandPaletteModal && !commandPaletteModal.classList.contains("hidden")) {
          e.preventDefault();
          closePalette();
          return;
        }
        const openModals = Array.from(document.querySelectorAll(".modal-overlay:not(.hidden)"));
        if (openModals.length > 0) {
          const topModal = openModals[openModals.length - 1];
          const closeBtn = topModal.querySelector(".modal-close");
          if (closeBtn) {
            closeBtn.click();
          } else {
            topModal.classList.add("hidden");
          }
        }
      }
    });

    if (commandPaletteModal) {
      commandPaletteModal.addEventListener("keydown", (e) => {
        const visible = getVisibleItems();
        if (e.key === "ArrowDown") {
          e.preventDefault();
          updateSelection(selectedIdx + 1);
        } else if (e.key === "ArrowUp") {
          e.preventDefault();
          updateSelection(selectedIdx <= 0 ? visible.length - 1 : selectedIdx - 1);
        } else if (e.key === "Enter" || (e.key === " " && document.activeElement?.matches(".cmd-item"))) {
          const activeItem = document.activeElement?.closest(".cmd-item") || visible[selectedIdx < 0 ? 0 : selectedIdx];
          if (activeItem) {
            e.preventDefault();
            activeItem.click();
          }
        } else if (e.key === "Tab") {
          if (visible.length > 0) {
            const lastItem = visible[visible.length - 1];
            if (!e.shiftKey && document.activeElement === lastItem) {
              e.preventDefault();
              cmdPaletteInput?.focus();
            } else if (e.shiftKey && document.activeElement === cmdPaletteInput) {
              e.preventDefault();
              lastItem.focus();
            }
          } else {
            e.preventDefault();
            cmdPaletteInput?.focus();
          }
        }
      });
    }

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
        closePalette();

        if (action.startsWith("tab-")) {
          const navBtn = document.querySelector(`.nav-btn[data-tab="${action}"]`);
          if (navBtn) navBtn.click();
        } else if (action === "select-node") {
          const pubkey = item.getAttribute("data-pubkey");
          const node = this.context.knownNodes.get(String(pubkey || "").toLowerCase());
          const role = String(node?.role || "CLIENT").toUpperCase();
          const localPk = (this.context.localNodePubkey || document.getElementById("localNodePubkey")?.value || "").toLowerCase();
          if (pubkey && pubkey.toLowerCase() !== localPk && role !== "REPEATER" && role !== "ROUTER") {
            document.querySelector('.nav-btn[data-tab="tab-chat"]')?.click();
            this.chatModule.openDmConversation(pubkey, item.getAttribute("data-name") || pubkey.slice(0, 8));
          } else {
            const navBtn = document.querySelector('.nav-btn[data-tab="tab-nodes"]');
            if (navBtn) navBtn.click();
          }
        } else if (action === "action-diag") {
          const navBtn = document.querySelector('.nav-btn[data-tab="tab-logs"]');
          if (navBtn) navBtn.click();
          try {
            const res = await fetch("/api/diagnostics/report", {
              headers: this.getAuthHeaders ? this.getAuthHeaders() : {},
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.showToast(I18n.t(data.status === "ok" ? "app.diag_ok" : "app.diag_error"), data.status === "ok" ? "success" : "error");
          } catch (err) {
            this.showToast(I18n.t("app.error", { error: err.message }), "error");
          }
        } else if (action === "action-debug-toggle") {
          try {
            const currentRes = await fetch("/api/system/logs/level", { headers: this.getAuthHeaders() });
            if (!currentRes.ok) throw new Error(`HTTP ${currentRes.status}`);
            const current = await currentRes.json();
            const level = current.level === "DEBUG" ? "INFO" : "DEBUG";
            const res = await fetch("/api/system/logs/level", {
              method: "POST",
              headers: this.getAuthHeaders ? this.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ level }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            this.showToast(I18n.t("app.log_level", { level: data.level || level }), "info");
          } catch (err) {
            this.showToast(I18n.t("app.error", { error: err.message }), "error");
          }
        } else if (action === "action-advert-hop") {
          try {
            const res = await fetch("/api/admin", {
              method: "POST",
              headers: this.getAuthHeaders ? this.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ action: "advert", hops: 0 }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.showToast(I18n.t("app.advert_hop_sent"), "success");
          } catch (err) {
            this.showToast(I18n.t("app.error", { error: err.message }), "error");
          }
        } else if (action === "action-advert-flood") {
          try {
            const res = await fetch("/api/admin", {
              method: "POST",
              headers: this.getAuthHeaders ? this.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ action: "advert", hops: 7 }),
            });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            this.showToast(I18n.t("app.advert_flood_sent"), "success");
          } catch (err) {
            this.showToast(I18n.t("app.error", { error: err.message }), "error");
          }
        } else if (action === "action-advert-clipboard") {
          const localPk = this.localNodePubkey || (document.getElementById("localNodePubkey")?.value || "");
          if (localPk) {
            const localName = (document.getElementById("localNodeName")?.value || "").trim() || "MeshCore Base";
            const uri = buildMeshCoreContactUri(localName, localPk, "CLIENT");
            try {
              await navigator.clipboard.writeText(uri);
              this.showToast(I18n.t("toast.uri_copied"), "success");
            } catch (err) {
              this.showToast(I18n.t("app.error", { error: err.message }), "error");
            }
          } else {
            this.showToast(I18n.t("app.local_key_missing"), "info");
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

    this.eventBus.on(EVENTS.AIRTIME_CUTOFF_CHANGE, (payload) => {
      if (!payload) return;
      const active = Boolean(payload.active);
      const chUtil = Number(payload.channel_utilization_pct != null ? payload.channel_utilization_pct : (payload.channel_utilization || 0));
      const thresh = Number(payload.threshold_pct || 35.0);
      const resume = Number(payload.resume_pct || 30.0);
      if (active) {
        this.showToast(I18n.t("app.cutoff_active", { value: chUtil, threshold: thresh }), "warning", 6000);
      } else {
        this.showToast(I18n.t("app.cutoff_restored", { value: chUtil, threshold: resume }), "info", 4000);
      }
      this.updateAirtimeBadge({ cutoff_active: active, channel_utilization_pct: chUtil });
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
    // Cutoff events contain only utilization; preserve the last duty-cycle values.
    const values = { ...payload };
    if (values.duty_cycle_pct == null && values.hourly_duty_cycle_pct != null) {
      values.duty_cycle_pct = values.hourly_duty_cycle_pct;
    }
    if (values.duty_cycle_pct != null) {
      values.is_critical = Boolean(values.is_critical);
      values.is_warning = Boolean(values.is_warning);
      values.level = values.level || "";
    }
    this._lastAirtimePayload = { ...this._lastAirtimePayload, ...values };
    payload = this._lastAirtimePayload;
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

    if (payload.cutoff_active != null) {
      this._lastCutoffActive = Boolean(payload.cutoff_active);
    }
    if (payload.channel_utilization_pct != null) {
      this._lastChannelUtil = Number(payload.channel_utilization_pct);
    }

    if (chip) {
      chip.classList.toggle("warning", isWarning);
      chip.classList.toggle("danger", isCritical);
      chip.classList.toggle("normal", !isWarning && !isCritical);
      chip.classList.toggle("airtime-cutoff", Boolean(this._lastCutoffActive));

      let titleStr = I18n.t(isCritical ? "app.airtime_critical_title" : (isWarning ? "app.airtime_warning_title" : "app.airtime_normal_title"), {
        value: pct.toFixed(1), limit: limitPct, warning: warnPct,
      });

      if (this._lastCutoffActive) {
        titleStr += I18n.t("app.airtime_cutoff_suffix", { value: this._lastChannelUtil || 0 });
      }
      chip.title = titleStr;
    }


    if (this._lastAirtimeStatus && this._lastAirtimeStatus !== newStatus) {
      if (newStatus === "critical") {
        this.showToast(I18n.t("app.airtime_critical_toast", { value: pct.toFixed(1) }), "error");
      } else if (newStatus === "warning") {
        this.showToast(I18n.t("app.airtime_warning_toast", { value: pct.toFixed(1) }), "warning");
      } else if (newStatus === "normal" && this._lastAirtimeStatus !== "normal") {
        this.showToast(I18n.t("app.airtime_normal_toast", { value: pct.toFixed(1) }), "info");
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
      ? I18n.t("app.radio_online_title", { port: portClean ? ` (${portClean})` : "" })
      : I18n.t("app.radio_offline_title");
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
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    toast.innerHTML = `
      <span class="toast-icon" aria-hidden="true">${icon}</span>
      <span class="toast-message">${escapeHtml(message)}</span>
      <button type="button" class="toast-close" data-i18n-aria-label="app.close_toast" aria-label="${escapeHtml(I18n.t("app.close_toast"))}">&times;</button>
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

  /**
   * Muestra un diálogo de confirmación modal con diseño del sistema.
   * @param {string} message
   * @param {Object} [options]
   * @returns {Promise<boolean>}
   */
  showConfirm(message, options = {}) {
    return this._showSystemDialog({
      mode: "confirm",
      message,
      title: options.title || (options.isDanger ? (I18n.t("modal.confirm") || "Confirmar") : (I18n.t("modal.confirm") || "Confirmar")),
      confirmText: options.confirmText || I18n.t("modal.confirm") || "Confirmar",
      cancelText: options.cancelText || I18n.t("modal.cancel") || "Cancelar",
      isDanger: Boolean(options.isDanger),
      type: options.type || (options.isDanger ? "warning" : "info"),
      icon: options.icon || (options.isDanger ? "alert-triangle" : "help-circle"),
    });
  }

  /**
   * Muestra un diálogo de alerta informativa o de error con diseño del sistema.
   * @param {string} message
   * @param {Object} [options]
   * @returns {Promise<void>}
   */
  showAlert(message, options = {}) {
    const isError = options.type === "error";
    return this._showSystemDialog({
      mode: "alert",
      message,
      title: options.title || (isError ? (I18n.t("modal.error") || "Error") : (I18n.t("modal.info") || "Información")),
      confirmText: options.confirmText || options.buttonText || I18n.t("modal.close") || "Aceptar",
      isDanger: false,
      type: options.type || (isError ? "error" : "info"),
      icon: options.icon || (isError ? "alert-triangle" : (options.type === "warning" ? "shield-alert" : "info")),
    });
  }

  /**
   * Muestra un diálogo para solicitud de texto simple.
   * @param {string} message
   * @param {string} [defaultValue=""]
   * @param {Object} [options]
   * @returns {Promise<string|null>}
   */
  showPrompt(message, defaultValue = "", options = {}) {
    return this._showSystemDialog({
      mode: "prompt",
      message,
      defaultValue,
      title: options.title || "Entrada de Datos",
      confirmText: options.confirmText || I18n.t("modal.confirm") || "Aceptar",
      cancelText: options.cancelText || I18n.t("modal.cancel") || "Cancelar",
      isDanger: false,
      type: "info",
      icon: options.icon || "help-circle",
    });
  }

  _ensureSystemDialogModal() {
    let modal = document.getElementById("systemDialogModal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "systemDialogModal";
      modal.className = "modal-overlay hidden";
      modal.setAttribute("role", "dialog");
      modal.setAttribute("aria-modal", "true");
      modal.setAttribute("aria-labelledby", "systemDialogTitleText");
      modal.setAttribute("aria-describedby", "systemDialogMessage");
      modal.innerHTML = `
        <div class="modal-card system-dialog-card" id="systemDialogCard">
          <div class="modal-header system-dialog-header">
            <h3 id="systemDialogTitle">
              <span class="modal-title-icon" id="systemDialogIcon" data-lucide="help-circle" data-size="18"></span>
              <span id="systemDialogTitleText">Confirmar</span>
            </h3>
            <button type="button" class="btn-icon modal-close" id="btnCloseSystemDialog" aria-label="Cerrar modal">✕</button>
          </div>
          <div class="modal-body system-dialog-body">
            <p id="systemDialogMessage" class="system-dialog-message"></p>
            <div id="systemDialogInputWrap" class="system-dialog-input-wrap hidden" style="margin-top: 14px;">
              <input type="text" id="systemDialogInput" class="text-input" style="width: 100%;" autocomplete="off" />
            </div>
          </div>
          <div class="modal-footer system-dialog-footer">
            <button type="button" class="btn-secondary" id="btnCancelSystemDialog">Cancelar</button>
            <button type="button" class="btn-primary" id="btnConfirmSystemDialog">Confirmar</button>
          </div>
        </div>
      `;
      document.body.appendChild(modal);
    }
    return modal;
  }

  _showSystemDialog(config) {
    return new Promise((resolve) => {
      const modal = this._ensureSystemDialogModal();

      const titleEl = document.getElementById("systemDialogTitleText");
      const iconEl = document.getElementById("systemDialogIcon");
      const msgEl = document.getElementById("systemDialogMessage");
      const inputWrap = document.getElementById("systemDialogInputWrap");
      const inputEl = document.getElementById("systemDialogInput");
      const btnConfirm = document.getElementById("btnConfirmSystemDialog");
      const btnCancel = document.getElementById("btnCancelSystemDialog");
      const btnClose = document.getElementById("btnCloseSystemDialog");

      if (titleEl) titleEl.textContent = config.title;
      if (msgEl) msgEl.textContent = config.message;

      if (iconEl && window.getLucideIcon) {
        iconEl.innerHTML = window.getLucideIcon(config.icon || "info", "", 18);
        iconEl.className = `modal-title-icon ${config.type === "error" || config.isDanger ? "is-danger" : (config.type === "warning" ? "is-warning" : "")}`;
      }

      if (btnConfirm) {
        btnConfirm.textContent = config.confirmText;
        btnConfirm.className = config.isDanger ? "btn-danger" : "btn-primary";
      }

      if (btnCancel) {
        if (config.mode === "alert") {
          btnCancel.classList.add("hidden");
        } else {
          btnCancel.classList.remove("hidden");
          btnCancel.textContent = config.cancelText;
        }
      }

      if (inputWrap && inputEl) {
        if (config.mode === "prompt") {
          inputWrap.classList.remove("hidden");
          inputEl.value = config.defaultValue || "";
        } else {
          inputWrap.classList.add("hidden");
        }
      }

      let settled = false;
      const cleanup = () => {
        if (settled) return;
        settled = true;
        modal.classList.add("hidden");
        document.removeEventListener("keydown", onKeyDown);
        if (btnConfirm) btnConfirm.removeEventListener("click", onConfirm);
        if (btnCancel) btnCancel.removeEventListener("click", onCancel);
        if (btnClose) btnClose.removeEventListener("click", onCancel);
        modal.removeEventListener("click", onOverlayClick);
      };

      const onConfirm = (e) => {
        if (e) e.preventDefault();
        cleanup();
        if (config.mode === "prompt") {
          resolve(inputEl ? inputEl.value : "");
        } else if (config.mode === "confirm") {
          resolve(true);
        } else {
          resolve();
        }
      };

      const onCancel = (e) => {
        if (e) e.preventDefault();
        cleanup();
        if (config.mode === "prompt") {
          resolve(null);
        } else if (config.mode === "confirm") {
          resolve(false);
        } else {
          resolve();
        }
      };

      const onOverlayClick = (e) => {
        if (e.target === modal) {
          onCancel(e);
        }
      };

      const onKeyDown = (e) => {
        if (e.key === "Escape") {
          e.preventDefault();
          onCancel(e);
        } else if (e.key === "Enter" && config.mode !== "prompt") {
          e.preventDefault();
          onConfirm(e);
        } else if (e.key === "Enter" && config.mode === "prompt" && document.activeElement === inputEl) {
          e.preventDefault();
          onConfirm(e);
        }
      };

      if (btnConfirm) btnConfirm.addEventListener("click", onConfirm);
      if (btnCancel) btnCancel.addEventListener("click", onCancel);
      if (btnClose) btnClose.addEventListener("click", onCancel);
      modal.addEventListener("click", onOverlayClick);
      document.addEventListener("keydown", onKeyDown);

      modal.classList.remove("hidden");

      setTimeout(() => {
        if (config.mode === "prompt" && inputEl) {
          inputEl.focus();
          inputEl.select();
        } else if (config.isDanger && btnCancel) {
          btnCancel.focus();
        } else if (btnConfirm) {
          btnConfirm.focus();
        }
      }, 50);
    });
  }
}

// Arranque de la aplicación cuando el DOM esté listo
document.addEventListener("DOMContentLoaded", () => {
  new MeshCoreApp();
});
