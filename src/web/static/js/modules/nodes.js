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

      deduplicatedNodes.push({
        ...rawNode,
        is_local: isThisLocal,
        role: isThisLocal ? "LOCAL" : (isRepeater ? "REPEATER" : (rawNode.role || "CLIENT")),
      });
    }

    this.knownNodes.clear();
    deduplicatedNodes.forEach((n) => {
      this.knownNodes.set(n.public_key.toLowerCase(), n);
    });

    if (this.ctx.knownNodes) {
      this.ctx.knownNodes = this.knownNodes;
    }

    if (this.dom.headerNodeCount) {
      this.dom.headerNodeCount.textContent = String(deduplicatedNodes.length);
    }

    if (contactsGrid) contactsGrid.textContent = "";
    if (unifiedNodesGrid) unifiedNodesGrid.textContent = "";

    const contactsFrag = document.createDocumentFragment();
    const nodesFrag = document.createDocumentFragment();

    for (const node of deduplicatedNodes) {
      const isLocal = node.is_local;
      const isRepeater = node.role === "REPEATER";
      const cleanName = node.name || node.alias || node.public_key.slice(0, 8);

      // Tarjetas para Contactos (SOLO CLIENTES)
      if (contactsGrid && !isLocal && !isRepeater && node.role === "CLIENT") {
        const cCard = document.createElement("div");
        cCard.className = "contact-card";
        cCard.setAttribute("data-pk", node.public_key);
        cCard.innerHTML = `
          <div class="contact-card-header">
            <span class="contact-name font-mono">${escapeHtml(cleanName)}</span>
            <span class="node-role-badge role-client">CLIENT</span>
          </div>
          <div class="contact-card-actions">
            <button type="button" class="btn-primary btn-sm btn-contact-dm">Iniciar Chat DM</button>
          </div>
        `;
        cCard.querySelector(".btn-contact-dm")?.addEventListener("click", () => {
          if (this.ctx.openDmConversation) this.ctx.openDmConversation(node.public_key, cleanName);
        });
        contactsFrag.appendChild(cCard);
      }

      // Tarjetas para Nodos Unificados
      if (unifiedNodesGrid) {
        const nCard = document.createElement("div");
        const roleBadge = isLocal ? "LOCAL" : (isRepeater ? "REPEATER" : (node.role || "CLIENT"));
        nCard.className = `node-card ${isLocal ? "role-local-card" : (isRepeater ? "role-repeater-card" : "role-client-card")}`;
        nCard.setAttribute("data-pk", node.public_key);
        nCard.setAttribute("data-role", roleBadge);
        nCard.innerHTML = `
          <div class="node-card-header">
            <span class="node-name font-mono">${escapeHtml(cleanName)}</span>
            <span class="node-role-badge">${escapeHtml(roleBadge)}</span>
          </div>
          <div class="node-meta-row">
            <span>Clave: <code>${escapeHtml(node.public_key.slice(0, 8))}...</code></span>
            <span>RSSI: <strong>${node.last_rssi != null ? `${node.last_rssi} dBm` : "--"}</strong></span>
          </div>
          <div class="node-card-actions">
            ${isRepeater ? `<button type="button" class="btn-primary btn-sm btn-manage-repeater">Administrar</button>` : ""}
            ${!isLocal && !isRepeater ? `<button type="button" class="btn-primary btn-sm btn-dm-node">Chat DM</button>` : ""}
            <button type="button" class="btn-secondary btn-sm btn-trace-node">Ruta</button>
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
        nCard.querySelector(".btn-trace-node")?.addEventListener("click", () => {
          if (this.ctx.openTracerouteModal) this.ctx.openTracerouteModal(node.public_key, cleanName);
        });

        nodesFrag.appendChild(nCard);
      }
    }

    if (contactsGrid) contactsGrid.appendChild(contactsFrag);
    if (unifiedNodesGrid) unifiedNodesGrid.appendChild(nodesFrag);

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
    document.querySelectorAll("#contactsGridUi .contact-card").forEach((card) => {
      const text = card.textContent.toLowerCase();
      card.classList.toggle("hidden", q && !text.includes(q));
    });
  }

  filterNodesGrid(query) {
    const q = (query || "").toLowerCase().trim();
    const roleFilter = this.activeNodesFilter;
    document.querySelectorAll("#nodesUnifiedGridUi .node-card").forEach((card) => {
      const text = card.textContent.toLowerCase();
      const role = card.getAttribute("data-role") || "ALL";
      const matchRole = roleFilter === "all" || role.toLowerCase() === roleFilter.toLowerCase();
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
