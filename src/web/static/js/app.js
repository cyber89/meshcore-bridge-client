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

/**
 * Capa de persistencia asíncrona en el navegador mediante IndexedDB.
 * Permite conservar historial de chat, tramas del sniffer y preferencias tras refrescar la página.
 */
class MeshCoreStorage {
  constructor(dbName = "MeshCoreStationDB", version = 1) {
    this.dbName = dbName;
    this.version = version;
    this.db = null;
    this.readyPromise = this.init();
  }

  async init() {
    if (!("indexedDB" in window)) {
      console.warn("IndexedDB no soportado en este entorno.");
      return null;
    }
    return new Promise((resolve) => {
      try {
        const request = indexedDB.open(this.dbName, this.version);
        request.onupgradeneeded = (e) => {
          const db = e.target.result;
          if (!db.objectStoreNames.contains("chat_messages")) {
            const chatStore = db.createObjectStore("chat_messages", { keyPath: "id", autoIncrement: true });
            chatStore.createIndex("by_feed", "feed_key", { unique: false });
            chatStore.createIndex("by_time", "timestamp", { unique: false });
          }
          if (!db.objectStoreNames.contains("sniffer_packets")) {
            const snifferStore = db.createObjectStore("sniffer_packets", { keyPath: "id", autoIncrement: true });
            snifferStore.createIndex("by_opcode", "opcode", { unique: false });
            snifferStore.createIndex("by_time", "timestamp", { unique: false });
          }
          if (!db.objectStoreNames.contains("app_settings")) {
            db.createObjectStore("app_settings", { keyPath: "key" });
          }
        };
        request.onsuccess = (e) => {
          this.db = e.target.result;
          resolve(this.db);
        };
        request.onerror = (e) => {
          console.warn("Error abriendo IndexedDB:", e);
          resolve(null);
        };
      } catch (err) {
        console.warn("Fallo inicializando IndexedDB:", err);
        resolve(null);
      }
    });
  }

  async saveMessage(feedKey, msg) {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const record = {
        feed_key: feedKey,
        msg_id: msg.msg_id || msg.id || null,
        sender: msg.sender,
        sender_name: msg.sender_name,
        text: msg.text,
        is_outgoing: !!msg.is_outgoing,
        channel_idx: msg.channel_idx,
        dm_target: msg.dm_target,
        timestamp: msg.timestamp || new Date().toISOString(),
        metrics: msg.metrics || null,
        delivered: !!msg.delivered,
        expected_ack: msg.expected_ack || null,
        trip_time_ms: msg.trip_time_ms || 0,
      };
      if (typeof msg._db_id === "number") {
        record.id = msg._db_id;
        store.put(record);
      } else {
        const req = store.add(record);
        req.onsuccess = (e) => {
          msg._db_id = e.target.result;
        };
      }
    } catch (_) {}
  }

  async updateMessageDelivery(msgId, ackCode, tripTime) {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const req = store.openCursor();
      const rawAck = (ackCode || "").toLowerCase();
      const ackClean = rawAck.startsWith("0x") ? rawAck.slice(2) : rawAck;
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          const val = cursor.value;
          const valExp = (val.expected_ack || "").toLowerCase();
          const valExpClean = valExp.startsWith("0x") ? valExp.slice(2) : valExp;
          const ackMatch = ackClean && valExpClean && valExpClean === ackClean;
          const match = (msgId && (val.msg_id === msgId || String(val.id) === String(msgId))) || ackMatch;
          if (match) {
            val.delivered = true;
            val.trip_time_ms = tripTime || 0;
            cursor.update(val);
          }
          cursor.continue();
        }
      };
    } catch (_) {}
  }

  async purgeNonCommonMessages(isCommandOrSystemTextFn) {
    await this.readyPromise;
    if (!this.db || typeof isCommandOrSystemTextFn !== "function") return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const req = store.openCursor();
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          const val = cursor.value;
          const txt = val.text || val.message || "";
          const txtType = val.txt_type || 0;
          if (isCommandOrSystemTextFn(txt, txtType)) {
            cursor.delete();
          }
          cursor.continue();
        }
      };
    } catch (_) {}
  }

  async getMessagesByFeed(feedKey, limit = 100) {
    await this.readyPromise;
    if (!this.db) return [];
    return new Promise((resolve) => {
      try {
        const tx = this.db.transaction("chat_messages", "readonly");
        const store = tx.objectStore("chat_messages");
        const index = store.index("by_feed");
        const req = index.getAll(IDBKeyRange.only(feedKey));
        req.onsuccess = () => {
          const msgs = req.result || [];
          resolve(msgs.slice(-limit));
        };
        req.onerror = () => resolve([]);
      } catch (_) {
        resolve([]);
      }
    });
  }

  async getDmConversations() {
    await this.readyPromise;
    if (!this.db) return [];
    return new Promise((resolve) => {
      try {
        const tx = this.db.transaction("chat_messages", "readonly");
        const store = tx.objectStore("chat_messages");
        const req = store.getAll();
        req.onsuccess = () => {
          const allMsgs = req.result || [];
          const threadsMap = new Map();

          for (const msg of allMsgs) {
            const feedKey = msg.feed_key || "";
            if (!feedKey.startsWith("dm_")) continue;
            const pubkey = feedKey.slice(3).trim();
            if (!pubkey || pubkey.toLowerCase() === "unknown" || pubkey.toLowerCase() === "local") continue;

            if (!threadsMap.has(pubkey)) {
              threadsMap.set(pubkey, {
                pubkey: pubkey,
                name: msg.sender_name || (msg.dm_target && msg.dm_target !== pubkey ? msg.dm_target : pubkey),
                lastMessage: msg.text || "",
                lastTimestamp: msg.timestamp || "",
                role: "CLIENT",
                messages: []
              });
            }
            const thread = threadsMap.get(pubkey);
            thread.messages.push(msg);
            if (!msg.is_outgoing && msg.sender_name && msg.sender_name.toLowerCase() !== "unknown" && msg.sender_name !== pubkey) {
              thread.name = msg.sender_name;
            }
            if (msg.timestamp && (!thread.lastTimestamp || new Date(msg.timestamp) > new Date(thread.lastTimestamp))) {
              thread.lastTimestamp = msg.timestamp;
              thread.lastMessage = msg.text || "";
            }
          }

          const threads = Array.from(threadsMap.values());
          threads.sort((a, b) => new Date(b.lastTimestamp || 0) - new Date(a.lastTimestamp || 0));
          resolve(threads);
        };
        req.onerror = () => resolve([]);
      } catch (_) {
        resolve([]);
      }
    });
  }

  async clearFeedMessages(feedKey) {

    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const index = store.index("by_feed");
      const req = index.openCursor(IDBKeyRange.only(feedKey));
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          store.delete(cursor.primaryKey);
          cursor.continue();
        }
      };
    } catch (_) {}
  }

  async saveSnifferPacket(pkt) {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("sniffer_packets", "readwrite");
      const store = tx.objectStore("sniffer_packets");
      store.add({
        opcode: String(pkt.opcode || pkt.payload_type || "DATA").toUpperCase(),
        sender: String(pkt.sender || pkt.src_node_id || pkt.from || "RF"),
        to: String(pkt.to || pkt.dst_node_id || "0xFFFF"),
        snr: pkt.metrics?.snr != null ? pkt.metrics.snr : (pkt.snr != null ? pkt.snr : "--"),
        rssi: pkt.metrics?.rssi != null ? pkt.metrics.rssi : (pkt.rssi != null ? pkt.rssi : "--"),
        byte_length: pkt.byte_length || pkt.length || (pkt.raw_hex ? Math.floor(pkt.raw_hex.length / 2) : 0),
        raw_hex: pkt.raw_hex || pkt.raw || "",
        text: pkt.text || "",
        timestamp: pkt.timestamp || Date.now(),
      });
    } catch (_) {}
  }

  async getSnifferPackets(limit = 200) {
    await this.readyPromise;
    if (!this.db) return [];
    return new Promise((resolve) => {
      try {
        const tx = this.db.transaction("sniffer_packets", "readonly");
        const store = tx.objectStore("sniffer_packets");
        const req = store.getAll();
        req.onsuccess = () => {
          const pkts = req.result || [];
          resolve(pkts.slice(-limit));
        };
        req.onerror = () => resolve([]);
      } catch (_) {
        resolve([]);
      }
    });
  }

  async clearSnifferPackets() {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("sniffer_packets", "readwrite");
      tx.objectStore("sniffer_packets").clear();
    } catch (_) {}
  }

  async clearAll() {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction(["chat_messages", "sniffer_packets"], "readwrite");
      tx.objectStore("chat_messages").clear();
      tx.objectStore("sniffer_packets").clear();
    } catch (_) {}
  }
}

