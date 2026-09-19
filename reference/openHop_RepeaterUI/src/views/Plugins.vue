<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import ApiService, { type CataloguePlugin, type PluginStatus } from '@/utils/api';
import Spinner from '@/components/ui/Spinner.vue';
import {
  Puzzle,
  RefreshCw,
  Upload,
  Power,
  PowerOff,
  Play,
  Square,
  RotateCcw,
  ScrollText,
  Trash2,
  ExternalLink,
  Settings,
  Download,
  Store,
  X,
} from '@lucide/vue';

defineOptions({ name: 'PluginsView' });

const PAGE_SIZE = 10;

const plugins = ref<PluginStatus[]>([]);
const loading = ref(false);
const initialLoadComplete = ref(false);
const error = ref<string | null>(null);
const managerUnavailable = ref(false);
const actionBusyId = ref<string | null>(null);
const statusMessage = ref<string | null>(null);
const searchQuery = ref('');
const page = ref(1);
const activeTab = ref<'installed' | 'catalogue'>('installed');

// Catalogue
const catalogue = ref<CataloguePlugin[]>([]);
const catalogueLoading = ref(false);
const catalogueError = ref<string | null>(null);
const catalogueLoaded = ref(false);
const catalogueBusyId = ref<string | null>(null);
const cataloguePage = ref(1);
const catalogueImageAspect = ref<Record<string, number>>({});

// Install dialog
const showInstallDialog = ref(false);
const installFile = ref<File | null>(null);
const installing = ref(false);
const installError = ref<string | null>(null);
const fileInput = ref<HTMLInputElement | null>(null);

// Logs dialog
const showLogsDialog = ref(false);
const logsPluginId = ref('');
const logsPluginName = ref('');
const logLines = ref<string[]>([]);
const logsLoading = ref(false);
const logsError = ref<string | null>(null);

// Uninstall dialog
const showUninstallDialog = ref(false);
const uninstallTarget = ref<PluginStatus | null>(null);
const uninstallDeleteData = ref(false);
const uninstalling = ref(false);

// Config dialog
const showConfigDialog = ref(false);
const configPlugin = ref<PluginStatus | null>(null);
const configPath = ref('');
const configText = ref('{}');
const configDefaults = ref<Record<string, unknown>>({});
const configUsingDefaults = ref(false);
const configLoading = ref(false);
const configSaving = ref(false);
const configError = ref<string | null>(null);
const configRestart = ref(true);

type PluginProgressState = 'idle' | 'running' | 'complete' | 'error' | 'timeout';
type PluginProgressOperation = 'install' | 'update';

const PROGRESS_LINE_LIMIT = 400;

const progressDialog = ref(false);
const progressPluginId = ref('');
const progressPluginName = ref('');
const progressOperation = ref<PluginProgressOperation | null>(null);
const progressState = ref<PluginProgressState>('idle');
const progressError = ref<string | null>(null);
const progressLines = ref<string[]>([]);
let progressSource: EventSource | null = null;

const progressTitle = computed(() => {
  if (!progressOperation.value) {
    return 'Plugin progress';
  }
  const verb = progressOperation.value === 'install' ? 'Installing' : 'Updating';
  return `${verb} ${progressPluginName.value || progressPluginId.value}`;
});

const filteredPlugins = computed(() => {
  const q = searchQuery.value.trim().toLowerCase();
  if (!q) return plugins.value;
  return plugins.value.filter((p) => {
    const hay = [p.id, p.name, p.version, p.state, p.description]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return hay.includes(q);
  });
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredPlugins.value.length / PAGE_SIZE)));

const pagedPlugins = computed(() => {
  const start = (page.value - 1) * PAGE_SIZE;
  return filteredPlugins.value.slice(start, start + PAGE_SIZE);
});

const installedPluginIds = computed(() => {
  const ids = new Set<string>();
  for (const plugin of plugins.value) {
    for (const candidate of pluginIdCandidates(plugin.id)) {
      ids.add(candidate);
    }
  }
  return ids;
});

const summaryCards = computed(() => {
  const list = plugins.value;
  const enabled = list.filter((p) => p.enabled).length;
  const running = list.filter((p) => p.state === 'RUNNING').length;
  const failed = list.filter((p) => p.state === 'FAILED').length;
  return [
    { label: 'Installed', value: String(list.length) },
    { label: 'Enabled', value: String(enabled) },
    { label: 'Running', value: String(running) },
    { label: 'Failed', value: String(failed) },
  ];
});

function stateBadgeClass(state?: string): string {
  switch ((state || '').toUpperCase()) {
    case 'UI READY':
      return 'bg-accent-green/opacity-light text-accent-green border-accent-green/opacity-medium';
    case 'RUNNING':
      return 'bg-accent-green/opacity-light text-accent-green border-accent-green/opacity-medium';
    case 'FAILED':
      return 'bg-accent-red/opacity-light text-accent-red border-accent-red/opacity-medium';
    case 'STARTING':
    case 'STOPPING':
      return 'bg-accent-amber/opacity-light text-accent-amber border-accent-amber/opacity-medium';
    case 'DISABLED':
      return 'bg-background-mute text-content-muted border-stroke-subtle';
    case 'STOPPED':
    default:
      return 'bg-accent-cyan/opacity-light text-accent-cyan border-accent-cyan/opacity-medium';
  }
}

function displayPluginState(plugin: PluginStatus): string {
  if (!plugin.has_runtime && plugin.has_ui) {
    return plugin.enabled ? 'UI READY' : 'DISABLED';
  }
  return plugin.state || 'UNKNOWN';
}

function pluginIdCandidates(id?: string | null): string[] {
  const raw = String(id || '').trim().toLowerCase();
  if (!raw) return [];
  const dot = raw.replace(/:/g, '.');
  const colon = raw.replace(/\./g, ':');
  const compact = raw.replace(/[.:]/g, '');
  return Array.from(new Set([raw, dot, colon, compact]));
}

function catalogueEntryFor(plugin: PluginStatus): CataloguePlugin | null {
  const idSet = new Set(pluginIdCandidates(plugin.id));
  for (const entry of catalogue.value) {
    for (const candidate of pluginIdCandidates(entry.id)) {
      if (idSet.has(candidate)) return entry;
    }
  }
  return null;
}

