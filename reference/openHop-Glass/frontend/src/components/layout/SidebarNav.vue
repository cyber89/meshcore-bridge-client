<template>
  <nav
    class="sidebar-shell"
    :class="{
      expanded: showLabels,
      collapsed: !showLabels,
      mobile,
    }"
    aria-label="Primary navigation"
  >
    <header class="sidebar-header">
      <router-link class="brand-link" to="/dashboard" @click="emitNavigate">
        <div class="brand-glyph">
          <img class="brand-logo" :src="logoImage" alt="pyMC_Glass logo" />
        </div>
      </router-link>
      <div v-if="!mobile" class="sidebar-toggle-row">
        <button
          class="nav-action-btn"
          type="button"
          :aria-label="showLabels ? 'Collapse sidebar' : 'Expand sidebar'"
          :aria-expanded="showLabels"
          @click="toggleSidebar()"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path d="M15 18l-6-6 6-6" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" />
          </svg>
        </button>
      </div>
    </header>

    <ul class="nav-list">
      <li v-for="item in visibleItems" :key="item.id" class="nav-node">
        <button
          v-if="item.children?.length"
          class="nav-item parent-item"
          type="button"
          :class="{
            'is-active': isItemActive(item),
            'is-open': showLabels && isParentOpen(item.id),
          }"
          :aria-expanded="showLabels ? isParentOpen(item.id) : false"
          :aria-controls="`submenu-${item.id}`"
          @click="handleParentPress(item.id)"
        >
          <span class="icon-box">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                v-for="(path, idx) in iconPathMap[item.icon]"
                :key="`${item.id}-${idx}`"
                :d="path"
                fill="none"
                stroke="currentColor"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1.85"
              />
            </svg>
          </span>
          <span class="item-label">{{ item.label }}</span>
          <span class="item-chevron" aria-hidden="true">
            <svg viewBox="0 0 24 24">
              <path d="M8 10l4 4 4-4" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" />
            </svg>
          </span>
          <span v-if="!showLabels" class="item-tooltip">{{ item.label }}</span>
        </button>

        <router-link
          v-else-if="item.to"
          class="nav-item"
          :class="{ 'is-active': isRouteActive(item.to) }"
          :to="item.to"
          @click="emitNavigate"
        >
          <span class="icon-box">
            <svg viewBox="0 0 24 24" aria-hidden="true">
              <path
                v-for="(path, idx) in iconPathMap[item.icon]"
                :key="`${item.id}-${idx}`"
                :d="path"
                fill="none"
                stroke="currentColor"
                stroke-linecap="round"
                stroke-linejoin="round"
                stroke-width="1.85"
              />
            </svg>
          </span>
          <span class="item-label">{{ item.label }}</span>
          <span v-if="!showLabels" class="item-tooltip">{{ item.label }}</span>
        </router-link>

        <transition name="submenu-reveal">
          <ul
            v-if="showLabels && item.children?.length && isParentOpen(item.id)"
            :id="`submenu-${item.id}`"
            class="submenu-tree"
          >
            <li v-for="child in item.children" :key="child.id" class="submenu-node">
              <router-link
                v-if="child.to"
                class="submenu-item"
                :class="{ 'is-active': isRouteActive(child.to) }"
                :to="child.to"
                @click="emitNavigate"
              >
                <span class="submenu-icon">
                  <svg viewBox="0 0 24 24" aria-hidden="true">
                    <path
                      v-for="(path, idx) in iconPathMap[child.icon]"
                      :key="`${child.id}-${idx}`"
                      :d="path"
                      fill="none"
                      stroke="currentColor"
                      stroke-linecap="round"
                      stroke-linejoin="round"
                      stroke-width="1.75"
                    />
                  </svg>
                </span>
                <span>{{ child.label }}</span>
              </router-link>
            </li>
          </ul>
        </transition>
      </li>
    </ul>

    <footer class="sidebar-footer">
      <p class="footer-text">Mesh fleet orchestration</p>
    </footer>
  </nav>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute } from "vue-router";
import { appState } from "../../state/appState";
import logoImage from "../../logo.png";

