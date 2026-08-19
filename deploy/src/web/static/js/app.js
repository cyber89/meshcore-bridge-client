/**
 * Función de sanitización XSS estricta para escape en el DOM.
 * @param {string} str Cadena a sanitizar
 * @returns {string} Cadena sanitizada
 */
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

/**
 * Utilidad de debouncing para optimizar inputs de búsqueda en tiempo real.
 */
function debounce(fn, waitMs = 150) {
  let timer = null;
  return function(...args) {
    if (timer) clearTimeout(timer);
    timer = setTimeout(() => {
      fn.apply(this, args);
    }, waitMs);
  };
}

// Límites de capacidad en RAM para ring-buffers
const MAX_RAW_PACKETS = 200;
const MAX_SYSTEM_LOGS = 300;
const MAX_FEED_MESSAGES = 100;

class MeshCoreStationApp {
  constructor() {
    this.ws = null;
    this.wsReconnectTimer = null;
    this.wsReconnectInterval = 3000;
    this.activeChannelIdx = 0;
    this.activeDmTarget = null;
    this.activeDmName = null;
    this.snifferActive = false;
    this.map = null;
    this.mapMarkers = new Map();
    this.knownNodes = new Map();
    this.rawPackets = [];
    this.systemLogs = [];
    this.logsScrollPaused = false;
    this.isDebugMode = false;
    this.cmdPaletteOpen = false;

    // Almacén aislado de mensajes por canal y DM
    this.channelFeeds = new Map(); // "ch_0", "ch_1", "dm_publickey"
    this.channelsList = [];
    this.conversationsWithMessages = new Set();

    this.initElements();
    this.initTheme();
    this.initNavigation();
    this.initCommandPalette();
    this.initChannelAndContactModals();
    this.initRepeaterDashboard();
    this.initSniffer();
    this.initAnalytics();
    this.initHomeAssistant();
    this.initPreflight();
    this.initSettingsDashboard();
    this.initLogsConsole();
    this.initChat();
    this.initWebSocket();
    this.initLeafletMap();
    this.fetchInitialData();

    // Exponer funciones globales para compatibilidad y tests E2E
    window.setDmTarget = (pubkey, name) => this.setDmTarget(pubkey, name);
    window.switchChannel = (idx) => this.switchChannel(idx);
  }

  escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  showToast(message, type = "info", durationMs = 3500) {
    let container = document.getElementById("appToastContainer");
    if (!container) {
      container = document.createElement("div");
      container.id = "appToastContainer";
      container.className = "toast-container";
      document.body.appendChild(container);
    }

    const toast = document.createElement("div");
    toast.className = `toast-item toast-${type}`;
    toast.textContent = message;

    container.appendChild(toast);

    setTimeout(() => {
      toast.classList.add("toast-fade-out");
      setTimeout(() => toast.remove(), 300);
    }, durationMs);
  }

  initElements() {
    this.dom = {
      wsStatus: document.getElementById("wsStatus"),
      headerNodeCount: document.getElementById("headerNodeCount"),
      headerRxCount: document.getElementById("headerRxCount"),
      headerTxCount: document.getElementById("headerTxCount"),
      headerErrorRate: document.getElementById("headerErrorRate"),
      headerQueueDepth: document.getElementById("headerQueueDepth"),
      themeToggleBtn: document.getElementById("themeToggleBtn"),
      chatMessageFeed: document.getElementById("chatMessageFeed"),
      chatInputForm: document.getElementById("chatInputForm"),
      chatInputText: document.getElementById("chatInputText"),
      chatActiveTitle: document.getElementById("chatActiveTitle"),
      chatActiveSub: document.getElementById("chatActiveSub"),
      chatSecurityChip: document.getElementById("chatSecurityChip"),
      channelListUi: document.getElementById("channelListUi"),
      dmListUi: document.getElementById("dmListUi"),
      dmCountBadge: document.getElementById("dmCountBadge"),
      clearChatBtn: document.getElementById("clearChatBtn"),
      btnAddChannel: document.getElementById("btnAddChannel"),
      btnImportData: document.getElementById("btnImportData"),
      btnAddContact: document.getElementById("btnAddContact"),
      btnShareTargetQr: document.getElementById("btnShareTargetQr"),
      btnToggleChannelsMobile: document.getElementById("btnToggleChannelsMobile"),
      sidebarChannelList: document.getElementById("sidebarChannelList"),

      createChannelModal: document.getElementById("createChannelModal"),
      createChannelForm: document.getElementById("createChannelForm"),
      chModalIndex: document.getElementById("chModalIndex"),
      chModalName: document.getElementById("chModalName"),
      chModalPsk: document.getElementById("chModalPsk"),
      btnGenRandomPsk: document.getElementById("btnGenRandomPsk"),
      btnCloseCreateChannelModal: document.getElementById("btnCloseCreateChannelModal"),
      btnCancelCreateChannel: document.getElementById("btnCancelCreateChannel"),

      createContactModal: document.getElementById("createContactModal"),
      createContactForm: document.getElementById("createContactForm"),
      contactModalPubKey: document.getElementById("contactModalPubKey"),
      contactModalName: document.getElementById("contactModalName"),
      contactModalRole: document.getElementById("contactModalRole"),
      btnCloseCreateContactModal: document.getElementById("btnCloseCreateContactModal"),
      btnCancelCreateContact: document.getElementById("btnCancelCreateContact"),

      qrShareModal: document.getElementById("qrShareModal"),
      qrShareCanvas: document.getElementById("qrShareCanvas"),
      qrShareTitle: document.getElementById("qrShareTitle"),
      qrShareDesc: document.getElementById("qrShareDesc"),
      qrShareUri: document.getElementById("qrShareUri"),
      qrShareJson: document.getElementById("qrShareJson"),
      btnCopyQrUri: document.getElementById("btnCopyQrUri"),
      btnDownloadQrJson: document.getElementById("btnDownloadQrJson"),
      btnCloseQrShareModal: document.getElementById("btnCloseQrShareModal"),
      btnCloseQrModalAction: document.getElementById("btnCloseQrModalAction"),

      importModal: document.getElementById("importModal"),
      importForm: document.getElementById("importForm"),
      importPayloadInput: document.getElementById("importPayloadInput"),
      btnCloseImportModal: document.getElementById("btnCloseImportModal"),
      btnCancelImport: document.getElementById("btnCancelImport"),

      activeRepeaterSelect: document.getElementById("activeRepeaterSelect"),
      repeaterTerminalForm: document.getElementById("repeaterTerminalForm"),
      repeaterTerminalInput: document.getElementById("repeaterTerminalInput"),
      repeaterTerminalOutput: document.getElementById("repeaterTerminalOutput"),
      btnToggleSniffer: document.getElementById("btnToggleSniffer"),
      btnClearSniffer: document.getElementById("btnClearSniffer"),
      snifferTableBody: document.getElementById("snifferTableBody"),
      snifferFilterOpcode: document.getElementById("snifferFilterOpcode"),
      snifferSearch: document.getElementById("snifferSearch"),
      btnPublishHaDiscovery: document.getElementById("btnPublishHaDiscovery"),
      haStatusBadge: document.getElementById("haStatusBadge"),
      haDiscoveredCount: document.getElementById("haDiscoveredCount"),
      btnRunPreflight: document.getElementById("btnRunPreflight"),
      nodesGridUi: document.getElementById("nodesGridUi"),
      nodesUnifiedGridUi: document.getElementById("nodesUnifiedGridUi"),
      nodesSearchInput: document.getElementById("nodesSearchInput"),
      btnRefreshAllNodes: document.getElementById("btnRefreshAllNodes"),
      repeaterAdminModal: document.getElementById("repeaterAdminModal"),
      adminModalNodeName: document.getElementById("adminModalNodeName"),
      adminModalNodePk: document.getElementById("adminModalNodePk"),
      adminModalNodePkDisplay: document.getElementById("adminModalNodePkDisplay"),
      adminModalPassword: document.getElementById("adminModalPassword"),
      btnModalAuthTest: document.getElementById("btnModalAuthTest"),
      adminModalAuthStatus: document.getElementById("adminModalAuthStatus"),
      btnModalActionReboot: document.getElementById("btnModalActionReboot"),
      btnModalActionClearStats: document.getElementById("btnModalActionClearStats"),
      btnModalActionAdvert: document.getElementById("btnModalActionAdvert"),
      btnModalActionClock: document.getElementById("btnModalActionClock"),
      btnCloseRepeaterAdminModal: document.getElementById("btnCloseRepeaterAdminModal"),
      contactsGridUi: document.getElementById("contactsGridUi"),
      btnHeaderAddContact: document.getElementById("btnHeaderAddContact"),
      contactsSearchInput: document.getElementById("contactsSearchInput"),
      btnRefreshNodes: document.getElementById("btnRefreshNodes"),
      systemLogsFeed: document.getElementById("systemLogsFeed"),
      btnToggleDebugMode: document.getElementById("btnToggleDebugMode"),
      btnQuickDiag: document.getElementById("btnQuickDiag"),
      btnCopyAIDiag: document.getElementById("btnCopyAIDiag"),
      btnDownloadRawLogs: document.getElementById("btnDownloadRawLogs"),
      btnExportDiag: document.getElementById("btnExportDiag"),
      btnClearLogs: document.getElementById("btnClearLogs"),
      btnPauseLogsScroll: document.getElementById("btnPauseLogsScroll"),
      logLevelFilter: document.getElementById("logLevelFilter"),
      logSearchInput: document.getElementById("logSearchInput"),
      quickDiagPanel: document.getElementById("quickDiagPanel"),
      quickDiagBody: document.getElementById("quickDiagBody"),
      btnCloseQuickDiag: document.getElementById("btnCloseQuickDiag"),
      chipSerialHealth: document.getElementById("chipSerialHealth"),
      chipMqttHealth: document.getElementById("chipMqttHealth"),
      chipDbHealth: document.getElementById("chipDbHealth"),
      chipTxHealth: document.getElementById("chipTxHealth"),
      chipErrorsCount: document.getElementById("chipErrorsCount"),
      localNodeConfigForm: document.getElementById("localNodeConfigForm"),
      localNodeName: document.getElementById("localNodeName"),
      localNodePubkey: document.getElementById("localNodePubkey"),
      localTxPower: document.getElementById("localTxPower"),
      localTxPowerVal: document.getElementById("localTxPowerVal"),
      localFreq: document.getElementById("localFreq"),
      localSf: document.getElementById("localSf"),
      localBw: document.getElementById("localBw"),
      localHopLimit: document.getElementById("localHopLimit"),
      localTelemetryInterval: document.getElementById("localTelemetryInterval"),
      btnSaveLocalConfig: document.getElementById("btnSaveLocalConfig"),
      btnRebootLocalNode: document.getElementById("btnRebootLocalNode"),
      localNodeRoleBadge: document.getElementById("localNodeRoleBadge"),
      remoteRepeaterConfigForm: document.getElementById("remoteRepeaterConfigForm"),
      btnApplyRemoteConfig: document.getElementById("btnApplyRemoteConfig"),
      remoteTargetNodeSelect: document.getElementById("remoteTargetNodeSelect"),
      remoteTargetNodeManual: document.getElementById("remoteTargetNodeManual"),
      remoteAdminPassword: document.getElementById("remoteAdminPassword"),
      btnTestRemoteLogin: document.getElementById("btnTestRemoteLogin"),
      remoteRepeaterName: document.getElementById("remoteRepeaterName"),
      remoteTxPower: document.getElementById("remoteTxPower"),
      remoteRepeatMode: document.getElementById("remoteRepeatMode"),
      remoteHopLimit: document.getElementById("remoteHopLimit"),
      remoteNewAdminPassword: document.getElementById("remoteNewAdminPassword"),
      btnApplyRemoteConfig: document.getElementById("btnApplyRemoteConfig"),
      btnRemoteReboot: document.getElementById("btnRemoteReboot"),
      btnRemoteClearStats: document.getElementById("btnRemoteClearStats"),
      btnRemoteDiscover: document.getElementById("btnRemoteDiscover"),
      remoteResponseOutput: document.getElementById("remoteResponseOutput"),
      btnClearRemoteResponse: document.getElementById("btnClearRemoteResponse"),
      commandPaletteModal: document.getElementById("commandPaletteModal"),
      btnCommandPalette: document.getElementById("btnCommandPalette"),
      cmdPaletteInput: document.getElementById("cmdPaletteInput"),
      cmdPaletteResults: document.getElementById("cmdPaletteResults"),
      packetDetailModal: document.getElementById("packetDetailModal"),
      btnClosePacketModal: document.getElementById("btnClosePacketModal"),
      packetModalBody: document.getElementById("packetModalBody"),
    };
  }

  initTheme() {
    const savedTheme = localStorage.getItem("meshcore_theme") || "dark";
    if (savedTheme === "light") {
      document.body.classList.remove("dark-theme");
      document.body.classList.add("light-theme");
    }
    this.dom.themeToggleBtn.addEventListener("click", () => {
      const isDark = document.body.classList.contains("dark-theme");
      if (isDark) {
        document.body.classList.remove("dark-theme");
        document.body.classList.add("light-theme");
        localStorage.setItem("meshcore_theme", "light");
      } else {
        document.body.classList.remove("light-theme");
        document.body.classList.add("dark-theme");
        localStorage.setItem("meshcore_theme", "dark");
      }
    });
  }

  initNavigation() {
    document.querySelectorAll(".nav-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".nav-btn").forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
          b.tabIndex = -1;
        });
        document.querySelectorAll(".tab-pane").forEach((p) => p.classList.remove("active"));

        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        btn.tabIndex = 0;

