<template>
  <section class="page-grid">
    <header class="page-header">
      <div>
        <h1 class="section-title">Alert Policies</h1>
        <p class="section-subtitle">
          Configure alert behavior workflow: groups → templates → assignments → evaluate.
        </p>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" :disabled="loading" @click="loadAll()">
          {{ loading ? "Refreshing..." : "Refresh" }}
        </button>
        <button class="btn btn-ghost" :disabled="!canOperate || loading" @click="bootstrapDefaults()">
          Bootstrap defaults
        </button>
        <button class="btn btn-primary" :disabled="!canOperate || loading" @click="openCreateGroupModal()">
          New group
        </button>
        <button class="btn btn-primary" :disabled="!canOperate || loading" @click="openCreateTemplateModal()">
          New template
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <div class="alert-policy-main">
        <section class="grid-3">
          <UiStatCard
            title="Node groups"
            :value="groups.length"
            subtitle="Use groups to apply policies to multiple repeaters."
          />
          <UiStatCard
            title="Policy templates"
            :value="templates.length"
            subtitle="Reusable thresholds and severities."
          />
          <UiStatCard
            title="Assignments"
            :value="assignments.length"
            subtitle="Scoped links between templates and targets."
          />
        </section>

        <section v-if="activeSubsection === 'groups'" class="grid-1">
      <UiPanelCard title="1. Node Groups" subtitle="Click a group row to manage members in a focused popup.">
        <template #actions>
          <button class="btn btn-secondary btn-sm" :disabled="!canOperate || actionLoading" @click="openCreateGroupModal()">
            Create group
          </button>
        </template>

        <UiDataTable>
          <thead>
            <tr>
              <th>Name</th>
              <th>Members</th>
              <th>Description</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="group in groups"
              :key="group.id"
              class="row-click"
              :class="{ selected: selectedGroupId === group.id }"
              @click="openGroupMembersModal(group.id)"
            >
              <td>
                <div class="group-name-cell">
                  <span>{{ group.name }}</span>
                  <span class="manage-members-chip">Manage members</span>
                </div>
              </td>
              <td>{{ group.member_count }}</td>
              <td>{{ group.description || "—" }}</td>
              <td>
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="actionLoading"
                  @click.stop="openGroupMembersModal(group.id)"
                >
                  Members
                </button>
                <button
                  class="btn btn-danger btn-sm"
                  :disabled="!canOperate || actionLoading"
                  @click.stop="requestDeleteGroup(group.id, group.name)"
                >
                  Delete
                </button>
              </td>
            </tr>
            <tr v-if="groups.length === 0">
              <td colspan="4" class="section-subtitle">
                No node groups created yet. Click “Create group” to begin scoping policies.
              </td>
            </tr>
          </tbody>
        </UiDataTable>
      </UiPanelCard>
    </section>

        <section v-if="activeSubsection === 'templates'" class="grid-1">
      <UiPanelCard title="2. Policy Templates" subtitle="Reusable rules and thresholds used by assignments.">
        <template #actions>
          <button class="btn btn-secondary btn-sm" :disabled="!canOperate || actionLoading" @click="openCreateTemplateModal()">
            Create template
          </button>
        </template>

        <UiDataTable>
          <thead>
            <tr>
              <th>Name</th>
              <th>Rule</th>
              <th>Severity</th>
              <th>Trigger</th>
              <th>Enabled</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="template in templates" :key="template.id">
              <td>{{ template.name }}</td>
              <td>{{ formatRuleTypeLabel(template.rule_type) }}</td>
              <td>
                <span class="severity-pill" :class="severityClass(template.severity)">{{ template.severity }}</span>
              </td>
              <td>{{ formatTemplateThreshold(template) }}</td>
              <td><StatusPill :status="template.enabled ? 'enabled' : 'disabled'" /></td>
              <td>
                <button
                  class="btn btn-danger btn-sm"
                  :disabled="!canOperate || actionLoading"
                  @click="requestDeleteTemplate(template.id, template.name)"
                >
                  Delete
                </button>
              </td>
            </tr>
            <tr v-if="templates.length === 0">
              <td colspan="6" class="section-subtitle">
                No policy templates yet. Create a template to define thresholds and severity.
              </td>
            </tr>
          </tbody>
        </UiDataTable>
      </UiPanelCard>
    </section>

        <section v-if="activeSubsection === 'assignments'" class="grid-1">
      <UiPanelCard title="3. Scope Assignments" subtitle="Attach templates globally, to groups, or to single repeaters.">
        <template #actions>
          <button class="btn btn-secondary btn-sm" :disabled="!canOperate || actionLoading" @click="openCreateAssignmentModal()">
            Create assignment
          </button>
        </template>
        <div class="assignment-filter-row">
          <label class="assignment-filter-label">
            Scope
            <select v-model="assignmentScopeFilter" class="field-select assignment-filter-select">
              <option value="all">All scopes</option>
              <option value="global">Global</option>
              <option value="group">Group</option>
              <option value="node">Node</option>
            </select>
          </label>
          <label class="assignment-filter-label assignment-filter-search">
            Search
            <input
              v-model.trim="assignmentSearch"
              class="field assignment-filter-input"
              placeholder="Template, rule, or scope target"
            />
          </label>
          <button class="btn btn-ghost btn-sm" type="button" @click="resetAssignmentFilters()">
            Clear filters
          </button>
        </div>

        <UiDataTable>
          <thead>
            <tr>
              <th>Template</th>
              <th>Rule</th>
              <th>Scope</th>
              <th>Priority</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="assignment in filteredAssignments" :key="assignment.id">
              <td>{{ assignment.template_name }}</td>
              <td>{{ formatRuleTypeLabel(assignment.rule_type) }}</td>
              <td>
                <div class="scope-cell">
                  <span class="scope-pill" :class="scopePillClass(assignment.scope_type)">{{ scopeTypeLabel(assignment.scope_type) }}</span>
                  <span class="section-subtitle">{{ assignment.scope_name || assignment.scope_id || "Fleet-wide" }}</span>
                </div>
              </td>
              <td>{{ assignment.priority }}</td>
              <td>
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="!canOperate || actionLoading"
                  @click="requestDeleteAssignment(assignment.id, assignment.template_name)"
                >
                  Delete
                </button>
              </td>
            </tr>
            <tr v-if="assignments.length === 0">
              <td colspan="5" class="section-subtitle">
                No assignments configured yet. Click “Create assignment” to target templates by scope.
              </td>
            </tr>
            <tr v-else-if="filteredAssignments.length === 0">
              <td colspan="5" class="section-subtitle">No assignments match the current filters.</td>
            </tr>
          </tbody>
        </UiDataTable>
      </UiPanelCard>
    </section>

        <UiPanelCard
          v-if="activeSubsection === 'evaluation'"
          title="4. Effective Policies + Evaluation"
          subtitle="Inspect the resolved policy set and run evaluation jobs."
        >
      <form class="panel-form" @submit.prevent="inspectEffectivePolicies()">
        <label class="field-label">
          Repeater
          <select v-model="selectedRepeaterId" class="field-select">
            <option value="">Select repeater</option>
            <option v-for="repeater in appState.repeaters" :key="repeater.id" :value="repeater.id">
              {{ repeater.node_name }}
            </option>
          </select>
        </label>
        <div class="header-actions">
          <button class="btn btn-secondary" :disabled="!selectedRepeaterId || loading">Inspect effective</button>
          <button
            class="btn btn-primary"
            type="button"
            :disabled="!canOperate || actionLoading || !selectedRepeaterId"
            @click="runEvaluation(selectedRepeaterId)"
          >
            Evaluate selected
          </button>
          <button
            class="btn btn-ghost"
            type="button"
            :disabled="!canOperate || actionLoading"
            @click="runEvaluation()"
          >
            Evaluate fleet
          </button>
        </div>
      </form>

      <p v-if="evaluationResult" class="section-subtitle">
        Evaluated {{ evaluationResult.evaluated_repeaters }} repeaters · activated
        {{ evaluationResult.alerts_activated }} · resolved {{ evaluationResult.alerts_resolved }}
      </p>

      <UiDataTable>
        <thead>
          <tr>
            <th>Rule</th>
            <th>Template</th>
            <th>Severity</th>
            <th>Source</th>
            <th>Threshold</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="policy in effectivePolicies" :key="`${policy.template_id}-${policy.rule_type}`">
            <td>{{ formatRuleTypeLabel(policy.rule_type) }}</td>
            <td>{{ policy.template_name }}</td>
            <td>
              <span class="severity-pill" :class="severityClass(policy.severity)">{{ policy.severity }}</span>
            </td>
            <td>
              <div class="scope-cell">
                <span class="scope-pill" :class="scopePillClass(policy.source_scope_type)">{{ scopeTypeLabel(policy.source_scope_type) }}</span>
                <span class="section-subtitle">{{ policy.source_scope_name || "Fleet-wide" }}</span>
              </div>
            </td>
            <td>{{ formatEffectiveThreshold(policy) }}</td>
          </tr>
          <tr v-if="effectivePolicies.length === 0">
            <td colspan="5" class="section-subtitle">
              Select a repeater and click “Inspect effective” to view resolved policy templates.
            </td>
          </tr>
        </tbody>
      </UiDataTable>
        </UiPanelCard>

        <section v-if="activeSubsection === 'actions'" class="grid-1">
          <UiPanelCard
            title="5. Actions"
            subtitle="Configure outbound integrations, reusable action templates, and policy-template bindings."
          >
        <div class="actions-toolbar">
          <div class="provider-capabilities">
            <span v-for="provider in actionProviders" :key="provider.provider_type" class="provider-chip">
              <strong>{{ provider.display_name }}</strong>
              <span class="provider-chip-detail">
                {{ provider.supports_send ? "Send ready" : "Scaffold only" }} ·
                {{ provider.supports_templated_payload ? "Templated payloads" : "No templating" }}
              </span>
            </span>
            <span v-if="actionProviders.length === 0" class="section-subtitle">No providers returned by backend.</span>
          </div>
        </div>

        <div class="action-block">
          <div class="action-block-header">
            <div>
              <h3>Integrations</h3>
              <p class="section-subtitle">Provider endpoints and credentials destination for action delivery.</p>
            </div>
            <button class="btn btn-secondary btn-sm" :disabled="!canOperate || actionLoading" @click="openCreateIntegrationModal()">
              New integration
            </button>
          </div>
          <UiDataTable>
            <thead>
              <tr>
                <th>Name</th>
                <th>Provider</th>
                <th>Description</th>
                <th>Status</th>
                <th>Secrets</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="integration in actionIntegrations" :key="integration.id">
                <td>{{ integration.name }}</td>
                <td>{{ providerLabel(integration.provider_type) }}</td>
                <td>{{ integration.description || "—" }}</td>
                <td><StatusPill :status="integration.enabled ? 'enabled' : 'disabled'" /></td>
                <td>{{ integration.has_secrets ? "Stored" : "None" }}</td>
                <td>
                  <button
                    class="btn btn-ghost btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="runIntegrationTestAction(integration)"
                  >
                    Test
                  </button>
                  <button
                    class="btn btn-ghost btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="openEditIntegrationModal(integration)"
                  >
                    Edit
                  </button>
                  <button
                    class="btn btn-danger btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="requestDeleteIntegration(integration.id, integration.name)"
                  >
                    Delete
                  </button>
                </td>
              </tr>
              <tr v-if="actionIntegrations.length === 0">
                <td colspan="6" class="section-subtitle">No integrations yet.</td>
              </tr>
            </tbody>
          </UiDataTable>
        </div>

        <div class="action-block">
          <div class="action-block-header">
            <div>
              <h3>Action Templates</h3>
              <p class="section-subtitle">Reusable title/body/payload templates for alert action events.</p>
            </div>
            <button class="btn btn-secondary btn-sm" :disabled="!canOperate || actionLoading" @click="openCreateActionTemplateModal()">
              New action template
            </button>
          </div>
          <UiDataTable>
            <thead>
              <tr>
                <th>Name</th>
                <th>Provider</th>
                <th>Default events</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="template in actionTemplates" :key="template.id">
                <td>{{ template.name }}</td>
                <td>{{ template.provider_type ? providerLabel(template.provider_type) : "Any provider" }}</td>
                <td>{{ formatActionEvents(template.default_event_types) || "None" }}</td>
                <td><StatusPill :status="template.enabled ? 'enabled' : 'disabled'" /></td>
                <td>
                  <button
                    class="btn btn-ghost btn-sm"
                    :disabled="actionLoading"
                    @click="openActionTemplatePreviewModal(template)"
                  >
                    Preview
                  </button>
                  <button
                    class="btn btn-ghost btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="openEditActionTemplateModal(template)"
                  >
                    Edit
                  </button>
                  <button
                    class="btn btn-danger btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="requestDeleteActionTemplate(template.id, template.name)"
                  >
                    Delete
                  </button>
                </td>
              </tr>
              <tr v-if="actionTemplates.length === 0">
                <td colspan="5" class="section-subtitle">No action templates yet.</td>
              </tr>
            </tbody>
          </UiDataTable>
        </div>

        <div class="action-block">
          <div class="action-block-header">
            <div>
              <h3>Policy Action Bindings</h3>
              <p class="section-subtitle">Bind policy templates to integrations/templates with event and severity routing.</p>
            </div>
            <button class="btn btn-secondary btn-sm" :disabled="!canOperate || actionLoading" @click="openCreateBindingModal()">
              New binding
            </button>
          </div>
          <div class="assignment-filter-row">
            <label class="assignment-filter-label">
              Provider
              <select v-model="bindingProviderFilter" class="field-select assignment-filter-select">
                <option value="all">All providers</option>
                <option v-for="provider in actionProviders" :key="provider.provider_type" :value="provider.provider_type">
                  {{ provider.display_name }}
                </option>
              </select>
            </label>
            <label class="assignment-filter-label assignment-filter-search">
              Search
              <input
                v-model.trim="bindingSearch"
                class="field assignment-filter-input"
                placeholder="Policy template, integration, action template"
              />
            </label>
            <button class="btn btn-ghost btn-sm" type="button" @click="resetBindingFilters()">
              Clear filters
            </button>
          </div>
          <UiDataTable>
            <thead>
              <tr>
                <th>Policy template</th>
                <th>Integration</th>
                <th>Action template</th>
                <th>Event types</th>
                <th>Min severity</th>
                <th>Order/Cooldown</th>
                <th>Status</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="binding in filteredActionBindings" :key="binding.id">
                <td>{{ policyTemplateName(binding.policy_template_id) }}</td>
                <td>{{ integrationName(binding.integration_id) }}</td>
                <td>{{ actionTemplateName(binding.action_template_id) }}</td>
                <td>{{ formatActionEvents(binding.event_types) || "All defaults" }}</td>
                <td>{{ binding.min_severity || "Any" }}</td>
                <td>{{ binding.sort_order }} / {{ binding.cooldown_seconds }}s</td>
                <td><StatusPill :status="binding.enabled ? 'enabled' : 'disabled'" /></td>
                <td>
                  <button
                    class="btn btn-ghost btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="openEditBindingModal(binding)"
                  >
                    Edit
                  </button>
                  <button
                    class="btn btn-danger btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="requestDeleteBinding(binding.id)"
                  >
                    Delete
                  </button>
                </td>
              </tr>
              <tr v-if="actionBindings.length === 0">
                <td colspan="8" class="section-subtitle">No policy action bindings yet.</td>
              </tr>
              <tr v-else-if="filteredActionBindings.length === 0">
                <td colspan="8" class="section-subtitle">No bindings match the current filters.</td>
              </tr>
            </tbody>
          </UiDataTable>
        </div>

        <div class="action-block">
          <div class="action-block-header">
            <div>
              <h3>Recent Deliveries</h3>
              <p class="section-subtitle">Inspect queued, sent, and failed action delivery events.</p>
            </div>
            <button class="btn btn-ghost btn-sm" :disabled="loading" @click="loadAll()">
              {{ loading ? "Refreshing..." : "Refresh deliveries" }}
            </button>
          </div>
          <section class="grid-4">
            <UiStatCard title="Total" :value="actionDeliverySummary?.total ?? 0" subtitle="Action events tracked" />
            <UiStatCard title="Queued" :value="actionDeliverySummary?.queued ?? 0" subtitle="Waiting for dispatch" />
            <UiStatCard title="Sent" :value="actionDeliverySummary?.sent ?? 0" subtitle="Provider accepted" />
            <UiStatCard title="Failed" :value="actionDeliverySummary?.failed ?? 0" subtitle="Delivery failed" />
          </section>
          <div
            v-if="actionDeliverySummary && Object.keys(actionDeliverySummary.by_provider_type).length > 0"
            class="provider-capabilities"
          >
            <span
              v-for="entry in Object.entries(actionDeliverySummary.by_provider_type)"
              :key="entry[0]"
              class="provider-chip"
            >
              <strong>{{ providerLabel(entry[0]) }}</strong>
              <span class="provider-chip-detail">{{ entry[1] }} deliveries</span>
            </span>
          </div>
          <div class="assignment-filter-row">
            <label class="assignment-filter-label">
              Status
              <select v-model="deliveryStatusFilter" class="field-select assignment-filter-select">
                <option value="all">All statuses</option>
                <option value="queued">queued</option>
                <option value="sent">sent</option>
                <option value="failed">failed</option>
              </select>
            </label>
            <label class="assignment-filter-label assignment-filter-search">
              Search
              <input
                v-model.trim="deliverySearch"
                class="field assignment-filter-input"
                placeholder="Event, integration, template, alert id, error"
              />
            </label>
            <button class="btn btn-ghost btn-sm" type="button" @click="resetDeliveryFilters()">
              Clear filters
            </button>
          </div>
          <UiDataTable>
            <thead>
              <tr>
                <th>Created</th>
                <th>Event</th>
                <th>Integration / Provider</th>
                <th>Action template</th>
                <th>Status</th>
                <th>Attempts</th>
                <th>Delivery detail</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="delivery in filteredActionDeliveries" :key="delivery.id">
                <td>{{ formatTimestamp(delivery.created_at) }}</td>
                <td>{{ actionEventLabel(delivery.event_type) }}</td>
                <td>
                  <div class="scope-cell">
                    <span>{{ delivery.integration_name || "—" }}</span>
                    <span class="section-subtitle">{{ delivery.provider_type ? providerLabel(delivery.provider_type) : "—" }}</span>
                  </div>
                </td>
                <td>{{ delivery.action_template_name || "—" }}</td>
                <td><StatusPill :status="delivery.status" /></td>
                <td>{{ delivery.attempts }}</td>
                <td>
                  <div class="scope-cell">
                    <span>{{ delivery.last_error || "—" }}</span>
                    <span v-if="!delivery.last_error && delivery.sent_at" class="section-subtitle">
                      Sent {{ formatTimestamp(delivery.sent_at) }}
                    </span>
                    <span v-else-if="delivery.next_attempt_at" class="section-subtitle">
                      Next {{ formatTimestamp(delivery.next_attempt_at) }}
                    </span>
                  </div>
                </td>
              </tr>
              <tr v-if="actionDeliveries.length === 0">
                <td colspan="7" class="section-subtitle">No action deliveries recorded yet.</td>
              </tr>
              <tr v-else-if="filteredActionDeliveries.length === 0">
                <td colspan="7" class="section-subtitle">No deliveries match the current filters.</td>
              </tr>
            </tbody>
          </UiDataTable>
        </div>
          </UiPanelCard>
        </section>
    </div>
  </section>
  <teleport to="body">
    <div v-if="showGroupMembersModal" class="modal-backdrop" @click.self="closeGroupMembersModal()">
      <div class="glass-card modal-card modal-card-lg">
        <header class="modal-header">
          <div>
            <h3>{{ selectedGroup ? `Group Members · ${selectedGroup.name}` : "Group Members" }}</h3>
            <p class="section-subtitle">Add or remove repeaters from this node group.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeGroupMembersModal()">Close</button>
        </header>

        <template v-if="selectedGroup">
          <form class="member-row" @submit.prevent="addSelectedMember()">
            <label class="field-label">
              Add repeater
              <select v-model="selectedMemberRepeaterId" class="field-select">
                <option value="">Select repeater</option>
                <option v-for="repeater in appState.repeaters" :key="repeater.id" :value="repeater.id">
                  {{ repeater.node_name }}
                </option>
              </select>
            </label>
            <button class="btn btn-secondary" :disabled="!canOperate || actionLoading || !selectedMemberRepeaterId">
              Add member
            </button>
          </form>
          <UiDataTable>
            <thead>
              <tr>
                <th>Node</th>
                <th>Status</th>
                <th>Last Inform</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="member in selectedGroup.members" :key="member.repeater_id">
                <td>{{ member.node_name }}</td>
                <td><StatusPill :status="member.status" /></td>
                <td>{{ formatTimestamp(member.last_inform_at) }}</td>
                <td>
                  <button
                    class="btn btn-ghost btn-sm"
                    :disabled="!canOperate || actionLoading"
                    @click="removeSelectedMember(member.repeater_id)"
                  >
                    Remove
                  </button>
                </td>
              </tr>
              <tr v-if="selectedGroup.members.length === 0">
                <td colspan="4" class="section-subtitle">No group members yet.</td>
              </tr>
            </tbody>
          </UiDataTable>
        </template>
        <p v-else class="section-subtitle">Select a group to view membership.</p>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div
      v-if="showActionTemplatePreviewModal"
      class="modal-backdrop"
      @click.self="closeActionTemplatePreviewModal()"
    >
      <div class="glass-card modal-card modal-card-lg">
        <header class="modal-header">
          <div>
            <h3>Action Template Preview</h3>
            <p class="section-subtitle">{{ actionTemplatePreviewName || "Template preview" }}</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeActionTemplatePreviewModal()">
            Close
          </button>
        </header>
        <div v-if="actionTemplatePreviewLoading" class="section-subtitle">Rendering template preview...</div>
        <div v-else-if="actionTemplatePreviewResult" class="preview-grid">
          <div class="scope-cell">
            <strong>Event</strong>
            <span>{{ actionEventLabel(actionTemplatePreviewResult.event_type) }}</span>
          </div>
          <div class="scope-cell">
            <strong>Rendered title</strong>
            <span>{{ actionTemplatePreviewResult.title || "—" }}</span>
          </div>
          <div class="scope-cell">
            <strong>Rendered body</strong>
            <span>{{ actionTemplatePreviewResult.body || "—" }}</span>
          </div>
          <div class="scope-cell">
            <strong>Rendered payload</strong>
            <pre class="json-preview">{{ prettyJson(actionTemplatePreviewResult.payload) }}</pre>
          </div>
          <div class="scope-cell">
            <strong>Context</strong>
            <pre class="json-preview">{{ prettyJson(actionTemplatePreviewResult.context) }}</pre>
          </div>
        </div>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showCreateGroupModal" class="modal-backdrop" @click.self="closeCreateGroupModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>Create Node Group</h3>
            <p class="section-subtitle">Use groups to apply template assignments to multiple repeaters.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeCreateGroupModal()">Close</button>
        </header>

        <form class="panel-form" @submit.prevent="submitCreateGroupModal()">
          <label class="field-label">
            Group name
            <input v-model.trim="groupForm.name" class="field" required />
          </label>
          <label class="field-label">
            Description
            <input v-model.trim="groupForm.description" class="field" />
          </label>
          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeCreateGroupModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="!canOperate || actionLoading">
              {{ actionLoading ? "Saving..." : "Create group" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showCreateTemplateModal" class="modal-backdrop" @click.self="closeCreateTemplateModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>Create Policy Template</h3>
            <p class="section-subtitle">Define one policy once, then assign it by scope.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeCreateTemplateModal()">Close</button>
        </header>

        <form class="panel-form" @submit.prevent="submitCreateTemplateModal()">
          <label class="field-label">
            Template name
            <input v-model.trim="templateForm.name" class="field" required />
          </label>
          <label class="field-label">
            Rule type
            <select v-model="templateForm.rule_type" class="field-select">
              <option v-for="option in ruleTypeOptions" :key="option.value" :value="option.value">
                {{ option.value }} · {{ option.label }}
              </option>
            </select>
          </label>
          <p class="section-subtitle">
            {{ selectedRuleTypeMeta?.description || "Choose a rule type and set thresholds as needed." }}
          </p>
          <label class="field-label">
            Severity
            <select v-model="templateForm.severity" class="field-select">
              <option value="critical">critical</option>
              <option value="warning">warning</option>
              <option value="info">info</option>
            </select>
          </label>
          <label v-if="selectedRuleTypeMeta?.usesThreshold" class="field-label">
            Threshold value
            <input v-model.number="templateForm.threshold_value" class="field" type="number" step="0.1" />
          </label>
          <label v-if="selectedRuleTypeMeta?.usesWindow" class="field-label">
            Window minutes
            <input v-model.number="templateForm.window_minutes" class="field" type="number" min="1" />
          </label>
          <label v-if="selectedRuleTypeMeta?.usesOfflineGrace" class="field-label">
            Offline grace seconds
            <input v-model.number="templateForm.offline_grace_seconds" class="field" type="number" min="5" />
          </label>
          <label class="toggle-row">
            <input v-model="templateForm.enabled" type="checkbox" />
            <span>Enabled</span>
          </label>
          <label class="toggle-row">
            <input v-model="templateForm.auto_resolve" type="checkbox" />
            <span>Auto resolve</span>
          </label>
          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeCreateTemplateModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="!canOperate || actionLoading">
              {{ actionLoading ? "Saving..." : "Create template" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showCreateAssignmentModal" class="modal-backdrop" @click.self="closeCreateAssignmentModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>Create Scope Assignment</h3>
            <p class="section-subtitle">Follow the guided steps to apply a template to the right scope.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeCreateAssignmentModal()">Close</button>
        </header>
        <div class="wizard-steps" role="tablist" aria-label="Assignment wizard steps">
          <span class="wizard-step" :class="{ active: assignmentWizardStep === 1 }">1. Template</span>
          <span class="wizard-step" :class="{ active: assignmentWizardStep === 2 }">2. Scope type</span>
          <span class="wizard-step" :class="{ active: assignmentWizardStep === 3 }">3. Scope target</span>
          <span class="wizard-step" :class="{ active: assignmentWizardStep === 4 }">4. Review</span>
        </div>

        <form class="panel-form" @submit.prevent="submitCreateAssignmentModal()">
          <template v-if="assignmentWizardStep === 1">
            <label class="field-label">
              Template
              <select v-model="assignmentForm.template_id" class="field-select">
                <option value="">Select template</option>
                <option v-for="template in templates" :key="template.id" :value="template.id">
                  {{ template.name }} ({{ formatRuleTypeLabel(template.rule_type) }})
                </option>
              </select>
            </label>
            <p class="section-subtitle" v-if="selectedAssignmentTemplate">
              {{ selectedAssignmentTemplate.name }} · {{ formatRuleTypeLabel(selectedAssignmentTemplate.rule_type) }} ·
              <span class="severity-pill" :class="severityClass(selectedAssignmentTemplate.severity)">{{ selectedAssignmentTemplate.severity }}</span>
            </p>
          </template>

          <template v-else-if="assignmentWizardStep === 2">
            <label class="field-label">
              Scope type
              <select v-model="assignmentForm.scope_type" class="field-select">
                <option value="global">Global (fleet-wide)</option>
                <option value="group">Group</option>
                <option value="node">Single repeater</option>
              </select>
            </label>
            <p class="section-subtitle">
              {{ assignmentForm.scope_type === "global"
                ? "Use this when every repeater should receive the template."
                : assignmentForm.scope_type === "group"
                  ? "Use this when only repeaters in a node group should receive the template."
                  : "Use this for a single repeater override." }}
            </p>
          </template>

          <template v-else-if="assignmentWizardStep === 3">
            <label v-if="assignmentForm.scope_type === 'group'" class="field-label">
              Group
              <select v-model="assignmentForm.scope_id" class="field-select">
                <option value="">Select group</option>
                <option v-for="group in groups" :key="group.id" :value="group.id">{{ group.name }}</option>
              </select>
            </label>
            <label v-if="assignmentForm.scope_type === 'node'" class="field-label">
              Repeater
              <select v-model="assignmentForm.scope_id" class="field-select">
                <option value="">Select repeater</option>
                <option v-for="repeater in appState.repeaters" :key="repeater.id" :value="repeater.id">
                  {{ repeater.node_name }}
                </option>
              </select>
            </label>
            <label class="field-label">
              Priority
              <input v-model.number="assignmentForm.priority" class="field" type="number" min="0" />
            </label>
            <label class="toggle-row">
              <input v-model="assignmentForm.enabled" type="checkbox" />
              <span>Enabled</span>
            </label>
          </template>

          <template v-else>
            <div class="review-grid">
              <p><strong>Template:</strong> {{ selectedAssignmentTemplate?.name || "—" }}</p>
              <p><strong>Rule:</strong> {{ selectedAssignmentTemplate ? formatRuleTypeLabel(selectedAssignmentTemplate.rule_type) : "—" }}</p>
              <p><strong>Scope type:</strong> {{ scopeTypeLabel(assignmentForm.scope_type) }}</p>
              <p><strong>Scope target:</strong> {{ assignmentScopeSummary }}</p>
              <p><strong>Priority:</strong> {{ assignmentForm.priority }}</p>
              <p><strong>Status:</strong> {{ assignmentForm.enabled ? "Enabled" : "Disabled" }}</p>
            </div>
          </template>

          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeCreateAssignmentModal()">Cancel</button>
            <button
              v-if="assignmentWizardStep > 1"
              class="btn btn-ghost"
              type="button"
              :disabled="actionLoading"
              @click="previousAssignmentWizardStep()"
            >
              Back
            </button>
            <button
              v-if="assignmentWizardStep < 4"
              class="btn btn-secondary"
              type="button"
              :disabled="!canProceedAssignmentWizardStep"
              @click="nextAssignmentWizardStep()"
            >
              Next
            </button>
            <button
              v-else
              class="btn btn-primary"
              :disabled="!canOperate || actionLoading || !canSubmitAssignmentWizard"
            >
              {{ actionLoading ? "Saving..." : "Create assignment" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>
  <teleport to="body">
    <div v-if="showIntegrationModal" class="modal-backdrop" @click.self="closeIntegrationModal()">
      <div class="glass-card modal-card modal-card-scroll">
        <header class="modal-header">
          <div>
            <h3>{{ integrationModalMode === "create" ? "Create Integration" : "Edit Integration" }}</h3>
            <p class="section-subtitle">Configure provider-specific delivery settings for outbound actions.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeIntegrationModal()">Close</button>
        </header>

        <form class="panel-form" @submit.prevent="submitIntegrationModal()">
          <label class="field-label">
            Name
            <input v-model.trim="integrationForm.name" class="field" required />
          </label>
          <label class="field-label">
            Provider
            <select v-model="integrationForm.provider_type" class="field-select" :disabled="integrationModalMode === 'edit'">
              <option v-for="provider in providerTypeOptions" :key="provider.value" :value="provider.value">
                {{ provider.label }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Description
            <input v-model.trim="integrationForm.description" class="field" />
          </label>

          <template v-if="integrationForm.provider_type === 'webhook'">
            <label class="field-label">
              Webhook URL
              <input v-model.trim="integrationForm.webhook_url" class="field" placeholder="https://example.com/webhook" required />
            </label>
            <div class="grid-2">
              <label class="field-label">
                HTTP method
                <select v-model="integrationForm.webhook_method" class="field-select">
                  <option value="POST">POST</option>
                  <option value="PUT">PUT</option>
                  <option value="PATCH">PATCH</option>
                </select>
              </label>
              <label class="field-label">
                Timeout (seconds)
                <input v-model.number="integrationForm.webhook_timeout_seconds" class="field" type="number" min="1" max="60" />
              </label>
              <label class="field-label">
                Max body bytes
                <input v-model.number="integrationForm.webhook_max_body_bytes" class="field" type="number" min="1024" max="5000000" />
              </label>
              <label class="toggle-row">
                <input v-model="integrationForm.webhook_verify_tls" type="checkbox" />
                <span>Verify TLS certificates</span>
              </label>
            </div>
            <label class="field-label">
              Extra headers (JSON object)
              <textarea
                v-model="integrationForm.webhook_headers_json"
                class="field-textarea"
                placeholder='{"X-Custom-Header":"value"}'
              />
            </label>
          </template>

          <template v-else-if="integrationForm.provider_type === 'pushover'">
            <div class="grid-2">
              <label class="field-label">
                App token
                <input v-model.trim="integrationForm.pushover_app_token" class="field" required />
              </label>
              <label class="field-label">
                User key
                <input v-model.trim="integrationForm.pushover_user_key" class="field" required />
              </label>
              <label class="field-label">
                Device (optional)
                <input v-model.trim="integrationForm.pushover_device" class="field" />
              </label>
              <label class="field-label">
                Priority
                <input v-model.number="integrationForm.pushover_priority" class="field" type="number" min="-2" max="2" />
              </label>
              <label class="field-label">
                Sound (optional)
                <input v-model.trim="integrationForm.pushover_sound" class="field" />
              </label>
            </div>
          </template>
          <template v-else-if="integrationForm.provider_type === 'apprise'">
            <label class="field-label">
              Apprise notify URL
              <input
                v-model.trim="integrationForm.apprise_api_url"
                class="field"
                placeholder="https://apprise.local/notify"
                required
              />
            </label>
            <label class="field-label">
              Destination URLs (optional for stateful endpoint)
              <textarea
                v-model="integrationForm.apprise_urls"
                class="field-textarea"
                placeholder="mailto://alerts@example.com"
              />
            </label>
            <div class="grid-2">
              <label class="field-label">
                Tag (optional)
                <input v-model.trim="integrationForm.apprise_tag" class="field" />
              </label>
              <label class="field-label">
                Default notification type
                <select v-model="integrationForm.apprise_notify_type" class="field-select">
                  <option value="info">info</option>
                  <option value="success">success</option>
                  <option value="warning">warning</option>
                  <option value="failure">failure</option>
                </select>
              </label>
              <label class="field-label">
                Default format
                <select v-model="integrationForm.apprise_format" class="field-select">
                  <option value="">Service default</option>
                  <option value="text">text</option>
                  <option value="markdown">markdown</option>
                  <option value="html">html</option>
                </select>
              </label>
              <label class="field-label">
                Timeout (seconds)
                <input v-model.number="integrationForm.apprise_timeout_seconds" class="field" type="number" min="1" max="60" />
              </label>
              <label class="toggle-row">
                <input v-model="integrationForm.apprise_verify_tls" type="checkbox" />
                <span>Verify TLS certificates</span>
              </label>
            </div>
            <label class="field-label">
              Extra headers (JSON object)
              <textarea
                v-model="integrationForm.apprise_headers_json"
                class="field-textarea"
                placeholder='{"X-Custom-Header":"value"}'
              />
            </label>
          </template>

          <template v-else>
            <label class="field-label">
              Settings (JSON object)
              <textarea v-model="integrationForm.settings_json" class="field-textarea" placeholder="{}" />
            </label>
          </template>

          <label class="field-label">
            Secrets (JSON object, optional)
            <textarea
              v-model="integrationForm.secrets_json"
              class="field-textarea"
              placeholder='{"api_token":"value"}'
            />
          </label>
          <label v-if="integrationModalMode === 'edit'" class="toggle-row">
            <input v-model="integrationForm.clear_secrets" type="checkbox" />
            <span>Clear stored secrets</span>
          </label>
          <label class="toggle-row">
            <input v-model="integrationForm.enabled" type="checkbox" />
            <span>Enabled</span>
          </label>

          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeIntegrationModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="!canOperate || actionLoading">
              {{ actionLoading ? "Saving..." : integrationModalMode === "create" ? "Create integration" : "Save integration" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showActionTemplateModal" class="modal-backdrop" @click.self="closeActionTemplateModal()">
      <div class="glass-card modal-card modal-card-lg">
        <header class="modal-header">
          <div>
            <h3>{{ actionTemplateModalMode === "create" ? "Create Action Template" : "Edit Action Template" }}</h3>
            <p class="section-subtitle">Define reusable title/body/payload templates for outbound actions.</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeActionTemplateModal()">Close</button>
        </header>

        <form class="panel-form" @submit.prevent="submitActionTemplateModal()">
          <label class="field-label">
            Name
            <input v-model.trim="actionTemplateForm.name" class="field" required />
          </label>
          <label class="field-label">
            Provider constraint
            <select v-model="actionTemplateForm.provider_type" class="field-select">
              <option value="">Any provider</option>
              <option v-for="provider in providerTypeOptions" :key="provider.value" :value="provider.value">
                {{ provider.label }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Description
            <input v-model.trim="actionTemplateForm.description" class="field" />
          </label>
          <label class="field-label">
            Title template (optional)
            <input
              v-model="actionTemplateForm.title_template"
              class="field"
              placeholder="{{ alert.alert_type }} on {{ repeater.node_name }}"
            />
          </label>
          <label class="field-label">
            Body template (optional)
            <textarea
              v-model="actionTemplateForm.body_template"
              class="field-textarea"
              placeholder="{{ alert.message }}"
            />
          </label>
          <label class="field-label">
            Payload template (JSON object, optional)
            <textarea
              v-model="actionTemplateForm.payload_template_json"
              class="field-textarea"
              placeholder='{"title":"{{ title }}","body":"{{ body }}"}'
            />
          </label>
          <div class="field-label">
            <span>Available merge fields</span>
            <pre class="json-preview merge-fields-preview">{{ actionTemplateMergeFieldHelp }}</pre>
          </div>
          <div class="field-label">
            <span>Default event types</span>
            <div class="event-options-grid">
              <label v-for="event in actionEventOptions" :key="event.value" class="toggle-row">
                <input v-model="actionTemplateForm.default_event_types" type="checkbox" :value="event.value" />
                <span>{{ event.label }}</span>
              </label>
            </div>
          </div>
          <label class="toggle-row">
            <input v-model="actionTemplateForm.enabled" type="checkbox" />
            <span>Enabled</span>
          </label>

          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeActionTemplateModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="!canOperate || actionLoading">
              {{ actionLoading ? "Saving..." : actionTemplateModalMode === "create" ? "Create action template" : "Save action template" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showBindingModal" class="modal-backdrop" @click.self="closeBindingModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>{{ bindingModalMode === "create" ? "Create Policy Action Binding" : "Edit Policy Action Binding" }}</h3>
            <p class="section-subtitle">
              Route alert policy template events through an integration and action template.
            </p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeBindingModal()">Close</button>
        </header>

        <form class="panel-form" @submit.prevent="submitBindingModal()">
          <label class="field-label">
            Policy template
            <select v-model="bindingForm.policy_template_id" class="field-select" :disabled="bindingModalMode === 'edit'">
              <option value="">Select policy template</option>
              <option v-for="template in templates" :key="template.id" :value="template.id">
                {{ template.name }}
              </option>
            </select>
          </label>
          <label class="field-label">
            Integration
            <select v-model="bindingForm.integration_id" class="field-select" :disabled="bindingModalMode === 'edit'">
              <option value="">Select integration</option>
              <option v-for="integration in actionIntegrations" :key="integration.id" :value="integration.id">
                {{ integration.name }} ({{ providerLabel(integration.provider_type) }})
              </option>
            </select>
          </label>
          <label class="field-label">
            Action template
            <select v-model="bindingForm.action_template_id" class="field-select" :disabled="bindingModalMode === 'edit'">
              <option value="">Select action template</option>
              <option v-for="template in availableBindingActionTemplates" :key="template.id" :value="template.id">
                {{ template.name }}{{ template.provider_type ? ` (${providerLabel(template.provider_type)})` : "" }}
              </option>
            </select>
          </label>

          <div class="field-label">
            <span>Event types (leave unselected to use action template defaults)</span>
            <div class="event-options-grid">
              <label v-for="event in actionEventOptions" :key="event.value" class="toggle-row">
                <input v-model="bindingForm.event_types" type="checkbox" :value="event.value" />
                <span>{{ event.label }}</span>
              </label>
            </div>
          </div>

          <div class="grid-2">
            <label class="field-label">
              Minimum severity
              <select v-model="bindingForm.min_severity" class="field-select">
                <option value="">Any severity</option>
                <option value="critical">critical</option>
                <option value="warning">warning</option>
                <option value="info">info</option>
              </select>
            </label>
            <label class="field-label">
              Sort order
              <input v-model.number="bindingForm.sort_order" class="field" type="number" min="0" max="1000" />
            </label>
            <label class="field-label">
              Cooldown seconds
              <input v-model.number="bindingForm.cooldown_seconds" class="field" type="number" min="0" max="86400" />
            </label>
          </div>

          <label class="toggle-row">
            <input v-model="bindingForm.enabled" type="checkbox" />
            <span>Enabled</span>
          </label>

          <div class="modal-actions">
            <button class="btn btn-ghost" type="button" @click="closeBindingModal()">Cancel</button>
            <button class="btn btn-primary" :disabled="!canOperate || actionLoading">
              {{ actionLoading ? "Saving..." : bindingModalMode === "create" ? "Create binding" : "Save binding" }}
            </button>
          </div>
        </form>
      </div>
    </div>
  </teleport>

  <teleport to="body">
    <div v-if="showDeleteConfirmModal" class="modal-backdrop" @click.self="closeDeleteConfirmModal()">
      <div class="glass-card modal-card">
        <header class="modal-header">
          <div>
            <h3>{{ deleteConfirmTitle }}</h3>
            <p class="section-subtitle">{{ deleteConfirmMessage }}</p>
          </div>
          <button class="btn btn-ghost btn-sm" type="button" @click="closeDeleteConfirmModal()">Close</button>
        </header>
        <div class="modal-actions">
          <button class="btn btn-ghost" type="button" @click="closeDeleteConfirmModal()">Cancel</button>
          <button class="btn btn-danger" :disabled="!canOperate || actionLoading" @click="confirmDelete()">
            {{ actionLoading ? "Deleting..." : "Delete" }}
          </button>
        </div>
      </div>
    </div>
  </teleport>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from "vue";
import { useRoute } from "vue-router";

import {
  addNodeGroupMember,
  bootstrapDefaultAlertPolicies,
  createAlertActionIntegration,
  createAlertActionTemplate,
  createAlertPolicyAssignment,
  createAlertPolicyActionBinding,
  createAlertPolicyTemplate,
  createNodeGroup,
  deleteAlertActionIntegration,
  deleteAlertActionTemplate,
  deleteAlertPolicyAssignment,
  deleteAlertPolicyActionBinding,
  deleteAlertPolicyTemplate,
  deleteNodeGroup,
  evaluateAlertPolicies,
  getAlertActionDeliverySummary,
  getEffectiveAlertPolicies,
  getNodeGroup,
  listAlertActionIntegrations,
  listAlertActionDeliveries,
  listAlertActionProviders,
  listAlertActionTemplates,
  listAlertPolicyAssignments,
  listAlertPolicyActionBindings,
  listAlertPolicyTemplates,
  listNodeGroups,
  previewAlertActionTemplate,
  removeNodeGroupMember,
  testAlertActionIntegration,
  updateAlertActionIntegration,
  updateAlertActionTemplate,
  updateAlertPolicyActionBinding,
} from "../api";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiPanelCard from "../components/ui/UiPanelCard.vue";
import StatusPill from "../components/ui/StatusPill.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";
import { appState, canOperate, formatTimestamp, refreshAllData } from "../state/appState";
import type {
  AlertActionDeliveryResponse,
  AlertActionDeliverySummaryResponse,
  AlertActionIntegrationResponse,
  AlertActionProviderCapabilityResponse,
  AlertActionTemplatePreviewResponse,
  AlertActionTemplateResponse,
  AlertPolicyActionBindingResponse,
  AlertPolicyAssignmentResponse,
  AlertPolicyEvaluationResponse,
  AlertPolicyTemplateResponse,
  EffectivePolicyItemResponse,
  NodeGroupDetailResponse,
  NodeGroupResponse,
} from "../types";

const loading = ref(false);
const actionLoading = ref(false);
const error = ref<string | null>(null);
const showGroupMembersModal = ref(false);
const showCreateGroupModal = ref(false);
const showCreateTemplateModal = ref(false);
const showCreateAssignmentModal = ref(false);
const assignmentWizardStep = ref(1);
const showDeleteConfirmModal = ref(false);
const deleteConfirmTitle = ref("Confirm delete");
const deleteConfirmMessage = ref("This action cannot be undone.");
const deleteConfirmAction = ref<
  | null
  | {
      type:
        | "group"
        | "template"
        | "assignment"
        | "integration"
        | "action_template"
        | "action_binding";
      id: string;
    }
>(null);
const showIntegrationModal = ref(false);
const integrationModalMode = ref<"create" | "edit">("create");
const integrationEditId = ref<string | null>(null);
const showActionTemplateModal = ref(false);
const actionTemplateModalMode = ref<"create" | "edit">("create");
const actionTemplateEditId = ref<string | null>(null);
const showBindingModal = ref(false);
const bindingModalMode = ref<"create" | "edit">("create");
const bindingEditId = ref<string | null>(null);
const showActionTemplatePreviewModal = ref(false);
const actionTemplatePreviewLoading = ref(false);
const actionTemplatePreviewName = ref("");
const actionTemplatePreviewResult = ref<AlertActionTemplatePreviewResponse | null>(null);
const route = useRoute();

const ruleTypeOptions = [
  {
    value: "offline_repeater",
    label: "Heartbeat stale",
    description: "Triggers when last inform age exceeds offline grace seconds.",
    usesThreshold: false,
    usesWindow: false,
    usesOfflineGrace: true,
  },
  {
    value: "tls_telemetry_stale",
    label: "TLS telemetry stale",
    description:
      "Triggers when inform and MQTT telemetry are stale while repeater MQTT TLS is enabled.",
    usesThreshold: false,
    usesWindow: false,
    usesOfflineGrace: true,
  },
  {
    value: "high_noise_floor",
    label: "High noise floor",
    description: "Triggers when average noise floor exceeds threshold over the window.",
    usesThreshold: true,
    usesWindow: true,
    usesOfflineGrace: false,
  },
  {
    value: "high_cpu_percent",
    label: "High CPU %",
    description: "Triggers when average CPU utilization exceeds threshold over the window.",
    usesThreshold: true,
    usesWindow: true,
    usesOfflineGrace: false,
  },
  {
    value: "high_memory_percent",
    label: "High memory %",
    description: "Triggers when average memory utilization exceeds threshold over the window.",
    usesThreshold: true,
    usesWindow: true,
    usesOfflineGrace: false,
  },
  {
    value: "high_disk_percent",
    label: "High disk %",
    description: "Triggers when average disk utilization exceeds threshold over the window.",
    usesThreshold: true,
    usesWindow: true,
    usesOfflineGrace: false,
  },
  {
    value: "high_temperature_c",
    label: "High temperature °C",
    description: "Triggers when current temperature exceeds threshold.",
    usesThreshold: true,
    usesWindow: false,
    usesOfflineGrace: false,
  },
  {
    value: "high_airtime_percent",
    label: "High airtime %",
    description: "Triggers when average airtime usage exceeds threshold over the window.",
    usesThreshold: true,
    usesWindow: true,
    usesOfflineGrace: false,
  },
  {
    value: "high_drop_rate",
    label: "High drop rate",
    description: "Triggers when dropped traffic ratio exceeds threshold over the window.",
    usesThreshold: true,
    usesWindow: true,
    usesOfflineGrace: false,
  },
  {
    value: "new_zero_hop_node_detected",
    label: "New zero-hop node detected",
    description: "Triggers when a never-before-seen node appears via zero-hop advert in the window.",
    usesThreshold: false,
    usesWindow: true,
    usesOfflineGrace: false,
  },
] as const;
const actionEventOptions = [
  { value: "alert_activated", label: "Alert activated" },
  { value: "alert_reactivated", label: "Alert reactivated" },
  { value: "alert_resolved", label: "Alert resolved" },
  { value: "alert_acknowledged", label: "Alert acknowledged" },
  { value: "alert_suppressed", label: "Alert suppressed" },
  { value: "alert_auto_resolved", label: "Alert auto-resolved" },
] as const;
const policySubsectionOptions = [
  { value: "groups", label: "Node Groups" },
  { value: "templates", label: "Policy Templates" },
  { value: "assignments", label: "Scope Assignments" },
  { value: "actions", label: "Actions" },
  { value: "evaluation", label: "Effective + Evaluation" },
] as const;
type PolicySubsection = (typeof policySubsectionOptions)[number]["value"];
const policySubsectionSet = new Set<PolicySubsection>(policySubsectionOptions.map((option) => option.value));
const activeSubsection = ref<PolicySubsection>("groups");
const actionTemplateMergeFieldHelp = [
  "alert: {{ alert.id }}, {{ alert.alert_type }}, {{ alert.severity }}, {{ alert.message }}, {{ alert.state }}, {{ alert.fingerprint }}, {{ alert.first_seen_at }}, {{ alert.last_seen_at }}, {{ alert.acked_at }}, {{ alert.resolved_at }}, {{ alert.note }}",
  "repeater: {{ repeater.id }}, {{ repeater.node_name }}, {{ repeater.pubkey }}, {{ repeater.status }}, {{ repeater.location }}",
  "policy: {{ policy.id }}, {{ policy.name }}, {{ policy.rule_type }}, {{ policy.severity }}",
  "event: {{ event.type }}, {{ event.label }}, {{ event.actor }}, {{ event.note }}, {{ event.occurred_at }}",
].join("\n");

const groups = ref<NodeGroupResponse[]>([]);
const templates = ref<AlertPolicyTemplateResponse[]>([]);
const assignments = ref<AlertPolicyAssignmentResponse[]>([]);
const actionProviders = ref<AlertActionProviderCapabilityResponse[]>([]);
const actionIntegrations = ref<AlertActionIntegrationResponse[]>([]);
const actionTemplates = ref<AlertActionTemplateResponse[]>([]);
const actionBindings = ref<AlertPolicyActionBindingResponse[]>([]);
const actionDeliverySummary = ref<AlertActionDeliverySummaryResponse | null>(null);
const actionDeliveries = ref<AlertActionDeliveryResponse[]>([]);
const selectedGroupId = ref<string | null>(null);
const selectedGroup = ref<NodeGroupDetailResponse | null>(null);
const selectedMemberRepeaterId = ref("");
const selectedRepeaterId = ref("");
const effectivePolicies = ref<EffectivePolicyItemResponse[]>([]);
const evaluationResult = ref<AlertPolicyEvaluationResponse | null>(null);

const groupForm = reactive({
  name: "",
  description: "",
});

const templateForm = reactive({
  name: "",
  rule_type: "offline_repeater",
  severity: "warning",
  threshold_value: null as number | null,
  window_minutes: null as number | null,
  offline_grace_seconds: null as number | null,
  enabled: true,
  auto_resolve: true,
});

const assignmentForm = reactive({
  template_id: "",
  scope_type: "global",
  scope_id: "",
  priority: 100,
  enabled: true,
});
const integrationForm = reactive({
  name: "",
  provider_type: "webhook",
  description: "",
  enabled: true,
  webhook_url: "",
  webhook_method: "POST",
  webhook_timeout_seconds: 10,
  webhook_verify_tls: true,
  webhook_max_body_bytes: 262_144,
  webhook_headers_json: "{}",
  pushover_app_token: "",
  pushover_user_key: "",
  pushover_device: "",
  pushover_priority: 0,
  pushover_sound: "",
  apprise_api_url: "",
  apprise_urls: "",
  apprise_tag: "",
  apprise_notify_type: "info",
  apprise_format: "",
  apprise_timeout_seconds: 15,
  apprise_verify_tls: true,
  apprise_headers_json: "{}",
  settings_json: "{}",
  secrets_json: "",
  clear_secrets: false,
});
const actionTemplateForm = reactive({
  name: "",
  provider_type: "",
  description: "",
  title_template: "",
  body_template: "",
  payload_template_json: "",
  default_event_types: [] as string[],
  enabled: true,
});
const bindingForm = reactive({
  policy_template_id: "",
  integration_id: "",
  action_template_id: "",
  event_types: [] as string[],
  min_severity: "",
  enabled: true,
  sort_order: 100,
  cooldown_seconds: 0,
});
const assignmentScopeFilter = ref("all");
const assignmentSearch = ref("");
const bindingProviderFilter = ref("all");
const bindingSearch = ref("");
const deliveryStatusFilter = ref("all");
const deliverySearch = ref("");

const selectedRuleTypeMeta = computed(() =>
  ruleTypeOptions.find((item) => item.value === templateForm.rule_type),
);
const providerTypeOptions = computed(() => {
  if (actionProviders.value.length > 0) {
    return actionProviders.value.map((provider) => ({
      value: provider.provider_type,
      label: provider.display_name,
    }));
  }
  return [
    { value: "webhook", label: "Webhook" },
    { value: "pushover", label: "Pushover" },
    { value: "apprise", label: "Apprise" },
  ];
});
const filteredAssignments = computed(() => {
  const scopeFilter = assignmentScopeFilter.value;
  const query = assignmentSearch.value.trim().toLowerCase();
  return assignments.value.filter((assignment) => {
    if (scopeFilter !== "all" && assignment.scope_type !== scopeFilter) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = [
      assignment.template_name,
      formatRuleTypeLabel(assignment.rule_type),
      scopeTypeLabel(assignment.scope_type),
      assignment.scope_name ?? "",
      assignment.scope_id ?? "",
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
});
const filteredActionDeliveries = computed(() => {
  const statusFilter = deliveryStatusFilter.value;
  const query = deliverySearch.value.trim().toLowerCase();
  return actionDeliveries.value.filter((delivery) => {
    if (statusFilter !== "all" && delivery.status !== statusFilter) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = [
      delivery.event_type,
      delivery.provider_type ?? "",
      delivery.integration_name ?? "",
      delivery.action_template_name ?? "",
      delivery.last_error ?? "",
      delivery.alert_id,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
});
const selectedAssignmentTemplate = computed(() =>
  templates.value.find((item) => item.id === assignmentForm.template_id) ?? null,
);
const canProceedAssignmentWizardStep = computed(() => {
  if (assignmentWizardStep.value === 1) {
    return Boolean(assignmentForm.template_id);
  }
  if (assignmentWizardStep.value === 2) {
    return true;
  }
  if (assignmentWizardStep.value === 3) {
    if (assignmentForm.scope_type === "global") {
      return true;
    }
    return Boolean(assignmentForm.scope_id);
  }
  return true;
});
const canSubmitAssignmentWizard = computed(() => {
  if (!assignmentForm.template_id) {
    return false;
  }
  if (assignmentForm.scope_type === "global") {
    return true;
  }
  return Boolean(assignmentForm.scope_id);
});
const assignmentScopeSummary = computed(() => {
  if (assignmentForm.scope_type === "global") {
    return "Fleet-wide";
  }
  if (!assignmentForm.scope_id) {
    return "—";
  }
  if (assignmentForm.scope_type === "group") {
    const group = groups.value.find((item) => item.id === assignmentForm.scope_id);
    return group?.name ?? assignmentForm.scope_id;
  }
  const repeater = appState.repeaters.find((item) => item.id === assignmentForm.scope_id);
  return repeater?.node_name ?? assignmentForm.scope_id;
});

const integrationById = computed(() => {
  return new Map(actionIntegrations.value.map((item) => [item.id, item]));
});
const actionTemplateById = computed(() => {
  return new Map(actionTemplates.value.map((item) => [item.id, item]));
});
const policyTemplateById = computed(() => {
  return new Map(templates.value.map((item) => [item.id, item]));
});
const availableBindingActionTemplates = computed(() => {
  const selectedIntegration = integrationById.value.get(bindingForm.integration_id);
  if (!selectedIntegration) {
    return actionTemplates.value;
  }
  return actionTemplates.value.filter(
    (template) =>
      !template.provider_type ||
      template.provider_type === selectedIntegration.provider_type ||
      template.id === bindingForm.action_template_id,
  );
});
const filteredActionBindings = computed(() => {
  const providerFilter = bindingProviderFilter.value;
  const query = bindingSearch.value.trim().toLowerCase();
  return actionBindings.value.filter((binding) => {
    const integration = integrationById.value.get(binding.integration_id);
    if (providerFilter !== "all" && integration?.provider_type !== providerFilter) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = [
      policyTemplateName(binding.policy_template_id),
      integrationName(binding.integration_id),
      actionTemplateName(binding.action_template_id),
      formatActionEvents(binding.event_types),
      binding.min_severity ?? "",
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(query);
  });
});
watch(
  () => assignmentForm.scope_type,
  () => {
    assignmentForm.scope_id = "";
  },
);

watch(
  () => templateForm.rule_type,
  () => {
    if (!selectedRuleTypeMeta.value?.usesThreshold) {
      templateForm.threshold_value = null;
    }
    if (!selectedRuleTypeMeta.value?.usesWindow) {
      templateForm.window_minutes = null;
    }
    if (!selectedRuleTypeMeta.value?.usesOfflineGrace) {
      templateForm.offline_grace_seconds = null;
    }
  },
);
watch(
  () => bindingForm.integration_id,
  () => {
    if (bindingModalMode.value !== "create" || !bindingForm.action_template_id) {
      return;
    }
    const stillCompatible = availableBindingActionTemplates.value.some(
      (template) => template.id === bindingForm.action_template_id,
    );
    if (!stillCompatible) {
      bindingForm.action_template_id = "";
    }
  },
);
watch(
  () => route.path,
  () => {
    activeSubsection.value = resolvePolicySubsectionFromPath(route.path);
  },
  { immediate: true },
);

onMounted(async () => {
  await refreshAllData();
  await loadAll();
});

function resetGroupForm(): void {
  groupForm.name = "";
  groupForm.description = "";
}

function formatRuleTypeLabel(ruleType: string): string {
  const rule = ruleTypeOptions.find((item) => item.value === ruleType);
  return rule?.label ?? ruleType;
}

function scopeTypeLabel(scopeType: string): string {
  if (scopeType === "global") {
    return "Global";
  }
  if (scopeType === "group") {
    return "Group";
  }
  if (scopeType === "node") {
    return "Node";
  }
  return scopeType;
}
function scopePillClass(scopeType: string): string {
  if (scopeType === "global") {
    return "scope-global";
  }
  if (scopeType === "group") {
    return "scope-group";
  }
  if (scopeType === "node") {
    return "scope-node";
  }
  return "";
}

function severityClass(severity: string): string {
  if (severity === "critical") {
    return "severity-critical";
  }
  if (severity === "warning") {
    return "severity-warning";
  }
  return "severity-info";
}

function resetTemplateForm(): void {
  templateForm.name = "";
  templateForm.rule_type = "offline_repeater";
  templateForm.severity = "warning";
  templateForm.threshold_value = null;
  templateForm.window_minutes = null;
  templateForm.offline_grace_seconds = null;
  templateForm.enabled = true;
  templateForm.auto_resolve = true;
}

function resetAssignmentForm(): void {
  assignmentForm.template_id = "";
  assignmentForm.scope_type = "global";
  assignmentForm.scope_id = "";
  assignmentForm.priority = 100;
  assignmentForm.enabled = true;
}
function resetAssignmentFilters(): void {
  assignmentScopeFilter.value = "all";
  assignmentSearch.value = "";
}
function resetBindingFilters(): void {
  bindingProviderFilter.value = "all";
  bindingSearch.value = "";
}
function resetDeliveryFilters(): void {
  deliveryStatusFilter.value = "all";
  deliverySearch.value = "";
}
function resolvePolicySubsectionFromPath(path: string): PolicySubsection {
  const subsectionCandidate = path.split("/").filter(Boolean)[1];
  if (typeof subsectionCandidate === "string" && policySubsectionSet.has(subsectionCandidate as PolicySubsection)) {
    return subsectionCandidate as PolicySubsection;
  }
  return "groups";
}
function resetIntegrationForm(): void {
  integrationForm.name = "";
  integrationForm.provider_type = providerTypeOptions.value[0]?.value ?? "webhook";
  integrationForm.description = "";
  integrationForm.enabled = true;
  integrationForm.webhook_url = "";
  integrationForm.webhook_method = "POST";
  integrationForm.webhook_timeout_seconds = 10;
  integrationForm.webhook_verify_tls = true;
  integrationForm.webhook_max_body_bytes = 262_144;
  integrationForm.webhook_headers_json = "{}";
  integrationForm.pushover_app_token = "";
  integrationForm.pushover_user_key = "";
  integrationForm.pushover_device = "";
  integrationForm.pushover_priority = 0;
  integrationForm.pushover_sound = "";
  integrationForm.apprise_api_url = "";
  integrationForm.apprise_urls = "";
  integrationForm.apprise_tag = "";
  integrationForm.apprise_notify_type = "info";
  integrationForm.apprise_format = "";
  integrationForm.apprise_timeout_seconds = 15;
  integrationForm.apprise_verify_tls = true;
  integrationForm.apprise_headers_json = "{}";
  integrationForm.settings_json = "{}";
  integrationForm.secrets_json = "";
  integrationForm.clear_secrets = false;
}
function resetActionTemplateForm(): void {
  actionTemplateForm.name = "";
  actionTemplateForm.provider_type = "";
  actionTemplateForm.description = "";
  actionTemplateForm.title_template = "{{ event.label }} · {{ policy.name }} · {{ alert.alert_type }} ({{ alert.severity }})";
  actionTemplateForm.body_template = [
    "Node: {{ repeater.node_name }}",
    "Message: {{ alert.message }}",
    "Event: {{ event.label }} ({{ event.type }}) at {{ event.occurred_at }}",
  ].join("\n");
  actionTemplateForm.payload_template_json = JSON.stringify(
    {
      title: "{{ policy.name }} · {{ alert.alert_type }}",
      body: "{{ alert.message }}",
      alert_id: "{{ alert.id }}",
      severity: "{{ alert.severity }}",
      node_name: "{{ repeater.node_name }}",
      event_type: "{{ event.type }}",
      event_label: "{{ event.label }}",
    },
    null,
    2,
  );
  actionTemplateForm.default_event_types = ["alert_activated", "alert_resolved"];
  actionTemplateForm.enabled = true;
}
function resetBindingForm(): void {
  bindingForm.policy_template_id = "";
  bindingForm.integration_id = "";
  bindingForm.action_template_id = "";
  bindingForm.event_types = [];
  bindingForm.min_severity = "";
  bindingForm.enabled = true;
  bindingForm.sort_order = 100;
  bindingForm.cooldown_seconds = 0;
}
function asRecord(value: unknown): Record<string, unknown> {
  if (!value || Array.isArray(value) || typeof value !== "object") {
    return {};
  }
  return value as Record<string, unknown>;
}
function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}
function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}
function asBoolean(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}
function parseJsonObject(
  raw: string,
  fieldLabel: string,
  options?: { allowEmpty?: boolean },
): Record<string, unknown> | null {
  const trimmed = raw.trim();
  const allowEmpty = options?.allowEmpty ?? false;
  if (!trimmed) {
    return allowEmpty ? null : {};
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    throw new Error(`${fieldLabel} must be valid JSON.`);
  }
  if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") {
    throw new Error(`${fieldLabel} must be a JSON object.`);
  }
  return parsed as Record<string, unknown>;
}
function providerLabel(providerType: string): string {
  return (
    actionProviders.value.find((item) => item.provider_type === providerType)?.display_name ?? providerType
  );
}
function actionEventLabel(eventType: string): string {
  return actionEventOptions.find((item) => item.value === eventType)?.label ?? eventType;
}
function formatActionEvents(eventTypes: string[]): string {
  if (eventTypes.length === 0) {
    return "";
  }
  return eventTypes.map((eventType) => actionEventLabel(eventType)).join(", ");
}
function policyTemplateName(templateId: string): string {
  return policyTemplateById.value.get(templateId)?.name ?? templateId;
}
function integrationName(integrationId: string): string {
  return integrationById.value.get(integrationId)?.name ?? integrationId;
}
function actionTemplateName(templateId: string): string {
  return actionTemplateById.value.get(templateId)?.name ?? templateId;
}

function openCreateGroupModal(): void {
  resetGroupForm();
  showCreateGroupModal.value = true;
}
async function openGroupMembersModal(groupId: string): Promise<void> {
  await selectGroup(groupId);
  showGroupMembersModal.value = true;
}

function closeGroupMembersModal(): void {
  showGroupMembersModal.value = false;
  selectedMemberRepeaterId.value = "";
}

function closeCreateGroupModal(): void {
  showCreateGroupModal.value = false;
}

function openCreateTemplateModal(): void {
  resetTemplateForm();
  showCreateTemplateModal.value = true;
}

function closeCreateTemplateModal(): void {
  showCreateTemplateModal.value = false;
}

function openCreateAssignmentModal(): void {
  resetAssignmentForm();
  assignmentWizardStep.value = 1;
  showCreateAssignmentModal.value = true;
}

function closeCreateAssignmentModal(): void {
  showCreateAssignmentModal.value = false;
  assignmentWizardStep.value = 1;
}
function openCreateIntegrationModal(): void {
  resetIntegrationForm();
  integrationModalMode.value = "create";
  integrationEditId.value = null;
  showIntegrationModal.value = true;
}
function openEditIntegrationModal(integration: AlertActionIntegrationResponse): void {
  resetIntegrationForm();
  integrationModalMode.value = "edit";
  integrationEditId.value = integration.id;
  integrationForm.name = integration.name;
  integrationForm.provider_type = integration.provider_type;
  integrationForm.description = integration.description ?? "";
  integrationForm.enabled = integration.enabled;
  const settings = asRecord(integration.settings);
  integrationForm.settings_json = JSON.stringify(settings, null, 2);
  if (integration.provider_type === "webhook") {
    integrationForm.webhook_url = asString(settings.url, "");
    integrationForm.webhook_method = asString(settings.method, "POST").toUpperCase();
    integrationForm.webhook_timeout_seconds = asNumber(settings.timeout_seconds, 10);
    integrationForm.webhook_verify_tls = asBoolean(settings.verify_tls, true);
    integrationForm.webhook_max_body_bytes = asNumber(settings.max_body_bytes, 262_144);
    integrationForm.webhook_headers_json = JSON.stringify(asRecord(settings.headers), null, 2);
  } else if (integration.provider_type === "pushover") {
    integrationForm.pushover_app_token = asString(settings.app_token, "");
    integrationForm.pushover_user_key = asString(settings.user_key, "");
    integrationForm.pushover_device = asString(settings.device, "");
    integrationForm.pushover_priority = asNumber(settings.priority, 0);
    integrationForm.pushover_sound = asString(settings.sound, "");
  } else if (integration.provider_type === "apprise") {
    integrationForm.apprise_api_url = asString(settings.api_url, "");
    const appriseUrls = settings.urls;
    if (Array.isArray(appriseUrls)) {
      integrationForm.apprise_urls = appriseUrls
        .map((entry) => asString(entry, ""))
        .filter((entry) => entry.length > 0)
        .join("\n");
    } else {
      integrationForm.apprise_urls = "";
    }
    integrationForm.apprise_tag = asString(settings.tag, "");
    integrationForm.apprise_notify_type = asString(settings.notify_type, "info");
    integrationForm.apprise_format = asString(settings.format, "");
    integrationForm.apprise_timeout_seconds = asNumber(settings.timeout_seconds, 15);
    integrationForm.apprise_verify_tls = asBoolean(settings.verify_tls, true);
    integrationForm.apprise_headers_json = JSON.stringify(asRecord(settings.headers), null, 2);
  }
  showIntegrationModal.value = true;
}
function closeIntegrationModal(): void {
  showIntegrationModal.value = false;
  integrationEditId.value = null;
}
function openCreateActionTemplateModal(): void {
  resetActionTemplateForm();
  actionTemplateModalMode.value = "create";
  actionTemplateEditId.value = null;
  showActionTemplateModal.value = true;
}
function openEditActionTemplateModal(template: AlertActionTemplateResponse): void {
  resetActionTemplateForm();
  actionTemplateModalMode.value = "edit";
  actionTemplateEditId.value = template.id;
  actionTemplateForm.name = template.name;
  actionTemplateForm.provider_type = template.provider_type ?? "";
  actionTemplateForm.description = template.description ?? "";
  actionTemplateForm.title_template = template.title_template ?? "";
  actionTemplateForm.body_template = template.body_template ?? "";
  actionTemplateForm.payload_template_json = template.payload_template
    ? JSON.stringify(template.payload_template, null, 2)
    : "";
  actionTemplateForm.default_event_types = [...template.default_event_types];
  actionTemplateForm.enabled = template.enabled;
  showActionTemplateModal.value = true;
}
function closeActionTemplateModal(): void {
  showActionTemplateModal.value = false;
  actionTemplateEditId.value = null;
}
function openCreateBindingModal(): void {
  resetBindingForm();
  bindingModalMode.value = "create";
  bindingEditId.value = null;
  showBindingModal.value = true;
}
function openEditBindingModal(binding: AlertPolicyActionBindingResponse): void {
  resetBindingForm();
  bindingModalMode.value = "edit";
  bindingEditId.value = binding.id;
  bindingForm.policy_template_id = binding.policy_template_id;
  bindingForm.integration_id = binding.integration_id;
  bindingForm.action_template_id = binding.action_template_id;
  bindingForm.event_types = [...binding.event_types];
  bindingForm.min_severity = binding.min_severity ?? "";
  bindingForm.enabled = binding.enabled;
  bindingForm.sort_order = binding.sort_order;
  bindingForm.cooldown_seconds = binding.cooldown_seconds;
  showBindingModal.value = true;
}
function closeBindingModal(): void {
  showBindingModal.value = false;
  bindingEditId.value = null;
}
function closeActionTemplatePreviewModal(): void {
  showActionTemplatePreviewModal.value = false;
  actionTemplatePreviewResult.value = null;
  actionTemplatePreviewName.value = "";
}

async function submitCreateGroupModal(): Promise<void> {
  const created = await createGroupEntry();
  if (created) {
    closeCreateGroupModal();
  }
}

async function submitCreateTemplateModal(): Promise<void> {
  const created = await createTemplateEntry();
  if (created) {
    closeCreateTemplateModal();
  }
}

async function submitCreateAssignmentModal(): Promise<void> {
  if (assignmentWizardStep.value < 4) {
    nextAssignmentWizardStep();
    return;
  }
  const created = await createAssignmentEntry();
  if (created) {
    closeCreateAssignmentModal();
  }
}
async function submitIntegrationModal(): Promise<void> {
  if (!appState.token || !integrationForm.name.trim()) {
    return;
  }
  actionLoading.value = true;
  try {
    let settings: Record<string, unknown> = {};
    if (integrationForm.provider_type === "webhook") {
      const webhookHeaders =
        parseJsonObject(integrationForm.webhook_headers_json, "Webhook headers", {
          allowEmpty: true,
        }) ?? {};
      settings = {
        url: integrationForm.webhook_url.trim(),
        method: integrationForm.webhook_method,
        headers: webhookHeaders,
        timeout_seconds: integrationForm.webhook_timeout_seconds,
        verify_tls: integrationForm.webhook_verify_tls,
        max_body_bytes: integrationForm.webhook_max_body_bytes,
      };
    } else if (integrationForm.provider_type === "pushover") {
      settings = {
        app_token: integrationForm.pushover_app_token.trim(),
        user_key: integrationForm.pushover_user_key.trim(),
        device: integrationForm.pushover_device.trim() || null,
        priority: integrationForm.pushover_priority,
        sound: integrationForm.pushover_sound.trim() || null,
      };
    } else if (integrationForm.provider_type === "apprise") {
      const appriseHeaders =
        parseJsonObject(integrationForm.apprise_headers_json, "Apprise headers", {
          allowEmpty: true,
        }) ?? {};
      const appriseUrls = integrationForm.apprise_urls
        .split(/[\n,]+/g)
        .map((entry) => entry.trim())
        .filter((entry) => entry.length > 0);
      settings = {
        api_url: integrationForm.apprise_api_url.trim(),
        urls: appriseUrls,
        tag: integrationForm.apprise_tag.trim() || null,
        notify_type: integrationForm.apprise_notify_type,
        format: integrationForm.apprise_format.trim() || null,
        timeout_seconds: integrationForm.apprise_timeout_seconds,
        verify_tls: integrationForm.apprise_verify_tls,
        headers: appriseHeaders,
      };
    } else {
      settings = parseJsonObject(integrationForm.settings_json, "Settings", {
        allowEmpty: true,
      }) ?? {};
    }

    const parsedSecrets = parseJsonObject(integrationForm.secrets_json, "Secrets", {
      allowEmpty: true,
    });
    if (integrationModalMode.value === "create") {
      await createAlertActionIntegration(appState.token, {
        name: integrationForm.name.trim(),
        provider_type: integrationForm.provider_type,
        description: integrationForm.description.trim() || undefined,
        enabled: integrationForm.enabled,
        settings,
        secrets: parsedSecrets ?? undefined,
      });
      appState.toastSuccess = "Action integration created.";
    } else if (integrationEditId.value) {
      const payload: Record<string, unknown> = {
        name: integrationForm.name.trim(),
        description: integrationForm.description.trim() || null,
        enabled: integrationForm.enabled,
        settings,
      };
      if (integrationForm.clear_secrets) {
        payload.secrets = {};
      } else if (parsedSecrets) {
        payload.secrets = parsedSecrets;
      }
      await updateAlertActionIntegration(
        appState.token,
        integrationEditId.value,
        payload as {
          name?: string;
          description?: string | null;
          enabled?: boolean;
          settings?: Record<string, unknown>;
          secrets?: Record<string, unknown>;
        },
      );
      appState.toastSuccess = "Action integration updated.";
    }
    await loadAll();
    closeIntegrationModal();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to save integration.";
  } finally {
    actionLoading.value = false;
  }
}
async function runIntegrationTestAction(integration: AlertActionIntegrationResponse): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    const result = await testAlertActionIntegration(appState.token, integration.id, {
      event_type: "alert_activated",
      payload: {
        source: "ui_test",
        integration_id: integration.id,
      },
      rendered_payload: {
        title: "pyMC_Glass Action Test",
        body: "Integration test send from Alert Policies Actions section.",
      },
    });
    if (result.status === "sent") {
      appState.toastSuccess = `Integration test sent via ${integration.name}.`;
    } else {
      appState.toastError = result.error || "Integration test failed.";
    }
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to test integration.";
  } finally {
    actionLoading.value = false;
  }
}
async function openActionTemplatePreviewModal(template: AlertActionTemplateResponse): Promise<void> {
  if (!appState.token) {
    return;
  }
  showActionTemplatePreviewModal.value = true;
  actionTemplatePreviewLoading.value = true;
  actionTemplatePreviewName.value = template.name;
  try {
    actionTemplatePreviewResult.value = await previewAlertActionTemplate(appState.token, {
      action_template_id: template.id,
      event_type: "alert_activated",
    });
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to preview action template.";
    actionTemplatePreviewResult.value = null;
  } finally {
    actionTemplatePreviewLoading.value = false;
  }
}
function prettyJson(value: unknown): string {
  if (value === null || value === undefined) {
    return "—";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}
async function submitActionTemplateModal(): Promise<void> {
  if (!appState.token || !actionTemplateForm.name.trim()) {
    return;
  }
  actionLoading.value = true;
  try {
    const parsedPayloadTemplate = parseJsonObject(
      actionTemplateForm.payload_template_json,
      "Payload template",
      { allowEmpty: true },
    );
    if (actionTemplateModalMode.value === "create") {
      await createAlertActionTemplate(appState.token, {
        name: actionTemplateForm.name.trim(),
        provider_type: actionTemplateForm.provider_type.trim() || null,
        description: actionTemplateForm.description.trim() || undefined,
        title_template: actionTemplateForm.title_template.trim() || null,
        body_template: actionTemplateForm.body_template.trim() || null,
        payload_template: parsedPayloadTemplate,
        default_event_types: [...actionTemplateForm.default_event_types],
        enabled: actionTemplateForm.enabled,
      });
      appState.toastSuccess = "Action template created.";
    } else if (actionTemplateEditId.value) {
      await updateAlertActionTemplate(appState.token, actionTemplateEditId.value, {
        name: actionTemplateForm.name.trim(),
        provider_type: actionTemplateForm.provider_type.trim() || null,
        description: actionTemplateForm.description.trim() || null,
        title_template: actionTemplateForm.title_template.trim() || null,
        body_template: actionTemplateForm.body_template.trim() || null,
        payload_template: parsedPayloadTemplate,
        default_event_types: [...actionTemplateForm.default_event_types],
        enabled: actionTemplateForm.enabled,
      });
      appState.toastSuccess = "Action template updated.";
    }
    await loadAll();
    closeActionTemplateModal();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to save action template.";
  } finally {
    actionLoading.value = false;
  }
}
async function submitBindingModal(): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    if (bindingModalMode.value === "create") {
      if (
        !bindingForm.policy_template_id ||
        !bindingForm.integration_id ||
        !bindingForm.action_template_id
      ) {
        appState.toastError = "Policy template, integration, and action template are required.";
        return;
      }
      await createAlertPolicyActionBinding(appState.token, {
        policy_template_id: bindingForm.policy_template_id,
        integration_id: bindingForm.integration_id,
        action_template_id: bindingForm.action_template_id,
        event_types: [...bindingForm.event_types],
        min_severity: bindingForm.min_severity || null,
        enabled: bindingForm.enabled,
        sort_order: bindingForm.sort_order,
        cooldown_seconds: bindingForm.cooldown_seconds,
      });
      appState.toastSuccess = "Policy action binding created.";
    } else if (bindingEditId.value) {
      await updateAlertPolicyActionBinding(appState.token, bindingEditId.value, {
        event_types: [...bindingForm.event_types],
        min_severity: bindingForm.min_severity || null,
        enabled: bindingForm.enabled,
        sort_order: bindingForm.sort_order,
        cooldown_seconds: bindingForm.cooldown_seconds,
      });
      appState.toastSuccess = "Policy action binding updated.";
    }
    await loadAll();
    closeBindingModal();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to save policy action binding.";
  } finally {
    actionLoading.value = false;
  }
}

function nextAssignmentWizardStep(): void {
  if (!canProceedAssignmentWizardStep.value) {
    return;
  }
  assignmentWizardStep.value = Math.min(4, assignmentWizardStep.value + 1);
}

function previousAssignmentWizardStep(): void {
  assignmentWizardStep.value = Math.max(1, assignmentWizardStep.value - 1);
}

async function loadAll(): Promise<void> {
  if (!appState.token) {
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    const [
      groupRows,
      templateRows,
      assignmentRows,
      providerRows,
      integrationRows,
      actionTemplateRows,
      bindingRows,
      deliverySummary,
      deliveryRows,
    ] = await Promise.all([
      listNodeGroups(appState.token),
      listAlertPolicyTemplates(appState.token),
      listAlertPolicyAssignments(appState.token),
      listAlertActionProviders(appState.token),
      listAlertActionIntegrations(appState.token),
      listAlertActionTemplates(appState.token),
      listAlertPolicyActionBindings(appState.token),
      getAlertActionDeliverySummary(appState.token),
      listAlertActionDeliveries(appState.token, { limit: 100, offset: 0 }),
    ]);
    groups.value = groupRows;
    templates.value = templateRows;
    assignments.value = assignmentRows;
    actionProviders.value = providerRows;
    actionIntegrations.value = integrationRows;
    actionTemplates.value = actionTemplateRows;
    actionBindings.value = bindingRows;
    actionDeliverySummary.value = deliverySummary;
    actionDeliveries.value = deliveryRows;
    if (selectedGroupId.value) {
      await selectGroup(selectedGroupId.value);
    }
  } catch (caught) {
    error.value = caught instanceof Error ? caught.message : "Failed to load alert policy data.";
  } finally {
    loading.value = false;
  }
}

async function createGroupEntry(): Promise<boolean> {
  if (!appState.token || !groupForm.name.trim()) {
    return false;
  }
  actionLoading.value = true;
  try {
    await createNodeGroup(appState.token, {
      name: groupForm.name.trim(),
      description: groupForm.description.trim() || undefined,
    });
    resetGroupForm();
    await loadAll();
    return true;
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to create node group.";
    return false;
  } finally {
    actionLoading.value = false;
  }
}

async function deleteGroupEntry(groupId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    await deleteNodeGroup(appState.token, groupId);
    if (selectedGroupId.value === groupId) {
      selectedGroupId.value = null;
      selectedGroup.value = null;
    }
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to delete node group.";
  } finally {
    actionLoading.value = false;
  }
}

async function selectGroup(groupId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  selectedGroupId.value = groupId;
  try {
    selectedGroup.value = await getNodeGroup(appState.token, groupId);
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to load group detail.";
  }
}

async function addSelectedMember(): Promise<void> {
  if (!appState.token || !selectedGroupId.value || !selectedMemberRepeaterId.value) {
    return;
  }
  actionLoading.value = true;
  try {
    selectedGroup.value = await addNodeGroupMember(appState.token, selectedGroupId.value, {
      repeater_id: selectedMemberRepeaterId.value,
    });
    selectedMemberRepeaterId.value = "";
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to add group member.";
  } finally {
    actionLoading.value = false;
  }
}

async function removeSelectedMember(repeaterId: string): Promise<void> {
  if (!appState.token || !selectedGroupId.value) {
    return;
  }
  actionLoading.value = true;
  try {
    selectedGroup.value = await removeNodeGroupMember(appState.token, selectedGroupId.value, repeaterId);
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to remove group member.";
  } finally {
    actionLoading.value = false;
  }
}

async function createTemplateEntry(): Promise<boolean> {
  if (!appState.token || !templateForm.name.trim()) {
    return false;
  }
  actionLoading.value = true;
  try {
    await createAlertPolicyTemplate(appState.token, {
      name: templateForm.name.trim(),
      rule_type: templateForm.rule_type,
      severity: templateForm.severity,
      enabled: templateForm.enabled,
      auto_resolve: templateForm.auto_resolve,
      threshold_value: selectedRuleTypeMeta.value?.usesThreshold
        ? templateForm.threshold_value ?? undefined
        : undefined,
      window_minutes: selectedRuleTypeMeta.value?.usesWindow
        ? templateForm.window_minutes ?? undefined
        : undefined,
      offline_grace_seconds: selectedRuleTypeMeta.value?.usesOfflineGrace
        ? templateForm.offline_grace_seconds ?? undefined
        : undefined,
      config: {},
    });
    resetTemplateForm();
    await loadAll();
    return true;
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to create policy template.";
    return false;
  } finally {
    actionLoading.value = false;
  }
}

async function deleteTemplateEntry(templateId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    await deleteAlertPolicyTemplate(appState.token, templateId);
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to delete policy template.";
  } finally {
    actionLoading.value = false;
  }
}

async function createAssignmentEntry(): Promise<boolean> {
  if (!appState.token || !assignmentForm.template_id) {
    return false;
  }
  actionLoading.value = true;
  try {
    await createAlertPolicyAssignment(appState.token, {
      template_id: assignmentForm.template_id,
      scope_type: assignmentForm.scope_type,
      scope_id: assignmentForm.scope_type === "global" ? undefined : assignmentForm.scope_id || undefined,
      priority: assignmentForm.priority,
      enabled: assignmentForm.enabled,
    });
    resetAssignmentForm();
    await loadAll();
    return true;
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to create policy assignment.";
    return false;
  } finally {
    actionLoading.value = false;
  }
}

async function deleteAssignmentEntry(assignmentId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    await deleteAlertPolicyAssignment(appState.token, assignmentId);
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to delete policy assignment.";
  } finally {
    actionLoading.value = false;
  }
}
async function deleteIntegrationEntry(integrationId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    await deleteAlertActionIntegration(appState.token, integrationId);
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to delete action integration.";
  } finally {
    actionLoading.value = false;
  }
}
async function deleteActionTemplateEntry(templateId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    await deleteAlertActionTemplate(appState.token, templateId);
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to delete action template.";
  } finally {
    actionLoading.value = false;
  }
}
async function deleteBindingEntry(bindingId: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    await deleteAlertPolicyActionBinding(appState.token, bindingId);
    await loadAll();
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to delete policy action binding.";
  } finally {
    actionLoading.value = false;
  }
}

async function inspectEffectivePolicies(): Promise<void> {
  if (!appState.token || !selectedRepeaterId.value) {
    return;
  }
  loading.value = true;
  try {
    const response = await getEffectiveAlertPolicies(appState.token, selectedRepeaterId.value);
    effectivePolicies.value = response.policies;
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to load effective policies.";
  } finally {
    loading.value = false;
  }
}

async function runEvaluation(repeaterId?: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    evaluationResult.value = await evaluateAlertPolicies(appState.token, {
      repeater_id: repeaterId || undefined,
    });
    if (repeaterId) {
      await inspectEffectivePolicies();
    }
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to run policy evaluation.";
  } finally {
    actionLoading.value = false;
  }
}

async function bootstrapDefaults(): Promise<void> {
  if (!appState.token) {
    return;
  }
  actionLoading.value = true;
  try {
    await bootstrapDefaultAlertPolicies(appState.token);
    await loadAll();
    appState.toastSuccess = "Default alert policy templates ensured.";
  } catch (caught) {
    appState.toastError = caught instanceof Error ? caught.message : "Failed to bootstrap defaults.";
  } finally {
    actionLoading.value = false;
  }
}


function requestDeleteGroup(groupId: string, groupName: string): void {
  deleteConfirmAction.value = { type: "group", id: groupId };
  deleteConfirmTitle.value = "Delete node group?";
  deleteConfirmMessage.value = `Delete “${groupName}” and its member mappings? This cannot be undone.`;
  showDeleteConfirmModal.value = true;
}

function requestDeleteTemplate(templateId: string, templateName: string): void {
  deleteConfirmAction.value = { type: "template", id: templateId };
  deleteConfirmTitle.value = "Delete policy template?";
  deleteConfirmMessage.value = `Delete “${templateName}”? Assignments depending on it may stop applying as expected.`;
  showDeleteConfirmModal.value = true;
}

function requestDeleteAssignment(assignmentId: string, templateName: string): void {
  deleteConfirmAction.value = { type: "assignment", id: assignmentId };
  deleteConfirmTitle.value = "Delete scope assignment?";
  deleteConfirmMessage.value = `Remove assignment for template “${templateName}”?`;
  showDeleteConfirmModal.value = true;
}
function requestDeleteIntegration(integrationId: string, integrationNameValue: string): void {
  deleteConfirmAction.value = { type: "integration", id: integrationId };
  deleteConfirmTitle.value = "Delete action integration?";
  deleteConfirmMessage.value = `Delete integration “${integrationNameValue}”? Existing bindings using it will break.`;
  showDeleteConfirmModal.value = true;
}
function requestDeleteActionTemplate(templateId: string, templateName: string): void {
  deleteConfirmAction.value = { type: "action_template", id: templateId };
  deleteConfirmTitle.value = "Delete action template?";
  deleteConfirmMessage.value = `Delete action template “${templateName}”? Existing bindings using it will break.`;
  showDeleteConfirmModal.value = true;
}
function requestDeleteBinding(bindingId: string): void {
  deleteConfirmAction.value = { type: "action_binding", id: bindingId };
  deleteConfirmTitle.value = "Delete policy action binding?";
  deleteConfirmMessage.value = "Delete this binding? The linked policy template will stop dispatching this action route.";
  showDeleteConfirmModal.value = true;
}

async function confirmDelete(): Promise<void> {
  if (!deleteConfirmAction.value) {
    return;
  }
  const currentAction = deleteConfirmAction.value;
  closeDeleteConfirmModal();
  if (currentAction.type === "group") {
    await deleteGroupEntry(currentAction.id);
    return;
  }
  if (currentAction.type === "template") {
    await deleteTemplateEntry(currentAction.id);
    return;
  }
  if (currentAction.type === "assignment") {
    await deleteAssignmentEntry(currentAction.id);
    return;
  }
  if (currentAction.type === "integration") {
    await deleteIntegrationEntry(currentAction.id);
    return;
  }
  if (currentAction.type === "action_template") {
    await deleteActionTemplateEntry(currentAction.id);
    return;
  }
  await deleteBindingEntry(currentAction.id);
}

function closeDeleteConfirmModal(): void {
  showDeleteConfirmModal.value = false;
  deleteConfirmAction.value = null;
}
function formatTemplateThreshold(template: AlertPolicyTemplateResponse): string {
  if (template.rule_type === "offline_repeater" || template.rule_type === "tls_telemetry_stale") {
    return `${template.offline_grace_seconds ?? "—"}s`;
  }
  if (template.rule_type === "new_zero_hop_node_detected") {
    return `${template.window_minutes ?? "—"}m discovery window`;
  }
  if (template.rule_type === "high_temperature_c") {
    return `${template.threshold_value ?? "—"} °C`;
  }
  if (template.rule_type === "high_drop_rate") {
    const percent = template.threshold_value != null ? `${(template.threshold_value * 100).toFixed(2)}%` : "—";
    return `${percent} / ${template.window_minutes ?? "—"}m`;
  }
  const unit = template.rule_type === "high_noise_floor" ? "dBm" : "%";
  return `${template.threshold_value ?? "—"} ${unit} / ${template.window_minutes ?? "—"}m`;
}

function formatEffectiveThreshold(policy: EffectivePolicyItemResponse): string {
  if (policy.rule_type === "offline_repeater" || policy.rule_type === "tls_telemetry_stale") {
    return `${policy.offline_grace_seconds ?? "—"}s`;
  }
  if (policy.rule_type === "new_zero_hop_node_detected") {
    return `${policy.window_minutes ?? "—"}m discovery window`;
  }
  if (policy.rule_type === "high_temperature_c") {
    return `${policy.threshold_value ?? "—"} °C`;
  }
  if (policy.rule_type === "high_drop_rate") {
    const percent = policy.threshold_value != null ? `${(policy.threshold_value * 100).toFixed(2)}%` : "—";
    return `${percent} / ${policy.window_minutes ?? "—"}m`;
  }
  const unit = policy.rule_type === "high_noise_floor" ? "dBm" : "%";
  return `${policy.threshold_value ?? "—"} ${unit} / ${policy.window_minutes ?? "—"}m`;
}
</script>

<style scoped>
.header-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.error-text {
  color: #fb787b;
  font-size: 0.88rem;
}

.alert-policy-main {
  min-width: 0;
  display: grid;
  gap: 0.9rem;
}

.actions-toolbar {
  display: grid;
  gap: 0.65rem;
  margin-bottom: 0.75rem;
}

.provider-capabilities {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
}

.provider-chip {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border-radius: 999px;
  border: 1px solid rgba(108, 150, 216, 0.45);
  background: rgba(27, 48, 86, 0.35);
  color: #d9eaff;
  padding: 0.22rem 0.58rem;
  font-size: 0.72rem;
}

.provider-chip-detail {
  color: #abc2e4;
}

.action-block {
  display: grid;
  gap: 0.7rem;
  margin-bottom: 0.9rem;
}

.action-block:last-child {
  margin-bottom: 0;
}

.action-block-header {
  display: flex;
  justify-content: space-between;
  align-items: end;
  gap: 0.8rem;
}

.event-options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.35rem 0.75rem;
}

.member-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  align-items: end;
}

.member-row .field-label {
  min-width: 220px;
}

.group-name-cell {
  display: inline-flex;
  align-items: center;
  gap: 0.45rem;
}

.manage-members-chip {
  display: inline-flex;
  border-radius: 999px;
  padding: 0.08rem 0.42rem;
  font-size: 0.68rem;
  border: 1px solid rgba(118, 167, 236, 0.42);
  background: rgba(43, 77, 130, 0.3);
  color: #d6ebff;
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
.modal-card-scroll {
  max-height: 82vh;
  overflow-y: auto;
}

.modal-card-lg {
  width: min(100%, 860px);
  max-height: 82vh;
  overflow-y: auto;
}

.wizard-steps {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0.45rem;
}

.wizard-step {
  border: 1px solid rgba(131, 157, 194, 0.28);
  background: rgba(13, 24, 43, 0.48);
  color: #9db4d7;
  border-radius: 999px;
  font-size: 0.72rem;
  padding: 0.28rem 0.5rem;
  text-align: center;
}

.wizard-step.active {
  border-color: rgba(118, 180, 255, 0.7);
  background: rgba(61, 107, 188, 0.38);
  color: #eef7ff;
}

.review-grid {
  display: grid;
  gap: 0.45rem;
}

.scope-cell {
  display: grid;
  gap: 0.18rem;
}

.scope-pill {
  display: inline-flex;
  width: fit-content;
  font-size: 0.68rem;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 600;
  border-radius: 999px;
  padding: 0.16rem 0.56rem;
  border: 1px solid rgba(121, 162, 224, 0.42);
  background: rgba(43, 75, 126, 0.35);
  color: #d4e8ff;
}
.scope-global {
  border-color: rgba(96, 191, 205, 0.62);
  background: rgba(42, 121, 134, 0.35);
  color: #d8fbff;
}

.scope-group {
  border-color: rgba(123, 156, 236, 0.62);
  background: rgba(58, 82, 164, 0.34);
  color: #e0e9ff;
}

.scope-node {
  border-color: rgba(176, 142, 237, 0.62);
  background: rgba(90, 59, 151, 0.34);
  color: #f0e3ff;
}

.severity-pill {
  display: inline-flex;
  width: fit-content;
  font-size: 0.72rem;
  border-radius: 999px;
  padding: 0.14rem 0.5rem;
  border: 1px solid transparent;
}

.severity-critical {
  background: rgba(170, 56, 76, 0.24);
  border-color: rgba(209, 98, 119, 0.55);
  color: #ffd9e1;
}

.severity-warning {
  background: rgba(157, 113, 26, 0.24);
  border-color: rgba(214, 159, 70, 0.55);
  color: #ffebb9;
}

.severity-info {
  background: rgba(39, 91, 142, 0.24);
  border-color: rgba(89, 146, 205, 0.55);
  color: #d8eeff;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 1rem;
}
.assignment-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.65rem;
  align-items: end;
  margin-bottom: 0.75rem;
}

.assignment-filter-label {
  display: grid;
  gap: 0.28rem;
  font-size: 0.78rem;
  color: #b8cae7;
}

.assignment-filter-select {
  min-width: 180px;
}

.assignment-filter-search {
  flex: 1 1 280px;
}

.assignment-filter-input {
  min-width: 220px;
}

.preview-grid {
  display: grid;
  gap: 0.75rem;
}

.json-preview {
  margin: 0;
  max-height: 220px;
  overflow: auto;
  padding: 0.65rem;
  border-radius: 0.65rem;
  border: 1px solid rgba(122, 162, 221, 0.35);
  background: rgba(8, 16, 30, 0.75);
  font-size: 0.76rem;
  line-height: 1.35;
  white-space: pre-wrap;
  word-break: break-word;
}

.merge-fields-preview {
  max-height: 180px;
  white-space: pre-line;
}

.modal-actions {
  display: flex;
  justify-content: end;
  gap: 0.6rem;
}
</style>