type NavIconName =
  | "dashboard"
  | "alerts"
  | "policy"
  | "fleet"
  | "repeaters"
  | "adoption"
  | "commands"
  | "map"
  | "stats"
  | "transport"
  | "settings"
  | "audit"
  | "users";

type NavItem = {
  id: string;
  label: string;
  icon: NavIconName;
  to?: string;
  roles?: string[];
  children?: NavItem[];
};

const props = withDefaults(
  defineProps<{
    mobile?: boolean;
  }>(),
  {
    mobile: false,
  },
);

const emit = defineEmits<{ (e: "navigate"): void }>();
const route = useRoute();

const SIDEBAR_EXPANDED_STORAGE_KEY = "pymc_glass_sidebar_expanded";
const autoCollapseWidth = 1600;

const desktopExpanded = ref(false);
const openParents = ref<Record<string, boolean>>({});
const mobile = computed(() => props.mobile);

const navItems: NavItem[] = [
  {
    id: "dashboard",
    label: "Dashboard",
    to: "/dashboard",
    icon: "dashboard",
  },
  {
    id: "alerts",
    label: "Alerts",
    icon: "alerts",
    children: [
      { id: "alerts-center", label: "Alert Center", to: "/alerts", icon: "alerts" },
      { id: "alerts-policies-groups", label: "Node Groups", to: "/alert-policies/groups", icon: "policy" },
      { id: "alerts-policies-templates", label: "Policy Templates", to: "/alert-policies/templates", icon: "policy" },
      {
        id: "alerts-policies-assignments",
        label: "Scope Assignments",
        to: "/alert-policies/assignments",
        icon: "policy",
      },
      { id: "alerts-policies-actions", label: "Actions", to: "/alert-policies/actions", icon: "policy" },
      {
        id: "alerts-policies-evaluation",
        label: "Effective + Evaluation",
        to: "/alert-policies/evaluation",
        icon: "policy",
      },
    ],
  },
  {
    id: "fleet",
    label: "Fleet",
    icon: "fleet",
    children: [
      { id: "fleet-repeaters", label: "Repeaters", to: "/repeaters", icon: "repeaters" },
      { id: "fleet-adoption", label: "Adoption", to: "/adoption", icon: "adoption" },
      { id: "fleet-commands", label: "Commands", to: "/commands", icon: "commands" },
      { id: "fleet-map", label: "Map", to: "/map", icon: "map" },
    ],
  },
  {
    id: "transport-keys",
    label: "Transport Keys",
    to: "/transport-keys",
    icon: "transport",
  },
  {
    id: "insights",
    label: "Insights",
    icon: "stats",
    children: [
      { id: "insights-global-stats", label: "Global Stats", to: "/global-stats", icon: "stats" },
      { id: "insights-topology", label: "Topology", to: "/insights-topology", icon: "map" },
    ],
  },
  {
    id: "admin",
    label: "Administration",
    icon: "settings",
    children: [
      { id: "admin-settings", label: "Settings", to: "/settings", icon: "settings" },
      { id: "admin-audit", label: "Audit", to: "/audit", icon: "audit" },
      { id: "admin-users", label: "Users & RBAC", to: "/users", icon: "users", roles: ["admin"] },
    ],
  },
];

