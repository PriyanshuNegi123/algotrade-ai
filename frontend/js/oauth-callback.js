"use strict";
(() => {
  const message = document.getElementById("oauth-return-status");
  let query = window.location.search;
  // Erase the browser URL before reading parameters or communicating with another tab.
  try { window.history.replaceState(null, "", window.location.pathname); }
  catch { message.textContent = "Authorization could not be completed. Return to your original tab and start again."; return; }
  const params = new URLSearchParams(query);
  query = "";
  let state = params.get("state");
  let code = params.get("code");
  const denied = params.has("error");
  let binding = null;
  try {
    const marker = window.sessionStorage.getItem("algotrade.upstox.flow");
    window.sessionStorage.removeItem("algotrade.upstox.flow");
    binding = JSON.parse(marker || "null");
  } catch { /* A missing/blocked popup binding fails closed. */ }
  const allowed = new Set(["state", "code", "error", "error_description", "error_uri"]);
  const valid = [...params.keys()].every((key) => allowed.has(key) && params.getAll(key).length === 1)
    && typeof state === "string" && /^[A-Za-z0-9_-]{43}$/.test(state)
    && (denied ? code === null : typeof code === "string" && code.length > 0 && code.length <= 8192)
    && typeof BroadcastChannel === "function"
    && binding && binding.state === state && /^[A-Za-z0-9_-]{43}$/.test(binding.nonce)
    && Number.isFinite(Date.parse(binding.expires_at)) && Date.parse(binding.expires_at) > Date.now();
  if (!valid) { message.textContent = "Invalid authorization return. Start again from your original AlgoTrade tab."; return; }
  const channel = new BroadcastChannel("algotrade-upstox-" + binding.nonce);
  binding = null;
  for (const key of [...params.keys()]) params.delete(key);
  const timeout = setTimeout(() => {
    channel.close(); code = null; state = null;
    message.textContent = "The original tab did not confirm authorization. Return there and check status before trying again.";
  }, 30000);
  channel.onmessage = (event) => {
    const result = event.data;
    if (!result || result.type !== "algotrade-oauth-result" || result.state !== state) return;
    clearTimeout(timeout);
    message.textContent = result.saved === true
      ? "Authorization saved locally. Return to your original AlgoTrade tab."
      : "Authorization was not confirmed. Return to your original AlgoTrade tab and review its status.";
    code = null; state = null; channel.close();
  };
  channel.postMessage({ type: "algotrade-oauth-callback", state, code, denied });
  code = null;
  // Never send the app nonce, session, CSRF value or any access token through this channel.
})();
