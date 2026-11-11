# Broker unit clarification — prepared, not sent

Prepared 11 November 2026 for the remaining Phase 2 normalization review. This is a draft
for an official provider channel. No message, issue, ticket or account request has been
submitted. It contains no account identifiers, credentials, tokens or captured private data.
Current raw-value preservation and BROKER_UNVERIFIED labels remain unchanged.

## Public evidence reviewed

| Source | Observation | Limit |
|---|---|---|
| [Instrument JSON contract](https://upstox.com/developer/api-documentation/instruments/) | The JSON field description identifies tick_size as an instrument price increment; examples include 5.0 | Does not explicitly state an INR/paise encoding rule for the selected index CE/PE JSON records; CSV examples are a separate representation |
| [V2 chain contract](https://upstox.com/developer/api-documentation/get-pc-option-chain/) | IV/POP are named metrics; sample IV values include 262.31 and 50.78 | Magnitudes do not establish a scale, and the field table does not provide the needed explicit unit convention |
| [Pinned official V2 chain example](https://github.com/upstox/upstox-python/blob/28655475bcaac5e47bbf7202ad1d55027cbe4d4e/interactive_examples/options_analytics/option_chain_native.py#L139-L140) | Reads IV from the chain result and multiplies it by 100 for percent display | This is an implementation assumption in an example, not confirmation of a universal serialization contract |
| [V3 REST Greek contract](https://upstox.com/developer/api-documentation/option-greek/) | Provides separate numeric Greek fields, including an IV example below one | Does not establish equivalence with V2 chain units or V3 streaming fields |
| [Pinned official V3 Greek example](https://github.com/upstox/upstox-python/blob/28655475bcaac5e47bbf7202ad1d55027cbe4d4e/interactive_examples/options_analytics/option_greeks.py#L144) | Its percentage formatter scales IV and its display commentary describes daily theta | Does not establish V2 theta's time/quantity basis or define calendar/trading-day conventions |

The provider's SDK repository commit is `28655475bcaac5e47bbf7202ad1d55027cbe4d4e`,
committer date 9 November 2026. The two examples were retrieved unauthenticated from that
exact revision and inspected as text only. Downloaded code was not executed or integrated.
The API pages were rechecked on 11 November; their example numbers are public documentation,
not current market observations or unit certification.

This follow-up found an implicit scaling choice in the official example, not sufficient
support to apply it to all supplied values. It does not prove the example or service is
incorrect. Examples, technical descriptions and endpoint versions need an explicit provider
mapping before conversion. Legacy NEST tick explanations and third-party adapters cannot
establish the selected BOD JSON encoding. No conversion follows from numerical plausibility.

## Draft questions for the provider

We are implementing read-only market-data research and preserving original values while
units are unresolved. Please provide current, endpoint/segment-specific definitions and
an authoritative versioned reference for the following:

1. For the public NSE instrument JSON master, specifically NSE_FO index CE/PE records,
   what currency/scale does tick_size use? How should raw 5.0 map to an INR price increment?
   Are there segment, instrument-type, file-format or effective-date exceptions? Please
   distinguish JSON from CSV and instrument-search results.
2. For `GET /v2/option/chain`, are option_greeks.iv and pop fractions, percentage points or
   another representation? Please reconcile the documented IV examples with the pinned
   official example's percent formatting. Which interpretation applies to raw 0.15,
   15.0 and values above 100? Please specify IV annualization and POP definition as well.
3. For that same V2 response, what is theta's time basis (calendar day, trading day, year
   or another interval) and day-count convention? Is the value per underlying unit or
   option contract/lot, and in which premium currency unit?
4. What volatility change does V2 vega represent: a unit volatility change, one percentage
   point or another step? What quantity/premium basis applies, and how does that relate
   to IV's serialization scale?
5. For V2 delta and gamma, what underlying price unit and quantity basis apply? Are any
   Greeks already multiplied by lot size or another contract multiplier? Please distinguish
   validation ranges from guaranteed unit definitions.
6. Are the corresponding conventions identical or different for `GET /v3/market-quote/option-greek`
   and V3 streaming option-Greek fields? Please provide the mapping per
   endpoint and identify version/effective-date changes rather than assuming equivalence.

Please use public or synthetic examples. No credentials, bearer tokens, app secrets,
account IDs, authorization codes or private response bodies are needed for these questions.

## Resolution record required before implementation

Retain the provider's dated answer, endpoint/segment scope, source URL/reference and any
version/effective dates. If it contradicts an example, request the corrected interpretation.
Then propose a separately reviewed conversion policy with raw-value lineage, explicit units,
missing/zero/extreme-value behavior and independent Decimal-based tests. Preserve original
archives/hashes; do not backfill or enable rounding, fills, strategies or execution as part
of this clarification. The current read-context policy remains UNRESOLVED.

Private source copies, retrieval metadata and SHA-256 hashes are retained under ignored
`.local/verification/unit_review_20261111/`; only public references and this draft are tracked.
The read-time unit-context identifier remains unchanged because its behavior is unchanged.
Neither a draft request nor inspected SDK code closes the broker-unit evidence gate.
