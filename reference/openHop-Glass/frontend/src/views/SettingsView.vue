<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Repeater Settings</h1>
        <p class="section-subtitle">
          Guided workflow: choose targets, define settings template, preview commands, then apply.
        </p>
      </div>
      <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="refreshAllData()">
        {{ appState.dataLoading ? "Refreshing..." : "Refresh inventory" }}
      </button>
    </header>
    <nav class="settings-tabs">
      <button
        class="btn"
        :class="activeTab === 'repeater' ? 'btn-primary' : 'btn-ghost'"
        type="button"
        @click="activeTab = 'repeater'"
      >
        Repeater Configuration
      </button>
      <button
        class="btn"
        :class="activeTab === 'global' ? 'btn-primary' : 'btn-ghost'"
        type="button"
        @click="activeTab = 'global'"
      >
        Global Managed MQTT
      </button>
    </nav>
    <template v-if="activeTab === 'repeater'">
    <section class="grid-3">
      <UiStatCard
        title="Step 1 · Targets"
        :value="selectedRepeaters.length"
        subtitle="Selected repeaters"
      />
      <UiStatCard
        title="Step 2 · Template"
        :value="actionsPerRepeater"
        subtitle="Actions per repeater"
      />
      <UiStatCard
        title="Step 3 · Preview"
        :value="draftCommands.length"
        subtitle="Commands queued on apply"
      />
    </section>
    <section class="grid-2 top-sections">
      <article class="glass-card panel">
        <h2>Step 1 · Target Selection</h2>
        <div class="selection-controls">
          <label class="toggle-row">
            <input type="checkbox" :checked="allSelected" @change="toggleSelectAll" />
            <span>Select all</span>
          </label>
          <button class="btn btn-ghost" @click="selectByStatuses(['adopted', 'connected'])" type="button">
            Select adopted + connected
          </button>
          <button class="btn btn-ghost" @click="selectByStatuses(['offline'])" type="button">
            Select offline
          </button>
          <button class="btn btn-ghost" @click="clearSelection" type="button">Clear</button>
        </div>
        <UiDataTable>
          <thead>
            <tr>
              <th></th>
              <th>Node</th>
              <th>Status</th>
              <th>Firmware</th>
              <th>Last inform</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="repeater in appState.repeaters"
              :key="repeater.id"
              class="row-click"
              @click="toggleSelection(repeater.id)"
            >
              <td>
                <input
                  type="checkbox"
                  :checked="selectedSet.has(repeater.id)"
                  @click.stop
                  @change="toggleSelection(repeater.id)"
                />
              </td>
              <td>
                <strong>{{ repeater.node_name }}</strong>
                <p class="section-subtitle">{{ repeater.pubkey }}</p>
              </td>
              <td><StatusPill :status="repeater.status" /></td>
              <td>{{ repeater.firmware_version || "—" }}</td>
              <td>{{ formatTimestamp(repeater.last_inform_at) }}</td>
            </tr>
            <tr v-if="appState.repeaters.length === 0">
              <td colspan="5" class="section-subtitle">No repeaters found.</td>
            </tr>
          </tbody>
        </UiDataTable>
      </article>
      <article class="glass-card panel">
        <h2>Step 2 · Settings Template</h2>
        <p v-if="!canOperate" class="section-subtitle">
          Viewer role is read-only and cannot queue configuration changes.
        </p>
        <form class="panel-form" @submit.prevent="applySettings">
          <label class="field-label">
            Mode
            <select v-model="settingsForm.mode" class="field-select">
              <option value="">No change</option>
              <option value="forward">forward</option>
              <option value="monitor">monitor</option>
              <option value="no_tx">no_tx</option>
            </select>
          </label>
          <label class="field-label">
            Inform interval (seconds)
            <input
              v-model.trim="settingsForm.interval_seconds"
              class="field"
              type="number"
              min="5"
              max="3600"
              placeholder="No change"
            />
          </label>
          <h3 class="subheading">Radio Settings</h3>
          <div class="grid-2">
            <label class="field-label">
              Frequency
              <input v-model.trim="settingsForm.frequency" class="field" type="number" placeholder="No change" />
            </label>
            <label class="field-label">
              Spreading factor
              <input
                v-model.trim="settingsForm.spreading_factor"
                class="field"
                type="number"
                min="6"
                max="12"
                placeholder="No change"
              />
            </label>
            <label class="field-label">
              Bandwidth
              <input v-model.trim="settingsForm.bandwidth" class="field" type="number" placeholder="No change" />
            </label>
            <label class="field-label">
              TX power
              <input v-model.trim="settingsForm.tx_power" class="field" type="number" placeholder="No change" />
            </label>
          </div>
          <h3 class="subheading">Advanced Config Patch</h3>
          <label class="field-label">
            Merge mode
            <select v-model="settingsForm.merge_mode" class="field-select">
              <option value="patch">patch</option>
              <option value="replace">replace</option>
            </select>
          </label>
          <label class="field-label">
            Config JSON
            <textarea
              v-model="settingsForm.config_json"
              class="field-textarea"
              placeholder='{"radio":{"tx_power":14},"repeater":{"mode":"forward"}}'
            />
          </label>
          <label class="field-label">
            Change reason
            <input
              v-model.trim="settingsForm.reason"
              class="field"
              placeholder="e.g. Regional power profile rollout"
            />
          </label>
          <div class="tip-box">
            <p>
              Settings are queued as commands and applied by each repeater on its next inform cycle.
            </p>
          </div>
        </form>
      </article>
    </section>
    <article class="glass-card panel preview-panel">
      <div class="preview-header">
        <div>
          <h2>Step 3 · Dry-run Preview</h2>
          <p class="section-subtitle">
            Exact commands that will be queued if you click <strong>Apply</strong>.
          </p>
        </div>
        <button class="btn btn-primary apply-btn" :disabled="!canApply" @click="applySettings" type="button">
          {{ appState.actionLoading ? "Applying..." : `Apply ${draftCommands.length} Command${draftCommands.length === 1 ? "" : "s"}` }}
        </button>
      </div>
      <ul v-if="validationMessages.length > 0" class="validation-list">
        <li v-for="message in validationMessages" :key="message">{{ message }}</li>
      </ul>
      <UiDataTable>
        <thead>
          <tr>
            <th>Node</th>
            <th>Action</th>
            <th>Parameters</th>
            <th>Reason</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="command in draftCommands" :key="`${command.node_name}-${command.action}-${compactJson(command.params)}`">
            <td>{{ command.node_name }}</td>
            <td><span class="pill pill-gray">{{ command.action }}</span></td>
            <td>
              <pre class="preview-json">{{ prettyJson(command.params) }}</pre>
            </td>
            <td>{{ command.reason || "—" }}</td>
          </tr>
          <tr v-if="draftCommands.length === 0">
            <td colspan="4" class="section-subtitle">No commands in preview yet.</td>
          </tr>
        </tbody>
      </UiDataTable>
      <details class="grouped-preview" v-if="previewByNode.length > 0">
        <summary>Grouped command preview by repeater</summary>
        <div class="grouped-grid">
          <article class="group-card" v-for="entry in previewByNode" :key="entry.nodeName">
            <h3>{{ entry.nodeName }}</h3>
            <ul>
              <li v-for="item in entry.actions" :key="`${entry.nodeName}-${item.action}`">
                <strong>{{ item.action }}</strong>
                <code>{{ item.params }}</code>
              </li>
            </ul>
          </article>
        </div>
      </details>
    </article>
    </template>
    <template v-else>
      <div class="global-panels">
        <UiPanelCard
          title="Managed MQTT Settings"
          subtitle="These values define the `glass_managed` MQTT config that repeaters receive."
        >
          <p class="section-subtitle">
            Source: <strong>{{ managedSettingsSource }}</strong> · Updated:
            {{ formatTimestamp(managedSettingsUpdatedAt) }}
          </p>
          <form class="panel-form" @submit.prevent="saveManagedSettings(false)">
            <label class="field-label">
              MQTT broker host
              <input v-model.trim="managedMqttForm.mqtt_broker_host" class="field" required />
            </label>
            <label class="field-label">
              MQTT broker port
              <input
                v-model.number="managedMqttForm.mqtt_broker_port"
                class="field"
                type="number"
                min="1"
                max="65535"
                required
              />
            </label>
            <label class="field-label">
              MQTT base topic
              <input v-model.trim="managedMqttForm.mqtt_base_topic" class="field" required />
            </label>
            <label class="toggle-row">
              <input v-model="managedMqttForm.mqtt_enabled" type="checkbox" />
              <span>Enable repeater MQTT telemetry publishing</span>
            </label>
            <label class="toggle-row">
              <input v-model="managedMqttForm.mqtt_tls_enabled" type="checkbox" />
              <span>Use TLS for repeater MQTT connection</span>
            </label>
            <label class="field-label">
              Change reason (optional)
              <input
                v-model.trim="managedMqttForm.reason"
                class="field"
                placeholder="e.g. Broker host correction"
              />
            </label>
            <div class="settings-actions">
              <button
                class="btn btn-secondary"
                type="button"
                :disabled="managedSettingsLoading || appState.actionLoading"
                @click="loadManagedSettings()"
              >
                {{ managedSettingsLoading ? "Loading..." : "Reload settings" }}
              </button>
              <button
                class="btn btn-primary"
                :disabled="managedSettingsLoading || appState.actionLoading || !canOperate"
              >
                {{ appState.actionLoading ? "Saving..." : "Save managed settings" }}
              </button>
              <button
                class="btn btn-danger"
                type="button"
                :disabled="managedSettingsLoading || appState.actionLoading || !canOperate"
                @click="saveManagedSettings(true)"
              >
                {{ appState.actionLoading ? "Queueing..." : "Save + Queue to all repeaters" }}
              </button>
            </div>
          </form>
        </UiPanelCard>
        <UiPanelCard
          title="Config Snapshot Encryption Keys"
          subtitle="Keys used to encrypt and decrypt repeater configuration backups."
        >
          <p class="section-subtitle">
            Source: <strong>{{ snapshotEncryptionSource }}</strong> · Updated:
            {{ formatTimestamp(snapshotEncryptionUpdatedAt) }}
          </p>
          <p v-if="!snapshotEncryptionConfigured" class="warning-inline">
            No snapshot encryption keys are configured. Backups cannot be queued until a key is set.
          </p>
          <div v-if="snapshotEncryptionKeyIds.length > 0" class="key-id-list">
            <span class="section-subtitle">Configured key IDs:</span>
            <div class="key-id-pills">
              <span v-for="keyId in snapshotEncryptionKeyIds" :key="keyId" class="pill pill-gray">
                {{ keyId }}
              </span>
            </div>
          </div>
          <p v-else class="section-subtitle">No key IDs available.</p>
          <p v-if="!isAdmin" class="section-subtitle">
            Only admins can update or generate snapshot encryption keys.
          </p>
          <form class="panel-form" @submit.prevent="saveSnapshotEncryptionKeys">
            <label class="field-label">
              Encryption key entries
              <textarea
                v-model="snapshotEncryptionInput"
                class="field-textarea"
                placeholder="key-20260416:xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx="
              />
            </label>
            <p class="section-subtitle">
              Paste one or more <code>key_id:fernet_key</code> entries separated by comma or newline.
            </p>
            <label class="field-label">
              Change reason (optional)
              <input
                v-model.trim="snapshotEncryptionReason"
                class="field"
                placeholder="e.g. Initial backup key setup"
              />
            </label>
            <div class="settings-actions">
              <button
                class="btn btn-secondary"
                type="button"
                :disabled="snapshotSettingsLoading || appState.actionLoading"
                @click="loadSnapshotEncryptionSettings()"
              >
                {{ snapshotSettingsLoading ? "Loading..." : "Reload key status" }}
              </button>
              <button
                class="btn btn-primary"
                :disabled="snapshotSettingsLoading || appState.actionLoading || !isAdmin"
              >
                {{ appState.actionLoading ? "Saving..." : "Save encryption keys" }}
              </button>
            </div>
          </form>
          <form class="panel-form generate-form" @submit.prevent="generateSnapshotEncryptionKey">
            <h3 class="subheading">Generate Key</h3>
            <label class="field-label">
              Key ID (optional)
              <input
                v-model.trim="snapshotGenerateKeyId"
                class="field"
                placeholder="generated-20260416160000"
              />
            </label>
            <label class="toggle-row">
              <input v-model="snapshotGenerateReplaceExisting" type="checkbox" />
              <span>Replace existing configured keys</span>
            </label>
            <label class="field-label">
              Generation reason (optional)
              <input
                v-model.trim="snapshotGenerateReason"
                class="field"
                placeholder="e.g. Rotate snapshot encryption key"
              />
            </label>
            <div class="settings-actions">
              <button
                class="btn btn-danger"
                :disabled="snapshotSettingsLoading || appState.actionLoading || !isAdmin"
              >
                {{ appState.actionLoading ? "Generating..." : "Generate key entry" }}
              </button>
            </div>
          </form>
          <label v-if="generatedSnapshotEntry" class="field-label generated-entry">
            Generated key entry (shown once — store securely before navigating away)
            <textarea :value="generatedSnapshotEntry" class="field-textarea" readonly />
          </label>
        </UiPanelCard>
      </div>
    </template>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from "vue";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiPanelCard from "../components/ui/UiPanelCard.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";
