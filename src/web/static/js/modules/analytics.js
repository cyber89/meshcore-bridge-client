/**
 * AnalyticsModule - Panel de métricas avanzadas, telemetría y analítica de tráfico de la malla LoRa.
 * Gestiona KPIs de red, ranking de calidad de enlace SNR/RSSI, estadísticas de repetidores y consumo de airtime (Duty Cycle).
 */

import { escapeHtml } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class AnalyticsModule {
  constructor(context) {
    this.ctx = context;
    this.dom = {};
    this.refreshTimer = null;
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.fetchAnalytics();
  }

  _bindElements() {
    this.dom = {
      btnRefreshAnalytics: document.getElementById("btnRefreshAnalytics"),

      // KPIs Principales
      kpiTotalPackets: document.getElementById("kpiTotalPackets"),
      kpiPacketsRatio: document.getElementById("kpiPacketsRatio"),
      kpiTotalNodes: document.getElementById("kpiTotalNodes"),
      kpiRepeatersCount: document.getElementById("kpiRepeatersCount"),
      kpiErrorRate: document.getElementById("kpiErrorRate"),
      kpiErrorsTotal: document.getElementById("kpiErrorsTotal"),
      kpiQueueDepth: document.getElementById("kpiQueueDepth"),
      kpiTxRate: document.getElementById("kpiTxRate"),

      // Tablas Analíticas
      analyticsTopActiveTable: document.getElementById("analyticsTopActiveTable"),
      analyticsSignalTable: document.getElementById("analyticsSignalTable"),
      analyticsRepeatersTable: document.getElementById("analyticsRepeatersTable"),

      // Salud del Sistema y Puente
      statDeduplication: document.getElementById("statDeduplication"),
      statQueueDepth: document.getElementById("statQueueDepth"),
      statSerialStatus: document.getElementById("statSerialStatus"),
      statMqttStatus: document.getElementById("statMqttStatus"),

      // Presupuesto de Airtime & Duty Cycle
      analyticsAirtimeLabel: document.getElementById("analyticsAirtimeLabel"),
      analyticsAirtimeMs: document.getElementById("analyticsAirtimeMs"),
      analyticsAirtimeFill: document.getElementById("analyticsAirtimeFill"),
    };
  }

  _bindEvents() {
    if (this.dom.btnRefreshAnalytics) {
      this.dom.btnRefreshAnalytics.addEventListener("click", () => {
        this.fetchAnalytics();
      });
    }
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    // Actualizar métricas cuando el usuario entra a la pestaña de analítica
    this.ctx.eventBus.on(EVENTS.TAB_CHANGED, (tabId) => {
      if (tabId === "tab-analytics") {
        this.fetchAnalytics();
      }
    });

    // Actualización reactiva periódica si llegan paquetes
    this.ctx.eventBus.on(EVENTS.RF_PACKET, () => {
      // Debounce suave para no saturar si hay ráfagas
      if (!this.refreshTimer) {
        this.refreshTimer = setTimeout(() => {
          this.refreshTimer = null;
          const activeTab = document.querySelector(".tab-pane.active")?.id;
          if (activeTab === "tab-analytics") {
            this.fetchAnalytics();
          }
        }, 5000);
      }
    });
  }

  async fetchAnalytics() {
    try {
      const headers = this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {};
      const [resAnalytics, resAirtime] = await Promise.all([
        fetch("/api/analytics", { headers }),
        fetch("/api/airtime/stats", { headers }).catch(() => null),
      ]);

      const dataAnalytics = await resAnalytics.json();
      let dataAirtime = null;
      if (resAirtime && resAirtime.ok) {
        dataAirtime = await resAirtime.json();
      }

      if (dataAnalytics.status === "ok" && dataAnalytics.data) {
        const payload = dataAnalytics.data;
        this.renderKpis(payload.summary || {}, payload);
        this.renderTopActiveTable(payload.top_nodes_by_traffic || []);
        this.renderSignalTable(payload.top_nodes_best_snr || [], payload.top_nodes_worst_snr || []);
        this.renderRepeatersTable(payload.top_repeaters_by_clients || []);
        this.renderBridgeHealth(payload);
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

    if (this.dom.kpiTotalPackets) {
      this.dom.kpiTotalPackets.textContent = total.toLocaleString();
    }
    if (this.dom.kpiPacketsRatio) {
      this.dom.kpiPacketsRatio.textContent = `RX: ${rx.toLocaleString()} | TX: ${tx.toLocaleString()}`;
    }

    if (this.dom.kpiTotalNodes) {
      this.dom.kpiTotalNodes.textContent = Number(summary.total_nodes || 0).toLocaleString();
    }
    if (this.dom.kpiRepeatersCount) {
      const reps = Array.isArray(rootData.top_repeaters_by_clients) ? rootData.top_repeaters_by_clients.length : 0;
      this.dom.kpiRepeatersCount.textContent = I18n.t('analytics.repeater_count').replace('{n}', reps);
    }

    if (this.dom.kpiErrorRate) {
      const rate = summary.global_error_rate_pct != null ? summary.global_error_rate_pct : 0.0;
      this.dom.kpiErrorRate.textContent = `${Number(rate).toFixed(1)}%`;
      this.dom.kpiErrorRate.style.color = rate > 5.0 ? "var(--accent-danger)" : (rate > 1.0 ? "var(--accent-warning)" : "var(--accent-success)");
    }
    if (this.dom.kpiErrorsTotal) {
      const errTotal = Number(summary.total_errors || 0);
      this.dom.kpiErrorsTotal.textContent = I18n.t('analytics.errors_acc').replace('{n}', errTotal);
    }

    if (this.dom.kpiQueueDepth) {
      const qDepth = Number(rootData.queue_depth || 0);
      this.dom.kpiQueueDepth.textContent = I18n.t('analytics.packets_count').replace('{n}', qDepth);
    }
  }

  renderTopActiveTable(nodes) {
    if (!this.dom.analyticsTopActiveTable) return;
    this.dom.analyticsTopActiveTable.textContent = "";

    if (!Array.isArray(nodes) || nodes.length === 0) {
      this.dom.analyticsTopActiveTable.innerHTML = '<tr><td colspan="5" class="text-center text-muted">No hay nodos con tráfico registrado todavía.</td></tr>';
      return;
    }

    const frag = document.createDocumentFragment();
    for (const n of nodes) {
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

      tr.innerHTML = `
        <td><strong class="font-mono text-sm">${escapeHtml(name)}</strong></td>
        <td><span class="badge-pill ${roleBadge} text-xs">${escapeHtml(role)}</span></td>
        <td class="font-mono text-xs">${rx.toLocaleString()}</td>
        <td class="font-mono text-xs">${tx.toLocaleString()}</td>
        <td class="font-mono text-xs font-semibold" style="color: var(--accent-primary);">${tot.toLocaleString()}</td>
      `;
      frag.appendChild(tr);
    }
    this.dom.analyticsTopActiveTable.appendChild(frag);
  }

  renderSignalTable(bestNodes, worstNodes) {
    if (!this.dom.analyticsSignalTable) return;
    this.dom.analyticsSignalTable.textContent = "";

    const combined = [...bestNodes];
    for (const w of worstNodes) {
      if (!combined.some((b) => b.public_key === w.public_key)) {
        combined.push(w);
      }
    }

    if (combined.length === 0) {
      this.dom.analyticsSignalTable.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No hay mediciones de SNR/RSSI registradas en la malla.</td></tr>';
      return;
    }

    // Ordenar de mejor a peor SNR
    combined.sort((a, b) => (Number(b.last_snr) || 0) - (Number(a.last_snr) || 0));

    const frag = document.createDocumentFragment();
    for (const n of combined.slice(0, 10)) {
      const tr = document.createElement("tr");
      const name = n.name || n.alias || (n.public_key ? `[${n.public_key.substring(0, 8)}]` : "Nodo");
      const snr = n.last_snr != null ? Number(n.last_snr).toFixed(1) : "--";
      const rssi = n.last_rssi != null ? `${Number(n.last_rssi)} dBm` : "--";

      let lqiStatus = I18n.t('signal.excellent');
      let lqiClass = "badge-success";
      const snrVal = Number(n.last_snr);
      if (snrVal < -10) {
        lqiStatus = I18n.t('signal.critical');
        lqiClass = "badge-danger";
      } else if (snrVal < 0) {
        lqiStatus = I18n.t('signal.weak');
        lqiClass = "badge-warning";
      } else if (snrVal < 6) {
        lqiStatus = I18n.t('signal.acceptable');
        lqiClass = "badge-primary";
      }

      tr.innerHTML = `
        <td><strong class="font-mono text-sm">${escapeHtml(name)}</strong></td>
        <td class="font-mono text-xs">${escapeHtml(snr)} dB</td>
        <td class="font-mono text-xs">${escapeHtml(rssi)}</td>
        <td><span class="badge-pill ${lqiClass} text-xs">${escapeHtml(lqiStatus)}</span></td>
      `;
      frag.appendChild(tr);
    }
    this.dom.analyticsSignalTable.appendChild(frag);
  }

  renderRepeatersTable(repeaters) {
    if (!this.dom.analyticsRepeatersTable) return;
    this.dom.analyticsRepeatersTable.textContent = "";

    if (!Array.isArray(repeaters) || repeaters.length === 0) {
      this.dom.analyticsRepeatersTable.innerHTML = '<tr><td colspan="4" class="text-center text-muted">No se detectaron repetidores o routers en la topología.</td></tr>';
      return;
    }

    const frag = document.createDocumentFragment();
    for (const r of repeaters) {
      const tr = document.createElement("tr");
      const name = r.name || r.alias || (r.public_key ? `[${r.public_key.substring(0, 8)}]` : I18n.t('common.repeater'));
      const clientCount = r.routed_clients_count != null ? r.routed_clients_count : (r.client_count || 0);
      const txPower = r.tx_power != null ? `${r.tx_power} dBm` : I18n.t('analytics.standard');
      const hopLimit = r.hop_limit != null ? I18n.t('analytics.hops_count').replace('{n}', r.hop_limit) : I18n.t('analytics.hops_count').replace('{n}', 3);

      tr.innerHTML = `
        <td><strong class="font-mono text-sm">${escapeHtml(name)}</strong></td>
        <td class="font-mono text-xs">${Number(clientCount).toLocaleString()} nodos</td>
        <td class="font-mono text-xs">${escapeHtml(txPower)}</td>
        <td class="font-mono text-xs">${escapeHtml(hopLimit)}</td>
      `;
      frag.appendChild(tr);
    }
    this.dom.analyticsRepeatersTable.appendChild(frag);
  }

  renderBridgeHealth(data) {
    if (this.dom.statDeduplication) {
      const dupCount = data.deduplication_count || 0;
      this.dom.statDeduplication.textContent = I18n.t('analytics.in_ram_dup').replace('{n}', dupCount);
    }
    if (this.dom.statQueueDepth) {
      this.dom.statQueueDepth.textContent = I18n.t('analytics.pkts_waiting').replace('{n}', data.queue_depth || 0);
    }
    if (this.dom.statSerialStatus) {
      const isSerOk = Boolean(data.serial_connected);
      this.dom.statSerialStatus.textContent = isSerOk ? I18n.t('analytics.connected_ok') : I18n.t('analytics.disconnected');
      this.dom.statSerialStatus.style.color = isSerOk ? "var(--accent-success)" : "var(--accent-danger)";
    }
    if (this.dom.statMqttStatus) {
      const isMqttOk = Boolean(data.mqtt_connected);
      this.dom.statMqttStatus.textContent = isMqttOk ? I18n.t('analytics.online_broker') : I18n.t('analytics.disconnected');
      this.dom.statMqttStatus.style.color = isMqttOk ? "var(--accent-success)" : "var(--accent-danger)";
    }
  }

  renderAirtimeStats(airtime) {
    const usedMs = Number(airtime.hourly_used_ms || 0);
    const budgetMs = Number(airtime.hourly_budget_ms || 360000);
    const dutyCyclePct = Number(airtime.hourly_duty_cycle_pct || 0.0);

    if (this.dom.analyticsAirtimeLabel) {
      this.dom.analyticsAirtimeLabel.textContent = I18n.t('analytics.usage_pct').replace('{pct}', dutyCyclePct.toFixed(2));
    }
    if (this.dom.analyticsAirtimeMs) {
      this.dom.analyticsAirtimeMs.textContent = `${usedMs.toLocaleString()} ms / ${budgetMs.toLocaleString()} ms`;
    }

    if (this.dom.analyticsAirtimeFill) {
      // Clampear el ancho visual entre 0% y 100%
      const fillWidth = Math.min(Math.max((dutyCyclePct / 10.0) * 100, 0), 100);
      this.dom.analyticsAirtimeFill.style.width = `${fillWidth}%`;

      this.dom.analyticsAirtimeFill.classList.remove("normal", "warning", "danger");
      if (dutyCyclePct >= 10.0) {
        this.dom.analyticsAirtimeFill.classList.add("danger");
      } else if (dutyCyclePct >= 1.0) {
        this.dom.analyticsAirtimeFill.classList.add("warning");
      } else {
        this.dom.analyticsAirtimeFill.classList.add("normal");
      }
    }
  }
}
