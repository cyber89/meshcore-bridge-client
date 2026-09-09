/**
 * SnifferModule - Consola de logs del sistema, diagnóstico de subsistemas y monitor de tramas LoRa en vivo.
 * Soporta vista dual (Logs vs Paquetes RF), inspector con Hex Dump Wireshark y exportación PCAP/JSON/CSV.
 */

import { escapeHtml, debounce, MAX_SYSTEM_LOGS, MAX_RAW_PACKETS } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

/**
 * Formatea un búfer binario o cadena hexadecimal al estilo estándar Wireshark / xxd.
 * Formato: 00000000  54 65 73 74 20 6d 65 73  73 61 67 65 20 66 72 6f  |Test message fro|
 */
function generateHexDump(rawHex, rawBytes) {
  let bytes = [];
  if (Array.isArray(rawBytes) || rawBytes instanceof Uint8Array) {
    bytes = Array.from(rawBytes);
  } else if (typeof rawHex === "string" && rawHex.length > 0) {
    const cleanHex = rawHex.replace(/[^0-9a-fA-F]/g, "");
    for (let i = 0; i < cleanHex.length; i += 2) {
      bytes.push(parseInt(cleanHex.substring(i, i + 2), 16));
    }
  }

  if (bytes.length === 0) {
    return "00000000                                                   |                |";
  }

  const lines = [];
  for (let i = 0; i < bytes.length; i += 16) {
    const chunk = bytes.slice(i, i + 16);
    const offsetStr = i.toString(16).padStart(8, "0");

    let hexPart1 = "";
    let hexPart2 = "";
    let asciiPart = "";

    for (let j = 0; j < 16; j++) {
      if (j < chunk.length) {
        const b = chunk[j];
        const hexByte = b.toString(16).padStart(2, "0");
        if (j < 8) {
          hexPart1 += hexByte + " ";
        } else {
          hexPart2 += hexByte + " ";
        }
        asciiPart += (b >= 32 && b <= 126) ? String.fromCharCode(b) : ".";
      } else {
        if (j < 8) {
          hexPart1 += "   ";
        } else {
          hexPart2 += "   ";
        }
        asciiPart += " ";
      }
    }

    lines.push(`${offsetStr}  ${hexPart1.padEnd(24)} ${hexPart2.padEnd(24)} |${asciiPart}|`);
  }

  return lines.join("\n");
}

export class SnifferModule {
  constructor(context) {
    this.ctx = context;
    this.systemLogs = [];
    this.rfPackets = [];
    this.isDebugMode = false;
    this.logsScrollPaused = false;
    this.isSnifferPaused = false;
    this.selectedPacketForInspect = null;
    this.dom = {};
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.fetchSystemLogs();
    this.fetchSubsystemsHealth();
    this.fetchCapturedPackets();
  }

  _bindElements() {
    this.dom = {
      // Subpestañas Dual Sniffer
      btnSubtabLogs: document.getElementById("btnSubtabLogs"),
      btnSubtabSniffer: document.getElementById("btnSubtabSniffer"),
      subpanelSystemLogs: document.getElementById("subpanelSystemLogs"),
      subpanelRfPackets: document.getElementById("subpanelRfPackets"),
      snifferPacketsBadge: document.getElementById("snifferPacketsBadge"),

      // Panel 1: Logs del Sistema
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

      // Panel 2: Monitor de Paquetes RF (LoRa Sniffer)
      btnToggleSnifferPause: document.getElementById("btnToggleSnifferPause"),
      btnClearSnifferPackets: document.getElementById("btnClearSnifferPackets"),
      btnExportPcap: document.getElementById("btnExportPcap"),
      btnExportJson: document.getElementById("btnExportJson"),
      btnExportCsv: document.getElementById("btnExportCsv"),
      snifferDirFilter: document.getElementById("snifferDirFilter"),
      snifferTypeFilter: document.getElementById("snifferTypeFilter"),
      snifferSearchInput: document.getElementById("snifferSearchInput"),
      snifferPacketsBody: document.getElementById("snifferPacketsBody"),

      // Modal Inspector de Trama LoRa
      packetInspectorModal: document.getElementById("packetInspectorModal"),
      btnClosePacketInspector: document.getElementById("btnClosePacketInspector"),
      inspectorPktIdDisplay: document.getElementById("inspectorPktIdDisplay"),
      inspectorDirBadge: document.getElementById("inspectorDirBadge"),
      inspectorTypeBadge: document.getElementById("inspectorTypeBadge"),
      inspectorTabSemantic: document.getElementById("inspectorTabSemantic"),
      inspectorTabHex: document.getElementById("inspectorTabHex"),
      inspectorTabJson: document.getElementById("inspectorTabJson"),
      inspectorPanelSemantic: document.getElementById("inspectorPanelSemantic"),
      inspectorPanelHex: document.getElementById("inspectorPanelHex"),
      inspectorPanelJson: document.getElementById("inspectorPanelJson"),
      inspFieldTime: document.getElementById("inspFieldTime"),
      inspFieldDir: document.getElementById("inspFieldDir"),
      inspFieldChannel: document.getElementById("inspFieldChannel"),
      inspFieldType: document.getElementById("inspFieldType"),
      inspFieldSender: document.getElementById("inspFieldSender"),
      inspFieldTarget: document.getElementById("inspFieldTarget"),
      inspFieldRf: document.getElementById("inspFieldRf"),
      inspFieldSize: document.getElementById("inspFieldSize"),
      inspFieldDecoded: document.getElementById("inspFieldDecoded"),
      inspHexDumpView: document.getElementById("inspHexDumpView"),
      inspJsonDumpView: document.getElementById("inspJsonDumpView"),
      btnCopyHexDump: document.getElementById("btnCopyHexDump"),
      btnCopyJsonDump: document.getElementById("btnCopyJsonDump"),
    };
  }

