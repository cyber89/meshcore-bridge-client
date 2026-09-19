import { computed, reactive } from "vue";

import {
  adoptRepeater,
  ApiError,
  createBootstrapAdmin,
  createRepeater,
  createUser,
  deleteRepeater,
  deleteStaleRepeaters,
  generateConfigSnapshotEncryptionKey as generateConfigSnapshotEncryptionKeyApi,
  getConfigSnapshotEncryptionSettings as getConfigSnapshotEncryptionSettingsApi,
  getManagedMqttSettings,
  getTelemetryStreamUrl,
  getBootstrapStatus,
  getCommand,
  getCurrentUser,
  listAudit,
  listCommands,
  listPendingAdoptions,
  listRepeaters,
  listUsers,
  login,
  logout,
  queueCommand,
  rejectRepeater,
  updateConfigSnapshotEncryptionSettings as updateConfigSnapshotEncryptionSettingsApi,
  updateUser,
  updateManagedMqttSettings,
  updateRepeater,
} from "../api";
import type {
  AuditRecordResponse,
  CommandQueueItemResponse,
  QueueCommandRequest,
  UserCreateRequest,
  UserManagementResponse,
  UserUpdateRequest,
  RepeaterCreateRequest,
  RepeaterResponse,
  RepeaterUpdateRequest,
  UserInfoResponse,
  MqttTelemetryEventResponse,
  ConfigSnapshotEncryptionKeyGenerateRequest,
  ConfigSnapshotEncryptionKeyGenerateResponse,
  ConfigSnapshotEncryptionSettingsResponse,
  ConfigSnapshotEncryptionSettingsUpdateRequest,
  ManagedMqttSettingsResponse,
  ManagedMqttSettingsUpdateRequest,
  ManagedMqttSettingsUpdateResponse,
} from "../types";

const TOKEN_STORAGE_KEY = "pymc_glass_token";
const USER_STORAGE_KEY = "pymc_glass_user";
const EXPIRES_AT_STORAGE_KEY = "pymc_glass_expires_at";
const SETUP_WIZARD_SKIP_KEY = "pymc_glass_setup_wizard_skipped";
const MAX_TELEMETRY_EVENTS = 100;

export const appState = reactive({
  initialized: false,
  initializing: true,
  needsBootstrap: false,
  loginLoading: false,
  bootstrapLoading: false,
  dataLoading: false,
  actionLoading: false,
  token: null as string | null,
  user: null as UserInfoResponse | null,
  expiresAt: null as string | null,
  repeaters: [] as RepeaterResponse[],
  pendingRepeaters: [] as RepeaterResponse[],
  commands: [] as CommandQueueItemResponse[],
  audits: [] as AuditRecordResponse[],
  users: [] as UserManagementResponse[],
  telemetryConnected: false,
  telemetryEvents: [] as MqttTelemetryEventResponse[],
  telemetryLastEventAt: null as string | null,
  lastSyncAt: null as string | null,
  toastSuccess: null as string | null,
  toastError: null as string | null,
  setupWizardVisible: false,
});

export const isAuthenticated = computed(() => Boolean(appState.token && appState.user));
export const canOperate = computed(
  () => appState.user?.role === "admin" || appState.user?.role === "operator",
);
export const isAdmin = computed(() => appState.user?.role === "admin");
export const statusCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const repeater of appState.repeaters) {
    counts[repeater.status] = (counts[repeater.status] ?? 0) + 1;
  }
  return counts;
});
export const commandCounts = computed(() => {
  const counts: Record<string, number> = {};
  for (const command of appState.commands) {
    counts[command.status] = (counts[command.status] ?? 0) + 1;
  }
  return counts;
});

let toastTimeout: ReturnType<typeof setTimeout> | null = null;
let telemetrySource: EventSource | null = null;

function addTelemetryEvent(event: MqttTelemetryEventResponse): void {
  appState.telemetryEvents = [event, ...appState.telemetryEvents].slice(0, MAX_TELEMETRY_EVENTS);
  appState.telemetryLastEventAt = event.ingested_at || new Date().toISOString();
  const repeater = appState.repeaters.find((item) => item.node_name === event.node_name);
  if (repeater) {
    repeater.last_inform_at = event.ingested_at || event.timestamp;
  }
}

export function showSuccessToast(message: string): void {
  pushSuccess(message);
}

