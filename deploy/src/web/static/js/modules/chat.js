/**
 * ChatModule - Mensajería de texto para canales broadcast, canales cifrados y mensajes directos (DM).
 * Incluye tracking de entrega (ACKs), alertas sonoras e historial persistente IndexedDB.
 */

import {
  escapeHtml,
  extractSenderAndText,
  isCommandOrSystemText,
  isCommonChatMessage,
  MAX_FEED_MESSAGES,
  buildMeshCoreContactUri,
  buildMeshCoreChannelUri,
  parseMeshCoreUri,
  MESHCORE_PUBLIC_CHANNEL_SECRET,
  MAX_LORA_TEXT_BYTES,
  getUtf8ByteLength,
  estimateLoraAirtimeMs,
} from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";

export class ChatModule {
  constructor(context) {
    this.ctx = context;
    this.channelFeeds = new Map();
    this.conversationsWithMessages = new Set();
    this.unreadCounts = new Map();
    this.activeChannelIdx = 0;
    this.activeDmTarget = null;
    this.activeDmName = null;
    this.pendingOutgoingAcks = new Map();
    this.chatSoundEnabled = localStorage.getItem("meshcore_chat_sound_enabled") !== "false";
    this._audioCtx = null;
    this.dom = {};

    // Hilos de mensajes directos cerrados/archivados por el usuario
    try {
      const rawClosed = localStorage.getItem("meshcore_closed_dm_threads");
      this.closedDmThreads = new Set(rawClosed ? JSON.parse(rawClosed) : []);
    } catch (_) {
      this.closedDmThreads = new Set();
    }

    // Estado del selector de emojis y compartir
    this.activeEmojiTab = "smileys";
    this.selectedShareContact = null;
    this.selectedShareChannel = null;
    this.emojiCategories = {
      smileys: [
        "😀","😃","😄","😁","😆","😅","😂","🤣","😊","😇",
        "🙂","🙃","😉","😌","😍","🥰","😘","😗","😙","😚",
        "😋","😛","😝","😜","🤪","🤨","🧐","🤓","😎","🤩",
        "🥳","😏","😒","😞","😔","😟","😕","🙁","☹️","😣",
        "😖","😫","😩","🥺","😢","😭","😤","😠","😡","🤬",
        "🤯","😳","🥵","🥶","😱","😨","😰","😥","😓","🤗",
        "🤔","🤭","🤫","🤥","😶","😐","😑","😬","🙄","😯",
        "😦","😧","😮","😲","🥱","😴","🤤","😪","😵","🤐",
        "🥴","🤢","🤮","🤧","😷","🤒","🤕"
      ],
      radio: [
        "📻","📡","📶","🔋","🔌","⚡","🚨","🆘","⚠️","🛰️",
        "🗺️","🧭","🏔️","🌲","🏕️","🔦","🔨","🔧","🛡️","🔒",
        "🔓","🔑","💬","📢","🔔","🔕","🎯","🚩","📍","🏁",
        "🎙️","🔊","🔉","🔈","🛠️","⚙️","🚗","🚙","🚚","🚒",
        "🚑","🚓","🚤","⛵","🚁","✈️","⛺","🌦️","🌧️","☀️"
      ],
      symbols: [
        "👍","👎","👌","✌️","🤞","🤟","🤙","👋","✋","👏",
        "🤝","🙏","💪","❤️","🧡","💛","💚","💙","💜","🖤",
        "🤍","💯","💢","💥","🔥","✨","⭐","🌟","✅","❌",
        "❓","❗","0️⃣","1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣",
        "8️⃣","9️⃣","🔟","ℹ️","🆗","🛑","⛔","🚀","🎉","🏆"
      ]
    };
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.loadInitialHistory();
    this._renderEmojiGrid("smileys");
    this.updateCharCounter();
    if (window.innerWidth <= 900 && this.dom.sidebarChannelList) {
      this.dom.sidebarChannelList.classList.add("mobile-open");
    }
  }

  _bindElements() {
    this.dom = {
      chatMessageFeed: document.getElementById("chatMessageFeed"),
      chatInputForm: document.getElementById("chatInputForm"),
      chatInputText: document.getElementById("chatInputText"),
      chatCharCounter: document.getElementById("chatCharCounter"),
      btnSendMsg: document.getElementById("btnSendMsg"),
      chatTargetName: document.getElementById("chatActiveTitle"),
      chatTargetSub: document.getElementById("chatActiveSub"),
      chatTargetAvatar: document.getElementById("chatTargetAvatar"),
      btnBackToChannelsMobile: document.getElementById("btnBackToChannelsMobile"),
      btnShareLocation: document.getElementById("btnShareLocation"),
      btnToggleChannelsMobile: document.getElementById("btnToggleChannelsMobile"),
      dmListUi: document.getElementById("dmListUi"),
      btnCloseChat: document.getElementById("btnCloseChat"),
      clearChatBtn: document.getElementById("clearChatBtn"),
      dmCountBadge: document.getElementById("dmCountBadge"),
      sidebarChannelList: document.getElementById("sidebarChannelList"),
      globalChatUnreadBadge: document.getElementById("globalChatUnreadBadge"),
      chkChatSoundAlerts: document.getElementById("chkChatSoundAlerts"),

      // Selector de emojis y adjuntos
      btnEmojiPicker: document.getElementById("btnEmojiPicker"),
      emojiPickerPopover: document.getElementById("emojiPickerPopover"),
      emojiPickerGrid: document.getElementById("emojiPickerGrid"),
      btnChatAttach: document.getElementById("btnChatAttach"),
      chatAttachMenu: document.getElementById("chatAttachMenu"),
      attachOptionContact: document.getElementById("attachOptionContact"),
      attachOptionChannel: document.getElementById("attachOptionChannel"),
      attachOptionLocation: document.getElementById("attachOptionLocation"),

      // Modales de compartir contacto y canal
      modalShareContact: document.getElementById("modalShareContact"),
      modalShareChannel: document.getElementById("modalShareChannel"),
      shareContactSearch: document.getElementById("shareContactSearch"),
      shareContactList: document.getElementById("shareContactList"),
      btnConfirmShareContact: document.getElementById("btnConfirmShareContact"),
      btnCancelShareContact: document.getElementById("btnCancelShareContact"),
      btnCloseShareContactModal: document.getElementById("btnCloseShareContactModal"),
      shareChannelList: document.getElementById("shareChannelList"),
      btnConfirmShareChannel: document.getElementById("btnConfirmShareChannel"),
      btnCancelShareChannel: document.getElementById("btnCancelShareChannel"),
      btnCloseShareChannelModal: document.getElementById("btnCloseShareChannelModal"),
    };
  }

