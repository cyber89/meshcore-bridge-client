<script setup lang="ts">
import { ref, watch } from 'vue';
import QRCode from 'qrcode';

const props = withDefaults(
  defineProps<{
    isOpen: boolean;
    title: string;
    subtitle?: string;
    value: string;
  }>(),
  {
    subtitle: '',
  },
);

const emit = defineEmits<{
  (event: 'close'): void;
}>();

const qrDataUrl = ref('');
const qrError = ref<string | null>(null);

async function renderQrCode() {
  qrError.value = null;
  qrDataUrl.value = '';

  if (!props.value?.trim()) {
    qrError.value = 'No QR payload is available for this identity.';
    return;
  }

  try {
    qrDataUrl.value = await QRCode.toDataURL(props.value, {
      width: 320,
      margin: 2,
      errorCorrectionLevel: 'M',
      color: {
        dark: '#111827',
        light: '#ffffffff',
      },
    });
  } catch (error) {
    qrError.value = error instanceof Error ? error.message : 'Failed to render QR code.';
  }
}

async function copyPayload() {
  if (!props.value?.trim()) {
    return;
  }
  try {
    await navigator.clipboard.writeText(props.value);
  } catch {
    // Clipboard failures are non-fatal; users can still manually copy the payload.
  }
}

watch(
  () => [props.isOpen, props.value],
  ([isOpen]) => {
    if (isOpen) {
      void renderQrCode();
    }
  },
  { immediate: true },
);
</script>

<template>
  <Teleport to="body">
    <div v-if="isOpen" class="modal-backdrop" @click.self="emit('close')">
      <div
        class="bg-white dark:bg-surface-elevated backdrop-blur-xl border border-stroke-subtle dark:border-white/opacity-light rounded-[15px] p-6 max-w-lg w-full"
      >
        <div class="flex items-start justify-between gap-4 mb-4">
          <div>
            <h3 class="text-xl font-bold text-content-primary">{{ title }}</h3>
            <p v-if="subtitle" class="mt-1 text-sm text-content-secondary dark:text-content-muted">
              {{ subtitle }}
            </p>
          </div>
          <button
            type="button"
            class="text-content-secondary hover:text-content-primary dark:text-content-muted dark:hover:text-content-primary"
            @click="emit('close')"
            aria-label="Close QR modal"
          >
            <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div class="rounded-[12px] border border-stroke-subtle dark:border-white/opacity-light bg-background-card dark:bg-white/opacity-subtle p-4">
          <div v-if="qrError" class="text-sm text-accent-red">
            {{ qrError }}
          </div>
          <div v-else class="flex justify-center">
            <img
              v-if="qrDataUrl"
              :src="qrDataUrl"
              alt="MeshCore QR code"
              class="rounded-[8px] border border-stroke-subtle bg-white p-2"
            />
          </div>
        </div>

        <div class="mt-4 rounded-[12px] border border-stroke-subtle dark:border-white/opacity-light bg-background-card dark:bg-white/opacity-subtle p-3">
          <p class="mb-2 text-xs uppercase tracking-wide text-content-muted">Payload</p>
          <p class="font-mono text-xs break-all text-content-primary/opacity-heavy">
            {{ value }}
          </p>
        </div>

        <div class="mt-5 flex justify-end gap-2">
          <button type="button" class="btn-secondary" @click="copyPayload">Copy Link</button>
          <button type="button" class="btn-primary" @click="emit('close')">Close</button>
        </div>
      </div>
    </div>
  </Teleport>
</template>