"use strict";
const byId = (id) => document.getElementById(id);
let csrfToken = null;
const currency = new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR" });
byId("date").textContent = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium", timeZone: "Asia/Kolkata",
}).format(new Date()) + " · IST";
try { document.body.classList.toggle("dark", localStorage.getItem("theme") === "dark"); } catch { /* Storage is optional. */ }
byId("theme").setAttribute("aria-pressed", String(document.body.classList.contains("dark")));
byId("theme").addEventListener("click", () => {
  const dark = document.body.classList.toggle("dark");
  byId("theme").setAttribute("aria-pressed", String(dark));
  try { localStorage.setItem("theme", dark ? "dark" : "light"); } catch { /* Storage is optional. */ }
});
async function api(path, options = {}) {
  const response = await fetch(path, { ...options, credentials: "same-origin", signal: AbortSignal.timeout(path === "/api/instruments/sync" ? 65000 : 20000) });
  if (!response.ok) {
    const error = new Error("Request failed");
    error.status = response.status;
    throw error;
  }
  return response.status === 204 ? null : response.json();
}
function clearAccount() {
  byId("account").hidden = true;
  byId("signin").hidden = false;
  byId("chain-form").hidden = true;
  byId("chain-status").textContent = "Sign-in required";
  byId("chain-feedback").textContent = "Sign in to review option-chain research snapshots.";
  byId("history-form").hidden = true;
  byId("history-status").textContent = "Sign-in required";
  byId("history-feedback").textContent = "Sign in to review historical imports.";
  byId("instrument-sync").hidden = true;
  byId("instrument-summary").hidden = true;
  byId("instrument-status").textContent = "Sign-in required";
  byId("instrument-feedback").textContent = "Sign in to review instrument metadata.";
  byId("broker-check").hidden = true;
  byId("broker-status").textContent = "Sign-in required";
  byId("broker-feedback").textContent = "Sign in to review the read-only connection configuration.";
  document.querySelectorAll(".metric-value, .ledger dd").forEach((node) => { node.textContent = "—"; });
}
async function loadOverview() {
  try {
    const state = await api("/api/overview");
    for (const key of ["balance", "available_capital", "starting_equity", "realized_pnl", "unrealized_pnl", "trading_costs", "daily_pnl", "monthly_pnl", "max_drawdown"]) {
      const value = state[key];
      byId(key).textContent = value == null ? "—" : key === "max_drawdown" ? `${value}%` : currency.format(value);
    }
    document.querySelector(".mode").textContent = state.mode;
    byId("account").hidden = false;
    byId("signin").hidden = csrfToken !== null;
    byId("logout").hidden = csrfToken === null;
    byId("feedback").textContent = csrfToken ? "Workspace loaded. Financial values remain unavailable until verified data is connected." : "Session restored. Sign in again to enable secure sign-out from this page.";
    await Promise.all([loadBrokerStatus(), loadInstrumentStatus(), loadHistoryStatus(), loadChainStatus()]);
  } catch (error) {
    clearAccount();
    byId("feedback").textContent = error.status === 401 ? "Sign in to load your private workspace." : "Account status unavailable. Trading remains disabled. Try again after checking service health.";
  }
}
async function loadBrokerStatus() {
  try {
    const result = await api("/api/broker/status");
    const labels = { NOT_CONFIGURED: "Not configured", EXPIRED: "Token expired", UNVERIFIED: "Not checked", CHECKED: "Check passed", AUTH_REQUIRED: "Authentication required", ACCESS_DENIED: "Access denied", RATE_LIMITED: "Rate limited", UNAVAILABLE: "Unavailable", INVALID_RESPONSE: "Invalid response" };
    byId("broker-status").textContent = labels[result.state] || "Unavailable";
    byId("broker-feedback").textContent = result.next_action;
    byId("broker-check").hidden = csrfToken === null;
    byId("broker-check").disabled = ["NOT_CONFIGURED", "EXPIRED"].includes(result.state);
    if (result.exchange) {
      byId("broker-feedback").textContent += ` NSE: ${result.exchange.status}. This is an exchange-state check, not a price feed.`;
    }
  } catch {
    byId("broker-status").textContent = "Unavailable";
    byId("broker-feedback").textContent = "Connection status could not be loaded. Sign in again if your session expired.";
    byId("broker-check").hidden = true;
  }
}
byId("broker-check").addEventListener("click", async () => {
  const button = byId("broker-check");
  button.disabled = true;
  button.textContent = "Checking…";
  byId("broker-feedback").textContent = "Checking read-only Upstox access…";
  try {
    await api("/api/broker/check", { method: "POST", headers: { "X-CSRF-Token": csrfToken } });
    await loadBrokerStatus();
  } catch (error) {
    await loadBrokerStatus();
    if (error.status === 429) byId("broker-feedback").textContent = "Check rate limited. Wait before trying again; no automatic retries are performed.";
  } finally {
    button.textContent = "Check read-only connection";
  }
});
async function loadHealth() {
  byId("health").textContent = "Checking backend readiness…";
  try {
    await api("/health/ready");
    byId("health").textContent = "Backend ready · execution disabled";
  } catch {
    byId("health").textContent = "Backend not ready · review database and administrator configuration";
  }
}
byId("login-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.currentTarget.querySelector("button");
  button.disabled = true;
  button.textContent = "Signing in…";
  byId("feedback").textContent = "Verifying administrator access…";
  try {
    const result = await api("/api/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: byId("password").value }),
    });
    csrfToken = result.csrf_token;
    await loadOverview();
  } catch (error) {
    clearAccount();
    byId("feedback").textContent = error.status === 401 ? "Password not recognized." : error.status === 429 ? "Too many attempts. Wait one minute before trying again." : "Sign-in unavailable. Check administrator configuration and database readiness.";
  } finally {
    byId("password").value = "";
    button.disabled = false;
    button.textContent = "Sign in";
  }
});
byId("logout").addEventListener("click", async () => {
  try {
    await api("/api/auth/logout", { method: "POST", headers: { "X-CSRF-Token": csrfToken } });
    csrfToken = null;
    clearAccount();
    byId("feedback").textContent = "Signed out. Your session has been revoked.";
  } catch { byId("feedback").textContent = "Sign-out could not be confirmed. Retry; the session expires automatically."; }
});
byId("refresh").addEventListener("click", () => { loadHealth(); loadOverview(); });
loadHealth();
loadOverview();

