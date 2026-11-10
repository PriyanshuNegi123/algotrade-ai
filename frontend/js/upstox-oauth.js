"use strict";
window.AlgoTradeOAuth = {
  create({ request, getCsrf }) {
    const button = document.getElementById("oauth-connect");
    const cancel = document.getElementById("oauth-cancel");
    const feedback = document.getElementById("oauth-feedback");
    let pending = null;
    function cleanup(closePopup = true) {
      if (!pending) return;
      clearTimeout(pending.timeout);
      if (pending.channel) pending.channel.close();
      if (closePopup && pending.popup) { try { pending.popup.close(); } catch { /* Browser may have detached the popup. */ } }
      pending.nonce = null; pending.state = null; pending = null;
      cancel.hidden = true; cancel.disabled = false;
      button.textContent = "Authorize Upstox OAuth";
    }
    function headers() { return { "Content-Type": "application/json", "X-CSRF-Token": getCsrf() }; }
    async function load() {
      try {
        const status = await request("/api/broker/oauth/status");
        button.hidden = !getCsrf();
        button.disabled = !status.can_start || pending !== null;
        if (!pending) feedback.textContent = status.state === "STORED_UNVERIFIED"
          ? "OAuth credential stored locally. Market data still uses Analytics; trading remains disabled."
          : status.can_start ? "Optional OAuth setup is available. Authorization opens in a separate window."
            : "OAuth setup is incomplete. Configure the registered app and private storage locally.";
      } catch {
        button.hidden = true;
        if (!pending) feedback.textContent = "Sign in to review OAuth setup.";
      }
    }
    async function deny(flow) {
      if (!flow.state || !flow.nonce || !getCsrf()) return;
      try { await request("/api/broker/oauth/finish", { method: "POST", headers: headers(), body: JSON.stringify({ state: flow.state, flow_nonce: flow.nonce, denied: true }) }); }
      catch { /* A lost session/response cannot authorize; a new start invalidates the old flow. */ }
    }
    button.addEventListener("click", async () => {
      if (!getCsrf() || pending) return;
      if (typeof BroadcastChannel !== "function") { feedback.textContent = "This browser cannot complete secure authorization. Use a browser with BroadcastChannel support."; return; }
      const popup = window.open("about:blank", "_blank", "popup,width=560,height=760");
      if (!popup) { feedback.textContent = "Allow the authorization popup and try again."; return; }
      try { popup.opener = null; }
      catch { popup.close(); feedback.textContent = "The authorization window could not be isolated. Try another browser."; return; }
      const flow = { popup, channel: null, state: null, nonce: null, timeout: null, busy: false };
      pending = flow; button.disabled = true; cancel.hidden = false;
      button.textContent = "Authorizing…";
      feedback.textContent = "Preparing secure Upstox authorization…";
      try {
        const started = await request("/api/broker/oauth/start", { method: "POST", headers: headers() });
        flow.state = started.state; flow.nonce = started.flow_nonce;
        if (pending !== flow) { await deny(flow); return; }
        const url = new URL(started.authorization_url);
        if (url.origin !== "https://api.upstox.com" || url.pathname !== "/v2/login/authorization/dialog"
          || !/^[A-Za-z0-9_-]{43}$/.test(flow.state) || !/^[A-Za-z0-9_-]{43}$/.test(flow.nonce)) throw new Error("Invalid authorization response");
        popup.sessionStorage.setItem("algotrade.upstox.flow", JSON.stringify({ state: flow.state, nonce: flow.nonce, expires_at: started.expires_at }));
        flow.channel = new BroadcastChannel("algotrade-upstox-" + flow.nonce);
        flow.channel.onmessage = async (event) => {
          const value = event.data;
          if (pending !== flow || flow.busy || !value || value.type !== "algotrade-oauth-callback" || value.state !== flow.state) return;
          if (typeof value.denied !== "boolean" || (!value.denied && (typeof value.code !== "string" || value.code.length < 1 || value.code.length > 8192))) return;
          flow.busy = true; cancel.disabled = true;
          feedback.textContent = "Verifying authorization and saving the credential locally…";
          let saved = false;
          let notice = "Authorization could not be confirmed. Check status before trying again.";
          try {
            const result = await request("/api/broker/oauth/finish", { method: "POST", headers: headers(), body: JSON.stringify({ state: flow.state, flow_nonce: flow.nonce, code: value.denied ? null : value.code, denied: value.denied }) });
            saved = result.state === "STORED_UNVERIFIED";
            notice = saved ? "OAuth credential saved locally. Analytics access is unchanged; trading remains disabled." : "Authorization was not completed. You can start a new attempt.";
          } catch { /* A lost response is not proof of rollback. */ }
          if (pending !== flow) return;
          flow.channel.postMessage({ type: "algotrade-oauth-result", state: flow.state, saved });
          cleanup(false); await load();
          if (!pending) feedback.textContent = notice;
        };
        const remaining = Math.max(0, Math.min(300000, Date.parse(started.expires_at) - Date.now()));
        flow.timeout = setTimeout(() => { if (pending !== flow) return; cleanup(); feedback.textContent = "Authorization expired. Start a new attempt."; void load(); }, remaining);
        popup.location.replace(url.href);
        feedback.textContent = "Complete consent in the Upstox window. Keep this AlgoTrade tab open.";
      } catch {
        if (pending === flow) { await deny(flow); if (pending === flow) { cleanup(); await load(); if (!pending) feedback.textContent = "Authorization could not start. Check local setup and service status."; } }
      }
    });
    cancel.addEventListener("click", async () => {
      const flow = pending;
      if (!flow || flow.busy) return;
      flow.busy = true; cancel.disabled = true;
      await deny(flow);
      if (pending !== flow) return;
      cleanup(); await load();
      if (!pending) feedback.textContent = "Authorization window closed. A new attempt invalidates the prior flow.";
    });
    return { load, reset() { cleanup(); button.hidden = true; feedback.textContent = "Sign in to review OAuth setup."; } };
  },
};
