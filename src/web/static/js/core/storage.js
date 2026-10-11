/** SQLite owns history. IndexedDB caches downloaded messages per validated station. */
import { getAuthHeaders } from "./utils.js";

const CACHE_STORE = "message_cache";
const META_STORE = "cache_metadata";
const LEGACY_STORE = "chat_messages";

export function messageIdentity(message) {
  return String(message.msg_id || message.server_id || message.id || "");
}

export function mergeMessage(previous, incoming) {
  const merged = { ...previous, ...incoming };
  // A late history response or TX result must never undo a confirmed ACK.
  if (previous?.status === "delivered" || incoming.status === "delivered") {
    merged.status = "delivered";
    merged.delivered = true;
  }
  return merged;
}

function transactionDone(transaction) {
  return new Promise((resolve, reject) => {
    transaction.oncomplete = resolve;
    transaction.onerror = () => reject(transaction.error || new Error("Cache transaction failed"));
    transaction.onabort = () => reject(transaction.error || new Error("Cache transaction aborted"));
  });
}

function requestValue(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export class MeshCoreStorage {
  constructor(dbName = "MeshCoreStationDB", version = 2) {
    this.dbName = dbName;
    this.version = Math.max(2, version);
    this.db = null;
    this.stationId = null;
    this.validatedOnline = false;
    this.authGeneration = 0;
    window.addEventListener("meshcore:credentials_changed", () => {
      this.authGeneration += 1;
      this.validatedOnline = false;
    });
    this.readyPromise = this.init();
  }

  async init() {
    if (!("indexedDB" in window)) return null;
    try {
      const request = indexedDB.open(this.dbName, this.version);
      request.onupgradeneeded = () => {
        const db = request.result;
        // Preserve the former browser archive for explicit, user-selected import.
        if (!db.objectStoreNames.contains(LEGACY_STORE)) {
          const legacy = db.createObjectStore(LEGACY_STORE, { keyPath: "id", autoIncrement: true });
          legacy.createIndex("by_feed", "feed_key");
        }
        if (!db.objectStoreNames.contains(CACHE_STORE)) {
          const cache = db.createObjectStore(CACHE_STORE, { keyPath: ["station_id", "msg_id"] });
          cache.createIndex("by_feed", ["station_id", "feed_key"]);
          cache.createIndex("by_station", "station_id");
          cache.createIndex("by_feed_seq", ["station_id", "feed_key", "seq"]);
        }
        if (!db.objectStoreNames.contains(META_STORE)) db.createObjectStore(META_STORE, { keyPath: "key" });
      };
      this.db = await new Promise((resolve, reject) => {
        let blocked = false;
        request.onblocked = () => {
          blocked = true;
          console.warn("Close other MeshCore tabs to upgrade the message cache.");
          resolve(null);
        };
        request.onsuccess = () => {
          if (blocked) request.result.close();
          else resolve(request.result);
        };
        request.onerror = () => reject(request.error);
      });
      if (!this.db) return null;
      this.db.onversionchange = () => { this.db?.close(); this.db = null; };
      const tx = this.db.transaction(META_STORE, "readonly");
      const metadata = await requestValue(tx.objectStore(META_STORE).get("last_station"));
      this.stationId = metadata?.station_id || null;
      return this.db;
    } catch (error) {
      console.warn("Message cache unavailable:", error);
      return null;
    }
  }

  async _request(path, options = {}) {
    const authGeneration = this.authGeneration;
    let response;
    try {
      response = await fetch(path, { ...options, headers: getAuthHeaders(options.headers) });
    } catch (cause) {
      const error = new Error("History server unavailable", { cause });
      error.offline = true;
      throw error;
    }
    const result = await response.json();
    if (authGeneration !== this.authGeneration) throw new Error("Credentials changed during history request");
    if (!response.ok || result.status !== "ok") {
      throw new Error(result.detail || result.message || result.error || `HTTP ${response.status}`);
    }
    const data = result.data;
    if (!data || typeof data.station_id !== "string" || !data.station_id) {
      throw new Error("History response has no station identity");
    }
    return data;
  }

  async _accept(data) {
    await this.readyPromise;
    if (this.db) {
      try {
        const tx = this.db.transaction([CACHE_STORE, META_STORE], "readwrite");
        const done = transactionDone(tx);
        const store = tx.objectStore(CACHE_STORE);
        for (const message of data.messages || []) {
          const msgId = messageIdentity(message);
          if (!msgId || !message.feed_key) continue;
          const get = store.get([data.station_id, msgId]);
          get.onsuccess = () => store.put({ ...mergeMessage(get.result, message), station_id: data.station_id, msg_id: msgId, id: msgId });
        }
        const metadata = tx.objectStore(META_STORE);
        metadata.put({ key: "last_station", station_id: data.station_id });
        this._cacheConversations(metadata, data);
        // Identity and downloaded messages become visible together after commit.
        await done;
      } catch (error) {
        console.warn("History downloaded, but offline cache unavailable:", error);
        this.db?.close();
        this.db = null;
      }
    }
    const previousStation = this.stationId;
    this.stationId = data.station_id;
    this.validatedOnline = true;
    if (previousStation !== this.stationId) {
      window.dispatchEvent(new CustomEvent("meshcore:station_changed", { detail: { station_id: this.stationId } }));
    }
    return data;
  }

  _cacheConversations(metadata, data) {
    const key = `conversations:${data.station_id}`;
    const request = metadata.get(key);
    request.onsuccess = () => {
      const conversations = new Map((request.result?.conversations || []).map(thread => [thread.feed_key, thread]));
      const downloaded = (data.messages || []).filter(message => Number.isInteger(message.seq) && message.seq > 0)
        .map(message => ({ feed_key: message.feed_key, last_seq: message.seq, last_message: message, timestamp: message.timestamp }));
      for (const thread of [...(data.conversations || []), ...downloaded]) {
        const previous = conversations.get(thread.feed_key);
        if (!previous || (thread.last_seq || 0) >= (previous.last_seq || 0)) conversations.set(thread.feed_key, thread);
      }
      metadata.put({ key, conversations: [...conversations.values()].sort((a, b) => (b.last_seq || 0) - (a.last_seq || 0)) });
    };
  }

  async getHistoryPage(feedKey, { limit = 100, before = null } = {}) {
    await this.readyPromise;
    const params = new URLSearchParams({ feed_key: feedKey, limit: String(limit) });
    if (before != null) params.set("before", String(before));
    try {
      const data = await this._request(`/api/messages/history?${params}`);
      await this._accept(data);
      return { ...data, offline: false };
    } catch (error) {
      if (!error.offline) throw error;
      const messages = await this._cachedFeed(feedKey, limit, before);
      return { messages, station_id: this.stationId, next_before: messages[0]?.seq || null, has_more: messages.length === limit, offline: true };
    }
  }

  async getMessagesByFeed(feedKey, limit = 100) {
    return (await this.getHistoryPage(feedKey, { limit })).messages;
  }

  async _cachedFeed(feedKey, limit, before) {
    if (!this.db || !this.stationId) return [];
    const stationId = this.stationId;
    return new Promise((resolve, reject) => {
      const tx = this.db.transaction(CACHE_STORE, "readonly");
      const range = IDBKeyRange.bound([stationId, feedKey, 0], [stationId, feedKey, before ?? Number.MAX_SAFE_INTEGER], false, before != null);
      const request = tx.objectStore(CACHE_STORE).index("by_feed_seq").openCursor(range, "prev");
      const messages = [];
      request.onerror = () => reject(request.error);
      request.onsuccess = () => {
        const cursor = request.result;
        if (cursor && messages.length < limit) {
          messages.push(cursor.value);
          cursor.continue();
        } else resolve(messages.reverse());
      };
    });
  }

  async getDmConversations(localPubkey = "") {
    await this.readyPromise;
    let conversations;
    try {
      const data = await this._request("/api/messages/conversations");
      await this._accept(data);
      conversations = data.conversations || [];
    } catch (error) {
      if (!error.offline) throw error;
      if (!this.db || !this.stationId) return [];
      const tx = this.db.transaction(META_STORE, "readonly");
      conversations = (await requestValue(tx.objectStore(META_STORE).get(`conversations:${this.stationId}`)))?.conversations || [];
    }
    return conversations.filter(thread => String(thread.feed_key || "").startsWith("dm_"))
      .map(thread => ({ ...thread, pubkey: thread.pubkey || thread.feed_key.slice(3), name: thread.name || thread.peer_name || (thread.last_message?.is_outgoing ? thread.last_message?.dm_target_name : thread.last_message?.sender_name) || thread.feed_key.slice(3, 11) }))
      .filter(thread => thread.pubkey.toLowerCase() !== String(localPubkey).toLowerCase());
  }

  async saveMessage(feedKey, message) {
    await this.readyPromise;
    if (!this.db || !this.stationId || !this.validatedOnline || !messageIdentity(message)) return;
    const tx = this.db.transaction([CACHE_STORE, META_STORE], "readwrite");
    const done = transactionDone(tx);
    const store = tx.objectStore(CACHE_STORE);
    const stationId = this.stationId;
    const msgId = messageIdentity(message);
    const get = store.get([stationId, msgId]);
    get.onsuccess = () => store.put({ ...mergeMessage(get.result, message), station_id: stationId, feed_key: feedKey, msg_id: msgId, id: msgId });
    this._cacheConversations(tx.objectStore(META_STORE), { station_id: stationId, messages: [{ ...message, feed_key: feedKey }] });
    await done;
  }

  async _updateMessages(matches, update) {
    await this.readyPromise;
    if (!this.db || !this.stationId) return;
    const tx = this.db.transaction(CACHE_STORE, "readwrite");
    const done = transactionDone(tx);
    const request = tx.objectStore(CACHE_STORE).index("by_station").openCursor(IDBKeyRange.only(this.stationId));
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      if (matches(cursor.value)) cursor.update(update(cursor.value));
      cursor.continue();
    };
    await done;
  }

  updateMessageExpectedAck(msgId, expectedAck) {
    return this._updateMessages(message => message.msg_id === msgId, message => ({ ...message, expected_ack: String(expectedAck || "").toLowerCase().replace(/^0x/, "").trim() }));
  }

  updateMessageDelivery(msgId, ackCode, tripTime) {
    const ack = String(ackCode || "").toLowerCase().replace(/^0x/, "").trim();
    return this._updateMessages(message => (msgId && message.msg_id === msgId) || (ack && !/^0+$/.test(ack) && String(message.expected_ack || "").toLowerCase().replace(/^0x/, "") === ack),
      message => ({ ...message, delivered: true, status: "delivered", trip_time_ms: tripTime || message.trip_time_ms || 0 }));
  }

  updateMessageStatus(msgId, status) {
    return this._updateMessages(message => message.msg_id === msgId,
      message => mergeMessage(message, { status, delivered: status === "delivered" }));
  }

  async _clear(feedKey = null) {
    await this.readyPromise;
    if (!this.db || !this.stationId) return;
    const tx = this.db.transaction(CACHE_STORE, "readwrite");
    const done = transactionDone(tx);
    const store = tx.objectStore(CACHE_STORE);
    const index = store.index(feedKey == null ? "by_station" : "by_feed");
    const request = index.openCursor(IDBKeyRange.only(feedKey == null ? this.stationId : [this.stationId, feedKey]));
    request.onsuccess = () => {
      const cursor = request.result;
      if (!cursor) return;
      store.delete(cursor.primaryKey);
      cursor.continue();
    };
    await done;
  }

  clearFeedMessages(feedKey) { return this._clear(feedKey); }
  clearAll() { return this._clear(); }

  async importLegacyHistory() {
    await this.readyPromise;
    if (!this.db) throw new Error("Legacy browser history is unavailable");
    // Explicit consent targets the currently authenticated station. Never replay TX.
    const station = await this._request("/api/messages/conversations");
    await this._accept(station);
    let imported = 0;
    let skipped = 0;
    let after = null;
    while (true) {
      const tx = this.db.transaction(LEGACY_STORE, "readonly");
      const range = after == null ? undefined : IDBKeyRange.lowerBound(after, true);
      const messages = await requestValue(tx.objectStore(LEGACY_STORE).getAll(range, 100));
      if (!messages.length) break;
      after = messages[messages.length - 1].id;
      const valid = messages.filter(message => typeof message.text === "string" && message.text.trim()
        && /^(?:ch_[0-9]+|dm_[0-9a-f]{8,64})$/.test(message.feed_key || "")
        && Number.isFinite(Date.parse(message.timestamp)));
      skipped += messages.length - valid.length;
      const batch = valid.map(message => {
        const { id, _db_id, ...fields } = message;
        return { ...fields, msg_id: message.msg_id || null };
      });
      if (!batch.length) continue;
      const data = await this._request("/api/messages/import", { method: "POST", body: JSON.stringify({ messages: batch, station_id: station.station_id }) });
      if (data.station_id !== station.station_id) throw new Error("Station changed during history import");
      imported += data.imported || data.imported_count || 0;
    }
    return { imported, skipped };
  }
}
