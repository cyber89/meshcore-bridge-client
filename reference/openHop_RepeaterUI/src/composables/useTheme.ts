import { ref, watch } from 'vue';

export type Theme = 'light' | 'dark';

const STORAGE_KEY = 'theme-preference';
const theme = ref<Theme>('dark');
const isInitialized = ref(false);

// Apply theme to document
function applyTheme(newTheme: Theme) {
  const html = document.documentElement;

  if (newTheme === 'dark') {
    html.classList.add('dark');
  } else {
    html.classList.remove('dark');
  }
}

// Initialize theme immediately when module loads
function initTheme() {
  if (isInitialized.value) return;

  const stored = localStorage.getItem(STORAGE_KEY) as Theme | null;

  if (stored && (stored === 'light' || stored === 'dark')) {
    theme.value = stored;
  } else if (window.matchMedia('(prefers-color-scheme: light)').matches) {
    theme.value = 'light';
  } else {
    theme.value = 'dark';
  }

  applyTheme(theme.value);
  isInitialized.value = true;
}

// Initialize immediately on module load
if (typeof window !== 'undefined') {
  initTheme();
}

// Watch for theme changes
watch(theme, (newTheme) => {
  localStorage.setItem(STORAGE_KEY, newTheme);
  applyTheme(newTheme);
});

export function useTheme() {
  const toggleTheme = () => {
    theme.value = theme.value === 'dark' ? 'light' : 'dark';
  };

  const setTheme = (newTheme: Theme) => {
    theme.value = newTheme;
  };

  const isDark = () => theme.value === 'dark';

  return {
    theme,
    toggleTheme,
    setTheme,
    isDark,
  };
}
