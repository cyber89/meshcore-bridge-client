/**
 * chart_engine.js — Motor de Gráficos SVG Nativo y Ultraligero (Zero-Dependency)
 * ─────────────────────────────────────────────────────────────────────────────
 * Gráficos interactivos, accesibles y fluidos para MeshCore Bridge:
 * - renderAreaChart: Series temporales con degradados semánticos y hover interactivo.
 * - renderDonutChart: Gráfico de anillo interactivo con leyenda y porcentajes.
 * - renderHorizontalBarChart: Comparativa de barras con etiquetas y métricas relativas.
 * - renderSparkline: Micro-gráficos de tendencia para tarjetas KPI.
 *
 * Cumple con WCAG 2.2 AA, variables CSS de tema (tokens.css) y cero dependencias externas.
 */

import { escapeHtml } from "./utils.js";

/**
 * Obtiene el valor computado de una variable CSS o un fallback seguro.
 */
function getCssVar(varName, fallback = "#3b82f6") {
  if (typeof window === "undefined" || !document.documentElement) return fallback;
  const val = getComputedStyle(document.documentElement).getPropertyValue(varName).trim();
  return val || fallback;
}

/**
 * Formatea una marca de tiempo epoch a formato de hora legible (HH:mm).
 */
function formatTime(epochSec) {
  if (!epochSec) return "--:--";
  const d = new Date(epochSec * 1000);
  const h = String(d.getHours()).padStart(2, "0");
  const m = String(d.getMinutes()).padStart(2, "0");
  return `${h}:${m}`;
}

/**
 * Genera un ID único para elementos SVG (degradados, máscaras, clips).
 */
let uidCounter = 0;
function getUniqueId(prefix = "chart") {
  uidCounter += 1;
  return `${prefix}_${Date.now()}_${uidCounter}`;
}

/**
 * Renderiza un gráfico de área / líneas temporales interactivo en un contenedor DOM.
 * @param {HTMLElement} container Contenedor donde se insertará el gráfico
 * @param {Object} options Opciones de configuración
 */