const iconPathMap: Record<NavIconName, string[]> = {
  dashboard: ["M3 3h8v8H3z", "M13 3h8v5h-8z", "M13 10h8v11h-8z", "M3 13h8v8H3z"],
  alerts: ["M18 8a6 6 0 10-12 0c0 7-3 9-3 9h18s-3-2-3-9", "M13.73 21a2 2 0 01-3.46 0"],
  policy: ["M12 2l9 5-9 5-9-5 9-5", "M3 12l9 5 9-5", "M3 17l9 5 9-5"],
  fleet: ["M4 5h16v4H4z", "M4 11h16v4H4z", "M4 17h16v4H4z", "M7 7h.01", "M7 13h.01", "M7 19h.01"],
  repeaters: ["M3 6h18", "M7 12h10", "M10 18h4", "M5 3h14v18H5z"],
  adoption: ["M20 6L9 17l-5-5"],
  commands: ["M4 8l4 4-4 4", "M12 16h8"],
  map: ["M3 6l6-3 6 3 6-3v15l-6 3-6-3-6 3z", "M9 3v15", "M15 6v15"],
  stats: ["M4 19V5", "M10 19V9", "M16 19v-6", "M22 19V3"],
  transport: [
    "M20 7.5a4.5 4.5 0 10-7.38 3.45L5 18.57V22h3.43l1.42-1.43h2.86v-2.85l1.43-1.43",
    "M17 7.5h.01",
  ],
  settings: [
    "M12 8a4 4 0 100 8 4 4 0 000-8z",
    "M12 2v2",
    "M12 20v2",
    "M4.93 4.93l1.41 1.41",
    "M17.66 17.66l1.41 1.41",
    "M2 12h2",
    "M20 12h2",
    "M4.93 19.07l1.41-1.41",
    "M17.66 6.34l1.41-1.41",
  ],
  audit: ["M9 3h6v3H9z", "M5 6h14v15H5z", "M9 11h6", "M9 15h6"],
  users: [
    "M16 21v-2a4 4 0 00-4-4H5a4 4 0 00-4 4v2",
    "M8.5 11a4 4 0 100-8 4 4 0 000 8z",
    "M23 21v-2a4 4 0 00-3-3.87",
    "M16 3.13a4 4 0 010 7.75",
  ],
};

const showLabels = computed(() => props.mobile || desktopExpanded.value);

const visibleItems = computed(() => filterItemsByRole(navItems));

watch(
  () => props.mobile,
  (isMobile) => {
    if (isMobile) {
      desktopExpanded.value = true;
    }
  },
  { immediate: true },
);

watch(
  () => route.path,
  () => {
    ensureActiveParentsExpanded();
  },
  { immediate: true },
);

watch(visibleItems, () => ensureActiveParentsExpanded());

onMounted(() => {
  if (props.mobile) {
    return;
  }
  const storedValue = localStorage.getItem(SIDEBAR_EXPANDED_STORAGE_KEY);
  desktopExpanded.value = storedValue === "true";
  autoCollapseForViewport();
  window.addEventListener("resize", autoCollapseForViewport);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", autoCollapseForViewport);
});

function autoCollapseForViewport(): void {
  if (props.mobile) {
    return;
  }
  if (window.innerWidth < autoCollapseWidth) {
    setDesktopExpanded(false);
  }
}

function setDesktopExpanded(value: boolean): void {
  desktopExpanded.value = value;
  localStorage.setItem(SIDEBAR_EXPANDED_STORAGE_KEY, value ? "true" : "false");
}

function toggleSidebar(): void {
  if (props.mobile) {
    return;
  }
  setDesktopExpanded(!desktopExpanded.value);
}

function emitNavigate(): void {
  emit("navigate");
}

function handleParentPress(parentId: string): void {
  if (!showLabels.value && !props.mobile) {
    setDesktopExpanded(true);
    openParents.value[parentId] = true;
    return;
  }
  openParents.value[parentId] = !openParents.value[parentId];
}

function isParentOpen(parentId: string): boolean {
  return openParents.value[parentId] === true;
}

function isRouteActive(path: string): boolean {
  if (route.path === path) {
    return true;
  }
  return route.path.startsWith(`${path}/`);
}

function isItemActive(item: NavItem): boolean {
  if (item.to && isRouteActive(item.to)) {
    return true;
  }
  if (item.children?.length) {
    return item.children.some((child) => isItemActive(child));
  }
  return false;
}

function ensureActiveParentsExpanded(): void {
  for (const item of visibleItems.value) {
    if (!item.children?.length) {
      continue;
    }
    if (item.children.some((child) => isItemActive(child))) {
      openParents.value[item.id] = true;
    }
  }
}

function filterItemsByRole(items: NavItem[]): NavItem[] {
  const role = appState.user?.role;
  return items
    .map((item) => {
      if (item.roles && (!role || !item.roles.includes(role))) {
        return null;
      }
      const children = item.children ? filterItemsByRole(item.children) : undefined;
      if (!item.to && (!children || children.length === 0)) {
        return null;
      }
      return {
        ...item,
        children,
      };
    })
    .filter((item): item is NavItem => item !== null);
}
</script>

