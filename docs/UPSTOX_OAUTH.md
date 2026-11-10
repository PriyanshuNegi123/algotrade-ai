# Upstox OAuth protocol foundation

Status:protocol,configuration,encrypted vault and browser HTTP/UI flow implemented and
synthetically verified. Real registered browser authorization and private runtime deployment
remain pending. This is separate from Google Drive OAuth and the working Analytics path.
Phase2 remains partial and live stays off. See [UPSTOX_OAUTH_BROWSER.md](UPSTOX_OAUTH_BROWSER.md).

## Local settings

After the initial local bootstrap, run this in your own interactive terminal:

```sh
uv run python -m scripts.configure_upstox_oauth
uv run python -m scripts.check_upstox_oauth
```

Enter the registered public API key, the API secret at the hidden prompt, and the exact
registered redirect URL. These are Upstox app settings, separate from the Analytics Token
and Google Drive credentials. Do not send secret values in chat, command arguments or logs.
The helper refuses noninteractive input or an echo fallback. It accepts no secret arguments
and rejects unknown arguments without echoing their values.

The helper saves only these three variables in the project `.env`:

```dotenv
UPSTOX_CLIENT_ID=YOUR_REGISTERED_PUBLIC_API_KEY
UPSTOX_CLIENT_SECRET=YOUR_LOCAL_API_SECRET
UPSTOX_REDIRECT_URI=YOUR_EXACT_REGISTERED_CALLBACK_URL
```

These are placeholders, not usable credentials or a proposed callback registration.
The helper requires an existing, private mode0600 regular environment file owned by the
current user. Symlinks, hardlinks, oversized or malformed files and duplicate keys are
rejected. OAuth aliases differing only by case cannot create duplicate settings. It validates
the callback against the existing allowed dashboard origins and supported callback paths;
it does not register a URL or change origin/cookie/security settings. OBSERVATION and
LIVE_ENABLED=false are required. No values are trimmed or normalized silently.

Unrelated original text, including multiline settings and line endings, is retained. A
shared bootstrap lock serializes cooperative writers; a detected external edit stops the
save. Publication is atomic using a private temporary file, followed by a directory sync.
A reported OAUTH_SETTINGS_SAVE_UNCERTAIN can occur after publication: inspect the local
checker before retrying. Identical values cause no rewrite. Existing nonempty app settings
require an explicit `--replace`; this preserves old settings until that deliberate command.
Changing app settings does not delete/reset old vault contents or activate a credential.

