/**
 * SettingsModule - Gestión de parámetros RF del transceptor local, administración de canales,
 * importación/exportación de contactos y diagnósticos preflight.
 */

import {
  escapeHtml,
  REGION_FREQUENCIES,
  parseMeshCoreUri,
  MESHCORE_PUBLIC_CHANNEL_SECRET,
} from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class SettingsModule {
  constructor(context) {
    this.ctx = context;
    this.channelsList = [];
    this.cachedConfig = {};
    this.observedConfig = {};
    this.dirtyFields = new Set();
    this._fieldEditVersions = new Map();
    this._configRevision = 0;
    this._configReadSequence = 0;
    this._isSavingRadio = false;
    this._isSavingIdentity = false;
    this._deviceClockHostBase = null;
    this._uptimeHostBase = null;
    this._tickInterval = null;
    this._localCliHistory = [];
    this._localCliHistoryIdx = -1;
    this._localCliTempInput = "";
    this.servicesConfig = null;
    this.servicesPresets = [];
    this._isSavingServices = false;
    this._isTestingExtMqtt = false;
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
    this.loadServicesConfig();
    this._startLiveTick();
    window.showQrModal = (title, uri, rawJson, label) => this.showQrModal(title, uri, rawJson, label);
  }

  onLanguageChange() {
    this.renderChannelsList(this.channelsList);
    if (this._customVars) this.renderCustomVarsTable(this._customVars);
    if (this.dom.chModalIndex) {
      Array.from(this.dom.chModalIndex.options).forEach(option => {
        option.textContent = I18n.t('settings.secondary_channel', { p0: option.value });
      });
    }
    this._applyLocalConfigCapabilities();
    if (this.servicesConfig) {
      this._updateServicesStatusBadge(this.servicesConfig);
    }
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
    } else if (this.ctx && typeof this.ctx.showAlert === "function") {
      this.ctx.showAlert(msg, { type });
    } else if (typeof window !== "undefined" && typeof window.showAlert === "function") {
      window.showAlert(msg, { type });
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
      btnHeaderAddContact: document.getElementById("btnHeaderAddContact"),
      createContactModal: document.getElementById("createContactModal"),
      btnCloseCreateContactModal: document.getElementById("btnCloseCreateContactModal"),
      btnCancelCreateContact: document.getElementById("btnCancelCreateContact"),
      createContactForm: document.getElementById("createContactForm"),
      contactModalPubKey: document.getElementById("contactModalPubKey"),
      contactModalName: document.getElementById("contactModalName"),
      contactModalLat: document.getElementById("contactModalLat"),
      contactModalLon: document.getElementById("contactModalLon"),
      contactModalFavorite: document.getElementById("contactModalFavorite"),
      contactModalFavBadge: document.getElementById("contactModalFavBadge"),
      qrShareModal: document.getElementById("qrShareModal"),
      btnCloseQrShareModal: document.getElementById("btnCloseQrShareModal"),
      btnCloseQrModalAction: document.getElementById("btnCloseQrModalAction"),
      qrCanvas: document.getElementById("qrCanvas"),
      qrUriDisplay: document.getElementById("qrUriDisplay"),
      qrShareJson: document.getElementById("qrShareJson"),
      qrModalTitle: document.getElementById("qrModalTitle"),
      btnCopyQrUri: document.getElementById("btnCopyQrUri"),
      btnDownloadQrJson: document.getElementById("btnDownloadQrJson"),
      btnHeaderImportContact: document.getElementById("btnHeaderImportContact"),
      btnImportData: document.getElementById("btnImportData"),
      importModal: document.getElementById("importModal"),
      importPayloadInput: document.getElementById("importPayloadInput"),
      btnCloseImportModal: document.getElementById("btnCloseImportModal"),
      btnCancelImport: document.getElementById("btnCancelImport"),
      importForm: document.getElementById("importForm"),
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

      // Servicios de Red & MQTT Externo
      badgeExtMqttStatus: document.getElementById("badgeExtMqttStatus"),
      chkExternalMqttEnabled: document.getElementById("chkExternalMqttEnabled"),
      selExtMqttPreset: document.getElementById("selExtMqttPreset"),
      presetTypeBadge: document.getElementById("presetTypeBadge"),
      presetDescriptionText: document.getElementById("presetDescriptionText"),
      btnSaveCurrentAsPreset: document.getElementById("btnSaveCurrentAsPreset"),
      btnDeleteCustomPreset: document.getElementById("btnDeleteCustomPreset"),
      inputExtMqttHost: document.getElementById("inputExtMqttHost"),
      inputExtMqttPort: document.getElementById("inputExtMqttPort"),
      selExtMqttTransport: document.getElementById("selExtMqttTransport"),
      chkExtMqttTls: document.getElementById("chkExtMqttTls"),
      chkExtMqttTlsVerify: document.getElementById("chkExtMqttTlsVerify"),
      selExtMqttAuthType: document.getElementById("selExtMqttAuthType"),
      selExtMqttPrivacy: document.getElementById("selExtMqttPrivacy"),
      extMqttUserPassFields: document.getElementById("extMqttUserPassFields"),
      inputExtMqttUser: document.getElementById("inputExtMqttUser"),
      inputExtMqttPass: document.getElementById("inputExtMqttPass"),
      extMqttTokenField: document.getElementById("extMqttTokenField"),
      inputExtMqttToken: document.getElementById("inputExtMqttToken"),
      selExtMqttTopicMode: document.getElementById("selExtMqttTopicMode"),
      inputExtMqttPrefix: document.getElementById("inputExtMqttPrefix"),
      inputExtMqttIata: document.getElementById("inputExtMqttIata"),
      selExtMqttFormat: document.getElementById("selExtMqttFormat"),
      selExtMqttQos: document.getElementById("selExtMqttQos"),
      chkExtObserverMode: document.getElementById("chkExtObserverMode"),
      chkExtFilterPublic: document.getElementById("chkExtFilterPublic"),
      chkExtFilterChannels: document.getElementById("chkExtFilterChannels"),
      chkExtFilterDirect: document.getElementById("chkExtFilterDirect"),
      chkExtFilterTelemetry: document.getElementById("chkExtFilterTelemetry"),
      chkExtFilterNodes: document.getElementById("chkExtFilterNodes"),
      chkExtFilterRaw: document.getElementById("chkExtFilterRaw"),
      chkExtDownlink: document.getElementById("chkExtDownlink"),
      btnTestExternalMqtt: document.getElementById("btnTestExternalMqtt"),
      extMqttTestStatus: document.getElementById("extMqttTestStatus"),

      // MQTT Local (n8n / Domótica)
      chkLocalMqttEnabled: document.getElementById("chkLocalMqttEnabled"),
      inputLocalMqttHost: document.getElementById("inputLocalMqttHost"),
      inputLocalMqttPort: document.getElementById("inputLocalMqttPort"),
      inputLocalMqttPrefix: document.getElementById("inputLocalMqttPrefix"),
      chkLocalMqttAuth: document.getElementById("chkLocalMqttAuth"),
      localMqttCredsRow: document.getElementById("localMqttCredsRow"),
      inputLocalMqttUser: document.getElementById("inputLocalMqttUser"),
      inputLocalMqttPass: document.getElementById("inputLocalMqttPass"),

      // Servidor TCP Companion
      chkTcpServerEnabled: document.getElementById("chkTcpServerEnabled"),
      selTcpServerHost: document.getElementById("selTcpServerHost"),
      inputTcpServerPort: document.getElementById("inputTcpServerPort"),
      inputTcpMaxClients: document.getElementById("inputTcpMaxClients"),
      inputTcpAllowedIps: document.getElementById("inputTcpAllowedIps"),

      btnSaveServicesConfig: document.getElementById("btnSaveServicesConfig"),

      // Modal Preset
      modalSavePreset: document.getElementById("modalSavePreset"),
      inputNewPresetName: document.getElementById("inputNewPresetName"),
      inputNewPresetDesc: document.getElementById("inputNewPresetDesc"),
      btnCloseSavePresetModal: document.getElementById("btnCloseSavePresetModal"),
      btnCancelSavePreset: document.getElementById("btnCancelSavePreset"),
      btnConfirmSavePreset: document.getElementById("btnConfirmSavePreset"),
    };
  }

  _setFieldIfNotDirty(id, value, isChecked = null) {
    if (this.dirtyFields.has(id)) return;
    const el = document.getElementById(id);
    if (!el || (document.activeElement === el && !this._confirmedFieldIds?.has(id))) return;
    if (isChecked !== null) {
      el.checked = Boolean(isChecked);
    } else if (value != null) {
      el.value = String(value);
    }
  }

  _bindEvents() {
    // Rastreo de campos en borrador modificados por el usuario (F01)
    const markDirty = (e) => {
      if (e.target && e.target.id) {
        this.dirtyFields.add(e.target.id);
        this._fieldEditVersions.set(e.target.id, (this._fieldEditVersions.get(e.target.id) || 0) + 1);
      }
    };
    [
      "localNodeName", "localFreq", "localRegion", "localSf", "localBw", "localCr",
      "localTxPower", "localHopLimit", "localRepeatMode", "localOwnerInfo",
      "localGpsLat", "localGpsLon", "localGpsAlt", "localPosFixed",
      "localDevicePin", "localPathHashMode", "localRxDelay", "localAirtimeFactor",
      "localTelemBase", "localTelemLoc", "localTelemEnv", "localAdvLocPolicy",
      "localMultiAcks", "localManualAddContacts", "localAdvertInterval",
      "localAdvertEnable", "localTelemetryInterval", "localTelemetryEnable",
      "chkAutoAddChat", "chkAutoAddOverwrite", "numAutoAddMaxHops", "inputFloodScope"
    ].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("input", markDirty);
        el.addEventListener("change", markDirty);
      }
    });

    // Copiar clave pública local al portapapeles
    const btnCopyPk = document.getElementById("btnCopyLocalPubkey");
    if (btnCopyPk) {
      btnCopyPk.addEventListener("click", async () => {
        const pkInput = document.getElementById("localNodePubkey");
        const val = pkInput?.value?.trim();
        if (val) {
          try {
            await navigator.clipboard.writeText(val);
            this._notify(I18n.t("qr.copied") || "Clave pública copiada al portapapeles", "success");
          } catch (_err) {
            pkInput.select();
            document.execCommand("copy");
            this._notify(I18n.t("qr.copied") || "Clave pública copiada al portapapeles", "success");
          }
        }
      });
    }

    // 1. Crear Canal Modal
    const openCreateChannel = () => {
      if (!this.dom.createChannelModal) return;

      const occupiedIndices = new Set(this.channelsList.map((c) => Number(c.index)));
      const availableIndices = [1, 2, 3, 4, 5, 6, 7].filter((idx) => !occupiedIndices.has(idx));

      if (availableIndices.length === 0) {
        const msg = I18n.t("settings.slots_full");
        this._notify(msg, "warning");
        return;
      }

      if (this.dom.chModalIndex) {
        this.dom.chModalIndex.innerHTML = "";
        availableIndices.forEach((idx) => {
          const opt = document.createElement("option");
          opt.value = String(idx);
          I18n.setText(opt, "settings.secondary_channel", { p0: idx });
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
        I18n.setText(this.dom.chModalEncryptedBadge, "settings.encrypted");
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
          I18n.setText(this.dom.chModalEncryptedBadge, isEnc ? "settings.encrypted" : "settings.open");
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

        const btnSubmit = this.dom.createChannelForm.querySelector('button[type="submit"]');
        if (btnSubmit) btnSubmit.disabled = true;

        try {
          const res = await fetch("/api/channels", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ index, name, psk }),
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.status === "ok") {
            closeCreateChannel();
            await this.fetchChannels();
            if (this.ctx.switchChannel) this.ctx.switchChannel(index);
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.ch_saved').replace('{index}', index).replace('{name}', escapeHtml(name)), "success");
          } else {
            const errDetail = data.detail || data.message || data.error || I18n.t("settings.unknown_failure");
            this._notify(I18n.t("settings.channel_save_error", { p0: errDetail }), "error");
          }
        } catch (err) {
          this._notify(I18n.t('settings.channel_save_network_error', { error: err.message }), "error");
        } finally {
          if (btnSubmit) btnSubmit.disabled = false;
        }
      });
    }

    // 3. Crear Contacto Modal
    const openCreateContact = () => {
      if (!this.dom.createContactModal) return;
      this.dom.createContactModal.classList.remove("hidden");
      if (this.dom.contactModalPubKey) this.dom.contactModalPubKey.value = "";
      if (this.dom.contactModalName) this.dom.contactModalName.value = "";
      if (this.dom.contactModalLat) this.dom.contactModalLat.value = "";
      if (this.dom.contactModalLon) this.dom.contactModalLon.value = "";
      if (this.dom.contactModalFavorite) {
        this.dom.contactModalFavorite.checked = false;
      }
      if (this.dom.contactModalFavBadge) {
        I18n.setText(this.dom.contactModalFavBadge, "settings.no");
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
          I18n.setText(this.dom.contactModalFavBadge, isFav ? "settings.yes" : "settings.no");
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

        const btnSubmit = this.dom.createContactForm.querySelector('button[type="submit"]');
        if (btnSubmit) btnSubmit.disabled = true;

        const payload = { public_key: pubkey, name: name, alias: name, role: role, is_favorite: isFavorite };
        const latVal = this.dom.contactModalLat ? parseFloat(this.dom.contactModalLat.value) : NaN;
        const lonVal = this.dom.contactModalLon ? parseFloat(this.dom.contactModalLon.value) : NaN;
        if (!isNaN(latVal)) payload.latitude = latVal;
        if (!isNaN(lonVal)) payload.longitude = lonVal;

        try {
          const res = await fetch("/api/contacts", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.status === "ok") {
            closeCreateContact();
            if (this.ctx.fetchNodes) await this.ctx.fetchNodes();
            if (this.ctx.setDmTarget) this.ctx.setDmTarget(pubkey, name || pubkey);
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.contact_added').replace('{name}', name || pubkey.slice(0, 8)), "success");
          } else {
            const errDetail = data.detail || data.message || data.error || I18n.t("settings.unknown_failure");
            this._notify(I18n.t("settings.contact_add_error", { p0: errDetail }), "error");
          }
        } catch (err) {
          this._notify(I18n.t('settings.contact_add_network_error', { error: err.message }), "error");
        } finally {
          if (btnSubmit) btnSubmit.disabled = false;
        }
      });
    }

    // 4. Modal QR
    const closeQr = () => {
      if (this.dom.qrShareModal) this.dom.qrShareModal.classList.add("hidden");
    };
    if (this.dom.btnCloseQrShareModal) this.dom.btnCloseQrShareModal.addEventListener("click", closeQr);
    if (this.dom.btnCloseQrModalAction) this.dom.btnCloseQrModalAction.addEventListener("click", closeQr);
    if (this.dom.qrShareModal) {
      this.dom.qrShareModal.addEventListener("click", (e) => {
        if (e.target === this.dom.qrShareModal) closeQr();
      });
    }
    if (this.dom.btnCopyQrUri) {
      this.dom.btnCopyQrUri.addEventListener("click", () => {
        const uriEl = this.dom.qrUriDisplay;
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
        if (target === "local-services") {
          this.loadServicesConfig();
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
          this.dirtyFields.add("localFreq");
          this._fieldEditVersions.set("localFreq", (this._fieldEditVersions.get("localFreq") || 0) + 1);
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
          I18n.setText(repeatBadge, checked ? 'common.on' : 'common.off');
          if (checked) {
            repeatBadge.classList.add("badge-active");
          } else {
            repeatBadge.classList.remove("badge-active");
          }
        }
        const sumRepeat = document.getElementById("localSummaryRepeat");
        if (sumRepeat) {
          I18n.setText(sumRepeat, checked ? "settings.enabled" : "settings.disabled");
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
            I18n.setText(badge, checked ? 'common.on' : 'common.off');
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
            I18n.setText(badge, checked ? 'common.on' : 'common.off');
            badge.classList.toggle("badge-active", checked);
          }
          if (input) {
            const capability = inputId === "localTelemetryInterval" ? "telemetry_interval" : "advert_interval";
            input.disabled = !checked || this.cachedConfig.capabilities?.[capability] === false;
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
          I18n.setText(posFixedBadge, checked ? "settings.fixed" : 'common.off');
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
            I18n.setText(this.dom.apiKeyStatusHint, "settings.api_saved_hint");
          }
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.api_key_saved'), "success");
        } else {
          localStorage.removeItem("meshcore_bridge_api_key");
          if (this.dom.apiKeyStatusHint) {
            this.dom.apiKeyStatusHint.classList.remove("hidden");
            I18n.setText(this.dom.apiKeyStatusHint, "settings.api_removed_hint");
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
          I18n.setText(this.dom.apiKeyStatusHint, 'toast.api_key_del');
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
          this.appendLocalTerminalLine(I18n.t("settings.connection_error", { p0: err.message }), "term-error");
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
    document.querySelectorAll("#localTerminalHelpDrawer .help-cmd-item[data-cmd]").forEach((item) => {
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
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.geo_unsupported"), "error");
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
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.geo_received"), "success");
          },
          (err) => {
            btnGetGps.disabled = false;
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.gps_error", { p0: err.message }), "error");
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
        if (content) I18n.setText(content, "settings.maps_reindexing");
        try {
          const res = await fetch("/api/map/reload", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          if (content) I18n.setText(content, "settings.maps_reindexed");
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.tiles_reindexed"), "success");
        } catch (e) {
          if (content) I18n.setText(content, "settings.maps_check_dir");
          this.ctx.showToast?.(I18n.t("settings.maps_check_dir"), "error");
        }
      });
    }

    if (this.dom.btnSaveMapSettings) {
      this.dom.btnSaveMapSettings.addEventListener("click", () => {
        const url = (this.dom.inputLocalTileUrl?.value || "").trim();
        if (url) {
          localStorage.setItem("meshcore_local_tile_url", url);
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.maps_saved"), "success");
        }
      });
    }

    const btnClearIdb = document.getElementById("btnClearIndexedDbStorage");
    if (btnClearIdb) {
      btnClearIdb.addEventListener("click", async () => {
        const confirmMsg = I18n.t("settings.clear_storage_confirm");
        const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
        const confirmed = confirmFn
          ? await confirmFn(confirmMsg, {
              title: I18n.t("settings.clear_storage_title") || "Vaciar Almacenamiento",
              isDanger: true,
              confirmText: I18n.t("modal.confirm") || "Vaciar",
            })
          : true;
        if (!confirmed) return;
        try {
          if (this.ctx.storage && this.ctx.storage.clearAll) {
            await this.ctx.storage.clearAll();
          } else {
            indexedDB.deleteDatabase("MeshCoreStationDB");
          }
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.storage_cleared"), "info");
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.storage_error", { p0: err.message }), "error");
        }
      });
    }

    // Acciones Rápidas de Hardware
    const refreshHardware = async () => {
      const btn = this.dom.btnRefreshLocalConfig || this.dom.btnRefreshLocalTelem;
      const icon = btn ? btn.querySelector("i, [data-lucide]") : null;
      if (icon) icon.classList.add("spin-animation");
      try {
        await this.fetchLocalNodeConfig(true);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.hardware_updated"), "success");
      } catch (err) {
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.radio_query_error", { p0: err.message }), "error");
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
              I18n.setText(statusEl, "settings.host_clock");
              statusEl.style.color = "var(--accent-success, #22c55e)";
            }
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.clock_synced"), "success");
            await this.fetchLocalNodeConfig(false);
          } else {
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message || I18n.t("settings.sync_failed")}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.network_error", { p0: err.message }), "error");
        }
      });
    }

    if (this.dom.btnActionAdvertHop) {
      this.dom.btnActionAdvertHop.addEventListener("click", async () => {
        const btn = this.dom.btnActionAdvertHop;
        btn.disabled = true;
        try {
          const res = await fetch("/api/node/advert", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ flood: false }),
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.advert_sent"), "success");
          } else {
            const errDetail = data.detail || data.message || data.error || I18n.t("settings.advert_failed");
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${errDetail}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.network_error", { p0: err.message }), "error");
        } finally {
          btn.disabled = false;
        }
      });
    }

    if (this.dom.btnActionAdvertFlood) {
      this.dom.btnActionAdvertFlood.addEventListener("click", async () => {
        const btn = this.dom.btnActionAdvertFlood;
        btn.disabled = true;
        try {
          const res = await fetch("/api/node/advert", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ flood: true }),
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.flood_sent"), "success");
          } else {
            const errDetail = data.detail || data.message || data.error || I18n.t("settings.flood_failed");
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${errDetail}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.network_error", { p0: err.message }), "error");
        } finally {
          btn.disabled = false;
        }
      });
    }

    if (this.dom.btnActionReconnectSerial) {
      this.dom.btnActionReconnectSerial.addEventListener("click", async () => {
        const btn = this.dom.btnActionReconnectSerial;
        btn.disabled = true;
        try {
          const res = await fetch("/api/config/reconnect", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.serial_reconnected"), "success");
            setTimeout(() => this.fetchLocalNodeConfig(true), 1500);
          } else {
            const errDetail = data.detail || data.message || data.error || I18n.t("settings.reconnect_failed");
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${errDetail}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.network_error", { p0: err.message }), "error");
        } finally {
          btn.disabled = false;
        }
      });
    }

    if (this.dom.btnActionRebootLocal) {
      this.dom.btnActionRebootLocal.addEventListener("click", async () => {
        const confirmMsg = I18n.t("settings.reboot_confirm");
        const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
        const confirmed = confirmFn
          ? await confirmFn(confirmMsg, {
              title: I18n.t("settings.reboot_title") || "Reiniciar Dispositivo",
              isDanger: true,
              confirmText: I18n.t("settings.btn_reboot") || "Reiniciar",
            })
          : true;
        if (!confirmed) return;
        const btn = this.dom.btnActionRebootLocal;
        btn.disabled = true;
        try {
          const res = await fetch("/api/config/reboot", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.reboot_sent"), "warning");
          } else {
            const errDetail = data.detail || data.message || data.error || I18n.t("settings.reboot_failed");
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${errDetail}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.network_error", { p0: err.message }), "error");
        } finally {
          btn.disabled = false;
        }
      });
    }

    if (this.dom.btnActionClearLocalStats) {
      this.dom.btnActionClearLocalStats.addEventListener("click", async () => {
        const confirmMsg = I18n.t('analytics.confirm_reset') || "¿Deseas restablecer todos los contadores de paquetes y métricas acumuladas?";
        const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
        const confirmed = confirmFn
          ? await confirmFn(confirmMsg, {
              title: I18n.t("analytics.reset_title") || "Restablecer Estadísticas",
              isDanger: true,
              confirmText: I18n.t("modal.confirm") || "Restablecer",
            })
          : true;
        if (!confirmed) return;
        const btn = this.dom.btnActionClearLocalStats;
        btn.disabled = true;
        try {
          const res = await fetch("/api/config/clear-stats", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
          });
          const data = await res.json().catch(() => ({}));
          if (res.ok && data.status === "ok") {
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.counters_reset"), "success");
            await this.fetchLocalNodeConfig(false);
            if (this.ctx.fetchNodes) await this.ctx.fetchNodes();
          } else {
            const errDetail = data.detail || data.message || data.error || I18n.t("settings.reset_failed");
            if (this.ctx.showToast) this.ctx.showToast(`Error: ${errDetail}`, "error");
          }
        } catch (err) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.network_error", { p0: err.message }), "error");
        } finally {
          btn.disabled = false;
        }
      });
    }

    // 7. Eventos de la pestaña de Servicios de Red & MQTT Externo
    this._bindServicesEvents();
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
        I18n.setText(elPktErrs, "settings.packet_errors", { p0: dups, p1: errs });
      }
      const sumQueue = document.getElementById("localSummaryQueue");
      if (sumQueue && payload.queue_depth != null) {
        I18n.setText(sumQueue, "settings.queue_packets", { p0: payload.queue_depth });
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

      const isEnc = ch.index !== 0 && Boolean(ch.is_encrypted ?? (ch.has_psk || (ch.psk && ch.psk.trim().length > 0)));
      const lockIcon = isEnc ? "lock" : "unlock";
      const lockTitle = isEnc
        ? I18n.t("settings.encrypted_channel")
        : (ch.index === 0 ? I18n.t("settings.public_channel") : I18n.t("settings.open_channel"));

      const chDisplayName = ch.name || (ch.index === 0 ? I18n.t('chat.ch_0_default') : I18n.t("settings.channel_label", { p0: ch.index }));

      li.innerHTML = `
        <span class="ch-badge font-mono">Ch ${ch.index}</span>
        <span class="ch-name">${escapeHtml(chDisplayName)}</span>
        <div class="ch-actions">
          <span class="ch-lock ${isEnc ? 'ch-locked' : 'ch-open'}" title="${lockTitle}">
            <i class="bi ${isEnc ? 'bi-lock' : 'bi-unlock'}" style="font-size: 13px;" aria-hidden="true"></i>
          </span>
          ${ch.index > 0 ? `
            <button type="button" class="btn-item-qr" data-ch-idx="${ch.index}" data-ch-name="${escapeHtml(chDisplayName)}" title="${I18n.t('settings.channel_qr_title')}" aria-label="${I18n.t('settings.share_channel', { index: ch.index })}">
              <i class="bi bi-qr-code" style="font-size: 13px;" aria-hidden="true"></i>
            </button>
            <button type="button" class="btn-item-delete" data-ch-idx="${ch.index}" data-ch-name="${escapeHtml(chDisplayName)}" title="${I18n.t('settings.delete_channel', { index: ch.index })}" aria-label="${I18n.t('settings.delete_channel', { index: ch.index })}">
              <i class="bi bi-trash" style="font-size: 13px;" aria-hidden="true"></i>
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
                window.showQrModal('', data.uri, data.data, { key: 'settings.qr_channel_title', params: { p0: chIdx, p1: chDisplayName } });
              }
            } else {
              this._notify(I18n.t("settings.channel_export_error", { p0: data.message || I18n.t("settings.unknown_failure") }), "error");
            }
          } catch (err) {
            this._notify(I18n.t('settings.channel_data_error', { error: err.message }), "error");
          }
        });
      }

      const btnDelete = li.querySelector(".btn-item-delete");
      if (btnDelete) {
        btnDelete.addEventListener("click", async (e) => {
          e.stopPropagation();
          const chIdx = Number(btnDelete.getAttribute("data-ch-idx"));
          const chName = btnDelete.getAttribute("data-ch-name") || I18n.t('settings.channel_label', { p0: chIdx });

          const confirmMsg = I18n.t("settings.channel_delete_confirm", { p0: chIdx, p1: chName });
          const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
          const confirmed = confirmFn
            ? await confirmFn(confirmMsg, {
                title: I18n.t("modal.delete") || "Eliminar Canal",
                isDanger: true,
                confirmText: I18n.t("modal.delete") || "Eliminar",
              })
            : true;
          if (!confirmed) return;

          try {
            const res = await fetch("/api/channels", {
              method: "DELETE",
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ index: chIdx }),
            });
            if (res.ok) {
              if (this.ctx.showToast) {
                this.ctx.showToast(I18n.t("settings.channel_deleted", { p0: chIdx, p1: chName }), "success");
              }
              this.channelsList = (this.channelsList || []).filter((c) => Number(c.index) !== chIdx);
              this.renderChannelsList(this.channelsList);

              if (this.ctx.activeChannelIdx === chIdx) {
                if (this.ctx.switchChannel) this.ctx.switchChannel(0);
              }
              await this.fetchChannels();
            } else {
              const data = await res.json().catch(() => ({}));
              this._notify(I18n.t("settings.channel_delete_error", { p0: data.detail || data.message || I18n.t("settings.unknown_failure") }), "error");
            }
          } catch (err) {
            this._notify(I18n.t('settings.channel_delete_network_error', { error: err.message }), "error");
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
          const confirmMsg = I18n.t("settings.overwrite_channel", { p0: idx, p1: name });
          const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
          const overwrite = confirmFn
            ? await confirmFn(confirmMsg, {
                title: I18n.t("settings.overwrite_title") || "Sobrescribir Canal",
                isDanger: true,
                confirmText: I18n.t("settings.overwrite_btn") || "Sobrescribir",
              })
            : true;
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
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.channel_imported", { p0: idx, p1: name }), "success");
        } else {
          this._notify(I18n.t("settings.channel_import_error", { p0: data.message || I18n.t("settings.unknown_failure") }), "error");
        }
        return;
      }

      // Caso 2: JSON estructurado
      if (cleanRaw.startsWith("{") || cleanRaw.startsWith("[")) {
        try {
          const parsed = JSON.parse(cleanRaw);
          if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && (parsed.type === "channel" || (parsed.index !== undefined && parsed.name && !parsed.public_key))) {
            const parsedIdx = parseInt(parsed.index, 10);
            const idx = !isNaN(parsedIdx) ? parsedIdx : 1;
            const name = parsed.name || `Canal ${idx}`;
            const psk = parsed.secret || parsed.psk || "";
            const cleanPsk = (psk && psk !== MESHCORE_PUBLIC_CHANNEL_SECRET) ? psk : "";
            const exists = this.channelsList.some((c) => Number(c.index) === idx);
            if (exists) {
              const confirmMsg = I18n.t("settings.overwrite_channel", { p0: idx, p1: name });
              const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
              const overwrite = confirmFn
                ? await confirmFn(confirmMsg, {
                    title: I18n.t("settings.overwrite_title") || "Sobrescribir Canal",
                    isDanger: true,
                    confirmText: I18n.t("settings.overwrite_btn") || "Sobrescribir",
                  })
                : true;
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
              if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.channel_imported", { p0: idx, p1: name }), "success");
            } else {
              this._notify(I18n.t("settings.channel_import_error", { p0: data.message || I18n.t("settings.unknown_failure") }), "error");
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
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.contacts_imported", { p0: count }), "success");
      } else {
        this._notify(I18n.t("settings.import_error", { p0: data.message || I18n.t("settings.invalid_import") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.import_network_error", { p0: err.message }), "error");
    }
  }

  async fetchLocalNodeConfig(force = false) {
    if (this._isSavingRadio || this._isSavingIdentity) return;
    const revision = this._configRevision;
    const readSequence = ++this._configReadSequence;
    try {
      const url = force ? "/api/config?refresh=true" : "/api/config";
      const res = await fetch(url, {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (res.ok && data.status === "ok" && data.data && revision === this._configRevision && readSequence === this._configReadSequence) {
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
    this.observedConfig = { ...this.cachedConfig };

    // Bloqueo y aviso visual ante desconexión física de la radio (F03)
    const isDisconnected = (cfg.serial_connected === false || cfg.radio_connected === false);
    const radioSubmit = this.dom.localRadioForm?.querySelector("button[type='submit']");
    const ownerSubmit = this.dom.localOwnerPosForm?.querySelector("button[type='submit']");
    if (radioSubmit) {
      radioSubmit.disabled = isDisconnected || this._isSavingRadio;
      if (isDisconnected) {
        radioSubmit.title = I18n.t("settings.radio_disconnected_notice");
      } else {
        radioSubmit.removeAttribute("title");
      }
    }
    if (ownerSubmit) {
      ownerSubmit.disabled = isDisconnected || this._isSavingIdentity;
      if (isDisconnected) {
        ownerSubmit.title = I18n.t("settings.radio_disconnected_notice");
      } else {
        ownerSubmit.removeAttribute("title");
      }
    }

    if (cfg.name) this._setFieldIfNotDirty("localNodeName", cfg.name);

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
      I18n.setText(roleBadge, isRepeat ? 'node.role_repeater' : 'node.role_local');
      roleBadge.className = `badge-pill ${isRepeat ? "badge-warning" : "badge-primary"}`;
    }

    // Parámetros de radio
    const freqVal = cfg.frequency ?? cfg.radio_freq;
    if (freqVal != null) this._setFieldIfNotDirty("localFreq", freqVal);

    const sfVal = cfg.spreading_factor ?? cfg.radio_sf ?? cfg.sf;
    if (sfVal != null) this._setFieldIfNotDirty("localSf", sfVal);

    const bwVal = cfg.bandwidth ?? cfg.radio_bw ?? cfg.bw;
    if (bwVal != null) {
      let b = parseFloat(bwVal);
      if (b > 1000) b = b / 1000.0;
      const bStr = String(b);
      const supportedBws = ["7.8", "10.4", "15.6", "20.8", "31.25", "41.7", "62.5", "125", "250", "500"];
      const found = supportedBws.find((opt) => parseFloat(opt) === b);
      this._setFieldIfNotDirty("localBw", found || bStr);
    }

    const crVal = cfg.coding_rate ?? cfg.radio_cr ?? cfg.cr;
    if (crVal != null) {
      const crStr = String(crVal).includes("/") ? String(crVal) : (crVal === 5 ? "4/5" : (crVal === 6 ? "4/6" : (crVal === 7 ? "4/7" : (crVal === 8 ? "4/8" : String(crVal)))));
      this._setFieldIfNotDirty("localCr", crStr);
    }

    const pwrVal = cfg.tx_power ?? cfg.power;
    const pwrValBadge = document.getElementById("localTxPowerVal");
    if (pwrVal != null) {
      this._setFieldIfNotDirty("localTxPower", pwrVal);
      if (pwrValBadge) pwrValBadge.textContent = `${pwrVal} dBm`;
    }

    const hopVal = cfg.hop_limit ?? cfg.hops;
    if (hopVal != null) this._setFieldIfNotDirty("localHopLimit", hopVal);

    // Modo Repetidor / Router
    if (cfg.repeat != null || cfg.repeat_enabled != null) {
      const isRepeat = Boolean(cfg.repeat ?? cfg.repeat_enabled);
      this._setFieldIfNotDirty("localRepeatMode", null, isRepeat);
      const repeatBadge = document.getElementById("localRepeatBadge");
      if (repeatBadge) {
        I18n.setText(repeatBadge, isRepeat ? 'common.on' : 'common.off');
        if (isRepeat) {
          repeatBadge.classList.add("badge-active");
        } else {
          repeatBadge.classList.remove("badge-active");
        }
      }
      const sumRepeat = document.getElementById("localSummaryRepeat");
      if (sumRepeat) {
        I18n.setText(sumRepeat, isRepeat ? "settings.enabled" : "settings.disabled");
        sumRepeat.style.color = isRepeat ? "var(--accent-success, #22c55e)" : "var(--text-muted, #94a3b8)";
      }
    }

    // Balizas & Transmisiones Periódicas
    const advIntVal = cfg.advert_interval ?? cfg.beacon_interval;
    const advBadge = document.getElementById("localAdvertEnableBadge");
    const advIntInput = document.getElementById("localAdvertInterval");
    if (advIntVal !== undefined && advIntVal !== null) {
      const isAdvOn = Number(advIntVal) > 0;
      this._setFieldIfNotDirty("localAdvertEnable", null, isAdvOn);
      if (advBadge) {
        I18n.setText(advBadge, isAdvOn ? 'common.on' : 'common.off');
        advBadge.classList.toggle("badge-active", isAdvOn);
      }
      if (advIntInput) {
        advIntInput.disabled = !isAdvOn;
        advIntInput.style.opacity = isAdvOn ? "1" : "0.5";
        if (isAdvOn) this._setFieldIfNotDirty("localAdvertInterval", advIntVal);
        else if (!advIntInput.value) this._setFieldIfNotDirty("localAdvertInterval", "300");
      }
    } else if (advIntVal != null) {
      this._setFieldIfNotDirty("localAdvertInterval", advIntVal);
    }

    const telemIntVal = cfg.telemetry_interval;
    const telemBadge = document.getElementById("localTelemetryEnableBadge");
    const telemIntInput = document.getElementById("localTelemetryInterval");
    if (telemIntVal !== undefined && telemIntVal !== null) {
      const isTelemOn = Number(telemIntVal) > 0 && cfg.telemetry_mode_base !== 0;
      this._setFieldIfNotDirty("localTelemetryEnable", null, isTelemOn);
      if (telemBadge) {
        I18n.setText(telemBadge, isTelemOn ? 'common.on' : 'common.off');
        telemBadge.classList.toggle("badge-active", isTelemOn);
      }
      if (telemIntInput) {
        telemIntInput.disabled = !isTelemOn;
        telemIntInput.style.opacity = isTelemOn ? "1" : "0.5";
        if (Number(telemIntVal) > 0) this._setFieldIfNotDirty("localTelemetryInterval", telemIntVal);
        else if (!telemIntInput.value) this._setFieldIfNotDirty("localTelemetryInterval", "60");
      }
    } else if (telemIntVal != null) {
      this._setFieldIfNotDirty("localTelemetryInterval", telemIntVal);
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
      I18n.setText(sumQueue, "settings.queue_config", { p0: cfg.queue_len ?? cfg.queue_depth });
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

    // Posición GPS & Propietario Form Inputs (F02)
    if (cfg.owner_info !== undefined || cfg.owner !== undefined) {
      this._setFieldIfNotDirty("localOwnerInfo", cfg.owner_info ?? cfg.owner ?? "");
    }

    if (cfg.latitude != null || cfg.adv_lat != null) {
      this._setFieldIfNotDirty("localGpsLat", cfg.latitude ?? cfg.adv_lat);
    }

    if (cfg.longitude != null || cfg.adv_lon != null) {
      this._setFieldIfNotDirty("localGpsLon", cfg.longitude ?? cfg.adv_lon);
    }

    const altVal = cfg.altitude_m ?? cfg.altitude ?? cfg.alt;
    if (altVal != null) {
      this._setFieldIfNotDirty("localGpsAlt", altVal);
    }

    const posFixedBadge = document.getElementById("localPosFixedBadge");
    if (cfg.fixed_position != null || cfg.pos_fixed != null) {
      const isFixed = Boolean(cfg.fixed_position ?? cfg.pos_fixed);
      this._setFieldIfNotDirty("localPosFixed", null, isFixed);
      if (posFixedBadge) {
        I18n.setText(posFixedBadge, isFixed ? "settings.fixed" : 'common.off');
        posFixedBadge.classList.toggle("is-active", isFixed);
      }
    }

    // Parámetros Avanzados del Firmware MeshCore
    if (cfg.pin !== undefined || cfg.device_pin !== undefined) {
      const pinVal = cfg.pin ?? cfg.device_pin;
      this._setFieldIfNotDirty("localDevicePin", pinVal != null ? String(pinVal) : "");
    }

    if (cfg.path_hash_mode !== undefined) {
      this._setFieldIfNotDirty("localPathHashMode", String(cfg.path_hash_mode));
    }

    if (cfg.rx_delay !== undefined) {
      this._setFieldIfNotDirty("localRxDelay", cfg.rx_delay != null ? String(cfg.rx_delay) : "");
    }

    if (cfg.airtime_factor !== undefined) {
      this._setFieldIfNotDirty("localAirtimeFactor", cfg.airtime_factor != null ? String(cfg.airtime_factor) : "");
    }

    if (cfg.telemetry_mode_base !== undefined) {
      this._setFieldIfNotDirty("localTelemBase", String(cfg.telemetry_mode_base));
    }

    if (cfg.telemetry_mode_loc !== undefined) {
      this._setFieldIfNotDirty("localTelemLoc", String(cfg.telemetry_mode_loc));
    }

    if (cfg.telemetry_mode_env !== undefined) {
      this._setFieldIfNotDirty("localTelemEnv", String(cfg.telemetry_mode_env));
    }

    if (cfg.adv_loc_policy !== undefined) {
      const advLocBadge = document.getElementById("localAdvLocBadge");
      const isAdv = Boolean(cfg.adv_loc_policy);
      this._setFieldIfNotDirty("localAdvLocPolicy", null, isAdv);
      if (advLocBadge) {
        I18n.setText(advLocBadge, isAdv ? 'common.on' : 'common.off');
        advLocBadge.classList.toggle("badge-active", isAdv);
      }
    }

    if (cfg.multi_acks !== undefined) {
      const multiAcksBadge = document.getElementById("localMultiAcksBadge");
      const isMulti = Boolean(cfg.multi_acks);
      this._setFieldIfNotDirty("localMultiAcks", null, isMulti);
      if (multiAcksBadge) {
        I18n.setText(multiAcksBadge, isMulti ? 'common.on' : 'common.off');
        multiAcksBadge.classList.toggle("badge-active", isMulti);
      }
    }

    if (cfg.manual_add_contacts !== undefined) {
      const manualAddBadge = document.getElementById("localManualAddBadge");
      const isManual = Boolean(cfg.manual_add_contacts);
      this._setFieldIfNotDirty("localManualAddContacts", null, isManual);
      if (manualAddBadge) {
        I18n.setText(manualAddBadge, isManual ? 'common.on' : 'common.off');
        manualAddBadge.classList.toggle("badge-active", isManual);
      }
    }

    if (cfg.custom_vars && typeof cfg.custom_vars === "object") {
      this.renderCustomVarsTable(cfg.custom_vars);
    }
    if (cfg.flood_scope && typeof cfg.flood_scope === "object") {
      this._renderFloodScope(cfg.flood_scope);
    }
    if (cfg.autoadd_config && typeof cfg.autoadd_config === "object") {
      this._populateAutoAddConfig(cfg.autoadd_config);
    }


    // Tarjeta de Alimentación Host USB (Estación Base 5V)
    const elSolar = document.getElementById("localSolarValue");
    const elSolarStatus = document.getElementById("localSolarStatus");
    if (elSolar && (cfg.power_source != null || cfg.battery_pct != null)) {
      if (cfg.power_source) {
        elSolar.removeAttribute('data-i18n');
        elSolar.textContent = cfg.power_source;
      } else if (cfg.battery_pct != null && cfg.battery_pct < 100) {
        I18n.setText(elSolar, "settings.lipo");
      } else {
        I18n.setText(elSolar, "settings.usb");
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
          I18n.setText(elClockStatus, "settings.clock_exact");
          elClockStatus.style.color = "var(--accent-success, #22c55e)";
        } else if (drift <= 60) {
          I18n.setText(elClockStatus, "settings.clock_drift_s", { p0: drift });
          elClockStatus.style.color = "var(--accent-warning, #eab308)";
        } else {
          I18n.setText(elClockStatus, "settings.clock_drift_m", { p0: Math.round(drift / 60) });
          elClockStatus.style.color = "var(--accent-danger, #ef4444)";
        }
      }
    } else if (cfg.clock) {
      if (elClock) elClock.textContent = cfg.clock;
      if (elClockStatus) {
        I18n.setText(elClockStatus, "settings.host_clock");
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
      I18n.setText(elPktErrs, "settings.config_packet_errors", { p0: cfg.duplicate_packets ?? 0, p1: cfg.packet_errors ?? 0 });
    }

    if (this.ctx.updateRadioBadge && (cfg.serial_connected != null || cfg.radio_connected != null)) {
      const isConnected = Boolean(cfg.serial_connected ?? cfg.radio_connected);
      this.ctx.updateRadioBadge(isConnected, cfg.serial_port || "");
    }
    this._applyLocalConfigCapabilities();
  }

  _applyLocalConfigCapabilities() {
    const capabilities = this.cachedConfig.capabilities || {};
    for (const [key, ids] of [
      ["telemetry_interval", ["localTelemetryEnable", "localTelemetryInterval"]],
      ["advert_interval", ["localAdvertEnable", "localAdvertInterval"]],
      ["hop_limit", ["localHopLimit"]], ["owner_info", ["localOwnerInfo"]],
      ["altitude", ["localGpsAlt"]], ["fixed_position", ["localPosFixed"]],
    ]) {
      if (capabilities[key] !== false) continue;
      for (const id of ids) {
        const element = document.getElementById(id);
        if (!element) continue;
        element.disabled = true;
        element.title = I18n.t("settings.config_unsupported");
        if (id === "localTelemetryInterval" || id === "localAdvertInterval") element.value = "";
        if (id === "localTelemetryEnable" || id === "localAdvertEnable") {
          element.checked = false;
          const badge = document.getElementById(`${id}Badge`);
          if (badge) {
            I18n.setText(badge, "common.off");
            badge.classList.remove("badge-active");
          }
        }
      }
    }
  }

  _localFieldValue(id) {
    const element = document.getElementById(id);
    return element?.type === "checkbox" ? Boolean(element.checked) : (element?.value ?? "");
  }

  _collectLocalConfigDraft(fields) {
    const payload = {};
    const snapshot = new Map();
    for (const [id, key, convert] of fields) {
      if (!this.dirtyFields.has(id)) continue;
      const raw = this._localFieldValue(id);
      const value = convert(raw);
      if (typeof value === "number" && !Number.isFinite(value)) {
        throw new Error(I18n.t("settings.invalid_value"));
      }
      payload[key] = value;
      snapshot.set(id, { key, raw, version: this._fieldEditVersions.get(id) || 0 });
    }
    return { payload, snapshot };
  }

  _hasAppliedConfigKey(applied, key) {
    const canonical = key === "altitude_m" ? "altitude" : key;
    return [key, canonical].some(name => Object.hasOwn(applied, name) && applied[name] != null && (typeof applied[name] !== "number" || Number.isFinite(applied[name])));
  }

  _applyLocalConfigSaveResult(data, snapshot) {
    const result = data.data && typeof data.data === "object" ? data.data : data;
    const applied = result.applied && typeof result.applied === "object" ? result.applied : {};
    const confirmedFields = new Set();
    // The requested payload is never evidence that the device accepted a change.
    for (const [id, saved] of snapshot) {
      if (!this._hasAppliedConfigKey(applied, saved.key)) continue;
      if (!result.pending_reboot && !result.reboot_required && this._localFieldValue(id) === saved.raw && (this._fieldEditVersions.get(id) || 0) === saved.version) {
        this.dirtyFields.delete(id);
        confirmedFields.add(id);
      }
    }
    const confirmed = result.config || data.config || applied;
    this._confirmedFieldIds = confirmedFields;
    try {
      if (confirmed && typeof confirmed === "object") this.populateLocalConfig(confirmed);
    } finally {
      this._confirmedFieldIds = null;
    }
    return { result, applied };
  }

  async _saveLocalConfigDraft(kind, draft) {
    if (Object.keys(draft.payload).length === 0) {
      this._notify(I18n.t("settings.no_config_changes"), "info");
      return;
    }
    const isRadio = kind === "radio";
    const savingFlag = isRadio ? "_isSavingRadio" : "_isSavingIdentity";
    if (this[savingFlag]) return;
    this[savingFlag] = true;
    ++this._configRevision;
    const form = isRadio ? this.dom.localRadioForm : this.dom.localOwnerPosForm;
    const submitBtn = form?.querySelector("button[type='submit']");
    if (submitBtn) submitBtn.disabled = true;
    try {
      const response = await fetch(`/api/config/${kind}`, {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify(draft.payload),
      });
      const data = await response.json();
      ++this._configRevision;
      const { result, applied } = this._applyLocalConfigSaveResult(data, draft.snapshot);
      const allApplied = Object.keys(draft.payload).every(key => this._hasAppliedConfigKey(applied, key));
      if (response.ok && data.status === "ok" && (!result.status || result.status === "ok") && allApplied) {
        if (result.pending_reboot || result.reboot_required) {
          this._notify(I18n.t("settings.config_pending_reboot"), "warning");
        } else {
          this._notify(I18n.t(isRadio ? 'toast.radio_cfg_ok' : 'toast.identity_ok'), "success");
        }
      } else {
        const detail = data.detail || result.detail || data.message || result.message || data.error || I18n.t("settings.config_unconfirmed");
        this._notify(I18n.t(isRadio ? 'settings.radio_save_error' : 'settings.identity_save_error', { error: detail }), "error");
      }
    } catch (error) {
      ++this._configRevision;
      this._notify(I18n.t(isRadio ? 'settings.radio_save_network_error' : 'settings.network_error', { error: error.message, p0: error.message }), "error");
    } finally {
      this[savingFlag] = false;
      const disconnected = this.cachedConfig.serial_connected === false || this.cachedConfig.radio_connected === false;
      if (submitBtn) submitBtn.disabled = disconnected;
    }
  }

  async saveLocalRadioConfig() {
    if (this._isSavingRadio) return;
    const numeric = raw => String(raw).trim() === "" ? NaN : Number(raw);
    const fields = [
      ["localFreq", "frequency", numeric], ["localTxPower", "tx_power", numeric],
      ["localSf", "spreading_factor", numeric], ["localBw", "bandwidth", numeric],
      ["localCr", "coding_rate", String], ["localRepeatMode", "repeat", Boolean],
      ["localHopLimit", "hop_limit", numeric], ["localPathHashMode", "path_hash_mode", numeric],
      ["localRxDelay", "rx_delay", numeric], ["localAirtimeFactor", "airtime_factor", numeric],
      ["localTelemBase", "telemetry_mode_base", numeric], ["localTelemLoc", "telemetry_mode_loc", numeric],
      ["localTelemEnv", "telemetry_mode_env", numeric], ["localAdvLocPolicy", "adv_loc_policy", Boolean],
      ["localMultiAcks", "multi_acks", Boolean], ["localManualAddContacts", "manual_add_contacts", Boolean],
      ["localDevicePin", "pin", raw => String(raw).trim() === "" ? 0 : Number(raw)],
      ["localAdvertInterval", "advert_interval", numeric], ["localTelemetryInterval", "telemetry_interval", numeric],
    ];
    try {
      const draft = this._collectLocalConfigDraft(fields);
      for (const [toggle, input, key] of [
        ["localAdvertEnable", "localAdvertInterval", "advert_interval"],
        ["localTelemetryEnable", "localTelemetryInterval", "telemetry_interval"],
      ]) {
        if (!this.dirtyFields.has(toggle)) continue;
        draft.payload[key] = this._localFieldValue(toggle) ? numeric(this._localFieldValue(input)) : 0;
        if (!Number.isFinite(draft.payload[key])) throw new Error(I18n.t("settings.invalid_value"));
        draft.snapshot.set(toggle, { key, raw: this._localFieldValue(toggle), version: this._fieldEditVersions.get(toggle) || 0 });
      }
      await this._saveLocalConfigDraft("radio", draft);
    } catch (error) {
      this._notify(I18n.t("settings.radio_save_error", { error: error.message }), "error");
    }
  }

  async saveLocalIdentityAndPosition() {
    if (this._isSavingIdentity) return;
    const numeric = raw => String(raw).trim() === "" ? NaN : Number(raw);
    try {
      const draft = this._collectLocalConfigDraft([
        ["localNodeName", "name", raw => String(raw).trim()],
        ["localOwnerInfo", "owner_info", raw => String(raw).trim()],
        ["localGpsLat", "latitude", numeric], ["localGpsLon", "longitude", numeric],
        ["localGpsAlt", "altitude_m", numeric], ["localPosFixed", "fixed_position", Boolean],
      ]);
      await this._saveLocalConfigDraft("identity", draft);
    } catch (error) {
      this._notify(I18n.t("settings.identity_save_error", { error: error.message }), "error");
    }
  }

  showQrModal(title, uri, rawJson = "", label = null) {
    if (!this.dom.qrShareModal) return;
    if (this.dom.qrModalTitle) {
      if (label) I18n.setText(this.dom.qrModalTitle, label.key, label.params || {});
      else if (!title) I18n.setText(this.dom.qrModalTitle, 'settings.qr_share');
      else {
        this.dom.qrModalTitle.removeAttribute('data-i18n');
        this.dom.qrModalTitle.removeAttribute('data-i18n-params');
        this.dom.qrModalTitle.textContent = title;
      }
    }
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
    this._customVars = varsObj;
    const tbody = document.getElementById("localCustomVarsTableBody");
    if (!tbody) return;
    const entries = typeof varsObj === "object" && varsObj !== null ? Object.entries(varsObj) : [];
    if (entries.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" class="text-center" style="color: var(--color-text-secondary);">${I18n.t("settings.no_custom_vars")}</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    entries.forEach(([k, v]) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td class="font-mono"><strong>${escapeHtml(String(k))}</strong></td>
        <td><code>${escapeHtml(String(v))}</code></td>
        <td style="text-align: right;">
          <button type="button" disabled class="btn btn-danger btn-sm btn-del-custom-var" data-key="${escapeHtml(String(k))}" title="${I18n.t("settings.config_unsupported")}">
            ${I18n.t("settings.delete_variable_button")}
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
      this._notify(I18n.t("settings.custom_var_empty"), "warning");
      return;
    }

    try {
      const res = await fetch("/api/config/custom_vars", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ key: k, value: v }),
      });
      const data = await res.json();
      if (res.ok && data.status === "ok") {
        this.renderCustomVarsTable(data.custom_vars || data.data || {});
        const inKey = document.getElementById("inputCustomVarKey");
        const inVal = document.getElementById("inputCustomVarVal");
        if (inKey) inKey.value = "";
        if (inVal) inVal.value = "";
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.custom_var_saved", { p0: k }), "success");
      } else {
        this._notify(I18n.t("settings.variable_save_error", { p0: data.message || I18n.t("settings.unknown") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
    }
  }

  async deleteCustomVar(key) {
    if (!key) return;
    const confirmMsg = I18n.t("settings.custom_var_delete_confirm", { p0: key });
    const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
    const confirmed = confirmFn
      ? await confirmFn(confirmMsg, {
          title: I18n.t("modal.delete") || "Eliminar Variable",
          isDanger: true,
          confirmText: I18n.t("modal.delete") || "Eliminar",
        })
      : true;
    if (!confirmed) return;
    try {
      const res = await fetch(`/api/config/custom_vars?key=${encodeURIComponent(key)}`, {
        method: "DELETE",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
      const data = await res.json();
      if (res.ok && data.status === "ok") {
        this.renderCustomVarsTable(data.custom_vars || data.data || {});
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.custom_var_deleted", { p0: key }), "info");
      } else {
        this._notify(I18n.t("settings.variable_delete_error", { p0: data.message || I18n.t("settings.unknown") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
    }
  }

  async fetchFloodScope() {
    const revision = this._configRevision;
    try {
      const res = await fetch("/api/config/flood_scope", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (res.ok && data.status === "ok" && revision === this._configRevision) {
        const fs = data.flood_scope || data.data || {};
        this._renderFloodScope(fs);
      }
    } catch (e) {
      console.warn("Error consultando flood scope:", e);
    }
  }

  async saveFloodScope() {
    if (this._savingFloodScope) return;
    const inScope = document.getElementById("inputFloodScope");
    const scopeVal = inScope ? inScope.value.trim() : "";
    const snapshot = this._snapshotAdvancedFields(["inputFloodScope"]);
    this._savingFloodScope = true;
    ++this._configRevision;
    try {
      const res = await fetch("/api/config/flood_scope", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: scopeVal }),
      });
      const data = await res.json();
      ++this._configRevision;
      const result = data.data || data;
      const confirmed = result.flood_scope;
      if (res.ok && data.status === "ok" && result.status === "ok" && confirmed) {
        const name = confirmed.scope_name || "";
        this._clearAdvancedFields(snapshot);
        this._renderFloodScope(confirmed);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.scope_applied", { p0: name || I18n.t("settings.global") }), "success");
      } else {
        this._notify(I18n.t("settings.scope_save_error", { p0: data.message || I18n.t("settings.unknown") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
    } finally {
      this._savingFloodScope = false;
      ++this._configRevision;
    }
  }

  async resetFloodScope() {
    if (this._savingFloodScope) return;
    const snapshot = this._snapshotAdvancedFields(["inputFloodScope"]);
    this._savingFloodScope = true;
    ++this._configRevision;
    try {
      const res = await fetch("/api/config/flood_scope", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ scope: "*" }),
      });
      const data = await res.json();
      ++this._configRevision;
      const result = data.data || data;
      if (res.ok && data.status === "ok" && result.status === "ok" && result.flood_scope?.scope_name === "") {
        this._clearAdvancedFields(snapshot);
        this._renderFloodScope(result.flood_scope);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.scope_reset"), "info");
      } else {
        this._notify(I18n.t("settings.scope_save_error", { p0: data.detail || data.message || I18n.t("settings.config_unconfirmed") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
    } finally {
      this._savingFloodScope = false;
      ++this._configRevision;
    }
  }

  async fetchAutoAddConfig() {
    const revision = this._configRevision;
    try {
      const res = await fetch("/api/config/autoadd", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      const data = await res.json();
      if (res.ok && data.status === "ok" && revision === this._configRevision) {
        const cfg = data.autoadd_config || data.data || {};
        this._populateAutoAddConfig(cfg);
      }
    } catch (e) {
      console.warn("Error consultando autoadd config:", e);
    }
  }

  async saveAutoAddConfig() {
    if (this._savingAutoAdd) return;
    const chkChat = document.getElementById("chkAutoAddChat");
    const chkOverwrite = document.getElementById("chkAutoAddOverwrite");
    const numHops = document.getElementById("numAutoAddMaxHops");
    const observed = this.cachedConfig.autoadd_config;
    if (!Number.isInteger(observed?.config)) {
      this._notify(I18n.t("settings.config_unconfirmed"), "error");
      return;
    }
    // Preserve firmware flags which are not exposed by these two checkboxes.
    let flags = observed.config & ~3;
    if (chkOverwrite?.checked) flags |= 1;
    if (chkChat?.checked) flags |= 2;
    const payload = { flags };
    if (observed.max_hops_supported === true && numHops && !numHops.disabled) {
      const maxHops = Number(numHops.value);
      if (numHops.value.trim() === "" || !Number.isInteger(maxHops) || maxHops < 0 || maxHops > 64) {
        this._notify(I18n.t("settings.invalid_value"), "error");
        return;
      }
      payload.max_hops = maxHops;
    }

    const snapshot = this._snapshotAdvancedFields(["chkAutoAddChat", "chkAutoAddOverwrite", "numAutoAddMaxHops"]);
    this._savingAutoAdd = true;
    ++this._configRevision;
    try {
      const res = await fetch("/api/config/autoadd", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      ++this._configRevision;
      const result = data.data || data;
      if (res.ok && data.status === "ok" && result.status === "ok" && result.autoadd_config?.config === flags) {
        this.cachedConfig.autoadd_config = result.autoadd_config;
        this._clearAdvancedFields(snapshot);
        this._populateAutoAddConfig(result.autoadd_config);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.auto_add_saved"), "success");
      } else {
        this._notify(I18n.t("settings.policy_save_error", { p0: data.message || I18n.t("settings.unknown") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
    } finally {
      this._savingAutoAdd = false;
      ++this._configRevision;
    }
  }

  _populateAutoAddConfig(cfg) {
    this.cachedConfig.autoadd_config = cfg;
    const known = Number.isInteger(cfg.config);
    const chat = document.getElementById("chkAutoAddChat");
    const overwrite = document.getElementById("chkAutoAddOverwrite");
    const hops = document.getElementById("numAutoAddMaxHops");
    const save = document.getElementById("btnSaveAutoAddConfig");
    if (chat) { chat.disabled = !known; this._setFieldIfNotDirty("chkAutoAddChat", null, known && (cfg.config & 2) !== 0); }
    if (overwrite) { overwrite.disabled = !known; this._setFieldIfNotDirty("chkAutoAddOverwrite", null, known && (cfg.config & 1) !== 0); }
    if (hops) {
      hops.disabled = !known || cfg.max_hops_supported !== true;
      this._setFieldIfNotDirty("numAutoAddMaxHops", cfg.max_hops != null ? String(cfg.max_hops) : "");
    }
    if (save) save.disabled = !known;
  }

  _snapshotAdvancedFields(ids) {
    return new Map(ids.map(id => [id, { raw: this._localFieldValue(id), version: this._fieldEditVersions.get(id) || 0 }]));
  }

  _renderFloodScope(scope) {
    this.cachedConfig.flood_scope = scope;
    const name = scope.scope_name || "";
    this._setFieldIfNotDirty("inputFloodScope", name);
    const label = document.getElementById("currentFloodScopeLabel");
    if (!label) return;
    if (name) {
      label.removeAttribute("data-i18n");
      label.removeAttribute("data-i18n-params");
      label.textContent = name;
    } else {
      I18n.setText(label, "settings.global_scope");
    }
  }

  _clearAdvancedFields(snapshot) {
    for (const [id, saved] of snapshot) {
      if (this._localFieldValue(id) === saved.raw && (this._fieldEditVersions.get(id) || 0) === saved.version) this.dirtyFields.delete(id);
    }
  }

  // ── Gestión de Servicios de Red & MQTT Externo (Paso 7) ────────────────────

  _bindServicesEvents() {
    // Selector de método de autenticación externa
    if (this.dom.selExtMqttAuthType) {
      this.dom.selExtMqttAuthType.addEventListener("change", () => {
        this._updateAuthFieldsVisibility();
      });
    }

    // Checkbox de autenticación MQTT local
    if (this.dom.chkLocalMqttAuth) {
      this.dom.chkLocalMqttAuth.addEventListener("change", () => {
        this._updateLocalMqttAuthVisibility();
      });
    }

    // Checkbox de modo Observer (informa si se activan o desactivan chats)
    if (this.dom.chkExtObserverMode) {
      this.dom.chkExtObserverMode.addEventListener("change", (e) => {
        if (e.target.checked && this.ctx.showToast) {
          this.ctx.showToast(I18n.t("services.observer_mode") || "Modo Observer activo: chats no reenviados", "info");
        }
      });
    }

    // Cambio de Preset en el dropdown
    if (this.dom.selExtMqttPreset) {
      this.dom.selExtMqttPreset.addEventListener("change", (e) => {
        const val = e.target.value;
        if (val === "custom") {
          this._updatePresetBadgeAndButtons("custom");
        } else {
          const p = (this.servicesPresets || []).find((x) => x.id === val);
          if (p) {
            this._applyPresetToForm(p);
            this._updatePresetBadgeAndButtons(val);
          }
        }
      });
    }

    // Botón: Abrir modal "Guardar como Preset"
    if (this.dom.btnSaveCurrentAsPreset) {
      this.dom.btnSaveCurrentAsPreset.addEventListener("click", () => {
        if (this.dom.modalSavePreset) {
          this.dom.modalSavePreset.classList.remove("hidden");
          if (this.dom.inputNewPresetName) {
            this.dom.inputNewPresetName.value = "";
            this.dom.inputNewPresetName.focus();
          }
          if (this.dom.inputNewPresetDesc) {
            this.dom.inputNewPresetDesc.value = "";
          }
        }
      });
    }

    // Botones de cierre del modal de Preset
    if (this.dom.btnCloseSavePresetModal) {
      this.dom.btnCloseSavePresetModal.addEventListener("click", () => {
        if (this.dom.modalSavePreset) this.dom.modalSavePreset.classList.add("hidden");
      });
    }
    if (this.dom.btnCancelSavePreset) {
      this.dom.btnCancelSavePreset.addEventListener("click", () => {
        if (this.dom.modalSavePreset) this.dom.modalSavePreset.classList.add("hidden");
      });
    }

    // Confirmar guardado de preset personalizado
    if (this.dom.btnConfirmSavePreset) {
      this.dom.btnConfirmSavePreset.addEventListener("click", () => {
        this.saveCustomPreset();
      });
    }

    // Botón: Eliminar preset personalizado
    if (this.dom.btnDeleteCustomPreset) {
      this.dom.btnDeleteCustomPreset.addEventListener("click", () => {
        this.deleteCustomPreset();
      });
    }

    // Botón: Probar conexión externa
    if (this.dom.btnTestExternalMqtt) {
      this.dom.btnTestExternalMqtt.addEventListener("click", () => {
        this.testExternalMqttConnection();
      });
    }

    // Botón principal: Guardar y aplicar configuración de servicios
    if (this.dom.btnSaveServicesConfig) {
      this.dom.btnSaveServicesConfig.addEventListener("click", () => {
        this.saveServicesConfig();
      });
    }
  }

  async loadServicesConfig() {
    try {
      const res = await fetch("/api/services/config", {
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const body = await res.json();
      if (body.status !== "ok" || !body.data) return;
      const data = body.data;
      this.servicesConfig = data;
      this.servicesPresets = data.all_presets || [];

      this._renderServicesPresetsDropdown(this.servicesPresets, data.external_mqtt?.selected_preset_id);
      this._populateServicesForm(data);
    } catch (err) {
      console.warn("Error cargando configuración de servicios:", err);
    }
  }

  _renderServicesPresetsDropdown(presets, selectedId = "custom") {
    const sel = this.dom.selExtMqttPreset;
    if (!sel) return;
    sel.innerHTML = "";

    const optCustom = document.createElement("option");
    optCustom.value = "custom";
    optCustom.textContent = "Personalizado / Manual";
    sel.appendChild(optCustom);

    presets.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.id;
      const icon = p.is_system ? "🔒" : "⭐";
      opt.textContent = `${icon} ${p.name}`;
      sel.appendChild(opt);
    });

    sel.value = selectedId || "custom";
    this._updatePresetBadgeAndButtons(sel.value);
  }

  _updatePresetBadgeAndButtons(selectedId) {
    const badge = this.dom.presetTypeBadge;
    const desc = this.dom.presetDescriptionText;
    const btnDel = this.dom.btnDeleteCustomPreset;

    if (!selectedId || selectedId === "custom") {
      if (badge) {
        badge.textContent = "Personalizado";
        badge.className = "badge-pill badge-primary text-xs";
      }
      if (desc) desc.textContent = "Configuración libre de servidor MQTT";
      if (btnDel) btnDel.disabled = true;
      return;
    }

    const p = (this.servicesPresets || []).find((x) => x.id === selectedId);
    if (!p) {
      if (btnDel) btnDel.disabled = true;
      return;
    }

    if (badge) {
      badge.textContent = p.is_system ? "Sistema" : "Personalizado";
      badge.className = p.is_system ? "badge-pill badge-secondary text-xs" : "badge-pill badge-primary text-xs";
    }
    if (desc) desc.textContent = p.description || "";
    if (btnDel) btnDel.disabled = Boolean(p.is_system);
  }

  _applyPresetToForm(p) {
    if (this.dom.inputExtMqttHost) this.dom.inputExtMqttHost.value = p.host || "";
    if (this.dom.inputExtMqttPort) this.dom.inputExtMqttPort.value = p.port || 1883;
    if (this.dom.selExtMqttTransport) this.dom.selExtMqttTransport.value = p.transport || "tcp";
    if (this.dom.chkExtMqttTls) this.dom.chkExtMqttTls.checked = Boolean(p.tls_enabled);
    if (this.dom.chkExtMqttTlsVerify) this.dom.chkExtMqttTlsVerify.checked = p.tls_verify !== false;
    if (this.dom.selExtMqttAuthType) this.dom.selExtMqttAuthType.value = p.auth_type || "anonymous";
    if (this.dom.selExtMqttPrivacy) this.dom.selExtMqttPrivacy.value = p.location_privacy || "fuzzed";
    if (this.dom.inputExtMqttUser) this.dom.inputExtMqttUser.value = p.username || "";
    if (this.dom.inputExtMqttPass) this.dom.inputExtMqttPass.value = p.password || "";
    if (this.dom.inputExtMqttToken) this.dom.inputExtMqttToken.value = p.token || "";
    if (this.dom.selExtMqttTopicMode) this.dom.selExtMqttTopicMode.value = p.topic_mode || "standard";
    if (this.dom.inputExtMqttPrefix) this.dom.inputExtMqttPrefix.value = p.topic_prefix || "meshcore/remote";
    if (this.dom.inputExtMqttIata) this.dom.inputExtMqttIata.value = p.region_iata || "XXX";
    if (this.dom.selExtMqttFormat) this.dom.selExtMqttFormat.value = p.payload_format || "json_canonical";
    if (this.dom.selExtMqttQos) this.dom.selExtMqttQos.value = String(p.qos ?? 0);
    if (this.dom.chkExtObserverMode) this.dom.chkExtObserverMode.checked = Boolean(p.filter_observer_mode);
    if (this.dom.chkExtFilterPublic) this.dom.chkExtFilterPublic.checked = Boolean(p.filter_public);
    if (this.dom.chkExtFilterChannels) this.dom.chkExtFilterChannels.checked = Boolean(p.filter_channels);
    if (this.dom.chkExtFilterDirect) this.dom.chkExtFilterDirect.checked = Boolean(p.filter_direct);
    if (this.dom.chkExtFilterTelemetry) this.dom.chkExtFilterTelemetry.checked = Boolean(p.filter_telemetry);
    if (this.dom.chkExtFilterNodes) this.dom.chkExtFilterNodes.checked = Boolean(p.filter_nodes);
    if (this.dom.chkExtFilterRaw) this.dom.chkExtFilterRaw.checked = Boolean(p.filter_raw);
    if (this.dom.chkExtDownlink) this.dom.chkExtDownlink.checked = Boolean(p.downlink_enabled);

    this._updateAuthFieldsVisibility();
  }

  _populateServicesForm(data) {
    const ext = data.external_mqtt || {};
    const loc = data.local_mqtt || {};
    const tcp = data.tcp_server || {};

    this._updateServicesStatusBadge(data);

    if (this.dom.chkExternalMqttEnabled) this.dom.chkExternalMqttEnabled.checked = Boolean(ext.enabled);
    if (this.dom.inputExtMqttHost) this.dom.inputExtMqttHost.value = ext.host || "";
    if (this.dom.inputExtMqttPort) this.dom.inputExtMqttPort.value = ext.port || 1883;
    if (this.dom.selExtMqttTransport) this.dom.selExtMqttTransport.value = ext.transport || "tcp";
    if (this.dom.chkExtMqttTls) this.dom.chkExtMqttTls.checked = Boolean(ext.tls_enabled);
    if (this.dom.chkExtMqttTlsVerify) this.dom.chkExtMqttTlsVerify.checked = ext.tls_verify !== false;
    if (this.dom.selExtMqttAuthType) this.dom.selExtMqttAuthType.value = ext.auth_type || "anonymous";
    if (this.dom.selExtMqttPrivacy) this.dom.selExtMqttPrivacy.value = ext.location_privacy || "fuzzed";
    if (this.dom.inputExtMqttUser) this.dom.inputExtMqttUser.value = ext.username || "";
    if (this.dom.inputExtMqttPass) this.dom.inputExtMqttPass.value = ext.password || "";
    if (this.dom.inputExtMqttToken) this.dom.inputExtMqttToken.value = ext.token || "";
    if (this.dom.selExtMqttTopicMode) this.dom.selExtMqttTopicMode.value = ext.topic_mode || "standard";
    if (this.dom.inputExtMqttPrefix) this.dom.inputExtMqttPrefix.value = ext.topic_prefix || "meshcore/remote";
    if (this.dom.inputExtMqttIata) this.dom.inputExtMqttIata.value = ext.region_iata || "XXX";
    if (this.dom.selExtMqttFormat) this.dom.selExtMqttFormat.value = ext.payload_format || "json_canonical";
    if (this.dom.selExtMqttQos) this.dom.selExtMqttQos.value = String(ext.qos ?? 0);
    if (this.dom.chkExtObserverMode) this.dom.chkExtObserverMode.checked = Boolean(ext.filter_observer_mode);
    if (this.dom.chkExtFilterPublic) this.dom.chkExtFilterPublic.checked = Boolean(ext.filter_public);
    if (this.dom.chkExtFilterChannels) this.dom.chkExtFilterChannels.checked = Boolean(ext.filter_channels);
    if (this.dom.chkExtFilterDirect) this.dom.chkExtFilterDirect.checked = Boolean(ext.filter_direct);
    if (this.dom.chkExtFilterTelemetry) this.dom.chkExtFilterTelemetry.checked = Boolean(ext.filter_telemetry);
    if (this.dom.chkExtFilterNodes) this.dom.chkExtFilterNodes.checked = Boolean(ext.filter_nodes);
    if (this.dom.chkExtFilterRaw) this.dom.chkExtFilterRaw.checked = Boolean(ext.filter_raw);
    if (this.dom.chkExtDownlink) this.dom.chkExtDownlink.checked = Boolean(ext.downlink_enabled);

    // MQTT Local
    if (this.dom.chkLocalMqttEnabled) this.dom.chkLocalMqttEnabled.checked = loc.enabled !== false;
    if (this.dom.inputLocalMqttHost) this.dom.inputLocalMqttHost.value = loc.host || "127.0.0.1";
    if (this.dom.inputLocalMqttPort) this.dom.inputLocalMqttPort.value = loc.port || 1883;
    if (this.dom.inputLocalMqttPrefix) this.dom.inputLocalMqttPrefix.value = loc.topic_prefix || "meshcore";
    if (this.dom.chkLocalMqttAuth) this.dom.chkLocalMqttAuth.checked = Boolean(loc.auth_enabled);
    if (this.dom.inputLocalMqttUser) this.dom.inputLocalMqttUser.value = loc.username || "";
    if (this.dom.inputLocalMqttPass) this.dom.inputLocalMqttPass.value = loc.password || "";

    // TCP Server
    if (this.dom.chkTcpServerEnabled) this.dom.chkTcpServerEnabled.checked = tcp.enabled !== false;
    if (this.dom.selTcpServerHost) this.dom.selTcpServerHost.value = tcp.host || "0.0.0.0";
    if (this.dom.inputTcpServerPort) this.dom.inputTcpServerPort.value = tcp.port || 5000;
    if (this.dom.inputTcpMaxClients) this.dom.inputTcpMaxClients.value = tcp.max_clients || 8;
    if (this.dom.inputTcpAllowedIps) this.dom.inputTcpAllowedIps.value = tcp.allowed_ips || "";

    this._updateAuthFieldsVisibility();
    this._updateLocalMqttAuthVisibility();
  }

  _updateServicesStatusBadge(data) {
    const badge = this.dom.badgeExtMqttStatus;
    if (!badge) return;
    const ext = data?.external_mqtt || {};
    if (data?.external_mqtt_connected) {
      badge.className = "badge-pill badge-success";
      badge.textContent = I18n.t("services.status_connected") || "Conectado";
    } else if (ext.enabled) {
      badge.className = "badge-pill badge-warning";
      badge.textContent = "Conectando...";
    } else {
      badge.className = "badge-pill badge-secondary";
      badge.textContent = I18n.t("services.status_disconnected") || "Desconectado";
    }
  }

  _updateAuthFieldsVisibility() {
    const authType = this.dom.selExtMqttAuthType?.value || "anonymous";
    if (this.dom.extMqttUserPassFields) {
      this.dom.extMqttUserPassFields.classList.toggle("hidden", authType !== "user_pass");
    }
    if (this.dom.extMqttTokenField) {
      this.dom.extMqttTokenField.classList.toggle("hidden", authType !== "token");
    }
  }

  _updateLocalMqttAuthVisibility() {
    const isAuth = Boolean(this.dom.chkLocalMqttAuth?.checked);
    if (this.dom.localMqttCredsRow) {
      this.dom.localMqttCredsRow.classList.toggle("hidden", !isAuth);
    }
  }

  _gatherExternalMqttFormData() {
    return {
      enabled: Boolean(this.dom.chkExternalMqttEnabled?.checked),
      host: (this.dom.inputExtMqttHost?.value || "").trim(),
      port: parseInt(this.dom.inputExtMqttPort?.value, 10) || 1883,
      transport: this.dom.selExtMqttTransport?.value || "tcp",
      tls_enabled: Boolean(this.dom.chkExtMqttTls?.checked),
      tls_verify: Boolean(this.dom.chkExtMqttTlsVerify?.checked),
      auth_type: this.dom.selExtMqttAuthType?.value || "anonymous",
      location_privacy: this.dom.selExtMqttPrivacy?.value || "fuzzed",
      username: (this.dom.inputExtMqttUser?.value || "").trim(),
      password: this.dom.inputExtMqttPass?.value || "",
      token: (this.dom.inputExtMqttToken?.value || "").trim(),
      downlink_enabled: Boolean(this.dom.chkExtDownlink?.checked),
      topic_mode: this.dom.selExtMqttTopicMode?.value || "standard",
      topic_prefix: (this.dom.inputExtMqttPrefix?.value || "").trim() || "meshcore/remote",
      region_iata: (this.dom.inputExtMqttIata?.value || "").trim().toUpperCase() || "XXX",
      payload_format: this.dom.selExtMqttFormat?.value || "json_canonical",
      qos: parseInt(this.dom.selExtMqttQos?.value, 10) || 0,
      filter_observer_mode: Boolean(this.dom.chkExtObserverMode?.checked),
      filter_public: Boolean(this.dom.chkExtFilterPublic?.checked),
      filter_channels: Boolean(this.dom.chkExtFilterChannels?.checked),
      filter_direct: Boolean(this.dom.chkExtFilterDirect?.checked),
      filter_telemetry: Boolean(this.dom.chkExtFilterTelemetry?.checked),
      filter_nodes: Boolean(this.dom.chkExtFilterNodes?.checked),
      filter_raw: Boolean(this.dom.chkExtFilterRaw?.checked),
      selected_preset_id: this.dom.selExtMqttPreset?.value || "custom",
    };
  }

  _gatherLocalMqttFormData() {
    return {
      enabled: Boolean(this.dom.chkLocalMqttEnabled?.checked),
      host: (this.dom.inputLocalMqttHost?.value || "").trim() || "127.0.0.1",
      port: parseInt(this.dom.inputLocalMqttPort?.value, 10) || 1883,
      topic_prefix: (this.dom.inputLocalMqttPrefix?.value || "").trim() || "meshcore",
      auth_enabled: Boolean(this.dom.chkLocalMqttAuth?.checked),
      username: (this.dom.inputLocalMqttUser?.value || "").trim(),
      password: this.dom.inputLocalMqttPass?.value || "",
    };
  }

  _gatherTcpServerFormData() {
    return {
      enabled: Boolean(this.dom.chkTcpServerEnabled?.checked),
      host: this.dom.selTcpServerHost?.value || "0.0.0.0",
      port: parseInt(this.dom.inputTcpServerPort?.value, 10) || 5000,
      max_clients: parseInt(this.dom.inputTcpMaxClients?.value, 10) || 8,
      allowed_ips: (this.dom.inputTcpAllowedIps?.value || "").trim(),
    };
  }

  async saveServicesConfig() {
    if (this._isSavingServices) return;
    const btn = this.dom.btnSaveServicesConfig;
    if (btn) btn.disabled = true;
    this._isSavingServices = true;

    try {
      const payload = {
        external_mqtt: this._gatherExternalMqttFormData(),
        local_mqtt: this._gatherLocalMqttFormData(),
        tcp_server: this._gatherTcpServerFormData(),
      };

      const res = await fetch("/api/services/config", {
        method: "POST",
        headers: this.ctx.getAuthHeaders
          ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" })
          : { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const body = await res.json().catch(() => ({}));
      if (res.ok && body.status === "ok") {
        if (this.ctx.showToast) {
          this.ctx.showToast(I18n.t("services.saved_success") || "Configuración guardada y aplicada correctamente", "success");
        }
        await this.loadServicesConfig();
      } else {
        const errDetail = body.detail || body.message || body.error || "Error al guardar servicios";
        this._notify(`Error: ${errDetail}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red al guardar servicios: ${err.message}`, "error");
    } finally {
      this._isSavingServices = false;
      if (btn) btn.disabled = false;
    }
  }

  async testExternalMqttConnection() {
    if (this._isTestingExtMqtt) return;
    const btn = this.dom.btnTestExternalMqtt;
    const statusEl = this.dom.extMqttTestStatus;
    if (btn) btn.disabled = true;
    this._isTestingExtMqtt = true;

    if (statusEl) {
      statusEl.textContent = "⏳ Probando conexión...";
      statusEl.style.color = "var(--color-text-secondary)";
    }

    try {
      const extData = this._gatherExternalMqttFormData();
      const res = await fetch("/api/services/mqtt-external/test", {
        method: "POST",
        headers: this.ctx.getAuthHeaders
          ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" })
          : { "Content-Type": "application/json" },
        body: JSON.stringify(extData),
      });

      const body = await res.json().catch(() => ({}));
      if (res.ok && body.status === "ok" && body.success) {
        const latency = body.latency_ms ?? 0;
        const msg = I18n.t("services.test_success", { latency }) || `✅ Conexión exitosa (${latency} ms)`;
        if (statusEl) {
          statusEl.textContent = msg;
          statusEl.style.color = "var(--accent-success, #22c55e)";
        }
        if (this.ctx.showToast) this.ctx.showToast(msg, "success");
      } else {
        const errMsg = body.error || body.detail || body.message || "Fallo de conexión";
        const msg = I18n.t("services.test_failed", { error: errMsg }) || `❌ Error: ${errMsg}`;
        if (statusEl) {
          statusEl.textContent = msg;
          statusEl.style.color = "var(--color-danger, #ef4444)";
        }
        if (this.ctx.showToast) this.ctx.showToast(msg, "error");
      }
    } catch (err) {
      const msg = `❌ Error de red: ${err.message}`;
      if (statusEl) {
        statusEl.textContent = msg;
        statusEl.style.color = "var(--color-danger, #ef4444)";
      }
    } finally {
      this._isTestingExtMqtt = false;
      if (btn) btn.disabled = false;
    }
  }

  async saveCustomPreset() {
    const nameInput = this.dom.inputNewPresetName;
    const descInput = this.dom.inputNewPresetDesc;
    const name = (nameInput?.value || "").trim();
    const description = (descInput?.value || "").trim();

    if (!name) {
      this._notify("Por favor ingrese un nombre para el perfil", "warning");
      nameInput?.focus();
      return;
    }

    const config = this._gatherExternalMqttFormData();
    try {
      const res = await fetch("/api/services/presets", {
        method: "POST",
        headers: this.ctx.getAuthHeaders
          ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" })
          : { "Content-Type": "application/json" },
        body: JSON.stringify({ name, description, config }),
      });

      const body = await res.json().catch(() => ({}));
      if (res.ok && body.status === "ok") {
        if (this.dom.modalSavePreset) {
          this.dom.modalSavePreset.classList.add("hidden");
        }
        const created = body.data;
        if (this.ctx.showToast) {
          this.ctx.showToast(I18n.t("services.preset_saved", { name }) || `Preset "${name}" guardado`, "success");
        }
        await this.loadServicesConfig();
        if (created && created.id && this.dom.selExtMqttPreset) {
          this.dom.selExtMqttPreset.value = created.id;
          this._updatePresetBadgeAndButtons(created.id);
        }
      } else {
        const errDetail = body.detail || body.message || "Error al crear preset";
        this._notify(`Error: ${errDetail}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red: ${err.message}`, "error");
    }
  }

  async deleteCustomPreset() {
    const sel = this.dom.selExtMqttPreset;
    const presetId = sel?.value;
    if (!presetId || presetId === "custom") return;

    const preset = (this.servicesPresets || []).find((p) => p.id === presetId);
    if (!preset || preset.is_system) {
      this._notify("No se pueden eliminar presets del sistema", "warning");
      return;
    }

    const confirmMsg = `¿Eliminar el perfil "${preset.name}"?`;
    const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
    const confirmed = confirmFn
      ? await confirmFn(confirmMsg, {
          title: "Eliminar Preset",
          isDanger: true,
          confirmText: "Eliminar",
        })
      : confirm(confirmMsg);

    if (!confirmed) return;

    try {
      const res = await fetch(`/api/services/presets/${presetId}`, {
        method: "DELETE",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {},
      });

      const body = await res.json().catch(() => ({}));
      if (res.ok && body.status === "ok") {
        if (this.ctx.showToast) {
          this.ctx.showToast(I18n.t("services.preset_deleted") || "Preset eliminado correctamente", "info");
        }
        await this.loadServicesConfig();
        if (this.dom.selExtMqttPreset) {
          this.dom.selExtMqttPreset.value = "custom";
          this._updatePresetBadgeAndButtons("custom");
        }
      } else {
        const errDetail = body.detail || body.message || "Error al eliminar preset";
        this._notify(`Error: ${errDetail}`, "error");
      }
    } catch (err) {
      this._notify(`Error de red: ${err.message}`, "error");
    }
  }
}

