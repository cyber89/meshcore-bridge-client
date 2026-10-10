/**
 * RepeaterModule - Gestión remota de repetidores, consola terminal interactiva,
 * autenticación segura y telemetría RF en tiempo real.
 */

import { escapeHtml, getHardwarePowerLimits, REGION_FREQUENCIES } from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class RepeaterModule {
  constructor(context) {
    this.ctx = context;
    this.selectedRepeaterTarget = null;
    this.selectedRepeaterName = null;
    this.authenticatedRepeaters = new Set();
    this.repeaterPasswords = new Map();
    this._remoteCliHistory = [];
    this._remoteCliHistoryIdx = -1;
    this._lastTerminalEntry = null;
    this.dom = {};
    this.dirtyFields = new Set();
    this._fieldEditVersions = new Map();
    this._modalRevision = 0;
    this._observationRevision = 0;
    this._remoteRadioPreferences = {};
    this._isSavingRadio = false;
    this._isSavingOwnerPos = false;
    this._isSavingSecurity = false;
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
  }

  onLanguageChange() {
    if (this._neighbors) this.renderNeighborsTable(this._neighbors);
    const submit = this.dom.btnRepeaterGateSubmit;
    if (submit) I18n.setText(submit, submit.disabled ? 'repeater.verify' : 'repeater.unlock');
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

  _resetModalInputs() {
    ++this._modalRevision;
    ++this._observationRevision;
    this.dirtyFields.clear();
    this._fieldEditVersions.clear();
    this._remoteRadioPreferences = {};
    this._isSavingRadio = false;
    this._isSavingOwnerPos = false;
    this._isSavingSecurity = false;
    for (const id of ["btnSubmitRepRadio", "btnSubmitRepOwnerPos", "btnSubmitRepSecurity"]) {
      const button = document.getElementById(id);
      if (button) button.disabled = false;
    }
    const setVal = (id, val = "") => {
      const el = document.getElementById(id);
      if (el) el.value = val;
    };
    setVal("radioFreq", "");
    setVal("radioRegion", "US915");
    setVal("radioPower", "");
    const pVal = document.getElementById("radioPowerVal");
    if (pVal) pVal.textContent = "-- dBm";
    setVal("radioHopLimit", "");
    setVal("radioBeaconInterval", "");
    setVal("radioSf", "");
    setVal("radioBw", "");
    setVal("radioCr", "");
    const repMode = document.getElementById("radioRepeatMode");
    if (repMode) repMode.checked = false;
    const repBadge = document.getElementById("radioRepeatBadge");
    if (repBadge) {
      I18n.setText(repBadge, 'settings.unknown');
      repBadge.className = "toggle-state-badge";
    }
    setVal("repOwnerName", "");
    setVal("repOwnerInfo", "");
    setVal("repPosLat", "");
    setVal("repPosLon", "");
    setVal("repPosAlt", "");
    const posFixed = document.getElementById("repPosFixed");
    if (posFixed) posFixed.checked = false;
    const posFixedBadge = document.getElementById("repPosFixedBadge");
    if (posFixedBadge) {
      I18n.setText(posFixedBadge, "repeater.dynamic_gps");
      posFixedBadge.className = "toggle-state-badge";
    }
    setVal("secNewAdminPwd", "");
    setVal("secNewGuestPwd", "");
    setVal("secAclMode", "public");
    setVal("secIdentityKey", "");
  }

  _bindElements() {
    this.dom = {
      repeaterAdminModal: document.getElementById("repeaterAdminModal"),
      repeaterAdminModalCard: document.getElementById("repeaterAdminModalCard"),
      adminModalNodeName: document.getElementById("adminModalNodeName"),
      adminModalNodePk: document.getElementById("adminModalNodePk"),
      adminModalNodePkDisplay: document.getElementById("adminModalNodePkDisplay"),
      repeaterAuthGate: document.getElementById("repeaterAuthGate"),
      repeaterAdminUnlockedContent: document.getElementById("repeaterAdminUnlockedContent"),
      adminModalAuthStatus: document.getElementById("adminModalAuthStatus"),
      repeaterGateStatus: document.getElementById("repeaterGateStatus"),
      btnRepeaterGateSubmit: document.getElementById("btnRepeaterGateSubmit"),
      repeaterGatePassword: document.getElementById("repeaterGatePassword"),
      btnToggleGatePwd: document.getElementById("btnToggleGatePwd"),
      btnRepeaterLogout: document.getElementById("btnRepeaterLogout"),
      repeaterTerminalInput: document.getElementById("repeaterTerminalInput"),
      repeaterTerminalForm: document.getElementById("repeaterTerminalForm"),
      repeaterTerminalOutput: document.getElementById("repeaterTerminalOutput"),
      btnClearRepeaterTerminal: document.getElementById("btnClearRepeaterTerminal"),
      repQuickCmdForm: document.getElementById("repQuickCmdForm"),
      repQuickCmdInput: document.getElementById("repQuickCmdInput"),
      repQuickCmdFeedback: document.getElementById("repQuickCmdFeedback"),
      btnGoToTerminalTab: document.getElementById("btnGoToTerminalTab"),
      btnCloseRepeaterAdminModal: document.getElementById("btnCloseRepeaterAdminModal"),
    };
  }

  _bindEvents() {
    // Rastreo de campos en borrador del modal de repetidor (F01, F11)
    const markDirty = (e) => {
      if (e.target && e.target.id) {
        this.dirtyFields.add(e.target.id);
        this._fieldEditVersions.set(e.target.id, (this._fieldEditVersions.get(e.target.id) || 0) + 1);
      }
    };
    [
      "radioFreq", "radioRegion", "radioPower", "radioHopLimit", "radioRepeatMode",
      "radioBeaconInterval", "radioSf", "radioBw", "radioCr",
      "repOwnerName", "repOwnerInfo", "repPosLat", "repPosLon", "repPosAlt", "repPosFixed",
      "secNewAdminPwd", "secNewGuestPwd", "secAclMode", "secIdentityKey"
    ].forEach((id) => {
      const el = document.getElementById(id);
      if (el) {
        el.addEventListener("input", markDirty);
        el.addEventListener("change", markDirty);
      }
    });

    const { repeaterGatePassword, btnToggleGatePwd, repeaterTerminalInput, repeaterTerminalForm } = this.dom;

    if (btnToggleGatePwd && repeaterGatePassword) {
      btnToggleGatePwd.addEventListener("click", () => {
        if (repeaterGatePassword.type === "password") {
          repeaterGatePassword.type = "text";
          btnToggleGatePwd.textContent = "🙈";
        } else {
          repeaterGatePassword.type = "password";
          btnToggleGatePwd.textContent = "👁️";
        }
      });
    }

    const gateForm = document.getElementById("repeaterGateForm");
    const gateSubmit = this.dom.btnRepeaterGateSubmit;
    const submitAuth = async () => {
      const target = this.selectedRepeaterTarget;
      const pwd = repeaterGatePassword ? repeaterGatePassword.value : "";
      if (!target) return;
      await this.authenticateRepeater(target, pwd);
    };

    if (gateForm) {
      gateForm.addEventListener("submit", (e) => {
        e.preventDefault();
        submitAuth();
      });
    }
    if (gateSubmit) {
      gateSubmit.addEventListener("click", submitAuth);
    }

    const logoutBtn = this.dom.btnRepeaterLogout;
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (target) {
          try {
            fetch("/api/repeater/remote/logout", {
              method: "POST",
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ target_node: target }),
            }).catch(() => {});
          } catch (_) {}
          this.clearStoredRepeaterPassword(target);
          this.lockRepeaterAdminView(target);
          if (repeaterGatePassword) {
            repeaterGatePassword.value = "";
            repeaterGatePassword.focus();
          }
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.rep_logout'), "info");
        }
      });
    }

    // Subtabs de repetidor
    document.querySelectorAll(".repeater-subtabs .subtab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".repeater-subtabs .subtab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".repeater-subpanel").forEach((p) => p.classList.remove("active"));
        btn.classList.add("active");
        const panelId = btn.getAttribute("data-subtab");
        const panel = document.getElementById(panelId);
        if (panel) panel.classList.add("active");

        if (panelId === "rep-console") {
          setTimeout(() => {
            const inp = this.dom.repeaterTerminalInput || document.getElementById("repeaterTerminalInput");
            if (inp) inp.focus();
            const out = this.dom.repeaterTerminalOutput || document.getElementById("repeaterTerminalOutput");
            if (out) out.scrollTop = out.scrollHeight;
          }, 80);
        }
      });
    });

    // Atajo desde Telemetría a Consola Terminal Completa
    const btnGoToTerm = this.dom.btnGoToTerminalTab || document.getElementById("btnGoToTerminalTab");
    if (btnGoToTerm) {
      btnGoToTerm.addEventListener("click", () => {
        const termSubtab = document.querySelector('.repeater-subtabs .subtab-btn[data-subtab="rep-console"]');
        if (termSubtab) termSubtab.click();
      });
    }

    // Consola de Comando Directo en Pestaña Principal (Telemetría & Estado)
    const repQuickCmdForm = this.dom.repQuickCmdForm || document.getElementById("repQuickCmdForm");
    const repQuickCmdInput = this.dom.repQuickCmdInput || document.getElementById("repQuickCmdInput");
    const repQuickCmdFeedback = this.dom.repQuickCmdFeedback || document.getElementById("repQuickCmdFeedback");

    if (repQuickCmdForm) {
      repQuickCmdForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const cmd = repQuickCmdInput ? repQuickCmdInput.value.trim() : "";
        const target = this.selectedRepeaterTarget;
        if (!cmd) return;
        if (!target) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.choose_target"), "warning");
          return;
        }
        if (this._redactRemoteCommand(cmd) === cmd) this._remoteCliHistory.push(cmd);
        this._remoteCliHistoryIdx = -1;
        if (repQuickCmdInput) repQuickCmdInput.value = "";

        if (repQuickCmdFeedback) {
          repQuickCmdFeedback.className = "rep-quick-feedback pending";
          I18n.setText(repQuickCmdFeedback, "repeater.transmitting_command", { p0: this._redactRemoteCommand(cmd) });
          repQuickCmdFeedback.classList.remove("hidden");
        }

        const password = this.getRepeaterPassword(target);
        try {
          if (cmd.toLowerCase() === "ping" || cmd.toLowerCase() === "ping 0" || cmd.toLowerCase() === "pingzero") {
            await this.pingZero(target, this.selectedRepeaterName);
          } else {
            await this.executeRepeaterCommand(target, cmd, {}, password);
          }
        } catch (err) {
          if (repQuickCmdFeedback) {
            repQuickCmdFeedback.className = "rep-quick-feedback error";
            I18n.setText(repQuickCmdFeedback, "repeater.command_error", { p0: err.message });
          }
        }
      });
    }

    // Cierre del modal de administración de repetidor
    const closeBtn = this.dom.btnCloseRepeaterAdminModal || document.getElementById("btnCloseRepeaterAdminModal");
    if (closeBtn) {
      closeBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.closeRepeaterAdminModal();
      });
    }

    const gateCancelBtn = document.getElementById("btnRepeaterGateCancel");
    if (gateCancelBtn) {
      gateCancelBtn.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        this.closeRepeaterAdminModal();
      });
    }

    const modal = this.dom.repeaterAdminModal || document.getElementById("repeaterAdminModal");
    if (modal) {
      modal.addEventListener("click", (e) => {
        if (e.target === modal) {
          this.closeRepeaterAdminModal();
        }
      });
    }

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        const m = this.dom.repeaterAdminModal || document.getElementById("repeaterAdminModal");
        if (m && !m.classList.contains("hidden")) {
          this.closeRepeaterAdminModal();
        }
      }
    });

    // Desplegable de Ayuda de Comandos
    const btnToggleCmdHelp = document.getElementById("btnToggleCmdHelp");
    const btnCloseCmdHelp = document.getElementById("btnCloseCmdHelp");
    const helpDrawer = document.getElementById("terminalHelpDrawer");

    if (btnToggleCmdHelp && helpDrawer) {
      btnToggleCmdHelp.addEventListener("click", () => {
        helpDrawer.classList.toggle("hidden");
      });
    }
    if (btnCloseCmdHelp && helpDrawer) {
      btnCloseCmdHelp.addEventListener("click", () => {
        helpDrawer.classList.add("hidden");
      });
    }

    // Clic en items de ayuda para insertar comando
    document.querySelectorAll("#terminalHelpDrawer .help-cmd-item").forEach((item) => {
      item.addEventListener("click", () => {
        const cmd = item.getAttribute("data-cmd");
        if (repeaterTerminalInput && cmd) {
          repeaterTerminalInput.value = cmd;
          repeaterTerminalInput.focus();
        }
      });
    });

    // Botón Probar Autenticación en Modal
    if (this.dom.btnModalAuthTest) {
      this.dom.btnModalAuthTest.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        const password = this.getRepeaterPassword(target);
        if (!target) {
          const msg = I18n.t("repeater.select_repeater");
          if (this.ctx.showAlert) {
            await this.ctx.showAlert(msg, { type: "warning", title: I18n.t("modal.warning") || "Atención" });
          } else if (this.ctx.showToast) {
            this.ctx.showToast(msg, "warning");
          }
          return;
        }
        if (!password) {
          const msg = I18n.t("repeater.enter_pin");
          if (this.ctx.showAlert) {
            await this.ctx.showAlert(msg, { type: "warning", title: I18n.t("modal.warning") || "Atención" });
          } else if (this.ctx.showToast) {
            this.ctx.showToast(msg, "warning");
          }
          return;
        }
        await this.authenticateRepeater(target, password);
      });
    }

    // Formulario de Parámetros RF
    const radioForm = document.getElementById("repRadioForm");
    const repRegionSelect = document.getElementById("radioRegion");
    const repFreqInput = document.getElementById("radioFreq");
    if (repRegionSelect && repFreqInput) {
      repRegionSelect.addEventListener("change", (e) => {
        const reg = e.target.value;
        if (REGION_FREQUENCIES[reg]) {
          repFreqInput.value = REGION_FREQUENCIES[reg];
          this.dirtyFields.add("radioFreq");
          this._fieldEditVersions.set("radioFreq", (this._fieldEditVersions.get("radioFreq") || 0) + 1);
        }
      });
    }

    const repPowerSlider = document.getElementById("radioPower");
    const repPowerVal = document.getElementById("radioPowerVal");
    if (repPowerSlider && repPowerVal) {
      repPowerSlider.addEventListener("input", (e) => {
        repPowerVal.textContent = `${e.target.value} dBm`;
      });
    }

    const repToggle = document.getElementById("radioRepeatMode");
    const repBadge = document.getElementById("radioRepeatBadge");
    if (repToggle && repBadge) {
      repToggle.addEventListener("change", (e) => {
        const isChecked = e.target.checked;
        I18n.setText(repBadge, isChecked ? 'common.on' : 'common.off');
        repBadge.className = isChecked ? "toggle-state-badge is-active-purple" : "toggle-state-badge";
      });
    }

    if (radioForm) {
      radioForm.addEventListener("submit", (event) => {
        event.preventDefault();
        this.saveRemoteConfiguration("radio");
      });
    }

    // Formulario de Propietario & Posición
    const ownerPosForm = document.getElementById("repOwnerPosForm");
    const posFixedToggle = document.getElementById("repPosFixed");
    const posFixedBadge = document.getElementById("repPosFixedBadge");
    if (posFixedToggle && posFixedBadge) {
      posFixedToggle.addEventListener("change", (e) => {
        const isChecked = e.target.checked;
        I18n.setText(posFixedBadge, isChecked ? "repeater.fixed" : "repeater.dynamic_gps");
        posFixedBadge.className = isChecked ? "toggle-state-badge is-active" : "toggle-state-badge";
      });
    }

    if (ownerPosForm) {
      ownerPosForm.addEventListener("submit", (event) => {
        event.preventDefault();
        this.saveRemoteConfiguration("ownerPos");
      });
    }

    // Formulario de Seguridad & ACL (F11)
    const securityForm = document.getElementById("repSecurityForm");
    if (securityForm) {
      securityForm.addEventListener("submit", (event) => {
        event.preventDefault();
        this.saveRemoteConfiguration("security");
      });
    }

    // Botón refrescar telemetría
    const btnRefreshTelem = document.getElementById("btnRefreshRepeaterTelem");
    if (btnRefreshTelem) {
      btnRefreshTelem.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.getRepeaterPassword(target);
        this.appendTerminalLine(I18n.t("repeater.tx_telemetry", { p0: target.slice(0, 8) }), "term-cmd");
        btnRefreshTelem.disabled = true;
        const lbl = btnRefreshTelem.querySelector(".btn-compact-label") || btnRefreshTelem;
        const origText = lbl.textContent;
        I18n.setText(lbl, "repeater.querying");
        try {
          const received = await this.refreshRepeaterFullTelemetry(target, password);
          if (received && this.ctx.showToast) this.ctx.showToast(I18n.t('toast.rep_telem_req'), "info");
        } catch (_) {
        } finally {
          btnRefreshTelem.disabled = false;
          lbl.textContent = origText || "Stats Core";
        }
      });
    }

    // Acciones Rápidas del Modal
    const btnActionPing = document.getElementById("btnModalActionPing");
    if (btnActionPing) {
      btnActionPing.addEventListener("click", () => {
        this.pingZero(this.selectedRepeaterTarget, this.selectedRepeaterName);
      });
    }

    const btnRadioStats = document.getElementById("btnModalActionRadioStats");
    if (btnRadioStats) {
      btnRadioStats.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.getRepeaterPassword(target);
        this.executeRepeaterCommand(target, "get radio", {}, password);
      });
    }

    const btnSyncClock = document.getElementById("btnSyncRepeaterClock");
    if (btnSyncClock) {
      btnSyncClock.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.getRepeaterPassword(target);
        this.executeRepeaterCommand(target, "sync_clock", {}, password);
      });
    }

    const btnModalAdvert = document.getElementById("btnModalActionAdvert");
    if (btnModalAdvert) {
      btnModalAdvert.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.getRepeaterPassword(target);
        this.executeRepeaterCommand(target, "advert", {}, password);
      });
    }

    const btnActionNeighbors = document.getElementById("btnModalActionNeighbors");
    if (btnActionNeighbors) {
      btnActionNeighbors.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const neighborsTabBtn = document.querySelector('.subtab-btn[data-subtab="rep-neighbors"]');
        if (neighborsTabBtn) neighborsTabBtn.click();
        this.fetchRepeaterNeighbors(target);
      });
    }

    const btnClearStats = document.getElementById("btnModalActionClearStats");
    if (btnClearStats) {
      btnClearStats.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const password = this.getRepeaterPassword(target);
        this.executeRepeaterCommand(target, "clear stats", {}, password);
      });
    }

    const btnReboot = document.getElementById("btnModalActionReboot");
    if (btnReboot) {
      btnReboot.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        const confirmMsg = I18n.t("repeater.reboot_confirm", { p0: target.slice(0, 8) });
        const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
        const confirmed = confirmFn
          ? await confirmFn(confirmMsg, {
              title: I18n.t("repeater.reboot_title") || "Reiniciar Repetidor",
              isDanger: true,
              confirmText: I18n.t("modal.confirm") || "Reiniciar",
            })
          : true;
        if (confirmed) {
          const password = this.getRepeaterPassword(target);
          this.executeRepeaterCommand(target, "reboot", {}, password);
        }
      });
    }

    const btnDiscoverNeighbors = document.getElementById("btnDiscoverNeighbors");
    if (btnDiscoverNeighbors) {
      btnDiscoverNeighbors.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        await this.fetchRepeaterNeighbors(target);
      });
    }

    const btnFetchRepOwner = document.getElementById("btnFetchRepOwner");
    if (btnFetchRepOwner) {
      btnFetchRepOwner.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        await this.fetchRepeaterOwner(target);
      });
    }

    const btnFetchRepRegions = document.getElementById("btnFetchRepRegions");
    if (btnFetchRepRegions) {
      btnFetchRepRegions.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        await this.fetchRepeaterRegions(target);
      });
    }

    const btnFetchRepAcl = document.getElementById("btnFetchRepAcl");
    if (btnFetchRepAcl) {
      btnFetchRepAcl.addEventListener("click", async () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        await this.fetchRepeaterAcl(target);
      });
    }

    document.querySelectorAll(".rep-quick-cmd").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cmd = btn.getAttribute("data-cmd");
        const target = this.selectedRepeaterTarget;
        if (!target) {
          this.appendTerminalLine(I18n.t('repeater.choose_target'), "term-error");
          return;
        }
        const password = this.getRepeaterPassword(target);
        if (cmd === "ping" || cmd === "ping 0") {
          this.pingZero(target, this.selectedRepeaterName);
        } else {
          this.executeRepeaterCommand(target, cmd, {}, password);
        }
      });
    });

    // Terminal Input & Form
    if (repeaterTerminalInput) {
      repeaterTerminalInput.addEventListener("keydown", (e) => {
        if (e.key === "ArrowUp") {
          e.preventDefault();
          if (this._remoteCliHistory.length === 0) return;
          if (this._remoteCliHistoryIdx === -1) {
            this._remoteCliHistoryIdx = this._remoteCliHistory.length - 1;
          } else if (this._remoteCliHistoryIdx > 0) {
            this._remoteCliHistoryIdx--;
          }
          repeaterTerminalInput.value = this._remoteCliHistory[this._remoteCliHistoryIdx] || "";
        } else if (e.key === "ArrowDown") {
          e.preventDefault();
          if (this._remoteCliHistoryIdx !== -1) {
            if (this._remoteCliHistoryIdx < this._remoteCliHistory.length - 1) {
              this._remoteCliHistoryIdx++;
              repeaterTerminalInput.value = this._remoteCliHistory[this._remoteCliHistoryIdx] || "";
            } else {
              this._remoteCliHistoryIdx = -1;
              repeaterTerminalInput.value = "";
            }
          }
        }
      });
    }

    // Botón Limpiar Consola de Repetidor
    const btnClearRepTerm = this.dom.btnClearRepeaterTerminal || document.getElementById("btnClearRepeaterTerminal");
    if (btnClearRepTerm) {
      btnClearRepTerm.addEventListener("click", () => {
        const out = this.dom.repeaterTerminalOutput || document.getElementById("repeaterTerminalOutput");
        if (out) {
          out.innerHTML = `<div class="term-line term-sys">${I18n.t("repeater.console_cleared")}</div>`;
        }
      });
    }

    // Clic en el área de salida del terminal enfoca automáticamente el campo de entrada
    const repTermOutput = this.dom.repeaterTerminalOutput || document.getElementById("repeaterTerminalOutput");
    if (repTermOutput) {
      repTermOutput.addEventListener("click", () => {
        const inp = this.dom.repeaterTerminalInput || document.getElementById("repeaterTerminalInput");
        if (inp) inp.focus();
      });
    }

    if (repeaterTerminalForm) {
      repeaterTerminalForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const cmd = repeaterTerminalInput ? repeaterTerminalInput.value.trim() : "";
        const target = this.selectedRepeaterTarget;
        if (!cmd) return;
        if (!target) {
          this.appendTerminalLine(I18n.t('repeater.choose_target'), "term-error");
          return;
        }

        // Comandos de emulación de terminal local interactiva
        if (cmd.toLowerCase() === "clear" || cmd.toLowerCase() === "cls") {
          const out = this.dom.repeaterTerminalOutput || document.getElementById("repeaterTerminalOutput");
          if (out) out.innerHTML = `<div class="term-line term-sys">${I18n.t("repeater.console_cleared")}</div>`;
          if (repeaterTerminalInput) repeaterTerminalInput.value = "";
          return;
        }
        if (cmd.toLowerCase() === "help" || cmd.toLowerCase() === "?") {
          const helpDrawer = document.getElementById("terminalHelpDrawer");
          if (helpDrawer) helpDrawer.classList.toggle("hidden");
        }

        if (this._redactRemoteCommand(cmd) === cmd) this._remoteCliHistory.push(cmd);
        this._remoteCliHistoryIdx = -1;
        if (repeaterTerminalInput) repeaterTerminalInput.value = "";
        const password = this.getRepeaterPassword(target);
        if (cmd.toLowerCase() === "ping" || cmd.toLowerCase() === "ping 0" || cmd.toLowerCase() === "pingzero") {
          this.pingZero(target, this.selectedRepeaterName);
        } else {
          this.executeRepeaterCommand(target, cmd, {}, password);
        }
      });
    }
  }

  _redactRemoteCommand(command) {
    return String(command).replace(/^((?:login|password|set\s+(?:password|guest\.password|identity))\s+).+$/i, "$1********");
  }

  _remoteFieldValue(id) {
    const element = document.getElementById(id);
    return element?.type === "checkbox" ? Boolean(element.checked) : (element?.value ?? "");
  }

  _collectRemoteDraft(kind) {
    const numeric = raw => String(raw).trim() === "" ? NaN : Number(raw);
    const fields = {
      radio: [
        ["radioFreq", "frequency", numeric], ["radioPower", "tx_power", numeric],
        ["radioSf", "spreading_factor", numeric], ["radioBw", "bandwidth", numeric],
        ["radioCr", "coding_rate", String], ["radioRepeatMode", "repeat", Boolean],
        ["radioBeaconInterval", "advert_interval", numeric], ["radioHopLimit", "hop_limit", numeric],
      ],
      ownerPos: [
        ["repOwnerName", "name", raw => String(raw).trim()], ["repOwnerInfo", "owner_info", String],
        ["repPosLat", "latitude", numeric], ["repPosLon", "longitude", numeric],
        ["repPosAlt", "altitude", numeric], ["repPosFixed", "fixed_position", Boolean],
      ],
      security: [
        ["secNewAdminPwd", "new_password", String], ["secNewGuestPwd", "guest_password", String],
        ["secAclMode", "acl_mode", String], ["secIdentityKey", "identity_key", String],
      ],
    };
    const params = {};
    const snapshot = new Map();
    for (const [id, key, convert] of fields[kind]) {
      if (!this.dirtyFields.has(id)) continue;
      const raw = this._remoteFieldValue(id);
      if (kind === "security" && (key === "new_password" || key === "guest_password") && raw === "") continue;
      const value = convert(raw);
      if (typeof value === "number" && !Number.isFinite(value)) throw new Error(I18n.t("settings.invalid_value"));
      if (key === "advert_interval" && value !== 0 && (!Number.isInteger(value) || value < 60 || value > 240 || value % 2 !== 0)) {
        throw new Error(I18n.t("repeater.advert_minutes_hint"));
      }
      params[key] = value;
      snapshot.set(id, {key,raw,version:this._fieldEditVersions.get(id) || 0});
    }
    if (kind === "radio" && ["frequency", "bandwidth", "spreading_factor", "coding_rate"].some(key => Object.hasOwn(params,key))) {
      for (const [id,key,convert] of fields.radio.slice(0,5).filter(([,key])=>key!=="tx_power")) {
        const raw = this._remoteFieldValue(id);
        if (String(raw).trim() === "") throw new Error(I18n.t("repeater.radio_baseline_required"));
        const value = convert(raw);
        if (typeof value === "number" && !Number.isFinite(value)) throw new Error(I18n.t("settings.invalid_value"));
        params[key] = value;
      }
    }
    return {params,snapshot};
  }

  _populateRemoteSavedRadio(saved) {
    if (!saved || typeof saved !== "object") return;
    this._remoteRadioPreferences = {...this._remoteRadioPreferences,...saved};
    for (const [key,id] of [["frequency","radioFreq"],["bandwidth","radioBw"],["spreading_factor","radioSf"],["coding_rate","radioCr"]]) {
      if (saved[key] == null) continue;
      const value = key === "coding_rate" && [5,6,7,8].includes(Number(saved[key])) ? `4/${saved[key]}` : saved[key];
      this._setFieldIfNotDirty(id,value);
    }
    const state = document.getElementById("remoteRadioSettingsState");
    if(state)I18n.setText(state,"repeater.radio_saved_preferences");
  }

  _remoteAppliedKey(applied, key) {
    const aliases = {
      frequency:["frequency","freq"], bandwidth:["bandwidth","bw"], spreading_factor:["spreading_factor","sf"],
      coding_rate:["coding_rate","cr"], repeat:["repeat","repeat_enabled"], name:["name","owner_name"],
      latitude:["latitude","lat"], longitude:["longitude","lon"], advert_interval:["advert_interval","beacon_interval"],
      new_password:["new_password","admin_password","password"],
    };
    return (aliases[key] || [key]).find(name => Object.hasOwn(applied, name) && applied[name] != null);
  }

  _commitRemoteConfirmed(target, applied, snapshot) {
    const confirmedFields = new Set();
    for (const [id, sent] of snapshot) {
      if (!this._remoteAppliedKey(applied, sent.key)) continue;
      if (this._remoteFieldValue(id) === sent.raw && (this._fieldEditVersions.get(id) || 0) === sent.version) {
        this.dirtyFields.delete(id);
        confirmedFields.add(id);
        if (id === "secNewAdminPwd" || id === "secNewGuestPwd") document.getElementById(id).value = "";
      }
      if (id === "secNewAdminPwd") {
        const canonical = this.resolveCanonicalPubkey(target) || target;
        this.setStoredRepeaterPassword(canonical, sent.raw);
        this.setStoredRepeaterPassword(target, sent.raw);
        if (this.dom.repeaterGatePassword) this.dom.repeaterGatePassword.value = sent.raw;
      }
    }
    const canonical = this.resolveCanonicalPubkey(target) || target;
    const existing = this.ctx.knownNodes?.get(canonical) || this.ctx.knownNodes?.get(target) || {};
    const next = {...existing};
    for (const key of ["frequency","tx_power","bandwidth","spreading_factor","coding_rate","repeat","name","owner_info","latitude","longitude","advert_interval"]) {
      const observed = this._remoteAppliedKey(applied, key);
      if (observed) next[key] = applied[observed];
    }
    if (Object.hasOwn(next,"name")) next.owner_name = next.alias = next.name;
    if (Object.hasOwn(next,"repeat")) next.repeat_enabled = next.repeat;
    this.ctx.knownNodes?.set(canonical,next);
    this._confirmedFieldIds = confirmedFields;
    try { this.populateRepeaterModalData({...next,public_key:canonical}); }
    finally { this._confirmedFieldIds = null; }
    if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonical,next);
  }

  async saveRemoteConfiguration(kind) {
    const flags = {radio:"_isSavingRadio",ownerPos:"_isSavingOwnerPos",security:"_isSavingSecurity"};
    const formIds = {radio:"repRadioForm",ownerPos:"repOwnerPosForm",security:"repSecurityForm"};
    const flag = flags[kind];
    if (this[flag]) return;
    const target = this.selectedRepeaterTarget;
    const canonical = this.resolveCanonicalPubkey(target) || target;
    if (!target || !this.authenticatedRepeaters.has(canonical)) {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.select_repeater"),"warning");
      return;
    }
    let draft;
    try { draft = this._collectRemoteDraft(kind); }
    catch(error) { if(this.ctx.showToast)this.ctx.showToast(error.message,"error");return; }
    if (Object.keys(draft.params).length === 0) {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("settings.no_config_changes"),"info");
      return;
    }
    const revision = this._modalRevision;
    const submit = document.getElementById(formIds[kind])?.querySelector("button[type='submit']");
    this[flag] = true;
    ++this._observationRevision;
    if(submit)submit.disabled=true;
    this.appendTerminalLine(I18n.t("repeater.config_sending"),"term-cmd");
    try {
      const response = await fetch("/api/repeater/remote/config",{
        method:"POST",
        headers:this.ctx.getAuthHeaders?this.ctx.getAuthHeaders({"Content-Type":"application/json"}):{"Content-Type":"application/json"},
        body:JSON.stringify({target_node:canonical,password:this.getRepeaterPassword(canonical),params:draft.params}),
      });
      const data = await response.json();
      if(revision!==this._modalRevision||this.selectedRepeaterTarget!==target)return;
      ++this._observationRevision;
      const result=data.data&&typeof data.data==="object"?data.data:data;
      const applied=result.applied&&typeof result.applied==="object"?result.applied:{};
      if(result.saved)this._populateRemoteSavedRadio(result.saved);
      if(Object.keys(applied).length)this._commitRemoteConfirmed(target,applied,draft.snapshot);
      const allApplied=Object.keys(draft.params).every(key=>this._remoteAppliedKey(applied,key));
      const allAcknowledged=Object.keys(draft.params).every(key=>this._remoteAppliedKey(applied,key)||this._remoteAppliedKey(result.saved||{},key));
      if(response.ok&&data.status==="ok"&&result.status==="ok"&&allApplied) {
        this.appendTerminalLine(I18n.t("repeater.config_confirmed"),"term-success");
        if(this.ctx.showToast)this.ctx.showToast(I18n.t("repeater.config_confirmed"),"success");
      } else if(response.ok&&data.status==="ok"&&result.pending_reboot&&allAcknowledged) {
        this.appendTerminalLine(I18n.t("repeater.config_saved_reboot"),"term-warning");
        if(this.ctx.showToast)this.ctx.showToast(I18n.t("repeater.config_saved_reboot"),"warning");
      } else if(response.ok&&data.status==="ok"&&result.status==="dispatched") {
        this.appendTerminalLine(I18n.t("repeater.config_dispatched"),"term-warning");
        if(this.ctx.showToast)this.ctx.showToast(I18n.t("repeater.config_dispatched"),"warning");
      } else {
        const detail=data.detail||result.detail||data.message||result.message||data.error||I18n.t("settings.config_unconfirmed");
        this.appendTerminalLine(`✗ ${detail}`,"term-error");
        if(response.status===401||result.authenticated===false)this.handleRepeaterAuthError(target,detail);
        else if(this.ctx.showToast)this.ctx.showToast(I18n.t("app.error",{error:detail}),"error");
      }
      for(const entry of result.results||[]) {
        if(entry.response)this.appendTerminalLine(`← ${entry.command}: ${entry.response}`,"term-resp");
      }
    } catch(error) {
      if(revision===this._modalRevision&&this.selectedRepeaterTarget===target) {
        this.appendTerminalLine(I18n.t("repeater.command_network_error",{p0:error.message}),"term-error");
        if(this.ctx.showToast)this.ctx.showToast(I18n.t("repeater.command_network_error",{p0:error.message}),"error");
      }
    } finally {
      if(revision===this._modalRevision) {
        this[flag]=false;
        if(submit)submit.disabled=false;
      }
    }
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;
    this.ctx.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (!payload || typeof payload !== "object" || !this.selectedRepeaterTarget) return;
      const type = payload.type || payload.event_type;
      const contact = payload.contact || payload.data || {};
      const sender = payload.sender || payload.pubkey || payload.from || contact.public_key || contact.pubkey || contact.sender;
      const canonicalSender = this.resolveCanonicalPubkey(sender);
      const canonicalTarget = this.resolveCanonicalPubkey(this.selectedRepeaterTarget);
      if (!canonicalSender || canonicalSender !== canonicalTarget) return;
      if (type === "repeater_response" || type === "repeater_telemetry") {
        const text = payload.text || payload.message || payload.response;
        if (text) this.appendTerminalLine(text, "term-resp");
        // Only structured, sender-scoped observations can change the registry.
        if (payload.telemetry && typeof payload.telemetry === "object") this._mergeRemoteObservation(canonicalSender, payload.telemetry);
      } else if (type === "contact_updated" || type === "contact_discovered") {
        this._mergeRemoteObservation(canonicalSender, contact);
      } else if (type === "telemetry" || type === "stats" || type === "STATS") {
        this._mergeRemoteObservation(canonicalSender, {...payload,...contact,...payload.telemetry});
      }
    });
  }

  _mergeRemoteObservation(target, observation) {
    if (!observation || typeof observation !== "object" || Array.isArray(observation)) return;
    const canonical = this.resolveCanonicalPubkey(target) || target;
    const existing = this.ctx.knownNodes?.get(canonical) || {};
    const updated = {...existing,...observation,public_key:canonical};
    this.ctx.knownNodes?.set(canonical,updated);
    if (this.resolveCanonicalPubkey(this.selectedRepeaterTarget) === canonical) this.populateRepeaterModalData(updated);
    if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonical,updated);
  }

  resolveCanonicalPubkey(pubkey) {
    if (this.ctx.resolveCanonicalPubkey) {
      return this.ctx.resolveCanonicalPubkey(pubkey);
    }
    return pubkey ? String(pubkey).trim().toLowerCase() : "";
  }

  getStoredRepeaterPassword(pubkey) {
    if (!pubkey) return "";
    try {
      return this.repeaterPasswords.get(pubkey.toLowerCase()) || "";
    } catch (_) {
      return "";
    }
  }

  setStoredRepeaterPassword(pubkey, pwd) {
    if (!pubkey || !pwd) return;
    try {
      this.repeaterPasswords.set(pubkey.toLowerCase(), pwd);
    } catch (_) {}
  }

  clearStoredRepeaterPassword(pubkey) {
    if (!pubkey) return;
    try {
      this.authenticatedRepeaters.delete(pubkey.toLowerCase());
      this.repeaterPasswords.delete(pubkey.toLowerCase());
    } catch (_) {}
  }

  getRepeaterPassword(target) {
    if (!target) return "";
    const canonicalPk = this.resolveCanonicalPubkey(target);
    return this.getStoredRepeaterPassword(canonicalPk) ||
      this.getStoredRepeaterPassword(target) ||
      (this.repeaterPasswords && (this.repeaterPasswords.get(canonicalPk) || this.repeaterPasswords.get(target))) ||
      (this.dom.repeaterGatePassword ? this.dom.repeaterGatePassword.value : "");
  }

  lockRepeaterAdminView(pubkey, errorMessage = null) {
    const card = this.dom.repeaterAdminModalCard || document.getElementById("repeaterAdminModalCard");
    if (card) {
      card.classList.remove("unlocked");
      card.classList.add("locked");
    }
    const gate = this.dom.repeaterAuthGate || document.getElementById("repeaterAuthGate");
    if (gate) gate.classList.remove("hidden");
    const unlocked = this.dom.repeaterAdminUnlockedContent || document.getElementById("repeaterAdminUnlockedContent");
    if (unlocked) unlocked.classList.add("hidden");

    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    if (statusEl) {
      if (errorMessage) {
        statusEl.className = "auth-gate-status error";
        statusEl.removeAttribute('data-i18n');
        statusEl.textContent = errorMessage;
        statusEl.classList.remove("hidden");
      } else {
        statusEl.className = "auth-gate-status hidden";
        statusEl.removeAttribute('data-i18n');
        statusEl.textContent = "";
      }
    }

    const pwdInput = this.dom.repeaterGatePassword || document.getElementById("repeaterGatePassword");
    if (pwdInput) {
      pwdInput.disabled = false;
      setTimeout(() => pwdInput.focus(), 150);
    }
    const submitBtn = this.dom.btnRepeaterGateSubmit || document.getElementById("btnRepeaterGateSubmit");
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = `<span class="btn-icon">🔐</span> ${I18n.t('repeater.unlock')}`;
      I18n.setText(submitBtn, 'repeater.unlock');
    }
  }

  unlockRepeaterAdminView(pubkey) {
    const card = this.dom.repeaterAdminModalCard || document.getElementById("repeaterAdminModalCard");
    if (card) {
      card.classList.remove("locked");
      card.classList.add("unlocked");
    }
    const gate = this.dom.repeaterAuthGate || document.getElementById("repeaterAuthGate");
    if (gate) gate.classList.add("hidden");
    const unlocked = this.dom.repeaterAdminUnlockedContent || document.getElementById("repeaterAdminUnlockedContent");
    if (unlocked) unlocked.classList.remove("hidden");

    const authStatus = this.dom.adminModalAuthStatus || document.getElementById("adminModalAuthStatus");
    if (authStatus) {
      authStatus.className = "auth-status-chip authenticated";
      I18n.setText(authStatus, "repeater.authenticated");
    }

    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    if (statusEl) {
      statusEl.className = "auth-gate-status hidden";
      statusEl.textContent = "";
    }
  }

  handleRepeaterAuthError(pubkey, message = I18n.t('rep.auth_err')) {
    if (this.ctx.showToast) this.ctx.showToast(message, "error");
    this.clearStoredRepeaterPassword(pubkey);
    this.lockRepeaterAdminView(pubkey, `⚠️ ${message}`);
  }

  async authenticateRepeater(pubkey, password) {
    if (!pubkey || !password) {
      this.handleRepeaterAuthError(pubkey, I18n.t("repeater.enter_password"));
      return false;
    }

    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    const revision = this._modalRevision;
    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    const submitBtn = this.dom.btnRepeaterGateSubmit || document.getElementById("btnRepeaterGateSubmit");

    if (statusEl) {
      statusEl.className = "auth-gate-status loading";
      I18n.setText(statusEl, 'rep.verifying');
      statusEl.classList.remove("hidden");
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = `<span class="btn-icon">⏳</span> ${I18n.t('repeater.verify')}`;
      I18n.setText(submitBtn, 'repeater.verify');
    }

    try {
      const res = await fetch("/api/repeater/remote/login", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: canonicalPk, password: password }),
      });
      const data = await res.json();
      if (revision !== this._modalRevision || this.resolveCanonicalPubkey(this.selectedRepeaterTarget) !== canonicalPk) return false;

      if (res.ok && data.status === "ok" && data.data?.authenticated === true) {
        this.authenticatedRepeaters.add(canonicalPk);
        this.authenticatedRepeaters.add(pubkey);
        this.setStoredRepeaterPassword(canonicalPk, password);
        this.unlockRepeaterAdminView(canonicalPk);
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.rep_auth_ok'), "success");

        this.refreshRepeaterFullTelemetry(canonicalPk, password);
        return true;
      } else {
        const errorDetail = data.message || data.data?.message || I18n.t("repeater.bad_password");
        this.handleRepeaterAuthError(canonicalPk, errorDetail);
        return false;
      }
    } catch (err) {
      if (revision !== this._modalRevision) return false;
      this.handleRepeaterAuthError(canonicalPk, I18n.t("repeater.connection_error", { p0: err.message }));
      return false;
    } finally {
      if (submitBtn && revision === this._modalRevision) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span class="btn-icon">🔐</span> ${I18n.t('repeater.unlock')}`;
        I18n.setText(submitBtn, 'repeater.unlock');
      }
    }
  }

  async refreshRepeaterFullTelemetry(canonicalPk, password) {
    const revision = this._modalRevision;
    const observationRevision = this._observationRevision;
    if (!canonicalPk || !password) return;
    try {
      const res = await fetch("/api/repeater/remote/action", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: canonicalPk, password: password, action: "refresh_telemetry" }),
      });
      const data = await res.json();
      if (revision !== this._modalRevision || observationRevision !== this._observationRevision) return false;
      if (res.ok && data.status === "ok" && !["error", "partial"].includes(data.data?.status)) {
        const payload = data.data || data;
        const telem = payload.telemetry || {};
        if (Object.keys(telem).length > 0 && this.ctx.knownNodes) {
          const existing = this.ctx.knownNodes.get(canonicalPk) || {};
          const updated = { ...existing, ...telem, public_key: canonicalPk };
          this.ctx.knownNodes.set(canonicalPk, updated);
          if (this.selectedRepeaterTarget && (this.selectedRepeaterTarget === canonicalPk || this.resolveCanonicalPubkey(this.selectedRepeaterTarget) === canonicalPk)) {
            this.populateRepeaterModalData(updated);
          }
          if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonicalPk, updated);
        }
        if (payload.responses) {
          for (const [cmd, resp] of Object.entries(payload.responses)) {
            this.appendTerminalLine(`← [${cmd}] ${resp}`, "term-resp");
          }
        }
        if (payload.saved) this._populateRemoteSavedRadio(payload.saved);
        return Object.keys(telem).length > 0 || Object.values(payload.responses || {}).some(text => Boolean(text));
      } else if (data.status === "error" && data.cooldown_remaining) {
        this.appendTerminalLine(I18n.t("repeater.telemetry_cooldown", { p0: data.cooldown_remaining }), "term-resp");
      } else {
        const detail = data.detail || data.message || data.data?.message || I18n.t("settings.config_unconfirmed");
        this.appendTerminalLine(I18n.t("repeater.command_error", {p0:detail}), "term-error");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.command_error", {p0:detail}), "error");
      }
    } catch (err) {
      console.warn("Error en refreshRepeaterFullTelemetry:", err);
    }
    return false;
  }

  calculateBatteryPct(val) {
    if (val == null || isNaN(val)) return null;
    const v = Number(val);
    const volt = v > 100 ? v / 1000 : v;
    if (volt >= 4.35) return 100;
    if (volt <= 3.30) return 0;
    const table = [
      [4.20, 100], [4.15, 95], [4.10, 90], [4.05, 85], [4.00, 80],
      [3.95, 75], [3.90, 70], [3.85, 65], [3.82, 60], [3.80, 55],
      [3.78, 50], [3.76, 45], [3.74, 40], [3.72, 35], [3.70, 30],
      [3.67, 25], [3.64, 20], [3.60, 15], [3.55, 10], [3.45, 5],
      [3.30, 0]
    ];
    for (let i = 0; i < table.length - 1; i++) {
      const [vHigh, pctHigh] = table[i];
      const [vLow, pctLow] = table[i + 1];
      if (volt >= vLow && volt <= vHigh) {
        const ratio = (volt - vLow) / (vHigh - vLow);
        return Math.round(pctLow + ratio * (pctHigh - pctLow));
      }
    }
    return 0;
  }

  openRepeaterAdminModal(pubkey, name) {
    if (this.ctx.knownNodes) {
      const canonicalPk = this.resolveCanonicalPubkey(pubkey);
      const existing = this.ctx.knownNodes.get(canonicalPk) || this.ctx.knownNodes.get(pubkey);
      if (existing) {
        const role = String(existing.role || existing.advert_type || "").toUpperCase();
        if (["LOCAL", "CLIENT", "SENSOR"].includes(role) || [0, 1, 4].includes(existing.advert_type) || canonicalPk === this.ctx.localNodePubkey) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.not_administrable"), "warning");
          return;
        }
      }
    }

    this._resetModalInputs();
    this.selectedRepeaterTarget = pubkey;
    this.selectedRepeaterName = name || pubkey;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    const modal = this.dom.repeaterAdminModal || document.getElementById("repeaterAdminModal");
    const nameEl = this.dom.adminModalNodeName || document.getElementById("adminModalNodeName");
    const pkInput = this.dom.adminModalNodePk || document.getElementById("adminModalNodePk");
    const pkDisplay = this.dom.adminModalNodePkDisplay || document.getElementById("adminModalNodePkDisplay");

    if (nameEl) nameEl.textContent = name || pubkey;
    if (pkInput) pkInput.value = canonicalPk;
    if (pkDisplay) pkDisplay.textContent = canonicalPk.length > 14 ? `${canonicalPk.slice(0, 8)}...${canonicalPk.slice(-4)}` : canonicalPk;

    const node = (this.ctx.knownNodes && (this.ctx.knownNodes.get(canonicalPk) || this.ctx.knownNodes.get(pubkey))) || {};
    this.populateRepeaterModalData(node);

    if (this.authenticatedRepeaters.has(canonicalPk) || this.authenticatedRepeaters.has(pubkey)) {
      this.unlockRepeaterAdminView(canonicalPk);
      const pwd = this.getRepeaterPassword(canonicalPk);
      if (pwd) {
        this.refreshRepeaterFullTelemetry(canonicalPk, pwd);
      }
    } else {
      const savedPwd = this.getStoredRepeaterPassword(canonicalPk);
      if (savedPwd) {
        this.lockRepeaterAdminView(canonicalPk);
        const pwdInput = this.dom.repeaterGatePassword || document.getElementById("repeaterGatePassword");
        if (pwdInput) pwdInput.value = savedPwd;
        this.authenticateRepeater(canonicalPk, savedPwd);
      } else {
        this.lockRepeaterAdminView(canonicalPk);
        const pwdInput = this.dom.repeaterGatePassword || document.getElementById("repeaterGatePassword");
        if (pwdInput) {
          pwdInput.value = "";
          setTimeout(() => pwdInput.focus(), 150);
        }
      }
    }

    if (modal) modal.classList.remove("hidden");
  }

  closeRepeaterAdminModal() {
    const modal = this.dom.repeaterAdminModal || document.getElementById("repeaterAdminModal");
    if (modal) {
      modal.classList.add("hidden");
    }
    this.selectedRepeaterTarget = null;
    this.selectedRepeaterName = null;
    this._resetModalInputs();
  }

  populateRepeaterModalData(node) {
    const pubkey = node.public_key || this.selectedRepeaterTarget;

    let calcBat = node.battery_pct != null ? Number(node.battery_pct) : (node.battery != null ? Number(node.battery) : (node.batt != null ? Number(node.batt) : null));
    let calcVolt = node.voltage_v != null ? Number(node.voltage_v) : (node.voltage != null ? Number(node.voltage) : (node.battery_mv ? Number(node.battery_mv) / 1000 : null));

    if (calcVolt != null && calcVolt > 100) {
      calcVolt = Number((calcVolt / 1000).toFixed(2));
    }

    if (calcBat == null && calcVolt != null && calcVolt >= 2.5) {
      calcBat = this.calculateBatteryPct(calcVolt);
    } else if (calcBat != null && calcBat > 100) {
      if (calcVolt == null) calcVolt = Number((calcBat / 1000).toFixed(2));
      calcBat = this.calculateBatteryPct(calcBat);
    }

    const batVal = calcBat != null && !isNaN(calcBat) ? calcBat : "--";
    const voltVal = calcVolt != null && !isNaN(calcVolt) ? (calcVolt > 100 ? (calcVolt / 1000).toFixed(2) : calcVolt.toFixed(2)) : "--";
    const solarVal = node.solar_v != null ? (Number(node.solar_v) > 100 ? (Number(node.solar_v) / 1000).toFixed(2) : Number(node.solar_v).toFixed(2)) : "--";

    const batEl = document.getElementById("repBatValue");
    if (batEl) batEl.textContent = batVal !== "--" ? `${batVal}%` : "-- %";
    const voltEl = document.getElementById("repVoltValue");
    if (voltEl) voltEl.textContent = voltVal !== "--" ? `${voltVal} V` : "-- V";
    const solarEl = document.getElementById("repSolarValue");
    if (solarEl) solarEl.textContent = solarVal !== "--" ? `${solarVal} V` : "-- V";

    const tempVal = node.temperature_c != null ? `${node.temperature_c} °C` : (node.temp != null ? `${node.temp} °C` : (node.temperature != null ? `${node.temperature} °C` : "-- °C"));
    const tempEl = document.getElementById("repTempValue");
    if (tempEl) tempEl.textContent = tempVal;

    const clockEl = document.getElementById("repClockValue");
    if (clockEl) clockEl.textContent = node.clock || "--:--:--";
    const uptimeEl = document.getElementById("repUptimeValue");
    if (uptimeEl) uptimeEl.textContent = node.uptime || "--";
    const seenEl = document.getElementById("repLastSeenValue");
    if (seenEl) I18n.setText(seenEl, node.last_seen ? "repeater.active_mesh" : "repeater.no_direct_contact");

    const airtimeVal = node.airtime_ms != null ? node.airtime_ms : (node.airtime != null ? node.airtime : null);
    const airtimeEl = document.getElementById("repAirtimeValue");
    if (airtimeEl) airtimeEl.textContent = airtimeVal != null ? `${airtimeVal} ms` : "-- ms";
    const airtimeDutyEl = document.getElementById("repAirtimeDuty");
    if (airtimeDutyEl) {
      if (node.duty_cycle_pct != null) {
        airtimeDutyEl.textContent = `Duty: ${Number(node.duty_cycle_pct).toFixed(1)}%`;
      } else if (airtimeVal != null) {
        airtimeDutyEl.textContent = `Duty: ${(airtimeVal / 36000).toFixed(2)}%`;
      } else {
        airtimeDutyEl.textContent = "Duty Cycle: --%";
      }
    }

    const noiseVal = node.noise_floor_dbm != null ? node.noise_floor_dbm : (node.noise_floor != null ? node.noise_floor : (node.noise != null ? node.noise : null));
    const noiseEl = document.getElementById("repNoiseValue");
    if (noiseEl) noiseEl.textContent = noiseVal != null ? `${noiseVal} dBm` : "-- dBm";

    const snrVal = node.last_snr != null ? node.last_snr : (node.snr != null ? node.snr : null);
    const rssiVal = node.last_rssi != null ? node.last_rssi : (node.rssi != null ? node.rssi : null);
    const snrEl = document.getElementById("repSnrValue");
    if (snrEl) snrEl.textContent = snrVal != null ? `${snrVal} dB` : "-- dB";
    const rssiEl = document.getElementById("repRssiValue");
    if (rssiEl) rssiEl.textContent = rssiVal != null ? `RSSI: ${rssiVal} dBm` : "RSSI: -- dBm";

    const pktsTx = node.packets_sent != null ? node.packets_sent : (node.tx_packets != null ? node.tx_packets : (node.nb_sent != null ? node.nb_sent : null));
    const pktsRx = node.packets_recv != null ? node.packets_recv : (node.rx_packets != null ? node.rx_packets : (node.nb_recv != null ? node.nb_recv : null));
    const pktsEl = document.getElementById("repPacketsValue");
    if (pktsEl) {
      if (pktsTx != null && pktsRx != null) {
        pktsEl.textContent = `${pktsTx} TX / ${pktsRx} RX`;
      } else if (pktsTx != null) {
        pktsEl.textContent = `${pktsTx} TX / -- RX`;
      } else if (pktsRx != null) {
        pktsEl.textContent = `-- TX / ${pktsRx} RX`;
      } else {
        pktsEl.textContent = "-- / --";
      }
    }

    const errsVal = node.packet_errors != null ? node.packet_errors : (node.error_count != null ? node.error_count : (node.rx_errors != null ? node.rx_errors : null));
    const dupsVal = node.duplicate_packets != null ? node.duplicate_packets : (node.duplicates != null ? node.duplicates : (node.direct_dups != null ? (node.direct_dups + (node.flood_dups || 0)) : null));
    const pktsErrEl = document.getElementById("repPacketErrorsValue");
    if (pktsErrEl) {
      const dStr = dupsVal != null ? dupsVal : "--";
      const eStr = errsVal != null ? errsVal : "--";
      I18n.setText(pktsErrEl, "repeater.packet_errors", { p0: dStr, p1: eStr });
    }

    const sumFreq = document.getElementById("repSummaryFreq");
    if (sumFreq) sumFreq.textContent = node.frequency != null ? `${node.frequency} MHz` : (node.freq != null ? `${node.freq} MHz` : "-- MHz");
    const sumPower = document.getElementById("repSummaryPower");
    if (sumPower) sumPower.textContent = node.tx_power != null ? `${node.tx_power} dBm` : (node.power != null ? `${node.power} dBm` : "-- dBm");
    const sumModem = document.getElementById("repSummaryModem");
    const sfVal = node.spreading_factor != null ? node.spreading_factor : (node.sf != null ? node.sf : "--");
    const bwVal = node.bandwidth != null ? node.bandwidth : (node.bw != null ? node.bw : "--");
    if (sumModem) sumModem.textContent = `SF${sfVal} / BW${Number(bwVal) > 1000 ? Number(bwVal) / 1000 : bwVal}`;

    const isRep = node.repeat_enabled != null ? Boolean(node.repeat_enabled) : (node.repeat != null ? Boolean(node.repeat) : null);

    const repHopLimit = node.hop_limit != null ? node.hop_limit : (node.default_hop_limit != null ? node.default_hop_limit : (node.hopLimit != null ? node.hopLimit : "--"));

    const sumHopLimit = document.getElementById("repSummaryHopLimit");
    if (sumHopLimit) I18n.setText(sumHopLimit, "repeater.hop_limit", { p0: repHopLimit });

    const sumRepeat = document.getElementById("repSummaryRepeat");
    if (sumRepeat) I18n.setText(sumRepeat, isRep == null ? "settings.unknown" : (isRep ? "repeater.enabled" : "repeater.disabled"));

    const sumQueue = document.getElementById("repSummaryQueue");
    if (sumQueue) I18n.setText(sumQueue, "repeater.queue_packets", { p0: node.queue_len != null ? node.queue_len : (node.tx_queue_len != null ? node.tx_queue_len : 0) });

    const sumPos = document.getElementById("repSummaryPos");
    if (sumPos) {
      if (node.latitude != null && node.longitude != null) {
        sumPos.removeAttribute('data-i18n');
        sumPos.textContent = `${Number(node.latitude).toFixed(4)}, ${Number(node.longitude).toFixed(4)}`;
      } else {
        I18n.setText(sumPos, "repeater.position_unset");
      }
    }

    const repFreq = node.frequency != null ? node.frequency : node.freq;
    if (repFreq != null) {
      const numF = parseFloat(repFreq);
      this._setFieldIfNotDirty("radioFreq", !isNaN(numF) ? numF.toFixed(3) : String(repFreq));
    }
    if (node.region) {
      this._setFieldIfNotDirty("radioRegion", node.region);
    } else if (repFreq != null) {
      const f = parseFloat(repFreq);
      if (f >= 863.0 && f < 865.0) this._setFieldIfNotDirty("radioRegion", "RU864");
      else if (f >= 865.0 && f < 867.0) this._setFieldIfNotDirty("radioRegion", "IN865");
      else if (f >= 867.0 && f <= 870.0) this._setFieldIfNotDirty("radioRegion", "EU868");
      else if (f >= 920.0 && f <= 925.0) this._setFieldIfNotDirty("radioRegion", "AS923");
      else if (f >= 902.0 && f <= 928.0) this._setFieldIfNotDirty("radioRegion", "US915");
    }

    const radioPowerInput = document.getElementById("radioPower");
    const radioPowerVal = document.getElementById("radioPowerVal");
    const pLimits = getHardwarePowerLimits(node);
    const rawPower = node.tx_power ?? node.power;
    const parsedPower = rawPower != null ? Number(rawPower) : null;
    const observedPower = Number.isInteger(parsedPower) ? parsedPower : null;
    if (radioPowerInput) {
      radioPowerInput.type = "number";
      radioPowerInput.step = "1";
      radioPowerInput.min = String(pLimits.min);
      radioPowerInput.max = String(pLimits.max);
      radioPowerInput.title = I18n.t(pLimits.confirmed ? 'repeater.power_limits_confirmed' : 'repeater.power_limits_unknown');
    }
    const powerLimitsHint = document.getElementById('radioPowerLimits');
    if (powerLimitsHint) I18n.setText(powerLimitsHint, pLimits.confirmed ? 'repeater.power_limits_confirmed' : 'repeater.power_limits_unknown');
    this._setFieldIfNotDirty("radioPower", observedPower ?? "");
    if (radioPowerVal) {
      const draftPower = this.dirtyFields.has('radioPower') && radioPowerInput?.value !== '' ? radioPowerInput?.value : observedPower;
      radioPowerVal.textContent = draftPower != null ? `${draftPower} dBm` : "-- dBm";
    }

    this._setFieldIfNotDirty("radioHopLimit", repHopLimit);

    if (node.advert_interval != null || node.beacon_interval != null) {
      this._setFieldIfNotDirty("radioBeaconInterval", node.advert_interval != null ? node.advert_interval : node.beacon_interval);
    }

    if (node.spreading_factor != null || node.sf != null) {
      let rawSf = String(node.spreading_factor != null ? node.spreading_factor : node.sf).toUpperCase().replace("SF", "").trim();
      this._setFieldIfNotDirty("radioSf", rawSf);
    }

    if (node.bandwidth != null || node.bw != null) {
      let rawBw = parseFloat(node.bandwidth != null ? node.bandwidth : node.bw);
      if (rawBw > 1000) rawBw = rawBw / 1000.0;
      const bwStr = String(rawBw);
      const supportedBws = ["7.8", "10.4", "15.6", "20.8", "31.25", "41.7", "62.5", "125", "250", "500"];
      const found = supportedBws.find((opt) => parseFloat(opt) === rawBw);
      this._setFieldIfNotDirty("radioBw", found || bwStr);
    }

    if (node.coding_rate != null || node.cr != null) {
      let rawCr = String(node.coding_rate != null ? node.coding_rate : node.cr).trim();
      if (["5", "6", "7", "8"].includes(rawCr)) rawCr = `4/${rawCr}`;
      if (["4/5", "4/6", "4/7", "4/8"].includes(rawCr)) {
        this._setFieldIfNotDirty("radioCr", rawCr);
      }
    }

    if (isRep != null) this._setFieldIfNotDirty("radioRepeatMode", null, isRep);
    const radioRepBadge = document.getElementById("radioRepeatBadge");
    if (radioRepBadge) {
      I18n.setText(radioRepBadge, isRep == null ? 'settings.unknown' : (isRep ? 'common.on' : 'common.off'));
      radioRepBadge.className = isRep ? "toggle-state-badge is-active-purple" : "toggle-state-badge";
    }

    if (node.owner_name != null || node.name != null) {
      this._setFieldIfNotDirty("repOwnerName", node.owner_name ?? node.name);
    }
    if (node.owner_info != null) {
      this._setFieldIfNotDirty("repOwnerInfo", node.owner_info);
    }

    const extractNum = (...keys) => {
      for (const k of keys) {
        if (k !== undefined && k !== null && k !== "") {
          const num = parseFloat(k);
          if (!isNaN(num)) return num;
        }
      }
      return "";
    };

    const posLatVal = extractNum(node.latitude, node.lat, node.gps_lat, node.gps?.latitude, node.position?.latitude);
    if (posLatVal !== "") this._setFieldIfNotDirty("repPosLat", posLatVal);

    const posLonVal = extractNum(node.longitude, node.lon, node.gps_lon, node.gps?.longitude, node.position?.longitude);
    if (posLonVal !== "") this._setFieldIfNotDirty("repPosLon", posLonVal);

    const posAltVal = extractNum(node.altitude_m, node.alt, node.altitude, node.gps?.altitude);
    if (posAltVal !== "") this._setFieldIfNotDirty("repPosAlt", posAltVal);

    const isFixed = (node.fixed_position !== undefined && node.fixed_position !== null)
      ? Boolean(node.fixed_position)
      : (node.fixed !== undefined && node.fixed !== null
          ? Boolean(node.fixed)
          : (node.latitude !== undefined && node.latitude !== null && node.latitude !== 0));
    this._setFieldIfNotDirty("repPosFixed", null, isFixed);
    const posFixedBadge = document.getElementById("repPosFixedBadge");
    if (posFixedBadge) {
      I18n.setText(posFixedBadge, isFixed ? "repeater.fixed" : "repeater.dynamic_gps");
      posFixedBadge.className = isFixed ? "toggle-state-badge is-active" : "toggle-state-badge";
    }

    if (node.acl_mode) {
      this._setFieldIfNotDirty("secAclMode", node.acl_mode);
    }
    if (Object.keys(this._remoteRadioPreferences).length) this._populateRemoteSavedRadio(this._remoteRadioPreferences);
  }

  appendTerminalLine(text, cssClass = "term-info") {
    if (!text) return;
    const strText = String(text).trim();
    if (!strText) return;

    const norm = strText
      .replace(/^[←ℹ✓>\s]+/, "")
      .replace(/^\[RESP\]\s*/i, "")
      .replace(/^\[RX OK\]\s*/i, "")
      .replace(/^\[TX\]\s*/i, "")
      .replace(/^>\s*/, "")
      .trim();

    const now = Date.now();
    if (norm && this._lastTerminalEntry) {
      const isDuplicate = (this._lastTerminalEntry.norm === norm) && (now - this._lastTerminalEntry.time < 4000);
      if (isDuplicate) {
        return;
      }
    }
    this._lastTerminalEntry = { norm: norm || strText, time: now };

    const line = document.createElement("div");
    line.className = `term-line ${cssClass}`;
    line.textContent = `[${new Date().toLocaleTimeString()}] ${strText}`;

    if (this.dom.repeaterTerminalOutput) {
      this.dom.repeaterTerminalOutput.appendChild(line);
      this.dom.repeaterTerminalOutput.scrollTop = this.dom.repeaterTerminalOutput.scrollHeight;
    }

  }


  async pingZero(targetNode, targetName) {
    const target = targetNode || this.selectedRepeaterTarget;
    const name = targetName || this.selectedRepeaterName || (target ? target.slice(0, 8) : I18n.t("repeater.unknown"));
    if (!target) {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.select_node"), "warning");
      return;
    }

    const norm = (target || "").toLowerCase().trim();
    const localPk = (document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();
    const isLocal = Boolean(target === "local") || (localPk && (
      norm === localPk ||
      (localPk.length >= 8 && norm.startsWith(localPk.slice(0, 8))) ||
      (norm.length >= 8 && localPk.startsWith(norm.slice(0, 8)))
    ));
    if (isLocal) {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.no_local_ping"), "warning");
      return;
    }

    if (this.ctx.knownNodes && this.ctx.knownNodes.has(target)) {
      const nodeInfo = this.ctx.knownNodes.get(target);
      if (nodeInfo && nodeInfo.role === "CLIENT") {
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.ping_repeaters_only"), "warning");
        return;
      }
    }

    if (!this._pingCooldowns) this._pingCooldowns = new Map();
    const cleanTarget = (target || "").toLowerCase();
    const now = Date.now();
    const cooldownExpires = this._pingCooldowns.get(cleanTarget) || 0;
    if (now < cooldownExpires) {
      const remainingSec = Math.ceil((cooldownExpires - now) / 1000);
      this.appendTerminalLine(I18n.t("repeater.ping_airtime_log", { p0: remainingSec, p1: escapeHtml(name) }), "term-warning");
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.ping_cooldown", { p0: remainingSec }), "warning");
      return;
    }

    this.appendTerminalLine(`meshcore@remote:~$ ping ${escapeHtml(name)} (${target.slice(0, 8)})`, "term-cmd");

    const btnActionPingEl = document.getElementById("btnModalActionPing");
    if (btnActionPingEl) {
      btnActionPingEl.disabled = true;
      I18n.setText(btnActionPingEl, "repeater.measuring");
    }

    try {
      const res = await fetch("/api/repeater/ping_zero", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target }),
      });
      const data = await res.json().catch(() => ({}));

      // Si el servidor activa rate-limiting LoRa 429
      if (res.status === 429 || data.code === 429) {
        const remSec = data.cooldown_remaining || 15;
        this._pingCooldowns.set(cleanTarget, Date.now() + remSec * 1000);
        const warnMsg = data.detail || data.message || I18n.t("repeater.ping_airtime", { p0: remSec });
        this.appendTerminalLine(`⚠️ [COOLDOWN] ${warnMsg}`, "term-warning");
        if (this.ctx.showToast) this.ctx.showToast(`⏳ ${warnMsg}`, "warning");
        this._startModalPingCooldown(remSec);
        return;
      }

      if (res.ok && data.status === "ok" && data.data) {
        this._pingCooldowns.set(cleanTarget, Date.now() + 15000);
        const pingData = data.data;
        const rtt = Number(pingData.rtt_ms || pingData.duration_ms || 0);
        const rssi = pingData.rssi != null ? `${pingData.rssi} dBm` : "--";
        const snrThere = pingData.snr_there != null ? `${Number(pingData.snr_there).toFixed(1)} dB` : (pingData.snr != null ? `${Number(pingData.snr).toFixed(1)} dB` : "--");
        const snrBack = pingData.snr_back != null ? `${Number(pingData.snr_back).toFixed(1)} dB` : (pingData.snr != null ? `${Number(pingData.snr).toFixed(1)} dB` : "--");

        const line = I18n.t("repeater.pong_direct", { p0: rtt, p1: snrThere, p2: snrBack, p3: rssi });
        this.appendTerminalLine(line, "term-success");

        const canonicalTarget = this.resolveCanonicalPubkey(target);
        if (this.ctx.knownNodes) {
          const existing = this.ctx.knownNodes.get(canonicalTarget) || this.ctx.knownNodes.get(target) || {
            public_key: canonicalTarget || target,
            name: name,
          };
          existing.ping_zero_rtt = rtt;
          if (pingData.rssi != null) existing.last_rssi = Number(pingData.rssi);
          if (pingData.snr_back != null) existing.last_snr = Number(pingData.snr_back);
          else if (pingData.snr != null) existing.last_snr = Number(pingData.snr);
          existing.last_seen = Math.floor(Date.now() / 1000);
          this.ctx.knownNodes.set(canonicalTarget, existing);
          if (target !== canonicalTarget) {
            this.ctx.knownNodes.set(target, existing);
          }
          if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonicalTarget, existing);
        }

        const snrStr = snrBack !== "--" ? ` | SNR: ${snrBack}` : "";
        const rssiStr = rssi !== "--" ? ` | RSSI: ${rssi}` : "";
        const pingMsg = (window.I18n ? window.I18n.t('toast.ping_ok') : null)
          ?.replace('{name}', name || cleanTarget)
          ?.replace('{rtt}', `${rtt} ms`)
          ?.replace('{snr}', snrStr)
          ?.replace('{rssi}', rssiStr) || `🎯 Pong de ${name || cleanTarget}: RTT ${rtt} ms${snrStr}${rssiStr}`;
        if (this.ctx.showToast) this.ctx.showToast(pingMsg, "success");
        this._startModalPingCooldown(15);
      } else {
        const errMsg = data.message || I18n.t('common.request_timeout');
        this.appendTerminalLine(I18n.t('repeater.ping_failure_line', { error: errMsg }), "term-error");
        if (errMsg.toLowerCase().includes("password") || errMsg.toLowerCase().includes("auth") || errMsg.toLowerCase().includes("pin")) {
          this.handleRepeaterAuthError(target, errMsg);
        } else {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.ping_failed", { p0: errMsg }), "error");
        }
      }
    } catch (err) {
      this.appendTerminalLine(`✗ [PING ERROR] ${err.message}`, "term-error");
      if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.ping_connection_error", { p0: err.message }), "error");
    } finally {
      if (!this._modalPingInterval) {
        const btnActionPingElFin = document.getElementById("btnModalActionPing");
        if (btnActionPingElFin) {
          btnActionPingElFin.disabled = false;
          I18n.setText(btnActionPingElFin, 'repeater.ping_button');
        }
      }
    }
  }

  _startModalPingCooldown(durationSec) {
    const btn = document.getElementById("btnModalActionPing");
    if (!btn) return;
    btn.disabled = true;
    if (this._modalPingInterval) clearInterval(this._modalPingInterval);

    let remaining = durationSec;
    I18n.setText(btn, "repeater.ping_wait", { p0: remaining });

    this._modalPingInterval = setInterval(() => {
      remaining--;
      if (remaining <= 0) {
        clearInterval(this._modalPingInterval);
        this._modalPingInterval = null;
        const currentBtn = document.getElementById("btnModalActionPing");
        if (currentBtn) {
          currentBtn.disabled = false;
          I18n.setText(currentBtn, 'repeater.ping_button');
        }
      } else {
        const currentBtn = document.getElementById("btnModalActionPing");
        if (currentBtn) {
          I18n.setText(currentBtn, "repeater.ping_wait", { p0: remaining });
        } else {
          clearInterval(this._modalPingInterval);
          this._modalPingInterval = null;
        }
      }
    }, 1000);
  }

  async executeRepeaterCommand(target, action, params = {}, password = "") {
    const revision = this._modalRevision;
    const observationRevision = this._observationRevision;
    const pwd = password || this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(`repeater> ${this._redactRemoteCommand(action)}`, "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/action", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, action, params, password: pwd }),
      });
      const data = await res.json();
      if (revision !== this._modalRevision || observationRevision !== this._observationRevision) return false;
      const qFeedback = document.getElementById("repQuickCmdFeedback");
      if (res.ok && data.status === "ok" && !["error", "partial"].includes(data.data?.status)) {
        const payload = data.data || data;
        const respTxt = payload.text || payload.response || (payload.status === "ok" ? payload.message : "") || "";
        if (respTxt) {
          const cleanTxt = String(respTxt).replace(/^>\s*/, "").trim();
          if (cleanTxt) {
            this.appendTerminalLine(`← [RESP] ${cleanTxt}`, "term-resp");
            if (qFeedback) {
              qFeedback.className = "rep-quick-feedback success";
              qFeedback.textContent = `← [RESP] ${cleanTxt}`;
              setTimeout(() => {
                if (qFeedback && qFeedback.classList.contains("success")) qFeedback.classList.add("hidden");
              }, 6000);
            }
          }
          const parsed = payload.telemetry || {};
          if (parsed && Object.keys(parsed).length > 0) {
            const canonicalPk = this.resolveCanonicalPubkey(target) || target;
            if (this.ctx.knownNodes) {
              const existing = this.ctx.knownNodes.get(canonicalPk) || {};
              const updated = { ...existing, ...parsed, public_key: canonicalPk };
              this.ctx.knownNodes.set(canonicalPk, updated);
              if (this.selectedRepeaterTarget && (this.selectedRepeaterTarget === target || canonicalPk === this.resolveCanonicalPubkey(this.selectedRepeaterTarget))) {
                this.populateRepeaterModalData(updated);
              }
              if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonicalPk, updated);
            }
          }
        } else if (qFeedback) {
          qFeedback.className = "rep-quick-feedback pending";
          I18n.setText(qFeedback, "repeater.command_sent", { p0: target.slice(0, 8) });
          setTimeout(() => {
            if (qFeedback && qFeedback.classList.contains("pending")) qFeedback.classList.add("hidden");
          }, 5000);
        }
        if (payload.saved) this._populateRemoteSavedRadio(payload.saved);
      } else {
        const errMsg = data.detail || data.message || data.error || I18n.t("repeater.unknown_error");
        this.appendTerminalLine(I18n.t('repeater.command_error', { p0: errMsg }), "term-error");
        if (qFeedback) {
          qFeedback.className = "rep-quick-feedback error";
          qFeedback.textContent = `✗ ${errMsg}`;
        }
        if (res.status === 401 || data.data?.authenticated === false) {
          this.handleRepeaterAuthError(target, errMsg);
        }
      }
    } catch (err) {
      if (revision !== this._modalRevision) return false;
      this.appendTerminalLine(I18n.t("repeater.command_network_error", { p0: err.message }), "term-error");
      const qFeedback = document.getElementById("repQuickCmdFeedback");
      if (qFeedback) {
        qFeedback.className = "rep-quick-feedback error";
        I18n.setText(qFeedback, "repeater.command_network_error", { p0: err.message });
      }
    }
  }

  async fetchRepeaterNeighbors(target) {
    const revision = this._modalRevision;
    const observationRevision = this._observationRevision;
    const pwd = this.getRepeaterPassword(target) || "";
    const btn = document.getElementById("btnDiscoverNeighbors");
    const tbody = document.getElementById("neighborsTableBody");
    if (btn) { btn.disabled = true; I18n.setText(btn, "repeater.probing"); }
    if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center">${I18n.t("repeater.probing_neighbors")}</td></tr>`;
    this.appendTerminalLine(I18n.t("repeater.tx_neighbors", { p0: target.slice(0, 8) }), "term-cmd");

    try {
      const res = await fetch("/api/repeater/remote/neighbours", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: pwd }),
      });
      const data = await res.json();
      if (revision !== this._modalRevision || observationRevision !== this._observationRevision) return false;
      if (res.ok && data.status === "ok" && (!data.data?.status || data.data.status === "ok") && Array.isArray(data.data?.neighbours ?? data.neighbours)) {
        const neighbours = data.data?.neighbours || data.neighbours || [];
        this.renderNeighborsTable(neighbours);
        const countBadge = document.getElementById("neighborsCountBadge");
        if (countBadge) I18n.setText(countBadge, "repeater.neighbor_count", { p0: neighbours.length });
        this.appendTerminalLine(I18n.t("repeater.rx_neighbors", { p0: neighbours.length }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.neighbors_detected", { p0: neighbours.length }), "success");
      } else {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">${escapeHtml(data.detail || data.data?.message || data.message || I18n.t("repeater.query_failed"))}</td></tr>`;
        this.appendTerminalLine(`✗ [ERROR] ${data.detail || data.data?.message || data.message || data.error || I18n.t("repeater.query_failed")}`, "term-error");
      }
    } catch (err) {
      if (revision !== this._modalRevision) return false;
      if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">${escapeHtml(err.message)}</td></tr>`;
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    } finally {
      if (btn && revision === this._modalRevision) {
        btn.disabled = false;
        btn.innerHTML = `<i class="bi bi-wifi me-1" style="font-size: 14px;" aria-hidden="true"></i> ${I18n.t('repeater.discover_neighbors')}`;
        I18n.setText(btn, 'repeater.discover_neighbors');
      }
    }
  }

  renderNeighborsTable(neighbours) {
    this._neighbors = neighbours;
    const tbody = document.getElementById("neighborsTableBody");
    if (!tbody) return;
    if (!Array.isArray(neighbours) || neighbours.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="color: var(--color-text-secondary);">${I18n.t("repeater.no_neighbors")}</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    neighbours.forEach((nb) => {
      const tr = document.createElement("tr");
      const pk = String(nb.public_key || nb.pubkey || nb.node || "").toLowerCase();
      const name = nb.name || nb.alias || (pk ? I18n.t("repeater.neighbor_name", { p0: pk.slice(0, 8) }) : "--");
      const snr = nb.snr != null ? `${nb.snr} dB` : "--";
      const hops = nb.hops != null ? nb.hops : 0;
      const lastSeen = nb.last_seen || nb.time || I18n.t("repeater.recent");

      tr.innerHTML = `
        <td class="font-mono"><strong>${escapeHtml(pk ? pk.slice(0, 12) + "..." : "--")}</strong></td>
        <td>${escapeHtml(name)}</td>
        <td><span class="badge-pill badge-outline">${escapeHtml(snr)}</span></td>
        <td><span class="badge-pill badge-secondary">${I18n.t('repeater.hops', { n: hops })}</span></td>
        <td>${escapeHtml(String(lastSeen))}</td>
        <td>
          <button type="button" class="btn btn-secondary btn-sm btn-neighbor-ping" data-target="${escapeHtml(pk)}" title="${I18n.t('repeater.direct_ping')}">
            🎯 Ping
          </button>
        </td>
      `;

      const pingBtn = tr.querySelector(".btn-neighbor-ping");
      if (pingBtn && pk) {
        pingBtn.addEventListener("click", () => {
          this.pingZero(pk, name);
        });
      }
      tbody.appendChild(tr);
    });
  }

  async fetchRepeaterOwner(target) {
    const revision = this._modalRevision;
    const observationRevision = this._observationRevision;
    const pwd = this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(I18n.t("repeater.tx_owner_query", { p0: target.slice(0, 8) }), "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/owner", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: pwd }),
      });
      const data = await res.json();
      if (revision !== this._modalRevision || observationRevision !== this._observationRevision) return false;
      if (this.selectedRepeaterTarget !== target) return;
      if (res.ok && data.status === "ok" && (!data.data?.status || data.data.status === "ok") && (data.data?.owner_name != null || data.data?.owner_info != null || data.owner_name != null || data.owner_info != null)) {
        const ownerName = data.data?.owner_name ?? data.data?.name ?? data.owner_name;
        const ownerInfo = data.data?.owner_info ?? data.owner_info;
        const nameEl = document.getElementById("repOwnerName");
        const infoEl = document.getElementById("repOwnerInfo");
        if (nameEl && ownerName != null && !this.dirtyFields.has("repOwnerName")) nameEl.value = ownerName;
        if (infoEl && ownerInfo != null && !this.dirtyFields.has("repOwnerInfo")) infoEl.value = ownerInfo;
        this.appendTerminalLine(I18n.t("repeater.owner_details", { p0: ownerName ?? "--", p1: ownerInfo ?? "--" }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.owner_received", { p0: ownerName || "OK" }), "success");
      } else {
        this.appendTerminalLine(`✗ [ERROR] ${data.detail || data.data?.message || data.message || data.error || I18n.t("repeater.query_failed")}`, "term-error");
      }
    } catch (err) {
      if (revision !== this._modalRevision) return false;
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    }
  }

  async fetchRepeaterRegions(target) {
    const revision = this._modalRevision;
    const observationRevision = this._observationRevision;
    const pwd = this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(I18n.t("repeater.tx_regions", { p0: target.slice(0, 8) }), "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/regions", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: pwd }),
      });
      const data = await res.json();
      if (revision !== this._modalRevision || observationRevision !== this._observationRevision) return false;
      if (this.selectedRepeaterTarget !== target) return;
      if (res.ok && data.status === "ok" && (!data.data?.status || data.data.status === "ok") && (data.data?.regions != null || data.regions != null)) {
        const regions = JSON.stringify(data.data?.regions || data.regions || []);
        this.appendTerminalLine(I18n.t("repeater.rx_regions", { p0: regions }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.regions", { p0: regions }), "info");
      } else {
        this.appendTerminalLine(`✗ [ERROR] ${data.detail || data.data?.message || data.message || data.error || I18n.t("repeater.query_failed")}`, "term-error");
      }
    } catch (err) {
      if (revision !== this._modalRevision) return false;
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    }
  }

  async fetchRepeaterAcl(target) {
    const revision = this._modalRevision;
    const observationRevision = this._observationRevision;
    const pwd = this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(I18n.t("repeater.tx_acl", { p0: target.slice(0, 8) }), "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/acl", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: pwd }),
      });
      const data = await res.json();
      if (revision !== this._modalRevision || observationRevision !== this._observationRevision) return false;
      if (this.selectedRepeaterTarget !== target) return;
      if (res.ok && data.status === "ok" && (!data.data?.status || data.data.status === "ok") && (data.data?.acl_data != null || data.acl_data != null)) {
        const aclData = JSON.stringify(data.data?.acl_data || data.acl_data || {});
        this.appendTerminalLine(I18n.t("repeater.rx_acl", { p0: aclData }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('repeater.acl_received'), "success");
      } else {
        this.appendTerminalLine(`✗ [ERROR] ${data.detail || data.data?.message || data.message || data.error || I18n.t("repeater.query_failed")}`, "term-error");
      }
    } catch (err) {
      if (revision !== this._modalRevision) return false;
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    }
  }
}

