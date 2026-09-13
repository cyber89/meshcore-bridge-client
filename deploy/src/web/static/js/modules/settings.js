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
    this._localCliTempInput = "";
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
    // 1. Crear Canal Modal
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
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.ch_saved').replace('{index}', index).replace('{name}', escapeHtml(name)), "success");
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
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.contact_added').replace('{name}', name || pubkey.slice(0, 8)), "success");
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
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.uri_copied'), "success");
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

    if (freqInput) {
      freqInput.addEventListener("input", (e) => {
        const sumFreq = document.getElementById("localSummaryFreq");
        if (sumFreq && e.target.value) sumFreq.textContent = `${Number(e.target.value).toFixed(3)} MHz`;
      });
    }

    const txSlider = document.getElementById("localTxPower");
    const txVal = document.getElementById("localTxPowerVal");
    if (txSlider && txVal) {
      txSlider.addEventListener("input", (e) => {
        txVal.textContent = `${e.target.value} dBm`;
        const sumPower = document.getElementById("localSummaryPower");
        if (sumPower) sumPower.textContent = `${e.target.value} dBm`;
      });
    }

    const sfSelect = document.getElementById("localSf");
    const bwSelect = document.getElementById("localBw");
    const updateModemSummary = () => {
      const sumModem = document.getElementById("localSummaryModem");
      if (sumModem && sfSelect && bwSelect) {
        sumModem.textContent = `SF${sfSelect.value} / BW${bwSelect.value}`;
      }
    };
    if (sfSelect) sfSelect.addEventListener("change", updateModemSummary);
    if (bwSelect) bwSelect.addEventListener("change", updateModemSummary);

    const repeatSwitch = document.getElementById("localRepeatMode");
    const repeatBadge = document.getElementById("localRepeatBadge");
    if (repeatSwitch) {
      repeatSwitch.addEventListener("change", (e) => {
        const checked = e.target.checked;
        if (repeatBadge) {
          repeatBadge.textContent = checked ? "ON" : "OFF";
          if (checked) {
            repeatBadge.classList.add("badge-active");
          } else {
            repeatBadge.classList.remove("badge-active");
          }
        }
        const sumRepeat = document.getElementById("localSummaryRepeat");
        if (sumRepeat) {
          sumRepeat.textContent = checked ? "Activado" : "Desactivado";
          sumRepeat.style.color = checked ? "var(--accent-success, #22c55e)" : "var(--text-muted, #94a3b8)";
        }
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
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.api_key_saved'), "success");
        } else {
          localStorage.removeItem("meshcore_bridge_api_key");
          if (this.dom.apiKeyStatusHint) {
            this.dom.apiKeyStatusHint.classList.remove("hidden");
            this.dom.apiKeyStatusHint.textContent = "ℹ️ Clave eliminada (modo sin autenticación)";
          }
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.api_key_del'), "info");
        }
      });
    }
    if (this.dom.btnClearBridgeApiKey && this.dom.inputBridgeApiKey) {
      this.dom.btnClearBridgeApiKey.addEventListener("click", () => {
        this.dom.inputBridgeApiKey.value = "";
        localStorage.removeItem("meshcore_bridge_api_key");
        if (this.dom.apiKeyStatusHint) {
          this.dom.apiKeyStatusHint.classList.remove("hidden");
          this.dom.apiKeyStatusHint.textContent = I18n.t('toast.api_key_del');
        }
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.api_key_del'), "info");
      });
    }

    // Terminal interactiva local
    if (this.dom.localTerminalForm) {
      this.dom.localTerminalForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const cmd = (this.dom.localTerminalInput?.value || "").trim();
        if (!cmd) return;

        this._localCliHistory.push(cmd);
        this._localCliHistoryIdx = -1;
        this._localCliTempInput = "";

        if (this.dom.localTerminalInput) this.dom.localTerminalInput.value = "";
        this.appendLocalTerminalLine(`meshcore@base:~$ ${cmd}`, "term-cmd");

        try {
          const res = await fetch("/api/admin", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ action: "cmd", command: cmd }),
          });
          const data = await res.json().catch(() => ({}));
          const isError = !res.ok || data.status === "error";
          const outText = data.response || data.message || data.result?.result || data.result?.message || (typeof data.result === "string" ? data.result : (typeof data === "string" ? data : JSON.stringify(data, null, 2)));
          this.appendLocalTerminalLine(outText, isError ? "term-error" : "term-success");
        } catch (err) {
          this.appendLocalTerminalLine(`✗ Error de conexión: ${err.message}`, "term-error");
        }
      });
    }

    if (this.dom.localTerminalInput) {
      this.dom.localTerminalInput.addEventListener("keydown", (e) => {
        if (e.key === "ArrowUp") {
          if (!this._localCliHistory || this._localCliHistory.length === 0) return;
          e.preventDefault();
          if (this._localCliHistoryIdx === -1) {
            this._localCliTempInput = this.dom.localTerminalInput.value;
            this._localCliHistoryIdx = this._localCliHistory.length - 1;
          } else if (this._localCliHistoryIdx > 0) {
            this._localCliHistoryIdx--;
          }
          this.dom.localTerminalInput.value = this._localCliHistory[this._localCliHistoryIdx] || "";
        } else if (e.key === "ArrowDown") {
          if (this._localCliHistoryIdx === -1) return;
          e.preventDefault();
          if (this._localCliHistoryIdx < this._localCliHistory.length - 1) {
            this._localCliHistoryIdx++;
            this.dom.localTerminalInput.value = this._localCliHistory[this._localCliHistoryIdx] || "";
          } else {
            this._localCliHistoryIdx = -1;
            this.dom.localTerminalInput.value = this._localCliTempInput || "";
          }
        }
      });
    }

    const btnToggleHelp = document.getElementById("btnToggleLocalCmdHelp");
    const helpDrawer = document.getElementById("localTerminalHelpDrawer");
    const btnCloseHelp = document.getElementById("btnCloseLocalHelpDrawer");
    const btnClearTerm = document.getElementById("btnClearLocalTerminal");

    if (btnToggleHelp && helpDrawer) {
      btnToggleHelp.addEventListener("click", () => helpDrawer.classList.toggle("hidden"));
    }
    if (btnCloseHelp && helpDrawer) {
      btnCloseHelp.addEventListener("click", () => helpDrawer.classList.add("hidden"));
    }
    if (btnClearTerm && this.dom.localTerminalOutput) {
      btnClearTerm.addEventListener("click", () => {
        this.dom.localTerminalOutput.innerHTML = "";
      });
    }
    document.querySelectorAll(".help-cmd-item[data-cmd]").forEach((item) => {
      item.addEventListener("click", () => {
        const cmd = item.getAttribute("data-cmd");
        if (this.dom.localTerminalInput && cmd) {
          this.dom.localTerminalInput.value = cmd;
          this.dom.localTerminalInput.focus();
        }
      });
    });

    // GPS del navegador
    const btnGetGps = document.getElementById("btnGetBrowserGps");
    if (btnGetGps) {
      btnGetGps.addEventListener("click", () => {
        if (!navigator.geolocation) {
          if (this.ctx.showToast) this.ctx.showToast("Geolocalización no soportada en este navegador", "error");
          return;
        }
        btnGetGps.disabled = true;
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            btnGetGps.disabled = false;
            const latIn = document.getElementById("localGpsLat");
            const lonIn = document.getElementById("localGpsLon");
            const altIn = document.getElementById("localGpsAlt");
            if (latIn) latIn.value = pos.coords.latitude.toFixed(6);
            if (lonIn) lonIn.value = pos.coords.longitude.toFixed(6);
            if (altIn && pos.coords.altitude != null) altIn.value = Math.round(pos.coords.altitude);
            if (this.ctx.showToast) this.ctx.showToast("Coordenadas GPS obtenidas del navegador", "success");
          },
          (err) => {
            btnGetGps.disabled = false;
            if (this.ctx.showToast) this.ctx.showToast(`Error de GPS: ${err.message}`, "error");
          },
          { enableHighAccuracy: true, timeout: 10000 }
        );
      });
    }

    // Mapas offline y almacenamiento
    const btnReloadMaps = document.getElementById("btnReloadLocalMaps");
    if (btnReloadMaps) {
      btnReloadMaps.addEventListener("click", async () => {
        const content = document.getElementById("localMapsStatusContent");
        if (content) content.textContent = "Reindexando archivos MBTiles...";
        try {
          const res = await fetch("/api/map/reload", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
          });
          if (content) content.textContent = res.ok ? "Archivos .mbtiles reindexados correctamente." : "Servicio de mapas activo.";
          if (this.ctx.showToast) this.ctx.showToast("Mosaicos locales reindexados", "success");
        } catch (e) {
          if (content) content.textContent = "Listo. Verifique directorio data/maps/.";
        }
      });
    }

    if (this.dom.btnSaveMapSettings) {
      this.dom.btnSaveMapSettings.addEventListener("click", () => {
        const url = (this.dom.inputLocalTileUrl?.value || "").trim();
        if (url) {
          localStorage.setItem("meshcore_local_tile_url", url);
          if (this.ctx.showToast) this.ctx.showToast("Configuración de mapas guardada", "success");
        }
      });
    }

    const btnClearIdb = document.getElementById("btnClearIndexedDbStorage");
    if (btnClearIdb) {
      btnClearIdb.addEventListener("click", async () => {
        if (!confirm("¿Deseas vaciar todo el almacenamiento local IndexedDB (mensajes y caché)?")) return;
        try {
          if (this.ctx.storage && this.ctx.storage.clearAll) {
            await this.ctx.storage.clearAll();
          } else {
            indexedDB.deleteDatabase("MeshCoreStationDB");
          }
          if (this.ctx.showToast) this.ctx.showToast("Almacenamiento IndexedDB vaciado con éxito", "info");
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(`Error al vaciar: ${err.message}`, "error");
        }
      });
    }

    const btnClearStats = document.getElementById("btnActionClearLocalStats");
    if (btnClearStats) {
      btnClearStats.addEventListener("click", async () => {
        const confirmMsg = I18n.t('analytics.confirm_reset') || "¿Deseas restablecer todos los contadores de paquetes y métricas acumuladas de la red?";
        if (!confirm(confirmMsg)) return;
        try {
          const res = await fetch("/api/analytics/reset", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
          });
          const data = await res.json();
          if (data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.metrics_reset') || "Métricas y contadores restablecidos correctamente", "success");
            await this.fetchLocalNodeConfig();
            if (this.ctx.fetchNodes) await this.ctx.fetchNodes();
          } else {
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message || "Fallo al restablecer"}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(`Error de red: ${err.message}`, "error");
        }
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
    const byteLen = Math.ceil(length / 2);
    const arr = new Uint8Array(byteLen);
    if (window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(arr);
    } else {
      for (let i = 0; i < byteLen; i++) arr[i] = Math.floor(Math.random() * 256);
    }
    return Array.from(arr, (b) => b.toString(16).padStart(2, "0")).join("").slice(0, length);
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
    const freqVal = cfg.frequency ?? cfg.radio_freq;
    const freqInput = document.getElementById("localFreq");
    if (freqInput && freqVal != null) freqInput.value = freqVal;

    const sfVal = cfg.spreading_factor ?? cfg.radio_sf ?? cfg.sf;
    const sfInput = document.getElementById("localSf");
    if (sfInput && sfVal != null) sfInput.value = String(sfVal);

    const bwVal = cfg.bandwidth ?? cfg.radio_bw ?? cfg.bw;
    const bwInput = document.getElementById("localBw");
    if (bwInput && bwVal != null) bwInput.value = String(bwVal);

    const crVal = cfg.coding_rate ?? cfg.radio_cr ?? cfg.cr;
    const crInput = document.getElementById("localCr");
    if (crInput && crVal != null) {
      const crStr = String(crVal).includes("/") ? String(crVal) : (crVal === 5 ? "4/5" : (crVal === 6 ? "4/6" : (crVal === 7 ? "4/7" : (crVal === 8 ? "4/8" : String(crVal)))));
      crInput.value = crStr;
    }

    const pwrVal = cfg.tx_power ?? cfg.power;
    const pwrInput = document.getElementById("localTxPower");
    const pwrValBadge = document.getElementById("localTxPowerVal");
    if (pwrInput && pwrVal != null) {
      pwrInput.value = pwrVal;
      if (pwrValBadge) pwrValBadge.textContent = `${pwrVal} dBm`;
    }

    const hopVal = cfg.hop_limit ?? cfg.hops;
    const hopInput = document.getElementById("localHopLimit");
    if (hopInput && hopVal != null) hopInput.value = hopVal;

    // Modo Repetidor / Router
    if (cfg.repeat != null || cfg.repeat_enabled != null) {
      const isRepeat = Boolean(cfg.repeat ?? cfg.repeat_enabled);
      const repeatChk = document.getElementById("localRepeatMode");
      const repeatBadge = document.getElementById("localRepeatBadge");
      if (repeatChk) repeatChk.checked = isRepeat;
      if (repeatBadge) {
        repeatBadge.textContent = isRepeat ? "ON" : "OFF";
        if (isRepeat) {
          repeatBadge.classList.add("badge-active");
        } else {
          repeatBadge.classList.remove("badge-active");
        }
      }
      const sumRepeat = document.getElementById("localSummaryRepeat");
      if (sumRepeat) {
        sumRepeat.textContent = isRepeat ? "Activado" : "Desactivado";
        sumRepeat.style.color = isRepeat ? "var(--accent-success, #22c55e)" : "var(--text-muted, #94a3b8)";
      }
    }

    // Intervalos
    const telemIntVal = cfg.telemetry_interval;
    const telemIntInput = document.getElementById("localTelemetryInterval");
    if (telemIntInput && telemIntVal != null) telemIntInput.value = telemIntVal;

    const advIntVal = cfg.advert_interval ?? cfg.beacon_interval;
    const advIntInput = document.getElementById("localAdvertInterval");
    if (advIntInput && advIntVal != null) advIntInput.value = advIntVal;

    // Resumen de Configuración Actual (Pills superiores)
    const sumFreq = document.getElementById("localSummaryFreq");
    if (sumFreq && freqVal != null) sumFreq.textContent = `${Number(freqVal).toFixed(3)} MHz`;

    const sumPower = document.getElementById("localSummaryPower");
    if (sumPower && pwrVal != null) sumPower.textContent = `${pwrVal} dBm`;

    const sumModem = document.getElementById("localSummaryModem");
    if (sumModem && (sfVal != null || bwVal != null)) {
      sumModem.textContent = `SF${sfVal || "--"} / BW${bwVal || "--"}`;
    }

    const sumQueue = document.getElementById("localSummaryQueue");
    if (sumQueue) sumQueue.textContent = `${cfg.queue_len ?? 0} paquetes`;

    const sumPos = document.getElementById("localSummaryPos");
    if (sumPos) {
      const lat = cfg.latitude ?? cfg.adv_lat;
      const lon = cfg.longitude ?? cfg.adv_lon;
      if (lat != null && lon != null && !isNaN(Number(lat)) && !isNaN(Number(lon))) {
        sumPos.textContent = `${Number(lat).toFixed(4)}, ${Number(lon).toFixed(4)}`;
      } else {
        sumPos.textContent = "--";
      }
    }

    // Posición GPS Form Inputs
    const latInput = document.getElementById("localGpsLat");
    if (latInput && (cfg.latitude != null || cfg.adv_lat != null)) latInput.value = cfg.latitude ?? cfg.adv_lat;

    const lonInput = document.getElementById("localGpsLon");
    if (lonInput && (cfg.longitude != null || cfg.adv_lon != null)) lonInput.value = cfg.longitude ?? cfg.adv_lon;

    const altInput = document.getElementById("localGpsAlt");
    if (altInput && (cfg.altitude != null || cfg.alt != null)) altInput.value = cfg.altitude ?? cfg.alt;

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
    const hop_limit = parseInt(document.getElementById("localHopLimit")?.value || "3", 10);
    const repeat = Boolean(document.getElementById("localRepeatMode")?.checked);
    const telemetry_interval = parseInt(document.getElementById("localTelemetryInterval")?.value || "60", 10);
    const advert_interval = parseInt(document.getElementById("localAdvertInterval")?.value || "300", 10);

    try {
      const res = await fetch("/api/config/radio", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({
          frequency: freq,
          tx_power,
          spreading_factor: sf,
          bandwidth: bw,
          coding_rate: cr,
          repeat,
          hop_limit,
          telemetry_interval,
          advert_interval,
        }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.populateLocalConfig({
          frequency: freq,
          tx_power,
          spreading_factor: sf,
          bandwidth: bw,
          coding_rate: cr,
          repeat,
          hop_limit,
          telemetry_interval,
          advert_interval,
        });
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.radio_cfg_ok'), "success");
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
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.identity_ok'), "success");
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

    if (this.dom.qrCanvas && (window.QRCodeGenerator || window.QRCode)) {
      this.dom.qrCanvas.innerHTML = "";
      try {
        if (window.QRCodeGenerator && typeof window.QRCodeGenerator.renderToCanvas === "function") {
          window.QRCodeGenerator.renderToCanvas(this.dom.qrCanvas, uri || "meshcore://", {
            size: 180,
            margin: 8,
          });
        } else if (typeof window.QRCode === "function") {
          new window.QRCode(this.dom.qrCanvas, {
            text: uri || "meshcore://",
            width: 180,
            height: 180,
            colorDark: "#000000",
            colorLight: "#ffffff",
            correctLevel: window.QRCode.CorrectLevel ? window.QRCode.CorrectLevel.M : 0,
          });
        }
      } catch (err) {
        console.warn("Error generando QR:", err);
      }
    }

    this.dom.qrShareModal.classList.remove("hidden");
  }

  appendLocalTerminalLine(text, cssClass = "term-info") {
    if (!text) return;
    const strText = String(text).trim();
    if (!strText) return;
    const termOut = this.dom.localTerminalOutput;
    if (!termOut) return;

    const line = document.createElement("div");
    line.className = `term-line ${cssClass}`;
    line.textContent = strText;
    termOut.appendChild(line);
    termOut.scrollTop = termOut.scrollHeight;
  }
}