<style scoped>
.sidebar-shell {
  --sidebar-collapsed-width: 88px;
  --sidebar-expanded-width: 260px;
  --submenu-line-color: rgba(130, 153, 190, 0.32);
  --submenu-line-color-soft: rgba(130, 153, 190, 0.22);
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 0.8rem;
  height: 100%;
  width: var(--sidebar-collapsed-width);
  padding: 0.7rem;
  transition: width 260ms ease;
}

.sidebar-shell.expanded {
  width: var(--sidebar-expanded-width);
}

.sidebar-shell.mobile {
  width: 100%;
}

.sidebar-header {
  display: grid;
  justify-items: center;
  gap: 0.55rem;
  border-bottom: 1px solid var(--color-border-subtle);
  padding: 0.2rem 0 0.75rem;
}

.brand-link {
  position: relative;
  display: inline-flex;
  justify-content: center;
  align-items: center;
  min-width: 0;
  border-radius: 0.8rem;
  padding: 0;
}

.brand-link:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(94, 188, 200, 0.55);
}

.brand-glyph {
  position: relative;
  display: grid;
  place-items: center;
  width: 101px;
  height: 101px;
  border-radius: 0.8rem;
  background: transparent;
  overflow: hidden;
  flex: 0 0 auto;
  transform: translateZ(0);
}
.sidebar-toggle-row {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}

.collapsed .sidebar-header {
  gap: 0.45rem;
}

.collapsed .brand-glyph {
  width: 52px;
  height: 52px;
}

.brand-logo {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
  border-radius: inherit;
  transform: translateZ(0);
  backface-visibility: hidden;
  -webkit-backface-visibility: hidden;
}

.nav-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 0.65rem;
  border: 1px solid var(--color-border-subtle);
  background: rgba(255, 255, 255, 0.03);
  color: var(--color-text-secondary);
  transition: background 220ms ease, transform 220ms ease, border-color 220ms ease;
  flex: 0 0 auto;
}

.expanded .nav-action-btn svg {
  transform: rotate(180deg);
}

.nav-action-btn svg {
  width: 15px;
  height: 15px;
  transition: transform 220ms ease;
}

.nav-action-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  border-color: rgba(114, 145, 180, 0.55);
}

.nav-action-btn:focus-visible {
  outline: none;
  box-shadow: 0 0 0 2px rgba(94, 188, 200, 0.55);
}

.nav-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  align-content: start;
  gap: 0.3rem;
  overflow-y: auto;
  min-height: 0;
}

.nav-node {
  display: grid;
  gap: 0.2rem;
}

.nav-item {
  position: relative;
  display: flex;
  align-items: center;
  gap: 0.62rem;
  width: 100%;
  border: 1px solid transparent;
  border-radius: 0.82rem;
  background: transparent;
  color: var(--color-text-secondary);
  text-align: left;
  padding: 0.5rem 0.56rem;
  overflow: hidden;
  transition: background 220ms ease, border-color 220ms ease, color 220ms ease;
}

.collapsed .nav-item {
  justify-content: center;
  padding-inline: 0.4rem;
}

.icon-box {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 0.65rem;
  color: #cdd6e7;
  background: rgba(255, 255, 255, 0.025);
  border: 1px solid rgba(255, 255, 255, 0.06);
  transition: opacity 220ms ease, transform 220ms ease, background 220ms ease, border-color 220ms ease;
  flex: 0 0 auto;
}

.icon-box svg {
  width: 16px;
  height: 16px;
}

.item-label {
  font-size: 0.82rem;
  font-weight: 550;
  color: #dce6f7;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  transition: opacity 220ms ease, transform 220ms ease, max-width 220ms ease;
}

.collapsed .item-label {
  display: none;
}

.collapsed .item-chevron {
  display: none;
}

.item-tooltip {
  position: absolute;
  left: calc(100% + 10px);
  top: 50%;
  transform: translateY(-50%);
  background: rgba(9, 16, 30, 0.96);
  border: 1px solid rgba(118, 147, 177, 0.4);
  border-radius: 0.58rem;
  color: #e7eefc;
  font-size: 0.74rem;
  line-height: 1;
  padding: 0.4rem 0.52rem;
  opacity: 0;
  pointer-events: none;
  transition: opacity 180ms ease;
  z-index: 20;
  white-space: nowrap;
}