import StatusPill from "../components/ui/StatusPill.vue";
import {
  type ConfigSnapshotEncryptionSettingsResponse,
  type ManagedMqttSettingsResponse,
  type QueueCommandRequest,
} from "../types";
import {
  appState,
  canOperate,
  fetchConfigSnapshotEncryptionSettings,
  fetchManagedMqttSettings,
  formatTimestamp,
  generateConfigSnapshotEncryptionKey as generateConfigSnapshotEncryptionKeyApi,
  isAdmin,
  queueBulkCommands,
  refreshAllData,
  saveConfigSnapshotEncryptionSettings as saveConfigSnapshotEncryptionSettingsApi,
  saveManagedMqttSettings as saveManagedMqttSettingsApi,
} from "../state/appState";

const selectedIds = ref<string[]>([]);
const activeTab = ref<"repeater" | "global">("repeater");
const settingsForm = reactive({
  mode: "",
  interval_seconds: "",
  frequency: "",
  spreading_factor: "",
  bandwidth: "",
  tx_power: "",
  merge_mode: "patch",
  config_json: "",
  reason: "",
});
const managedSettingsLoading = ref(false);
const managedSettingsSource = ref("defaults");
const managedSettingsUpdatedAt = ref<string | null>(null);
const managedMqttForm = reactive({
  mqtt_enabled: true,
  mqtt_broker_host: "",
  mqtt_broker_port: 1883,
  mqtt_base_topic: "glass",
  mqtt_tls_enabled: false,
  reason: "",
});
const snapshotSettingsLoading = ref(false);
const snapshotEncryptionConfigured = ref(false);
const snapshotEncryptionSource = ref("unset");
const snapshotEncryptionUpdatedAt = ref<string | null>(null);
const snapshotEncryptionKeyIds = ref<string[]>([]);
const snapshotEncryptionInput = ref("");
const snapshotEncryptionReason = ref("");
const snapshotGenerateKeyId = ref("");
const snapshotGenerateReplaceExisting = ref(false);
const snapshotGenerateReason = ref("");
const generatedSnapshotEntry = ref("");

