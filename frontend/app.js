// Ops panel for the forecast service. Polls /stats for rolling request
// metrics and lets the user fire a live /v1/forecast request from the browser.
// No build step, no dependencies — kept simple on purpose for a demo panel.

// Three ways this page gets served: opened straight off disk, served by a
// separate static server in local dev (any port), or served from the same
// origin as the API in a container. Only the last can assume same-origin, so
// treat "served from a port that isn't the API's" as local dev.
// On a static host (Vercel) there is no API on this origin, so the backend
// URL comes from ?api=https://host — or edit API_FALLBACK below once the
// backend has a permanent home.
const API_PORT = "8000";
const API_FALLBACK = "";
const apiParam = new URLSearchParams(window.location.search).get("api");
const servedFromApi =
  window.location.protocol.startsWith("http") &&
  (window.location.port === API_PORT || window.location.port === "");
const API_BASE =
  (apiParam && apiParam.replace(/\/$/, "")) ||
  (servedFromApi ? window.location.origin : "") ||
  API_FALLBACK ||
  `http://localhost:${API_PORT}`;

document.getElementById("endpoint-label").textContent = API_BASE;

const el = (id) => document.getElementById(id);
const statusDot = el("status-dot");
const statusText = el("status-text");

function setStatus(ok) {
  statusDot.classList.toggle("ok", ok);
  statusDot.classList.toggle("bad", !ok);
  statusText.textContent = ok ? "LIVE" : "UNREACHABLE";
}

function formatUptime(seconds) {
  if (seconds == null) return "—";
  const s = Math.floor(seconds);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h > 0) return `${h}h ${m}m`;
  if (m > 0) return `${m}m ${sec}s`;
  return `${sec}s`;
}

function drawSparkline(svgId, points, color) {
  const svg = el(svgId);
  const w = 600, h = 140, pad = 10;
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.innerHTML = "";

  if (!points.length) {
    const text = document.createElementNS("http://www.w3.org/2000/svg", "text");
    text.setAttribute("x", w / 2);
    text.setAttribute("y", h / 2);
    text.setAttribute("text-anchor", "middle");
    text.setAttribute("fill", "#5c6472");
    text.setAttribute("font-size", "11");
    text.setAttribute("font-family", "IBM Plex Mono, monospace");
    text.textContent = "no data yet";
    svg.appendChild(text);
    return;
  }

  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const range = Math.max(max - min, 1);
  const stepX = points.length > 1 ? (w - pad * 2) / (points.length - 1) : 0;

  const coords = points.map((v, i) => {
    const x = pad + i * stepX;
    const y = h - pad - ((v - min) / range) * (h - pad * 2);
    return [x, y];
  });

  const linePath = coords.map((c, i) => `${i === 0 ? "M" : "L"} ${c[0].toFixed(1)} ${c[1].toFixed(1)}`).join(" ");
  const areaPath = `${linePath} L ${coords[coords.length - 1][0].toFixed(1)} ${h - pad} L ${coords[0][0].toFixed(1)} ${h - pad} Z`;

  const ns = "http://www.w3.org/2000/svg";

  const area = document.createElementNS(ns, "path");
  area.setAttribute("d", areaPath);
  area.setAttribute("fill", color);
  area.setAttribute("fill-opacity", "0.12");
  area.setAttribute("stroke", "none");
  svg.appendChild(area);

  const line = document.createElementNS(ns, "path");
  line.setAttribute("d", linePath);
  line.setAttribute("fill", "none");
  line.setAttribute("stroke", color);
  line.setAttribute("stroke-width", "2");
  line.setAttribute("stroke-linejoin", "round");
  line.setAttribute("stroke-linecap", "round");
  svg.appendChild(line);

  coords.forEach(([x, y]) => {
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", x);
    dot.setAttribute("cy", y);
    dot.setAttribute("r", "2.5");
    dot.setAttribute("fill", color);
    svg.appendChild(dot);
  });
}

function renderLog(requests) {
  const stream = el("log-stream");
  if (!requests.length) {
    stream.innerHTML = `<div class="log-empty">waiting for traffic…</div>`;
    return;
  }
  stream.innerHTML = requests
    .map((r) => {
      const ok = r.status_code < 400;
      const time = new Date(r.timestamp * 1000).toLocaleTimeString();
      return `<div class="log-row ${ok ? "ok" : "err"}">
        <span>${time}</span>
        <span>${r.method} ${r.route}</span>
        <span class="lr-code">${r.status_code}</span>
        <span class="lr-lat">${r.latency_ms.toFixed(1)}ms</span>
      </div>`;
    })
    .join("");
}

async function poll() {
  try {
    const res = await fetch(`${API_BASE}/stats`);
    if (!res.ok) throw new Error("bad status");
    const data = await res.json();
    setStatus(true);

    el("val-uptime").textContent = formatUptime(data.uptime_seconds);
    el("val-requests").textContent = data.recent_request_count;
    el("val-errors").textContent = data.recent_error_count;
    el("val-latency").innerHTML = `${data.avg_latency_ms}<small>ms</small>`;

    el("gauge-errors").classList.toggle("has-errors", data.recent_error_count > 0);

    const latencies = [...data.recent_requests].reverse().map((r) => r.latency_ms);
    drawSparkline("latency-scope", latencies, "#52d6c9");
    renderLog(data.recent_requests);
  } catch (err) {
    setStatus(false);
  }
}

async function runForecast() {
  const btn = el("run-forecast");
  const resultEl = el("try-result");
  const seriesRaw = el("series-input").value;
  const horizon = parseInt(el("horizon-input").value, 10);

  const series = seriesRaw
    .split(",")
    .map((v) => parseFloat(v.trim()))
    .filter((v) => !Number.isNaN(v));

  if (series.length < 4) {
    resultEl.textContent = "Need at least 4 numeric points in the series.";
    resultEl.classList.add("err");
    return;
  }

  btn.disabled = true;
  btn.textContent = "RUNNING…";
  resultEl.classList.remove("err");
  resultEl.textContent = "";

  try {
    const res = await fetch(`${API_BASE}/v1/forecast`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ series, horizon }),
    });
    const data = await res.json();

    if (!res.ok) {
      resultEl.textContent = data.detail || "Request failed.";
      resultEl.classList.add("err");
      drawSparkline("forecast-plot", [], "#ffb020");
      return;
    }

    resultEl.textContent = `fit in ${(data.model_fit_seconds * 1000).toFixed(1)}ms · model ${data.model_version}`;
    drawSparkline("forecast-plot", [...series, ...data.forecast], "#ffb020");
    poll(); // refresh stats immediately after a manual request
  } catch (err) {
    resultEl.textContent = "Could not reach the service. Is it running?";
    resultEl.classList.add("err");
  } finally {
    btn.disabled = false;
    btn.textContent = "RUN";
  }
}

el("run-forecast").addEventListener("click", runForecast);

drawSparkline("latency-scope", [], "#52d6c9");
drawSparkline("forecast-plot", [], "#ffb020");
poll();
setInterval(poll, 4000);