function pluginLatestVersion(plugin: PluginStatus): string | null {
  const fromPlugin = plugin.latestVersion || null;
  if (fromPlugin) return fromPlugin;
  return catalogueEntryFor(plugin)?.latestVersion || null;
}

function pluginHasUpdate(plugin: PluginStatus): boolean {
  if (plugin.updateAvailable) return true;
  const entry = catalogueEntryFor(plugin);
  if (entry?.updateAvailable) return true;
  const latest = pluginLatestVersion(plugin);
  if (!plugin.version || !latest) return false;
  return plugin.version !== latest;
}

function flash(message: string) {
  statusMessage.value = message;
  window.setTimeout(() => {
    if (statusMessage.value === message) statusMessage.value = null;
  }, 4000);
}

function progressStateLabel(state: PluginProgressState): string {
  const verb = progressOperation.value === 'update' ? 'Updating' : 'Installing';
  switch (state) {
    case 'running':
      return `${verb}...`;
    case 'complete':
      return 'Complete';
    case 'error':
    case 'timeout':
      return 'Error';
    case 'idle':
    default:
      return `${verb}...`;
  }
}

function progressStateClass(state: PluginProgressState): string {
  switch (state) {
    case 'complete':
      return 'bg-accent-green/opacity-light text-accent-green border-accent-green/opacity-medium';
    case 'error':
    case 'timeout':
      return 'bg-accent-red/opacity-light text-accent-red border-accent-red/opacity-medium';
    case 'running':
      return 'bg-accent-cyan/opacity-light text-accent-cyan border-accent-cyan/opacity-medium';
    case 'idle':
    default:
      return 'bg-accent-amber/opacity-light text-accent-amber border-accent-amber/opacity-medium';
  }
}

function closeProgressStream() {
  if (progressSource) {
    progressSource.close();
    progressSource = null;
  }
}

function openProgressDialog(pluginId: string, pluginName: string, operation: PluginProgressOperation) {
  progressDialog.value = true;
  progressPluginId.value = pluginId;
  progressPluginName.value = pluginName;
  progressOperation.value = operation;
  progressState.value = 'running';
  progressError.value = null;
  progressLines.value = [];
}

function dismissProgressDialog() {
  if (progressState.value === 'running' || progressState.value === 'idle') {
    return;
  }
  progressDialog.value = false;
}

function appendProgressLine(line: string) {
  progressLines.value.push(line);
  if (progressLines.value.length > PROGRESS_LINE_LIMIT) {
    progressLines.value.splice(0, progressLines.value.length - PROGRESS_LINE_LIMIT);
  }
}

function normalizeProgressState(state?: string): PluginProgressState {
  switch ((state || '').toLowerCase()) {
    case 'running':
    case 'complete':
    case 'error':
    case 'timeout':
    case 'idle':
      return state as PluginProgressState;
    default:
      return 'running';
  }
}

function clearProgressBusy(operation: PluginProgressOperation) {
  if (operation === 'install') {
    catalogueBusyId.value = null;
  } else {
    actionBusyId.value = null;
  }
}

function completeProgressOperation(
  operation: PluginProgressOperation,
  successMessage: string,
  refresh: () => Promise<void>,
  payload: { state?: string; error?: string | null },
) {
  const nextState = normalizeProgressState(payload.state);
  progressState.value = nextState;
  progressError.value =
    nextState === 'complete'
      ? null
      : payload.error || (nextState === 'timeout' ? 'Progress stream timed out' : 'Plugin operation failed');
  closeProgressStream();
  clearProgressBusy(operation);
  if (nextState === 'complete') {
    flash(successMessage);
    void refresh().catch((err) => {
      console.error('Failed to refresh plugins after progress completion:', err);
    });
  }
}

async function runProgressTrackedAction(
  pluginId: string,
  pluginName: string,
  operation: PluginProgressOperation,
  successMessage: string,
  startAction: () => Promise<{ success?: boolean; error?: string }>,
  refresh: () => Promise<void>,
) {
  closeProgressStream();
  openProgressDialog(pluginId, pluginName, operation);
  let streamDone = false;
  if (operation === 'install') {
    catalogueBusyId.value = pluginId;
  } else {
    actionBusyId.value = pluginId;
  }

  const source = ApiService.openPluginProgressStream(pluginId, 0, true);
  progressSource = source;
  source.onmessage = (event) => {
    try {
      const payload = JSON.parse(event.data) as {
        type?: string;
        line?: string;
        state?: string;
        error?: string | null;
      };
      switch (payload.type) {
        case 'connected':
        case 'keepalive':
          return;
        case 'line':
          if (payload.line) {
            appendProgressLine(payload.line);
          }
          progressState.value = 'running';
          return;
        case 'status':
          progressState.value = normalizeProgressState(payload.state);
          return;
        case 'done':
          streamDone = true;
          completeProgressOperation(operation, successMessage, refresh, payload);
          return;
        default:
          return;
      }
    } catch (err) {
      console.error('Failed to parse plugin progress event:', err);
    }
  };
  source.onerror = () => {
    if (progressSource !== source) {
      return;
    }
    if (streamDone) {
      return;
    }
    // Keep UI non-technical: action result remains authoritative.
    closeProgressStream();
  };

  try {
    const res = await startAction();
    if (res.success === false) {
      throw new Error(res.error || `${operation === 'install' ? 'Catalogue install' : 'Update'} failed`);
    }
    // Some environments can briefly drop SSE. If the action itself succeeded,
    // treat that as authoritative completion and refresh state.
    if (!streamDone) {
      streamDone = true;
      completeProgressOperation(operation, successMessage, refresh, { state: 'complete', error: null });
    }
  } catch (err) {
    progressState.value = 'error';
    progressError.value = err instanceof Error ? err.message : `${operation === 'install' ? 'Catalogue install' : 'Update'} failed`;
    closeProgressStream();
    clearProgressBusy(operation);
    throw err;
  }
}

