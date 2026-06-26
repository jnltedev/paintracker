const state = {
  selectedDate: toISODate(new Date()),
  cursor: new Date(),
  entries: new Map(),
  allEntries: new Map(),
  profile: {},
  autosaveReady: false,
  entryAutosaveTimer: null,
  profileAutosaveTimer: null,
};

const AUTOSAVE_DELAY = 800;
const APP_VERSION = "1.0.0";
const GITHUB_OWNER = "jnltedev";
const GITHUB_REPO = "paintracker";
const REQUIRED_ENTRY_FIELDS = [
  "pain_morning",
  "pain_noon",
  "pain_evening",
  "pain_night",
  "symptoms",
  "triggers",
  "wellbeing",
  "medication",
  "weather",
  "temperature",
];

const monthTitle = document.querySelector("#monthTitle");
const calendarEl = document.querySelector("#calendar");
const selectedDateLabel = document.querySelector("#selectedDateLabel");
const entryMetaEl = document.querySelector("#entryMeta");
const dashboardStatsEl = document.querySelector("#dashboardStats");
const dashboardChartEl = document.querySelector("#dashboardChart");
const appVersionEl = document.querySelector("#appVersion");
const updateToastEl = document.querySelector("#updateToast");
const entryForm = document.querySelector("#entryForm");
const profileForm = document.querySelector("#profileForm");
const entryStatus = document.querySelector("#entryStatus");
const profileStatus = document.querySelector("#profileStatus");
const deleteButton = document.querySelector("#deleteEntry");
const prevMonthButton = document.querySelector("#prevMonth");
const nextMonthButton = document.querySelector("#nextMonth");

const TODAY = toISODate(new Date());

appVersionEl.textContent = `Version v${APP_VERSION}`;

function toISODate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("de-DE", {
    weekday: "long",
    day: "2-digit",
    month: "long",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function formToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) {
    throw new Error(data.error || "Die Anfrage ist fehlgeschlagen.");
  }
  return data;
}

function clearEntryForm() {
  entryForm.reset();
  entryForm.entry_date.value = state.selectedDate;
  entryForm.querySelectorAll('input[type="range"]').forEach((input) => {
    input.value = "0";
    input.nextElementSibling.textContent = "0";
  });
}

function fillForm(form, data) {
  [...form.elements].forEach((element) => {
    if (!element.name || element.type === "submit") return;
    if (element.type === "radio") {
      element.checked = element.value === (data[element.name] ?? "");
      return;
    }
    element.value = data[element.name] ?? "";
    if (element.type === "range") {
      element.value = data[element.name] ?? "0";
      element.nextElementSibling.textContent = element.value;
    }
  });
}

function autosaveMessage(manual, successText = "Automatisch gespeichert") {
  return manual ? "Gespeichert" : successText;
}

function compareVersions(left, right) {
  const normalize = (value) => String(value || "")
    .trim()
    .replace(/^v/i, "")
    .split(".")
    .map((part) => Number.parseInt(part, 10));
  const leftParts = normalize(left);
  const rightParts = normalize(right);
  const length = Math.max(leftParts.length, rightParts.length, 3);
  for (let index = 0; index < length; index += 1) {
    const a = leftParts[index] || 0;
    const b = rightParts[index] || 0;
    if (a > b) return 1;
    if (a < b) return -1;
  }
  return 0;
}

function extractVersionCandidate(release) {
  const values = [release?.name, release?.tag_name];
  for (const value of values) {
    const match = String(value || "").match(/v?\d+(?:\.\d+){0,2}/i);
    if (match) return match[0];
  }
  return "";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function hasValue(value) {
  return value !== null && value !== undefined && String(value).trim() !== "";
}

function isEntryComplete(entry) {
  if (!entry || !entry.entry_date) return false;
  return REQUIRED_ENTRY_FIELDS.every((field) => hasValue(entry[field]));
}

function cleanLabel(value) {
  return String(value || "").trim();
}

function painScore(entry) {
  const values = ["pain_morning", "pain_noon", "pain_evening", "pain_night"]
    .map((field) => Number(entry[field]))
    .filter((value) => Number.isFinite(value));
  if (!values.length) return null;
  return values.reduce((sum, value) => sum + value, 0) / values.length;
}

function formatCompactDate(value) {
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
  }).format(new Date(`${value}T12:00:00`));
}

