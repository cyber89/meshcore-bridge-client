<script setup lang="ts">
import { ref, nextTick, onUnmounted, Teleport } from 'vue';

// Global menu management to ensure only one menu is open at a time
interface MenuManager {
  activeMenu: { closeMenu: () => void } | null;
  setActiveMenu: (menu: { closeMenu: () => void } | null) => void;
}

const globalMenuManager: MenuManager = (
  window as unknown as { __neighborMenuManager?: MenuManager }
).__neighborMenuManager || {
  activeMenu: null,
  setActiveMenu: (menu: { closeMenu: () => void } | null) => {
    if (globalMenuManager.activeMenu && globalMenuManager.activeMenu !== menu) {
      try {
        globalMenuManager.activeMenu.closeMenu();
      } catch (error) {
        console.warn('Error closing previous menu:', error);
      }
    }
    globalMenuManager.activeMenu = menu;
  },
};

// Store global reference
(window as unknown as { __neighborMenuManager: MenuManager }).__neighborMenuManager =
  globalMenuManager;

interface Neighbor {
  id: number;
  timestamp?: number;
  pubkey?: string;
  node_name?: string | null;
  is_repeater?: boolean;
  route_type?: number | null;
  contact_type?: string;
  latitude?: number | null;
  longitude?: number | null;
  first_seen?: number;
  last_seen?: number;
  rssi?: number | null;
  snr?: number | null;
  advert_count?: number;
  is_new_neighbor?: boolean;
  short_name?: string;
  long_name?: string;
  node_num?: number;
  node_num_hex?: string;
  hw_model?: string;
}

interface Props {
  neighbor: Neighbor;
  canPing?: boolean;
  /** Off by default: only repeater identities answer the region-scopes request —
   *  core routes it straight to the login handler for a room server. */
  canQueryScopes?: boolean;
}

interface Emits {
  (e: 'ping', neighbor: Neighbor): void;
  (e: 'delete', neighbor: Neighbor): void;
  (e: 'show-details', neighbor: Neighbor): void;
  (e: 'query-scopes', neighbor: Neighbor): void;
}

const props = defineProps<Props>();
const emit = defineEmits<Emits>();

// Kept in step with the `w-44` class on the menu below, which the mobile
// overflow check needs to know before the menu is rendered and measurable.
// Widened from w-36/144px because "Query Scopes" did not fit on one line: a
// button is text-align:center by default, so the wrapped label centred itself and
// read as an indent next to the single-line items.
const MENU_WIDTH_PX = 176;

const showMenu = ref(false);
const buttonRef = ref<HTMLButtonElement>();
const menuRef = ref<HTMLDivElement>();
const menuPosition = ref({ top: 0, left: 0 });

// Menu control functions
const closeMenu = () => {
  showMenu.value = false;
  document.removeEventListener('click', handleGlobalClick, true);
  document.removeEventListener('keydown', handleEscapeKey);
  if (globalMenuManager.activeMenu === menuInstance) {
    globalMenuManager.activeMenu = null;
  }
};

// Create menu instance for global management
const menuInstance = { closeMenu };

const handlePing = () => {
  closeMenu();
  emit('ping', props.neighbor);
};

const handleShowDetails = () => {
  closeMenu();
  emit('show-details', props.neighbor);
};

const handleQueryScopes = () => {
  closeMenu();
  emit('query-scopes', props.neighbor);
};

const handleDelete = () => {
  closeMenu();
  emit('delete', props.neighbor);
};

// Improved click outside handling with capture phase
const handleGlobalClick = (event: MouseEvent) => {
  const target = event.target as Element;
  if (!target.closest('[data-menu-container]')) {
    closeMenu();
  }
};

// Handle escape key
const handleEscapeKey = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    closeMenu();
  }
};

