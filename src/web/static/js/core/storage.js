/**
 * MeshCoreStorage - Capa de persistencia asíncrona en el navegador mediante IndexedDB.
 * Permite conservar historial de chat y preferencias tras refrescar la página.
 */

export class MeshCoreStorage {
  constructor(dbName = "MeshCoreStationDB", version = 1) {
    this.dbName = dbName;
    this.version = version;
    this.db = null;
    this.readyPromise = this.init();
  }

  async init() {
    if (!("indexedDB" in window)) {
      console.warn("IndexedDB no soportado en este entorno.");
      return null;
    }
    return new Promise((resolve) => {
      try {
        const request = indexedDB.open(this.dbName, this.version);
        request.onupgradeneeded = (e) => {
          const db = e.target.result;
          if (!db.objectStoreNames.contains("chat_messages")) {
            const chatStore = db.createObjectStore("chat_messages", { keyPath: "id", autoIncrement: true });
            chatStore.createIndex("by_feed", "feed_key", { unique: false });
            chatStore.createIndex("by_time", "timestamp", { unique: false });
          }
          if (!db.objectStoreNames.contains("app_settings")) {
            db.createObjectStore("app_settings", { keyPath: "key" });
          }
        };
        request.onsuccess = (e) => {
          this.db = e.target.result;
          resolve(this.db);
        };
        request.onerror = (e) => {
          console.warn("Error abriendo IndexedDB:", e);
          resolve(null);
        };
      } catch (err) {
        console.warn("Fallo inicializando IndexedDB:", err);
        resolve(null);
      }
    });
  }

  async saveMessage(feedKey, msg) {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const record = {
        feed_key: feedKey,
        msg_id: msg.msg_id || msg.id || null,
        sender: msg.sender,
        sender_name: msg.sender_name,
        text: msg.text,
        is_outgoing: !!msg.is_outgoing,
        channel_idx: msg.channel_idx,
        dm_target: msg.dm_target,
        timestamp: msg.timestamp || new Date().toISOString(),
        metrics: msg.metrics || null,
        delivered: !!msg.delivered,
        status: msg.status || (msg.delivered ? "delivered" : (msg.is_outgoing ? "sent" : "received")),
        expected_ack: msg.expected_ack || null,
        trip_time_ms: msg.trip_time_ms || 0,
        quote: msg.quote || null,
        location: msg.location || null,
      };
      if (typeof msg._db_id === "number") {
        record.id = msg._db_id;
        store.put(record);
      } else {
        const req = store.add(record);
        req.onsuccess = (e) => {
          msg._db_id = e.target.result;
        };
      }
    } catch (_) {}
  }

  async updateMessageDelivery(msgId, ackCode, tripTime) {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const req = store.openCursor();
      const rawAck = (ackCode || "").toLowerCase();
      const ackClean = rawAck.startsWith("0x") ? rawAck.slice(2) : rawAck;
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          const val = cursor.value;
          const valExp = (val.expected_ack || "").toLowerCase();
          const valExpClean = valExp.startsWith("0x") ? valExp.slice(2) : valExp;
          const ackMatch = ackClean && valExpClean && valExpClean === ackClean;
          const match = (msgId && (val.msg_id === msgId || String(val.id) === String(msgId))) || ackMatch;
          if (match) {
            val.delivered = true;
            val.status = "delivered";
            val.trip_time_ms = tripTime || 0;
            cursor.update(val);
          }
          cursor.continue();
        }
      };
    } catch (_) {}
  }

  async updateMessageStatus(msgId, status) {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const req = store.openCursor();
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          const val = cursor.value;
          if (msgId && (val.msg_id === msgId || String(val.id) === String(msgId))) {
            val.status = status;
            if (status === "delivered") val.delivered = true;
            cursor.update(val);
          }
          cursor.continue();
        }
      };
    } catch (_) {}
  }

  async purgeNonCommonMessages(isCommandOrSystemTextFn) {
    await this.readyPromise;
    if (!this.db || typeof isCommandOrSystemTextFn !== "function") return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const req = store.openCursor();
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          const val = cursor.value;
          const txt = val.text || val.message || "";
          const txtType = val.txt_type || 0;
          if (isCommandOrSystemTextFn(txt, txtType)) {
            cursor.delete();
          }
          cursor.continue();
        }
      };
    } catch (_) {}
  }

  async getMessagesByFeed(feedKey, limit = 100) {
    await this.readyPromise;
    if (!this.db) return [];
    return new Promise((resolve) => {
      try {
        const tx = this.db.transaction("chat_messages", "readonly");
        const store = tx.objectStore("chat_messages");
        const index = store.index("by_feed");
        const req = index.getAll(IDBKeyRange.only(feedKey));
        req.onsuccess = () => {
          const msgs = req.result || [];
          resolve(msgs.slice(-limit));
        };
        req.onerror = () => resolve([]);
      } catch (_) {
        resolve([]);
      }
    });
  }

  async getDmConversations() {
    await this.readyPromise;
    if (!this.db) return [];
    return new Promise((resolve) => {
      try {
        const tx = this.db.transaction("chat_messages", "readonly");
        const store = tx.objectStore("chat_messages");
        const req = store.getAll();
        req.onsuccess = () => {
          const allMsgs = req.result || [];
          const threadsMap = new Map();

          for (const msg of allMsgs) {
            const feedKey = msg.feed_key || "";
            if (!feedKey.startsWith("dm_")) continue;
            const pubkey = feedKey.slice(3).trim();
            if (!pubkey || pubkey.toLowerCase() === "unknown" || pubkey.toLowerCase() === "local") continue;

            if (!threadsMap.has(pubkey)) {
              threadsMap.set(pubkey, {
                pubkey: pubkey,
                name: msg.sender_name || (msg.dm_target && msg.dm_target !== pubkey ? msg.dm_target : pubkey),
                lastMessage: msg.text || "",
                lastTimestamp: msg.timestamp || "",
                role: "CLIENT",
                messages: []
              });
            }
            const thread = threadsMap.get(pubkey);
            thread.messages.push(msg);
            if (!msg.is_outgoing && msg.sender_name && msg.sender_name.toLowerCase() !== "unknown" && msg.sender_name !== pubkey) {
              thread.name = msg.sender_name;
            }
            if (msg.timestamp && (!thread.lastTimestamp || new Date(msg.timestamp) > new Date(thread.lastTimestamp))) {
              thread.lastTimestamp = msg.timestamp;
              thread.lastMessage = msg.text || "";
            }
          }

          const threads = Array.from(threadsMap.values());
          threads.sort((a, b) => new Date(b.lastTimestamp || 0) - new Date(a.lastTimestamp || 0));
          resolve(threads);
        };
        req.onerror = () => resolve([]);
      } catch (_) {
        resolve([]);
      }
    });
  }

  async clearFeedMessages(feedKey) {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      const store = tx.objectStore("chat_messages");
      const index = store.index("by_feed");
      const req = index.openCursor(IDBKeyRange.only(feedKey));
      req.onsuccess = (e) => {
        const cursor = e.target.result;
        if (cursor) {
          store.delete(cursor.primaryKey);
          cursor.continue();
        }
      };
    } catch (_) {}
  }

  async clearAll() {
    await this.readyPromise;
    if (!this.db) return;
    try {
      const tx = this.db.transaction("chat_messages", "readwrite");
      tx.objectStore("chat_messages").clear();
    } catch (_) {}
  }
}
