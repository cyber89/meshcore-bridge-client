/**
 * Manual-activation tabs for native buttons. Arrow/Home/End navigation only
 * moves focus; Enter/Space retain native click activation. The caller owns
 * view-specific classes and effects, while this helper owns ARIA and hidden.
 * Call sync(button) after programmatic selection; it does not run onActivate.
 */
export function initManualTabs(tablist, {
  tabSelector = ".subtab-btn",
  panelAttribute = "data-subtab",
  orientation = "horizontal",
  onActivate = () => {},
} = {}) {
  if (!tablist) return null;
  const tabs = Array.from(tablist.querySelectorAll(tabSelector));
  if (!tabs.length) return null;
  tablist.setAttribute("role", "tablist");
  tablist.setAttribute("aria-orientation", orientation);
  for (const tab of tabs) {
    const panelId = tab.getAttribute(panelAttribute);
    const panel = document.getElementById(panelId);
    tab.type = "button";
    tab.setAttribute("role", "tab");
    if (!panel) continue;
    if (!tab.id) tab.id = `${panelId}-tab`;
    tab.setAttribute("aria-controls", panelId);
    panel.setAttribute("role", "tabpanel");
    panel.setAttribute("aria-labelledby", tab.id);
    panel.tabIndex = 0;
  }

  const sync = (selected) => {
    if (!tabs.includes(selected)) return;
    for (const tab of tabs) {
      const isSelected = tab === selected;
      tab.setAttribute("aria-selected", String(isSelected));
      tab.tabIndex = isSelected ? 0 : -1;
      const panel = document.getElementById(tab.getAttribute(panelAttribute));
      if (panel) panel.hidden = !isSelected;
    }
  };
  sync(tabs.find((tab) => tab.classList.contains("active")) || tabs[0]);

  const click = (event) => {
    const tab = event.target.closest(tabSelector);
    if (!tabs.includes(tab) || tab.disabled) return;
    sync(tab);
    onActivate(tab, document.getElementById(tab.getAttribute(panelAttribute)));
  };
  const keydown = (event) => {
    const current = event.target.closest(tabSelector);
    if (!tabs.includes(current) || event.altKey || event.ctrlKey || event.metaKey) return;
    const available = tabs.filter((tab) => !tab.disabled && !tab.hidden);
    const index = available.indexOf(current);
    const vertical = tablist.getAttribute("aria-orientation") === "vertical";
    const previous = vertical ? "ArrowUp" : "ArrowLeft";
    const next = vertical ? "ArrowDown" : "ArrowRight";
    let destination;
    if (event.key === "Home") destination = available[0];
    else if (event.key === "End") destination = available.at(-1);
    else if (event.key === previous) destination = available[(index - 1 + available.length) % available.length];
    else if (event.key === next) destination = available[(index + 1) % available.length];
    else return;
    if (!destination) return;
    event.preventDefault();
    for (const tab of tabs) tab.tabIndex = tab === destination ? 0 : -1;
    destination.focus();
  };
  tablist.addEventListener("click", click);
  tablist.addEventListener("keydown", keydown);
  return {
    sync,
    destroy() {
      tablist.removeEventListener("click", click);
      tablist.removeEventListener("keydown", keydown);
    },
  };
}
