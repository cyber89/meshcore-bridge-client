/**
 * AnalyticsModule - Panel de métricas avanzadas, telemetría y analítica de tráfico de la malla LoRa.
 * Gestiona KPIs con micro-sparklines, gráficos de series temporales (RX vs TX), distribución
 * de tipos de paquetes, eficiencia de enrutamiento (Flood vs Direct), diagnóstico de fallos y airtime.
 */

import { escapeHtml } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";
import {
  renderAreaChart,
  renderDonutChart,
  renderHorizontalBarChart,
  renderSparkline,
} from "../core/chart_engine.js";

/**
 * Formatea segundos de uptime en un formato compacto legible: Xd Xh Xm.
 */
function formatUptimeSecs(secs) {
  if (secs == null || isNaN(secs) || secs < 0) return "--";
  const s = Math.floor(secs);
  const days = Math.floor(s / 86400);
  const hours = Math.floor((s % 86400) / 3600);
  const minutes = Math.floor((s % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h ${minutes}m`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m ${s % 60}s`;
}

export class AnalyticsModule {
  constructor(context) {
    this.ctx = context;
    this.dom = {};
    this.refreshTimer = null;
    this.currentRange = "24h";
    this._lastAnalytics = null;
    this._lastAirtime = null;
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    if (window.initLucideIcons) {
      window.initLucideIcons(document.getElementById("tab-analytics"));
    }
    this.fetchAnalytics();
  }

  onLanguageChange() {
    if (this._lastAnalytics) {
      const payload = this._lastAnalytics;
      this.renderKpis(payload.summary || {}, payload);
      this.renderCharts(payload);
      this.renderDiagnostics(payload);
      this.renderHardwareStats(payload);
      this.renderTopActiveTable(payload.top_nodes_by_traffic || []);
    }
    if (this._lastAirtime) this.renderAirtimeStats(this._lastAirtime);
  }

  _bindElements() {
    this.dom = {
      btnRefreshAnalytics: document.getElementById("btnRefreshAnalytics"),
      btnResetMetrics: document.getElementById("btnResetMetrics"),
      rangeButtons: document.querySelectorAll(".time-range-selector .btn-range"),

      // KPIs Principales
      kpiTotalPackets: document.getElementById("kpiTotalPackets"),
      kpiPacketsRatio: document.getElementById("kpiPacketsRatio"),
      kpiSparklinePackets: document.getElementById("kpiSparklinePackets"),

      kpiRoutingDirect: document.getElementById("kpiRoutingDirect"),
      kpiRoutingRatio: document.getElementById("kpiRoutingRatio"),
      kpiSparklineRouting: document.getElementById("kpiSparklineRouting"),

      kpiErrorRate: document.getElementById("kpiErrorRate"),
      kpiErrorsTotal: document.getElementById("kpiErrorsTotal"),
      kpiSparklineErrors: document.getElementById("kpiSparklineErrors"),

      kpiDutyCycleVal: document.getElementById("kpiDutyCycleVal"),
      kpiDutyCycleSub: document.getElementById("kpiDutyCycleSub"),
      kpiSparklineAirtime: document.getElementById("kpiSparklineAirtime"),

      // Contenedores de Gráficos Primarios
      chartTrafficTimeline: document.getElementById("chartTrafficTimeline"),
      chartTrafficRangeBadge: document.getElementById("chartTrafficRangeBadge"),
      chartPacketTypes: document.getElementById("chartPacketTypes"),

      // Diagnóstico de Enrutamiento y Errores
      chartRoutingBars: document.getElementById("chartRoutingBars"),
      chartErrorBars: document.getElementById("chartErrorBars"),

      // Salud del Transceptor y Hardware
      statHwNoiseFloor: document.getElementById("statHwNoiseFloor"),
      statHwSignal: document.getElementById("statHwSignal"),
      statHwUptime: document.getElementById("statHwUptime"),
      statDeduplication: document.getElementById("statDeduplication"),
      statQueueDepth: document.getElementById("statQueueDepth"),
      statSerialStatus: document.getElementById("statSerialStatus"),
      statMqttStatus: document.getElementById("statMqttStatus"),

      // Tabla de Top Nodos
      analyticsTopActiveTable: document.getElementById("analyticsTopActiveTable"),

      // Presupuesto de Airtime & Duty Cycle
      analyticsAirtimeLabel: document.getElementById("analyticsAirtimeLabel"),
      analyticsAirtimeMs: document.getElementById("analyticsAirtimeMs"),
      analyticsAirtimeFill: document.getElementById("analyticsAirtimeFill"),
      analyticsAirtimeWarnMarker: document.getElementById("analyticsAirtimeWarnMarker"),
      analyticsAirtimeWarnLabel: document.getElementById("analyticsAirtimeWarnLabel"),
      analyticsAirtimeLimitLabel: document.getElementById("analyticsAirtimeLimitLabel"),
    };
  }

  _bindEvents() {
    if (this.dom.btnRefreshAnalytics) {
      this.dom.btnRefreshAnalytics.addEventListener("click", () => {
        this.fetchAnalytics();
      });
    }
    if (this.dom.btnResetMetrics) {
      this.dom.btnResetMetrics.addEventListener("click", () => {
        this.resetMetrics();
      });
    }

    if (this.dom.rangeButtons) {
      this.dom.rangeButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
          const range = btn.dataset.range;
          if (!range || range === this.currentRange) return;

          this.dom.rangeButtons.forEach((b) => b.classList.remove("active"));
          btn.classList.add("active");
          this.currentRange = range;

          if (this.dom.chartTrafficRangeBadge) {
            this.dom.chartTrafficRangeBadge.textContent = range;
          }

          this.fetchAnalytics();
        });
      });
    }
  }

  async resetMetrics() {
    const confirmMsg = I18n.t("analytics.confirm_reset") || "¿Deseas restablecer todos los contadores de paquetes y métricas acumuladas de la red?";
    if (!confirm(confirmMsg)) return;

    try {
      const res = await fetch("/api/analytics/reset", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
      });
      const data = await res.json();
      if (data.status === "ok") {
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("toast.metrics_reset") || "Métricas y contadores restablecidos correctamente", "success");
        await this.fetchAnalytics();
        if (this.ctx.fetchNodes) await this.ctx.fetchNodes();
      } else {
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("app.error", { error: data.message || I18n.t("settings.reset_failed") }), "error");
      }
    } catch (err) {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("analytics.network_error", { p0: err.message }), "error");
    }
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    // Actualizar métricas cuando el usuario entra a la pestaña de analítica
    this.ctx.eventBus.on(EVENTS.TAB_CHANGED, (tabId) => {
      if (tabId === "tab-analytics") {
        this.fetchAnalytics();
        if (this._liveAnalyticsInterval) clearInterval(this._liveAnalyticsInterval);
        this._liveAnalyticsInterval = setInterval(() => {
          if (document.hidden) return;
          const activeTab = document.querySelector(".tab-pane.active")?.id;
          if (activeTab === "tab-analytics") {
            this.fetchAnalytics();
          } else {
            clearInterval(this._liveAnalyticsInterval);
            this._liveAnalyticsInterval = null;
          }
        }, 15000);
      } else if (this._liveAnalyticsInterval) {
        clearInterval(this._liveAnalyticsInterval);
        this._liveAnalyticsInterval = null;
      }
    });

    // Actualización reactiva periódica ante paquetes RF con debounce de 5s
    const triggerDebouncedRefresh = () => {
      if (document.hidden) return;
      if (!this.refreshTimer) {
        this.refreshTimer = setTimeout(() => {
          this.refreshTimer = null;
          if (document.hidden) return;
          const activeTab = document.querySelector(".tab-pane.active")?.id;
          if (activeTab === "tab-analytics") {
            this.fetchAnalytics();
          }
        }, 5000);
      }
    };

    this.ctx.eventBus.on(EVENTS.RF_PACKET, triggerDebouncedRefresh);
    if (EVENTS.METRICS_UPDATE) {
      this.ctx.eventBus.on(EVENTS.METRICS_UPDATE, (payload) => {
        if (payload) {
          const airtimeData = payload.airtime || (payload.duty_cycle_pct != null || payload.hourly_duty_cycle_pct != null ? payload : null);
          if (airtimeData) {
            this.renderAirtimeStats(airtimeData);
          }
        }
      });
    }
    if (EVENTS.DUTY_CYCLE_ALERT) {
      this.ctx.eventBus.on(EVENTS.DUTY_CYCLE_ALERT, (payload) => {
        if (payload) {
          this.renderAirtimeStats(payload);
        }
      });
    }
  }

  async fetchAnalytics() {
    try {
      const headers = this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {};
      const url = `/api/analytics?range=${encodeURIComponent(this.currentRange)}`;
      const [resAnalytics, resAirtime] = await Promise.all([
        fetch(url, { headers }),
        fetch("/api/airtime/stats", { headers }).catch(() => null),
      ]);

      const dataAnalytics = await resAnalytics.json();
      let dataAirtime = null;
      if (resAirtime && resAirtime.ok) {
        dataAirtime = await resAirtime.json();
      }

      if (dataAnalytics.status === "ok" && dataAnalytics.data) {
        const payload = dataAnalytics.data;
        this._lastAnalytics = payload;

        this.renderKpis(payload.summary || {}, payload);
        this.renderCharts(payload);
        this.renderDiagnostics(payload);
        this.renderHardwareStats(payload);
        this.renderTopActiveTable(payload.top_nodes_by_traffic || []);
      }

      if (dataAirtime && dataAirtime.status === "ok" && dataAirtime.data) {
        this.renderAirtimeStats(dataAirtime.data);
      }
    } catch (e) {
      console.warn("Error cargando métricas analíticas:", e);
    }
  }

  renderKpis(summary, rootData) {
    const rx = Number(summary.total_rx_packets || 0);
    const tx = Number(summary.total_tx_packets || 0);
    const total = rx + tx;

    // 1. Paquetes Totales y Micro-sparkline
    if (this.dom.kpiTotalPackets) {
      this.dom.kpiTotalPackets.textContent = total.toLocaleString();
    }
    if (this.dom.kpiPacketsRatio) {
      this.dom.kpiPacketsRatio.textContent = `RX: ${rx.toLocaleString()} | TX: ${tx.toLocaleString()}`;
    }

    const points = rootData.time_series?.points || [];
    if (this.dom.kpiSparklinePackets && points.length > 1) {
      const rxValues = points.map((p) => Number(p.rx || 0));
      renderSparkline(this.dom.kpiSparklinePackets, rxValues, "var(--accent-primary, #3b82f6)");
    }

    // 2. Eficiencia de Enrutamiento (Direct vs Flood)
    const eff = rootData.routing_efficiency || {};
    const floodPct = Number(eff.flood_ratio_pct != null ? eff.flood_ratio_pct : 0.0);
    const directPct = Math.max(0, 100 - floodPct);
    const totalDirect = Number(eff.total_direct || (Number(eff.direct_rx || 0) + Number(eff.direct_tx || 0)));
    const totalFlood = Number(eff.total_flood || (Number(eff.flood_rx || 0) + Number(eff.flood_tx || 0)));

    if (this.dom.kpiRoutingDirect) {
      this.dom.kpiRoutingDirect.textContent = `${directPct.toFixed(1)}%`;
      this.dom.kpiRoutingDirect.style.color = directPct >= 70 ? "var(--accent-success, #10b981)" : (directPct >= 40 ? "var(--accent-warning, #f59e0b)" : "var(--accent-primary, #3b82f6)");
    }
    if (this.dom.kpiRoutingRatio) {
      this.dom.kpiRoutingRatio.textContent = `Direct: ${totalDirect.toLocaleString()} | Flood: ${totalFlood.toLocaleString()}`;
    }
    if (this.dom.kpiSparklineRouting && points.length > 1) {
      const directValues = points.map((p) => Number(p.direct || 0));
      renderSparkline(this.dom.kpiSparklineRouting, directValues, "var(--accent-success, #10b981)");
    }

    // 3. Tasa de Error Global
    const rate = summary.global_error_rate_pct != null ? summary.global_error_rate_pct : 0.0;
    if (this.dom.kpiErrorRate) {
      this.dom.kpiErrorRate.textContent = `${Number(rate).toFixed(1)}%`;
      this.dom.kpiErrorRate.style.color = rate > 5.0 ? "var(--accent-danger, #ef4444)" : (rate > 1.0 ? "var(--accent-warning, #f59e0b)" : "var(--accent-success, #10b981)");
    }
    if (this.dom.kpiErrorsTotal) {
      const errTotal = Number(summary.total_errors || 0);
      I18n.setText(this.dom.kpiErrorsTotal, "analytics.errors_acc", { n: errTotal });
    }
    if (this.dom.kpiSparklineErrors && points.length > 1) {
      const errValues = points.map((p) => Number(p.errors || 0));
      renderSparkline(this.dom.kpiSparklineErrors, errValues, "var(--accent-danger, #ef4444)");
    }
  }

  renderCharts(rootData) {
    // 1. Gráfico de Área Temporal RX vs TX
    if (this.dom.chartTrafficTimeline) {
      const points = rootData.time_series?.points || [];
      renderAreaChart(this.dom.chartTrafficTimeline, {
        points,
        series: [
          { key: "rx", label: I18n.t("analytics.chart_rx_label") || "RX (Recibidos)", color: "var(--accent-primary, #3b82f6)" },
          { key: "tx", label: I18n.t("analytics.chart_tx_label") || "TX (Transmitidos)", color: "var(--accent-success, #10b981)" },
        ],
        emptyText: I18n.t("analytics.no_traffic_data") || "Sin datos de tráfico en este rango",
        ariaLabel: I18n.t("analytics.chart_traffic_title") || "Actividad temporal de tráfico",
      });
    }

    // 2. Gráfico Donut de Tipos de Trama
    if (this.dom.chartPacketTypes) {
      const rawTypes = rootData.packet_type_breakdown || {};
      const typePalette = {
        CHAT: { label: I18n.t("analytics.type_chat") || "Mensajes Chat", color: "var(--accent-primary, #3b82f6)" },
        ADVERT: { label: I18n.t("analytics.type_advert") || "Anuncios Malla", color: "var(--accent-purple, #a855f7)" },
        TELEMETRY: { label: I18n.t("analytics.type_telemetry") || "Telemetría", color: "var(--accent-cyan, #06b6d4)" },
        TRACEROUTE: { label: I18n.t("analytics.type_traceroute") || "Traceroute", color: "var(--accent-success, #10b981)" },
        PING: { label: I18n.t("analytics.type_ping") || "Ping / Pong", color: "var(--accent-warning, #f59e0b)" },
        ADMIN: { label: I18n.t("analytics.type_admin") || "Admin / Control", color: "var(--accent-danger, #ef4444)" },
        OTHER: { label: I18n.t("analytics.type_other") || "Otros / RAW", color: "var(--text-muted, #94a3b8)" },
      };

      const donutData = Object.entries(rawTypes).map(([typeKey, count]) => {
        const meta = typePalette[typeKey] || { label: typeKey, color: "var(--text-muted, #94a3b8)" };
        return {
          label: meta.label,
          value: Number(count) || 0,
          color: meta.color,
        };
      });

      renderDonutChart(this.dom.chartPacketTypes, {
        data: donutData,
        centerLabel: I18n.t("common.total") || "Total",
        emptyText: I18n.t("analytics.no_packets") || "0 tramas",
        ariaLabel: I18n.t("analytics.chart_types_title") || "Composición por tipo de trama",
      });
    }
  }

  renderDiagnostics(rootData) {
    // 1. Barras de Enrutamiento (Direct vs Flood)
    if (this.dom.chartRoutingBars) {
      const eff = rootData.routing_efficiency || {};
      const totalDirect = Number(eff.total_direct || (Number(eff.direct_rx || 0) + Number(eff.direct_tx || 0)));
      const totalFlood = Number(eff.total_flood || (Number(eff.flood_rx || 0) + Number(eff.flood_tx || 0)));

      const routingItems = [
        {
          label: I18n.t("analytics.routing_direct") || "Direct Unicast (Punto a Punto)",
          value: totalDirect,
          color: "var(--accent-success, #10b981)",
          icon: "🎯",
          detail: `${I18n.t("analytics.optimal_route") || "Óptimo"}`,
        },
        {
          label: I18n.t("analytics.routing_flood") || "Flood Broadcast (Inundación Malla)",
          value: totalFlood,
          color: "var(--accent-warning, #f59e0b)",
          icon: "🌊",
          detail: `${eff.flood_ratio_pct != null ? Number(eff.flood_ratio_pct).toFixed(1) : "0"}%`,
        },
      ];
      renderHorizontalBarChart(this.dom.chartRoutingBars, routingItems);
    }

    // 2. Barras de Desglose de Errores
    if (this.dom.chartErrorBars) {
      const errMap = rootData.error_breakdown || {};
      const crcErr = Number(errMap.crc_errors || 0);
      const timeouts = Number(errMap.timeouts || 0);
      const queueOver = Number(errMap.queue_overflow || 0);
      const airtimeCut = Number(errMap.airtime_cutoff || 0);

      const errorItems = [
        {
          label: I18n.t("analytics.err_crc") || "CRC / Trama Corrupta",
          value: crcErr,
          color: "var(--accent-danger, #ef4444)",
          icon: "💥",
        },
        {
          label: I18n.t("analytics.err_timeout") || "Timeouts / Sin ACK",
          value: timeouts,
          color: "var(--accent-warning, #f59e0b)",
          icon: "⏱️",
        },
        {
          label: I18n.t("analytics.err_cutoff") || "Bloqueos por Airtime (Cutoff)",
          value: airtimeCut,
          color: "var(--accent-purple, #a855f7)",
          icon: "🛡️",
        },
        {
          label: I18n.t("analytics.err_queue") || "Desbordamiento de Cola",
          value: queueOver,
          color: "var(--text-muted, #94a3b8)",
          icon: "📦",
        },
      ];
      renderHorizontalBarChart(this.dom.chartErrorBars, errorItems);
    }
  }

  renderHardwareStats(rootData) {
    const hw = rootData.radio_hardware || {};

    if (this.dom.statHwNoiseFloor) {
      const nf = hw.noise_floor_dbm;
      this.dom.statHwNoiseFloor.textContent = nf != null ? `${Number(nf)} dBm` : "-- dBm";
      this.dom.statHwNoiseFloor.style.color = (nf != null && nf > -95) ? "var(--accent-danger, #ef4444)" : "var(--text-bright, #ffffff)";
    }

    if (this.dom.statHwSignal) {
      const snr = hw.last_snr != null ? `${Number(hw.last_snr).toFixed(1)} dB` : "--";
      const rssi = hw.last_rssi != null ? `${Number(hw.last_rssi)} dBm` : "--";
      this.dom.statHwSignal.textContent = `${snr} / ${rssi}`;
    }

    if (this.dom.statHwUptime) {
      this.dom.statHwUptime.textContent = formatUptimeSecs(hw.uptime_secs);
    }

    if (this.dom.statDeduplication) {
      const dupCount = rootData.deduplication_count || 0;
      I18n.setText(this.dom.statDeduplication, "analytics.in_ram_dup", { n: dupCount });
    }

    if (this.dom.statQueueDepth) {
      const qDepth = Number(rootData.queue_depth || 0);
      I18n.setText(this.dom.statQueueDepth, "analytics.packets_count", { n: qDepth });
      this.dom.statQueueDepth.style.color = qDepth > 10 ? "var(--accent-danger, #ef4444)" : "var(--text-bright, #ffffff)";
    }

    if (this.dom.statSerialStatus) {
      const isSerOk = Boolean(rootData.serial_connected);
      I18n.setText(this.dom.statSerialStatus, isSerOk ? "analytics.connected_ok" : "analytics.disconnected");
      this.dom.statSerialStatus.style.color = isSerOk ? "var(--accent-success, #10b981)" : "var(--accent-danger, #ef4444)";
    }

    if (this.dom.statMqttStatus) {
      const isMqttOk = Boolean(rootData.mqtt_connected);
      I18n.setText(this.dom.statMqttStatus, isMqttOk ? "analytics.online_broker" : "analytics.disconnected");
      this.dom.statMqttStatus.style.color = isMqttOk ? "var(--accent-success, #10b981)" : "var(--accent-danger, #ef4444)";
    }
  }

  renderTopActiveTable(nodes) {
    if (!this.dom.analyticsTopActiveTable) return;
    this.dom.analyticsTopActiveTable.textContent = "";

    if (!Array.isArray(nodes) || nodes.length === 0) {
      this.dom.analyticsTopActiveTable.innerHTML = `<tr><td colspan="6" class="text-center text-muted">${I18n.t("analytics.no_traffic")}</td></tr>`;
      return;
    }

    const frag = document.createDocumentFragment();
    // Limitar a los 6 más relevantes para mantener el layout limpio y equilibrado
    for (const n of nodes.slice(0, 6)) {
      const tr = document.createElement("tr");
      const name = n.name || n.alias || (n.public_key ? `[${n.public_key.substring(0, 8)}]` : "Nodo");
      const role = n.role || "CLIENT";
      const rx = Number(n.rx_packets || 0);
      const tx = Number(n.tx_packets || 0);
      const tot = Number(n.total_packets || (rx + tx));

      let roleBadge = "badge-primary";
      if (role === "REPEATER" || role === "ROUTER") roleBadge = "badge-purple";
      else if (role === "LOCAL") roleBadge = "badge-success";
      else if (role === "ROOM") roleBadge = "badge-warning";
      else if (role === "SENSOR") roleBadge = "badge-secondary";

      let lqiStatus = I18n.t("signal.excellent");
      let lqiClass = "badge-success";
      const snrVal = Number(n.last_snr);
      if (snrVal < -10) {
        lqiStatus = I18n.t("signal.critical");
        lqiClass = "badge-danger";
      } else if (snrVal < 0) {
        lqiStatus = I18n.t("signal.weak");
        lqiClass = "badge-warning";
      } else if (snrVal < 6) {
        lqiStatus = I18n.t("signal.acceptable");
        lqiClass = "badge-primary";
      }

      tr.innerHTML = `
        <td><strong class="font-mono text-sm">${escapeHtml(name)}</strong></td>
        <td><span class="badge-pill ${roleBadge} text-xs">${escapeHtml(role)}</span></td>
        <td class="font-mono text-xs">${rx.toLocaleString()}</td>
        <td class="font-mono text-xs">${tx.toLocaleString()}</td>
        <td class="font-mono text-xs font-semibold" style="color: var(--accent-primary, #3b82f6);">${tot.toLocaleString()}</td>
        <td><span class="badge-pill ${lqiClass} text-xs">${escapeHtml(lqiStatus)}</span></td>
      `;
      frag.appendChild(tr);
    }
    this.dom.analyticsTopActiveTable.appendChild(frag);
  }

  renderAirtimeStats(airtime) {
    this._lastAirtime = airtime;
    if (!airtime) return;

    const usedMs = Number(airtime.hourly_used_ms != null ? airtime.hourly_used_ms : (airtime.airtime_ms || 0));
    const limitPct = Number(airtime.hourly_limit_pct || 1.0);
    const warnThresholdPct = Number(airtime.warn_threshold_pct || 80.0);
    const budgetMs = Number(airtime.hourly_budget_ms || (3600000.0 * (limitPct / 100.0)));
    const dutyCyclePct = Number(airtime.hourly_duty_cycle_pct != null ? airtime.hourly_duty_cycle_pct : (airtime.duty_cycle_pct || 0.0));

    const isCritical = Boolean(airtime.is_critical || airtime.level === "critical" || (dutyCyclePct >= limitPct));
    const isWarning = Boolean(airtime.is_warning || airtime.level === "warning" || (!isCritical && dutyCyclePct >= (limitPct * (warnThresholdPct / 100.0))));

    // Actualizar KPI de Duty Cycle
    if (this.dom.kpiDutyCycleVal) {
      this.dom.kpiDutyCycleVal.textContent = `${dutyCyclePct.toFixed(2)}%`;
      this.dom.kpiDutyCycleVal.style.color = isCritical ? "var(--accent-danger, #ef4444)" : (isWarning ? "var(--accent-warning, #f59e0b)" : "var(--accent-primary, #3b82f6)");
    }
    if (this.dom.kpiDutyCycleSub) {
      const statusNote = isCritical ? ` [${I18n.t("analytics.critical_cutoff") || "CRÍTICO"}]` : (isWarning ? ` [${I18n.t("analytics.warning_cutoff") || "ADVERTENCIA"}]` : "");
      this.dom.kpiDutyCycleSub.textContent = `${Math.round(usedMs).toLocaleString()} / ${Math.round(budgetMs).toLocaleString()} ms${statusNote}`;
    }

    // Sparkline de Airtime
    if (this.dom.kpiSparklineAirtime && this._lastAnalytics?.time_series?.points) {
      const txValues = this._lastAnalytics.time_series.points.map((p) => Number(p.tx || 0));
      renderSparkline(this.dom.kpiSparklineAirtime, txValues, isCritical ? "var(--accent-danger, #ef4444)" : "var(--accent-primary, #3b82f6)");
    }

    // Barra de progreso inferior
    if (this.dom.analyticsAirtimeLabel) {
      const statusSuffix = isCritical ? " — 🔴 CRÍTICO" : (isWarning ? " — ⚠️ ADVERTENCIA" : "");
      this.dom.analyticsAirtimeLabel.textContent = `${I18n.t("analytics.usage_pct").replace("{pct}", dutyCyclePct.toFixed(2))}${statusSuffix}`;
    }
    if (this.dom.analyticsAirtimeMs) {
      I18n.setText(this.dom.analyticsAirtimeMs, "analytics.airtime_limit", {
        p0: Math.round(usedMs).toLocaleString(),
        p1: Math.round(budgetMs).toLocaleString(),
        p2: limitPct.toFixed(1),
      });
    }

    if (this.dom.analyticsAirtimeWarnMarker) {
      this.dom.analyticsAirtimeWarnMarker.style.left = `${warnThresholdPct}%`;
      this.dom.analyticsAirtimeWarnMarker.title = I18n.t("analytics.warning_threshold", { p0: warnThresholdPct });
    }
    if (this.dom.analyticsAirtimeWarnLabel) {
      const warnLimitPct = (limitPct * (warnThresholdPct / 100.0)).toFixed(2);
      I18n.setText(this.dom.analyticsAirtimeWarnLabel, "analytics.warning_label", { p0: warnLimitPct, p1: warnThresholdPct });
    }
    if (this.dom.analyticsAirtimeLimitLabel) {
      I18n.setText(this.dom.analyticsAirtimeLimitLabel, "analytics.legal_limit", { p0: limitPct.toFixed(1) });
    }

    if (this.dom.analyticsAirtimeFill) {
      const fillWidth = limitPct > 0 ? Math.min(Math.max((dutyCyclePct / limitPct) * 100, 0), 100) : 0;
      this.dom.analyticsAirtimeFill.style.width = `${fillWidth}%`;

      this.dom.analyticsAirtimeFill.classList.remove("normal", "warning", "danger");
      if (isCritical) {
        this.dom.analyticsAirtimeFill.classList.add("danger");
      } else if (isWarning) {
        this.dom.analyticsAirtimeFill.classList.add("warning");
      } else {
        this.dom.analyticsAirtimeFill.classList.add("normal");
      }
    }
  }
}