  _bindEvents() {
    // Alternar subpestañas Dual Sniffer
    if (this.dom.btnSubtabLogs) {
      this.dom.btnSubtabLogs.addEventListener("click", () => this.switchSubtab("logs"));
    }
    if (this.dom.btnSubtabSniffer) {
      this.dom.btnSubtabSniffer.addEventListener("click", () => this.switchSubtab("sniffer"));
    }

    // Controles de Logs del Sistema
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

    // Controles del Sniffer de Paquetes RF
    if (this.dom.btnToggleSnifferPause) {
      this.dom.btnToggleSnifferPause.addEventListener("click", () => this.toggleSnifferPause());
    }
    if (this.dom.btnClearSnifferPackets) {
      this.dom.btnClearSnifferPackets.addEventListener("click", () => this.clearCapturedPackets());
    }
    if (this.dom.btnExportPcap) {
      this.dom.btnExportPcap.addEventListener("click", () => this.exportPackets("pcap"));
    }
    if (this.dom.btnExportJson) {
      this.dom.btnExportJson.addEventListener("click", () => this.exportPackets("json"));
    }
    if (this.dom.btnExportCsv) {
      this.dom.btnExportCsv.addEventListener("click", () => this.exportPackets("csv"));
    }
    if (this.dom.snifferDirFilter) {
      this.dom.snifferDirFilter.addEventListener("change", () => this.renderFilteredPackets());
    }
    if (this.dom.snifferTypeFilter) {
      this.dom.snifferTypeFilter.addEventListener("change", () => this.renderFilteredPackets());
    }
    if (this.dom.snifferSearchInput) {
      this.dom.snifferSearchInput.addEventListener(
        "input",
        debounce(() => this.renderFilteredPackets(), 150)
      );
    }

    // Modal Inspector de Trama
    if (this.dom.btnClosePacketInspector) {
      this.dom.btnClosePacketInspector.addEventListener("click", () => this.closePacketInspector());
    }
    if (this.dom.inspectorTabSemantic) {
      this.dom.inspectorTabSemantic.addEventListener("click", () => this.switchInspectorTab("semantic"));
    }
    if (this.dom.inspectorTabHex) {
      this.dom.inspectorTabHex.addEventListener("click", () => this.switchInspectorTab("hex"));
    }
    if (this.dom.inspectorTabJson) {
      this.dom.inspectorTabJson.addEventListener("click", () => this.switchInspectorTab("json"));
    }
    if (this.dom.btnCopyHexDump) {
      this.dom.btnCopyHexDump.addEventListener("click", () => this.copyHexDumpToClipboard());
    }
    if (this.dom.btnCopyJsonDump) {
      this.dom.btnCopyJsonDump.addEventListener("click", () => this.copyJsonDumpToClipboard());
    }
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    this.ctx.eventBus.on(EVENTS.RF_PACKET, (pkt) => {
      if (pkt) {
        this.onRfPacketReceived(pkt);
      }
    });

    this.ctx.eventBus.on(EVENTS.SYSTEM_LOG, (logData) => {
      if (!logData) return;
      this.systemLogs.push(logData);
      if (this.systemLogs.length > MAX_SYSTEM_LOGS) {
        this.systemLogs.shift();
      }
      this.appendLogEntryToDom(logData);
    });

    this.ctx.eventBus.on(EVENTS.METRICS_UPDATE, (payload) => {
      if (payload && payload.radio_connected != null && this.dom.chipSerialHealth) {
        const isSerOk = Boolean(payload.radio_connected);
        const portName = payload.radio_port || "";
        const el = this.dom.chipSerialHealth.querySelector(".val");
        if (el) {
          el.textContent = isSerOk ? `Conectado (${portName || "/dev/ttyACM0"})` : "Desconectado";
          el.className = `val ${isSerOk ? "ok" : "err"}`;
        }
      }
    });
  }

