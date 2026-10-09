"use strict";

(() => {
  const HTTP_METHODS = new Set(["get", "put", "post", "delete", "options", "head", "patch", "trace"]);
  const ui = Object.fromEntries([
    "load-form", "api-key", "load-button", "clear-button", "status", "contract",
    "contract-title", "contract-description", "contract-version", "contract-notes",
    "search", "method", "tag", "result-count", "operations", "components",
  ].map((id) => [id, document.getElementById(id)]));
  let apiKey = "";
  let schema = null;
  let operations = [];
  let controller = null;
  let generation = 0;

  const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
  const text = (value) => typeof value === "string" ? value : JSON.stringify(value, null, 2);
  const make = (tag, value, className) => {
    const node = document.createElement(tag);
    if (value !== undefined) node.textContent = text(value);
    if (className) node.className = className;
    return node;
  };
  const resetView = () => {
    schema = null;
    operations = [];
    ui.contract.hidden = true;
    ui.operations.replaceChildren();
    ui.components.replaceChildren();
    ui["contract-notes"].replaceChildren();
    ui["contract-title"].textContent = "Contrato";
    ui["contract-description"].textContent = "";
    ui["contract-version"].textContent = "";
    ui["result-count"].textContent = "";
    ui.search.value = "";
    ui.method.replaceChildren(make("option", "Todos los métodos"));
    ui.method.options[0].value = "";
    ui.tag.replaceChildren(make("option", "Todos los grupos"));
    ui.tag.options[0].value = "";
  };
  const forgetKey = () => { apiKey = ""; ui["api-key"].value = ""; };
  const cancelLoad = () => {
    generation += 1;
    if (controller) controller.abort();
    controller = null;
    ui["load-button"].disabled = false;
    ui["load-form"].removeAttribute("aria-busy");
  };
  const closeDocumentation = () => {
    cancelLoad();
    forgetKey();
    resetView();
    ui.status.textContent = "Documentación cerrada. Clave borrada de la memoria del visor.";
  };

  function resolveLocalReference(ref) {
    if (typeof ref !== "string" || !ref.startsWith("#/")) return null;
    let cursor = schema;
    try {
      const pointer = decodeURIComponent(ref.slice(2));
      for (const part of pointer.split("/")) {
        const key = part.replace(/~1/g, "/").replace(/~0/g, "~");
        if (!isObject(cursor) || !Object.prototype.hasOwnProperty.call(cursor, key)) return null;
        cursor = cursor[key];
      }
      return cursor;
    } catch {
      return null;
    }
  }

  function appendJson(parent, label, value) {
    if (value === undefined) return;
    const details = make("details");
    details.append(make("summary", label), make("pre", value));
    parent.append(details);
    // Resolve each distinct reference only one level. Recursive schemas remain readable.
    const refs = new Set();
    const pending = [value];
    while (pending.length) {
      const current = pending.pop();
      if (Array.isArray(current)) pending.push(...current);
      else if (isObject(current)) {
        if (typeof current.$ref === "string") refs.add(current.$ref);
        pending.push(...Object.values(current));
      }
    }
    for (const ref of refs) {
      const resolved = resolveLocalReference(ref);
      const view = make("details");
      view.append(make("summary", `Referencia: ${ref}`));
      view.append(resolved === null
        ? make("p", "Referencia externa o no disponible. No se realiza ninguna descarga.")
        : make("pre", resolved));
      details.append(view);
    }
  }

  function appendExtensions(parent, item) {
    if (!isObject(item)) return;
    for (const [name, value] of Object.entries(item)) {
      if (name.startsWith("x-")) appendJson(parent, name, value);
    }
  }

  function appendParameters(parent, entry) {
    const parameters = [...(Array.isArray(entry.pathItem.parameters) ? entry.pathItem.parameters : []),
      ...(Array.isArray(entry.operation.parameters) ? entry.operation.parameters : [])];
    if (!parameters.length) return;
    parent.append(make("h3", "Parámetros de ruta, consulta y cabecera"));
    const wrapper = make("div", undefined, "table-wrap");
    const table = make("table");
    const head = make("thead");
    const headerRow = make("tr");
    for (const label of ["Nombre", "Ubicación", "Obligatorio", "Descripción y esquema"]) headerRow.append(make("th", label));
    head.append(headerRow);
    const body = make("tbody");
    for (const original of parameters) {
      const parameter = isObject(original) && original.$ref ? resolveLocalReference(original.$ref) : original;
      const row = make("tr");
      if (!isObject(parameter)) {
        const cell = make("td");
        cell.colSpan = 4;
        appendJson(cell, "Referencia de parámetro", original);
        row.append(cell);
      } else {
        row.append(make("td", parameter.name || "—"), make("td", parameter.in || "—"), make("td", parameter.required ? "Sí" : "No"));
        const cell = make("td");
        if (parameter.description) cell.append(make("p", parameter.description));
        appendJson(cell, "Definición", parameter);
        row.append(cell);
      }
      body.append(row);
    }
    table.append(head, body);
    wrapper.append(table);
    parent.append(wrapper);
  }

  function operationView(entry) {
    const operation = entry.operation;
    const details = make("details", undefined, "operation");
    const summary = make("summary");
    summary.append(make("span", entry.method.toUpperCase(), "method"), make("span", entry.path, "path"));
    if (operation.summary) summary.append(make("span", operation.summary, "operation-label"));
    details.append(summary);
    // Populate operation details only when opened; no network action is attached.
    details.addEventListener("toggle", () => {
      if (!details.open || details.dataset.rendered) return;
      details.dataset.rendered = "true";
      if (operation.operationId) details.append(make("p", `Operación: ${operation.operationId}`, "muted"));
      if (operation.description) details.append(make("p", operation.description));
      if (Array.isArray(operation.tags)) details.append(make("p", `Grupos: ${operation.tags.join(", ")}`, "muted"));
      if (operation.deprecated) details.append(make("p", "Operación marcada como obsoleta en el contrato.", "note"));
      const security = operation.security === undefined ? schema.security : operation.security;
      details.append(make("h3", "Autorización documentada"));
      if (!security || (Array.isArray(security) && !security.length)) details.append(make("p", "Sin requisito OpenAPI explícito. Consulta las notas de seguridad del contrato para la política efectiva."));
      else appendJson(details, "Requisitos de seguridad", security);
      appendParameters(details, entry);
      if (operation.requestBody !== undefined) {
        details.append(make("h3", "Cuerpo de la solicitud"));
        appendJson(details, "Tipos de contenido, esquema y ejemplos", operation.requestBody);
      }
      details.append(make("h3", "Respuestas documentadas"));
      if (isObject(operation.responses)) {
        for (const [code, response] of Object.entries(operation.responses)) appendJson(details, `HTTP ${code}`, response);
      } else details.append(make("p", "No hay respuestas declaradas."));
      appendJson(details, "Ejemplos de operación", operation.examples);
      appendExtensions(details, operation);
      appendExtensions(details, entry.pathItem);
    });
    return details;
  }

  function renderOperations() {
    const query = ui.search.value.toLocaleLowerCase().trim();
    const selected = operations.filter((entry) => (!ui.method.value || entry.method === ui.method.value)
      && (!ui.tag.value || entry.tags.includes(ui.tag.value)) && (!query || entry.search.includes(query)));
    ui.operations.replaceChildren(...selected.map(operationView));
    ui["result-count"].textContent = `${selected.length} de ${operations.length} operaciones.`;
    if (!selected.length) ui.operations.append(make("p", "No hay operaciones que coincidan con los filtros.", "panel"));
  }

  function renderContract(document) {
    schema = document;
    const info = isObject(document.info) ? document.info : {};
    ui["contract-title"].textContent = info.title || "Contrato OpenAPI";
    ui["contract-description"].textContent = info.description || "Contrato publicado por el candidato.";
    ui["contract-version"].textContent = `OpenAPI ${document.openapi} · Versión ${info.version || "sin declarar"}`;
    appendExtensions(ui["contract-notes"], document);
    appendExtensions(ui["contract-notes"], info);
    const methods = new Set();
    const tags = new Set();
    for (const [path, pathItem] of Object.entries(document.paths)) {
      if (!isObject(pathItem)) continue;
      for (const [method, operation] of Object.entries(pathItem)) {
        if (!HTTP_METHODS.has(method) || !isObject(operation)) continue;
        const groups = Array.isArray(operation.tags) ? operation.tags.filter((tag) => typeof tag === "string") : [];
        operations.push({path, pathItem, method, operation, tags: groups, search: `${path} ${method} ${JSON.stringify(operation)}`.toLocaleLowerCase()});
        methods.add(method);
        groups.forEach((tag) => tags.add(tag));
      }
    }
    for (const method of [...methods].sort()) { const option = make("option", method.toUpperCase()); option.value = method; ui.method.append(option); }
    for (const tag of [...tags].sort()) { const option = make("option", tag); option.value = tag; ui.tag.append(option); }
    if (isObject(document.components)) {
      for (const [kind, definitions] of Object.entries(document.components)) {
        const section = make("section", undefined, "component");
        section.append(make("h3", kind));
        if (isObject(definitions)) {
          for (const [name, value] of Object.entries(definitions)) appendJson(section, name, value);
        } else appendJson(section, "Definiciones", definitions);
        ui.components.append(section);
      }
    }
    renderOperations();
    ui.contract.hidden = false;
  }

  ui["load-form"].addEventListener("submit", async (event) => {
    event.preventDefault();
    cancelLoad();
    resetView();
    if (ui["api-key"].value) apiKey = ui["api-key"].value;
    ui["api-key"].value = "";
    const requestGeneration = generation;
    const activeController = new AbortController();
    controller = activeController;
    ui["load-button"].disabled = true;
    ui["load-form"].setAttribute("aria-busy", "true");
    ui.status.textContent = "Cargando el contrato local…";
    try {
      const headers = new Headers({Accept: "application/json"});
      if (apiKey) headers.set("X-Api-Key", apiKey);
      const response = await fetch("/openapi.json", {method: "GET", headers, cache: "no-store", credentials: "omit", redirect: "error", signal: activeController.signal});
      if (generation !== requestGeneration) return;
      if (!response.ok) {
        if (response.status === 401 || response.status === 403) {
          forgetKey();
          ui.status.textContent = "Acceso rechazado. La clave se ha borrado; introduce una clave válida para cargar la documentación.";
        } else ui.status.textContent = `No se pudo cargar el contrato (HTTP ${response.status}).`;
        return;
      }
      const document = await response.json();
      if (generation !== requestGeneration) return;
      if (!isObject(document) || typeof document.openapi !== "string" || !isObject(document.paths)) {
        ui.status.textContent = "La respuesta no contiene un documento OpenAPI compatible.";
        return;
      }
      renderContract(document);
      ui.status.textContent = "Contrato cargado. La exploración es de solo lectura; no ejecuta operaciones API.";
    } catch (error) {
      if (generation !== requestGeneration || error.name === "AbortError") return;
      resetView();
      ui.status.textContent = "No se pudo leer el contrato local. Comprueba la disponibilidad del servidor y vuelve a cargarlo cuando lo decidas.";
    } finally {
      if (generation === requestGeneration) {
        controller = null;
        ui["load-button"].disabled = false;
        ui["load-form"].removeAttribute("aria-busy");
      }
    }
  });
  ui["clear-button"].addEventListener("click", closeDocumentation);
  ui.search.addEventListener("input", renderOperations);
  ui.method.addEventListener("change", renderOperations);
  ui.tag.addEventListener("change", renderOperations);
  window.addEventListener("pagehide", () => { cancelLoad(); forgetKey(); resetView(); });
})();
