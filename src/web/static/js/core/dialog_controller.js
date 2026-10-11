/** One lifecycle and keyboard owner for application dialogs and the Bootstrap adapter. */
export class DialogController {
  constructor() {
    this.entries = new WeakMap();
    this.stack = [];
    this.lastOutsideFocus = document.activeElement;
    this.redirectingFocus = false;
    document.querySelectorAll('.modal-overlay[role="dialog"]').forEach((modal) => this.register(modal));
    this.backdropObserver = new MutationObserver(() => this._syncBackdrops());
    this.backdropObserver.observe(document.body, { childList: true });
    document.addEventListener("keydown", (event) => this._onKeyDown(event), true);
    document.addEventListener("focusin", (event) => {
      const targetModal = event.target.closest?.('.modal-overlay[role="dialog"]');
      if (targetModal && !targetModal.classList.contains("hidden") && !targetModal.hidden &&
          this.entries.get(targetModal)?.phase === "closed") this.open(targetModal);
      const top = this.stack.at(-1);
      if (!top) {
        this.lastOutsideFocus = event.target;
      } else if (top.modal.contains(event.target)) {
        top.lastFocus = event.target;
      } else if (!top.modal.contains(event.target) && !this.redirectingFocus && top.phase === "open") {
        this.redirectingFocus = true;
        this._focus(top);
        this.redirectingFocus = false;
      }
    });
  }

  register(modal) {
    if (this.entries.has(modal)) return this.entries.get(modal);
    const entry = { modal, phase: "closed", initialFocus: null, dismiss: null, waiters: [] };
    this.entries.set(modal, entry);
    if (window.bootstrap?.Modal) {
      // Native Bootstrap focus traps and Escape handlers compete with stacked dialogs.
      entry.adapter = window.bootstrap.Modal.getOrCreateInstance(modal, {
        backdrop: modal.id === "systemDialogModal" ? "static" : true,
        keyboard: false,
        focus: false,
      });
    }
    entry.observer = new MutationObserver(() => {
      const hidden = modal.classList.contains("hidden") || modal.hidden;
      if (hidden && (entry.phase === "open" || entry.phase === "opening")) this.close(modal);
      else if (hidden && entry.phase === "closing") {
        // A module click handler may run after Bootstrap's delegated dismissal.
        modal.hidden = false;
        modal.classList.remove("hidden");
      }
      else if (!hidden && entry.phase === "closed") this.open(modal);
    });
    entry.observer.observe(modal, { attributes: true, attributeFilter: ["class", "hidden"] });
    modal.addEventListener("shown.bs.modal", () => {
      entry.phase = "open";
      this._syncStack();
      if (entry.closeRequested) this._beginClose(entry);
      else if (this.isTop(modal)) this._focus(entry);
    });
    modal.addEventListener("hide.bs.modal", (event) => {
      if (!this.isTop(modal) && entry.phase !== "closing") {
        event.preventDefault();
        return;
      }
      entry.phase = "closing";
      modal.hidden = false;
      modal.classList.remove("hidden");
    });
    modal.addEventListener("hidden.bs.modal", () => this._finishClose(entry));
    // A parent overlay must not consume a click while a child dialog is open.
    modal.addEventListener("click", (event) => {
      if (!this.isTop(modal)) {
        event.preventDefault();
        event.stopImmediatePropagation();
      }
    }, true);
    if (!modal.classList.contains("hidden") && !modal.hidden) this.open(modal);
    return entry;
  }

  isTop(modal) {
    return this.stack.at(-1)?.modal === modal;
  }

  open(modal, { initialFocus = null, dismiss = null } = {}) {
    const entry = this.register(modal);
    entry.initialFocus = initialFocus;
    entry.dismiss = dismiss;
    if (entry.phase !== "closed") return;
    const active = document.activeElement;
    entry.previousFocus = modal.contains(active) ? this.stack.at(-1)?.lastFocus || this.lastOutsideFocus : active;
    entry.originalInert = modal.inert;
    entry.originalZIndex = modal.style.zIndex;
    entry.closeRequested = false;
    entry.phase = "opening";
    modal.hidden = false;
    modal.classList.remove("hidden");
    this.stack.push(entry);
    this._syncStack();
    if (entry.adapter) entry.adapter.show();
    else {
      modal.setAttribute("aria-modal", "true");
      modal.removeAttribute("aria-hidden");
      entry.phase = "open";
      this._focus(entry);
    }
  }

