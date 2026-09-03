/**
 * MapModule - Visualización cartográfica Leaflet, capas de mosaicos online y offline (MBTiles),
 * marcadores de nodos de malla, Heatmap táctico RF y trazado de rutas Traceroute.
 */

import { escapeHtml } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class MapModule {
  constructor(context) {
    this.ctx = context;
    this.map = null;
    this.tileLayers = {};
    this.mapMarkers = new Map();
    this.tacticalRadarGroup = null;
    this.rfHeatmapGroup = null;
    this.rfHeatmapActive = false;
    this.rfHeatmapInterval = null;
    this.selectedTraceTarget = null;
    this.selectedTraceName = null;
    this.localTileUrl = localStorage.getItem("meshcore_local_tile_url") || "/api/map/tiles/{z}/{x}/{y}.png";
    const savedLayer = localStorage.getItem("meshcore_map_layer_mode");
    this.mapLayerMode = (savedLayer === "cartodb" || !savedLayer) ? "dark" : savedLayer;
    this.dom = {};
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.initLeafletMap();
    this.initMapOverlayToggle();
    this.initAirtimeMonitoring();
    this.initTraceroute();
  }

  _bindElements() {
    this.dom = {
      liveGpsMap: document.getElementById("liveGpsMap"),
      mapOverlayInfo: document.getElementById("mapOverlayInfo"),
      btnToggleMapNodes: document.getElementById("btnToggleMapNodes"),
      mapOverlayHeader: document.getElementById("mapOverlayHeader"),
      mapNodesList: document.getElementById("mapNodesList"),
      btnToggleHeatmap: document.getElementById("btnToggleHeatmap"),
      tracerouteModal: document.getElementById("tracerouteModal"),
      btnCloseTracerouteModal: document.getElementById("btnCloseTracerouteModal"),
      btnExecuteTrace: document.getElementById("btnExecuteTrace"),
      traceTargetNameDisplay: document.getElementById("traceTargetNameDisplay"),
      traceTargetPkDisplay: document.getElementById("traceTargetPkDisplay"),
      traceCustomPathInput: document.getElementById("traceCustomPathInput"),
      traceStatusPill: document.getElementById("traceStatusPill"),
      traceVisualGraph: document.getElementById("traceVisualGraph"),
      traceBreakdownTableBody: document.getElementById("traceBreakdownTableBody"),
      headerDutyCycle: document.getElementById("headerDutyCycle"),
    };
  }

  _bindEvents() {
    document.querySelectorAll(".map-layer-switcher .map-layer-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        const mode = btn.getAttribute("data-layer");
        if (mode) this.setMapLayer(mode);
      });
    });

    if (this.dom.btnToggleHeatmap) {
      this.dom.btnToggleHeatmap.addEventListener("click", () => this.toggleRfHeatmap());
    }
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    this.ctx.eventBus.on(EVENTS.TAB_CHANGED, (tabId) => {
      if (tabId === "tab-map" && this.map) {
        setTimeout(() => {
          try {
            this.map.invalidateSize();
          } catch (_) {}
        }, 150);
      }
    });

    this.ctx.eventBus.on(EVENTS.NODE_UPDATED, (node) => {
      if (node && node.latitude != null && node.longitude != null) {
        this.updateSingleNodeMarker(node);
      }
    });
  }

  initLeafletMap() {
    if (!this.dom.liveGpsMap) return;

    if (typeof L === "undefined") {
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

      const darkLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        className: 'map-tiles-dark',
        maxZoom: 19,
      });

      const osmLayer = L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
        maxZoom: 19,
      });

      const satelliteLayer = L.tileLayer("https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}", {
        attribution: '&copy; <a href="https://www.esri.com/">Esri</a>, Earthstar Geographics',
        maxZoom: 19,
        maxNativeZoom: 18,
      });

      this.tileLayers = {
        dark: darkLayer,
        cartodb: darkLayer,
        osm: osmLayer,
        satellite: satelliteLayer,
        local: L.tileLayer(this.localTileUrl, {
          attribution: 'MeshCore Offline Local Tiles',
          maxZoom: 18,
          errorTileUrl: 'data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" fill="%230f172a"><rect width="256" height="256"/><text x="128" y="128" fill="%23475569" text-anchor="middle" font-size="11" font-family="sans-serif">Mosaico Local No Disponible</text></svg>',
        }),
      };

      this.tacticalRadarGroup = L.layerGroup();
      this.rfHeatmapGroup = L.layerGroup();

      this.setMapLayer(this.mapLayerMode || "dark");

      if (this.ctx.knownNodes && this.ctx.knownNodes.size > 0) {
        this.updateMapMarkers(Array.from(this.ctx.knownNodes.values()));
      }
    } catch (err) {
      console.warn("No se pudo inicializar el mapa Leaflet:", err);
    }
  }

  setMapLayer(mode) {
    if (!this.map || !this.tileLayers) return;

    Object.values(this.tileLayers).forEach((layer) => {
      if (this.map.hasLayer(layer)) {
        this.map.removeLayer(layer);
      }
    });

    const selected = this.tileLayers[mode] || this.tileLayers.dark;
    selected.addTo(this.map);
    this.mapLayerMode = mode;
    localStorage.setItem("meshcore_map_layer_mode", mode);

    document.querySelectorAll(".map-layer-switcher .map-layer-btn").forEach((btn) => {
      btn.classList.toggle("active", btn.getAttribute("data-layer") === mode);
    });

    this.renderTacticalRadarOverlay();
  }

  initMapOverlayToggle() {
    const overlay = this.dom.mapOverlayInfo;
    const btnToggle = this.dom.btnToggleMapNodes;
    const header = this.dom.mapOverlayHeader;
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

    const savedState = localStorage.getItem("meshcore_map_nodes_minimized");
    if (savedState === "true") {
      setMinimizedState(true);
    }

    if (btnToggle) {
      btnToggle.addEventListener("click", (e) => {
        e.stopPropagation();
        setMinimizedState(!overlay.classList.contains("minimized"));
      });
    }

    if (header) {
      header.addEventListener("click", (e) => {
        if (e.target.closest("#btnToggleMapNodes")) return;
        setMinimizedState(!overlay.classList.contains("minimized"));
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
      if (this.rfHeatmapInterval) {
        clearInterval(this.rfHeatmapInterval);
        this.rfHeatmapInterval = null;
      }
      if (this.ctx.showToast) this.ctx.showToast("🔥 Mapa de calor RF desactivado", "info");
      return;
    }

    await this.refreshRfHeatmap(true);

    if (!this.rfHeatmapInterval) {
      this.rfHeatmapInterval = setInterval(() => {
        if (this.rfHeatmapActive) this.refreshRfHeatmap(false);
      }, 10000);
    }
  }

  async refreshRfHeatmap(showToast = false) {
    if (!this.map || !this.rfHeatmapActive) return;

    try {
      const res = await fetch("/api/rf/heatmap", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && data.data && Array.isArray(data.data.points)) {
        if (!this.rfHeatmapGroup) this.rfHeatmapGroup = L.layerGroup();
        this.rfHeatmapGroup.clearLayers();

        const points = data.data.points;

        points.forEach((pt) => {
          const ptRssi = pt.rssi != null ? Number(pt.rssi) : -100;
          const ptSnr = pt.snr != null ? Number(pt.snr) : 0;
          const isLocal = Boolean(pt.is_local);

          const baseRadius = Math.max(500, Math.min(3500, (ptRssi + 135) * 45));

          let color = "#ef4444";
          let qualityLabel = "Débil";
          if (ptRssi >= -75 || (isLocal && ptRssi >= -85)) {
            color = "#10b981";
            qualityLabel = "Excelente";
          } else if (ptRssi >= -95) {
            color = "#06b6d4";
            qualityLabel = "Buena";
          } else if (ptRssi >= -110) {
            color = "#f59e0b";
            qualityLabel = "Marginal";
          }

          const outerCircle = L.circle([pt.lat, pt.lon], {
            radius: baseRadius,
            color: color,
            fillColor: color,
            fillOpacity: 0.12,
            weight: 1,
            dashArray: "4, 4",
          });

          const innerCircle = L.circle([pt.lat, pt.lon], {
            radius: baseRadius * 0.45,
            color: color,
            fillColor: color,
            fillOpacity: 0.32,
            weight: 2,
          });

          const rssiPart = pt.rssi != null ? `${Math.round(ptRssi)} dBm` : "--";
          const snrPart = pt.snr != null ? `${ptSnr > 0 ? "+" : ""}${ptSnr.toFixed(1)} dB` : "--";
          const noisePart = pt.noise_floor != null ? `${pt.noise_floor} dBm` : "--";
          const roleLabel = pt.role || (isLocal ? "LOCAL" : "CLIENT");

          const popupHtml = `
            <div class="custom-map-popup" style="min-width: 190px;">
              <div class="popup-title" style="color: ${color};">
                <span data-lucide="flame" data-size="14"></span> <strong>${escapeHtml(pt.name)}</strong>
              </div>
              <div class="popup-info">
                <div><span>Rol:</span> <span class="badge-pill" style="font-size: 10px;">${escapeHtml(roleLabel)}</span></div>
                <div><span>Calidad Enlace:</span> <strong style="color: ${color};">${qualityLabel}</strong></div>
                <div><span>RSSI / SNR:</span> <strong>${rssiPart} / ${snrPart}</strong></div>
                <div><span>Piso Ruido:</span> <strong>${noisePart}</strong></div>
                <div><span>Radio Cobertura:</span> <code>~${(baseRadius / 1000).toFixed(1)} km</code></div>
              </div>
            </div>
          `;

          innerCircle.bindPopup(popupHtml);
          outerCircle.bindPopup(popupHtml);

          this.rfHeatmapGroup.addLayer(outerCircle);
          this.rfHeatmapGroup.addLayer(innerCircle);
        });

        if (!this.map.hasLayer(this.rfHeatmapGroup)) {
          this.rfHeatmapGroup.addTo(this.map);
        }

        if (showToast && this.ctx.showToast) {
          this.ctx.showToast(`🔥 Heatmap RF generado con ${points.length} puntos de cobertura activa`, "success");
        }
      }
    } catch (err) {
      if (showToast && this.ctx.showToast) {
        this.ctx.showToast(`Error cargando Heatmap RF: ${err.message}`, "error");
      }
    }
  }

  initAirtimeMonitoring() {
    this.fetchAirtimeStats();
    setInterval(() => this.fetchAirtimeStats(), 15000);
  }

  async fetchAirtimeStats() {
    try {
      const res = await fetch("/api/airtime/stats", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        const stats = data.data;
        const pct = stats.hourly_duty_cycle_pct || 0.0;
        if (this.dom.headerDutyCycle) {
          this.dom.headerDutyCycle.textContent = `${pct.toFixed(1)}%`;
        }
      }
    } catch (_) {}
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
    this.selectedTraceTarget = targetNode;
    this.selectedTraceName = targetName || (targetNode ? targetNode.slice(0, 8) : "Nodo");

    if (this.dom.traceTargetNameDisplay) this.dom.traceTargetNameDisplay.textContent = this.selectedTraceName;
    if (this.dom.traceTargetPkDisplay) this.dom.traceTargetPkDisplay.textContent = targetNode;
    if (this.dom.traceCustomPathInput) this.dom.traceCustomPathInput.value = "";
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
      this.dom.traceStatusPill.textContent = "Transmitiendo sonda RF...";
      this.dom.traceStatusPill.className = "trace-status-pill running";
    }
    if (this.dom.btnExecuteTrace) {
      this.dom.btnExecuteTrace.disabled = true;
      this.dom.btnExecuteTrace.textContent = "⏳ Trazando...";
    }

    try {
      const res = await fetch("/api/repeater/traceroute", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, path: customPath }),
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        const trace = data.data;
        if (this.dom.traceStatusPill) {
          this.dom.traceStatusPill.textContent = `✓ Completado (${trace.total_hops || 0} saltos, ${trace.total_rtt_ms || 0}ms)`;
          this.dom.traceStatusPill.className = "trace-status-pill success";
        }
        this.renderTracerouteGraph(trace.hops_breakdown || []);
        this.renderTracerouteTable(trace.hops_breakdown || []);
        if (this.ctx.showToast) this.ctx.showToast(`🗺️ Ruta completada en ${trace.total_hops || 0} saltos (${trace.total_rtt_ms || 0} ms)`, "success");
      } else {
        if (this.dom.traceStatusPill) {
          this.dom.traceStatusPill.textContent = "✗ Fallo de traza o sin respuesta";
          this.dom.traceStatusPill.className = "trace-status-pill error";
        }
        if (this.ctx.showToast) this.ctx.showToast(`Error en traza: ${data.message || "Sin respuesta"}`, "error");
      }
    } catch (err) {
      if (this.dom.traceStatusPill) {
        this.dom.traceStatusPill.textContent = "✗ Error de conexión";
        this.dom.traceStatusPill.className = "trace-status-pill error";
      }
      if (this.ctx.showToast) this.ctx.showToast(`Error de red: ${err.message}`, "error");
    } finally {
      if (this.dom.btnExecuteTrace) {
        this.dom.btnExecuteTrace.disabled = false;
        this.dom.btnExecuteTrace.textContent = "🚀 Iniciar Traza";
      }
    }
  }

  renderTracerouteGraph(hops) {
    if (!this.dom.traceVisualGraph) return;
    this.dom.traceVisualGraph.innerHTML = "";
    if (!Array.isArray(hops) || hops.length === 0) return;

    hops.forEach((hop, idx) => {
      const nodeEl = document.createElement("div");
      nodeEl.className = "trace-node-item";
      const isTarget = idx === hops.length - 1;
      const isStart = idx === 0;

      nodeEl.innerHTML = `
        <div class="trace-node-circle ${isStart ? "start" : (isTarget ? "target" : "repeater")}">
          ${isStart ? "🏠" : (isTarget ? "🎯" : "📻")}
        </div>
        <div class="trace-node-name font-mono">${escapeHtml(hop.name || (hop.pubkey ? hop.pubkey.slice(0, 8) : `Hop ${idx}`))}</div>
        <div class="trace-node-snr">${hop.snr != null ? `${hop.snr} dB` : ""}</div>
      `;
      this.dom.traceVisualGraph.appendChild(nodeEl);

      if (idx < hops.length - 1) {
        const arrowEl = document.createElement("div");
        arrowEl.className = "trace-arrow";
        arrowEl.innerHTML = `<span>➔</span>`;
        this.dom.traceVisualGraph.appendChild(arrowEl);
      }
    });
  }

  renderTracerouteTable(hops) {
    if (!this.dom.traceBreakdownTableBody) return;
    this.dom.traceBreakdownTableBody.innerHTML = "";
    if (!Array.isArray(hops) || hops.length === 0) return;

    hops.forEach((h, i) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>#${i}</strong></td>
        <td><code>${escapeHtml(h.pubkey ? h.pubkey.slice(0, 8) : "--")}</code></td>
        <td>${escapeHtml(h.name || "Nodo")}</td>
        <td><span class="badge-pill">${escapeHtml(h.role || "NODE")}</span></td>
        <td>${h.snr != null ? `${h.snr} dB` : "--"}</td>
        <td>${h.rtt_ms != null ? `${h.rtt_ms} ms` : "--"}</td>
      `;
      this.dom.traceBreakdownTableBody.appendChild(tr);
    });
  }

  renderTacticalRadarOverlay() {
    if (!this.map || !this.tacticalRadarGroup) return;
    this.tacticalRadarGroup.clearLayers();

    let center = this.map.getCenter();
    if (this.ctx.knownNodes) {
      for (const node of this.ctx.knownNodes.values()) {
        if (node.is_local || node.role === "LOCAL") {
          const lat = parseFloat(node.latitude || node.lat);
          const lon = parseFloat(node.longitude || node.lon);
          if (!isNaN(lat) && !isNaN(lon) && lat !== 0) {
            center = L.latLng(lat, lon);
            break;
          }
        }
      }
    }

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

    const delta = 0.35;
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

  updateMapMarkers(nodes) {
    if (!this.map || !Array.isArray(nodes)) return;

    nodes.forEach((node) => {
      this.updateSingleNodeMarker(node);
    });
  }

  updateSingleNodeMarker(node) {
    if (!this.map || !node) return;
    const lat = parseFloat(node.latitude ?? node.lat);
    const lon = parseFloat(node.longitude ?? node.lon);
    if (isNaN(lat) || isNaN(lon) || (lat === 0 && lon === 0)) return;

    const pk = (node.public_key || "").toLowerCase();
    if (!pk) return;

    const isLocal = Boolean(node.is_local || node.role === "LOCAL");
    const isRepeater = String(node.role || "").toUpperCase() === "REPEATER";
    const markerColor = isLocal ? "#10b981" : (isRepeater ? "#8b5cf6" : "#0ea5e9");

    if (this.mapMarkers.has(pk)) {
      const m = this.mapMarkers.get(pk);
      m.setLatLng([lat, lon]);
      return;
    }

    const customIcon = L.divIcon({
      className: "custom-leaflet-marker",
      html: `<div style="background: ${markerColor}; width: 14px; height: 14px; border-radius: 50%; border: 2px solid white; box-shadow: 0 0 6px ${markerColor};"></div>`,
      iconSize: [14, 14],
      iconAnchor: [7, 7],
    });

    const marker = L.marker([lat, lon], { icon: customIcon });
    const name = node.name || node.alias || pk.slice(0, 8);

    marker.bindPopup(`
      <div class="custom-map-popup">
        <div class="popup-title" style="color: ${markerColor};">
          <strong>${escapeHtml(name)}</strong>
        </div>
        <div class="popup-info">
          <div><span>Rol:</span> <span class="badge-pill">${escapeHtml(node.role || "CLIENT")}</span></div>
          <div><span>Clave:</span> <code>${escapeHtml(pk.slice(0, 8))}...</code></div>
          ${node.last_rssi != null ? `<div><span>RSSI:</span> <strong>${node.last_rssi} dBm</strong></div>` : ""}
          ${node.last_snr != null ? `<div><span>SNR:</span> <strong>${node.last_snr} dB</strong></div>` : ""}
        </div>
      </div>
    `);

    marker.addTo(this.map);
    this.mapMarkers.set(pk, marker);
  }
}
