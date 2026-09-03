/**
 * SettingsModule - Gestión de parámetros RF del transceptor local, administración de canales,
 * importación/exportación de contactos y diagnósticos preflight.
 */

import { escapeHtml, getHardwarePowerLimits, REGION_FREQUENCIES, debounce } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class SettingsModule {
  constructor(context) {
    this.ctx = context;
    this.channelsList = [];
    this._localCliHistory = [];
    this._localCliHistoryIdx = -1;
    this.dom = {};
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.fetchChannels();
    this.fetchLocalNodeConfig();
    window.showQrModal = (title, uri, rawJson) => this.showQrModal(title, uri, rawJson);
  }

  _bindElements() {
    this.dom = {
      channelListUi: document.getElementById("channelListUi"),
      sidebarChannelList: document.getElementById("sidebarChannelList"),
      btnToggleChannelsMobile: document.getElementById("btnToggleChannelsMobile"),
      btnAddChannel: document.getElementById("btnAddChannel"),
      createChannelModal: document.getElementById("createChannelModal"),
      btnCloseCreateChannelModal: document.getElementById("btnCloseCreateChannelModal"),
      btnCancelCreateChannel: document.getElementById("btnCancelCreateChannel"),
      createChannelForm: document.getElementById("createChannelForm"),
      chModalIndex: document.getElementById("chModalIndex"),
      chModalName: document.getElementById("chModalName"),
      chModalPsk: document.getElementById("chModalPsk"),
      btnGenRandomPsk: document.getElementById("btnGenRandomPsk"),
      btnHeaderAddContact: document.getElementById("btnHeaderAddContact"),
      createContactModal: document.getElementById("createContactModal"),
      btnCloseCreateContactModal: document.getElementById("btnCloseCreateContactModal"),
      btnCancelCreateContact: document.getElementById("btnCancelCreateContact"),
      createContactForm: document.getElementById("createContactForm"),
      contactModalPubKey: document.getElementById("contactModalPubKey"),
      contactModalName: document.getElementById("contactModalName"),
      qrShareModal: document.getElementById("qrShareModal"),
      btnCloseQrModal: document.getElementById("btnCloseQrShareModal"),
      btnCloseQrModalAction: document.getElementById("btnCloseQrModalAction"),
      qrModalTitle: document.getElementById("qrShareTitle"),
      qrCanvas: document.getElementById("qrShareCanvas"),
      qrUriDisplay: document.getElementById("qrShareUri"),
      qrShareJson: document.getElementById("qrShareJson"),
      btnCopyQrUri: document.getElementById("btnCopyQrUri"),
      btnDownloadQrJson: document.getElementById("btnDownloadQrJson"),
      localRadioForm: document.getElementById("localRadioForm"),
      localOwnerPosForm: document.getElementById("localOwnerPosForm"),
      localTerminalForm: document.getElementById("localTerminalForm"),
      localTerminalInput: document.getElementById("localTerminalInput"),
      localTerminalOutput: document.getElementById("localTerminalOutput"),
      inputBridgeApiKey: document.getElementById("inputBridgeApiKey"),
      btnSaveBridgeApiKey: document.getElementById("btnSaveBridgeApiKey"),
      btnClearBridgeApiKey: document.getElementById("btnClearBridgeApiKey"),
      apiKeyStatusHint: document.getElementById("apiKeyStatusHint"),
      inputLocalTileUrl: document.getElementById("inputLocalTileUrl"),
      btnSaveMapSettings: document.getElementById("btnSaveMapSettings"),
    };
  }

  _bindEvents() {
    // 1. Mobile Channel Drawer Toggle
    if (this.dom.btnToggleChannelsMobile && this.dom.sidebarChannelList) {
      this.dom.btnToggleChannelsMobile.addEventListener("click", () => {
        this.dom.sidebarChannelList.classList.toggle("mobile-open");
      });
    }

    // 2. Crear Canal Modal
    const openCreateChannel = () => {
      if (!this.dom.createChannelModal) return;
      this.dom.createChannelModal.classList.remove("hidden");
      if (this.dom.chModalName) this.dom.chModalName.value = "";
      if (this.dom.chModalPsk) this.dom.chModalPsk.value = this.generateRandomHex(32);
      if (this.dom.chModalName) this.dom.chModalName.focus();
    };
    const closeCreateChannel = () => {
      if (this.dom.createChannelModal) this.dom.createChannelModal.classList.add("hidden");
    };

    if (this.dom.btnAddChannel) this.dom.btnAddChannel.addEventListener("click", openCreateChannel);
    if (this.dom.btnCloseCreateChannelModal) this.dom.btnCloseCreateChannelModal.addEventListener("click", closeCreateChannel);
    if (this.dom.btnCancelCreateChannel) this.dom.btnCancelCreateChannel.addEventListener("click", closeCreateChannel);

    if (this.dom.btnGenRandomPsk) {
      this.dom.btnGenRandomPsk.addEventListener("click", () => {
        if (this.dom.chModalPsk) this.dom.chModalPsk.value = this.generateRandomHex(32);
      });
    }

    if (this.dom.createChannelForm) {
      this.dom.createChannelForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const index = parseInt(this.dom.chModalIndex.value, 10);
        const name = this.dom.chModalName.value.trim();
        const psk = this.dom.chModalPsk.value.trim();
        if (!name) return;

        try {
          const res = await fetch("/api/channels", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ index, name, psk }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            closeCreateChannel();
            await this.fetchChannels();
            if (this.ctx.switchChannel) this.ctx.switchChannel(index);
            if (this.ctx.showToast) this.ctx.showToast(`✅ Canal ${index} (${escapeHtml(name)}) guardado y sincronizado`, "success");
          } else {
            alert(`Error guardando canal: ${data.message || "Fallo desconocido"}`);
          }
        } catch (err) {
          alert(`Error de red al guardar canal: ${err.message}`);
        }
      });
    }

    // 3. Crear Contacto Modal
    const openCreateContact = () => {
      if (!this.dom.createContactModal) return;
      this.dom.createContactModal.classList.remove("hidden");
      if (this.dom.contactModalPubKey) this.dom.contactModalPubKey.value = "";
      if (this.dom.contactModalName) this.dom.contactModalName.value = "";
      if (this.dom.contactModalPubKey) this.dom.contactModalPubKey.focus();
    };
    const closeCreateContact = () => {
      if (this.dom.createContactModal) this.dom.createContactModal.classList.add("hidden");
    };

    if (this.dom.btnAddContact) this.dom.btnAddContact.addEventListener("click", openCreateContact);
    if (this.dom.btnHeaderAddContact) this.dom.btnHeaderAddContact.addEventListener("click", openCreateContact);
    if (this.dom.btnCloseCreateContactModal) this.dom.btnCloseCreateContactModal.addEventListener("click", closeCreateContact);
    if (this.dom.btnCancelCreateContact) this.dom.btnCancelCreateContact.addEventListener("click", closeCreateContact);

    if (this.dom.createContactForm) {
      this.dom.createContactForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const pubkey = this.dom.contactModalPubKey.value.trim();
        const name = this.dom.contactModalName.value.trim();
        const role = this.dom.contactModalRole ? this.dom.contactModalRole.value : "CLIENT";
        if (!pubkey) return;

        try {
          const res = await fetch("/api/contacts", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ public_key: pubkey, name: name, alias: name, role: role }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            closeCreateContact();
            if (this.ctx.fetchNodes) await this.ctx.fetchNodes();
            if (this.ctx.setDmTarget) this.ctx.setDmTarget(pubkey, name || pubkey);
            if (this.ctx.showToast) this.ctx.showToast(`✅ Contacto ${name || pubkey.slice(0, 8)} agregado`, "success");
          } else {
            alert(`Error agregando contacto: ${data.message || "Fallo desconocido"}`);
          }
        } catch (err) {
          alert(`Error de red al agregar contacto: ${err.message}`);
        }
      });
    }

    // 4. Modal QR
    if (this.dom.btnCloseQrModal) {
      this.dom.btnCloseQrModal.addEventListener("click", () => {
        if (this.dom.qrShareModal) this.dom.qrShareModal.classList.add("hidden");
      });
    }
    if (this.dom.btnCloseQrModalAction) {
      this.dom.btnCloseQrModalAction.addEventListener("click", () => {
        if (this.dom.qrShareModal) this.dom.qrShareModal.classList.add("hidden");
      });
    }
    if (this.dom.btnCopyQrUri) {
      this.dom.btnCopyQrUri.addEventListener("click", () => {
        const uri = this.dom.qrUriDisplay ? (this.dom.qrUriDisplay.value || this.dom.qrUriDisplay.textContent || "") : "";
        if (uri) {
          navigator.clipboard.writeText(uri);
          if (this.ctx.showToast) this.ctx.showToast("📋 Enlace URI copiado al portapapeles", "success");
        }
      });
    }
    if (this.dom.btnDownloadQrJson) {
      this.dom.btnDownloadQrJson.addEventListener("click", () => {
        const json = this.dom.qrShareJson ? this.dom.qrShareJson.value : "";
        if (json) {
          const blob = new Blob([json], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = "meshcore_share.json";
          a.click();
          URL.revokeObjectURL(url);
        }
      });
    }

    // 5. Navegación subpestañas locales
    document.querySelectorAll(".local-subtab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".local-subtab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".local-settings-subpanel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const target = btn.getAttribute("data-subtab");
        const panel = document.getElementById(target);
        if (panel) panel.classList.add("active");
        if (target === "local-radio" || target === "local-telemetry" || target === "local-owner-pos") {
          this.fetchLocalNodeConfig();
        }
      });
    });

    const regionSelect = document.getElementById("localRegion");
    const freqInput = document.getElementById("localFreq");
    if (regionSelect && freqInput) {
      regionSelect.addEventListener("change", (e) => {
        const reg = e.target.value;
        if (REGION_FREQUENCIES[reg]) {
          freqInput.value = REGION_FREQUENCIES[reg];
          const sumFreq = document.getElementById("localSummaryFreq");
          if (sumFreq) sumFreq.textContent = `${REGION_FREQUENCIES[reg]} MHz`;
        }
      });
    }

    const txSlider = document.getElementById("localTxPower");
    const txVal = document.getElementById("localTxPowerVal");
    if (txSlider && txVal) {
      txSlider.addEventListener("input", (e) => {
        txVal.textContent = `${e.target.value} dBm`;
      });
    }

    if (this.dom.localRadioForm) {
      this.dom.localRadioForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.saveLocalRadioConfig();
      });
    }

    if (this.dom.localOwnerPosForm) {
      this.dom.localOwnerPosForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.saveLocalIdentityAndPosition();
      });
    }

    // Gestión de API Key
    if (this.dom.inputBridgeApiKey) {
      this.dom.inputBridgeApiKey.value = localStorage.getItem("meshcore_bridge_api_key") || "";
    }
    if (this.dom.btnSaveBridgeApiKey && this.dom.inputBridgeApiKey) {
      this.dom.btnSaveBridgeApiKey.addEventListener("click", () => {
        const val = this.dom.inputBridgeApiKey.value.trim();
        if (val) {
          localStorage.setItem("meshcore_bridge_api_key", val);
          if (this.dom.apiKeyStatusHint) {
            this.dom.apiKeyStatusHint.classList.remove("hidden");
            this.dom.apiKeyStatusHint.textContent = "✓ API Key guardada con éxito en este navegador";
          }
          if (this.ctx.showToast) this.ctx.showToast("🔑 API Key guardada en el navegador", "success");
        } else {
          localStorage.removeItem("meshcore_bridge_api_key");
          if (this.dom.apiKeyStatusHint) {
            this.dom.apiKeyStatusHint.classList.remove("hidden");
            this.dom.apiKeyStatusHint.textContent = "ℹ️ Clave eliminada (modo sin autenticación)";
          }
          if (this.ctx.showToast) this.ctx.showToast("ℹ️ API Key eliminada", "info");
        }
      });
    }
    if (this.dom.btnClearBridgeApiKey && this.dom.inputBridgeApiKey) {
      this.dom.btnClearBridgeApiKey.addEventListener("click", () => {
        this.dom.inputBridgeApiKey.value = "";
        localStorage.removeItem("meshcore_bridge_api_key");
        if (this.dom.apiKeyStatusHint) {
          this.dom.apiKeyStatusHint.classList.remove("hidden");
          this.dom.apiKeyStatusHint.textContent = "ℹ️ API Key eliminada";
        }
        if (this.ctx.showToast) this.ctx.showToast("ℹ️ API Key eliminada de este navegador", "info");
      });
    }
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    this.ctx.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (!payload || typeof payload !== "object") return;
      if (payload.type === "channels_updated" || payload.event_type === "channels_updated") {
        if (Array.isArray(payload.data)) {
          this.renderChannelsList(payload.data);
        } else {
          this.fetchChannels();
        }
      }
    });
  }

  generateRandomHex(length = 32) {
    const chars = "0123456789abcdef";
    let res = "";
    for (let i = 0; i < length; i++) {
      res += chars[Math.floor(Math.random() * chars.length)];
    }
    return res;
  }

  async fetchChannels() {
    try {
      const res = await fetch("/api/channels", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && Array.isArray(data.data)) {
        this.channelsList = data.data;
        this.renderChannelsList(data.data);
      }
    } catch (e) {
      console.warn("Error cargando canales:", e);
    }
  }

  renderChannelsList(channels) {
    const listEl = this.dom.channelListUi || document.getElementById("channelListUi");
    if (!listEl) return;
    listEl.textContent = "";

    const activeIdx = this.ctx.activeChannelIdx ?? 0;

    channels.forEach((ch) => {
      const li = document.createElement("li");
      const isActive = ch.index === activeIdx && !this.ctx.activeDmTarget;
      li.className = `channel-item ${isActive ? "active" : ""}`;
      li.setAttribute("data-channel-idx", String(ch.index));
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", isActive ? "true" : "false");
      li.innerHTML = `
        <span class="ch-badge font-mono">Ch ${ch.index}</span>
        <span class="ch-name">${escapeHtml(ch.name || (ch.index === 0 ? "Public / Broadcast" : `Canal ${ch.index}`))}</span>
        <span class="ch-lock" title="${ch.index === 0 ? "Canal Público" : "Canal Cifrado"}">
          <span data-lucide="${ch.index === 0 ? "unlock" : "lock"}" data-size="13"></span>
        </span>
      `;
      li.addEventListener("click", () => {
        if (this.ctx.switchChannel) this.ctx.switchChannel(ch.index);
        if (this.dom.sidebarChannelList) this.dom.sidebarChannelList.classList.remove("mobile-open");
      });
      listEl.appendChild(li);
    });

    if (window.initLucideIcons) {
      window.initLucideIcons(listEl);
    }
  }

  async fetchLocalNodeConfig() {
    try {
      const res = await fetch("/api/config", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        this.populateLocalConfig(data.data);
      }
    } catch (e) {
      console.warn("Error obteniendo configuración local:", e);
    }
  }

  populateLocalConfig(cfg) {
    if (!cfg) return;
    const nameInput = document.getElementById("localNodeName");
    if (nameInput && cfg.name) nameInput.value = cfg.name;

    const pkInput = document.getElementById("localNodePubkey");
    if (pkInput && cfg.public_key) {
      pkInput.value = cfg.public_key;
      this.ctx.localNodePubkey = cfg.public_key.toLowerCase();
    }

    // Parámetros de radio
    const freqInput = document.getElementById("localFreq");
    if (freqInput && cfg.frequency) freqInput.value = cfg.frequency;

    const sfInput = document.getElementById("localSf");
    if (sfInput && cfg.spreading_factor) sfInput.value = cfg.spreading_factor;

    const bwInput = document.getElementById("localBw");
    if (bwInput && cfg.bandwidth) bwInput.value = cfg.bandwidth;

    const crInput = document.getElementById("localCr");
    if (crInput && cfg.coding_rate) crInput.value = cfg.coding_rate;

    const pwrInput = document.getElementById("localTxPower");
    const pwrVal = document.getElementById("localTxPowerVal");
    if (pwrInput && cfg.tx_power != null) {
      pwrInput.value = cfg.tx_power;
      if (pwrVal) pwrVal.textContent = `${cfg.tx_power} dBm`;
    }

    // Posición GPS
    const latInput = document.getElementById("localGpsLat");
    if (latInput && cfg.latitude != null) latInput.value = cfg.latitude;

    const lonInput = document.getElementById("localGpsLon");
    if (lonInput && cfg.longitude != null) lonInput.value = cfg.longitude;

    const altInput = document.getElementById("localGpsAlt");
    if (altInput && cfg.altitude != null) altInput.value = cfg.altitude;

    // Tarjetas de Telemetría en Vivo
    const elBat = document.getElementById("localBatValue");
    if (elBat) elBat.textContent = cfg.battery_pct != null ? `${cfg.battery_pct} %` : "100 % (USB)";

    const elVolt = document.getElementById("localVoltValue");
    if (elVolt) elVolt.textContent = cfg.voltage != null ? `${cfg.voltage} V` : (cfg.battery_mv ? `${(cfg.battery_mv / 1000).toFixed(2)} V` : "5.00 V");

    const elClock = document.getElementById("localClockValue");
    if (elClock) elClock.textContent = cfg.clock || (cfg.device_epoch_time ? new Date(cfg.device_epoch_time * 1000).toLocaleTimeString() : "--:--:--");

    const elUptime = document.getElementById("localUptimeValue");
    if (elUptime) elUptime.textContent = cfg.uptime_str || (cfg.uptime ? `${cfg.uptime} s` : "--");

    const elAirtime = document.getElementById("localAirtimeValue");
    if (elAirtime) elAirtime.textContent = cfg.airtime_ms != null ? `${cfg.airtime_ms} ms` : "--";

    const elDuty = document.getElementById("localAirtimeDuty");
    if (elDuty) elDuty.textContent = `Duty Cycle: ${cfg.duty_cycle_pct != null ? cfg.duty_cycle_pct : 0}%`;

    const elSnr = document.getElementById("localSnrValue");
    if (elSnr) elSnr.textContent = cfg.last_snr != null ? `${cfg.last_snr} dB` : "Local";

    const elRssi = document.getElementById("localRssiValue");
    if (elRssi) elRssi.textContent = `RSSI: ${cfg.last_rssi != null ? `${cfg.last_rssi} dBm` : "Local"}`;

    const elNoise = document.getElementById("localNoiseValue");
    if (elNoise) elNoise.textContent = cfg.noise_floor_dbm != null ? `${cfg.noise_floor_dbm} dBm` : "--";

    const elPkts = document.getElementById("localPacketsValue");
    if (elPkts) elPkts.textContent = `${cfg.tx_count ?? 0} TX / ${cfg.rx_count ?? 0} RX`;

    const elPktErrs = document.getElementById("localPacketErrorsValue");
    if (elPktErrs) elPktErrs.textContent = `Duplicados: ${cfg.duplicate_packets ?? 0} | Errores: ${cfg.packet_errors ?? 0}`;

    if (this.ctx.updateRadioBadge && (cfg.serial_connected != null || cfg.radio_connected != null)) {
      const isConnected = Boolean(cfg.serial_connected ?? cfg.radio_connected);
      this.ctx.updateRadioBadge(isConnected, cfg.serial_port || "");
    }
  }

  async saveLocalRadioConfig() {
    const freq = parseFloat(document.getElementById("localFreq")?.value || "915.000");
    const tx_power = parseInt(document.getElementById("localTxPower")?.value || "20", 10);
    const sf = parseInt(document.getElementById("localSf")?.value || "11", 10);
    const bw = parseFloat(document.getElementById("localBw")?.value || "250");
    const cr = document.getElementById("localCr")?.value || "4/5";

    try {
      const res = await fetch("/api/config/radio", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ frequency: freq, tx_power, spreading_factor: sf, bandwidth: bw, coding_rate: cr }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        if (this.ctx.showToast) this.ctx.showToast("📻 Parámetros de radio locales actualizados", "success");
      } else {
        alert("Error guardando radio: " + (data.message || "desconocido"));
      }
    } catch (e) {
      alert("Error de red guardando radio: " + e.message);
    }
  }

  async saveLocalIdentityAndPosition() {
    const name = document.getElementById("localNodeName")?.value.trim() || "";
    const lat = parseFloat(document.getElementById("localGpsLat")?.value || "");
    const lon = parseFloat(document.getElementById("localGpsLon")?.value || "");
    const alt = parseFloat(document.getElementById("localGpsAlt")?.value || "");

    const payload = { name };
    if (!isNaN(lat) && !isNaN(lon)) {
      payload.latitude = lat;
      payload.longitude = lon;
      if (!isNaN(alt)) payload.altitude_m = alt;
    }

    try {
      const res = await fetch("/api/config/identity", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.status === "ok") {
        if (this.ctx.showToast) this.ctx.showToast("📍 Identidad y ubicación guardadas", "success");
      } else {
        alert("Error guardando identidad: " + (data.message || "desconocido"));
      }
    } catch (e) {
      alert("Error de red: " + e.message);
    }
  }

  showQrModal(title, uri, rawJson = "") {
    if (!this.dom.qrShareModal) return;
    if (this.dom.qrModalTitle) this.dom.qrModalTitle.textContent = title || "Compartir por Código QR";
    if (this.dom.qrUriDisplay) this.dom.qrUriDisplay.value = uri || "";
    if (this.dom.qrShareJson) {
      this.dom.qrShareJson.value = typeof rawJson === "object" ? JSON.stringify(rawJson, null, 2) : String(rawJson || "");
    }

    if (this.dom.qrCanvas && window.QRCode) {
      this.dom.qrCanvas.innerHTML = "";
      try {
        new QRCode(this.dom.qrCanvas, {
          text: uri || "meshcore://",
          width: 180,
          height: 180,
          colorDark: "#000000",
          colorLight: "#ffffff",
          correctLevel: QRCode.CorrectLevel.M,
        });
      } catch (err) {
        console.warn("Error generando QR:", err);
      }
    }

    this.dom.qrShareModal.classList.remove("hidden");
  }
}
