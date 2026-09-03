/**
 * SnifferModule - Consola de logs del sistema, diagnóstico de subsistemas y monitor de tramas en vivo.
 */

import { escapeHtml, debounce, MAX_SYSTEM_LOGS, MAX_RAW_PACKETS } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class SnifferModule {
  constructor(context) {
    this.ctx = context;
    this.systemLogs = [];
    this.rawPackets = [];
    this.isDebugMode = false;
    this.logsScrollPaused = false;
    this.dom = {};
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.fetchSystemLogs();
    this.fetchSubsystemsHealth();
  }

  _bindElements() {
    this.dom = {
      systemLogsFeed: document.getElementById("systemLogsFeed"),
      logLevelFilter: document.getElementById("logLevelFilter"),
      logSearchInput: document.getElementById("logSearchInput"),
      btnToggleDebugMode: document.getElementById("btnToggleDebugMode"),
      btnQuickDiag: document.getElementById("btnQuickDiag"),
      btnDownloadRawLogs: document.getElementById("btnDownloadRawLogs"),
      btnClearLogs: document.getElementById("btnClearLogs"),
      btnPauseLogsScroll: document.getElementById("btnPauseLogsScroll"),
      quickDiagPanel: document.getElementById("quickDiagPanel"),
      quickDiagBody: document.getElementById("quickDiagBody"),
      btnCloseQuickDiag: document.getElementById("btnCloseQuickDiag"),
      chipSerialHealth: document.getElementById("chipSerialHealth"),
      chipMqttHealth: document.getElementById("chipMqttHealth"),
      chipTxHealth: document.getElementById("chipTxHealth"),
      chipErrorsCount: document.getElementById("chipErrorsCount"),
    };
  }

  _bindEvents() {
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

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    this.ctx.eventBus.on(EVENTS.SYSTEM_LOG_RECV, (log) => {
      if (log) {
        this.systemLogs.push(log);
        if (this.systemLogs.length > MAX_SYSTEM_LOGS) {
          this.systemLogs.shift();
        }
        this.appendLogEntryToDom(log);
      }
    });

    this.ctx.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (payload && (payload.type === "system_log" || payload.event_type === "system_log")) {
        const logData = payload.data || payload;
        this.systemLogs.push(logData);
        if (this.systemLogs.length > MAX_SYSTEM_LOGS) {
          this.systemLogs.shift();
        }
        this.appendLogEntryToDom(logData);
      }
    });
  }

  async fetchSystemLogs() {
    try {
      const res = await fetch("/api/system/logs?limit=200", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
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
      const res = await fetch("/api/diagnostics", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        this.updateHealthChips(data.data);
      }
    } catch (e) {
      console.warn("Error actualizando salud de subsistemas:", e);
    }
  }

  updateHealthChips(diag) {
    if (!diag) return;
    const sub = diag.subsystems || {};

    if (this.dom.chipSerialHealth) {
      const isSerOk = sub.serial_companion?.connected ?? diag.serial_connected ?? diag.radio_connected ?? false;
      const portName = sub.serial_companion?.port || document.getElementById("localNodeSerialPort")?.value || "";
      if (this.ctx.updateRadioBadge) this.ctx.updateRadioBadge(isSerOk, isSerOk ? portName : "");
      const el = this.dom.chipSerialHealth.querySelector(".val");
      if (el) {
        el.textContent = isSerOk ? `Conectado (${portName || "/dev/ttyACM0"})` : "Desconectado";
        el.className = `val ${isSerOk ? "ok" : "err"}`;
      }
    }

    if (this.dom.chipMqttHealth) {
      const isMqttOk = sub.mqtt_broker?.connected ?? diag.mqtt_connected ?? false;
      const brokerName = sub.mqtt_broker?.broker || "MQTT";
      const el = this.dom.chipMqttHealth.querySelector(".val");
      if (el) {
        el.textContent = isMqttOk ? `Online (${brokerName})` : "Offline";
        el.className = `val ${isMqttOk ? "ok" : "err"}`;
      }
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
      const msg = log.message || "";
      if (levelFilter !== "ALL") {
        if (levelFilter === "SECURITY") {
          const isSec = msg.includes("[TRAFICO-SOSPECHOSO]") || msg.includes("[SEGURIDAD]") || msg.includes("403 Forbidden") || msg.includes("Unauthorized");
          if (!isSec) return false;
        } else if (levelFilter === "NET") {
          const isNet = msg.includes("[HTTP-CLIENT]") || msg.includes("[REST-API]") || msg.includes("[TCP-COMPANION]") || msg.includes("[WEBSOCKET]");
          if (!isNet) return false;
        } else if (levelFilter === "ERROR" && !["ERROR", "CRITICAL"].includes(log.level)) {
          return false;
        } else if (levelFilter === "WARNING" && !["WARNING", "WARN"].includes(log.level)) {
          return false;
        } else if (levelFilter === "INFO" && log.level !== "INFO") {
          return false;
        } else if (levelFilter === "DEBUG" && log.level !== "DEBUG") {
          return false;
        }
      }
      if (searchQuery) {
        const text = `${escapeHtml(log.message)} ${log.module} ${log.logger} ${log.exception || ""}`.toLowerCase();
        if (!text.includes(searchQuery)) return false;
      }
      return true;
    });

    this.dom.systemLogsFeed.textContent = "";
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
    const msg = log.message || "";
    const isSuspicious = msg.includes("[TRAFICO-SOSPECHOSO]");
    const isNetwork = msg.includes("[HTTP-CLIENT]") || msg.includes("[REST-API]") || msg.includes("[TCP-COMPANION]") || msg.includes("[WEBSOCKET]");

    let extraClass = "";
    if (isSuspicious) extraClass = "log-row-suspicious";
    else if (isNetwork) extraClass = "log-row-network";

    row.className = `log-row ${extraClass}`;

    const lvlLower = (log.level || "info").toLowerCase();
    const timeStr = log.iso_time ? (log.iso_time.split(" ")[1] || log.iso_time) : new Date((log.timestamp || (Date.now() / 1000)) * 1000).toLocaleTimeString();

    row.innerHTML = `
      <span class="log-time">${escapeHtml(timeStr)}</span>
      <span class="log-badge badge-lvl-${escapeHtml(lvlLower)}">${escapeHtml(log.level)}</span>
      <span class="log-mod font-mono" title="${escapeHtml(log.module || log.logger)}">${escapeHtml(log.module || log.logger || "core")}</span>
      <span class="log-msg">${escapeHtml(log.message)}</span>
      ${log.exception ? `<pre class="log-trace">${escapeHtml(log.exception)}</pre>` : ""}
    `;

    return row;
  }

  appendLogEntryToDom(log) {
    if (!this.dom.systemLogsFeed) return;
    if (this.dom.systemLogsFeed.querySelector("div[style]")) {
      this.dom.systemLogsFeed.textContent = "";
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
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
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
      await fetch("/api/system/logs", {
        method: "DELETE",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
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
    this.dom.quickDiagBody.textContent = "Ejecutando auto-diagnóstico de subsistemas...";
    try {
      const res = await fetch("/api/diagnostics", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.dom.quickDiagBody.innerHTML = `<pre>${escapeHtml(JSON.stringify(data.data, null, 2))}</pre>`;
        this.updateHealthChips(data.data);
      }
    } catch (e) {
      this.dom.quickDiagBody.innerHTML = `<span style="color: var(--accent-danger)">Error: ${escapeHtml(e.message)}</span>`;
    }
  }

  async downloadRawLogs() {
    try {
      const res = await fetch("/api/logs/download", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
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
}