const selectedSet = computed(() => new Set(selectedIds.value));
const selectedRepeaters = computed(() =>
  appState.repeaters.filter((repeater) => selectedSet.value.has(repeater.id)),
);
const allSelected = computed(
  () => appState.repeaters.length > 0 && selectedIds.value.length === appState.repeaters.length,
);

function parseOptionalInteger(value: string): number | undefined {
  if (!value.trim()) {
    return undefined;
  }
  const parsed = Number.parseInt(value, 10);
  return Number.isNaN(parsed) ? undefined : parsed;
}

const templateParse = computed(() => {
  const errors: string[] = [];
  const intervalSeconds = parseOptionalInteger(settingsForm.interval_seconds);
  const frequency = parseOptionalInteger(settingsForm.frequency);
  const spreadingFactor = parseOptionalInteger(settingsForm.spreading_factor);
  const bandwidth = parseOptionalInteger(settingsForm.bandwidth);
  const txPower = parseOptionalInteger(settingsForm.tx_power);

  if (settingsForm.interval_seconds.trim() && intervalSeconds === undefined) {
    errors.push("Inform interval must be a valid integer.");
  }
  if (settingsForm.spreading_factor.trim() && spreadingFactor === undefined) {
    errors.push("Spreading factor must be a valid integer.");
  }

  const radioPayload: Record<string, number> = {};
  if (frequency !== undefined) {
    radioPayload.frequency = frequency;
  }
  if (spreadingFactor !== undefined) {
    radioPayload.spreading_factor = spreadingFactor;
  }
  if (bandwidth !== undefined) {
    radioPayload.bandwidth = bandwidth;
  }
  if (txPower !== undefined) {
    radioPayload.tx_power = txPower;
  }

  let configPayload: Record<string, unknown> | null = null;
  if (settingsForm.config_json.trim()) {
    try {
      const parsed = JSON.parse(settingsForm.config_json);
      if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        errors.push("Config JSON must be an object.");
      } else {
        configPayload = parsed as Record<string, unknown>;
      }
    } catch {
      errors.push("Config JSON is invalid.");
    }
  }

  return {
    errors,
    intervalSeconds,
    radioPayload,
    configPayload,
  };
});

