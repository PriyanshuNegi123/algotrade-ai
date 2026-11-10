# Browser-bound Upstox OAuth callback

Implemented and verified with synthetic HTTP/PostgreSQL tests and isolated headless Chrome.
Real registered authorization, private runtime deployment and broker acceptance are still
pending. Existing Analytics remains the only active market-data credential. Live stays off.

## Enablement and operator flow

The optional routes fail closed unless all of these server settings are valid:

- UPSTOX_CLIENT_ID,UPSTOX_CLIENT_SECRET and UPSTOX_REDIRECT_URI from the registered app.
- UPSTOX_OAUTH_VAULT_DIR:an absolute,canonical,private local storage path controlled by the
  service. The parent must exist and be writable by the backend UID. Current read-only
  Compose has no OAuth vault mount;configure a dedicated durable private mount before use.
- The registered callback origin must be in ALLOWED_ORIGINS. Use that same origin for the
  dashboard. Callback path must be canonical ASCII segments,not root,reserved API/assets/
  health/docs paths,percent-encoded or trailing-slash paths. Exact URI is preserved upstream.

For example,`http://127.0.0.1:8000/auth/upstox/callback` is a possible local callback to
register if that is your chosen deployment. It is not a claim about your current app's
registration. A container path such as `/app/.local/upstox` requires an appropriate mount;
merely adding its name to.env does not make the read-only container writable. No deployment,
volume ownership change,secret update or real store initialization occurred this iteration.

After deployment,sign in freshly so the original dashboard has its in-memory CSRF value.
The Broker connection card shows optional OAuth setup independently from Analytics. Click
Authorize Upstox OAuth,complete consent in the separate window,and keep the original tab
open. A stored credential is labeled unverified;it does not enable trading or replace Analytics.

## Security boundaries

POST `/api/broker/oauth/start` requires the current administrator cookie,allowed Origin and
CSRF header. It explicitly prepares the protected vault before issuing a provider link:an
empty directory/key/lock can be initialized here,but no token is created or overwritten.
Unsafe existing storage stops the flow before consent. Pending state is bound to the admin
session and app;an additional random256-bit browser nonce is returned only to that browser.

The original dashboard retains session/CSRF/flow nonce in memory. It seeds only a short-lived
state/nonce/expiry marker into the newly opened popup's per-window sessionStorage,detaches
the popup opener,and navigates to the fixed official authorization URL. No access token,
password,client secret,CSRF value or callback code is written to browser storage. The marker
is removed immediately on return;closing the popup removes its window storage. A server
expiry/new start also invalidates abandoned markers. There is no localStorage token store.

GET of the exact callback serves static same-origin HTML/JS. It does not require the Strict
administrator cookie,exchange a code,write a token or reflect query/error values. An ASGI
middleware removes the query in the original server scope before application/access logging;
the browser independently clears its URL before parsing. Referrer-policy,no-store and strict
CSP headers remain. Reverse proxies/edge logs must separately suppress callback queries;
application redaction cannot sanitize logs written before the request reaches the app.

The popup validates/removes its own marker and returns only code/state/denial through a
same-origin BroadcastChannel named with the secret nonce,not the public URL state. A separate
unbound tab with a copied state cannot complete this handshake. The original tab then makes
POST `/api/broker/oauth/finish` with its existing Strict cookie,CSRF,Origin,state and nonce.
The callback never receives an access token,session cookie value or vault key.

Finish validates all bindings and atomically consumes the pending flow before the one token
exchange. Session validity is checked before exchange and again before persistence. The final
PostgreSQL session row lock serializes that authorization point with concurrent logout.
Changed app/storage settings during exchange,revocation,expiry,replay or wrong browser/session
stop persistence. A generation guard also prevents an older in-flight exchange from
publishing after a newer start,serialized with final storage. OAuth API bodies and callback queries are bounded16KiB;body receives have a
5second deadline. Error/denial/invalid inputs do not echo secrets. Valid provider denial or
user cancellation consumes state without a token request. There are no automatic retries.

All OAuth token responses remain encrypted/server-only in the quarantine vault. There is no
new order adapter,activation flag,funds request,market-data request or observation recording.
A slow request/disconnect can leave final storage uncertain;inspect status before a new
attempt instead of assuming rollback. In-memory pending flows are single-process and lost
on restart;completed encrypted vault data is separate. Existing administrator cookie attributes
stay HttpOnly/SameSite=Strict with the existing Secure policy. No Lax authentication cookie.

GET `/api/broker/oauth/status` requires admin authentication and reports only setup/storage
state and false broker/execution flags. It never creates a key. The local configuration checker
reports file-field presence only;tokens_stored=null/token_storage_checked=false avoids claiming
a physical vault inspection. browser_flow_implemented=true means code exists,not real consent.

## Reproducible synthetic browser proof

Use an existing Chrome/Chromium executable;the script downloads nothing:

```sh
uv run python -m scripts.verify_oauth_browser \
  --chrome-binary '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

The verifier creates a fresh temporary browser profile and migrated SQLite app on random
loopback ports. A synthetic localhost provider is cross-site from the127.0.0.1app. Browser
requests to the official authorization hostname are intercepted before network,other non-fixture
requests blocked,and token responses mocked. It verifies successful completion,Strict cookie
absence on cross-site GET and presence on original-tab POST,popup isolation,marker/query
cleanup,unbound-tab rejection,one mock exchange and nonempty scrubbed Uvicorn access logs.
No real profile,broker,credentials or operational DB is used. Only its own fixtures are removed.

33new pytest cases include two disposable PostgreSQL cases. They cover authentication,Origin,
CSRF,nonce/session mismatch,replay,denial,cancellation,new-flow invalidation,revocation/expiry/
configuration changes during exchange,unsafe storage,bounded/safe errors and reserved paths.
Full final tests and security results are in VERIFICATION.md. A pre-existing nonfatal Starlette
warning remains. No new hosted CI pass or real broker authorization is claimed.

Primary contracts: [Upstox authentication](https://upstox.com/developer/api-documentation/authentication/),
[BroadcastChannel](https://developer.mozilla.org/en-US/docs/Web/API/Broadcast_Channel_API),
[window.open](https://developer.mozilla.org/en-US/docs/Web/API/Window/open),
[SameSite cookies](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie).