async function loadInstrumentStatus() {
  try {
    const result = await api("/api/instruments/status");
    const snapshot = result.snapshot;
    byId("instrument-sync").hidden = csrfToken === null;
    byId("instrument-status").textContent = snapshot ? snapshot.state === "CURRENT_METADATA" ? "Current metadata" : "Stale metadata" : "Not imported";
    byId("instrument-summary").hidden = !snapshot;
    byId("instrument-feedback").textContent = snapshot ? "Snapshot preserved. Tick-size units still require verification before execution." : "Import the official catalog to load current lot sizes, expiries and instrument keys.";
    if (snapshot) {
      byId("instrument-selected").textContent = snapshot.selected_records.toLocaleString("en-IN");
      byId("instrument-source-count").textContent = snapshot.source_records.toLocaleString("en-IN");
      const dates = new Intl.DateTimeFormat("en-IN", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Kolkata" });
      byId("instrument-published").textContent = dates.format(new Date(snapshot.source_modified_at));
      byId("instrument-imported").textContent = dates.format(new Date(snapshot.imported_at));
    }
  } catch {
    byId("instrument-status").textContent = "Unavailable";
    byId("instrument-feedback").textContent = "Catalog status could not be loaded. Review backend health and sign-in.";
    byId("instrument-sync").hidden = true;
    byId("instrument-summary").hidden = true;
  }
}
byId("instrument-sync").addEventListener("click", async () => {
  const button = byId("instrument-sync");
  button.disabled = true;
  button.textContent = "Importing metadata…";
  byId("instrument-feedback").textContent = "Fetching and validating the official NSE catalog…";
  try {
    await api("/api/instruments/sync", { method: "POST", headers: { "X-CSRF-Token": csrfToken } });
    await loadInstrumentStatus();
  } catch (error) {
    await loadInstrumentStatus();
    byId("instrument-feedback").textContent = error.status === 429 ? "Import cooldown active. Wait five minutes before retrying." : error.status === 409 ? "An import is already in progress." : "Import could not be confirmed. The prior validated snapshot is preserved; refresh status before retrying.";
  } finally {
    button.disabled = false;
    button.textContent = "Import official NSE metadata";
  }
});

function istDate(value) {
  const parts = new Intl.DateTimeFormat("en-CA", { year: "numeric", month: "2-digit", day: "2-digit", timeZone: "Asia/Kolkata" }).formatToParts(value);
  const field = (type) => parts.find((part) => part.type === type).value;
  return `${field("year")}-${field("month")}-${field("day")}`;
}
const lastHistoryDate = istDate(new Date(Date.now() - 86400000));
byId("history-from").max = lastHistoryDate;
byId("history-to").max = lastHistoryDate;
byId("history-to").value = lastHistoryDate;
byId("history-from").value = istDate(new Date(Date.now() - 7 * 86400000));
async function loadHistoryStatus() {
  try {
    const status = await api("/api/candles/status");
    byId("history-form").hidden = csrfToken === null;
    const batch = status.latest_import;
    byId("history-status").textContent = batch ? batch.row_count ? "Research data imported" : "Empty response" : "Not imported";
    byId("history-feedback").textContent = batch ? `${batch.instrument_key}: ${batch.row_count.toLocaleString("en-IN")} completed bars; ${batch.gap_count.toLocaleString("en-IN")} potential missing intraday bars. Session completeness and historical metadata are unverified.` : "Requires imported metadata and a server-side Analytics Token. Select up to 28 calendar days ending before today.";
  } catch {
    byId("history-form").hidden = true;
    byId("history-status").textContent = "Unavailable";
    byId("history-feedback").textContent = "History status unavailable. Review schema readiness and administrator access.";
  }
}
byId("history-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("history-import");
  button.disabled = true;
  button.textContent = "Importing candles…";
  byId("history-feedback").textContent = "Requesting and validating historical candles…";
  try {
    await api("/api/candles/import", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken }, body: JSON.stringify({ instrument_key: byId("history-key").value, interval: Number(byId("history-interval").value), from_date: byId("history-from").value, to_date: byId("history-to").value }) });
    await loadHistoryStatus();
  } catch (error) {
    await loadHistoryStatus();
    byId("history-feedback").textContent = error.status === 429 ? "Import rate limited. Wait before retrying; requests are never automatically resubmitted." : error.status === 422 ? "Import rejected. Review the catalog key, date range, interval and returned candle quality." : "Import could not be confirmed. Review the server credential and backend health, then refresh status before retrying.";
  } finally {
    button.disabled = false;
    button.textContent = "Import historical candles";
  }
});