        const targetTabId = btn.getAttribute("data-tab");
        const targetPane = document.getElementById(targetTabId);
        if (targetPane) {
          targetPane.classList.add("active");
          if (targetTabId === "tab-map") {
            if (!this.map) {
              this.initLeafletMap();
            }
            setTimeout(() => {
              if (this.map) {
                this.map.invalidateSize();
                if (this.mapMarkers && this.mapMarkers.size > 0) {
                  const bounds = Array.from(this.mapMarkers.values()).map((m) => m.getLatLng());
                  if (bounds.length > 0) {
                    try {
                      this.map.fitBounds(bounds, { padding: [50, 50], maxZoom: 14 });
                    } catch (_) {}
                  }
                }
              }
            }, 100);
            setTimeout(() => {
              if (this.map) this.map.invalidateSize();
            }, 400);
          } else if (targetTabId === "tab-analytics") {
            this.fetchAnalytics();
          } else if (targetTabId === "tab-logs") {
            this.fetchSystemLogs();
            this.fetchSubsystemsHealth();
          } else if (targetTabId === "tab-settings") {
            this.fetchLocalNodeConfig();
          }
        }
      });
    });
  }

  initCommandPalette() {
    const openModal = () => {
      this.dom.commandPaletteModal.classList.remove("hidden");
      this.dom.cmdPaletteInput.value = "";
      this.dom.cmdPaletteInput.focus();
      this.cmdPaletteOpen = true;
    };
    const closeModal = () => {
      this.dom.commandPaletteModal.classList.add("hidden");
      this.cmdPaletteOpen = false;
    };

    this.dom.btnCommandPalette.addEventListener("click", openModal);
    this.dom.commandPaletteModal.addEventListener("click", (e) => {
      if (e.target === this.dom.commandPaletteModal) closeModal();
    });

    document.addEventListener("keydown", (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (this.cmdPaletteOpen) closeModal();
        else openModal();
      }
      if (e.key === "Escape" && this.cmdPaletteOpen) {
        closeModal();
      }
    });

    this.dom.cmdPaletteResults.querySelectorAll(".cmd-item").forEach((item) => {
      item.addEventListener("click", () => {
        const action = item.getAttribute("data-action");
        closeModal();
        if (action.startsWith("tab-")) {
          const navBtn = document.querySelector(`.nav-btn[data-tab="${action}"]`);
          if (navBtn) navBtn.click();
        } else if (action === "action-advert") {
          this.executeAdminCommand("advert", {});
        } else if (action === "action-ha") {
          this.publishHomeAssistantDiscovery();
        } else if (action === "action-diag") {
          const navBtn = document.querySelector('.nav-btn[data-tab="tab-logs"]');
          if (navBtn) navBtn.click();
          this.runQuickDiagnostic();
        } else if (action === "action-debug-toggle") {
          this.toggleDebugMode();
        } else if (action === "action-export-diag") {
          this.exportDiagnosticReport();
        }
      });
    });
  }

  initChannelAndContactModals() {
    // 1. Mobile Channel Drawer Toggle
    if (this.dom.btnToggleChannelsMobile && this.dom.sidebarChannelList) {
      this.dom.btnToggleChannelsMobile.addEventListener("click", () => {
        this.dom.sidebarChannelList.classList.toggle("mobile-open");
      });
    }

    // 2. Crear Canal Modal
    const openCreateChannel = () => {
      if (!this.dom.createChannelModal) return;
      this.dom.createChannelModal.classList.remove("hidden");
      this.dom.chModalName.value = "";
      this.dom.chModalPsk.value = this.generateRandomHex(32);
      this.dom.chModalName.focus();
    };
    const closeCreateChannel = () => {
      if (this.dom.createChannelModal) this.dom.createChannelModal.classList.add("hidden");
    };

    if (this.dom.btnAddChannel) this.dom.btnAddChannel.addEventListener("click", openCreateChannel);
    if (this.dom.btnCloseCreateChannelModal) this.dom.btnCloseCreateChannelModal.addEventListener("click", closeCreateChannel);
    if (this.dom.btnCancelCreateChannel) this.dom.btnCancelCreateChannel.addEventListener("click", closeCreateChannel);

    if (this.dom.btnGenRandomPsk) {
      this.dom.btnGenRandomPsk.addEventListener("click", () => {
        this.dom.chModalPsk.value = this.generateRandomHex(32);
      });
    }

    if (this.dom.createChannelForm) {
      this.dom.createChannelForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const index = parseInt(this.dom.chModalIndex.value, 10);
        const name = this.dom.chModalName.value.trim();
        const psk = this.dom.chModalPsk.value.trim();
        if (!name) return;

        try {
          const res = await fetch("/api/channels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index, name, psk }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            closeCreateChannel();
            await this.fetchChannels();
            this.switchChannel(index);
            this.showToast(`✅ Canal ${index} (${name}) guardado y sincronizado`, "success");
          } else {
            alert(`Error guardando canal: ${data.message || "Fallo desconocido"}`);
          }
        } catch (err) {
          alert(`Error de red al guardar canal: ${err.message}`);
        }
      });
    }

    // 3. Crear Contacto Modal
    const openCreateContact = () => {
      if (!this.dom.createContactModal) return;
      this.dom.createContactModal.classList.remove("hidden");
      this.dom.contactModalPubKey.value = "";
      this.dom.contactModalName.value = "";
      this.dom.contactModalPubKey.focus();
    };
    const closeCreateContact = () => {
      if (this.dom.createContactModal) this.dom.createContactModal.classList.add("hidden");
    };

    if (this.dom.btnAddContact) this.dom.btnAddContact.addEventListener("click", openCreateContact);
    if (this.dom.btnHeaderAddContact) this.dom.btnHeaderAddContact.addEventListener("click", openCreateContact);
    if (this.dom.btnCloseCreateContactModal) this.dom.btnCloseCreateContactModal.addEventListener("click", closeCreateContact);
    if (this.dom.btnCancelCreateContact) this.dom.btnCancelCreateContact.addEventListener("click", closeCreateContact);

    if (this.dom.contactsSearchInput) {
      this.dom.contactsSearchInput.addEventListener(
        "input",
        debounce((e) => {
          this.filterContactsGrid(e.target.value);
        }, 150)
      );
    }

    if (this.dom.createContactForm) {
      this.dom.createContactForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const pubkey = this.dom.contactModalPubKey.value.trim();
        const name = this.dom.contactModalName.value.trim();
        const role = this.dom.contactModalRole ? this.dom.contactModalRole.value : "CLIENT";
        if (!pubkey) return;

        try {
          const res = await fetch("/api/contacts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ public_key: pubkey, name: name, alias: name, role: role }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            closeCreateContact();
            await this.fetchNodes();
            this.setDmTarget(pubkey, name || pubkey);
            this.showToast(`✅ Contacto ${name || pubkey.slice(0, 8)} agregado`, "success");
          } else {
            alert(`Error agregando contacto: ${data.message || "Fallo desconocido"}`);
          }
        } catch (err) {
          alert(`Error de red al agregar contacto: ${err.message}`);
        }
      });
    }

    // 3.1 Filtros y Búsqueda de Nodos (Directorio Unificado)
    document.querySelectorAll(".nodes-filter-pills .filter-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".nodes-filter-pills .filter-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        this.activeNodesFilter = pill.getAttribute("data-filter") || "all";
        this.filterNodesGrid();
      });
    });

    if (this.dom.nodesSearchInput) {
      this.dom.nodesSearchInput.addEventListener(
        "input",
        debounce(() => {
          this.filterNodesGrid();
        }, 150)
      );
    }



    if (this.dom.btnCloseRepeaterAdminModal) {
      this.dom.btnCloseRepeaterAdminModal.addEventListener("click", () => {
        if (this.dom.repeaterAdminModal) this.dom.repeaterAdminModal.classList.add("hidden");
      });
    }

    if (this.dom.repeaterAdminModal) {
      this.dom.repeaterAdminModal.addEventListener("click", (e) => {
        if (e.target === this.dom.repeaterAdminModal) {
          this.dom.repeaterAdminModal.classList.add("hidden");
        }
      });
    }

    // 4. Visor QR y Exportación
    if (this.dom.btnShareTargetQr) {
      this.dom.btnShareTargetQr.addEventListener("click", () => {
        this.openShareActiveTargetQr();
      });
    }

    if (this.dom.btnCloseQrShareModal) {
      this.dom.btnCloseQrShareModal.addEventListener("click", () => this.closeQrModal());
    }
    if (this.dom.btnCloseQrModalAction) {
      this.dom.btnCloseQrModalAction.addEventListener("click", () => this.closeQrModal());
    }
    if (this.dom.btnCopyQrUri) {
      this.dom.btnCopyQrUri.addEventListener("click", () => {
        if (this.dom.qrShareUri) {
          navigator.clipboard.writeText(this.dom.qrShareUri.value);
          this.showToast("📋 Enlace URI copiado al portapapeles", "success");
        }
      });
    }
    if (this.dom.btnDownloadQrJson) {
      this.dom.btnDownloadQrJson.addEventListener("click", () => {
        if (this.dom.qrShareJson) {
          const blob = new Blob([this.dom.qrShareJson.value], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `meshcore_export_${Date.now()}.json`;
          a.click();
          URL.revokeObjectURL(url);
          this.showToast("💾 Archivo JSON descargado", "success");
        }
      });
    }

    // 6. Importador de URI / JSON
    const openImport = () => {
      if (!this.dom.importModal) return;
      this.dom.importModal.classList.remove("hidden");
      this.dom.importPayloadInput.value = "";
      this.dom.importPayloadInput.focus();
    };
    const closeImport = () => {
      if (this.dom.importModal) this.dom.importModal.classList.add("hidden");
    };

    if (this.dom.btnImportData) this.dom.btnImportData.addEventListener("click", openImport);
    if (this.dom.btnCloseImportModal) this.dom.btnCloseImportModal.addEventListener("click", closeImport);
    if (this.dom.btnCancelImport) this.dom.btnCancelImport.addEventListener("click", closeImport);

    if (this.dom.importForm) {
      this.dom.importForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const raw = this.dom.importPayloadInput.value.trim();
        if (!raw) return;
        await this.processImportPayload(raw);
        closeImport();
      });
    }
  }

  generateRandomHex(len) {
    const chars = "0123456789ABCDEF";
    let res = "";
    for (let i = 0; i < len; i++) {
      res += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return res;
  }

  openShareActiveTargetQr() {
    if (this.activeDmTarget) {
      // Compartir Contacto DM
      const node = this.knownNodes.get(this.activeDmTarget) || {};
      const role = node.role || "CLIENT";
      const payload = {
        type: "contact",
        public_key: this.activeDmTarget,
        name: this.activeDmName || this.activeDmTarget,
        role: role,
      };
      const uri = `meshcore://contact?pubkey=${encodeURIComponent(payload.public_key)}&name=${encodeURIComponent(payload.name)}&role=${encodeURIComponent(role)}`;
      this.renderQrModal(`👥 Contacto: ${payload.name}`, uri, payload);
    } else {
      // Compartir Canal Activo
      const ch = (this.channelsList || []).find((c) => c.index === this.activeChannelIdx) || {
        index: this.activeChannelIdx,
        name: this.activeChannelIdx === 0 ? "Public / Broadcast" : `Canal ${this.activeChannelIdx}`,
        psk: "",
        is_public: this.activeChannelIdx === 0,
      };
      const payload = {
        type: "channel",
        index: ch.index,
        name: ch.name,
        psk: ch.psk || "",
      };
      const uri = `meshcore://channel?idx=${ch.index}&name=${encodeURIComponent(ch.name)}&psk=${encodeURIComponent(ch.psk || "")}`;
      this.renderQrModal(`📻 Canal ${ch.index}: ${ch.name}`, uri, payload);
    }
  }

  renderQrModal(title, uri, payloadObj) {
    if (!this.dom.qrShareModal) return;
    this.dom.qrShareTitle.textContent = title;
    this.dom.qrShareUri.value = uri;
    this.dom.qrShareJson.value = JSON.stringify(payloadObj, null, 2);

    if (window.QRCodeGenerator && this.dom.qrShareCanvas) {
      try {
        window.QRCodeGenerator.renderToCanvas(this.dom.qrShareCanvas, uri, { size: 160, margin: 2 });
      } catch (err) {
        console.warn("Fallo dibujando QR en Canvas:", err);
      }
    }
    this.dom.qrShareModal.classList.remove("hidden");
  }

  closeQrModal() {
    if (this.dom.qrShareModal) this.dom.qrShareModal.classList.add("hidden");
  }

  async processImportPayload(text) {
    try {
      if (text.startsWith("{")) {
        const obj = JSON.parse(text);
        if (obj.type === "channel" || obj.index !== undefined) {
          const res = await fetch("/api/channels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(obj),
          });
          const data = await res.json();
          if (data.status === "ok") {
            await this.fetchChannels();
            this.switchChannel(obj.index || 0);
            this.showToast(`✅ Canal ${obj.name || obj.index} importado`, "success");
            return;
          }
        } else if (obj.type === "contact" || obj.public_key) {
          const res = await fetch("/api/contacts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(obj),
          });
          const data = await res.json();
          if (data.status === "ok") {
            await this.fetchNodes();
            this.setDmTarget(obj.public_key, obj.name || obj.public_key);
            this.showToast(`✅ Contacto ${obj.name || obj.public_key} importado`, "success");
            return;
          }
        }
      } else if (text.startsWith("meshcore://channel")) {
        const url = new URL(text.replace("meshcore://", "http://fake/"));
        const idx = parseInt(url.searchParams.get("idx") || "1", 10);
        const name = url.searchParams.get("name") || `Canal ${idx}`;
        const psk = url.searchParams.get("psk") || "";
        const res = await fetch("/api/channels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ index: idx, name, psk }),
        });
        const data = await res.json();
        if (data.status === "ok") {
          await this.fetchChannels();
          this.switchChannel(idx);
          this.showToast(`✅ Canal ${name} importado desde URI`, "success");
          return;
        }
      } else if (text.startsWith("meshcore://contact")) {
        const url = new URL(text.replace("meshcore://", "http://fake/"));
        const pk = url.searchParams.get("pubkey") || "";
        const name = url.searchParams.get("name") || pk;
        const role = url.searchParams.get("role") || "CLIENT";
        if (pk) {
          const res = await fetch("/api/contacts", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ public_key: pk, name, role }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            await this.fetchNodes();
            this.setDmTarget(pk, name);
            this.showToast(`✅ Contacto ${name} importado desde URI`, "success");
            return;
          }
        }
      }
      this.showToast("Formato no reconocido. Pega un JSON válido o URI meshcore://...", "error");
    } catch (err) {
      this.showToast(`Error al procesar importación: ${err.message}`, "error");
    }
  }

  async fetchChannels() {
    try {
      const res = await fetch("/api/channels");
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        this.renderChannelsList(data.data);
      }
    } catch (e) {
      console.debug("Error fetching channels:", e);
    }
  }

  async fetchNodes() {
    try {
      const res = await fetch("/api/nodes");
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        this.renderNodesDirectory(data.data);
      }
    } catch (e) {
      console.debug("Error fetching nodes:", e);
    }
  }

  async deleteChannel(index, name) {
    if (index === 0) {
      alert("No se puede eliminar el canal público principal 0.");
      return;
    }
    if (!confirm(`¿Estás seguro de eliminar el Canal ${index} (${name || ''}) del dispositivo?`)) {
      return;
    }

    try {
      const res = await fetch("/api/channels", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ index }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.showToast(`🗑️ Canal ${index} eliminado del dispositivo`, "info");
        if (this.activeChannelIdx === index) {
          this.switchChannel(0);
        }
        await this.fetchChannels();
      } else {
        alert(`Error al eliminar canal: ${data.message || "Fallo desconocido"}`);
      }
    } catch (err) {
      alert(`Error de red al eliminar canal: ${err.message}`);
    }
  }

  async deleteContact(pubkey, name) {
    const displayName = name || pubkey.slice(0, 8);
    if (!confirm(`¿Estás seguro de eliminar a "${displayName}" de la libreta de contactos del dispositivo?`)) {
      return;
    }

    try {
      const res = await fetch("/api/contacts", {
        method: "DELETE",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ public_key: pubkey }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.showToast(`🗑️ Contacto ${displayName} eliminado del dispositivo`, "info");
        const li = this.dom.dmListUi.querySelector(`li[data-pubkey="${pubkey}"]`);
        if (li) li.remove();
        const count = this.dom.dmListUi.querySelectorAll("li.channel-item").length;
        this.dom.dmCountBadge.textContent = count;
        if (this.activeDmTarget === pubkey) {
          this.switchChannel(0);
        }
        await this.fetchNodes();
      } else {
        alert(`Error al eliminar contacto: ${data.message || "Fallo desconocido"}`);
      }
    } catch (err) {
      alert(`Error de red al eliminar contacto: ${err.message}`);
    }
  }

  openRepeaterAdminModal(pubkey, name) {
    this.selectedRepeaterTarget = pubkey;
    const modal = this.dom.repeaterAdminModal || document.getElementById("repeaterAdminModal");
    const nameEl = this.dom.adminModalNodeName || document.getElementById("adminModalNodeName");
    const pkInput = this.dom.adminModalNodePk || document.getElementById("adminModalNodePk");
    const pkDisplay = this.dom.adminModalNodePkDisplay || document.getElementById("adminModalNodePkDisplay");
    const pwdInput = this.dom.adminModalPassword || document.getElementById("adminModalPassword");
    const authStatus = this.dom.adminModalAuthStatus || document.getElementById("adminModalAuthStatus");

    if (nameEl) nameEl.textContent = name || pubkey;
    if (pkInput) pkInput.value = pubkey;
    if (pkDisplay) pkDisplay.textContent = pubkey.length > 14 ? `${pubkey.slice(0, 8)}...${pubkey.slice(-4)}` : pubkey;

    this.repeaterPasswords = this.repeaterPasswords || new Map();
    if (this.repeaterPasswords.has(pubkey) && this.repeaterPasswords.get(pubkey)) {
      if (pwdInput) pwdInput.value = this.repeaterPasswords.get(pubkey);
      if (authStatus) {
        authStatus.className = "auth-status-chip authenticated";
        authStatus.textContent = "🔓 PIN configurado";
      }
    } else {
      if (pwdInput) pwdInput.value = "";
      if (authStatus) {
        authStatus.className = "auth-status-chip";
        authStatus.textContent = "🔒 PIN no ingresado";
      }
    }

    // Buscar nodo en el registro local
    const node = this.knownNodes.get(pubkey) || {};

    // 1. Batería & Voltajes
    const batVal = node.battery_pct !== undefined && node.battery_pct !== null ? node.battery_pct : (node.battery !== undefined ? node.battery : "--");
    const voltVal = node.voltage_v !== undefined && node.voltage_v !== null ? node.voltage_v : (node.voltage !== undefined ? node.voltage : "--");
    const solarVal = node.solar_v !== undefined && node.solar_v !== null ? node.solar_v : "--";

    const batEl = document.getElementById("repBatValue");
    if (batEl) batEl.textContent = batVal !== "--" ? `${batVal}%` : "-- %";
    const voltEl = document.getElementById("repVoltValue");
    if (voltEl) voltEl.textContent = voltVal !== "--" ? `${voltVal} V` : "-- V";
    const solarEl = document.getElementById("repSolarValue");
    if (solarEl) solarEl.textContent = solarVal !== "--" ? `${solarVal} V` : "-- V";

    // 2. Reloj & Uptime
    const clockEl = document.getElementById("repClockValue");
    if (clockEl) clockEl.textContent = node.clock || new Date().toLocaleTimeString();
    const uptimeEl = document.getElementById("repUptimeValue");
    if (uptimeEl) uptimeEl.textContent = node.uptime || "En línea";
    const seenEl = document.getElementById("repLastSeenValue");
    if (seenEl) seenEl.textContent = "Activo en malla LoRa";

    // 3. Airtime & Ruido
    const airtimeEl = document.getElementById("repAirtimeValue");
    if (airtimeEl) airtimeEl.textContent = node.airtime_ms !== undefined ? `${node.airtime_ms} ms` : "-- ms";
    const airtimeDutyEl = document.getElementById("repAirtimeDuty");
    if (airtimeDutyEl) airtimeDutyEl.textContent = node.airtime_ms !== undefined ? `Duty: ${(node.airtime_ms / 36000).toFixed(2)}%` : "Duty Cycle: --%";

    const noiseEl = document.getElementById("repNoiseValue");
    if (noiseEl) noiseEl.textContent = node.noise_floor_dbm !== undefined ? `${node.noise_floor_dbm} dBm` : "-- dBm";

    // 4. Calidad de Señal
    const snrEl = document.getElementById("repSnrValue");
    if (snrEl) snrEl.textContent = `${node.last_snr !== undefined ? node.last_snr : (node.snr !== undefined ? node.snr : 10.0)} dB`;
    const rssiEl = document.getElementById("repRssiValue");
    if (rssiEl) rssiEl.textContent = `RSSI: ${node.last_rssi !== undefined ? node.last_rssi : (node.rssi !== undefined ? node.rssi : -80)} dBm`;

    // 5. Paquetes & Errores
    const pktsTx = node.packets_sent !== undefined ? node.packets_sent : (node.tx_packets || 0);
    const pktsRx = node.packets_recv !== undefined ? node.packets_recv : (node.rx_packets || 0);
    const pktsEl = document.getElementById("repPacketsValue");
    if (pktsEl) pktsEl.textContent = `${pktsTx} TX / ${pktsRx} RX`;

    const errsVal = node.packet_errors !== undefined ? node.packet_errors : (node.error_count || 0);
    const dupsVal = node.duplicate_packets !== undefined ? node.duplicate_packets : 0;
    const pktsErrEl = document.getElementById("repPacketErrorsValue");
    if (pktsErrEl) pktsErrEl.textContent = `Duplicados: ${dupsVal} | Errores: ${errsVal}`;

    // 6. Resumen de parámetros
    const sumFreq = document.getElementById("repSummaryFreq");
    if (sumFreq) sumFreq.textContent = `${node.frequency || node.freq || 915.000} MHz`;
    const sumPower = document.getElementById("repSummaryPower");
    if (sumPower) sumPower.textContent = `${node.tx_power || 20} dBm`;
    const sumModem = document.getElementById("repSummaryModem");
    if (sumModem) sumModem.textContent = `SF${node.spreading_factor || node.sf || 11} / BW${node.bandwidth || node.bw || 250}`;
    const sumRepeat = document.getElementById("repSummaryRepeat");
    if (sumRepeat) sumRepeat.textContent = node.repeat_enabled === false ? "Desactivado" : "Activado";
    const sumQueue = document.getElementById("repSummaryQueue");
    if (sumQueue) sumQueue.textContent = `${node.queue_len || 0} paquetes`;

    const sumPos = document.getElementById("repSummaryPos");
    if (sumPos) {
      if (node.latitude && node.longitude) {
        sumPos.textContent = `${Number(node.latitude).toFixed(4)}, ${Number(node.longitude).toFixed(4)}`;
      } else {
        sumPos.textContent = "No configurada";
      }
    }

    // Llenar formulario de Radio
    const radioFreqInput = document.getElementById("radioFreq");
    if (radioFreqInput) radioFreqInput.value = node.frequency || node.freq || 915.000;
    const radioPowerInput = document.getElementById("radioPower");
    if (radioPowerInput) radioPowerInput.value = node.tx_power || 20;
    const radioHopLimitInput = document.getElementById("radioHopLimit");
    if (radioHopLimitInput) radioHopLimitInput.value = node.hops || node.hop_limit || 3;
    const radioBeaconInput = document.getElementById("radioBeaconInterval");
    if (radioBeaconInput && node.advert_interval) radioBeaconInput.value = node.advert_interval;

    // Llenar formulario de Propietario & Posición
    const ownerNameInput = document.getElementById("repOwnerName");
    if (ownerNameInput) ownerNameInput.value = node.owner_name || node.alias || node.name || "";
    const ownerInfoInput = document.getElementById("repOwnerInfo");
    if (ownerInfoInput) ownerInfoInput.value = node.owner_info || "";
    const posLatInput = document.getElementById("repPosLat");
    if (posLatInput && node.latitude) posLatInput.value = node.latitude;
    const posLonInput = document.getElementById("repPosLon");
    if (posLonInput && node.longitude) posLonInput.value = node.longitude;
    const posAltInput = document.getElementById("repPosAlt");
    if (posAltInput && node.altitude_m) posAltInput.value = node.altitude_m;

    this.refreshNeighborsTable(pubkey);
    if (modal) modal.classList.remove("hidden");
  }

  initRepeaterDashboard() {
    document.querySelectorAll(".repeater-subtabs .subtab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".repeater-subtabs .subtab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".repeater-subpanel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const panelId = btn.getAttribute("data-subtab");
        const panel = document.getElementById(panelId);
        if (panel) panel.classList.add("active");
      });
    });

    // Desplegable de Ayuda de Comandos
    const btnToggleCmdHelp = document.getElementById("btnToggleCmdHelp");
    const btnCloseCmdHelp = document.getElementById("btnCloseCmdHelp");
    const helpDrawer = document.getElementById("terminalHelpDrawer");

    if (btnToggleCmdHelp && helpDrawer) {
      btnToggleCmdHelp.addEventListener("click", () => {
        helpDrawer.classList.toggle("hidden");
      });
    }
    if (btnCloseCmdHelp && helpDrawer) {
      btnCloseCmdHelp.addEventListener("click", () => {
        helpDrawer.classList.add("hidden");
      });
    }

    // Clic en items de ayuda para insertar comando
    document.querySelectorAll(".help-cmd-item").forEach((item) => {
      item.addEventListener("click", () => {
        const cmd = item.getAttribute("data-cmd");
        if (this.dom.repeaterTerminalInput && cmd) {
          this.dom.repeaterTerminalInput.value = cmd;
          this.dom.repeaterTerminalInput.focus();
        }
      });
    });

    // Botón Probar Autenticación en Modal
    if (this.dom.btnModalAuthTest) {
      this.dom.btnModalAuthTest.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        if (!target) {
          alert("Selecciona primero un repetidor.");
          return;
        }
        if (!password) {
          alert("Ingresa la contraseña o PIN de administración del repetidor.");
          return;
        }
        this.appendTerminalLine(`> [TX AUTH] Verificando PIN con repetidor ${target.slice(0, 8)}...`, "term-cmd");
        this.dom.btnModalAuthTest.disabled = true;
        this.dom.btnModalAuthTest.textContent = "🔐 Verificando...";

        try {
          const res = await fetch("/api/repeater/remote/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.repeaterPasswords = this.repeaterPasswords || new Map();
            this.repeaterPasswords.set(target, password);
            if (this.dom.adminModalAuthStatus) {
              this.dom.adminModalAuthStatus.className = "auth-status-chip authenticated";
              this.dom.adminModalAuthStatus.textContent = "🔓 PIN verificado";
            }
            this.appendTerminalLine(`✓ [RX OK] Login transmitido por RF hacia ${target.slice(0, 8)}.`, "term-success");
            this.showToast("🔐 Autenticación enviada al repetidor", "success");
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            this.showToast(`Error de autenticación: ${data.message}`, "error");
          }
        } catch (e) {
          this.appendTerminalLine(`✗ [ERROR] ${e.message}`, "term-error");
        } finally {
          this.dom.btnModalAuthTest.disabled = false;
          this.dom.btnModalAuthTest.textContent = "🔐 Autenticar";
        }
      });
    }

    // 1. Formulario de Parámetros RF
    const radioForm = document.getElementById("repRadioForm");
    if (radioForm) {
      radioForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert("Selecciona primero un repetidor objetivo.");
          return;
        }
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        const freq = parseFloat(document.getElementById("radioFreq").value);
        const region = document.getElementById("radioRegion")?.value || "US915";
        const tx_power = parseInt(document.getElementById("radioPower").value, 10);
        const sf = parseInt(document.getElementById("radioSf").value, 10);
        const bw = parseFloat(document.getElementById("radioBw").value);
        const cr = document.getElementById("radioCr")?.value || "4/5";
        const hop_limit = parseInt(document.getElementById("radioHopLimit").value, 10);
        const repeat = document.getElementById("radioRepeatMode").value === "on";
        const beacon_interval = parseInt(document.getElementById("radioBeaconInterval")?.value || "300", 10);

        const params = { freq, region, tx_power, sf, bw, cr, hop_limit, repeat, beacon_interval };
        this.appendTerminalLine(`> [TX CONFIG] Transmitiendo parámetros RF a ${target.slice(0, 8)} (${freq}MHz, ${tx_power}dBm, SF${sf}, BW${bw}kHz)...`, "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.appendTerminalLine(`✓ [RX OK] Parámetros RF aplicados al repetidor ${target.slice(0, 8)}.`, "term-success");
            this.showToast("📻 Configuración RF transmitida al repetidor", "success");
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            this.showToast(`Error: ${data.message}`, "error");
          }
        } catch (err) {
          this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
        }
      });
    }

    // 2. Formulario de Propietario & Posición
    const ownerPosForm = document.getElementById("repOwnerPosForm");
    if (ownerPosForm) {
      ownerPosForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert("Selecciona primero un repetidor.");
          return;
        }
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        const owner_name = document.getElementById("repOwnerName")?.value.trim() || "";
        const owner_info = document.getElementById("repOwnerInfo")?.value.trim() || "";
        const lat = parseFloat(document.getElementById("repPosLat")?.value || "0");
        const lon = parseFloat(document.getElementById("repPosLon")?.value || "0");
        const alt = parseFloat(document.getElementById("repPosAlt")?.value || "0");
        const fixed = document.getElementById("repPosFixed")?.value === "1";

        const params = { owner_name, owner_info, lat, lon, alt, fixed };
        this.appendTerminalLine(`> [TX OWNER/POS] Configurando propietario '${owner_name}' y posición (${lat}, ${lon}) en ${target.slice(0, 8)}...`, "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.appendTerminalLine(`✓ [RX OK] Información y coordenadas guardadas en repetidor ${target.slice(0, 8)}.`, "term-success");
            this.showToast("📍 Información y posición aplicadas al repetidor", "success");
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            this.showToast(`Error: ${data.message}`, "error");
          }
        } catch (err) {
          this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
        }
      });
    }

    // 3. Formulario de Seguridad & ACL
    const securityForm = document.getElementById("repSecurityForm");
    if (securityForm) {
      securityForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert("Selecciona primero un repetidor.");
          return;
        }
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        const admin_password = document.getElementById("secNewAdminPwd")?.value.trim() || "";
        const guest_password = document.getElementById("secNewGuestPwd")?.value.trim() || "";
        const acl_mode = document.getElementById("secAclMode")?.value || "public";
        const identity_key = document.getElementById("secIdentityKey")?.value.trim() || "";

        const params = { acl_mode };
        if (admin_password) params.admin_password = admin_password;
        if (guest_password) params.guest_password = guest_password;
        if (identity_key) params.identity_key = identity_key;

        this.appendTerminalLine(`> [TX SECURITY] Aplicando parámetros de seguridad y ACL en ${target.slice(0, 8)}...`, "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            if (admin_password) this.repeaterPasswords.set(target, admin_password);
            this.appendTerminalLine(`✓ [RX OK] Parámetros de seguridad actualizados con éxito.`, "term-success");
            this.showToast("🔐 Seguridad actualizada en el repetidor", "success");
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            this.showToast(`Error: ${data.message}`, "error");
          }
        } catch (err) {
          this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
        }
      });
    }

    // Botones de Telemetría y Reloj
    const btnRefreshTelem = document.getElementById("btnRefreshRepeaterTelem");
    if (btnRefreshTelem) {
      btnRefreshTelem.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        this.appendTerminalLine(`> [TX] Solicitando telemetría completa a ${target.slice(0, 8)}...`, "term-cmd");
        this.executeRepeaterCommand(target, "stats-core", {}, password);
        this.executeRepeaterCommand(target, "stats-radio", {}, password);
      });
    }

    const btnSyncClock = document.getElementById("btnSyncRepeaterClock");
    if (btnSyncClock) {
      btnSyncClock.addEventListener("click", () => this.sendModalRepeaterAction("sync_clock"));
    }

    const btnDiscover = document.getElementById("btnDiscoverNeighbors");
    if (btnDiscover) {
      btnDiscover.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert("Selecciona primero un repetidor.");
          return;
        }
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        this.appendTerminalLine(`> [TX] Sondeando vecinos en la malla desde ${target.slice(0, 8)}...`, "term-cmd");
        await this.executeRepeaterCommand(target, "discover.neighbors", {}, password);
        this.refreshNeighborsTable(target);
      });
    }

    // Acciones Rápidas del Modal
    if (this.dom.btnModalActionReboot) {
      this.dom.btnModalActionReboot.addEventListener("click", () => this.sendModalRepeaterAction("reboot"));
    }
    if (this.dom.btnModalActionClearStats) {
      this.dom.btnModalActionClearStats.addEventListener("click", () => this.sendModalRepeaterAction("clear_stats"));
    }
    if (this.dom.btnModalActionAdvert) {
      this.dom.btnModalActionAdvert.addEventListener("click", () => this.sendModalRepeaterAction("advert"));
    }
    if (this.dom.btnModalActionClock) {
      this.dom.btnModalActionClock.addEventListener("click", () => this.sendModalRepeaterAction("sync_clock"));
    }

    const btnModalActionTelem = document.getElementById("btnModalActionTelemetry");
    if (btnModalActionTelem) {
      btnModalActionTelem.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        this.executeRepeaterCommand(target, "telemetry", {}, password);
      });
    }

    const btnModalActionVer = document.getElementById("btnModalActionVersion");
    if (btnModalActionVer) {
      btnModalActionVer.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        this.executeRepeaterCommand(target, "ver", {}, password);
        this.executeRepeaterCommand(target, "board", {}, password);
      });
    }

    document.querySelectorAll(".rep-quick-cmd").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cmd = btn.getAttribute("data-cmd");
        const target = this.selectedRepeaterTarget;
        if (!target) {
          this.appendTerminalLine("⚠️ Selecciona primero un repetidor objetivo.", "term-error");
          return;
        }
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        this.executeRepeaterCommand(target, cmd, {}, password);
      });
    });

    if (this.dom.repeaterTerminalForm) {
      this.dom.repeaterTerminalForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const cmd = this.dom.repeaterTerminalInput ? this.dom.repeaterTerminalInput.value.trim() : "";
        const target = this.selectedRepeaterTarget;
        if (!cmd) return;
        if (!target) {
          this.appendTerminalLine("⚠️ Selecciona primero un repetidor objetivo.", "term-error");
          return;
        }
        if (this.dom.repeaterTerminalInput) this.dom.repeaterTerminalInput.value = "";
        const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
        this.executeRepeaterCommand(target, cmd, {}, password);
      });
    }
  }

  async sendModalRepeaterAction(actionName) {
    const target = this.selectedRepeaterTarget;
    if (!target) {
      alert("Selecciona primero un repetidor.");
      return;
    }
    const password = this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "";
    this.appendTerminalLine(`> [TX ACTION] Ejecutando acción '${actionName}' en ${target.slice(0, 8)}...`, "term-cmd");

    try {
      const res = await fetch("/api/repeater/remote/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: password, action: actionName }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.appendTerminalLine(`✓ [RX OK] Acción '${actionName}' ejecutada con éxito.`, "term-success");
        this.showToast(`✅ Acción '${actionName}' ejecutada`, "success");
      } else {
        this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
        this.showToast(`Error: ${data.message}`, "error");
      }
    } catch (e) {
      this.appendTerminalLine(`✗ [ERROR] ${e.message}`, "term-error");
    }
  }

  onRepeaterSelected() {
    const pubkey = this.dom.activeRepeaterSelect.value;
    if (!pubkey) return;
    const node = this.knownNodes.get(pubkey) || {
      battery: 98,
      solar_v: 5.12,
      snr: 12.4,
      rssi: -65,
      uptime: "142h 30m",
      last_seen: "Ahora",
    };
    const batEl = document.getElementById("repBatteryValue");
    if (batEl) batEl.textContent = `${node.battery || 95}%`;
    const solarEl = document.getElementById("repSolarValue");
    if (solarEl) solarEl.textContent = `${node.solar_v || node.voltage || 4.8} V`;
    const snrEl = document.getElementById("repSnrValue");
    if (snrEl) snrEl.textContent = `${node.snr || 12.0} dB`;
    const rssiEl = document.getElementById("repRssiValue");
    if (rssiEl) rssiEl.textContent = `RSSI: ${node.rssi || -68} dBm`;
    const uptimeEl = document.getElementById("repUptimeValue");
    if (uptimeEl) uptimeEl.textContent = node.uptime || "142h 30m";
    const seenEl = document.getElementById("repLastSeenValue");
    if (seenEl) seenEl.textContent = "Activo en malla LoRa";

    this.refreshNeighborsTable(pubkey);
  }

  refreshNeighborsTable(pubkey) {
    const tbody = document.getElementById("neighborsTableBody");
    if (!tbody) return;
    tbody.innerHTML = "";
    const otherNodes = Array.from(this.knownNodes.values()).filter((n) => n.public_key !== pubkey);
    if (otherNodes.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-center">No hay vecinos registrados aún.</td></tr>';
      return;
    }
    for (const n of otherNodes) {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><code class="font-mono">${this.escapeHtml(n.public_key.slice(0, 8))}...</code></td>
        <td><strong>${this.escapeHtml(n.name || n.alias || "Nodo")}</strong></td>
        <td><span class="badge-pill badge-success">${n.snr || 10.5} dB</span></td>
        <td>${n.hops || 1} salto(s)</td>
        <td>${new Date().toLocaleTimeString()}</td>
        <td><button class="btn-xs btn-outline btn-rep-dm" data-pk="${n.public_key}" data-name="${this.escapeHtml(n.name || n.alias)}">💬 DM</button></td>
      `;
      tr.querySelector(".btn-rep-dm").addEventListener("click", () => {
        const navBtn = document.querySelector('.nav-btn[data-tab="tab-chat"]');
        if (navBtn) navBtn.click();
        this.addDmContact(n.public_key, n.name || n.alias);
        this.setDmTarget(n.public_key, n.name || n.alias);
      });
      tbody.appendChild(tr);
    }
  }

  appendTerminalLine(text, cssClass = "term-info") {
    const line = document.createElement("div");
    line.className = `term-line ${cssClass}`;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
    this.dom.repeaterTerminalOutput.appendChild(line);
    this.dom.repeaterTerminalOutput.scrollTop = this.dom.repeaterTerminalOutput.scrollHeight;
  }

  async executeRepeaterCommand(target, action, params = {}, password = "") {
    const pwd = password || (this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "");
    this.appendTerminalLine(`> Enviando a ${target.slice(0, 8)}: ${action}`, "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, action, params, password: pwd }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.appendTerminalLine(`✓ Respuesta: ${JSON.stringify(data.data || data.result || data)}`, "term-success");
      } else {
        this.appendTerminalLine(`✗ Error: ${data.message || data.error}`, "term-error");
      }
    } catch (err) {
      this.appendTerminalLine(`✗ Error de red: ${err.message}`, "term-error");
    }
  }

  async executeAdminCommand(action, params = {}) {
    try {
      const res = await fetch("/api/admin/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action, params }),
      });
      const data = await res.json();
      return data;
    } catch (err) {
      console.error("Error en comando admin:", err);
    }
  }

  initSniffer() {
    this.snifferPaused = false;
    this.snifferFilterOpcode = "all";
    this.snifferSearchQuery = "";
    this.currentInspectedPacket = null;

    if (this.dom.btnToggleSniffer) {
      this.dom.btnToggleSniffer.addEventListener("click", async () => {
        this.snifferActive = !this.snifferActive;
        const statusEl = document.getElementById("snifferStatusText");

        if (this.snifferActive) {
          this.dom.btnToggleSniffer.textContent = "⏹ Detener Sniffer";
          this.dom.btnToggleSniffer.className = "btn-secondary btn-sniffer-active";
          if (statusEl) {
            statusEl.textContent = "Capturando (0x88)";
            statusEl.className = "stat-value text-success";
          }
          this.showToast("🕵️ Sniffer de tramas LoRa activado", "info");
        } else {
          this.dom.btnToggleSniffer.textContent = "▶ Iniciar Sniffer (0x88)";
          this.dom.btnToggleSniffer.className = "btn-primary";
          if (statusEl) {
            statusEl.textContent = "Detenido";
            statusEl.className = "stat-value text-muted";
          }
          this.showToast("⏹ Sniffer detenido", "info");
        }

        try {
          await fetch("/api/sniffer/control", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: this.snifferActive ? "start" : "stop" }),
          });
        } catch (err) {
          console.warn("Fallo controlando el sniffer:", err);
        }
      });
    }

    if (this.dom.btnClearSniffer) {
      this.dom.btnClearSniffer.addEventListener("click", () => {
        this.rawPackets = [];
        this.dom.snifferTableBody.innerHTML = '<tr><td colspan="8" class="text-center">Historial limpiado.</td></tr>';
        this.updateSnifferStats();
        this.showToast("🧹 Historial del sniffer vaciado", "info");
      });
    }

    const btnExport = document.getElementById("btnExportSniffer");
    if (btnExport) {
      btnExport.addEventListener("click", () => {
        if (!this.rawPackets || this.rawPackets.length === 0) {
          alert("No hay tramas capturadas para exportar.");
          return;
        }
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(this.rawPackets, null, 2));
        const a = document.createElement("a");
        a.setAttribute("href", dataStr);
        a.setAttribute("download", `meshcore_sniffer_capture_${new Date().toISOString().replace(/[:.]/g, "-")}.json`);
        document.body.appendChild(a);
        a.click();
        a.remove();
        this.showToast("💾 Captura de tramas exportada a JSON", "success");
      });
    }

    const btnToggleScroll = document.getElementById("btnToggleSnifferScroll");
    if (btnToggleScroll) {
      btnToggleScroll.addEventListener("click", () => {
        this.snifferPaused = !this.snifferPaused;
        btnToggleScroll.textContent = this.snifferPaused ? "▶" : "⏸";
        btnToggleScroll.title = this.snifferPaused ? "Reanudar desplazamiento automático" : "Pausar desplazamiento automático";
        this.showToast(this.snifferPaused ? "⏸ Auto-scroll del sniffer pausado" : "▶ Auto-scroll reanudado", "info");
      });
    }

    // Filtros de Opcode
    document.querySelectorAll(".sniffer-filter-pills .filter-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".sniffer-filter-pills .filter-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        this.snifferFilterOpcode = pill.getAttribute("data-opcode") || "all";
        this.filterSnifferTable();
      });
    });

    const searchInput = document.getElementById("snifferSearch");
    if (searchInput) {
      searchInput.addEventListener(
        "input",
        debounce((e) => {
          this.snifferSearchQuery = (e.target.value || "").trim().toLowerCase();
          this.filterSnifferTable();
        }, 150)
      );
    }

    // Modal de Paquete
    if (this.dom.btnClosePacketModal) {
      this.dom.btnClosePacketModal.addEventListener("click", () => {
        this.dom.packetDetailModal.classList.add("hidden");
      });
    }

    const btnCloseFooter = document.getElementById("btnClosePacketModalFooter");
    if (btnCloseFooter) {
      btnCloseFooter.addEventListener("click", () => {
        this.dom.packetDetailModal.classList.add("hidden");
      });
    }

    const btnCopyHex = document.getElementById("btnCopyPacketHex");
    if (btnCopyHex) {
      btnCopyHex.addEventListener("click", () => {
        if (this.currentInspectedPacket) {
          const hex = this.currentInspectedPacket.raw_hex || this.currentInspectedPacket.raw || "";
          navigator.clipboard.writeText(hex);
          this.showToast("📋 Hexadecimal copiado al portapapeles", "success");
        }
      });
    }

    const btnCopyJson = document.getElementById("btnCopyPacketJson");
    if (btnCopyJson) {
      btnCopyJson.addEventListener("click", () => {
        if (this.currentInspectedPacket) {
          navigator.clipboard.writeText(JSON.stringify(this.currentInspectedPacket, null, 2));
          this.showToast("📋 JSON del paquete copiado al portapapeles", "success");
        }
      });
    }

    this.dom.packetDetailModal.addEventListener("click", (e) => {
      if (e.target === this.dom.packetDetailModal) {
        this.dom.packetDetailModal.classList.add("hidden");
      }
    });
  }

  updateSnifferStats() {
    const totalEl = document.getElementById("snifferTotalPackets");
    const countAllEl = document.getElementById("snifferCountAll");
    const avgRssiEl = document.getElementById("snifferAvgRssi");
    const lastOpcodeEl = document.getElementById("snifferLastOpcode");

    const total = this.rawPackets.length;
    if (totalEl) totalEl.textContent = String(total);
    if (countAllEl) countAllEl.textContent = String(total);

    if (total > 0) {
      const lastPkt = this.rawPackets[0];
      if (lastOpcodeEl) {
        lastOpcodeEl.textContent = lastPkt.opcode || lastPkt.payload_type || "DATA";
      }
      const rssiList = this.rawPackets
        .map((p) => parseFloat(p.metrics?.rssi || p.rssi || p.RSSI))
        .filter((v) => !isNaN(v) && v !== 0);

      if (rssiList.length > 0 && avgRssiEl) {
        const avg = (rssiList.reduce((a, b) => a + b, 0) / rssiList.length).toFixed(1);
        avgRssiEl.textContent = `${avg} dBm`;
      }
    }
  }

  filterSnifferTable() {
    const rows = this.dom.snifferTableBody.querySelectorAll("tr[data-opcode]");
    rows.forEach((tr) => {
      const op = tr.getAttribute("data-opcode") || "";
      const searchData = tr.getAttribute("data-search") || "";

      let matchOpcode = this.snifferFilterOpcode === "all" || op.toUpperCase().includes(this.snifferFilterOpcode.toUpperCase());
      let matchQuery = !this.snifferSearchQuery || searchData.includes(this.snifferSearchQuery);

      tr.style.display = matchOpcode && matchQuery ? "" : "none";
    });
  }

  renderSnifferPacket(pkt) {
    this.rawPackets.unshift(pkt);
    if (this.rawPackets.length > MAX_RAW_PACKETS) this.rawPackets.pop();

    if (this.dom.snifferTableBody.querySelector("td[colspan]")) {
      this.dom.snifferTableBody.innerHTML = "";
    }

    const tr = document.createElement("tr");
    const opcode = String(pkt.opcode || pkt.payload_type || "DATA").toUpperCase();
    const src = String(pkt.sender || pkt.src_node_id || pkt.from || "RF");
    const dst = String(pkt.to || pkt.dst_node_id || "0xFFFF");
    const snr = pkt.metrics?.snr !== undefined ? pkt.metrics.snr : (pkt.snr !== undefined ? pkt.snr : "--");
    const rssi = pkt.metrics?.rssi !== undefined ? pkt.metrics.rssi : (pkt.rssi !== undefined ? pkt.rssi : "--");
    const len = pkt.byte_length || pkt.length || (pkt.raw_hex ? Math.floor(pkt.raw_hex.length / 2) : 0);
    const hex = pkt.raw_hex || pkt.raw || "";

    let badgeClass = "opcode-raw";
    if (opcode.includes("TEXT") || opcode.includes("MSG") || opcode.includes("CHAT")) badgeClass = "opcode-text";
    else if (opcode.includes("TELEM") || opcode.includes("SENSOR")) badgeClass = "opcode-telemetry";
    else if (opcode.includes("ADV") || opcode.includes("BEACON")) badgeClass = "opcode-advert";
    else if (opcode.includes("ACK")) badgeClass = "opcode-ack";
    else if (opcode.includes("ROUT") || opcode.includes("HOP") || opcode.includes("PATH")) badgeClass = "opcode-routing";

    tr.setAttribute("data-opcode", opcode);
    const searchString = `${opcode} ${src} ${dst} ${hex} ${pkt.text || ""}`.toLowerCase();
    tr.setAttribute("data-search", searchString);

    const shortSrc = src.length > 12 ? `${src.slice(0, 8)}...` : src;
    const shortDst = dst.length > 12 ? `${dst.slice(0, 8)}...` : dst;

    tr.innerHTML = `
      <td style="color: var(--text-muted); font-size: 11px;">${new Date().toLocaleTimeString()}</td>
      <td><span class="badge-opcode ${badgeClass}">${this.escapeHtml(opcode)}</span></td>
      <td><code class="font-mono" title="${this.escapeHtml(src)}">${this.escapeHtml(shortSrc)}</code></td>
      <td><code class="font-mono" title="${this.escapeHtml(dst)}">${this.escapeHtml(shortDst)}</code></td>
      <td><strong>${snr} dB</strong> <span style="color: var(--text-muted); font-size: 11px;">/ ${rssi} dBm</span></td>
      <td><span class="badge-pill" style="font-size: 10.5px;">${len} B</span></td>
      <td><span class="hex-preview-box" title="${this.escapeHtml(hex)}">${this.escapeHtml(hex.slice(0, 32))}${hex.length > 32 ? "..." : ""}</span></td>
      <td><button type="button" class="btn-xs btn-outline btn-view-pkt">🔍 Ver</button></td>
    `;

    tr.querySelector(".btn-view-pkt").addEventListener("click", () => {
      this.showPacketDetail(pkt);
    });

    if (this.dom.snifferTableBody.firstChild) {
      this.dom.snifferTableBody.insertBefore(tr, this.dom.snifferTableBody.firstChild);
    } else {
      this.dom.snifferTableBody.appendChild(tr);
    }

    // Podar filas DOM sobrantes para evitar consumo innecesario de memoria en el navegador
    while (this.dom.snifferTableBody.children.length > MAX_RAW_PACKETS) {
      this.dom.snifferTableBody.removeChild(this.dom.snifferTableBody.lastChild);
    }

    this.updateSnifferStats();

    // Aplicar filtros en tiempo real
    const op = opcode;
    let matchOpcode = this.snifferFilterOpcode === "all" || op.includes(this.snifferFilterOpcode.toUpperCase());
    let matchQuery = !this.snifferSearchQuery || searchString.includes(this.snifferSearchQuery);
    tr.style.display = matchOpcode && matchQuery ? "" : "none";

    // Auto-scroll si no está pausado
    if (!this.snifferPaused && this.dom.snifferTableBody.parentElement) {
      const container = this.dom.snifferTableBody.parentElement.parentElement;
      if (container) container.scrollTop = 0;
    }
  }

  showPacketDetail(pkt) {
    this.currentInspectedPacket = pkt;
    const badgeEl = document.getElementById("packetDetailOpcodeBadge");
    const opcode = String(pkt.opcode || pkt.payload_type || "DATA").toUpperCase();
    if (badgeEl) badgeEl.textContent = opcode;

    const hex = pkt.raw_hex || pkt.raw || "";
    const src = pkt.sender || pkt.src_node_id || pkt.from || "RF";
    const dst = pkt.to || pkt.dst_node_id || "0xFFFF";
    const snr = pkt.metrics?.snr !== undefined ? pkt.metrics.snr : (pkt.snr !== undefined ? pkt.snr : "--");
    const rssi = pkt.metrics?.rssi !== undefined ? pkt.metrics.rssi : (pkt.rssi !== undefined ? pkt.rssi : "--");
    const len = pkt.byte_length || pkt.length || (hex ? Math.floor(hex.length / 2) : 0);

    // Formatear Hex con Offset estilo Wireshark
    let formattedHex = "";
    if (hex) {
      const cleanHex = hex.replace(/[^0-9a-fA-F]/g, "");
      for (let i = 0; i < cleanHex.length; i += 32) {
        const chunk = cleanHex.slice(i, i + 32);
        const offset = i.toString(16).padStart(4, "0");
        let bytesGroup = "";
        for (let j = 0; j < chunk.length; j += 2) {
          bytesGroup += chunk.slice(j, j + 2) + " ";
        }
        formattedHex += `0x${offset}:  ${bytesGroup.padEnd(48, " ")}\n`;
      }
    } else {
      formattedHex = "No hay volcado hexadecimal disponible para este paquete.";
    }

    this.dom.packetModalBody.innerHTML = `
      <div class="packet-meta-grid">
        <div class="packet-meta-item">
          <span>Tipo / OpCode</span>
          <strong>${this.escapeHtml(opcode)}</strong>
        </div>
        <div class="packet-meta-item">
          <span>Origen</span>
          <strong class="font-mono">${this.escapeHtml(src)}</strong>
        </div>
        <div class="packet-meta-item">
          <span>Destino</span>
          <strong class="font-mono">${this.escapeHtml(dst)}</strong>
        </div>
        <div class="packet-meta-item">
          <span>Calidad RF</span>
          <strong>${snr} dB / ${rssi} dBm</strong>
        </div>
        <div class="packet-meta-item">
          <span>Longitud</span>
          <strong>${len} Bytes</strong>
        </div>
        <div class="packet-meta-item">
          <span>Hora de Captura</span>
          <strong>${new Date().toLocaleTimeString()}</strong>
        </div>
      </div>

      <div class="packet-section-title">📦 Volcado Hexadecimal (Raw Hex Dump)</div>
      <div class="packet-hex-dump">${this.escapeHtml(formattedHex)}</div>

      <div class="packet-section-title">🔍 Campos Decodificados (JSON Schema)</div>
      <div class="packet-json-dump">${this.escapeHtml(JSON.stringify(pkt, null, 2))}</div>
    `;

    this.dom.packetDetailModal.classList.remove("hidden");
  }

  handleIncomingLiveEvent(payload) {
    if (!payload || typeof payload !== "object") return;

    if (payload.type === "channels_updated" || payload.event_type === "channels_updated") {
      if (Array.isArray(payload.data)) {
        this.renderChannelsList(payload.data);
      } else {
        this.fetchChannels();
      }
      return;
    }

    if (payload.type === "contacts_updated" || payload.event_type === "contacts_updated") {
      if (Array.isArray(payload.data)) {
        this.renderNodesDirectory(payload.data);
      } else {
        this.fetchNodes();
      }
      return;
    }

    if (payload.event === "metrics_update" || payload.type === "metrics_update" || (payload.rx_count !== undefined && payload.tx_count !== undefined)) {
      this.updateHeaderMetrics(payload);
    } else if (
      payload.event_type === "public" ||
      payload.event_type === "channel" ||
      payload.event_type === "direct" ||
      payload.type === "CHANNEL_MSG" ||
      payload.type === "DIRECT_MSG" ||
      (payload.text && (payload.channel_idx !== undefined || payload.sender))
    ) {
      const isDm = payload.event_type === "direct" || payload.type === "DIRECT_MSG";
      const chIdx = payload.channel_idx !== undefined ? Number(payload.channel_idx) : (payload.event_type === "channel" ? 1 : 0);
      const senderKey = payload.sender || payload.pubkey_prefix || "unknown";
      const senderName = payload.sender_name || payload.name || senderKey;

      const feedKey = isDm ? `dm_${senderKey}` : `ch_${chIdx}`;
      if (!this.channelFeeds.has(feedKey)) this.channelFeeds.set(feedKey, []);

      const normalizedMsg = {
        sender: senderKey,
        sender_name: senderName,
        text: payload.text || payload.message || "",
        channel_idx: chIdx,
        is_outgoing: false,
        metrics: payload.metrics || { rssi: payload.rssi || payload.RSSI, snr: payload.snr || payload.SNR },
        timestamp: payload.timestamp || new Date().toISOString(),
      };

      const feed = this.channelFeeds.get(feedKey);
      feed.push(normalizedMsg);
      if (feed.length > MAX_FEED_MESSAGES) feed.shift();

      let isCurrent = false;
      if (isDm) {
        isCurrent = Boolean(this.activeDmTarget && (this.activeDmTarget === senderKey || senderKey.startsWith(this.activeDmTarget) || this.activeDmTarget.startsWith(senderKey)));
      } else {
        isCurrent = !this.activeDmTarget && this.activeChannelIdx === chIdx;
      }

      if (isCurrent) {
        this.appendChatMessage(normalizedMsg);
      }

      if (isDm && senderKey && senderKey !== "unknown") {
        this.addDmContact(senderKey, senderName);
      }
    } else if (payload.byte_length !== undefined || payload.event_type === "rf_log" || payload.raw_hex !== undefined) {
      this.renderSnifferPacket(payload);
    } else if (payload.event_type === "system_log" && payload.data) {
      const log = payload.data;
      this.systemLogs.push(log);
      if (this.systemLogs.length > MAX_SYSTEM_LOGS) this.systemLogs.shift();

      const levelFilter = this.dom.logLevelFilter?.value || "ALL";
      const searchQuery = (this.dom.logSearchInput?.value || "").toLowerCase().trim();

      let matches = true;
      if (levelFilter !== "ALL") {
        if (levelFilter === "ERROR" && !["ERROR", "CRITICAL"].includes(log.level)) matches = false;
        if (levelFilter === "WARNING" && !["WARNING", "WARN"].includes(log.level)) matches = false;
        if (levelFilter === "INFO" && log.level !== "INFO") matches = false;
        if (levelFilter === "DEBUG" && log.level !== "DEBUG") matches = false;
      }
      if (searchQuery && matches) {
        const text = `${log.message} ${log.module} ${log.logger} ${log.exception || ""}`.toLowerCase();
        if (!text.includes(searchQuery)) matches = false;
      }

      if (matches && this.dom.systemLogsFeed) {
        if (this.dom.systemLogsFeed.querySelector("div[style]")) {
          this.dom.systemLogsFeed.innerHTML = "";
        }
        this.appendLogEntryToDom(log);
        if (!this.logsScrollPaused) {
          this.dom.systemLogsFeed.scrollTop = this.dom.systemLogsFeed.scrollHeight;
        }
      }

      if (log.level === "ERROR" || log.level === "CRITICAL") {
        const errChip = this.dom.chipErrorsCount?.querySelector(".val");
        if (errChip) {
          const cur = parseInt(errChip.textContent, 10) || 0;
          errChip.textContent = cur + 1;
          errChip.className = "val err";
        }
      }
    } else if (
      payload.temperature !== undefined ||
      payload.battery !== undefined ||
      payload.battery_pct !== undefined ||
      payload.voltage !== undefined ||
      payload.voltage_v !== undefined ||
      payload.solar_v !== undefined ||
      payload.event_type === "node_discovered" ||
      payload.event_type === "advert" ||
      payload.event_type === "telemetry" ||
      payload.event_type === "repeater_telemetry"
    ) {
      const senderKey = payload.sender || payload.public_key || payload.pubkey_prefix;
      if (senderKey && senderKey !== "unknown") {
        const existing = this.knownNodes.get(senderKey) || {};
        const telemData = payload.telemetry || payload;
        const updated = {
          ...existing,
          ...payload,
          ...telemData,
          public_key: existing.public_key || senderKey,
          last_seen: Math.floor(Date.now() / 1000),
        };
        this.knownNodes.set(senderKey, updated);
        this.renderNodesDirectory(Array.from(this.knownNodes.values()));

        // Si el modal de administración de este repetidor está abierto, actualizar métricas en vivo
        if (this.selectedRepeaterTarget && 
            (this.selectedRepeaterTarget === senderKey || 
             this.selectedRepeaterTarget.startsWith(senderKey) || 
             senderKey.startsWith(this.selectedRepeaterTarget))) {
          this.openRepeaterAdminModal(this.selectedRepeaterTarget, updated.name || updated.alias);
        }
      }
    }
  }

  initAnalytics() {
    const btnRefresh = document.getElementById("btnRefreshAnalytics");
    if (btnRefresh) {
      btnRefresh.addEventListener("click", async () => {
        btnRefresh.disabled = true;
        btnRefresh.textContent = "🔄 Actualizando...";
        await this.fetchAnalytics();
        btnRefresh.disabled = false;
        btnRefresh.textContent = "🔄 Actualizar Métricas";
        this.showToast("📈 Métricas analíticas actualizadas", "info");
      });
    }
  }

  async fetchAnalytics() {
    try {
      const res = await fetch("/api/analytics");
      const json = await res.json();
      if (json.status !== "ok" || !json.data) return;

      const data = json.data;
      const summary = data.summary || {};

      // 1. KPIs Principales
      const totalRx = summary.total_rx_packets || 0;
      const totalTx = summary.total_tx_packets || 0;
      const totalPackets = totalRx + totalTx;
      const totalNodes = summary.total_nodes || this.knownNodes.size || 0;
      const errorRate = summary.global_error_rate_pct !== undefined ? summary.global_error_rate_pct : 0.0;
      const totalErrors = summary.total_errors || 0;
      const offlineBuffer = data.offline_buffer_size !== undefined ? data.offline_buffer_size : 0;
      const queueDepth = data.queue_depth !== undefined ? data.queue_depth : 0;

      const kpiPkts = document.getElementById("kpiTotalPackets");
      if (kpiPkts) kpiPkts.textContent = totalPackets.toLocaleString();
      const kpiRatio = document.getElementById("kpiPacketsRatio");
      if (kpiRatio) kpiRatio.textContent = `RX: ${totalRx} | TX: ${totalTx}`;

      const kpiNodes = document.getElementById("kpiTotalNodes");
      if (kpiNodes) kpiNodes.textContent = String(totalNodes);
      
      const repeatersList = data.top_repeaters_by_clients || [];
      const kpiRep = document.getElementById("kpiRepeatersCount");
      if (kpiRep) kpiRep.textContent = `${repeatersList.length} Repetidores en Malla`;

      const kpiErr = document.getElementById("kpiErrorRate");
      if (kpiErr) {
        kpiErr.textContent = `${errorRate}%`;
        kpiErr.style.color = errorRate > 5 ? "var(--accent-danger)" : (errorRate > 2 ? "var(--accent-warning)" : "var(--accent-success)");
      }
      const kpiErrTot = document.getElementById("kpiErrorsTotal");
      if (kpiErrTot) kpiErrTot.textContent = `${totalErrors} errores acumulados`;

      const kpiBuf = document.getElementById("kpiOfflineBuffer");
      if (kpiBuf) kpiBuf.textContent = `${offlineBuffer} msgs`;
      const kpiQ = document.getElementById("kpiQueueDepth");
      if (kpiQ) kpiQ.textContent = `Cola TX: ${queueDepth} paquetes`;

      // 2. Tabla Top Nodos por Tráfico
      const topTrafficTable = document.getElementById("analyticsTopActiveTable");
      if (topTrafficTable) {
        const topNodes = data.top_nodes_by_traffic || [];
        if (topNodes.length === 0) {
          topTrafficTable.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No hay actividad de tráfico registrada aún.</td></tr>';
        } else {
          topTrafficTable.innerHTML = "";
          const frag = document.createDocumentFragment();
          for (const n of topNodes) {
            const tr = document.createElement("tr");
            const name = n.alias || n.name || (n.public_key ? `Nodo ${n.public_key.slice(0, 6)}` : "Nodo");
            const role = (n.role || "CLIENT").toUpperCase();
            const rx = n.rx_packets || 0;
            const tx = n.tx_packets || 0;
            const total = n.total_packets || (rx + tx);

            tr.innerHTML = `
              <td><strong>${this.escapeHtml(name)}</strong></td>
              <td><span class="badge-pill" style="font-size: 10px;">${role}</span></td>
              <td>${rx}</td>
              <td>${tx}</td>
              <td><strong>${total}</strong></td>
            `;
            frag.appendChild(tr);
          }
          topTrafficTable.appendChild(frag);
        }
      }

      // 3. Tabla de Calidad de Señal RF (Mejores y Peores SNR)
      const signalTable = document.getElementById("analyticsSignalTable");
      if (signalTable) {
        const bestSnr = data.top_nodes_best_snr || [];
        if (bestSnr.length === 0) {
          signalTable.innerHTML = '<tr><td colspan="4" class="text-center text-muted">Esperando mediciones de SNR/RSSI de la malla...</td></tr>';
        } else {
          signalTable.innerHTML = "";
          const frag = document.createDocumentFragment();
          for (const n of bestSnr) {
            const tr = document.createElement("tr");
            const name = n.alias || n.name || (n.public_key ? `Nodo ${n.public_key.slice(0, 6)}` : "Nodo");
            const snr = parseFloat(n.last_snr !== undefined ? n.last_snr : (n.snr || 0));
            const rssi = n.last_rssi !== undefined ? n.last_rssi : (n.rssi || "--");

            const pct = Math.min(Math.max(((snr + 15) / 30) * 100, 10), 100);
            const qualityClass = snr >= 6 ? "good" : (snr >= 0 ? "medium" : "poor");

            tr.innerHTML = `
              <td><strong>${this.escapeHtml(name)}</strong></td>
              <td><strong>${snr.toFixed(1)} dB</strong></td>
              <td>${rssi} dBm</td>
              <td>
                <div class="signal-bar-wrap">
                  <div class="signal-bar-bg">
                    <div class="signal-bar-fill ${qualityClass}" style="width: ${pct}%;"></div>
                  </div>
                  <span style="font-size: 10.5px; color: var(--text-muted);">${qualityClass.toUpperCase()}</span>
                </div>
              </td>
            `;
            frag.appendChild(tr);
          }
          signalTable.appendChild(frag);
        }
      }

      // 4. Tabla de Repetidores
      const repTable = document.getElementById("analyticsRepeatersTable");
      if (repTable) {
        if (repeatersList.length === 0) {
          repTable.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No se han detectado repetidores en la malla.</td></tr>';
        } else {
          repTable.innerHTML = "";
          const frag = document.createDocumentFragment();
          for (const r of repeatersList) {
            const tr = document.createElement("tr");
            const name = r.alias || r.name || (r.public_key ? `Router ${r.public_key.slice(0, 6)}` : "Repetidor");
            const clientsCount = r.connected_clients_count || (r.neighbors ? r.neighbors.length : 0);
            const txPower = r.tx_power || 20;
            const hopLimit = r.hop_limit || 3;

            tr.innerHTML = `
              <td><strong>${this.escapeHtml(name)}</strong></td>
              <td><span class="badge-pill badge-success">${clientsCount} nodo(s)</span></td>
              <td>${txPower} dBm</td>
              <td>${hopLimit} saltos</td>
            `;
            frag.appendChild(tr);
          }
          repTable.appendChild(frag);
        }
      }

      // 5. Filas de Estado del Sistema
      const bufEl = document.getElementById("statBufferOffline");
      if (bufEl) bufEl.textContent = `${offlineBuffer} msgs`;
      const qEl = document.getElementById("statQueueDepth");
      if (qEl) qEl.textContent = `${queueDepth} paquetes`;

    } catch (err) {
      console.warn("Error cargando analítica de malla:", err);
    }
  }

  initHomeAssistant() {
    this.dom.btnPublishHaDiscovery.addEventListener("click", () => {
      this.publishHomeAssistantDiscovery();
    });
  }

  async publishHomeAssistantDiscovery() {
    try {
      this.dom.btnPublishHaDiscovery.disabled = true;
      this.dom.btnPublishHaDiscovery.textContent = "📢 Anunciando...";
      const res = await fetch("/api/ha/publish", { method: "POST" });
      const data = await res.json();
      if (data.status === "ok") {
        this.dom.haDiscoveredCount.textContent = data.data.published_entities;
        alert(`✓ Home Assistant Discovery anunciado con éxito (${data.data.published_entities} entidades).`);
      }
    } catch (e) {
      alert("Error al anunciar Home Assistant Discovery: " + e.message);
    } finally {
      this.dom.btnPublishHaDiscovery.disabled = false;
      this.dom.btnPublishHaDiscovery.textContent = "📢 Re-anunciar Discovery en MQTT";
    }
  }

  initPreflight() {
    this.dom.btnRunPreflight.addEventListener("click", async () => {
      this.dom.preflightResults.innerHTML = "Ejecutando comprobaciones de diagnóstico...";
      try {
        const res = await fetch("/api/preflight");
        const data = await res.json();
        if (data.status === "ok") {
          this.renderPreflightReport(data.data);
        }
      } catch (err) {
        this.dom.preflightResults.innerHTML = `<span class="text-danger">Error: ${err.message}</span>`;
      }
    });
  }

  renderPreflightReport(report) {
    let html = `<div style="margin-top: 10px; display: flex; flex-direction: column; gap: 8px;">`;
    html += `<div style="font-weight: 600; color: ${report.status === "OK" ? "var(--accent-success)" : "var(--accent-warning)"}">Estado General: ${report.status}</div>`;
    for (const c of report.checks) {
      html += `
        <div style="background: var(--bg-surface-elevated); padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-subtle); display: flex; justify-content: space-between;">
          <span>${this.escapeHtml(c.name)}</span>
          <span style="color: ${c.passed ? "var(--accent-success)" : "var(--accent-danger)"}">${c.passed ? "✓ PASS" : "✗ FALLO"}: ${this.escapeHtml(c.message)}</span>
        </div>
      `;
    }
    html += `</div>`;
    this.dom.preflightResults.innerHTML = html;
  }

  initSettingsDashboard() {
    this.fetchLocalNodeConfig();

    // 1. Navegación por subpestañas locales
    document.querySelectorAll(".local-subtab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".local-subtab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".local-settings-subpanel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const target = btn.getAttribute("data-subtab");
        const panel = document.getElementById(target);
        if (panel) panel.classList.add("active");
      });
    });

    // 2. Slider de potencia TX
    const txSlider = document.getElementById("localTxPower");
    const txVal = document.getElementById("localTxPowerVal");
    if (txSlider && txVal) {
      txSlider.addEventListener("input", (e) => {
        txVal.textContent = `${e.target.value} dBm`;
      });
    }

    // 3. Formulario Parámetros RF & Radio
    const radioForm = document.getElementById("localRadioForm");
    if (radioForm) {
      radioForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.saveLocalRadioConfig();
      });
    }

    // 4. Formulario Identidad, Propietario & Posición
    const ownerPosForm = document.getElementById("localOwnerPosForm");
    if (ownerPosForm) {
      ownerPosForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.saveLocalIdentityAndPosition();
      });
    }

    // 5. Botón Copiar Clave Pública Local
    const btnCopyPk = document.getElementById("btnCopyLocalPubkey");
    if (btnCopyPk) {
      btnCopyPk.addEventListener("click", () => {
        const pk = document.getElementById("localNodePubkey")?.value || "";
        if (pk) {
          navigator.clipboard.writeText(pk);
          this.showToast("📋 Clave pública copiada al portapapeles", "success");
        }
      });
    }

    // 6. Botón Obtener GPS del Navegador
    const btnBrowserGps = document.getElementById("btnGetBrowserGps");
    if (btnBrowserGps) {
      btnBrowserGps.addEventListener("click", () => {
        if (!navigator.geolocation) {
          alert("La geolocalización no está soportada por tu navegador.");
          return;
        }
        btnBrowserGps.disabled = true;
        btnBrowserGps.textContent = "🛰️ Localizando...";
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            const latInput = document.getElementById("localGpsLat");
            const lonInput = document.getElementById("localGpsLon");
            const altInput = document.getElementById("localGpsAlt");
            if (latInput) latInput.value = pos.coords.latitude.toFixed(6);
            if (lonInput) lonInput.value = pos.coords.longitude.toFixed(6);
            if (altInput && pos.coords.altitude) altInput.value = Math.round(pos.coords.altitude);
            btnBrowserGps.disabled = false;
            btnBrowserGps.textContent = "🛰️ Obtener GPS del Navegador";
            this.showToast("📍 Coordenadas GPS del navegador obtenidas", "success");
          },
          (err) => {
            btnBrowserGps.disabled = false;
            btnBrowserGps.textContent = "🛰️ Obtener GPS del Navegador";
            alert("No se pudo obtener la posición GPS del navegador: " + err.message);
          },
          { enableHighAccuracy: true, timeout: 10000 }
        );
      });
    }

    // 7. Consola Terminal Local
    const termForm = document.getElementById("localTerminalForm");
    const termInput = document.getElementById("localTerminalInput");
    if (termForm && termInput) {
      termForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const cmd = termInput.value.trim();
        if (cmd) {
          termInput.value = "";
          await this.sendLocalCliCommand(cmd);
        }
      });
    }

    const btnToggleHelp = document.getElementById("btnToggleLocalCmdHelp");
    const helpDrawer = document.getElementById("localTerminalHelpDrawer");
    const btnCloseHelp = document.getElementById("btnCloseLocalHelpDrawer");
    if (btnToggleHelp && helpDrawer) {
      btnToggleHelp.addEventListener("click", () => {
        helpDrawer.classList.toggle("hidden");
      });
    }
    if (btnCloseHelp && helpDrawer) {
      btnCloseHelp.addEventListener("click", () => {
        helpDrawer.classList.add("hidden");
      });
    }

    document.querySelectorAll("#localTerminalHelpDrawer .help-cmd-item").forEach((item) => {
      item.addEventListener("click", () => {
        const cmd = item.getAttribute("data-cmd");
        if (cmd && termInput) {
          termInput.value = cmd;
          termInput.focus();
        }
      });
    });

    const btnClearTerm = document.getElementById("btnClearLocalTerminal");
    if (btnClearTerm) {
      btnClearTerm.addEventListener("click", () => {
        const out = document.getElementById("localTerminalOutput");
        if (out) out.textContent = "[Sistema] Terminal local limpiada.\n";
      });
    }

    // 8. Botones de Actualización y Acciones
    const btnRefreshCfg = document.getElementById("btnRefreshLocalConfig");
    if (btnRefreshCfg) {
      btnRefreshCfg.addEventListener("click", async () => {
        await this.fetchLocalNodeConfig();
        this.showToast("🔄 Parámetros del nodo local actualizados", "info");
      });
    }

    const btnRefreshTelem = document.getElementById("btnRefreshLocalTelem");
    if (btnRefreshTelem) {
      btnRefreshTelem.addEventListener("click", async () => {
        await this.sendLocalCliCommand("get_stats_core");
      });
    }

    const btnSyncClock = document.getElementById("btnSyncLocalClock") || document.getElementById("btnActionSyncClock");
    if (btnSyncClock) {
      btnSyncClock.addEventListener("click", async () => {
        await this.syncLocalClock();
      });
    }

    const btnAdvert = document.getElementById("btnLocalAdvertNow") || document.getElementById("btnActionBroadcastAdvert");
    if (btnAdvert) {
      btnAdvert.addEventListener("click", async () => {
        await this.sendLocalCliCommand("advert");
        this.showToast("📢 Anuncio de presencia emitido por radio", "success");
      });
    }

    const btnReboot = document.getElementById("btnActionRebootLocal");
    if (btnReboot) {
      btnReboot.addEventListener("click", async () => {
        if (confirm("¿Confirmas el reinicio de hardware del microcontrolador local (ESP32/nRF52)?")) {
          await this.rebootLocalNode();
        }
      });
    }

    const btnClearStats = document.getElementById("btnActionClearLocalStats");
    if (btnClearStats) {
      btnClearStats.addEventListener("click", async () => {
        await this.sendLocalCliCommand("clear stats");
        this.showToast("🧹 Estadísticas locales restablecidas", "info");
      });
    }

    const btnReconnectSerial = document.getElementById("btnActionReconnectSerial");
    if (btnReconnectSerial) {
      btnReconnectSerial.addEventListener("click", async () => {
        try {
          btnReconnectSerial.disabled = true;
          btnReconnectSerial.textContent = "📻 Reconectando...";
          const res = await fetch("/api/admin/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "reconnect_serial" }),
          });
          await res.json();
          this.showToast("📻 Ciclo de reconexión serial ejecutado", "info");
          await this.fetchLocalNodeConfig();
        } catch (err) {
          alert("Error reconectando serial: " + err.message);
        } finally {
          btnReconnectSerial.disabled = false;
          btnReconnectSerial.textContent = "📻 Reconectar Serial";
        }
      });
    }
  }

  async fetchLocalNodeConfig() {
    try {
      const res = await fetch("/api/node/config");
      const json = await res.json();
      if (json.status !== "ok" || !json.data) return;

      const cfg = json.data;

      // Inputs de Identidad
      const nameInput = document.getElementById("localNodeName");
      if (nameInput && cfg.name) nameInput.value = cfg.name;

      const pubkeyInput = document.getElementById("localNodePubkey");
      if (pubkeyInput) pubkeyInput.value = cfg.public_key || "000000000000";

      const ownerInput = document.getElementById("localOwnerInfo");
      if (ownerInput && (cfg.owner_info || cfg.owner)) ownerInput.value = cfg.owner_info || cfg.owner;

      const latInput = document.getElementById("localGpsLat");
      if (latInput && (cfg.latitude || cfg.lat)) latInput.value = cfg.latitude || cfg.lat;

      const lonInput = document.getElementById("localGpsLon");
      if (lonInput && (cfg.longitude || cfg.lon)) lonInput.value = cfg.longitude || cfg.lon;

      const altInput = document.getElementById("localGpsAlt");
      if (altInput && (cfg.altitude || cfg.alt)) altInput.value = cfg.altitude || cfg.alt;

      // Inputs de Radio
      const freqInput = document.getElementById("localFreq");
      if (freqInput && (cfg.frequency || cfg.radio_freq)) freqInput.value = String(cfg.frequency || cfg.radio_freq);

      const txInput = document.getElementById("localTxPower");
      const txVal = document.getElementById("localTxPowerVal");
      if (txInput) {
        txInput.value = String(cfg.tx_power || 20);
        if (txVal) txVal.textContent = `${cfg.tx_power || 20} dBm`;
      }

      const hopInput = document.getElementById("localHopLimit");
      if (hopInput && cfg.hop_limit) hopInput.value = String(cfg.hop_limit);

      const sfInput = document.getElementById("localSf");
      if (sfInput && (cfg.spreading_factor || cfg.sf)) sfInput.value = String(cfg.spreading_factor || cfg.sf);

      const bwInput = document.getElementById("localBw");
      if (bwInput && (cfg.bandwidth || cfg.bw)) bwInput.value = String(cfg.bandwidth || cfg.bw);

      const crInput = document.getElementById("localCr");
      if (crInput && (cfg.coding_rate || cfg.cr)) crInput.value = String(cfg.coding_rate || cfg.cr);

      const repInput = document.getElementById("localRepeatMode");
      if (repInput && cfg.repeat !== undefined) repInput.value = cfg.repeat ? "on" : "off";

      const telemInput = document.getElementById("localTelemetryInterval");
      if (telemInput && cfg.telemetry_interval) telemInput.value = String(cfg.telemetry_interval);

      const advInput = document.getElementById("localAdvertInterval");
      if (advInput && (cfg.advert_interval || cfg.beacon_interval)) advInput.value = String(cfg.advert_interval || cfg.beacon_interval);

      // Resumen y Badges
      const roleBadge = document.getElementById("localNodeRoleBadge");
      if (roleBadge) roleBadge.textContent = cfg.role || "Estación Base";

      const sumFreq = document.getElementById("localSummaryFreq");
      if (sumFreq) sumFreq.textContent = `${cfg.frequency || cfg.radio_freq || 915.0} MHz`;

      const sumPower = document.getElementById("localSummaryPower");
      if (sumPower) sumPower.textContent = `${cfg.tx_power || 20} dBm`;

      const sumModem = document.getElementById("localSummaryModem");
      if (sumModem) sumModem.textContent = `SF${cfg.spreading_factor || cfg.sf || 11} / BW${cfg.bandwidth || cfg.bw || 250}`;

      const sumRepeat = document.getElementById("localSummaryRepeat");
      if (sumRepeat) sumRepeat.textContent = cfg.repeat === false ? "Desactivado" : "Activado";

      const sumPos = document.getElementById("localSummaryPos");
      if (sumPos) {
        const lat = cfg.latitude || cfg.lat;
        const lon = cfg.longitude || cfg.lon;
        sumPos.textContent = lat && lon ? `${parseFloat(lat).toFixed(4)}, ${parseFloat(lon).toFixed(4)}` : "Sin fijar";
      }

      // Telemetría en Vivo si está presente
      if (cfg.battery_pct !== undefined || cfg.battery !== undefined) {
        const batEl = document.getElementById("localBatValue");
        if (batEl) batEl.textContent = `${cfg.battery_pct || cfg.battery}%`;
      }
      if (cfg.battery_mv !== undefined || cfg.voltage !== undefined) {
        const vEl = document.getElementById("localVoltValue");
        if (vEl) vEl.textContent = `${((cfg.battery_mv || cfg.voltage * 1000) / 1000).toFixed(2)} V`;
      }
      if (cfg.uptime_str || cfg.uptime) {
        const upEl = document.getElementById("localUptimeValue");
        if (upEl) upEl.textContent = cfg.uptime_str || `${cfg.uptime}s`;
      }
      if (cfg.airtime_ms !== undefined) {
        const airEl = document.getElementById("localAirtimeValue");
        if (airEl) airEl.textContent = `${cfg.airtime_ms} ms`;
      }
      if (cfg.last_snr !== undefined) {
        const snrEl = document.getElementById("localSnrValue");
        if (snrEl) snrEl.textContent = `${cfg.last_snr} dB`;
      }
      if (cfg.last_rssi !== undefined) {
        const rssiEl = document.getElementById("localRssiValue");
        if (rssiEl) rssiEl.textContent = `RSSI: ${cfg.last_rssi} dBm`;
      }
    } catch (err) {
      console.warn("Error cargando configuración local:", err);
    }
  }

  async saveLocalRadioConfig() {
    const payload = {
      frequency: parseFloat(document.getElementById("localFreq")?.value) || 915.0,
      region: document.getElementById("localRegion")?.value || "US915",
      tx_power: parseInt(document.getElementById("localTxPower")?.value, 10) || 20,
      hop_limit: parseInt(document.getElementById("localHopLimit")?.value, 10) || 3,
      spreading_factor: parseInt(document.getElementById("localSf")?.value, 10) || 11,
      bandwidth: parseInt(document.getElementById("localBw")?.value, 10) || 250,
      coding_rate: document.getElementById("localCr")?.value || "4/5",
      repeat: document.getElementById("localRepeatMode")?.value === "on",
      telemetry_interval: parseInt(document.getElementById("localTelemetryInterval")?.value, 10) || 60,
      advert_interval: parseInt(document.getElementById("localAdvertInterval")?.value, 10) || 300,
    };

    const btn = document.getElementById("btnSaveLocalRadio");
    try {
      if (btn) {
        btn.disabled = true;
        btn.textContent = "💾 Guardando...";
      }
      const res = await fetch("/api/node/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.showToast("✓ Parámetros de radio aplicados correctamente al transceptor local", "success");
        await this.fetchLocalNodeConfig();
      } else {
        alert("Error guardando ajustes: " + (data.message || data.error));
      }
    } catch (err) {
      alert("Error al comunicarse con la API: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "💾 Guardar y Aplicar Parámetros de Radio";
      }
    }
  }

  async saveLocalIdentityAndPosition() {
    const payload = {
      name: document.getElementById("localNodeName")?.value.trim() || "MeshCore_Base",
      owner_info: document.getElementById("localOwnerInfo")?.value.trim() || "",
      latitude: parseFloat(document.getElementById("localGpsLat")?.value) || null,
      longitude: parseFloat(document.getElementById("localGpsLon")?.value) || null,
      altitude: parseInt(document.getElementById("localGpsAlt")?.value, 10) || null,
    };

    const btn = document.getElementById("btnSaveLocalIdentityPos");
    try {
      if (btn) {
        btn.disabled = true;
        btn.textContent = "💾 Guardando...";
      }
      const res = await fetch("/api/node/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.showToast("✓ Identidad y posición geográfica guardadas", "success");
        await this.fetchLocalNodeConfig();
      } else {
        alert("Error guardando identidad: " + (data.message || data.error));
      }
    } catch (err) {
      alert("Error al comunicarse con la API: " + err.message);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = "💾 Guardar Identidad & Posición";
      }
    }
  }

  async sendLocalCliCommand(cmdText) {
    const out = document.getElementById("localTerminalOutput");
    const appendTerm = (msg) => {
      if (out) {
        out.textContent += `\n[${new Date().toLocaleTimeString()}] ${msg}`;
        out.scrollTop = out.scrollHeight;
      }
    };

    appendTerm(`> ${cmdText}`);
    try {
      const res = await fetch("/api/admin/command", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: cmdText }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const resultStr = typeof data.result === "object" ? JSON.stringify(data.result, null, 2) : String(data.result || "OK");
        appendTerm(`< ${resultStr}`);
      } else {
        appendTerm(`! ERROR: ${data.message || data.error || "Fallo en comando"}`);
      }
    } catch (err) {
      appendTerm(`! ERROR RED: ${err.message}`);
    }
  }

  async syncLocalClock() {
    const nowIso = new Date().toISOString();
    const clockEl = document.getElementById("localClockValue");
    if (clockEl) clockEl.textContent = new Date().toLocaleTimeString();

    await this.sendLocalCliCommand("sync_clock");
    this.showToast("🕒 Reloj RTC del nodo local sincronizado con el servidor", "success");
  }

  async rebootLocalNode() {
    try {
      const res = await fetch("/api/node/reboot", { method: "POST" });
      const data = await res.json();
      if (data.status === "ok") {
        this.showToast("🔄 Comando de reinicio emitido al transceptor local", "info");
      }
    } catch (e) {
      alert("Error enviando comando de reinicio: " + e.message);
    }
  }

  initLogsConsole() {
    if (!this.dom.systemLogsFeed) return;

    this.fetchSystemLogs();
    this.fetchSubsystemsHealth();

    if (this.dom.btnToggleDebugMode) {
      this.dom.btnToggleDebugMode.addEventListener("click", () => this.toggleDebugMode());
    }
    if (this.dom.btnQuickDiag) {
      this.dom.btnQuickDiag.addEventListener("click", () => this.runQuickDiagnostic());
    }
    if (this.dom.btnCopyAIDiag) {
      this.dom.btnCopyAIDiag.addEventListener("click", () => this.copyAIDiagnostics());
    }
    if (this.dom.btnDownloadRawLogs) {
      this.dom.btnDownloadRawLogs.addEventListener("click", () => this.downloadRawLogs());
    }
    if (this.dom.btnExportDiag) {
      this.dom.btnExportDiag.addEventListener("click", () => this.exportDiagnosticReport());
    }
    if (this.dom.btnClearLogs) {
      this.dom.btnClearLogs.addEventListener("click", () => this.clearSystemLogs());
    }
    if (this.dom.btnPauseLogsScroll) {
      this.dom.btnPauseLogsScroll.addEventListener("click", () => this.toggleLogsScroll());
    }
    if (this.dom.logLevelFilter) {
      this.dom.logLevelFilter.addEventListener("change", () => this.renderFilteredLogs());
    }
    if (this.dom.logSearchInput) {
      this.dom.logSearchInput.addEventListener(
        "input",
        debounce(() => this.renderFilteredLogs(), 150)
      );
    }
    if (this.dom.btnCloseQuickDiag) {
      this.dom.btnCloseQuickDiag.addEventListener("click", () => {
        if (this.dom.quickDiagPanel) this.dom.quickDiagPanel.classList.add("hidden");
      });
    }
  }

  async fetchSystemLogs() {
    try {
      const res = await fetch("/api/system/logs?limit=200");
      const data = await res.json();
      if (data.status === "ok" && Array.isArray(data.data)) {
        this.systemLogs = data.data;
        if (data.current_level) {
          this.isDebugMode = data.current_level === "DEBUG";
          this.updateDebugButtonState();
        }
        this.renderFilteredLogs();
      }
    } catch (e) {
      console.warn("Error cargando logs iniciales:", e);
    }
  }

  async fetchSubsystemsHealth() {
    try {
      const res = await fetch("/api/diagnostics");
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        this.updateHealthChips(data.data);
      }
    } catch (e) {
      console.warn("Error actualizando salud de subsistemas:", e);
    }
  }

  updateHealthChips(diag) {
    if (!diag || !diag.subsystems) return;
    const sub = diag.subsystems;

    if (this.dom.chipSerialHealth) {
      const isSerOk = sub.serial_companion?.connected;
      const el = this.dom.chipSerialHealth.querySelector(".val");
      if (el) {
        el.textContent = isSerOk ? `Conectado (${sub.serial_companion.port})` : "Desconectado";
        el.className = `val ${isSerOk ? "ok" : "err"}`;
      }
    }

    if (this.dom.chipMqttHealth) {
      const isMqttOk = sub.mqtt_broker?.connected;
      const el = this.dom.chipMqttHealth.querySelector(".val");
      if (el) {
        el.textContent = isMqttOk ? `Online (${sub.mqtt_broker.broker})` : "Offline";
        el.className = `val ${isMqttOk ? "ok" : "err"}`;
      }
    }

    if (this.dom.chipDbHealth) {
      const el = this.dom.chipDbHealth.querySelector(".val");
      if (el) el.textContent = "WAL OK";
    }

    if (this.dom.chipTxHealth) {
      const depth = sub.rate_limiter?.queue_depth || 0;
      const el = this.dom.chipTxHealth.querySelector(".val");
      if (el) el.textContent = depth;
    }

    if (this.dom.chipErrorsCount) {
      const errs = diag.counters?.log_errors || 0;
      const el = this.dom.chipErrorsCount.querySelector(".val");
      if (el) {
        el.textContent = errs;
        el.className = `val ${errs > 0 ? "err" : "ok"}`;
      }
    }
  }

  renderFilteredLogs() {
    if (!this.dom.systemLogsFeed) return;
    const levelFilter = this.dom.logLevelFilter?.value || "ALL";
    const searchQuery = (this.dom.logSearchInput?.value || "").toLowerCase().trim();

    const filtered = this.systemLogs.filter((log) => {
      if (levelFilter !== "ALL") {
        if (levelFilter === "ERROR" && !["ERROR", "CRITICAL"].includes(log.level)) return false;
        if (levelFilter === "WARNING" && !["WARNING", "WARN"].includes(log.level)) return false;
        if (levelFilter === "INFO" && log.level !== "INFO") return false;
        if (levelFilter === "DEBUG" && log.level !== "DEBUG") return false;
      }
      if (searchQuery) {
        const text = `${log.message} ${log.module} ${log.logger} ${log.exception || ""}`.toLowerCase();
        if (!text.includes(searchQuery)) return false;
      }
      return true;
    });

    this.dom.systemLogsFeed.innerHTML = "";
    if (filtered.length === 0) {
      this.dom.systemLogsFeed.innerHTML = '<div style="color: var(--text-muted); padding: 14px; text-align: center;">No hay logs que coincidan con los filtros actuales.</div>';
      return;
    }

    const frag = document.createDocumentFragment();
    const visibleLogs = filtered.slice(-MAX_SYSTEM_LOGS);
    for (const log of visibleLogs) {
      frag.appendChild(this.createLogElement(log));
    }
    this.dom.systemLogsFeed.appendChild(frag);

    if (!this.logsScrollPaused) {
      this.dom.systemLogsFeed.scrollTop = this.dom.systemLogsFeed.scrollHeight;
    }
  }

  createLogElement(log) {
    const row = document.createElement("div");
    row.className = "log-row";

    const lvlLower = (log.level || "info").toLowerCase();
    const timeStr = log.iso_time ? (log.iso_time.split(" ")[1] || log.iso_time) : new Date((log.timestamp || (Date.now() / 1000)) * 1000).toLocaleTimeString();

    row.innerHTML = `
      <span class="log-time">${this.escapeHtml(timeStr)}</span>
      <span class="log-badge badge-lvl-${this.escapeHtml(lvlLower)}">${this.escapeHtml(log.level)}</span>
      <span class="log-mod font-mono" title="${this.escapeHtml(log.module || log.logger)}">${this.escapeHtml(log.module || log.logger || "core")}</span>
      <span class="log-msg">${this.escapeHtml(log.message)}</span>
      ${log.exception ? `<pre class="log-trace">${this.escapeHtml(log.exception)}</pre>` : ""}
    `;

    this.dom.systemLogsFeed.appendChild(row);
  }

  async toggleDebugMode() {
    this.isDebugMode = !this.isDebugMode;
    const targetLevel = this.isDebugMode ? "DEBUG" : "INFO";
    try {
      const res = await fetch("/api/system/logs/level", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: targetLevel }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.updateDebugButtonState();
      }
    } catch (e) {
      console.warn("Error cambiando nivel de log:", e);
    }
  }

  updateDebugButtonState() {
    if (!this.dom.btnToggleDebugMode) return;
    if (this.isDebugMode) {
      this.dom.btnToggleDebugMode.textContent = "🐞 Modo DEBUG: ON";
      this.dom.btnToggleDebugMode.className = "btn-primary";
    } else {
      this.dom.btnToggleDebugMode.textContent = "🐞 Modo DEBUG: OFF";
      this.dom.btnToggleDebugMode.className = "btn-secondary";
    }
  }

  async clearSystemLogs() {
    try {
      await fetch("/api/system/logs", { method: "DELETE" });
      this.systemLogs = [];
      this.renderFilteredLogs();
    } catch (e) {
      console.warn("Error limpiando logs:", e);
    }
  }

  toggleLogsScroll() {
    this.logsScrollPaused = !this.logsScrollPaused;
    if (this.dom.btnPauseLogsScroll) {
      this.dom.btnPauseLogsScroll.textContent = this.logsScrollPaused ? "▶️ Reanudar Scroll" : "⏸️ Pausar Scroll";
      this.dom.btnPauseLogsScroll.className = this.logsScrollPaused ? "btn-secondary btn-sm" : "btn-outline btn-sm";
    }
  }

  async runQuickDiagnostic() {
    if (!this.dom.quickDiagPanel || !this.dom.quickDiagBody) return;
    this.dom.quickDiagPanel.classList.remove("hidden");
    this.dom.quickDiagBody.innerHTML = "Ejecutando auto-diagnóstico de subsistemas...";
    try {
      const res = await fetch("/api/diagnostics");
      const data = await res.json();
      if (data.status === "ok") {
        this.dom.quickDiagBody.innerHTML = `<pre>${this.escapeHtml(JSON.stringify(data.data, null, 2))}</pre>`;
        this.updateHealthChips(data.data);
      }
    } catch (e) {
      this.dom.quickDiagBody.innerHTML = `<span style="color: var(--accent-danger)">Error: ${this.escapeHtml(e.message)}</span>`;
    }
  }

  async copyAIDiagnostics() {
    if (this.dom.btnCopyAIDiag) {
      this.dom.btnCopyAIDiag.textContent = "⏳ Generando...";
    }
    try {
      const res = await fetch("/api/diagnostics/report.md");
      const data = await res.json();
      const md = (data.status === "ok" && data.markdown) ? data.markdown : (typeof data === "string" ? data : JSON.stringify(data, null, 2));

      await navigator.clipboard.writeText(md);
      if (this.dom.btnCopyAIDiag) {
        this.dom.btnCopyAIDiag.textContent = "✓ ¡Copiado al Portapapeles!";
        setTimeout(() => {
          if (this.dom.btnCopyAIDiag) this.dom.btnCopyAIDiag.textContent = "📋 Copiar para IA";
        }, 2500);
      }
    } catch (e) {
      console.warn("Fallo al copiar diagnóstico:", e);
      try {
        const res = await fetch("/api/diagnostics/report.md");
        const data = await res.json();
        const md = data.markdown || JSON.stringify(data);
        prompt("Copia el siguiente reporte de diagnóstico para tu IA / soporte:", md);
      } catch (err) {
        alert("Error al obtener reporte para IA: " + err.message);
      }
      if (this.dom.btnCopyAIDiag) this.dom.btnCopyAIDiag.textContent = "📋 Copiar para IA";
    }
  }

  async downloadRawLogs() {
    try {
      const res = await fetch("/api/logs/download");
      const data = await res.json();
      const rawText = data.raw_logs || "";
      const blob = new Blob([rawText], { type: "text/plain;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `meshcore_bridge_${new Date().toISOString().replace(/[:.]/g, "-")}.log`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("Error descargando archivo de logs: " + e.message);
    }
  }

  async exportDiagnosticReport() {
    try {
      const res = await fetch("/api/diagnostics/export");
      const data = await res.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `meshcore_diagnostics_${Date.now()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("Error descargando reporte de diagnóstico: " + e.message);
    }
  }

  initChat() {
    this.dom.chatInputForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const text = this.dom.chatInputText.value.trim();
      if (!text) return;
      this.dom.chatInputText.value = "";

      const target = this.activeDmTarget || "broadcast";
      const outgoingMsg = {
        sender: "local",
        sender_name: "Estación Local (Tú)",
        text: text,
        is_outgoing: true,
        channel_idx: this.activeChannelIdx,
        dm_target: this.activeDmTarget,
        timestamp: new Date().toISOString(),
      };

      const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
      if (!this.channelFeeds.has(feedKey)) this.channelFeeds.set(feedKey, []);
      const feed = this.channelFeeds.get(feedKey);
      feed.push(outgoingMsg);
      if (feed.length > MAX_FEED_MESSAGES) feed.shift();

      if (this.activeDmTarget) {
        this.conversationsWithMessages.add(this.activeDmTarget);
        this.addDmContact(this.activeDmTarget, this.activeDmName);
      }

      this.appendChatMessage(outgoingMsg);

      try {
        await fetch("/api/tx", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            to: target,
            channel_index: this.activeChannelIdx,
            text: text,
          }),
        });
      } catch (err) {
        console.error("Error transmitiendo mensaje:", err);
      }
    });

    this.dom.clearChatBtn.addEventListener("click", () => {
      const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
      this.channelFeeds.set(feedKey, []);
      this.dom.chatMessageFeed.innerHTML = "";
    });

    this.dom.channelListUi.addEventListener("click", (e) => {
      const li = e.target.closest("li.channel-item");
      if (li && li.hasAttribute("data-channel-idx")) {
        const idx = li.getAttribute("data-channel-idx");
        this.switchChannel(parseInt(idx, 10));
      }
    });
  }

  switchChannel(idx) {
    this.activeChannelIdx = idx;
    this.activeDmTarget = null;
    this.activeDmName = null;

    if (this.dom.sidebarChannelList) {
      this.dom.sidebarChannelList.classList.remove("mobile-open");
    }

    document.querySelectorAll("#channelListUi li").forEach((li) => {
      const chIdx = parseInt(li.getAttribute("data-channel-idx") || "-1", 10);
      li.classList.toggle("active", chIdx === idx);
    });
    document.querySelectorAll("#dmListUi li").forEach((li) => li.classList.remove("active"));

    if (idx === 0) {
      this.dom.chatActiveTitle.textContent = "Canal 0 (Public / Broadcast)";
      if (this.dom.chatSecurityChip) this.dom.chatSecurityChip.textContent = "🔓 Abierto";
      this.dom.chatActiveSub.textContent = "Canal público de difusión general";
    } else {
      const chObj = this.channelsList.find((c) => c.index === idx);
      const chName = chObj ? chObj.name : `Canal Privado ${this.activeChannelIdx}`;
      this.dom.chatActiveTitle.textContent = `Canal ${this.activeChannelIdx} (${chName})`;
      if (this.dom.chatSecurityChip) this.dom.chatSecurityChip.textContent = "🔒 Privado";
      this.dom.chatActiveSub.textContent = `Canal privado • ${chName}`;
    }

    this.renderCurrentConversation();
  }

  setDmTarget(pubkey, name) {
    this.activeDmTarget = pubkey;
    this.activeDmName = name || pubkey;

    if (this.dom.sidebarChannelList) {
      this.dom.sidebarChannelList.classList.remove("mobile-open");
    }

    this.addDmContact(pubkey, this.activeDmName);

    document.querySelectorAll("#channelListUi li").forEach((li) => li.classList.remove("active"));
    document.querySelectorAll("#dmListUi li").forEach((li) => {
      li.classList.toggle("active", li.getAttribute("data-pubkey") === pubkey);
      li.setAttribute("aria-selected", String(li.getAttribute("data-pubkey") === pubkey));
    });

    this.dom.chatActiveTitle.textContent = `${this.activeDmName}`;
    if (this.dom.chatSecurityChip) this.dom.chatSecurityChip.textContent = "🔒 Privado";
    this.dom.chatActiveSub.textContent = `Mensaje directo punto a punto • ${this.activeDmName}`;

    this.renderCurrentConversation();
  }

  openDmConversation(pubkey, name) {
    const navBtn = document.querySelector('.nav-btn[data-tab="tab-chat"]');
    if (navBtn) navBtn.click();
    this.conversationsWithMessages.add(pubkey);
    this.addDmContact(pubkey, name);
    this.setDmTarget(pubkey, name);
    if (this.dom.chatInputText) this.dom.chatInputText.focus();
  }

  renderCurrentConversation() {
    this.dom.chatMessageFeed.innerHTML = "";
    const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    const messages = this.channelFeeds.get(feedKey) || [];

    if (messages.length === 0) {
      return;
    }

    for (const msg of messages) {
      this.appendChatMessage(msg);
    }
  }

  appendChatMessage(msg) {
    if (this.dom.chatMessageFeed.querySelector(".chat-welcome-card")) {
      this.dom.chatMessageFeed.innerHTML = "";
    }

    const row = document.createElement("div");
    row.className = `message-bubble-row ${msg.is_outgoing ? "outgoing" : "incoming"}`;

    const timeStr = new Date(msg.timestamp || Date.now()).toLocaleTimeString();
    const sender = msg.sender_name || msg.sender || "Anónimo";
    const rssi = msg.metrics?.rssi || msg.rssi;
    const snr = msg.metrics?.snr || msg.snr;

    row.innerHTML = `
      <div class="msg-meta">
        <strong>${this.escapeHtml(sender)}</strong>
        <span>${timeStr}</span>
      </div>
      <div class="msg-bubble">${this.escapeHtml(msg.text)}</div>
      <div class="msg-footer">
        ${rssi !== undefined ? `<span class="signal-chip">📶 ${rssi} dBm / ${snr} dB</span>` : ""}
        <span>${msg.is_outgoing ? "📡 TX" : "📥 RX"}</span>
      </div>
    `;

    this.dom.chatMessageFeed.appendChild(row);
    this.dom.chatMessageFeed.scrollTop = this.dom.chatMessageFeed.scrollHeight;
  }

  initWebSocket() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      this.dom.wsStatus.querySelector(".status-dot").className = "status-dot connected";
      this.dom.wsStatus.querySelector(".status-text").textContent = "En línea (WS)";
    };

    this.ws.onclose = () => {
      this.dom.wsStatus.querySelector(".status-dot").className = "status-dot disconnected";
      this.dom.wsStatus.querySelector(".status-text").textContent = "Reconectando...";
      clearTimeout(this.wsReconnectTimer);
      this.wsReconnectTimer = setTimeout(() => this.initWebSocket(), this.wsReconnectInterval);
    };

    this.ws.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data);
        this.handleIncomingLiveEvent(payload);
      } catch (err) {
        console.error("Error parseando WebSocket payload:", err);
      }
    };
  }

  addDmContact(pubkey, name, role = "CLIENT") {
    if (!pubkey || pubkey === "unknown" || !this.dom.dmListUi) return;

    const roleStr = (role || "CLIENT").toUpperCase();
    const isClient = roleStr === "CLIENT" || roleStr === "CHAT" || role === "1" || role === 1;
    if (!isClient) return;

    // Solo mostrar si tiene mensajes o si es la conversación actualmente abierta
    const feedKey = `dm_${pubkey}`;
    const hasMessages = this.conversationsWithMessages.has(pubkey) ||
      (this.channelFeeds.has(feedKey) && this.channelFeeds.get(feedKey).length > 0) ||
      this.activeDmTarget === pubkey;

    if (!hasMessages) return;

    const emptyHint = this.dom.dmListUi.querySelector(".empty-hint");
    if (emptyHint) emptyHint.remove();

    let li = this.dom.dmListUi.querySelector(`li[data-pubkey="${pubkey}"]`);
    const cleanName = name || pubkey;
    const isAct = this.activeDmTarget === pubkey;
    const roleIcon = "👤";

    if (!li) {
      li = document.createElement("li");
      li.className = `channel-item ${isAct ? "active" : ""}`;
      li.setAttribute("data-pubkey", pubkey);
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(isAct));
      li.innerHTML = `
        <span class="ch-badge">${roleIcon}</span>
        <span class="ch-name" title="${this.escapeHtml(cleanName)}">${this.escapeHtml(cleanName)}</span>
        <div class="ch-actions">
          <button type="button" class="btn-item-delete" title="Cerrar conversación de la lista" data-del-dm="${pubkey}">✕</button>
        </div>
      `;
      li.addEventListener("click", () => this.setDmTarget(pubkey, cleanName));

      const delBtn = li.querySelector(".btn-item-delete");
      if (delBtn) {
        delBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this.conversationsWithMessages.delete(pubkey);
          li.remove();
          if (this.activeDmTarget === pubkey) {
            this.switchChannel(0);
          }
          this.updateDmBadgeCount();
        });
      }

      this.dom.dmListUi.appendChild(li);
    } else {
      li.classList.toggle("active", isAct);
      li.setAttribute("aria-selected", String(isAct));
      const nameEl = li.querySelector(".ch-name");
      if (nameEl) nameEl.textContent = cleanName;
    }

    this.updateDmBadgeCount();
  }

  updateDmBadgeCount() {
    if (!this.dom.dmListUi || !this.dom.dmCountBadge) return;
    const items = this.dom.dmListUi.querySelectorAll("li.channel-item");
    this.dom.dmCountBadge.textContent = items.length;
    if (items.length === 0 && !this.dom.dmListUi.querySelector(".empty-hint")) {
      const hint = document.createElement("li");
      hint.className = "empty-hint";
      hint.textContent = "Sin conversaciones activas";
      this.dom.dmListUi.appendChild(hint);
    }
  }

  updateHeaderMetrics(metrics) {
    if (!metrics) return;
    const nodeCount = metrics.node_count ?? metrics.known_mesh_nodes;
    const rxCount = metrics.rx_count ?? metrics.total_rx_packets;
    const txCount = metrics.tx_count ?? metrics.total_tx_packets;
    const errorRate = metrics.error_rate !== undefined ? metrics.error_rate : (metrics.total_tx_errors !== undefined ? metrics.total_tx_errors : undefined);
    const queueDepth = metrics.queue_depth ?? metrics.tx_queue_depth;

    if (nodeCount !== undefined && this.dom.headerNodeCount) {
      this.dom.headerNodeCount.textContent = nodeCount;
    }
    if (rxCount !== undefined && this.dom.headerRxCount) {
      this.dom.headerRxCount.textContent = rxCount;
    }
    if (txCount !== undefined && this.dom.headerTxCount) {
      this.dom.headerTxCount.textContent = txCount;
    }
    if (errorRate !== undefined && this.dom.headerErrorRate) {
      const errStr = typeof errorRate === "number" ? `${errorRate}%` : `${errorRate}`;
      this.dom.headerErrorRate.textContent = errStr.endsWith("%") ? errStr : `${errStr}%`;
    }
    if (queueDepth !== undefined && this.dom.headerQueueDepth) {
      this.dom.headerQueueDepth.textContent = queueDepth;
    }
  }

  createMapMarkerIcon(type = "default", label = "") {
    let colorClass = "marker-blue";
    let iconSymbol = "📍";
    let pinColor = "#0284c7";

    if (type === "local") {
      colorClass = "marker-green";
      iconSymbol = "🏠";
      pinColor = "#10b981";
    } else if (type === "selected") {
      colorClass = "marker-red";
      iconSymbol = "🎯";
      pinColor = "#ef4444";
    } else if (type === "repeater") {
      colorClass = "marker-orange";
      iconSymbol = "🏔️";
      pinColor = "#f59e0b";
    } else if (type === "sensor") {
      colorClass = "marker-purple";
      iconSymbol = "📡";
      pinColor = "#a855f7";
    }

    const html = `
      <div class="custom-map-pin ${colorClass}">
        <div class="pin-head" style="background-color: ${pinColor};">
          <span class="pin-symbol">${iconSymbol}</span>
        </div>
        <div class="pin-pointer" style="border-top-color: ${pinColor};"></div>
        <div class="pin-pulse"></div>
      </div>
    `;

    return L.divIcon({
      className: `leaflet-custom-div-icon ${colorClass}`,
      html: html,
      iconSize: [32, 40],
      iconAnchor: [16, 40],
      popupAnchor: [0, -38],
    });
  }

  selectMapNode(pubkey) {
    if (!this.map || !this.mapMarkers.has(pubkey)) return;
    this.selectedMapNodePk = pubkey;

    // 1. Actualizar iconos de todos los marcadores en el mapa
    for (const [pk, marker] of this.mapMarkers.entries()) {
      const node = this.knownNodes.get(pk) || {};
      const isLocal = (this.localNodePubkey && pk.toLowerCase() === this.localNodePubkey.toLowerCase()) || Boolean(node.is_local) || node.role === "LOCAL" || pk === "local";

      if (pk === pubkey) {
        // Nodo Seleccionado: ROJO siempre
        marker.setIcon(this.createMapMarkerIcon("selected", node.name || node.alias));
        marker.setZIndexOffset(1000);
      } else if (isLocal) {
        // Nodo Local: VERDE siempre
        marker.setIcon(this.createMapMarkerIcon("local", node.name || node.alias));
        marker.setZIndexOffset(900);
      } else {
        const role = (node.role || "CLIENT").toUpperCase();
        let defaultType = "default";
        if (role === "REPEATER" || role === "ROUTER" || node.type === 2) defaultType = "repeater";
        else if (role === "SENSOR" || node.type === 4) defaultType = "sensor";
        marker.setIcon(this.createMapMarkerIcon(defaultType, node.name || node.alias));
        marker.setZIndexOffset(100);
      }
    }

    // 2. Centrar mapa y abrir popup del nodo seleccionado
    const targetMarker = this.mapMarkers.get(pubkey);
    const targetLatLng = targetMarker.getLatLng();
    this.map.flyTo(targetLatLng, Math.max(this.map.getZoom(), 13), {
      animate: true,
      duration: 0.7,
    });
    targetMarker.openPopup();

    // 3. Resaltar en la lista lateral del mapa
    document.querySelectorAll(".map-node-item").forEach((el) => {
      const itemPk = el.getAttribute("data-pk");
      const dotEl = el.querySelector(".map-node-dot");
      const isLocalItem = el.classList.contains("is-local");

      if (itemPk === pubkey) {
        el.classList.add("selected");
        if (dotEl) dotEl.textContent = "🔴";
        el.scrollIntoView({ block: "nearest", behavior: "smooth" });
      } else {
        el.classList.remove("selected");
        if (dotEl) dotEl.textContent = isLocalItem ? "🟢" : "📍";
      }
    });
  }

  initLeafletMap() {
    const mapEl = document.getElementById("liveGpsMap");
    if (!mapEl) return;

    if (typeof L === "undefined") {
      // Reintentar si Leaflet JS aún se está cargando
      if (!this._leafletRetryCount) this._leafletRetryCount = 0;
      if (this._leafletRetryCount < 20) {
        this._leafletRetryCount++;
        setTimeout(() => this.initLeafletMap(), 250);
      }
      return;
    }

    if (this.map) {
      try {
        this.map.invalidateSize();
      } catch (_) {}
      return;
    }

    try {
      this.map = L.map("liveGpsMap", {
        zoomControl: true,
        attributionControl: true,
      }).setView([20.15, -75.20], 12);

      // Proveedor primario de mapas oscuros (CartoDB Dark Matter)
      const primaryLayer = L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
        attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
        subdomains: "abcd",
      });

      primaryLayer.on("tileerror", () => {
        // Fallback a OpenStreetMap estándar si CartoDB falla
        if (!this._osmFallbackAdded) {
          this._osmFallbackAdded = true;
          L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
            attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
            maxZoom: 19,
          }).addTo(this.map);
        }
      });

      primaryLayer.addTo(this.map);

      // Si ya hay nodos conocidos en memoria, renderizarlos inmediatamente en el mapa
      if (this.knownNodes && this.knownNodes.size > 0) {
        this.renderNodesDirectory(Array.from(this.knownNodes.values()));
      }
    } catch (err) {
      console.warn("No se pudo inicializar el mapa Leaflet:", err);
    }
  }

  async fetchInitialData() {
    await this.fetchLocalNodeConfig();
    const loadStatus = async () => {
      try {
        const [statusRes, nodesRes, channelsRes] = await Promise.all([
          fetch("/api/status").then((r) => r.json()),
          fetch("/api/nodes").then((r) => r.json()),
          fetch("/api/channels").then((r) => r.json()).catch(() => ({ status: "ok", data: [] })),
        ]);

        if (statusRes.status === "ok" && statusRes.data) {
          this.updateHeaderMetrics(statusRes.data);
        }

        if (nodesRes.status === "ok" && nodesRes.data) {
          this.renderNodesDirectory(nodesRes.data);
          this.populateRepeaterDropdown(nodesRes.data);
        }

        if (channelsRes.status === "ok" && channelsRes.data && channelsRes.data.length > 0) {
          this.renderChannelsList(channelsRes.data);
        }

        this.fetchAnalytics();
      } catch (err) {
        console.warn("Fallo cargando datos REST:", err);
      }
    };

    await loadStatus();

    // Heartbeat de métricas periódico de respaldo cada 4 segundos
    setInterval(async () => {
      try {
        const res = await fetch("/api/status");
        const json = await res.json();
        if (json.status === "ok" && json.data) {
          this.updateHeaderMetrics(json.data);
        }
      } catch (_) {}
    }, 4000);
  }

  renderChannelsList(channels) {
    this.channelsList = channels;
    if (!this.dom.channelListUi) return;
    this.dom.channelListUi.innerHTML = "";
    for (const ch of channels) {
      const li = document.createElement("li");
      li.className = `channel-item ${ch.index === this.activeChannelIdx && !this.activeDmTarget ? "active" : ""}`;
      li.setAttribute("data-channel-idx", ch.index);
      const isPub = ch.is_public || ch.index === 0;
      const icon = isPub ? "🔓" : "🔒";

      const deleteBtnHtml = ch.index > 0
        ? `<button type="button" class="btn-item-delete" title="Eliminar canal del dispositivo" data-del-idx="${ch.index}">🗑️</button>`
        : "";

      li.innerHTML = `
        <span class="ch-badge">Ch ${ch.index}</span>
        <span class="ch-name" title="${this.escapeHtml(ch.name)}">${this.escapeHtml(ch.name)}</span>
        <div class="ch-actions">
          <span class="ch-lock" title="${isPub ? 'Canal Público' : 'Canal Privado'}">${icon}</span>
          ${deleteBtnHtml}
        </div>
      `;
      li.addEventListener("click", () => this.switchChannel(ch.index));

      const delBtn = li.querySelector(".btn-item-delete");
      if (delBtn) {
        delBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this.deleteChannel(ch.index, ch.name);
        });
      }

      this.dom.channelListUi.appendChild(li);
    }
  }

  renderNodesDirectory(nodes) {
    const contactsGrid = this.dom.contactsGridUi || document.getElementById("contactsGridUi");
    const unifiedNodesGrid = this.dom.nodesUnifiedGridUi || document.getElementById("nodesUnifiedGridUi");
    const mapList = document.getElementById("mapNodesList");
    if (mapList) mapList.innerHTML = "";

    if (!nodes || nodes.length === 0) {
      if (contactsGrid) contactsGrid.innerHTML = '<div class="empty-state">No hay contactos registrados en el dispositivo.</div>';
      if (unifiedNodesGrid) unifiedNodesGrid.innerHTML = '<div class="empty-state">No se han descubierto nodos en la malla LoRa.</div>';
      return;
    }

    // Deduplicación inteligente: fusionar entradas que compartan prefijo de clave (>=8 chars) o mismo nombre
    const deduplicatedNodes = [];
    for (const rawNode of nodes) {
      if (!rawNode || !rawNode.public_key) continue;
      const normPk = String(rawNode.public_key).toLowerCase().trim();
      const normName = String(rawNode.name || rawNode.alias || "").toLowerCase().trim();

      let matchIndex = -1;
      for (let i = 0; i < deduplicatedNodes.length; i++) {
        const existing = deduplicatedNodes[i];
        const exPk = String(existing.public_key).toLowerCase().trim();
        const exName = String(existing.name || existing.alias || "").toLowerCase().trim();

        const pkMatch = exPk === normPk ||
          (exPk.length >= 8 && normPk.length >= 8 && (exPk.startsWith(normPk) || normPk.startsWith(exPk))) ||
          (normPk.length === 12 && exPk.startsWith(normPk.slice(0, 12))) ||
          (exPk.length === 12 && normPk.startsWith(exPk.slice(0, 12)));

        const nameMatch = normName && exName === normName &&
          (exPk.startsWith(normPk.slice(0, 6)) || normPk.startsWith(exPk.slice(0, 6)));

        if (pkMatch || nameMatch) {
          matchIndex = i;
          break;
        }
      }

      if (matchIndex >= 0) {
        const prev = deduplicatedNodes[matchIndex];
        const canonicalPk = normPk.length >= prev.public_key.length ? normPk : prev.public_key;
        deduplicatedNodes[matchIndex] = {
          ...prev,
          ...rawNode,
          public_key: canonicalPk,
          battery_pct: rawNode.battery_pct !== undefined && rawNode.battery_pct !== null ? rawNode.battery_pct : (rawNode.battery !== undefined ? rawNode.battery : prev.battery_pct),
          last_rssi: rawNode.last_rssi !== undefined && rawNode.last_rssi !== -80 ? rawNode.last_rssi : prev.last_rssi,
          last_snr: rawNode.last_snr !== undefined && rawNode.last_snr !== 10.0 ? rawNode.last_snr : prev.last_snr,
        };
      } else {
        deduplicatedNodes.push(rawNode);
      }
    }

    if (contactsGrid) contactsGrid.innerHTML = "";
    if (unifiedNodesGrid) unifiedNodesGrid.innerHTML = "";

    const contactsFrag = document.createDocumentFragment();
    const nodesFrag = document.createDocumentFragment();
    const mapFrag = document.createDocumentFragment();

    const mapBounds = [];
    let clientContactCount = 0;
    let totalCount = 0;
    let repeaterCount = 0;
    let sensorCount = 0;
    let roomCount = 0;
    let clientCount = 0;

    for (const node of deduplicatedNodes) {
      this.knownNodes.set(node.public_key, node);
      totalCount++;

      const roleStr = (node.role || "CLIENT").toUpperCase();
      const isRepeater = roleStr === "REPEATER" || roleStr === "ROUTER" || node.type === 2 || node.adv_type === 2;
      const isSensor = roleStr === "SENSOR" || node.type === 4 || node.adv_type === 4 || !!(node.temperature_c || node.temp || node.humidity_pct || node.humidity);
      const isRoom = roleStr === "ROOM" || node.type === 3 || node.adv_type === 3;
      const isClient = !isRepeater && !isSensor && !isRoom;

      if (isRepeater) repeaterCount++;
      else if (isSensor) sensorCount++;
      else if (isRoom) roomCount++;
      else clientCount++;

      const cleanName = node.alias || node.name || `Node_${node.public_key.slice(0, 6)}`;
      const shortPk = node.public_key.length > 16 ? `${node.public_key.slice(0, 10)}...${node.public_key.slice(-4)}` : node.public_key;
      const snrVal = node.snr !== undefined ? node.snr : (node.last_snr !== undefined ? node.last_snr : "--");
      const rssiVal = node.rssi !== undefined ? node.rssi : (node.last_rssi !== undefined ? node.last_rssi : "--");
      const batVal = node.battery !== undefined ? `${node.battery}%` : (node.battery_pct !== undefined && node.battery_pct !== null ? `${node.battery_pct}%` : "--");

      // Si ya hay una conversación con mensajes para este nodo (y es cliente), mantenerlo en la barra lateral de chat
      const feedKey = `dm_${node.public_key}`;
      if (isClient && (this.conversationsWithMessages.has(node.public_key) ||
          (this.channelFeeds.has(feedKey) && this.channelFeeds.get(feedKey).length > 0) ||
          this.activeDmTarget === node.public_key)) {
        this.addDmContact(node.public_key, cleanName, node.role);
      }

      // 1. SOLO renderizar en la libreta de Contactos si es tipo CLIENT
      if (isClient && contactsGrid) {
        clientContactCount++;
        const cCard = document.createElement("div");
        cCard.className = "contact-item-card";
        cCard.setAttribute("data-pk", node.public_key);
        const searchData = `${node.alias || ''} ${node.name || ''} ${node.public_key}`.toLowerCase();
        cCard.setAttribute("data-search", searchData);

        cCard.innerHTML = `
          <div class="contact-card-header">
            <div class="contact-avatar">👤</div>
            <div class="contact-meta">
              <span class="contact-name" title="${this.escapeHtml(cleanName)}">${this.escapeHtml(cleanName)}</span>
              <span class="contact-pubkey font-mono" title="${this.escapeHtml(node.public_key)}">
                ${this.escapeHtml(shortPk)}
                <button type="button" class="btn-copy-pk" title="Copiar clave pública">📋</button>
              </span>
            </div>
            <span class="contact-battery-chip" title="Nivel de batería">🔋 ${batVal}</span>
          </div>
          <div class="contact-card-chips">
            <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal} dB</strong></span>
            <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal} dBm</strong></span>
            <span class="stat-pill" title="Saltos de retransmisión">🦘 <strong>${node.hops !== undefined ? node.hops : 0} ${(node.hops === 1 ? 'salto' : 'saltos')}</strong></span>
          </div>
          <div class="contact-card-actions">
            <button type="button" class="btn-contact-action btn-contact-dm" title="Abrir chat en Mensajería">💬 DM</button>
            <button type="button" class="btn-contact-action btn-contact-qr" title="Exportar tarjeta o código QR">📤 QR</button>
            <button type="button" class="btn-contact-action btn-contact-del" title="Eliminar del dispositivo">🗑️</button>
          </div>
        `;

        const copyBtn = cCard.querySelector(".btn-copy-pk");
        if (copyBtn) {
          copyBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            navigator.clipboard.writeText(node.public_key);
            this.showToast("📋 Clave pública copiada", "success");
          });
        }

        cCard.querySelector(".btn-contact-dm").addEventListener("click", () => {
          this.openDmConversation(node.public_key, cleanName);
        });

        cCard.querySelector(".btn-contact-qr").addEventListener("click", () => {
          const payload = { type: "contact", public_key: node.public_key, name: cleanName, role: "CLIENT" };
          const uri = `meshcore://contact?pubkey=${encodeURIComponent(node.public_key)}&name=${encodeURIComponent(cleanName)}&role=CLIENT`;
          this.renderQrModal(`👥 Contacto: ${cleanName}`, uri, payload);
        });

        cCard.querySelector(".btn-contact-del").addEventListener("click", () => {
          this.deleteContact(node.public_key, cleanName);
        });

        contactsFrag.appendChild(cCard);
      }

      // 2. Renderizar en la vista unificada "Nodos" (TODOS los nodos con tarjetas adaptativas)
      if (unifiedNodesGrid) {
        const nCard = document.createElement("div");
        const roleClass = isSensor ? "role-sensor-card" : isRepeater ? "role-repeater-card" : isRoom ? "role-room-card" : "role-client-card";
        const avatarClass = isSensor ? "avatar-sensor" : isRepeater ? "avatar-repeater" : isRoom ? "avatar-room" : "avatar-client";
        const avatarIcon = isSensor ? "📡" : isRepeater ? "🏔️" : isRoom ? "🏠" : "👤";
        const roleLabel = isSensor ? "SENSOR" : isRepeater ? "REPEATER" : isRoom ? "ROOM" : "CLIENT";
        const roleBadgeClass = isSensor ? "role-sensor" : isRepeater ? "role-repeater" : isRoom ? "role-room" : "role-client";

        // Calcular estado de conectividad en base a last_seen
        const nowSec = Date.now() / 1000;
        let lastSeenSec = node.last_seen;
        if (typeof lastSeenSec === "string" && !isNaN(Number(lastSeenSec))) {
          lastSeenSec = Number(lastSeenSec);
        }

        let statusLabel = "En Línea";
        let statusClass = "status-online";
        let statusDot = "🟢";
        let timeAgoStr = "Ahora";

        if (lastSeenSec && typeof lastSeenSec === "number" && lastSeenSec > 1000000000) {
          const diff = nowSec - lastSeenSec;
          if (diff < 1800) {
            statusLabel = "En Línea";
            statusClass = "status-online";
            statusDot = "🟢";
            timeAgoStr = diff < 60 ? "Hace un momento" : `Hace ${Math.floor(diff / 60)}m`;
          } else if (diff < 7200) {
            statusLabel = "Inactivo";
            statusClass = "status-idle";
            statusDot = "🟡";
            timeAgoStr = `Hace ${Math.floor(diff / 60)}m`;
          } else {
            statusLabel = "Fuera de línea";
            statusClass = "status-offline";
            statusDot = "🔴";
            const hours = Math.floor(diff / 3600);
            timeAgoStr = hours < 24 ? `Hace ${hours}h` : `Hace ${Math.floor(hours / 24)}d`;
          }
        }

        const isOffline = statusClass === "status-offline";
        nCard.className = `node-card ${roleClass} ${isOffline ? "node-card-offline" : ""}`;
        nCard.setAttribute("data-role", roleLabel);
        nCard.setAttribute("data-pk", node.public_key);
        const searchData = `${node.alias || ''} ${node.name || ''} ${node.public_key} ${roleLabel}`.toLowerCase();
        nCard.setAttribute("data-search", searchData);

        let bodyHtml = "";

        if (isSensor) {
          const temp = node.temperature_c !== undefined ? node.temperature_c : (node.temp !== undefined ? node.temp : "--");
          const hum = node.humidity_pct !== undefined ? node.humidity_pct : (node.humidity !== undefined ? node.humidity : "--");
          const press = node.pressure_hpa !== undefined ? node.pressure_hpa : (node.pressure !== undefined ? node.pressure : "--");
          bodyHtml = `
            <div class="node-telemetry-panel">
              <div class="telemetry-sensors-grid">
                <div class="sensor-box">
                  <span class="sensor-box-label">Temp</span>
                  <span class="sensor-box-value sensor-temp-val">${temp}°C</span>
                </div>
                <div class="sensor-box">
                  <span class="sensor-box-label">Humedad</span>
                  <span class="sensor-box-value sensor-hum-val">${hum}%</span>
                </div>
                <div class="sensor-box">
                  <span class="sensor-box-label">Presión</span>
                  <span class="sensor-box-value sensor-press-val">${press} hPa</span>
                </div>
              </div>
            </div>
            <div class="node-rf-strip">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal} dB</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal} dBm</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${node.hops || 0} saltos</strong></span>
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-secondary btn-sm btn-node-primary btn-sensor-qr" title="Exportar QR del sensor">📤 QR Telemetría</button>
            </div>
          `;
        } else if (isRepeater) {
          bodyHtml = `
            <div class="node-telemetry-panel">
              <div style="font-size: 12px; display: flex; justify-content: space-between; color: var(--text-main);">
                <span>🏔️ Router de Malla</span>
                <strong style="color: #c084fc;">TX: ${node.tx_power || 20} dBm</strong>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between;">
                <span>Reenvío: Activo</span>
                <span>Hop Limit: ${node.hop_limit || 3}</span>
              </div>
            </div>
            <div class="node-rf-strip">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal} dB</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal} dBm</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${node.hops || 0} saltos</strong></span>
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-primary btn-sm btn-node-primary btn-manage-node-repeater">🎛️ Administrar</button>
            </div>
          `;
        } else if (isRoom) {
          bodyHtml = `
            <div class="node-telemetry-panel">
              <div style="font-size: 12px; color: var(--text-main); font-weight: 600;">🏠 Servidor de Sala / BBS</div>
              <div style="font-size: 11px; color: var(--text-muted);">Canal: ${node.channel || "General"}</div>
            </div>
            <div class="node-rf-strip">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal} dB</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal} dBm</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${node.hops || 0} saltos</strong></span>
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-secondary btn-sm btn-node-primary btn-room-channel">💬 Ver Canal</button>
            </div>
          `;
        } else {
          // CLIENT
          bodyHtml = `
            <div class="node-rf-strip" style="margin-top: 4px;">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal} dB</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal} dBm</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${node.hops || 0} saltos</strong></span>
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-primary btn-sm btn-node-primary btn-client-dm">💬 Iniciar Chat DM</button>
              <button type="button" class="btn-secondary btn-sm btn-node-secondary btn-client-qr" title="Ver código QR">📤 QR</button>
            </div>
          `;
        }

        nCard.innerHTML = `
          <div class="node-card-header">
            <div class="node-card-avatar ${avatarClass}">${avatarIcon}</div>
            <div class="node-card-info">
              <div class="node-card-title-row">
                <span class="node-card-name" title="${this.escapeHtml(cleanName)}">${this.escapeHtml(cleanName)}</span>
                <div style="display: flex; gap: 4px; align-items: center;">
                  <span class="node-status-chip ${statusClass}" title="${timeAgoStr}">${statusDot} ${statusLabel}</span>
                  <span class="node-role-badge ${roleBadgeClass}">${roleLabel}</span>
                </div>
              </div>
              <span class="node-card-pubkey font-mono" title="${this.escapeHtml(node.public_key)}">
                ${this.escapeHtml(shortPk)}
                <button type="button" class="btn-copy-pk" title="Copiar clave pública">📋</button>
              </span>
            </div>
            <span class="contact-battery-chip" title="Nivel de batería">🔋 ${batVal}</span>
          </div>
          ${bodyHtml}
        `;

        const copyBtn = nCard.querySelector(".btn-copy-pk");
        if (copyBtn) {
          copyBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            navigator.clipboard.writeText(node.public_key);
            this.showToast("📋 Clave pública copiada", "success");
          });
        }

        const btnManage = nCard.querySelector(".btn-manage-node-repeater");
        if (btnManage) {
          btnManage.addEventListener("click", () => {
            this.openRepeaterAdminModal(node.public_key, cleanName);
          });
        }

        const btnDm = nCard.querySelector(".btn-client-dm");
        if (btnDm) {
          btnDm.addEventListener("click", () => {
            this.openDmConversation(node.public_key, cleanName);
          });
        }

        const btnQr = nCard.querySelector(".btn-client-qr") || nCard.querySelector(".btn-sensor-qr");
        if (btnQr) {
          btnQr.addEventListener("click", () => {
            const payload = { type: isSensor ? "sensor" : "contact", public_key: node.public_key, name: cleanName, role: roleLabel };
            const uri = `meshcore://${isSensor ? "sensor" : "contact"}?pubkey=${encodeURIComponent(node.public_key)}&name=${encodeURIComponent(cleanName)}&role=${roleLabel}`;
            this.renderQrModal(`👥 ${cleanName}`, uri, payload);
          });
        }

        const btnRoom = nCard.querySelector(".btn-room-channel");
        if (btnRoom) {
          btnRoom.addEventListener("click", () => {
            const navBtn = document.querySelector('.nav-btn[data-tab="tab-chat"]');
            if (navBtn) navBtn.click();
          });
        }

        nodesFrag.appendChild(nCard);
      }

      // 3. Marcadores y Lista Lateral del Mapa Leaflet
      const extractCoord = (...vals) => {
        for (const v of vals) {
          if (v !== undefined && v !== null && v !== "") {
            const num = parseFloat(v);
            if (!isNaN(num) && num !== 0.0) return num;
          }
        }
        return null;
      };

      const lat = extractCoord(
        node.latitude,
        node.lat,
        node.gps_lat,
        node.gps?.latitude,
        node.gps?.lat,
        node.position?.latitude,
        node.position?.lat
      );
      const lon = extractCoord(
        node.longitude,
        node.lon,
        node.gps_lon,
        node.gps?.longitude,
        node.gps?.lon,
        node.position?.longitude,
        node.position?.lon
      );

      const hasGps = lat !== null && lon !== null && lat >= -90.0 && lat <= 90.0 && lon >= -180.0 && lon <= 180.0;
      const isLocal = (this.localNodePubkey && node.public_key.toLowerCase() === this.localNodePubkey.toLowerCase()) || Boolean(node.is_local) || node.role === "LOCAL" || node.public_key === "local";
      const isSelected = this.selectedMapNodePk === node.public_key;

      if (hasGps) {
        geoLocatedCount++;
        mapBounds.push([lat, lon]);

        if (this.map && typeof L !== "undefined") {
          let iconType = "default";
          if (isSelected) iconType = "selected";
          else if (isLocal) iconType = "local";
          else if (isRepeater) iconType = "repeater";
          else if (isSensor) iconType = "sensor";

          const popupContent = `
            <div class="custom-map-popup">
              <div class="popup-title">
                ${isLocal ? '🟢 <strong>' + this.escapeHtml(cleanName) + ' (Local)</strong>' : (isSelected ? '🎯 <strong>' + this.escapeHtml(cleanName) + ' (Seleccionado)</strong>' : '📍 <strong>' + this.escapeHtml(cleanName) + '</strong>')}
              </div>
              <div class="popup-info">
                <div><span>Rol:</span> <strong>${roleStr}</strong></div>
                <div><span>SNR:</span> <strong>${snrVal} dB</strong></div>
                <div><span>Batería:</span> <strong>${batVal}</strong></div>
                <div><span>GPS:</span> <code>${lat.toFixed(4)}, ${lon.toFixed(4)}</code> (${node.altitude_m || node.alt || 0}m)</div>
              </div>
            </div>
          `;

          if (!this.mapMarkers.has(node.public_key)) {
            const marker = L.marker([lat, lon], {
              icon: this.createMapMarkerIcon(iconType, cleanName),
            }).addTo(this.map);

            marker.bindPopup(popupContent);
            marker.on("click", () => {
              this.selectMapNode(node.public_key);
            });

            this.mapMarkers.set(node.public_key, marker);
          } else {
            const existingMarker = this.mapMarkers.get(node.public_key);
            existingMarker.setLatLng([lat, lon]);
            existingMarker.setIcon(this.createMapMarkerIcon(iconType, cleanName));
            existingMarker.setPopupContent(popupContent);
          }
        }
      }

      // Renderizar SIEMPRE en la lista lateral del mapa (con o sin GPS)
      if (mapList) {
        const item = document.createElement("div");
        item.className = `map-node-item ${isLocal ? "is-local" : ""} ${isSelected ? "selected" : ""} ${hasGps ? "has-gps" : "no-gps"}`;
        item.setAttribute("data-pk", node.public_key);

        let statusDot = isSelected ? "🔴" : (isLocal ? "🟢" : (hasGps ? "📍" : "🛰️"));
        let roleBadge = isLocal
          ? `<span class="badge-pill badge-success" style="font-size: 10px;">LOCAL</span>`
          : `<span class="badge-pill" style="font-size: 10px;">${roleStr}</span>`;

        const coordsText = hasGps
          ? `🌐 ${lat.toFixed(4)}, ${lon.toFixed(4)}`
          : `<span style="color: var(--text-muted); font-style: italic;">🛰️ Sin fijación GPS</span>`;

        item.innerHTML = `
          <div class="map-node-item-header">
            <span class="map-node-dot">${statusDot}</span>
            <strong class="map-node-name" title="${this.escapeHtml(cleanName)}">${this.escapeHtml(cleanName)}</strong>
            ${roleBadge}
          </div>
          <div class="map-node-coords">
            <span>${coordsText}</span>
            <span>📶 ${snrVal} dB</span>
          </div>
        `;

        item.addEventListener("click", () => {
          if (hasGps) {
            this.selectMapNode(node.public_key);
          } else {
            this.showToast(`📡 ${cleanName} activo por RF (sin coordenadas GPS fijadas)`, "info");
            if (isRepeater) {
              this.openRepeaterAdminModal(node.public_key, cleanName);
            }
          }
        });

        mapFrag.appendChild(item);
      }
    }

    // Volcar fragmentos en el DOM en un único reflow
    if (contactsGrid) contactsGrid.appendChild(contactsFrag);
    if (unifiedNodesGrid) unifiedNodesGrid.appendChild(nodesFrag);
    if (mapList) mapList.appendChild(mapFrag);

    // Actualizar indicador de conteo en panel lateral del mapa
    const mapCountEl = document.getElementById("mapNodesCount");
    if (mapCountEl) {
      mapCountEl.textContent = `${totalCount} (${geoLocatedCount} en mapa)`;
    }

    // Auto-ajustar mapa a los nodos descubiertos si hay posiciones
    if (this.map && mapBounds.length > 0) {
      try {
        if (!this.selectedMapNodePk) {
          this.map.fitBounds(mapBounds, { padding: [40, 40], maxZoom: 14 });
        }
      } catch (_) {}
    }

    // Actualizar contadores de filtros
    const countAllEl = document.getElementById("countAllNodes");
    if (countAllEl) countAllEl.textContent = String(totalCount);
    const countRepEl = document.getElementById("countRepeaters");
    if (countRepEl) countRepEl.textContent = String(repeaterCount);
    const countSensEl = document.getElementById("countSensors");
    if (countSensEl) countSensEl.textContent = String(sensorCount);
    const countRoomEl = document.getElementById("countRooms");
    if (countRoomEl) countRoomEl.textContent = String(roomCount);
    const countCliEl = document.getElementById("countClients");
    if (countCliEl) countCliEl.textContent = String(clientCount);

    if (contactsGrid && clientContactCount === 0) {
      contactsGrid.innerHTML = '<div class="empty-state">No hay contactos cliente (CLIENT) registrados en el dispositivo.</div>';
    }

    if (unifiedNodesGrid && totalCount === 0) {
      unifiedNodesGrid.innerHTML = '<div class="empty-state">No se han descubierto nodos en la malla LoRa.</div>';
    }
  }

  filterContactsGrid(query) {
    const contactsGrid = this.dom.contactsGridUi || document.getElementById("contactsGridUi");
    if (!contactsGrid) return;
    const cards = contactsGrid.querySelectorAll(".contact-item-card");
    const q = (query || "").trim().toLowerCase();
    cards.forEach((card) => {
      const search = card.getAttribute("data-search") || "";
      card.style.display = search.includes(q) ? "flex" : "none";
    });
  }

  filterNodesGrid() {
    const grid = this.dom.nodesUnifiedGridUi || document.getElementById("nodesUnifiedGridUi");
    if (!grid) return;
    const cards = grid.querySelectorAll(".node-card");
    const q = (this.dom.nodesSearchInput ? this.dom.nodesSearchInput.value : "").trim().toLowerCase();
    const activeFilter = this.activeNodesFilter || "all";

    cards.forEach((card) => {
      const search = card.getAttribute("data-search") || "";
      const role = card.getAttribute("data-role") || "";
      const matchesSearch = search.includes(q);
      const matchesFilter = activeFilter === "all" || role === activeFilter;
      card.style.display = (matchesSearch && matchesFilter) ? "flex" : "none";
    });
  }

  populateRepeaterDropdown(nodes) {
    if (this.dom.activeRepeaterSelect) {
      this.dom.activeRepeaterSelect.innerHTML = '<option value="">Selecciona un repetidor...</option>';
      for (const node of nodes) {
        const opt = document.createElement("option");
        opt.value = node.public_key;
        opt.textContent = `${node.alias || node.name || node.public_key.slice(0, 8)} (${node.public_key.slice(0, 6)})`;
        this.dom.activeRepeaterSelect.appendChild(opt);
      }

      // Auto-seleccionar primer repetidor si está vacío
      if (!this.dom.activeRepeaterSelect.value && nodes.length > 0) {
        this.dom.activeRepeaterSelect.value = nodes[0].public_key;
        this.onRepeaterSelected();
      }
    }

    if (this.dom.remoteTargetNodeSelect) {
      const currentVal = this.dom.remoteTargetNodeSelect.value;
      this.dom.remoteTargetNodeSelect.innerHTML = '<option value="">-- Selecciona un repetidor o ingresa clave manual --</option>';
      for (const node of nodes) {
        const opt = document.createElement("option");
        opt.value = node.public_key;
        const isRep = node.role === "Repeater" || node.type === 2 || (node.name || "").toLowerCase().includes("rep");
        opt.textContent = `${isRep ? "🏔️ [Repetidor] " : "📻 "}${node.alias || node.name || node.public_key} (${node.public_key.slice(0, 8)})`;
        this.dom.remoteTargetNodeSelect.appendChild(opt);
      }
      if (currentVal) this.dom.remoteTargetNodeSelect.value = currentVal;
    }
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.app = new MeshCoreStationApp();
});
