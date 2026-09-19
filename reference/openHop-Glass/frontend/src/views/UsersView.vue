<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Users & RBAC</h1>
        <p class="section-subtitle">Manage users, activation state, and role assignments.</p>
      </div>
      <div class="users-actions">
        <button class="btn btn-secondary" :disabled="appState.dataLoading" @click="refreshUsersList()">
          {{ appState.dataLoading ? "Refreshing..." : "Refresh users" }}
        </button>
        <button class="btn btn-primary" :disabled="appState.actionLoading || !isAdmin" @click="openCreateUserModal()">
          New user
        </button>
        <button
          class="btn btn-primary"
          :disabled="appState.actionLoading || !selectedUser || !isAdmin"
          @click="openEditUserModal()"
        >
          Edit selected
        </button>
      </div>
    </header>

    <article class="glass-card panel">
      <h2>User Directory</h2>
      <p class="section-subtitle">
        Roles: <code>admin</code> (full), <code>operator</code> (write ops), <code>viewer</code> (read-only).
      </p>
      <UiDataTable>
        <thead>
          <tr>
            <th>Email</th>
            <th>Role</th>
            <th>Status</th>
            <th>Display</th>
            <th>Created</th>
            <th>Updated</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="user in appState.users"
            :key="user.id"
            class="row-click"
            :class="{ selected: selectedUserId === user.id }"
            @click="selectUser(user.id)"
          >
            <td><strong>{{ user.email }}</strong></td>
            <td>
              <span class="pill" :class="rolePillClass(user.role)">{{ user.role }}</span>
            </td>
            <td>
              <span class="pill" :class="user.is_active ? 'pill-green' : 'pill-red'">
                {{ user.is_active ? "active" : "disabled" }}
              </span>
            </td>
            <td>{{ user.display_name || "—" }}</td>
            <td>{{ formatTimestamp(user.created_at) }}</td>
            <td>{{ formatTimestamp(user.updated_at) }}</td>
          </tr>
          <tr v-if="appState.users.length === 0">
            <td colspan="6" class="section-subtitle">No users found.</td>
          </tr>
        </tbody>
      </UiDataTable>
    </article>
  </section>

  <teleport to="body">
    <div v-if="showCreateUserModal" class="modal-backdrop" @click.self="closeCreateUserModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>Create User</h3>
            <p class="section-subtitle">Create a user account and set initial role and status.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeCreateUserModal()">Close</button>
        </header>

        <form class="panel-form" @submit.prevent="submitCreateUserModal()">
          <label class="field-label">
            Email
            <input v-model.trim="createForm.email" type="email" class="field" required />
          </label>
          <label class="field-label">
            Password
            <input v-model="createForm.password" type="password" class="field" minlength="10" required />
          </label>
          <label class="field-label">
            Display name
            <input v-model.trim="createForm.display_name" class="field" />
          </label>
          <label class="field-label">
            Role
            <select v-model="createForm.role" class="field-select">
              <option value="admin">admin</option>
              <option value="operator">operator</option>
              <option value="viewer">viewer</option>
            </select>
          </label>
          <label class="toggle-row">
            <input v-model="createForm.is_active" type="checkbox" />
            <span>Active</span>
          </label>
          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeCreateUserModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="appState.actionLoading || !isAdmin">
              {{ appState.actionLoading ? "Creating..." : "Create user" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showEditUserModal" class="modal-backdrop" @click.self="closeEditUserModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>Edit User</h3>
            <p class="section-subtitle">Update role, display name, status, or reset password.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeEditUserModal()">Close</button>
        </header>

        <form class="panel-form" @submit.prevent="submitEditUserModal()">
          <label class="field-label">
            Selected user
            <input :value="selectedUser?.email || ''" class="field" disabled />
          </label>
          <label class="field-label">
            Display name
            <input v-model.trim="editForm.display_name" class="field" />
          </label>
          <label class="field-label">
            Role
            <select v-model="editForm.role" class="field-select">
              <option value="admin">admin</option>
              <option value="operator">operator</option>
              <option value="viewer">viewer</option>
            </select>
          </label>
          <label class="toggle-row">
            <input v-model="editForm.is_active" type="checkbox" />
            <span>Active</span>
          </label>
          <label class="field-label">
            Reset password (optional)
            <input
              v-model="editForm.password"
              type="password"
              class="field"
              minlength="10"
              placeholder="Leave blank to keep current"
            />
          </label>
          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeEditUserModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="appState.actionLoading || !selectedUser || !isAdmin">
              {{ appState.actionLoading ? "Saving..." : "Save user changes" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import UiDataTable from "../components/ui/UiDataTable.vue";

import {
  appState,
  createUserAccount,
  formatTimestamp,
  isAdmin,
  refreshUsersList,
  updateUserAccount,
} from "../state/appState";

const createForm = reactive({
  email: "",
  password: "",
  display_name: "",
  role: "operator",
  is_active: true,
});

const selectedUserId = ref<string | null>(null);
const showCreateUserModal = ref(false);
const showEditUserModal = ref(false);
const editForm = reactive({
  role: "viewer",
  display_name: "",
  is_active: true,
  password: "",
});

const selectedUser = computed(() =>
  appState.users.find((user) => user.id === selectedUserId.value),
);

watch(
  selectedUser,
  (user) => {
    if (!user) {
      editForm.role = "viewer";
      editForm.display_name = "";
      editForm.is_active = true;
      editForm.password = "";
      return;
    }
    editForm.role = user.role;
    editForm.display_name = user.display_name || "";
    editForm.is_active = user.is_active;
    editForm.password = "";
  },
  { immediate: true },
);

onMounted(async () => {
  await refreshUsersList();
});

function selectUser(userId: string): void {
  selectedUserId.value = userId;
}
function resetCreateForm(): void {
  createForm.email = "";
  createForm.password = "";
  createForm.display_name = "";
  createForm.role = "operator";
  createForm.is_active = true;
}

function openCreateUserModal(): void {
  resetCreateForm();
  showCreateUserModal.value = true;
}

function closeCreateUserModal(): void {
  showCreateUserModal.value = false;
}

function openEditUserModal(): void {
  if (!selectedUser.value) {
    return;
  }
  showEditUserModal.value = true;
}

function closeEditUserModal(): void {
  showEditUserModal.value = false;
}

async function createUserEntry(): Promise<boolean> {
  appState.toastError = null;
  appState.toastSuccess = null;
  await createUserAccount({
    email: createForm.email,
    password: createForm.password,
    role: createForm.role,
    display_name: createForm.display_name || undefined,
    is_active: createForm.is_active,
  });
  if (appState.toastError) {
    return false;
  }
  resetCreateForm();
  return true;
}

async function saveUserEdits(): Promise<boolean> {
  if (!selectedUserId.value) {
    return false;
  }
  appState.toastError = null;
  appState.toastSuccess = null;
  await updateUserAccount(selectedUserId.value, {
    role: editForm.role,
    display_name: editForm.display_name || null,
    is_active: editForm.is_active,
    password: editForm.password || undefined,
  });
  if (appState.toastError) {
    return false;
  }
  editForm.password = "";
  return true;
}

async function submitCreateUserModal(): Promise<void> {
  const created = await createUserEntry();
  if (created) {
    closeCreateUserModal();
  }
}

async function submitEditUserModal(): Promise<void> {
  const saved = await saveUserEdits();
  if (saved) {
    closeEditUserModal();
  }
}

function rolePillClass(role: string): string {
  if (role === "admin") {
    return "pill-red";
  }
  if (role === "operator") {
    return "pill-amber";
  }
  return "pill-gray";
}
</script>

<style scoped>
.users-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1200;
  display: grid;
  place-items: center;
  padding: 1.2rem;
  background: rgba(5, 9, 18, 0.64);
  backdrop-filter: blur(5px);
}

.modal-card {
  width: min(100%, 620px);
  display: grid;
  gap: 1rem;
  padding: 1rem;
  border-radius: 1rem;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 1rem;
}

.modal-actions {
  display: flex;
  justify-content: end;
  gap: 0.6rem;
}
</style>