const actionsPerRepeater = computed(() => {
  let count = 0;
  if (settingsForm.mode) {
    count += 1;
  }
  if (settingsForm.interval_seconds.trim()) {
    count += 1;
  }
  if (Object.keys(templateParse.value.radioPayload).length > 0) {
    count += 1;
  }
  if (settingsForm.config_json.trim()) {
    count += 1;
  }
  return count;
});

const draftCommands = computed<QueueCommandRequest[]>(() => {
  if (templateParse.value.errors.length > 0) {
    return [];
  }
  const requestedBy = appState.user?.email || "operator";
  const reason = settingsForm.reason || "Bulk settings update";
  const commands: QueueCommandRequest[] = [];

  for (const repeater of selectedRepeaters.value) {
    if (settingsForm.mode) {
      commands.push({
        node_name: repeater.node_name,
        action: "set_mode",
        params: { mode: settingsForm.mode },
        requested_by: requestedBy,
        reason,
      });
    }
    if (templateParse.value.intervalSeconds !== undefined) {
      commands.push({
        node_name: repeater.node_name,
        action: "set_inform_interval",
        params: { interval_seconds: templateParse.value.intervalSeconds },
        requested_by: requestedBy,
        reason,
      });
    }
    if (Object.keys(templateParse.value.radioPayload).length > 0) {
      commands.push({
        node_name: repeater.node_name,
        action: "set_radio",
        params: { radio: templateParse.value.radioPayload },
        requested_by: requestedBy,
        reason,
      });
    }
    if (templateParse.value.configPayload) {
      commands.push({
        node_name: repeater.node_name,
        action: "config_update",
        params: { config: templateParse.value.configPayload, merge_mode: settingsForm.merge_mode },
        requested_by: requestedBy,
        reason,
      });
    }
  }

  return commands;
});

