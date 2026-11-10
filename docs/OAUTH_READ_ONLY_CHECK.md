# Bounded OAuth market-status verification

The saved ordinary OAuth credential stays quarantined from the Analytics adapter. An
explicit local command can check one documented market-status endpoint using that credential.
It introduces no HTTP route, scheduled job, browser action, account/profile/funds request,
market capture, order operation or credential promotion. Live remains disabled.

For the existing local Compose project, after deploying the reviewed image:

```sh
docker compose --project-name algotrade-ai-local \
  --file docker-compose.yml --file docker-compose.oauth.yml --env-file .env \
  exec -T app python -m backend.app.brokers.oauth_probe
```

Use your configured project name if different. The module accepts no arguments and rejects
unexpected arguments without echoing them. Do not pass credentials on the command line.
It must run inside the app container so it reads the actual private mounted vault. A host
invocation has no configured service path and fails closed. No `.env` or token is changed.

The command requires OBSERVATION/live false, valid app settings, an absolute private vault
and an unexpired token. It loads the token only in process memory using the existing vault
safety checks and sends one GET to the fixed official NSE exchange-status URL. Proxy
environment variables, redirects and retries are disabled. The request has a five-second
network timeout and ten-second total network deadline. The response must be identity-encoded
JSON, at most 64 KiB, without duplicate object keys and with the expected status/exchange/
phase/timestamp schema. Future exchange-state times beyond the existing tolerance are
rejected. Expiry is rechecked before sending and after response validation.

Only allowlisted aggregate results are printed. CHECKED means the endpoint returned a
validated response using the saved credential at that time. It does not certify account
identity, permission scope, read-only nature of the grant, quote freshness, trading session
coverage or future access. An exchange state-change timestamp is not a price timestamp.
The result keeps account_permissions_verified, credential_promoted, recording_started,
entries_enabled and live_enabled false. Response profiles/extras and raw errors are discarded.

401/403 become AUTH_REQUIRED/ACCESS_DENIED; a 429 returns RATE_LIMITED with a bounded
retry_after. There is no automatic retry or polling. Respect that delay before a deliberate
new attempt. Expired storage returns REAUTHORIZE_REQUIRED without a request. Missing,
corrupt or unsafe storage also stops before network activity. Network/timeouts return
UNAVAILABLE; invalid responses never become CHECKED. Exit 0 means CHECKED; exit 2 means
no successful endpoint check. The command never rotates, deletes or repairs credentials.

Verification is one-shot metadata, not a durable permission badge. The dashboard's
STORED_UNVERIFIED status remains the encrypted-storage status and is not rewritten by the
probe. Analytics remains the active credential for all existing data operations.

Automated tests use temporary vaults, fixed synthetic clocks and mocked responses only.
They cover request restriction, secrets/redaction, unchanged Analytics/vault bytes, expiry,
local storage gates, hostile JSON/media/lengths, streamed boundaries, connection failures,
cancellation, redirects and proxy disabling. Genuine operator acceptance is recorded
separately in VERIFICATION.md and agent handoff records.

Official contracts reviewed 10 November 2026:
[exchange status](https://upstox.com/developer/api-documentation/get-market-status/) and
[market phases](https://upstox.com/developer/api-documentation/appendix/market-status/).

## Local acceptance — 10 November 2026

After 39 mocked security cases and the full 713-test PostgreSQL suite passed, the reviewed
image was deployed with the existing OAuth volume retained. One explicit real invocation
returned CHECKED and CLOSING_END. Endpoint verification was true; account permissions,
promotion, recording and entries/live remained false. The token survived app recreation.
Subsequent local-only status checks confirmed unchanged Analytics selection and storage.
The aggregate receipt is ignored/private at `.local/verification/oauth_market_status_probe.json`.
No additional broker probe or retry was made. Hosted CI for these changes remains unverified.
