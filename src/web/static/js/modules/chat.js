/**
 * ChatModule - Mensajería de texto para canales broadcast, canales cifrados y mensajes directos (DM).
 * Incluye tracking de entrega (ACKs), alertas sonoras y caché IndexedDB del historial SQLite.
 */

import {
  escapeHtml,
  extractSenderAndText,
  isCommandOrSystemText,
  isCommonChatMessage,
  MAX_FEED_MESSAGES,
  buildMeshCoreChannelUri,
  formatMeshCoreContactMessage,
  parseMeshCoreUri,
  getRoleFromNumericType,
  MESHCORE_PUBLIC_CHANNEL_SECRET,
  MAX_LORA_TEXT_BYTES,
  getUtf8ByteLength,
  splitUtf8Message,
  estimateLoraAirtimeMs,
  formatRelativeTime,
  getDateGroupLabel,
  readLocalPreference,
  writeLocalPreference,
} from "../core/utils.js";
import { EVENTS } from "../core/eventbus.js";
import { mergeMessage, messageIdentity } from "../core/storage.js";

export class ChatModule {
  constructor(context) {
    this.ctx = context;
    this.channelFeeds = new Map();
    this._renderGeneration = 0;
    this._feedGenerations = new Map();
    this.activeChannelIdx = 0;
    this.activeDmTarget = null;
    this.activeDmName = null;
    this.pendingOutgoingAcks = new Map();
    this.historyPages = new Map();
    this._historyStates = new Map();
    this._visibleFeedKey = null;
    this._historyAccessDenied = false;
    this.chatSoundEnabled = readLocalPreference("meshcore_chat_sound_enabled") !== "false";
    this._sending = false;
    this._audioCtx = null;
    this.dom = {};

    // Hilos de mensajes directos cerrados/archivados por el usuario
    try {
      const rawClosed = localStorage.getItem("meshcore_closed_dm_threads");
      this.closedDmThreads = new Set(rawClosed ? JSON.parse(rawClosed) : []);
    } catch (_) {
      this.closedDmThreads = new Set();
    }
    this.conversationsWithMessages = new Set();
    this.unreadCounts = new Map();

    // Estado del selector de emojis y compartir
    this.activeEmojiTab = "smileys";
    this.selectedShareContact = null;
    this.selectedShareChannel = null;
    this._sharingChannel = false;
    this._shareChannelSession = 0;
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
    this._bindComposerPopoverSizing();
    this._subscribeBus();
    window.addEventListener("meshcore:station_changed", () => {
      this.channelFeeds.clear();
      this.historyPages.clear();
      this._historyStates.clear();
      this._visibleFeedKey = null;
      this.pendingOutgoingAcks.clear();
      if (this.dom.dmListUi) this.dom.dmListUi.textContent = "";
      if (this.dom.dmCountBadge) this.dom.dmCountBadge.textContent = "0";
      this._paintConversation(this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`);
    });
    window.addEventListener("meshcore:credentials_changed", () => {
      this._clearProtectedHistory();
      this.loadInitialHistory();
    });
    window.addEventListener("meshcore:history_access_denied", () => {
      this._clearProtectedHistory();
      const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
      this._historyStates.set(feedKey, "auth");
      this._paintConversation(feedKey);
    });
    window.addEventListener("meshcore:history_imported", () => this.loadInitialHistory());
    window.addEventListener("meshcore:cache_cleared", () => {
      ++this._renderGeneration;
      this.channelFeeds.clear();
      this.historyPages.clear();
      this._historyStates.clear();
      this._visibleFeedKey = null;
      this._paintConversation(this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`);
    });
    this.loadInitialHistory();
    this._renderEmojiGrid("smileys");
    this.updateCharCounter();
    this._updateActiveChatHeader();
    if (window.innerWidth <= 900 && this.dom.sidebarChannelList) {
      this.dom.sidebarChannelList.classList.add("mobile-open");
    }
  }

