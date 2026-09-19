<template>
  <div
    class="fixed inset-0 z-[1500] flex items-center justify-center bg-slate-950/80 p-4 backdrop-blur-sm"
    role="dialog"
    aria-modal="true"
    aria-label="Server setup wizard"
  >
    <section class="glass-card w-full max-w-xl p-6 sm:p-8">
      <!-- Header -->
      <header class="mb-6">
        <div class="mb-4 flex items-center justify-between">
          <h2 class="text-xl font-semibold text-slate-100">Server Setup</h2>
          <span class="text-xs text-slate-400">Step {{ currentStep }} of {{ totalSteps }}</span>
        </div>
        <!-- Step dots -->
        <div class="flex gap-2">
          <span
            v-for="n in totalSteps"
            :key="n"
            class="h-1.5 flex-1 rounded-full transition-colors duration-200"
            :class="n <= currentStep ? 'bg-cyan-400' : 'bg-slate-700'"
          />
        </div>
      </header>

      <!-- Step 1: Welcome -->
      <template v-if="currentStep === 1">
        <div class="space-y-4">
          <div class="flex items-start gap-3 rounded-xl border border-slate-700/60 bg-slate-900/50 p-4">
            <span class="mt-0.5 text-2xl">🛰️</span>
            <div>
              <h3 class="font-semibold text-slate-100">Welcome to pyMC_Glass</h3>
              <p class="mt-1 text-sm text-slate-400">
                This wizard will help you configure the core server settings so your repeaters
                can connect. It only takes a minute.
              </p>
            </div>
          </div>
          <ul class="space-y-2 pl-1 text-sm text-slate-300">
            <li class="flex items-center gap-2">
              <span class="text-cyan-400">✓</span> MQTT broker connection details
            </li>
            <li class="flex items-center gap-2">
              <span class="text-cyan-400">✓</span> TLS / certificate options
            </li>
            <li class="flex items-center gap-2">
              <span class="text-cyan-400">✓</span> Push settings to all repeaters
            </li>
          </ul>
        </div>
      </template>

      <!-- Step 2: MQTT Broker -->
      <template v-else-if="currentStep === 2">
        <div class="space-y-4">
          <p class="text-sm text-slate-400">
            Enter the MQTT broker details that your repeaters will connect to.
          </p>
          <label class="field-label">
            Broker hostname or IP
            <input
              v-model.trim="form.mqtt_broker_host"
              class="field"
              type="text"
              placeholder="e.g. mqtt.example.com or 192.168.1.10"
              required
            />
          </label>
          <div class="grid grid-cols-2 gap-3">
            <label class="field-label">
              Port
              <span class="ml-1 text-xs text-slate-500">
                ({{ form.mqtt_tls_enabled ? 'TLS default: 8883' : 'default: 1883' }})
              </span>
              <input
                v-model.number="form.mqtt_broker_port"
                class="field"
                type="number"
                min="1"
                max="65535"
                required
                @input="portManuallyEdited = true"
              />
            </label>
            <label class="field-label">
              Base topic
              <input
                v-model.trim="form.mqtt_base_topic"
                class="field"
                type="text"
                placeholder="glass"
                required
              />
            </label>
          </div>
          <p v-if="step2Error" class="text-xs text-red-400">{{ step2Error }}</p>
        </div>
      </template>

      <!-- Step 3: TLS -->
      <template v-else-if="currentStep === 3">
        <div class="space-y-4">
          <p class="text-sm text-slate-400">
            Enable TLS so repeater connections are encrypted and authenticated with certificates.
          </p>
          <label class="flex cursor-pointer items-center gap-3 rounded-xl border border-slate-700/60 bg-slate-900/50 p-4 transition-colors hover:border-cyan-500/40">
            <input
              v-model="form.mqtt_tls_enabled"
              type="checkbox"
              class="h-4 w-4 accent-cyan-400"
            />
            <div>
              <span class="font-medium text-slate-100">Enable TLS</span>
              <p class="mt-0.5 text-xs text-slate-400">
                Repeaters will connect over TLS and present client certificates signed by this
                server's PKI.
              </p>
            </div>
          </label>
          <div
            v-if="form.mqtt_tls_enabled"
            class="rounded-xl border border-cyan-700/40 bg-cyan-950/20 p-4 text-sm text-slate-300"
          >
            <p class="font-medium text-cyan-300">Automatic certificate management</p>
            <p class="mt-1 text-slate-400">
              pyMC_Glass will automatically generate a local Certificate Authority, broker
              certificate, and per-repeater client certificates. No manual certificate handling
              required.
            </p>
            <ul class="mt-2 space-y-1 text-xs text-slate-400">
              <li>• CA + broker cert generated on first start</li>
              <li>• Each repeater receives its own client cert on adoption</li>
              <li>• Certs are renewed automatically before expiry</li>
            </ul>
          </div>
          <div
            v-else
            class="rounded-xl border border-slate-700/40 bg-slate-900/30 p-4 text-sm text-slate-400"
          >
            TLS is disabled. Repeater connections will use plain MQTT. You can enable TLS later
            from <span class="text-slate-300">Settings → Global Managed MQTT</span>.
          </div>
        </div>
      </template>

      <!-- Step 4: Review & Apply -->
      <template v-else-if="currentStep === 4">
        <div class="space-y-4">
          <p class="text-sm text-slate-400">
            Review your settings before saving. These will be pushed to all currently managed
            repeaters.
          </p>
          <dl class="space-y-2 rounded-xl border border-slate-700/60 bg-slate-900/50 p-4 text-sm">
            <div class="flex justify-between gap-2">
              <dt class="text-slate-400">Broker host</dt>
              <dd class="font-mono text-slate-100">{{ form.mqtt_broker_host || '—' }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-400">Port</dt>
              <dd class="font-mono text-slate-100">{{ form.mqtt_broker_port }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-400">Base topic</dt>
              <dd class="font-mono text-slate-100">{{ form.mqtt_base_topic }}</dd>
            </div>
            <div class="flex justify-between gap-2">
              <dt class="text-slate-400">TLS</dt>
              <dd :class="form.mqtt_tls_enabled ? 'text-cyan-300' : 'text-slate-400'">
                {{ form.mqtt_tls_enabled ? 'Enabled (auto PKI)' : 'Disabled' }}
              </dd>
            </div>
          </dl>
          <p v-if="saveError" class="text-xs text-red-400">{{ saveError }}</p>
        </div>
      </template>

      <!-- Footer nav -->
      <footer class="mt-6 flex items-center justify-between gap-3 border-t border-slate-700/60 pt-4">
        <div>
          <button
            v-if="currentStep > 1"
            class="btn btn-ghost"
            type="button"
            :disabled="saving"
            @click="prevStep"
          >
            Back
          </button>
          <button
            v-else
            class="btn btn-ghost text-slate-500 hover:text-slate-300"
            type="button"
            @click="skipWizard"
          >
            Skip for now
          </button>
        </div>
        <button
          v-if="currentStep < totalSteps"
          class="btn btn-primary"
          type="button"
          @click="nextStep"
        >
          Next
        </button>
        <button
          v-else
          class="btn btn-primary"
          type="button"
          :disabled="saving"
          @click="saveAndApply"
        >
          {{ saving ? 'Saving…' : 'Save & Apply' }}
        </button>
      </footer>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from "vue";
import { saveManagedMqttSettings } from "../../state/appState";

const emit = defineEmits<{ complete: [] }>();

const SKIP_KEY = "pymc_glass_setup_wizard_skipped";
const DEFAULT_PORT_PLAIN = 1883;
const DEFAULT_PORT_TLS = 8883;

const totalSteps = 4;
const currentStep = ref(1);
const saving = ref(false);
const saveError = ref<string | null>(null);
const portManuallyEdited = ref(false);

const form = reactive({
  mqtt_broker_host: "",
  mqtt_broker_port: DEFAULT_PORT_PLAIN,
  mqtt_base_topic: "glass",
  mqtt_tls_enabled: false,
});

// Auto-switch port when TLS is toggled, unless the user already typed a custom port.
watch(
  () => form.mqtt_tls_enabled,
  (tlsOn) => {
    if (!portManuallyEdited.value) {
      form.mqtt_broker_port = tlsOn ? DEFAULT_PORT_TLS : DEFAULT_PORT_PLAIN;
    }
  },
);

const step2Error = computed(() => {
  if (currentStep.value !== 2) return null;
  if (!form.mqtt_broker_host) return "Broker hostname is required.";
  if (form.mqtt_broker_port < 1 || form.mqtt_broker_port > 65535) return "Port must be 1–65535.";
  if (!form.mqtt_base_topic) return "Base topic is required.";
  return null;
});

function prevStep(): void {
  if (currentStep.value > 1) currentStep.value--;
}

function nextStep(): void {
  if (currentStep.value === 2 && step2Error.value) return;
  if (currentStep.value < totalSteps) currentStep.value++;
}

function skipWizard(): void {
  localStorage.setItem(SKIP_KEY, "1");
  emit("complete");
}

async function saveAndApply(): Promise<void> {
  saving.value = true;
  saveError.value = null;
  try {
    const result = await saveManagedMqttSettings({
      mqtt_enabled: true,
      mqtt_broker_host: form.mqtt_broker_host,
      mqtt_broker_port: form.mqtt_broker_port,
      mqtt_base_topic: form.mqtt_base_topic,
      mqtt_tls_enabled: form.mqtt_tls_enabled,
      queue_to_repeaters: true,
      reason: "Initial server setup wizard",
    });
    if (result) {
      localStorage.removeItem(SKIP_KEY);
      emit("complete");
    } else {
      saveError.value = "Failed to save settings. Check your connection and try again.";
    }
  } catch (err) {
    saveError.value = err instanceof Error ? err.message : "Unexpected error saving settings.";
  } finally {
    saving.value = false;
  }
}
</script>