export function renderAreaChart(container, options = {}) {
  if (!container) return;
  container.innerHTML = "";

  const points = options.points || [];
  const series = options.series || [
    { key: "rx", label: "RX (Recibidos)", color: "var(--accent-primary, #3b82f6)" },
    { key: "tx", label: "TX (Transmitidos)", color: "var(--accent-success, #10b981)" },
  ];

  if (!points || points.length === 0) {
    container.innerHTML = `<div class="chart-empty-state"><span class="text-muted text-sm">${escapeHtml(options.emptyText || I18n.t("analytics.no_traffic_data"))}</span></div>`;
    return;
  }

  const width = 800;
  const height = 240;
  const padLeft = 46;
  const padRight = 16;
  const padTop = 16;
  const padBottom = 32;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  // Calcular valor máximo entre todas las series
  let maxVal = 1;
  points.forEach((pt) => {
    series.forEach((s) => {
      const v = Number(pt[s.key] || 0);
      if (v > maxVal) maxVal = v;
    });
  });
  // Añadir 15% de holgura superior
  maxVal = Math.ceil(maxVal * 1.15) || 5;

  const n = points.length;
  const getX = (idx) => padLeft + (idx / Math.max(n - 1, 1)) * chartW;
  const getY = (val) => padTop + chartH - (Math.min(val, maxVal) / maxVal) * chartH;

  const gradRxId = getUniqueId("grad_rx");
  const gradTxId = getUniqueId("grad_tx");

  // Construir SVG
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "chart-svg-area");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", options.ariaLabel || "Gráfico de tráfico LoRa RX vs TX");

  // 1. Defs (Degradados semánticos)
  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  defs.innerHTML = `
    <linearGradient id="${gradRxId}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--accent-primary, #3b82f6)" stop-opacity="0.35"/>
      <stop offset="100%" stop-color="var(--accent-primary, #3b82f6)" stop-opacity="0.0"/>
    </linearGradient>
    <linearGradient id="${gradTxId}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0%" stop-color="var(--accent-success, #10b981)" stop-opacity="0.30"/>
      <stop offset="100%" stop-color="var(--accent-success, #10b981)" stop-opacity="0.0"/>
    </linearGradient>
  `;
  svg.appendChild(defs);

  // 2. Líneas de Rejilla y Etiquetas de Eje Y (4 niveles)
  const gridG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  gridG.setAttribute("class", "chart-grid");
  const yTicks = 4;
  for (let i = 0; i <= yTicks; i++) {
    const yVal = Math.round((maxVal / yTicks) * i);
    const yPos = getY(yVal);

    // Línea horizontal
    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", padLeft);
    line.setAttribute("y1", yPos);
    line.setAttribute("x2", width - padRight);
    line.setAttribute("y2", yPos);
    line.setAttribute("stroke", "var(--border-subtle, rgba(255,255,255,0.08))");
    line.setAttribute("stroke-dasharray", i === 0 ? "none" : "3,3");
    line.setAttribute("stroke-width", "1");
    gridG.appendChild(line);

    // Etiqueta Y
    const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    txt.setAttribute("x", padLeft - 8);
    txt.setAttribute("y", yPos + 3.5);
    txt.setAttribute("text-anchor", "end");
    txt.setAttribute("fill", "var(--text-muted, #94a3b8)");
    txt.setAttribute("font-size", "11");
    txt.setAttribute("font-family", "var(--font-mono, monospace)");
    txt.textContent = yVal.toLocaleString();
    gridG.appendChild(txt);
  }
  svg.appendChild(gridG);

  // 3. Eje X y Etiquetas de tiempo (5 intervalos equidistantes)
  const xG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  xG.setAttribute("class", "chart-axis-x");
  const xTicksCount = Math.min(6, n);
  for (let i = 0; i < xTicksCount; i++) {
    const idx = Math.round((i / (xTicksCount - 1)) * (n - 1));
    const pt = points[idx];
    if (!pt) continue;

    const xPos = getX(idx);
    const timeLabel = formatTime(pt.timestamp);

    const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    txt.setAttribute("x", xPos);
    txt.setAttribute("y", height - 10);
    txt.setAttribute("text-anchor", i === 0 ? "start" : (i === xTicksCount - 1 ? "end" : "middle"));
    txt.setAttribute("fill", "var(--text-muted, #94a3b8)");
    txt.setAttribute("font-size", "11");
    txt.setAttribute("font-family", "var(--font-mono, monospace)");
    txt.textContent = timeLabel;
    xG.appendChild(txt);
  }
  svg.appendChild(xG);

  // 4. Dibujar Áreas y Líneas para cada serie
  series.forEach((s) => {
    const gradId = s.key === "rx" ? gradRxId : gradTxId;

    // Construir d para el path
    let pathD = "";
    let areaD = "";

    points.forEach((pt, idx) => {
      const x = getX(idx);
      const val = Number(pt[s.key] || 0);
      const y = getY(val);

      if (idx === 0) {
        pathD += `M ${x.toFixed(1)} ${y.toFixed(1)}`;
        areaD += `M ${x.toFixed(1)} ${getY(0).toFixed(1)} L ${x.toFixed(1)} ${y.toFixed(1)}`;
      } else {
        pathD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
        areaD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
      }
    });

    const lastX = getX(n - 1);
    const zeroY = getY(0);
    areaD += ` L ${lastX.toFixed(1)} ${zeroY.toFixed(1)} Z`;

    // Path de relleno degradado
    const areaPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    areaPath.setAttribute("d", areaD);
    areaPath.setAttribute("fill", `url(#${gradId})`);
    areaPath.setAttribute("class", `chart-area-${s.key}`);
    svg.appendChild(areaPath);

    // Path de la línea superior
    const linePath = document.createElementNS("http://www.w3.org/2000/svg", "path");
    linePath.setAttribute("d", pathD);
    linePath.setAttribute("fill", "none");
    linePath.setAttribute("stroke", s.color);
    linePath.setAttribute("stroke-width", "2");
    linePath.setAttribute("stroke-linecap", "round");
    linePath.setAttribute("stroke-linejoin", "round");
    linePath.setAttribute("class", `chart-line-${s.key}`);
    svg.appendChild(linePath);
  });

  // 5. Capa interactiva de Hover / Guía vertical
  const guideLine = document.createElementNS("http://www.w3.org/2000/svg", "line");
  guideLine.setAttribute("y1", padTop);
  guideLine.setAttribute("y2", padTop + chartH);
  guideLine.setAttribute("stroke", "var(--text-muted, #94a3b8)");
  guideLine.setAttribute("stroke-width", "1");
  guideLine.setAttribute("stroke-dasharray", "2,2");
  guideLine.style.display = "none";
  svg.appendChild(guideLine);

  container.appendChild(svg);

  // 6. Tooltip Flotante en HTML para alta fidelidad
  const tooltip = document.createElement("div");
  tooltip.className = "chart-tooltip hidden";
  container.appendChild(tooltip);

  // Escuchadores táctiles y de ratón
  const onMove = (clientX) => {
    const rect = svg.getBoundingClientRect();
    const relX = clientX - rect.left;
    const svgX = (relX / rect.width) * width;

    if (svgX < padLeft || svgX > width - padRight) {
      guideLine.style.display = "none";
      tooltip.classList.add("hidden");
      return;
    }

    // Encontrar el punto más cercano
    const ratio = (svgX - padLeft) / chartW;
    const nearestIdx = Math.max(0, Math.min(n - 1, Math.round(ratio * (n - 1))));
    const pt = points[nearestIdx];
    if (!pt) return;

    const snapX = getX(nearestIdx);
    guideLine.setAttribute("x1", snapX);
    guideLine.setAttribute("x2", snapX);
    guideLine.style.display = "block";

    // Formatear Tooltip
    const timeStr = formatTime(pt.timestamp);
    const rxVal = Number(pt.rx || 0);
    const txVal = Number(pt.tx || 0);
    const floodVal = pt.flood != null ? Number(pt.flood) : null;
    const directVal = pt.direct != null ? Number(pt.direct) : null;
    const errVal = Number(pt.errors || 0);

    let html = `
      <div class="tooltip-time">⏱️ ${timeStr}</div>
      <div class="tooltip-row"><span class="dot-indicator" style="background: var(--accent-primary, #3b82f6);"></span> RX: <strong>${rxVal.toLocaleString()}</strong></div>
      <div class="tooltip-row"><span class="dot-indicator" style="background: var(--accent-success, #10b981);"></span> TX: <strong>${txVal.toLocaleString()}</strong></div>
    `;

    if (floodVal !== null && directVal !== null) {
      html += `
        <div class="tooltip-sub text-xs">Direct: ${directVal} | Flood: ${floodVal}</div>
      `;
    }
    if (errVal > 0) {
      html += `<div class="tooltip-row text-danger"><span class="dot-indicator bg-danger"></span> Errores: <strong>${errVal}</strong></div>`;
    }

    tooltip.innerHTML = html;
    tooltip.classList.remove("hidden");

    // Posicionar tooltip relativo al contenedor
    const leftPx = (snapX / width) * rect.width;
    const isRightHalf = snapX > width / 2;
    tooltip.style.left = isRightHalf ? `${leftPx - 130}px` : `${leftPx + 15}px`;
    tooltip.style.top = "20px";
  };

  svg.addEventListener("mousemove", (e) => onMove(e.clientX));
  svg.addEventListener("mouseleave", () => {
    guideLine.style.display = "none";
    tooltip.classList.add("hidden");
  });

  svg.addEventListener("touchmove", (e) => {
    if (e.touches && e.touches[0]) onMove(e.touches[0].clientX);
  }, { passive: true });
  svg.addEventListener("touchend", () => {
    guideLine.style.display = "none";
    tooltip.classList.add("hidden");
  });
}