function setEntryMeta(entry) {
  if (!entry || !entry.entry_date) {
    entryMetaEl.textContent = "";
    return;
  }
  const created = fmtHistory(entry.created_at);
  const updated = fmtHistory(entry.updated_at);
  entryMetaEl.textContent = created === updated
    ? `Erfasst: ${created}`
    : `Erfasst: ${created} · Geändert: ${updated}`;
}

function fmtHistory(value) {
  if (!value) return "-";
  if (String(value).includes("T")) {
    const stamp = new Date(value);
    if (!Number.isNaN(stamp.getTime())) {
      return new Intl.DateTimeFormat("de-DE", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      }).format(stamp);
    }
  }
  return new Intl.DateTimeFormat("de-DE", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(new Date(`${value}T12:00:00`));
}

function showUpdateToast(release) {
  const version = extractVersionCandidate(release) || "unbekannt";
  updateToastEl.hidden = false;
  updateToastEl.innerHTML = `
    <div class="toast-content">
      <div>
        <strong>Neue Version verfügbar</strong>
        <span>${escapeHtml(version.startsWith("v") ? version : `v${version}`)}</span>
      </div>
      <a href="${escapeHtml(release.html_url || `https://github.com/${GITHUB_OWNER}/${GITHUB_REPO}/releases`)}" target="_blank" rel="noreferrer">Release öffnen</a>
      <button type="button" aria-label="Toast schließen">Schließen</button>
    </div>
  `;
  const closeButton = updateToastEl.querySelector("button");
  closeButton.addEventListener("click", () => {
    updateToastEl.hidden = true;
  });
  window.setTimeout(() => {
    updateToastEl.hidden = true;
  }, 12000);
}

async function checkForUpdates() {
  try {
    const response = await fetch(`https://api.github.com/repos/${GITHUB_OWNER}/${GITHUB_REPO}/releases/latest`, {
      headers: {
        Accept: "application/vnd.github+json",
      },
      cache: "no-store",
    });
    if (!response.ok) return;
    const release = await response.json();
    const latestVersion = extractVersionCandidate(release).replace(/^v/i, "");
    if (!latestVersion) return;
    if (compareVersions(latestVersion, APP_VERSION) > 0) {
      showUpdateToast(release);
    }
  } catch (_) {
    // Silent fallback: offline or GitHub unavailable.
  }
}

function isBeforeDate(left, right) {
  return left < right;
}

function isFutureDate(dateValue) {
  return dateValue > TODAY;
}

function isBeforeAccidentDate(dateValue) {
  return hasValue(state.profile.accident_date) && isBeforeDate(dateValue, state.profile.accident_date);
}

function isOverdueDate(dateValue, today) {
  return isBeforeDate(dateValue, today) && !isBeforeAccidentDate(dateValue);
}

function renderDashboard() {
  const entries = [...state.allEntries.values()].sort((a, b) => a.entry_date.localeCompare(b.entry_date));
  const scoredEntries = entries
    .map((entry) => ({ ...entry, score: painScore(entry) }))
    .filter((entry) => entry.score !== null);

  const completeCount = entries.filter(isEntryComplete).length;
  const incompleteCount = entries.length - completeCount;
  const avgScore = scoredEntries.length
    ? scoredEntries.reduce((sum, entry) => sum + entry.score, 0) / scoredEntries.length
    : null;
  const trend = scoredEntries.length > 1
    ? scoredEntries[scoredEntries.length - 1].score - scoredEntries[0].score
    : null;
  const strongest = scoredEntries.reduce((best, entry) => {
    if (!best || entry.score > best.score) return entry;
    return best;
  }, null);
  const weatherCounts = entries.reduce((counts, entry) => {
    const key = cleanLabel(entry.weather);
    if (key) counts[key] = (counts[key] || 0) + 1;
    return counts;
  }, {});
  const mostCommonWeather = Object.entries(weatherCounts).sort((a, b) => b[1] - a[1])[0]?.[0] || "-";
  const completionRate = entries.length ? Math.round((completeCount / entries.length) * 100) : 0;

  dashboardStatsEl.innerHTML = [
    {
      label: "Einträge",
      value: String(entries.length),
      detail: `${completeCount} vollständig`,
    },
    {
      label: "Ø Schmerz",
      value: avgScore === null ? "-" : avgScore.toFixed(1),
      detail: "über alle Tage",
    },
    {
      label: "Trend",
      value: trend === null ? "-" : `${trend > 0 ? "+" : ""}${trend.toFixed(1)}`,
      detail: trend === null ? "zu wenig Daten" : "erster bis letzter Punkt",
    },
    {
      label: "Höchstwert",
      value: strongest ? strongest.score.toFixed(1) : "-",
      detail: strongest ? formatDate(strongest.entry_date) : "kein Messwert",
    },
    {
      label: "Häufigstes Wetter",
      value: mostCommonWeather,
      detail: "nach Einträgen",
    },
    {
      label: "Vollständig",
      value: `${completionRate}%`,
      detail: `${incompleteCount} unvollständig`,
    },
  ]
    .map((card) => `
      <article class="stat-card">
        <p>${escapeHtml(card.label)}</p>
        <strong>${escapeHtml(card.value)}</strong>
        <span>${escapeHtml(card.detail)}</span>
      </article>
    `)
    .join("");

  renderChart(scoredEntries);
}

