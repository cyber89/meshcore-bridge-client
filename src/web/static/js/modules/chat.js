/**
 * ChatModule - Mensajería de texto para canales broadcast, canales cifrados y mensajes directos (DM).
 * Incluye tracking de entrega (ACKs), alertas sonoras e historial persistente IndexedDB.
 */

import { escapeHtml, extractSenderAndText, isCommandOrSystemText, isCommonChatMessage, MAX_FEED_MESSAGES } from "../core/utils.js";
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
  }

  init() {
    this._bindElements();
    this._bindEvents();
    this._subscribeBus();
    this.loadInitialHistory();
  }

  _bindElements() {
    this.dom = {
      chatMessageFeed: document.getElementById("chatMessageFeed"),
      chatInputForm: document.getElementById("chatInputForm"),
      chatInputText: document.getElementById("chatInputText"),
      chatTargetName: document.getElementById("chatTargetName"),
      chatTargetBadge: document.getElementById("chatTargetBadge"),
      btnCancelReply: document.getElementById("btnCancelReply"),
      btnShareLocation: document.getElementById("btnShareLocation"),
      dmListUi: document.getElementById("dmListUi"),
      sidebarChannelList: document.getElementById("sidebarChannelList"),
      globalChatUnreadBadge: document.getElementById("globalChatUnreadBadge"),
      chkChatSoundAlerts: document.getElementById("chkChatSoundAlerts"),
    };
  }

  _bindEvents() {
    if (this.dom.chatInputForm) {
      this.dom.chatInputForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        await this.sendMessage();
      });
    }

    if (this.dom.btnCancelReply) {
      this.dom.btnCancelReply.addEventListener("click", () => this.cancelReplyTarget());
    }

    if (this.dom.btnShareLocation) {
      this.dom.btnShareLocation.addEventListener("click", () => this.shareCurrentLocation());
    }

    if (this.dom.chkChatSoundAlerts) {
      this.dom.chkChatSoundAlerts.checked = this.chatSoundEnabled;
      this.dom.chkChatSoundAlerts.addEventListener("change", (e) => {
        this.chatSoundEnabled = e.target.checked;
        localStorage.setItem("meshcore_chat_sound_enabled", String(this.chatSoundEnabled));
        if (this.chatSoundEnabled) {
          this.playNotificationChime();
          if (this.ctx.showToast) this.ctx.showToast("🔔 Alertas sonoras de chat activadas", "info");
        } else {
          if (this.ctx.showToast) this.ctx.showToast("🔕 Alertas sonoras de chat desactivadas", "info");
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
          this.conversationsWithMessages.add(canonicalPk);
          this.addDmContact(canonicalPk, thread.name || canonicalPk.slice(0, 8));
        }
      }
    } catch (_) {}
  }

  resolveCanonicalPubkey(pubkey) {
    if (this.ctx.resolveCanonicalPubkey) {
      return this.ctx.resolveCanonicalPubkey(pubkey);
    }
    return pubkey ? String(pubkey).trim().toLowerCase() : "";
  }

  switchChannel(idx) {
    this.activeChannelIdx = Number(idx) || 0;
    this.activeDmTarget = null;
    this.activeDmName = null;

    if (this.dom.chatTargetName) {
      this.dom.chatTargetName.textContent = this.activeChannelIdx === 0 ? "Canal Público 0 (Broadcast)" : `Canal Privado #${this.activeChannelIdx}`;
    }
    if (this.dom.chatTargetBadge) {
      this.dom.chatTargetBadge.textContent = `#${this.activeChannelIdx}`;
      this.dom.chatTargetBadge.className = "chat-target-badge badge-channel";
    }

    document.querySelectorAll(".channel-item").forEach((el) => el.classList.remove("active"));
    const activeItem = document.querySelector(`.channel-item[data-channel-idx="${this.activeChannelIdx}"]`);
    if (activeItem) activeItem.classList.add("active");

    this.renderCurrentConversation();
  }

  setDmTarget(pubkey, name) {
    this.openDmConversation(pubkey, name);
  }

  openDmConversation(pubkey, name) {
    if (!pubkey) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);

    this.activeDmTarget = canonicalPk;
    this.activeDmName = name || canonicalPk.slice(0, 8);

    if (this.dom.chatTargetName) {
      this.dom.chatTargetName.textContent = `DM: ${this.activeDmName}`;
    }
    if (this.dom.chatTargetBadge) {
      this.dom.chatTargetBadge.textContent = "DM";
      this.dom.chatTargetBadge.className = "chat-target-badge badge-dm";
    }

    this.addDmContact(canonicalPk, this.activeDmName);

    document.querySelectorAll(".channel-item").forEach((el) => el.classList.remove("active"));
    const activeDmEl = document.querySelector(`.channel-item[data-pubkey="${canonicalPk}"]`);
    if (activeDmEl) activeDmEl.classList.add("active");

    const navBtn = document.querySelector('.nav-btn[data-tab="tab-chat"]');
    if (navBtn) navBtn.click();

    this.renderCurrentConversation();
  }

  addDmContact(pubkey, name) {
    if (!pubkey || !this.dom.dmListUi) return;
    const canonicalPk = this.resolveCanonicalPubkey(pubkey);

    const existing = this.dom.dmListUi.querySelector(`.channel-item[data-pubkey="${canonicalPk}"]`);
    if (existing) return;

    const li = document.createElement("li");
    li.className = "channel-item";
    li.setAttribute("data-pubkey", canonicalPk);
    li.innerHTML = `
      <span class="channel-icon">💬</span>
      <span class="channel-name ch-name">${escapeHtml(name || canonicalPk.slice(0, 8))}</span>
      <span class="channel-idx font-mono">DM</span>
    `;
    li.addEventListener("click", () => this.openDmConversation(canonicalPk, name));
    this.dom.dmListUi.appendChild(li);
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
          <p>No hay mensajes en esta conversación aún.</p>
          <small>Escribe un mensaje abajo para transmitir por la malla LoRa.</small>
        </div>
      `;
      return;
    }

    const frag = document.createDocumentFragment();
    msgs.forEach((m) => {
      frag.appendChild(this.createMessageBubble(m));
    });
    this.dom.chatMessageFeed.appendChild(frag);
    this.dom.chatMessageFeed.scrollTop = this.dom.chatMessageFeed.scrollHeight;
  }

  createMessageBubble(msg) {
    const row = document.createElement("div");
    row.className = `message-bubble-row ${msg.is_outgoing ? "outgoing" : "incoming"}`;
    row.setAttribute("data-msg-id", msg.id || msg.msg_id || "");

    const timeStr = msg.timestamp ? new Date(msg.timestamp).toLocaleTimeString() : "";
    const sender = msg.is_outgoing ? "Tú" : (msg.sender_name || msg.sender || "Anónimo");

    row.innerHTML = `
      <div class="message-bubble">
        <div class="msg-meta">
          <span class="msg-sender">${escapeHtml(sender)}</span>
          <span class="msg-time">${escapeHtml(timeStr)}</span>
        </div>
        <div class="msg-body">${escapeHtml(msg.text)}</div>
        ${msg.is_outgoing ? `<div class="msg-status-indicator font-mono">${msg.delivered ? "✓✓ Entregado" : "✓ Enviado"}</div>` : ""}
      </div>
    `;
    return row;
  }

  async sendMessage() {
    const rawInput = this.dom.chatInputText ? this.dom.chatInputText.value.trim() : "";
    if (!rawInput) return;
    if (this.dom.chatInputText) this.dom.chatInputText.value = "";

    const msgId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 6)}`;
    const canonicalTarget = this.activeDmTarget ? this.resolveCanonicalPubkey(this.activeDmTarget) : null;

    if (canonicalTarget) {
      const normTarget = canonicalTarget.toLowerCase().trim();
      const localPk = (document.getElementById("localNodePubkey")?.value || "").toLowerCase().trim();
      if (normTarget === "local" || (localPk && normTarget === localPk)) {
        if (this.ctx.showToast) this.ctx.showToast("No se puede enviar mensajes de chat hacia el nodo local", "warning");
        return;
      }
    }

    const target = canonicalTarget || "broadcast";

    const outgoingMsg = {
      id: msgId,
      msg_id: msgId,
      sender: "local",
      sender_name: "Estación Local (Tú)",
      text: rawInput,
      is_outgoing: true,
      channel_idx: this.activeChannelIdx,
      dm_target: canonicalTarget,
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
      }
    } catch (e) {
      console.warn("Error transmitiendo mensaje:", e);
    }
  }

  appendChatMessage(msg) {
    if (!this.dom.chatMessageFeed) return;
    const emptyState = this.dom.chatMessageFeed.querySelector(".chat-empty-state");
    if (emptyState) emptyState.remove();

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

    const newMsg = {
      id: payload.msg_id || `rx_${Date.now()}`,
      sender: canonicalSender,
      sender_name: senderName,
      text: cleanText,
      is_outgoing: false,
      channel_idx: payload.channel_idx ?? 0,
      timestamp: payload.timestamp ? new Date(payload.timestamp * 1000).toISOString() : new Date().toISOString(),
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
      const indicator = row.querySelector(".msg-status-indicator");
      if (indicator) {
        indicator.textContent = "✓✓ Entregado";
        indicator.classList.add("delivered");
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