  switchSubtab(target) {
    const isLogs = target === "logs";
    if (this.dom.btnSubtabLogs) this.dom.btnSubtabLogs.classList.toggle("active", isLogs);
    if (this.dom.btnSubtabSniffer) this.dom.btnSubtabSniffer.classList.toggle("active", !isLogs);
    if (this.dom.subpanelSystemLogs) this.dom.subpanelSystemLogs.classList.toggle("hidden", !isLogs);
    if (this.dom.subpanelRfPackets) this.dom.subpanelRfPackets.classList.toggle("hidden", isLogs);

    if (!isLogs) {
      this.renderFilteredPackets();
    }
  }

  // ================================================================
  // Módulo de Paquetes RF (LoRa Sniffer)
  // ================================================================

  async fetchCapturedPackets() {
    try {
      const res = await fetch("/api/packets?limit=200", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && Array.isArray(data.data)) {
        this.rfPackets = data.data;
        this.updateSnifferBadge();
        this.renderFilteredPackets();
      }
    } catch (e) {
      console.warn("Error cargando paquetes RF iniciales:", e);
    }
  }

  onRfPacketReceived(pkt) {
    this.rfPackets.push(pkt);
    if (this.rfPackets.length > MAX_RAW_PACKETS) {
      this.rfPackets.shift();
    }
    this.updateSnifferBadge();

    if (!this.isSnifferPaused && this.dom.subpanelRfPackets && !this.dom.subpanelRfPackets.classList.contains("hidden")) {
      this.renderFilteredPackets();
    }
  }

  updateSnifferBadge() {
    if (this.dom.snifferPacketsBadge) {
      this.dom.snifferPacketsBadge.textContent = this.rfPackets.length;
    }
  }

  toggleSnifferPause() {
    this.isSnifferPaused = !this.isSnifferPaused;
    if (this.dom.btnToggleSnifferPause) {
      this.dom.btnToggleSnifferPause.innerHTML = this.isSnifferPaused
        ? '<span data-lucide="play" data-size="14"></span> Reanudar Captura'
        : '<span data-lucide="pause" data-size="14"></span> Pausar Captura';
      this.dom.btnToggleSnifferPause.className = this.isSnifferPaused
        ? "btn-secondary btn-sm"
        : "btn-outline btn-sm";
    }
  }

