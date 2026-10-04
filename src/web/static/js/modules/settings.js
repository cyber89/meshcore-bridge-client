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
    this._isSavingRadio = false;
    this._isSavingIdentity = false;
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
    };
  }

  _setFieldIfNotDirty(id, value, isChecked = null) {
    if (this.dirtyFields.has(id)) return;
    const el = document.getElementById(id);
    if (!el || document.activeElement === el) return;
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
      }
    };
    [
      "localNodeName", "localFreq", "localRegion", "localSf", "localBw", "localCr",
      "localTxPower", "localHopLimit", "localRepeatMode", "localOwnerInfo",
      "localGpsLat", "localGpsLon", "localGpsAlt", "localPosFixed",
      "localDevicePin", "localPathHashMode", "localRxDelay", "localAirtimeFactor",
      "localTelemBase", "localTelemLoc", "localTelemEnv", "localAdvLocPolicy",
      "localMultiAcks", "localManualAddContacts", "localAdvertInterval",
      "localAdvertEnable", "localTelemetryInterval", "localTelemetryEnable"
    ].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("input", markDirty);
        el.addEventListener("change", markDirty);
      }
    });

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
          if (content) I18n.setText(content, res.ok ? "settings.maps_reindexed" : "settings.maps_active");
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.tiles_reindexed"), "success");
        } catch (e) {
          if (content) I18n.setText(content, "settings.maps_check_dir");
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
      const icon = btn ? btn.querySelector("[data-lucide]") : null;
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
            <span data-lucide="${lockIcon}" data-size="13"></span>
          </span>
          ${ch.index > 0 ? `
            <button type="button" class="btn-item-qr" data-ch-idx="${ch.index}" data-ch-name="${escapeHtml(chDisplayName)}" title="${I18n.t('settings.channel_qr_title')}" aria-label="${I18n.t('settings.share_channel', { index: ch.index })}">
              <span data-lucide="qr-code" data-size="13"></span>
            </button>
            <button type="button" class="btn-item-delete" data-ch-idx="${ch.index}" data-ch-name="${escapeHtml(chDisplayName)}" title="${I18n.t('settings.delete_channel', { index: ch.index })}" aria-label="${I18n.t('settings.delete_channel', { index: ch.index })}">
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
    this.observedConfig = { ...this.cachedConfig };

    // Bloqueo y aviso visual ante desconexión física de la radio (F03)
    const isDisconnected = (cfg.serial_connected === false || cfg.radio_connected === false);
    const radioSubmit = this.dom.localRadioForm?.querySelector("button[type='submit']");
    const ownerSubmit = this.dom.localOwnerPosForm?.querySelector("button[type='submit']");
    if (radioSubmit) {
      radioSubmit.disabled = isDisconnected;
      if (isDisconnected) {
        radioSubmit.title = I18n.t("settings.radio_disconnected_notice");
      } else {
        radioSubmit.removeAttribute("title");
      }
    }
    if (ownerSubmit) {
      ownerSubmit.disabled = isDisconnected;
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
      const scopeName = cfg.flood_scope.scope_name || "";
      const inScope = document.getElementById("inputFloodScope");
      const lbl = document.getElementById("currentFloodScopeLabel");
      if (inScope && !inScope.value) inScope.value = scopeName;
      if (lbl) lbl.textContent = scopeName ? scopeName : I18n.t("settings.global_scope");
    }
    if (cfg.autoadd_config && typeof cfg.autoadd_config === "object") {
      const flags = Number(cfg.autoadd_config.config ?? 0);
      const maxHops = cfg.autoadd_config.max_hops != null ? Number(cfg.autoadd_config.max_hops) : 3;
      const chkChat = document.getElementById("chkAutoAddChat");
      const chkOverwrite = document.getElementById("chkAutoAddOverwrite");
      const numHops = document.getElementById("numAutoAddMaxHops");
      if (chkOverwrite) chkOverwrite.checked = (flags & 1) !== 0;
      if (chkChat) chkChat.checked = (flags & 2) !== 0;
      if (numHops && maxHops != null) numHops.value = String(maxHops);
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
  }

  async saveLocalRadioConfig() {
    if (this._isSavingRadio) return;
    const submitBtn = this.dom.localRadioForm?.querySelector("button[type='submit']");
    this._isSavingRadio = true;
    if (submitBtn) submitBtn.disabled = true;

    try {
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

      const isDirty = (id) => this.dirtyFields.has(id);
      const path_hash_mode = parseInt(document.getElementById("localPathHashMode")?.value || "0", 10);
      const rxDelayVal = document.getElementById("localRxDelay")?.value.trim();
      const rx_delay = rxDelayVal ? parseFloat(rxDelayVal) : 0;
      const airtimeFactorVal = document.getElementById("localAirtimeFactor")?.value.trim();
      const airtime_factor = airtimeFactorVal ? parseFloat(airtimeFactorVal) : 0;
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

      // Omitir PIN si no fue explícitamente modificado por el usuario (VUI02)
      if (isDirty("localDevicePin")) {
        const pinVal = document.getElementById("localDevicePin")?.value.trim();
        payload.pin = pinVal ? parseInt(pinVal, 10) : 0;
      }

      const res = await fetch("/api/config/radio", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const confirmed = data.config || data.applied || data.data?.config || data.data?.applied || payload;
        const radioFields = [
          "localFreq", "localTxPower", "localSf", "localBw", "localCr", "localRepeatMode",
          "localHopLimit", "localTelemetryEnable", "localTelemetryInterval", "localAdvertEnable",
          "localAdvertInterval", "localDevicePin", "localPathHashMode", "localRxDelay",
          "localAirtimeFactor", "localTelemBase", "localTelemLoc", "localTelemEnv",
          "localAdvLocPolicy", "localMultiAcks", "localManualAddContacts"
        ];
        radioFields.forEach((id) => this.dirtyFields.delete(id));
        this.populateLocalConfig(confirmed);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.radio_cfg_ok'), "success");
      } else {
        const errMsg = data.detail || data.message || data.error || I18n.t('settings.unknown');
        this._notify(I18n.t('settings.radio_save_error', { error: errMsg }), "error");
      }
    } catch (e) {
      this._notify(I18n.t('settings.radio_save_network_error', { error: e.message }), "error");
    } finally {
      this._isSavingRadio = false;
      if (submitBtn) submitBtn.disabled = false;
    }
  }

  async saveLocalIdentityAndPosition() {
    if (this._isSavingIdentity) return;
    const submitBtn = this.dom.localOwnerPosForm?.querySelector("button[type='submit']");
    this._isSavingIdentity = true;
    if (submitBtn) submitBtn.disabled = true;

    try {
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

      const res = await fetch("/api/config/identity", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const confirmed = data.config || data.applied || data.data?.config || data.data?.applied || payload;
        ["localNodeName", "localOwnerInfo", "localGpsLat", "localGpsLon", "localGpsAlt", "localPosFixed"].forEach((id) => this.dirtyFields.delete(id));
        this.populateLocalConfig(confirmed);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.identity_ok'), "success");
      } else {
        const errMsg = data.detail || data.message || data.error || I18n.t('settings.unknown');
        this._notify(I18n.t('settings.identity_save_error', { error: errMsg }), "error");
      }
    } catch (e) {
      this._notify(I18n.t('settings.network_error', { p0: e.message }), "error");
    } finally {
      this._isSavingIdentity = false;
      if (submitBtn) submitBtn.disabled = false;
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
          <button type="button" class="btn-danger btn-xs btn-del-custom-var" data-key="${escapeHtml(String(k))}" title="${I18n.t("settings.delete_variable")}">
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
      if (data.status === "ok") {
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
      if (data.status === "ok") {
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
        if (lbl) lbl.textContent = scopeName ? scopeName : I18n.t("settings.global_scope");
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
        if (lbl) lbl.textContent = scopeVal ? scopeVal : I18n.t("settings.global_scope");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.scope_applied", { p0: scopeVal || I18n.t("settings.global") }), "success");
      } else {
        this._notify(I18n.t("settings.scope_save_error", { p0: data.message || I18n.t("settings.unknown") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
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
        if (lbl) I18n.setText(lbl, "settings.global_scope");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.scope_reset"), "info");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
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
        const maxHops = cfg.max_hops != null ? Number(cfg.max_hops) : 3;
        const chkChat = document.getElementById("chkAutoAddChat");
        const chkOverwrite = document.getElementById("chkAutoAddOverwrite");
        const numHops = document.getElementById("numAutoAddMaxHops");
        if (chkOverwrite) chkOverwrite.checked = (flags & 1) !== 0;
        if (chkChat) chkChat.checked = (flags & 2) !== 0;
        if (numHops && maxHops != null) numHops.value = String(maxHops);
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
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.auto_add_saved"), "success");
      } else {
        this._notify(I18n.t("settings.policy_save_error", { p0: data.message || I18n.t("settings.unknown") }), "error");
      }
    } catch (err) {
      this._notify(I18n.t("settings.network_error", { p0: err.message }), "error");
    }
  }
}