  close(modal) {
    const entry = this.register(modal);
    if (entry.phase === "closed") return Promise.resolve();
    const closed = new Promise((resolve) => entry.waiters.push(resolve));
    entry.closeRequested = true;
    if (entry.adapter && entry.phase === "opening") {
      // Bootstrap ignores hide() while its opening transition is in progress.
      modal.hidden = false;
      modal.classList.remove("hidden");
    } else if (entry.phase !== "closing") {
      this._beginClose(entry);
    }
    return closed;
  }

  _beginClose(entry) {
    entry.phase = "closing";
    if (entry.adapter) {
      // Keep the element renderable until Bootstrap finishes its hide transition.
      entry.modal.hidden = false;
      entry.modal.classList.remove("hidden");
      entry.adapter.hide();
    } else this._finishClose(entry);
  }

  _finishClose(entry) {
    if (entry.phase === "closed") return;
    const wasTop = this.isTop(entry.modal);
    entry.phase = "closed";
    entry.modal.classList.add("hidden");
    entry.modal.setAttribute("aria-hidden", "true");
    entry.modal.removeAttribute("aria-modal");
    entry.modal.inert = entry.originalInert;
    entry.modal.style.zIndex = entry.originalZIndex;
    this.stack = this.stack.filter((item) => item !== entry);
    this._syncStack();
    if (wasTop) {
      const parent = this.stack.at(-1);
      const target = entry.previousFocus;
      if (this._visible(target) && (!parent || parent.modal.contains(target))) target.focus();
      else if (parent) this._focus(parent);
    }
    const waiters = entry.waiters.splice(0);
    waiters.forEach((resolve) => resolve());
  }

  _syncStack() {
    this.stack.forEach((entry, index) => {
      entry.modal.inert = index !== this.stack.length - 1;
      entry.modal.style.zIndex = String(1055 + index * 20);
    });
    // Bootstrap removes this class when any dialog closes, including a child.
    document.body.classList.toggle("modal-open", this.stack.length > 0);
    this._syncBackdrops();
  }

  _syncBackdrops() {
    document.querySelectorAll(".modal-backdrop").forEach((backdrop, index) => {
      backdrop.style.zIndex = String(1050 + index * 20);
    });
  }

  _visible(element) {
    return element?.isConnected && !element.disabled && !element.closest('[hidden], .hidden, [inert]') && element.getClientRects().length > 0;
  }

  _focusables(modal) {
    return Array.from(modal.querySelectorAll('button, input:not([type="hidden"]), select, textarea, a[href], [tabindex]'))
      .filter((element) => element.tabIndex >= 0 && this._visible(element));
  }

  _focus(entry) {
    const preferred = typeof entry.initialFocus === "function" ? entry.initialFocus() : entry.initialFocus;
    const items = this._focusables(entry.modal);
    const target = this._visible(preferred) ? preferred : items.find((element) => !element.matches(".modal-close, .modal-close-btn, .btn-close")) || items[0];
    if (target) target.focus();
    else {
      entry.modal.tabIndex = -1;
      entry.modal.focus();
    }
  }

  _onKeyDown(event) {
    const entry = this.stack.at(-1);
    if (!entry) return;
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (entry.phase === "closing") return;
      if (entry.dismiss) entry.dismiss();
      else {
        const close = entry.modal.querySelector(".modal-close, .modal-close-btn, .btn-close");
        if (close) close.click();
        else this.close(entry.modal);
      }
    } else if (event.key === "Tab") {
      const items = this._focusables(entry.modal);
      const first = items[0];
      const last = items.at(-1);
      if (!first || !entry.modal.contains(document.activeElement) ||
          (event.shiftKey && document.activeElement === first) || (!event.shiftKey && document.activeElement === last)) {
        event.preventDefault();
        event.stopImmediatePropagation();
        (event.shiftKey ? last : first)?.focus();
        if (!first) this._focus(entry);
      }
    }
  }
}