Secrets use a literal single-quoted representation. Dollar, hash and escaped quote characters
are verified through Python and actual Compose/container loading. Backslash characters and
`${...}` interpolation forms are refused rather than silently changing the secret between
parsers. This helper restriction does not change the OAuth protocol's validation rules.
See [Docker environment-file syntax](https://docs.docker.com/compose/how-tos/environment-variables/variable-interpolation/).

Keep `.env` ignored by Git and mode0600. Analytics values remain separate and preserved.
Configuration is optional: missing/partial OAuth settings do not break the Analytics app.
OAuth itself rejects missing, partial or invalid settings. Check without exposing values:

```sh
uv run python -m scripts.check_upstox_oauth
```

The helper does not start Docker, open a browser, exchange tokens or initialize a vault.
After successful setup, deploy private OAuth storage explicitly with
`uv run python -m scripts.bootstrap_local --oauth-vault`, then sign in to the dashboard
and use its OAuth control for genuine consent. The Compose overlay supplies the service
storage path; the helper does not add UPSTOX_OAUTH_VAULT_DIR to the host `.env`.
For a non-Compose deployment, configure that private absolute service path separately.
See [browser flow](UPSTOX_OAUTH_BROWSER.md) and [bootstrap](LOCAL_BOOTSTRAP.md).

It prints only presence/status metadata,unverified registration,false live flags and
unknown tokens_stored=null/token_storage_checked=false. browser_flow_implemented=true
means source exists,not real registered acceptance. Exit0 means CONFIGURED_OPERATOR_DECLARED;exit2 means not configured, incomplete,
invalid or unavailable. It never writes settings, starts Docker, opens a browser, accesses
the database or contacts Upstox. Local format validation cannot verify console registration.

Client IDs use bounded ASCII letters/digits/underscore/hyphen. The callback must be an
absolute HTTPS URL, or HTTP on an explicit local loopback host for development; the provider
must actually accept and register that exact URL. Credentials, query strings, fragments,
control characters and backslashes are rejected. Values are not normalized before exchange.
The configured callback can be mounted by the new router only after all browser/storage
configuration checks pass;this local check does not prove deployment or reachability.

## Implemented protocol safeguards

`backend/app/brokers/oauth.py` provides:

- An authorization URL for the fixed official endpoint, using only response_type=code,
  client_id, exact redirect_uri and mandatory random256-bit state. URL/state are represented
  by SecretStr and omitted from object repr; the URL is never logged by this module.
- A locked, bounded single-process ledger:32pending flows maximum,one per supplied session
  digest,up to5minutes clipped to that session's expiry. Only state/app/session hashes and
  timestamps are retained. Changed app settings,new flow,expiry,replay and clock rollback
  invalidate affected flows. Concurrent callbacks have exactly one successful consumer.
- State consumption bound to the same caller-provided session digest, before code validation
  or network activity. A failed token exchange cannot retry/replay the consumed callback.
- One form-encoded POST to the fixed token endpoint. No arbitrary URL/method,proxy environment,
  redirect following,scope,PKCE,refresh endpoint or automatic retry is introduced. Requests
  have5second network and10second total timeouts;identity JSON responses are bounded64KiB.
  Duplicate JSON fields,invalid bearer formats and compressed/malformed/oversized responses
  fail closed. Exceptions expose fixed local codes instead of remote bodies/PII/secrets.
- A SecretStr-wrapped access-token result with local request/receipt timestamps and a
  conservative next03:30IST cutoff derived from request start. This is documented expiry
  policy,not independently verified broker issuance/validity. Exchanges crossing that cutoff
  or the pending session deadline are rejected. Profile and extended-token fields discarded.

The state ledger does not authenticate users or look up revocation. Future callers must
validate the real active administrator session and supply its digest/expiry. Multi-worker
coordination is not implemented; process restart invalidates pending flows. No pending
flow,secret or token is written to a database or file by the protocol code. Operator-supplied
client settings remain in the ignored local.env;OAuth access tokens are not saved by the
protocol. An opt-in encrypted storage component is now implemented separately;see
[UPSTOX_OAUTH_VAULT.md](UPSTOX_OAUTH_VAULT.md). Browser integration is implemented;
real registered consent and vault initialization remain pending.

## Remaining integration gates

1. Obtain/validate the actual registered public client ID and exact callback;keep the secret
   in protected local configuration. Latest local check in this iteration:NOT_CONFIGURED.
2. Deploy and genuinely verify the implemented authenticated/CSRF start and browser-bound
   one-use callback. See UPSTOX_OAUTH_BROWSER.md for the Strict-cookie popup design.
   Preserve existing administrator SameSite=Strict cookies. Cross-site callback binding must
   be designed and tested explicitly; do not expose a route that trusts state alone or relax
   existing cookies. Recheck session revocation and app configuration on callback.
3. Application/server query scrubbing and HTTP replay/browser/revocation/expiry/denial
   tests are implemented. Review any proxy/edge logging separately before real deployment.
4. Wire the tested encrypted server-only vault to a private backend-owned durable path,
   lifecycle and explicit operator consent;no real store is initialized yet.
   The normal OAuth token is not established as read-only. Never substitute it into the
   Analytics setting or introduce order/funds/trading permissions through this foundation.
5. Complete genuine registered browser authorization and bounded read-only acceptance.
   No genuine browser or upstream token exchange has been performed for this foundation.

Callback routes and UI are now implemented behind local configuration. No real store,
credential rotation,account request,market capture,order adapter or live activation was used. PostgreSQL remains operational;
Google backups and their schedule remain unchanged.

## Verification and primary sources

46synthetic security cases cover URL construction,session binding,replay,concurrent consume,
ledger bounds,expiry/clock/cutoff boundaries,configuration validation,safe failures,fixed token
requests and hostile responses. All token exchanges use httpx.MockTransport with synthetic
credentials. Genuine credentials are never used by tests.

Official contracts rechecked10November2026:
[Authentication](https://upstox.com/developer/api-documentation/authentication/) and
[Get Token](https://upstox.com/developer/api-documentation/get-token/).
