# Broker field-unit evidence and unresolved normalization

Review:10 November2026. Scope:the currently reviewed Upstox BOD JSON, option-chain V2 and
feed V3 technical documentation. This review does not certify every broker document,
segment or historical API version. No unit conversion is authorized by numerical examples.

| Field/source | Established by reviewed technical contract | Remaining uncertainty | Current behavior |
|---|---|---|---|
| BOD JSON tick_size | Minimum instrument price increment | A rupee/paise scaling rule for our selected JSON segments was not established | Retain tick_size_raw and BROKER_UNVERIFIED; no division or rounding |
| V2 chain IV/POP | Numeric option metrics | Percentage-versus-fraction convention is not established for all returned values | Preserve supplied numeric strings, including values above1; do not multiply/divide100 |
| V2 chain theta/vega | Time decay and volatility sensitivity | Exact time basis, volatility step and quantity basis are not specified | Preserve sign/value; no daily/annual or per-lot conversion |
| V2 chain delta/gamma | Directional sensitivity and delta change | Read-time unit context does not certify a normalized quantity basis | Existing sign/range checks unchanged; raw values retained |
| V3 option Greeks | Greek fields described independently | V3 descriptions do not establish equivalence with V2 chain scaling | Do not transfer conventions between endpoints |

Primary technical sources inspected:

- [Instrument JSON field descriptions](https://upstox.com/developer/api-documentation/instruments/)
- [Option-chain V2 response fields](https://upstox.com/developer/api-documentation/get-pc-option-chain/)
- [Market Data Feed V3 fields](https://upstox.com/developer/api-documentation/v3/get-market-data-feed/)

The instrument page also has CSV examples; these are not a normalization contract for JSON.
Educational explanations of Greeks describe mathematical intuition but do not specify an
API's precise serialization basis. Third-party adapters and plausible example magnitudes
are not promoted to primary evidence. The unresolved conclusions are bounded to this review;
they do not assert that no authoritative clarification exists anywhere.

## Explicit option-chain read context

Snapshot metadata now adds `unit_context` to capture receipts, latest status and paginated
reads. It has a stable review identifier/date, fixed primary source URL, UNRESOLVED status,
and BROKER_UNVERIFIED labels for each supplied Greek field. units_verified,
normalization_applied, contract_multiplier_applied and execution_eligible stay false.

The scope is CURRENT_READ_CONTEXT_NOT_CAPTURE_TIME_CERTIFICATION. This describes the
current interpretation policy, not what the broker guaranteed on an older snapshot's date.
It is computed during serialization; canonical archives, hashes, database schema and stored
Greek dictionaries are unchanged. No backfill, new broker fetch, missing-value fabrication
or arithmetic is performed. Each response gets its own metadata object.

Existing delta CE/PE bounds are validation policy, not independent evidence that units were
certified. No validation or execution check was relaxed. Future normalization requires
endpoint/segment-specific primary clarification, explicit conversion/versioning policy,
raw-value lineage and independent tests before any downstream calculations are permitted.

## Verification

Seven new cases cover fractional and percent-looking IV values without rescaling, signed
theta/unchanged quantities, empty/missing Greeks, metadata isolation and native PostgreSQL
archive preservation. Actual SQL reads are SELECT-only and do not load deferred canonical
bytes; a separate controlled archive comparison confirms unchanged bytes and hashes.
Existing authenticated API/CSRF/cooldown tests now also assert the unresolved context.
Full disposable PostgreSQL suite:735passed,0failed,0skipped;one existing Starlette warning.
The default targeted run had33passed/1PostgreSQL skip; native full verification executed it.

The unit uncertainty is now explicit to API consumers. It is not resolved or certified by
adding metadata. Calendar amendment completeness and genuine observation evidence remain
separate Phase2 gates. No account funds, strategy, order or live functionality is added.

Local deployment returned READY_LOCAL with login and retained OAuth volume verified. A
two-leg existing archived response was compared before/after: removing only unit_context
made both status and snapshot payloads identical, including raw values and canonical digest.
No new broker capture was requested. Safe ignored proof:
`.local/verification/unit_context_runtime_acceptance.json`. Credential storage and disabled
entries/live state were rechecked locally. Hosted CI for this change remains unverified.

To resolve the outstanding evidence gate, obtain endpoint/segment-specific primary answers
for BOD JSON tick_size scaling; V2 chain IV/POP scale; theta time basis; vega volatility
step; per-unit versus per-contract quantities; and whether any V3 convention differs.
Record source/version/date and retain original raw values before proposing normalization.
No request to the broker has been sent by this review.