/**
 * Renderiza un gráfico Donut SVG interactivo con leyenda semántica.
 * @param {HTMLElement} container Contenedor DOM
 * @param {Object} options Opciones de configuración
 */
export function renderDonutChart(container, options = {}) {
  if (!container) return;
  container.innerHTML = "";

  const data = options.data || [];
  const total = data.reduce((acc, d) => acc + (Number(d.value) || 0), 0);

  const wrapper = document.createElement("div");
  wrapper.className = "donut-chart-wrapper";

  const size = 180;
  const strokeWidth = 26;
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${size} ${size}`);
  svg.setAttribute("class", "donut-chart-svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", options.ariaLabel || "Distribución por tipo de paquete");

  if (total === 0) {
    // Estado vacío: Círculo tenue
    const bgCircle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    bgCircle.setAttribute("cx", size / 2);
    bgCircle.setAttribute("cy", size / 2);
    bgCircle.setAttribute("r", radius);
    bgCircle.setAttribute("fill", "none");
    bgCircle.setAttribute("stroke", "var(--border-subtle, rgba(255,255,255,0.1))");
    bgCircle.setAttribute("stroke-width", strokeWidth);
    svg.appendChild(bgCircle);

    const txt = document.createElementNS("http://www.w3.org/2000/svg", "text");
    txt.setAttribute("x", size / 2);
    txt.setAttribute("y", size / 2 + 5);
    txt.setAttribute("text-anchor", "middle");
    txt.setAttribute("fill", "var(--text-muted, #94a3b8)");
    txt.setAttribute("font-size", "12");
    txt.textContent = options.emptyText || "0 tramas";
    svg.appendChild(txt);

    wrapper.appendChild(svg);
    container.appendChild(wrapper);
    return;
  }

  let accumulatedOffset = 0;

  // Dibujar cada segmento circular
  data.forEach((item) => {
    const val = Number(item.value) || 0;
    if (val <= 0) return;

    const pct = val / total;
    const strokeDash = pct * circumference;
    const gap = circumference - strokeDash;

    const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    circle.setAttribute("cx", size / 2);
    circle.setAttribute("cy", size / 2);
    circle.setAttribute("r", radius);
    circle.setAttribute("fill", "none");
    circle.setAttribute("stroke", item.color);
    circle.setAttribute("stroke-width", strokeWidth);
    circle.setAttribute("stroke-dasharray", `${strokeDash.toFixed(2)} ${gap.toFixed(2)}`);
    circle.setAttribute("stroke-dashoffset", (-accumulatedOffset).toFixed(2));
    circle.setAttribute("class", "donut-segment");
    circle.style.transformOrigin = "50% 50%";
    circle.style.transform = "rotate(-90deg)";
    circle.style.transition = "stroke-width 0.2s ease, opacity 0.2s ease";

    // Tooltip nativo SVG
    const titleEl = document.createElementNS("http://www.w3.org/2000/svg", "title");
    titleEl.textContent = `${item.label}: ${val.toLocaleString()} (${(pct * 100).toFixed(1)}%)`;
    circle.appendChild(titleEl);

    // Efecto hover
    circle.addEventListener("mouseenter", () => {
      circle.setAttribute("stroke-width", strokeWidth + 4);
      centerSub.textContent = item.label;
      centerVal.textContent = `${(pct * 100).toFixed(1)}%`;
    });
    circle.addEventListener("mouseleave", () => {
      circle.setAttribute("stroke-width", strokeWidth);
      centerSub.textContent = options.centerLabel || "Total";
      centerVal.textContent = total.toLocaleString();
    });

    svg.appendChild(circle);
    accumulatedOffset += strokeDash;
  });

  // Texto central (Total o Segmento)
  const centerG = document.createElementNS("http://www.w3.org/2000/svg", "g");
  centerG.setAttribute("class", "donut-center-group");

  const centerVal = document.createElementNS("http://www.w3.org/2000/svg", "text");
  centerVal.setAttribute("x", size / 2);
  centerVal.setAttribute("y", size / 2);
  centerVal.setAttribute("text-anchor", "middle");
  centerVal.setAttribute("fill", "var(--text-bright, #ffffff)");
  centerVal.setAttribute("font-size", "18");
  centerVal.setAttribute("font-weight", "700");
  centerVal.textContent = total.toLocaleString();

  const centerSub = document.createElementNS("http://www.w3.org/2000/svg", "text");
  centerSub.setAttribute("x", size / 2);
  centerSub.setAttribute("y", size / 2 + 18);
  centerSub.setAttribute("text-anchor", "middle");
  centerSub.setAttribute("fill", "var(--text-muted, #94a3b8)");
  centerSub.setAttribute("font-size", "11");
  centerSub.textContent = options.centerLabel || "Total";

  centerG.appendChild(centerVal);
  centerG.appendChild(centerSub);
  svg.appendChild(centerG);

  wrapper.appendChild(svg);

  // Leyenda en HTML modular
  const legend = document.createElement("div");
  legend.className = "donut-legend-grid";

  data.forEach((item) => {
    const val = Number(item.value) || 0;
    const pct = total > 0 ? ((val / total) * 100).toFixed(1) : "0.0";

    const itemEl = document.createElement("div");
    itemEl.className = "donut-legend-item";
    itemEl.innerHTML = `
      <span class="legend-color-dot" style="background: ${item.color};"></span>
      <span class="legend-label">${escapeHtml(item.label)}</span>
      <span class="legend-pct font-mono">${pct}%</span>
      <span class="legend-val font-mono text-muted">(${val.toLocaleString()})</span>
    `;
    legend.appendChild(itemEl);
  });

  wrapper.appendChild(legend);
  container.appendChild(wrapper);
}

/**
 * Renderiza barras comparativas horizontales (e.g. Eficiencia Flood vs Direct o Errores).
 * @param {HTMLElement} container Contenedor DOM
 * @param {Array} items Lista de { label, value, color, icon, detail }
 */
export function renderHorizontalBarChart(container, items = []) {
  if (!container) return;
  container.innerHTML = "";

  if (!items || items.length === 0) {
    container.innerHTML = `<div class="chart-empty-state"><span class="text-muted text-sm">${escapeHtml(I18n.t("analytics.no_comparison_data"))}</span></div>`;
    return;
  }

  const maxVal = Math.max(...items.map((i) => Number(i.value) || 0), 1);
  const list = document.createElement("div");
  list.className = "bar-chart-list";

  items.forEach((item) => {
    const val = Number(item.value) || 0;
    const pct = Math.min((val / maxVal) * 100, 100);

    const row = document.createElement("div");
    row.className = "bar-chart-row";
    row.innerHTML = `
      <div class="bar-header">
        <span class="bar-label">${item.icon ? `<span class="bar-icon">${item.icon}</span> ` : ""}${escapeHtml(item.label)}</span>
        <span class="bar-value font-mono font-semibold">${val.toLocaleString()} ${item.detail ? `<small class="text-muted">(${escapeHtml(item.detail)})</small>` : ""}</span>
      </div>
      <div class="bar-track">
        <div class="bar-fill" style="width: ${pct.toFixed(1)}%; background: ${item.color};"></div>
      </div>
    `;
    list.appendChild(row);
  });

  container.appendChild(list);
}

/**
 * Renderiza una micro-curva Sparkline SVG para tarjetas KPI.
 * @param {HTMLElement} container Contenedor
 * @param {Array<number>} values Lista de valores numéricos
 * @param {string} color Color de la línea (CSS var o hex)
 */
export function renderSparkline(container, values = [], color = "var(--accent-primary, #3b82f6)") {
  if (!container) return;
  container.innerHTML = "";

  if (!values || values.length < 2) return;

  const width = 100;
  const height = 28;
  const maxVal = Math.max(...values, 1);
  const minVal = Math.min(...values, 0);
  const range = maxVal - minVal || 1;

  const n = values.length;
  const getX = (i) => (i / (n - 1)) * width;
  const getY = (v) => height - 3 - ((v - minVal) / range) * (height - 6);

  let pathD = "";
  let areaD = "";

  values.forEach((v, i) => {
    const x = getX(i);
    const y = getY(v);
    if (i === 0) {
      pathD += `M ${x.toFixed(1)} ${y.toFixed(1)}`;
      areaD += `M ${x.toFixed(1)} ${height} L ${x.toFixed(1)} ${y.toFixed(1)}`;
    } else {
      pathD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
      areaD += ` L ${x.toFixed(1)} ${y.toFixed(1)}`;
    }
  });

  areaD += ` L ${width} ${height} Z`;

  const gradId = getUniqueId("spark_grad");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
  svg.setAttribute("class", "sparkline-svg");
  svg.setAttribute("aria-hidden", "true");

  svg.innerHTML = `
    <defs>
      <linearGradient id="${gradId}" x1="0" y1="0" x2="0" y2="1">
        <stop offset="0%" stop-color="${color}" stop-opacity="0.35"/>
        <stop offset="100%" stop-color="${color}" stop-opacity="0.0"/>
      </linearGradient>
    </defs>
    <path d="${areaD}" fill="url(#${gradId})" />
    <path d="${pathD}" fill="none" stroke="${color}" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" />
  `;

  container.appendChild(svg);
}