const previewByNode = computed(() => {
  const grouped = new Map<string, Array<{ action: string; params: string }>>();
  for (const command of draftCommands.value) {
    const current = grouped.get(command.node_name) ?? [];
    current.push({ action: command.action, params: compactJson(command.params) });
    grouped.set(command.node_name, current);
  }
  return Array.from(grouped.entries()).map(([nodeName, actions]) => ({ nodeName, actions }));
});

const validationMessages = computed(() => {
  const messages = [...templateParse.value.errors];
  if (!canOperate.value) {
    messages.push("Your role cannot apply repeater settings.");
  }
  if (selectedRepeaters.value.length === 0) {
    messages.push("Select at least one repeater target.");
  }
  if (actionsPerRepeater.value === 0) {
    messages.push("Choose at least one settings change before applying.");
  }
  return messages;
});

const canApply = computed(
  () => !appState.actionLoading && validationMessages.value.length === 0 && draftCommands.value.length > 0,
);

function toggleSelection(repeaterId: string): void {
  if (selectedSet.value.has(repeaterId)) {
    selectedIds.value = selectedIds.value.filter((id) => id !== repeaterId);
    return;
  }
  selectedIds.value = [...selectedIds.value, repeaterId];
}

function toggleSelectAll(): void {
  if (allSelected.value) {
    selectedIds.value = [];
    return;
  }
  selectedIds.value = appState.repeaters.map((repeater) => repeater.id);
}

