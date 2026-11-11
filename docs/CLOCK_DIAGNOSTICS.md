# Read-only time diagnostics and coverage limits

The 11 November 2026 genuine feed samples sometimes arrived with broker generation time
roughly 0.1 seconds ahead of local receipt time. This does not establish which clock is
incorrect. Lifecycle `RECENT_TRADE` is a research health label; conservative coverage also
requires nonnegative frame and trade ages. The two labels need not agree.

## Verified measurements

macOS `/usr/bin/sntp` was inspected through its local manual before use. These commands
only measure time; clock-setting/slewing options were not supplied:

```sh
/usr/bin/sntp -t 3 time.apple.com
/usr/bin/sntp -t 3 time.cloudflare.com
```

Apple returned +85.321 ms with +/-93.765 ms uncertainty. Cloudflare returned +66.557 ms
with +/-87.767 ms uncertainty; one address timed out before a successful exchange. Their
uncertainty ranges include zero, so these results do not prove a clock fault or certify
broker time. Do not interpret timeout diagnostic values as measured offsets.

Five host-before / container-time / host-after comparisons had 41.969–61.050 ms round trips.
Every clock-offset bracket includes zero; their intersection is approximately -5.827 to
+35.932 ms (container minus host), under the bracket measurement assumptions. These reads
do not independently establish UTC accuracy or the broker's own timestamp semantics.
No system time, synchronization setting or container configuration was changed.

## Handling the evidence

Keep raw archived timestamps and all existing age checks. Do not add the measured offset
to receipts, clamp negative coverage ages, relax tolerances or fabricate missing samples.
Use independent lower-uncertainty time checks before longer collection; leave the cause
unverified until evidence distinguishes host, container, network and broker timing.

The controlled reconnect acceptance used one 80-second capture with two maximum attempts.
Only its own first real socket was closed once after a genuine update. The unchanged
runner waited normal backoff and obtained fresh authorization. This is a deliberate close
of a real connection, not a naturally occurring outage or a synthetic market frame.
Coverage was verified not to bridge the 31.488-second disconnect-to-snapshot gap.

Scoped results: 82 canonical events / 78,177 bytes; 13 accepted samples / 307 sampled ms,
58 unusable frames, both attempts closed and no active app HTTPS socket afterward. This
proves the bounded path observed on that run; it does not certify all network failure modes,
a full session, seven observation days, strategy readiness or trading permission.

Private receipts live under ignored `.local/verification/`; suspected secrets and OAuth
material are never part of these reports. PostgreSQL remains the operational store.
OBSERVATION mode and disabled live execution remain mandatory.
