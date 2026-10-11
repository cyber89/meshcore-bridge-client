/** Field-linked feedback for explicitly submitted forms. No values enter markup. */
export class FormFeedback {
  constructor(form, fields, errorFields = {}) {
    this.form = form;
    this.fields = fields;
    this.errorFields = errorFields;
    this.busy = false;
    this.errors = new Map();
    this.submitStates = new Map();
    form.noValidate = true;
    this.summary = document.createElement("p");
    this.summary.id = `${form.id}-feedback`;
    this.summary.className = "form-feedback-summary";
    this.summary.setAttribute("role", "alert");
    this.summary.tabIndex = -1;
    this.summary.hidden = true;
    form.prepend(this.summary);
    this._describe(form, this.summary.id);
    for (const field of new Set(Object.values(fields).filter(Boolean))) {
      const group = field.closest(".form-group");
      group?.querySelectorAll(".field-hint").forEach((hint, index) => {
        if (!hint.id) hint.id = `${field.id}-hint-${index}`;
        this._describe(field, hint.id);
      });
      const error = document.createElement("p");
      error.id = `${field.id}-error`;
      error.className = "field-error";
      error.hidden = true;
      (group || field.parentElement).appendChild(error);
      this.errors.set(field, error);
      field.addEventListener("input", () => this.clearField(field));
      field.addEventListener("change", () => this.clearField(field));
    }
  }

  _describe(element, id) {
    const descriptions = new Set((element.getAttribute("aria-describedby") || "").split(/\s+/).filter(Boolean));
    descriptions.add(id);
    element.setAttribute("aria-describedby", [...descriptions].join(" "));
  }

  clearField(field) {
    const error = this.errors.get(field);
    if (!error) return;
    error.hidden = true;
    error.textContent = "";
    error.removeAttribute("data-i18n");
    field.removeAttribute("aria-invalid");
    const descriptions = (field.getAttribute("aria-describedby") || "").split(/\s+/).filter((id) => id && id !== error.id);
    if (descriptions.length) field.setAttribute("aria-describedby", descriptions.join(" "));
    else field.removeAttribute("aria-describedby");
  }

  clear() {
    for (const field of this.errors.keys()) this.clearField(field);
    this.summary.hidden = true;
    this.summary.textContent = "";
    this.summary.removeAttribute("data-i18n");
  }

  fieldError(field, message, translationKey = null) {
    const error = this.errors.get(field);
    if (!error) return;
    error.removeAttribute("data-i18n");
    if (translationKey) I18n.setText(error, translationKey);
    else error.textContent = message;
    error.hidden = false;
    field.setAttribute("aria-invalid", "true");
    this._describe(field, error.id);
  }

  validate(customErrors = {}) {
    this.clear();
    for (const [name, field] of Object.entries(this.fields)) {
      if (!field || !field.willValidate) continue;
      const invalid = !field.checkValidity();
      const translationKey = invalid
        ? field.validity.valueMissing ? "forms.required" : "forms.invalid_value"
        : customErrors[name];
      if (translationKey) this.fieldError(field, "", translationKey);
    }
    return !this.focusInvalid();
  }

  focusInvalid() {
    const field = [...this.errors.keys()].find((item) => item.getAttribute("aria-invalid") === "true");
    field?.focus();
    return Boolean(field);
  }

  networkError() {
    I18n.setText(this.summary, "forms.network_error");
    this.summary.hidden = false;
    this.summary.focus();
  }

  serverError(data) {
    const messages = [];
    const detail = data?.detail;
    if (Array.isArray(detail)) {
      for (const issue of detail) {
        const message = typeof issue?.msg === "string" ? issue.msg : I18n.t("forms.invalid_value");
        const location = Array.isArray(issue?.loc) ? issue.loc.filter((part) => part !== "body") : [];
        const field = location.length === 1 ? this.fields[location[0]] : null;
        if (field) this.fieldError(field, message);
        messages.push(message);
      }
    } else {
      const message = [detail, data?.message].find((value) => typeof value === "string" && value.trim());
      if (message) messages.push(message);
      const field = this.fields[this.errorFields[data?.error]];
      if (field) this.fieldError(field, message || I18n.t("forms.invalid_value"));
    }
    this.summary.removeAttribute("data-i18n");
    if (messages.length) this.summary.textContent = [...new Set(messages)].join(" ");
    else I18n.setText(this.summary, "forms.request_failed");
    this.summary.hidden = false;
    if (!this.focusInvalid()) this.summary.focus();
  }

  setBusy(busy) {
    this.busy = busy;
    this.form.setAttribute("aria-busy", String(busy));
    if (busy) {
      for (const button of this.form.querySelectorAll('button[type="submit"]')) {
        this.submitStates.set(button, button.disabled);
        button.disabled = true;
      }
    } else {
      for (const [button, disabled] of this.submitStates) button.disabled = disabled;
      this.submitStates.clear();
    }
  }
}
