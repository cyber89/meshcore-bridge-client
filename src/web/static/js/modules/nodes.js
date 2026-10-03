/**
 * NodesModule - Directorio unificado de nodos, libreta de contactos (clientes),
 * filtrado reactivo, presencia en tiempo real y telemetría analítica.
 */

import { escapeHtml, debounce, buildMeshCoreContactUri, formatLastSeen, getPresenceState, calculateDistanceM, formatDistance, formatTimeAgo } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class NodesModule {
  constructor(context) {
    this.ctx = context;
    this.knownNodes = context.knownNodes || new Map();
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

  onLanguageChange() {
    this.renderNodesDirectory(Array.from(this.knownNodes.values()));
  }

  _bindElements() {
    this.dom = {
      contactsGridUi: document.getElementById("contactsGridUi"),
      nodesUnifiedGridUi: document.getElementById("nodesUnifiedGridUi"),
      contactsSearchInput: document.getElementById("contactsSearchInput"),
      nodesSearchInput: document.getElementById("nodesSearchInput"),
      headerNodeCount: document.getElementById("headerNodeCount"),
      btnRefreshContacts: document.getElementById("btnRefreshContacts"),
    };
  }

  _bindEvents() {
    if (this.dom.btnRefreshContacts) {
      this.dom.btnRefreshContacts.addEventListener("click", () => {
        this.fetchNodes();
        if (this.ctx.showToast) {
          this.ctx.showToast(I18n.t('contacts.refreshed'), "info");
        }
      });
    }

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

    const handlePayload = (payload) => {
      if (!payload || typeof payload !== "object") return;
      const evType = payload.type || payload.event_type;

      if (evType === "contacts_updated") {
        if (Array.isArray(payload.data)) {
          this.renderNodesDirectory(payload.data);
        } else {
          this.fetchNodes();
        }
        return;
      }

      if (evType === "contact_discovered" || evType === "contact_updated") {
        const c = payload.contact || payload.data;
        if (c && c.public_key && this.isValidNodeKey(c.public_key)) {
          const canonicalPk = this.resolveCanonicalPubkey(c.public_key) || c.public_key.toLowerCase().trim();
          const prev = this.knownNodes.get(canonicalPk) || {};
          const merged = { ...prev, ...c, public_key: canonicalPk };
          this.knownNodes.set(canonicalPk, merged);
          this.updateNodeInDom(canonicalPk, merged);
        } else {
          this.fetchNodes();
        }
        return;
      }

      // Actualizar presencia y métricas ante paquetes y eventos entrantes (RX)
      const isTx = payload.direction === "tx" || payload.is_rx === false || payload.status === "sent" || payload.type === "tx_sent";
      const isPresenceEvent = evType === "telemetry" || evType === "chat_msg" || evType === "channel_msg" ||
                              evType === "advert" || evType === "packet_rx" || evType === "ping_reply" ||
                              evType === "message_delivered" || evType === "rf_packet";

      if (!isTx && isPresenceEvent) {
        const sender = payload.sender || payload.from || payload.pubkey || (payload.contact && payload.contact.public_key);
        if (sender && this.isValidNodeKey(sender)) {
          const canonicalPk = this.resolveCanonicalPubkey(sender);
          if (canonicalPk && canonicalPk !== "local") {
            const existing = this.knownNodes.get(canonicalPk) || { public_key: canonicalPk, role: "CLIENT" };
            existing.last_seen = Math.floor(Date.now() / 1000);
            if (payload.rssi != null) existing.last_rssi = payload.rssi;
            if (payload.snr != null) existing.last_snr = payload.snr;
            if (payload.battery_pct != null) existing.battery_pct = payload.battery_pct;
            if (payload.voltage_v != null) existing.voltage_v = payload.voltage_v;
            if (payload.hops != null) existing.hops = payload.hops;
            if (payload.sender_name && !existing.name) existing.name = payload.sender_name;

            this.knownNodes.set(canonicalPk, existing);
            this.updateNodeInDom(canonicalPk, existing);
          }
        }
      }
    };

    this.ctx.eventBus.on(EVENTS.RX_PACKET, handlePayload);
    if (EVENTS.RF_PACKET) {
      this.ctx.eventBus.on(EVENTS.RF_PACKET, handlePayload);
    }
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

    // 1. Coincidencia exacta
    for (const [k, node] of this.knownNodes.entries()) {
      const nodePk = String(node.public_key || k).toLowerCase();
      if (nodePk === clean) return nodePk;
    }

    // 2. Coincidencias por prefijo
    const matches = [];
    for (const [k, node] of this.knownNodes.entries()) {
      const nodePk = String(node.public_key || k).toLowerCase();
      if (nodePk.length >= 8 && clean.length >= 8 && (nodePk.startsWith(clean) || clean.startsWith(nodePk))) {
        if (!matches.includes(nodePk)) {
          matches.push(nodePk);
        }
      }
    }

    if (matches.length === 1) {
      return matches[0];
    }

    return clean;
  }

  async fetchNodes() {
    try {
      const allNodes = [];
      let offset = 0;
      const limit = 100;
      let totalCount = Infinity;

      while (allNodes.length < totalCount) {
        const res = await fetch(`/api/nodes?limit=${limit}&offset=${offset}`, {
          headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
        });
        const data = await res.json();
        if (data.status === "ok" && Array.isArray(data.data)) {
          allNodes.push(...data.data);
          totalCount = typeof data.total_count === "number" ? data.total_count : data.data.length;
          if (data.data.length < limit || allNodes.length >= totalCount) {
            break;
          }
          offset += data.data.length;
        } else {
          break;
        }
      }

      if (allNodes.length > 0) {
        this.renderNodesDirectory(allNodes);
      }
    } catch (e) {
      console.warn("Error cargando nodos:", e);
    }
  }

  _getLocalCoordinates() {
    for (const n of this.knownNodes.values()) {
      if (n.is_local || n.public_key === "local") {
        const lat = n.latitude ?? n.lat ?? n.adv_lat ?? n.gps?.latitude;
        const lon = n.longitude ?? n.lon ?? n.adv_lon ?? n.gps?.longitude;
        if (lat != null && lon != null) {
          const fLat = parseFloat(lat);
          const fLon = parseFloat(lon);
          if (!isNaN(fLat) && !isNaN(fLon) && (fLat !== 0 || fLon !== 0 || n.position_valid)) {
            return { lat: fLat, lon: fLon };
          }
        }
      }
    }
    return null;
  }

  _renderTelemetryMetricsHtml(node, isLocal) {
    // 1. Distance away
    let distHtml = "";
    if (isLocal) {
      distHtml = `<span class="node-metric-tag">${escapeHtml(I18n.t('nodes.dist_local'))}</span>`;
    } else if (node.distance_m != null) {
      distHtml = `<strong>${escapeHtml(formatDistance(node.distance_m))}</strong>`;
    } else {
      const rawLat = node.latitude ?? node.lat ?? node.adv_lat ?? node.gps?.latitude;
      const rawLon = node.longitude ?? node.lon ?? node.adv_lon ?? node.gps?.longitude;
      const fLat = rawLat != null ? parseFloat(rawLat) : NaN;
      const fLon = rawLon != null ? parseFloat(rawLon) : NaN;
      const hasNodeGps = !isNaN(fLat) && !isNaN(fLon) && (fLat !== 0 || fLon !== 0 || node.position_valid);

      if (!hasNodeGps) {
        distHtml = `<span class="color-dim">${escapeHtml(I18n.t('nodes.dist_no_remote_gps'))}</span>`;
      } else {
        const localCoords = this._getLocalCoordinates();
        if (localCoords) {
          const d = calculateDistanceM(localCoords.lat, localCoords.lon, fLat, fLon);
          distHtml = d != null ? `<strong>${escapeHtml(formatDistance(d))}</strong>` : `<span class="color-dim">--</span>`;
        } else {
          distHtml = `<span class="color-dim">${escapeHtml(I18n.t('nodes.dist_no_local_gps'))}</span>`;
        }
      }
    }

    // 2. Last Advert Heard
    let advertHeardHtml = "";
    if (isLocal) {
      advertHeardHtml = `<span class="node-metric-tag">${escapeHtml(I18n.t('nodes.advert_heard_local'))}</span>`;
    } else if (node.last_advert_heard_at != null && node.last_advert_heard_at > 0) {
      const timeAgo = formatTimeAgo(node.last_advert_heard_at);
      const fullDate = new Date(node.last_advert_heard_at * 1000).toLocaleString();
      advertHeardHtml = `<span title="${escapeHtml(fullDate)}">${escapeHtml(timeAgo)}</span> <span class="node-metric-tag">${escapeHtml(I18n.t('nodes.advert_verified_badge'))}</span>`;
    } else {
      advertHeardHtml = `<span class="color-dim">--</span> <span class="node-metric-tag">${escapeHtml(I18n.t('nodes.advert_heard_never'))}</span>`;
    }

    // 3. Inbound Path (RX)
    let rxPathHtml = "";
    let rxHashesStr = "";
    let rxRouteType = "--";
    let rxHashWidth = "--";
    let rxReceivedAt = "--";
    let rxTrust = "--";

    if (isLocal) {
      rxPathHtml = `<span class="node-metric-tag">${escapeHtml(I18n.t('nodes.not_applicable'))}</span>`;
    } else if (node.last_rx_route && Array.isArray(node.last_rx_route.hashes) && node.last_rx_route.hashes.length > 0) {
      rxHashesStr = node.last_rx_route.hashes.join(" → ");
      const chips = node.last_rx_route.hashes.slice(0, 3).map(h => `<span class="route-hash-chip">${escapeHtml(h)}</span>`).join('<span class="route-flow-arrow">→</span>');
      const more = node.last_rx_route.hashes.length > 3 ? ` <span class="color-dim">+${node.last_rx_route.hashes.length - 3}</span>` : "";
      const widthTag = node.last_rx_route.hash_size_bytes ? ` <span class="node-metric-tag">${node.last_rx_route.hash_size_bytes}B/hash</span>` : "";
      rxPathHtml = `<div class="route-flow">${chips}${more}</div>${widthTag}`;
      rxRouteType = node.last_rx_route.route_type || "FLOOD";
      rxHashWidth = node.last_rx_route.hash_size_bytes ? `${node.last_rx_route.hash_size_bytes}B (${node.last_rx_route.hash_size_bytes * 8} bits)` : "--";
      rxReceivedAt = node.last_rx_route.received_at ? new Date(node.last_rx_route.received_at * 1000).toLocaleString() : "--";
      rxTrust = node.last_rx_route.identity_trust === "verified" ? I18n.t('nodes.route_trust_verified') : I18n.t('nodes.route_trust_unverified');
    } else if (node.last_rx_route && node.last_rx_route.count === 0) {
      rxPathHtml = `<span>${escapeHtml(I18n.t('nodes.rx_path_direct'))}</span>`;
      rxRouteType = "DIRECT";
    } else {
      rxPathHtml = `<span class="color-dim">--</span> <span class="node-metric-tag">${escapeHtml(I18n.t('nodes.rx_path_none'))}</span>`;
    }

    // 4. Hops Away
    let hopsHtml = "";
    if (isLocal) {
      hopsHtml = `<strong>0</strong> <span class="node-metric-tag">${escapeHtml(I18n.t('nodes.hops_source_local'))}</span>`;
    } else if (node.hops !== null && node.hops !== undefined) {
      let sourceTag = "";
      if (node.hops_source === "rx_flood") sourceTag = I18n.t('nodes.hops_source_rx_flood');
      else if (node.hops_source === "rx_direct") sourceTag = I18n.t('nodes.hops_source_rx_direct');
      else if (node.hops_source === "out_path") sourceTag = I18n.t('nodes.hops_source_out_path');
      else if (node.hops_source === "trace") sourceTag = I18n.t('nodes.hops_source_trace');
      else if (node.hops === 0) sourceTag = I18n.t('nodes.route_direct');

      hopsHtml = `<strong>${node.hops}</strong> ${sourceTag ? `<span class="node-metric-tag">${escapeHtml(sourceTag)}</span>` : ""}`;
    } else {
      hopsHtml = `<span class="color-dim">--</span> <span class="node-metric-tag">${escapeHtml(I18n.t('nodes.hops_unknown'))}</span>`;
    }

    // 5. Out Path
    let outPathHtml = "";
    let txHashesStr = "";
    let txState = node.out_route_state || (node.out_path && node.out_path.length > 0 ? "known" : "unknown");
    let txHashWidth = "--";

    if (isLocal) {
      outPathHtml = `<span class="node-metric-tag">${escapeHtml(I18n.t('nodes.not_applicable'))}</span>`;
    } else if (node.out_path && Array.isArray(node.out_path) && node.out_path.length > 0) {
      txHashesStr = node.out_path.join(" → ");
      const chips = node.out_path.slice(0, 3).map(h => `<span class="route-hash-chip">${escapeHtml(h)}</span>`).join('<span class="route-flow-arrow">→</span>');
      const more = node.out_path.length > 3 ? ` <span class="color-dim">+${node.out_path.length - 3}</span>` : "";
      const hopCountStr = `${node.out_path.length} ${node.out_path.length === 1 ? I18n.t('nodes.hops.one') : I18n.t('nodes.hops')}`;
      outPathHtml = `<div class="route-flow">${chips}${more}</div> <span class="node-metric-tag">${escapeHtml(hopCountStr)}</span>`;
    } else if (txState === "direct") {
      outPathHtml = `<span>${escapeHtml(I18n.t('nodes.out_path_direct'))}</span>`;
    } else if (txState === "flood") {
      outPathHtml = `<span>${escapeHtml(I18n.t('nodes.out_path_flood'))}</span>`;
    } else {
      outPathHtml = `<span class="color-dim">--</span> <span class="node-metric-tag">${escapeHtml(I18n.t('nodes.out_path_none'))}</span>`;
    }

    // 6. Out Path Hash Size
    let hashSizeHtml = "";
    const hashBytes = node.out_path_hash_size_bytes ?? (node.out_path_hash_mode != null ? (Number(node.out_path_hash_mode) + 1) : null);
    if (isLocal) {
      hashSizeHtml = `<span class="node-metric-tag">${escapeHtml(I18n.t('nodes.not_applicable'))}</span>`;
    } else if (hashBytes != null && hashBytes >= 1 && hashBytes <= 3) {
      const bits = hashBytes * 8;
      const str = I18n.t('nodes.hash_size_val', { bytes: hashBytes, bits });
      hashSizeHtml = `<span>${escapeHtml(str)}</span>`;
      txHashWidth = `${hashBytes}B (${bits} bits)`;
    } else {
      hashSizeHtml = `<span class="color-dim">--</span> <span class="node-metric-tag">${escapeHtml(I18n.t('nodes.hash_size_none'))}</span>`;
    }

    const metricsDl = `
      <dl class="node-telemetry-metrics">
        <div class="node-metric-item">
          <dt>${I18n.t('nodes.distance_label')}</dt>
          <dd class="metric-distance-val">${distHtml}</dd>
        </div>
        <div class="node-metric-item">
          <dt>${I18n.t('nodes.last_advert_heard_label')}</dt>
          <dd class="metric-advert-heard-val">${advertHeardHtml}</dd>
        </div>
        <div class="node-metric-item">
          <dt>${I18n.t('nodes.rx_path_label')}</dt>
          <dd class="metric-rx-path-val">${rxPathHtml}</dd>
        </div>
        <div class="node-metric-item">
          <dt>${I18n.t('nodes.hops_label')}</dt>
          <dd class="metric-hops-val">${hopsHtml}</dd>
        </div>
        <div class="node-metric-item">
          <dt>${I18n.t('nodes.out_path_label')}</dt>
          <dd class="metric-out-path-val">${outPathHtml}</dd>
        </div>
        <div class="node-metric-item">
          <dt>${I18n.t('nodes.out_hash_size_label')}</dt>
          <dd class="metric-out-hash-val">${hashSizeHtml}</dd>
        </div>
      </dl>
    `;

    if (isLocal) {
      return metricsDl;
    }

    const accordion = `
      <details class="node-route-accordion">
        <summary class="route-accordion-summary">
          <span data-lucide="route" data-size="12"></span>
          <span>${I18n.t('nodes.route_details_btn')}</span>
        </summary>
        <div class="route-accordion-content">
          <div class="route-section">
            <div class="route-section-title">
              <span>${I18n.t('nodes.route_rx_title')}</span>
              ${rxHashesStr ? `
                <button type="button" class="btn-copy-hashes" data-hashes="${escapeHtml(rxHashesStr)}" title="${I18n.t('nodes.copy_hashes')}">
                  <span data-lucide="copy" data-size="11"></span>
                </button>
              ` : ''}
            </div>
            ${rxHashesStr ? `<div class="route-full-hashes-box">${escapeHtml(rxHashesStr)}</div>` : ''}
            <div class="route-details-grid">
              <span>${I18n.t('nodes.route_type_label')} <strong>${escapeHtml(rxRouteType)}</strong></span>
              <span>${I18n.t('nodes.hash_width_label')} <strong>${escapeHtml(rxHashWidth)}</strong></span>
              <span>${I18n.t('nodes.route_received_label')} <strong>${escapeHtml(rxReceivedAt)}</strong></span>
              <span>${I18n.t('nodes.route_trust_label')} <strong>${escapeHtml(rxTrust)}</strong></span>
            </div>
          </div>
          <div class="route-section">
            <div class="route-section-title">
              <span>${I18n.t('nodes.route_tx_title')}</span>
              ${txHashesStr ? `
                <button type="button" class="btn-copy-hashes" data-hashes="${escapeHtml(txHashesStr)}" title="${I18n.t('nodes.copy_hashes')}">
                  <span data-lucide="copy" data-size="11"></span>
                </button>
              ` : ''}
            </div>
            ${txHashesStr ? `<div class="route-full-hashes-box">${escapeHtml(txHashesStr)}</div>` : ''}
            <div class="route-details-grid">
              <span>${I18n.t('nodes.route_state_label')} <strong>${escapeHtml(txState)}</strong></span>
              <span>${I18n.t('nodes.hash_width_label')} <strong>${escapeHtml(txHashWidth)}</strong></span>
            </div>
          </div>
        </div>
      </details>
    `;

    return metricsDl + accordion;
  }





  /**
   * Generador unificado de tarjetas para contactos y nodos de la red.
   * Elimina duplicación de marcado y eventos entre las vistas de libreta y malla.
   * @param {Object} node Objeto de información de nodo.
   * @param {"contact"|"node"} mode Modo de renderizado: "contact" (libreta) o "node" (malla).
   * @returns {HTMLElement} Elemento DOM de la tarjeta configurado con listeners.
   */
  createNodeCard(node, mode = "node") {
    const isContact = mode === "contact";
    const isLocal = Boolean(node.is_local);
    const isRepeater = node.role === "REPEATER" || node.role === "ROUTER";
    const isSensor = node.role === "SENSOR";
    const isRoom = node.role === "ROOM";
    const cleanName = node.name || node.alias || node.public_key.slice(0, 8);
    const presenceClass = getPresenceState(node.last_seen, isLocal);
    const isOnline = presenceClass === "status-online";
    const isDisconnected = !isLocal && (presenceClass === "status-offline" || node.presence_status === "offline");
    const rawLat = node.latitude ?? node.lat ?? node.adv_lat ?? node.gps?.latitude;
    const rawLon = node.longitude ?? node.lon ?? node.adv_lon ?? node.gps?.longitude;
    const fLat = rawLat != null ? parseFloat(rawLat) : NaN;
    const fLon = rawLon != null ? parseFloat(rawLon) : NaN;
    const hasGps = !isNaN(fLat) && !isNaN(fLon) && (fLat !== 0 || fLon !== 0);
    const lastSeenText = formatLastSeen(node.last_seen, isLocal);
    const fullDateTime = node.last_seen_formatted || (node.last_seen && node.last_seen > 0 ? new Date(node.last_seen * 1000).toLocaleString() : (window.I18n ? window.I18n.t('time.no_signal') : "Sin señal registrada"));
    const signalTooltip = isLocal ? I18n.t("nodes.local_signal") : (window.I18n ? window.I18n.t('time.last_signal_tooltip').replace('{time}', fullDateTime) : `Última señal recibida: ${fullDateTime}`);

    const roleUpper = isLocal ? "LOCAL" : (isRepeater ? "REPEATER" : (isSensor ? "SENSOR" : (isRoom ? "ROOM" : "CLIENT")));
    const roleClass = isLocal ? "role-local" : (isRepeater ? "role-repeater" : (isSensor ? "role-sensor" : (isRoom ? "role-room" : "role-client")));

    const batText = isLocal ? null : (node.battery_pct != null ? `${node.battery_pct}%` : (node.voltage_v != null ? `${node.voltage_v}V` : null));
    const snrVal = isLocal ? null : (node.last_snr != null ? `${node.last_snr} dB` : "--");
    const rssiVal = isLocal ? null : (node.last_rssi != null ? `${node.last_rssi} dBm` : "--");
    const lqiVal = isLocal ? null : (node.lqi_score ? `${Math.round(node.lqi_score)}%` : (node.last_rssi != null ? "50%" : "--"));
    const hopsVal = isLocal ? null : (node.hops != null ? (node.hops === 0 ? I18n.t('nodes.route_direct') : `${node.hops} ${I18n.t('nodes.hops', { count: node.hops })}`) : "--");

    const card = document.createElement("div");
    card.setAttribute("data-pk", node.public_key);
    card.setAttribute("data-online", isOnline ? "1" : "0");
    card.setAttribute("data-has-gps", hasGps ? "1" : "0");

    if (isContact) {
      card.className = `contact-card ${isDisconnected ? "contact-card-offline" : ""}`;
      card.setAttribute("data-favorite", node.is_favorite ? "1" : "0");

      card.innerHTML = `
        <div class="contact-card-header">
          <div class="node-card-avatar-wrapper">
            <div class="contact-avatar font-mono">${escapeHtml(cleanName.slice(0, 2).toUpperCase())}</div>
            <span class="avatar-status-dot ${presenceClass}" title="${escapeHtml(signalTooltip)}"></span>
          </div>
          <div class="contact-info">
            <div class="contact-title-row">
              <span class="contact-name font-mono" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</span>
              ${batText ? `<span class="contact-battery-chip" title="${escapeHtml(I18n.t('nodes.battery_title').replace('{val}', batText))}">🔋 ${escapeHtml(batText)}</span>` : ""}
              <button type="button" class="btn-toggle-fav ${node.is_favorite ? "is-fav" : ""}" title="${node.is_favorite ? I18n.t('nodes.remove_fav') : I18n.t('nodes.add_fav')}" aria-label="${I18n.t('nodes.favorite')}">
                <span data-lucide="star" data-size="14"></span>
              </button>
            </div>
            <div class="node-card-sub-row">
              <span class="node-card-activity font-mono" title="${escapeHtml(signalTooltip)}">${escapeHtml(lastSeenText)}</span>
            </div>
          </div>
        </div>

        <div class="node-telemetry-panel">
          <div class="node-meta-row">
            <span>${I18n.t('nodes.key_label')} <code>${escapeHtml(node.public_key.slice(0, 8))}…</code></span>
            <span>${hasGps ? `📍 ${fLat.toFixed(3)}, ${fLon.toFixed(3)}` : `<span class="color-dim font-mono">${I18n.t('common.no_gps')}</span>`}</span>
          </div>
          <div class="node-meta-sub">
            <span>${I18n.t('nodes.route_label')} <strong>${escapeHtml(node.best_route || (node.hops === 0 ? I18n.t('nodes.route_direct') : I18n.t('nodes.route_mesh')))}</strong></span>
            <span>${I18n.t('nodes.lqi_label')} <strong>${escapeHtml(lqiVal)}</strong></span>
          </div>
        </div>

        <div class="contact-card-chips">
          <div class="stat-pill" title="${I18n.t('nodes.tooltip_rssi')}">📡 <strong>${escapeHtml(rssiVal)}</strong></div>
          <div class="stat-pill" title="${I18n.t('nodes.tooltip_snr')}">📶 <strong>${escapeHtml(snrVal)}</strong></div>
          <div class="stat-pill" title="${I18n.t('nodes.tooltip_hops')}">🔀 <strong>${escapeHtml(hopsVal)}</strong></div>
        </div>

        <div class="contact-card-actions">
          <button type="button" class="btn-primary btn-sm btn-contact-dm" title="${I18n.t('contacts.title_chat')}">
            <span data-lucide="message-square" data-size="13"></span>${I18n.t('nodes.chat_btn')}
          </button>
          <button type="button" class="btn-secondary btn-sm btn-contact-trace" title="${I18n.t('contacts.title_trace')}">
            <span data-lucide="git-commit" data-size="13"></span>${I18n.t('nodes.trace_btn')}
          </button>
          <button type="button" class="btn-outline btn-sm btn-contact-qr" title="${I18n.t('contacts.title_qr')}">
            <span data-lucide="qr-code" data-size="13"></span>
          </button>
          <button type="button" class="btn-outline btn-sm btn-contact-del" title="${I18n.t('contacts.title_del')}">
            <span data-lucide="trash-2" data-size="13"></span>
          </button>
        </div>
      `;

      // Eventos para tarjeta de contacto
      const favBtn = card.querySelector(".btn-toggle-fav");
      if (favBtn) {
        favBtn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const newFav = !node.is_favorite;
          node.is_favorite = newFav;
          card.setAttribute("data-favorite", newFav ? "1" : "0");
          favBtn.classList.toggle("is-fav", newFav);
          favBtn.title = newFav ? I18n.t('nodes.remove_fav') : I18n.t('nodes.add_fav');

          const known = this.knownNodes.get(node.public_key.toLowerCase());
          if (known) known.is_favorite = newFav;

          let favCount = 0;
          document.querySelectorAll("#contactsGridUi .contact-card").forEach((c) => {
            if (c.getAttribute("data-favorite") === "1") favCount++;
          });
          const cCFav = document.getElementById("countFavContacts");
          if (cCFav) cCFav.textContent = String(favCount);

          const q = this.dom.contactsSearchInput ? this.dom.contactsSearchInput.value : "";
          this.filterContactsGrid(q);

          if (this.ctx.showToast) {
            this.ctx.showToast(newFav ? I18n.t('toast.fav_added').replace('{name}', cleanName) : I18n.t('toast.fav_removed').replace('{name}', cleanName), "info");
          }

          try {
            await fetch("/api/contacts", {
              method: "POST",
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({
                public_key: node.public_key,
                name: cleanName,
                alias: node.alias || "",
                role: node.role || "CLIENT",
                is_favorite: newFav,
              }),
            });
          } catch (err) {
            console.warn("Error guardando estado de favorito:", err);
          }
        });
      }

      card.querySelector(".btn-contact-dm")?.addEventListener("click", () => {
        if (this.ctx.openDmConversation) this.ctx.openDmConversation(node.public_key, cleanName);
      });

      card.querySelector(".btn-contact-trace")?.addEventListener("click", () => {
        if (this.ctx.openTracerouteModal) this.ctx.openTracerouteModal(node.public_key, cleanName);
      });

      card.querySelector(".btn-contact-qr")?.addEventListener("click", () => {
        const uri = buildMeshCoreContactUri(cleanName, node.public_key, node.role || "CLIENT");
        const json = JSON.stringify({ type: "contact", public_key: node.public_key, name: cleanName, role: node.role || "CLIENT", uri }, null, 2);
        if (window.showQrModal) window.showQrModal('', uri, json, { key: 'nodes.qr_contact_title', params: { name: cleanName } });
      });

      card.querySelector(".btn-contact-del")?.addEventListener("click", async () => {
        if (!confirm(I18n.t('nodes.del_confirm').replace('{name}', cleanName))) return;
        try {
          const res = await fetch(`/api/contacts/${encodeURIComponent(node.public_key)}`, {
            method: "DELETE",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ public_key: node.public_key }),
          });
          if (!res.ok) {
            const errData = await res.json().catch(() => ({}));
            const msg = errData.detail || errData.error || `HTTP ${res.status}`;
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('app.error', { error: msg }), "error");
            return;
          }
          card.remove();
          this.knownNodes.delete(node.public_key.toLowerCase());
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.contact_deleted'), "info");
        } catch (e) {
          console.warn("Fallo eliminando contacto:", e);
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.network_error') || "Error de red", "error");
        }
      });

    } else {
      // Modo Node (Malla Unificada)
      card.className = `node-card ${roleClass}-card ${isDisconnected ? "node-card-offline" : ""}`;
      card.setAttribute("data-role", roleUpper);

      const avatarIcon = isLocal ? "🏠" : (isRepeater ? "📡" : (isSensor ? "🌡️" : (isRoom ? "💬" : "👤")));

      let telemLine2 = `${I18n.t('nodes.route_label')} <strong>${escapeHtml(node.best_route || (node.hops === 0 ? I18n.t('nodes.route_direct') : I18n.t('nodes.route_mesh')))}</strong>`;
      if (isLocal) {
        telemLine2 = `🖥️ <strong>${I18n.t("nodes.usb_host")}</strong>`;
      } else if (node.temperature_c != null) {
        telemLine2 = `🌡️ <strong>${escapeHtml(String(node.temperature_c))}°C</strong> ${node.humidity_pct != null ? `💧 ${escapeHtml(String(node.humidity_pct))}%` : ""}`;
      } else if (node.owner_name) {
        telemLine2 = `${I18n.t('nodes.owner_label')} <strong>${escapeHtml(node.owner_name)}</strong>`;
      }

      card.innerHTML = `
        <div class="node-card-header">
          <div class="node-card-avatar-wrapper">
            <div class="node-card-avatar avatar-${roleClass === "role-local" ? "local" : (roleClass === "role-repeater" ? "repeater" : (roleClass === "role-sensor" ? "sensor" : "client"))}">
              ${avatarIcon}
            </div>
            <span class="avatar-status-dot ${presenceClass}" title="${escapeHtml(signalTooltip)}"></span>
          </div>
          <div class="node-card-info">
            <div class="node-card-top-row">
              <span class="node-card-name font-mono" title="${escapeHtml(cleanName)}">${escapeHtml(cleanName)}</span>
              <div class="node-card-badges-group">
                ${batText ? `<span class="contact-battery-chip" title="${escapeHtml(I18n.t('nodes.battery_title').replace('{val}', batText))}">🔋 ${escapeHtml(batText)}</span>` : ""}
                <span class="node-role-badge ${roleClass}">${escapeHtml(I18n.role(roleUpper))}</span>
              </div>
            </div>
            <div class="node-card-sub-row">
              <span class="node-card-activity font-mono" title="${escapeHtml(signalTooltip)}">${escapeHtml(lastSeenText)}</span>
            </div>
          </div>
        </div>

        <div class="node-telemetry-panel">
          <div class="node-meta-row">
            <span>${I18n.t('nodes.key_label')} <code>${escapeHtml(node.public_key.slice(0, 8))}…</code></span>
            <span>${hasGps ? `📍 ${fLat.toFixed(3)}, ${fLon.toFixed(3)}` : `<span class="color-dim font-mono">${I18n.t('common.no_gps')}</span>`}</span>
          </div>
          <div class="node-meta-sub">
            <span>${telemLine2}</span>
            ${isLocal ? `<span>⚡ <strong>5V USB</strong></span>` : `<span>${I18n.t('nodes.lqi_label')} <strong>${escapeHtml(lqiVal)}</strong></span>`}
          </div>
        </div>

        ${isLocal ? "" : `
        <div class="node-rf-strip">
          <div class="stat-pill" title="${I18n.t('nodes.tooltip_rssi')}">📡 <strong>${escapeHtml(rssiVal)}</strong></div>
          <div class="stat-pill" title="${I18n.t('nodes.tooltip_snr')}">📶 <strong>${escapeHtml(snrVal)}</strong></div>
          <div class="stat-pill" title="${I18n.t('nodes.tooltip_hops')}">🔀 <strong>${escapeHtml(hopsVal)}</strong></div>
        </div>
        `}

        ${this._renderTelemetryMetricsHtml(node, isLocal)}

        <div class="node-actions-bar">
          ${isRepeater ? `
            <button type="button" class="btn-primary btn-sm btn-manage-repeater" title="${I18n.t('nodes.title_manage')}">
              <span data-lucide="sliders" data-size="13"></span>${I18n.t('nodes.manage_btn')}
            </button>
          ` : ""}
          ${!isLocal && !isRepeater ? `
            <button type="button" class="btn-primary btn-sm btn-dm-node" title="${I18n.t('nodes.title_dm')}">
              <span data-lucide="message-square" data-size="13"></span>${I18n.t('nodes.chat_btn')} DM
            </button>
          ` : ""}
          ${!isLocal && isRepeater ? `
            <button type="button" class="btn-secondary btn-sm btn-ping-node" title="${I18n.t('nodes.ping_title') || 'Ping directo de 0 saltos'}">
              <span data-lucide="crosshair" data-size="13"></span> ${I18n.t('nodes.ping_btn') || 'Ping'}
            </button>
          ` : ""}
          ${isLocal ? `
            <button type="button" class="btn-secondary btn-sm btn-configure-local" title="${I18n.t('nodes.title_settings')}">
              <span data-lucide="settings" data-size="13"></span>${I18n.t('nodes.settings_btn')}
            </button>
          ` : ""}
          ${!isLocal ? `
            <button type="button" class="btn-secondary btn-sm btn-trace-node" title="${I18n.t('nodes.title_trace')}">
              <span data-lucide="git-commit" data-size="13"></span>${I18n.t('nodes.trace_btn')}
            </button>
          ` : ""}
          <button type="button" class="btn-outline btn-sm btn-node-qr" title="${I18n.t('nodes.title_qr')}">
            <span data-lucide="qr-code" data-size="13"></span>
          </button>
        </div>
      `;

      card.querySelectorAll(".btn-copy-hashes").forEach((btn) => {
        btn.addEventListener("click", async (e) => {
          e.stopPropagation();
          const hashes = btn.getAttribute("data-hashes");
          if (hashes) {
            try {
              await navigator.clipboard.writeText(hashes);
              if (this.ctx.showToast) {
                this.ctx.showToast(I18n.t('nodes.hashes_copied'), "info");
              }
            } catch (_) {}
          }
        });
      });

      if (isRepeater) {
        card.querySelector(".btn-manage-repeater")?.addEventListener("click", () => {
          if (this.ctx.openRepeaterAdminModal) this.ctx.openRepeaterAdminModal(node.public_key, cleanName);
        });
      }
      if (!isLocal && !isRepeater) {
        card.querySelector(".btn-dm-node")?.addEventListener("click", () => {
          if (this.ctx.openDmConversation) this.ctx.openDmConversation(node.public_key, cleanName);
        });
      }
      if (isLocal) {
        card.querySelector(".btn-configure-local")?.addEventListener("click", () => {
          const navBtn = document.querySelector('.nav-btn[data-tab="tab-settings"]');
          if (navBtn) navBtn.click();
        });
      }
      if (!isLocal && isRepeater) {
        card.querySelector(".btn-ping-node")?.addEventListener("click", (e) => {
          this.pingNode(node.public_key, cleanName, e.currentTarget);
        });
      }
      if (!isLocal) {
        card.querySelector(".btn-trace-node")?.addEventListener("click", () => {
          if (this.ctx.openTracerouteModal) this.ctx.openTracerouteModal(node.public_key, cleanName);
        });
      }
      card.querySelector(".btn-node-qr")?.addEventListener("click", () => {
        const uri = buildMeshCoreContactUri(cleanName, node.public_key, node.role || "CLIENT");
        const json = JSON.stringify({ type: "node", public_key: node.public_key, name: cleanName, role: node.role || "CLIENT", uri }, null, 2);
        if (window.showQrModal) window.showQrModal('', uri, json, { key: 'nodes.qr_node_title', params: { name: cleanName } });
      });
    }

    return card;
  }

  renderNodesDirectory(nodes = Array.from(this.knownNodes.values())) {
    const contactsGrid = this.dom.contactsGridUi;
    const unifiedNodesGrid = this.dom.nodesUnifiedGridUi;

    if (!nodes || nodes.length === 0) {
      this.knownNodes.clear();
      if (contactsGrid) contactsGrid.innerHTML = `<div class="empty-state">${I18n.t('nodes.no_contacts')}</div>`;
      if (unifiedNodesGrid) unifiedNodesGrid.innerHTML = `<div class="empty-state">${I18n.t('nodes.no_nodes')}</div>`;
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
      const isRepeater = !isThisLocal && (
        roleStr === "REPEATER" || roleStr === "ROUTER"
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

      // 1. Tarjetas para Contactos (Exclusivamente Clientes de Usuario)
      if (contactsGrid && !isLocal && !isRepeater && (node.role === "CLIENT" || isClient)) {
        cntContacts++;
        if (node.is_favorite) cntFavContacts++;
        const cRawLat = node.latitude ?? node.lat ?? node.adv_lat ?? node.gps?.latitude;
        const cRawLon = node.longitude ?? node.lon ?? node.adv_lon ?? node.gps?.longitude;
        const cfLat = cRawLat != null ? parseFloat(cRawLat) : NaN;
        const cfLon = cRawLon != null ? parseFloat(cRawLon) : NaN;
        if (!isNaN(cfLat) && !isNaN(cfLon) && (cfLat !== 0 || cfLon !== 0)) cntGpsContacts++;

        const cCard = this.createNodeCard(node, "contact");
        contactsFrag.appendChild(cCard);
      }

      // 2. Tarjetas para Nodos Unificados (Todos los nodos descubiertos en la malla)
      if (unifiedNodesGrid) {
        const nCard = this.createNodeCard(node, "node");
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

    // Notificar al bus para actualizar mapa con la lista completa de nodos
    this.ctx.eventBus.emit(EVENTS.NODE_UPDATED, deduplicatedNodes);
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
    if (this._presenceInterval) clearInterval(this._presenceInterval);
    this._presenceInterval = setInterval(() => {
      if (document.hidden) return; // Ahorro de CPU: no actualizar DOM si la pestaña está en segundo plano u oculta
      // Actualización visual periódica de estados en línea/inactivo/desconectado
      document.querySelectorAll(".node-card, .contact-card").forEach((card) => {
        const pk = card.getAttribute("data-pk");
        if (!pk) return;
        const node = this.knownNodes.get(pk.toLowerCase());
        if (!node) return;
        const isLoc = Boolean(node.is_local);
        const st = getPresenceState(node.last_seen, isLoc);
        const isDisc = !isLoc && (st === "status-offline" || node.presence_status === "offline");
        const fullDateTime = node.last_seen_formatted || (node.last_seen && node.last_seen > 0 ? new Date(node.last_seen * 1000).toLocaleString() : (window.I18n ? window.I18n.t('time.no_signal') : "Sin señal registrada"));
        const signalTooltip = isLoc ? I18n.t("nodes.local_signal") : (window.I18n ? window.I18n.t('time.last_signal_tooltip').replace('{time}', fullDateTime) : `Última señal recibida: ${fullDateTime}`);

        const dot = card.querySelector(".avatar-status-dot");
        const act = card.querySelector(".node-card-activity");
        if (dot) {
          dot.className = `avatar-status-dot ${st}`;
          dot.title = signalTooltip;
        }
        if (act) {
          act.textContent = formatLastSeen(node.last_seen, isLoc);
          act.title = signalTooltip;
        }

        if (isDisc) {
          card.classList.add("node-card-offline", "contact-card-offline");
          card.setAttribute("data-online", "0");
          const snrEl = card.querySelector(".metric-snr, .stat-pill:nth-child(2) strong");
          if (snrEl) snrEl.textContent = "--";
          const rssiEl = card.querySelector(".metric-rssi, .stat-pill:nth-child(1) strong");
          if (rssiEl) rssiEl.textContent = "--";
          const lqiBadge = card.querySelector(".lqi-score, .node-meta-sub strong:last-child");
          if (lqiBadge) lqiBadge.textContent = "--";
        } else {
          card.classList.remove("node-card-offline", "contact-card-offline");
          card.setAttribute("data-online", st === "status-online" ? "1" : "0");
        }
      });
    }, 30000);
  }

  initContactDiscovery() {
    this.fetchDiscoveredContacts();
    const banner = document.getElementById("discoveryBanner");
    const countEl = document.getElementById("discoveryCount");
    const acceptBtn = document.getElementById("btnAcceptAllDiscovered");
    const discoveredPks = new Set();

    if (acceptBtn && banner) {
      acceptBtn.addEventListener("click", () => {
        banner.classList.add("hidden");
        discoveredPks.clear();
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('nodes.contacts_accepted'), "success");
      });
    }

    if (this.ctx.eventBus) {
      this.ctx.eventBus.on("contact_discovered", (evt) => {
        if (evt && evt.is_new && evt.contact && evt.contact.public_key && banner && countEl) {
          discoveredPks.add(evt.contact.public_key.toLowerCase());
          countEl.textContent = String(discoveredPks.size);
          banner.classList.remove("hidden");
        }
      });
    }
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
    const cards = document.querySelectorAll("#contactsGridUi .contact-card");
    let visibleCount = 0;

    cards.forEach((card) => {
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

      const isVisible = matchText && matchPill;
      card.classList.toggle("hidden", !isVisible);
      if (isVisible) visibleCount++;
    });

    const grid = this.dom.contactsGridUi;
    if (grid) {
      let emptyMsg = grid.querySelector(".contacts-empty-filter-state");
      if (visibleCount === 0 && cards.length > 0) {
        if (!emptyMsg) {
          emptyMsg = document.createElement("div");
          emptyMsg.className = "contacts-empty-filter-state empty-state";
          grid.appendChild(emptyMsg);
        }
        let desc = I18n.t('nodes.empty_filter');
        if (filter === "favorites") {
          desc = I18n.t('nodes.empty_fav');
        } else if (filter === "online") {
          desc = I18n.t('nodes.empty_online');
        } else if (filter === "gps") {
          desc = I18n.t('nodes.empty_gps');
        } else if (q) {
          desc = I18n.t('nodes.empty_search').replace('{q}', escapeHtml(q));
        }
        emptyMsg.innerHTML = `<p>${desc}</p>`;
      } else if (emptyMsg) {
        emptyMsg.remove();
      }
    }
  }

  filterNodesGrid(query) {
    const q = (query || "").toLowerCase().trim();
    const roleFilter = (this.activeNodesFilter || "all").toUpperCase();
    const cards = document.querySelectorAll("#nodesUnifiedGridUi .node-card");
    let visibleCount = 0;

    cards.forEach((card) => {
      const text = card.textContent.toLowerCase();
      const role = (card.getAttribute("data-role") || "ALL").toUpperCase();
      const matchRole = roleFilter === "ALL" || role === roleFilter || (roleFilter === "CLIENT" && role === "CLIENT");
      const matchText = !q || text.includes(q);
      const isVisible = matchRole && matchText;
      card.classList.toggle("hidden", !isVisible);
      if (isVisible) visibleCount++;
    });

    const grid = this.dom.nodesUnifiedGridUi;
    if (grid) {
      let emptyMsg = grid.querySelector(".nodes-empty-filter-state");
      if (visibleCount === 0 && cards.length > 0) {
        if (!emptyMsg) {
          emptyMsg = document.createElement("div");
          emptyMsg.className = "nodes-empty-filter-state empty-state";
          grid.appendChild(emptyMsg);
        }
        emptyMsg.innerHTML = `<p>${I18n.t('nodes.empty_filter')}</p>`;
      } else if (emptyMsg) {
        emptyMsg.remove();
      }
    }
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

  updateNodeInDom(arg1, arg2) {
    const node = (arg2 && typeof arg2 === "object") ? arg2 : (arg1 && typeof arg1 === "object" ? arg1 : null);
    if (!node) return;
    if (!node.public_key && typeof arg1 === "string") node.public_key = arg1;
    if (!node.public_key) return;
    const pk = String(node.public_key).toLowerCase();
    const cards = document.querySelectorAll(`[data-pk="${pk}"], [data-pubkey="${pk}"]`);
    if (!cards || cards.length === 0) {
      this.knownNodes.set(pk, { ...(this.knownNodes.get(pk) || {}), ...node });
      this.renderNodesDirectory(Array.from(this.knownNodes.values()));
      return;
    }

    const isLocal = Boolean(node.is_local);
    const presenceClass = getPresenceState(node.last_seen, isLocal);
    const isDisconnected = !isLocal && (presenceClass === "status-offline" || node.presence_status === "offline");
    const fullDateTime = node.last_seen_formatted || (node.last_seen && node.last_seen > 0 ? new Date(node.last_seen * 1000).toLocaleString() : (window.I18n ? window.I18n.t('time.no_signal') : "Sin señal registrada"));
    const signalTooltip = isLocal ? I18n.t("nodes.local_signal") : (window.I18n ? window.I18n.t('time.last_signal_tooltip').replace('{time}', fullDateTime) : `Última señal recibida: ${fullDateTime}`);
    const lastSeenText = formatLastSeen(node.last_seen, isLocal);

    cards.forEach((card) => {
      const dot = card.querySelector(".avatar-status-dot");
      if (dot) {
        dot.className = `avatar-status-dot ${presenceClass}`;
        dot.title = signalTooltip;
      }
      if (isDisconnected) {
        card.classList.add("node-card-offline", "contact-card-offline");
        card.setAttribute("data-online", "0");
      } else {
        card.classList.remove("node-card-offline", "contact-card-offline");
        card.setAttribute("data-online", presenceClass === "status-online" ? "1" : "0");
      }

      // Señal: SNR y RSSI (preservar última señal conocida incluso si está offline)
      const snrEl = card.querySelector(".metric-snr, .stat-pill:nth-child(2) strong");
      if (snrEl) {
        snrEl.textContent = isLocal ? "Local" : (node.last_snr != null ? `${node.last_snr} dB` : "--");
      }
      const rssiEl = card.querySelector(".metric-rssi, .stat-pill:nth-child(1) strong");
      if (rssiEl) {
        rssiEl.textContent = isLocal ? "Local" : (node.last_rssi != null ? `${node.last_rssi} dBm` : "--");
      }
      const lqiBadge = card.querySelector(".lqi-score, .node-meta-sub strong:last-child");
      if (lqiBadge) {
        lqiBadge.textContent = isLocal ? "100%" : (node.lqi_score ? `${Math.round(node.lqi_score)}%` : "--");
      }

      // Saltos / Hops
      const hopsEl = card.querySelector(".stat-pill:nth-child(3) strong");
      if (hopsEl) {
        hopsEl.textContent = isLocal ? "0" : (node.hops != null ? (node.hops === 0 ? I18n.t('nodes.route_direct') : `${node.hops} ${I18n.t('nodes.hops', { count: node.hops })}`) : "--");
      }

      // Chip de Batería (los nodos locales se alimentan por USB 5V, no llevan batería LoRa)
      const batText = (!isLocal && node.battery_pct != null) ? `${node.battery_pct}%` : (!isLocal && node.voltage_v != null ? `${node.voltage_v}V` : null);
      if (batText) {
        let batEl = card.querySelector(".contact-battery-chip");
        if (batEl) {
          batEl.textContent = `🔋 ${batText}`;
          batEl.title = I18n.t('nodes.battery_title', { val: batText });
        } else {
          const titleRow = card.querySelector(".contact-title-row, .node-card-badges-group");
          if (titleRow) {
            const chip = document.createElement("span");
            chip.className = "contact-battery-chip";
            chip.title = I18n.t('nodes.battery_title', { val: batText });
            chip.textContent = `🔋 ${batText}`;
            titleRow.insertBefore(chip, titleRow.firstChild);
          }
        }
      } else if (isLocal) {
        const batEl = card.querySelector(".contact-battery-chip");
        if (batEl) batEl.remove();
      }

      // Telemetría / Ruta
      const telemEl = card.querySelector(".node-telemetry-panel .node-meta-sub span:first-child");
      if (telemEl) {
        if (isLocal) {
          telemEl.innerHTML = `🖥️ <strong>${I18n.t("nodes.usb_host")}</strong>`;
        } else if (node.temperature_c != null) {
          telemEl.innerHTML = `🌡️ <strong>${escapeHtml(String(node.temperature_c))}°C</strong> ${node.humidity_pct != null ? `💧 ${escapeHtml(String(node.humidity_pct))}%` : ""}`;
        } else if (node.owner_name) {
          telemEl.innerHTML = `${window.I18n ? window.I18n.t('nodes.owner_label') : "Dueño:"} <strong>${escapeHtml(node.owner_name)}</strong>`;
        } else if (node.best_route || node.hops != null) {
          telemEl.innerHTML = `${window.I18n ? window.I18n.t('nodes.route_label') : "Ruta:"} <strong>${escapeHtml(node.best_route || (node.hops === 0 ? (window.I18n ? window.I18n.t('nodes.route_direct') : "Directo") : (window.I18n ? window.I18n.t('nodes.route_mesh') : "Malla")))}</strong>`;
        }
      }

      // Tiempo de actividad y tooltip
      const timeEl = card.querySelector(".node-last-seen, .node-card-activity");
      if (timeEl) {
        timeEl.textContent = lastSeenText;
        timeEl.title = signalTooltip;
      }

      // Coordenadas GPS
      const rawLat = node.latitude ?? node.lat ?? node.adv_lat ?? node.gps?.latitude;
      const rawLon = node.longitude ?? node.lon ?? node.adv_lon ?? node.gps?.longitude;
      const fLat = rawLat != null ? parseFloat(rawLat) : NaN;
      const fLon = rawLon != null ? parseFloat(rawLon) : NaN;
      const hasGps = !isNaN(fLat) && !isNaN(fLon) && (fLat !== 0 || fLon !== 0 || node.position_valid);
      const gpsEl = card.querySelector(".node-telemetry-panel .node-meta-row span:last-child");
      if (gpsEl) {
        gpsEl.innerHTML = hasGps ? `📍 ${fLat.toFixed(3)}, ${fLon.toFixed(3)}` : `<span class="color-dim font-mono">${I18n.t('common.no_gps')}</span>`;
      }
      card.setAttribute("data-has-gps", hasGps ? "1" : "0");

      // Actualizar 6 Métricas de Telemetría y Acordeón de Rutas (en vista Nodos)
      const metricsContainer = card.querySelector(".node-telemetry-metrics");
      const accordionContainer = card.querySelector(".node-route-accordion");
      if (metricsContainer) {
        const tempDiv = document.createElement("div");
        tempDiv.innerHTML = this._renderTelemetryMetricsHtml(node, isLocal);
        const newMetrics = tempDiv.querySelector(".node-telemetry-metrics");
        const newAccordion = tempDiv.querySelector(".node-route-accordion");
        if (newMetrics) {
          metricsContainer.replaceWith(newMetrics);
        }
        if (accordionContainer && newAccordion) {
          accordionContainer.replaceWith(newAccordion);
        } else if (!accordionContainer && newAccordion && newMetrics) {
          newMetrics.insertAdjacentElement("afterend", newAccordion);
        }
        card.querySelectorAll(".btn-copy-hashes").forEach((btn) => {
          btn.addEventListener("click", async (e) => {
            e.stopPropagation();
            const hashes = btn.getAttribute("data-hashes");
            if (hashes) {
              try {
                await navigator.clipboard.writeText(hashes);
                if (this.ctx.showToast) {
                  this.ctx.showToast(I18n.t('nodes.hashes_copied'), "info");
                }
              } catch (_) {}
            }
          });
        });
        if (window.initLucideIcons) {
          window.initLucideIcons(card);
        }
      }
    });
  }

  async pingNode(pubkey, name, btnEl) {
    if (!pubkey) return;
    const cleanName = name || pubkey.slice(0, 8);
    const cleanKey = pubkey.toLowerCase();

    const node = this.knownNodes?.get(cleanKey);
    const roleUpper = String(node?.role || "").toUpperCase();
    if (roleUpper === "CLIENT") {
      if (this.ctx.showToast) {
        this.ctx.showToast(I18n.t("nodes.ping_repeaters_only"), "warning");
      }
      return;
    }

    if (!this._pingCooldowns) this._pingCooldowns = new Map();
    if (!this._pingingNodes) this._pingingNodes = new Set();

    // 1. Evitar peticiones concurrentes hacia el mismo repetidor
    if (this._pingingNodes.has(cleanKey)) {
      return;
    }

    // 2. Comprobar cooldown de protección de Airtime LoRa del lado cliente
    const now = Date.now();
    const cooldownExpires = this._pingCooldowns.get(cleanKey) || 0;
    if (now < cooldownExpires) {
      const remainingSec = Math.ceil((cooldownExpires - now) / 1000);
      if (this.ctx.showToast) {
        this.ctx.showToast(I18n.t("nodes.ping_cooldown", { p0: remainingSec, p1: cleanName }), "warning");
      }
      return;
    }

    this._pingingNodes.add(cleanKey);

    const originalHtml = btnEl ? btnEl.innerHTML : null;
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.innerHTML = `<span data-lucide="loader-2" data-size="13" class="spin"></span> ${window.I18n ? window.I18n.t('nodes.pinging') || 'Midiendo...' : 'Midiendo...'}`;
      if (window.initLucideIcons) window.initLucideIcons(btnEl);
    }

    try {
      const res = await fetch("/api/node/ping_zero", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: pubkey }),
      });
      const data = await res.json().catch(() => ({}));

      // Si el servidor activa rate-limiting LoRa 429
      if (res.status === 429 || data.code === 429) {
        const remSec = data.cooldown_remaining || 15;
        this._pingCooldowns.set(cleanKey, Date.now() + remSec * 1000);
        const warnMsg = data.detail || data.message || I18n.t("nodes.ping_airtime", { p0: remSec });
        if (this.ctx.showToast) this.ctx.showToast(`⏳ ${warnMsg}`, "warning");
        this._startPingButtonCooldown(btnEl, cleanKey, remSec, originalHtml);
        return;
      }

      if (res.ok && data.status === "ok") {
        this._pingCooldowns.set(cleanKey, Date.now() + 15000);
        const rtt = data.data?.rtt_ms != null ? `${data.data.rtt_ms} ms` : "OK";
        const snr = data.data?.snr != null ? ` | SNR: ${data.data.snr} dB` : "";
        const rssi = data.data?.rssi != null ? ` | RSSI: ${data.data.rssi} dBm` : "";
        const msg = (window.I18n ? window.I18n.t('toast.ping_ok') : null)
          ?.replace('{name}', cleanName)
          ?.replace('{rtt}', rtt)
          ?.replace('{snr}', snr)
          ?.replace('{rssi}', rssi) || `🎯 Pong de ${cleanName}: ${rtt}${snr}${rssi}`;
        if (this.ctx.showToast) this.ctx.showToast(msg, "success");
        this._startPingButtonCooldown(btnEl, cleanKey, 15, originalHtml);
      } else {
        const errMsg = data.detail || data.message || data.error || I18n.t('common.request_timeout');
        const msg = (window.I18n ? window.I18n.t('toast.ping_err') : null)?.replace('{name}', cleanName) || `⚠️ Sin respuesta de Ping (${errMsg})`;
        if (this.ctx.showToast) this.ctx.showToast(msg, "warning");
        if (btnEl && originalHtml) {
          btnEl.disabled = false;
          btnEl.innerHTML = originalHtml;
          if (window.initLucideIcons) window.initLucideIcons(btnEl);
        }
      }
    } catch (err) {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("nodes.ping_execution_error", { p0: err.message }), "error");
      if (btnEl && originalHtml) {
        btnEl.disabled = false;
        btnEl.innerHTML = originalHtml;
        if (window.initLucideIcons) window.initLucideIcons(btnEl);
      }
    } finally {
      this._pingingNodes.delete(cleanKey);
    }
  }

  _startPingButtonCooldown(btnEl, cleanKey, durationSec, originalHtml) {
    if (!btnEl) return;
    btnEl.disabled = true;

    const tick = () => {
      const expires = this._pingCooldowns?.get(cleanKey) || 0;
      const remaining = Math.ceil((expires - Date.now()) / 1000);
      if (remaining <= 0) {
        btnEl.disabled = false;
        if (originalHtml) {
          btnEl.innerHTML = originalHtml;
        } else {
          btnEl.innerHTML = `<span data-lucide="crosshair" data-size="13"></span> ${window.I18n ? window.I18n.t('nodes.ping_btn') || 'Ping' : 'Ping'}`;
        }
        if (window.initLucideIcons) window.initLucideIcons(btnEl);
      } else {
        btnEl.innerHTML = `<span data-lucide="clock" data-size="13"></span> ${remaining}s`;
        if (window.initLucideIcons) window.initLucideIcons(btnEl);
        setTimeout(tick, 1000);
      }
    };
    tick();
  }
}