// Toggle menu and position it
const toggleMenu = async () => {
  if (!showMenu.value && buttonRef.value) {
    // Close any other open menu first
    globalMenuManager.setActiveMenu(menuInstance);

    // Calculate position
    const rect = buttonRef.value.getBoundingClientRect();
    const viewportWidth = window.innerWidth;
    const menuWidth = MENU_WIDTH_PX;

    // Check if we're on mobile and if menu would overflow on the right
    const isMobile = viewportWidth < 1024; // lg breakpoint
    const wouldOverflow = rect.left + menuWidth > viewportWidth - 16; // 16px margin

    let leftPosition = rect.left;
    if (isMobile && wouldOverflow) {
      // Position menu to the left of the button on mobile
      leftPosition = rect.right - menuWidth;
    }

    // Ensure menu doesn't go off the left edge
    leftPosition = Math.max(8, leftPosition);

    menuPosition.value = {
      top: rect.bottom + 4,
      left: leftPosition,
    };

    showMenu.value = true;

    await nextTick();

    // Flip upward if the menu would overflow the bottom of the viewport
    if (menuRef.value) {
      const menuHeight = menuRef.value.offsetHeight;
      if (rect.bottom + 4 + menuHeight > window.innerHeight - 8) {
        menuPosition.value = {
          top: rect.top - menuHeight - 4,
          left: leftPosition,
        };
      }
    }

    // Add event listeners with capture for better handling
    document.addEventListener('click', handleGlobalClick, true);
    document.addEventListener('keydown', handleEscapeKey);
  } else {
    closeMenu();
  }
};

// Cleanup on unmount
onUnmounted(() => {
  closeMenu();
});
</script>

<template>
  <div class="relative" data-menu-container>
    <button
      ref="buttonRef"
      @click="toggleMenu"
      class="p-1 rounded hover:bg-stroke-subtle dark:hover:bg-white/opacity-light transition-colors text-content-secondary dark:text-content-muted hover:text-content-primary dark:hover:text-content-primary/opacity-heavy"
      :class="{
        'bg-background-mute dark:bg-stroke/opacity-subtle text-content-primary/opacity-heavy':
          showMenu,
      }"
      data-menu-container
    >
      <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path
          stroke-linecap="round"
          stroke-linejoin="round"
          stroke-width="2"
          d="M12 5v.01M12 12v.01M12 19v.01M12 6a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2zm0 7a1 1 0 110-2 1 1 0 010 2z"
        />
      </svg>
    </button>

    <!-- Use Teleport to render menu in body without manual DOM manipulation -->
    <Teleport to="body">
      <div
        v-if="showMenu"
        ref="menuRef"
        class="fixed w-44 bg-white dark:bg-surface-elevated backdrop-blur-lg border border-stroke-subtle dark:border-white/opacity-medium rounded-[15px] shadow-2xl z-[450]"
        :style="{ top: menuPosition.top + 'px', left: menuPosition.left + 'px' }"
        data-menu-container
      >
        <div class="py-2">
          <button
            @click="handleShowDetails"
            class="flex items-center gap-3 w-full px-4 py-3 text-left text-sm text-content-primary hover:bg-primary/opacity-light transition-colors border-b border-stroke-subtle dark:border-white/opacity-light"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
            <span class="font-medium">Details</span>
          </button>

          <button
            @click="handlePing"
            class="flex items-center gap-3 w-full px-4 py-3 text-left text-sm text-content-primary hover:bg-primary/opacity-light transition-colors border-b border-stroke-subtle dark:border-white/opacity-light"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M8.111 16.404a5.5 5.5 0 017.778 0M12 20h.01m-7.08-7.071c3.904-3.905 10.236-3.905 14.141 0M1.394 9.393c5.857-5.857 15.355-5.857 21.213 0"
              />
            </svg>
            <span class="font-medium">Ping</span>
          </button>

          <button
            v-if="canQueryScopes"
            @click="handleQueryScopes"
            class="flex items-center gap-3 w-full px-4 py-3 text-left text-sm text-content-primary hover:bg-primary/opacity-light transition-colors border-b border-stroke-subtle dark:border-white/opacity-light"
          >
            <!-- Inline rather than the lucide component: that one carries
                 width/height="24" attributes of its own, which pushed this row's
                 label out of line with the others. Same tag glyph, same markup
                 shape as every sibling item here. -->
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M12.586 2.586A2 2 0 0011.172 2H4a2 2 0 00-2 2v7.172a2 2 0 00.586 1.414l8.704 8.704a2.426 2.426 0 003.42 0l6.58-6.58a2.426 2.426 0 000-3.42z"
              />
              <circle cx="7.5" cy="7.5" r="1.25" fill="currentColor" stroke="none" />
            </svg>
            <span class="font-medium">Query Scopes</span>
          </button>

          <button
            @click="handleDelete"
            class="flex items-center gap-3 w-full px-4 py-3 text-left text-sm text-accent-red hover:bg-accent-red/opacity-light transition-colors"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="2"
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
            <span class="font-medium">Delete</span>
          </button>
        </div>
      </div>
    </Teleport>
  </div>
</template>