async function fetchPlugins() {
  loading.value = true;
  error.value = null;
  managerUnavailable.value = false;
  try {
    const res = await ApiService.listPlugins();
    if (res.success === false) {
      throw new Error(res.error || 'Failed to list plugins');
    }
    plugins.value = Array.isArray(res.plugins) ? res.plugins : [];
    if (page.value > totalPages.value) page.value = totalPages.value;
    window.dispatchEvent(new CustomEvent('plugins-state-changed'));
  } catch (err) {
    const message = err instanceof Error ? err.message : 'Failed to load plugins';
    error.value = message;
    if (/unavailable|503/i.test(message)) {
      managerUnavailable.value = true;
    }
    plugins.value = [];
  } finally {
    loading.value = false;
    initialLoadComplete.value = true;
  }
}

async function runAction(id: string, action: () => Promise<unknown>, okMessage: string) {
  actionBusyId.value = id;
  error.value = null;
  try {
    await action();
    flash(okMessage);
    await fetchPlugins();
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Action failed';
  } finally {
    actionBusyId.value = null;
  }
}

function openInstallDialog() {
  installFile.value = null;
  installError.value = null;
  showInstallDialog.value = true;
}

function onFileChange(event: Event) {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0] ?? null;
  installFile.value = file;
  installError.value = null;
}

async function submitInstall() {
  if (!installFile.value) {
    installError.value = 'Select a .whl file to install';
    return;
  }
  if (!installFile.value.name.endsWith('.whl')) {
    installError.value = 'Only .whl packages are supported';
    return;
  }
  installing.value = true;
  installError.value = null;
  try {
    const res = await ApiService.installPluginWheel(installFile.value);
    if (res.success === false) {
      throw new Error(res.error || 'Install failed');
    }
    showInstallDialog.value = false;
    flash(`Installed ${res.plugin?.id || installFile.value.name}`);
    await fetchPlugins();
  } catch (err) {
    installError.value = err instanceof Error ? err.message : 'Install failed';
  } finally {
    installing.value = false;
  }
}

async function openLogs(plugin: PluginStatus) {
  logsPluginId.value = plugin.id;
  logsPluginName.value = plugin.name || plugin.id;
  logLines.value = [];
  logsError.value = null;
  showLogsDialog.value = true;
  logsLoading.value = true;
  try {
    const res = await ApiService.getPluginLogs(plugin.id, 300);
    if (res.success === false) {
      throw new Error(res.error || 'Failed to load logs');
    }
    logLines.value = Array.isArray(res.lines) ? res.lines : [];
  } catch (err) {
    logsError.value = err instanceof Error ? err.message : 'Failed to load logs';
  } finally {
    logsLoading.value = false;
  }
}

function openUninstall(plugin: PluginStatus) {
  uninstallTarget.value = plugin;
  uninstallDeleteData.value = false;
  showUninstallDialog.value = true;
}

async function openConfig(plugin: PluginStatus) {
  configPlugin.value = plugin;
  configPath.value = '';
  configText.value = '{\n}\n';
  configDefaults.value = {};
  configUsingDefaults.value = false;
  configError.value = null;
  configRestart.value = !!plugin.has_runtime;
  showConfigDialog.value = true;
  configLoading.value = true;
  try {
    const res = await ApiService.getPluginConfig(plugin.id);
    if (res.success === false) {
      throw new Error(res.error || 'Failed to load config');
    }
    configPath.value = res.path || '';
    const defaults =
      res.defaults && typeof res.defaults === 'object' && !Array.isArray(res.defaults)
        ? (res.defaults as Record<string, unknown>)
        : {};
    configDefaults.value = defaults;
    const payload = res.config ?? {};
    configUsingDefaults.value = !res.exists || Object.keys(payload as object).length === 0;
    configText.value = JSON.stringify(payload, null, 2) + '\n';
  } catch (err) {
    configError.value = err instanceof Error ? err.message : 'Failed to load config';
  } finally {
    configLoading.value = false;
  }
}

function resetConfigToDefaults() {
  if (!Object.keys(configDefaults.value).length) {
    configError.value = 'This plugin did not declare config defaults';
    return;
  }
  configError.value = null;
  configUsingDefaults.value = true;
  configText.value = JSON.stringify(configDefaults.value, null, 2) + '\n';
}

async function saveConfig() {
  if (!configPlugin.value) return;
  configError.value = null;
  let parsed: Record<string, unknown>;
  try {
    const value = JSON.parse(configText.value);
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
      throw new Error('Config must be a JSON object');
    }
    parsed = value as Record<string, unknown>;
  } catch (err) {
    configError.value = err instanceof Error ? err.message : 'Invalid JSON';
    return;
  }

  configSaving.value = true;
  try {
    const res = await ApiService.setPluginConfig(
      configPlugin.value.id,
      parsed,
      configRestart.value,
    );
    if (res.success === false) {
      throw new Error(res.error || 'Failed to save config');
    }
    showConfigDialog.value = false;
    const restarted = res.restarted ? ' and restarted' : '';
    flash(`Saved config for ${configPlugin.value.id}${restarted}`);
    await fetchPlugins();
  } catch (err) {
    configError.value = err instanceof Error ? err.message : 'Failed to save config';
  } finally {
    configSaving.value = false;
  }
}

async function confirmUninstall() {
  if (!uninstallTarget.value) return;
  uninstalling.value = true;
  try {
    await ApiService.uninstallPlugin(uninstallTarget.value.id, uninstallDeleteData.value);
    showUninstallDialog.value = false;
    flash(`Uninstalled ${uninstallTarget.value.id}`);
    await Promise.all([
      fetchPlugins(),
      catalogueLoaded.value ? fetchCatalogue(true) : Promise.resolve(),
    ]);
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Uninstall failed';
  } finally {
    uninstalling.value = false;
  }
}

function openUi(plugin: PluginStatus) {
  if (!plugin.has_ui || !plugin.enabled) return;
  window.open(`/plugins/${encodeURIComponent(plugin.id)}/`, '_blank', 'noopener');
}

function prevPage() {
  if (page.value > 1) page.value -= 1;
}

function nextPage() {
  if (page.value < totalPages.value) page.value += 1;
}