class MeshCoreStationApp {
  constructor() {
    this.storage = new MeshCoreStorage();
    this.mapLayerMode = localStorage.getItem("meshcore_map_layer_mode") || "cartodb";
    this.localTileUrl = localStorage.getItem("meshcore_local_tile_url") || "/api/map/tiles/{z}/{x}/{y}.png";
    this.tacticalRadarGroup = null;
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
    this.unreadCounts = new Map(); // feedKey -> number
    this.lastReadTimestamps = new Map(); // feedKey -> ISO string
    this.authenticatedRepeaters = new Set(); // Conjunto de pubkeys autenticados en sesión
    this.repeaterPasswords = new Map(); // pubkey -> password en memoria

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
    this.initMapOverlayToggle();
    this.initAirtimeMonitoring();
    this.initContactDiscovery();
    this.initTraceroute();
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

  extractSenderAndText(text, currentSenderName = null) {
    if (!text || typeof text !== "string") {
      return { senderName: currentSenderName || "Anónimo", cleanText: text || "" };
    }
    const trimmed = text.trim();
    const match = trimmed.match(/^([a-zA-Z0-9_\-\.]{2,32}):\s*([\s\S]*)$/);
    if (match) {
      const candidateName = match[1].trim();
      const actualText = match[2].trim();
      const lowerCandidate = candidateName.toLowerCase();
      if (!["http", "https", "ftp", "ws", "wss", "json", "data", "cmd", "r", "ack", "req", "res", "echo", "status"].includes(lowerCandidate)) {
        const isUnknown = !currentSenderName ||
          currentSenderName.toLowerCase() === "unknown" ||
          currentSenderName.toLowerCase() === "anónimo" ||
          currentSenderName.toLowerCase() === "anonimo" ||
          currentSenderName.startsWith("Node_unknow") ||
          currentSenderName.length >= 12;
        return {
          senderName: isUnknown ? candidateName : currentSenderName,
          cleanText: actualText || trimmed
        };
      }
    }
    return {
      senderName: currentSenderName && currentSenderName.toLowerCase() !== "unknown" ? currentSenderName : "Anónimo",
      cleanText: trimmed
    };
  }

  isCommandOrSystemText(text, txtType = 0) {

    if (txtType === 1) return true;
    if (!text || typeof text !== "string") return true;

    const clean = text.trim();
    if (!clean) return true;

    let cleanLower = clean.toLowerCase();
    if (cleanLower.startsWith("->") || cleanLower.startsWith("- >") || cleanLower.startsWith(">")) {
      cleanLower = cleanLower.replace(/^[- >]+/, "").trim();
    }

    if (
      cleanLower.startsWith("unknown command") ||
      cleanLower.startsWith("error: unknown command") ||
      cleanLower.startsWith("error unknown command") ||
      cleanLower.startsWith("invalid command") ||
      cleanLower.startsWith("cmd ") ||
      cleanLower.startsWith("login ") ||
      cleanLower.startsWith("auth ") ||
      cleanLower.startsWith("stats-") ||
      cleanLower.startsWith("stats ") ||
      cleanLower.startsWith("set ") ||
      cleanLower.startsWith("get ") ||
      cleanLower.startsWith("log ") ||
      cleanLower.startsWith("reboot") ||
      cleanLower.startsWith("logging off") ||
      cleanLower.startsWith("log erased") ||
      cleanLower.startsWith("eof") ||
      cleanLower.startsWith("welcome admin") ||
      cleanLower.startsWith("access denied") ||
      cleanLower.startsWith("bad pin") ||
      cleanLower.startsWith("wrong password") ||
      cleanLower.startsWith("incorrect password") ||
      cleanLower.startsWith("permission denied") ||
      cleanLower.startsWith("not logged in") ||
      cleanLower === "unknown command" ||
      cleanLower === "ok" ||
      cleanLower === "error" ||
      cleanLower === "success" ||
      cleanLower === "failed" ||
      cleanLower === "unauthorized" ||
      cleanLower === "advert" ||
      cleanLower === "[advert]" ||
      cleanLower === "beacon" ||
      cleanLower === "logging off" ||
      cleanLower === "log erased" ||
      cleanLower === "eof" ||
      cleanLower === "pong" ||
      cleanLower === "ping"
    ) {
      return true;
    }

    if (clean.startsWith("[Eco ") || clean.startsWith("[Status ") || clean.startsWith("[ACK") ||
        clean.startsWith("📡 ") || clean.startsWith("⛔ ") || clean.startsWith("📖 ") ||
        clean.startsWith("⏰ ") || clean.startsWith("📅 ") || clean.startsWith("🏓 ")) {
      return true;
    }

    return false;
  }

  isCommonChatMessage(payload) {
    if (!payload || typeof payload !== "object") return false;

    const evType = String(payload.event_type || payload.type || "");
    const nonChatEventTypes = [
      "repeater_response", "repeater_telemetry", "advert", "node_advert",
      "node_discovered", "contact_discovered", "contact_updated", "contacts_updated",
      "channels_updated", "message_delivered", "trace_data", "system_log",
      "metrics_update", "rf_log", "telemetry", "stats_radio", "stats_core", "ack", "trace"
    ];

    if (nonChatEventTypes.includes(evType)) {
      return false;
    }

    const isChatType = (
      evType === "public" ||
      evType === "channel" ||
      evType === "direct" ||
      payload.type === "CHANNEL_MSG" ||
      payload.type === "DIRECT_MSG"
    );

    if (!isChatType) {
      return false;
    }

    const txtType = Number(payload.txt_type ?? payload.text_type ?? 0);
    if (txtType === 1) {
      return false;
    }

    const text = String(payload.text || payload.message || "").trim();
    if (!text) {
      return false;
    }

    if (this.isCommandOrSystemText(text, txtType)) {
      return false;
    }

    return true;
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
      globalChatUnreadBadge: document.getElementById("globalChatUnreadBadge"),
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
      repeaterAdminModalCard: document.getElementById("repeaterAdminModalCard"),
      repeaterAuthGate: document.getElementById("repeaterAuthGate"),
      repeaterGateForm: document.getElementById("repeaterGateForm"),
      repeaterGatePassword: document.getElementById("repeaterGatePassword"),
      btnToggleGatePwd: document.getElementById("btnToggleGatePwd"),
      btnRepeaterGateSubmit: document.getElementById("btnRepeaterGateSubmit"),
      repeaterGateStatus: document.getElementById("repeaterGateStatus"),
      repeaterAdminUnlockedContent: document.getElementById("repeaterAdminUnlockedContent"),
      btnRepeaterLogout: document.getElementById("btnRepeaterLogout"),
      adminModalNodeName: document.getElementById("adminModalNodeName"),
      adminModalNodePk: document.getElementById("adminModalNodePk"),
      adminModalNodePkDisplay: document.getElementById("adminModalNodePkDisplay"),
      adminModalPassword: document.getElementById("adminModalPassword"),
      btnModalAuthTest: document.getElementById("btnModalAuthTest"),
      adminModalAuthStatus: document.getElementById("adminModalAuthStatus"),
      btnModalHeaderPingZero: document.getElementById("btnModalHeaderPingZero"),
      adminModalPingZeroBadge: document.getElementById("adminModalPingZeroBadge"),
      btnModalActionPingZero: document.getElementById("btnModalActionPingZero"),
      repQuickPingResult: document.getElementById("repQuickPingResult"),
      btnModalActionReboot: document.getElementById("btnModalActionReboot"),
      btnModalActionClearStats: document.getElementById("btnModalActionClearStats"),
      btnModalActionAdvert: document.getElementById("btnModalActionAdvert"),
      btnModalActionClock: document.getElementById("btnModalActionClock"),
      btnCloseRepeaterAdminModal: document.getElementById("btnCloseRepeaterAdminModal"),
      headerDutyCycle: document.getElementById("headerDutyCycle"),
      headerAirtimeChip: document.getElementById("headerAirtimeChip"),
      btnToggleHeatmap: document.getElementById("btnToggleHeatmap"),
      mapOverlayInfo: document.getElementById("mapOverlayInfo"),
      mapOverlayHeader: document.getElementById("mapOverlayHeader"),
      btnToggleMapNodes: document.getElementById("btnToggleMapNodes"),
      discoveryBanner: document.getElementById("discoveryBanner"),
      discoveryCount: document.getElementById("discoveryCount"),
      btnAcceptAllDiscovered: document.getElementById("btnAcceptAllDiscovered"),
      tracerouteModal: document.getElementById("tracerouteModal"),
      tracerouteModalTitle: document.getElementById("tracerouteModalTitle"),
      traceTargetNameDisplay: document.getElementById("traceTargetNameDisplay"),
      traceTargetPkDisplay: document.getElementById("traceTargetPkDisplay"),
      traceCustomPathInput: document.getElementById("traceCustomPathInput"),
      btnExecuteTrace: document.getElementById("btnExecuteTrace"),
      traceStatusPill: document.getElementById("traceStatusPill"),
      traceVisualGraph: document.getElementById("traceVisualGraph"),
      traceBreakdownTableBody: document.getElementById("traceBreakdownTableBody"),
      btnCloseTracerouteModal: document.getElementById("btnCloseTracerouteModal"),
      contactsGridUi: document.getElementById("contactsGridUi"),
      btnHeaderAddContact: document.getElementById("btnHeaderAddContact"),
      contactsSearchInput: document.getElementById("contactsSearchInput"),
      btnRefreshNodes: document.getElementById("btnRefreshNodes"),
      systemLogsFeed: document.getElementById("systemLogsFeed"),
      btnToggleDebugMode: document.getElementById("btnToggleDebugMode"),
      btnQuickDiag: document.getElementById("btnQuickDiag"),
      btnDownloadRawLogs: document.getElementById("btnDownloadRawLogs"),
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
    if (this.dom.themeToggleBtn) {
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
          if (targetTabId === "tab-chat") {
            this.renderCurrentConversation();
          } else if (targetTabId === "tab-map") {
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
      if (this.dom.commandPaletteModal) {
        this.dom.commandPaletteModal.classList.remove("hidden");
      }
      if (this.dom.cmdPaletteInput) {
        this.dom.cmdPaletteInput.value = "";
        this.dom.cmdPaletteInput.focus();
      }
      this.cmdPaletteOpen = true;
    };
    const closeModal = () => {
      if (this.dom.commandPaletteModal) {
        this.dom.commandPaletteModal.classList.add("hidden");
      }
      this.cmdPaletteOpen = false;
    };

    if (this.dom.btnCommandPalette) {
      this.dom.btnCommandPalette.addEventListener("click", openModal);
    }
    if (this.dom.commandPaletteModal) {
      this.dom.commandPaletteModal.addEventListener("click", (e) => {
        if (e.target === this.dom.commandPaletteModal) closeModal();
      });
    }

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

    if (this.dom.cmdPaletteResults) {
      this.dom.cmdPaletteResults.querySelectorAll(".cmd-item").forEach((item) => {
        item.addEventListener("click", () => {
          const action = item.getAttribute("data-action");
          closeModal();
          if (action.startsWith("tab-")) {
            const navBtn = document.querySelector(`.nav-btn[data-tab="${action}"]`);
            if (navBtn) navBtn.click();
          } else if (action === "action-advert-hop" || action === "action-advert") {
            this.sendAdvert(false);
          } else if (action === "action-advert-flood") {
            this.sendAdvert(true);
          } else if (action === "action-advert-clipboard") {
            this.copyAdvertToClipboard();
          } else if (action === "action-ha") {
            this.publishHomeAssistantDiscovery();
          } else if (action === "action-diag") {
            const navBtn = document.querySelector('.nav-btn[data-tab="tab-logs"]');
            if (navBtn) navBtn.click();
            this.runQuickDiagnostic();
          } else if (action === "action-debug-toggle") {
            this.toggleDebugMode();
          }
        });
      });
    }
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

  getStoredRepeaterPassword(pubkey) {
    if (!pubkey) return null;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    try {
      const stored = localStorage.getItem("meshcore_repeater_passwords");
      if (stored) {
        const map = JSON.parse(stored);
        return map[canonicalPk] || map[pubkey] || null;
      }
    } catch (_) {}
    return null;
  }

  setStoredRepeaterPassword(pubkey, password) {
    if (!pubkey || !password) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    this.repeaterPasswords = this.repeaterPasswords || new Map();
    this.repeaterPasswords.set(canonicalPk, password);
    this.repeaterPasswords.set(pubkey, password);
    try {
      const stored = localStorage.getItem("meshcore_repeater_passwords");
      const map = stored ? JSON.parse(stored) : {};
      map[canonicalPk] = password;
      map[pubkey] = password;
      localStorage.setItem("meshcore_repeater_passwords", JSON.stringify(map));
    } catch (_) {}
  }

  clearStoredRepeaterPassword(pubkey) {
    if (!pubkey) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    this.authenticatedRepeaters.delete(canonicalPk);
    this.authenticatedRepeaters.delete(pubkey);
    if (this.repeaterPasswords) {
      this.repeaterPasswords.delete(canonicalPk);
      this.repeaterPasswords.delete(pubkey);
    }
    try {
      const stored = localStorage.getItem("meshcore_repeater_passwords");
      if (stored) {
        const map = JSON.parse(stored);
        delete map[canonicalPk];
        delete map[pubkey];
        localStorage.setItem("meshcore_repeater_passwords", JSON.stringify(map));
      }
    } catch (_) {}
  }

  getRepeaterPassword(target) {
    if (!target) return "";
    const canonicalPk = this.resolveCanonicalPubkey(target);
    return this.getStoredRepeaterPassword(canonicalPk) ||
      this.getStoredRepeaterPassword(target) ||
      (this.repeaterPasswords && (this.repeaterPasswords.get(canonicalPk) || this.repeaterPasswords.get(target))) ||
      (this.dom.repeaterGatePassword ? this.dom.repeaterGatePassword.value.trim() : "") ||
      (this.dom.adminModalPassword ? this.dom.adminModalPassword.value.trim() : "");
  }

  lockRepeaterAdminView(pubkey, errorMessage = null) {
    const card = this.dom.repeaterAdminModalCard || document.getElementById("repeaterAdminModalCard");
    if (card) {
      card.classList.remove("unlocked");
      card.classList.add("locked");
    }
    const gate = this.dom.repeaterAuthGate || document.getElementById("repeaterAuthGate");
    if (gate) gate.classList.remove("hidden");
    const unlocked = this.dom.repeaterAdminUnlockedContent || document.getElementById("repeaterAdminUnlockedContent");
    if (unlocked) unlocked.classList.add("hidden");

    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    if (statusEl) {
      if (errorMessage) {
        statusEl.className = "auth-gate-status error";
        statusEl.textContent = errorMessage;
        statusEl.classList.remove("hidden");
      } else {
        statusEl.className = "auth-gate-status hidden";
        statusEl.textContent = "";
      }
    }

    const pwdInput = this.dom.repeaterGatePassword || document.getElementById("repeaterGatePassword");
    if (pwdInput) {
      pwdInput.disabled = false;
      setTimeout(() => pwdInput.focus(), 150);
    }
    const submitBtn = this.dom.btnRepeaterGateSubmit || document.getElementById("btnRepeaterGateSubmit");
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = '<span class="btn-icon">🔐</span> Desbloquear & Autenticar Repetidor';
    }
  }

  unlockRepeaterAdminView(pubkey) {
    const card = this.dom.repeaterAdminModalCard || document.getElementById("repeaterAdminModalCard");
    if (card) {
      card.classList.remove("locked");
      card.classList.add("unlocked");
    }
    const gate = this.dom.repeaterAuthGate || document.getElementById("repeaterAuthGate");
    if (gate) gate.classList.add("hidden");
    const unlocked = this.dom.repeaterAdminUnlockedContent || document.getElementById("repeaterAdminUnlockedContent");
    if (unlocked) unlocked.classList.remove("hidden");

    const authStatus = this.dom.adminModalAuthStatus || document.getElementById("adminModalAuthStatus");
    if (authStatus) {
      authStatus.className = "auth-status-chip authenticated";
      authStatus.textContent = "🔓 Autenticado";
    }

    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    if (statusEl) {
      statusEl.className = "auth-gate-status hidden";
      statusEl.textContent = "";
    }
  }

  handleRepeaterAuthError(pubkey, message = "Contraseña incorrecta o cambiada en el repetidor") {
    this.showToast(message, "error");
    this.clearStoredRepeaterPassword(pubkey);
    this.lockRepeaterAdminView(pubkey, `⚠️ ${message}`);
  }

  async authenticateRepeater(pubkey, password) {
    if (!pubkey || !password) {
      this.handleRepeaterAuthError(pubkey, "Ingresa la contraseña de administración.");
      return false;
    }

    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    const submitBtn = this.dom.btnRepeaterGateSubmit || document.getElementById("btnRepeaterGateSubmit");

    if (statusEl) {
      statusEl.className = "auth-gate-status loading";
      statusEl.textContent = "⏳ Verificando credenciales con el repetidor por RF...";
      statusEl.classList.remove("hidden");
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="btn-icon">⏳</span> Verificando...';
    }

    try {
      const res = await fetch("/api/repeater/remote/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: canonicalPk, password: password }),
      });
      const data = await res.json();

      if (data.status === "ok") {
        this.authenticatedRepeaters.add(canonicalPk);
        this.authenticatedRepeaters.add(pubkey);
        this.setStoredRepeaterPassword(canonicalPk, password);
        this.unlockRepeaterAdminView(canonicalPk);
        this.showToast("🔓 Repetidor autenticado con éxito", "success");

        // Solicitar telemetría y configuración completa tras autenticación
        try {
          const fetchAction = (act) => fetch("/api/repeater/remote/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: canonicalPk, password: password, action: act }),
          }).catch(() => {});

          fetchAction("stats-core");
          setTimeout(() => fetchAction("stats-radio"), 600);
          setTimeout(() => fetchAction("pos"), 1200);
          setTimeout(() => fetchAction("owner"), 1800);
        } catch (_) {}

        return true;
      } else {
        this.handleRepeaterAuthError(canonicalPk, data.message || "Contraseña incorrecta o cambiada en el repetidor");
        return false;
      }
    } catch (err) {
      this.handleRepeaterAuthError(canonicalPk, `Error de conexión: ${err.message}`);
      return false;
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span class="btn-icon">🔐</span> Desbloquear & Autenticar Repetidor';
      }
    }
  }

  openRepeaterAdminModal(pubkey, name) {
    this.selectedRepeaterTarget = pubkey;
    this.selectedRepeaterName = name || pubkey;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    const modal = this.dom.repeaterAdminModal || document.getElementById("repeaterAdminModal");
    const nameEl = this.dom.adminModalNodeName || document.getElementById("adminModalNodeName");
    const pkInput = this.dom.adminModalNodePk || document.getElementById("adminModalNodePk");
    const pkDisplay = this.dom.adminModalNodePkDisplay || document.getElementById("adminModalNodePkDisplay");

    if (nameEl) nameEl.textContent = name || pubkey;
    if (pkInput) pkInput.value = canonicalPk;
    if (pkDisplay) pkDisplay.textContent = canonicalPk.length > 14 ? `${canonicalPk.slice(0, 8)}...${canonicalPk.slice(-4)}` : canonicalPk;

    // Buscar nodo y poblar telemetría
    const node = this.knownNodes.get(canonicalPk) || this.knownNodes.get(pubkey) || {};
    this.populateRepeaterModalData(node);

    // GATING: Comprobar autenticación de sesión o almacenamiento persistente
    if (this.authenticatedRepeaters.has(canonicalPk) || this.authenticatedRepeaters.has(pubkey)) {
      this.unlockRepeaterAdminView(canonicalPk);
      const pwd = this.getRepeaterPassword(canonicalPk);
      if (pwd) {
        fetch("/api/repeater/remote/action", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ target_node: canonicalPk, password: pwd, action: "stats-core" }),
        }).catch(() => {});
      }
    } else {
      const savedPwd = this.getStoredRepeaterPassword(canonicalPk);
      if (savedPwd) {
        this.lockRepeaterAdminView(canonicalPk);
        const pwdInput = this.dom.repeaterGatePassword || document.getElementById("repeaterGatePassword");
        if (pwdInput) pwdInput.value = savedPwd;
        this.authenticateRepeater(canonicalPk, savedPwd);
      } else {
        this.lockRepeaterAdminView(canonicalPk);
        const pwdInput = this.dom.repeaterGatePassword || document.getElementById("repeaterGatePassword");
        if (pwdInput) {
          pwdInput.value = "";
          setTimeout(() => pwdInput.focus(), 150);
        }
      }
    }

    if (modal) modal.classList.remove("hidden");
  }

  populateRepeaterModalData(node) {
    const pubkey = node.public_key || this.selectedRepeaterTarget;

    // 0. Estado de Ping Zero previo
    if (this.dom.adminModalPingZeroBadge) {
      if (node.ping_zero_rtt) {
        const pingRssi = node.last_rssi != null ? ` (${node.last_rssi} dBm)` : "";
        this.dom.adminModalPingZeroBadge.textContent = `🎯 Ping 0: ${node.ping_zero_rtt} ms${pingRssi}`;
        this.dom.adminModalPingZeroBadge.className = "ping-zero-badge ping-success";
      } else {
        this.dom.adminModalPingZeroBadge.textContent = "🎯 Ping 0: -- ms";
        this.dom.adminModalPingZeroBadge.className = "ping-zero-badge";
      }
    }
    if (this.dom.repQuickPingResult) {
      if (node.ping_zero_rtt) {
        const rRssi = node.last_rssi != null ? ` • RSSI ${node.last_rssi} dBm` : "";
        const rSnr = node.last_snr != null ? ` • SNR ${node.last_snr} dB` : "";
        this.dom.repQuickPingResult.textContent = `🟢 RTT ${node.ping_zero_rtt} ms${rRssi}${rSnr} (0 Saltos)`;
      } else {
        this.dom.repQuickPingResult.textContent = "Sin mediciones recientes";
      }
    }

    // 1. Batería & Voltajes
    const batVal = node.battery_pct != null ? node.battery_pct : (node.battery != null ? node.battery : "--");
    const voltVal = node.voltage_v != null ? node.voltage_v : (node.voltage != null ? node.voltage : "--");
    const solarVal = node.solar_v != null ? node.solar_v : "--";

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
    const airtimeVal = node.airtime_ms != null ? node.airtime_ms : (node.airtime != null ? node.airtime : null);
    const airtimeEl = document.getElementById("repAirtimeValue");
    if (airtimeEl) airtimeEl.textContent = airtimeVal != null ? `${airtimeVal} ms` : "-- ms";
    const airtimeDutyEl = document.getElementById("repAirtimeDuty");
    if (airtimeDutyEl) airtimeDutyEl.textContent = airtimeVal != null ? `Duty: ${(airtimeVal / 36000).toFixed(2)}%` : "Duty Cycle: --%";

    const noiseVal = node.noise_floor_dbm != null ? node.noise_floor_dbm : (node.noise_floor != null ? node.noise_floor : (node.noise != null ? node.noise : null));
    const noiseEl = document.getElementById("repNoiseValue");
    if (noiseEl) noiseEl.textContent = noiseVal != null ? `${noiseVal} dBm` : "-- dBm";

    // 4. Calidad de Señal
    const snrVal = node.last_snr != null ? node.last_snr : (node.snr != null ? node.snr : null);
    const rssiVal = node.last_rssi != null ? node.last_rssi : (node.rssi != null ? node.rssi : null);
    const snrEl = document.getElementById("repSnrValue");
    if (snrEl) snrEl.textContent = snrVal != null ? `${snrVal} dB` : "-- dB";
    const rssiEl = document.getElementById("repRssiValue");
    if (rssiEl) rssiEl.textContent = rssiVal != null ? `RSSI: ${rssiVal} dBm` : "RSSI: -- dBm";

    // 5. Paquetes & Errores
    const pktsTx = node.packets_sent != null ? node.packets_sent : (node.tx_packets != null ? node.tx_packets : (node.nb_sent != null ? node.nb_sent : null));
    const pktsRx = node.packets_recv != null ? node.packets_recv : (node.rx_packets != null ? node.rx_packets : (node.nb_recv != null ? node.nb_recv : null));
    const pktsEl = document.getElementById("repPacketsValue");
    if (pktsEl) {
      if (pktsTx != null && pktsRx != null) {
        pktsEl.textContent = `${pktsTx} TX / ${pktsRx} RX`;
      } else if (pktsTx != null) {
        pktsEl.textContent = `${pktsTx} TX / -- RX`;
      } else if (pktsRx != null) {
        pktsEl.textContent = `-- TX / ${pktsRx} RX`;
      } else {
        pktsEl.textContent = "-- / --";
      }
    }

    const errsVal = node.packet_errors != null ? node.packet_errors : (node.error_count != null ? node.error_count : (node.rx_errors != null ? node.rx_errors : null));
    const dupsVal = node.duplicate_packets != null ? node.duplicate_packets : (node.duplicates != null ? node.duplicates : (node.direct_dups != null ? (node.direct_dups + (node.flood_dups || 0)) : null));
    const pktsErrEl = document.getElementById("repPacketErrorsValue");
    if (pktsErrEl) {
      const dStr = dupsVal != null ? dupsVal : "--";
      const eStr = errsVal != null ? errsVal : "--";
      pktsErrEl.textContent = `Duplicados: ${dStr} | Errores: ${eStr}`;
    }

    // 6. Resumen de parámetros
    const sumFreq = document.getElementById("repSummaryFreq");
    if (sumFreq) sumFreq.textContent = node.frequency != null ? `${node.frequency} MHz` : (node.freq != null ? `${node.freq} MHz` : "915.000 MHz");
    const sumPower = document.getElementById("repSummaryPower");
    if (sumPower) sumPower.textContent = node.tx_power != null ? `${node.tx_power} dBm` : (node.power != null ? `${node.power} dBm` : "20 dBm");
    const sumModem = document.getElementById("repSummaryModem");
    const sfVal = node.spreading_factor != null ? node.spreading_factor : (node.sf != null ? node.sf : 11);
    const bwVal = node.bandwidth != null ? node.bandwidth : (node.bw != null ? node.bw : 250);
    if (sumModem) sumModem.textContent = `SF${sfVal} / BW${bwVal}`;
    const sumRepeat = document.getElementById("repSummaryRepeat");
    if (sumRepeat) sumRepeat.textContent = node.repeat_enabled === false ? "Desactivado" : "Activado";
    const sumQueue = document.getElementById("repSummaryQueue");
    if (sumQueue) sumQueue.textContent = `${node.queue_len != null ? node.queue_len : (node.tx_queue_len != null ? node.tx_queue_len : 0)} paquetes`;

    const sumPos = document.getElementById("repSummaryPos");
    if (sumPos) {
      if (node.latitude != null && node.longitude != null) {
        sumPos.textContent = `${Number(node.latitude).toFixed(4)}, ${Number(node.longitude).toFixed(4)}`;
      } else {
        sumPos.textContent = "No configurada";
      }
    }

    // Llenar formulario de Radio
    const radioFreqInput = document.getElementById("radioFreq");
    if (radioFreqInput && (node.frequency != null || node.freq != null)) {
      radioFreqInput.value = node.frequency != null ? node.frequency : node.freq;
    }
    const radioPowerInput = document.getElementById("radioPower");
    if (radioPowerInput && (node.tx_power != null || node.power != null)) {
      radioPowerInput.value = node.tx_power != null ? node.tx_power : node.power;
    }
    const radioHopLimitInput = document.getElementById("radioHopLimit");
    if (radioHopLimitInput && (node.hops != null || node.hop_limit != null)) {
      radioHopLimitInput.value = node.hops != null ? node.hops : node.hop_limit;
    }
    const radioBeaconInput = document.getElementById("radioBeaconInterval");
    if (radioBeaconInput && (node.advert_interval != null || node.beacon_interval != null)) {
      radioBeaconInput.value = node.advert_interval != null ? node.advert_interval : node.beacon_interval;
    }
    const radioSf = document.getElementById("radioSf");
    if (radioSf && (node.spreading_factor != null || node.sf != null)) {
      radioSf.value = String(node.spreading_factor != null ? node.spreading_factor : node.sf);
    }
    const radioBw = document.getElementById("radioBw");
    if (radioBw && (node.bandwidth != null || node.bw != null)) {
      radioBw.value = String(node.bandwidth != null ? node.bandwidth : node.bw);
    }
    const radioCr = document.getElementById("radioCr");
    if (radioCr && (node.coding_rate != null || node.cr != null)) {
      radioCr.value = String(node.coding_rate != null ? node.coding_rate : node.cr);
    }
    const radioRepeatMode = document.getElementById("radioRepeatMode");
    if (radioRepeatMode && node.repeat_enabled !== undefined) {
      radioRepeatMode.value = node.repeat_enabled === false ? "off" : "on";
    }

    // Llenar formulario de Propietario & Posición
    const ownerNameInput = document.getElementById("repOwnerName");
    if (ownerNameInput) ownerNameInput.value = node.owner_name || node.alias || node.name || "";
    const ownerInfoInput = document.getElementById("repOwnerInfo");
    if (ownerInfoInput) ownerInfoInput.value = node.owner_info || "";
    const posLatInput = document.getElementById("repPosLat");
    if (posLatInput && node.latitude != null) posLatInput.value = node.latitude;
    const posLonInput = document.getElementById("repPosLon");
    if (posLonInput && node.longitude != null) posLonInput.value = node.longitude;
    const posAltInput = document.getElementById("repPosAlt");
    if (posAltInput && node.altitude_m != null) posAltInput.value = node.altitude_m;
    const posFixed = document.getElementById("repPosFixed");
    if (posFixed && node.fixed_position !== undefined) {
      posFixed.value = node.fixed_position === false ? "0" : "1";
    }

    if (pubkey) this.refreshNeighborsTable(pubkey);
  }

  initRepeaterDashboard() {
    // Gate de Autenticación
    const gateForm = document.getElementById("repeaterGateForm");
    const gateSubmit = document.getElementById("btnRepeaterGateSubmit");
    const gatePwd = document.getElementById("repeaterGatePassword");
    const togglePwdBtn = document.getElementById("btnToggleGatePwd");
    const logoutBtn = document.getElementById("btnRepeaterLogout");

    if (togglePwdBtn && gatePwd) {
      togglePwdBtn.addEventListener("click", () => {
        if (gatePwd.type === "password") {
          gatePwd.type = "text";
          togglePwdBtn.textContent = "🙈";
        } else {
          gatePwd.type = "password";
          togglePwdBtn.textContent = "👁️";
        }
      });
    }

    const submitAuth = async () => {
      const target = this.selectedRepeaterTarget;
      const pwd = gatePwd ? gatePwd.value.trim() : "";
      if (!target) return;
      await this.authenticateRepeater(target, pwd);
    };

    if (gateForm) {
      gateForm.addEventListener("submit", (e) => {
        e.preventDefault();
        submitAuth();
      });
    }
    if (gateSubmit) {
      gateSubmit.addEventListener("click", submitAuth);
    }

    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (target) {
          this.clearStoredRepeaterPassword(target);
          this.lockRepeaterAdminView(target);
          if (gatePwd) {
            gatePwd.value = "";
            gatePwd.focus();
          }
          this.showToast("🔒 Sesión de administración cerrada para este repetidor", "info");
        }
      });
    }
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
        const password = this.getRepeaterPassword(target);
        if (!target) {
          alert("Selecciona primero un repetidor.");
          return;
        }
        if (!password) {
          alert("Ingresa la contraseña o PIN de administración del repetidor.");
          return;
        }
        await this.authenticateRepeater(target, password);
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
        const password = this.getRepeaterPassword(target);
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
            if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
              this.handleRepeaterAuthError(target, data.message);
            } else {
              this.showToast(`Error: ${data.message}`, "error");
            }
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
        const password = this.getRepeaterPassword(target);
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
            if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
              this.handleRepeaterAuthError(target, data.message);
            } else {
              this.showToast(`Error: ${data.message}`, "error");
            }
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
        const password = this.getRepeaterPassword(target);
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
            if (admin_password) {
              this.setStoredRepeaterPassword(target, admin_password);
            }
            this.appendTerminalLine(`✓ [RX OK] Parámetros de seguridad actualizados con éxito.`, "term-success");
            this.showToast("🔐 Seguridad actualizada en el repetidor", "success");
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
              this.handleRepeaterAuthError(target, data.message);
            } else {
              this.showToast(`Error: ${data.message}`, "error");
            }
          }
        } catch (err) {
          this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
        }
      });
    }

    // Botones de Telemetría y Reloj
    const btnRefreshTelem = document.getElementById("btnRefreshRepeaterTelem");
    if (btnRefreshTelem) {
      btnRefreshTelem.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.getRepeaterPassword(target);
        this.appendTerminalLine(`> [TX] Solicitando telemetría completa y parámetros a ${target.slice(0, 8)}...`, "term-cmd");
        btnRefreshTelem.disabled = true;
        btnRefreshTelem.textContent = "🔄 Consultando...";
        try {
          await this.executeRepeaterCommand(target, "stats-core", {}, password);
          await new Promise((r) => setTimeout(r, 400));
          await this.executeRepeaterCommand(target, "stats-radio", {}, password);
          await new Promise((r) => setTimeout(r, 400));
          await this.executeRepeaterCommand(target, "pos", {}, password);
          await new Promise((r) => setTimeout(r, 400));
          await this.executeRepeaterCommand(target, "owner", {}, password);
          this.showToast("📡 Solicitud de telemetría completa transmitida al repetidor", "info");
        } catch (_) {}
        finally {
          setTimeout(() => {
            btnRefreshTelem.disabled = false;
            btnRefreshTelem.textContent = "🔄 Actualizar Telemetría Remota (stats-core)";
          }, 1500);
        }
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
        const password = this.getRepeaterPassword(target);
        this.appendTerminalLine(`> [TX] Sondeando vecinos en la malla desde ${target.slice(0, 8)}...`, "term-cmd");
        await this.executeRepeaterCommand(target, "discover.neighbors", {}, password);
        this.refreshNeighborsTable(target);
      });
    }

    // Acciones Rápidas del Modal
    if (this.dom.btnModalHeaderPingZero) {
      this.dom.btnModalHeaderPingZero.addEventListener("click", () => {
        this.pingZero(this.selectedRepeaterTarget, this.selectedRepeaterName);
      });
    }
    if (this.dom.btnModalActionPingZero) {
      this.dom.btnModalActionPingZero.addEventListener("click", () => {
        this.pingZero(this.selectedRepeaterTarget, this.selectedRepeaterName);
      });
    }
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
        const password = this.getRepeaterPassword(target);
        this.executeRepeaterCommand(target, "telemetry", {}, password);
      });
    }

    const btnModalActionVer = document.getElementById("btnModalActionVersion");
    if (btnModalActionVer) {
      btnModalActionVer.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.getRepeaterPassword(target);
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
        const password = this.getRepeaterPassword(target);
        if (cmd === "ping 0" || cmd === "ping") {
          this.pingZero(target, this.selectedRepeaterName);
        } else {
          this.executeRepeaterCommand(target, cmd, {}, password);
        }
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
        const password = this.getRepeaterPassword(target);
        if (cmd.toLowerCase() === "ping" || cmd.toLowerCase() === "ping 0" || cmd.toLowerCase() === "pingzero") {
          this.pingZero(target, this.selectedRepeaterName);
        } else {
          this.executeRepeaterCommand(target, cmd, {}, password);
        }
      });
    }
  }

  async pingZero(targetNode, targetName) {
    const target = targetNode || this.selectedRepeaterTarget;
    const name = targetName || this.selectedRepeaterName || (target ? target.slice(0, 8) : "desconocido");
    if (!target) {
      this.showToast("⚠️ Selecciona un repetidor o nodo objetivo", "warning");
      return;
    }

    const norm = (target || "").toLowerCase().trim();
    const localPk = (this.localNodePubkey || "").toLowerCase().trim();
    const isLocal = Boolean(target === "local") || (localPk && (
      norm === localPk ||
      (localPk.length >= 8 && norm.startsWith(localPk.slice(0, 8))) ||
      (norm.length >= 8 && localPk.startsWith(norm.slice(0, 8)))
    ));
    if (isLocal) {
      this.showToast("No se puede hacer ping a la estación base local", "warning");
      return;
    }

    if (this.knownNodes.has(target)) {
      const nodeInfo = this.knownNodes.get(target);
      if (nodeInfo && nodeInfo.role === "CLIENT") {
        this.showToast("Ping Zero está disponible únicamente para repetidores de malla", "warning");
        return;
      }
    }

    this.appendTerminalLine(`> [PING ZERO] Enviando sonda directa de 0 saltos a ${name} (${target.slice(0, 8)})...`, "term-cmd");

    if (this.dom.adminModalPingZeroBadge) {
      this.dom.adminModalPingZeroBadge.textContent = "🎯 Ping 0: Midiendo...";
      this.dom.adminModalPingZeroBadge.className = "ping-zero-badge measuring";
    }
    if (this.dom.btnModalHeaderPingZero) {
      this.dom.btnModalHeaderPingZero.disabled = true;
      this.dom.btnModalHeaderPingZero.textContent = "🎯 Midiendo...";
    }
    if (this.dom.btnModalActionPingZero) {
      this.dom.btnModalActionPingZero.disabled = true;
      this.dom.btnModalActionPingZero.textContent = "🎯 Midiendo...";
    }

    try {
      const res = await fetch("/api/repeater/ping_zero", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target }),
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        const pingData = data.data;
        const rtt = Number(pingData.rtt_ms || pingData.duration_ms || 0);
        const rssi = pingData.rssi != null ? `${pingData.rssi} dBm` : "--";
        const snrThere = pingData.snr_there != null ? `${Number(pingData.snr_there).toFixed(1)} dB` : (pingData.snr != null ? `${Number(pingData.snr).toFixed(1)} dB` : "--");
        const snrBack = pingData.snr_back != null ? `${Number(pingData.snr_back).toFixed(1)} dB` : (pingData.snr != null ? `${Number(pingData.snr).toFixed(1)} dB` : "--");

        const line = `✓ [PONG DIRECTO] Duration: ${rtt} ms | SNR there: ${snrThere} | SNR back: ${snrBack} | RSSI: ${rssi}`;
        this.appendTerminalLine(line, "term-success");

        if (this.dom.adminModalPingZeroBadge) {
          const rssiPart = rssi !== "--" ? ` (${rssi})` : "";
          this.dom.adminModalPingZeroBadge.textContent = `🎯 Ping 0: ${rtt} ms${rssiPart}`;
          this.dom.adminModalPingZeroBadge.className = "ping-zero-badge ping-success";
        }
        if (this.dom.repQuickPingResult) {
          const rPart = rssi !== "--" ? ` • RSSI ${rssi}` : "";
          const sPart = (snrThere !== "--" || snrBack !== "--") ? ` • SNR ${snrThere}/${snrBack}` : "";
          this.dom.repQuickPingResult.textContent = `🟢 Duration: ${rtt} ms${sPart}${rPart} (0 Saltos)`;
        }

        // Actualizar nodo en knownNodes si existe
        const canonicalTarget = this.resolveCanonicalPubkey(target);
        const existing = this.knownNodes.get(canonicalTarget) || this.knownNodes.get(target) || {
          public_key: canonicalTarget || target,
          name: name,
        };
        existing.ping_zero_rtt = rtt;
        if (pingData.rssi != null) existing.last_rssi = Number(pingData.rssi);
        if (pingData.snr_back != null) existing.last_snr = Number(pingData.snr_back);
        else if (pingData.snr != null) existing.last_snr = Number(pingData.snr);
        existing.last_seen = Math.floor(Date.now() / 1000);
        this.knownNodes.set(canonicalTarget, existing);
        if (target !== canonicalTarget) {
          this.knownNodes.set(target, existing);
        }
        this.updateNodeInDom(canonicalTarget, existing);

        this.showToast(`🎯 Ping a ${name}: Duration: ${rtt} ms, SNR there: ${snrThere}, SNR back: ${snrBack} (RSSI: ${rssi})`, "success");
      } else {
        const errMsg = data.message || "Timeout esperando eco de 0 saltos";
        this.appendTerminalLine(`✗ [PING ZERO FALLIDO] ${errMsg}`, "term-error");
        if (this.dom.adminModalPingZeroBadge) {
          this.dom.adminModalPingZeroBadge.textContent = "🎯 Ping 0: Fallo";
          this.dom.adminModalPingZeroBadge.className = "ping-zero-badge ping-error";
        }
        if (this.dom.repQuickPingResult) {
          this.dom.repQuickPingResult.textContent = `🔴 Fallo: ${errMsg}`;
        }
        if (errMsg.toLowerCase().includes("password") || errMsg.toLowerCase().includes("auth") || errMsg.toLowerCase().includes("pin")) {
          this.handleRepeaterAuthError(target, errMsg);
        } else {
          this.showToast(`⚠️ Ping Zero: ${errMsg}`, "error");
        }
      }
    } catch (err) {
      this.appendTerminalLine(`✗ [PING ZERO ERROR] ${err.message}`, "term-error");
      if (this.dom.adminModalPingZeroBadge) {
        this.dom.adminModalPingZeroBadge.textContent = "🎯 Ping 0: Error";
        this.dom.adminModalPingZeroBadge.className = "ping-zero-badge ping-error";
      }
      this.showToast(`Error de red en Ping Zero: ${err.message}`, "error");
    } finally {
      if (this.dom.btnModalHeaderPingZero) {
        this.dom.btnModalHeaderPingZero.disabled = false;
        this.dom.btnModalHeaderPingZero.textContent = "🎯 Ping Zero";
      }
      if (this.dom.btnModalActionPingZero) {
        this.dom.btnModalActionPingZero.disabled = false;
        this.dom.btnModalActionPingZero.textContent = "🎯 Ejecutar Ping Zero";
      }
    }
  }

  async sendModalRepeaterAction(actionName) {
    const target = this.selectedRepeaterTarget;
    if (!target) {
      alert("Selecciona primero un repetidor.");
      return;
    }
    const password = this.getRepeaterPassword(target);
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
        if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
          this.handleRepeaterAuthError(target, data.message);
        } else {
          this.showToast(`Error: ${data.message}`, "error");
        }
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
        this.storage.clearSnifferPackets();
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

    // Cargar tramas del sniffer previamente guardadas en IndexedDB
    this.storage.getSnifferPackets().then((packets) => {
      if (packets && packets.length > 0 && this.rawPackets.length === 0) {
        for (const pkt of packets) {
          this.renderSnifferPacket(pkt, false);
        }
      }
    });
  }

  updateSnifferStats() {
    const totalEl = document.getElementById("snifferTotalPackets");
    const countAllEl = document.getElementById("snifferCountAll");
    const lastOpcodeEl = document.getElementById("snifferLastOpcode");

    const total = this.rawPackets.length;
    if (totalEl) totalEl.textContent = String(total);
    if (countAllEl) countAllEl.textContent = String(total);

    if (total > 0) {
      const lastPkt = this.rawPackets[0];
      if (lastOpcodeEl) {
        lastOpcodeEl.textContent = lastPkt.opcode || lastPkt.payload_type || "DATA";
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

  renderSnifferPacket(pkt, persist = true) {
    if (persist) {
      this.storage.saveSnifferPacket(pkt);
    }
    this.rawPackets.unshift(pkt);
    if (this.rawPackets.length > MAX_RAW_PACKETS) this.rawPackets.pop();

    if (this.dom.snifferTableBody.querySelector("td[colspan]")) {
      this.dom.snifferTableBody.innerHTML = "";
    }

    const tr = document.createElement("tr");
    const opcode = String(pkt.opcode || pkt.payload_type || "DATA").toUpperCase();
    const src = String(pkt.sender || pkt.src_node_id || pkt.from || "RF");
    const dst = String(pkt.to || pkt.dst_node_id || "0xFFFF");
    const snr = pkt.metrics?.snr != null ? pkt.metrics.snr : (pkt.snr != null ? pkt.snr : "--");
    const rssi = pkt.metrics?.rssi != null ? pkt.metrics.rssi : (pkt.rssi != null ? pkt.rssi : "--");
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

    const snrText = snr !== "--" ? `${snr} dB` : "--";
    const rssiText = rssi !== "--" ? `${rssi} dBm` : "--";

    tr.innerHTML = `
      <td style="color: var(--text-muted); font-size: 11px;">${new Date().toLocaleTimeString()}</td>
      <td><span class="badge-opcode ${badgeClass}">${this.escapeHtml(opcode)}</span></td>
      <td><code class="font-mono" title="${this.escapeHtml(src)}">${this.escapeHtml(shortSrc)}</code></td>
      <td><code class="font-mono" title="${this.escapeHtml(dst)}">${this.escapeHtml(shortDst)}</code></td>
      <td><strong>${snrText}</strong> <span style="color: var(--text-muted); font-size: 11px;">/ ${rssiText}</span></td>
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
    const snr = pkt.metrics?.snr != null ? pkt.metrics.snr : (pkt.snr != null ? pkt.snr : "--");
    const rssi = pkt.metrics?.rssi != null ? pkt.metrics.rssi : (pkt.rssi != null ? pkt.rssi : "--");
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

    if (payload.type === "contact_discovered" || payload.type === "contact_updated" || payload.event_type === "contact_discovered" || payload.event_type === "contact_updated") {
      const c = payload.contact || payload.data;
      if (c && c.public_key && this.isValidNodeKey(c.public_key)) {
        const canonicalPk = this.resolveCanonicalPubkey(c.public_key);
        if (this.isValidNodeKey(canonicalPk)) {
          this.knownNodes.set(canonicalPk, c);
          this.knownNodes.set(c.public_key, c);
          let isAlreadySaved = false;
          const cNameClean = (c.name || c.alias || "").trim().toLowerCase();
          for (const [k, node] of this.knownNodes.entries()) {
            if (!node) continue;
            const nodePk = String(node.public_key || "").toLowerCase();
            const nodeName = String(node.alias || node.name || "").trim().toLowerCase();
            const isMatchPk = nodePk === canonicalPk.toLowerCase() ||
              (nodePk.length >= 6 && canonicalPk.toLowerCase().length >= 6 && (nodePk.startsWith(canonicalPk.toLowerCase()) || canonicalPk.toLowerCase().startsWith(nodePk)));
            const isMatchName = cNameClean && !cNameClean.startsWith("node_") && !cNameClean.startsWith("unknow") && (nodeName === cNameClean);
            if ((isMatchPk || isMatchName) && node.auto_discovered === false) {
              isAlreadySaved = true;
              break;
            }
          }
          if (payload.is_new && !isAlreadySaved && c.name && !c.name.startsWith("Node_unknow")) {
            this.fetchDiscoveredContacts();
            const name = c.name || canonicalPk.slice(0, 8);
            this.showToast(`📡 Nuevo nodo descubierto en el aire: ${name}`, "info");
          }

        }
      } else {
        this.fetchNodes();
      }
      return;
    }

    if (payload.type === "message_delivered" || payload.event_type === "message_delivered") {
      const msgId = payload.msg_id;
      const rawAck = (payload.ack_code || "").toLowerCase();
      const ackClean = rawAck.startsWith("0x") ? rawAck.slice(2) : rawAck;
      const ackWithPrefix = `0x${ackClean}`;
      const tripTime = payload.trip_time_ms || 0;

      // 1. Actualizar elementos en el DOM actual
      let matchedRows = [];
      if (msgId) {
        matchedRows = Array.from(document.querySelectorAll(`.message-bubble-row[data-msg-id="${msgId}"]`));
      }
      if (matchedRows.length === 0 && ackClean) {
        matchedRows = Array.from(document.querySelectorAll(`.message-bubble-row[data-ack-code="${ackClean}"], .message-bubble-row[data-ack-code="${ackWithPrefix}"]`));
      }
      matchedRows.forEach((row) => {
        row.classList.add("delivered");
        const ackEl = row.querySelector(".msg-ack-status");
        if (ackEl) {
          ackEl.className = "msg-ack-status delivered";
          ackEl.textContent = "✓✓ TX";
          ackEl.title = `Entregado por radio (${tripTime} ms)`;
        }
      });

      // 2. Actualizar mensajes en memoria (channelFeeds) y en IndexedDB
      for (const [feedKey, msgs] of this.channelFeeds.entries()) {
        for (const m of msgs) {
          const mExp = (m.expected_ack || "").toLowerCase();
          const mExpClean = mExp.startsWith("0x") ? mExp.slice(2) : mExp;
          const isAckMatch = Boolean(ackClean && mExpClean && mExpClean === ackClean);
          if ((msgId && (m.id === msgId || m.msg_id === msgId)) || isAckMatch) {
            m.delivered = true;
            m.trip_time_ms = tripTime;
            this.storage.saveMessage(feedKey, m);
          }
        }
      }
      this.storage.updateMessageDelivery(msgId, ackClean, tripTime);

      // 3. El nodo destinatario que respondió con ACK está activo en la malla
      if (payload.recipient && payload.recipient !== "local" && payload.recipient !== "broadcast") {
        const canonicalRecipient = this.resolveCanonicalPubkey(payload.recipient);
        const existing = this.knownNodes.get(canonicalRecipient) || this.knownNodes.get(payload.recipient) || {
          public_key: canonicalRecipient || payload.recipient,
          role: "CLIENT",
        };
        const updated = {
          ...existing,
          public_key: existing.public_key || canonicalRecipient || payload.recipient,
          last_seen: Math.floor(Date.now() / 1000),
        };
        this.knownNodes.set(canonicalRecipient, updated);
        if (payload.recipient !== canonicalRecipient) {
          this.knownNodes.set(payload.recipient, updated);
        }
        this.updateNodeInDom(canonicalRecipient, updated);
      }
      return;
    }

    if (payload.type === "trace_data" && payload.data) {
      if (this.dom.tracerouteModal && !this.dom.tracerouteModal.classList.contains("hidden")) {
        this.renderTracerouteGraph(payload.data.hops_breakdown || []);
        this.renderTracerouteTable(payload.data.hops_breakdown || []);
      }
      return;
    }

    if (payload.event === "metrics_update" || payload.type === "metrics_update" || (payload.rx_count !== undefined && payload.tx_count !== undefined)) {
      this.updateHeaderMetrics(payload);
    } else if (payload.type === "repeater_response" || payload.event_type === "repeater_response") {
      const senderKey = payload.sender || payload.pubkey_prefix || "unknown";
      const rawText = (payload.text || payload.message || "").toLowerCase();
      const isRepeaterTarget = Boolean(this.selectedRepeaterTarget && (
        this.selectedRepeaterTarget === senderKey ||
        (this.selectedRepeaterTarget.length >= 8 && senderKey.length >= 8 && (this.selectedRepeaterTarget.startsWith(senderKey) || senderKey.startsWith(this.selectedRepeaterTarget)))
      ));

      if (payload.telemetry) {
        const canonicalPk = this.resolveCanonicalPubkey(senderKey);
        const existing = this.knownNodes.get(canonicalPk) || this.knownNodes.get(senderKey) || {};
        const updated = {
          ...existing,
          ...payload.telemetry,
          public_key: existing.public_key || canonicalPk || senderKey,
          last_seen: Math.floor(Date.now() / 1000),
        };
        this.knownNodes.set(canonicalPk, updated);
        this.knownNodes.set(senderKey, updated);
        if (isRepeaterTarget) {
          this.populateRepeaterModalData(updated);
        }
      }

      if (isRepeaterTarget) {
        if (payload.telemetry?.auth_status === "failed" ||
            rawText.includes("invalid password") ||
            rawText.includes("access denied") ||
            rawText.includes("bad pin") ||
            rawText.includes("login failed") ||
            rawText.includes("wrong password") ||
            rawText.includes("incorrect password") ||
            rawText.includes("not logged in") ||
            rawText.includes("permission denied")) {
          this.handleRepeaterAuthError(senderKey, "Contraseña incorrecta o cambiada en el repetidor");
        } else if (payload.telemetry?.auth_status === "success" ||
                   rawText.includes("login ok") ||
                   rawText.includes("logged in") ||
                   rawText.includes("auth ok") ||
                   rawText.includes("welcome admin") ||
                   payload.telemetry?.battery_pct !== undefined) {
          if (!this.authenticatedRepeaters.has(senderKey)) {
            this.authenticatedRepeaters.add(senderKey);
            this.unlockRepeaterAdminView(senderKey);
          }
        }
        if (payload.text) {
          this.appendTerminalLine(`← [RESP] ${payload.text}`, "term-resp");
        }
      }
      return;
    } else if (this.isCommonChatMessage(payload)) {
      const isDm = payload.event_type === "direct" || payload.type === "DIRECT_MSG";
      const chIdx = payload.channel_idx !== undefined ? Number(payload.channel_idx) : (payload.event_type === "channel" ? 1 : 0);
      const rawSenderKey = payload.sender || payload.pubkey_prefix || "unknown";
      const senderKey = isDm ? this.resolveCanonicalPubkey(rawSenderKey) : rawSenderKey;

      const rawText = payload.text || payload.message || "";
      let senderName = payload.sender_name || payload.name;
      const extracted = this.extractSenderAndText(rawText, senderName);
      if (extracted.senderName && (!senderName || senderName === rawSenderKey || senderName === senderKey || senderName.toLowerCase() === "unknown" || senderName.startsWith("Node_unknow"))) {
        senderName = extracted.senderName;
      }
      if (!senderName || senderName === rawSenderKey || senderName === senderKey || senderName.toLowerCase() === "unknown") {
        const known = this.knownNodes.get(senderKey) || this.knownNodes.get(rawSenderKey);
        senderName = known ? (known.alias || known.name || senderKey) : (senderName || senderKey);
      }
      if (senderName && (senderName.toLowerCase() === "unknown" || senderName.startsWith("Node_unknow"))) {
        senderName = extracted.senderName || (senderKey && this.isValidNodeKey(senderKey) ? senderKey : "Anónimo");
      }

      const feedKey = isDm ? `dm_${senderKey}` : `ch_${chIdx}`;

      if (!this.channelFeeds.has(feedKey)) {
        if (isDm && rawSenderKey !== senderKey && this.channelFeeds.has(`dm_${rawSenderKey}`)) {
          this.channelFeeds.set(feedKey, this.channelFeeds.get(`dm_${rawSenderKey}`));
        } else {
          this.channelFeeds.set(feedKey, []);
        }
      }

      const normalizedMsg = {
        sender: senderKey,
        sender_name: senderName,
        text: payload.text || payload.message || "",
        channel_idx: chIdx,
        txt_type: Number(payload.txt_type ?? payload.text_type ?? 0),
        is_outgoing: false,
        metrics: payload.metrics || { rssi: payload.rssi || payload.RSSI, snr: payload.snr || payload.SNR },
        timestamp: payload.timestamp || new Date().toISOString(),
      };

      const feed = this.channelFeeds.get(feedKey);
      feed.push(normalizedMsg);
      if (feed.length > MAX_FEED_MESSAGES) feed.shift();

      this.storage.saveMessage(feedKey, normalizedMsg);

      // Actualizar vivacidad y estado En Línea del nodo emisor en tiempo real
      if (senderKey && this.isValidNodeKey(senderKey) && senderKey !== "local") {
        const canonicalPk = this.resolveCanonicalPubkey(senderKey);
        const existing = this.knownNodes.get(canonicalPk) || this.knownNodes.get(senderKey) || {
          public_key: canonicalPk || senderKey,
          name: senderName,
          role: isDm ? "CLIENT" : "CLIENT",
        };
        const nowEpoch = Math.floor(Date.now() / 1000);
        const updatedNode = {
          ...existing,
          public_key: existing.public_key || canonicalPk || senderKey,
          name: existing.name || senderName,
          alias: existing.alias || (senderName !== senderKey ? senderName : null),
          last_seen: nowEpoch,
          last_rssi: payload.rssi != null ? payload.rssi : (payload.metrics?.rssi != null ? payload.metrics.rssi : existing.last_rssi),
          last_snr: payload.snr != null ? payload.snr : (payload.metrics?.snr != null ? payload.metrics.snr : existing.last_snr),
          hops: payload.hops != null ? payload.hops : (payload.hop_count != null ? payload.hop_count : existing.hops),
          ...(payload.telemetry || {}),
        };
        this.knownNodes.set(canonicalPk, updatedNode);
        if (senderKey !== canonicalPk) {
          this.knownNodes.set(senderKey, updatedNode);
        }
        this.updateNodeInDom(canonicalPk, updatedNode);
      }

      let isCurrent = false;
      if (isDm) {
        isCurrent = Boolean(this.activeDmTarget && (
          this.activeDmTarget === senderKey ||
          this.activeDmTarget === rawSenderKey ||
          (this.activeDmTarget.length >= 8 && senderKey.length >= 8 && (this.activeDmTarget.startsWith(senderKey) || senderKey.startsWith(this.activeDmTarget)))
        ));
      } else {
        isCurrent = !this.activeDmTarget && this.activeChannelIdx === chIdx;
      }

      const isChatTabActive = document.getElementById("tab-chat")?.classList.contains("active");

      if (isCurrent && isChatTabActive) {
        this.appendChatMessage(normalizedMsg);
        this.lastReadTimestamps.set(feedKey, normalizedMsg.timestamp);
        this.unreadCounts.set(feedKey, 0);
        this.updateFeedUnreadBadge(feedKey);
      } else {
        const unread = (this.unreadCounts.get(feedKey) || 0) + 1;
        this.unreadCounts.set(feedKey, unread);
        this.updateFeedUnreadBadge(feedKey);
      }

      if (isDm && senderKey && this.isValidNodeKey(senderKey)) {
        this.conversationsWithMessages.add(senderKey);
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
      if (senderKey && this.isValidNodeKey(senderKey)) {
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
          this.populateRepeaterModalData(updated);
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
            const rawSnr = n.last_snr != null ? n.last_snr : (n.snr != null ? n.snr : null);
            const rawRssi = n.last_rssi != null ? n.last_rssi : (n.rssi != null ? n.rssi : null);
            const snr = rawSnr != null ? parseFloat(rawSnr) : null;
            const rssi = rawRssi != null ? rawRssi : "--";

            const snrNum = snr != null ? snr : 0;
            const pct = Math.min(Math.max(((snrNum + 15) / 30) * 100, 10), 100);
            const qualityClass = snr != null ? (snr >= 6 ? "good" : (snr >= 0 ? "medium" : "poor")) : "medium";

            tr.innerHTML = `
              <td><strong>${this.escapeHtml(name)}</strong></td>
              <td><strong>${snr != null ? `${snr.toFixed(1)} dB` : "--"}</strong></td>
              <td>${rssi !== "--" ? `${rssi} dBm` : "--"}</td>
              <td>
                <div class="signal-bar-wrap">
                  <div class="signal-bar-bg">
                    <div class="signal-bar-fill ${qualityClass}" style="width: ${pct}%;"></div>
                  </div>
                  <span style="font-size: 10.5px; color: var(--text-muted);">${snr != null ? qualityClass.toUpperCase() : "N/D"}</span>
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
            const clientsCount = r.connected_clients_count != null ? r.connected_clients_count : (r.neighbors ? r.neighbors.length : 0);
            const txPower = r.tx_power != null ? `${r.tx_power} dBm` : "--";
            const hopLimit = r.hop_limit != null ? `${r.hop_limit} saltos` : (r.hops != null ? `${r.hops} saltos` : "--");

            tr.innerHTML = `
              <td><strong>${this.escapeHtml(name)}</strong></td>
              <td><span class="badge-pill badge-success">${clientsCount} nodo(s)</span></td>
              <td>${txPower}</td>
              <td>${hopLimit}</td>
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
    if (this.dom.btnPublishHaDiscovery) {
      this.dom.btnPublishHaDiscovery.addEventListener("click", () => {
        this.publishHomeAssistantDiscovery();
      });
    }
  }

  async publishHomeAssistantDiscovery() {
    if (!this.dom.btnPublishHaDiscovery) return;
    try {
      this.dom.btnPublishHaDiscovery.disabled = true;
      this.dom.btnPublishHaDiscovery.textContent = "📢 Anunciando...";
      const res = await fetch("/api/ha/publish", { method: "POST" });
      const data = await res.json();
      if (data.status === "ok") {
        if (this.dom.haDiscoveredCount) {
          this.dom.haDiscoveredCount.textContent = data.data.published_entities;
        }
        alert(`✓ Home Assistant Discovery anunciado con éxito (${data.data.published_entities} entidades).`);
      }
    } catch (e) {
      alert("Error al anunciar Home Assistant Discovery: " + e.message);
    } finally {
      if (this.dom.btnPublishHaDiscovery) {
        this.dom.btnPublishHaDiscovery.disabled = false;
        this.dom.btnPublishHaDiscovery.textContent = "📢 Re-anunciar Discovery en MQTT";
      }
    }
  }

  initPreflight() {
    if (this.dom.btnRunPreflight) {
      this.dom.btnRunPreflight.addEventListener("click", async () => {
        if (this.dom.preflightResults) {
          this.dom.preflightResults.innerHTML = "Ejecutando comprobaciones de diagnóstico...";
        }
        try {
          const res = await fetch("/api/preflight");
          const data = await res.json();
          if (data.status === "ok") {
            this.renderPreflightReport(data.data);
          }
        } catch (err) {
          if (this.dom.preflightResults) {
            this.dom.preflightResults.innerHTML = `<span class="text-danger">Error: ${err.message}</span>`;
          }
        }
      });
    }
  }

  renderPreflightReport(report) {
    if (!this.dom.preflightResults) return;
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

    const btnAdvertHop = document.getElementById("btnActionAdvertHop");
    if (btnAdvertHop) {
      btnAdvertHop.addEventListener("click", async () => {
        await this.sendAdvert(false);
      });
    }

    const btnAdvertFlood = document.getElementById("btnActionAdvertFlood");
    if (btnAdvertFlood) {
      btnAdvertFlood.addEventListener("click", async () => {
        await this.sendAdvert(true);
      });
    }

    const btnAdvertClipboard = document.getElementById("btnActionAdvertClipboard");
    if (btnAdvertClipboard) {
      btnAdvertClipboard.addEventListener("click", () => {
        this.copyAdvertToClipboard();
      });
    }

    const btnAdvert = document.getElementById("btnLocalAdvertNow") || document.getElementById("btnActionBroadcastAdvert");
    if (btnAdvert) {
      btnAdvert.addEventListener("click", async () => {
        await this.sendAdvert(false);
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

    // 9. Manejadores de Almacenamiento IndexedDB y Mapas Offline
    const btnClearStorage = document.getElementById("btnClearIndexedDbStorage");
    if (btnClearStorage) {
      btnClearStorage.addEventListener("click", async () => {
        if (confirm("¿Estás seguro de vaciar todo el historial de chat y tramas sniffer guardadas en IndexedDB?")) {
          await this.storage.clearAll();
          this.channelFeeds.clear();
          this.rawPackets = [];
          if (this.dom.chatMessageFeed) this.dom.chatMessageFeed.innerHTML = "";
          if (this.dom.snifferTableBody) this.dom.snifferTableBody.innerHTML = '<tr><td colspan="8" class="text-center">Historial limpiado.</td></tr>';
          this.showToast("🧹 Almacenamiento local IndexedDB vaciado", "success");
        }
      });
    }

    const inputLocalTileUrl = document.getElementById("inputLocalTileUrl");
    const btnSaveMapSettings = document.getElementById("btnSaveMapSettings");
    if (inputLocalTileUrl) {
      inputLocalTileUrl.value = this.localTileUrl;
    }
    if (btnSaveMapSettings && inputLocalTileUrl) {
      btnSaveMapSettings.addEventListener("click", () => {
        const url = inputLocalTileUrl.value.trim();
        if (url) {
          this.localTileUrl = url;
          localStorage.setItem("meshcore_local_tile_url", url);
          if (this.tileLayers && this.tileLayers.local) {
            this.tileLayers.local.setUrl(url);
          }
          this.showToast("💾 Configuración de servidor de mapas offline guardada", "success");
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
      if (cfg.public_key) {
        this.localNodePubkey = String(cfg.public_key).toLowerCase().trim();
      }

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

      // Badges de Puerto Serie y Rol
      const roleBadge = document.getElementById("localNodeRoleBadge");
      if (roleBadge) roleBadge.textContent = cfg.role || "Estación Base";

      const portBadge = document.getElementById("localNodeSerialPortBadge");
      if (portBadge && (cfg.serial_port || cfg.port)) {
        portBadge.textContent = cfg.serial_port || cfg.port;
      }

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

      // Telemetría en Vivo de Transceptor Local
      const batVal = cfg.battery_pct != null ? cfg.battery_pct : (cfg.battery != null ? cfg.battery : 100);
      const batEl = document.getElementById("localBatValue");
      if (batEl) batEl.textContent = `${batVal}%`;

      const voltVal = cfg.battery_mv != null ? (cfg.battery_mv / 1000).toFixed(2) : (cfg.voltage != null ? Number(cfg.voltage).toFixed(2) : "5.00");
      const vEl = document.getElementById("localVoltValue");
      if (vEl) vEl.textContent = `${voltVal} V`;

      const pwrEl = document.getElementById("localSolarValue");
      if (pwrEl) pwrEl.textContent = cfg.power_source || "Conectado";

      const pwrStatusEl = document.getElementById("localSolarStatus");
      if (pwrStatusEl) pwrStatusEl.textContent = cfg.power_status || "USB 5V Directo";

      const clockEl = document.getElementById("localClockValue");
      if (clockEl) clockEl.textContent = cfg.clock || new Date().toLocaleTimeString();

      const upEl = document.getElementById("localUptimeValue");
      if (upEl) upEl.textContent = cfg.uptime_str || (cfg.uptime != null ? `${cfg.uptime}s` : "En línea");

      const airEl = document.getElementById("localAirtimeValue");
      if (airEl) airEl.textContent = `${cfg.airtime_ms ?? 0} ms`;

      const dutyEl = document.getElementById("localAirtimeDuty");
      if (dutyEl) dutyEl.textContent = `Duty Cycle: ${cfg.duty_cycle_pct ?? 0}%`;

      const snrEl = document.getElementById("localSnrValue");
      if (snrEl) snrEl.textContent = cfg.last_snr != null ? `${cfg.last_snr} dB` : "-- dB";

      const rssiEl = document.getElementById("localRssiValue");
      if (rssiEl) rssiEl.textContent = cfg.last_rssi != null ? `RSSI: ${cfg.last_rssi} dBm` : "RSSI: -- dBm";

      const noiseEl = document.getElementById("localNoiseValue");
      if (noiseEl) noiseEl.textContent = `${cfg.noise_floor_dbm ?? -118} dBm`;

      const packetsEl = document.getElementById("localPacketsValue");
      if (packetsEl) packetsEl.textContent = `${cfg.tx_count ?? 0} / ${cfg.rx_count ?? 0}`;

      const errEl = document.getElementById("localPacketErrorsValue");
      if (errEl) errEl.textContent = `Duplicados: ${cfg.duplicate_packets ?? 0} | Errores: ${cfg.packet_errors ?? 0}`;

      // Actualizar información del puerto serial
      if (cfg.serial_port && portBadge) portBadge.textContent = cfg.serial_port;
    } catch (err) {
      console.warn("Error cargando configuración local:", err);
    }
  }

  async sendAdvert(flood = false) {
    try {
      const modeStr = flood ? "Flood Routed (toda la malla)" : "Hop 0 (vecindario directo)";
      const res = await fetch("/api/node/advert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ flood: flood }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.showToast(`📢 Anuncio Advert emitido: ${modeStr}`, "success");
      } else {
        this.showToast(`⚠️ Error al emitir anuncio: ${data.message || "Fallo en radio"}`, "warning");
      }
    } catch (e) {
      console.warn("Fallo emitiendo advert:", e);
      this.showToast("Error de conexión al emitir anuncio", "error");
    }
  }

  copyAdvertToClipboard() {
    const pk = this.localNodePubkey || "000000000000";
    const name = document.getElementById("localNodeName")?.value || "MeshCore_Base";
    const uri = `meshcore://contact?pubkey=${encodeURIComponent(pk)}&name=${encodeURIComponent(name)}&role=CLIENT`;
    navigator.clipboard.writeText(uri).then(() => {
      this.showToast("📋 Tarjeta de contacto MeshCore copiada al portapapeles", "success");
    }).catch(() => {
      this.showToast("No se pudo acceder al portapapeles", "error");
    });
  }

  focusNodeOnMap(pubkey) {
    const navBtn = document.querySelector('.nav-btn[data-tab="tab-map"]');
    if (navBtn) navBtn.click();
    setTimeout(() => {
      if (this.map) {
        this.map.invalidateSize();
        this.selectMapNode(pubkey);
      }
    }, 150);
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
    if (this.dom.btnDownloadRawLogs) {
      this.dom.btnDownloadRawLogs.addEventListener("click", () => this.downloadRawLogs());
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

    return row;
  }

  appendLogEntryToDom(log) {
    if (!this.dom.systemLogsFeed) return;
    if (this.dom.systemLogsFeed.querySelector("div[style]")) {
      this.dom.systemLogsFeed.innerHTML = "";
    }
    const el = this.createLogElement(log);
    this.dom.systemLogsFeed.appendChild(el);
    while (this.dom.systemLogsFeed.children.length > MAX_SYSTEM_LOGS) {
      this.dom.systemLogsFeed.removeChild(this.dom.systemLogsFeed.firstElementChild);
    }
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

  initChat() {
    if (this.dom.chatInputForm) {
      this.dom.chatInputForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = this.dom.chatInputText ? this.dom.chatInputText.value.trim() : "";
        if (!text) return;
        if (this.dom.chatInputText) this.dom.chatInputText.value = "";

        const msgId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
        const canonicalTarget = this.activeDmTarget ? this.resolveCanonicalPubkey(this.activeDmTarget) : null;
        const target = canonicalTarget || "broadcast";
        const outgoingMsg = {
          id: msgId,
          msg_id: msgId,
          sender: "local",
          sender_name: "Estación Local (Tú)",
          text: text,
          is_outgoing: true,
          channel_idx: this.activeChannelIdx,
          dm_target: canonicalTarget,
          timestamp: new Date().toISOString(),
          delivered: false,
        };

        const feedKey = canonicalTarget ? `dm_${canonicalTarget}` : `ch_${this.activeChannelIdx}`;
        if (!this.channelFeeds.has(feedKey)) this.channelFeeds.set(feedKey, []);
        const feed = this.channelFeeds.get(feedKey);
        feed.push(outgoingMsg);
        if (feed.length > MAX_FEED_MESSAGES) feed.shift();

        this.storage.saveMessage(feedKey, outgoingMsg);

        if (canonicalTarget) {
          this.conversationsWithMessages.add(canonicalTarget);
          this.addDmContact(canonicalTarget, this.activeDmName);
        }

        this.appendChatMessage(outgoingMsg);

        try {
          const res = await fetch("/api/tx", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              to: target,
              channel_index: this.activeChannelIdx,
              text: text,
              request_id: msgId,
            }),
          });
          const txData = await res.json();
          if (txData && txData.data && txData.data.expected_ack) {
            outgoingMsg.expected_ack = txData.data.expected_ack;
            const bubble = document.querySelector(`.message-bubble-row[data-msg-id="${msgId}"]`);
            if (bubble) {
              bubble.setAttribute("data-ack-code", String(txData.data.expected_ack).toLowerCase());
            }
            this.storage.saveMessage(feedKey, outgoingMsg);
          }
        } catch (err) {
          console.error("Error transmitiendo mensaje:", err);
        }
      });
    }

    if (this.dom.clearChatBtn) {
      this.dom.clearChatBtn.addEventListener("click", () => {
        const canonicalTarget = this.activeDmTarget ? this.resolveCanonicalPubkey(this.activeDmTarget) : null;
        const feedKey = canonicalTarget ? `dm_${canonicalTarget}` : `ch_${this.activeChannelIdx}`;
        this.channelFeeds.set(feedKey, []);
        this.storage.clearFeedMessages(feedKey);
        if (this.dom.chatMessageFeed) this.dom.chatMessageFeed.innerHTML = "";
      });
    }

    if (this.dom.channelListUi) {
      this.dom.channelListUi.addEventListener("click", (e) => {
        const li = e.target.closest("li.channel-item");
        if (li && li.hasAttribute("data-channel-idx")) {
          const idx = li.getAttribute("data-channel-idx");
          this.switchChannel(parseInt(idx, 10));
        }
      });
    }
  }

  resolveCanonicalPubkey(rawKey) {
    if (!rawKey || typeof rawKey !== "string") return rawKey;
    const norm = rawKey.trim().toLowerCase();
    if (!norm || norm === "unknown" || norm === "broadcast" || norm === "local") return norm;

    // 1. Buscar en this.knownNodes coincidencia exacta o por prefijo (>= 8 caracteres)
    for (const [k, node] of this.knownNodes.entries()) {
      const kNorm = String(k).trim().toLowerCase();
      if (kNorm === norm) return k;
      if (kNorm.length >= 8 && norm.length >= 8) {
        if (kNorm.startsWith(norm) || norm.startsWith(kNorm)) {
          return kNorm.length >= norm.length ? k : rawKey;
        }
      }
      if (norm.length === 12 && kNorm.startsWith(norm)) return k;
      if (kNorm.length === 12 && norm.startsWith(kNorm)) return norm.length >= kNorm.length ? rawKey : k;
    }

    // 2. Buscar en elementos existentes de la lista DM
    if (this.dom.dmListUi) {
      const items = this.dom.dmListUi.querySelectorAll("li.channel-item");
      for (const item of items) {
        const pk = String(item.getAttribute("data-pubkey") || "").trim().toLowerCase();
        if (pk === norm) return item.getAttribute("data-pubkey");
        if (pk.length >= 8 && norm.length >= 8 && (pk.startsWith(norm) || norm.startsWith(pk))) {
          return pk.length >= norm.length ? item.getAttribute("data-pubkey") : rawKey;
        }
      }
    }

    // 3. Buscar por coincidencia en knownNodes si coinciden
    for (const node of this.knownNodes.values()) {
      const nodePk = String(node.public_key || "").trim().toLowerCase();
      if (nodePk.length >= 8 && norm.length >= 8 && (nodePk.startsWith(norm) || norm.startsWith(nodePk))) {
        return node.public_key;
      }
    }

    return rawKey;
  }

  async switchChannel(idx) {
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

    await this.renderCurrentConversation();
  }

  async setDmTarget(pubkey, name) {
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    this.activeDmTarget = canonicalPk;

    let cleanName = name;
    if (!cleanName || cleanName === pubkey || cleanName === canonicalPk) {
      const known = this.knownNodes.get(canonicalPk) || this.knownNodes.get(pubkey);
      cleanName = known ? (known.alias || known.name || canonicalPk) : (cleanName || canonicalPk);
    }
    this.activeDmName = cleanName;

    if (this.dom.sidebarChannelList) {
      this.dom.sidebarChannelList.classList.remove("mobile-open");
    }

    this.addDmContact(canonicalPk, this.activeDmName);

    document.querySelectorAll("#channelListUi li").forEach((li) => li.classList.remove("active"));
    document.querySelectorAll("#dmListUi li").forEach((li) => {
      const itemPk = (li.getAttribute("data-pubkey") || "").trim().toLowerCase();
      const cPkLower = canonicalPk.toLowerCase();
      const isMatch = itemPk === cPkLower ||
        (itemPk.length >= 8 && cPkLower.length >= 8 && (itemPk.startsWith(cPkLower) || cPkLower.startsWith(itemPk)));
      li.classList.toggle("active", isMatch);
      li.setAttribute("aria-selected", String(isMatch));
    });

    this.dom.chatActiveTitle.textContent = `${this.activeDmName}`;
    if (this.dom.chatSecurityChip) this.dom.chatSecurityChip.textContent = "🔒 Privado";
    this.dom.chatActiveSub.textContent = `Mensaje directo punto a punto • ${this.activeDmName}`;

    await this.renderCurrentConversation();
  }

  openDmConversation(pubkey, name) {
    const norm = (pubkey || "").toLowerCase().trim();
    const localPk = (this.localNodePubkey || "").toLowerCase().trim();
    const isLocal = Boolean(pubkey === "local") || (localPk && (
      norm === localPk ||
      (localPk.length >= 8 && norm.startsWith(localPk.slice(0, 8))) ||
      (norm.length >= 8 && localPk.startsWith(norm.slice(0, 8)))
    ));
    if (isLocal) {
      this.showToast("No se puede iniciar chat directo con la estación base local", "warning");
      return;
    }

    const navBtn = document.querySelector('.nav-btn[data-tab="tab-chat"]');
    if (navBtn) navBtn.click();
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    this.conversationsWithMessages.add(canonicalPk);
    this.addDmContact(canonicalPk, name);
    this.setDmTarget(canonicalPk, name);
    if (this.dom.chatInputText) this.dom.chatInputText.focus();
  }

  async renderCurrentConversation() {
    this.dom.chatMessageFeed.innerHTML = "";
    const canonicalTarget = this.activeDmTarget ? this.resolveCanonicalPubkey(this.activeDmTarget) : null;
    const feedKey = canonicalTarget ? `dm_${canonicalTarget}` : `ch_${this.activeChannelIdx}`;

    if (!this.channelFeeds.has(feedKey) || this.channelFeeds.get(feedKey).length === 0) {
      let stored = await this.storage.getMessagesByFeed(feedKey);
      if (stored && stored.length > 0) {
        stored = stored.filter((m) => !this.isCommandOrSystemText(m.text, m.txt_type));
        this.channelFeeds.set(feedKey, stored);
      } else if (canonicalTarget && this.activeDmTarget && canonicalTarget !== this.activeDmTarget) {
        let storedOld = await this.storage.getMessagesByFeed(`dm_${this.activeDmTarget}`);
        if (storedOld && storedOld.length > 0) {
          storedOld = storedOld.filter((m) => !this.isCommandOrSystemText(m.text, m.txt_type));
          this.channelFeeds.set(feedKey, storedOld);
        }
      }
    }

    const rawMessages = this.channelFeeds.get(feedKey) || [];
    const messages = rawMessages.filter((m) => !this.isCommandOrSystemText(m.text, m.txt_type));
    this.channelFeeds.set(feedKey, messages);

    if (messages.length === 0) {
      this.unreadCounts.set(feedKey, 0);
      this.updateFeedUnreadBadge(feedKey);
      return;
    }

    const lastReadTimeStr = this.lastReadTimestamps.get(feedKey);
    const unreadCount = this.unreadCounts.get(feedKey) || 0;
    let dividerInserted = false;

    let firstUnreadIndex = -1;
    if (unreadCount > 0) {
      firstUnreadIndex = Math.max(0, messages.length - unreadCount);
    } else if (lastReadTimeStr) {
      const lastReadTs = new Date(lastReadTimeStr).getTime();
      firstUnreadIndex = messages.findIndex(
        (m) => !m.is_outgoing && m.timestamp && new Date(m.timestamp).getTime() > lastReadTs
      );
    }

    for (let i = 0; i < messages.length; i++) {
      if (firstUnreadIndex !== -1 && i === firstUnreadIndex && !dividerInserted) {
        const divider = document.createElement("div");
        divider.className = "chat-unread-divider";
        divider.id = "chatUnreadDivider";
        divider.innerHTML = `
          <div class="unread-divider-line"></div>
          <span class="unread-divider-pill">⚡ Mensajes Nuevos</span>
          <div class="unread-divider-line"></div>
        `;
        this.dom.chatMessageFeed.appendChild(divider);
        dividerInserted = true;
      }
      this.appendChatMessage(messages[i]);
    }

    // Marcar conversación como leída
    const lastMsg = messages[messages.length - 1];
    this.lastReadTimestamps.set(feedKey, lastMsg?.timestamp || new Date().toISOString());
    this.unreadCounts.set(feedKey, 0);
    this.updateFeedUnreadBadge(feedKey);

    // Scroll inteligente: al delimitador de nuevos mensajes si existe, o al fondo
    const unreadDividerEl = document.getElementById("chatUnreadDivider");
    if (unreadDividerEl) {
      unreadDividerEl.scrollIntoView({ behavior: "smooth", block: "center" });
    } else {
      this.dom.chatMessageFeed.scrollTop = this.dom.chatMessageFeed.scrollHeight;
    }
  }

  updateGlobalUnreadBadge() {
    let total = 0;
    for (const count of this.unreadCounts.values()) {
      total += count;
    }
    const badge = this.dom.globalChatUnreadBadge || document.getElementById("globalChatUnreadBadge");
    if (badge) {
      badge.textContent = total > 99 ? "99+" : String(total);
      badge.classList.toggle("hidden", total === 0);
    }
  }

  updateFeedUnreadBadge(feedKey) {
    const count = this.unreadCounts.get(feedKey) || 0;
    if (feedKey.startsWith("ch_")) {
      const chIdx = feedKey.replace("ch_", "");
      const li = this.dom.channelListUi?.querySelector(`li[data-channel-idx="${chIdx}"]`);
      if (li) {
        let badge = li.querySelector(".ch-unread-badge");
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "ch-unread-badge";
          const actions = li.querySelector(".ch-actions");
          if (actions) li.insertBefore(badge, actions);
          else li.appendChild(badge);
        }
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.classList.toggle("hidden", count === 0);
      }
    } else if (feedKey.startsWith("dm_")) {
      const pk = feedKey.replace("dm_", "");
      const li = this.dom.dmListUi?.querySelector(`li[data-pubkey="${pk}"]`);
      if (li) {
        let badge = li.querySelector(".ch-unread-badge");
        if (!badge) {
          badge = document.createElement("span");
          badge.className = "ch-unread-badge";
          const actions = li.querySelector(".ch-actions");
          if (actions) li.insertBefore(badge, actions);
          else li.appendChild(badge);
        }
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.classList.toggle("hidden", count === 0);
      }
    }
    this.updateGlobalUnreadBadge();
  }

  appendChatMessage(msg) {
    if (this.dom.chatMessageFeed.querySelector(".chat-welcome-card")) {
      this.dom.chatMessageFeed.innerHTML = "";
    }

    const row = document.createElement("div");
    row.className = `message-bubble-row ${msg.is_outgoing ? "outgoing" : "incoming"} ${msg.delivered ? "delivered" : ""}`;
    const msgId = msg.id || msg.msg_id || (msg.is_outgoing && msg.timestamp ? `msg_${Date.parse(msg.timestamp)}` : "");
    if (msgId) {
      row.setAttribute("data-msg-id", String(msgId));
    }
    if (msg.expected_ack) {
      row.setAttribute("data-ack-code", String(msg.expected_ack).toLowerCase());
    }

    const timeStr = new Date(msg.timestamp || Date.now()).toLocaleTimeString();
    let sender = msg.sender_name || msg.sender || "Anónimo";
    const rawText = msg.text || "";

    const extracted = this.extractSenderAndText(rawText, sender);
    if (!sender || sender.toLowerCase() === "unknown" || sender.toLowerCase() === "anónimo" || sender.toLowerCase() === "anonimo" || sender.startsWith("Node_unknow") || sender === msg.sender) {
      if (extracted.senderName && extracted.senderName.toLowerCase() !== "unknown") {
        sender = extracted.senderName;
      }
    }
    if (msg.sender && this.knownNodes) {
      const canonical = this.resolveCanonicalPubkey(msg.sender);
      const known = this.knownNodes.get(canonical) || this.knownNodes.get(msg.sender);
      if (known && (known.alias || known.name) && !known.name.startsWith("Node_unknow")) {
        sender = known.alias || known.name;
      }
    }
    if (!sender || sender.toLowerCase() === "unknown") {
      sender = extracted.senderName || "Anónimo";
    }

    const rssi = msg.metrics?.rssi != null ? msg.metrics.rssi : (msg.rssi != null ? msg.rssi : null);
    const snr = msg.metrics?.snr != null ? msg.metrics.snr : (msg.snr != null ? msg.snr : null);
    const ackSymbol = msg.delivered ? "✓✓ TX" : (msg.is_outgoing ? "✓ TX" : "📥 RX");
    const ackTitle = msg.delivered ? `Entregado (${msg.trip_time_ms || 0} ms)` : (msg.is_outgoing ? "Transmitido por radio" : "Recibido");


    let signalHtml = "";
    if (rssi != null && snr != null) {
      signalHtml = `<span class="signal-chip">📶 ${rssi} dBm / ${snr} dB</span>`;
    } else if (rssi != null) {
      signalHtml = `<span class="signal-chip">📶 ${rssi} dBm</span>`;
    } else if (snr != null) {
      signalHtml = `<span class="signal-chip">📶 ${snr} dB</span>`;
    }

    row.innerHTML = `
      <div class="msg-meta">
        <strong>${this.escapeHtml(sender)}</strong>
        <span>${timeStr}</span>
      </div>
      <div class="msg-bubble">${this.escapeHtml(msg.text)}</div>
      <div class="msg-footer">
        ${signalHtml}
        <span class="msg-ack-status ${msg.delivered ? 'delivered' : (msg.is_outgoing ? 'sent' : 'received')}" title="${ackTitle}">${ackSymbol}</span>
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

    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    const roleStr = (role || "CLIENT").toUpperCase();
    const isClient = roleStr === "CLIENT" || roleStr === "CHAT" || role === "1" || role === 1;
    if (!isClient) return;

    // Excluir nodo local
    const isLocal = (this.localNodePubkey && (
      canonicalPk.toLowerCase() === this.localNodePubkey ||
      (this.localNodePubkey.length >= 8 && canonicalPk.toLowerCase().startsWith(this.localNodePubkey.slice(0, 8))) ||
      (canonicalPk.length >= 8 && this.localNodePubkey.startsWith(canonicalPk.toLowerCase().slice(0, 8)))
    )) || canonicalPk.toLowerCase() === "local";
    if (isLocal) return;

    // Solo mostrar si tiene mensajes o si es la conversación actualmente abierta
    const feedKey = `dm_${canonicalPk}`;
    const hasMessages = this.conversationsWithMessages.has(canonicalPk) ||
      this.conversationsWithMessages.has(pubkey) ||
      (this.channelFeeds.has(feedKey) && this.channelFeeds.get(feedKey).length > 0) ||
      (this.channelFeeds.has(`dm_${pubkey}`) && this.channelFeeds.get(`dm_${pubkey}`).length > 0) ||
      this.activeDmTarget === canonicalPk ||
      this.activeDmTarget === pubkey;

    if (!hasMessages) return;

    const emptyHint = this.dom.dmListUi.querySelector(".empty-hint");
    if (emptyHint) emptyHint.remove();

    // Buscar si ya existe un elemento li para esta clave o cualquier prefijo coincidente y deduplicar
    let li = null;
    const allItems = this.dom.dmListUi.querySelectorAll("li.channel-item");
    for (const item of allItems) {
      const itemPk = (item.getAttribute("data-pubkey") || "").trim().toLowerCase();
      const cPkLower = canonicalPk.toLowerCase();
      const isMatch = itemPk === cPkLower ||
          (itemPk.length >= 8 && cPkLower.length >= 8 && (itemPk.startsWith(cPkLower) || cPkLower.startsWith(itemPk)));
      if (isMatch) {
        if (!li) {
          li = item;
          if (canonicalPk.length >= itemPk.length) {
            li.setAttribute("data-pubkey", canonicalPk);
          }
        } else {
          // Elemento duplicado encontrado: eliminarlo del DOM
          item.remove();
        }
      }
    }

    // Resolver nombre limpio desde knownNodes
    let cleanName = name;
    if (!cleanName || cleanName === pubkey || cleanName === canonicalPk) {
      const known = this.knownNodes.get(canonicalPk) || this.knownNodes.get(pubkey);
      cleanName = known ? (known.alias || known.name || canonicalPk) : (cleanName || canonicalPk);
    }

    const isAct = Boolean(this.activeDmTarget && (
      this.activeDmTarget === canonicalPk ||
      this.activeDmTarget === pubkey ||
      (this.activeDmTarget.length >= 8 && canonicalPk.length >= 8 && (this.activeDmTarget.startsWith(canonicalPk) || canonicalPk.startsWith(this.activeDmTarget)))
    ));
    const roleIcon = "👤";
    const unreadCount = this.unreadCounts.get(feedKey) || 0;
    const unreadBadgeHtml = `<span class="ch-unread-badge ${unreadCount > 0 ? '' : 'hidden'}">${unreadCount}</span>`;

    if (!li) {
      li = document.createElement("li");
      li.className = `channel-item ${isAct ? "active" : ""}`;
      li.setAttribute("data-pubkey", canonicalPk);
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(isAct));
      li.innerHTML = `
        <span class="ch-badge">${roleIcon}</span>
        <span class="ch-name" title="${this.escapeHtml(cleanName)}">${this.escapeHtml(cleanName)}</span>
        ${unreadBadgeHtml}
        <div class="ch-actions">
          <button type="button" class="btn-item-delete" title="Cerrar conversación de la lista" data-del-dm="${canonicalPk}">✕</button>
        </div>
      `;
      li.addEventListener("click", () => this.setDmTarget(canonicalPk, cleanName));

      const delBtn = li.querySelector(".btn-item-delete");
      if (delBtn) {
        delBtn.addEventListener("click", (e) => {
          e.stopPropagation();
          this.conversationsWithMessages.delete(canonicalPk);
          this.conversationsWithMessages.delete(pubkey);
          this.unreadCounts.delete(feedKey);
          li.remove();
          if (this.activeDmTarget === canonicalPk || this.activeDmTarget === pubkey) {
            this.switchChannel(0);
          }
          this.updateDmBadgeCount();
          this.updateGlobalUnreadBadge();
        });
      }

      this.dom.dmListUi.appendChild(li);
    } else {
      li.classList.toggle("active", isAct);
      li.setAttribute("aria-selected", String(isAct));
      const nameEl = li.querySelector(".ch-name");
      if (nameEl && cleanName && cleanName !== canonicalPk) {
        nameEl.textContent = cleanName;
      }
      let badge = li.querySelector(".ch-unread-badge");
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "ch-unread-badge";
        const actions = li.querySelector(".ch-actions");
        if (actions) li.insertBefore(badge, actions);
        else li.appendChild(badge);
      }
      badge.textContent = unreadCount > 99 ? "99+" : String(unreadCount);
      badge.classList.toggle("hidden", unreadCount === 0);
    }

    this.updateDmBadgeCount();
    this.updateGlobalUnreadBadge();
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
    const errorRate = metrics.error_rate != null ? metrics.error_rate : (metrics.total_tx_errors != null ? metrics.total_tx_errors : null);
    const queueDepth = metrics.queue_depth ?? metrics.tx_queue_depth;

    if (nodeCount != null && this.dom.headerNodeCount) {
      this.dom.headerNodeCount.textContent = nodeCount;
    }
    if (rxCount != null && this.dom.headerRxCount) {
      this.dom.headerRxCount.textContent = rxCount;
    }
    if (txCount != null && this.dom.headerTxCount) {
      this.dom.headerTxCount.textContent = txCount;
    }
    if (errorRate != null && this.dom.headerErrorRate) {
      const errStr = typeof errorRate === "number" ? `${errorRate}%` : `${errorRate}`;
      this.dom.headerErrorRate.textContent = errStr.endsWith("%") ? errStr : `${errStr}%`;
    }
    if (queueDepth != null && this.dom.headerQueueDepth) {
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

      this.tileLayers = {
        cartodb: L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
          attribution: '&copy; <a href="https://carto.com/">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: 19,
          subdomains: "abcd",
        }),
        osm: L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
          attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
          maxZoom: 19,
        }),
        local: L.tileLayer(this.localTileUrl, {
          attribution: 'MeshCore Offline Local Tiles',
          maxZoom: 18,
          errorTileUrl: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" fill="%230f172a"><rect width="256" height="256"/><text x="128" y="128" fill="%23475569" text-anchor="middle" font-size="11" font-family="sans-serif">Mosaico Local No Disponible</text></svg>',
        }),
      };

      this.tacticalRadarGroup = L.layerGroup();

      // Detección automática de desconexión / fallo en teselas online
      this.tileLayers.cartodb.on("tileerror", () => {
        if (!this._offlineMapFallbackTriggered) {
          this._offlineMapFallbackTriggered = true;
          this.showToast("📡 Mapas online no disponibles: Conmutando a modo Radar Táctico / Grícula LoRa", "info", 5000);
          this.setMapLayer("tactical_radar");
        }
      });

      // Configurar botones de control de capas
      document.querySelectorAll(".map-layer-switcher .map-layer-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const mode = btn.getAttribute("data-layer");
          if (mode) this.setMapLayer(mode);
        });
      });

      // Configurar botón de Heatmap RF
      if (this.dom.btnToggleHeatmap) {
        this.dom.btnToggleHeatmap.addEventListener("click", () => this.toggleRfHeatmap());
      }
      this.rfHeatmapGroup = L.layerGroup();

      // Activar capa inicial según preferencia persistida
      this.setMapLayer(this.mapLayerMode || "cartodb");

      // Si ya hay nodos conocidos en memoria, renderizarlos inmediatamente en el mapa
      if (this.knownNodes && this.knownNodes.size > 0) {
        this.renderNodesDirectory(Array.from(this.knownNodes.values()));
      }
    } catch (err) {
      console.warn("No se pudo inicializar el mapa Leaflet:", err);
    }
  }

  initMapOverlayToggle() {
    const overlay = this.dom.mapOverlayInfo || document.getElementById("mapOverlayInfo");
    const btnToggle = this.dom.btnToggleMapNodes || document.getElementById("btnToggleMapNodes");
    const header = this.dom.mapOverlayHeader || document.getElementById("mapOverlayHeader");
    if (!overlay) return;

    const setMinimizedState = (minimized) => {
      overlay.classList.toggle("minimized", minimized);
      if (btnToggle) {
        const icon = btnToggle.querySelector(".toggle-icon");
        if (icon) icon.textContent = minimized ? "＋" : "−";
        btnToggle.setAttribute("aria-expanded", String(!minimized));
        btnToggle.title = minimized ? "Expandir lista de nodos" : "Minimizar lista de nodos";
      }
      localStorage.setItem("meshcore_map_nodes_minimized", String(minimized));
    };

    // Restaurar estado persistido en localStorage
    const savedState = localStorage.getItem("meshcore_map_nodes_minimized");
    if (savedState === "true") {
      setMinimizedState(true);
    }

    if (btnToggle) {
      btnToggle.addEventListener("click", (e) => {
        e.stopPropagation();
        const isCurrentlyMinimized = overlay.classList.contains("minimized");
        setMinimizedState(!isCurrentlyMinimized);
      });
    }

    if (header) {
      header.addEventListener("click", (e) => {
        if (e.target.closest("#btnToggleMapNodes")) return;
        const isCurrentlyMinimized = overlay.classList.contains("minimized");
        setMinimizedState(!isCurrentlyMinimized);
      });
    }
  }

  async toggleRfHeatmap() {
    if (!this.map) return;
    this.rfHeatmapActive = !this.rfHeatmapActive;
    if (this.dom.btnToggleHeatmap) {
      this.dom.btnToggleHeatmap.classList.toggle("active", this.rfHeatmapActive);
    }

    if (!this.rfHeatmapActive) {
      if (this.rfHeatmapGroup) this.rfHeatmapGroup.clearLayers();
      this.showToast("🔥 Mapa de calor RF desactivado", "info");
      return;
    }

    try {
      const res = await fetch("/api/rf/heatmap");
      const data = await res.json();
      if (data.status === "ok" && data.data && Array.isArray(data.data.points)) {
        if (!this.rfHeatmapGroup) this.rfHeatmapGroup = L.layerGroup();
        this.rfHeatmapGroup.clearLayers();

        data.data.points.forEach((pt) => {
          const ptRssi = pt.rssi != null ? pt.rssi : -100;
          const radius = Math.max(400, Math.min(3000, (ptRssi + 130) * 40));
          let color = "#ef4444"; // Rojo (débil)
          if (ptRssi >= -75) color = "#22c55e"; // Verde (excelente)
          else if (ptRssi >= -95) color = "#0ea5e9"; // Azul (bueno)
          else if (ptRssi >= -110) color = "#f59e0b"; // Amarillo (regular)

          const circle = L.circle([pt.lat, pt.lon], {
            radius: radius,
            color: color,
            fillColor: color,
            fillOpacity: 0.28,
            weight: 2,
          });
          const rssiPart = pt.rssi != null ? `${pt.rssi} dBm` : "--";
          const snrPart = pt.snr != null ? `${pt.snr} dB` : "--";
          const noisePart = pt.noise_floor != null ? `${pt.noise_floor} dBm` : "--";
          circle.bindPopup(`
            <strong>🔥 Cobertura RF: ${this.escapeHtml(pt.name)}</strong><br/>
            RSSI: <strong>${rssiPart}</strong> | SNR: <strong>${snrPart}</strong><br/>
            Piso de Ruido: <strong>${noisePart}</strong>
          `);
          this.rfHeatmapGroup.addLayer(circle);
        });

        this.rfHeatmapGroup.addTo(this.map);
        this.showToast(`🔥 Heatmap RF generado con ${data.data.points.length} puntos de cobertura`, "success");
      }
    } catch (err) {
      this.showToast(`Error cargando Heatmap RF: ${err.message}`, "error");
    }
  }

  initAirtimeMonitoring() {
    this.fetchAirtimeStats();
    setInterval(() => this.fetchAirtimeStats(), 15000);
  }

  async fetchAirtimeStats() {
    try {
      const res = await fetch("/api/airtime/stats");
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        const stats = data.data;
        const pct = stats.hourly_duty_cycle_pct || 0.0;
        const usedSec = (stats.hourly_used_ms / 1000).toFixed(1);
        const budgetSec = (stats.hourly_budget_ms / 1000).toFixed(0);

        if (this.dom.headerDutyCycle) {
          this.dom.headerDutyCycle.textContent = `${pct.toFixed(2)}%`;
        }
        if (this.dom.headerAirtimeChip) {
          this.dom.headerAirtimeChip.title = `Duty Cycle: ${pct.toFixed(2)}% (${usedSec}s / ${budgetSec}s presupuestados en 1h)`;
          if (pct >= stats.hourly_limit_pct) {
            this.dom.headerAirtimeChip.className = "metric-chip airtime-metric-chip airtime-danger";
          } else if (pct >= stats.hourly_limit_pct * 0.75) {
            this.dom.headerAirtimeChip.className = "metric-chip airtime-metric-chip airtime-warning";
          } else {
            this.dom.headerAirtimeChip.className = "metric-chip airtime-metric-chip airtime-normal";
          }
        }
      }
    } catch (_) {}
  }

  initContactDiscovery() {
    this.fetchDiscoveredContacts();
    if (this.dom.btnAcceptAllDiscovered) {
      this.dom.btnAcceptAllDiscovered.addEventListener("click", () => this.acceptAllDiscovered());
    }
  }

  async fetchDiscoveredContacts() {
    try {
      const res = await fetch("/api/contacts/discovered");
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        const rawList = Array.isArray(data.data.discovered) ? data.data.discovered : [];
        const trulyNewContacts = rawList.filter((c) => {
          if (!c || !c.public_key) return false;
          const canonicalPk = this.resolveCanonicalPubkey(c.public_key);
          const isLocal = (this.localNodePubkey && (
            canonicalPk.toLowerCase() === this.localNodePubkey ||
            (this.localNodePubkey.length >= 8 && canonicalPk.toLowerCase().startsWith(this.localNodePubkey.slice(0, 8))) ||
            (canonicalPk.length >= 8 && this.localNodePubkey.startsWith(canonicalPk.toLowerCase().slice(0, 8)))
          )) || canonicalPk.toLowerCase() === "local";
          if (isLocal) return false;

          const roleStr = (c.role || "CLIENT").toUpperCase();
          const nameUpper = (c.alias || c.name || "").toUpperCase();
          const isRepeater = roleStr === "REPEATER" || roleStr === "ROUTER" || c.type === 2 || c.adv_type === 2 ||
            nameUpper.startsWith("R-") || nameUpper.startsWith("R1-") || nameUpper.startsWith("R2-") || nameUpper.startsWith("R3-") || nameUpper.startsWith("REP-") || nameUpper.startsWith("ROUTER-") ||
            nameUpper.includes("REPEATER") || nameUpper.includes("ROUTER");
          const isSensor = roleStr === "SENSOR" || c.type === 4 || c.adv_type === 4;
          const isRoom = roleStr === "ROOM" || c.type === 3 || c.adv_type === 3;
          if (isRepeater || isSensor || isRoom) return false;

          // Si el nodo ya está registrado en la libreta de contactos (auto_discovered === false) o coincide con un contacto guardado
          const cNameClean = (c.alias || c.name || "").trim().toLowerCase();
          for (const [k, node] of this.knownNodes.entries()) {
            if (!node) continue;
            const nodePk = String(node.public_key || "").toLowerCase();
            const nodeName = String(node.alias || node.name || "").trim().toLowerCase();
            const isMatchPk = nodePk === canonicalPk.toLowerCase() ||
              (nodePk.length >= 6 && canonicalPk.toLowerCase().length >= 6 && (nodePk.startsWith(canonicalPk.toLowerCase()) || canonicalPk.toLowerCase().startsWith(nodePk)));
            const isMatchName = cNameClean && !cNameClean.startsWith("node_") && !cNameClean.startsWith("unknow") && (nodeName === cNameClean);
            if ((isMatchPk || isMatchName) && node.auto_discovered === false) {
              return false;
            }
          }
          return true;

        });

        const count = trulyNewContacts.length;
        if (this.dom.discoveryCount) this.dom.discoveryCount.textContent = String(count);
        if (this.dom.discoveryBanner) {
          this.dom.discoveryBanner.classList.toggle("hidden", count === 0);
        }
      }
    } catch (_) {}
  }

  async acceptAllDiscovered() {
    try {
      const res = await fetch("/api/contacts/discovered");
      const data = await res.json();
      if (data.status === "ok" && data.data && Array.isArray(data.data.discovered)) {
        for (const c of data.data.discovered) {
          await fetch("/api/contacts/accept", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ public_key: c.public_key }),
          });
        }
        this.showToast("✅ Todos los contactos descubiertos han sido aceptados", "success");
        if (this.dom.discoveryBanner) this.dom.discoveryBanner.classList.add("hidden");
        this.fetchNodes();
      }
    } catch (err) {
      this.showToast(`Error aceptando contactos: ${err.message}`, "error");
    }
  }

  initTraceroute() {
    if (this.dom.btnCloseTracerouteModal) {
      this.dom.btnCloseTracerouteModal.addEventListener("click", () => {
        if (this.dom.tracerouteModal) this.dom.tracerouteModal.classList.add("hidden");
      });
    }
    if (this.dom.tracerouteModal) {
      this.dom.tracerouteModal.addEventListener("click", (e) => {
        if (e.target === this.dom.tracerouteModal) {
          this.dom.tracerouteModal.classList.add("hidden");
        }
      });
    }
    if (this.dom.btnExecuteTrace) {
      this.dom.btnExecuteTrace.addEventListener("click", () => {
        this.executeTraceroute();
      });
    }
  }

  openTracerouteModal(targetNode, targetName) {
    const norm = (targetNode || "").toLowerCase().trim();
    const localPk = (this.localNodePubkey || "").toLowerCase().trim();
    const isLocal = Boolean(targetNode === "local") || (localPk && (
      norm === localPk ||
      (localPk.length >= 8 && norm.startsWith(localPk.slice(0, 8))) ||
      (norm.length >= 8 && localPk.startsWith(norm.slice(0, 8)))
    ));
    if (isLocal) {
      this.showToast("No se puede trazar ruta hacia la estación base local", "warning");
      return;
    }

    this.selectedTraceTarget = targetNode;
    this.selectedTraceName = targetName || targetNode.slice(0, 8);

    if (this.dom.traceTargetNameDisplay) {
      this.dom.traceTargetNameDisplay.textContent = this.selectedTraceName;
    }
    if (this.dom.traceTargetPkDisplay) {
      this.dom.traceTargetPkDisplay.textContent = targetNode;
    }
    if (this.dom.traceCustomPathInput) {
      this.dom.traceCustomPathInput.value = "";
    }
    if (this.dom.traceStatusPill) {
      this.dom.traceStatusPill.textContent = "Listo para trazar";
      this.dom.traceStatusPill.className = "trace-status-pill";
    }
    if (this.dom.traceVisualGraph) {
      this.dom.traceVisualGraph.innerHTML = `<div class="trace-empty-hint">Haz clic en "Iniciar Traza" para enviar una sonda multi-salto y mapear los repetidores.</div>`;
    }
    if (this.dom.traceBreakdownTableBody) {
      this.dom.traceBreakdownTableBody.innerHTML = `<tr><td colspan="6" class="text-center">Presiona "Iniciar Traza" para comenzar</td></tr>`;
    }
    if (this.dom.tracerouteModal) {
      this.dom.tracerouteModal.classList.remove("hidden");
    }
  }

  async executeTraceroute() {
    const target = this.selectedTraceTarget;
    if (!target) return;
    const customPath = this.dom.traceCustomPathInput ? this.dom.traceCustomPathInput.value.trim() : "";

    if (this.dom.traceStatusPill) {
      this.dom.traceStatusPill.textContent = "🚀 Trazando ruta multi-salto...";
      this.dom.traceStatusPill.className = "trace-status-pill trace-measuring";
    }
    if (this.dom.btnExecuteTrace) {
      this.dom.btnExecuteTrace.disabled = true;
      this.dom.btnExecuteTrace.textContent = "🚀 Trazando...";
    }

    try {
      const res = await fetch("/api/traceroute", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, path: customPath }),
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        const trace = data.data;
        if (this.dom.traceStatusPill) {
          this.dom.traceStatusPill.textContent = `🟢 Traza completada: ${trace.total_hops} saltos • ${trace.total_rtt_ms} ms RTT`;
          this.dom.traceStatusPill.className = "trace-status-pill trace-success";
        }
        this.renderTracerouteGraph(trace.hops_breakdown || []);
        this.renderTracerouteTable(trace.hops_breakdown || []);
        this.showToast(`🗺️ Traza a ${this.selectedTraceName}: ${trace.total_hops} saltos (${trace.total_rtt_ms} ms)`, "success");
      } else {
        const err = data.message || "Timeout esperando eco de ruta";
        if (this.dom.traceStatusPill) {
          this.dom.traceStatusPill.textContent = `🔴 Fallo: ${err}`;
          this.dom.traceStatusPill.className = "trace-status-pill trace-error";
        }
        this.showToast(`Error en traceroute: ${err}`, "error");
      }
    } catch (err) {
      if (this.dom.traceStatusPill) {
        this.dom.traceStatusPill.textContent = `🔴 Error: ${err.message}`;
      }
      this.showToast(`Error de red: ${err.message}`, "error");
    } finally {
      if (this.dom.btnExecuteTrace) {
        this.dom.btnExecuteTrace.disabled = false;
        this.dom.btnExecuteTrace.textContent = "🚀 Iniciar Traza";
      }
    }
  }

  renderTracerouteGraph(hops) {
    if (!this.dom.traceVisualGraph || !hops || hops.length === 0) return;

    let html = `<div class="trace-nodes-chain">`;
    hops.forEach((hop, idx) => {
      const isFirst = idx === 0;
      const isLast = idx === hops.length - 1;
      const roleIcon = isFirst ? "🏠" : isLast ? "🎯" : "🏔️";
      const rawSnr = hop.snr_in != null ? hop.snr_in : (hop.snr != null ? hop.snr : null);
      const snrVal = rawSnr != null ? rawSnr : null;
      let snrColor = "#22c55e"; // Verde (> 6 dB)
      if (snrVal != null) {
        if (snrVal < 0) snrColor = "#ef4444"; // Rojo
        else if (snrVal < 6) snrColor = "#f59e0b"; // Amarillo
      } else {
        snrColor = "var(--text-muted)";
      }

      html += `
        <div class="trace-node-box ${isFirst ? 'trace-node-base' : isLast ? 'trace-node-target' : 'trace-node-hop'}">
          <div class="trace-node-avatar">${roleIcon}</div>
          <strong class="trace-node-name">${this.escapeHtml(hop.name || hop.pubkey.slice(0, 8))}</strong>
          <span class="trace-node-pk font-mono">${this.escapeHtml(hop.pubkey.slice(0, 8))}</span>
          <span class="trace-node-snr" style="color: ${snrColor};">📶 ${snrVal != null ? `${snrVal} dB` : "--"}</span>
        </div>
      `;

      if (!isLast) {
        const nextHop = hops[idx + 1];
        const segRtt = nextHop.rtt_segment_ms != null ? `${nextHop.rtt_segment_ms} ms` : "--";
        html += `
          <div class="trace-link-arrow">
            <span class="trace-link-rtt">${segRtt}</span>
            <div class="trace-link-line" style="background-color: ${snrColor};"></div>
            <span class="trace-link-sym">➔</span>
          </div>
        `;
      }
    });
    html += `</div>`;
    this.dom.traceVisualGraph.innerHTML = html;
  }

  renderTracerouteTable(hops) {
    if (!this.dom.traceBreakdownTableBody || !hops || hops.length === 0) return;
    let html = "";
    hops.forEach((h) => {
      const snrInStr = h.snr_in != null ? `${h.snr_in} dB` : "--";
      const snrOutStr = h.snr_out != null ? `${h.snr_out} dB` : "--";
      const rttStr = h.rtt_segment_ms != null ? `${h.rtt_segment_ms} ms` : "--";
      html += `
        <tr>
          <td><strong>#${h.hop_index}</strong></td>
          <td>${this.escapeHtml(h.name)}</td>
          <td class="font-mono">${this.escapeHtml(h.pubkey.slice(0, 12))}</td>
          <td><span class="stat-pill">📶 ${snrInStr}</span></td>
          <td><span class="stat-pill">📡 ${snrOutStr}</span></td>
          <td>⏱️ ${rttStr}</td>
        </tr>
      `;
    });
    this.dom.traceBreakdownTableBody.innerHTML = html;
  }

  setMapLayer(mode) {
    if (!this.map) return;
    this.mapLayerMode = mode;
    localStorage.setItem("meshcore_map_layer_mode", mode);

    document.querySelectorAll(".map-layer-switcher .map-layer-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-layer") === mode);
    });

    // Retirar capas activas
    Object.values(this.tileLayers || {}).forEach((l) => {
      if (this.map.hasLayer(l)) this.map.removeLayer(l);
    });

    const mapCanvas = document.getElementById("liveGpsMap");

    if (mode === "tactical_radar") {
      if (mapCanvas) mapCanvas.classList.add("tactical-radar-mode");
      if (!this.map.hasLayer(this.tacticalRadarGroup)) {
        this.tacticalRadarGroup.addTo(this.map);
      }
      this.renderTacticalRadarOverlay();
    } else {
      if (mapCanvas) mapCanvas.classList.remove("tactical-radar-mode");
      if (this.tacticalRadarGroup && this.map.hasLayer(this.tacticalRadarGroup)) {
        this.map.removeLayer(this.tacticalRadarGroup);
      }
      const targetLayer = this.tileLayers[mode] || this.tileLayers.cartodb;
      targetLayer.addTo(this.map);
    }
  }

  renderTacticalRadarOverlay() {
    if (!this.map || !this.tacticalRadarGroup) return;
    this.tacticalRadarGroup.clearLayers();

    // Obtener centro: coordenadas del nodo local o centro actual del mapa
    let center = this.map.getCenter();
    for (const node of this.knownNodes.values()) {
      if (node.is_local || node.role === "LOCAL") {
        const lat = parseFloat(node.latitude || node.lat);
        const lon = parseFloat(node.longitude || node.lon);
        if (!isNaN(lat) && !isNaN(lon) && lat !== 0) {
          center = L.latLng(lat, lon);
          break;
        }
      }
    }

    // Anillos concéntricos de alcance táctico (1km, 5km, 10km, 25km)
    const ranges = [
      { radius: 1000, label: "1 km (LoRa Urbana)", color: "#38bdf8" },
      { radius: 5000, label: "5 km (LoRa Suburbana)", color: "#0ea5e9" },
      { radius: 10000, label: "10 km (Línea de Vista)", color: "#0284c7" },
      { radius: 25000, label: "25 km (Largo Alcance RF)", color: "#0369a1" },
    ];

    for (const r of ranges) {
      const circle = L.circle(center, {
        radius: r.radius,
        color: r.color,
        weight: 1.2,
        opacity: 0.7,
        dashArray: "4, 6",
        fillColor: r.color,
        fillOpacity: 0.03,
      });

      circle.bindTooltip(`🎯 ${r.label}`, {
        permanent: false,
        direction: "top",
        className: "radar-range-tooltip",
      });

      this.tacticalRadarGroup.addLayer(circle);
    }

    // Grícula táctica / Ejes cardinales Norte-Sur y Este-Oeste
    const delta = 0.35; // ~38 km
    const northSouth = L.polyline([[center.lat - delta, center.lng], [center.lat + delta, center.lng]], {
      color: "rgba(56, 189, 248, 0.25)",
      weight: 1,
      dashArray: "2, 4",
    });
    const eastWest = L.polyline([[center.lat, center.lng - delta], [center.lat, center.lng + delta]], {
      color: "rgba(56, 189, 248, 0.25)",
      weight: 1,
      dashArray: "2, 4",
    });

    this.tacticalRadarGroup.addLayer(northSouth);
    this.tacticalRadarGroup.addLayer(eastWest);
  }

  async fetchInitialData() {
    await this.fetchLocalNodeConfig();

    // Purgar mensajes históricos de sistema (Unknown command, CLI, etc.) de IndexedDB
    await this.storage.purgeNonCommonMessages((t, tt) => this.isCommandOrSystemText(t, tt));

    // Cargar historial de chat inicial para el canal público 0 desde IndexedDB
    const initialMsgs = await this.storage.getMessagesByFeed("ch_0");
    if (initialMsgs && initialMsgs.length > 0) {
      const cleanMsgs = initialMsgs.filter((m) => !this.isCommandOrSystemText(m.text, m.txt_type));
      this.channelFeeds.set("ch_0", cleanMsgs);
      if (this.activeChannelIdx === 0 && !this.activeDmTarget) {
        await this.renderCurrentConversation();
      }
    }

    // Cargar y restaurar todas las conversaciones de mensajes directos activas desde IndexedDB (estilo WhatsApp)
    try {
      const dmThreads = await this.storage.getDmConversations();
      if (dmThreads && dmThreads.length > 0) {
        for (const thread of dmThreads) {
          const canonicalPk = this.resolveCanonicalPubkey(thread.pubkey);
          this.conversationsWithMessages.add(canonicalPk);
          if (thread.pubkey !== canonicalPk) {
            this.conversationsWithMessages.add(thread.pubkey);
          }
          const cleanMsgs = (thread.messages || []).filter((m) => !this.isCommandOrSystemText(m.text, m.txt_type));
          this.channelFeeds.set(`dm_${canonicalPk}`, cleanMsgs);

          let displayName = thread.name;
          const known = this.knownNodes.get(canonicalPk) || this.knownNodes.get(thread.pubkey);
          if (known && (known.alias || known.name) && !known.name.startsWith("Node_unknow")) {
            displayName = known.alias || known.name;
          }
          this.addDmContact(canonicalPk, displayName || canonicalPk, thread.role || "CLIENT");
        }
        this.updateDmBadgeCount();
        this.updateGlobalUnreadBadge();
      }
    } catch (err) {
      console.warn("Error restaurando hilos DM desde IndexedDB:", err);
    }

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

      const unreadCount = this.unreadCounts.get(`ch_${ch.index}`) || 0;
      const unreadBadgeHtml = `<span class="ch-unread-badge ${unreadCount > 0 ? '' : 'hidden'}">${unreadCount}</span>`;

      li.innerHTML = `
        <span class="ch-badge">Ch ${ch.index}</span>
        <span class="ch-name" title="${this.escapeHtml(ch.name)}">${this.escapeHtml(ch.name)}</span>
        ${unreadBadgeHtml}
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

  isValidNodeKey(key) {
    if (!key || typeof key !== "string") return false;
    const norm = key.trim().toLowerCase();
    if (!norm || norm === "unknown" || norm === "broadcast" || norm === "none" || norm === "null" || norm === "system" || norm === "00000000" || norm === "000000000000" || norm === "ffff" || norm === "0xffff" || norm.startsWith("unknow") || norm.startsWith("broadcast") || norm.startsWith("0x0000") || norm.length < 4) {
      return false;
    }
    return true;
  }

  updateNodeInDom(pubkey, node) {
    if (!pubkey || !node || !this.isValidNodeKey(pubkey)) return;
    if (node.name && (node.name.startsWith("Node_unknow") || node.name.toLowerCase() === "unknown")) return;
    const norm = String(pubkey).trim().toLowerCase();

    // 1. Actualizar tarjetas en el grid unificado de nodos
    const cards = document.querySelectorAll("#nodesUnifiedGridUi .node-card, #contactsGridUi .contact-card");
    let found = false;

    cards.forEach((card) => {
      const cardPk = String(card.getAttribute("data-pk") || "").trim().toLowerCase();
      const isMatch = cardPk === norm ||
        (cardPk.length >= 8 && norm.length >= 8 && (cardPk.startsWith(norm) || norm.startsWith(cardPk)));

      if (isMatch) {
        found = true;
        // Actualizar chip de estado a En Línea
        const statusChip = card.querySelector(".node-status-chip");
        if (statusChip) {
          statusChip.className = "node-status-chip status-online";
          statusChip.textContent = "🟢 En Línea";
          statusChip.title = "Hace un momento";
        }
        card.classList.remove("node-card-offline", "contact-card-offline");

        // Actualizar RF stat pills si vienen métricas
        const rawRssi = node.last_rssi ?? node.rssi ?? node.metrics?.rssi;
        if (rawRssi != null && rawRssi !== "" && rawRssi !== "--") {
          const rssiPill = card.querySelector('.stat-pill[title*="Señal"] strong, .stat-pill[title*="Intensidad"] strong');
          if (rssiPill) rssiPill.textContent = `${Math.round(Number(rawRssi))} dBm`;
        }
        const rawSnr = node.last_snr ?? node.snr ?? node.metrics?.snr;
        if (rawSnr != null && rawSnr !== "" && rawSnr !== "--") {
          const snrPill = card.querySelector('.stat-pill[title*="Ruido"] strong, .stat-pill[title*="SNR"] strong');
          if (snrPill) snrPill.textContent = `${Number(rawSnr) > 0 ? "+" : ""}${Number(rawSnr).toFixed(1)} dB`;
        }
        const rawHops = node.hops ?? node.hop_count ?? node.metrics?.hops;
        if (rawHops != null && rawHops !== "" && rawHops !== "--") {
          const hopsPill = card.querySelector('.stat-pill[title*="Saltos"] strong');
          if (hopsPill) {
            const h = Number(rawHops);
            hopsPill.textContent = !isNaN(h) ? (h === 0 ? "0 (Directo)" : (h === 1 ? "1 salto" : `${h} saltos`)) : String(rawHops);
          }
        }
        const rawBat = node.battery ?? node.battery_pct ?? node.metrics?.battery;
        if (rawBat != null && rawBat !== "" && rawBat !== "--") {
          const batChip = card.querySelector(".contact-battery-chip");
          if (batChip) {
            batChip.className = "contact-battery-chip";
            batChip.textContent = `🔋 ${Math.min(100, Math.max(0, Math.round(Number(rawBat))))}%`;
          }
        }
      }
    });


    // 2. Si no se encontró en el DOM y tenemos la lista de nodos, refrescar el directorio
    if (!found && this.knownNodes && this.knownNodes.size > 0) {
      this.renderNodesDirectory(Array.from(this.knownNodes.values()));
    }
  }

  renderNodesDirectory(nodes) {
    const contactsGrid = this.dom.contactsGridUi || document.getElementById("contactsGridUi");
    const unifiedNodesGrid = this.dom.nodesUnifiedGridUi || document.getElementById("nodesUnifiedGridUi");
    const mapList = document.getElementById("mapNodesList");
    if (mapList) mapList.innerHTML = "";

    // Purgar entradas inválidas de knownNodes
    if (this.knownNodes && this.knownNodes.size > 0) {
      for (const [k, v] of Array.from(this.knownNodes.entries())) {
        if (!this.isValidNodeKey(k) || !this.isValidNodeKey(v?.public_key) || (v?.name && v.name.startsWith("Node_unknow"))) {
          this.knownNodes.delete(k);
        }
      }
    }

    if (!nodes || nodes.length === 0) {
      if (contactsGrid) contactsGrid.innerHTML = '<div class="empty-state">No hay contactos registrados en el dispositivo.</div>';
      if (unifiedNodesGrid) unifiedNodesGrid.innerHTML = '<div class="empty-state">No se han descubierto nodos en la malla LoRa.</div>';
      return;
    }

    // Deduplicación inteligente: fusionar entradas que compartan prefijo de clave (>=8 chars) o mismo nombre
    const deduplicatedNodes = [];
    for (const rawNode of nodes) {
      if (!rawNode || !this.isValidNodeKey(rawNode.public_key)) continue;
      if (rawNode.name && (rawNode.name.startsWith("Node_unknow") || rawNode.name.toLowerCase() === "unknown")) continue;
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
        deduplicatedNodes[matchIndex] = {
          ...prev,
          ...rawNode,
          public_key: prev.public_key.length >= rawNode.public_key.length ? prev.public_key : rawNode.public_key,
          name: prev.name && !prev.name.startsWith("Node_") ? prev.name : (rawNode.name || prev.name),
          alias: prev.alias || rawNode.alias,
          last_seen: Math.max(Number(prev.last_seen) || 0, Number(rawNode.last_seen) || 0),
          last_rssi: rawNode.last_rssi != null ? rawNode.last_rssi : prev.last_rssi,
          last_snr: rawNode.last_snr != null ? rawNode.last_snr : prev.last_snr,
          hops: rawNode.hops != null ? rawNode.hops : prev.hops,
        };
      } else {
        deduplicatedNodes.push({ ...rawNode });
      }
    }

    if (contactsGrid) contactsGrid.innerHTML = "";
    if (unifiedNodesGrid) unifiedNodesGrid.innerHTML = "";

    const contactsFrag = document.createDocumentFragment();
    const nodesFrag = document.createDocumentFragment();
    const mapFrag = document.createDocumentFragment();

    const mapBounds = [];
    let geoLocatedCount = 0;
    let clientContactCount = 0;
    let totalCount = 0;
    let repeaterCount = 0;
    let sensorCount = 0;
    let roomCount = 0;
    let clientCount = 0;

    for (const node of deduplicatedNodes) {
      if (!this.isValidNodeKey(node.public_key)) continue;
      this.knownNodes.set(node.public_key, node);
      totalCount++;

      // Actualizar nombre amigable en la lista de DMs activos si coincide con este nodo
      if (this.dom.dmListUi) {
        const canonicalKey = this.resolveCanonicalPubkey(node.public_key);
        const dmItems = this.dom.dmListUi.querySelectorAll("li.channel-item");
        for (const dmItem of dmItems) {
          const itemPk = (dmItem.getAttribute("data-pubkey") || "").trim().toLowerCase();
          const cPkLower = canonicalKey.toLowerCase();
          const isMatch = itemPk === cPkLower ||
            (itemPk.length >= 8 && cPkLower.length >= 8 && (itemPk.startsWith(cPkLower) || cPkLower.startsWith(itemPk)));
          if (isMatch) {
            const nameEl = dmItem.querySelector(".ch-name");
            const cleanNameCand = node.alias || node.name;
            if (nameEl && cleanNameCand && !cleanNameCand.startsWith("Node_unknow") && cleanNameCand.toLowerCase() !== "unknown") {
              nameEl.textContent = cleanNameCand;
              nameEl.title = cleanNameCand;
            }
          }
        }
      }

      const normNodePk = (node.public_key || "").toLowerCase().trim();

      const localPk = (this.localNodePubkey || "").toLowerCase().trim();
      const isLocal = (localPk && (
        normNodePk === localPk ||
        (localPk.length >= 8 && normNodePk.startsWith(localPk.slice(0, 8))) ||
        (normNodePk.length >= 8 && localPk.startsWith(normNodePk.slice(0, 8)))
      )) || Boolean(node.is_local) || node.role === "LOCAL" || normNodePk === "local";

      const roleStr = (node.role || "CLIENT").toUpperCase();
      const nodeNameUpper = (node.alias || node.name || "").toUpperCase();
      const isRepeater = !isLocal && (roleStr === "REPEATER" || roleStr === "ROUTER" || node.type === 2 || node.adv_type === 2 ||
        nodeNameUpper.startsWith("R-") || nodeNameUpper.startsWith("R1-") || nodeNameUpper.startsWith("R2-") || nodeNameUpper.startsWith("R3-") || nodeNameUpper.startsWith("REP-") || nodeNameUpper.startsWith("ROUTER-") ||
        nodeNameUpper.includes("REPEATER") || nodeNameUpper.includes("ROUTER"));
      const isSensor = !isLocal && (roleStr === "SENSOR" || node.type === 4 || node.adv_type === 4 || !!(node.temperature_c || node.temp || node.humidity_pct || node.humidity));
      const isRoom = !isLocal && (roleStr === "ROOM" || node.type === 3 || node.adv_type === 3 || nodeNameUpper.includes("ROOM") || nodeNameUpper.includes("BBS"));
      const isClient = !isLocal && !isRepeater && !isSensor && !isRoom;

      if (isRepeater) repeaterCount++;
      else if (isSensor) sensorCount++;
      else if (isRoom) roomCount++;
      else if (isClient) clientCount++;

      const cleanName = node.alias || node.name || `Node_${node.public_key.slice(0, 6)}`;
      const shortPk = node.public_key.length > 16 ? `${node.public_key.slice(0, 10)}...${node.public_key.slice(-4)}` : node.public_key;

      const rawSnr = node.snr ?? node.last_snr ?? node.metrics?.snr ?? node.telemetry?.snr ?? (node.SNR != null ? node.SNR : null);
      const rawRssi = node.rssi ?? node.last_rssi ?? node.metrics?.rssi ?? node.telemetry?.rssi ?? (node.RSSI != null ? node.RSSI : null);
      const rawHops = node.hops ?? node.hop_count ?? node.metrics?.hops ?? node.hop_limit ?? (node.hops_count != null ? node.hops_count : null);
      const rawBat = node.battery ?? node.battery_pct ?? node.metrics?.battery ?? node.telemetry?.battery_pct ?? (node.batt != null ? node.batt : null);
      const rawVolt = node.voltage_v ?? node.voltage ?? node.metrics?.voltage ?? node.telemetry?.voltage_v ?? (node.battery_mv ? node.battery_mv / 1000 : null);
      const rawNoise = node.noise_floor_dbm ?? node.noise_floor ?? (isLocal ? (this.localNodeConfig?.noise_floor_dbm || this.localNodeConfig?.noise_floor) : null);
      const rawUptime = node.uptime_str ?? node.uptime ?? (isLocal ? (this.localNodeConfig?.uptime_str || this.localNodeConfig?.uptime) : null);

      // Calcular SNR
      let snrVal = "N/D";
      if (isLocal) {
        snrVal = "Host USB";
      } else if (rawSnr !== undefined && rawSnr !== null && rawSnr !== "" && rawSnr !== "--") {
        const numSnr = Number(rawSnr);
        snrVal = !isNaN(numSnr) ? `${numSnr > 0 ? "+" : ""}${numSnr.toFixed(1)} dB` : `${rawSnr} dB`;
      }

      // Calcular RSSI
      let rssiVal = "N/D";
      if (isLocal) {
        rssiVal = "Directo";
      } else if (rawRssi !== undefined && rawRssi !== null && rawRssi !== "" && rawRssi !== "--") {
        const numRssi = Number(rawRssi);
        rssiVal = !isNaN(numRssi) ? `${Math.round(numRssi)} dBm` : `${rawRssi} dBm`;
      }

      // Calcular Saltos (Hops)
      let hopsVal = "N/D";
      if (isLocal) {
        hopsVal = "0 (Host)";
      } else if (rawHops !== undefined && rawHops !== null && rawHops !== "" && rawHops !== "--") {
        const numHops = Number(rawHops);
        if (!isNaN(numHops)) {
          hopsVal = numHops === 0 ? "0 (Directo)" : (numHops === 1 ? "1 salto" : `${numHops} saltos`);
        } else {
          hopsVal = String(rawHops);
        }
      } else if (node.out_path_len !== undefined && node.out_path_len !== null && node.out_path_len >= 0) {
        const pLen = Number(node.out_path_len);
        hopsVal = pLen === 0 ? "0 (Directo)" : (pLen === 1 ? "1 salto" : `${pLen} saltos`);
      } else if ((rawSnr !== undefined && rawSnr !== null && rawSnr !== "" && rawSnr !== "--") || (rawRssi !== undefined && rawRssi !== null && rawRssi !== "" && rawRssi !== "--")) {
        // Recepción RF directa en nuestra antena
        hopsVal = "0 (Directo)";
      } else {
        hopsVal = "N/D";
      }


      // Calcular Batería
      let batVal = "N/D";
      let hasRealBat = false;
      if (isLocal) {
        if (rawBat !== undefined && rawBat !== null && rawBat !== "" && rawBat !== "--") {
          batVal = `${Math.min(100, Math.max(0, Math.round(Number(rawBat))))}%`;
          hasRealBat = true;
        } else {
          batVal = "USB 5V";
        }
      } else if (rawBat !== undefined && rawBat !== null && rawBat !== "" && rawBat !== "--") {
        const numBat = Number(rawBat);
        if (!isNaN(numBat)) {
          batVal = `${Math.min(100, Math.max(0, Math.round(numBat)))}%`;
          hasRealBat = true;
        }
      } else if (rawVolt !== undefined && rawVolt !== null && rawVolt !== "" && rawVolt !== "--") {
        const numVolt = Number(rawVolt);
        if (!isNaN(numVolt) && numVolt > 2.5) {
          const estPct = Math.min(100, Math.max(5, Math.round(((numVolt - 3.2) / 1.0) * 100)));
          batVal = `${estPct}% (${numVolt.toFixed(1)}V)`;
          hasRealBat = true;
        }
      }

      // Uptime
      let uptimeVal = null;
      if (rawUptime !== undefined && rawUptime !== null && rawUptime !== "" && rawUptime !== "--") {
        if (typeof rawUptime === "number") {
          const hrs = Math.floor(rawUptime / 3600);
          const mins = Math.floor((rawUptime % 3600) / 60);
          uptimeVal = hrs > 0 ? `${hrs}h ${mins}m` : `${mins}m`;
        } else {
          uptimeVal = String(rawUptime);
        }
      }

      // Noise Floor
      let noiseVal = null;
      if (rawNoise !== undefined && rawNoise !== null && rawNoise !== "" && rawNoise !== "--") {
        const numNoise = Number(rawNoise);
        noiseVal = !isNaN(numNoise) ? `${Math.round(numNoise)} dBm` : `${rawNoise} dBm`;
      }

      // Calcular estado de conectividad en base a last_seen
      const nowSec = Date.now() / 1000;
      let lastSeenSec = node.last_seen;
      if (typeof lastSeenSec === "string") {
        if (!isNaN(Number(lastSeenSec))) {
          lastSeenSec = Number(lastSeenSec);
        } else {
          const parsed = Date.parse(lastSeenSec);
          if (!isNaN(parsed)) lastSeenSec = parsed / 1000;
        }
      }
      if (typeof lastSeenSec === "number" && lastSeenSec > 1e11) {
        lastSeenSec = lastSeenSec / 1000;
      }

      let statusLabel = isLocal ? "Estación Base Local" : "En Línea";
      let statusClass = "status-online";
      let statusDot = "🟢";
      let timeAgoStr = isLocal ? "Enlace USB / Serial Activo" : "Ahora";

      if (!isLocal) {
        if (lastSeenSec && typeof lastSeenSec === "number" && lastSeenSec > 1000000000) {
          const diff = Math.max(0, nowSec - lastSeenSec);
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
        } else {
          statusLabel = "Fuera de línea";
          statusClass = "status-offline";
          statusDot = "🔴";
          timeAgoStr = "Sin actividad reciente";
        }
      }

      const isOffline = statusClass === "status-offline";

      // 1. Renderizar en la pestaña "Contactos" (solo clientes/contactos externos)
      if (contactsGrid && !isLocal && !isRepeater && !isSensor && !isRoom) {
        clientContactCount++;
        const cCard = document.createElement("div");
        cCard.className = `contact-card ${isOffline ? "contact-card-offline" : ""}`;
        cCard.setAttribute("data-pk", node.public_key);
        cCard.setAttribute("data-search", `${cleanName} ${node.public_key}`.toLowerCase());

        const batChipHtml = hasRealBat
          ? `<span class="contact-battery-chip" title="Nivel de batería">🔋 ${batVal}</span>`
          : `<span class="contact-battery-chip bat-unknown" title="Batería no reportada">🔋 N/D</span>`;

        cCard.innerHTML = `
          <div class="contact-card-header">
            <div class="contact-avatar">👤</div>
            <div class="contact-info">
              <div class="contact-title-row">
                <span class="contact-name" title="${this.escapeHtml(cleanName)}">${this.escapeHtml(cleanName)}</span>
                <span class="node-status-chip ${statusClass}" title="${timeAgoStr}">${statusDot} ${statusLabel}</span>
              </div>
              <span class="contact-pubkey font-mono" title="${this.escapeHtml(node.public_key)}">
                ${this.escapeHtml(shortPk)}
                <button type="button" class="btn-copy-pk" title="Copiar clave pública">📋</button>
              </span>
            </div>
            ${batChipHtml}
          </div>
          <div class="contact-card-chips">
            <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal}</strong></span>
            <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal}</strong></span>
            <span class="stat-pill" title="Saltos de retransmisión">🦘 <strong>${hopsVal}</strong></span>
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
        const roleClass = isLocal ? "role-local-card is-local" : (isSensor ? "role-sensor-card" : isRepeater ? "role-repeater-card" : isRoom ? "role-room-card" : "role-client-card");
        const avatarClass = isLocal ? "avatar-local" : (isSensor ? "avatar-sensor" : isRepeater ? "avatar-repeater" : isRoom ? "avatar-room" : "avatar-client");
        const avatarIcon = isLocal ? "🏠" : (isSensor ? "📡" : isRepeater ? "🏔️" : isRoom ? "🏠" : "👤");
        const roleLabel = isLocal ? "LOCAL" : (isSensor ? "SENSOR" : isRepeater ? "REPEATER" : isRoom ? "ROOM" : "CLIENT");
        const roleBadgeClass = isLocal ? "role-local" : (isSensor ? "role-sensor" : isRepeater ? "role-repeater" : isRoom ? "role-room" : "role-client");

        nCard.className = `node-card ${roleClass} ${isOffline ? "node-card-offline" : ""}`;
        nCard.setAttribute("data-role", roleLabel);
        nCard.setAttribute("data-pk", node.public_key);
        const searchData = `${node.alias || ''} ${node.name || ''} ${node.public_key} ${roleLabel}`.toLowerCase();
        nCard.setAttribute("data-search", searchData);

        let bodyHtml = "";
        const hasNodeGps = !!((node.latitude && node.longitude) || (node.lat && node.lon));

        if (isLocal) {
          const lFreq = this.localNodeConfig?.frequency || this.localNodeConfig?.radio_freq || 915.0;
          const lPower = this.localNodeConfig?.tx_power != null ? `${this.localNodeConfig.tx_power} dBm` : "20 dBm";
          const lSf = this.localNodeConfig?.spreading_factor || this.localNodeConfig?.sf || 11;
          const lBw = this.localNodeConfig?.bandwidth || this.localNodeConfig?.bw || 250;
          const lPort = this.localNodeConfig?.serial_port || (this.dom.headerPortBadge ? this.dom.headerPortBadge.textContent : "USB / Serial");
          bodyHtml = `
            <div class="node-telemetry-panel">
              <div style="font-size: 12px; color: var(--text-main); font-weight: 600; display: flex; justify-content: space-between;">
                <span>🏠 Estación Base Transceptora</span>
                <span style="color: var(--accent-success); font-weight: 700;">Host Bridge</span>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">
                Puerto: ${this.escapeHtml(lPort)} • Enlace USB Directo
              </div>
            </div>
            <div class="node-rf-strip" style="grid-template-columns: repeat(3, 1fr);">
              <span class="stat-pill" title="Frecuencia de Operación">📻 <strong>${lFreq} MHz</strong></span>
              <span class="stat-pill" title="Potencia de Transmisión TX">⚡ <strong>${lPower}</strong></span>
              <span class="stat-pill" title="Modem LoRa">📡 <strong>SF${lSf}/BW${lBw}</strong></span>
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-primary btn-sm btn-node-primary btn-node-local-settings">⚙️ Ajustes de Radio</button>
              <button type="button" class="btn-secondary btn-sm btn-node-secondary btn-client-qr" title="Ver código QR">📤 QR</button>
            </div>
          `;
        } else if (isSensor) {
          const rawTemp = node.temperature_c ?? node.temp ?? node.temperature ?? node.telemetry?.temperature_c ?? (node.telemetry?.temp != null ? node.telemetry.temp : null);
          const rawHum = node.humidity_pct ?? node.humidity ?? node.telemetry?.humidity_pct ?? (node.telemetry?.hum != null ? node.telemetry.hum : null);
          const rawPress = node.pressure_hpa ?? node.pressure ?? node.telemetry?.pressure_hpa ?? (node.telemetry?.press != null ? node.telemetry.press : null);
          const tempStr = (rawTemp !== undefined && rawTemp !== null && rawTemp !== "" && rawTemp !== "--") ? `${Number(rawTemp).toFixed(1)}°C` : "N/D";
          const humStr = (rawHum !== undefined && rawHum !== null && rawHum !== "" && rawHum !== "--") ? `${Math.round(Number(rawHum))}%` : "N/D";
          const pressStr = (rawPress !== undefined && rawPress !== null && rawPress !== "" && rawPress !== "--") ? `${Math.round(Number(rawPress))} hPa` : "N/D";
          bodyHtml = `
            <div class="node-telemetry-panel">
              <div class="telemetry-sensors-grid">
                <div class="sensor-box">
                  <span class="sensor-box-label">Temp</span>
                  <span class="sensor-box-value sensor-temp-val">${tempStr}</span>
                </div>
                <div class="sensor-box">
                  <span class="sensor-box-label">Humedad</span>
                  <span class="sensor-box-value sensor-hum-val">${humStr}</span>
                </div>
                <div class="sensor-box">
                  <span class="sensor-box-label">Presión</span>
                  <span class="sensor-box-value sensor-press-val">${pressStr}</span>
                </div>
              </div>
            </div>
            <div class="node-rf-strip">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal}</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal}</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${hopsVal}</strong></span>
              ${noiseVal ? `<span class="stat-pill" title="Piso de Ruido">🔊 <strong>${noiseVal}</strong></span>` : ''}
              ${uptimeVal ? `<span class="stat-pill" title="Tiempo Activo">⏱️ <strong>${uptimeVal}</strong></span>` : ''}
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-secondary btn-sm btn-node-primary btn-sensor-qr" title="Exportar QR del sensor">📤 QR Telemetría</button>
              ${hasNodeGps ? `<button type="button" class="btn-secondary btn-sm btn-node-secondary btn-node-view-map" title="Centrar y ver en mapa">🗺️ Mapa</button>` : ''}
            </div>
          `;
        } else if (isRepeater) {
          const rawTxPower = node.tx_power ?? 20;
          const txPowerStr = `${rawTxPower} dBm`;
          const rawHopLimit = node.hop_limit ?? 3;
          const hopLimitStr = `${rawHopLimit} saltos`;
          bodyHtml = `
            <div class="node-telemetry-panel">
              <div style="font-size: 12px; display: flex; justify-content: space-between; color: var(--text-main); font-weight: 600;">
                <span>🏔️ Router de Malla</span>
                <strong style="color: #c084fc;">TX: ${txPowerStr}</strong>
              </div>
              <div style="font-size: 11px; color: var(--text-muted); display: flex; justify-content: space-between; margin-top: 2px;">
                <span>Reenvío: Activo</span>
                <span>Hop Limit: ${hopLimitStr}</span>
              </div>
            </div>
            <div class="node-rf-strip">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal}</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal}</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${hopsVal}</strong></span>
              ${noiseVal ? `<span class="stat-pill" title="Piso de Ruido">🔊 <strong>${noiseVal}</strong></span>` : ''}
              ${uptimeVal ? `<span class="stat-pill" title="Tiempo Activo">⏱️ <strong>${uptimeVal}</strong></span>` : ''}
              ${node.ping_zero_rtt ? `<span class="stat-pill stat-pill-ping" title="Último Ping Zero directo">🎯 <strong>${node.ping_zero_rtt} ms</strong></span>` : ''}
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-primary btn-sm btn-node-primary btn-manage-node-repeater">🎛️ Administrar</button>
              <button type="button" class="btn-secondary btn-sm btn-node-secondary btn-node-ping-zero" title="Hacer Ping Zero directo (0 saltos)">🎯 Ping 0</button>
              <button type="button" class="btn-secondary btn-sm btn-node-secondary btn-node-traceroute" title="Trazar ruta multi-salto">🗺️ Ruta</button>
              ${hasNodeGps ? `<button type="button" class="btn-secondary btn-sm btn-node-secondary btn-node-view-map" title="Centrar y ver en mapa">🗺️ Mapa</button>` : ''}
            </div>
          `;
        } else if (isRoom) {
          bodyHtml = `
            <div class="node-telemetry-panel">
              <div style="font-size: 12px; color: var(--text-main); font-weight: 600;">🏠 Servidor de Sala / BBS</div>
              <div style="font-size: 11px; color: var(--text-muted);">Canal: ${node.channel || "General"}</div>
            </div>
            <div class="node-rf-strip">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal}</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal}</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${hopsVal}</strong></span>
              ${noiseVal ? `<span class="stat-pill" title="Piso de Ruido">🔊 <strong>${noiseVal}</strong></span>` : ''}
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-secondary btn-sm btn-node-primary btn-room-channel">💬 Ver Canal</button>
              ${hasNodeGps ? `<button type="button" class="btn-secondary btn-sm btn-node-secondary btn-node-view-map" title="Centrar y ver en mapa">🗺️ Mapa</button>` : ''}
            </div>
          `;
        } else {
          // CLIENT
          bodyHtml = `
            <div class="node-rf-strip" style="margin-top: 4px;">
              <span class="stat-pill" title="Relación Señal/Ruido">📶 <strong>${snrVal}</strong></span>
              <span class="stat-pill" title="Intensidad de Señal">📡 <strong>${rssiVal}</strong></span>
              <span class="stat-pill" title="Saltos">🦘 <strong>${hopsVal}</strong></span>
              ${noiseVal ? `<span class="stat-pill" title="Piso de Ruido">🔊 <strong>${noiseVal}</strong></span>` : ''}
              ${uptimeVal ? `<span class="stat-pill" title="Tiempo Activo">⏱️ <strong>${uptimeVal}</strong></span>` : ''}
            </div>
            <div class="node-actions-bar">
              <button type="button" class="btn-primary btn-sm btn-node-primary btn-client-dm">💬 Iniciar Chat DM</button>
              <button type="button" class="btn-secondary btn-sm btn-node-secondary btn-node-traceroute" title="Trazar ruta multi-salto">🗺️ Ruta</button>
              <button type="button" class="btn-secondary btn-sm btn-node-secondary btn-client-qr" title="Ver código QR">📤 QR</button>
              ${hasNodeGps ? `<button type="button" class="btn-secondary btn-sm btn-node-secondary btn-node-view-map" title="Centrar y ver en mapa">🗺️ Mapa</button>` : ''}
            </div>
          `;
        }

        const batteryChipHtml = isLocal
          ? (hasRealBat ? `<span class="contact-battery-chip" title="Nivel de batería">🔋 ${batVal}</span>` : '<span class="contact-battery-chip" style="background: rgba(16,185,129,0.15); color: #10b981; border-color: rgba(16,185,129,0.35);">⚡ USB 5V</span>')
          : (hasRealBat ? `<span class="contact-battery-chip" title="Nivel de batería">🔋 ${batVal}</span>` : '<span class="contact-battery-chip bat-unknown" title="Batería no reportada">🔋 N/D</span>');

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
            ${batteryChipHtml}
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

        const btnLocalSettings = nCard.querySelector(".btn-node-local-settings");
        if (btnLocalSettings) {
          btnLocalSettings.addEventListener("click", () => {
            const navBtn = document.querySelector('.nav-btn[data-tab="tab-settings"]');
            if (navBtn) navBtn.click();
          });
        }

        const btnManage = nCard.querySelector(".btn-manage-node-repeater");
        if (btnManage) {
          btnManage.addEventListener("click", () => {
            this.openRepeaterAdminModal(node.public_key, cleanName);
          });
        }

        const btnPingZero = nCard.querySelector(".btn-node-ping-zero");
        if (btnPingZero) {
          btnPingZero.addEventListener("click", (e) => {
            e.stopPropagation();
            this.pingZero(node.public_key, cleanName);
          });
        }

        const btnTrace = nCard.querySelector(".btn-node-traceroute");
        if (btnTrace) {
          btnTrace.addEventListener("click", (e) => {
            e.stopPropagation();
            this.openTracerouteModal(node.public_key, cleanName);
          });
        }

        const btnViewMap = nCard.querySelector(".btn-node-view-map");
        if (btnViewMap) {
          btnViewMap.addEventListener("click", (e) => {
            e.stopPropagation();
            this.focusNodeOnMap(node.public_key);
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
            const payload = { type: isLocal ? "local" : isSensor ? "sensor" : "contact", public_key: node.public_key, name: cleanName, role: roleLabel };
            const uri = `meshcore://${isLocal ? "local" : isSensor ? "sensor" : "contact"}?pubkey=${encodeURIComponent(node.public_key)}&name=${encodeURIComponent(cleanName)}&role=${roleLabel}`;
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

          const altStr = (node.altitude_m != null || node.alt != null) ? ` (${node.altitude_m ?? node.alt}m)` : "";
          const popupContent = `
            <div class="custom-map-popup">
              <div class="popup-title">
                ${isLocal ? '🟢 <strong>' + this.escapeHtml(cleanName) + ' (Local)</strong>' : (isSelected ? '🎯 <strong>' + this.escapeHtml(cleanName) + ' (Seleccionado)</strong>' : '📍 <strong>' + this.escapeHtml(cleanName) + '</strong>')}
              </div>
              <div class="popup-info">
                <div><span>Rol:</span> <strong>${roleStr}</strong></div>
                <div><span>SNR:</span> <strong>${snrVal}</strong></div>
                <div><span>Batería:</span> <strong>${batVal}</strong></div>
                <div><span>GPS:</span> <code>${lat.toFixed(4)}, ${lon.toFixed(4)}</code>${altStr}</div>
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
            <span>📶 ${snrVal}</span>
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
    if (contactsGrid) {
      if (clientContactCount === 0) {
        contactsGrid.innerHTML = '<div class="empty-state">No hay otros contactos cliente registrados. Los nodos repetidores y routers se gestionan en la pestaña <strong>Nodos</strong>.</div>';
      } else {
        contactsGrid.appendChild(contactsFrag);
      }
    }
    if (unifiedNodesGrid) {
      if (totalCount === 0) {
        unifiedNodesGrid.innerHTML = '<div class="empty-state">No se han descubierto nodos en la malla LoRa.</div>';
      } else {
        unifiedNodesGrid.appendChild(nodesFrag);
      }
    }
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
    const cards = contactsGrid.querySelectorAll(".contact-card, .contact-item-card");
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