  async clearCapturedPackets() {
    try {
      await fetch("/api/packets", {
        method: "DELETE",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      this.rfPackets = [];
      this.updateSnifferBadge();
      this.renderFilteredPackets();
    } catch (e) {
      console.warn("Error limpiando búfer de paquetes:", e);
    }
  }

  async exportPackets(format) {
    try {
      const res = await fetch(`/api/packets/export?format=${encodeURIComponent(format)}`, {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status !== "ok") {
        alert("Error exportando paquetes: " + (data.message || data.title || "Fallo en servidor"));
        return;
      }

      let blob;
      if (format === "pcap" && data.base64_data) {
        const binStr = atob(data.base64_data);
        const len = binStr.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) {
          bytes[i] = binStr.charCodeAt(i);
        }
        blob = new Blob([bytes], { type: data.mime_type || "application/vnd.tcpdump.pcap" });
      } else {
        blob = new Blob([data.text_data || ""], { type: data.mime_type || "text/plain;charset=utf-8" });
      }

      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = data.filename || `meshcore_packets_${Date.now()}.${format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e) {
      alert("Error descargando exportación de paquetes: " + e.message);
    }
  }

  renderFilteredPackets() {
    if (!this.dom.snifferPacketsBody) return;
    const dirFilter = (this.dom.snifferDirFilter?.value || "").toLowerCase().trim();
    const typeFilter = (this.dom.snifferTypeFilter?.value || "").toUpperCase().trim();
    const searchQuery = (this.dom.snifferSearchInput?.value || "").toLowerCase().trim();

    const filtered = this.rfPackets.filter((pkt) => {
      if (dirFilter && (pkt.direction || "").toLowerCase() !== dirFilter) {
        return false;
      }
      if (typeFilter) {
        const pktType = (pkt.packet_type || "").toUpperCase();
        if (!pktType.includes(typeFilter)) return false;
      }
      if (searchQuery) {
        const fullText = `${pkt.sender || ""} ${pkt.sender_name || ""} ${pkt.target || ""} ${pkt.text || ""} ${pkt.packet_type || ""}`.toLowerCase();
        if (!fullText.includes(searchQuery)) return false;
      }
      return true;
    });

    this.dom.snifferPacketsBody.textContent = "";
    if (filtered.length === 0) {
      const emptyRow = document.createElement("tr");
      emptyRow.innerHTML = '<td colspan="11" class="text-center text-muted" style="padding: 24px;">No hay paquetes que coincidan con los filtros actuales.</td>';
      this.dom.snifferPacketsBody.appendChild(emptyRow);
      return;
    }

    const frag = document.createDocumentFragment();
    // Renderizar orden cronológico inverso (los más recientes primero)
    const visiblePackets = filtered.slice(-200).reverse();

    for (const pkt of visiblePackets) {
      const tr = document.createElement("tr");

      const isRx = (pkt.direction || "").toLowerCase() === "rx";
      const dirBadgeClass = isRx ? "badge-dir-rx" : "badge-dir-tx";
      const dirLabel = isRx ? "RX" : "TX";

      const pType = (pkt.packet_type || "PACKET").toUpperCase();
      let typeBadgeClass = "badge-secondary";
      if (pType.includes("CHAT")) typeBadgeClass = "badge-type-chat";
      else if (pType.includes("ADVERT")) typeBadgeClass = "badge-type-advert";
      else if (pType.includes("TELEM")) typeBadgeClass = "badge-type-telemetry";
      else if (pType.includes("ADMIN")) typeBadgeClass = "badge-type-admin";
      else if (pType.includes("ACK")) typeBadgeClass = "badge-type-ack";

      const timeStr = pkt.iso_time ? (pkt.iso_time.split("T")[1]?.split(".")[0] || pkt.iso_time) : new Date((pkt.timestamp || (Date.now() / 1000)) * 1000).toLocaleTimeString();

      const senderDisplay = pkt.sender_name || (pkt.sender ? `[${pkt.sender.substring(0, 8)}]` : "--");
      const targetDisplay = pkt.target === "broadcast" ? "📢 Broadcast" : (pkt.target ? `[${pkt.target.substring(0, 8)}]` : "--");

      let rfMetrics = "--";
      if (pkt.snr != null || pkt.rssi != null) {
        rfMetrics = `${pkt.snr != null ? pkt.snr + " dB" : "--"} / ${pkt.rssi != null ? pkt.rssi + " dBm" : "--"}`;
      }

      const summaryText = pkt.text || (pkt.payload_dict ? JSON.stringify(pkt.payload_dict).substring(0, 50) : "--");

      tr.innerHTML = `
        <td class="font-mono text-muted text-xs">#${escapeHtml(String(pkt.packet_id || 0))}</td>
        <td class="font-mono text-xs">${escapeHtml(timeStr)}</td>
        <td><span class="${dirBadgeClass}">${dirLabel}</span></td>
        <td><span class="badge-pill ${typeBadgeClass} text-xs">${escapeHtml(pType)}</span></td>
        <td class="font-mono text-xs">#${escapeHtml(String(pkt.channel_idx != null ? pkt.channel_idx : 0))}</td>
        <td class="font-mono text-xs" title="${escapeHtml(pkt.sender || "")}">${escapeHtml(senderDisplay)}</td>
        <td class="font-mono text-xs" title="${escapeHtml(pkt.target || "")}">${escapeHtml(targetDisplay)}</td>
        <td class="font-mono text-xs">${escapeHtml(rfMetrics)}</td>
        <td class="font-mono text-xs">${escapeHtml(String(pkt.size_bytes || 0))} B</td>
        <td class="text-xs truncate" style="max-width: 280px;" title="${escapeHtml(pkt.text || "")}">${escapeHtml(summaryText)}</td>
        <td style="text-align: center;">
          <button type="button" class="btn-icon btn-xs" title="Inspeccionar trama" data-pkt-id="${escapeHtml(String(pkt.packet_id))}">
            🔍
          </button>
        </td>
      `;

      const inspectBtn = tr.querySelector("button[data-pkt-id]");
      if (inspectBtn) {
        inspectBtn.addEventListener("click", () => this.openPacketInspector(pkt));
      }

      frag.appendChild(tr);
    }

    this.dom.snifferPacketsBody.appendChild(frag);
  }

  // ================================================================
  // Modal Inspector de Tramas LoRa
  // ================================================================

  openPacketInspector(pkt) {
    if (!this.dom.packetInspectorModal) return;
    this.selectedPacketForInspect = pkt;

    // Encabezado
    if (this.dom.inspectorPktIdDisplay) {
      this.dom.inspectorPktIdDisplay.textContent = `#${pkt.packet_id || 0}`;
    }
    if (this.dom.inspectorDirBadge) {
      const isRx = (pkt.direction || "").toLowerCase() === "rx";
      this.dom.inspectorDirBadge.textContent = isRx ? "RX (Entrante)" : "TX (Saliente)";
      this.dom.inspectorDirBadge.className = isRx ? "badge-pill badge-success" : "badge-pill badge-primary";
    }
    if (this.dom.inspectorTypeBadge) {
      this.dom.inspectorTypeBadge.textContent = (pkt.packet_type || "PACKET").toUpperCase();
    }

    // Panel Semántico
    if (this.dom.inspFieldTime) this.dom.inspFieldTime.textContent = pkt.iso_time || new Date().toISOString();
    if (this.dom.inspFieldDir) this.dom.inspFieldDir.textContent = (pkt.direction || "").toUpperCase();
    if (this.dom.inspFieldChannel) this.dom.inspFieldChannel.textContent = `Canal #${pkt.channel_idx != null ? pkt.channel_idx : 0}`;
    if (this.dom.inspFieldType) this.dom.inspFieldType.textContent = pkt.packet_type || "PACKET";
    if (this.dom.inspFieldSender) this.dom.inspFieldSender.textContent = `${pkt.sender_name ? pkt.sender_name + " " : ""}(${pkt.sender || "desconocido"})`;
    if (this.dom.inspFieldTarget) this.dom.inspFieldTarget.textContent = pkt.target || "broadcast";

    let rfStr = `SNR: ${pkt.snr != null ? pkt.snr + " dB" : "N/A"} | RSSI: ${pkt.rssi != null ? pkt.rssi + " dBm" : "N/A"}`;
    if (pkt.lqi_score != null) rfStr += ` | LQI: ${pkt.lqi_score.toFixed(1)}% (${pkt.lqi_status || "N/A"})`;
    if (this.dom.inspFieldRf) this.dom.inspFieldRf.textContent = rfStr;

    if (this.dom.inspFieldSize) this.dom.inspFieldSize.textContent = `${pkt.size_bytes || 0} bytes`;

    let decodedDetails = [];
    if (pkt.text) decodedDetails.push(`Texto: "${pkt.text}"`);
    if (pkt.payload_dict && typeof pkt.payload_dict === "object") {
      decodedDetails.push(JSON.stringify(pkt.payload_dict, null, 2));
    }
    if (this.dom.inspFieldDecoded) {
      this.dom.inspFieldDecoded.textContent = decodedDetails.length > 0 ? decodedDetails.join("\n\n") : "(Sin payload decodificado)";
    }

    // Panel Hex Dump Wireshark Style
    if (this.dom.inspHexDumpView) {
      const hexDump = generateHexDump(pkt.raw_hex || "", pkt.raw_bytes);
      this.dom.inspHexDumpView.textContent = hexDump;
    }

    // Panel JSON Crudo
    if (this.dom.inspJsonDumpView) {
      this.dom.inspJsonDumpView.textContent = JSON.stringify(pkt, null, 2);
    }

    this.switchInspectorTab("semantic");
    this.dom.packetInspectorModal.classList.remove("hidden");
  }

  closePacketInspector() {
    if (this.dom.packetInspectorModal) {
      this.dom.packetInspectorModal.classList.add("hidden");
    }
    this.selectedPacketForInspect = null;
  }

  switchInspectorTab(tab) {
    if (this.dom.inspectorTabSemantic) this.dom.inspectorTabSemantic.classList.toggle("active", tab === "semantic");
    if (this.dom.inspectorTabHex) this.dom.inspectorTabHex.classList.toggle("active", tab === "hex");
    if (this.dom.inspectorTabJson) this.dom.inspectorTabJson.classList.toggle("active", tab === "json");

    if (this.dom.inspectorPanelSemantic) this.dom.inspectorPanelSemantic.classList.toggle("hidden", tab !== "semantic");
    if (this.dom.inspectorPanelHex) this.dom.inspectorPanelHex.classList.toggle("hidden", tab !== "hex");
    if (this.dom.inspectorPanelJson) this.dom.inspectorPanelJson.classList.toggle("hidden", tab !== "json");
  }

  copyHexDumpToClipboard() {
    if (this.dom.inspHexDumpView && navigator.clipboard) {
      navigator.clipboard.writeText(this.dom.inspHexDumpView.textContent);
      if (this.dom.btnCopyHexDump) {
        const orig = this.dom.btnCopyHexDump.textContent;
        this.dom.btnCopyHexDump.textContent = "✓ ¡Copiado!";
        setTimeout(() => { this.dom.btnCopyHexDump.textContent = orig; }, 1500);
      }
    }
  }

  copyJsonDumpToClipboard() {
    if (this.dom.inspJsonDumpView && navigator.clipboard) {
      navigator.clipboard.writeText(this.dom.inspJsonDumpView.textContent);
      if (this.dom.btnCopyJsonDump) {
        const orig = this.dom.btnCopyJsonDump.textContent;
        this.dom.btnCopyJsonDump.textContent = "✓ ¡Copiado!";
        setTimeout(() => { this.dom.btnCopyJsonDump.textContent = orig; }, 1500);
      }
    }
  }

  // ================================================================
  // Logs del Sistema y Diagnóstico
  // ================================================================

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
      const portName = sub.serial_companion?.port || diag.radio_port || diag.serial_port || "";
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

  matchesLogFilter(log) {
    if (!log) return false;
    const levelFilter = this.dom.logLevelFilter?.value || "ALL";
    const searchQuery = (this.dom.logSearchInput?.value || "").toLowerCase().trim();
    const msg = log.message || "";

    if (levelFilter !== "ALL") {
      if (levelFilter === "RF") {
        const isRf = msg.includes("[RX-") || msg.includes("[TX-") || msg.includes("[NODO-DESCUBIERTO]") || msg.includes("[ESTACIÓN LOCAL]") || msg.includes("Advertisement recibido");
        if (!isRf) return false;
      } else if (levelFilter === "SECURITY") {
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
      const text = `${msg} ${log.module || ""} ${log.logger || ""} ${log.exception || ""}`.toLowerCase();
      if (!text.includes(searchQuery)) return false;
    }

    return true;
  }

  renderFilteredLogs() {
    if (!this.dom.systemLogsFeed) return;
    const filtered = this.systemLogs.filter((log) => this.matchesLogFilter(log));

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
    const isRf = msg.includes("[RX-") || msg.includes("[TX-") || msg.includes("[NODO-DESCUBIERTO]") || msg.includes("[ESTACIÓN LOCAL]");

    let extraClass = "";
    if (isSuspicious) extraClass = "log-row-suspicious";
    else if (isNetwork) extraClass = "log-row-network";
    else if (isRf) extraClass = "log-row-rf";

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
    if (!this.dom.systemLogsFeed || !this.matchesLogFilter(log)) return;
    if (this.dom.systemLogsFeed.querySelector("div[style]")) {
      this.dom.systemLogsFeed.textContent = "";
    }
    const el = this.createLogElement(log);
    this.dom.systemLogsFeed.appendChild(el);
    while (this.dom.systemLogsFeed.children.length > MAX_SYSTEM_LOGS) {
      this.dom.systemLogsFeed.removeChild(this.dom.systemLogsFeed.firstElementChild);
    }
    if (!this.logsScrollPaused) {
      this.dom.systemLogsFeed.scrollTop = this.dom.systemLogsFeed.scrollHeight;
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
