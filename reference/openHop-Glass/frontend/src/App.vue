<template>
  <RouterView />
  <SetupWizardModal
    v-if="appState.setupWizardVisible"
    @complete="appState.setupWizardVisible = false"
  />
  <div
    v-if="showReleasePopup && !appState.setupWizardVisible"
    class="fixed inset-0 z-[1400] flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-label="Release update"
  >
    <section class="glass-card w-full max-w-2xl p-5 sm:p-6">
      <header class="mb-3 flex items-start justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-slate-100">What’s new in v{{ appVersion }}</h2>
          <p class="mt-1 text-xs text-slate-400">This appears once per version in your browser.</p>
        </div>
        <button class="btn btn-ghost btn-sm" @click="dismissReleasePopup">Close</button>
      </header>

      <div class="max-h-[45vh] overflow-y-auto rounded-xl border border-slate-700/70 bg-slate-950/35 p-3">
        <pre class="release-pre whitespace-pre-wrap break-words">{{ releaseNotes }}</pre>
      </div>

      <footer class="mt-4 flex flex-col items-start justify-between gap-3 border-t border-slate-700/70 pt-3 sm:flex-row sm:items-center">
        <a
          v-if="buyMeCoffeeUrl"
          class="text-sm font-medium text-cyan-300 underline-offset-2 hover:text-cyan-200 hover:underline"
          :href="buyMeCoffeeUrl"
          target="_blank"
          rel="noopener noreferrer"
        >
          ☕ Support on Buy Me a Coffee
        </a>
        <button class="btn btn-primary" @click="dismissReleasePopup">Got it</button>
      </footer>
    </section>
  </div>
</template>
<script setup lang="ts">
import { RouterView, useRoute } from "vue-router";
import { onMounted, ref, watch } from "vue";
import { appState, isAuthenticated } from "./state/appState";
import SetupWizardModal from "./components/ui/SetupWizardModal.vue";

const VERSION_COOKIE_NAME = "pymc_glass_seen_version";
const appVersion = ((import.meta.env.VITE_APP_VERSION as string | undefined) ?? "0.1.0").trim();
const buyMeCoffeeUrl = (
  (import.meta.env.VITE_BUYMEACOFFEE_URL as string | undefined) ??
  "https://buymeacoffee.com/rightup"
).trim();

const showReleasePopup = ref(false);
const releaseNotes = ref("Loading changelog...");
const releaseCheckStarted = ref(false);
const route = useRoute();

function getCookie(name: string): string | null {
  const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
  return match ? decodeURIComponent(match[1]) : null;
}

function setCookie(name: string, value: string, days = 365): void {
  const expires = new Date(Date.now() + days * 24 * 60 * 60 * 1000).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

function extractVersionSection(markdown: string, version: string): string | null {
  const escapedVersion = version.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const versionRegex = new RegExp(
    `## \\[${escapedVersion}\\][\\s\\S]*?(?=\\n## \\[|$)`,
  );
  const matchedVersion = markdown.match(versionRegex);
  if (matchedVersion?.[0]) {
    return matchedVersion[0].trim();
  }

  const unreleasedRegex = /## \[Unreleased\][\s\S]*?(?=\n## \[|$)/;
  const matchedUnreleased = markdown.match(unreleasedRegex);
  return matchedUnreleased?.[0]?.trim() ?? null;
}

async function loadReleaseNotes(version: string): Promise<string> {
  try {
    const response = await fetch("/CHANGELOG.md", { cache: "no-store" });
    if (!response.ok) {
      return "Changelog is currently unavailable.";
    }
    const markdown = await response.text();
    return (
      extractVersionSection(markdown, version) ??
      "No specific changelog section found for this version."
    );
  } catch {
    return "Unable to load changelog right now.";
  }
}

async function maybeShowReleasePopup(): Promise<void> {
  const seenVersion = getCookie(VERSION_COOKIE_NAME);
  if (seenVersion === appVersion) {
    return;
  }
  releaseNotes.value = await loadReleaseNotes(appVersion);
  showReleasePopup.value = true;
}

function dismissReleasePopup(): void {
  setCookie(VERSION_COOKIE_NAME, appVersion);
  showReleasePopup.value = false;
}
function canCheckReleasePopup(): boolean {
  return isAuthenticated.value && route.name !== "login";
}

async function maybeShowReleasePopupAfterLogin(): Promise<void> {
  if (releaseCheckStarted.value || !canCheckReleasePopup()) {
    return;
  }
  releaseCheckStarted.value = true;
  await maybeShowReleasePopup();
}

onMounted(() => {
  void maybeShowReleasePopupAfterLogin();
});

watch([isAuthenticated, () => route.name], () => {
  void maybeShowReleasePopupAfterLogin();
});
</script>
<style scoped>
.release-pre {
  margin: 0;
  color: #d5e0f3;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono",
    "Courier New", monospace;
  font-size: 0.82rem;
  line-height: 1.45;
}
</style>