const catalogueTotalPages = computed(() =>
  Math.max(1, Math.ceil(catalogueAvailable.value.length / PAGE_SIZE)),
);
const catalogueAvailable = computed(() =>
  catalogue.value.filter((entry) => {
    const candidateIds = pluginIdCandidates(entry.id);
    const installed = candidateIds.some((candidate) => installedPluginIds.value.has(candidate));
    return !installed || !!entry.updateAvailable;
  }),
);
const pagedCatalogue = computed(() => {
  const start = (cataloguePage.value - 1) * PAGE_SIZE;
  return catalogueAvailable.value.slice(start, start + PAGE_SIZE);
});

function onCatalogueLogoError(event: Event) {
  const img = event.target;
  if (img instanceof HTMLImageElement) {
    img.style.display = 'none';
  }
}

function onCatalogueLogoLoad(id: string, event: Event) {
  const img = event.target;
  if (!(img instanceof HTMLImageElement)) return;
  const { naturalWidth, naturalHeight } = img;
  if (!naturalWidth || !naturalHeight) return;
  catalogueImageAspect.value = {
    ...catalogueImageAspect.value,
    [id]: naturalWidth / naturalHeight,
  };
}

function catalogueHeroImageClass(id: string): string {
  const aspect = catalogueImageAspect.value[id];
  if (!aspect) return 'w-full h-full object-cover object-center';
  // Square/portrait artwork is usually a logo and should remain fully visible.
  if (aspect <= 1.2) return 'w-full h-full object-contain object-center p-2';
  return 'w-full h-full object-cover object-center';
}