function renderChart(entries) {
  dashboardChartEl.innerHTML = "";
  const ns = "http://www.w3.org/2000/svg";

  if (!entries.length) {
    const empty = document.createElementNS(ns, "text");
    empty.setAttribute("x", "500");
    empty.setAttribute("y", "160");
    empty.setAttribute("text-anchor", "middle");
    empty.setAttribute("class", "chart-empty");
    empty.textContent = "Noch keine Daten für den Verlauf";
    dashboardChartEl.appendChild(empty);
    return;
  }

  const width = 1000;
  const height = 320;
  const padding = { top: 26, right: 24, bottom: 56, left: 54 };
  const innerWidth = width - padding.left - padding.right;
  const innerHeight = height - padding.top - padding.bottom;
  const values = entries.map((entry) => entry.score);
  const minValue = Math.max(0, Math.floor(Math.min(...values)) - 1);
  const maxValue = Math.min(10, Math.ceil(Math.max(...values)) + 1);
  const range = Math.max(1, maxValue - minValue);

  for (let tick = minValue; tick <= maxValue; tick += 2) {
    const y = padding.top + innerHeight - ((tick - minValue) / range) * innerHeight;
    const line = document.createElementNS(ns, "line");
    line.setAttribute("x1", String(padding.left));
    line.setAttribute("x2", String(width - padding.right));
    line.setAttribute("y1", String(y));
    line.setAttribute("y2", String(y));
    line.setAttribute("class", "chart-grid");
    dashboardChartEl.appendChild(line);

    const label = document.createElementNS(ns, "text");
    label.setAttribute("x", "20");
    label.setAttribute("y", String(y + 4));
    label.setAttribute("class", "chart-axis-label");
    label.textContent = String(tick);
    dashboardChartEl.appendChild(label);
  }

  const points = entries.map((entry, index) => {
    const x = padding.left + (entries.length === 1 ? innerWidth / 2 : (index / (entries.length - 1)) * innerWidth);
    const y = padding.top + innerHeight - ((entry.score - minValue) / range) * innerHeight;
    return { ...entry, x, y };
  });

  const polyline = document.createElementNS(ns, "polyline");
  polyline.setAttribute("points", points.map((point) => `${point.x},${point.y}`).join(" "));
  polyline.setAttribute("class", "chart-line");
  dashboardChartEl.appendChild(polyline);

  points.forEach((point) => {
    const circle = document.createElementNS(ns, "circle");
    circle.setAttribute("cx", String(point.x));
    circle.setAttribute("cy", String(point.y));
    circle.setAttribute("r", "5");
    circle.setAttribute("class", "chart-point");
    const title = document.createElementNS(ns, "title");
    title.textContent = `${formatDate(point.entry_date)}: ${point.score.toFixed(1)}`;
    circle.appendChild(title);
    dashboardChartEl.appendChild(circle);

    const label = document.createElementNS(ns, "text");
    label.setAttribute("x", String(point.x));
    label.setAttribute("y", String(height - 18));
    label.setAttribute("text-anchor", "middle");
    label.setAttribute("class", "chart-label");
    label.textContent = formatCompactDate(point.entry_date);
    dashboardChartEl.appendChild(label);
  });
}

