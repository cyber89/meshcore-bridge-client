/**
 * MeshCore UI - Bootstrap Icons Adapter (100% Offline, Zero CDN dependency).
 * Provee iconos vectoriales Bootstrap Icons integrados con la SPA.
 */

const BS_ICON_MAP = {
  'radio': 'bi-broadcast',
  'radio-tower': 'bi-broadcast-pin',
  'users': 'bi-people',
  'user': 'bi-person',
  'user-plus': 'bi-person-plus',
  'user-check': 'bi-person-check',
  'network': 'bi-hdd-network',
  'map': 'bi-map',
  'map-pin': 'bi-geo-alt',
  'activity': 'bi-activity',
  'file-text': 'bi-file-earmark-text',
  'sliders': 'bi-sliders',
  'settings': 'bi-gear',
  'save': 'bi-floppy',
  'shield': 'bi-shield-check',
  'shield-alert': 'bi-shield-exclamation',
  'terminal': 'bi-terminal',
  'sun': 'bi-sun',
  'moon': 'bi-moon',
  'copy': 'bi-clipboard',
  'trash-2': 'bi-trash',
  'share-2': 'bi-share',
  'qr-code': 'bi-qr-code',
  'crosshair': 'bi-bullseye',
  'zap': 'bi-lightning',
  'battery': 'bi-battery-half',
  'refresh-cw': 'bi-arrow-repeat',
  'volume-2': 'bi-volume-up',
  'volume-x': 'bi-volume-mute',
  'chevron-left': 'bi-chevron-left',
  'chevron-right': 'bi-chevron-right',
  'plus': 'bi-plus-lg',
  'plus-circle': 'bi-plus-circle',
  'circle-plus': 'bi-plus-circle',
  'help-circle': 'bi-question-circle',
  'message-square': 'bi-chat-dots',
  'message-square-plus': 'bi-chat-dots-fill',
  'download': 'bi-download',
  'upload': 'bi-upload',
  'check': 'bi-check-lg',
  'check-check': 'bi-check-all',
  'server': 'bi-hdd-stack',
  'home': 'bi-house',
  'cpu': 'bi-cpu',
  'gauge': 'bi-speedometer2',
  'lock': 'bi-lock',
  'unlock': 'bi-unlock',
  'search': 'bi-search',
  'alert-triangle': 'bi-exclamation-triangle',
  'clock': 'bi-clock',
  'send': 'bi-send',
  'wifi': 'bi-wifi',
  'git-branch': 'bi-diagram-2',
  'git-commit': 'bi-record-circle',
  'package': 'bi-box-seam',
  'globe': 'bi-globe',
  'trophy': 'bi-trophy',
  'award': 'bi-award',
  'star': 'bi-star',
  'route': 'bi-signpost-split',
  'loader-2': 'bi-arrow-repeat',
  'flame': 'bi-fire',
  'signal': 'bi-reception-4',
  'bar-chart-2': 'bi-bar-chart',
  'trending-up': 'bi-graph-up-arrow',
  'database': 'bi-database',
  'hard-drive': 'bi-hdd',
  'stethoscope': 'bi-heart-pulse',
  'bug': 'bi-bug',
  'broom': 'bi-brush',
  'repeat': 'bi-arrow-repeat',
  'info': 'bi-info-circle',
  'filter': 'bi-funnel',
  'layers': 'bi-layers',
  'radar': 'bi-radar',
  'eye': 'bi-eye',
  'thermometer': 'bi-thermometer-half',
  'droplets': 'bi-droplet',
  'compass': 'bi-compass',
  'smile': 'bi-emoji-smile',
  'paperclip': 'bi-paperclip',
  'arrow-left': 'bi-arrow-left'
};

function getLucideIcon(name, extraClass = '', size = 18) {
  const biClass = BS_ICON_MAP[name] || `bi-${name}`;
  const sizeStyle = size ? `font-size: ${size}px;` : '';
  return `<i class="bi ${biClass} ${extraClass}" style="${sizeStyle}" aria-hidden="true"></i>`;
}

function initLucideIcons(container = document) {
  const elements = container.querySelectorAll('[data-lucide]');
  elements.forEach((el) => {
    const name = el.getAttribute('data-lucide');
    const size = parseInt(el.getAttribute('data-size'), 10) || 18;
    const extraClass = el.getAttribute('data-class') || '';
    if (name) {
      el.innerHTML = getLucideIcon(name, extraClass, size);
    }
  });
}

// Compatibilidad con window.lucide
window.LUCIDE_ICONS = BS_ICON_MAP;
window.getLucideIcon = getLucideIcon;
window.initLucideIcons = initLucideIcons;
window.lucide = {
  createIcons: function(options = {}) {
    initLucideIcons(document);
  }
};

// Auto-inicialización reactiva en DOMContentLoaded
if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => initLucideIcons());
  } else {
    initLucideIcons();
  }
}
