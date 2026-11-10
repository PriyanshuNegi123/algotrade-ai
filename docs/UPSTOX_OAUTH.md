# Upstox OAuth protocol foundation

Status: protocol and optional configuration foundation implemented; end-to-end browser
OAuth is not implemented or accepted. This is separate from the working Google Drive OAuth
and the existing Upstox Analytics market-data path. Phase2 remains partial and live stays off.

## Local settings

Save the following variables in the project `.env`, using values from your registered
Upstox application. Keep the API secret local; never paste it or any token into chat:

```dotenv
UPSTOX_CLIENT_ID=YOUR_REGISTERED_PUBLIC_API_KEY
UPSTOX_CLIENT_SECRET=YOUR_LOCAL_API_SECRET
UPSTOX_REDIRECT_URI=YOUR_EXACT_REGISTERED_CALLBACK_URL
```

These are placeholders, not usable credentials or a proposed callback registration.
Keep `.env` ignored by Git and mode0600. Existing Analytics values must remain separate.
Configuration is optional: missing/partial OAuth settings do not break the Analytics app.
OAuth itself rejects missing, partial or invalid settings. Check without exposing values:

```sh
uv run python -m scripts.check_upstox_oauth
```

It prints only field-presence booleans, a fixed status and false registration/browser/token/
live flags. Exit0 means CONFIGURED_OPERATOR_DECLARED;exit2 means not configured, incomplete,
invalid or unavailable. It never writes settings, starts Docker, opens a browser, accesses
the database or contacts Upstox. Local format validation cannot verify console registration.

Client IDs use bounded ASCII letters/digits/underscore/hyphen. The callback must be an
absolute HTTPS URL, or HTTP on an explicit local loopback host for development; the provider
must actually accept and register that exact URL. Credentials, query strings, fragments,
control characters and backslashes are rejected. Values are not normalized before exchange.
This validation does not set up a callback server or prove its reachability.

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
client settings remain in the ignored local.env;OAuth access tokens are not saved.

## Remaining integration gates

1. Obtain/validate the actual registered public client ID and exact callback;keep the secret
   in protected local configuration. Latest local check in this iteration:NOT_CONFIGURED.
2. Add authenticated,origin/CSRF-protected start and secure one-use callback integration.
   Preserve existing administrator SameSite=Strict cookies. Cross-site callback binding must
   be designed and tested explicitly; do not expose a route that trusts state alone or relax
   existing cookies. Recheck session revocation and app configuration on callback.
3. Prevent callback query/code/token logging at application,server and any proxy layer; add
   replay/cross-browser/session-revocation/expiry/denial tests through actual HTTP routes.
4. Add protected server-only credential storage, lifecycle and explicit operator consent.
   The normal OAuth token is not established as read-only. Never substitute it into the
   Analytics setting or introduce order/funds/trading permissions through this foundation.
5. Complete genuine registered browser authorization and bounded read-only acceptance.
   No genuine browser or upstream token exchange has been performed for this foundation.

No callback route,UI,real token store,credential rotation,broker account request,market
capture,order adapter or live activation is included. PostgreSQL remains operational;
Google backups and their schedule remain unchanged.

## Verification and primary sources

46synthetic security cases cover URL construction,session binding,replay,concurrent consume,
ledger bounds,expiry/clock/cutoff boundaries,configuration validation,safe failures,fixed token
requests and hostile responses. All token exchanges use httpx.MockTransport with synthetic
credentials. Genuine credentials are never used by tests.

Official contracts rechecked10November2026:
[Authentication](https://upstox.com/developer/api-documentation/authentication/) and
[Get Token](https://upstox.com/developer/api-documentation/get-token/).
