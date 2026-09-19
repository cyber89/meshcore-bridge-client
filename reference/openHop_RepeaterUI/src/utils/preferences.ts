/**
 * Utility for managing user preferences in localStorage
 */

const PREFERENCE_PREFIX = 'pymc_pref_';

/**
 * Get a preference from localStorage
 */
export function getPreference<T>(key: string, defaultValue: T): T {
  try {
    const item = localStorage.getItem(PREFERENCE_PREFIX + key);
    if (item === null) {
      return defaultValue;
    }
    return JSON.parse(item) as T;
  } catch (error) {
    console.warn(`Failed to get preference ${key}:`, error);
    return defaultValue;
  }
}

/**
 * Set a preference in localStorage
 */
export function setPreference<T>(key: string, value: T): void {
  try {
    localStorage.setItem(PREFERENCE_PREFIX + key, JSON.stringify(value));
  } catch (error) {
    console.warn(`Failed to set preference ${key}:`, error);
  }
}

/**
 * Remove a preference from localStorage
 */
export function removePreference(key: string): void {
  try {
    localStorage.removeItem(PREFERENCE_PREFIX + key);
  } catch (error) {
    console.warn(`Failed to remove preference ${key}:`, error);
  }
}

/**
 * Clear all preferences
 */
export function clearAllPreferences(): void {
  try {
    const keys = Object.keys(localStorage);
    keys.forEach((key) => {
      if (key.startsWith(PREFERENCE_PREFIX)) {
        localStorage.removeItem(key);
      }
    });
  } catch (error) {
    console.warn('Failed to clear preferences:', error);
  }
}
