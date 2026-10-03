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
      const pwd = repeaterGatePassword ? repeaterGatePassword.value.trim() : "";
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
        this._remoteCliHistory.push(cmd);
        this._remoteCliHistoryIdx = -1;
        if (repQuickCmdInput) repQuickCmdInput.value = "";

        if (repQuickCmdFeedback) {
          repQuickCmdFeedback.className = "rep-quick-feedback pending";
          I18n.setText(repQuickCmdFeedback, "repeater.transmitting_command", { p0: cmd });
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
          alert(I18n.t("repeater.select_repeater"));
          return;
        }
        if (!password) {
          alert(I18n.t("repeater.enter_pin"));
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
      radioForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert(I18n.t('repeater.select_repeater'));
          return;
        }
        const password = this.getRepeaterPassword(target);
        const freq = parseFloat(document.getElementById("radioFreq").value);
        const region = document.getElementById("radioRegion")?.value || "US915";
        const tx_power = parseInt(document.getElementById("radioPower").value, 10);
        const sf = parseInt(document.getElementById("radioSf").value, 10);
        const bw = parseFloat(document.getElementById("radioBw").value);
        const cr = document.getElementById("radioCr")?.value || "4/5";
        const hop_limit = parseInt(document.getElementById("radioHopLimit").value, 10);
        const repeat = document.getElementById("radioRepeatMode")?.checked === true;
        const beacon_interval = parseInt(document.getElementById("radioBeaconInterval")?.value || "300", 10);

        const params = { freq, region, tx_power, sf, bw, cr, hop_limit, repeat, beacon_interval };
        this.appendTerminalLine(I18n.t("repeater.tx_config", { p0: target.slice(0, 8), p1: freq, p2: tx_power, p3: sf, p4: bw }), "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.appendTerminalLine(I18n.t("repeater.rx_config", { p0: target.slice(0, 8) }), "term-success");
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.rep_cfg_ok'), "success");

            const sFreq = document.getElementById("repSummaryFreq");
            if (sFreq) sFreq.textContent = `${freq.toFixed(3)} MHz`;
            const sPower = document.getElementById("repSummaryPower");
            if (sPower) sPower.textContent = `${tx_power} dBm`;
            const sModem = document.getElementById("repSummaryModem");
            if (sModem) sModem.textContent = `SF${sf} / BW${bw}`;
            const sHop = document.getElementById("repSummaryHopLimit");
            if (sHop) I18n.setText(sHop, "repeater.hop_count", { p0: hop_limit });
            const sRep = document.getElementById("repSummaryRepeat");
            if (sRep) I18n.setText(sRep, repeat ? "repeater.enabled" : "repeater.disabled");

            if (this.ctx.knownNodes) {
              const canonicalPk = this.resolveCanonicalPubkey(target) || target;
              const existing = this.ctx.knownNodes.get(canonicalPk) || this.ctx.knownNodes.get(target);
              if (existing) {
                existing.frequency = freq;
                existing.tx_power = tx_power;
                existing.spreading_factor = sf;
                existing.bandwidth = bw;
                existing.coding_rate = cr;
                existing.hop_limit = hop_limit;
                existing.repeat_enabled = repeat;
                existing.advert_interval = beacon_interval;
                if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonicalPk, existing);
              }
            }
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
              this.handleRepeaterAuthError(target, data.message);
            } else {
              if (this.ctx.showToast) this.ctx.showToast(I18n.t('app.error', { error: data.message }), "error");
            }
          }
        } catch (err) {
          this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
        }
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
      ownerPosForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert(I18n.t("repeater.select_repeater"));
          return;
        }
        const password = this.getRepeaterPassword(target);
        const owner_name = document.getElementById("repOwnerName")?.value.trim() || "";
        const owner_info = document.getElementById("repOwnerInfo")?.value.trim() || "";
        const rawLat = document.getElementById("repPosLat")?.value.trim();
        const rawLon = document.getElementById("repPosLon")?.value.trim();
        const rawAlt = document.getElementById("repPosAlt")?.value.trim();
        const lat = rawLat !== undefined && rawLat !== "" && !isNaN(parseFloat(rawLat)) ? parseFloat(rawLat) : null;
        const lon = rawLon !== undefined && rawLon !== "" && !isNaN(parseFloat(rawLon)) ? parseFloat(rawLon) : null;
        const alt = rawAlt !== undefined && rawAlt !== "" && !isNaN(parseFloat(rawAlt)) ? parseFloat(rawAlt) : null;
        const fixed = document.getElementById("repPosFixed")?.checked === true;

        const params = { owner_name, owner_info, lat, lon, alt, fixed, fixed_position: fixed };
        this.appendTerminalLine(I18n.t("repeater.tx_owner", { p0: owner_name, p1: lat ?? '--', p2: lon ?? '--', p3: target.slice(0, 8) }), "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.appendTerminalLine(I18n.t("repeater.rx_owner", { p0: target.slice(0, 8) }), "term-success");
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.rep_pos_ok'), "success");

            if (this.ctx.knownNodes) {
              const canonicalPk = this.resolveCanonicalPubkey(target) || target;
              const existing = this.ctx.knownNodes.get(canonicalPk) || this.ctx.knownNodes.get(target);
              if (existing) {
                if (owner_name) { existing.name = owner_name; existing.alias = owner_name; existing.owner_name = owner_name; }
                if (owner_info) existing.owner_info = owner_info;
                if (lat !== null) existing.latitude = lat;
                if (lon !== null) existing.longitude = lon;
                if (alt !== null) existing.altitude_m = alt;
                existing.fixed_position = fixed;
                existing.fixed = fixed;
              }
              if (this.ctx.renderNodesDirectory) this.ctx.renderNodesDirectory(Array.from(this.ctx.knownNodes.values()));
            }
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
              this.handleRepeaterAuthError(target, data.message);
            } else {
              if (this.ctx.showToast) this.ctx.showToast(I18n.t('app.error', { error: data.message }), "error");
            }
          }
        } catch (err) {
          this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
        }
      });
    }

    // Formulario de Seguridad & ACL
    const securityForm = document.getElementById("repSecurityForm");
    if (securityForm) {
      securityForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert(I18n.t("repeater.select_repeater"));
          return;
        }
        const currentPassword = this.getRepeaterPassword(target);
        const adminPwdInput = document.getElementById("secNewAdminPwd");
        const guestPwdInput = document.getElementById("secNewGuestPwd");
        const aclModeInput = document.getElementById("secAclMode");
        const identityKeyInput = document.getElementById("secIdentityKey");

        const newAdminPwd = adminPwdInput ? adminPwdInput.value.trim() : "";
        const newGuestPwd = guestPwdInput ? guestPwdInput.value.trim() : "";
        const aclMode = aclModeInput ? aclModeInput.value : "public";
        const identityKey = identityKeyInput ? identityKeyInput.value.trim() : "";

        if (!newAdminPwd && !newGuestPwd && !identityKey && !aclMode) {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.no_security_changes"), "info");
          return;
        }

        const params = {};
        if (newAdminPwd) params.new_password = newAdminPwd;
        if (newGuestPwd) params.guest_password = newGuestPwd;
        if (identityKey) params.identity_key = identityKey;
        if (aclMode) params.acl_mode = aclMode;

        this.appendTerminalLine(I18n.t("repeater.tx_security", { p0: target.slice(0, 8) }), "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: currentPassword, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.appendTerminalLine(I18n.t("repeater.rx_security", { p0: target.slice(0, 8) }), "term-success");
            if (newAdminPwd) {
              const canonicalPk = this.resolveCanonicalPubkey(target) || target;
              this.setStoredRepeaterPassword(canonicalPk, newAdminPwd);
              this.setStoredRepeaterPassword(target, newAdminPwd);
              if (this.dom.repeaterGatePassword) this.dom.repeaterGatePassword.value = newAdminPwd;
              this.appendTerminalLine(I18n.t("repeater.cached_credentials", {  }), "term-info");
            }
            if (adminPwdInput) adminPwdInput.value = "";
            if (guestPwdInput) guestPwdInput.value = "";
            if (identityKeyInput) identityKeyInput.value = "";
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.security_applied"), "success");
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            if (this.ctx.showToast) this.ctx.showToast(I18n.t('app.error', { error: data.message || data.error }), "error");
          }
        } catch (err) {
          this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
        }
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
          await this.refreshRepeaterFullTelemetry(target, password);
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.rep_telem_req'), "info");
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
      btnReboot.addEventListener("click", () => {
        const target = this.selectedRepeaterTarget;
        if (!target) return;
        if (confirm(I18n.t("repeater.reboot_confirm", { p0: target.slice(0, 8) }))) {
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

        this._remoteCliHistory.push(cmd);
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

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    this.ctx.eventBus.on(EVENTS.RX_PACKET, (payload) => {
      if (!payload || typeof payload !== "object") return;
      const evType = payload.type || payload.event_type;

      if (evType === "repeater_response" || evType === "repeater_telemetry") {
        const text = payload.text || payload.message || payload.response || "";
        if (text) {
          this.appendTerminalLine(text, "term-resp");
          const parsed = this.parseRepeaterTelemetryFromText(text);
          if (parsed && Object.keys(parsed).length > 0 && this.selectedRepeaterTarget) {
            const canonicalPk = this.resolveCanonicalPubkey(this.selectedRepeaterTarget) || this.selectedRepeaterTarget;
            if (this.ctx.knownNodes) {
              const existing = this.ctx.knownNodes.get(canonicalPk) || {};
              const updated = { ...existing, ...parsed, public_key: canonicalPk };
              this.ctx.knownNodes.set(canonicalPk, updated);
              this.populateRepeaterModalData(updated);
              if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonicalPk, updated);
            }
          }
        }
      }

      // Actualización en vivo del modal de repetidor si llega telemetría o contacto actualizado
      if (this.selectedRepeaterTarget) {
        const canonicalTarget = this.resolveCanonicalPubkey(this.selectedRepeaterTarget) || this.selectedRepeaterTarget;

        if ((evType === "contact_updated" || evType === "contact_discovered") && payload.contact) {
          const c = payload.contact;
          const cPk = this.resolveCanonicalPubkey(c.public_key || c.pubkey || c.sender || "");
          if (cPk && (cPk === canonicalTarget || cPk.startsWith(canonicalTarget.slice(0, 8)) || canonicalTarget.startsWith(cPk.slice(0, 8)))) {
            if (this.ctx.knownNodes) {
              const existing = this.ctx.knownNodes.get(canonicalTarget) || {};
              const updated = { ...existing, ...c, public_key: canonicalTarget };
              this.ctx.knownNodes.set(canonicalTarget, updated);
              this.populateRepeaterModalData(updated);
            }
          }
        } else if (evType === "telemetry" || evType === "stats" || evType === "STATS") {
          const sender = payload.sender || payload.pubkey || payload.from;
          if (sender) {
            const sPk = this.resolveCanonicalPubkey(sender);
            if (sPk && (sPk === canonicalTarget || sPk.startsWith(canonicalTarget.slice(0, 8)) || canonicalTarget.startsWith(sPk.slice(0, 8)))) {
              if (this.ctx.knownNodes) {
                const existing = this.ctx.knownNodes.get(canonicalTarget) || {};
                const updated = { ...existing, ...payload, public_key: canonicalTarget };
                this.ctx.knownNodes.set(canonicalTarget, updated);
                this.populateRepeaterModalData(updated);
              }
            }
          }
        } else {
          const c = payload.contact || payload.data || payload;
          const pk = c.public_key || c.sender || c.from || payload.sender || payload.from;
          if (pk) {
            const cPk = this.resolveCanonicalPubkey(pk);
            if (cPk && (cPk === canonicalTarget || cPk.startsWith(canonicalTarget.slice(0, 8)) || canonicalTarget.startsWith(cPk.slice(0, 8)))) {
              if (this.ctx.knownNodes) {
                const existing = this.ctx.knownNodes.get(canonicalTarget) || {};
                const updated = { ...existing, ...c, ...payload, public_key: canonicalTarget };
                this.ctx.knownNodes.set(canonicalTarget, updated);
                this.populateRepeaterModalData(updated);
              }
            }
          }
        }
      }
    });
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
      (this.dom.repeaterGatePassword ? this.dom.repeaterGatePassword.value.trim() : "");
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
      this.handleRepeaterAuthError(canonicalPk, I18n.t("repeater.connection_error", { p0: err.message }));
      return false;
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span class="btn-icon">🔐</span> ${I18n.t('repeater.unlock')}`;
        I18n.setText(submitBtn, 'repeater.unlock');
      }
    }
  }

  async refreshRepeaterFullTelemetry(canonicalPk, password) {
    if (!canonicalPk || !password) return;
    try {
      const res = await fetch("/api/repeater/remote/action", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: canonicalPk, password: password, action: "refresh_telemetry" }),
      });
      const data = await res.json();
      if (data.status === "ok") {
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
      } else if (data.status === "error" && data.cooldown_remaining) {
        this.appendTerminalLine(I18n.t("repeater.telemetry_cooldown", { p0: data.cooldown_remaining }), "term-resp");
      }
    } catch (err) {
      console.warn("Error en refreshRepeaterFullTelemetry:", err);
    }
  }

  calculateBatteryPct(val) {
    if (val == null || isNaN(val)) return null;
    const v = Number(val);
    const volt = v > 100 ? v / 1000 : v;
    if (volt >= 4.8) return 100;
    if (volt <= 3.0) return 0;
    return Math.max(0, Math.min(100, Math.round(((volt - 3.0) / 1.2) * 100)));
  }

  parseRepeaterTelemetryFromText(text) {
    if (!text || typeof text !== "string") return {};
    const extracted = {};
    const clean = text.trim();

    // 1. Batería & Voltaje
    const batM = clean.match(/(?:battery|batt|bat|pwrmgt\.bootmv|boot\s+voltage|bootmv)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mv|v|%)?(?:\s*\((?:(\d+)\s*%)?\))?/i)
      || clean.match(/(?:^|>)\s*(\d{3,4})\s*(?:mv)?(?:\s*\((?:(\d+)\s*%)?\))?$/i)
      || clean.match(/(?:^|>)\s*([34]\.\d{1,3})\s*(?:v)?$/i)
      || clean.match(/(?:^|>)\s*(\d{1,2}|100)\s*%$/i);

    if (batM) {
      const rawVal = parseFloat(batM[1]);
      const pctParen = batM[2] ? parseInt(batM[2], 10) : null;
      if (!isNaN(rawVal)) {
        if (batM[0].includes("%") || (rawVal <= 100 && rawVal > 4.5)) {
          extracted.battery_pct = Math.round(rawVal);
        } else if (rawVal > 100) {
          extracted.voltage_v = Number((rawVal / 1000).toFixed(2));
          extracted.battery_pct = pctParen !== null ? pctParen : this.calculateBatteryPct(rawVal);
        } else {
          extracted.voltage_v = Number(rawVal.toFixed(2));
          extracted.battery_pct = pctParen !== null ? pctParen : this.calculateBatteryPct(rawVal);
        }
      }
    }

    // Voltaje explícito
    if (extracted.voltage_v == null) {
      const voltM = clean.match(/(?:voltage|volt|vbat|v_bat)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(?:mv|v)?/i);
      if (voltM) {
        const vNum = parseFloat(voltM[1]);
        if (!isNaN(vNum)) {
          extracted.voltage_v = vNum > 100 ? Number((vNum / 1000).toFixed(2)) : Number(vNum.toFixed(2));
          if (extracted.battery_pct == null) {
            extracted.battery_pct = this.calculateBatteryPct(extracted.voltage_v);
          }
        }
      }
    }

    // Solar
    const solM = clean.match(/(?:solar(?:_v)?|vin|v_in|vsolar|input(?:_v)?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*v?/i);
    if (solM) {
      const sNum = parseFloat(solM[1]);
      if (!isNaN(sNum)) extracted.solar_v = Number(sNum.toFixed(2));
    }

    // Radio: > 915.000,250,11,5
    const radM = clean.match(/(?:^|>)\s*(\d{3}(?:\.\d+)?)\s*,\s*(\d+(?:\.\d+)?)\s*,\s*(\d+)\s*,\s*(\d+)/);
    if (radM) {
      extracted.frequency = parseFloat(radM[1]);
      extracted.bandwidth = parseFloat(radM[2]);
      extracted.spreading_factor = parseInt(radM[3], 10);
      extracted.coding_rate = `4/${radM[4]}`;
    }

    // Uptime
    const upM = clean.match(/(?:uptime|up)\s*[:=]?\s*([0-9a-zA-Z\s]+?)(?:,|$|\n)/i);
    if (upM) extracted.uptime = upM[1].trim();

    // Clock
    let clkM = clean.match(/(?:clock|rtc|time)(?:\s*set)?\s*[:=]?\s*([0-9\-:\s\/]+(?:[ap]m|utc)?)/i);
    if (!clkM || !clkM[1].trim()) {
      clkM = clean.match(/(?:^|>)\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*-\s*\d{1,2}\/\d{1,2}\/\d{2,4})?(?:\s*(?:UTC|[ap]m))?)/i);
    }
    if (!clkM || !clkM[1].trim()) {
      clkM = clean.match(/(?:^|>)\s*([0-9\-:\s\/]+UTC)/i);
    }
    if (clkM && clkM[1].trim()) extracted.clock = clkM[1].trim();

    // Duty Cycle
    let dutyM = clean.match(/(?:duty(?:cycle)?)\s*[:=]?\s*(\d+(?:\.\d+)?)\s*%/i);
    if (!dutyM) {
      dutyM = clean.match(/(?:^|>)\s*(\d+(?:\.\d+)?)\s*%/);
    }
    if (dutyM) extracted.duty_cycle_pct = parseFloat(dutyM[1]);

    // Noise Floor
    const noiseM = clean.match(/(?:noise(?:\s*floor)?|noisefloor|floor)\s*[:=]?\s*(-?\d+(?:\.\d+)?)\s*(?:dbm)?/i);
    if (noiseM) extracted.noise_floor_dbm = parseInt(noiseM[1], 10);

    // Airtime
    const atM = clean.match(/(?:total\s+)?airtime\s*[:=]?\s*(\d+(?:\.\d+)?)\s*(ms|s)?/i);
    if (atM) {
      const v = parseFloat(atM[1]);
      extracted.airtime_ms = (atM[2] || "").toLowerCase() === "s" ? Math.round(v * 1000) : Math.round(v);
    }

    // Packets rx, tx
    const pktM = clean.match(/packets:\s*rx=(\d+),\s*tx=(\d+)(?:,\s*routed=(\d+))?(?:,\s*(?:drop|err|errors?)=(\d+))?/i);
    if (pktM) {
      extracted.packets_recv = parseInt(pktM[1], 10);
      extracted.packets_sent = parseInt(pktM[2], 10);
      if (pktM[4]) extracted.packet_errors = parseInt(pktM[4], 10);
    }

    // TX Power
    const pwrM = clean.match(/(?:tx_?power|power)\s*[:=]?\s*(\d+)\s*(?:dbm)?/i) || clean.match(/^>\s*(\d{1,2})\s*(?:dbm)?$/);
    if (pwrM) {
      const p = parseInt(pwrM[1], 10);
      if (p <= 33) extracted.tx_power = p;
    }

    // Lat / Lon
    const latM = clean.match(/lat(?:itude)?\s*[:=]?\s*(-?\d+\.\d+)/i) || clean.match(/^>\s*(-?\d{1,2}\.\d{3,7})$/);
    if (latM) extracted.latitude = parseFloat(latM[1]);

    const lonM = clean.match(/lon(?:gitude)?\s*[:=]?\s*(-?\d+\.\d+)/i);
    if (lonM) extracted.longitude = parseFloat(lonM[1]);

    return extracted;
  }

  openRepeaterAdminModal(pubkey, name) {
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
  }

  populateRepeaterModalData(node) {
    const pubkey = node.public_key || this.selectedRepeaterTarget;

    let calcBat = node.battery_pct != null ? Number(node.battery_pct) : (node.battery != null ? Number(node.battery) : (node.batt != null ? Number(node.batt) : null));
    let calcVolt = node.voltage_v != null ? Number(node.voltage_v) : (node.voltage != null ? Number(node.voltage) : (node.battery_mv ? Number(node.battery_mv) / 1000 : null));

    if (calcVolt != null && calcVolt > 100) {
      calcVolt = Number((calcVolt / 1000).toFixed(2));
    }

    if (calcVolt != null && calcVolt >= 2.5 && calcVolt <= 4.5) {
      calcBat = this.calculateBatteryPct(calcVolt);
    } else if (calcBat != null && calcBat > 100) {
      if (calcVolt == null) calcVolt = Number((calcBat / 1000).toFixed(2));
      calcBat = this.calculateBatteryPct(calcBat);
    } else if (calcBat == null && calcVolt != null && calcVolt >= 2.5) {
      calcBat = this.calculateBatteryPct(calcVolt);
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
    if (sumFreq) sumFreq.textContent = node.frequency != null ? `${node.frequency} MHz` : (node.freq != null ? `${node.freq} MHz` : "915.000 MHz");
    const sumPower = document.getElementById("repSummaryPower");
    if (sumPower) sumPower.textContent = node.tx_power != null ? `${node.tx_power} dBm` : (node.power != null ? `${node.power} dBm` : "20 dBm");
    const sumModem = document.getElementById("repSummaryModem");
    const sfVal = node.spreading_factor != null ? node.spreading_factor : (node.sf != null ? node.sf : 11);
    const bwVal = node.bandwidth != null ? node.bandwidth : (node.bw != null ? node.bw : 250);
    if (sumModem) sumModem.textContent = `SF${sfVal} / BW${bwVal}`;

    const isRep = node.repeat_enabled !== undefined && node.repeat_enabled !== null
      ? Boolean(node.repeat_enabled)
      : (node.repeat !== undefined && node.repeat !== null
          ? Boolean(node.repeat)
          : (String(node.role || "").toUpperCase() === "REPEATER" || node.is_repeater === true || node.advert_type === 2 || String(node.raw_role || "").toUpperCase() === "REPEATER"));

    const repHopLimit = node.hop_limit != null ? node.hop_limit : (node.default_hop_limit != null ? node.default_hop_limit : (node.hopLimit != null ? node.hopLimit : 3));

    const sumHopLimit = document.getElementById("repSummaryHopLimit");
    if (sumHopLimit) I18n.setText(sumHopLimit, "repeater.hop_limit", { p0: repHopLimit });

    const sumRepeat = document.getElementById("repSummaryRepeat");
    if (sumRepeat) I18n.setText(sumRepeat, isRep ? "repeater.enabled" : "repeater.disabled");

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

    const radioFreqInput = document.getElementById("radioFreq");
    const repFreq = node.frequency != null ? node.frequency : node.freq;
    if (radioFreqInput && repFreq != null) {
      const numF = parseFloat(repFreq);
      radioFreqInput.value = !isNaN(numF) ? numF.toFixed(3) : String(repFreq);
    }
    const radioRegionInput = document.getElementById("radioRegion");
    if (radioRegionInput) {
      if (node.region) {
        radioRegionInput.value = node.region;
      } else if (repFreq != null) {
        const f = parseFloat(repFreq);
        if (f >= 863.0 && f < 865.0) radioRegionInput.value = "RU864";
        else if (f >= 865.0 && f < 867.0) radioRegionInput.value = "IN865";
        else if (f >= 867.0 && f <= 870.0) radioRegionInput.value = "EU868";
        else if (f >= 920.0 && f <= 925.0) radioRegionInput.value = "AS923";
        else if (f >= 902.0 && f <= 928.0) radioRegionInput.value = "US915";
      }
    }
    const radioPowerInput = document.getElementById("radioPower");
    const radioPowerVal = document.getElementById("radioPowerVal");
    const pLimits = getHardwarePowerLimits(node);
    const rawPower = node.tx_power != null ? node.tx_power : (node.power != null ? node.power : pLimits.def);
    const clampedPower = Math.max(pLimits.min, Math.min(pLimits.max, parseInt(rawPower, 10) || pLimits.def));
    if (radioPowerInput) {
      radioPowerInput.min = String(pLimits.min);
      radioPowerInput.max = String(pLimits.max);
      radioPowerInput.value = String(clampedPower);
    }
    if (radioPowerVal) {
      radioPowerVal.textContent = `${clampedPower} dBm`;
    }
    const radioHopLimitInput = document.getElementById("radioHopLimit");
    if (radioHopLimitInput) {
      radioHopLimitInput.value = String(repHopLimit);
    }
    const radioBeaconInput = document.getElementById("radioBeaconInterval");
    if (radioBeaconInput && (node.advert_interval != null || node.beacon_interval != null)) {
      radioBeaconInput.value = node.advert_interval != null ? node.advert_interval : node.beacon_interval;
    }
    const radioSf = document.getElementById("radioSf");
    if (radioSf && (node.spreading_factor != null || node.sf != null)) {
      let rawSf = String(node.spreading_factor != null ? node.spreading_factor : node.sf).toUpperCase().replace("SF", "").trim();
      radioSf.value = rawSf;
    }
    const radioBw = document.getElementById("radioBw");
    if (radioBw && (node.bandwidth != null || node.bw != null)) {
      let rawBw = parseFloat(node.bandwidth != null ? node.bandwidth : node.bw);
      if (rawBw > 1000) rawBw = rawBw / 1000.0;
      const bwStr = String(rawBw);
      const supportedBws = ["7.8", "10.4", "15.6", "20.8", "31.25", "41.7", "62.5", "125", "250", "500"];
      const found = supportedBws.find((opt) => parseFloat(opt) === rawBw);
      radioBw.value = found || bwStr;
    }
    const radioCr = document.getElementById("radioCr");
    if (radioCr && (node.coding_rate != null || node.cr != null)) {
      let rawCr = String(node.coding_rate != null ? node.coding_rate : node.cr).trim();
      if (["5", "6", "7", "8"].includes(rawCr)) rawCr = `4/${rawCr}`;
      if (["4/5", "4/6", "4/7", "4/8"].includes(rawCr)) {
        radioCr.value = rawCr;
      }
    }
    const radioRepeatMode = document.getElementById("radioRepeatMode");
    const radioRepBadge = document.getElementById("radioRepeatBadge");
    if (radioRepeatMode) {
      radioRepeatMode.checked = isRep;
      if (radioRepBadge) {
        I18n.setText(radioRepBadge, isRep ? 'common.on' : 'common.off');
        radioRepBadge.className = isRep ? "toggle-state-badge is-active-purple" : "toggle-state-badge";
      }
    }

    const ownerNameInput = document.getElementById("repOwnerName");
    if (ownerNameInput) ownerNameInput.value = node.owner_name || node.alias || node.name || "";
    const ownerInfoInput = document.getElementById("repOwnerInfo");
    if (ownerInfoInput) ownerInfoInput.value = node.owner_info || "";

    const extractNum = (...keys) => {
      for (const k of keys) {
        if (k !== undefined && k !== null && k !== "") {
          const num = parseFloat(k);
          if (!isNaN(num)) return num;
        }
      }
      return "";
    };

    const posLatInput = document.getElementById("repPosLat");
    if (posLatInput) posLatInput.value = extractNum(node.latitude, node.lat, node.gps_lat, node.gps?.latitude, node.position?.latitude);
    const posLonInput = document.getElementById("repPosLon");
    if (posLonInput) posLonInput.value = extractNum(node.longitude, node.lon, node.gps_lon, node.gps?.longitude, node.position?.longitude);
    const posAltInput = document.getElementById("repPosAlt");
    if (posAltInput) posAltInput.value = extractNum(node.altitude_m, node.alt, node.altitude, node.gps?.altitude);
    const posFixed = document.getElementById("repPosFixed");
    const posFixedBadge = document.getElementById("repPosFixedBadge");
    if (posFixed) {
      const isFixed = (node.fixed_position !== undefined && node.fixed_position !== null)
        ? Boolean(node.fixed_position)
        : (node.fixed !== undefined && node.fixed !== null
            ? Boolean(node.fixed)
            : (node.latitude !== undefined && node.latitude !== null && node.latitude !== 0));
      posFixed.checked = isFixed;
      if (posFixedBadge) {
        I18n.setText(posFixedBadge, isFixed ? "repeater.fixed" : "repeater.dynamic_gps");
        posFixedBadge.className = isFixed ? "toggle-state-badge is-active" : "toggle-state-badge";
      }
    }
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

    if (this.selectedRepeaterTarget) {
      const parsed = this.parseRepeaterTelemetryFromText(strText);
      if (parsed && Object.keys(parsed).length > 0 && this.ctx.knownNodes) {
        const canonicalPk = this.resolveCanonicalPubkey(this.selectedRepeaterTarget) || this.selectedRepeaterTarget;
        const existing = this.ctx.knownNodes.get(canonicalPk) || {};
        const updated = { ...existing, ...parsed, public_key: canonicalPk };
        this.ctx.knownNodes.set(canonicalPk, updated);
        this.populateRepeaterModalData(updated);
        if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(canonicalPk, updated);
      }
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

      if (data.status === "ok" && data.data) {
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

        if (this.ctx.showToast) this.ctx.showToast(`🎯 Pong: ${rtt} ms | SNR: ${snrBack} | RSSI: ${rssi}`, "success");
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
    const pwd = password || this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(`repeater> ${action}`, "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/action", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, action, params, password: pwd }),
      });
      const data = await res.json();
      const qFeedback = document.getElementById("repQuickCmdFeedback");
      if (data.status === "ok") {
        const payload = data.data || data;
        const respTxt = payload.text || payload.response || payload.message || "";
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
          const parsed = { ...(payload.telemetry || {}), ...this.parseRepeaterTelemetryFromText(cleanTxt) };
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
          qFeedback.className = "rep-quick-feedback success";
          I18n.setText(qFeedback, "repeater.command_sent", { p0: target.slice(0, 8) });
          setTimeout(() => {
            if (qFeedback && qFeedback.classList.contains("success")) qFeedback.classList.add("hidden");
          }, 5000);
        }
      } else {
        const errMsg = data.detail || data.message || data.error || I18n.t("repeater.unknown_error");
        this.appendTerminalLine(I18n.t('repeater.command_error', { p0: errMsg }), "term-error");
        if (qFeedback) {
          qFeedback.className = "rep-quick-feedback error";
          qFeedback.textContent = `✗ ${errMsg}`;
        }
        if (errMsg && (errMsg.toLowerCase().includes("password") || errMsg.toLowerCase().includes("auth") || errMsg.toLowerCase().includes("pin"))) {
          this.handleRepeaterAuthError(target, errMsg);
        }
      }
    } catch (err) {
      this.appendTerminalLine(I18n.t("repeater.command_network_error", { p0: err.message }), "term-error");
      const qFeedback = document.getElementById("repQuickCmdFeedback");
      if (qFeedback) {
        qFeedback.className = "rep-quick-feedback error";
        I18n.setText(qFeedback, "repeater.command_network_error", { p0: err.message });
      }
    }
  }

  async fetchRepeaterNeighbors(target) {
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
      if (data.status === "ok") {
        const neighbours = data.data?.neighbours || data.neighbours || [];
        this.renderNeighborsTable(neighbours);
        const countBadge = document.getElementById("neighborsCountBadge");
        if (countBadge) I18n.setText(countBadge, "repeater.neighbor_count", { p0: neighbours.length });
        this.appendTerminalLine(I18n.t("repeater.rx_neighbors", { p0: neighbours.length }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.neighbors_detected", { p0: neighbours.length }), "success");
      } else {
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">${escapeHtml(data.message || I18n.t("repeater.query_failed"))}</td></tr>`;
        this.appendTerminalLine(`✗ [ERROR] ${data.message || data.error}`, "term-error");
      }
    } catch (err) {
      if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">${escapeHtml(err.message)}</td></tr>`;
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = `<span data-lucide="wifi" data-size="14"></span> ${I18n.t('repeater.discover_neighbors')}`;
        I18n.setText(btn, 'repeater.discover_neighbors');
      }
      if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
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
          <button type="button" class="btn-secondary btn-xs btn-neighbor-ping" data-target="${escapeHtml(pk)}" title="${I18n.t('repeater.direct_ping')}">
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
    const pwd = this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(I18n.t("repeater.tx_owner_query", { p0: target.slice(0, 8) }), "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/owner", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: pwd }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const ownerName = data.data?.owner_name || data.owner_name || "";
        const ownerInfo = data.data?.owner_info || data.owner_info || "";
        const nameEl = document.getElementById("repOwnerName");
        const infoEl = document.getElementById("repOwnerInfo");
        if (nameEl && ownerName) nameEl.value = ownerName;
        if (infoEl && ownerInfo) infoEl.value = ownerInfo;
        this.appendTerminalLine(I18n.t("repeater.owner_details", { p0: ownerName, p1: ownerInfo }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.owner_received", { p0: ownerName || "OK" }), "success");
      } else {
        this.appendTerminalLine(`✗ [ERROR] ${data.message || data.error}`, "term-error");
      }
    } catch (err) {
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    }
  }

  async fetchRepeaterRegions(target) {
    const pwd = this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(I18n.t("repeater.tx_regions", { p0: target.slice(0, 8) }), "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/regions", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: pwd }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const regions = JSON.stringify(data.data?.regions || data.regions || []);
        this.appendTerminalLine(I18n.t("repeater.rx_regions", { p0: regions }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("repeater.regions", { p0: regions }), "info");
      } else {
        this.appendTerminalLine(`✗ [ERROR] ${data.message || data.error}`, "term-error");
      }
    } catch (err) {
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    }
  }

  async fetchRepeaterAcl(target) {
    const pwd = this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(I18n.t("repeater.tx_acl", { p0: target.slice(0, 8) }), "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/acl", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, password: pwd }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        const aclData = JSON.stringify(data.data?.acl_data || data.acl_data || {});
        this.appendTerminalLine(I18n.t("repeater.rx_acl", { p0: aclData }), "term-success");
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('repeater.acl_received'), "success");
      } else {
        this.appendTerminalLine(`✗ [ERROR] ${data.message || data.error}`, "term-error");
      }
    } catch (err) {
      this.appendTerminalLine(`✗ [ERROR] ${err.message}`, "term-error");
    }
  }
}

