import { defineStore } from 'pinia';
import { reactive } from 'vue';

export const useTreeStateStore = defineStore('treeState', () => {
  // Global expanded state that persists across component lifecycle
  const expandedNodes = reactive(new Set<number>());

  // Global selection state
  const selectedNodeId = reactive<{ value: number | null }>({ value: null });

  const addExpandedNode = (nodeId: number) => {
    expandedNodes.add(nodeId);
  };

  const removeExpandedNode = (nodeId: number) => {
    expandedNodes.delete(nodeId);
  };

  const isNodeExpanded = (nodeId: number) => {
    return expandedNodes.has(nodeId);
  };

  const setSelectedNode = (nodeId: number | null) => {
    selectedNodeId.value = nodeId;
  };

  const toggleExpanded = (nodeId: number) => {
    if (expandedNodes.has(nodeId)) {
      removeExpandedNode(nodeId);
    } else {
      addExpandedNode(nodeId);
    }
  };

  return {
    expandedNodes,
    selectedNodeId,
    addExpandedNode,
    removeExpandedNode,
    isNodeExpanded,
    setSelectedNode,
    toggleExpanded,
  };
});