function selectByStatuses(statuses: string[]): void {
  const allowed = new Set(statuses);
  selectedIds.value = appState.repeaters
    .filter((repeater) => allowed.has(repeater.status))
    .map((repeater) => repeater.id);
}

function clearSelection(): void {
  selectedIds.value = [];
}

function setLocalError(message: string): void {
  appState.toastSuccess = null;
  appState.toastError = message;
}

function compactJson(value: unknown): string {
  return JSON.stringify(value ?? {});
}

function prettyJson(value: unknown): string {
  return JSON.stringify(value ?? {}, null, 2);
}

async function applySettings(): Promise<void> {
  if (validationMessages.value.length > 0) {
    setLocalError(validationMessages.value[0]);
    return;
  }
  await queueBulkCommands(draftCommands.value);
}

function applyManagedSettingsToForm(settings: ManagedMqttSettingsResponse): void {
  managedMqttForm.mqtt_enabled = settings.mqtt_enabled;
  managedMqttForm.mqtt_broker_host = settings.mqtt_broker_host;
  managedMqttForm.mqtt_broker_port = settings.mqtt_broker_port;
  managedMqttForm.mqtt_base_topic = settings.mqtt_base_topic;
  managedMqttForm.mqtt_tls_enabled = settings.mqtt_tls_enabled;
  managedSettingsSource.value = settings.source;
  managedSettingsUpdatedAt.value = settings.updated_at;
}

async function loadManagedSettings(): Promise<void> {
  managedSettingsLoading.value = true;
  try {
    const settings = await fetchManagedMqttSettings();
    if (settings) {
      applyManagedSettingsToForm(settings);
    }
  } finally {
    managedSettingsLoading.value = false;
  }
}

async function saveManagedSettings(queueToRepeaters: boolean): Promise<void> {
  if (!canOperate.value) {
    setLocalError("Your role cannot change managed MQTT settings.");
    return;
  }
  const host = managedMqttForm.mqtt_broker_host.trim();
  const topic = managedMqttForm.mqtt_base_topic.trim().replace(/^\/+|\/+$/g, "");
  if (!host) {
    setLocalError("MQTT broker host cannot be empty.");
    return;
  }
  if (!topic) {
    setLocalError("MQTT base topic cannot be empty.");
    return;
  }
  if (queueToRepeaters) {
    const proceed = window.confirm(
      "Queue this managed MQTT update to all non-rejected repeaters now?",
    );
    if (!proceed) {
      return;
    }
  }
  const response = await saveManagedMqttSettingsApi({
    mqtt_enabled: managedMqttForm.mqtt_enabled,
    mqtt_broker_host: host,
    mqtt_broker_port: managedMqttForm.mqtt_broker_port,
    mqtt_base_topic: topic,
    mqtt_tls_enabled: managedMqttForm.mqtt_tls_enabled,
    queue_to_repeaters: queueToRepeaters,
    reason: managedMqttForm.reason.trim() || undefined,
  });
  if (!response) {
    return;
  }
  applyManagedSettingsToForm(response.settings);
  if (response.queued_commands > 0) {
    await refreshAllData();
  }
}

function applySnapshotEncryptionSettingsToForm(
  settings: ConfigSnapshotEncryptionSettingsResponse,
): void {
  snapshotEncryptionConfigured.value = settings.configured;
  snapshotEncryptionSource.value = settings.source;
  snapshotEncryptionUpdatedAt.value = settings.updated_at;
  snapshotEncryptionKeyIds.value = settings.key_ids;
}

function normalizeEncryptionKeyEntries(value: string): string {
  return value
    .split(/[\n,]/)
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0)
    .join(",");
}

async function loadSnapshotEncryptionSettings(): Promise<void> {
  snapshotSettingsLoading.value = true;
  try {
    const settings = await fetchConfigSnapshotEncryptionSettings();
    if (settings) {
      applySnapshotEncryptionSettingsToForm(settings);
    }
  } finally {
    snapshotSettingsLoading.value = false;
  }
}