async function saveEntry(manual = false) {
  clearTimeout(state.entryAutosaveTimer);
  state.entryAutosaveTimer = null;
  if (isFutureDate(state.selectedDate)) {
    entryStatus.textContent = "Zukünftige Tage können nicht bearbeitet werden.";
    return;
  }
  entryStatus.textContent = manual ? "Speichere..." : "Speichere automatisch...";
  const payload = formToObject(entryForm);
  payload.entry_date = state.selectedDate;
  try {
    const entry = await api("/api/entries", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    state.entries.set(entry.entry_date, entry);
    state.allEntries.set(entry.entry_date, entry);
    entryStatus.textContent = autosaveMessage(manual);
    setEntryMeta(entry);
    renderCalendar();
    renderDashboard();
    deleteButton.disabled = false;
    return entry;
  } catch (error) {
    entryStatus.textContent = error.message;
    throw error;
  }
}

function scheduleEntryAutosave() {
  if (!state.autosaveReady) return;
  clearTimeout(state.entryAutosaveTimer);
  entryStatus.textContent = "Autosave wartet...";
  state.entryAutosaveTimer = setTimeout(() => {
    saveEntry(false).catch(() => {});
  }, AUTOSAVE_DELAY);
}

async function flushEntryAutosave() {
  if (!state.entryAutosaveTimer) return;
  await saveEntry(false);
}

async function saveProfile(manual = false) {
  clearTimeout(state.profileAutosaveTimer);
  state.profileAutosaveTimer = null;
  profileStatus.textContent = manual ? "Speichere..." : "Speichere automatisch...";
  try {
    const profile = await api("/api/profile", {
      method: "POST",
      body: JSON.stringify(formToObject(profileForm)),
    });
    state.profile = profile;
    renderCalendar();
    profileStatus.textContent = autosaveMessage(manual);
  } catch (error) {
    profileStatus.textContent = error.message;
    throw error;
  }
}

function scheduleProfileAutosave() {
  if (!state.autosaveReady) return;
  clearTimeout(state.profileAutosaveTimer);
  profileStatus.textContent = "Autosave wartet...";
  state.profileAutosaveTimer = setTimeout(() => {
    saveProfile(false).catch(() => {});
  }, AUTOSAVE_DELAY);
}

function sendPendingAutosaves() {
  if (!navigator.sendBeacon) return;
  if (state.entryAutosaveTimer) {
    clearTimeout(state.entryAutosaveTimer);
    state.entryAutosaveTimer = null;
    const payload = formToObject(entryForm);
    payload.entry_date = state.selectedDate;
    navigator.sendBeacon(
      "/api/entries",
      new Blob([JSON.stringify(payload)], { type: "application/json" }),
    );
  }
  if (state.profileAutosaveTimer) {
    clearTimeout(state.profileAutosaveTimer);
    state.profileAutosaveTimer = null;
    navigator.sendBeacon(
      "/api/profile",
      new Blob([JSON.stringify(formToObject(profileForm))], { type: "application/json" }),
    );
  }
}

async function loadProfile() {
  const profile = await api("/api/profile");
  state.profile = profile;
  fillForm(profileForm, profile);
}

async function loadAllEntries() {
  const rows = await api("/api/entries");
  state.allEntries = new Map(rows.map((entry) => [entry.entry_date, entry]));
  renderDashboard();
}

async function loadMonth() {
  const year = state.cursor.getFullYear();
  const month = state.cursor.getMonth() + 1;
  const rows = await api(`/api/entries?year=${year}&month=${month}`);
  state.entries = new Map(rows.map((entry) => [entry.entry_date, entry]));
  renderCalendar();
}

async function loadSelectedEntry() {
  selectedDateLabel.textContent = formatDate(state.selectedDate);
  clearEntryForm();
  if (isFutureDate(state.selectedDate)) {
    entryStatus.textContent = "Zukünftige Tage können nicht bearbeitet werden.";
    setEntryMeta(null);
    deleteButton.disabled = true;
    return;
  }
  const known = state.entries.get(state.selectedDate);
  if (known) {
    fillForm(entryForm, known);
    setEntryMeta(known);
  } else {
    const entry = await api(`/api/entries/${state.selectedDate}`);
    if (entry.entry_date) {
      fillForm(entryForm, entry);
      setEntryMeta(entry);
    } else {
      setEntryMeta(null);
    }
  }
  deleteButton.disabled = !state.entries.has(state.selectedDate);
}

function renderCalendar() {
  calendarEl.innerHTML = "";
  const year = state.cursor.getFullYear();
  const month = state.cursor.getMonth();
  const first = new Date(year, month, 1);
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const offset = (first.getDay() + 6) % 7;
  const currentMonth = new Date(TODAY);
  const monthIsFuture = year > currentMonth.getFullYear() || (year === currentMonth.getFullYear() && month > currentMonth.getMonth());

  monthTitle.textContent = new Intl.DateTimeFormat("de-DE", {
    month: "long",
    year: "numeric",
  }).format(first);

  prevMonthButton.disabled = false;
  nextMonthButton.disabled = monthIsFuture || (year === currentMonth.getFullYear() && month === currentMonth.getMonth());

  for (let i = 0; i < offset; i += 1) {
    calendarEl.append(document.createElement("span"));
  }

  for (let day = 1; day <= daysInMonth; day += 1) {
    const dateValue = `${year}-${String(month + 1).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = day;
    button.className = "day";
    const isFuture = isFutureDate(dateValue);
    if (isFuture) {
      button.disabled = true;
      button.classList.add("future-day");
    }
    const entry = state.entries.get(dateValue);
    if (entry) {
      button.classList.add(isEntryComplete(entry) ? "complete-entry" : "incomplete-entry");
    } else if (isOverdueDate(dateValue, TODAY)) {
      button.classList.add("overdue-entry");
    }
    if (dateValue === TODAY) button.classList.add("is-today");
    if (dateValue === state.selectedDate) button.classList.add("is-selected");
    if (!isFuture) {
      button.addEventListener("click", async () => {
        await flushEntryAutosave();
        state.selectedDate = dateValue;
        renderCalendar();
        await loadSelectedEntry();
      });
    }
    calendarEl.append(button);
  }
}

prevMonthButton.addEventListener("click", async () => {
  state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth() - 1, 1);
  await loadMonth();
});

nextMonthButton.addEventListener("click", async () => {
  state.cursor = new Date(state.cursor.getFullYear(), state.cursor.getMonth() + 1, 1);
  await loadMonth();
});

entryForm.querySelectorAll('input[type="range"]').forEach((input) => {
  input.addEventListener("input", () => {
    input.nextElementSibling.textContent = input.value;
  });
});

entryForm.addEventListener("input", scheduleEntryAutosave);
entryForm.addEventListener("change", scheduleEntryAutosave);
profileForm.addEventListener("input", scheduleProfileAutosave);
profileForm.addEventListener("change", scheduleProfileAutosave);

entryForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveEntry(true).catch(() => {});
});

profileForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  saveProfile(true).catch(() => {});
});

deleteButton.addEventListener("click", async () => {
  clearTimeout(state.entryAutosaveTimer);
  state.entryAutosaveTimer = null;
  if (!confirm(`Eintrag vom ${formatDate(state.selectedDate)} löschen?`)) return;
  await api(`/api/entries/${state.selectedDate}`, { method: "DELETE" });
  state.entries.delete(state.selectedDate);
  state.allEntries.delete(state.selectedDate);
  clearEntryForm();
  setEntryMeta(null);
  renderCalendar();
  renderDashboard();
  deleteButton.disabled = true;
  entryStatus.textContent = "Gelöscht";
});

window.addEventListener("beforeunload", sendPendingAutosaves);
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") sendPendingAutosaves();
});

async function boot() {
  state.cursor = new Date(`${state.selectedDate}T12:00:00`);
  await loadProfile();
  await loadAllEntries();
  await loadMonth();
  await loadSelectedEntry();
  state.autosaveReady = true;
  entryStatus.textContent = "Autosave aktiv";
  profileStatus.textContent = "Autosave aktiv";
  checkForUpdates();
}

boot().catch((error) => {
  entryStatus.textContent = error.message;
});
