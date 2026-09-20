/**
 * SettingsModule - Gestión de parámetros RF del transceptor local, administración de canales,
 * importación/exportación de contactos y diagnósticos preflight.
 */

import {
  escapeHtml,
  getHardwarePowerLimits,
  REGION_FREQUENCIES,
  debounce,
  buildMeshCoreContactUri,
  buildMeshCoreChannelUri,
  parseMeshCoreUri,
  MESHCORE_PUBLIC_CHANNEL_SECRET,
} from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class SettingsModule {
  constructor(context) {
    this.ctx = context;
    this.channelsList = [];
    this.cachedConfig = {};
    this._deviceClockHostBase = null;
    this._uptimeHostBase = null;
    this._tickInterval = null;
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
    this.fetchCustomVars();
    this.fetchFloodScope();
    this.fetchAutoAddConfig();
    this._startLiveTick();
    window.showQrModal = (title, uri, rawJson) => this.showQrModal(title, uri, rawJson);
  }

  _startLiveTick() {
    if (this._tickInterval) clearInterval(this._tickInterval);
    this._tickInterval = setInterval(() => {
      if (document.hidden) return;
      const activeTab = document.querySelector(".tab-pane.active")?.id;
      if (activeTab !== "tab-settings") return;
      if (!this.cachedConfig) return;
      if (this.cachedConfig.device_epoch_time && this._deviceClockHostBase) {
        const elClock = document.getElementById("localClockValue");
        if (elClock) {
          const elapsedMs = Date.now() - this._deviceClockHostBase;
          const liveDate = new Date((this.cachedConfig.device_epoch_time * 1000) + elapsedMs);
          elClock.textContent = liveDate.toLocaleTimeString();
        }
      }
      if (this._deviceUptime != null && this._deviceUptimeHostBase) {
        const elUptime = document.getElementById("localUptimeValue");
        if (elUptime) {
          const elapsedSec = Math.floor((Date.now() - this._deviceUptimeHostBase) / 1000);
          const totalSec = this._deviceUptime + elapsedSec;
          const days = Math.floor(totalSec / 86400);
          const hours = Math.floor((totalSec % 86400) / 3600);
          const mins = Math.floor((totalSec % 3600) / 60);
          elUptime.textContent = days > 0
            ? `${days}d ${hours}h ${mins}m`
            : (hours > 0 ? `${hours}h ${mins}m` : `${mins}m`);
        }
      }
    }, 1000);
  }

  _notify(msg, type = "info") {
    if (this.ctx && typeof this.ctx.showToast === "function") {
      this.ctx.showToast(msg, type);
    } else {
      alert(msg);
    }
  }

  _bindElements() {
    this.dom = {
      channelListUi: document.getElementById("channelListUi"),
      sidebarChannelList: document.getElementById("sidebarChannelList"),
      btnAddChannel: document.getElementById("btnAddChannel"),
      createChannelModal: document.getElementById("createChannelModal"),
      btnCloseCreateChannelModal: document.getElementById("btnCloseCreateChannelModal"),
      btnCancelCreateChannel: document.getElementById("btnCancelCreateChannel"),
      createChannelForm: document.getElementById("createChannelForm"),
      chModalIndex: document.getElementById("chModalIndex"),
      chModalName: document.getElementById("chModalName"),
      chModalIsEncrypted: document.getElementById("chModalIsEncrypted"),
      chModalEncryptedBadge: document.getElementById("chModalEncryptedBadge"),
      chModalPskGroup: document.getElementById("chModalPskGroup"),
      chModalPsk: document.getElementById("chModalPsk"),
      btnGenRandomPsk: document.getElementById("btnGenRandomPsk"),
      btnSaveChannel: document.getElementById("btnSaveChannel"),
      btnOpenAddContact: document.getElementById("btnOpenAddContact") || document.getElementById("btnHeaderAddContact"),
      btnHeaderAddContact: document.getElementById("btnHeaderAddContact"),
      createContactModal: document.getElementById("createContactModal"),
      btnCloseCreateContactModal: document.getElementById("btnCloseCreateContactModal"),
      btnCancelCreateContact: document.getElementById("btnCancelCreateContact"),
      createContactForm: document.getElementById("createContactForm"),
      contactModalPubKey: document.getElementById("contactModalPubKey"),
      contactModalName: document.getElementById("contactModalName"),
      contactModalFavorite: document.getElementById("contactModalFavorite"),
      contactModalFavBadge: document.getElementById("contactModalFavBadge"),
      qrShareModal: document.getElementById("qrShareModal"),
      btnCloseQrShareModal: document.getElementById("btnCloseQrShareModal"),
      btnCloseQrModal: document.getElementById("btnCloseQrShareModal") || document.getElementById("btnCloseQrModal"),
      btnCloseQrModalAction: document.getElementById("btnCloseQrModalAction"),
      qrCanvas: document.getElementById("qrCanvas") || document.getElementById("qrShareCanvas"),
      qrShareCanvas: document.getElementById("qrCanvas") || document.getElementById("qrShareCanvas"),
      qrUriDisplay: document.getElementById("qrUriDisplay") || document.getElementById("qrShareUri"),
      qrShareUri: document.getElementById("qrUriDisplay") || document.getElementById("qrShareUri"),
      qrShareJson: document.getElementById("qrShareJson"),
      qrModalTitle: document.getElementById("qrModalTitle"),
      btnCopyQrUri: document.getElementById("btnCopyQrUri"),
      btnDownloadQrJson: document.getElementById("btnDownloadQrJson"),
      importFileInput: document.getElementById("importFileInput"),
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
      btnRefreshLocalConfig: document.getElementById("btnRefreshLocalConfig"),
      btnRefreshLocalTelem: document.getElementById("btnRefreshLocalTelem"),
      btnSyncLocalClock: document.getElementById("btnSyncLocalClock"),
      btnActionAdvertHop: document.getElementById("btnActionAdvertHop"),
      btnActionAdvertFlood: document.getElementById("btnActionAdvertFlood"),
      btnActionReconnectSerial: document.getElementById("btnActionReconnectSerial"),
      btnActionRebootLocal: document.getElementById("btnActionRebootLocal"),
      btnActionClearLocalStats: document.getElementById("btnActionClearLocalStats"),
      localHwBoardBadge: document.getElementById("localHwBoardBadge"),
      localFwVersionBadge: document.getElementById("localFwVersionBadge"),
    };
  }

  _bindEvents() {
    // 1. Crear Canal Modal
    const openCreateChannel = () => {
      if (!this.dom.createChannelModal) return;

      const occupiedIndices = new Set(this.channelsList.map((c) => Number(c.index)));
      const availableIndices = [1, 2, 3, 4, 5, 6, 7].filter((idx) => !occupiedIndices.has(idx));

      if (availableIndices.length === 0) {
        const msg = "No hay ranuras disponibles de canales secundarios (canales 1 a 7 ocupados). Elimina un canal antes de crear uno nuevo.";
        this._notify(msg, "warning");
        return;
      }

      if (this.dom.chModalIndex) {
        this.dom.chModalIndex.innerHTML = "";
        availableIndices.forEach((idx) => {
          const opt = document.createElement("option");
          opt.value = String(idx);
          opt.textContent = `Canal ${idx} (Secundario)`;
          this.dom.chModalIndex.appendChild(opt);
        });
        this.dom.chModalIndex.value = String(availableIndices[0]);
      }

      this.dom.createChannelModal.classList.remove("hidden");
      if (this.dom.chModalName) this.dom.chModalName.value = "";
      if (this.dom.chModalIsEncrypted) {
        this.dom.chModalIsEncrypted.checked = true;
      }
      if (this.dom.chModalEncryptedBadge) {
        this.dom.chModalEncryptedBadge.textContent = "CIFRADO";
        this.dom.chModalEncryptedBadge.classList.add("is-active");
      }
      if (this.dom.chModalPskGroup) {
        this.dom.chModalPskGroup.classList.remove("hidden");
      }
      if (this.dom.chModalPsk) {
        this.dom.chModalPsk.required = true;
        this.dom.chModalPsk.value = this.generateRandomHex(32);
      }
      if (this.dom.chModalName) this.dom.chModalName.focus();
    };
    const closeCreateChannel = () => {
      if (this.dom.createChannelModal) {
        this.dom.createChannelModal.classList.add("hidden");
      }
    };

    if (this.dom.btnAddChannel) {
      this.dom.btnAddChannel.addEventListener("click", openCreateChannel);
    }
    if (this.dom.btnCloseCreateChannelModal) {
      this.dom.btnCloseCreateChannelModal.addEventListener("click", closeCreateChannel);
    }
    if (this.dom.btnCancelCreateChannel) {
      this.dom.btnCancelCreateChannel.addEventListener("click", closeCreateChannel);
    }

    if (this.dom.chModalIsEncrypted) {
      this.dom.chModalIsEncrypted.addEventListener("change", (e) => {
        const isEnc = e.target.checked;
        if (this.dom.chModalEncryptedBadge) {
          this.dom.chModalEncryptedBadge.textContent = isEnc ? "CIFRADO" : "ABIERTO";
          this.dom.chModalEncryptedBadge.classList.toggle("is-active", isEnc);
        }
        if (this.dom.chModalPskGroup) {
          this.dom.chModalPskGroup.classList.toggle("hidden", !isEnc);
        }
        if (this.dom.chModalPsk) {
          this.dom.chModalPsk.required = isEnc;
          if (isEnc && !this.dom.chModalPsk.value) {
            this.dom.chModalPsk.value = this.generateRandomHex(32);
          }
        }
      });
    }

    if (this.dom.btnGenRandomPsk) {
      this.dom.btnGenRandomPsk.addEventListener("click", () => {
        if (this.dom.chModalPsk) {
          this.dom.chModalPsk.value = this.generateRandomHex(32);
        }
      });
    }

    if (this.dom.createChannelForm) {
      this.dom.createChannelForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const index = parseInt(this.dom.chModalIndex.value, 10);
        const name = this.dom.chModalName.value.trim();
        const isEncrypted = this.dom.chModalIsEncrypted ? this.dom.chModalIsEncrypted.checked : true;
        const psk = isEncrypted ? this.dom.chModalPsk.value.trim() : "";

        try {
          const res = await fetch("/api/channels", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ index, name, psk }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            closeCreateChannel();
            await this.fetchChannels();
            if (this.ctx.switchChannel) this.ctx.switchChannel(index);
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.ch_saved').replace('{index}', index).replace('{name}', escapeHtml(name)), "success");
          } else {
            this._notify(`Error guardando canal: ${data.message || "Fallo desconocido"}`, "error");
          }
        } catch (err) {
          this._notify(`Error de red al guardar canal: ${err.message}`, "error");
        }
      });
    }

    // 3. Crear Contacto Modal
    const openCreateContact = () => {
      if (!this.dom.createContactModal) return;
      this.dom.createContactModal.classList.remove("hidden");
      if (this.dom.contactModalPubKey) this.dom.contactModalPubKey.value = "";
      if (this.dom.contactModalName) this.dom.contactModalName.value = "";
      if (this.dom.contactModalFavorite) {
        this.dom.contactModalFavorite.checked = false;
      }
      if (this.dom.contactModalFavBadge) {
        this.dom.contactModalFavBadge.textContent = "NO";
        this.dom.contactModalFavBadge.classList.remove("is-active");
      }
      if (this.dom.contactModalPubKey) this.dom.contactModalPubKey.focus();
    };
    const closeCreateContact = () => {
      if (this.dom.createContactModal) this.dom.createContactModal.classList.add("hidden");
    };

    if (this.dom.btnAddContact) this.dom.btnAddContact.addEventListener("click", openCreateContact);
    if (this.dom.btnHeaderAddContact) this.dom.btnHeaderAddContact.addEventListener("click", openCreateContact);
    if (this.dom.btnCloseCreateContactModal) this.dom.btnCloseCreateContactModal.addEventListener("click", closeCreateContact);
    if (this.dom.btnCancelCreateContact) this.dom.btnCancelCreateContact.addEventListener("click", closeCreateContact);

    if (this.dom.contactModalFavorite) {
      this.dom.contactModalFavorite.addEventListener("change", (e) => {
        const isFav = e.target.checked;
        if (this.dom.contactModalFavBadge) {
          this.dom.contactModalFavBadge.textContent = isFav ? "SÍ" : "NO";
          this.dom.contactModalFavBadge.classList.toggle("is-active", isFav);
        }
      });
    }

    if (this.dom.createContactForm) {
      this.dom.createContactForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const pubkey = this.dom.contactModalPubKey.value.trim();
        const name = this.dom.contactModalName.value.trim();
        const role = this.dom.contactModalRole ? this.dom.contactModalRole.value : "CLIENT";
        const isFavorite = Boolean(this.dom.contactModalFavorite?.checked);
        if (!pubkey) return;

        try {
          const res = await fetch("/api/contacts", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ public_key: pubkey, name: name, alias: name, role: role, is_favorite: isFavorite }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            closeCreateContact();
            if (this.ctx.fetchNodes) await this.ctx.fetchNodes();
            if (this.ctx.setDmTarget) this.ctx.setDmTarget(pubkey, name || pubkey);
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.contact_added').replace('{name}', name || pubkey.slice(0, 8)), "success");
          } else {
            this._notify(`Error agregando contacto: ${data.message || "Fallo desconocido"}`, "error");
          }
        } catch (err) {
          this._notify(`Error de red al agregar contacto: ${err.message}`, "error");
        }
      });
    }

    // 4. Modal QR
    const closeQr = () => {
      if (this.dom.qrShareModal) this.dom.qrShareModal.classList.add("hidden");
    };
    if (this.dom.btnCloseQrShareModal) this.dom.btnCloseQrShareModal.addEventListener("click", closeQr);
    if (this.dom.btnCloseQrModal) this.dom.btnCloseQrModal.addEventListener("click", closeQr);
    if (this.dom.btnCloseQrModalAction) this.dom.btnCloseQrModalAction.addEventListener("click", closeQr);
    if (this.dom.qrShareModal) {
      this.dom.qrShareModal.addEventListener("click", (e) => {
        if (e.target === this.dom.qrShareModal) closeQr();
      });
    }
    if (this.dom.btnCopyQrUri) {
      this.dom.btnCopyQrUri.addEventListener("click", () => {
        const uriEl = this.dom.qrUriDisplay || this.dom.qrShareUri;
        const uri = uriEl ? (uriEl.value || uriEl.textContent || "") : "";
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

    // 5. Modal de Importación (Canal o Contacto)
    const openImportModal = () => {
      if (!this.dom.importModal) return;
      if (this.dom.importPayloadInput) this.dom.importPayloadInput.value = "";
      this.dom.importModal.classList.remove("hidden");
      if (this.dom.importPayloadInput) this.dom.importPayloadInput.focus();
    };
    const closeImportModal = () => {
      if (this.dom.importModal) this.dom.importModal.classList.add("hidden");
    };

    if (this.dom.btnImportData) this.dom.btnImportData.addEventListener("click", openImportModal);
    if (this.dom.btnHeaderImportContact) this.dom.btnHeaderImportContact.addEventListener("click", openImportModal);
    if (this.dom.btnCloseImportModal) this.dom.btnCloseImportModal.addEventListener("click", closeImportModal);
    if (this.dom.btnCancelImport) this.dom.btnCancelImport.addEventListener("click", closeImportModal);

    if (this.dom.importFileInput) {
      this.dom.importFileInput.addEventListener("change", (e) => {
        const file = e.target.files && e.target.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = (ev) => {
          if (this.dom.importPayloadInput && ev.target?.result) {
            this.dom.importPayloadInput.value = String(ev.target.result).trim();
          }
        };
        reader.readAsText(file);
      });
    }

    if (this.dom.importForm) {
      this.dom.importForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const raw = this.dom.importPayloadInput ? this.dom.importPayloadInput.value.trim() : "";
        if (!raw) return;

        await this.processImportPayload(raw, closeImportModal);
      });
    }

    // 6. Navegación subpestañas locales
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
        if (target === "local-radio") {
          this.fetchCustomVars();
        }
        if (target === "local-security") {
          this.fetchFloodScope();
          this.fetchAutoAddConfig();
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
 
    const setupToggle = (chkId, badgeId) => {
      const chk = document.getElementById(chkId);
      const badge = document.getElementById(badgeId);
      if (chk) {
        chk.addEventListener("change", (e) => {
          const checked = e.target.checked;
          if (badge) {
            badge.textContent = checked ? "ON" : "OFF";
            badge.classList.toggle("badge-active", checked);
          }
        });
      }
    };
    const setupToggleWithInput = (chkId, badgeId, inputId) => {
      const chk = document.getElementById(chkId);
      const badge = document.getElementById(badgeId);
      const input = document.getElementById(inputId);
      if (chk) {
        chk.addEventListener("change", (e) => {
          const checked = e.target.checked;
          if (badge) {
            badge.textContent = checked ? "ON" : "OFF";
            badge.classList.toggle("badge-active", checked);
          }
          if (input) {
            input.disabled = !checked;
            input.style.opacity = checked ? "1" : "0.5";
          }
        });
      }
    };
    setupToggleWithInput("localAdvertEnable", "localAdvertEnableBadge", "localAdvertInterval");
    setupToggleWithInput("localTelemetryEnable", "localTelemetryEnableBadge", "localTelemetryInterval");
    setupToggle("localAdvLocPolicy", "localAdvLocBadge");
    setupToggle("localMultiAcks", "localMultiAcksBadge");
    setupToggle("localManualAddContacts", "localManualAddBadge");

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

    const posFixedSwitch = document.getElementById("localPosFixed");
    const posFixedBadge = document.getElementById("localPosFixedBadge");
    if (posFixedSwitch) {
      posFixedSwitch.addEventListener("change", (e) => {
        const checked = e.target.checked;
        if (posFixedBadge) {
          posFixedBadge.textContent = checked ? "FIJA" : "OFF";
          posFixedBadge.classList.toggle("is-active", checked);
        }
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

    // Custom Vars
    const btnRefreshCustomVars = document.getElementById("btnRefreshCustomVars");
    if (btnRefreshCustomVars) {
      btnRefreshCustomVars.addEventListener("click", () => this.fetchCustomVars());
    }
    const btnSaveCustomVar = document.getElementById("btnSaveCustomVar");
    if (btnSaveCustomVar) {
      btnSaveCustomVar.addEventListener("click", () => this.saveCustomVar());
    }

    // Flood Scope
    const btnSaveFloodScope = document.getElementById("btnSaveFloodScope");
    if (btnSaveFloodScope) {
      btnSaveFloodScope.addEventListener("click", () => this.saveFloodScope());
    }
    const btnResetFloodScope = document.getElementById("btnResetFloodScope");
    if (btnResetFloodScope) {
      btnResetFloodScope.addEventListener("click", () => this.resetFloodScope());
    }

    // AutoAdd config
    const btnSaveAutoAdd = document.getElementById("btnSaveAutoAddConfig");
    if (btnSaveAutoAdd) {
      btnSaveAutoAdd.addEventListener("click", () => this.saveAutoAddConfig());
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
        this.appendLocalTerminalLine(`meshcore> ${cmd}`, "term-cmd");

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

          if (!isError) {
            const freshCfg = data.config || data.result?.config || (typeof data.data === "object" ? data.data : null);
            if (freshCfg) {
              this.populateLocalConfig(freshCfg);
            }
          }
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

    // Acciones Rápidas de Hardware
    const refreshHardware = async () => {
      const btn = this.dom.btnRefreshLocalConfig || this.dom.btnRefreshLocalTelem;
      const icon = btn ? btn.querySelector("[data-lucide]") : null;
      if (icon) icon.classList.add("spin-animation");
      try {
        await this.fetchLocalNodeConfig(true);
        if (this.ctx.showToast) this.ctx.showToast("Parámetros de hardware actualizados desde la radio", "success");
      } catch (err) {
        if (this.ctx.showToast) this.ctx.showToast(`Error consultando radio: ${err.message}`, "error");
      } finally {
        if (icon) icon.classList.remove("spin-animation");
      }
    };

    if (this.dom.btnRefreshLocalConfig) {
      this.dom.btnRefreshLocalConfig.addEventListener("click", refreshHardware);
    }
    if (this.dom.btnRefreshLocalTelem) {
      this.dom.btnRefreshLocalTelem.addEventListener("click", refreshHardware);
    }

    if (this.dom.btnSyncLocalClock) {
      this.dom.btnSyncLocalClock.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/config/sync-clock", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ epoch: Math.floor(Date.now() / 1000) }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            const clockEl = document.getElementById("localClockValue");
            if (clockEl) clockEl.textContent = data.data?.clock || new Date().toLocaleTimeString();
            const statusEl = document.getElementById("localClockStatus");
            if (statusEl) {
              statusEl.textContent = "Sincronizado con Host";
              statusEl.style.color = "var(--accent-success, #22c55e)";
            }
            if (this.ctx.showToast) this.ctx.showToast("Reloj RTC sincronizado exitosamente con el host", "success");
            await this.fetchLocalNodeConfig(false);
          } else {
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message || "Fallo al sincronizar"}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(`Error de red: ${err.message}`, "error");
        }
      });
    }

    if (this.dom.btnActionAdvertHop) {
      this.dom.btnActionAdvertHop.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/node/advert", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ flood: false }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast("Baliza Advert Hop 0 emitida a vecinos directos", "success");
          } else {
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message || "Fallo al emitir advert"}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(`Error de red: ${err.message}`, "error");
        }
      });
    }

    if (this.dom.btnActionAdvertFlood) {
      this.dom.btnActionAdvertFlood.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/node/advert", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ flood: true }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast("Baliza Advert Flood propagada a la malla", "success");
          } else {
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message || "Fallo al emitir flood"}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(`Error de red: ${err.message}`, "error");
        }
      });
    }

    if (this.dom.btnActionReconnectSerial) {
      this.dom.btnActionReconnectSerial.addEventListener("click", async () => {
        try {
          const res = await fetch("/api/config/reconnect", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
          });
          const data = await res.json();
          if (data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast("Reconexión de puerto serial completada", "success");
            setTimeout(() => this.fetchLocalNodeConfig(true), 1500);
          } else {
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message || "Fallo al reconectar"}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(`Error de red: ${err.message}`, "error");
        }
      });
    }

    if (this.dom.btnActionRebootLocal) {
      this.dom.btnActionRebootLocal.addEventListener("click", async () => {
        if (!confirm("¿Deseas reiniciar el microcontrolador de hardware del nodo local?")) return;
        try {
          const res = await fetch("/api/config/reboot", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
          });
          const data = await res.json();
          if (data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast("Comando de reinicio de hardware transmitido al dispositivo", "warning");
          } else {
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message || "Fallo al reiniciar"}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(`Error de red: ${err.message}`, "error");
        }
      });
    }

    if (this.dom.btnActionClearLocalStats) {
      this.dom.btnActionClearLocalStats.addEventListener("click", async () => {
        const confirmMsg = I18n.t('analytics.confirm_reset') || "¿Deseas restablecer todos los contadores de paquetes y métricas acumuladas?";
        if (!confirm(confirmMsg)) return;
        try {
          const res = await fetch("/api/config/clear-stats", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
          });
          const data = await res.json();
          if (data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast("Contadores y métricas restablecidos a cero", "success");
            await this.fetchLocalNodeConfig(false);
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

    this.ctx.eventBus.on(EVENTS.TAB_CHANGED, (tabId) => {
      if (tabId === "tab-settings") {
        const now = Date.now();
        if (!this._lastFetchTime || (now - this._lastFetchTime) > 30000) {
          this.fetchLocalNodeConfig(false);
        }
      }
    });

    this.ctx.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (!payload || typeof payload !== "object") return;
      if (payload.type === "channels_updated" || payload.event_type === "channels_updated") {
        if (Array.isArray(payload.data)) {
          this.renderChannelsList(payload.data);
        } else {
          this.fetchChannels();
        }
      }
      const evType = String(payload.event || payload.event_type || payload.type || "").toLowerCase();
      if (evType === "self_info" || evType === "device_info" || evType === "battery" || evType === "clock_synced") {
        this.populateLocalConfig(payload.data || payload);
      }
    });

    this.ctx.eventBus.on(EVENTS.METRICS_UPDATE, (payload) => {
      if (!payload || typeof payload !== "object") return;
      if (!this.cachedConfig) this.cachedConfig = {};

      // Detectar desconexión / reconexión para resetear y re-obtener uptime del dispositivo
      const isConnected = payload.serial_connected ?? payload.radio_connected;
      if (isConnected === false) {
        this._deviceWasDisconnected = true;
        this._deviceUptime = null;
        this._deviceClockHostBase = null;
      } else if (isConnected === true && this._deviceWasDisconnected) {
        this._deviceWasDisconnected = false;
        this._reconnected = true;
        // Reconexión detectada: re-obtener uptime y configuración fresca del hardware
        this.fetchLocalNodeConfig(true);
      }

      if (payload.rx_count != null) this.cachedConfig.rx_count = payload.rx_count;
      if (payload.tx_count != null) this.cachedConfig.tx_count = payload.tx_count;
      if (payload.error_rate != null) this.cachedConfig.error_rate = payload.error_rate;
      if (payload.queue_depth != null) this.cachedConfig.queue_depth = payload.queue_depth;
      if (payload.airtime_ms != null) this.cachedConfig.airtime_ms = payload.airtime_ms;
      if (payload.duty_cycle_pct != null) this.cachedConfig.duty_cycle_pct = payload.duty_cycle_pct;
      if (payload.packet_errors != null) this.cachedConfig.packet_errors = payload.packet_errors;
      if (payload.duplicate_packets != null) this.cachedConfig.duplicate_packets = payload.duplicate_packets;

      const elPkts = document.getElementById("localPacketsValue");
      if (elPkts && (payload.tx_count != null || payload.rx_count != null)) {
        const tx = payload.tx_count ?? this.cachedConfig.tx_count ?? 0;
        const rx = payload.rx_count ?? this.cachedConfig.rx_count ?? 0;
        elPkts.textContent = `${tx} TX / ${rx} RX`;
      }
      const elPktErrs = document.getElementById("localPacketErrorsValue");
      if (elPktErrs && (payload.packet_errors != null || payload.duplicate_packets != null)) {
        const dups = payload.duplicate_packets ?? this.cachedConfig.duplicate_packets ?? 0;
        const errs = payload.packet_errors ?? this.cachedConfig.packet_errors ?? 0;
        elPktErrs.textContent = `Duplicados: ${dups} | Errores: ${errs}`;
      }
      const sumQueue = document.getElementById("localSummaryQueue");
      if (sumQueue && payload.queue_depth != null) {
        sumQueue.textContent = `${payload.queue_depth} paquetes`;
      }
      const elAirtime = document.getElementById("localAirtimeValue");
      if (elAirtime && payload.airtime_ms != null) {
        elAirtime.textContent = `${payload.airtime_ms} ms`;
      }
      const elDuty = document.getElementById("localAirtimeDuty");
      if (elDuty && payload.duty_cycle_pct != null) {
        elDuty.textContent = `Duty Cycle: ${payload.duty_cycle_pct}%`;
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
    this.channelsList = Array.isArray(channels) ? channels : [];
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

      const isEnc = Boolean(ch.has_psk || (ch.psk && ch.psk.trim().length > 0));
      const lockIcon = isEnc ? "lock" : "unlock";
      const lockTitle = isEnc
        ? "Canal Cifrado (AES-128)"
        : (ch.index === 0 ? "Canal Público (Abierto)" : "Canal Abierto (Sin Cifrar)");

      const chDisplayName = ch.name || (ch.index === 0 ? "Public / Broadcast" : `Canal ${ch.index}`);

      li.innerHTML = `
        <span class="ch-badge font-mono">Ch ${ch.index}</span>
        <span class="ch-name">${escapeHtml(chDisplayName)}</span>
        <div class="ch-actions">
          <span class="ch-lock ${isEnc ? 'ch-locked' : 'ch-open'}" title="${lockTitle}">
            <span data-lucide="${lockIcon}" data-size="13"></span>
          </span>
          ${ch.index > 0 ? `
            <button type="button" class="btn-item-qr" data-ch-idx="${ch.index}" data-ch-name="${escapeHtml(chDisplayName)}" title="Compartir canal vía QR / URI oficial" aria-label="Compartir canal ${ch.index}">
              <span data-lucide="qr-code" data-size="13"></span>
            </button>
            <button type="button" class="btn-item-delete" data-ch-idx="${ch.index}" data-ch-name="${escapeHtml(chDisplayName)}" title="Eliminar canal ${ch.index}" aria-label="Eliminar canal ${ch.index}">
              <span data-lucide="trash-2" data-size="13"></span>
            </button>
          ` : ''}
        </div>
      `;

      li.addEventListener("click", (e) => {
        if (e.target.closest(".btn-item-delete, .btn-item-qr")) return;
        if (this.ctx.switchChannel) this.ctx.switchChannel(ch.index);
        if (this.dom.sidebarChannelList) this.dom.sidebarChannelList.classList.remove("mobile-open");
      });

      const btnQr = li.querySelector(".btn-item-qr");
      if (btnQr) {
        btnQr.addEventListener("click", async (e) => {
          e.stopPropagation();
          const chIdx = Number(btnQr.getAttribute("data-ch-idx"));
          try {
            const res = await fetch(`/api/channels/export?index=${chIdx}`, {
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
            });
            const data = await res.json();
            if (data.status === "ok" && data.uri) {
              if (window.showQrModal) {
                window.showQrModal(`Canal ${chIdx}: ${chDisplayName}`, data.uri, data.data);
              }
            } else {
              this._notify(`Error exportando canal: ${data.message || "Fallo desconocido"}`, "error");
            }
          } catch (err) {
            this._notify(`Error obteniendo datos del canal: ${err.message}`, "error");
          }
        });
      }

      const btnDelete = li.querySelector(".btn-item-delete");
      if (btnDelete) {
        btnDelete.addEventListener("click", async (e) => {
          e.stopPropagation();
          const chIdx = Number(btnDelete.getAttribute("data-ch-idx"));
          const chName = btnDelete.getAttribute("data-ch-name") || `Canal ${chIdx}`;

          const confirmed = window.confirm(
            `⚠️ ADVERTENCIA: ¿Estás seguro de que deseas eliminar el Canal ${chIdx} ("${chName}")?\n\nEsta acción borrará la configuración y desvinculará este canal.`
          );
          if (!confirmed) return;

          try {
            const res = await fetch("/api/channels", {
              method: "DELETE",
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ index: chIdx }),
            });
            if (res.ok) {
              if (this.ctx.showToast) {
                this.ctx.showToast(`Canal ${chIdx} ("${chName}") eliminado correctamente`, "success");
              }
              this.channelsList = (this.channelsList || []).filter((c) => Number(c.index) !== chIdx);
              this.renderChannelsList(this.channelsList);

              if (this.ctx.activeChannelIdx === chIdx) {
                if (this.ctx.switchChannel) this.ctx.switchChannel(0);
              }
              await this.fetchChannels();
            } else {
              const data = await res.json().catch(() => ({}));
              this._notify(`Error al eliminar canal: ${data.detail || data.message || "Fallo desconocido"}`, "error");
            }
          } catch (err) {
            this._notify(`Error de red al eliminar canal: ${err.message}`, "error");
          }
        });
      }

      listEl.appendChild(li);
    });

    if (window.initLucideIcons) {
      window.initLucideIcons(listEl);
    }
  }

  async processImportPayload(raw, closeCallback) {
    try {
      const cleanRaw = String(raw).trim();
      const parsedUri = parseMeshCoreUri(cleanRaw);

      // Caso 1: Es un Canal (URI canónica meshcore://channel/add?... o compatible)
      if (parsedUri && parsedUri.kind === "channel") {
        const idx = parsedUri.index ?? 1;
        const name = parsedUri.name || `Canal ${idx}`;
        const psk = (parsedUri.secret && parsedUri.secret !== MESHCORE_PUBLIC_CHANNEL_SECRET) ? parsedUri.secret : "";

        const exists = this.channelsList.some((c) => Number(c.index) === idx);
        if (exists) {
          const overwrite = window.confirm(
            `El Canal ${idx} ("${name}") ya existe en la configuración.\n\n¿Deseas sobreescribirlo con los datos importados?`
          );
          if (!overwrite) return;
        }

        const res = await fetch("/api/channels", {
          method: "POST",
          headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
          body: JSON.stringify({ index: idx, name, psk, overwrite: exists }),
        });
        const data = await res.json();
        if (data.status === "ok") {
          if (closeCallback) closeCallback();
          await this.fetchChannels();
          if (this.ctx.switchChannel) this.ctx.switchChannel(idx);
          if (this.ctx.showToast) this.ctx.showToast(`Canal ${idx} ("${name}") importado correctamente`, "success");
        } else {
          this._notify(`Error importando canal: ${data.message || "Fallo desconocido"}`, "error");
        }
        return;
      }

      // Caso 2: JSON estructurado
      if (cleanRaw.startsWith("{") || cleanRaw.startsWith("[")) {
        try {
          const parsed = JSON.parse(cleanRaw);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && (parsed.type === "channel" || (parsed.index !== undefined && parsed.name && !parsed.public_key))) {
            const idx = parseInt(parsed.index, 10) || 1;
            const name = parsed.name || `Canal ${idx}`;
            const psk = parsed.secret || parsed.psk || "";
            const cleanPsk = (psk && psk !== MESHCORE_PUBLIC_CHANNEL_SECRET) ? psk : "";
            const exists = this.channelsList.some((c) => Number(c.index) === idx);
            if (exists) {
              const overwrite = window.confirm(
                `El Canal ${idx} ("${name}") ya existe en la configuración.\n\n¿Deseas sobreescribirlo con los datos importados?`
              );
              if (!overwrite) return;
            }

            const res = await fetch("/api/channels", {
              method: "POST",
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ index: idx, name, psk: cleanPsk, overwrite: exists }),
            });
            const data = await res.json();
            if (data.status === "ok") {
              if (closeCallback) closeCallback();
              await this.fetchChannels();
              if (this.ctx.switchChannel) this.ctx.switchChannel(idx);
              if (this.ctx.showToast) this.ctx.showToast(`Canal ${idx} ("${name}") importado correctamente`, "success");
            } else {
              this._notify(`Error importando canal: ${data.message || "Fallo desconocido"}`, "error");
            }
            return;
          }
        } catch (ignore) {}
      }

      // Caso 3: Contacto(s) (URI meshcore://contact/add?..., JSON o hexadecimal)
      const res = await fetch("/api/contacts/import", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ data: cleanRaw }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        if (closeCallback) closeCallback();
        if (this.ctx.fetchNodes) await this.ctx.fetchNodes();
        const count = data.imported ?? (data.data ? (Array.isArray(data.data) ? data.data.length : 1) : 1);
        if (this.ctx.showToast) this.ctx.showToast(`Se importaron ${count} contacto(s) correctamente a la libreta`, "success");
      } else {
        this._notify(`Error importando: ${data.message || "Formato no válido o contacto rechazado"}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red al procesar importación: ${err.message}`, "error");
    }
  }

  async fetchLocalNodeConfig(force = false) {
    try {
      const url = force ? "/api/config?refresh=true" : "/api/config";
      const res = await fetch(url, {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        this._lastFetchTime = Date.now();
        this.populateLocalConfig(data.data);
      }
    } catch (e) {
      console.warn("Error obteniendo configuración local:", e);
    }
  }

  populateLocalConfig(incoming) {
    if (!incoming || typeof incoming !== "object") return;
    if (!this.cachedConfig) this.cachedConfig = {};

    // Combinar de forma atómica ignorando propiedades undefined y null para evitar pérdida de estado
    for (const [k, v] of Object.entries(incoming)) {
      if (v !== undefined && v !== null) {
        this.cachedConfig[k] = v;
      }
    }

    if (incoming.device_epoch_time) {
      if (!this._deviceClockHostBase || this._reconnected) {
        this._deviceClockHostBase = Date.now();
      }
    }
    const devUptimeVal = incoming.device_uptime ?? incoming.uptime_secs ?? incoming.uptime;
    if (devUptimeVal != null) {
      if (this._deviceUptime == null || this._reconnected) {
        this._deviceUptime = Number(devUptimeVal);
        this._deviceUptimeHostBase = Date.now();
        this._reconnected = false;
      }
    }
    const cfg = this.cachedConfig;

    const nameInput = document.getElementById("localNodeName");
    if (nameInput && cfg.name) nameInput.value = cfg.name;

    const pkInput = document.getElementById("localNodePubkey");
    if (pkInput && cfg.public_key) {
      pkInput.value = cfg.public_key;
      this.ctx.localNodePubkey = cfg.public_key.toLowerCase();
    }

    // Badges de Cabecera del Nodo Local
    const hwBadge = document.getElementById("localHwBoardBadge");
    if (hwBadge) {
      const hwName = cfg.hardware_board || cfg.board || cfg.model;
      if (hwName) hwBadge.textContent = hwName;
    }

    const fwBadge = document.getElementById("localFwVersionBadge");
    if (fwBadge) {
      const fw = cfg.fw_ver || cfg.ver || cfg.fw_version;
      const build = cfg.fw_build || cfg.build;
      if (fw) {
        fwBadge.textContent = build ? `FW: v${fw} (b${build})` : `FW: v${fw}`;
      }
    }

    const roleBadge = document.getElementById("localNodeRoleBadge");
    if (roleBadge && (cfg.repeat != null || cfg.repeat_enabled != null || cfg.role != null)) {
      const isRepeat = Boolean(cfg.repeat ?? cfg.repeat_enabled);
      roleBadge.textContent = isRepeat ? "Repeater / Router" : (cfg.role || "Base Station");
      roleBadge.className = `badge-pill ${isRepeat ? "badge-warning" : "badge-primary"}`;
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
    if (bwInput && bwVal != null) {
      let b = parseFloat(bwVal);
      if (b > 1000) b = b / 1000.0;
      const bStr = String(b);
      const supportedBws = ["7.8", "10.4", "15.6", "20.8", "31.25", "41.7", "62.5", "125", "250", "500"];
      const found = supportedBws.find((opt) => parseFloat(opt) === b);
      bwInput.value = found || bStr;
    }

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

    // Balizas & Transmisiones Periódicas
    const advIntVal = cfg.advert_interval ?? cfg.beacon_interval;
    const advChk = document.getElementById("localAdvertEnable");
    const advBadge = document.getElementById("localAdvertEnableBadge");
    const advIntInput = document.getElementById("localAdvertInterval");
    if (advChk && advIntVal !== undefined && advIntVal !== null) {
      const isAdvOn = Number(advIntVal) > 0;
      advChk.checked = isAdvOn;
      if (advBadge) {
        advBadge.textContent = isAdvOn ? "ON" : "OFF";
        advBadge.classList.toggle("badge-active", isAdvOn);
      }
      if (advIntInput) {
        advIntInput.disabled = !isAdvOn;
        advIntInput.style.opacity = isAdvOn ? "1" : "0.5";
        if (isAdvOn) advIntInput.value = advIntVal;
        else if (!advIntInput.value) advIntInput.value = "300";
      }
    } else if (advIntInput && advIntVal != null) {
      advIntInput.value = advIntVal;
    }

    const telemIntVal = cfg.telemetry_interval;
    const telemChk = document.getElementById("localTelemetryEnable");
    const telemBadge = document.getElementById("localTelemetryEnableBadge");
    const telemIntInput = document.getElementById("localTelemetryInterval");
    if (telemChk && (telemIntVal !== undefined && telemIntVal !== null)) {
      const isTelemOn = Number(telemIntVal) > 0 && cfg.telemetry_mode_base !== 0;
      telemChk.checked = isTelemOn;
      if (telemBadge) {
        telemBadge.textContent = isTelemOn ? "ON" : "OFF";
        telemBadge.classList.toggle("badge-active", isTelemOn);
      }
      if (telemIntInput) {
        telemIntInput.disabled = !isTelemOn;
        telemIntInput.style.opacity = isTelemOn ? "1" : "0.5";
        if (Number(telemIntVal) > 0) telemIntInput.value = telemIntVal;
        else if (!telemIntInput.value) telemIntInput.value = "60";
      }
    } else if (telemIntInput && telemIntVal != null) {
      telemIntInput.value = telemIntVal;
    }

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
    if (sumQueue && (cfg.queue_len != null || cfg.queue_depth != null)) {
      sumQueue.textContent = `${cfg.queue_len ?? cfg.queue_depth} paquetes`;
    }

    const sumPos = document.getElementById("localSummaryPos");
    if (sumPos) {
      const lat = cfg.latitude ?? cfg.adv_lat;
      const lon = cfg.longitude ?? cfg.adv_lon;
      if (lat != null && lon != null && !isNaN(Number(lat)) && !isNaN(Number(lon))) {
        sumPos.textContent = `${Number(lat).toFixed(4)}, ${Number(lon).toFixed(4)}`;
      } else if (cfg.latitude != null || cfg.adv_lat != null) {
        sumPos.textContent = "--";
      }
    }

    // Posición GPS & Propietario Form Inputs
    const ownerInput = document.getElementById("localOwnerInfo");
    if (ownerInput && (cfg.owner_info !== undefined || cfg.owner !== undefined)) {
      ownerInput.value = cfg.owner_info ?? cfg.owner ?? "";
    }

    const latInput = document.getElementById("localGpsLat");
    if (latInput && (cfg.latitude != null || cfg.adv_lat != null)) latInput.value = cfg.latitude ?? cfg.adv_lat;

    const lonInput = document.getElementById("localGpsLon");
    if (lonInput && (cfg.longitude != null || cfg.adv_lon != null)) lonInput.value = cfg.longitude ?? cfg.adv_lon;

    const altInput = document.getElementById("localGpsAlt");
    if (altInput && (cfg.altitude != null || cfg.alt != null)) altInput.value = cfg.altitude ?? cfg.alt;

    const posFixedSwitch = document.getElementById("localPosFixed");
    const posFixedBadge = document.getElementById("localPosFixedBadge");
    if (posFixedSwitch && (cfg.fixed_position != null || cfg.pos_fixed != null)) {
      const isFixed = Boolean(cfg.fixed_position ?? cfg.pos_fixed);
      posFixedSwitch.checked = isFixed;
      if (posFixedBadge) {
        posFixedBadge.textContent = isFixed ? "FIJA" : "OFF";
        posFixedBadge.classList.toggle("is-active", isFixed);
      }
    }

    // Parámetros Avanzados del Firmware MeshCore
    const pinInput = document.getElementById("localDevicePin");
    if (pinInput && (cfg.pin !== undefined || cfg.device_pin !== undefined)) {
      const pinVal = cfg.pin ?? cfg.device_pin;
      pinInput.value = pinVal != null ? String(pinVal) : "";
    }

    const pathHashSelect = document.getElementById("localPathHashMode");
    if (pathHashSelect && cfg.path_hash_mode !== undefined) {
      pathHashSelect.value = String(cfg.path_hash_mode);
    }

    const rxDelayInput = document.getElementById("localRxDelay");
    if (rxDelayInput && cfg.rx_delay !== undefined) {
      rxDelayInput.value = cfg.rx_delay != null ? String(cfg.rx_delay) : "";
    }

    const airtimeFactorInput = document.getElementById("localAirtimeFactor");
    if (airtimeFactorInput && cfg.airtime_factor !== undefined) {
      airtimeFactorInput.value = cfg.airtime_factor != null ? String(cfg.airtime_factor) : "";
    }

    const telemBaseSelect = document.getElementById("localTelemBase");
    if (telemBaseSelect && cfg.telemetry_mode_base !== undefined) {
      telemBaseSelect.value = String(cfg.telemetry_mode_base);
    }

    const telemLocSelect = document.getElementById("localTelemLoc");
    if (telemLocSelect && cfg.telemetry_mode_loc !== undefined) {
      telemLocSelect.value = String(cfg.telemetry_mode_loc);
    }

    const telemEnvSelect = document.getElementById("localTelemEnv");
    if (telemEnvSelect && cfg.telemetry_mode_env !== undefined) {
      telemEnvSelect.value = String(cfg.telemetry_mode_env);
    }

    if (cfg.adv_loc_policy !== undefined) {
      const advLocChk = document.getElementById("localAdvLocPolicy");
      const advLocBadge = document.getElementById("localAdvLocBadge");
      const isAdv = Boolean(cfg.adv_loc_policy);
      if (advLocChk) advLocChk.checked = isAdv;
      if (advLocBadge) {
        advLocBadge.textContent = isAdv ? "ON" : "OFF";
        advLocBadge.classList.toggle("badge-active", isAdv);
      }
    }

    if (cfg.multi_acks !== undefined) {
      const multiAcksChk = document.getElementById("localMultiAcks");
      const multiAcksBadge = document.getElementById("localMultiAcksBadge");
      const isMulti = Boolean(cfg.multi_acks);
      if (multiAcksChk) multiAcksChk.checked = isMulti;
      if (multiAcksBadge) {
        multiAcksBadge.textContent = isMulti ? "ON" : "OFF";
        multiAcksBadge.classList.toggle("badge-active", isMulti);
      }
    }

    if (cfg.manual_add_contacts !== undefined) {
      const manualAddChk = document.getElementById("localManualAddContacts");
      const manualAddBadge = document.getElementById("localManualAddBadge");
      const isManual = Boolean(cfg.manual_add_contacts);
      if (manualAddChk) manualAddChk.checked = isManual;
      if (manualAddBadge) {
        manualAddBadge.textContent = isManual ? "ON" : "OFF";
        manualAddBadge.classList.toggle("badge-active", isManual);
      }
    }

    if (cfg.custom_vars && typeof cfg.custom_vars === "object") {
      this.renderCustomVarsTable(cfg.custom_vars);
    }
    if (cfg.flood_scope && typeof cfg.flood_scope === "object") {
      const scopeName = cfg.flood_scope.scope_name || "";
      const inScope = document.getElementById("inputFloodScope");
      const lbl = document.getElementById("currentFloodScopeLabel");
      if (inScope && !inScope.value) inScope.value = scopeName;
      if (lbl) lbl.textContent = scopeName ? scopeName : "Global (*)";
    }
    if (cfg.autoadd_config && typeof cfg.autoadd_config === "object") {
      const flags = Number(cfg.autoadd_config.config ?? 0);
      const maxHops = Number(cfg.autoadd_config.max_hops ?? 3);
      const chkChat = document.getElementById("chkAutoAddChat");
      const chkOverwrite = document.getElementById("chkAutoAddOverwrite");
      const numHops = document.getElementById("numAutoAddMaxHops");
      if (chkOverwrite) chkOverwrite.checked = (flags & 1) !== 0;
      if (chkChat) chkChat.checked = (flags & 2) !== 0 || flags === 0;
      if (numHops && maxHops) numHops.value = String(maxHops);
    }


    // Tarjeta de Alimentación Host USB (Estación Base 5V)
    const elSolar = document.getElementById("localSolarValue");
    const elSolarStatus = document.getElementById("localSolarStatus");
    if (elSolar && (cfg.power_source != null || cfg.battery_pct != null)) {
      if (cfg.power_source) {
        elSolar.textContent = cfg.power_source;
      } else if (cfg.battery_pct != null && cfg.battery_pct < 100) {
        elSolar.textContent = "Batería LiPo";
      } else {
        elSolar.textContent = "USB Conectado";
      }
    }
    if (elSolarStatus && (cfg.battery_mv != null || cfg.voltage != null)) {
      const mv = cfg.battery_mv != null ? cfg.battery_mv : Math.round((cfg.voltage || 5) * 1000);
      const vStr = cfg.voltage != null ? `${cfg.voltage} V` : `${(mv / 1000).toFixed(2)} V`;
      elSolarStatus.textContent = `${mv} mV (${vStr})`;
    }

    const elClock = document.getElementById("localClockValue");
    const elClockStatus = document.getElementById("localClockStatus");
    if (cfg.device_epoch_time) {
      const elapsedMs = this._deviceClockHostBase ? (Date.now() - this._deviceClockHostBase) : 0;
      const devDate = new Date((cfg.device_epoch_time * 1000) + elapsedMs);
      if (elClock) elClock.textContent = devDate.toLocaleTimeString();
      if (elClockStatus) {
        const drift = cfg.device_time_drift != null
          ? Math.abs(cfg.device_time_drift)
          : (this._deviceClockHostBase
              ? Math.abs(Math.floor(this._deviceClockHostBase / 1000) - cfg.device_epoch_time)
              : 0);

        if (drift <= 2) {
          elClockStatus.textContent = "Sincronizado (±0s)";
          elClockStatus.style.color = "var(--accent-success, #22c55e)";
        } else if (drift <= 60) {
          elClockStatus.textContent = `Desfase: ${drift}s`;
          elClockStatus.style.color = "var(--accent-warning, #eab308)";
        } else {
          elClockStatus.textContent = `Desfase: ${Math.round(drift / 60)}m`;
          elClockStatus.style.color = "var(--accent-danger, #ef4444)";
        }
      }
    } else if (cfg.clock) {
      if (elClock) elClock.textContent = cfg.clock;
      if (elClockStatus) {
        elClockStatus.textContent = "Sincronizado con Host";
        elClockStatus.style.color = "var(--accent-success, #22c55e)";
      }
    }

    const elUptime = document.getElementById("localUptimeValue");
    if (elUptime) {
      if (this._deviceUptime != null && this._deviceUptimeHostBase) {
        const elapsedSec = Math.floor((Date.now() - this._deviceUptimeHostBase) / 1000);
        const totalSec = this._deviceUptime + elapsedSec;
        const days = Math.floor(totalSec / 86400);
        const hours = Math.floor((totalSec % 86400) / 3600);
        const mins = Math.floor((totalSec % 3600) / 60);
        elUptime.textContent = days > 0
          ? `${days}d ${hours}h ${mins}m`
          : (hours > 0 ? `${hours}h ${mins}m` : `${mins}m`);
      } else if (cfg.uptime_str != null || cfg.uptime != null) {
        if (cfg.uptime_str) {
          elUptime.textContent = cfg.uptime_str;
        } else {
          const totalSec = Number(cfg.uptime) || 0;
          const days = Math.floor(totalSec / 86400);
          const hours = Math.floor((totalSec % 86400) / 3600);
          const mins = Math.floor((totalSec % 3600) / 60);
          elUptime.textContent = days > 0
            ? `${days}d ${hours}h ${mins}m`
            : (hours > 0 ? `${hours}h ${mins}m` : `${mins}m`);
        }
      }
    }

    const elAirtime = document.getElementById("localAirtimeValue");
    if (elAirtime && cfg.airtime_ms != null) {
      elAirtime.textContent = `${cfg.airtime_ms} ms`;
    }

    const elDuty = document.getElementById("localAirtimeDuty");
    if (elDuty && cfg.duty_cycle_pct != null) {
      elDuty.textContent = `Duty Cycle: ${cfg.duty_cycle_pct}%`;
    }

    const elNoise = document.getElementById("localNoiseValue");
    if (elNoise && cfg.noise_floor_dbm != null) {
      elNoise.textContent = `${cfg.noise_floor_dbm} dBm`;
    }

    const elPkts = document.getElementById("localPacketsValue");
    if (elPkts && (cfg.tx_count != null || cfg.rx_count != null)) {
      elPkts.textContent = `${cfg.tx_count ?? 0} TX / ${cfg.rx_count ?? 0} RX`;
    }

    const elPktErrs = document.getElementById("localPacketErrorsValue");
    if (elPktErrs && (cfg.duplicate_packets != null || cfg.packet_errors != null)) {
      elPktErrs.textContent = `Duplicados: ${cfg.duplicate_packets ?? 0} | Errores: ${cfg.packet_errors ?? 0}`;
    }

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
    const advertEnabled = Boolean(document.getElementById("localAdvertEnable")?.checked);
    const advert_interval = advertEnabled
      ? parseInt(document.getElementById("localAdvertInterval")?.value || "300", 10)
      : 0;

    const telemEnabled = Boolean(document.getElementById("localTelemetryEnable")?.checked);
    const telemetry_interval = telemEnabled
      ? parseInt(document.getElementById("localTelemetryInterval")?.value || "60", 10)
      : 0;

    const pinVal = document.getElementById("localDevicePin")?.value.trim();
    const pin = pinVal ? parseInt(pinVal, 10) : 0;
    const path_hash_mode = parseInt(document.getElementById("localPathHashMode")?.value || "0", 10);
    const rxDelayVal = document.getElementById("localRxDelay")?.value.trim();
    const rx_delay = rxDelayVal ? parseInt(rxDelayVal, 10) : 0;
    const airtimeFactorVal = document.getElementById("localAirtimeFactor")?.value.trim();
    const airtime_factor = airtimeFactorVal ? parseInt(airtimeFactorVal, 10) : 0;
    let telemetry_mode_base = parseInt(document.getElementById("localTelemBase")?.value || "1", 10);
    if (!telemEnabled) {
      telemetry_mode_base = 0;
    }
    const telemetry_mode_loc = parseInt(document.getElementById("localTelemLoc")?.value || "1", 10);
    const telemetry_mode_env = parseInt(document.getElementById("localTelemEnv")?.value || "1", 10);
    const adv_loc_policy = Boolean(document.getElementById("localAdvLocPolicy")?.checked);
    const multi_acks = Boolean(document.getElementById("localMultiAcks")?.checked);
    const manual_add_contacts = Boolean(document.getElementById("localManualAddContacts")?.checked);

    const payload = {
      frequency: freq,
      tx_power,
      spreading_factor: sf,
      bandwidth: bw,
      coding_rate: cr,
      repeat,
      hop_limit,
      telemetry_interval,
      advert_interval,
      beacon_interval: advert_interval,
      pin,
      path_hash_mode,
      rx_delay,
      airtime_factor,
      telemetry_mode_base,
      telemetry_mode_loc,
      telemetry_mode_env,
      adv_loc_policy,
      multi_acks,
      manual_add_contacts,
    };

    try {
      const res = await fetch("/api/config/radio", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.populateLocalConfig(payload);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.radio_cfg_ok'), "success");
      } else {
        this._notify("Error guardando radio: " + (data.message || "desconocido"), "error");
      }
    } catch (e) {
      this._notify("Error de red guardando radio: " + e.message, "error");
    }
  }

  async saveLocalIdentityAndPosition() {
    const name = document.getElementById("localNodeName")?.value.trim() || "";
    const owner_info = document.getElementById("localOwnerInfo")?.value.trim() || "";
    const lat = parseFloat(document.getElementById("localGpsLat")?.value || "");
    const lon = parseFloat(document.getElementById("localGpsLon")?.value || "");
    const alt = parseFloat(document.getElementById("localGpsAlt")?.value || "");

    const payload = { name, owner_info };
    const posFixedElem = document.getElementById("localPosFixed");
    if (posFixedElem) {
      payload.fixed_position = Boolean(posFixedElem.checked);
    }
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
        this.populateLocalConfig(payload);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.identity_ok'), "success");
      } else {
        this._notify("Error guardando identidad: " + (data.message || "desconocido"), "error");
      }
    } catch (e) {
      this._notify("Error de red: " + e.message, "error");
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
    if (window.initLucideIcons) {
      window.initLucideIcons(this.dom.qrShareModal);
    }
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

  async fetchCustomVars() {
    try {
      const res = await fetch("/api/config/custom_vars", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok") {
        const varsObj = data.custom_vars || data.data || {};
        this.renderCustomVarsTable(varsObj);
      }
    } catch (e) {
      console.warn("Error consultando custom vars:", e);
    }
  }

  renderCustomVarsTable(varsObj) {
    const tbody = document.getElementById("localCustomVarsTableBody");
    if (!tbody) return;
    const entries = typeof varsObj === "object" && varsObj !== null ? Object.entries(varsObj) : [];
    if (entries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" class="text-center" style="color: var(--color-text-secondary);">Sin variables registradas</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    entries.forEach(([k, v]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="font-mono"><strong>${escapeHtml(String(k))}</strong></td>
        <td><code>${escapeHtml(String(v))}</code></td>
        <td style="text-align: right;">
          <button type="button" class="btn-danger btn-xs btn-del-custom-var" data-key="${escapeHtml(String(k))}" title="Eliminar variable">
            🗑️ Borrar
          </button>
        </td>
      `;

      const delBtn = tr.querySelector(".btn-del-custom-var");
      if (delBtn) {
        delBtn.addEventListener("click", () => this.deleteCustomVar(k));
      }
      tbody.appendChild(tr);
    });
  }

  async saveCustomVar(key = "", val = "") {
    const k = key || document.getElementById("inputCustomVarKey")?.value.trim() || "";
    const v = val || document.getElementById("inputCustomVarVal")?.value.trim() || "";
    if (!k) {
      this._notify("El nombre de la variable no puede estar vacío", "warning");
      return;
    }

    try {
      const res = await fetch("/api/config/custom_vars", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ key: k, value: v }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.renderCustomVarsTable(data.custom_vars || data.data || {});
        const inKey = document.getElementById("inputCustomVarKey");
        const inVal = document.getElementById("inputCustomVarVal");
        if (inKey) inKey.value = "";
        if (inVal) inVal.value = "";
        if (this.ctx.showToast) this.ctx.showToast(`Variable '${k}' guardada`, "success");
      } else {
        this._notify(`Error guardando variable: ${data.message || "desconocido"}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red: ${err.message}`, "error");
    }
  }

  async deleteCustomVar(key) {
    if (!key || !confirm(`¿Deseas eliminar la variable personalizada '${key}'?`)) return;
    try {
      const res = await fetch(`/api/config/custom_vars?key=${encodeURIComponent(key)}`, {
        method: "DELETE",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        this.renderCustomVarsTable(data.custom_vars || data.data || {});
        if (this.ctx.showToast) this.ctx.showToast(`Variable '${key}' eliminada`, "info");
      } else {
        this._notify(`Error eliminando variable: ${data.message || "desconocido"}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red: ${err.message}`, "error");
    }
  }

  async fetchFloodScope() {
    try {
      const res = await fetch("/api/config/flood_scope", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok") {
        const fs = data.flood_scope || data.data || {};
        const scopeName = fs.scope_name || "";
        const inScope = document.getElementById("inputFloodScope");
        const lbl = document.getElementById("currentFloodScopeLabel");
        if (inScope && !inScope.value) inScope.value = scopeName;
        if (lbl) lbl.textContent = scopeName ? scopeName : "Global (*)";
      }
    } catch (e) {
      console.warn("Error consultando flood scope:", e);
    }
  }

  async saveFloodScope() {
    const inScope = document.getElementById("inputFloodScope");
    const scopeVal = inScope ? inScope.value.trim() : "";
    try {
      const res = await fetch("/api/config/flood_scope", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: scopeVal }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const lbl = document.getElementById("currentFloodScopeLabel");
        if (lbl) lbl.textContent = scopeVal ? scopeVal : "Global (*)";
        if (this.ctx.showToast) this.ctx.showToast(`Ámbito de inundación aplicado: ${scopeVal || "Global"}`, "success");
      } else {
        this._notify(`Error guardando scope: ${data.message || "desconocido"}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red: ${err.message}`, "error");
    }
  }

  async resetFloodScope() {
    try {
      const res = await fetch("/api/config/flood_scope", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: "*" }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const inScope = document.getElementById("inputFloodScope");
        const lbl = document.getElementById("currentFloodScopeLabel");
        if (inScope) inScope.value = "";
        if (lbl) lbl.textContent = "Global (*)";
        if (this.ctx.showToast) this.ctx.showToast("Ámbito de inundación restablecido a Global (*)", "info");
      }
    } catch (err) {
      this._notify(`Error de red: ${err.message}`, "error");
    }
  }

  async fetchAutoAddConfig() {
    try {
      const res = await fetch("/api/config/autoadd", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (data.status === "ok") {
        const cfg = data.autoadd_config || data.data || {};
        const flags = Number(cfg.config ?? 0);
        const maxHops = Number(cfg.max_hops ?? 3);
        const chkChat = document.getElementById("chkAutoAddChat");
        const chkOverwrite = document.getElementById("chkAutoAddOverwrite");
        const numHops = document.getElementById("numAutoAddMaxHops");
        if (chkOverwrite) chkOverwrite.checked = (flags & 1) !== 0;
        if (chkChat) chkChat.checked = (flags & 2) !== 0 || flags === 0;
        if (numHops && maxHops) numHops.value = String(maxHops);
      }
    } catch (e) {
      console.warn("Error consultando autoadd config:", e);
    }
  }

  async saveAutoAddConfig() {
    const chkChat = document.getElementById("chkAutoAddChat");
    const chkOverwrite = document.getElementById("chkAutoAddOverwrite");
    const numHops = document.getElementById("numAutoAddMaxHops");
    let flags = 0;
    if (chkOverwrite?.checked) flags |= 1;
    if (chkChat?.checked) flags |= 2;
    const maxHops = numHops ? parseInt(numHops.value, 10) : 3;

    try {
      const res = await fetch("/api/config/autoadd", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ flags, max_hops: maxHops }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        if (this.ctx.showToast) this.ctx.showToast("Política de Auto-Adición guardada exitosamente", "success");
      } else {
        this._notify(`Error guardando política: ${data.message || "desconocido"}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red: ${err.message}`, "error");
    }
  }
}

