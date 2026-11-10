# Browser-bound Upstox OAuth callback

Implemented and verified with synthetic HTTP/PostgreSQL tests and isolated headless Chrome.
The operator completed genuine browser consent on 10 November. Private runtime deployment
and authenticated metadata status confirm encrypted local storage (STORED_UNVERIFIED).
Broker account permissions and use of this credential for data remain unverified. Existing
Analytics remains the active market-data credential. Live stays off.

## Enablement and operator flow

The optional routes fail closed unless all of these server settings are valid:

Use `uv run python -m scripts.configure_upstox_oauth` in your own terminal to save the three
registered app fields securely; the secret prompt is hidden. See [setup](UPSTOX_OAUTH.md).

- UPSTOX_CLIENT_ID,UPSTOX_CLIENT_SECRET and UPSTOX_REDIRECT_URI from the registered app.
- UPSTOX_OAUTH_VAULT_DIR:an absolute,canonical,private local storage path controlled by the
  service. The parent must exist and be writable by the backend UID. The base Compose file
  has no vault mount; the optional overlay described below supplies a dedicated volume.
- The registered callback origin must be in ALLOWED_ORIGINS. Use that same origin for the
  dashboard. Callback path must be canonical ASCII segments,not root,reserved API/assets/
  health/docs paths,percent-encoded or trailing-slash paths. Exact URI is preserved upstream.

For example,`http://127.0.0.1:8000/auth/upstox/callback` is a possible local callback to
register if that is your chosen deployment. It is not a claim about your current app's
registration. A container path such as `/app/.local/upstox` requires an appropriate mount;
merely adding its name to.env does not make the read-only container writable. No deployment,
volume ownership change,secret update or real store initialization occurred this iteration.

## Optional container storage

`docker-compose.oauth.yml` can be explicitly layered over `docker-compose.yml`. It mounts
only the application's `/var/lib/algotrade/oauth` directory using a project-scoped named
volume and sets the matching server path. The image supplies an empty directory owned by
UID 10001 with mode 0700. Docker initializes a new volume from that directory; no runtime
root process, ownership repair, key generation or token creation is added. Existing unsafe
volume permissions still fail closed. The rest of the application filesystem stays read-only.
The database and migration service receive no vault mount. Default deployment is unchanged.

Verify with generated synthetic settings and a disposable project first:

```sh
uv run python -m scripts.verify_compose --oauth-vault
```

The verifier tests metadata reads without key creation, rejected CSRF, explicit start/denial,
encrypted synthetic storage, UID/modes and decryption after forced container replacement.
It also runs the existing auth/database outage smoke checks. No authorization page is opened
and no provider request is made. Only its own containers and volumes are removed.

For a later operator-approved deployment, use the same Compose project name and both files
for every lifecycle command, for example:

```sh
docker compose --project-name algotrade-ai-local \
  --file docker-compose.yml --file docker-compose.oauth.yml config --quiet
```

This validates only; it does not start or replace the running application. Do not print
expanded Compose configuration because it contains secrets. Configure the actual registered
OAuth app settings locally before genuine consent. Bootstrap now supports first opt-in with
`uv run python -m scripts.bootstrap_local --oauth-vault`; subsequent runs detect the exact
project's existing named volume and retain the overlay automatically. No credential is
generated or exchanged by bootstrap. See [local bootstrap](LOCAL_BOOTSTRAP.md) for lifecycle
validation and disposable verification commands. Manual Compose lifecycle commands still
require both files.
Never use `down --volumes` against the operational project: it destroys both database and
OAuth storage. Retain the named volume across rebuilds; do not silently reset unsafe data.

This small credential volume stays local and is excluded from PostgreSQL/Drive backups and
the recovery kit. Loss requires fresh consent. Bulk archives/backups retain their existing
Drive policy. Docker administrators can access the key and ciphertext; this mount is not a
boundary against host or Docker account compromise. Proxy logging review and real consent
remain separate acceptance gates.

Volume initialization and lifecycle follow the official [Docker volume documentation](https://docs.docker.com/engine/storage/volumes/).

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