  onLanguageChange() {
    this._updateActiveChatHeader();
    this.updateCharCounter();
    this._syncConversationSelection();
    this.dom.dmListUi?.querySelectorAll(".channel-item").forEach((item) => {
      this._updateDmCloseLabel(item);
    });
    this._paintConversation(this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`, { preserveScroll: true });
    if (this.dom.modalShareContact && !this.dom.modalShareContact.classList.contains('hidden')) {
      this._populateShareContactList(this.dom.shareContactSearch?.value || '');
    }
    if (this.dom.modalShareChannel && !this.dom.modalShareChannel.classList.contains('hidden')) {
      this._populateShareChannelList();
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
      chatTargetAvatar: document.getElementById("chatTargetAvatar"),
      btnBackToChannelsMobile: document.getElementById("btnBackToChannelsMobile"),
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

    // Selector de Emojis
    if (this.dom.btnEmojiPicker && this.dom.emojiPickerPopover) {
      this.dom.btnEmojiPicker.addEventListener("click", (e) => {
        e.stopPropagation();
        this._toggleComposerPopover("emoji");
      });
    }

    // Pestañas de categorías de Emojis
    document.querySelectorAll(".emoji-tab").forEach((tab) => {
      tab.addEventListener("click", (e) => {
        e.stopPropagation();
        const cat = tab.getAttribute("data-tab") || "smileys";
        this.activeEmojiTab = cat;
        tab.focus({ preventScroll: true });
        this._renderEmojiGrid(cat);
      });
    });

    // Menú flotante de adjuntos
    if (this.dom.btnChatAttach && this.dom.chatAttachMenu) {
      this.dom.btnChatAttach.addEventListener("click", (e) => {
        e.stopPropagation();
        this._toggleComposerPopover("attach");
      });
    }

    if (this.dom.attachOptionLocation) {
      this.dom.attachOptionLocation.addEventListener("click", () => {
        this._closeComposerPopovers({ restoreFocus: true });
        this.shareCurrentLocation();
      });
    }

    if (this.dom.attachOptionContact) {
      this.dom.attachOptionContact.addEventListener("click", () => {
        this._closeComposerPopovers({ restoreFocus: true });
        this.openShareContactModal();
      });
    }

    if (this.dom.attachOptionChannel) {
      this.dom.attachOptionChannel.addEventListener("click", () => {
        this._closeComposerPopovers({ restoreFocus: true });
        this.openShareChannelModal();
      });
    }

    // Cerrar menús flotantes al hacer clic en cualquier otra parte
    document.addEventListener("click", (event) => {
      const open = this._getOpenComposerPopover();
      if (open && !open.panel.contains(event.target) && !open.trigger.contains(event.target)) {
        this._closeComposerPopovers({ restoreFocus: open.panel.contains(document.activeElement) });
      }
    });
    document.addEventListener("focusin", (event) => {
      const open = this._getOpenComposerPopover();
      if (open && !open.panel.contains(event.target) && !open.trigger.contains(event.target)) {
        this._closeComposerPopovers();
      }
    });
    document.addEventListener("keydown", (event) => {
      const open = this._getOpenComposerPopover();
      if (event.key !== "Escape" || event.defaultPrevented || !open) return;
      if (!open.panel.contains(event.target) && !open.trigger.contains(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      this._closeComposerPopovers({ restoreFocus: true });
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
        writeLocalPreference("meshcore_chat_sound_enabled", this.chatSoundEnabled);
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
        return;
      }

      if (evType === "contact_discovered" || evType === "contact_updated" || evType === "contacts_updated") {
        this.refreshDmNamesFromKnownNodes();
      }
    });
  }

  async loadInitialHistory() {
    if (!this.ctx.storage) return;
    await this.renderCurrentConversation();
    if (this._historyAccessDenied) return;
    const generation = this._renderGeneration;
    const authGeneration = this.ctx.storage.authGeneration;

    try {
      const localPk = (this.ctx.localNodePubkey || (typeof document !== "undefined" ? document.getElementById("localNodePubkey")?.value : "") || "").toLowerCase().trim();
      const dmThreads = await this.ctx.storage.getDmConversations(localPk);
      if (generation !== this._renderGeneration || authGeneration !== this.ctx.storage.authGeneration) return;
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
    } catch (error) {
      if (generation !== this._renderGeneration || authGeneration !== this.ctx.storage.authGeneration) return;
      if (error.authRequired || error.status === 401 || error.status === 403) {
        this._clearProtectedHistory();
        this._historyAccessDenied = true;
        const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
        this._historyStates.set(feedKey, "auth");
        this._paintConversation(feedKey);
      }
      console.warn("Conversation history unavailable:", error);
    }
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
    this.dom.emojiPickerPopover?.querySelectorAll(".emoji-tab").forEach((tab) => {
      const selected = tab.dataset.tab === category;
      tab.classList.toggle("active", selected);
      tab.setAttribute("aria-pressed", String(selected));
    });
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

  _composerPopovers() {
    return [
      { name: "emoji", panel: this.dom.emojiPickerPopover, trigger: this.dom.btnEmojiPicker },
      { name: "attach", panel: this.dom.chatAttachMenu, trigger: this.dom.btnChatAttach },
    ].filter(({ panel, trigger }) => panel && trigger);
  }

  _getOpenComposerPopover() {
    return this._composerPopovers().find(({ panel }) => !panel.hidden && !panel.classList.contains("hidden"));
  }

  _bindComposerPopoverSizing() {
    const update = () => this._fitComposerPopover();
    if (typeof ResizeObserver !== "undefined") this._popoverResizeObserver = new ResizeObserver(update);
    window.addEventListener("resize", update);
    window.visualViewport?.addEventListener("resize", update);
    window.visualViewport?.addEventListener("scroll", update);
  }

  _fitComposerPopover() {
    const open = this._getOpenComposerPopover();
    if (!open || open.panel.inert) return;
    const wrapper = open.panel.closest(".chat-composer-wrapper");
    const conversation = wrapper?.closest(".chat-conversation-panel");
    if (!wrapper || !conversation || conversation.closest("[inert], [hidden]") || !conversation.getClientRects().length) return;
    const wrapperRect = wrapper.getBoundingClientRect();
    const conversationRect = conversation.getBoundingClientRect();
    const viewport = window.visualViewport;
    const viewportTop = viewport?.offsetTop || 0;
    const viewportBottom = viewportTop + (viewport?.height || window.innerHeight);
    const top = Math.max(conversationRect.top, viewportTop);
    const bottom = Math.min(wrapperRect.top - 8, viewportBottom - 8);
    open.panel.style.setProperty("--chat-popover-space", `${Math.max(0, bottom - top)}px`);
    open.panel.style.setProperty("--chat-popover-lift", `${Math.max(0, wrapperRect.top - viewportBottom)}px`);
  }

  _closeComposerPopovers({ restoreFocus = false } = {}) {
    const open = this._getOpenComposerPopover();
    this._popoverResizeObserver?.disconnect();
    this._composerPopovers().forEach(({ panel, trigger }) => {
      panel.classList.add("hidden");
      panel.hidden = true;
      panel.inert = true;
      trigger.setAttribute("aria-expanded", "false");
    });
    if (restoreFocus) open?.trigger.focus();
  }

  _toggleComposerPopover(name) {
    const current = this._getOpenComposerPopover();
    this._closeComposerPopovers();
    if (current?.name === name) return;
    const next = this._composerPopovers().find((entry) => entry.name === name);
    if (!next || next.trigger.closest("[inert], [hidden]") || !next.trigger.getClientRects().length) return;
    next.panel.hidden = false;
    next.panel.inert = false;
    next.panel.classList.remove("hidden");
    this._fitComposerPopover();
    const wrapper = next.panel.closest(".chat-composer-wrapper");
    const conversation = wrapper?.closest(".chat-conversation-panel");
    if (wrapper) this._popoverResizeObserver?.observe(wrapper);
    if (conversation) this._popoverResizeObserver?.observe(conversation);
    next.trigger.setAttribute("aria-controls", next.panel.id);
    next.trigger.setAttribute("aria-expanded", "true");
    const initialFocus = next.panel.querySelector('.emoji-tab[aria-pressed="true"]') || next.panel.querySelector("button:not(:disabled)");
    initialFocus?.focus();
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
    this._closeComposerPopovers();
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
  }

  closeShareContactModal() {
    if (this.dom.modalShareContact) this.dom.modalShareContact.classList.add("hidden");
    this.selectedShareContact = null;
  }

  _populateShareContactList(filterQuery = "") {
    if (!this.dom.shareContactList) return;
    const focusKey = this._getPickerFocusKey(this.dom.shareContactList);
    this.dom.shareContactList.innerHTML = "";
    const q = (filterQuery || "").toLowerCase().trim();

    // SSoT: Obtener nodos cliente exclusivamente (excluir REPEATER)
    const allNodes = this.ctx.knownNodes ? Array.from(this.ctx.knownNodes.values()) : [];
    const localPk = (this.ctx.localNodePubkey || document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();
    const localName = (document.getElementById("localNodeName")?.value || "").trim() || I18n.t("chat.local_name");

    // Mi Contacto (Estación Local)
    const myContact = (localPk && localPk !== "local" && localPk !== "000000000000") ? {
      public_key: localPk,
      name: `${localName} (${window.I18n ? window.I18n.t('chat.my_contact') : 'Mi Contacto'})`,
      alias: localName,
      role: "CLIENT",
      is_my_contact: true,
    } : null;

    const clientContacts = allNodes.filter((n) => {
      if (!n || !n.public_key) return false;
      const pk = n.public_key.toLowerCase().trim();
      // Excluir nodo local de los contactos remotos (se incluye explícitamente arriba como myContact)
      if (pk === "local" || (localPk && (pk === localPk || pk.startsWith(localPk.slice(0, 8)))) || n.is_local) return false;
      const roleUpper = String(n.role || "").toUpperCase();
      if (roleUpper === "REPEATER" || roleUpper === "ROUTER") return false;
      if (q) {
        const name = (n.name || n.alias || "").toLowerCase();
        return name.includes(q) || pk.includes(q);
      }
      return true;
    });

    // Si coincide con la búsqueda o la búsqueda está vacía, anteponer Mi Contacto al inicio
    if (myContact) {
      const matchMyContact = !q || "mi contacto".includes(q) || localName.toLowerCase().includes(q) || localPk.includes(q);
      if (matchMyContact) {
        clientContacts.unshift(myContact);
      }
    }

    if (clientContacts.length === 0) {
      this.dom.shareContactList.innerHTML = `
        <div class="empty-state text-center text-muted p-3 small">
          ${q ? I18n.t("chat.contacts_no_match", { p0: escapeHtml(q) }) : I18n.t("chat.no_contacts_share")}
        </div>
      `;
      this._restorePickerFocus(this.dom.shareContactList, focusKey);
      return;
    }

    const frag = document.createDocumentFragment();
    clientContacts.forEach((contact) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "share-picker-item";
      item.dataset.shareKey = contact.public_key;
      const isMyContact = Boolean(contact.is_my_contact);
      const cleanName = contact.name || contact.alias || contact.public_key.slice(0, 8);
      const isSelected = this.selectedShareContact?.public_key === contact.public_key;
      if (isSelected) item.classList.add("selected");
      item.setAttribute("aria-pressed", String(isSelected));

      item.innerHTML = `
        <span class="share-picker-left">
          <span class="share-picker-avatar" aria-hidden="true">${isMyContact ? "⭐" : "👤"}</span>
          <span>
            <span class="share-picker-title">${escapeHtml(cleanName)}</span>
            <span class="share-picker-sub">${escapeHtml(contact.public_key.slice(0, 14))}… • ${isMyContact ? (window.I18n ? window.I18n.t('chat.my_station_sub') : "Mi Estación Local") : escapeHtml(contact.role || "CLIENT")}</span>
          </span>
        </span>
        <span class="badge-pill ${isMyContact ? 'badge-primary' : ''}">${isMyContact ? (window.I18n ? window.I18n.t('chat.my_contact_badge') : "Mi Contacto") : (contact.is_favorite ? "⭐" : I18n.t("chat.contact"))}</span>
      `;

      item.addEventListener("click", () => {
        this._selectPickerItem(this.dom.shareContactList, item);
        this.selectedShareContact = contact;
        if (this.dom.btnConfirmShareContact) this.dom.btnConfirmShareContact.disabled = false;
      });

      frag.appendChild(item);
    });

    this.dom.shareContactList.appendChild(frag);
    this._restorePickerFocus(this.dom.shareContactList, focusKey);
  }

  _getPickerFocusKey(list) {
    const focused = document.activeElement;
    return list.contains(focused) ? focused?.dataset.shareKey : null;
  }

  _restorePickerFocus(list, key) {
    if (key == null) return;
    const replacement = Array.from(list.querySelectorAll(".share-picker-item"))
      .find((item) => item.dataset.shareKey === key);
    if (replacement) replacement.focus({ preventScroll: true });
    else {
      const fallback = list === this.dom.shareContactList
        ? this.dom.shareContactSearch
        : this.dom.btnCancelShareChannel;
      fallback?.focus({ preventScroll: true });
    }
  }

  _selectPickerItem(list, selected) {
    list.querySelectorAll(".share-picker-item").forEach((item) => {
      item.classList.toggle("selected", item === selected);
      item.setAttribute("aria-pressed", String(item === selected));
    });
  }

  filterShareContactList(query) {
    this._populateShareContactList(query);
  }

  async confirmShareContact() {
    if (!this.selectedShareContact) return;
    const c = this.selectedShareContact;
    const shareName = c.is_my_contact ? (c.alias || (document.getElementById("localNodeName")?.value || "").trim() || I18n.t("chat.my_node")) : (c.name || c.alias || I18n.t("chat.contact"));
    const contactMsg = formatMeshCoreContactMessage(shareName, c.public_key, "CLIENT");
    this.closeShareContactModal();
    await this.sendMessageWithText(contactMsg);
  }

  openShareChannelModal() {
    if (!this.dom.modalShareChannel || this._sharingChannel) return;
    ++this._shareChannelSession;

    const rawList = this.ctx.channelsList || this.ctx.settingsModule?.channelsList || [];
    // REGLA SSoT: El canal 0 (Public / Broadcast) es universal y todos los nodos ya lo tienen.
    // NUNCA permitir compartir el canal público. Solo compartir canales privados/cifrados (índice >= 1).
    const chList = rawList.filter((ch) => Number(ch.index) > 0);

    if (chList.length === 0) {
      if (this.ctx.showToast) {
        this.ctx.showToast(window.I18n ? window.I18n.t('chat.no_channels_to_share') : "No hay canales que compartir", "info");
      }
      return;
    }

    this.selectedShareChannel = null;
    if (this.dom.btnConfirmShareChannel) this.dom.btnConfirmShareChannel.disabled = true;
    this._populateShareChannelList();
    this.dom.modalShareChannel.classList.remove("hidden");
  }

  closeShareChannelModal() {
    ++this._shareChannelSession;
    this._shareChannelAbort?.abort();
    if (this.dom.modalShareChannel) this.dom.modalShareChannel.classList.add("hidden");
    this.selectedShareChannel = null;
  }

  _populateShareChannelList() {
    if (!this.dom.shareChannelList) return;
    const focusKey = this._getPickerFocusKey(this.dom.shareChannelList);
    this.dom.shareChannelList.innerHTML = "";

    const rawList = this.ctx.channelsList || this.ctx.settingsModule?.channelsList || [];
    // REGLA SSoT: El canal 0 (Public / Broadcast) es universal y todos los nodos ya lo tienen.
    // NUNCA permitir compartir el canal público. Solo compartir canales privados/cifrados (índice >= 1).
    const chList = rawList.filter((ch) => Number(ch.index) > 0);

    if (chList.length === 0) {
      const emptyDiv = document.createElement("div");
      emptyDiv.className = "share-picker-empty text-center text-muted p-4 small";
      emptyDiv.innerHTML = `
        <div class="chat-empty-icon">📻</div>
        <strong>${I18n.t("chat.no_private_channels")}</strong>
        <p class="chat-empty-subtext">
          ${I18n.t("chat.public_channel_help")}
        </p>
      `;
      this.dom.shareChannelList.appendChild(emptyDiv);
      if (this.dom.btnConfirmShareChannel) this.dom.btnConfirmShareChannel.disabled = true;
      this._restorePickerFocus(this.dom.shareChannelList, focusKey);
      return;
    }

    const frag = document.createDocumentFragment();
    chList.forEach((ch) => {
      const item = document.createElement("button");
      item.type = "button";
      item.className = "share-picker-item";
      item.dataset.shareKey = String(ch.index);
      const isSelected = String(this.selectedShareChannel?.index) === String(ch.index);
      item.classList.toggle("selected", isSelected);
      item.setAttribute("aria-pressed", String(isSelected));
      const chName = ch.name || I18n.t("chat.channel_name", { p0: ch.index });
      const isEncrypted = Boolean(ch.is_encrypted ?? (ch.has_psk || (ch.psk && ch.psk.trim().length > 0 && ch.psk !== MESHCORE_PUBLIC_CHANNEL_SECRET)));

      item.innerHTML = `
        <span class="share-picker-left">
          <span class="share-picker-avatar" aria-hidden="true">${isEncrypted ? "🔒" : "📻"}</span>
          <span>
            <span class="share-picker-title">${escapeHtml(chName)}</span>
            <span class="share-picker-sub">${I18n.t('chat.index', { index: ch.index })} • ${isEncrypted ? I18n.t("chat.private_encrypted") : I18n.t("chat.open_secondary")}</span>
          </span>
        </span>
        <span class="badge-pill">${isEncrypted ? I18n.t('chat.encrypted_badge') : I18n.t('chat.open_badge')}</span>
      `;

      item.addEventListener("click", () => {
        if (this._sharingChannel) return;
        this._selectPickerItem(this.dom.shareChannelList, item);
        this.selectedShareChannel = ch;
        if (this.dom.btnConfirmShareChannel) this.dom.btnConfirmShareChannel.disabled = false;
      });

      frag.appendChild(item);
    });

    this.dom.shareChannelList.appendChild(frag);
    this._restorePickerFocus(this.dom.shareChannelList, focusKey);
  }

  async confirmShareChannel() {
    if (!this.selectedShareChannel) return;
    const ch = this.selectedShareChannel;
    let secret = String(ch.psk || ch.secret || "").trim();
    const isPublic = (ch.name || "").toLowerCase() === "public" || ch.index === 0;

    // Si es un canal privado y la clave está enmascarada, intentar obtenerla de /api/channels/export
    if (!isPublic && (!secret || secret.includes("•") || secret === "••••••••")) {
      try {
        const headers = this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders() : {};
        const exportUrl = ch.index != null ? `/api/channels/export?index=${encodeURIComponent(ch.index)}` : "/api/channels/export";
        const res = await fetch(exportUrl, { headers });
        if (res.ok) {
          const exportData = await res.json();
          let rawPsk = String(exportData.data?.secret || exportData.secret || "").trim();
          if (!rawPsk || rawPsk.includes("•")) {
            const list = Array.isArray(exportData) ? exportData : (exportData.channels || []);
            const found = list.find((c) => Number(c.index) === Number(ch.index) || c.name === ch.name);
            if (found) {
              rawPsk = String(found.psk || found.secret || "").trim();
            }
          }
          if (rawPsk && !rawPsk.includes("•")) {
            secret = rawPsk;
          }
        }
      } catch (_) {}
    }

    if (!isPublic && (!secret || secret.includes("•"))) {
      const alertMsg = I18n.t("chat.protected_channel_alert") || I18n.t("chat.protected_channel");
      if (this.ctx.showAlert) {
        await this.ctx.showAlert(alertMsg, {
          title: I18n.t("modal.warning") || "Advertencia",
          type: "warning",
        });
      } else if (this.ctx.showToast) {
        this.ctx.showToast(alertMsg, "warning");
      }
      return;
    }

    // Protección de seguridad (OpSec): Advertir si se comparte una clave privada en el canal público (Canal 0)
    if (!isPublic && secret && !this.activeDmTarget && Number(this.activeChannelIdx) === 0) {
      const confirmWarning = (window.I18n ? window.I18n.t("chat.warn_share_psk_public") : null) ||
        `⚠️ ADVERTENCIA DE SEGURIDAD:\n\nEstás a punto de compartir la clave secreta (PSK) de un canal privado en el CANAL PÚBLICO (Broadcast #0).\nCualquier nodo que reciba este mensaje podrá descifrar y unirse a este canal.\n\n¿Estás seguro de que deseas transmitir esta clave por radio abierta?`;
      const confirmFn = this.ctx?.showConfirm || window?.showConfirm;
      const confirmed = confirmFn
        ? await confirmFn(confirmWarning, {
            title: I18n.t("modal.warning") || "Advertencia de Seguridad",
            isDanger: true,
            confirmText: I18n.t("modal.confirm") || "Transmitir Clave",
          })
        : true;
      if (!confirmed) return;
    }

    const uri = buildMeshCoreChannelUri(ch.name, secret, ch.index);
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
    const chunks = splitUtf8Message(text, MAX_LORA_TEXT_BYTES);
    const charCount = [...text].length;

    // Obtener parámetros RF de modulación en vivo del nodo
    const cfg = this.ctx.localConfig || {};
    const sf = Number(cfg.spreading_factor || cfg.sf || 11);
    const bw = Number(cfg.bandwidth || cfg.bw || 250);
    const cr = Number(cfg.coding_rate || cfg.cr || 5);
    const airtimeMs = chunks.reduce((total, chunk) => total + estimateLoraAirtimeMs(getUtf8ByteLength(chunk), sf, bw, cr), 0);

    // Actualizar texto del badge sin límite forzado
    this.dom.chatCharCounter.textContent = chunks.length > 1 ? `${byteLen} B (${chunks.length} pkts)` : `${byteLen} B`;

    // Tooltip informativo con ocupación estimada de espectro
    this.dom.chatCharCounter.title = chunks.length > 1
      ? I18n.t("chat.fragmented_payload_title", { bytes: byteLen, packets: chunks.length, max: MAX_LORA_TEXT_BYTES, sf, bw, airtime: airtimeMs })
      : I18n.t("chat.payload_title", { p0: byteLen, p1: MAX_LORA_TEXT_BYTES, p2: charCount, p3: sf, p4: bw, p5: airtimeMs });

    // Sin bloqueo ni desactivación del botón de envío por longitud
    this.dom.chatCharCounter.classList.remove("is-warning", "is-danger");
    if (this.dom.btnSendMsg) this.dom.btnSendMsg.disabled = this._sending;
  }





  _updateActiveChatHeader() {
    if (this.activeDmTarget) {
      // Caso Conversación Directa (DM)
      const normTarget = this.activeDmTarget.toLowerCase().trim();
      const node = (this.ctx.knownNodes ? Array.from(this.ctx.knownNodes.values()) : []).find(
        (n) => (n.public_key && n.public_key.toLowerCase() === normTarget) ||
               (n.key_prefix && normTarget.startsWith(n.key_prefix.toLowerCase()))
      );

      const isHexOrFallback = !this.activeDmName ||
        this.activeDmName.toLowerCase() === "unknown" ||
        this.activeDmName.toLowerCase() === "anónimo" ||
        this.activeDmName.toLowerCase() === "anonimo" ||
        this.activeDmName === this.activeDmTarget ||
        this.activeDmName === this.activeDmTarget.slice(0, 8) ||
        this.activeDmName.startsWith("Nodo [") ||
        this.activeDmName.includes(I18n.t("chat.local_name")) ||
        this.activeDmName.includes("Local Station");

      const displayName = (isHexOrFallback && (node?.name || node?.alias))
        ? (node.alias || node.name)
        : (this.activeDmName || node?.alias || node?.name || this.activeDmTarget.slice(0, 8));

      if (this.dom.chatTargetAvatar) {
        this.dom.chatTargetAvatar.textContent = "👤";
      }
      if (this.dom.chatTargetName) {
        this.dom.chatTargetName.textContent = `DM: ${displayName}`;
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
        if (this.activeChannelIdx === 0) {
          this.dom.chatTargetAvatar.innerHTML = '<i class="bi bi-globe2" aria-hidden="true"></i>';
        } else this.dom.chatTargetAvatar.textContent = isEncrypted ? "🔒" : "📻";
      }
    }
  }

  switchChannel(idx) {
    this._closeComposerPopovers();
    this.activeChannelIdx = Number(idx) || 0;
    this.activeDmTarget = null;
    this.activeDmName = null;

    if (this.dom.btnCloseChat) {
      this.dom.btnCloseChat.classList.add("hidden");
    }

    this._updateActiveChatHeader();

    this._syncConversationSelection();

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

    this._closeComposerPopovers();
    // Si el hilo estaba cerrado/archivado, reabrirlo
    if (this.closedDmThreads.has(canonicalPk)) {
      this.closedDmThreads.delete(canonicalPk);
      this._saveClosedDmThreads();
    }

    this.activeDmTarget = canonicalPk;
    this.activeDmName = name || canonicalPk.slice(0, 8);
    if (this.activeDmName.includes(I18n.t("chat.local_name")) || this.activeDmName.includes("Local Station")) {
      this.activeDmName = targetNode?.name || canonicalPk.slice(0, 8);
    }

    if (this.dom.btnCloseChat) {
      this.dom.btnCloseChat.classList.remove("hidden");
    }

    this._updateActiveChatHeader();
    this.addDmContact(canonicalPk, this.activeDmName);

    this._syncConversationSelection();

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
      this._fallbackShareLocalStationLocation(I18n.t("chat.geo_unsupported"));
      return;
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
      },
      (err) => {
        this._fallbackShareLocalStationLocation(I18n.t("chat.gps_failed", { p0: err.message }));
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
      return;
    }

    if (this.ctx.showToast) {
      this.ctx.showToast(I18n.t("chat.gps_settings", { p0: reason }), "warning");
    }
  }