async function saveSnapshotEncryptionKeys(): Promise<void> {
  if (!isAdmin.value) {
    setLocalError("Only admin users can update snapshot encryption keys.");
    return;
  }
  const normalizedEntries = normalizeEncryptionKeyEntries(snapshotEncryptionInput.value);
  if (!normalizedEntries) {
    setLocalError("Provide at least one key_id:fernet_key entry.");
    return;
  }
  const updated = await saveConfigSnapshotEncryptionSettingsApi({
    encryption_keys: normalizedEntries,
    reason: snapshotEncryptionReason.value.trim() || undefined,
  });
  if (!updated) {
    return;
  }
  applySnapshotEncryptionSettingsToForm(updated);
  generatedSnapshotEntry.value = "";
}

async function generateSnapshotEncryptionKey(): Promise<void> {
  if (!isAdmin.value) {
    setLocalError("Only admin users can generate snapshot encryption keys.");
    return;
  }
  if (snapshotEncryptionConfigured.value && snapshotGenerateReplaceExisting.value) {
    const proceed = window.confirm(
      "This replaces currently configured snapshot encryption keys. Continue?",
    );
    if (!proceed) {
      return;
    }
  }
  const generated = await generateConfigSnapshotEncryptionKeyApi({
    key_id: snapshotGenerateKeyId.value.trim() || undefined,
    replace_existing: snapshotGenerateReplaceExisting.value,
    reason: snapshotGenerateReason.value.trim() || undefined,
  });
  if (!generated) {
    return;
  }
  applySnapshotEncryptionSettingsToForm(generated.settings);
  generatedSnapshotEntry.value = generated.generated_entry;
}

onMounted(() => {
  void Promise.all([loadManagedSettings(), loadSnapshotEncryptionSettings()]);
});
</script>
<style scoped>
.settings-tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.global-panels {
  display: grid;
  gap: 1rem;
}

.warning-inline {
  margin: 0;
  padding: 0.65rem 0.8rem;
  border: 1px solid rgba(171, 86, 107, 0.65);
  border-radius: 10px;
  background: rgba(82, 29, 40, 0.82);
  color: #ffd7df;
}

.key-id-list {
  display: grid;
  gap: 0.4rem;
}

.key-id-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.generate-form {
  margin-top: 0.4rem;
  padding-top: 0.7rem;
  border-top: 1px solid var(--color-border-subtle);
}

.generated-entry {
  margin-top: 0.7rem;
}

.top-sections {
  align-items: start;
}

.subheading {
  font-size: 0.88rem;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: var(--color-text-muted);
}

.panel-form {
  display: grid;
  gap: 0.7rem;
}

.selection-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.55rem;
}

.toggle-row {
  display: flex;
  align-items: center;
  gap: 0.45rem;
}

.row-click {
  cursor: pointer;
}

.row-click:hover {
  background: rgba(255, 255, 255, 0.03);
}

.tip-box {
  border: 1px solid var(--color-border-subtle);
  border-radius: 10px;
  padding: 0.6rem 0.75rem;
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-text-muted);
}

.preview-panel {
  gap: 0.9rem;
}

.preview-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.9rem;
}

.apply-btn {
  min-width: 220px;
}

.settings-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.validation-list {
  margin: 0;
  padding: 0.65rem 0.8rem 0.65rem 1.5rem;
  border: 1px solid rgba(171, 86, 107, 0.65);
  border-radius: 10px;
  background: rgba(82, 29, 40, 0.82);
  color: #ffd7df;
  display: grid;
  gap: 0.2rem;
}

.preview-json {
  margin: 0;
  white-space: pre-wrap;
  font-size: 0.75rem;
  color: #d2deef;
}

.grouped-preview summary {
  cursor: pointer;
  color: var(--color-text-secondary);
  font-weight: 600;
}

.grouped-grid {
  margin-top: 0.7rem;
  display: grid;
  gap: 0.7rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.group-card {
  border: 1px solid var(--color-border-subtle);
  border-radius: 10px;
  padding: 0.65rem;
  background: rgba(255, 255, 255, 0.02);
}

.group-card h3 {
  font-size: 0.9rem;
  margin-bottom: 0.5rem;
}

.group-card ul {
  margin: 0;
  padding-left: 1.1rem;
  display: grid;
  gap: 0.35rem;
}

.group-card li {
  display: grid;
  gap: 0.2rem;
}

@media (max-width: 980px) {
  .grouped-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 740px) {

  .preview-header {
    flex-direction: column;
  }

  .apply-btn {
    width: 100%;
  }

  .settings-actions {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