  _bindEvents() {
    // Botón de retorno a canales en móvil (estilo WhatsApp)
    const handleMobileBack = () => {
      const panel = this.dom.sidebarChannelList || document.querySelector(".chat-channels-panel");
      if (panel) {
        panel.classList.toggle("mobile-open");
      }
    };
    if (this.dom.btnBackToChannelsMobile) {
      this.dom.btnBackToChannelsMobile.addEventListener("click", handleMobileBack);
    }
    if (this.dom.btnToggleChannelsMobile) {
      this.dom.btnToggleChannelsMobile.addEventListener("click", handleMobileBack);
    }

    // Contador de caracteres/bytes en tiempo real
    if (this.dom.chatInputText) {
      this.dom.chatInputText.addEventListener("input", () => this.updateCharCounter());
    }

    if (this.dom.chatInputForm) {
      this.dom.chatInputForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.sendMessage();
      });
    }

    if (this.dom.btnCloseChat) {
      this.dom.btnCloseChat.addEventListener("click", () => {
        if (this.activeDmTarget) {
          this.closeDmConversation(this.activeDmTarget);
        }
      });
    }

    if (this.dom.clearChatBtn) {
      this.dom.clearChatBtn.addEventListener("click", () => this.clearCurrentChat());
    }

    if (this.dom.btnShareLocation) {
      this.dom.btnShareLocation.addEventListener("click", () => this.shareCurrentLocation());
    }

    // Selector de Emojis
    if (this.dom.btnEmojiPicker && this.dom.emojiPickerPopover) {
      this.dom.btnEmojiPicker.addEventListener("click", (e) => {
        e.stopPropagation();
        if (this.dom.chatAttachMenu) this.dom.chatAttachMenu.classList.add("hidden");
        this.dom.emojiPickerPopover.classList.toggle("hidden");
      });
    }

    // Pestañas de categorías de Emojis
    document.querySelectorAll(".emoji-tab").forEach((tab) => {
      tab.addEventListener("click", (e) => {
        e.stopPropagation();
        document.querySelectorAll(".emoji-tab").forEach((t) => t.classList.remove("active"));
        tab.classList.add("active");
        const cat = tab.getAttribute("data-tab") || "smileys";
        this.activeEmojiTab = cat;
        this._renderEmojiGrid(cat);
      });
    });

    // Menú flotante de adjuntos
    if (this.dom.btnChatAttach && this.dom.chatAttachMenu) {
      this.dom.btnChatAttach.addEventListener("click", (e) => {
        e.stopPropagation();
        if (this.dom.emojiPickerPopover) this.dom.emojiPickerPopover.classList.add("hidden");
        this.dom.chatAttachMenu.classList.toggle("hidden");
      });
    }

    if (this.dom.attachOptionLocation) {
      this.dom.attachOptionLocation.addEventListener("click", () => {
        if (this.dom.chatAttachMenu) this.dom.chatAttachMenu.classList.add("hidden");
        this.shareCurrentLocation();
      });
    }

    if (this.dom.attachOptionContact) {
      this.dom.attachOptionContact.addEventListener("click", () => {
        if (this.dom.chatAttachMenu) this.dom.chatAttachMenu.classList.add("hidden");
        this.openShareContactModal();
      });
    }

    if (this.dom.attachOptionChannel) {
      this.dom.attachOptionChannel.addEventListener("click", () => {
        if (this.dom.chatAttachMenu) this.dom.chatAttachMenu.classList.add("hidden");
        this.openShareChannelModal();
      });
    }

    // Cerrar menús flotantes al hacer clic en cualquier otra parte
    document.addEventListener("click", (e) => {
      if (this.dom.emojiPickerPopover && !this.dom.emojiPickerPopover.classList.contains("hidden")) {
        if (!this.dom.emojiPickerPopover.contains(e.target) && e.target !== this.dom.btnEmojiPicker) {
          this.dom.emojiPickerPopover.classList.add("hidden");
        }
      }
      if (this.dom.chatAttachMenu && !this.dom.chatAttachMenu.classList.contains("hidden")) {
        if (!this.dom.chatAttachMenu.contains(e.target) && e.target !== this.dom.btnChatAttach) {
          this.dom.chatAttachMenu.classList.add("hidden");
        }
      }
    });

    // Eventos de Modales de Compartir
    if (this.dom.btnCloseShareContactModal) {
      this.dom.btnCloseShareContactModal.addEventListener("click", () => this.closeShareContactModal());
    }
    if (this.dom.btnCancelShareContact) {
      this.dom.btnCancelShareContact.addEventListener("click", () => this.closeShareContactModal());
    }
    if (this.dom.btnConfirmShareContact) {
      this.dom.btnConfirmShareContact.addEventListener("click", () => this.confirmShareContact());
    }
    if (this.dom.shareContactSearch) {
      this.dom.shareContactSearch.addEventListener("input", (e) => this.filterShareContactList(e.target.value));
    }

    if (this.dom.btnCloseShareChannelModal) {
      this.dom.btnCloseShareChannelModal.addEventListener("click", () => this.closeShareChannelModal());
    }
    if (this.dom.btnCancelShareChannel) {
      this.dom.btnCancelShareChannel.addEventListener("click", () => this.closeShareChannelModal());
    }
    if (this.dom.btnConfirmShareChannel) {
      this.dom.btnConfirmShareChannel.addEventListener("click", () => this.confirmShareChannel());
    }

    if (this.dom.chkChatSoundAlerts) {
      this.dom.chkChatSoundAlerts.checked = this.chatSoundEnabled;
      this.dom.chkChatSoundAlerts.addEventListener("change", (e) => {
        this.chatSoundEnabled = e.target.checked;
        localStorage.setItem("meshcore_chat_sound_enabled", String(this.chatSoundEnabled));
        if (this.chatSoundEnabled) {
          this.playNotificationChime();
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('chat.sound_on'), "info");
        } else {
          if (this.ctx.showToast) this.ctx.showToast(I18n.t('chat.sound_off'), "info");
        }
      });
    }
  }

  _subscribeBus() {
    if (!this.ctx.eventBus) return;

    this.ctx.eventBus.on(EVENTS.RX_PACKET, async (payload) => {
      if (!payload || typeof payload !== "object") return;
      const evType = payload.type || payload.event_type;

      if (evType === "message_delivered") {
        this.handleDeliveryAck(payload);
        return;
      }

      if (isCommonChatMessage(payload)) {
        await this.handleIncomingChatMessage(payload);
      }
    });
  }

  async loadInitialHistory() {
    if (!this.ctx.storage) return;

    const initialMsgs = await this.ctx.storage.getMessagesByFeed("ch_0");
    if (initialMsgs && initialMsgs.length > 0) {
      const cleanMsgs = initialMsgs.filter((m) => !isCommandOrSystemText(m.text, m.txt_type));
      this.channelFeeds.set("ch_0", cleanMsgs);
      if (this.activeChannelIdx === 0 && !this.activeDmTarget) {
        await this.renderCurrentConversation();
      }
    }

    try {
      const dmThreads = await this.ctx.storage.getDmConversations();
      if (dmThreads && dmThreads.length > 0) {
        for (const thread of dmThreads) {
          const canonicalPk = this.resolveCanonicalPubkey(thread.pubkey);
          if (this._isLocalTarget(canonicalPk)) continue;
          const node = this.ctx.knownNodes?.get(canonicalPk.toLowerCase());
          const roleUpper = String(node?.role || "").toUpperCase();
          if (roleUpper === "REPEATER" || roleUpper === "ROUTER") continue;
          this.conversationsWithMessages.add(canonicalPk);
          if (this.closedDmThreads.has(canonicalPk)) continue;
          this.addDmContact(canonicalPk, thread.name || canonicalPk.slice(0, 8));
        }
      }
    } catch (_) {}
  }

  _isLocalTarget(pubkey) {
    if (!pubkey) return true;
    const norm = String(pubkey).trim().toLowerCase();
    if (norm === "local" || norm === "000000000000") return true;
    const localPk = (document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();
    if (localPk && (norm === localPk || (localPk.length >= 8 && norm.startsWith(localPk.slice(0, 8))) || (norm.length >= 8 && localPk.startsWith(norm.slice(0, 8))))) {
      return true;
    }
    const node = this.ctx.knownNodes?.get(norm);
    if (node && (node.is_local || String(node.role).toUpperCase() === "LOCAL")) return true;
    return false;
  }

  resolveCanonicalPubkey(pubkey) {
    if (this.ctx.resolveCanonicalPubkey) {
      return this.ctx.resolveCanonicalPubkey(pubkey);
    }
    return pubkey ? String(pubkey).trim().toLowerCase() : "";
  }

  _renderEmojiGrid(category) {
    if (!this.dom.emojiPickerGrid) return;
    this.dom.emojiPickerGrid.innerHTML = "";
    const list = this.emojiCategories[category] || this.emojiCategories.smileys;
    const frag = document.createDocumentFragment();

    list.forEach((emoji) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "emoji-btn";
      btn.textContent = emoji;
      btn.title = emoji;
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        this.insertEmoji(emoji);
      });
      frag.appendChild(btn);
    });

    this.dom.emojiPickerGrid.appendChild(frag);
  }

  insertEmoji(emoji) {
    if (!this.dom.chatInputText) return;
    const input = this.dom.chatInputText;
    const start = input.selectionStart || 0;
    const end = input.selectionEnd || 0;
    const val = input.value;
    input.value = val.substring(0, start) + emoji + val.substring(end);
    const newPos = start + emoji.length;
    input.setSelectionRange(newPos, newPos);
    input.focus();
    this.updateCharCounter();
  }

  openShareContactModal() {
    if (!this.dom.modalShareContact) return;
    this.selectedShareContact = null;
    if (this.dom.btnConfirmShareContact) this.dom.btnConfirmShareContact.disabled = true;
    if (this.dom.shareContactSearch) this.dom.shareContactSearch.value = "";
    this._populateShareContactList("");
    this.dom.modalShareContact.classList.remove("hidden");
    if (window.initLucideIcons) {
      window.initLucideIcons(this.dom.modalShareContact);
    }
  }

  closeShareContactModal() {
    if (this.dom.modalShareContact) this.dom.modalShareContact.classList.add("hidden");
    this.selectedShareContact = null;
  }

  _populateShareContactList(filterQuery = "") {
    if (!this.dom.shareContactList) return;
    this.dom.shareContactList.innerHTML = "";
    const q = (filterQuery || "").toLowerCase().trim();

    // SSoT: Obtener nodos cliente exclusivamente (excluir REPEATER y LOCAL)
    const allNodes = this.ctx.knownNodes ? Array.from(this.ctx.knownNodes.values()) : [];
    const localPk = (document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();

    const clientContacts = allNodes.filter((n) => {
      if (!n || !n.public_key) return false;
      const pk = n.public_key.toLowerCase().trim();
      if (pk === "local" || (localPk && (pk === localPk || pk.startsWith(localPk.slice(0, 8)))) || n.is_local) return false;
      const roleUpper = String(n.role || "").toUpperCase();
      if (roleUpper === "REPEATER" || roleUpper === "ROUTER") return false;
      if (q) {
        const name = (n.name || n.alias || "").toLowerCase();
        return name.includes(q) || pk.includes(q);
      }
      return true;
    });

    if (clientContacts.length === 0) {
      this.dom.shareContactList.innerHTML = `
        <div class="empty-state" style="padding: 18px; font-size: 12px; color: var(--text-muted); text-align: center;">
          ${q ? `No se encontraron contactos para "${escapeHtml(q)}"` : "No hay contactos disponibles para compartir en este momento."}
        </div>
      `;
      return;
    }

    const frag = document.createDocumentFragment();
    clientContacts.forEach((contact) => {
      const item = document.createElement("div");
      item.className = "share-picker-item";
      const cleanName = contact.name || contact.alias || contact.public_key.slice(0, 8);
      const isSelected = this.selectedShareContact?.public_key === contact.public_key;
      if (isSelected) item.classList.add("selected");

      item.innerHTML = `
        <div class="share-picker-left">
          <span style="font-size: 18px;">👤</span>
          <div>
            <div class="share-picker-title">${escapeHtml(cleanName)}</div>
            <div class="share-picker-sub">${contact.public_key.slice(0, 14)}… • ${contact.role || "CLIENT"}</div>
          </div>
        </div>
        <span class="badge-pill">${contact.is_favorite ? "⭐" : "Contacto"}</span>
      `;

      item.addEventListener("click", () => {
        this.dom.shareContactList.querySelectorAll(".share-picker-item").forEach((el) => el.classList.remove("selected"));
        item.classList.add("selected");
        this.selectedShareContact = contact;
        if (this.dom.btnConfirmShareContact) this.dom.btnConfirmShareContact.disabled = false;
      });

      frag.appendChild(item);
    });

    this.dom.shareContactList.appendChild(frag);
  }

  filterShareContactList(query) {
    this._populateShareContactList(query);
  }

  async confirmShareContact() {
    if (!this.selectedShareContact) return;
    const c = this.selectedShareContact;
    const uri = buildMeshCoreContactUri(c.name || c.alias || "Contacto", c.public_key, c.role || "CLIENT");
    this.closeShareContactModal();
    await this.sendMessageWithText(uri);
  }

  openShareChannelModal() {
    if (!this.dom.modalShareChannel) return;
    this.selectedShareChannel = null;
    if (this.dom.btnConfirmShareChannel) this.dom.btnConfirmShareChannel.disabled = true;
    this._populateShareChannelList();
    this.dom.modalShareChannel.classList.remove("hidden");
    if (window.initLucideIcons) {
      window.initLucideIcons(this.dom.modalShareChannel);
    }
  }

  closeShareChannelModal() {
    if (this.dom.modalShareChannel) this.dom.modalShareChannel.classList.add("hidden");
    this.selectedShareChannel = null;
  }

  _populateShareChannelList() {
    if (!this.dom.shareChannelList) return;
    this.dom.shareChannelList.innerHTML = "";

    const rawList = this.ctx.channelsList || this.ctx.settingsModule?.channelsList || [];
    // REGLA SSoT: El canal 0 (Public / Broadcast) es universal y todos los nodos ya lo tienen.
    // NUNCA permitir compartir el canal público. Solo compartir canales privados/cifrados (índice >= 1).
    const chList = rawList.filter((ch) => Number(ch.index) > 0);

    if (chList.length === 0) {
      const emptyDiv = document.createElement("div");
      emptyDiv.className = "share-picker-empty";
      emptyDiv.style.cssText = "padding: 24px 16px; text-align: center; color: var(--text-muted); font-size: 0.85rem;";
      emptyDiv.innerHTML = `
        <div style="font-size: 28px; margin-bottom: 8px; opacity: 0.6;">📻</div>
        <strong>No hay canales privados para compartir</strong>
        <p style="margin: 6px 0 0 0; font-size: 0.78rem; opacity: 0.8;">
          El canal 0 es público y universal (todos los nodos de la malla ya lo tienen). Puedes configurar canales cifrados en la pestaña <strong>Ajustes</strong>.
        </p>
      `;
      this.dom.shareChannelList.appendChild(emptyDiv);
      if (this.dom.btnConfirmShareChannel) this.dom.btnConfirmShareChannel.disabled = true;
      return;
    }

    const frag = document.createDocumentFragment();
    chList.forEach((ch) => {
      const item = document.createElement("div");
      item.className = "share-picker-item";
      const chName = ch.name || `Canal #${ch.index}`;
      const isEncrypted = Boolean(ch.has_psk || (ch.psk && ch.psk.trim().length > 0 && ch.psk !== MESHCORE_PUBLIC_CHANNEL_SECRET));

      item.innerHTML = `
        <div class="share-picker-left">
          <span style="font-size: 18px;">${isEncrypted ? "🔒" : "📻"}</span>
          <div>
            <div class="share-picker-title">${escapeHtml(chName)}</div>
            <div class="share-picker-sub">Índice #${ch.index} • ${isEncrypted ? "Canal Privado Cifrado" : "Canal Abierto Secundario"}</div>
          </div>
        </div>
        <span class="badge-pill">${isEncrypted ? "Cifrado" : "Abierto"}</span>
      `;

      item.addEventListener("click", () => {
        this.dom.shareChannelList.querySelectorAll(".share-picker-item").forEach((el) => el.classList.remove("selected"));
        item.classList.add("selected");
        this.selectedShareChannel = ch;
        if (this.dom.btnConfirmShareChannel) this.dom.btnConfirmShareChannel.disabled = false;
      });

      frag.appendChild(item);
    });

    this.dom.shareChannelList.appendChild(frag);
  }

  async confirmShareChannel() {
    if (!this.selectedShareChannel) return;
    const ch = this.selectedShareChannel;
    const uri = buildMeshCoreChannelUri(ch.name, ch.psk || ch.secret || "", ch.index);
    this.closeShareChannelModal();
    await this.sendMessageWithText(uri);
  }

  async sendMessageWithText(text) {
    if (!text) return;
    if (this.dom.chatInputText) {
      this.dom.chatInputText.value = text;
      this.updateCharCounter();
    }
    await this.sendMessage();
  }

  updateCharCounter() {
    if (!this.dom.chatInputText || !this.dom.chatCharCounter) return;
    const text = this.dom.chatInputText.value || "";
    const byteLen = getUtf8ByteLength(text);
    const maxBytes = MAX_LORA_TEXT_BYTES;
    const charCount = [...text].length;

    // Obtener parámetros RF de modulación en vivo del nodo
    const cfg = this.ctx.localConfig || {};
    const sf = Number(cfg.spreading_factor || cfg.sf || 11);
    const bw = Number(cfg.bandwidth || cfg.bw || 250);
    const cr = Number(cfg.coding_rate || cfg.cr || 5);
    const airtimeMs = byteLen > 0 ? estimateLoraAirtimeMs(byteLen, sf, bw, cr) : 0;

    // Actualizar texto del badge
    this.dom.chatCharCounter.textContent = `${byteLen} / ${maxBytes} B`;

    // Tooltip informativo con ocupación estimada de espectro
    this.dom.chatCharCounter.title = `Carga útil LoRa: ${byteLen} bytes de ${maxBytes} B máx. (${charCount} car.). Modulación SF${sf}/${bw}kHz (Airtime estimado: ~${airtimeMs} ms)`;

    // Manejo de umbrales visuales y estado del botón de envío
    this.dom.chatCharCounter.classList.remove("is-warning", "is-danger");
    if (byteLen > maxBytes) {
      this.dom.chatCharCounter.classList.add("is-danger");
      if (this.dom.btnSendMsg) this.dom.btnSendMsg.disabled = true;
    } else if (byteLen >= Math.floor(maxBytes * 0.8)) {
      this.dom.chatCharCounter.classList.add("is-warning");
      if (this.dom.btnSendMsg) this.dom.btnSendMsg.disabled = false;
    } else {
      if (this.dom.btnSendMsg) this.dom.btnSendMsg.disabled = false;
    }
  }

  _formatMessageTimestamp(timestamp) {
    if (!timestamp) return "";
    const msgDate = new Date(timestamp);
    if (isNaN(msgDate.getTime())) return "";

    const now = new Date();
    const isToday = msgDate.toDateString() === now.toDateString();

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    const isYesterday = msgDate.toDateString() === yesterday.toDateString();

    const timeStr = msgDate.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    if (isToday) {
      return timeStr;
    } else if (isYesterday) {
      const ayerStr = (window.I18n ? window.I18n.t('chat.yesterday') : null) || "Ayer";
      return `${ayerStr} ${timeStr}`;
    } else {
      const dateStr = msgDate.toLocaleDateString([], { day: "2-digit", month: "2-digit", year: "numeric" });
      return `${dateStr} ${timeStr}`;
    }
  }

  _getDateGroupLabel(timestamp) {
    if (!timestamp) return "";
    const msgDate = new Date(timestamp);
    if (isNaN(msgDate.getTime())) return "";

    const now = new Date();
    if (msgDate.toDateString() === now.toDateString()) {
      return (window.I18n ? window.I18n.t('chat.date_today') : null) || "HOY";
    }

    const yesterday = new Date(now);
    yesterday.setDate(yesterday.getDate() - 1);
    if (msgDate.toDateString() === yesterday.toDateString()) {
      return (window.I18n ? window.I18n.t('chat.date_yesterday') : null) || "AYER";
    }

    return msgDate.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: "numeric" }).toUpperCase();
  }

  _updateActiveChatHeader() {
    if (this.activeDmTarget) {
      // Caso Conversación Directa (DM)
      if (this.dom.chatTargetAvatar) {
        this.dom.chatTargetAvatar.textContent = "👤";
      }
      if (this.dom.chatTargetName) {
        this.dom.chatTargetName.textContent = `DM: ${this.activeDmName || this.activeDmTarget.slice(0, 8)}`;
      }
      if (this.dom.chatTargetSub) {
        const normTarget = this.activeDmTarget.toLowerCase().trim();
        const node = (this.ctx.knownNodes ? Array.from(this.ctx.knownNodes.values()) : []).find(
          (n) => (n.public_key && n.public_key.toLowerCase() === normTarget) ||
                 (n.key_prefix && normTarget.startsWith(n.key_prefix.toLowerCase()))
        );

        let subParts = [];
        if (node && node.last_seen && Number(node.last_seen) > 0) {
          let effTs = Number(node.last_seen);
          if (effTs > 1e11) effTs = Math.floor(effTs / 1000);
          const diff = Math.max(0, Math.floor(Date.now() / 1000) - effTs);
          if (diff < 900) {
            subParts.push(window.I18n ? window.I18n.t('chat.online_now') || '🟢 En línea' : '🟢 En línea');
          } else if (diff < 7200) {
            const mins = Math.max(1, Math.floor(diff / 60));
            const str = window.I18n ? window.I18n.t('chat.last_seen_mins') : null;
            subParts.push(str ? str.replace('{n}', mins) : `Últ. vez hace ${mins} min`);
          } else if (diff < 86400) {
            const hours = Math.floor(diff / 3600);
            const str = window.I18n ? window.I18n.t('chat.last_seen_hours') : null;
            subParts.push(str ? str.replace('{n}', hours) : `Últ. vez hace ${hours} h`);
          } else {
            const days = Math.max(1, Math.floor(diff / 86400));
            const str = window.I18n ? window.I18n.t('chat.last_seen_days') : null;
            subParts.push(str ? str.replace('{n}', days) : `Últ. vez hace ${days} d`);
          }
        } else {
          subParts.push(window.I18n ? window.I18n.t('chat.no_telemetry') || 'Sin telemetría reciente' : 'Sin telemetría reciente');
        }

        // Batería si está presente
        if (node?.battery_pct != null) {
          subParts.push(`🔋 ${node.battery_pct}%`);
        } else if (node?.voltage_v != null) {
          subParts.push(`🔋 ${node.voltage_v}V`);
        }

        // SNR si está disponible
        if (node?.last_snr != null) {
          subParts.push(`📶 SNR ${node.last_snr} dB`);
        }

        if (subParts.length === 1 && !node) {
          subParts.push(`ID: ${this.activeDmTarget.slice(0, 10)}…`);
        }

        this.dom.chatTargetSub.textContent = subParts.join(" • ");
      }
    } else {
      // Caso Canal
      const chList = this.ctx.settingsModule?.channelsList || [];
      const ch = chList.find((c) => Number(c.index) === this.activeChannelIdx);
      const isEncrypted = ch ? Boolean(ch.has_psk || (ch.psk && ch.psk.trim().length > 0 && ch.psk !== MESHCORE_PUBLIC_CHANNEL_SECRET)) : (this.activeChannelIdx !== 0);
      const prefix = window.I18n ? window.I18n.t('chat.channel_prefix') || 'Canal' : 'Canal';
      let chTitle = `${prefix} #${this.activeChannelIdx}`;
      if (ch?.name && ch.name.trim()) {
        chTitle += `: ${ch.name.trim()}`;
      } else if (this.activeChannelIdx === 0) {
        chTitle += `: ${window.I18n ? window.I18n.t('chat.ch_0_default') || 'Public / Broadcast' : 'Public / Broadcast'}`;
      }

      if (this.dom.chatTargetName) {
        this.dom.chatTargetName.textContent = chTitle;
      }

      if (this.dom.chatTargetAvatar) {
        this.dom.chatTargetAvatar.textContent = this.activeChannelIdx === 0 ? "📢" : (isEncrypted ? "🔒" : "📻");
      }

      if (this.dom.chatTargetSub) {
        if (this.activeChannelIdx === 0) {
          this.dom.chatTargetSub.textContent = (window.I18n ? window.I18n.t('chat.ch_0_sub') : null) || '📢 Canal público broadcast • Sin cifrar';
        } else if (isEncrypted) {
          const subTemplate = (window.I18n ? window.I18n.t('chat.ch_n_encrypted_sub') : null) || '🔒 Canal privado cifrado #{n}';
          this.dom.chatTargetSub.textContent = subTemplate.replace('{n}', this.activeChannelIdx);
        } else {
          const subTemplate = (window.I18n ? window.I18n.t('chat.ch_n_open_sub') : null) || '📻 Canal abierto sin cifrar #{n}';
          this.dom.chatTargetSub.textContent = subTemplate.replace('{n}', this.activeChannelIdx);
        }
      }
    }
  }

  switchChannel(idx) {
    this.activeChannelIdx = Number(idx) || 0;
    this.activeDmTarget = null;
    this.activeDmName = null;

    if (this.dom.btnCloseChat) {
      this.dom.btnCloseChat.classList.add("hidden");
    }

    this._updateActiveChatHeader();

    document.querySelectorAll(".channel-item").forEach((el) => el.classList.remove("active"));
    const activeItem = document.querySelector(`.channel-item[data-channel-idx="${this.activeChannelIdx}"]`);
    if (activeItem) activeItem.classList.add("active");

    const panel = document.querySelector(".chat-channels-panel");
    if (panel && window.innerWidth <= 900) {
      panel.classList.remove("mobile-open");
    }

    this.renderCurrentConversation();
  }

  setDmTarget(pubkey, name) {
    this.openDmConversation(pubkey, name);
  }

  openDmConversation(pubkey, name) {
    if (!pubkey) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    if (this._isLocalTarget(canonicalPk)) {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.dm_local_err'), "warning");
      return;
    }

    const normTarget = canonicalPk.toLowerCase().trim();
    const targetNode = (this.ctx.knownNodes ? Array.from(this.ctx.knownNodes.values()) : []).find(
      (n) => (n.public_key && n.public_key.toLowerCase() === normTarget) ||
             (n.key_prefix && normTarget.startsWith(n.key_prefix.toLowerCase()))
    );
    const roleUpper = String(targetNode?.role || "").toUpperCase();
    if (roleUpper === "REPEATER" || roleUpper === "ROUTER") {
      if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.repeater_chat_err'), "warning");
      return;
    }

    // Si el hilo estaba cerrado/archivado, reabrirlo
    if (this.closedDmThreads.has(canonicalPk)) {
      this.closedDmThreads.delete(canonicalPk);
      this._saveClosedDmThreads();
    }

    this.activeDmTarget = canonicalPk;
    this.activeDmName = name || canonicalPk.slice(0, 8);
    if (this.activeDmName.includes("Estación Local") || this.activeDmName.includes("Local Station")) {
      this.activeDmName = targetNode?.name || canonicalPk.slice(0, 8);
    }

    if (this.dom.btnCloseChat) {
      this.dom.btnCloseChat.classList.remove("hidden");
    }

    this._updateActiveChatHeader();
    this.addDmContact(canonicalPk, this.activeDmName);

    document.querySelectorAll(".channel-item").forEach((el) => el.classList.remove("active"));
    const activeDmEl = document.querySelector(`.channel-item[data-pubkey="${canonicalPk}"]`);
    if (activeDmEl) activeDmEl.classList.add("active");

    const navBtn = document.querySelector('.nav-btn[data-tab="tab-chat"]');
    if (navBtn) navBtn.click();

    const panel = document.querySelector(".chat-channels-panel");
    if (panel && window.innerWidth <= 900) {
      panel.classList.remove("mobile-open");
    }

    this.renderCurrentConversation();
  }

  shareCurrentLocation() {
    if (!navigator.geolocation) {
      this._fallbackShareLocalStationLocation("Geolocalización no soportada en el navegador");
      return;
    }

    if (this.ctx.showToast) {
      this.ctx.showToast(I18n.t('toast.gps_loading'), "info", 2000);
    }

    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const lat = pos.coords.latitude.toFixed(5);
        const lon = pos.coords.longitude.toFixed(5);
        const text = `📍 ${lat}, ${lon}`;
        if (this.dom.chatInputText) {
          this.dom.chatInputText.value = text;
          this.dom.chatInputText.focus();
        }
        if (this.ctx.showToast) {
          this.ctx.showToast(I18n.t('toast.gps_ready').replace('{lat}', lat).replace('{lon}', lon), "success");
        }
      },
      (err) => {
        this._fallbackShareLocalStationLocation(`No se pudo obtener GPS del navegador (${err.message})`);
      },
      { timeout: 8000, enableHighAccuracy: true }
    );
  }

  _fallbackShareLocalStationLocation(reason) {
    const latInput = document.getElementById("localGpsLat");
    const lonInput = document.getElementById("localGpsLon");
    const latVal = latInput ? parseFloat(latInput.value) : NaN;
    const lonVal = lonInput ? parseFloat(lonInput.value) : NaN;

    if (!isNaN(latVal) && !isNaN(lonVal) && (latVal !== 0 || lonVal !== 0)) {
      const text = `📍 ${latVal.toFixed(5)}, ${lonVal.toFixed(5)}`;
      if (this.dom.chatInputText) {
        this.dom.chatInputText.value = text;
        this.dom.chatInputText.focus();
      }
      if (this.ctx.showToast) {
        this.ctx.showToast(I18n.t('toast.gps_station').replace('{lat}', latVal.toFixed(5)).replace('{lon}', lonVal.toFixed(5)), "info");
      }
      return;
    }

    if (this.ctx.showToast) {
      this.ctx.showToast(`${reason}. Configura latitud/longitud en Ajustes.`, "warning");
    }
  }

  async clearCurrentChat() {
    const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    this.channelFeeds.delete(feedKey);

    if (this.ctx.storage && this.ctx.storage.clearFeedMessages) {
      try {
        await this.ctx.storage.clearFeedMessages(feedKey);
      } catch (_) {}
    }

    if (this.dom.chatMessageFeed) {
      this.dom.chatMessageFeed.innerHTML = `
        <div class="chat-empty-state">
          <p>${window.I18n ? window.I18n.t('chat.cleared') : 'Historial de chat limpiado'}</p>
          <small>${window.I18n ? window.I18n.t('chat.write_below') : 'Escribe un mensaje abajo para comenzar'}</small>
        </div>
      `;
    }

    if (this.ctx.showToast) {
      this.ctx.showToast(window.I18n ? window.I18n.t('chat.cleared') : "Historial de chat limpiado", "info");
    }
  }

  _saveClosedDmThreads() {
    try {
      localStorage.setItem("meshcore_closed_dm_threads", JSON.stringify(Array.from(this.closedDmThreads)));
    } catch (_) {}
  }

  closeDmConversation(pubkey) {
    if (!pubkey) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    this.closedDmThreads.add(canonicalPk);
    this._saveClosedDmThreads();

    // Eliminar el elemento del DOM en dmListUi
    if (this.dom.dmListUi) {
      const item = this.dom.dmListUi.querySelector(`.channel-item[data-pubkey="${canonicalPk}"]`);
      if (item) item.remove();
      const totalDms = this.dom.dmListUi.querySelectorAll(".channel-item").length;
      if (this.dom.dmCountBadge) {
        this.dom.dmCountBadge.textContent = String(totalDms);
      }
    }

    // Si el chat cerrado era el que estaba activo en pantalla, conmutar suavemente al Canal 0 (Público)
    if (this.activeDmTarget === canonicalPk) {
      this.switchChannel(0);
    }

    if (this.ctx.showToast) {
      this.ctx.showToast(window.I18n ? window.I18n.t('chat.chat_closed') : "Conversación cerrada (mensajes conservados)", "info");
    }
  }

  addDmContact(pubkey, name) {
    if (!pubkey || !this.dom.dmListUi) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    if (this._isLocalTarget(canonicalPk)) return;

    // SSoT Rule 1: Repeaters must NEVER be in contacts or DM list
    const node = this.ctx.knownNodes?.get(canonicalPk.toLowerCase());
    const roleUpper = String(node?.role || "").toUpperCase();
    if (roleUpper === "REPEATER" || roleUpper === "ROUTER") return;

    let cleanDisplayName = name || canonicalPk.slice(0, 8);
    if (cleanDisplayName.includes("Estación Local") || cleanDisplayName.includes("Local Station")) {
      cleanDisplayName = node?.name || canonicalPk.slice(0, 8);
    }

    const emptyHint = this.dom.dmListUi.querySelector(".empty-hint");
    if (emptyHint) emptyHint.remove();

    const existing = this.dom.dmListUi.querySelector(`.channel-item[data-pubkey="${canonicalPk}"]`);
    if (existing) return;

    const li = document.createElement("li");
    li.className = "channel-item";
    li.setAttribute("data-pubkey", canonicalPk);
    li.innerHTML = `
      <span class="channel-icon">💬</span>
      <span class="channel-name ch-name">${escapeHtml(cleanDisplayName)}</span>
      <span class="channel-idx font-mono">DM</span>
      <button type="button" class="btn-close-dm" title="${window.I18n ? window.I18n.t('chat.close_chat') : 'Cerrar chat'}" aria-label="${window.I18n ? window.I18n.t('chat.close_chat') : 'Cerrar chat'}">✕</button>
    `;
    li.addEventListener("click", () => this.openDmConversation(canonicalPk, cleanDisplayName));

    const btnClose = li.querySelector(".btn-close-dm");
    if (btnClose) {
      btnClose.addEventListener("click", (e) => {
        e.stopPropagation();
        this.closeDmConversation(canonicalPk);
      });
    }

    this.dom.dmListUi.appendChild(li);

    const totalDms = this.dom.dmListUi.querySelectorAll(".channel-item").length;
    if (this.dom.dmCountBadge) {
      this.dom.dmCountBadge.textContent = String(totalDms);
    }
  }

  async renderCurrentConversation() {
    if (!this.dom.chatMessageFeed) return;
    this.dom.chatMessageFeed.textContent = "";

    const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    let msgs = this.channelFeeds.get(feedKey);

    if (!msgs && this.ctx.storage) {
      msgs = await this.ctx.storage.getMessagesByFeed(feedKey);
      this.channelFeeds.set(feedKey, msgs || []);
    }

    if (!msgs || msgs.length === 0) {
      this.dom.chatMessageFeed.innerHTML = `
        <div class="chat-empty-state">
          <p>${window.I18n ? window.I18n.t('chat.no_messages') : 'No hay mensajes en esta conversación'}</p>
          <small>${window.I18n ? window.I18n.t('chat.write_below') : 'Escribe un mensaje abajo para comenzar'}</small>
        </div>
      `;
      return;
    }

    const frag = document.createDocumentFragment();
    let lastDateStr = null;

    msgs.forEach((m) => {
      if (m.timestamp) {
        const msgDateStr = new Date(m.timestamp).toDateString();
        if (msgDateStr !== lastDateStr) {
          lastDateStr = msgDateStr;
          const sep = document.createElement("div");
          sep.className = "chat-date-separator";
          sep.innerHTML = `<span>${escapeHtml(this._getDateGroupLabel(m.timestamp))}</span>`;
          frag.appendChild(sep);
        }
      }
      frag.appendChild(this.createMessageBubble(m));
    });

    this.dom.chatMessageFeed.appendChild(frag);
    this.dom.chatMessageFeed.scrollTop = this.dom.chatMessageFeed.scrollHeight;
  }

  createMessageBubble(msg) {
    const row = document.createElement("div");
    row.className = `message-bubble-row ${msg.is_outgoing ? "outgoing" : "incoming"}`;
    row.setAttribute("data-msg-id", msg.id || msg.msg_id || "");

    const timeStr = this._formatMessageTimestamp(msg.timestamp);
    const sender = msg.is_outgoing ? (window.I18n ? window.I18n.t('common.you') : "Tú") : (msg.sender_name || msg.sender || (window.I18n ? window.I18n.t('common.anonymous') : "Anónimo"));

    const text = msg.text || "";

    // 1. Detección de URIs oficiales de MeshCore (Compartir Contacto o Canal)
    let richCardHtml = "";
    let cleanDisplayText = text;
    const meshcoreUriMatch = text.match(/meshcore:\/\/[^\s]+/i);
    let parsedUri = null;

    if (meshcoreUriMatch) {
      const rawUri = meshcoreUriMatch[0];
      parsedUri = parseMeshCoreUri(rawUri);
      if (parsedUri) {
        cleanDisplayText = text.replace(rawUri, "").trim();

        if (parsedUri.type === "contact") {
          const cName = parsedUri.name || "Contacto MeshCore";
          const cRole = parsedUri.role || "CLIENT";
          const cPk = parsedUri.public_key || "";
          const isKnown = this.ctx.knownNodes?.has(cPk.toLowerCase());

          richCardHtml = `
            <div class="chat-contact-card" data-pk="${escapeHtml(cPk)}">
              <div class="card-top-row">
                <div class="card-avatar">👤</div>
                <div class="card-info">
                  <span class="card-name">${escapeHtml(cName)}</span>
                  <span class="card-sub"><span class="badge-pill">${escapeHtml(cRole)}</span> <span class="card-key-mono">${escapeHtml(cPk.slice(0, 10))}…</span></span>
                </div>
              </div>
              <button type="button" class="card-action-btn btn-save-shared-contact ${isKnown ? 'btn-saved' : ''}" data-pk="${escapeHtml(cPk)}" data-name="${escapeHtml(cName)}" data-role="${escapeHtml(cRole)}" ${isKnown ? 'disabled' : ''}>
                <span data-lucide="${isKnown ? 'check' : 'user-plus'}" data-size="13"></span>
                <span>${isKnown ? (window.I18n ? window.I18n.t('chat.saved_contact') : '✓ Contacto Guardado') : (window.I18n ? window.I18n.t('chat.save_contact') : 'Guardar en Contactos')}</span>
              </button>
            </div>
          `;
        } else if (parsedUri.type === "channel") {
          const chName = parsedUri.name || "Canal Compartido";
          const chIdx = parsedUri.index !== null && parsedUri.index !== undefined ? parsedUri.index : "?";
          const isEnc = Boolean(parsedUri.secret && parsedUri.secret.length > 0 && parsedUri.secret !== MESHCORE_PUBLIC_CHANNEL_SECRET);

          richCardHtml = `
            <div class="chat-channel-card" data-idx="${chIdx}">
              <div class="card-top-row">
                <div class="card-avatar">${isEnc ? "🔒" : "📻"}</div>
                <div class="card-info">
                  <span class="card-name">${escapeHtml(chName)} (Canal #${chIdx})</span>
                  <span class="card-sub">${isEnc ? "🔒 Canal Privado Cifrado" : "📢 Canal Abierto Broadcast"}</span>
                </div>
              </div>
              <button type="button" class="card-action-btn btn-join-shared-channel" data-name="${escapeHtml(chName)}" data-secret="${escapeHtml(parsedUri.secret || '')}" data-idx="${chIdx}">
                <span data-lucide="radio" data-size="13"></span>
                <span>${window.I18n ? window.I18n.t('chat.join_channel') : 'Unirse al Canal'}</span>
              </button>
            </div>
          `;
        }
      }
    }

    // 2. Detección de coordenadas GPS en el texto
    const gpsMatch = cleanDisplayText.match(/(-?\d{1,3}\.\d{3,7}),\s*(-?\d{1,3}\.\d{3,7})/);
    let locationCardHtml = "";
    let detectedLat = null;
    let detectedLon = null;

    if (gpsMatch) {
      detectedLat = parseFloat(gpsMatch[1]);
      detectedLon = parseFloat(gpsMatch[2]);
      if (!isNaN(detectedLat) && !isNaN(detectedLon)) {
        locationCardHtml = `
          <div class="chat-location-card">
            <div class="loc-card-header">
              <span>📍</span> <strong>${window.I18n ? window.I18n.t('chat.gps_shared') : 'Ubicación GPS Compartida'}</strong>
            </div>
            <div class="loc-coords-badge">${detectedLat.toFixed(5)}, ${detectedLon.toFixed(5)}</div>
            <button type="button" class="btn-view-on-map" data-lat="${detectedLat}" data-lon="${detectedLon}">
              <span data-lucide="map-pin" data-size="12"></span> ${window.I18n ? window.I18n.t('chat.view_map') : 'Ver en Mapa'}
            </button>
          </div>
        `;
      }
    }

    // 3. Indicador de entrega estilo WhatsApp (Checkmarks)
    let ackHtml = "";
    if (msg.is_outgoing) {
      if (msg.delivered) {
        ackHtml = `<span class="ack-indicator ack-delivered" title="${window.I18n ? window.I18n.t('chat.delivered') : 'Entregado'}">✓✓</span>`;
      } else if (msg.status === "sent") {
        ackHtml = `<span class="ack-indicator ack-sent" title="${window.I18n ? window.I18n.t('chat.sent') : 'Transmitido'}">✓</span>`;
      } else {
        ackHtml = `<span class="ack-indicator ack-queued" title="${window.I18n ? window.I18n.t('chat.queued') : 'En cola'}">✓</span>`;
      }
    }

    // 4. Construcción de la burbuja WhatsApp
    const showSender = !msg.is_outgoing && !this.activeDmTarget;
    row.innerHTML = `
      <div class="msg-bubble message-bubble">
        ${showSender ? `<span class="msg-sender">${escapeHtml(sender)}</span>` : ""}
        ${cleanDisplayText ? `<div class="msg-text">${escapeHtml(cleanDisplayText)}</div>` : ""}
        ${richCardHtml}
        ${locationCardHtml}
        <div class="msg-footer">
          <span class="msg-time">${escapeHtml(timeStr)}</span>
          ${ackHtml}
        </div>
      </div>
    `;

    // 5. Cableado de interactividad en tarjetas
    if (parsedUri?.type === "contact") {
      const btnSave = row.querySelector(".btn-save-shared-contact");
      if (btnSave && !btnSave.classList.contains("btn-saved")) {
        btnSave.addEventListener("click", async () => {
          const pk = btnSave.getAttribute("data-pk");
          const name = btnSave.getAttribute("data-name");
          const role = btnSave.getAttribute("data-role") || "CLIENT";
          try {
            const res = await fetch("/api/contacts", {
              method: "POST",
              headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
              body: JSON.stringify({ public_key: pk, name, role }),
            });
            if (res.ok) {
              btnSave.classList.add("btn-saved");
              btnSave.disabled = true;
              btnSave.innerHTML = `<span>✓ ${window.I18n ? window.I18n.t('chat.saved_contact') : 'Contacto Guardado'}</span>`;
              if (this.ctx.showToast) this.ctx.showToast(`Contacto ${name} guardado con éxito`, "success");
            }
          } catch (e) {
            console.warn("Error guardando contacto compartido:", e);
          }
        });
      }
    }

    if (parsedUri?.type === "channel") {
      const btnJoin = row.querySelector(".btn-join-shared-channel");
      if (btnJoin) {
        btnJoin.addEventListener("click", () => {
          const idx = parseInt(btnJoin.getAttribute("data-idx"), 10);
          if (!isNaN(idx) && idx >= 0) {
            this.switchChannel(idx);
            if (this.ctx.showToast) this.ctx.showToast(`Cambiado al Canal #${idx}`, "info");
          } else {
            const navBtn = document.querySelector('.nav-btn[data-tab="tab-settings"]');
            if (navBtn) navBtn.click();
          }
        });
      }
    }

    if (gpsMatch && detectedLat !== null && detectedLon !== null) {
      const btnViewMap = row.querySelector(".btn-view-on-map");
      if (btnViewMap) {
        btnViewMap.addEventListener("click", () => {
          const navBtn = document.querySelector('.nav-btn[data-tab="tab-map"]');
          if (navBtn) navBtn.click();
          if (this.ctx.centerMapOnCoords) {
            this.ctx.centerMapOnCoords(detectedLat, detectedLon, 14);
          } else if (this.ctx.eventBus) {
            this.ctx.eventBus.emit("CENTER_MAP_COORDS", { lat: detectedLat, lon: detectedLon, zoom: 14 });
          }
        });
      }
    }

    if (window.initLucideIcons) {
      window.initLucideIcons(row);
    }

    return row;
  }

  async sendMessage() {
    const rawInput = this.dom.chatInputText ? this.dom.chatInputText.value.trim() : "";
    if (!rawInput) return;

    // Validación estricta del límite físico/lógico de trama LoRa (160 bytes UTF-8)
    const byteLen = getUtf8ByteLength(rawInput);
    if (byteLen > MAX_LORA_TEXT_BYTES) {
      if (this.ctx.showToast) {
        this.ctx.showToast(
          `El mensaje excede el límite de transmisión LoRa (${byteLen}/${MAX_LORA_TEXT_BYTES} bytes). Reduce el texto o emoticones.`,
          "warning"
        );
      }
      return;
    }

    if (this.dom.chatInputText) this.dom.chatInputText.value = "";
    this.updateCharCounter();

    const msgId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    const canonicalTarget = this.activeDmTarget ? this.resolveCanonicalPubkey(this.activeDmTarget) : null;

    if (canonicalTarget) {
      const normTarget = canonicalTarget.toLowerCase().trim();
      const localPk = (document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();
      if (normTarget === "local" || (localPk && (normTarget === localPk || normTarget.startsWith(localPk) || localPk.startsWith(normTarget)))) {
        if (this.ctx.showToast) this.ctx.showToast("No se puede enviar mensajes de chat hacia el nodo local", "warning");
        return;
      }
      const targetNode = (this.ctx.knownNodes ? Array.from(this.ctx.knownNodes.values()) : []).find(
        (n) => (n.public_key && n.public_key.toLowerCase() === normTarget) ||
               (n.key_prefix && normTarget.startsWith(n.key_prefix.toLowerCase()))
      );
      const roleUpper = String(targetNode?.role || "").toUpperCase();
      if (roleUpper === "REPEATER" || roleUpper === "ROUTER") {
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.repeater_chat_err'), "warning");
        return;
      }
    }

    const target = canonicalTarget || "broadcast";

    const outgoingMsg = {
      id: msgId,
      msg_id: msgId,
      sender: "local",
      sender_name: window.I18n ? window.I18n.t('common.local_station') : "Estación Local",
      text: rawInput,
      is_outgoing: true,
      channel_idx: this.activeChannelIdx,
      dm_target: canonicalTarget,
      dm_target_name: this.activeDmName || canonicalTarget,
      timestamp: new Date().toISOString(),
      delivered: false,
      status: "queued",
    };

    const feedKey = canonicalTarget ? `dm_${canonicalTarget}` : `ch_${this.activeChannelIdx}`;
    if (!this.channelFeeds.has(feedKey)) this.channelFeeds.set(feedKey, []);
    const feed = this.channelFeeds.get(feedKey);
    feed.push(outgoingMsg);
    if (feed.length > MAX_FEED_MESSAGES) feed.shift();

    if (this.ctx.storage) {
      this.ctx.storage.saveMessage(feedKey, outgoingMsg);
    }

    this.appendChatMessage(outgoingMsg);

    try {
      const res = await fetch("/api/tx", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({
          to: target,
          channel_index: this.activeChannelIdx,
          text: rawInput,
          request_id: msgId,
        }),
      });
      const txData = await res.json();
      if (res.ok && txData && txData.status === "ok") {
        outgoingMsg.status = "sent";
        const row = this.dom.chatMessageFeed?.querySelector(`.message-bubble-row[data-msg-id="${msgId}"]`);
        if (row) {
          const indicator = row.querySelector(".ack-indicator");
          if (indicator && !outgoingMsg.delivered) {
            indicator.className = "ack-indicator ack-sent";
            indicator.textContent = "✓";
            indicator.title = window.I18n ? window.I18n.t('chat.sent') : "Transmitido";
          }
        }
      }
    } catch (e) {
      console.warn("Error transmitiendo mensaje:", e);
    }
  }

  appendChatMessage(msg) {
    if (!this.dom.chatMessageFeed) return;
    const emptyState = this.dom.chatMessageFeed.querySelector(".chat-empty-state");
    if (emptyState) emptyState.remove();

    // Comprobar si se necesita un nuevo separador de fecha estilo WhatsApp
    if (msg.timestamp) {
      const msgDateStr = new Date(msg.timestamp).toDateString();
      const lastBubble = this.dom.chatMessageFeed.querySelector(".message-bubble-row:last-child");
      let needSep = false;
      if (!lastBubble) {
        needSep = true;
      } else {
        const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
        const feed = this.channelFeeds.get(feedKey) || [];
        if (feed.length >= 2) {
          const prevMsg = feed[feed.length - 2];
          if (prevMsg?.timestamp && new Date(prevMsg.timestamp).toDateString() !== msgDateStr) {
            needSep = true;
          }
        }
      }
      if (needSep) {
        const sep = document.createElement("div");
        sep.className = "chat-date-separator";
        sep.innerHTML = `<span>${escapeHtml(this._getDateGroupLabel(msg.timestamp))}</span>`;
        this.dom.chatMessageFeed.appendChild(sep);
      }
    }

    const bubble = this.createMessageBubble(msg);
    this.dom.chatMessageFeed.appendChild(bubble);
    this.dom.chatMessageFeed.scrollTop = this.dom.chatMessageFeed.scrollHeight;
  }

  async handleIncomingChatMessage(payload) {
    const rawText = payload.text || payload.message || "";
    const senderKey = payload.from || payload.sender || payload.public_key || "unknown";
    const canonicalSender = this.resolveCanonicalPubkey(senderKey);
    const { senderName, cleanText } = extractSenderAndText(rawText, payload.sender_name || payload.name);

    const isDm = payload.is_direct || payload.type === "direct" || payload.type === "DIRECT_MSG";
    const feedKey = isDm ? `dm_${canonicalSender}` : `ch_${payload.channel_idx ?? payload.channel ?? 0}`;

    let safeIsoTimestamp = new Date().toISOString();
    if (payload.timestamp) {
      if (typeof payload.timestamp === "number") {
        safeIsoTimestamp = new Date(payload.timestamp < 1e11 ? payload.timestamp * 1000 : payload.timestamp).toISOString();
      } else if (typeof payload.timestamp === "string") {
        const d = new Date(payload.timestamp);
        safeIsoTimestamp = isNaN(d.getTime()) ? new Date().toISOString() : d.toISOString();
      }
    }

    const newMsg = {
      id: payload.msg_id || `rx_${Date.now()}`,
      sender: canonicalSender,
      sender_name: senderName,
      text: cleanText,
      is_outgoing: false,
      channel_idx: payload.channel_idx ?? 0,
      timestamp: safeIsoTimestamp,
      delivered: true,
      status: "received",
    };

    if (!this.channelFeeds.has(feedKey)) this.channelFeeds.set(feedKey, []);
    const feed = this.channelFeeds.get(feedKey);
    feed.push(newMsg);
    if (feed.length > MAX_FEED_MESSAGES) feed.shift();

    if (this.ctx.storage) {
      this.ctx.storage.saveMessage(feedKey, newMsg);
    }

    if (isDm) {
      this.conversationsWithMessages.add(canonicalSender);
      if (this.closedDmThreads.has(canonicalSender)) {
        this.closedDmThreads.delete(canonicalSender);
        this._saveClosedDmThreads();
      }
      this.addDmContact(canonicalSender, senderName);
    }

    const currentFeed = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    if (feedKey === currentFeed) {
      this.appendChatMessage(newMsg);
    }

    if (this.chatSoundEnabled) {
      this.playNotificationChime();
    }
  }

  handleDeliveryAck(payload) {
    const msgId = payload.msg_id;
    if (!msgId) return;

    const row = this.dom.chatMessageFeed?.querySelector(`.message-bubble-row[data-msg-id="${msgId}"]`);
    if (row) {
      const indicator = row.querySelector(".ack-indicator");
      if (indicator) {
        indicator.textContent = "✓✓";
        indicator.className = "ack-indicator ack-delivered";
        indicator.title = window.I18n ? window.I18n.t('chat.delivered') : "Entregado";
      }
    }

    if (this.ctx.storage) {
      this.ctx.storage.updateMessageDelivery(msgId, payload.ack_code, payload.trip_time_ms);
    }
  }

  playNotificationChime() {
    if (!this.chatSoundEnabled) return;
    try {
      const AudioCtx = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtx) return;
      if (!this._audioCtx) this._audioCtx = new AudioCtx();
      if (this._audioCtx.state === "suspended") this._audioCtx.resume();

      const now = this._audioCtx.currentTime;
      const osc = this._audioCtx.createOscillator();
      const gain = this._audioCtx.createGain();
      osc.type = "sine";
      osc.frequency.setValueAtTime(880, now);
      gain.gain.setValueAtTime(0.05, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.12);
      osc.connect(gain);
      gain.connect(this._audioCtx.destination);
      osc.start(now);
      osc.stop(now + 0.12);
    } catch (_) {}
  }
}