  async clearCurrentChat() {
    const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    const renderGeneration = ++this._renderGeneration;
    this._feedGenerations.set(feedKey, (this._feedGenerations.get(feedKey) || 0) + 1);
    this.channelFeeds.set(feedKey, []);
    this.historyPages.delete(feedKey);
    this._historyStates.set(feedKey, this._historyAccessDenied ? "auth" : "ready");

    if (this.ctx.storage && this.ctx.storage.clearFeedMessages) {
      try {
        await this.ctx.storage.clearFeedMessages(feedKey);
      } catch (_) {}
    }

    const currentFeed = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    if (renderGeneration === this._renderGeneration && feedKey === currentFeed && this.dom.chatMessageFeed) {
      this._paintConversation(feedKey);
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

  _syncConversationSelection() {
    document.querySelectorAll(".channel-item").forEach((item) => {
      const selected = this.activeDmTarget
        ? item.dataset.pubkey === this.activeDmTarget
        : item.dataset.channelIdx !== undefined && Number(item.dataset.channelIdx) === this.activeChannelIdx;
      item.classList.toggle("active", selected);
      item.querySelector(".channel-select")?.setAttribute("aria-pressed", String(selected));
    });
  }

  _updateDmCloseLabel(item) {
    const button = item.querySelector(".btn-close-dm");
    if (!button) return;
    const label = `${I18n.t("chat.close_chat")}: ${item.querySelector(".ch-name")?.textContent || item.dataset.pubkey}`;
    button.title = label;
    button.setAttribute("aria-label", label);
  }

  closeDmConversation(pubkey) {
    if (!pubkey) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    this.closedDmThreads.add(canonicalPk);
    this._saveClosedDmThreads();

    let restoreFocus = false;
    let focusReplacement = null;
    // Eliminar el elemento del DOM en dmListUi
    if (this.dom.dmListUi) {
      const item = this.dom.dmListUi.querySelector(`.channel-item[data-pubkey="${canonicalPk}"]`);
      restoreFocus = Boolean(item?.contains(document.activeElement));
      if (restoreFocus) {
        focusReplacement = item.nextElementSibling?.querySelector(".channel-select")
          || item.previousElementSibling?.querySelector(".channel-select");
      }
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
    if (restoreFocus) {
      (focusReplacement || document.querySelector('.channel-item[data-channel-idx="0"] .channel-select'))
        ?.focus({ preventScroll: true });
    }

    if (this.ctx.showToast) {
      this.ctx.showToast(I18n.t('chat.chat_closed'), "info");
    }
  }

  refreshDmNamesFromKnownNodes() {
    if (!this.dom.dmListUi) return;
    this.dom.dmListUi.querySelectorAll(".channel-item[data-pubkey]").forEach((item) => {
      const pk = item.getAttribute("data-pubkey");
      if (!pk) return;
      const canonicalPk = this.resolveCanonicalPubkey(pk);
      const node = this.ctx.knownNodes?.get(canonicalPk.toLowerCase());
      if (node && (node.name || node.alias)) {
        const nameSpan = item.querySelector(".ch-name");
        const realName = node.alias || node.name;
        if (nameSpan && realName && nameSpan.textContent !== realName) {
          nameSpan.textContent = realName;
          this._updateDmCloseLabel(item);
        }
      }
    });
    if (this.activeDmTarget) {
      this._updateActiveChatHeader();
    }
  }

  _isGenericOrHexNodeName(name, pubkey = null) {
    if (!name || typeof name !== "string") return true;
    const clean = name.trim();
    const lower = clean.toLowerCase();
    if (!clean || lower === "unknown" || lower === "anónimo" || lower === "anonimo" || lower === "anonymous") return true;
    if (pubkey) {
      const pk = String(pubkey).toLowerCase().trim();
      if (lower === pk || lower === pk.slice(0, 8)) return true;
    }
    if (clean.startsWith("Nodo [") || clean.startsWith("Node [") || lower.startsWith("node_unknow")) return true;
    if (lower.includes("local station") || (window.I18n && clean.includes(I18n.t("chat.local_name")))) return true;
    return false;
  }

  addDmContact(pubkey, name) {
    if (!pubkey || !this.dom.dmListUi) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);
    if (this._isLocalTarget(canonicalPk)) return;

    // SSoT Rule 1: Repeaters must NEVER be in contacts or DM list
    const node = this.ctx.knownNodes?.get(canonicalPk.toLowerCase());
    const roleUpper = String(node?.role || "").toUpperCase();
    if (roleUpper === "REPEATER" || roleUpper === "ROUTER") return;

    const isHexOrFallback = this._isGenericOrHexNodeName(name, canonicalPk);

    let cleanDisplayName = (isHexOrFallback && (node?.name || node?.alias))
      ? (node.alias || node.name)
      : (name || node?.alias || node?.name || canonicalPk.slice(0, 8));

    const emptyHint = this.dom.dmListUi.querySelector(".empty-hint");
    if (emptyHint) emptyHint.remove();

    const existing = this.dom.dmListUi.querySelector(`.channel-item[data-pubkey="${canonicalPk}"]`);
    if (existing) {
      if (cleanDisplayName && (!isHexOrFallback || (node?.name || node?.alias))) {
        const nameSpan = existing.querySelector(".ch-name");
        if (nameSpan && nameSpan.textContent !== cleanDisplayName) {
          nameSpan.textContent = cleanDisplayName;
          this._updateDmCloseLabel(existing);
        }
      }
      return;
    }

    const li = document.createElement("li");
    li.className = "channel-item";
    li.setAttribute("data-pubkey", canonicalPk);
    li.innerHTML = `
      <button type="button" class="channel-select" aria-pressed="${this.activeDmTarget === canonicalPk}">
        <span class="channel-icon" aria-hidden="true"><i class="bi bi-chat-dots"></i></span>
        <span class="channel-name ch-name">${escapeHtml(cleanDisplayName)}</span>
        <span class="channel-idx font-mono">DM</span>
      </button>
      <button type="button" class="btn-close-dm"><i class="bi bi-x-lg" aria-hidden="true"></i></button>
    `;
    li.classList.toggle("active", this.activeDmTarget === canonicalPk);
    li.querySelector(".channel-select").addEventListener("click", () => {
      this.openDmConversation(canonicalPk, li.querySelector(".ch-name").textContent);
    });
    this._updateDmCloseLabel(li);

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

  _clearProtectedHistory() {
    ++this._renderGeneration;
    this._historyAccessDenied = true;
    this.channelFeeds.clear();
    this.historyPages.clear();
    this._historyStates.clear();
    this.pendingOutgoingAcks.clear();
    this.conversationsWithMessages.clear();
    this.unreadCounts.clear();
    this._visibleFeedKey = null;
    if (this.dom.dmListUi) this.dom.dmListUi.textContent = "";
    if (this.dom.dmCountBadge) this.dom.dmCountBadge.textContent = "0";
    if (this.dom.globalChatUnreadBadge) {
      this.dom.globalChatUnreadBadge.textContent = "0";
      this.dom.globalChatUnreadBadge.classList.add("hidden");
    }
    if (this.dom.chatMessageFeed) {
      this.dom.chatMessageFeed.textContent = "";
      this.dom.chatMessageFeed.classList.remove("is-empty-conversation");
      this.dom.chatMessageFeed.setAttribute("aria-busy", "false");
    }
  }

  async renderCurrentConversation({ refresh = true, before = null } = {}) {
    if (!this.dom.chatMessageFeed) return;
    const renderGeneration = ++this._renderGeneration;
    const feedKey = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    const feedGeneration = this._feedGenerations.get(feedKey) || 0;
    const authGeneration = this.ctx.storage?.authGeneration;
    const preserveScroll = this._visibleFeedKey === feedKey && (this.channelFeeds.get(feedKey)?.length || 0) > 0;
    const isCurrent = () => renderGeneration === this._renderGeneration
      && feedGeneration === (this._feedGenerations.get(feedKey) || 0)
      && authGeneration === this.ctx.storage?.authGeneration
      && feedKey === (this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`);

    if (refresh && this.ctx.storage) {
      this._historyStates.set(feedKey, "loading");
      this._paintConversation(feedKey, { preserveScroll });
      try {
        const page = await this.ctx.storage.getHistoryPage(feedKey, { before });
        if (!isCurrent() || page.station_id !== this.ctx.storage.stationId) return;
        const existing = this.channelFeeds.get(feedKey) || [];
        const byId = new Map(existing.map(msg => [messageIdentity(msg), msg]));
        for (const msg of page.messages || []) {
          if (isCommandOrSystemText(msg.text, msg.txt_type)) continue;
          const id = messageIdentity(msg);
          const display = msg.is_outgoing ? msg : { ...msg, text: extractSenderAndText(msg.text, msg.sender_name).cleanText };
          if (id) byId.set(id, { ...mergeMessage(byId.get(id), display), id });
        }
        const merged = [...byId.values()].sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp) || (a.seq || 0) - (b.seq || 0));
        this.channelFeeds.set(feedKey, before == null ? merged.slice(-MAX_FEED_MESSAGES) : merged);
        this.historyPages.set(feedKey, page);
        this._historyAccessDenied = false;
        this._historyStates.set(feedKey, page.offline ? "offline" : "ready");
      } catch (error) {
        if (!isCurrent()) return;
        console.warn("History unavailable:", error);
        if (error.authRequired || error.status === 401 || error.status === 403) {
          this._clearProtectedHistory();
          this._historyAccessDenied = true;
          this._historyStates.set(feedKey, "auth");
          this._paintConversation(feedKey);
          return;
        }
        this._historyStates.set(feedKey, "error");
      }
    }
    if (!isCurrent()) return;
    this._paintConversation(feedKey, { preserveScroll });
  }

  _paintConversation(feedKey, { preserveScroll = false } = {}) {
    const feed = this.dom.chatMessageFeed;
    if (!feed) return;
    const oldTop = feed.scrollTop;
    const msgs = this.channelFeeds.get(feedKey) || [];
    const page = this.historyPages.get(feedKey);
    const state = this._historyStates.get(feedKey) || (this._historyAccessDenied ? "auth" : (page?.offline ? "offline" : "ready"));
    feed.setAttribute("aria-busy", String(state === "loading"));
    feed.classList.toggle("is-empty-conversation", msgs.length === 0 && state === "ready");
    const frag = document.createDocumentFragment();
    const statusKey = {
      loading: "chat.history_loading",
      error: "chat.history_failed",
      auth: "chat.history_auth_required",
      offline: msgs.length ? "chat.offline_cache" : "chat.offline_empty",
    }[state];
    if (statusKey) {
      const notice = document.createElement("p");
      notice.id = "chatHistoryStatus";
      notice.className = "view-state-notice";
      notice.dataset.state = state;
      notice.setAttribute("role", "status");
      notice.textContent = I18n.t(statusKey);
      frag.appendChild(notice);
    }

    if (msgs.length === 0 && state === "ready") {
      const empty = document.createElement("div");
      empty.className = "chat-empty-state";
      const help = document.createElement("p");
      help.textContent = I18n.t("chat.write_below");
      empty.appendChild(help);
      frag.appendChild(empty);
    }

    if (page?.has_more && page.next_before && state !== "auth") {
      const older = document.createElement("button");
      older.type = "button";
      older.className = "btn btn-secondary btn-sm";
      older.textContent = I18n.t("chat.load_older");
      older.disabled = state === "loading";
      older.addEventListener("click", async () => {
        older.disabled = true;
        const oldHeight = this.dom.chatMessageFeed.scrollHeight;
        const oldTop = this.dom.chatMessageFeed.scrollTop;
        await this.renderCurrentConversation({ before: page.next_before });
        if (feedKey === (this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`)) {
          this.dom.chatMessageFeed.scrollTop = oldTop + this.dom.chatMessageFeed.scrollHeight - oldHeight;
        }
      });
      frag.appendChild(older);
    }
    let lastDateStr = null;