function catalogueReadmeUrl(entry: CataloguePlugin): string | null {
  const candidate = entry.homepage;
  if (!candidate) return null;
  if (!/^https?:\/\//i.test(candidate)) return null;
  return candidate;
}

function openCatalogueReadme(entry: CataloguePlugin) {
  const url = catalogueReadmeUrl(entry);
  if (!url) return;
  window.open(url, '_blank', 'noopener');
}

async function fetchCatalogue(refresh = false) {
  catalogueLoading.value = true;
  catalogueError.value = null;
  try {
    const res = await ApiService.listPluginCatalogue(refresh);
    if (res.success === false) {
      throw new Error(res.error || 'Could not load plugin catalogue');
    }
    catalogue.value = Array.isArray(res.plugins) ? res.plugins : [];
    if (cataloguePage.value > catalogueTotalPages.value) {
      cataloguePage.value = catalogueTotalPages.value;
    }
  } catch (err) {
    catalogueError.value =
      err instanceof Error ? err.message : 'Could not load plugin catalogue';
    catalogue.value = [];
  } finally {
    catalogueLoading.value = false;
    catalogueLoaded.value = true;
  }
}

async function selectTab(tab: 'installed' | 'catalogue') {
  activeTab.value = tab;
  if (tab === 'catalogue' && !catalogueLoaded.value) {
    await fetchCatalogue();
  }
  if (tab === 'installed') {
    await Promise.all([fetchPlugins(), fetchCatalogue(true)]);
  }
}

async function installFromCatalogue(entry: CataloguePlugin) {
  catalogueError.value = null;
  await runProgressTrackedAction(
    entry.id,
    entry.name || entry.id,
    'install',
    `Installed ${entry.name || entry.id}`,
    () => ApiService.installCataloguePlugin(entry.id),
    async () => {
      await Promise.all([fetchPlugins(), fetchCatalogue(true)]);
      activeTab.value = 'installed';
    },
  ).catch((err) => {
    catalogueError.value = err instanceof Error ? err.message : 'Catalogue install failed';
  });
}

async function updateInstalledPlugin(plugin: PluginStatus) {
  error.value = null;
  await runProgressTrackedAction(
    plugin.id,
    plugin.name || plugin.id,
    'update',
    `Updated ${plugin.name || plugin.id}`,
    () => ApiService.updatePlugin(plugin.id),
    async () => {
      await Promise.all([
        fetchPlugins(),
        catalogueLoaded.value ? fetchCatalogue(true) : Promise.resolve(),
      ]);
    },
  ).catch((err) => {
    error.value = err instanceof Error ? err.message : 'Update failed';
  });
}

async function checkUpdateFor(plugin: PluginStatus) {
  actionBusyId.value = plugin.id;
  error.value = null;
  try {
    const res = await ApiService.checkPluginUpdate(plugin.id, true);
    if (res.success === false) {
      throw new Error(res.error || 'Update check failed');
    }
    if (res.updateAvailable) {
      flash(
        `Update available for ${plugin.id}: ${res.installedVersion} → ${res.latestVersion}`,
      );
    } else if (res.reason) {
      flash(res.reason);
    } else {
      flash(`${plugin.id} is up to date (${res.latestVersion || res.installedVersion || 'unknown'})`);
    }
    // Merge hint onto local row
    const idx = plugins.value.findIndex((p) => p.id === plugin.id);
    if (idx >= 0) {
      plugins.value[idx] = {
        ...plugins.value[idx],
        latestVersion: res.latestVersion ?? plugins.value[idx].latestVersion,
        updateAvailable: !!res.updateAvailable,
      };
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Update check failed';
  } finally {
    actionBusyId.value = null;
  }
}

onMounted(() => {
  void fetchPlugins();
  void fetchCatalogue();
});

onBeforeUnmount(() => {
  closeProgressStream();
});
</script>

<template>
  <div class="p-3 sm:p-6 space-y-4 sm:space-y-6">
    <!-- Header -->
    <div class="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <h1 class="text-ui-title sm:text-ui-title-lg font-bold text-content-primary flex items-center gap-2">
          <Puzzle class="w-6 h-6 text-primary" />
          Plugins
        </h1>
        <p class="text-content-secondary dark:text-content-muted mt-1 sm:mt-2 text-ui-label sm:text-ui-body">
          Install and manage external openHop plugins. Lifecycle is handled by the plugin manager service.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button class="btn-secondary inline-flex items-center gap-2" :disabled="loading" @click="fetchPlugins">
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': loading }" />
          Refresh
        </button>
        <button class="btn-primary inline-flex items-center gap-2" @click="openInstallDialog">
          <Upload class="w-4 h-4" />
          Install wheel
        </button>
      </div>
    </div>

    <!-- Status banners -->
    <div
      v-if="managerUnavailable"
      class="glass-card rounded-[15px] p-4 border border-accent-amber/opacity-medium text-accent-amber text-sm"
    >
      Plugin manager is unavailable. Repeater is still running. Start
      <code class="mx-1">openhop-plugin-manager</code>
      to manage plugins.
    </div>
    <div
      v-else-if="error"
      class="glass-card rounded-[15px] p-4 border border-accent-red/opacity-medium text-accent-red text-sm"
    >
      {{ error }}
    </div>
    <div
      v-if="statusMessage"
      class="glass-card rounded-[15px] p-3 border border-accent-green/opacity-medium text-accent-green text-sm"
    >
      {{ statusMessage }}
    </div>

    <!-- Progress dialog -->
    <div
      v-if="progressDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="dismissProgressDialog"
    >
      <div class="glass-card w-full max-w-3xl rounded-[15px] p-5 sm:p-6 shadow-xl">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-lg font-semibold text-content-heading">{{ progressTitle }}</h3>
            <p class="mt-1 text-sm text-content-muted">{{ progressPluginId }}</p>
          </div>
          <span
            class="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold"
            :class="progressStateClass(progressState)"
          >
            <Spinner v-if="progressState === 'running'" class="w-3.5 h-3.5" />
            {{ progressStateLabel(progressState) }}
          </span>
        </div>

        <div
          v-if="progressLines.length"
          class="mt-4 rounded-[12px] border border-stroke-subtle dark:border-white/opacity-light bg-black/opacity-light"
        >
          <div class="max-h-80 overflow-auto p-3">
            <pre class="whitespace-pre-wrap break-words text-xs leading-5 text-content-primary">{{ progressLines.join('\n') }}</pre>
          </div>
        </div>

        <div
          v-if="progressError"
          class="mt-4 rounded-[12px] border border-accent-red/opacity-medium bg-accent-red/opacity-light p-3 text-sm text-accent-red"
        >
          {{ progressError }}
        </div>

        <div class="mt-4 flex justify-end">
          <button
            class="btn-secondary inline-flex items-center gap-2"
            :disabled="progressState === 'idle' || progressState === 'running'"
            @click="dismissProgressDialog"
          >
            <X class="w-4 h-4" />
            Close
          </button>
        </div>
      </div>
    </div>


    <!-- Tabs -->
    <div class="flex flex-wrap gap-2">
      <button
        class="px-3 py-1.5 rounded-[10px] text-sm border transition-colors"
        :class="activeTab === 'installed'
          ? 'bg-primary/opacity-light border-primary text-primary'
          : 'border-stroke-subtle text-content-muted hover:text-content-primary'"
        @click="selectTab('installed')"
      >
        Installed
      </button>
      <button
        class="px-3 py-1.5 rounded-[10px] text-sm border transition-colors inline-flex items-center gap-1.5"
        :class="activeTab === 'catalogue'
          ? 'bg-primary/opacity-light border-primary text-primary'
          : 'border-stroke-subtle text-content-muted hover:text-content-primary'"
        @click="selectTab('catalogue')"
      >
        <Store class="w-4 h-4" />
        Catalogue
      </button>
    </div>

    <div v-if="activeTab === 'installed'">
      <!-- Summary cards -->
      <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
        <div
          v-for="card in summaryCards"
          :key="card.label"
          class="glass-card rounded-[15px] p-4"
        >
          <div class="text-content-secondary dark:text-content-muted text-sm mb-1">{{ card.label }}</div>
          <div class="text-2xl font-bold text-content-primary">{{ card.value }}</div>
        </div>
      </div>

      <!-- Table card -->
      <div class="glass-card rounded-[15px] p-4 sm:p-6 mt-4">
        <div>
          <h2 class="text-lg font-semibold text-content-heading">Installed plugins</h2>
          <p class="text-sm text-content-muted">
            {{ filteredPlugins.length }} shown
            <span v-if="searchQuery">of {{ plugins.length }}</span>
          </p>
        </div>
        <input
          v-model="searchQuery"
          type="search"
          placeholder="Search plugins…"
          class="w-full sm:w-72 rounded-[10px] border border-stroke-subtle dark:border-white/opacity-light bg-transparent px-3 py-2 text-sm text-content-primary placeholder:text-content-muted"
          @input="page = 1"
        />

        <div v-if="loading && !initialLoadComplete" class="flex items-center justify-center py-12">
          <div class="text-center">
            <Spinner class="mx-auto mb-4" />
            <div class="text-content-secondary dark:text-content-muted">Loading plugins…</div>
          </div>
        </div>

        <div v-else-if="pagedPlugins.length === 0" class="py-10 text-center text-content-muted">
          No plugins installed yet. Use <span class="text-content-heading">Install wheel</span> to add one.
        </div>

        <div v-else class="overflow-x-auto rounded-[12px] border border-stroke-subtle dark:border-white/opacity-light mt-4">
          <table class="min-w-full text-sm">
            <thead class="bg-black/opacity-light dark:bg-white/opacity-subtle">
              <tr>
                <th class="px-3 py-2 text-left text-content-muted font-medium">Plugin</th>
                <th class="px-3 py-2 text-left text-content-muted font-medium">Version</th>
                <th class="px-3 py-2 text-left text-content-muted font-medium">State</th>
                <th class="px-3 py-2 text-left text-content-muted font-medium">Type</th>
                <th class="px-3 py-2 text-right text-content-muted font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
            <tr
              v-for="plugin in pagedPlugins"
              :key="plugin.id"
              class="border-t border-stroke-subtle dark:border-white/opacity-light"
            >
              <td class="px-3 py-3 align-top">
                <div class="flex items-center gap-2">
                  <div class="font-medium text-content-heading">{{ plugin.name || plugin.id }}</div>
                  <span
                    v-if="pluginHasUpdate(plugin)"
                    class="inline-flex rounded-full border border-accent-amber/opacity-medium bg-accent-amber/opacity-light px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-accent-amber"
                  >
                    Update available
                  </span>
                </div>
                <div class="text-xs text-content-muted break-all">{{ plugin.id }}</div>
                <div v-if="plugin.description" class="mt-1 text-xs text-content-muted line-clamp-2">
                  {{ plugin.description }}
                </div>
              </td>
              <td class="px-3 py-3 align-top text-content-heading">
                <div>{{ plugin.version || '—' }}</div>
                <div v-if="pluginHasUpdate(plugin) && pluginLatestVersion(plugin)" class="text-xs text-accent-amber">
                  Latest {{ pluginLatestVersion(plugin) }}
                </div>
              </td>
              <td class="px-3 py-3 align-top">
                <span
                  class="inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold"
                  :class="stateBadgeClass(displayPluginState(plugin))"
                >
                  {{ displayPluginState(plugin) }}
                </span>
                <div class="mt-1 text-xs text-content-muted">
                  <div v-if="plugin.has_runtime">
                    {{ plugin.enabled ? 'Enabled' : 'Disabled' }}
                    <span v-if="plugin.pid"> · pid {{ plugin.pid }}</span>
                  </div>
                  <div v-else-if="plugin.has_ui">
                    {{ plugin.enabled ? 'No background service' : 'UI disabled' }}
                  </div>
                  <div v-else>
                    {{ plugin.enabled ? 'Enabled' : 'Disabled' }}
                  </div>
                </div>
              </td>
              <td class="px-3 py-3 align-top text-content-muted">
                <div v-if="plugin.has_runtime">Service</div>
                <div v-if="plugin.has_ui">UI app</div>
                <div v-if="!plugin.has_runtime && !plugin.has_ui">—</div>
              </td>
              <td class="px-3 py-3 align-top">
                <div class="flex flex-wrap justify-end gap-1.5">
                  <button
                    v-if="!plugin.enabled"
                    class="btn-primary-xs inline-flex items-center gap-1"
                    :disabled="actionBusyId === plugin.id"
                    title="Enable"
                    @click="runAction(plugin.id, () => ApiService.enablePlugin(plugin.id), `Enabled ${plugin.id}`)"
                  >
                    <Power class="w-3.5 h-3.5" />
                    Enable
                  </button>
                  <button
                    v-else
                    class="btn-secondary-xs inline-flex items-center gap-1"
                    :disabled="actionBusyId === plugin.id"
                    title="Disable"
                    @click="runAction(plugin.id, () => ApiService.disablePlugin(plugin.id), `Disabled ${plugin.id}`)"
                  >
                    <PowerOff class="w-3.5 h-3.5" />
                    Disable
                  </button>

                  <button
                    v-if="plugin.has_runtime && plugin.enabled"
                    class="btn-secondary-xs inline-flex items-center gap-1"
                    :disabled="actionBusyId === plugin.id"
                    title="Start"
                    @click="runAction(plugin.id, () => ApiService.startPlugin(plugin.id), `Started ${plugin.id}`)"
                  >
                    <Play class="w-3.5 h-3.5" />
                  </button>
                  <button
                    v-if="plugin.has_runtime && plugin.enabled"
                    class="btn-secondary-xs inline-flex items-center gap-1"
                    :disabled="actionBusyId === plugin.id"
                    title="Stop"
                    @click="runAction(plugin.id, () => ApiService.stopPlugin(plugin.id), `Stopped ${plugin.id}`)"
                  >
                    <Square class="w-3.5 h-3.5" />
                  </button>
                  <button
                    v-if="plugin.has_runtime && plugin.enabled"
                    class="btn-secondary-xs inline-flex items-center gap-1"
                    :disabled="actionBusyId === plugin.id"
                    title="Restart"
                    @click="runAction(plugin.id, () => ApiService.restartPlugin(plugin.id), `Restarted ${plugin.id}`)"
                  >
                    <RotateCcw class="w-3.5 h-3.5" />
                  </button>

                  <button
                    class="btn-secondary-xs inline-flex items-center gap-1"
                    title="Config"
                    @click="openConfig(plugin)"
                  >
                    <Settings class="w-3.5 h-3.5" />
                  </button>
                  <button
                    class="btn-secondary-xs inline-flex items-center gap-1"
                    title="Logs"
                    @click="openLogs(plugin)"
                  >
                    <ScrollText class="w-3.5 h-3.5" />
                  </button>
                  <button
                    v-if="plugin.has_ui && plugin.enabled"
                    class="btn-secondary-xs inline-flex items-center gap-1"
                    title="Open UI"
                    @click="openUi(plugin)"
                  >
                    <ExternalLink class="w-3.5 h-3.5" />
                  </button>
                  <button
                    class="btn-danger-xs inline-flex items-center gap-1"
                    title="Uninstall"
                    @click="openUninstall(plugin)"
                  >
                    <Trash2 class="w-3.5 h-3.5" />
                  </button>
                </div>
              </td>
            </tr>
            </tbody>
          </table>
        </div>
      </div>
      <!-- Pagination -->
      <div
        v-if="filteredPlugins.length > PAGE_SIZE"
        class="mt-4 flex items-center justify-between gap-3 text-sm text-content-muted"
      >
        <button class="btn-secondary-xs" :disabled="page <= 1" @click="prevPage">Previous</button>
        <span>Page {{ page }} of {{ totalPages }}</span>
        <button class="btn-secondary-xs" :disabled="page >= totalPages" @click="nextPage">Next</button>
      </div>
    </div>


    <!-- Catalogue panel -->
    <div v-if="activeTab === 'catalogue'" class="glass-card rounded-[15px] p-4 sm:p-6 space-y-4">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 class="text-lg font-semibold text-content-heading">Plugin catalogue</h2>
          <p class="text-sm text-content-muted">
            Curated plugins. Versions come from GitHub Releases.
          </p>
        </div>
        <button
          class="btn-secondary inline-flex items-center gap-2"
          :disabled="catalogueLoading"
          @click="fetchCatalogue(true)"
        >
          <RefreshCw class="w-4 h-4" :class="{ 'animate-spin': catalogueLoading }" />
          Refresh
        </button>
      </div>

      <div
        v-if="catalogueError"
        class="rounded-[12px] border border-accent-amber/opacity-medium p-4 text-sm text-accent-amber space-y-2"
      >
        <p>Could not load plugin catalogue. Installed plugins are unaffected.</p>
        <p class="text-content-muted">{{ catalogueError }}</p>
        <button class="btn-secondary inline-flex items-center gap-2" @click="fetchCatalogue(true)">
          <RefreshCw class="w-4 h-4" />
          Retry
        </button>
      </div>

      <div v-else-if="catalogueLoading && !catalogueLoaded" class="flex items-center justify-center py-12">
        <div class="text-center">
          <Spinner class="mx-auto mb-4" />
          <div class="text-content-muted">Loading catalogue…</div>
        </div>
      </div>

      <div v-else-if="catalogue.length === 0" class="py-10 text-center text-content-muted">
        Catalogue is empty.
      </div>

      <div v-else-if="catalogueAvailable.length === 0" class="py-10 text-center text-content-muted">
        All catalogue plugins are already installed.
      </div>

      <div v-else class="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          v-for="entry in pagedCatalogue"
          :key="entry.id"
          class="rounded-[12px] border border-stroke-subtle dark:border-white/opacity-light overflow-hidden"
        >
          <div
            v-if="entry.logo"
            class="relative aspect-[16/6] border-b border-stroke-subtle dark:border-white/opacity-light bg-black/opacity-light overflow-hidden"
          >
            <a
              v-if="catalogueReadmeUrl(entry)"
              :href="catalogueReadmeUrl(entry) || undefined"
              target="_blank"
              rel="noopener noreferrer"
              class="block w-full h-full"
            >
              <img
                :src="entry.logo"
                :alt="`${entry.name} artwork`"
                :class="catalogueHeroImageClass(entry.id)"
                loading="lazy"
                referrerpolicy="no-referrer"
                @load="onCatalogueLogoLoad(entry.id, $event)"
                @error="onCatalogueLogoError"
              />
            </a>
            <img
              v-else
              :src="entry.logo"
              :alt="`${entry.name} artwork`"
              :class="catalogueHeroImageClass(entry.id)"
              loading="lazy"
              referrerpolicy="no-referrer"
              @load="onCatalogueLogoLoad(entry.id, $event)"
              @error="onCatalogueLogoError"
            />
          </div>

          <div class="p-4 space-y-3">
            <div class="flex items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="font-semibold text-content-heading">{{ entry.name }}</div>
                <div class="text-xs text-content-muted break-all">{{ entry.id }}</div>
              </div>
              <span
                v-if="entry.category"
                class="shrink-0 text-xs px-2 py-0.5 rounded-full border border-stroke-subtle text-content-muted"
              >
                {{ entry.category }}
              </span>
            </div>
            <p class="text-sm text-content-secondary line-clamp-3">{{ entry.description }}</p>
            <div class="text-xs text-content-muted break-all">{{ entry.repository }}</div>
            <div class="flex flex-wrap gap-3 text-xs text-content-muted">
              <span v-if="entry.latestVersion">Latest {{ entry.latestVersion }}</span>
              <span v-if="entry.installed">Installed {{ entry.installedVersion }}</span>
              <span v-if="entry.updateAvailable" class="text-accent-amber">Update available</span>
              <span v-if="entry.releasesError" class="text-accent-amber">{{ entry.releasesError }}</span>
            </div>
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <button
                  v-if="catalogueReadmeUrl(entry)"
                  class="btn-secondary inline-flex items-center gap-2"
                  @click="openCatalogueReadme(entry)"
                >
                  <ScrollText class="w-4 h-4" />
                  Homepage
                </button>
              </div>
              <div class="ml-auto flex items-center gap-2">
                <button
                  v-if="!entry.installed"
                  class="btn-primary inline-flex items-center gap-2"
                  :disabled="catalogueBusyId === entry.id"
                  @click="installFromCatalogue(entry)"
                >
                  <Download class="w-4 h-4" />
                  {{ catalogueBusyId === entry.id ? 'Installing…' : 'Install' }}
                </button>
                <button
                  v-else-if="entry.updateAvailable"
                  class="btn-primary inline-flex items-center gap-2"
                  :disabled="catalogueBusyId === entry.id || actionBusyId === entry.id"
                  @click="updateInstalledPlugin({ id: entry.id, name: entry.name })"
                >
                  <Download class="w-4 h-4" />
                  {{ actionBusyId === entry.id ? 'Updating…' : 'Update' }}
                </button>
                <span v-else class="text-sm text-accent-green">Installed</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-if="catalogueTotalPages > 1" class="flex items-center justify-end gap-2 pt-2">
        <button class="btn-secondary" :disabled="cataloguePage <= 1" @click="cataloguePage -= 1">Prev</button>
        <span class="text-sm text-content-muted">{{ cataloguePage }} / {{ catalogueTotalPages }}</span>
        <button
          class="btn-secondary"
          :disabled="cataloguePage >= catalogueTotalPages"
          @click="cataloguePage += 1"
        >
          Next
        </button>
      </div>
    </div>

    <!-- Install dialog -->
    <div
      v-if="showInstallDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="showInstallDialog = false"
    >
      <div class="glass-card w-full max-w-lg rounded-[15px] p-5 sm:p-6 shadow-xl">
        <div class="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 class="text-lg font-semibold text-content-heading">Install plugin wheel</h3>
            <p class="text-sm text-content-muted mt-1">
              Upload a local <code>.whl</code> containing <code>openhop-plugin.json</code>.
            </p>
          </div>
          <button class="btn-secondary-xs" @click="showInstallDialog = false">
            <X class="w-4 h-4" />
          </button>
        </div>

        <input
          ref="fileInput"
          type="file"
          accept=".whl,application/zip"
          class="block w-full text-sm text-content-muted file:mr-3 file:rounded-lg file:border-0 file:bg-primary/opacity-medium file:px-3 file:py-2 file:text-primary file:text-sm"
          @change="onFileChange"
        />
        <p v-if="installFile" class="mt-2 text-xs text-content-muted break-all">
          Selected: {{ installFile.name }}
        </p>
        <p v-if="installError" class="mt-3 text-sm text-accent-red">{{ installError }}</p>

        <div class="mt-5 flex justify-end gap-2">
          <button class="btn-secondary" :disabled="installing" @click="showInstallDialog = false">
            Cancel
          </button>
          <button class="btn-primary inline-flex items-center gap-2" :disabled="installing" @click="submitInstall">
            <Spinner v-if="installing" class="w-4 h-4" />
            <Upload v-else class="w-4 h-4" />
            Install
          </button>
        </div>
      </div>
    </div>

    <!-- Logs dialog -->
    <div
      v-if="showLogsDialog"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="showLogsDialog = false"
    >
      <div class="glass-card w-full max-w-3xl rounded-[15px] p-5 sm:p-6 shadow-xl max-h-[85vh] flex flex-col">
        <div class="flex items-start justify-between gap-3 mb-4">
          <div>
            <h3 class="text-lg font-semibold text-content-heading">Logs · {{ logsPluginName }}</h3>
            <p class="text-xs text-content-muted mt-1 break-all">{{ logsPluginId }}</p>
          </div>
          <button class="btn-secondary-xs" @click="showLogsDialog = false">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div v-if="logsLoading" class="flex justify-center py-10">
          <Spinner />
        </div>
        <div v-else-if="logsError" class="text-sm text-accent-red py-4">{{ logsError }}</div>
        <pre
          v-else
          class="flex-1 overflow-auto rounded-[12px] border border-stroke-subtle dark:border-white/opacity-light bg-black/opacity-light dark:bg-black/opacity-medium p-3 text-xs text-content-heading whitespace-pre-wrap break-all min-h-[240px]"
        >{{ logLines.length ? logLines.join('\n') : 'No log lines yet.' }}</pre>

        <div class="mt-4 flex justify-end gap-2">
          <button
            class="btn-secondary"
            :disabled="logsLoading"
            @click="openLogs({ id: logsPluginId, name: logsPluginName })"
          >
            Refresh
          </button>
          <button class="btn-primary" @click="showLogsDialog = false">Close</button>
        </div>
      </div>
    </div>

    <!-- Uninstall dialog -->
    <div
      v-if="showUninstallDialog && uninstallTarget"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="showUninstallDialog = false"
    >
      <div class="glass-card w-full max-w-md rounded-[15px] p-5 sm:p-6 shadow-xl">
        <h3 class="text-lg font-semibold text-content-heading">Uninstall plugin</h3>
        <p class="mt-2 text-sm text-content-muted">
          Remove
          <span class="text-content-heading font-medium">{{ uninstallTarget.name || uninstallTarget.id }}</span>
          release code and stop any running process.
        </p>
        <label class="mt-4 flex items-center gap-2 text-sm text-content-primary">
          <input v-model="uninstallDeleteData" type="checkbox" class="rounded border-stroke-subtle" />
          Also delete persistent data directory
        </label>
        <p class="mt-2 text-xs text-content-muted">
          Default keeps <code>data/</code> so configuration survives reinstall.
        </p>
        <div class="mt-5 flex justify-end gap-2">
          <button class="btn-secondary" :disabled="uninstalling" @click="showUninstallDialog = false">
            Cancel
          </button>
          <button class="btn-danger inline-flex items-center gap-2" :disabled="uninstalling" @click="confirmUninstall">
            <Spinner v-if="uninstalling" class="w-4 h-4" />
            <Trash2 v-else class="w-4 h-4" />
            Uninstall
          </button>
        </div>
      </div>
    </div>

    <!-- Config dialog -->
    <div
      v-if="showConfigDialog && configPlugin"
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      @click.self="showConfigDialog = false"
    >
      <div class="glass-card w-full max-w-2xl rounded-[15px] p-5 sm:p-6 shadow-xl max-h-[90vh] flex flex-col">
        <div class="flex items-start justify-between gap-3 mb-3">
          <div>
            <h3 class="text-lg font-semibold text-content-heading">
              Config · {{ configPlugin.name || configPlugin.id }}
            </h3>
            <p class="text-xs text-content-muted mt-1 break-all">
              {{ configPath || 'data/config.json' }}
            </p>
            <p class="text-xs text-content-muted mt-1">
              Plugin-owned settings. The manager stores this JSON under the plugin data directory and does not interpret keys.
            </p>
          </div>
          <button class="btn-secondary-xs" @click="showConfigDialog = false">
            <X class="w-4 h-4" />
          </button>
        </div>

        <div
          v-if="configUsingDefaults && Object.keys(configDefaults).length"
          class="mb-3 rounded-[10px] border border-accent-amber/opacity-medium bg-accent-amber/opacity-light px-3 py-2 text-xs text-accent-amber"
        >
          Showing plugin default settings. Edit and save to write
          <code>data/config.json</code>.
        </div>

        <div v-if="configLoading" class="flex justify-center py-10">
          <Spinner />
        </div>
        <textarea
          v-else
          v-model="configText"
          spellcheck="false"
          class="w-full min-h-[280px] flex-1 rounded-[12px] border border-stroke-subtle dark:border-white/opacity-light bg-black/opacity-light dark:bg-black/opacity-medium p-3 font-mono text-xs text-content-heading"
        ></textarea>

        <p v-if="configError" class="mt-3 text-sm text-accent-red">{{ configError }}</p>

        <label
          v-if="configPlugin.has_runtime"
          class="mt-3 flex items-center gap-2 text-sm text-content-primary"
        >
          <input v-model="configRestart" type="checkbox" class="rounded border-stroke-subtle" />
          Restart plugin after save
        </label>

        <div class="mt-4 flex flex-wrap justify-end gap-2">
          <button
            class="btn-secondary"
            :disabled="configLoading || configSaving || !Object.keys(configDefaults).length"
            @click="resetConfigToDefaults"
          >
            Reset to defaults
          </button>
          <button class="btn-secondary" :disabled="configSaving" @click="showConfigDialog = false">
            Cancel
          </button>
          <button
            class="btn-primary inline-flex items-center gap-2"
            :disabled="configLoading || configSaving"
            @click="saveConfig"
          >
            <Spinner v-if="configSaving" class="w-4 h-4" />
            <Settings v-else class="w-4 h-4" />
            Save
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