function resetChainExpiries() {
  const option = document.createElement("option");
  option.value = "";
  option.textContent = "Load catalog expiries first";
  byId("chain-expiry").replaceChildren(option);
  byId("chain-expiry").disabled = true;
  byId("chain-capture").disabled = true;
}
byId("chain-key").addEventListener("input", resetChainExpiries);
async function loadChainStatus() {
  try {
    const result = await api("/api/option-chain/status");
    byId("chain-form").hidden = csrfToken === null;
    const snapshot = result.latest_snapshot;
    byId("chain-status").textContent = snapshot ? snapshot.leg_count ? "Research snapshot" : "Empty response" : "Not captured";
    byId("chain-feedback").textContent = snapshot ? `${snapshot.underlying_key} · ${snapshot.expiry_date}: ${snapshot.strike_count.toLocaleString("en-IN")} strikes, ${snapshot.leg_count.toLocaleString("en-IN")} legs, ${snapshot.flagged_legs.toLocaleString("en-IN")} legs with diagnostic flags. Quote freshness remains unknown; signals and execution are disabled.` : "Import current metadata, load an explicit catalog expiry and configure the server Analytics credential before capture.";
  } catch {
    byId("chain-form").hidden = true;
    byId("chain-status").textContent = "Unavailable";
    byId("chain-feedback").textContent = "Chain status unavailable. Review administrator access and schema readiness.";
  }
}
byId("chain-expiries").addEventListener("click", async () => {
  const button = byId("chain-expiries");
  button.disabled = true;
  resetChainExpiries();
  try {
    const result = await api(`/api/option-chain/expiries?${new URLSearchParams({ underlying_key: byId("chain-key").value.trim() })}`);
    if (result.expiry_dates.length) {
      const options = result.expiry_dates.map((expiry) => {
        const option = document.createElement("option");
        option.value = expiry;
        option.textContent = expiry;
        return option;
      });
      byId("chain-expiry").replaceChildren(...options);
      byId("chain-expiry").disabled = false;
      byId("chain-capture").disabled = false;
      byId("chain-feedback").textContent = "Catalog expiry dates loaded locally. Capture validates the complete CE/PE mapping before broker access.";
    } else byId("chain-feedback").textContent = "No unexpired option expiry exists in this catalog for the index.";
  } catch {
    byId("chain-feedback").textContent = "Could not load expiries. Check the imported index key and catalog freshness.";
  } finally { button.disabled = false; }
});
byId("chain-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = byId("chain-capture");
  button.disabled = true;
  button.textContent = "Capturing…";
  byId("chain-feedback").textContent = "Checking catalog identity and capturing a read-only snapshot…";
  try {
    await api("/api/option-chain/capture", { method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrfToken }, body: JSON.stringify({ underlying_key: byId("chain-key").value.trim(), expiry_date: byId("chain-expiry").value }) });
    await loadChainStatus();
  } catch (error) {
    await loadChainStatus();
    byId("chain-feedback").textContent = error.status === 429 ? "Capture rate limited. Wait before retrying; snapshots are not automatically resubmitted." : error.status === 422 ? "Snapshot rejected. Review catalog freshness, expiry/CE/PE identity and quote quality." : "Capture could not be confirmed. Review the server credential and backend health; refresh status before retrying.";
  } finally {
    button.textContent = "Capture research snapshot";
    button.disabled = byId("chain-expiry").disabled;
  }
});