.collapsed .nav-item:hover .item-tooltip,
.collapsed .nav-item:focus-visible .item-tooltip {
  opacity: 1;
}

.item-chevron {
  margin-left: auto;
  width: 16px;
  height: 16px;
  color: #a9bdd8;
  transition: transform 220ms ease, opacity 220ms ease;
}

.item-chevron svg {
  width: 16px;
  height: 16px;
}

.parent-item.is-open .item-chevron {
  transform: rotate(180deg);
}

.parent-item.is-open .icon-box {
  opacity: 0.62;
  transform: scale(0.92);
}

.nav-item:hover {
  background: rgba(29, 44, 67, 0.36);
  border-color: rgba(93, 132, 171, 0.32);
}

.nav-item:focus-visible {
  outline: none;
  border-color: rgba(96, 216, 203, 0.55);
  box-shadow: 0 0 0 2px rgba(96, 216, 203, 0.28);
}

.nav-item.is-active {
  color: #e5f5f4;
  background: linear-gradient(90deg, rgba(24, 79, 88, 0.5), rgba(24, 49, 79, 0.45));
  border-color: rgba(96, 216, 203, 0.45);
  box-shadow: inset 2px 0 0 rgba(106, 234, 219, 0.72);
}

.nav-item.is-active .icon-box {
  color: #e0f7f4;
  border-color: rgba(113, 219, 207, 0.45);
  background: rgba(84, 178, 177, 0.17);
}

.submenu-tree {
  position: relative;
  list-style: none;
  margin: 0;
  margin-left: 0.68rem;
  padding: 0.1rem 0 0.2rem 0.95rem;
  display: grid;
  gap: 0.2rem;
}

.submenu-tree::before {
  content: "";
  position: absolute;
  left: 0.38rem;
  top: 0.28rem;
  bottom: 0.35rem;
  width: 1px;
  background: linear-gradient(180deg, var(--submenu-line-color), var(--submenu-line-color-soft));
}

.submenu-node {
  position: relative;
}

.submenu-node::before {
  content: "";
  position: absolute;
  top: 50%;
  left: -0.58rem;
  width: 0.56rem;
  border-top: 1px solid var(--submenu-line-color);
}

.submenu-item {
  display: flex;
  align-items: center;
  gap: 0.45rem;
  border: 1px solid transparent;
  border-radius: 0.62rem;
  color: #bdc9dc;
  padding: 0.39rem 0.45rem;
  font-size: 0.77rem;
  transition: background 220ms ease, border-color 220ms ease, color 220ms ease;
}

.submenu-item:hover {
  background: rgba(32, 46, 70, 0.34);
  border-color: rgba(93, 132, 171, 0.28);
}

.submenu-item:focus-visible {
  outline: none;
  border-color: rgba(96, 216, 203, 0.52);
  box-shadow: 0 0 0 2px rgba(96, 216, 203, 0.24);
}

.submenu-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  opacity: 0.72;
  flex: 0 0 auto;
}

.submenu-icon svg {
  width: 13px;
  height: 13px;
}

.submenu-item.is-active {
  color: #e2f8f5;
  background: rgba(40, 97, 99, 0.28);
  border-color: rgba(96, 216, 203, 0.42);
}

.submenu-item.is-active .submenu-icon {
  opacity: 1;
}

.sidebar-footer {
  border-top: 1px solid var(--color-border-subtle);
  padding-top: 0.55rem;
}

.footer-text {
  color: var(--color-text-muted);
  font-size: 0.72rem;
  margin: 0;
  transition: opacity 220ms ease;
}

.collapsed .footer-text {
  opacity: 0;
}

.submenu-reveal-enter-active,
.submenu-reveal-leave-active {
  transition: opacity 220ms ease, transform 220ms ease;
  transform-origin: top;
}

.submenu-reveal-enter-from,
.submenu-reveal-leave-to {
  opacity: 0;
  transform: translateY(-5px) scaleY(0.97);
}
</style>
