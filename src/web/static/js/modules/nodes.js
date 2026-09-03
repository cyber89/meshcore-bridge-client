/**
 * NodesModule - Directorio unificado de nodos, libreta de contactos (clientes),
 * filtrado reactivo, presencia en tiempo real y telemetría analítica.
 */

import { escapeHtml, debounce } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class NodesModule {
  constructor(context) {
    this.ctx = context;
    this.knownNodes = new Map();
    this.activeNodesFilter = "all";
    this.activeContactsFilter = "all";
    this._analyticsDebounceTimer = null;
    this.dom = {};
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.initPresenceTicker();
    this.initContactDiscovery();
    this.initAnalytics();
    this.fetchNodes();
  }

  _bindElements() {
    this.dom = {
      contactsGridUi: document.getElementById("contactsGridUi"),
      nodesUnifiedGridUi: document.getElementById("nodesUnifiedGridUi"),
      contactsSearchInput: document.getElementById("contactsSearchInput"),
      nodesSearchInput: document.getElementById("nodesSearchInput"),
      headerNodeCount: document.getElementById("headerNodeCount"),
    };
  }

  _bindEvents() {
    if (this.dom.contactsSearchInput) {
      const handleContactSearch = debounce((val) => {
        this.filterContactsGrid(val);
      }, 100);
      this.dom.contactsSearchInput.addEventListener("input", (e) => handleContactSearch(e.target.value));
      this.dom.contactsSearchInput.addEventListener("search", (e) => this.filterContactsGrid(e.target.value));
    }

    if (this.dom.nodesSearchInput) {
      const handleNodeSearch = debounce((val) => {
        this.filterNodesGrid(val);
      }, 100);
      this.dom.nodesSearchInput.addEventListener("input", (e) => handleNodeSearch(e.target.value));
      this.dom.nodesSearchInput.addEventListener("search", (e) => this.filterNodesGrid(e.target.value));
    }

    document.querySelectorAll(".contacts-filter-pills .filter-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".contacts-filter-pills .filter-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        this.activeContactsFilter = pill.getAttribute("data-contact-filter") || "all";
        const q = this.dom.contactsSearchInput ? this.dom.contactsSearchInput.value : "";
        this.filterContactsGrid(q);
      });
    });

    document.querySelectorAll(".nodes-filter-pills .filter-pill").forEach((pill) => {
      pill.addEventListener("click", () => {
        document.querySelectorAll(".nodes-filter-pills .filter-pill").forEach((p) => p.classList.remove("active"));
        pill.classList.add("active");
        this.activeNodesFilter = pill.getAttribute("data-filter") || "all";
        const q = this.dom.nodesSearchInput ? this.dom.nodesSearchInput.value : "";
        this.filterNodesGrid(q);
      });
    });
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    this.ctx.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (!payload || typeof payload !== "object") return;
      const evType = payload.type || payload.event_type;

      if (evType === "contacts_updated") {
        if (Array.isArray(payload.data)) {
          this.renderNodesDirectory(payload.data);
        } else {
          this.fetchNodes();
        }
      } else if (evType === "contact_discovered" || evType === "contact_updated") {
        const c = payload.contact || payload.data;
        if (c && c.public_key && this.isValidNodeKey(c.public_key)) {
          const canonicalPk = this.resolveCanonicalPubkey(c.public_key) || c.public_key.toLowerCase().trim();
          this.knownNodes.set(canonicalPk, { ...c, public_key: canonicalPk });
          this.renderNodesDirectory(Array.from(this.knownNodes.values()));
        } else {
          this.fetchNodes();
        }
      }

      // Actualizar presencia
      const sender = payload.sender || payload.public_key || payload.from || payload.pubkey || payload.target_node;
      if (sender && this.isValidNodeKey(sender)) {
        this.updateNodePresenceRealtime(this.resolveCanonicalPubkey(sender), payload);
      }
    });
  }

  isValidNodeKey(key) {
    if (!key || typeof key !== "string") return false;
    const clean = key.trim().toLowerCase();
    if (clean === "local" || clean === "000000000000") return true;
    if (clean.length < 8) return false;
    return /^[0-9a-f]+$/i.test(clean);
  }

  resolveCanonicalPubkey(pubkey) {
    if (!pubkey) return "";
    const clean = String(pubkey).trim().toLowerCase();
    if (clean === "local") return "local";

    for (const [k, node] of this.knownNodes.entries()) {
      const nodePk = String(node.public_key || k).toLowerCase();
      if (nodePk === clean) return nodePk;
      if (nodePk.length >= 8 && clean.length >= 8 && (nodePk.startsWith(clean) || clean.startsWith(nodePk))) {
        return nodePk;
      }
    }
    return clean;
  }

  async fetchNodes() {
    try {
      const res = await fetch("/api/nodes", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && Array.isArray(data.data)) {
        this.renderNodesDirectory(data.data);
      }
    } catch (e) {
      console.warn("Error cargando nodos:", e);
    }
  }

  formatLastSeen(lastSeen, isLocal = false) {
    if (isLocal) return "En línea (Host)";
    if (!lastSeen || lastSeen <= 0) return "Desconocido";
    const diff = Math.floor(Date.now() / 1000) - lastSeen;
    if (diff < 0 || diff < 60) return "Hace un momento";
    if (diff < 3600) return `Hace ${Math.floor(diff / 60)} min`;
    if (diff < 86400) return `Hace ${Math.floor(diff / 3600)} h`;
    return `Hace ${Math.floor(diff / 86400)} d`;
  }

  getPresenceState(lastSeen, isLocal = false) {
    if (isLocal) return "status-online";
    if (!lastSeen || lastSeen <= 0) return "status-offline";
    const diff = Math.floor(Date.now() / 1000) - lastSeen;
    if (diff < 900) return "status-online";
    if (diff < 3600) return "status-idle";
    return "status-offline";
  }

  renderNodesDirectory(nodes) {
    const contactsGrid = this.dom.contactsGridUi;
    const unifiedNodesGrid = this.dom.nodesUnifiedGridUi;

    if (!nodes || nodes.length === 0) {
      if (contactsGrid) contactsGrid.innerHTML = '<div class="empty-state">No hay contactos registrados en el dispositivo.</div>';
      if (unifiedNodesGrid) unifiedNodesGrid.innerHTML = '<div class="empty-state">No se han descubierto nodos en la malla LoRa.</div>';
      return;
    }

    const localPk = (document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();

    const deduplicatedNodes = [];
    for (const rawNode of nodes) {
      if (!rawNode || !this.isValidNodeKey(rawNode.public_key)) continue;
      const normPk = String(rawNode.public_key).toLowerCase().trim();

      const isThisLocal = Boolean(rawNode.is_local) ||
        (rawNode.role && String(rawNode.role).toUpperCase() === "LOCAL") ||
        normPk === "local" ||
        (localPk && (normPk === localPk || (localPk.length >= 8 && normPk.startsWith(localPk.slice(0, 8)))));

      const roleStr = (rawNode.role || "CLIENT").toUpperCase();
      const nodeNameUpper = String(rawNode.name || rawNode.alias || "").toUpperCase();

      const isRepeater = !isThisLocal && (
        roleStr === "REPEATER" || roleStr === "ROUTER" ||
        nodeNameUpper.startsWith("R-") || nodeNameUpper.startsWith("REP-") || nodeNameUpper.includes("REPEATER")
      );

      const effectiveRole = isThisLocal ? "LOCAL" : (isRepeater ? "REPEATER" : (rawNode.role || "CLIENT"));

      deduplicatedNodes.push({
        ...rawNode,
        is_local: isThisLocal,
        role: effectiveRole,
      });
    }

    this.knownNodes.clear();
    deduplicatedNodes.forEach((n) => {
      this.knownNodes.set(n.public_key.toLowerCase(), n);
    });

    if (this.ctx.knownNodes) {
      this.ctx.knownNodes = this.knownNodes;
    }

    // Actualizar contadores globales de la interfaz
    if (this.dom.headerNodeCount) {
      this.dom.headerNodeCount.textContent = String(deduplicatedNodes.length);
    }

    let cntRepeaters = 0;
    let cntSensors = 0;
    let cntRooms = 0;
    let cntClients = 0;

    let cntContacts = 0;
    let cntFavContacts = 0;
    let cntOnlineContacts = 0;
    let cntGpsContacts = 0;

    if (contactsGrid) contactsGrid.textContent = "";
    if (unifiedNodesGrid) unifiedNodesGrid.textContent = "";

    const contactsFrag = document.createDocumentFragment();
    const nodesFrag = document.createDocumentFragment();

    for (const node of deduplicatedNodes) {
      const isLocal = node.is_local;
      const isRepeater = node.role === "REPEATER";
      const isSensor = node.role === "SENSOR";
      const isRoom = node.role === "ROOM";
      const isClient = !isLocal && !isRepeater && !isSensor && !isRoom;

      if (isRepeater) cntRepeaters++;
      else if (isSensor) cntSensors++;
      else if (isRoom) cntRooms++;
      else if (isClient) cntClients++;

      const cleanName = node.name || node.alias || node.public_key.slice(0, 8);
      const presenceClass = this.getPresenceState(node.last_seen, isLocal);
      const isOnline = presenceClass === "status-online";
      const hasGps = node.latitude != null && node.longitude != null;
      const lastSeenText = this.formatLastSeen(node.last_seen, isLocal);

      // 1. Tarjetas para Contactos (Exclusivamente Clientes de Usuario)
      if (contactsGrid && !isLocal && !isRepeater && (node.role === "CLIENT" || isClient)) {
        cntContacts++;
        if (node.is_favorite) cntFavContacts++;
        if (isOnline) cntOnlineContacts++;
        if (hasGps) cntGpsContacts++;

        const cCard = document.createElement("div");
        cCard.className = `contact-card ${presenceClass === "status-offline" ? "contact-card-offline" : ""}`;
        cCard.setAttribute("data-pk", node.public_key);
        cCard.setAttribute("data-favorite", node.is_favorite ? "1" : "0");
        cCard.setAttribute("data-online", isOnline ? "1" : "0");
        cCard.setAttribute("data-has-gps", hasGps ? "1" : "0");

        const batText = node.battery_pct != null ? `${node.battery_pct}%` : (node.voltage_v != null ? `${node.voltage_v}V` : null);
        const snrVal = node.last_snr != null ? `${node.last_snr} dB` : "--";
        const rssiVal = node.last_rssi != null ? `${node.last_rssi} dBm` : "--";
        const hopsVal = node.hops != null ? (node.hops === 0 ? "Directo" : `${node.hops} saltos`) : "--";

        cCard.innerHTML = `
          <div class="contact-card-header">
            <div class="node-card-avatar-wrapper">
              <div class="contact-avatar font-mono">${escapeHtml(cleanName.slice(0, 2).toUpperCase())}</div>
              <span class="avatar-status-dot ${presenceClass}" title="${isOnline ? 'En línea' : 'Inactivo'}"></span>
            </div>
            <div class="contact-info">
              <div class="contact-title-row">
                <span class="contact-name font-mono" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</span>
                ${batText ? `<span class="contact-battery-chip" title="Batería: ${batText}">🔋 ${escapeHtml(batText)}</span>` : ""}
              </div>
              <div class="node-card-sub-row">
                <span class="node-card-activity font-mono">${escapeHtml(lastSeenText)}</span>
              </div>
            </div>
          </div>

          <div class="node-telemetry-panel">
            <div class="node-meta-row">
              <span>Clave: <code>${escapeHtml(node.public_key.slice(0, 8))}…</code></span>
              <span>${hasGps ? `📍 ${node.latitude.toFixed(3)}, ${node.longitude.toFixed(3)}` : `<span class="color-dim font-mono">Sin GPS</span>`}</span>
            </div>
            <div class="node-meta-sub">
              <span>Ruta: <strong>${escapeHtml(node.best_route || (node.hops === 0 ? "Directo" : "Malla"))}</strong></span>
              <span>LQI: <strong>${node.lqi_score ? `${Math.round(node.lqi_score)}%` : "--"}</strong></span>
            </div>
          </div>

          <div class="contact-card-chips">
            <div class="stat-pill" title="RSSI de última recepción">📡 <strong>${escapeHtml(rssiVal)}</strong></div>
            <div class="stat-pill" title="SNR de señal">📶 <strong>${escapeHtml(snrVal)}</strong></div>
            <div class="stat-pill" title="Saltos en la malla">🔀 <strong>${escapeHtml(hopsVal)}</strong></div>
          </div>

          <div class="contact-card-actions">
            <button type="button" class="btn-primary btn-sm btn-contact-dm" title="Abrir chat con este contacto">
              <span data-lucide="message-square" data-size="13"></span> Chat
            </button>
            <button type="button" class="btn-secondary btn-sm btn-contact-trace" title="Trazar ruta traceroute">
              <span data-lucide="git-commit" data-size="13"></span> Ruta
            </button>
            <button type="button" class="btn-outline btn-sm btn-contact-qr" title="Compartir QR del contacto">
              <span data-lucide="qr-code" data-size="13"></span>
            </button>
            <button type="button" class="btn-outline btn-sm btn-contact-del" title="Eliminar de contactos">
              <span data-lucide="trash-2" data-size="13"></span>
            </button>
          </div>
        `;

        cCard.querySelector(".btn-contact-dm")?.addEventListener("click", () => {
          if (this.ctx.openDmConversation) this.ctx.openDmConversation(node.public_key, cleanName);
        });

        cCard.querySelector(".btn-contact-trace")?.addEventListener("click", () => {
          if (this.ctx.openTracerouteModal) this.ctx.openTracerouteModal(node.public_key, cleanName);
        });

        cCard.querySelector(".btn-contact-qr")?.addEventListener("click", () => {
          const uri = `meshcore://contact?pubkey=${encodeURIComponent(node.public_key)}&name=${encodeURIComponent(cleanName)}`;
          const json = JSON.stringify({ type: "contact", pubkey: node.public_key, name: cleanName, role: node.role }, null, 2);
          if (window.showQrModal) window.showQrModal(`Contacto: ${cleanName}`, uri, json);
        });

        cCard.querySelector(".btn-contact-del")?.addEventListener("click", async () => {
          if (!confirm(`¿Eliminar al contacto "${cleanName}"?`)) return;
          try {
            await fetch(`/api/contacts/${encodeURIComponent(node.public_key)}`, {
              method: "DELETE",
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
            });
            cCard.remove();
            if (this.ctx.showToast) this.ctx.showToast("Contacto eliminado", "info");
          } catch (e) {
            console.warn("Fallo eliminando contacto:", e);
          }
        });

        contactsFrag.appendChild(cCard);
      }

      // 2. Tarjetas para Nodos Unificados (Todos los nodos descubiertos en la malla)
      if (unifiedNodesGrid) {
        const nCard = document.createElement("div");
        const roleUpper = isLocal ? "LOCAL" : (isRepeater ? "REPEATER" : (node.role || "CLIENT").toUpperCase());
        const roleClass = isLocal ? "role-local" : (isRepeater ? "role-repeater" : (isSensor ? "role-sensor" : (isRoom ? "role-room" : "role-client")));

        nCard.className = `node-card ${roleClass}-card ${presenceClass === "status-offline" ? "node-card-offline" : ""}`;
        nCard.setAttribute("data-pk", node.public_key);
        nCard.setAttribute("data-role", roleUpper);
        nCard.setAttribute("data-online", isOnline ? "1" : "0");
        nCard.setAttribute("data-has-gps", hasGps ? "1" : "0");

        const avatarIcon = isLocal ? "🏠" : (isRepeater ? "📡" : (isSensor ? "🌡️" : (isRoom ? "💬" : "👤")));
        const batText = isLocal ? "⚡ Host" : (node.battery_pct != null ? `${node.battery_pct}%` : (node.voltage_v != null ? `${node.voltage_v}V` : null));
        const snrVal = isLocal ? "Local" : (node.last_snr != null ? `${node.last_snr} dB` : "--");
        const rssiVal = isLocal ? "Local" : (node.last_rssi != null ? `${node.last_rssi} dBm` : "--");
        const hopsVal = isLocal ? "0 (Host)" : (node.hops != null ? (node.hops === 0 ? "Directo" : `${node.hops} saltos`) : "--");

        let telemLine2 = `Ruta: <strong>${escapeHtml(node.best_route || (node.hops === 0 ? "Directo" : "Malla"))}</strong>`;
        if (node.temperature_c != null) {
          telemLine2 = `🌡️ <strong>${node.temperature_c}°C</strong> ${node.humidity_pct != null ? `💧 ${node.humidity_pct}%` : ""}`;
        } else if (node.owner_name) {
          telemLine2 = `Dueño: <strong>${escapeHtml(node.owner_name)}</strong>`;
        }

        nCard.innerHTML = `
          <div class="node-card-header">
            <div class="node-card-avatar-wrapper">
              <div class="node-card-avatar avatar-${roleClass === "role-local" ? "local" : (roleClass === "role-repeater" ? "repeater" : (roleClass === "role-sensor" ? "sensor" : "client"))}">
                ${avatarIcon}
              </div>
              <span class="avatar-status-dot ${presenceClass}" title="${isOnline ? 'En línea' : 'Inactivo'}"></span>
            </div>
            <div class="node-card-info">
              <div class="node-card-top-row">
                <span class="node-card-name font-mono" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</span>
                <div class="node-card-badges-group">
                  ${batText ? `<span class="contact-battery-chip" title="Energía">${escapeHtml(batText)}</span>` : ""}
                  <span class="node-role-badge ${roleClass}">${escapeHtml(roleUpper)}</span>
                </div>
              </div>
              <div class="node-card-sub-row">
                <span class="node-card-activity font-mono">${escapeHtml(lastSeenText)}</span>
              </div>
            </div>
          </div>

          <div class="node-telemetry-panel">
            <div class="node-meta-row">
              <span>Clave: <code>${escapeHtml(node.public_key.slice(0, 8))}…</code></span>
              <span>${hasGps ? `📍 ${node.latitude.toFixed(3)}, ${node.longitude.toFixed(3)}` : `<span class="color-dim font-mono">Sin GPS</span>`}</span>
            </div>
            <div class="node-meta-sub">
              <span>${telemLine2}</span>
              <span>LQI: <strong>${node.lqi_score ? `${Math.round(node.lqi_score)}%` : "--"}</strong></span>
            </div>
          </div>

          <div class="node-rf-strip">
            <div class="stat-pill" title="RSSI recibido">📡 <strong>${escapeHtml(rssiVal)}</strong></div>
            <div class="stat-pill" title="SNR">📶 <strong>${escapeHtml(snrVal)}</strong></div>
            <div class="stat-pill" title="Saltos en la red">🔀 <strong>${escapeHtml(hopsVal)}</strong></div>
          </div>

          <div class="node-actions-bar">
            ${isRepeater ? `
              <button type="button" class="btn-primary btn-sm btn-manage-repeater" title="Administrar Repetidor Remoto">
                <span data-lucide="sliders" data-size="13"></span> Administrar
              </button>
            ` : ""}
            ${!isLocal && !isRepeater ? `
              <button type="button" class="btn-primary btn-sm btn-dm-node" title="Enviar Mensaje Directo">
                <span data-lucide="message-square" data-size="13"></span> Chat DM
              </button>
            ` : ""}
            ${isLocal ? `
              <button type="button" class="btn-secondary btn-sm btn-configure-local" title="Configurar Nodo Local">
                <span data-lucide="settings" data-size="13"></span> Ajustes
              </button>
            ` : ""}
            ${!isLocal ? `
              <button type="button" class="btn-secondary btn-sm btn-trace-node" title="Trazar ruta de red">
                <span data-lucide="git-commit" data-size="13"></span> Ruta
              </button>
            ` : ""}
            <button type="button" class="btn-outline btn-sm btn-node-qr" title="Compartir QR">
              <span data-lucide="qr-code" data-size="13"></span>
            </button>
          </div>
        `;

        if (isRepeater) {
          nCard.querySelector(".btn-manage-repeater")?.addEventListener("click", () => {
            if (this.ctx.openRepeaterAdminModal) this.ctx.openRepeaterAdminModal(node.public_key, cleanName);
          });
        }
        if (!isLocal && !isRepeater) {
          nCard.querySelector(".btn-dm-node")?.addEventListener("click", () => {
            if (this.ctx.openDmConversation) this.ctx.openDmConversation(node.public_key, cleanName);
          });
        }
        if (isLocal) {
          nCard.querySelector(".btn-configure-local")?.addEventListener("click", () => {
            const navBtn = document.querySelector('.nav-btn[data-tab="tab-settings"]');
            if (navBtn) navBtn.click();
          });
        }
        if (!isLocal) {
          nCard.querySelector(".btn-trace-node")?.addEventListener("click", () => {
            if (this.ctx.openTracerouteModal) this.ctx.openTracerouteModal(node.public_key, cleanName);
          });
        }
        nCard.querySelector(".btn-node-qr")?.addEventListener("click", () => {
          const uri = `meshcore://node?pubkey=${encodeURIComponent(node.public_key)}&name=${encodeURIComponent(cleanName)}`;
          const json = JSON.stringify({ type: "node", pubkey: node.public_key, name: cleanName, role: node.role }, null, 2);
          if (window.showQrModal) window.showQrModal(`Nodo: ${cleanName}`, uri, json);
        });

        nodesFrag.appendChild(nCard);
      }
    }

    // Actualizar contadores en badges de filtros de UI
    const cAll = document.getElementById("countAllNodes");
    const cRep = document.getElementById("countRepeaters");
    const cSen = document.getElementById("countSensors");
    const cRoo = document.getElementById("countRooms");
    const cCli = document.getElementById("countClients");
    if (cAll) cAll.textContent = String(deduplicatedNodes.length);
    if (cRep) cRep.textContent = String(cntRepeaters);
    if (cSen) cSen.textContent = String(cntSensors);
    if (cRoo) cRoo.textContent = String(cntRooms);
    if (cCli) cCli.textContent = String(cntClients);

    const cCAll = document.getElementById("countAllContacts");
    const cCFav = document.getElementById("countFavContacts");
    const cCOnl = document.getElementById("countOnlineContacts");
    const cCGps = document.getElementById("countGpsContacts");
    if (cCAll) cCAll.textContent = String(cntContacts);
    if (cCFav) cCFav.textContent = String(cntFavContacts);
    if (cCOnl) cCOnl.textContent = String(cntOnlineContacts);
    if (cCGps) cCGps.textContent = String(cntGpsContacts);

    if (contactsGrid) contactsGrid.appendChild(contactsFrag);
    if (unifiedNodesGrid) unifiedNodesGrid.appendChild(nodesFrag);

    if (window.initLucideIcons) {
      if (contactsGrid) window.initLucideIcons(contactsGrid);
      if (unifiedNodesGrid) window.initLucideIcons(unifiedNodesGrid);
    }

    // Re-aplicar filtros activos
    const qC = this.dom.contactsSearchInput ? this.dom.contactsSearchInput.value : "";
    this.filterContactsGrid(qC);

    const qN = this.dom.nodesSearchInput ? this.dom.nodesSearchInput.value : "";
    this.filterNodesGrid(qN);

    // Notificar al bus para actualizar mapa
    this.ctx.eventBus.emit(EVENTS.NODE_UPDATED, null);
  }

  updateNodePresenceRealtime(canonicalSender, payload) {
    if (!canonicalSender) return;
    const node = this.knownNodes.get(canonicalSender);
    if (node) {
      node.last_seen = Math.floor(Date.now() / 1000);
      if (payload.rssi != null) node.last_rssi = payload.rssi;
      if (payload.snr != null) node.last_snr = payload.snr;
    }
  }

  initPresenceTicker() {
    setInterval(() => {
      // Actualización visual periódica de estados en línea/inactivo
      const now = Math.floor(Date.now() / 1000);
      document.querySelectorAll(".node-card, .contact-card").forEach((card) => {
        const pk = card.getAttribute("data-pk");
        if (!pk) return;
        const node = this.knownNodes.get(pk.toLowerCase());
        if (!node) return;
        const dot = card.querySelector(".avatar-status-dot");
        const act = card.querySelector(".node-card-activity");
        if (dot) {
          const isLoc = node.is_local;
          const st = this.getPresenceState(node.last_seen, isLoc);
          dot.className = `avatar-status-dot ${st}`;
        }
        if (act) {
          act.textContent = this.formatLastSeen(node.last_seen, node.is_local);
        }
      });
    }, 30000);
  }

  initContactDiscovery() {
    this.fetchDiscoveredContacts();
  }

  async fetchDiscoveredContacts() {
    try {
      const res = await fetch("/api/contacts", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && Array.isArray(data.data)) {
        // Contactos guardados
      }
    } catch (_) {}
  }

  filterContactsGrid(query) {
    const q = (query || "").toLowerCase().trim();
    const filter = this.activeContactsFilter || "all";

    document.querySelectorAll("#contactsGridUi .contact-card").forEach((card) => {
      const text = card.textContent.toLowerCase();
      const matchText = !q || text.includes(q);

      let matchPill = true;
      if (filter === "favorites") {
        matchPill = card.getAttribute("data-favorite") === "1";
      } else if (filter === "online") {
        matchPill = card.getAttribute("data-online") === "1";
      } else if (filter === "gps") {
        matchPill = card.getAttribute("data-has-gps") === "1";
      }

      card.classList.toggle("hidden", !(matchText && matchPill));
    });
  }

  filterNodesGrid(query) {
    const q = (query || "").toLowerCase().trim();
    const roleFilter = (this.activeNodesFilter || "all").toUpperCase();

    document.querySelectorAll("#nodesUnifiedGridUi .node-card").forEach((card) => {
      const text = card.textContent.toLowerCase();
      const role = (card.getAttribute("data-role") || "ALL").toUpperCase();
      const matchRole = roleFilter === "ALL" || role === roleFilter || (roleFilter === "CLIENT" && role === "CLIENT");
      const matchText = !q || text.includes(q);
      card.classList.toggle("hidden", !(matchRole && matchText));
    });
  }

  initAnalytics() {
    this.fetchAnalytics();
  }

  async fetchAnalytics() {
    try {
      const res = await fetch("/api/analytics", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        // Renderizar analítica
      }
    } catch (_) {}
  }
}
