import { createRouter, createWebHistory } from "vue-router";

import AppLayout from "../components/layout/AppLayout.vue";
import AdoptionView from "../views/AdoptionView.vue";
import AlertsView from "../views/AlertsView.vue";
import AlertPoliciesView from "../views/AlertPoliciesView.vue";
import AuditView from "../views/AuditView.vue";
import AuthView from "../views/AuthView.vue";
import CommandsView from "../views/CommandsView.vue";
import DashboardView from "../views/DashboardView.vue";
import GlobalStatsView from "../views/GlobalStatsView.vue";
import InsightsTopologyView from "../views/InsightsTopologyView.vue";
import MapView from "../views/MapView.vue";
import RepeaterDetailView from "../views/RepeaterDetailView.vue";
import RepeatersView from "../views/RepeatersView.vue";
import SettingsView from "../views/SettingsView.vue";
import TransportKeysView from "../views/TransportKeysView.vue";
import UsersView from "../views/UsersView.vue";
import { appState, initializeAppState, isAuthenticated } from "../state/appState";

const routes = [
  {
    path: "/login",
    name: "login",
    component: AuthView,
  },
  {
    path: "/",
    component: AppLayout,
    meta: { requiresAuth: true },
    children: [
      { path: "", redirect: "/dashboard" },
      { path: "dashboard", name: "dashboard", component: DashboardView },
      { path: "alerts", name: "alerts", component: AlertsView },
      { path: "alert-policies", redirect: "/alert-policies/groups" },
      { path: "alert-policies/groups", name: "alert-policies-groups", component: AlertPoliciesView },
      { path: "alert-policies/templates", name: "alert-policies-templates", component: AlertPoliciesView },
      { path: "alert-policies/assignments", name: "alert-policies-assignments", component: AlertPoliciesView },
      { path: "alert-policies/actions", name: "alert-policies-actions", component: AlertPoliciesView },
      { path: "alert-policies/evaluation", name: "alert-policies-evaluation", component: AlertPoliciesView },
      { path: "global-stats", name: "global-stats", component: GlobalStatsView },
      { path: "insights-topology", name: "insights-topology", component: InsightsTopologyView },
      { path: "repeaters", name: "repeaters", component: RepeatersView },
      { path: "repeaters/:repeaterId", name: "repeater-detail", component: RepeaterDetailView },
      { path: "adoption", name: "adoption", component: AdoptionView },
      { path: "commands", name: "commands", component: CommandsView },
      { path: "transport-keys", name: "transport-keys", component: TransportKeysView },
      { path: "settings", name: "settings", component: SettingsView },
      { path: "audit", name: "audit", component: AuditView },
      { path: "map", name: "map", component: MapView },
      {
        path: "users",
        name: "users",
        component: UsersView,
        meta: { requiresAuth: true, roles: ["admin"] },
      },
    ],
  },
  {
    path: "/:pathMatch(.*)*",
    redirect: "/dashboard",
  },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach(async (to) => {
  if (!appState.initialized) {
    await initializeAppState();
  }

  if (to.meta.requiresAuth && !isAuthenticated.value) {
    return { name: "login" };
  }

  const routeRoles = to.meta.roles;
  if (Array.isArray(routeRoles)) {
    const role = appState.user?.role;
    if (!role || !routeRoles.includes(role)) {
      return { name: "dashboard" };
    }
  }

  if (to.name === "login" && isAuthenticated.value) {
    return { name: "dashboard" };
  }

  return true;
});
