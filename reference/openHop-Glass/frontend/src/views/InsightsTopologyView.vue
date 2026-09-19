<template>
  <section class="page-grid insights-page">
    <header class="page-header">
      <div>
        <h1 class="section-title">Topology Insights</h1>
        <p class="section-subtitle">
          Live neighbor reachability on a real map with observer, route, and node trend drill-down.
        </p>
      </div>
      <div class="header-actions">
        <span class="live-pill" :class="livePillClass">
          {{ liveStatusLabel }}
        </span>
        <button class="btn btn-secondary" :disabled="loading" @click="loadObservations()">
          {{ loading ? "Refreshing..." : "Refresh" }}
        </button>
      </div>
    </header>

    <p v-if="error" class="error-text">{{ error }}</p>

    <section class="grid-3 summary-stats">
      <UiStatCard
        title="Observations"
        :value="topologySummary?.total_observations ?? observationsResponse?.total ?? 0"
      />
      <UiStatCard
        title="Unique Nodes"
        :value="topologySummary?.unique_nodes ?? observationsResponse?.unique_observed_nodes ?? 0"
      />
      <UiStatCard
        title="Observers"
        :value="topologySummary?.unique_observers ?? observationsResponse?.unique_observers ?? 0"
      />
      <UiStatCard
        title="Mapped Nodes"
        :value="mapNodes.length"
        :subtitle="`Edges: ${edgeResponse?.total ?? 0}`"
      />
      <UiStatCard title="Zero-hop" :value="topologySummary?.zero_hop_observations ?? 0" />
      <UiStatCard title="Multi-hop" :value="topologySummary?.multi_hop_observations ?? 0" />
      <UiStatCard title="Stale nodes" :value="topologySummary?.stale_nodes ?? 0" />
      <UiStatCard
        title="Topology advert lag"
        :value="formatLag(topologyAdvertLagSeconds)"
        :subtitle="
          topologySummary?.top_observer_node_name
            ? `Top observer: ${topologySummary.top_observer_node_name} (${topologySummary.top_observer_count ?? 0})`
            : undefined
        "
      />
      <UiStatCard title="MQTT overall lag" :value="formatLag(mqttOverallLagSeconds)" />
      <UiStatCard title="MQTT packet lag" :value="formatLag(mqttPacketLagSeconds)" />
      <UiStatCard title="MQTT event lag" :value="formatLag(mqttEventLagSeconds)" />
    </section>
    <p v-if="isTopologyAdvertStale" class="warning-text">
      Topology advert data appears stale (lag {{ formatLag(topologyAdvertLagSeconds) }}).
    </p>
    <p
      v-if="isTopologyAdvertStale && mqttOverallLagSeconds !== null && !isMqttOverallStale"
      class="section-subtitle"
    >
      MQTT ingest is active (overall lag {{ formatLag(mqttOverallLagSeconds) }}), so this stale signal is advert-specific.
    </p>

    <UiPanelCard title="Filters" subtitle="Refine neighbor observations before map/table analysis.">
      <div class="filter-grid">
        <label class="field-label">
          Time range
          <select v-model.number="selectedHours" class="field-select">
            <option v-for="option in timeOptions" :key="option.value" :value="option.value">
              {{ option.label }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Observer
          <select v-model="observerFilter" class="field-select">
            <option value="all">All observers</option>
            <option v-for="observer in observerOptions" :key="observer" :value="observer">
              {{ observer }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Contact type
          <select v-model="contactTypeFilter" class="field-select">
            <option value="all">All contact types</option>
            <option v-for="contactType in contactTypeOptions" :key="contactType" :value="contactType">
              {{ contactType }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Route type
          <select v-model="routeTypeFilter" class="field-select">
            <option value="all">All routes</option>
            <option v-for="route in routeTypeOptions" :key="route.value" :value="route.value">
              {{ route.label }}
            </option>
          </select>
        </label>
        <label class="field-label">
          Zero hop
          <select v-model="zeroHopFilter" class="field-select">
            <option value="all">All</option>
            <option value="true">True</option>
            <option value="false">False</option>
          </select>
        </label>
        <label class="field-label">
          Search
          <input
            v-model.trim="searchFilter"
            class="field"
            placeholder="pubkey, node name, observer..."
            type="text"
          />
        </label>
        <label class="field-label field-checkbox">
          <span>Heatmap layer</span>
          <input v-model="showHeatmap" type="checkbox" />
        </label>
        <label class="field-label field-checkbox">
          <span>Live auto-refresh</span>
          <input v-model="liveAutoRefresh" type="checkbox" />
        </label>
      </div>
    </UiPanelCard>

    <UiPanelCard title="Neighbor Topology Map" subtitle="Interactive map; click any node marker for details.">
      <div class="map-shell">
        <div ref="mapContainer" class="real-map" />
        <div v-if="mapNodes.length === 0" class="map-empty">
          No nodes with valid coordinates in the current filter set.
        </div>
      </div>
    </UiPanelCard>

    <UiPanelCard
      title="Observer-to-Neighbor Table"
      :subtitle="`Showing ${pagedRangeStart}-${pagedRangeEnd} of ${observations.length} observer-node relationships.`"
    >
      <UiDataTable>
        <thead>
          <tr>
            <th>Node</th>
            <th>Observer</th>
            <th>Contact</th>
            <th>Route</th>
            <th>Zero-hop</th>
            <th>Last seen</th>
            <th>RSSI</th>
            <th>SNR</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="item in pagedObservations"
            :key="`${item.observer_repeater_id}-${item.pubkey}`"
            class="row-click"
            :class="{ selected: item.pubkey === selectedPubkey }"
            @click="openNodeDetail(item.pubkey)"
          >
            <td>
              <div class="node-cell">
                <strong>{{ item.node_name || shortPubkey(item.pubkey) }}</strong>
                <code>{{ shortPubkey(item.pubkey) }}</code>
              </div>
            </td>
            <td>{{ item.observer_node_name }}</td>
            <td>{{ item.contact_type || "Unknown" }}</td>
            <td>{{ formatRouteType(item.route_type) }}</td>
            <td>
              <span class="pill" :class="item.zero_hop ? 'pill-green' : 'pill-gray'">
                {{ item.zero_hop ? "true" : "false" }}
              </span>
            </td>
            <td>{{ formatTimestamp(item.last_seen) }}</td>
            <td>{{ formatSignal(item.rssi, "dBm") }}</td>
            <td>{{ formatSignal(item.snr, "dB") }}</td>
          </tr>
          <tr v-if="!loading && observations.length === 0">
            <td colspan="8" class="section-subtitle">No observations match current filters.</td>
          </tr>
          <tr v-if="loading">
            <td colspan="8" class="section-subtitle">Loading observations...</td>
          </tr>
        </tbody>
      </UiDataTable>
      <div class="table-pagination">
        <label class="field-label pagination-size">
          Rows
          <select v-model.number="tablePageSize" class="field-select">
            <option v-for="size in tablePageSizeOptions" :key="size" :value="size">{{ size }}</option>
          </select>
        </label>
        <div class="pagination-actions">
          <button class="btn btn-ghost btn-sm" :disabled="tablePage <= 1" @click="goToPreviousTablePage()">
            Previous
          </button>
          <span class="pagination-status">Page {{ tablePage }} / {{ tableTotalPages }}</span>
          <button
            class="btn btn-ghost btn-sm"
            :disabled="tablePage >= tableTotalPages"
            @click="goToNextTablePage()"
          >
            Next
          </button>
        </div>
      </div>
    </UiPanelCard>

    <UiPanelCard title="Route Pattern Analysis" subtitle="Aggregate route mix and observer behavior over current filters.">
      <div class="route-pattern-grid">
        <article class="route-pattern-card">
          <h3>Route distribution</h3>
          <ul>
            <li v-for="item in routePatternList" :key="item.key">
              <span>{{ item.label }}</span>
              <strong>{{ item.count }}</strong>
              <div class="route-bar">
                <div class="route-bar-fill" :style="{ width: `${item.percent}%` }" />
              </div>
            </li>
          </ul>
        </article>
        <article class="route-pattern-card">
          <h3>Zero-hop ratio</h3>
          <p class="ratio-value">{{ zeroHopRatioLabel }}</p>
          <p class="section-subtitle">
            {{ zeroHopObservations }} of {{ observations.length }} links are zero-hop in this window.
          </p>
          <h3>Contact types</h3>
          <ul>
            <li v-for="item in contactTypePatternList" :key="item.key">
              <span>{{ item.label }}</span>
              <strong>{{ item.count }}</strong>
            </li>
          </ul>
        </article>
      </div>
    </UiPanelCard>

    <UiPanelCard
      title="Packet-derived Topology Quality"
      subtitle="Packet transport quality: route/type mix, relay share, and signal trends."
    >
      <p v-if="!packetQuality" class="section-subtitle">
        Packet-quality analytics are unavailable for the current window.
      </p>
      <template v-else>
        <section class="grid-3">
          <UiStatCard title="Packets analyzed" :value="packetQuality.total_packets" />
          <UiStatCard title="Avg RSSI" :value="formatSignal(packetQuality.avg_rssi, 'dBm')" />
          <UiStatCard title="Avg SNR" :value="formatSignal(packetQuality.avg_snr, 'dB')" />
        </section>
        <div class="route-pattern-grid">
          <article class="route-pattern-card">
            <h3>Packet route mix</h3>
            <ul>
              <li v-for="item in packetRouteMixList" :key="`packet-route-${item.key}`">
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
                <div class="route-bar">
                  <div class="route-bar-fill" :style="{ width: `${item.percent}%` }" />
                </div>
              </li>
            </ul>
          </article>
          <article class="route-pattern-card">
            <h3>Packet type mix</h3>
            <ul>
              <li v-for="item in packetTypeMixList" :key="`packet-type-${item.key}`">
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
                <div class="route-bar">
                  <div class="route-bar-fill" :style="{ width: `${item.percent}%` }" />
                </div>
              </li>
            </ul>
          </article>
          <article class="route-pattern-card">
            <h3>Repeater traffic share</h3>
            <ul>
              <li v-for="item in pagedPacketRepeaterShareRows" :key="item.repeater_id">
                <span>{{ item.repeater_node_name }}</span>
                <strong>{{ item.packet_count }} ({{ item.share_percent.toFixed(1) }}%)</strong>
              </li>
              <li v-if="pagedPacketRepeaterShareRows.length === 0" class="section-subtitle">
                No repeater share rows in this range.
              </li>
            </ul>
            <div class="table-pagination">
              <span class="pagination-status">
                Page {{ packetRepeaterSharePage }} / {{ packetRepeaterShareTotalPages }}
              </span>
              <div class="pagination-actions">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="packetRepeaterSharePage <= 1"
                  @click="packetRepeaterSharePage -= 1"
                >
                  Previous
                </button>
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="packetRepeaterSharePage >= packetRepeaterShareTotalPages"
                  @click="packetRepeaterSharePage += 1"
                >
                  Next
                </button>
              </div>
            </div>
          </article>
        </div>
        <UiDataTable>
          <thead>
            <tr>
              <th>Bucket start</th>
              <th>Packets</th>
              <th>Avg RSSI</th>
              <th>Avg SNR</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="point in pagedPacketSignalTrendRows" :key="point.bucket_start">
              <td>{{ formatTimestamp(point.bucket_start) }}</td>
              <td>{{ point.packet_count }}</td>
              <td>{{ formatSignal(point.avg_rssi, "dBm") }}</td>
              <td>{{ formatSignal(point.avg_snr, "dB") }}</td>
            </tr>
            <tr v-if="pagedPacketSignalTrendRows.length === 0">
              <td colspan="4" class="section-subtitle">No packet trend points available.</td>
            </tr>
          </tbody>
        </UiDataTable>
        <div class="table-pagination">
          <span class="pagination-status">
            Signal trend page {{ packetSignalTrendPage }} / {{ packetSignalTrendTotalPages }}
          </span>
          <div class="pagination-actions">
            <button
              class="btn btn-ghost btn-sm"
              :disabled="packetSignalTrendPage <= 1"
              @click="packetSignalTrendPage -= 1"
            >
              Previous
            </button>
            <button
              class="btn btn-ghost btn-sm"
              :disabled="packetSignalTrendPage >= packetSignalTrendTotalPages"
              @click="packetSignalTrendPage += 1"
            >
              Next
            </button>
          </div>
        </div>
      </template>
    </UiPanelCard>

    <UiPanelCard
      title="Packet Structure Signals"
      subtitle="Best-effort path/subpath/neighbor graph extraction from packet payloads and raw bytes."
    >
      <p v-if="!packetStructure" class="section-subtitle">
        Packet-structure analytics are unavailable for the current window.
      </p>
      <template v-else>
        <section class="grid-3">
          <UiStatCard title="Packet events scanned" :value="packetStructure.total_packet_events" />
          <UiStatCard
            title="Decoded hop coverage"
            :value="`${packetStructure.decode_coverage_percent.toFixed(1)}%`"
            :subtitle="`${packetStructure.packets_with_decoded_hops} / ${packetStructure.analyzed_events}`"
          />
          <UiStatCard
            title="Graph entities"
            :value="packetGraphEdgeRows.length"
            :subtitle="`Nodes: ${packetGraphNodeRows.length}`"
          />
        </section>
        <div class="route-pattern-grid">
          <article class="route-pattern-card">
            <h3>Neighbor graph summary</h3>
            <p class="section-subtitle">
              Nodes: {{ packetGraphNodeRows.length }} · Edges: {{ packetGraphEdgeRows.length }}
            </p>
            <UiDataTable>
              <thead>
                <tr>
                  <th>Edge</th>
                  <th>Count</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="edge in pagedPacketGraphEdgeRows"
                  :key="`${edge.source_node_id}-${edge.target_node_id}`"
                >
                  <td>{{ edge.source_node_id }} → {{ edge.target_node_id }}</td>
                  <td>{{ edge.count }}</td>
                </tr>
                <tr v-if="pagedPacketGraphEdgeRows.length === 0">
                  <td colspan="2" class="section-subtitle">No decoded graph edges available.</td>
                </tr>
              </tbody>
            </UiDataTable>
            <div class="table-pagination">
              <span class="pagination-status">
                Edge page {{ packetGraphEdgePage }} / {{ packetGraphEdgeTotalPages }}
              </span>
              <div class="pagination-actions">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="packetGraphEdgePage <= 1"
                  @click="packetGraphEdgePage -= 1"
                >
                  Previous
                </button>
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="packetGraphEdgePage >= packetGraphEdgeTotalPages"
                  @click="packetGraphEdgePage += 1"
                >
                  Next
                </button>
              </div>
            </div>
          </article>
          <article class="route-pattern-card">
            <h3>Top subpaths</h3>
            <ul>
              <li v-for="item in pagedPacketSubpathRows" :key="item.hops.join('>')">
                <span>{{ item.hops.join(" → ") }}</span>
                <strong>{{ item.count }}</strong>
              </li>
              <li v-if="pagedPacketSubpathRows.length === 0" class="section-subtitle">
                No decoded subpaths available.
              </li>
            </ul>
            <div class="table-pagination">
              <span class="pagination-status">
                Subpath page {{ packetSubpathPage }} / {{ packetSubpathTotalPages }}
              </span>
              <div class="pagination-actions">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="packetSubpathPage <= 1"
                  @click="packetSubpathPage -= 1"
                >
                  Previous
                </button>
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="packetSubpathPage >= packetSubpathTotalPages"
                  @click="packetSubpathPage += 1"
                >
                  Next
                </button>
              </div>
            </div>
          </article>
          <article class="route-pattern-card">
            <h3>Channel detail mix</h3>
            <p class="section-subtitle">
              Packets with channel detail: {{ packetStructure.packets_with_channel_details }}
            </p>
            <ul>
              <li v-for="item in packetChannelMixList" :key="item.key">
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
              </li>
            </ul>
          </article>
        </div>
      </template>
    </UiPanelCard>

    <Teleport to="body">
      <div v-if="selectedPubkey" class="detail-dialog-backdrop" @click.self="closeDetailDrawer()">
        <section class="detail-dialog" role="dialog" aria-modal="true" aria-label="Node details">
          <header class="drawer-header">
        <div>
          <h2>Node Details</h2>
          <p class="section-subtitle">{{ selectedPubkey ? shortPubkey(selectedPubkey) : "No selection" }}</p>
        </div>
        <button class="btn btn-ghost btn-sm" @click="closeDetailDrawer()">Close</button>
          </header>
          <div class="drawer-body">
        <p v-if="detailLoading" class="section-subtitle">Loading node detail...</p>
        <p v-else-if="detailError" class="error-text">{{ detailError }}</p>
        <template v-else-if="selectedNodeDetail">
          <div class="drawer-summary">
            <div>
              <p class="section-subtitle">Node</p>
              <strong>{{ selectedNodeDetail.node_name || shortPubkey(selectedNodeDetail.pubkey) }}</strong>
            </div>
            <div>
              <p class="section-subtitle">Contact type</p>
              <strong>{{ selectedNodeDetail.contact_type || "Unknown" }}</strong>
            </div>
            <div>
              <p class="section-subtitle">Observers</p>
              <strong>{{ selectedNodeDetail.observer_count }}</strong>
            </div>
            <div>
              <p class="section-subtitle">Zero-hop observers</p>
              <strong>{{ selectedNodeDetail.zero_hop_observer_count }}</strong>
            </div>
          </div>

          <div class="drawer-meta">
            <p><span>Pubkey:</span> <code>{{ selectedNodeDetail.pubkey }}</code></p>
            <p><span>First seen:</span> {{ formatTimestamp(selectedNodeDetail.first_seen) }}</p>
            <p><span>Last seen:</span> {{ formatTimestamp(selectedNodeDetail.last_seen) }}</p>
            <p>
              <span>Coordinates:</span>
              {{ formatCoordinates(selectedNodeDetail.latitude, selectedNodeDetail.longitude) }}
            </p>
          </div>

          <div class="tab-row">
            <button class="tab-btn" :class="{ active: detailTab === 'overview' }" @click="detailTab = 'overview'">
              Overview
            </button>
            <button class="tab-btn" :class="{ active: detailTab === 'peers' }" @click="detailTab = 'peers'">
              Peers
            </button>
            <button class="tab-btn" :class="{ active: detailTab === 'routes' }" @click="detailTab = 'routes'">
              Routes
            </button>
            <button class="tab-btn" :class="{ active: detailTab === 'trend' }" @click="detailTab = 'trend'">
              Trend
            </button>
          </div>

          <template v-if="detailTab === 'overview'">
            <UiDataTable>
              <thead>
                <tr>
                  <th>Observer</th>
                  <th>Route</th>
                  <th>Zero-hop</th>
                  <th>Last seen</th>
                  <th>RSSI</th>
                  <th>SNR</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="observer in selectedNodeDetail.observers" :key="observer.observer_repeater_id">
                  <td>{{ observer.observer_node_name }}</td>
                  <td>{{ formatRouteType(observer.route_type) }}</td>
                  <td>
                    <span class="pill" :class="observer.zero_hop ? 'pill-green' : 'pill-gray'">
                      {{ observer.zero_hop ? "true" : "false" }}
                    </span>
                  </td>
                  <td>{{ formatTimestamp(observer.last_seen) }}</td>
                  <td>{{ formatSignal(observer.rssi, "dBm") }}</td>
                  <td>{{ formatSignal(observer.snr, "dB") }}</td>
                </tr>
              </tbody>
            </UiDataTable>
          </template>

          <template v-else-if="detailTab === 'peers'">
            <p class="section-subtitle">Mini-graph of observer peers linked to this node.</p>
            <svg class="peer-mini-graph" viewBox="0 0 320 220" role="img" aria-label="Peer network mini graph">
              <rect x="0" y="0" width="320" height="220" rx="12" class="peer-bg" />
              <line
                v-for="edge in peerMiniEdges"
                :key="edge.id"
                :x1="edge.x1"
                :y1="edge.y1"
                :x2="edge.x2"
                :y2="edge.y2"
                class="peer-edge"
              />
              <circle :cx="160" :cy="110" r="16" class="peer-center" />
              <text x="160" y="114" text-anchor="middle" class="peer-center-label">N</text>
              <g v-for="node in peerMiniNodes" :key="node.id">
                <circle :cx="node.x" :cy="node.y" :r="node.radius" class="peer-node" />
                <text :x="node.x" :y="node.y + 3" text-anchor="middle" class="peer-node-label">
                  {{ node.label }}
                </text>
              </g>
            </svg>
            <UiDataTable>
              <thead>
                <tr>
                  <th>Peer</th>
                  <th>Links</th>
                  <th>Avg RSSI</th>
                  <th>Latest seen</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="peer in peerTableRows" :key="peer.id">
                  <td>{{ peer.label }}</td>
                  <td>{{ peer.links }}</td>
                  <td>{{ formatSignal(peer.avgRssi, "dBm") }}</td>
                  <td>{{ formatTimestamp(peer.lastSeen) }}</td>
                </tr>
              </tbody>
            </UiDataTable>
          </template>

          <template v-else-if="detailTab === 'routes'">
            <p class="section-subtitle">Route-type and contact pattern for the selected node.</p>
            <ul v-if="selectedNodeRoutePatternList.length > 0" class="detail-route-list">
              <li v-for="item in selectedNodeRoutePatternList" :key="item.key">
                <span>{{ item.label }}</span>
                <strong>{{ item.count }}</strong>
                <div class="route-bar">
                  <div class="route-bar-fill" :style="{ width: `${item.percent}%` }" />
                </div>
              </li>
            </ul>
            <p v-else class="section-subtitle">No route pattern data available for this node.</p>
            <p class="section-subtitle">
              Zero-hop observers: {{ selectedNodeDetail.zero_hop_observer_count }} / {{ selectedNodeDetail.observer_count }}
            </p>
          </template>

          <template v-else>
            <div class="timeseries-section">
              <h3>Node Trend ({{ selectedHours }}h)</h3>
              <p v-if="timeseriesLoading" class="section-subtitle">Loading trend data...</p>
              <p v-else-if="timeseriesError" class="error-text">{{ timeseriesError }}</p>
              <p v-else-if="timeseriesPoints.length === 0" class="section-subtitle">
                No sampled trend points available yet.
              </p>
              <template v-else>
                <svg class="trend-chart" viewBox="0 0 320 120" role="img" aria-label="Node sample count trend">
                  <rect x="0" y="0" width="320" height="120" rx="10" class="trend-bg" />
                  <path :d="timeseriesPath" class="trend-line" />
                </svg>
                <UiDataTable>
                  <thead>
                    <tr>
                      <th>Bucket start</th>
                      <th>Samples</th>
                      <th>Avg RSSI</th>
                      <th>Avg SNR</th>
                      <th>Zero-hop</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="point in timeseriesPoints.slice().reverse().slice(0, 12)" :key="point.bucket_start">
                      <td>{{ formatTimestamp(point.bucket_start) }}</td>
                      <td>{{ point.sample_count }}</td>
                      <td>{{ formatSignal(point.avg_rssi, "dBm") }}</td>
                      <td>{{ formatSignal(point.avg_snr, "dB") }}</td>
                      <td>{{ point.zero_hop_count }}</td>
                    </tr>
                  </tbody>
                </UiDataTable>
              </template>
            </div>
          </template>
        </template>
          </div>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import {
  getInsightNodeDetail,
  getInsightNodeTimeseries,
  getTopologyPacketQuality,
  getTopologyPacketStructure,
  getTopologyInsightsStreamUrl,
  getTopologySummary,
  listNeighborObservations,
  listTopologyEdges,
} from "../api";
import UiDataTable from "../components/ui/UiDataTable.vue";
import UiPanelCard from "../components/ui/UiPanelCard.vue";
import UiStatCard from "../components/ui/UiStatCard.vue";
import { appState, formatTimestamp } from "../state/appState";
import type {
  NeighborObservationListResponse,
  NeighborObservationResponse,
  NodeDetailResponse,
  NodeTimeseriesResponse,
  TopologyEdgeListResponse,
  TopologyPacketQualityResponse,
  TopologyPacketStructureResponse,
  TopologySummaryResponse,
} from "../types";

type MapNode = {
  pubkey: string;
  node_name: string | null;
  latitude: number;
  longitude: number;
  observer_count: number;
  last_seen: string;
};

type MapEdge = {
  id: string;
  observer_repeater_id: string;
  observed_node_pubkey: string;
  observer_latitude: number;
  observer_longitude: number;
  observed_latitude: number;
  observed_longitude: number;
  last_seen: string;
};

type PatternRow = {
  key: string;
  label: string;
  count: number;
  percent: number;
};

type PeerMiniNode = {
  id: string;
  label: string;
  x: number;
  y: number;
  radius: number;
  links: number;
  avgRssi: number | null;
  lastSeen: string | null;
};

const mapContainer = ref<HTMLDivElement | null>(null);

const loading = ref(false);
const error = ref<string | null>(null);
const detailLoading = ref(false);
const detailError = ref<string | null>(null);
const timeseriesLoading = ref(false);
const timeseriesError = ref<string | null>(null);

const detailTab = ref<"overview" | "peers" | "routes" | "trend">("overview");
const showHeatmap = ref(true);
const liveAutoRefresh = ref(true);
const liveState = ref<"idle" | "connecting" | "connected" | "reconnecting">("idle");

const selectedHours = ref(168);
const observerFilter = ref("all");
const contactTypeFilter = ref("all");
const routeTypeFilter = ref("all");
const zeroHopFilter = ref("all");
const searchFilter = ref("");
const tablePage = ref(1);
const tablePageSize = ref(25);
const tablePageSizeOptions = [25, 50, 100];
const packetSignalTrendPage = ref(1);
const packetSignalTrendPageSize = 12;
const packetRepeaterSharePage = ref(1);
const packetRepeaterSharePageSize = 8;
const packetSubpathPage = ref(1);
const packetSubpathPageSize = 8;
const packetGraphEdgePage = ref(1);
const packetGraphEdgePageSize = 10;

const observationsResponse = ref<NeighborObservationListResponse | null>(null);
const topologySummary = ref<TopologySummaryResponse | null>(null);
const edgeResponse = ref<TopologyEdgeListResponse | null>(null);
const packetQuality = ref<TopologyPacketQualityResponse | null>(null);
const packetStructure = ref<TopologyPacketStructureResponse | null>(null);

const selectedPubkey = ref<string | null>(null);
const selectedNodeDetail = ref<NodeDetailResponse | null>(null);
const nodeTimeseries = ref<NodeTimeseriesResponse | null>(null);

const timeOptions = [
  { value: 24, label: "24 hours" },
  { value: 72, label: "3 days" },
  { value: 168, label: "7 days" },
  { value: 336, label: "14 days" },
  { value: 720, label: "30 days" },
];
const PACKET_TYPE_LABELS: Record<string, string> = {
  "0": "Request",
  "1": "Response",
  "2": "Plain Text Message",
  "3": "Acknowledgment",
  "4": "Node Advertisement",
  "5": "Group Text Message",
  "6": "Group Datagram",
  "7": "Anonymous Request",
  "8": "Returned Path",
  "9": "Trace",
  "10": "Multi-part Packet",
  "11": "Control",
  "15": "Custom Packet",
};

const ROUTE_TYPE_LABELS: Record<string, string> = {
  "0": "Transport Flood",
  "1": "Flood",
  "2": "Direct",
  "3": "Transport Direct",
};

const routeTypeOptions = [
  { value: "0", label: "Transport Flood" },
  { value: "1", label: "Flood" },
  { value: "2", label: "Direct" },
  { value: "3", label: "Transport Direct" },
];

const observations = computed<NeighborObservationResponse[]>(() => observationsResponse.value?.items ?? []);
const tableTotalPages = computed(() =>
  Math.max(1, Math.ceil(observations.value.length / Math.max(tablePageSize.value, 1))),
);
const pagedObservations = computed(() => {
  const start = (tablePage.value - 1) * tablePageSize.value;
  return observations.value.slice(start, start + tablePageSize.value);
});
const pagedRangeStart = computed(() => {
  if (observations.value.length === 0) {
    return 0;
  }
  return (tablePage.value - 1) * tablePageSize.value + 1;
});
const pagedRangeEnd = computed(() =>
  observations.value.length === 0
    ? 0
    : Math.min(tablePage.value * tablePageSize.value, observations.value.length),
);
const observerOptions = computed(() =>
  Array.from(new Set(observations.value.map((item) => item.observer_node_name))).sort(),
);
const contactTypeOptions = computed(() =>
  Array.from(new Set(observations.value.map((item) => item.contact_type).filter(Boolean) as string[])).sort(),
);
const topologyAdvertLagSeconds = computed(() =>
  topologySummary.value?.topology_advert_lag_seconds ?? topologySummary.value?.telemetry_lag_seconds ?? null,
);
const mqttOverallLagSeconds = computed(() => topologySummary.value?.mqtt_overall_lag_seconds ?? null);
const mqttPacketLagSeconds = computed(() => topologySummary.value?.mqtt_packet_lag_seconds ?? null);
const mqttEventLagSeconds = computed(() => topologySummary.value?.mqtt_event_lag_seconds ?? null);
const isTopologyAdvertStale = computed(
  () => topologyAdvertLagSeconds.value !== null && topologyAdvertLagSeconds.value > 900,
);
const isMqttOverallStale = computed(
  () => mqttOverallLagSeconds.value !== null && mqttOverallLagSeconds.value > 900,
);
const liveStatusLabel = computed(() => {
  switch (liveState.value) {
    case "connected":
      return "Live SSE connected";
    case "connecting":
      return "Live SSE connecting…";
    case "reconnecting":
      return "Live SSE reconnecting…";
    default:
      return "Live SSE idle";
  }
});
const livePillClass = computed(() => {
  if (liveState.value === "connected") {
    return "live-pill-on";
  }
  if (liveState.value === "connecting" || liveState.value === "reconnecting") {
    return "live-pill-warn";
  }
  return "live-pill-off";
});
const packetRouteMixList = computed<PatternRow[]>(() =>
  buildPatternRowsFromCounts(packetQuality.value?.route_mix ?? {}, formatPacketRouteLabel),
);
const packetTypeMixList = computed<PatternRow[]>(() =>
  buildPatternRowsFromCounts(packetQuality.value?.packet_type_mix ?? {}, formatPacketTypeLabel),
);
const packetRepeaterShareRows = computed(() => packetQuality.value?.repeater_traffic_share ?? []);
const packetSignalTrendRows = computed(() => (packetQuality.value?.signal_trend ?? []).slice().reverse());
const packetSignalTrendTotalPages = computed(() =>
  Math.max(1, Math.ceil(packetSignalTrendRows.value.length / packetSignalTrendPageSize)),
);
const pagedPacketSignalTrendRows = computed(() => {
  const start = (packetSignalTrendPage.value - 1) * packetSignalTrendPageSize;
  return packetSignalTrendRows.value.slice(start, start + packetSignalTrendPageSize);
});
const packetRepeaterShareTotalPages = computed(() =>
  Math.max(1, Math.ceil(packetRepeaterShareRows.value.length / packetRepeaterSharePageSize)),
);
const pagedPacketRepeaterShareRows = computed(() => {
  const start = (packetRepeaterSharePage.value - 1) * packetRepeaterSharePageSize;
  return packetRepeaterShareRows.value.slice(start, start + packetRepeaterSharePageSize);
});
const packetSubpathRows = computed(() => packetStructure.value?.top_subpaths ?? []);
const packetSubpathTotalPages = computed(() =>
  Math.max(1, Math.ceil(packetSubpathRows.value.length / packetSubpathPageSize)),
);
const pagedPacketSubpathRows = computed(() => {
  const start = (packetSubpathPage.value - 1) * packetSubpathPageSize;
  return packetSubpathRows.value.slice(start, start + packetSubpathPageSize);
});
const packetGraphNodeRows = computed(() => packetStructure.value?.neighbor_graph_nodes ?? []);
const packetGraphEdgeRows = computed(() => packetStructure.value?.neighbor_graph_edges ?? []);
const packetGraphEdgeTotalPages = computed(() =>
  Math.max(1, Math.ceil(packetGraphEdgeRows.value.length / packetGraphEdgePageSize)),
);
const pagedPacketGraphEdgeRows = computed(() => {
  const start = (packetGraphEdgePage.value - 1) * packetGraphEdgePageSize;
  return packetGraphEdgeRows.value.slice(start, start + packetGraphEdgePageSize);
});
const packetChannelMixList = computed<PatternRow[]>(() =>
  buildPatternRowsFromCounts(packetStructure.value?.channel_detail_mix ?? {}, (key) => key),
);

const mapNodes = computed<MapNode[]>(() => {
  const grouped = new Map<
    string,
    {
      pubkey: string;
      node_name: string | null;
      latitude: number | null;
      longitude: number | null;
      observerSet: Set<string>;
      last_seen: string;
    }
  >();

  for (const item of observations.value) {
    const key = item.pubkey.toLowerCase();
    const existing = grouped.get(key);
    const itemSeen = new Date(item.last_seen).getTime();
    const existingSeen = existing ? new Date(existing.last_seen).getTime() : -1;

    if (!existing) {
      grouped.set(key, {
        pubkey: item.pubkey,
        node_name: item.node_name,
        latitude: item.latitude,
        longitude: item.longitude,
        observerSet: new Set([item.observer_repeater_id]),
        last_seen: item.last_seen,
      });
      continue;
    }

    existing.observerSet.add(item.observer_repeater_id);
    if (itemSeen >= existingSeen) {
      existing.last_seen = item.last_seen;
      existing.node_name = item.node_name ?? existing.node_name;
      if (isRenderableCoordinate(item.latitude, item.longitude)) {
        existing.latitude = item.latitude;
        existing.longitude = item.longitude;
      }
    }
  }

  return Array.from(grouped.values())
    .filter((item) => isRenderableCoordinate(item.latitude, item.longitude))
    .map((item) => ({
      pubkey: item.pubkey,
      node_name: item.node_name,
      latitude: item.latitude as number,
      longitude: item.longitude as number,
      observer_count: item.observerSet.size,
      last_seen: item.last_seen,
    }))
    .sort((a, b) => new Date(b.last_seen).getTime() - new Date(a.last_seen).getTime());
});

const mapEdges = computed<MapEdge[]>(() =>
  (edgeResponse.value?.items ?? [])
    .filter(
      (item) =>
        isRenderableCoordinate(item.observer_latitude, item.observer_longitude) &&
        isRenderableCoordinate(item.observed_latitude, item.observed_longitude),
    )
    .map((item) => ({
      id: `${item.observer_repeater_id}-${item.observed_node_pubkey}-${item.last_seen}`,
      observer_repeater_id: item.observer_repeater_id,
      observed_node_pubkey: item.observed_node_pubkey,
      observer_latitude: item.observer_latitude as number,
      observer_longitude: item.observer_longitude as number,
      observed_latitude: item.observed_latitude as number,
      observed_longitude: item.observed_longitude as number,
      last_seen: item.last_seen,
    })),
);

const mapHeatNodes = computed(() => {
  if (mapNodes.value.length === 0) {
    return [];
  }
  const maxObservers = Math.max(...mapNodes.value.map((item) => item.observer_count), 1);
  return mapNodes.value.map((item) => {
    const ratio = item.observer_count / maxObservers;
    return {
      pubkey: item.pubkey,
      latitude: item.latitude,
      longitude: item.longitude,
      radius: 12 + ratio * 24,
      opacity: 0.2 + ratio * 0.32,
    };
  });
});

const zeroHopObservations = computed(() => observations.value.filter((item) => item.zero_hop).length);
const zeroHopRatioLabel = computed(() => {
  if (observations.value.length === 0) {
    return "0%";
  }
  return `${((zeroHopObservations.value / observations.value.length) * 100).toFixed(1)}%`;
});

const routePatternList = computed<PatternRow[]>(() =>
  buildPatternRows(
    observations.value.map((item) => (item.route_type == null ? "unknown" : String(item.route_type))),
    formatPacketRouteLabel,
  ),
);

const contactTypePatternList = computed<PatternRow[]>(() =>
  buildPatternRows(
    observations.value.map((item) => item.contact_type || "unknown"),
    (key) => (key === "unknown" ? "Unknown" : key),
  ),
);

const selectedNodeRoutePatternList = computed<PatternRow[]>(() =>
  buildPatternRows(
    selectedNodeDetail.value?.observers.map((item) => (item.route_type == null ? "unknown" : String(item.route_type))) ??
      [],
    formatPacketRouteLabel,
  ),
);

const timeseriesPoints = computed(() => nodeTimeseries.value?.points ?? []);
const timeseriesPath = computed(() => {
  const points = timeseriesPoints.value;
  if (points.length === 0) {
    return "";
  }
  const maxCount = Math.max(...points.map((point) => point.sample_count), 1);
  const xStart = 16;
  const yTop = 14;
  const width = 288;
  const height = 92;
  const xDivisor = Math.max(points.length - 1, 1);
  return points
    .map((point, index) => {
      const x = xStart + (index / xDivisor) * width;
      const y = yTop + (1 - point.sample_count / maxCount) * height;
      return `${index === 0 ? "M" : "L"}${x.toFixed(2)} ${y.toFixed(2)}`;
    })
    .join(" ");
});

const peerMiniNodes = computed<PeerMiniNode[]>(() => {
  const observers = selectedNodeDetail.value?.observers ?? [];
  if (observers.length === 0) {
    return [];
  }
  const angleStep = (Math.PI * 2) / Math.max(observers.length, 1);
  const radius = 78;
  return observers.map((observer, index) => {
    const x = 160 + Math.cos(index * angleStep - Math.PI / 2) * radius;
    const y = 110 + Math.sin(index * angleStep - Math.PI / 2) * radius;
    const observerObservations = observations.value.filter(
      (item) => item.observer_repeater_id === observer.observer_repeater_id,
    );
    const signalValues = observerObservations
      .map((item) => item.rssi)
      .filter((value): value is number => typeof value === "number");
    const avgRssi =
      signalValues.length > 0
        ? signalValues.reduce((sum, value, _, arr) => sum + value / arr.length, 0)
        : null;
    const labelSource = observer.observer_node_name || `Peer ${index + 1}`;
    return {
      id: observer.observer_repeater_id,
      label: labelSource.slice(0, 4).toUpperCase(),
      x,
      y,
      radius: 8 + Math.min(observerObservations.length, 10) * 0.45,
      links: observerObservations.length,
      avgRssi,
      lastSeen: observer.last_seen,
    };
  });
});

const peerMiniEdges = computed(() =>
  peerMiniNodes.value.map((node) => ({
    id: node.id,
    x1: 160,
    y1: 110,
    x2: node.x,
    y2: node.y,
  })),
);

const peerTableRows = computed(() =>
  peerMiniNodes.value
    .slice()
    .sort((a, b) => b.links - a.links)
    .map((item) => ({
      id: item.id,
      label: item.label,
      links: item.links,
      avgRssi: item.avgRssi,
      lastSeen: item.lastSeen,
    })),
);

let topologyEventSource: EventSource | null = null;
let refreshDebounceTimer: ReturnType<typeof setTimeout> | null = null;

let leafletMap: L.Map | null = null;
let markerLayer: L.LayerGroup | null = null;
let edgeLayer: L.LayerGroup | null = null;
let heatLayer: L.LayerGroup | null = null;
let hasFittedBounds = false;

watch(
  () => appState.token,
  async (token) => {
    if (token) {
      await loadObservations();
      startTopologyStream();
      return;
    }
    stopTopologyStream();
  },
);

watch(
  [selectedHours, observerFilter, contactTypeFilter, routeTypeFilter, zeroHopFilter, searchFilter],
  async () => {
    hasFittedBounds = false;
    tablePage.value = 1;
    resetPacketAnalyticsPagination();
    await loadObservations();
  },
);
watch([observations, tablePageSize], () => {
  if (tablePage.value > tableTotalPages.value) {
    tablePage.value = tableTotalPages.value;
  }
  if (tablePage.value < 1) {
    tablePage.value = 1;
  }
});
watch(
  [
    packetSignalTrendRows,
    packetRepeaterShareRows,
    packetSubpathRows,
    packetGraphEdgeRows,
    packetSignalTrendTotalPages,
    packetRepeaterShareTotalPages,
    packetSubpathTotalPages,
    packetGraphEdgeTotalPages,
  ],
  () => {
    packetSignalTrendPage.value = Math.min(
      Math.max(packetSignalTrendPage.value, 1),
      packetSignalTrendTotalPages.value,
    );
    packetRepeaterSharePage.value = Math.min(
      Math.max(packetRepeaterSharePage.value, 1),
      packetRepeaterShareTotalPages.value,
    );
    packetSubpathPage.value = Math.min(Math.max(packetSubpathPage.value, 1), packetSubpathTotalPages.value);
    packetGraphEdgePage.value = Math.min(
      Math.max(packetGraphEdgePage.value, 1),
      packetGraphEdgeTotalPages.value,
    );
  },
);

watch([mapNodes, mapEdges, showHeatmap], () => {
  renderMapLayers();
});

watch(selectedPubkey, () => {
  renderMapLayers();
});

onMounted(async () => {
  await nextTick();
  initMap();
  await loadObservations();
  startTopologyStream();
  window.addEventListener("keydown", handleEscapeKey);
});

onBeforeUnmount(() => {
  stopTopologyStream();
  if (refreshDebounceTimer) {
    clearTimeout(refreshDebounceTimer);
    refreshDebounceTimer = null;
  }
  destroyMap();
  window.removeEventListener("keydown", handleEscapeKey);
});

function initMap(): void {
  if (!mapContainer.value || leafletMap) {
    return;
  }
  leafletMap = L.map(mapContainer.value, {
    zoomControl: true,
    attributionControl: true,
  }).setView([20, 0], 2);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap contributors",
  }).addTo(leafletMap);

  edgeLayer = L.layerGroup().addTo(leafletMap);
  heatLayer = L.layerGroup().addTo(leafletMap);
  markerLayer = L.layerGroup().addTo(leafletMap);
}

function resetPacketAnalyticsPagination(): void {
  packetSignalTrendPage.value = 1;
  packetRepeaterSharePage.value = 1;
  packetSubpathPage.value = 1;
  packetGraphEdgePage.value = 1;
}

function destroyMap(): void {
  if (!leafletMap) {
    return;
  }
  leafletMap.remove();
  leafletMap = null;
  markerLayer = null;
  edgeLayer = null;
  heatLayer = null;
  hasFittedBounds = false;
}

function renderMapLayers(forceFit = false): void {
  if (!leafletMap || !markerLayer || !edgeLayer || !heatLayer) {
    return;
  }
  markerLayer.clearLayers();
  edgeLayer.clearLayers();
  heatLayer.clearLayers();

  for (const edge of mapEdges.value) {
    L.polyline(
      [
        [edge.observer_latitude, edge.observer_longitude],
        [edge.observed_latitude, edge.observed_longitude],
      ],
      {
        color: "#7ea8f3",
        weight: 2,
        opacity: 0.45,
      },
    ).addTo(edgeLayer);
  }

  if (showHeatmap.value) {
    for (const heat of mapHeatNodes.value) {
      L.circleMarker([heat.latitude, heat.longitude], {
        radius: heat.radius,
        color: "#95bfff",
        opacity: 0,
        fillColor: "#7eaef8",
        fillOpacity: heat.opacity,
      }).addTo(heatLayer);
    }
  }

  for (const node of mapNodes.value) {
    const marker = L.circleMarker([node.latitude, node.longitude], {
      radius: selectedPubkey.value?.toLowerCase() === node.pubkey.toLowerCase() ? 9 : 6,
      color: "#f4fbff",
      weight: 1.2,
      fillColor: markerColor(node.last_seen),
      fillOpacity: 0.95,
    });
    marker.bindTooltip(
      `${node.node_name || shortPubkey(node.pubkey)} • observers: ${node.observer_count} • last seen: ${formatTimestamp(node.last_seen)}`,
    );
    marker.on("click", () => {
      void openNodeDetail(node.pubkey);
    });
    marker.addTo(markerLayer);
  }

  if (mapNodes.value.length > 0 && (forceFit || !hasFittedBounds)) {
    const bounds = L.latLngBounds(
      mapNodes.value.map((node) => [node.latitude, node.longitude] as [number, number]),
    );
    if (bounds.isValid()) {
      leafletMap.fitBounds(bounds, {
        padding: [24, 24],
        maxZoom: 10,
      });
      hasFittedBounds = true;
    }
  }
}

async function loadObservations(): Promise<void> {
  if (!appState.token) {
    return;
  }
  loading.value = true;
  error.value = null;
  try {
    const filterOptions = {
      hours: selectedHours.value,
      limit: 1000,
      offset: 0,
      observer_node_name: observerFilter.value === "all" ? undefined : observerFilter.value,
      contact_type: contactTypeFilter.value === "all" ? undefined : contactTypeFilter.value,
      route_type: routeTypeFilter.value === "all" ? undefined : Number.parseInt(routeTypeFilter.value, 10),
      zero_hop: zeroHopFilter.value === "all" ? undefined : zeroHopFilter.value === "true",
      search: searchFilter.value || undefined,
    };

    const [observationsResult, summaryResult, edgesResult] = await Promise.all([
      listNeighborObservations(appState.token, filterOptions),
      getTopologySummary(appState.token, { hours: selectedHours.value, stale_after_hours: 6 }),
      listTopologyEdges(appState.token, { ...filterOptions, limit: 2000 }),
    ]);
    const [packetQualityResult, packetStructureResult] = await Promise.allSettled([
      getTopologyPacketQuality(appState.token, {
        hours: selectedHours.value,
        bucket_minutes: selectedHours.value <= 72 ? 30 : 60,
        limit: 5000,
        observer_node_name: observerFilter.value === "all" ? undefined : observerFilter.value,
      }),
      getTopologyPacketStructure(appState.token, {
        hours: selectedHours.value,
        limit: 3000,
        top_subpaths: 20,
        top_nodes: 120,
        top_edges: 120,
      }),
    ]);

    observationsResponse.value = observationsResult;
    topologySummary.value = summaryResult;
    edgeResponse.value = edgesResult;
    packetQuality.value = packetQualityResult.status === "fulfilled" ? packetQualityResult.value : null;
    packetStructure.value =
      packetStructureResult.status === "fulfilled" ? packetStructureResult.value : null;
    renderMapLayers(true);

    if (
      selectedPubkey.value &&
      !observations.value.some((item) => item.pubkey.toLowerCase() === selectedPubkey.value?.toLowerCase())
    ) {
      closeDetailDrawer();
    } else if (selectedPubkey.value) {
      await Promise.all([loadNodeDetail(selectedPubkey.value), loadNodeTimeseries(selectedPubkey.value)]);
    }
  } catch (caught) {
    packetQuality.value = null;
    packetStructure.value = null;
    error.value = caught instanceof Error ? caught.message : "Failed to load topology observations.";
  } finally {
    loading.value = false;
  }
}

async function openNodeDetail(pubkey: string): Promise<void> {
  selectedPubkey.value = pubkey;
  detailTab.value = "overview";
  renderMapLayers();
  await Promise.all([loadNodeDetail(pubkey), loadNodeTimeseries(pubkey)]);
}

async function loadNodeDetail(pubkey: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  detailLoading.value = true;
  detailError.value = null;
  try {
    selectedNodeDetail.value = await getInsightNodeDetail(appState.token, pubkey, {
      hours: selectedHours.value,
    });
  } catch (caught) {
    selectedNodeDetail.value = null;
    detailError.value = caught instanceof Error ? caught.message : "Failed to load node details.";
  } finally {
    detailLoading.value = false;
  }
}

async function loadNodeTimeseries(pubkey: string): Promise<void> {
  if (!appState.token) {
    return;
  }
  timeseriesLoading.value = true;
  timeseriesError.value = null;
  try {
    nodeTimeseries.value = await getInsightNodeTimeseries(appState.token, pubkey, {
      hours: selectedHours.value,
      bucket_hours: selectedHours.value <= 72 ? 2 : 6,
    });
  } catch (caught) {
    nodeTimeseries.value = null;
    timeseriesError.value = caught instanceof Error ? caught.message : "Failed to load node trend.";
  } finally {
    timeseriesLoading.value = false;
  }
}

function buildPatternRows(values: string[], toLabel: (key: string) => string): PatternRow[] {
  const counts = new Map<string, number>();
  for (const value of values) {
    counts.set(value, (counts.get(value) ?? 0) + 1);
  }
  const total = values.length || 1;
  return Array.from(counts.entries())
    .map(([key, count]) => ({
      key,
      label: toLabel(key),
      count,
      percent: (count / total) * 100,
    }))
    .sort((a, b) => b.count - a.count);
}

function buildPatternRowsFromCounts(
  countsMap: Record<string, number>,
  toLabel: (key: string) => string,
): PatternRow[] {
  const entries = Object.entries(countsMap);
  const total = entries.reduce((sum, [, count]) => sum + count, 0) || 1;
  return entries
    .map(([key, count]) => ({
      key,
      label: toLabel(key),
      count,
      percent: (count / total) * 100,
    }))
    .sort((a, b) => b.count - a.count);
}

function startTopologyStream(): void {
  if (!appState.token) {
    stopTopologyStream();
    return;
  }
  stopTopologyStream();
  liveState.value = "connecting";
  const source = new EventSource(getTopologyInsightsStreamUrl(appState.token));
  topologyEventSource = source;
  source.onopen = () => {
    liveState.value = "connected";
  };

  source.addEventListener("ready", () => {
    liveState.value = "connected";
  });
  source.addEventListener("topology_update", (event) => {
    liveState.value = "connected";
    handleTopologySseEvent((event as MessageEvent<string>).data);
  });
  source.onerror = () => {
    liveState.value = source.readyState === EventSource.CLOSED ? "idle" : "reconnecting";
  };
}

function stopTopologyStream(): void {
  if (topologyEventSource) {
    topologyEventSource.close();
    topologyEventSource = null;
  }
  liveState.value = "idle";
}

function handleTopologySseEvent(raw: string): void {
  if (!liveAutoRefresh.value) {
    return;
  }
  try {
    const parsed = JSON.parse(raw) as { payload?: unknown } | null;
    if (!parsed || typeof parsed !== "object") {
      return;
    }
    queueRefresh();
  } catch {
    // Ignore malformed events.
  }
}

function queueRefresh(): void {
  if (refreshDebounceTimer) {
    clearTimeout(refreshDebounceTimer);
  }
  refreshDebounceTimer = setTimeout(() => {
    refreshDebounceTimer = null;
    void loadObservations();
  }, 1200);
}

function goToPreviousTablePage(): void {
  if (tablePage.value > 1) {
    tablePage.value -= 1;
  }
}

function goToNextTablePage(): void {
  if (tablePage.value < tableTotalPages.value) {
    tablePage.value += 1;
  }
}

function handleEscapeKey(event: KeyboardEvent): void {
  if (event.key === "Escape" && selectedPubkey.value) {
    closeDetailDrawer();
  }
}

function closeDetailDrawer(): void {
  selectedPubkey.value = null;
  selectedNodeDetail.value = null;
  detailError.value = null;
  nodeTimeseries.value = null;
  timeseriesError.value = null;
  detailTab.value = "overview";
  renderMapLayers();
}

function shortPubkey(pubkey: string): string {
  if (pubkey.length <= 14) {
    return pubkey;
  }
  return `${pubkey.slice(0, 8)}…${pubkey.slice(-4)}`;
}

function formatRouteType(value: number | null): string {
  if (value == null) {
    return "Unknown";
  }
  const label = routeTypeName(value);
  return label === "Unknown" ? `Route ${value}` : label;
}

function routeTypeName(value: number | null): string {
  if (value == null) {
    return "Unknown";
  }
  return ROUTE_TYPE_LABELS[String(value)] ?? "Unknown";
}

function numericKey(value: string): number | null {
  const normalized = value.trim();
  if (!/^-?\d+$/.test(normalized)) {
    return null;
  }
  return Number.parseInt(normalized, 10);
}

function toTitleWords(value: string): string {
  return value
    .split(/\s+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase())
    .join(" ");
}

function normalizeLabelText(value: string): string {
  const normalized = value.trim();
  if (!normalized) {
    return "Unknown";
  }
  if (normalized.toLowerCase() === "unknown") {
    return "Unknown";
  }
  if (/[a-z]/.test(normalized) && /[A-Z]/.test(normalized)) {
    return normalized;
  }
  const spaced = normalized.replace(/[_-]+/g, " ").replace(/\s+/g, " ").trim();
  return toTitleWords(spaced);
}

function formatPacketRouteLabel(key: string): string {
  if (key.trim().toLowerCase() === "unknown") {
    return "Unknown";
  }
  const routeType = numericKey(key);
  if (routeType == null) {
    return normalizeLabelText(key);
  }
  const label = routeTypeName(routeType);
  return label === "Unknown" ? `Route ${routeType}` : label;
}

function formatPacketTypeLabel(key: string): string {
  if (key.trim().toLowerCase() === "unknown") {
    return "Unknown";
  }
  const maybeNumeric = numericKey(key);
  if (maybeNumeric != null) {
    return PACKET_TYPE_LABELS[String(maybeNumeric)] ?? `Packet ${maybeNumeric}`;
  }
  if (PACKET_TYPE_LABELS[key]) {
    return PACKET_TYPE_LABELS[key];
  }
  return normalizeLabelText(key);
}

function formatSignal(value: number | null, unit: string): string {
  if (value == null || Number.isNaN(value)) {
    return "—";
  }
  return `${value.toFixed(1)} ${unit}`;
}

function formatCoordinates(latitude: number | null, longitude: number | null): string {
  if (latitude == null || longitude == null) {
    return "—";
  }
  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`;
}

function formatLag(seconds: number | null): string {
  if (seconds == null || Number.isNaN(seconds)) {
    return "—";
  }
  if (seconds < 60) {
    return `${seconds}s`;
  }
  if (seconds < 3600) {
    return `${Math.round(seconds / 60)}m`;
  }
  return `${(seconds / 3600).toFixed(1)}h`;
}

function isRenderableCoordinate(
  latitude: number | null | undefined,
  longitude: number | null | undefined,
): boolean {
  if (latitude == null || longitude == null) {
    return false;
  }
  const epsilon = 1e-6;
  return Math.abs(latitude) > epsilon || Math.abs(longitude) > epsilon;
}

function markerColor(lastSeen: string): string {
  const seenAt = new Date(lastSeen).getTime();
  if (Number.isNaN(seenAt)) {
    return "#9fb2cf";
  }
  const ageHours = (Date.now() - seenAt) / (1000 * 60 * 60);
  if (ageHours >= 24) {
    return "#f08095";
  }
  if (ageHours >= 6) {
    return "#f5c159";
  }
  return "#56d88a";
}
</script>

<style scoped>
.insights-page {
  position: relative;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.live-pill {
  border-radius: 999px;
  padding: 0.2rem 0.55rem;
  font-size: 0.72rem;
  border: 1px solid transparent;
}

.live-pill-on {
  color: #7deab0;
  background: rgba(45, 156, 98, 0.18);
  border-color: rgba(84, 196, 140, 0.35);
}
.live-pill-warn {
  color: #f4d68a;
  background: rgba(150, 101, 21, 0.2);
  border-color: rgba(207, 151, 61, 0.5);
}

.live-pill-off {
  color: #f3c978;
  background: rgba(125, 97, 46, 0.12);
  border-color: rgba(170, 134, 72, 0.3);
}

.filter-grid {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
}

.summary-stats {
  gap: 0.55rem;
  grid-template-columns: repeat(auto-fit, minmax(145px, 1fr));
}

.summary-stats :deep(.stat-card) {
  padding: 0.58rem 0.72rem;
  gap: 0.2rem;
  border-radius: 10px;
}

.summary-stats :deep(.stat-card h3) {
  font-size: 0.64rem;
  letter-spacing: 0.045em;
}

.summary-stats :deep(.stat-card strong) {
  font-size: 1.05rem;
  line-height: 1.15;
}

.summary-stats :deep(.section-subtitle) {
  font-size: 0.7rem;
  line-height: 1.2;
}

.field-checkbox {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.error-text {
  color: #fb787b;
  font-size: 0.88rem;
}

.warning-text {
  color: #f5c159;
  font-size: 0.88rem;
}

.map-shell {
  position: relative;
}

.real-map {
  width: 100%;
  min-height: 430px;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(130, 156, 198, 0.2);
}

.map-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  background: rgba(8, 16, 28, 0.72);
  border-radius: 12px;
  color: #9cb2d4;
  font-size: 0.9rem;
}

.node-cell {
  display: grid;
  gap: 0.12rem;
}

.route-pattern-grid {
  display: grid;
  gap: 0.9rem;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.route-pattern-card {
  border: 1px solid rgba(133, 157, 197, 0.22);
  border-radius: 12px;
  padding: 0.75rem;
  background: rgba(14, 24, 41, 0.45);
}

.route-pattern-card h3 {
  margin: 0 0 0.5rem;
  font-size: 0.86rem;
}

.route-pattern-card ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.42rem;
}

.route-pattern-card li {
  display: grid;
  gap: 0.22rem;
}

.route-pattern-card :deep(.table-pagination) {
  margin-top: 0.55rem;
}

.ratio-value {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 700;
  color: #e8f5ff;
}

.route-bar {
  height: 7px;
  border-radius: 999px;
  background: rgba(106, 133, 182, 0.22);
  overflow: hidden;
}

.route-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #70acf5, #9bd9ff);
}

.table-pagination {
  margin-top: 0.7rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.8rem;
  flex-wrap: wrap;
}

.pagination-size {
  min-width: 120px;
}

.pagination-actions {
  display: flex;
  align-items: center;
  gap: 0.55rem;
}

.pagination-status {
  color: #a8bddf;
  font-size: 0.82rem;
}

.detail-dialog-backdrop {
  position: fixed;
  inset: 0;
  z-index: 2400;
  background: rgba(5, 10, 20, 0.58);
  display: grid;
  place-items: center;
  padding: 2.25rem;
}

.detail-dialog {
  width: min(760px, 92vw);
  max-height: min(80vh, 820px);
  background: rgba(6, 11, 20, 0.97);
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 14px;
  backdrop-filter: blur(20px);
  box-shadow: 0 24px 48px rgba(0, 0, 0, 0.45);
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
}

.drawer-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.6rem;
  padding: 0.85rem 0.95rem;
  border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.drawer-body {
  padding: 0.85rem 0.95rem;
  display: grid;
  gap: 0.75rem;
  overflow-y: auto;
}

.drawer-summary {
  display: grid;
  gap: 0.6rem;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.drawer-summary strong {
  color: #f6fbff;
}

.drawer-meta {
  display: grid;
  gap: 0.25rem;
  font-size: 0.82rem;
}

.drawer-meta p {
  display: flex;
  gap: 0.35rem;
  align-items: baseline;
  flex-wrap: wrap;
}

.drawer-meta span {
  color: #9caec9;
}

.tab-row {
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.tab-btn {
  border: 1px solid rgba(130, 158, 202, 0.35);
  border-radius: 999px;
  background: rgba(20, 34, 59, 0.55);
  color: #d6e8ff;
  font-size: 0.72rem;
  line-height: 1;
  padding: 0.32rem 0.62rem;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.tab-btn.active {
  background: rgba(70, 124, 214, 0.35);
  border-color: rgba(119, 176, 255, 0.75);
  color: #ffffff;
}

.detail-route-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.42rem;
}

.detail-route-list li {
  display: grid;
  gap: 0.2rem;
}

.peer-mini-graph {
  width: 100%;
  height: auto;
}

.peer-bg {
  fill: rgba(12, 24, 42, 0.88);
}

.peer-edge {
  stroke: rgba(133, 169, 231, 0.55);
  stroke-width: 1.2;
}

.peer-center {
  fill: #4f8ef0;
}

.peer-center-label {
  fill: #fff;
  font-size: 0.65rem;
  font-weight: 700;
}

.peer-node {
  fill: rgba(131, 189, 255, 0.9);
}

.peer-node-label {
  fill: #0a1a2f;
  font-size: 0.46rem;
  font-weight: 700;
}

.timeseries-section {
  display: grid;
  gap: 0.55rem;
}

.timeseries-section h3 {
  margin: 0;
  font-size: 0.92rem;
}

.trend-chart {
  width: 100%;
  height: auto;
}

.trend-bg {
  fill: rgba(14, 24, 42, 0.9);
}

.trend-line {
  fill: none;
  stroke: #8dc3ff;
  stroke-width: 2;
}

:deep(.leaflet-container) {
  font: inherit;
}

@media (max-width: 1200px) {
  .detail-dialog {
    width: min(840px, 94vw);
  }
}

@media (max-width: 900px) {
  .detail-dialog-backdrop {
    padding: 0.9rem;
  }

  .detail-dialog {
    width: 96vw;
    max-height: 86vh;
  }
}
</style>
