/**
 * MeshCore Web Client - Reactive Vanilla JS Application Engine (v3.0)
 * Incluye mensajería, mapa interactivo, RF Sniffer 0x88, métricas avanzadas y consola de logs.
 */

(function () {
  "use strict";

  // Estado global de la aplicación
  const state = {
    ws: null,
    connected: false,
    activeTarget: { type: "channel", id: 0, name: "Canal 0 (Público)" },
    nodes: [],
    contacts: [],
    channels: [],
    messages: [],
    telemetry: [],
    snifferLogs: [],
    systemLogs: [],
    analytics: {},
    map: null,
    mapMarkers: {},
    snifferActive: false,
    selectedLogLevel: "ALL",
    logSearchQuery: "",
  };

  // Elementos DOM
  const dom = {
    wsStatus: document.getElementById("wsStatus"),
    headerNodeCount: document.getElementById("headerNodeCount"),
    headerRxCount: document.getElementById("headerRxCount"),
    headerTxCount: document.getElementById("headerTxCount"),
    headerErrorRate: document.getElementById("headerErrorRate"),
    headerQueueDepth: document.getElementById("headerQueueDepth"),
    themeToggleBtn: document.getElementById("themeToggleBtn"),
    navButtons: document.querySelectorAll(".nav-btn"),
    tabPanes: document.querySelectorAll(".tab-pane"),
    channelListUi: document.getElementById("channelListUi"),
    dmListUi: document.getElementById("dmListUi"),
    chatActiveTitle: document.getElementById("chatActiveTitle"),
    chatActiveSub: document.getElementById("chatActiveSub"),
    chatMessageFeed: document.getElementById("chatMessageFeed"),
    chatInputForm: document.getElementById("chatInputForm"),
    chatInputText: document.getElementById("chatInputText"),
    clearChatBtn: document.getElementById("clearChatBtn"),
    nodesGridUi: document.getElementById("nodesGridUi"),
    btnRefreshNodes: document.getElementById("btnRefreshNodes"),
    repeaterCmdForm: document.getElementById("repeaterCmdForm"),
    repTarget: document.getElementById("repTarget"),
    repAction: document.getElementById("repAction"),
    repConsoleOutput: document.getElementById("repConsoleOutput"),
    // Sniffer DOM
    btnToggleSniffer: document.getElementById("btnToggleSniffer"),
    btnClearSniffer: document.getElementById("btnClearSniffer"),
    filterSnifferType: document.getElementById("filterSnifferType"),
    filterSnifferNode: document.getElementById("filterSnifferNode"),
    filterSnifferRoute: document.getElementById("filterSnifferRoute"),
    snifferTableBody: document.getElementById("snifferTableBody"),
    // Analytics DOM
    btnRefreshAnalytics: document.getElementById("btnRefreshAnalytics"),
    kpiTotalPackets: document.getElementById("kpiTotalPackets"),
    kpiRxTxSplit: document.getElementById("kpiRxTxSplit"),
    kpiActiveNodes: document.getElementById("kpiActiveNodes"),
    kpiGlobalErrorRate: document.getElementById("kpiGlobalErrorRate"),
    kpiTotalErrorsCount: document.getElementById("kpiTotalErrorsCount"),
    kpiAvgSnr: document.getElementById("kpiAvgSnr"),
    kpiAvgRssi: document.getElementById("kpiAvgRssi"),
    topTrafficNodesList: document.getElementById("topTrafficNodesList"),
    topRepeatersList: document.getElementById("topRepeatersList"),
    topSignalNodesList: document.getElementById("topSignalNodesList"),
    topErrorsList: document.getElementById("topErrorsList"),
    // Logs DOM
    btnExportLogs: document.getElementById("btnExportLogs"),
    btnClearLogs: document.getElementById("btnClearLogs"),
    levelChips: document.querySelectorAll(".level-chips .chip"),
    logSearchInput: document.getElementById("logSearchInput"),
    autoScrollLogs: document.getElementById("autoScrollLogs"),
    terminalLogFeed: document.getElementById("terminalLogFeed"),
    // Contactos & Canales DOM
    addContactForm: document.getElementById("addContactForm"),
    contactsListContainer: document.getElementById("contactsListContainer"),
    addChannelForm: document.getElementById("addChannelForm"),
    channelsDetailContainer: document.getElementById("channelsDetailContainer"),
    telemetryGridUi: document.getElementById("telemetryGridUi"),
    localRadioForm: document.getElementById("localRadioForm"),
    btnRebootRadio: document.getElementById("btnRebootRadio"),
    diagBridgeStatus: document.getElementById("diagBridgeStatus"),
    diagSerialPort: document.getElementById("diagSerialPort"),
    diagMqttConnected: document.getElementById("diagMqttConnected"),
    diagBufferCount: document.getElementById("diagBufferCount"),
    diagUptime: document.getElementById("diagUptime"),
  };

  // ================================================================
  // Inicialización
  // ================================================================
  function init() {
    setupTabNavigation();
    setupThemeToggle();
    setupForms();
    setupSnifferControls();
    setupLogsControls();
    initLeafletMap();
    connectWebSocket();
    fetchInitialData();
    setInterval(fetchPeriodicStatus, 5000);
  }

  // ================================================================
  // Navegación por Pestañas
  // ================================================================
  function setupTabNavigation() {
    dom.navButtons.forEach((btn, index) => {
      btn.addEventListener("click", () => {
        const targetTab = btn.getAttribute("data-tab");
        dom.navButtons.forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
        });
        dom.tabPanes.forEach((p) => p.classList.remove("active"));

        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        const pane = document.getElementById(targetTab);
        if (pane) pane.classList.add("active");

        if (targetTab === "tab-map" && state.map) {
          setTimeout(() => state.map.invalidateSize(), 200);
        }
        if (targetTab === "tab-analytics") {
          fetchAnalytics();
        }
        if (targetTab === "tab-sniffer") {
          fetchSnifferLogs();
        }
        if (targetTab === "tab-logs") {
          fetchSystemLogs();
        }
      });

      // Navegación accesible por teclado (Flechas Arriba/Abajo)
      btn.addEventListener("keydown", (e) => {
        let nextBtn = null;
        if (e.key === "ArrowDown" || e.key === "ArrowRight") {
          nextBtn = dom.navButtons[(index + 1) % dom.navButtons.length];
        } else if (e.key === "ArrowUp" || e.key === "ArrowLeft") {
          nextBtn = dom.navButtons[(index - 1 + dom.navButtons.length) % dom.navButtons.length];
        }
        if (nextBtn) {
          e.preventDefault();
          nextBtn.focus();
          nextBtn.click();
        }
      });
    });

    if (dom.clearChatBtn) {
      dom.clearChatBtn.addEventListener("click", () => {
        dom.chatMessageFeed.innerHTML = "";
      });
    }

    if (dom.btnRefreshNodes) {
      dom.btnRefreshNodes.addEventListener("click", fetchNodes);
    }

    if (dom.btnRefreshAnalytics) {
      dom.btnRefreshAnalytics.addEventListener("click", fetchAnalytics);
    }
  }

  // ================================================================
  // Tema Claro / Oscuro
  // ================================================================
  function setupThemeToggle() {
    if (!dom.themeToggleBtn) return;
    dom.themeToggleBtn.addEventListener("click", () => {
      document.body.classList.toggle("light-theme");
      document.body.classList.toggle("dark-theme");
    });
  }

  // ================================================================
  // WebSocket en Tiempo Real
  // ================================================================
  function connectWebSocket() {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${proto}//${window.location.host}/ws/live`;

    try {
      state.ws = new WebSocket(wsUrl);

      state.ws.onopen = () => {
        state.connected = true;
        updateWsBadge(true);
        appendTerminalLog("INFO", "Conexión WebSocket establecida con el bridge.");
      };

      state.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleIncomingWsEvent(data);
        } catch (e) {
          console.debug("Error parseando evento WS:", e);
        }
      };

      state.ws.onclose = () => {
        state.connected = false;
        updateWsBadge(false);
        appendTerminalLog("WARN", "WebSocket desconectado. Reintentando...");
        setTimeout(connectWebSocket, 3000);
      };

      state.ws.onerror = () => {
        state.connected = false;
        updateWsBadge(false);
      };
    } catch (e) {
      setTimeout(connectWebSocket, 3000);
    }
  }

  function updateWsBadge(connected) {
    if (!dom.wsStatus) return;
    const dot = dom.wsStatus.querySelector(".status-dot");
    const text = dom.wsStatus.querySelector(".status-text");
    if (connected) {
      if (dot) dot.className = "status-dot connected";
      if (text) text.textContent = "En Vivo (LoRa)";
    } else {
      if (dot) dot.className = "status-dot disconnected";
      if (text) text.textContent = "Reconectando...";
    }
  }

  function handleIncomingWsEvent(event) {
    const type = event.event_type || "";

    // 1. Mensaje de Texto
    if (type === "public" || type === "channel" || type === "direct" || event.text) {
      appendChatMessage(event);
      state.messages.push(event);
      if (type === "direct" && event.sender) {
        addOrUpdateDmItem(event.sender, event.sender_name);
      }
      appendTerminalLog("INFO", `Mensaje [${type}] de ${event.sender_name || event.sender}: ${event.text || ""}`);
    }

    // 2. Telemetría Ambiental
    if (type === "telemetry" || event.temperature_c !== undefined || event.battery_pct !== undefined) {
      state.telemetry.unshift(event);
      renderTelemetryCards();
      if (event.gps) {
        updateMapNodePosition(event.sender || event.sender_id, event.sender_name, event.gps);
      }
      appendTerminalLog("INFO", `Telemetría recibida de nodo ${event.sender || event.sender_id}`);
    }

    // 3. Log de Sniffer RF
    if (type === "rf_log") {
      state.snifferLogs.unshift(event);
      renderSnifferTable();
      appendTerminalLog("INFO", `[RF SNIFFER] Capturada trama de ${event.byte_length || 0} bytes en ${event.route_type_id || "RF"}`);
    }

    // 4. Anuncio de Nodos
    if (type === "node_advert" || event.public_key) {
      fetchNodes();
      appendTerminalLog("INFO", `Anuncio de presencia de nodo ${event.public_key || ""}`);
    }
  }

  // ================================================================
  // Feed de Mensajería y Renderizado de Burbujas
  // ================================================================
  function appendChatMessage(msg) {
    if (!dom.chatMessageFeed) return;

    const chIdx = msg.channel_idx !== undefined ? msg.channel_idx : (msg.channel_index !== undefined ? msg.channel_index : 0);
    const isDirect = msg.event_type === "direct";
    const sender = msg.sender || msg.sender_id || "Desconocido";
    const senderName = msg.sender_name || sender;

    if (state.activeTarget.type === "channel" && (isDirect || chIdx !== state.activeTarget.id)) {
      return;
    }
    if (state.activeTarget.type === "dm" && (!isDirect || sender !== state.activeTarget.id)) {
      return;
    }

    const bubble = document.createElement("div");
    bubble.className = msg.is_outbound ? "chat-bubble outbound" : "chat-bubble";

    const timeStr = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : new Date().toLocaleTimeString();
    const rssiStr = msg.metrics && msg.metrics.rssi ? ` | RSSI: ${msg.metrics.rssi} dBm` : "";
    const snrStr = msg.metrics && msg.metrics.snr ? ` | SNR: ${msg.metrics.snr} dB` : "";

    bubble.innerHTML = `
      <div class="bubble-meta">
        <span class="sender-tag">${escapeHtml(senderName)}</span>
        <span class="time">${timeStr}</span>
      </div>
      <div class="bubble-text">${escapeHtml(msg.text || "")}</div>
      ${!msg.is_outbound ? `<div class="bubble-metrics">${rssiStr}${snrStr}</div>` : ""}
    `;

    dom.chatMessageFeed.appendChild(bubble);
    dom.chatMessageFeed.scrollTop = dom.chatMessageFeed.scrollHeight;
  }

  // ================================================================
  // RF Packet Sniffer & Analizador de Tramas
  // ================================================================
  function setupSnifferControls() {
    if (dom.btnToggleSniffer) {
      dom.btnToggleSniffer.addEventListener("click", async () => {
        const action = state.snifferActive ? "stop" : "start";
        try {
          const res = await fetch("/api/sniffer/control", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: action }),
          });
          const json = await res.json();
          state.snifferActive = json.sniffer_active;
          dom.btnToggleSniffer.textContent = state.snifferActive ? "⏹ Detener Sniffer" : "▶ Iniciar Sniffer";
          dom.btnToggleSniffer.className = state.snifferActive ? "btn-danger" : "btn-primary";
          appendTerminalLog("INFO", `Sniffer RF ${state.snifferActive ? "ACTIVADO" : "DETENIDO"}`);
        } catch (e) {
          appendTerminalLog("ERROR", `Error controlando sniffer: ${e.message}`);
        }
      });
    }

    if (dom.btnClearSniffer) {
      dom.btnClearSniffer.addEventListener("click", () => {
        state.snifferLogs = [];
        renderSnifferTable();
      });
    }

    if (dom.filterSnifferType) dom.filterSnifferType.addEventListener("change", renderSnifferTable);
    if (dom.filterSnifferNode) dom.filterSnifferNode.addEventListener("input", renderSnifferTable);
    if (dom.filterSnifferRoute) dom.filterSnifferRoute.addEventListener("change", renderSnifferTable);
  }

  async function fetchSnifferLogs() {
    try {
      const res = await fetch("/api/logs");
      const data = await res.json();
      state.snifferLogs = data.logs || [];
      renderSnifferTable();
    } catch (e) {
      console.debug(e);
    }
  }

  function renderSnifferTable() {
    if (!dom.snifferTableBody) return;

    const typeFilter = dom.filterSnifferType ? dom.filterSnifferType.value : "ALL";
    const nodeFilter = dom.filterSnifferNode ? dom.filterSnifferNode.value.trim().toLowerCase() : "";
    const routeFilter = dom.filterSnifferRoute ? dom.filterSnifferRoute.value : "ALL";

    const filtered = state.snifferLogs.filter((log) => {
      const pType = String(log.payload_type_id || log.payload_type || "");
      const rType = String(log.route_type_id || log.route_type || "");
      const sender = String(log.sender || log.src_node || "").toLowerCase();

      if (typeFilter !== "ALL" && !pType.includes(typeFilter)) return false;
      if (routeFilter !== "ALL" && !rType.includes(routeFilter)) return false;
      if (nodeFilter && !sender.includes(nodeFilter)) return false;
      return true;
    });

    if (filtered.length === 0) {
      dom.snifferTableBody.innerHTML = '<tr class="empty-row"><td colspan="8">No hay tramas coincidentes con los filtros.</td></tr>';
      return;
    }

    dom.snifferTableBody.innerHTML = filtered
      .slice(0, 100)
      .map((log) => {
        const timeStr = log.iso_time || (log.timestamp ? new Date(log.timestamp).toLocaleTimeString() : "--");
        const routeTag = `<span class="tag-route">${escapeHtml(log.route_type_id || "FLOOD")}</span>`;
        const payloadTag = `<span class="tag-payload">${escapeHtml(log.payload_type_id || log.payload_type || "UNKNOWN")}</span>`;
        const senderStr = escapeHtml(log.sender || log.src_node || "broadcast");
        const hopsStr = log.hop_count !== undefined ? `${log.hop_count} saltos` : "0";
        const bytesStr = `${log.byte_length || (log.raw_hex ? log.raw_hex.length / 2 : 0)} B`;
        const metricsStr = log.metrics ? `${log.metrics.rssi || -80}dBm / ${log.metrics.snr || 10}dB` : "--";
        const hexDump = log.raw_hex || log.hex_data || "0xAA ... 0x55";

        return `
        <tr>
          <td>${timeStr}</td>
          <td>${routeTag}</td>
          <td>${payloadTag}</td>
          <td><strong>${senderStr}</strong></td>
          <td>${hopsStr}</td>
          <td>${bytesStr}</td>
          <td>${metricsStr}</td>
          <td class="hex-cell" title="${escapeHtml(hexDump)}">${escapeHtml(hexDump)}</td>
        </tr>
      `;
      })
      .join("");
  }

  // ================================================================
  // Métricas Avanzadas y Tops
  // ================================================================
  async function fetchAnalytics() {
    try {
      const res = await fetch("/api/analytics");
      const data = await res.json();
      state.analytics = data;
      renderAnalyticsDashboard(data);
    } catch (e) {
      console.debug("Error obteniendo analítica:", e);
    }
  }

  function renderAnalyticsDashboard(data) {
    const sum = data.summary || {};

    if (dom.kpiTotalPackets) dom.kpiTotalPackets.textContent = (sum.total_rx_packets || 0) + (sum.total_tx_packets || 0);
    if (dom.kpiRxTxSplit) dom.kpiRxTxSplit.textContent = `RX: ${sum.total_rx_packets || 0} | TX: ${sum.total_tx_packets || 0}`;
    if (dom.kpiActiveNodes) dom.kpiActiveNodes.textContent = sum.total_nodes || state.nodes.length;
    if (dom.kpiGlobalErrorRate) dom.kpiGlobalErrorRate.textContent = `${sum.global_error_rate_pct || 0.0}%`;
    if (dom.headerErrorRate) dom.headerErrorRate.textContent = `${sum.global_error_rate_pct || 0.0}%`;
    if (dom.kpiTotalErrorsCount) dom.kpiTotalErrorsCount.textContent = `${sum.total_errors || 0} errores registrados`;

    // 1. Top Nodos por Tráfico
    if (dom.topTrafficNodesList) {
      const topT = data.top_nodes_by_traffic || [];
      if (topT.length === 0) {
        dom.topTrafficNodesList.innerHTML = '<div class="empty-state">Sin tráfico acumulado.</div>';
      } else {
        const maxPackets = Math.max(...topT.map((n) => n.total_packets || 1), 1);
        dom.topTrafficNodesList.innerHTML = topT
          .map((n, idx) => {
            const pct = Math.round(((n.total_packets || 0) / maxPackets) * 100);
            return `
            <div class="leaderboard-item">
              <span class="leaderboard-rank">#${idx + 1}</span>
              <span style="font-weight:600; width:120px;">${escapeHtml(n.alias || n.name)}</span>
              <div class="progress-bar-container">
                <div class="progress-bar-fill" style="width: ${pct}%"></div>
              </div>
              <span><strong>${n.total_packets || 0}</strong> pkts (RX:${n.rx_packets || 0}/TX:${n.tx_packets || 0})</span>
            </div>
          `;
          })
          .join("");
      }
    }

    // 2. Top Repetidores por Clientes
    if (dom.topRepeatersList) {
      const topR = data.top_repeaters_by_clients || [];
      if (topR.length === 0) {
        dom.topRepeatersList.innerHTML = '<div class="empty-state">Sin repetidores con vecinos registrados.</div>';
      } else {
        dom.topRepeatersList.innerHTML = topR
          .map((r, idx) => `
          <div class="leaderboard-item">
            <span class="leaderboard-rank">#${idx + 1}</span>
            <span style="font-weight:600;">${escapeHtml(r.alias || r.name)}</span>
            <span class="badge-tag">${r.connected_clients_count || 0} clientes conectados</span>
          </div>
        `)
          .join("");
      }
    }

    // 3. Ranking de Señal
    if (dom.topSignalNodesList) {
      const topS = data.top_nodes_best_snr || [];
      if (topS.length === 0) {
        dom.topSignalNodesList.innerHTML = '<div class="empty-state">Sin nodos con métricas de enlace.</div>';
      } else {
        dom.topSignalNodesList.innerHTML = topS
          .map((s, idx) => `
          <div class="leaderboard-item">
            <span class="leaderboard-rank">#${idx + 1}</span>
            <span>${escapeHtml(s.alias || s.name)}</span>
            <span>SNR: <strong>${s.last_snr} dB</strong> | RSSI: ${s.last_rssi} dBm</span>
          </div>
        `)
          .join("");
      }
    }

    // 4. Desglose de Errores
    if (dom.topErrorsList) {
      const errors = data.top_error_breakdown || [];
      const hasErrors = errors.some((e) => e.count > 0);
      if (!hasErrors) {
        dom.topErrorsList.innerHTML = '<div class="empty-state" style="color:var(--accent-emerald)">0 errores detectados. Operación estable al 100%.</div>';
      } else {
        dom.topErrorsList.innerHTML = errors
          .filter((e) => e.count > 0)
          .map((e) => `
          <div class="leaderboard-item">
            <span style="color:var(--accent-rose); font-weight:600;">${escapeHtml(e.category)}</span>
            <span><strong>${e.count}</strong> incidencias</span>
          </div>
        `)
          .join("");
      }
    }
  }

  // ================================================================
  // Consola de Logs del Sistema
  // ================================================================
  function setupLogsControls() {
    if (dom.levelChips) {
      dom.levelChips.forEach((chip) => {
        chip.addEventListener("click", () => {
          dom.levelChips.forEach((c) => c.classList.remove("active"));
          chip.classList.add("active");
          state.selectedLogLevel = chip.getAttribute("data-level") || "ALL";
          renderTerminalLogs();
        });
      });
    }

    if (dom.logSearchInput) {
      dom.logSearchInput.addEventListener("input", (e) => {
        state.logSearchQuery = e.target.value.toLowerCase();
        renderTerminalLogs();
      });
    }

    if (dom.btnClearLogs) {
      dom.btnClearLogs.addEventListener("click", () => {
        state.systemLogs = [];
        renderTerminalLogs();
      });
    }

    if (dom.btnExportLogs) {
      dom.btnExportLogs.addEventListener("click", () => {
        const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(state.systemLogs, null, 2));
        const dlAnchor = document.createElement("a");
        dlAnchor.setAttribute("href", dataStr);
        dlAnchor.setAttribute("download", `meshcore_logs_${new Date().toISOString().slice(0, 10)}.json`);
        document.body.appendChild(dlAnchor);
        dlAnchor.click();
        dlAnchor.remove();
      });
    }
  }

  async function fetchSystemLogs() {
    try {
      const res = await fetch("/api/system/logs");
      const data = await res.json();
      state.systemLogs = data.system_logs || [];
      renderTerminalLogs();
    } catch (e) {
      console.debug(e);
    }
  }

  function appendTerminalLog(level, msg) {
    const entry = {
      timestamp: Date.now(),
      iso_time: new Date().toLocaleTimeString(),
      level: level.toUpperCase(),
      message: msg,
    };
    state.systemLogs.push(entry);
    if (state.systemLogs.length > 500) state.systemLogs.shift();
    renderTerminalLogs();
  }

  function renderTerminalLogs() {
    if (!dom.terminalLogFeed) return;

    const filtered = state.systemLogs.filter((l) => {
      if (state.selectedLogLevel !== "ALL" && l.level !== state.selectedLogLevel) return false;
      if (state.logSearchQuery && !l.message.toLowerCase().includes(state.logSearchQuery)) return false;
      return true;
    });

    dom.terminalLogFeed.innerHTML = filtered
      .map((l) => {
        const lvlClass = l.level === "ERROR" ? "error" : (l.level === "WARN" ? "warn" : "info");
        return `<div class="log-line ${lvlClass}"><span class="log-timestamp">[${l.iso_time}]</span> [${l.level}] ${escapeHtml(l.message)}</div>`;
      })
      .join("");

    if (dom.autoScrollLogs && dom.autoScrollLogs.checked) {
      dom.terminalLogFeed.scrollTop = dom.terminalLogFeed.scrollHeight;
    }
  }

  // ================================================================
  // Enviar Mensaje TX y Comandos
  // ================================================================
  function setupForms() {
    if (dom.chatInputForm) {
      dom.chatInputForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const text = (dom.chatInputText.value || "").trim();
        if (!text) return;

        const payload = {
          text: text,
          to: state.activeTarget.type === "dm" ? state.activeTarget.id : "broadcast",
          channel_index: state.activeTarget.type === "channel" ? state.activeTarget.id : 0,
        };

        appendChatMessage({
          sender_name: "Tú (Base)",
          text: text,
          is_outbound: true,
          timestamp: new Date().toISOString(),
        });
        dom.chatInputText.value = "";

        try {
          const res = await fetch("/api/tx", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const json = await res.json();
          if (json.status !== "ok") {
            appendConsoleLog(`[ERROR TX] ${json.error || "Fallo en transmisión"}`);
          }
        } catch (err) {
          appendConsoleLog(`[ERROR TX] ${err.message}`);
        }
      });
    }

    if (dom.repeaterCmdForm) {
      dom.repeaterCmdForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = dom.repTarget.value.trim();
        const action = dom.repAction.value;
        if (!target) return;

        appendConsoleLog(`[TX CMD] Enviando "${action}" a repetidor ${target}...`);

        try {
          const res = await fetch("/api/admin/repeater", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, action: action }),
          });
          const json = await res.json();
          appendConsoleLog(`[RESP CMD] ${JSON.stringify(json.result || json)}`);
        } catch (err) {
          appendConsoleLog(`[ERROR CMD] ${err.message}`);
        }
      });
    }

    if (dom.addContactForm) {
      dom.addContactForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const key = document.getElementById("contactPubKey").value.trim();
        const name = document.getElementById("contactName").value.trim();
        const alias = document.getElementById("contactAlias").value.trim();

        if (!key) return;
        await fetch("/api/contacts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ public_key: key, name: name, alias: alias }),
        });

        dom.addContactForm.reset();
        fetchContacts();
      });
    }

    if (dom.addChannelForm) {
      dom.addChannelForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const idx = parseInt(document.getElementById("chIndexSelect").value, 10);
        const name = document.getElementById("chNameInput").value.trim();
        const psk = document.getElementById("chPskInput").value.trim();

        await fetch("/api/channels", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ index: idx, name: name, psk: psk }),
        });

        dom.addChannelForm.reset();
        fetchChannels();
      });
    }

    if (dom.localRadioForm) {
      dom.localRadioForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const name = document.getElementById("localNodeName").value.trim();
        const pwr = parseInt(document.getElementById("localTxPower").value, 10);

        if (name) {
          await fetch("/api/admin/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "set_name", name: name }),
          });
        }
        if (pwr) {
          await fetch("/api/admin/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "set_tx_power", power: pwr }),
          });
        }
        alert("Configuración enviada a la radio local.");
      });
    }

    if (dom.btnRebootRadio) {
      dom.btnRebootRadio.addEventListener("click", async () => {
        if (confirm("¿Reiniciar transceptor LoRa local?")) {
          await fetch("/api/admin/command", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "reboot" }),
          });
        }
      });
    }
  }

  // ================================================================
  // Consultas REST
  // ================================================================
  async function fetchInitialData() {
    await Promise.all([fetchChannels(), fetchNodes(), fetchContacts(), fetchPeriodicStatus(), fetchAnalytics()]);
  }

  async function fetchChannels() {
    try {
      const res = await fetch("/api/channels");
      const data = await res.json();
      state.channels = data.channels || [];
      renderChannelList();
    } catch (e) {
      console.debug(e);
    }
  }

  async function fetchNodes() {
    try {
      const res = await fetch("/api/nodes");
      const data = await res.json();
      state.nodes = data.nodes || [];
      renderNodesGrid();
      if (dom.headerNodeCount) dom.headerNodeCount.textContent = state.nodes.length;
    } catch (e) {
      console.debug(e);
    }
  }

  async function fetchContacts() {
    try {
      const res = await fetch("/api/contacts");
      const data = await res.json();
      state.contacts = data.contacts || [];
      renderContactsList();
    } catch (e) {
      console.debug(e);
    }
  }

  async function fetchPeriodicStatus() {
    try {
      const res = await fetch("/api/status");
      const data = await res.json();
      if (dom.headerRxCount) dom.headerRxCount.textContent = data.total_rx_packets || 0;
      if (dom.headerTxCount) dom.headerTxCount.textContent = data.total_tx_packets || 0;
      if (dom.headerQueueDepth) dom.headerQueueDepth.textContent = data.tx_queue_depth || 0;
      if (dom.diagBridgeStatus) dom.diagBridgeStatus.textContent = data.bridge_status || "Online";
      if (dom.diagMqttConnected) dom.diagMqttConnected.textContent = data.mqtt_connected ? "Conectado" : "Desconectado";
      if (dom.diagBufferCount) dom.diagBufferCount.textContent = data.offline_buffer_pending || 0;
      if (dom.diagUptime) dom.diagUptime.textContent = `${data.uptime_seconds || 0}s`;
    } catch (e) {
      console.debug(e);
    }
  }

  // ================================================================
  // Renderizado de Componentes
  // ================================================================
  function renderChannelList() {
    if (!dom.channelListUi) return;
    dom.channelListUi.innerHTML = "";

    state.channels.forEach((ch) => {
      const li = document.createElement("li");
      const isActive = state.activeTarget.type === "channel" && state.activeTarget.id === ch.index;
      li.className = isActive ? "channel-item active" : "channel-item";
      li.innerHTML = `
        <span class="ch-badge">Ch ${ch.index}</span>
        <span class="ch-name">${escapeHtml(ch.name)}</span>
      `;
      li.addEventListener("click", () => {
        state.activeTarget = { type: "channel", id: ch.index, name: `Canal ${ch.index} (${ch.name})` };
        dom.chatActiveTitle.textContent = state.activeTarget.name;
        dom.chatActiveSub.textContent = ch.is_public ? "Difusión comunitaria" : "Canal cifrado con AES";
        renderChannelList();
      });
      dom.channelListUi.appendChild(li);
    });

    if (dom.channelsDetailContainer) {
      dom.channelsDetailContainer.innerHTML = state.channels
        .map(
          (c) => `
        <div class="stat-item">
          <span><strong>Ch ${c.index}:</strong> ${escapeHtml(c.name)}</span>
          <span class="badge-tag">${c.is_public ? "Público" : "Cifrado"}</span>
        </div>
      `
        )
        .join("");
    }
  }

  function addOrUpdateDmItem(key, name) {
    if (!dom.dmListUi) return;
    let existing = dom.dmListUi.querySelector(`[data-dm-key="${key}"]`);
    if (!existing) {
      const li = document.createElement("li");
      li.className = "channel-item";
      li.setAttribute("data-dm-key", key);
      li.innerHTML = `
        <span class="ch-badge">DM</span>
        <span class="ch-name">${escapeHtml(name || key.substring(0, 8))}</span>
      `;
      li.addEventListener("click", () => {
        state.activeTarget = { type: "dm", id: key, name: `DM con ${name || key}` };
        dom.chatActiveTitle.textContent = state.activeTarget.name;
        dom.chatActiveSub.textContent = `Clave: ${key}`;
      });
      dom.dmListUi.appendChild(li);
    }
  }

  function renderNodesGrid() {
    if (!dom.nodesGridUi) return;
    if (!state.nodes || state.nodes.length === 0) {
      dom.nodesGridUi.innerHTML = '<div class="empty-state">No se han detectado nodos aún.</div>';
      return;
    }

    dom.nodesGridUi.innerHTML = state.nodes
      .map(
        (n) => `
      <div class="node-card">
        <div class="node-header">
          <span class="node-name">${escapeHtml(n.alias || n.name)}</span>
          <span class="badge-tag">${n.hops || 0} Saltos</span>
        </div>
        <div class="node-key">${escapeHtml(n.public_key || "")}</div>
        <div class="node-stats">
          <div>📶 RSSI: <strong>${n.last_rssi || -80} dBm</strong></div>
          <div>📡 SNR: <strong>${n.last_snr || 10} dB</strong></div>
          <div>🔋 Batería: <strong>${n.battery_pct !== null && n.battery_pct !== undefined ? n.battery_pct + "%" : "N/A"}</strong></div>
          <div>📦 Tráfico: <strong>${n.total_packets || 0} pkts</strong></div>
        </div>
        <button class="btn-secondary btn-sm" onclick="window.setDmTarget('${n.public_key}', '${escapeHtml(n.name)}')">Enviar DM 💬</button>
      </div>
    `
      )
      .join("");
  }

  function renderContactsList() {
    if (!dom.contactsListContainer) return;
    dom.contactsListContainer.innerHTML = state.contacts
      .map(
        (c) => `
      <div class="stat-item">
        <div>
          <strong>${escapeHtml(c.alias || c.name)}</strong>
          <div style="font-size:0.75rem; color:var(--text-muted); font-family:monospace;">${escapeHtml(c.public_key)}</div>
        </div>
        <button class="btn-secondary btn-sm" onclick="window.setDmTarget('${c.public_key}', '${escapeHtml(c.alias || c.name)}')">Chat</button>
      </div>
    `
      )
      .join("");
  }

  function renderTelemetryCards() {
    if (!dom.telemetryGridUi) return;
    dom.telemetryGridUi.innerHTML = state.telemetry
      .slice(0, 12)
      .map(
        (t) => `
      <div class="node-card">
        <div class="node-header">
          <span class="node-name">Nodo ${escapeHtml(t.sender_name || t.sender || "Sensor")}</span>
          <span class="badge-tag">CayenneLPP</span>
        </div>
        <div class="node-stats">
          ${t.temperature_c !== undefined ? `<div>🌡️ Temp: <strong>${t.temperature_c} °C</strong></div>` : ""}
          ${t.humidity_pct !== undefined ? `<div>💧 Humedad: <strong>${t.humidity_pct} %</strong></div>` : ""}
          ${t.pressure_hpa !== undefined ? `<div>⏱️ Presión: <strong>${t.pressure_hpa} hPa</strong></div>` : ""}
          ${t.voltage_v !== undefined ? `<div>⚡ Voltaje: <strong>${t.voltage_v} V</strong></div>` : ""}
          ${t.battery_pct !== undefined ? `<div>🔋 Batería: <strong>${t.battery_pct} %</strong></div>` : ""}
        </div>
      </div>
    `
      )
      .join("");
  }

  // ================================================================
  // Mapa Leaflet con Resiliencia Offline
  // ================================================================
  function initLeafletMap() {
    const mapEl = document.getElementById("liveGpsMap");
    if (!mapEl) return;

    if (typeof L === "undefined") {
      mapEl.innerHTML = `
        <div class="map-offline-fallback">
          <div style="font-size: 2.8rem; margin-bottom: 12px;">🗺️</div>
          <h3>Modo de Mapa Offline</h3>
          <p>La estación base está operando sin conexión a Internet externa.</p>
          <p style="font-size: 0.82rem; color: var(--text-muted); margin-top: 8px;">
            Las posiciones GPS de los nodos continúan registrándose y mostrándose en el panel lateral.
          </p>
        </div>
      `;
      return;
    }

    try {
      state.map = L.map("liveGpsMap").setView([20.0, -75.0], 4);
      L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
        maxZoom: 19,
        attribution: "© OpenStreetMap",
      }).addTo(state.map);
    } catch (e) {
      console.debug("Error inicializando mapa Leaflet:", e);
    }
  }

  function updateMapNodePosition(nodeId, nodeName, gps) {
    if (!state.map || !gps || !gps.latitude || !gps.longitude) return;

    const lat = gps.latitude;
    const lon = gps.longitude;

    if (!state.mapMarkers[nodeId]) {
      const marker = L.marker([lat, lon]).addTo(state.map);
      marker.bindPopup(`<b>${escapeHtml(nodeName || nodeId)}</b><br>Altitud: ${gps.altitude_m || 0}m`);
      state.mapMarkers[nodeId] = marker;
      state.map.setView([lat, lon], 12);
    } else {
      state.mapMarkers[nodeId].setLatLng([lat, lon]);
    }
  }

  function appendConsoleLog(text) {
    if (!dom.repConsoleOutput) return;
    const line = document.createElement("div");
    line.textContent = `[${new Date().toLocaleTimeString()}] ${text}`;
    dom.repConsoleOutput.appendChild(line);
    dom.repConsoleOutput.scrollTop = dom.repConsoleOutput.scrollHeight;
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  window.setDmTarget = function (key, name) {
    state.activeTarget = { type: "dm", id: key, name: `DM con ${name || key}` };
    if (dom.chatActiveTitle) dom.chatActiveTitle.textContent = state.activeTarget.name;
    if (dom.chatActiveSub) dom.chatActiveSub.textContent = `Clave: ${key}`;
    const chatTabBtn = document.querySelector('[data-tab="tab-chat"]');
    if (chatTabBtn) chatTabBtn.click();
  };

  // Iniciar al cargar el DOM
  document.addEventListener("DOMContentLoaded", init);
})();
