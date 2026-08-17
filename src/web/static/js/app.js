/**
 * MeshCore Web Client - Reactive Vanilla JS Application Engine (v3.0)
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
    map: null,
    mapMarkers: {},
  };

  // Elementos DOM
  const dom = {
    wsStatus: document.getElementById("wsStatus"),
    headerNodeCount: document.getElementById("headerNodeCount"),
    headerRxCount: document.getElementById("headerRxCount"),
    headerTxCount: document.getElementById("headerTxCount"),
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
    initLeafletMap();
    connectWebSocket();
    fetchInitialData();
    setInterval(fetchPeriodicStatus, 5000);
  }

  // ================================================================
  // Navegación por Pestañas
  // ================================================================
  function setupTabNavigation() {
    dom.navButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        const targetTab = btn.getAttribute("data-tab");
        dom.navButtons.forEach((b) => b.classList.remove("active"));
        dom.tabPanes.forEach((p) => p.classList.remove("active"));

        btn.classList.add("active");
        const pane = document.getElementById(targetTab);
        if (pane) pane.classList.add("active");

        if (targetTab === "tab-map" && state.map) {
          setTimeout(() => state.map.invalidateSize(), 200);
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

    // 1. Mensaje de Texto (Público, Canal o DM)
    if (type === "public" || type === "channel" || type === "direct" || event.text) {
      appendChatMessage(event);
      state.messages.push(event);
      if (type === "direct" && event.sender) {
        addOrUpdateDmItem(event.sender, event.sender_name);
      }
    }

    // 2. Telemetría Ambiental
    if (type === "telemetry" || event.temperature_c !== undefined || event.battery_pct !== undefined) {
      state.telemetry.unshift(event);
      renderTelemetryCards();
      if (event.gps) {
        updateMapNodePosition(event.sender || event.sender_id, event.sender_name, event.gps);
      }
    }

    // 3. Log de Sniffer RF
    if (type === "rf_log") {
      appendConsoleLog(`[SNIFFER RF] Ruta: ${event.route_type_id} | Tipo: ${event.payload_type_id} | Bytes: ${event.byte_length}`);
    }

    // 4. Anuncio de Nodos
    if (type === "node_advert" || event.public_key) {
      fetchNodes();
    }
  }

  // ================================================================
  // Feed de Mensajería y Renderizado de Burbujas
  // ================================================================
  function appendChatMessage(msg) {
    if (!dom.chatMessageFeed) return;

    // Filtrar si el mensaje corresponde al canal / DM activo
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
  // Enviar Mensaje TX
  // ================================================================
  function setupForms() {
    // 1. Formulario de Chat
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

        // Mostrar de inmediato en UI
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

    // 2. Formulario de Comandos a Repetidores
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

    // 3. Formulario de Añadir Contacto
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

    // 4. Formulario de Añadir Canal
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

    // 5. Configuración de Radio Local
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
    await Promise.all([fetchChannels(), fetchNodes(), fetchContacts(), fetchPeriodicStatus()]);
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
          <div>⏱️ Visto: <strong>${Math.round(Date.now() / 1000 - (n.last_seen || 0))}s atrás</strong></div>
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
  // Mapa Leaflet
  // ================================================================
  function initLeafletMap() {
    const mapEl = document.getElementById("liveGpsMap");
    if (!mapEl || typeof L === "undefined") return;

    state.map = L.map("liveGpsMap").setView([20.0, -75.0], 4);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: "© OpenStreetMap",
    }).addTo(state.map);
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