    msgs.forEach((m) => {
      if (m.timestamp) {
        const msgDateStr = new Date(m.timestamp).toDateString();
        if (msgDateStr !== lastDateStr) {
          lastDateStr = msgDateStr;
          const sep = document.createElement("div");
          sep.className = "chat-date-separator";
          sep.innerHTML = `<span>${escapeHtml(getDateGroupLabel(m.timestamp))}</span>`;
          frag.appendChild(sep);
        }
      }
      frag.appendChild(this.createMessageBubble(m));
    });

    feed.replaceChildren(frag);
    this._visibleFeedKey = feedKey;
    feed.scrollTop = preserveScroll ? oldTop : feed.scrollHeight;
  }

  createMessageBubble(msg) {
    const row = document.createElement("div");
    row.className = `message-bubble-row ${msg.is_outgoing ? "outgoing" : "incoming"}`;
    row.setAttribute("data-msg-id", msg.id || msg.msg_id || "");
    if (msg.expected_ack) {
      const cleanAck = String(msg.expected_ack).toLowerCase().replace(/^0x/, "").trim();
      if (cleanAck) {
        row.setAttribute("data-ack-code", cleanAck);
        if (msg.is_outgoing && !msg.delivered) {
          this.pendingOutgoingAcks.set(cleanAck, msg.id || msg.msg_id);
        }
      }
    }

    const timeStr = formatRelativeTime(msg.timestamp);
    const messageDate = new Date(msg.timestamp);
    const validDate = Boolean(msg.timestamp) && !Number.isNaN(messageDate.getTime());
    const absoluteTime = validDate ? messageDate.toLocaleString(window.I18n?.lang) : "";
    const timeAttributes = validDate ? ` datetime="${escapeHtml(messageDate.toISOString())}" title="${escapeHtml(absoluteTime)}"` : "";
    let sender = msg.is_outgoing ? (window.I18n ? window.I18n.t('common.you') : "Tú") : (msg.sender_name || msg.sender || (window.I18n ? window.I18n.t('common.anonymous') : "Anónimo"));
    if (!msg.is_outgoing && sender) {
      const senderPk = msg.sender ? this.resolveCanonicalPubkey(msg.sender) : null;
      if (senderPk) {
        const node = this.ctx.knownNodes?.get(senderPk.toLowerCase());
        const isHexOrFallback = this._isGenericOrHexNodeName(sender, senderPk);
        if (isHexOrFallback && (node?.name || node?.alias)) {
          sender = node.alias || node.name;
        }
      }
    }

    const text = msg.text || "";

    // 1. Detección de formato oficial de contacto MeshCore: <pubkey:type:name> o URIs oficiales (meshcore://...)
    let richCardHtml = "";
    let cleanDisplayText = text;
    let parsedUri = null;

    const contactTagMatch = text.match(/<([0-9a-fA-F]{64}):([0-9]+):([^>]+)>/);
    if (contactTagMatch) {
      const rawTag = contactTagMatch[0];
      const cPk = contactTagMatch[1].toLowerCase();
      const cType = parseInt(contactTagMatch[2], 10);
      const cName = contactTagMatch[3].trim();
      const cRole = getRoleFromNumericType(cType);
      cleanDisplayText = text.replace(rawTag, "").trim();
      parsedUri = {
        type: "contact",
        name: cName,
        public_key: cPk,
        role: cRole,
        contact_type: cType,
      };
    } else {
      const meshcoreUriMatch = text.match(/meshcore:\/\/[^\s]+/i);
      if (meshcoreUriMatch) {
        const rawUri = meshcoreUriMatch[0];
        parsedUri = parseMeshCoreUri(rawUri);
        if (parsedUri) {
          cleanDisplayText = text.replace(rawUri, "").trim();
        }
      }
    }

    if (parsedUri) {
        if (parsedUri.type === "contact") {
          const cName = parsedUri.name || I18n.t("chat.meshcore_contact");
          const cRole = parsedUri.role || "CLIENT";
          const cPk = parsedUri.public_key || "";
          const localPk = (this.ctx.localNodePubkey || document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();
          const isLocal = Boolean(cPk && localPk && (cPk === localPk || cPk.startsWith(localPk.slice(0, 8))));
          const isKnown = isLocal || this.ctx.knownNodes?.has(cPk.toLowerCase());

          let footerActionHtml = "";
          if (isLocal) {
            const stationLabel = window.I18n ? window.I18n.t('chat.my_station_sub') : 'Mi Estación Local';
            footerActionHtml = `
              <div class="card-local-pill">
                <i class="bi bi-broadcast me-1" aria-hidden="true"></i>
                <span>${escapeHtml(stationLabel)}</span>
              </div>
            `;
          } else {
            const btnLabel = isKnown
              ? (window.I18n ? window.I18n.t('chat.saved_contact') : 'Contacto Guardado')
              : (window.I18n ? window.I18n.t('chat.save_contact') : 'Guardar en Contactos');
            footerActionHtml = `
              <button type="button" class="card-action-btn btn-save-shared-contact ${isKnown ? 'btn-saved' : ''}" data-pk="${escapeHtml(cPk)}" data-name="${escapeHtml(cName)}" data-role="${escapeHtml(cRole)}" ${isKnown ? 'disabled' : ''}>
                <i class="bi ${isKnown ? 'bi-check-lg' : 'bi-person-plus'} me-1" aria-hidden="true"></i>
                <span>${btnLabel}</span>
              </button>
            `;
          }

          richCardHtml = `
            <div class="chat-contact-card" data-pk="${escapeHtml(cPk)}">
              <div class="card-top-row">
                <div class="card-avatar"><i class="bi ${isLocal ? "bi-house-door" : "bi-person"}" aria-hidden="true"></i></div>
                <div class="card-info">
                  <span class="card-name">${escapeHtml(cName)}</span>
                  <span class="card-sub"><span class="badge-pill ${isLocal ? 'badge-primary' : ''}">${escapeHtml(cRole)}</span> <span class="card-key-mono">${escapeHtml(cPk.slice(0, 10))}…</span></span>
                </div>
              </div>
              ${footerActionHtml}
            </div>
          `;
        } else if (parsedUri.type === "channel") {
          const chName = parsedUri.name || I18n.t("chat.shared_channel");
          const chIdx = parsedUri.index !== null && parsedUri.index !== undefined ? parsedUri.index : "?";
          const isEnc = Boolean(parsedUri.secret && parsedUri.secret.length > 0 && parsedUri.secret !== MESHCORE_PUBLIC_CHANNEL_SECRET);

          richCardHtml = `
            <div class="chat-channel-card" data-idx="${chIdx}">
              <div class="card-top-row">
                <div class="card-avatar"><i class="bi ${isEnc ? "bi-lock" : "bi-broadcast"}" aria-hidden="true"></i></div>
                <div class="card-info">
                  <span class="card-name">${escapeHtml(chName)} (${I18n.t('chat.channel_number', { index: chIdx })})</span>
                  <span class="card-sub">${isEnc ? I18n.t("chat.encrypted_channel_icon") : I18n.t("chat.broadcast_channel_icon")}</span>
                </div>
              </div>
              <button type="button" class="card-action-btn btn-join-shared-channel" data-name="${escapeHtml(chName)}" data-secret="${escapeHtml(parsedUri.secret || '')}" data-idx="${chIdx}">
                <i class="bi bi-broadcast me-1" aria-hidden="true"></i>
                <span>${window.I18n ? window.I18n.t('chat.join_channel') : 'Unirse al Canal'}</span>
              </button>
            </div>
          `;
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
        // Limpiar las coordenadas del texto para evitar que se muestren dos veces en la misma burbuja
        const textWithoutGps = cleanDisplayText.replace(gpsMatch[0], "").replace(/^[📍\s:]+/, "").replace(/[📍\s:]+$/, "").trim();
        cleanDisplayText = textWithoutGps;

        locationCardHtml = `
          <div class="chat-location-card">
            <div class="loc-card-header">
              <i class="bi bi-geo-alt" aria-hidden="true"></i> <strong>${window.I18n ? window.I18n.t('chat.gps_shared') : 'Ubicación GPS Compartida'}</strong>
            </div>
            <div class="loc-coords-badge">${detectedLat.toFixed(5)}, ${detectedLon.toFixed(5)}</div>
            <button type="button" class="btn-view-on-map" data-lat="${detectedLat}" data-lon="${detectedLon}">
              <i class="bi bi-geo-alt me-1" aria-hidden="true"></i> ${window.I18n ? window.I18n.t('chat.view_map') : 'Ver en Mapa'}
            </button>
          </div>
        `;
      }
    }

    // 3. Indicador de entrega estilo WhatsApp (Checkmarks)
    let ackHtml = "";
    if (msg.is_outgoing) {
      if (msg.delivered) {
        const label = escapeHtml(I18n.t('chat.delivered'));
        ackHtml = `<span class="ack-indicator ack-delivered" role="img" title="${label}" aria-label="${label}"><i class="bi bi-check-all" aria-hidden="true"></i></span>`;
      } else if (msg.status === "sent") {
        const label = escapeHtml(I18n.t('chat.sent'));
        ackHtml = `<span class="ack-indicator ack-sent" role="img" title="${label}" aria-label="${label}"><i class="bi bi-check-lg" aria-hidden="true"></i></span>`;
      } else if (msg.status === "failed") {
        const label = escapeHtml(I18n.t('chat.failed'));
        ackHtml = `<span class="ack-indicator ack-failed" role="img" title="${label}" aria-label="${label}"><i class="bi bi-exclamation-circle" aria-hidden="true"></i></span>`;
      } else {
        const label = escapeHtml(I18n.t('chat.queued'));
        ackHtml = `<span class="ack-indicator ack-queued" role="img" title="${label}" aria-label="${label}"><i class="bi bi-clock" aria-hidden="true"></i></span>`;
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
          <time class="msg-time"${timeAttributes}>${escapeHtml(timeStr)}</time>
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
              btnSave.innerHTML = `
                <i class="bi bi-check-lg me-1" aria-hidden="true"></i>
                <span>${window.I18n ? window.I18n.t('chat.saved_contact') : 'Contacto Guardado'}</span>
              `;
              if (this.ctx.showToast) this.ctx.showToast(I18n.t("chat.contact_saved", { p0: name }), "success");
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
            if (this.ctx.showToast) this.ctx.showToast(I18n.t("chat.channel_switched", { p0: idx }), "info");
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


    return row;
  }

  async _persistOutgoingMessage(operation) {
    try {
      await operation();
    } catch (error) {
      console.warn("Error guardando mensaje:", error);
      this.ctx.showToast?.(I18n.t('chat.storage_error'), 'warning');
    }
  }

  async sendMessage() {
    if (this._sending) return;
    const rawInput = this.dom.chatInputText ? this.dom.chatInputText.value.trim() : "";
    if (!rawInput) return;
    // A conversation change must not redirect the remaining fragments.
    const destination = Object.freeze({
      canonicalTarget: this.activeDmTarget ? this.resolveCanonicalPubkey(this.activeDmTarget) : null,
      channelIdx: this.activeChannelIdx,
      dmName: this.activeDmName,
    });
    this._sending = true;
    this.dom.chatInputForm?.setAttribute("aria-busy", "true");
    try {
      if (this.dom.chatInputText) this.dom.chatInputText.value = "";
      this.updateCharCounter();
      const chunks = splitUtf8Message(rawInput, MAX_LORA_TEXT_BYTES);
      for (let i = 0; i < chunks.length; i++) {
        const accepted = await this._sendSingleMessageChunk(chunks[i], destination);
        if (!accepted) {
          const originalFeed = destination.canonicalTarget ? `dm_${destination.canonicalTarget}` : `ch_${destination.channelIdx}`;
          const visibleFeed = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
          if (originalFeed === visibleFeed && this.dom.chatInputText && !this.dom.chatInputText.value.trim()) {
            this.dom.chatInputText.value = chunks.slice(i).join("");
          }
          break;
        }
        if (i < chunks.length - 1) {
          await new Promise((resolve) => setTimeout(resolve, 300));
        }
      }
    } finally {
      this._sending = false;
      this.dom.chatInputForm?.setAttribute("aria-busy", "false");
      this.updateCharCounter();
    }
  }

  async _sendSingleMessageChunk(rawInput, destination) {
    const msgId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    const { canonicalTarget, channelIdx, dmName } = destination;

    if (canonicalTarget) {
      if (this._isLocalTarget(canonicalTarget)) {
        if (this.ctx.showToast) this.ctx.showToast(I18n.t("chat.no_local_message"), "warning");
        return false;
      }
      const normTarget = canonicalTarget.toLowerCase().trim();
      const targetNode = (this.ctx.knownNodes ? Array.from(this.ctx.knownNodes.values()) : []).find(
        (n) => (n.public_key && n.public_key.toLowerCase() === normTarget) ||
               (n.key_prefix && normTarget.startsWith(n.key_prefix.toLowerCase()))
      );
      const roleUpper = String(targetNode?.role || "").toUpperCase();
      if (roleUpper === "REPEATER" || roleUpper === "ROUTER") {
        if (this.ctx.showToast) this.ctx.showToast(I18n.t('toast.repeater_chat_err'), "warning");
        return false;
      }
    }

    const target = canonicalTarget || "broadcast";

    const outgoingMsg = {
      id: msgId,
      msg_id: msgId,
      sender: "local",
      sender_name: window.I18n ? window.I18n.t('common.local_station') : I18n.t("chat.local_name"),
      text: rawInput,
      is_outgoing: true,
      channel_idx: channelIdx,
      dm_target: canonicalTarget,
      dm_target_name: dmName || canonicalTarget,
      timestamp: new Date().toISOString(),
      delivered: false,
      status: "queued",
    };

    const feedKey = canonicalTarget ? `dm_${canonicalTarget}` : `ch_${channelIdx}`;
    if (!this.channelFeeds.has(feedKey)) this.channelFeeds.set(feedKey, []);
    const feed = this.channelFeeds.get(feedKey);
    feed.push(outgoingMsg);
    if (feed.length > MAX_FEED_MESSAGES) feed.shift();

    const visibleFeed = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    if (visibleFeed === feedKey) this.appendChatMessage(outgoingMsg);

    await this._persistOutgoingMessage(() => this.ctx.storage?.saveMessage(feedKey, outgoingMsg));
    try {
      const res = await fetch("/api/tx", {
        method: "POST",
        headers: this.ctx.getAuthHeaders ? this.ctx.getAuthHeaders({ "Content-Type": "application/json" }) : { "Content-Type": "application/json" },
        body: JSON.stringify({
          to: target,
          channel_index: outgoingMsg.channel_idx,
          text: rawInput,
          request_id: msgId,
        }),
      });
      const txData = await res.json();
      if (!res.ok || !txData || txData.status !== "ok") {
        throw new Error(txData?.detail || txData?.message || txData?.error || `HTTP ${res.status}`);
      }
      if (res.ok && txData && txData.status === "ok") {
        if (!outgoingMsg.delivered && outgoingMsg.status !== "delivered") outgoingMsg.status = "sent";
        await this._persistOutgoingMessage(() => this.ctx.storage?.updateMessageStatus?.(msgId, outgoingMsg.status));
        const deliveryTracking = txData.data?.delivery_tracking || txData.delivery_tracking;
        const canTrackDelivery = !deliveryTracking || deliveryTracking === "registered";
        if (!canTrackDelivery) {
          this.ctx.showToast?.(I18n.t('chat.delivery_tracking_unavailable'), 'info');
        }
        const rawExpectedAck = txData.data?.expected_ack || txData.expected_ack;
        if (rawExpectedAck && canTrackDelivery) {
          const cleanExpectedAck = String(rawExpectedAck).toLowerCase().replace(/^0x/, "").trim();
          if (cleanExpectedAck) {
            outgoingMsg.expected_ack = cleanExpectedAck;
            if (!outgoingMsg.delivered) this.pendingOutgoingAcks.set(cleanExpectedAck, msgId);
            await this._persistOutgoingMessage(() => this.ctx.storage?.updateMessageExpectedAck?.(msgId, cleanExpectedAck));
          }
        }
        const row = this.dom.chatMessageFeed?.querySelector(`.message-bubble-row[data-msg-id="${msgId}"]`);
        if (row) {
          if (outgoingMsg.expected_ack) {
            row.setAttribute("data-ack-code", outgoingMsg.expected_ack);
          }
          const indicator = row.querySelector(".ack-indicator");
          if (indicator && !outgoingMsg.delivered) {
            indicator.className = "ack-indicator ack-sent";
            indicator.innerHTML = '<i class="bi bi-check-lg" aria-hidden="true"></i>';
            indicator.title = I18n.t('chat.sent');
            indicator.setAttribute("aria-label", indicator.title);
          }
        }
      }
    } catch (e) {
      console.warn("Error transmitiendo mensaje:", e);
      if (outgoingMsg.delivered || outgoingMsg.status === "delivered") return true;
      outgoingMsg.status = "failed";
      await this._persistOutgoingMessage(() => this.ctx.storage?.updateMessageStatus?.(msgId, "failed"));
      this.ctx.showToast?.(I18n.t('chat.send_failed', { error: e.message }), 'error');
      const currentFeed = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
      if (currentFeed === feedKey) {
        const row = this.dom.chatMessageFeed?.querySelector(`.message-bubble-row[data-msg-id="${msgId}"]`);
        row?.replaceWith(this.createMessageBubble(outgoingMsg));
      }
      return false;
    }
    return true;
  }

  appendChatMessage(msg) {
    if (!this.dom.chatMessageFeed || this._historyAccessDenied) return;
    const emptyState = this.dom.chatMessageFeed.querySelector(".chat-empty-state");
    if (emptyState) emptyState.remove();
    this.dom.chatMessageFeed.classList.remove("is-empty-conversation");

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
        sep.innerHTML = `<span>${escapeHtml(getDateGroupLabel(msg.timestamp))}</span>`;
        this.dom.chatMessageFeed.appendChild(sep);
      }
    }

    const bubble = this.createMessageBubble(msg);
    this.dom.chatMessageFeed.appendChild(bubble);
    this.dom.chatMessageFeed.scrollTop = this.dom.chatMessageFeed.scrollHeight;
  }

  async handleIncomingChatMessage(payload) {
    if (this._historyAccessDenied) return;
    if (payload.station_id && payload.station_id !== this.ctx.storage?.stationId) return;
    const rawText = payload.text || payload.message || "";
    const outgoing = Boolean(payload.is_outgoing);
    const senderKey = payload.from || payload.sender || payload.public_key || "unknown";
    const canonicalSender = this.resolveCanonicalPubkey(senderKey);
    const { senderName, cleanText } = outgoing
      ? { senderName: payload.sender_name, cleanText: rawText }
      : extractSenderAndText(rawText, payload.sender_name || payload.name);

    const isDm = Boolean(
      payload.is_direct || payload.dm_target ||
      payload.type === "direct" ||
      payload.type === "DIRECT_MSG" ||
      payload.event_type === "direct"
    );
    const peer = outgoing ? this.resolveCanonicalPubkey(payload.dm_target || payload.target || "") : canonicalSender;
    const feedKey = payload.feed_key || (isDm ? `dm_${peer}` : `ch_${payload.channel_idx ?? payload.channel ?? 0}`);

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
      ...payload,
      id: payload.msg_id || payload.server_id || `rx_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
      msg_id: payload.msg_id || payload.server_id,
      server_id: payload.server_id,
      seq: payload.seq,
      sender: canonicalSender,
      sender_name: senderName,
      text: cleanText,
      is_outgoing: outgoing,
      channel_idx: payload.channel_idx ?? 0,
      dm_target: isDm ? peer : null,
      timestamp: safeIsoTimestamp,
      delivered: payload.delivered ?? !outgoing,
      status: payload.status || (outgoing ? "sent" : "received"),
    };

    if (!this.channelFeeds.has(feedKey)) this.channelFeeds.set(feedKey, []);
    const feed = this.channelFeeds.get(feedKey);
    const previousIndex = feed.findIndex(message => messageIdentity(message) === messageIdentity(newMsg));
    if (previousIndex >= 0) {
      feed[previousIndex] = mergeMessage(feed[previousIndex], newMsg);
      this.ctx.storage?.saveMessage(feedKey, feed[previousIndex]).catch(error => console.warn("Message cache unavailable:", error));
      const row = [...(this.dom.chatMessageFeed?.querySelectorAll(".message-bubble-row") || [])]
        .find(element => element.getAttribute("data-msg-id") === messageIdentity(newMsg));
      row?.replaceWith(this.createMessageBubble(feed[previousIndex]));
      return;
    }
    feed.push(newMsg);
    if (feed.length > MAX_FEED_MESSAGES) feed.shift();

    if (this.ctx.storage) {
      this.ctx.storage.saveMessage(feedKey, newMsg).catch(error => console.warn("Message cache unavailable:", error));
    }

    if (isDm) {
      this.conversationsWithMessages.add(peer);
      if (this.closedDmThreads.has(peer)) {
        this.closedDmThreads.delete(peer);
        this._saveClosedDmThreads();
      }
      this.addDmContact(peer, outgoing ? payload.dm_target_name : senderName);
    }

    const currentFeed = this.activeDmTarget ? `dm_${this.activeDmTarget}` : `ch_${this.activeChannelIdx}`;
    if (feedKey === currentFeed) {
      this.appendChatMessage(newMsg);
    }

    if (!outgoing && this.chatSoundEnabled) {
      this.playNotificationChime();
    }
  }

  handleDeliveryAck(payload) {
    if (!payload || typeof payload !== "object") return;
    if (payload.station_id && payload.station_id !== this.ctx.storage?.stationId) return;
    const rawAck = (payload.ack_code || payload.code || "").toString().toLowerCase().trim();
    const ackClean = rawAck.startsWith("0x") ? rawAck.slice(2) : rawAck;
    if (!ackClean || /^0+$/.test(ackClean)) return;
    let msgId = payload.msg_id;
    if (!msgId && ackClean) {
      msgId = this.pendingOutgoingAcks.get(ackClean);
    }

    let row = null;
    if (msgId) {
      row = this.dom.chatMessageFeed?.querySelector(`.message-bubble-row[data-msg-id="${msgId}"]`);
    }
    if (!row && ackClean) {
      row = this.dom.chatMessageFeed?.querySelector(`.message-bubble-row[data-ack-code="${ackClean}"]`);
    }

    const tripTime = payload.trip_time_ms || payload.trip_time || payload.rtt_ms;

    if (row) {
      const indicator = row.querySelector(".ack-indicator");
      if (indicator) {
        indicator.innerHTML = '<i class="bi bi-check-all" aria-hidden="true"></i>';
        indicator.className = "ack-indicator ack-delivered";
        const rttText = tripTime ? ` (${tripTime} ms)` : "";
        indicator.title = (window.I18n ? window.I18n.t('chat.delivered') : "Entregado") + rttText;
        indicator.setAttribute("aria-label", indicator.title);
      }
    }

    // Actualizar estado en memoria de los feeds de conversación
    for (const [feedKey, msgs] of this.channelFeeds.entries()) {
      for (const m of msgs) {
        const mExp = (m.expected_ack || "").toString().toLowerCase().replace(/^0x/, "").trim();
        if ((msgId && (m.id === msgId || m.msg_id === msgId)) || (ackClean && mExp === ackClean)) {
          m.delivered = true;
          m.status = "delivered";
          m.trip_time_ms = tripTime || 0;
        }
      }
    }

    if (this.ctx.storage) {
      this.ctx.storage.updateMessageDelivery(msgId, ackClean, tripTime).catch(error => console.warn("Message cache unavailable:", error));
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
