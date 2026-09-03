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
          this.clearStoredRepeaterPassword(target);
          this.lockRepeaterAdminView(target);
          if (repeaterGatePassword) {
            repeaterGatePassword.value = "";
            repeaterGatePassword.focus();
          }
          if (this.ctx.showToast) this.ctx.showToast("🔒 Sesión de administración cerrada para este repetidor", "info");
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
      });
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
    document.querySelectorAll(".help-cmd-item").forEach((item) => {
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
          alert("Selecciona primero un repetidor.");
          return;
        }
        if (!password) {
          alert("Ingresa la contraseña o PIN de administración del repetidor.");
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
        repBadge.textContent = isChecked ? "ON" : "OFF";
        repBadge.className = isChecked ? "toggle-state-badge is-active-purple" : "toggle-state-badge";
      });
    }

    if (radioForm) {
      radioForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert("Selecciona primero un repetidor objetivo.");
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
        this.appendTerminalLine(`> [TX CONFIG] Transmitiendo parámetros RF a ${target.slice(0, 8)} (${freq}MHz, ${tx_power}dBm, SF${sf}, BW${bw}kHz)...`, "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.appendTerminalLine(`✓ [RX OK] Parámetros RF aplicados al repetidor ${target.slice(0, 8)}.`, "term-success");
            if (this.ctx.showToast) this.ctx.showToast("📻 Configuración RF transmitida al repetidor", "success");

            const sFreq = document.getElementById("repSummaryFreq");
            if (sFreq) sFreq.textContent = `${freq.toFixed(3)} MHz`;
            const sPower = document.getElementById("repSummaryPower");
            if (sPower) sPower.textContent = `${tx_power} dBm`;
            const sModem = document.getElementById("repSummaryModem");
            if (sModem) sModem.textContent = `SF${sf} / BW${bw}`;
            const sHop = document.getElementById("repSummaryHopLimit");
            if (sHop) sHop.textContent = `${hop_limit} saltos`;
            const sRep = document.getElementById("repSummaryRepeat");
            if (sRep) sRep.textContent = repeat ? "Activado" : "Desactivado";

            if (this.ctx.knownNodes) {
              const existing = this.ctx.knownNodes.get(target);
              if (existing) {
                existing.frequency = freq;
                existing.tx_power = tx_power;
                existing.spreading_factor = sf;
                existing.bandwidth = bw;
                existing.coding_rate = cr;
                existing.hop_limit = hop_limit;
                existing.repeat_enabled = repeat;
                existing.advert_interval = beacon_interval;
                if (this.ctx.updateNodeInDom) this.ctx.updateNodeInDom(existing);
              }
            }
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
              this.handleRepeaterAuthError(target, data.message);
            } else {
              if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message}`, "error");
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
        posFixedBadge.textContent = isChecked ? "FIJA" : "GPS DINÁMICO";
        posFixedBadge.className = isChecked ? "toggle-state-badge is-active" : "toggle-state-badge";
      });
    }

    if (ownerPosForm) {
      ownerPosForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const target = this.selectedRepeaterTarget;
        if (!target) {
          alert("Selecciona primero un repetidor.");
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

        const params = { owner_name, owner_info, lat, lon, alt, fixed };
        this.appendTerminalLine(`> [TX OWNER/POS] Configurando propietario '${owner_name}' y posición (${lat ?? '--'}, ${lon ?? '--'}) en ${target.slice(0, 8)}...`, "term-cmd");

        try {
          const res = await fetch("/api/repeater/remote/config", {
            method: "POST",
            headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
            body: JSON.stringify({ target_node: target, password: password, params: params }),
          });
          const data = await res.json();
          if (data.status === "ok") {
            this.appendTerminalLine(`✓ [RX OK] Información y coordenadas guardadas en repetidor ${target.slice(0, 8)}.`, "term-success");
            if (this.ctx.showToast) this.ctx.showToast("📍 Información y posición aplicadas al repetidor", "success");

            if (this.ctx.knownNodes) {
              const existing = this.ctx.knownNodes.get(target);
              if (existing) {
                if (owner_name) { existing.name = owner_name; existing.alias = owner_name; existing.owner_name = owner_name; }
                if (owner_info) existing.owner_info = owner_info;
                if (lat !== null) existing.latitude = lat;
                if (lon !== null) existing.longitude = lon;
                if (alt !== null) existing.altitude_m = alt;
                existing.fixed_position = fixed;
              }
              if (this.ctx.renderNodesDirectory) this.ctx.renderNodesDirectory(Array.from(this.ctx.knownNodes.values()));
            }
          } else {
            this.appendTerminalLine(`✗ [RX ERROR] ${data.message || data.error}`, "term-error");
            if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
              this.handleRepeaterAuthError(target, data.message);
            } else {
              if (this.ctx.showToast) this.ctx.showToast(`Error: ${data.message}`, "error");
            }
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
        this.appendTerminalLine(`> [TX] Solicitando telemetría completa, batería y parámetros a ${target.slice(0, 8)}...`, "term-cmd");
        btnRefreshTelem.disabled = true;
        btnRefreshTelem.textContent = "🔄 Consultando...";
        try {
          this.refreshRepeaterFullTelemetry(target, password);
          if (this.ctx.showToast) this.ctx.showToast("📡 Consultando telemetría, batería y estado al repetidor por RF...", "info");
        } catch (_) {}
        finally {
          setTimeout(() => {
            btnRefreshTelem.disabled = false;
            btnRefreshTelem.textContent = "🔄 Consultar Parámetros";
          }, 3500);
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
        if (confirm(`¿Confirmas el reinicio remoto por RF del repetidor ${target.slice(0, 8)}?`)) {
          const password = this.getRepeaterPassword(target);
          this.executeRepeaterCommand(target, "reboot", {}, password);
        }
      });
    }

    document.querySelectorAll(".rep-quick-cmd").forEach((btn) => {
      btn.addEventListener("click", () => {
        const cmd = btn.getAttribute("data-cmd");
        const target = this.selectedRepeaterTarget;
        if (!target) {
          this.appendTerminalLine("⚠️ Selecciona primero un repetidor objetivo.", "term-error");
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

    if (repeaterTerminalForm) {
      repeaterTerminalForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const cmd = repeaterTerminalInput ? repeaterTerminalInput.value.trim() : "";
        const target = this.selectedRepeaterTarget;
        if (!cmd) return;
        if (!target) {
          this.appendTerminalLine("⚠️ Selecciona primero un repetidor objetivo.", "term-error");
          return;
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
      return sessionStorage.getItem(`rep_pwd_${pubkey.toLowerCase()}`) || "";
    } catch (_) {
      return "";
    }
  }

  setStoredRepeaterPassword(pubkey, pwd) {
    if (!pubkey || !pwd) return;
    try {
      sessionStorage.setItem(`rep_pwd_${pubkey.toLowerCase()}`, pwd);
      this.repeaterPasswords.set(pubkey.toLowerCase(), pwd);
    } catch (_) {}
  }

  clearStoredRepeaterPassword(pubkey) {
    if (!pubkey) return;
    try {
      sessionStorage.removeItem(`rep_pwd_${pubkey.toLowerCase()}`);
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
        statusEl.textContent = errorMessage;
        statusEl.classList.remove("hidden");
      } else {
        statusEl.className = "auth-gate-status hidden";
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
      submitBtn.innerHTML = '<span class="btn-icon">🔐</span> Desbloquear & Autenticar Repetidor';
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
      authStatus.textContent = "🔓 Autenticado";
    }

    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    if (statusEl) {
      statusEl.className = "auth-gate-status hidden";
      statusEl.textContent = "";
    }
  }

  handleRepeaterAuthError(pubkey, message = "Contraseña incorrecta o cambiada en el repetidor") {
    if (this.ctx.showToast) this.ctx.showToast(message, "error");
    this.clearStoredRepeaterPassword(pubkey);
    this.lockRepeaterAdminView(pubkey, `⚠️ ${message}`);
  }

  async authenticateRepeater(pubkey, password) {
    if (!pubkey || !password) {
      this.handleRepeaterAuthError(pubkey, "Ingresa la contraseña de administración.");
      return false;
    }

    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    const statusEl = this.dom.repeaterGateStatus || document.getElementById("repeaterGateStatus");
    const submitBtn = this.dom.btnRepeaterGateSubmit || document.getElementById("btnRepeaterGateSubmit");

    if (statusEl) {
      statusEl.className = "auth-gate-status loading";
      statusEl.textContent = "⏳ Verificando credenciales con el repetidor por RF...";
      statusEl.classList.remove("hidden");
    }
    if (submitBtn) {
      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="btn-icon">⏳</span> Verificando...';
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
        if (this.ctx.showToast) this.ctx.showToast("🔓 Repetidor autenticado con éxito", "success");

        this.refreshRepeaterFullTelemetry(canonicalPk, password);
        return true;
      } else {
        const errorDetail = data.message || data.data?.message || "Contraseña incorrecta o el repetidor no respondió";
        this.handleRepeaterAuthError(canonicalPk, errorDetail);
        return false;
      }
    } catch (err) {
      this.handleRepeaterAuthError(canonicalPk, `Error de conexión: ${err.message}`);
      return false;
    } finally {
      if (submitBtn) {
        submitBtn.disabled = false;
        submitBtn.innerHTML = '<span class="btn-icon">🔐</span> Desbloquear & Autenticar Repetidor';
      }
    }
  }

  refreshRepeaterFullTelemetry(canonicalPk, password) {
    if (!canonicalPk || !password) return;
    const fetchAction = (act) => fetch("/api/repeater/remote/action", {
      method: "POST",
      headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
      body: JSON.stringify({ target_node: canonicalPk, password: password, action: act }),
    }).catch(() => {});

    fetchAction("ver");
    setTimeout(() => fetchAction("stats-core"), 350);
    setTimeout(() => fetchAction("bat"), 700);
    setTimeout(() => fetchAction("get radio"), 1050);
    setTimeout(() => fetchAction("get tx"), 1400);
    setTimeout(() => fetchAction("get lat"), 1750);
    setTimeout(() => fetchAction("get lon"), 2100);
    setTimeout(() => fetchAction("get owner.info"), 2450);
    setTimeout(() => fetchAction("clock"), 2800);
    setTimeout(() => fetchAction("neighbors"), 3150);
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
          extracted.battery_pct = pctParen !== null ? pctParen : Math.max(0, Math.min(100, Math.round((rawVal - 3300) / (4200 - 3300) * 100)));
        } else {
          extracted.voltage_v = Number(rawVal.toFixed(2));
          extracted.battery_pct = pctParen !== null ? pctParen : Math.max(0, Math.min(100, Math.round((rawVal - 3.3) / (4.2 - 3.3) * 100)));
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
            extracted.battery_pct = Math.max(0, Math.min(100, Math.round((extracted.voltage_v - 3.3) / (4.2 - 3.3) * 100)));
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
    const clkM = clean.match(/(?:clock|rtc|time)\s*[:=]?\s*([0-9\-:\s]+(?:[ap]m)?)/i);
    if (clkM) extracted.clock = clkM[1].trim();

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

  populateRepeaterModalData(node) {
    const pubkey = node.public_key || this.selectedRepeaterTarget;

    let calcBat = node.battery_pct != null ? Number(node.battery_pct) : (node.battery != null ? Number(node.battery) : (node.batt != null ? Number(node.batt) : null));
    let calcVolt = node.voltage_v != null ? Number(node.voltage_v) : (node.voltage != null ? Number(node.voltage) : (node.battery_mv ? Number(node.battery_mv) / 1000 : null));

    if (calcBat != null && calcBat > 100) {
      if (calcVolt == null) calcVolt = Number((calcBat / 1000).toFixed(2));
      calcBat = Math.max(0, Math.min(100, Math.round((calcBat - 3300) / (4200 - 3300) * 100)));
    } else if (calcBat == null && calcVolt != null && calcVolt >= 2.5) {
      const vNorm = calcVolt > 100 ? calcVolt / 1000 : calcVolt;
      calcBat = Math.max(0, Math.min(100, Math.round((vNorm - 3.3) / (4.2 - 3.3) * 100)));
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

    const clockEl = document.getElementById("repClockValue");
    if (clockEl) clockEl.textContent = node.clock || new Date().toLocaleTimeString();
    const uptimeEl = document.getElementById("repUptimeValue");
    if (uptimeEl) uptimeEl.textContent = node.uptime || "En línea";
    const seenEl = document.getElementById("repLastSeenValue");
    if (seenEl) seenEl.textContent = "Activo en malla LoRa";

    const airtimeVal = node.airtime_ms != null ? node.airtime_ms : (node.airtime != null ? node.airtime : null);
    const airtimeEl = document.getElementById("repAirtimeValue");
    if (airtimeEl) airtimeEl.textContent = airtimeVal != null ? `${airtimeVal} ms` : "-- ms";
    const airtimeDutyEl = document.getElementById("repAirtimeDuty");
    if (airtimeDutyEl) airtimeDutyEl.textContent = airtimeVal != null ? `Duty: ${(airtimeVal / 36000).toFixed(2)}%` : "Duty Cycle: --%";

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
      pktsErrEl.textContent = `Duplicados: ${dStr} | Errores: ${eStr}`;
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
    if (sumHopLimit) sumHopLimit.textContent = `${repHopLimit} saltos`;

    const sumRepeat = document.getElementById("repSummaryRepeat");
    if (sumRepeat) sumRepeat.textContent = isRep ? "Activado" : "Desactivado";

    const sumQueue = document.getElementById("repSummaryQueue");
    if (sumQueue) sumQueue.textContent = `${node.queue_len != null ? node.queue_len : (node.tx_queue_len != null ? node.tx_queue_len : 0)} paquetes`;

    const sumPos = document.getElementById("repSummaryPos");
    if (sumPos) {
      if (node.latitude != null && node.longitude != null) {
        sumPos.textContent = `${Number(node.latitude).toFixed(4)}, ${Number(node.longitude).toFixed(4)}`;
      } else {
        sumPos.textContent = "No configurada";
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
      const bwStr = String(Math.round(rawBw));
      if (["125", "250", "500"].includes(bwStr)) {
        radioBw.value = bwStr;
      }
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
        radioRepBadge.textContent = isRep ? "ON" : "OFF";
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
      const isFixed = node.fixed_position !== undefined ? Boolean(node.fixed_position) : true;
      posFixed.checked = isFixed;
      if (posFixedBadge) {
        posFixedBadge.textContent = isFixed ? "FIJA" : "GPS DINÁMICO";
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
    const name = targetName || this.selectedRepeaterName || (target ? target.slice(0, 8) : "desconocido");
    if (!target) {
      if (this.ctx.showToast) this.ctx.showToast("⚠️ Selecciona un repetidor o nodo objetivo", "warning");
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
      if (this.ctx.showToast) this.ctx.showToast("No se puede hacer ping a la estación base local", "warning");
      return;
    }

    if (this.ctx.knownNodes && this.ctx.knownNodes.has(target)) {
      const nodeInfo = this.ctx.knownNodes.get(target);
      if (nodeInfo && nodeInfo.role === "CLIENT") {
        if (this.ctx.showToast) this.ctx.showToast("Ping está disponible únicamente para repetidores de malla", "warning");
        return;
      }
    }

    this.appendTerminalLine(`meshcore@remote:~$ ping ${escapeHtml(name)} (${target.slice(0, 8)})`, "term-cmd");

    const btnActionPingEl = document.getElementById("btnModalActionPing");
    if (btnActionPingEl) {
      btnActionPingEl.disabled = true;
      btnActionPingEl.textContent = "🎯 Midiendo...";
    }

    try {
      const res = await fetch("/api/repeater/ping_zero", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target }),
      });
      const data = await res.json();
      if (data.status === "ok" && data.data) {
        const pingData = data.data;
        const rtt = Number(pingData.rtt_ms || pingData.duration_ms || 0);
        const rssi = pingData.rssi != null ? `${pingData.rssi} dBm` : "--";
        const snrThere = pingData.snr_there != null ? `${Number(pingData.snr_there).toFixed(1)} dB` : (pingData.snr != null ? `${Number(pingData.snr).toFixed(1)} dB` : "--");
        const snrBack = pingData.snr_back != null ? `${Number(pingData.snr_back).toFixed(1)} dB` : (pingData.snr != null ? `${Number(pingData.snr).toFixed(1)} dB` : "--");

        const line = `✓ [PONG DIRECTO] Duration: ${rtt} ms | SNR there: ${snrThere} | SNR back: ${snrBack} | RSSI: ${rssi}`;
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

        if (this.ctx.showToast) this.ctx.showToast(`🎯 Ping a ${escapeHtml(name)}: Duration: ${rtt} ms | SNR: ${snrBack} | RSSI: ${rssi}`, "success");
      } else {
        const errMsg = data.message || "Timeout esperando respuesta";
        this.appendTerminalLine(`✗ [PING FALLIDO] ${errMsg}`, "term-error");
        if (errMsg.toLowerCase().includes("password") || errMsg.toLowerCase().includes("auth") || errMsg.toLowerCase().includes("pin")) {
          this.handleRepeaterAuthError(target, errMsg);
        } else {
          if (this.ctx.showToast) this.ctx.showToast(`⚠️ Ping: ${errMsg}`, "error");
        }
      }
    } catch (err) {
      this.appendTerminalLine(`✗ [PING ERROR] ${err.message}`, "term-error");
      if (this.ctx.showToast) this.ctx.showToast(`Error de red en Ping: ${err.message}`, "error");
    } finally {
      const btnActionPingElFin = document.getElementById("btnModalActionPing");
      if (btnActionPingElFin) {
        btnActionPingElFin.disabled = false;
        btnActionPingElFin.textContent = "🎯 Ping";
      }
    }
  }

  async executeRepeaterCommand(target, action, params = {}, password = "") {
    const pwd = password || this.getRepeaterPassword(target) || "";
    this.appendTerminalLine(`meshcore@remote:~$ ${action}`, "term-cmd");
    try {
      const res = await fetch("/api/repeater/remote/action", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({ target_node: target, action, params, password: pwd }),
      });
      const data = await res.json();
      if (data.status === "ok") {
        if (data.data?.text || data.text || data.message) {
          const cleanTxt = (data.data?.text || data.text || data.message || "").replace(/^>\s*/, "").trim();
          if (cleanTxt) {
            this.appendTerminalLine(`← [RESP] ${cleanTxt}`, "term-resp");
          }
        }
      } else {
        this.appendTerminalLine(`✗ Error: ${data.message || data.error}`, "term-error");
        if (data.message && (data.message.toLowerCase().includes("password") || data.message.toLowerCase().includes("auth") || data.message.toLowerCase().includes("pin"))) {
          this.handleRepeaterAuthError(target, data.message);
        }
      }
    } catch (err) {
      this.appendTerminalLine(`✗ Error de red: ${err.message}`, "term-error");
    }
  }
}