export function showErrorToast(error: unknown): void {
  pushError(error);
}

function parseTelemetryEvent(raw: string): MqttTelemetryEventResponse | null {
  try {
    const parsed = JSON.parse(raw) as MqttTelemetryEventResponse;
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    if (!parsed.event_id || !parsed.node_name || !parsed.topic || !parsed.timestamp) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function stopTelemetryStream(): void {
  if (telemetrySource) {
    telemetrySource.close();
    telemetrySource = null;
  }
  appState.telemetryConnected = false;
}

function startTelemetryStream(): void {
  if (!appState.token) {
    stopTelemetryStream();
    return;
  }
  stopTelemetryStream();

  const streamUrl = getTelemetryStreamUrl(appState.token);
  const source = new EventSource(streamUrl);
  telemetrySource = source;

  source.addEventListener("ready", () => {
    appState.telemetryConnected = true;
  });
  source.addEventListener("mqtt_ingest", (event) => {
    appState.telemetryConnected = true;
    const parsed = parseTelemetryEvent((event as MessageEvent<string>).data);
    if (parsed) {
      addTelemetryEvent(parsed);
    }
  });
  source.onerror = () => {
    appState.telemetryConnected = false;
  };
}

function pushSuccess(message: string): void {
  appState.toastSuccess = message;
  appState.toastError = null;
  if (toastTimeout) {
    clearTimeout(toastTimeout);
  }
  toastTimeout = setTimeout(() => {
    appState.toastSuccess = null;
  }, 3200);
}

function pushError(error: unknown): void {
  const message =
    error instanceof ApiError
      ? `${error.message} (HTTP ${error.status})`
      : error instanceof Error
        ? error.message
        : "Unexpected error";
  appState.toastError = message;
  appState.toastSuccess = null;
  if (toastTimeout) {
    clearTimeout(toastTimeout);
  }
  toastTimeout = setTimeout(() => {
    appState.toastError = null;
  }, 4200);
}

function persistSession(token: string, user: UserInfoResponse, expiresAt: string): void {
  appState.token = token;
  appState.user = user;
  appState.expiresAt = expiresAt;
  localStorage.setItem(TOKEN_STORAGE_KEY, token);
  localStorage.setItem(USER_STORAGE_KEY, JSON.stringify(user));
  localStorage.setItem(EXPIRES_AT_STORAGE_KEY, expiresAt);
}

function clearSession(): void {
  stopTelemetryStream();
  appState.token = null;
  appState.user = null;
  appState.expiresAt = null;
  appState.repeaters = [];
  appState.pendingRepeaters = [];
  appState.commands = [];
  appState.audits = [];
  appState.users = [];
  appState.telemetryEvents = [];
  appState.telemetryLastEventAt = null;
  localStorage.removeItem(TOKEN_STORAGE_KEY);
  localStorage.removeItem(USER_STORAGE_KEY);
  localStorage.removeItem(EXPIRES_AT_STORAGE_KEY);
}

async function checkSetupWizard(): Promise<void> {
  if (localStorage.getItem(SETUP_WIZARD_SKIP_KEY)) {
    return;
  }
  try {
    const status = await getBootstrapStatus();
    if (!status.server_setup_complete) {
      appState.setupWizardVisible = true;
    }
  } catch {
    // Non-critical — silently ignore if the check fails.
  }
}

export async function initializeAppState(): Promise<void> {
  appState.initializing = true;
  try {
    const bootstrapStatus = await getBootstrapStatus();
    appState.needsBootstrap = bootstrapStatus.needs_bootstrap;

    const storedToken = localStorage.getItem(TOKEN_STORAGE_KEY);
    const storedExpiresAt = localStorage.getItem(EXPIRES_AT_STORAGE_KEY);

    if (storedToken) {
      try {
        const user = await getCurrentUser(storedToken);
        persistSession(storedToken, user, storedExpiresAt ?? "");
        await refreshAllData();
        startTelemetryStream();
        await checkSetupWizard();
      } catch {
        clearSession();
      }
    }
  } catch (error) {
    pushError(error);
  } finally {
    appState.initializing = false;
    appState.initialized = true;
  }
}

export async function queueBulkCommands(payloads: QueueCommandRequest[]): Promise<number> {
  if (!appState.token || payloads.length === 0) {
    return 0;
  }
  appState.actionLoading = true;
  let queued = 0;
  try {
    for (const payload of payloads) {
      await queueCommand(appState.token, payload);
      queued += 1;
    }
    await refreshCommandsList({ limit: 200 });
    pushSuccess(`Queued ${queued} command${queued === 1 ? "" : "s"}.`);
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
  return queued;
}

export async function fetchManagedMqttSettings(): Promise<ManagedMqttSettingsResponse | null> {
  if (!appState.token) {
    return null;
  }
  try {
    return await getManagedMqttSettings(appState.token);
  } catch (error) {
    pushError(error);
    return null;
  }
}

export async function saveManagedMqttSettings(
  payload: ManagedMqttSettingsUpdateRequest,
): Promise<ManagedMqttSettingsUpdateResponse | null> {
  if (!appState.token) {
    return null;
  }
  appState.actionLoading = true;
  try {
    const updated = await updateManagedMqttSettings(appState.token, payload);
    if (updated.queued_commands > 0) {
      pushSuccess(
        `Managed MQTT settings updated and ${updated.queued_commands} repeater command${updated.queued_commands === 1 ? "" : "s"} queued.`,
      );
    } else {
      pushSuccess("Managed MQTT settings updated.");
    }
    return updated;
  } catch (error) {
    pushError(error);
    return null;
  } finally {
    appState.actionLoading = false;
  }
}

export async function fetchConfigSnapshotEncryptionSettings(): Promise<ConfigSnapshotEncryptionSettingsResponse | null> {
  if (!appState.token) {
    return null;
  }
  try {
    return await getConfigSnapshotEncryptionSettingsApi(appState.token);
  } catch (error) {
    pushError(error);
    return null;
  }
}

export async function saveConfigSnapshotEncryptionSettings(
  payload: ConfigSnapshotEncryptionSettingsUpdateRequest,
): Promise<ConfigSnapshotEncryptionSettingsResponse | null> {
  if (!appState.token) {
    return null;
  }
  appState.actionLoading = true;
  try {
    const updated = await updateConfigSnapshotEncryptionSettingsApi(appState.token, payload);
    pushSuccess("Config snapshot encryption keys updated.");
    return updated;
  } catch (error) {
    pushError(error);
    return null;
  } finally {
    appState.actionLoading = false;
  }
}

export async function generateConfigSnapshotEncryptionKey(
  payload: ConfigSnapshotEncryptionKeyGenerateRequest,
): Promise<ConfigSnapshotEncryptionKeyGenerateResponse | null> {
  if (!appState.token) {
    return null;
  }
  appState.actionLoading = true;
  try {
    const generated = await generateConfigSnapshotEncryptionKeyApi(appState.token, payload);
    pushSuccess("Config snapshot encryption key generated. Store it securely now.");
    return generated;
  } catch (error) {
    pushError(error);
    return null;
  } finally {
    appState.actionLoading = false;
  }
}

export async function bootstrapAdminAccount(payload: {
  email: string;
  password: string;
  display_name?: string;
}): Promise<void> {
  appState.bootstrapLoading = true;
  try {
    await createBootstrapAdmin(payload);
    appState.needsBootstrap = false;
    pushSuccess("Bootstrap admin created. You can sign in now.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.bootstrapLoading = false;
  }
}

export async function loginAccount(email: string, password: string): Promise<void> {
  appState.loginLoading = true;
  try {
    const response = await login(email, password);
    persistSession(response.access_token, response.user, response.expires_at);
    await refreshAllData();
    startTelemetryStream();
    pushSuccess("Signed in.");
    await checkSetupWizard();
  } catch (error) {
    pushError(error);
  } finally {
    appState.loginLoading = false;
  }
}

export async function logoutAccount(): Promise<void> {
  try {
    if (appState.token) {
      await logout(appState.token);
    }
  } catch {
    // Ignore remote logout failures and still clear local session.
  } finally {
    clearSession();
    pushSuccess("Signed out.");
  }
}

export async function refreshAllData(): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.dataLoading = true;
  try {
    const [repeaters, pending, commands, audits, users] = await Promise.all([
      listRepeaters(appState.token),
      listPendingAdoptions(appState.token),
      listCommands(appState.token, { limit: 200 }),
      listAudit(appState.token, 200),
      isAdmin.value ? listUsers(appState.token) : Promise.resolve([]),
    ]);
    appState.repeaters = repeaters;
    appState.pendingRepeaters = pending;
    appState.commands = commands;
    appState.audits = audits;
    appState.users = users;
    appState.lastSyncAt = new Date().toISOString();
  } catch (error) {
    pushError(error);
  } finally {
    appState.dataLoading = false;
  }
}

export async function refreshCommandsList(options?: {
  status?: string;
  node_name?: string;
  limit?: number;
}): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.dataLoading = true;
  try {
    appState.commands = await listCommands(appState.token, options);
    appState.lastSyncAt = new Date().toISOString();
  } catch (error) {
    pushError(error);
  } finally {
    appState.dataLoading = false;
  }
}

export async function refreshAuditEntries(limit = 200): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.dataLoading = true;
  try {
    appState.audits = await listAudit(appState.token, limit);
    appState.lastSyncAt = new Date().toISOString();
  } catch (error) {
    pushError(error);
  } finally {
    appState.dataLoading = false;
  }
}

export async function createRepeaterRecord(payload: RepeaterCreateRequest): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.actionLoading = true;
  try {
    await createRepeater(appState.token, payload);
    await refreshAllData();
    pushSuccess("Repeater created.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function refreshUsersList(): Promise<void> {
  if (!appState.token || !isAdmin.value) {
    return;
  }
  appState.dataLoading = true;
  try {
    appState.users = await listUsers(appState.token);
    appState.lastSyncAt = new Date().toISOString();
  } catch (error) {
    pushError(error);
  } finally {
    appState.dataLoading = false;
  }
}

export async function createUserAccount(payload: UserCreateRequest): Promise<void> {
  if (!appState.token || !isAdmin.value) {
    return;
  }
  appState.actionLoading = true;
  try {
    await createUser(appState.token, payload);
    await refreshUsersList();
    pushSuccess("User created.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function updateUserAccount(userId: string, payload: UserUpdateRequest): Promise<void> {
  if (!appState.token || !isAdmin.value) {
    return;
  }
  appState.actionLoading = true;
  try {
    await updateUser(appState.token, userId, payload);
    await refreshUsersList();
    pushSuccess("User updated.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function updateRepeaterRecord(
  repeaterId: string,
  payload: RepeaterUpdateRequest,
): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.actionLoading = true;
  try {
    await updateRepeater(appState.token, repeaterId, payload);
    await refreshAllData();
    pushSuccess("Repeater updated.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function removeRepeaterRecord(repeaterId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.actionLoading = true;
  try {
    await deleteRepeater(appState.token, repeaterId);
    await refreshAllData();
    pushSuccess("Repeater removed.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function removeStaleRepeaterRecords(inactiveHours = 168): Promise<number> {
  if (!appState.token) {
    return 0;
  }
  appState.actionLoading = true;
  try {
    const response = await deleteStaleRepeaters(appState.token, inactiveHours);
    await refreshAllData();
    pushSuccess(`Removed ${response.removed} stale repeater${response.removed === 1 ? "" : "s"}.`);
    return response.removed;
  } catch (error) {
    pushError(error);
    return 0;
  } finally {
    appState.actionLoading = false;
  }
}

export async function adoptPendingRepeater(repeaterId: string, note?: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.actionLoading = true;
  try {
    await adoptRepeater(appState.token, repeaterId, { note });
    await refreshAllData();
    pushSuccess("Repeater adopted.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function rejectPendingRepeater(repeaterId: string, note?: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.actionLoading = true;
  try {
    await rejectRepeater(appState.token, repeaterId, { note });
    await refreshAllData();
    pushSuccess("Repeater rejected.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function queueCommandEntry(payload: QueueCommandRequest): Promise<void> {
  if (!appState.token) {
    return;
  }
  appState.actionLoading = true;
  try {
    await queueCommand(appState.token, payload);
    await refreshCommandsList({ limit: 200 });
    pushSuccess("Command queued.");
  } catch (error) {
    pushError(error);
  } finally {
    appState.actionLoading = false;
  }
}

export async function loadCommandDetail(commandId: string): Promise<CommandQueueItemResponse> {
  if (!appState.token) {
    throw new Error("Not authenticated");
  }
  return getCommand(appState.token, commandId);
}

export function formatTimestamp(value: string | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}
