<script setup lang="ts">
import { computed, ref, watch, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { NavItemConfig } from '@/config/navigation'
import { NAV_ACTION_HANDLERS_KEY } from '@/config/navActionHandlers'
import { useSidebarPin } from '@/composables/useSidebarPin'
import { ChevronDown } from '@lucide/vue'

defineOptions({ name: 'NavItem' })

const props = defineProps<{
  item: NavItemConfig
  depth?: number
  precedesActive?: boolean
  searchActive?: boolean
}>()

const route = useRoute()
const router = useRouter()

const depth = computed(() => props.depth ?? 0)

const actionHandlers = inject<Record<string, () => void>>(NAV_ACTION_HANDLERS_KEY, {})

// ── Active state ──────────────────────────────────────────────────────────────

function matchesActive(cfg: NavItemConfig, currentPath: string, currentQuery: Record<string, string>): boolean {
  const targets = cfg.activeOn ?? (cfg.route ? [cfg.route] : [])
  if (targets.length === 0) return false
  if (!targets.some((t) => currentPath === t || currentPath.startsWith(t + '/'))) return false
  if (cfg.params && !cfg.children) {
    return Object.entries(cfg.params).every(([k, v]) => currentQuery[k] === v)
  }
  return true
}

function anyChildActive(items: NavItemConfig[], currentPath: string, currentQuery: Record<string, string>): boolean {
  return items.some((child) =>
    child.children
      ? anyChildActive(child.children, currentPath, currentQuery)
      : matchesActive(child, currentPath, currentQuery),
  )
}

const isActive = computed(() => {
  if (props.item.children) return false
  return matchesActive(props.item, route.path, route.query as Record<string, string>)
})

const hasActiveDescendant = computed(() =>
  !!props.item.children && anyChildActive(props.item.children, route.path, route.query as Record<string, string>),
)

// Index of the first child that is active or contains the active item.
// Children before this index receive the 'precedesActive' prop.
const activeChildIndex = computed(() => {
  if (!props.item.children) return -1
  return props.item.children.findIndex((child) =>
    child.children
      ? anyChildActive(child.children, route.path, route.query as Record<string, string>)
      : matchesActive(child, route.path, route.query as Record<string, string>),
  )
})

// ── Expand / collapse ─────────────────────────────────────────────────────────

const isGroup = computed(() => !!props.item.children?.length)
const { getRestoredFold, recordFold } = useSidebarPin()

// Initialise from saved pin state when available, otherwise default to closed.
const restored = isGroup.value ? getRestoredFold(props.item.id) : null
const expanded = ref(restored !== null ? restored : false)
const visibleExpanded = computed(() => (props.searchActive && isGroup.value) || expanded.value)

watch(
  hasActiveDescendant,
  (active) => { if (active) expanded.value = true },
  { immediate: true },
)

// Persist fold changes whenever the pin is active.
watch(expanded, (val) => { if (isGroup.value) recordFold(props.item.id, val) })

function toggle() { expanded.value = !expanded.value }

// ── Navigation ────────────────────────────────────────────────────────────────

function navigate() {
  if (!props.item.route) return
  const query = props.item.params ? { ...props.item.params } : undefined
  router.push({ path: props.item.route, query })
}

function handleClick() {
  if (isGroup.value) toggle()
  else if (props.item.action) actionHandlers[props.item.action]?.()
  else navigate()
}

// ── Styles ────────────────────────────────────────────────────────────────────

const isChild = computed(() => depth.value > 0)
const isExpandedGroup = computed(() => isGroup.value && visibleExpanded.value)

const buttonClass = computed(() => {
  const base = `w-full rounded-[10px] py-1.5 flex items-center gap-1.5 text-sm transition-all duration-200`
  const indent = isChild.value ? 'pl-3 pr-2' : 'pl-4 pr-2'
  const groupState = isExpandedGroup.value ? 'bg-surface-elevated border border-stroke-subtle font-semibold' : 'border border-transparent font-medium'

  if (isActive.value) {
    return `${base} ${indent} ${groupState} text-primary`
  }
  return `${base} ${indent} ${groupState} text-content-primary hover:text-primary`
})

const iconClass = computed(() =>
  isActive.value
    ? 'w-3.5 h-3.5 flex-shrink-0 text-primary'
    : 'w-3.5 h-3.5 flex-shrink-0 text-content-muted',
)
</script>

<template>
  <div :class="{
    'nav-item-active':    isActive,
    'nav-has-active':     hasActiveDescendant,
    'nav-precedes-active': props.precedesActive,
    'nav-group-expanded': isExpandedGroup,
  }">
    <button :class="buttonClass" @click="handleClick">
      <component :is="item.icon" v-if="item.icon" :class="iconClass" />
      <span class="nav-label flex-1 text-left">{{ item.label }}</span>
      <ChevronDown
        v-if="isGroup"
        :class="['w-3 h-3 flex-shrink-0 transition-transform duration-200 text-content-muted', visibleExpanded ? 'rotate-180' : '']"
      />
    </button>

    <Transition name="nav-expand">
      <div
        v-if="isGroup && visibleExpanded"
        :class="['nav-children mt-1 space-y-1', depth === 0 ? 'ml-2' : 'ml-3']"
      >
        <NavItem
          v-for="(child, i) in item.children"
          :key="child.id"
          :item="child"
          :depth="depth + 1"
          :precedes-active="activeChildIndex >= 0 && i < activeChildIndex"
          :search-active="searchActive"
        />
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.nav-expand-enter-active,
.nav-expand-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
  transform-origin: top;
}
.nav-expand-enter-from,
.nav-expand-leave-to {
  opacity: 0;
  transform: scaleY(0.95) translateY(-4px);
}

button:hover .nav-label { text-shadow: var(--nav-hover-label-shadow); }
button:hover svg        { filter: var(--nav-hover-icon-shadow); }

.nav-group-expanded > button {
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.03);
}

.nav-children {
  margin-top: 0.35rem;
  padding: 0.35rem 0 0.35rem 0.7rem;
  border-left: 1px solid var(--color-border-subtle);
  border-radius: 0 0.5rem 0.5rem 0;
}

.nav-children > div {
  position: relative;
}
</style>
