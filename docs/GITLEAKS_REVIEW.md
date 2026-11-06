# Gitleaks review and scoped remediation

Updated:2026-11-06T15:31:49.450576+00:00. No suspected values are reproduced here or in the allowance file.

| Filename | Detection | Classification | Remediation |
|---|---|---|---|
| docs/CAPTURE_PREFLIGHT.md:90 | generic-api-key | Verified false positive: ordinary slash-separated negative test-case prose, not a credential or placeholder. | Exact finding fingerprint in .gitleaksignore, with justification. Source unchanged. |
| backend/app/market_data/calendar_data/market-timings.html:118 | generic-api-key | Verified false positive for secret exposure: public mPulse/Boomerang browser application identifier embedded in archived public NSE HTML, not a private authentication credential. | Exact finding fingerprint in .gitleaksignore, with justification. Source and calendar checksums unchanged. |

## Verification

Original report:/tmp/algotrade-scan.bCIDm5/report.json. Its secret fields are redacted; actual
matching values were inspected locally through a private temporary scanner report and checked
against source. No detected values were emitted during this remediation, copied into new
repository files, or included in commit messages. The temporary unredacted report was removed.
The prior review accidentally displayed public HTML context; subsequent reviews use
classification metadata only. Current source files are byte-identical to commit37d8cd9.

Akamai documents that the visible browser key identifies an mPulse application and is not a
private key; authentication uses a separate token. Primary sources:
[mPulse concepts](https://techdocs.akamai.com/mpulse/reference/api-concepts) and
[origin snippet setup](https://techdocs.akamai.com/mpulse/docs/set-up-behavior-options).
Neither finding requires credential rotation or removal. The previously exposed local admin
password had already been rotated in a separate task; this task changes no operator secrets.

Gitleaks8.30.1 default-rule full-history scan, with project ignores bypassed, reproduced
exactly these two findings in37d8cd90fe616f9a2f1117c5c182b67fee8085fc. There is one reachable
local commit. Baseline exit1, two findings, no additional detections. Previous review also
compared all142reachable committed blobs against current configured operator secrets and
found no matches; that prior result is not an exhaustive proof about all possible secrets.

## Narrow allowances

.gitleaksignore contains exactly two fingerprints. Each includes the full immutable commit
ID, exact filename, rule identifier and line number. No matched value is stored in this file.
No entire file, directory, commit or rule is excluded. Default Gitleaks rules remain active;
there is no replacement config, disabled rule, bulk baseline or inline allow marker.

Gitleaks supports this specific-finding mechanism in its
[official versioned documentation](https://github.com/gitleaks/gitleaks/blob/v8.30.1/README.md#gitleaksignore).
If the same text is introduced in a new commit, the fingerprint changes and it requires a
fresh review. Directory scans have different fingerprints and can still flag these two
harmless source occurrences; this remediation targets the requested full Git-history scan.
Do not copy these exceptions into broader path/content exclusions to hide future findings.

## After-remediation results

- Full reachable Git history with repository .gitleaksignore:exit0, zero unallowed findings.
  Exactly two reviewed historical false positives are allowed, not removed from source.
- Isolated synthetic test:the same ignore file did not suppress newly generated fake
  generic-api-key findings at either same file path/line in a different commit. Both were
  detected (expected exit1). Synthetic values remained in a private temporary fixture and
  were never added to this project or displayed. Fixture removed after verification.
- Source files unchanged; calendar evidence integrity PASS. Git whitespace checks PASS.
- No Python/app/UI/schema/dependency/broker/environment/security-setting changes. No actual
  broker calls, credential rotation, execution activation or recording. OBSERVATION retained.
- No project staging, commit, history rewrite, remote access, push or force-push performed.
  Runtime regression tests not rerun for ignore-file/documentation-only changes.

Reproduce from repository root with the reviewed Gitleaks version/default rules:

```sh
gitleaks git --log-opts="--all --full-history" --redact=100 --no-banner .
```

Ensure no environment/config overrides hide rules. A CI checkout must contain full history
and the reviewed .gitleaksignore; a scanner that bypasses the ignore file will still report
the two acknowledged harmless detections. Do not treat a bypassed-ignore scan's exit1 as a
new confirmed credential exposure without inspecting its metadata.

## Actions before first public push

Review and make a normal follow-up commit containing .gitleaksignore, this review and the
requested handoff updates. This agent has not staged or committed them. Then rerun the full
history command on the final proposed refs; require exit0 with no additional unreviewed
findings. Keep real operator environment/password files excluded from Git. No history cleaning
or credential rotation is necessary for these two false positives. No force-push or history
rewrite is needed or authorized. This result is limited to reachable local history and the
reviewed findings, not a production security approval or audit of remote/dangling objects.
If a different actual secret is found later, stop publication, rotate it and obtain approval
for a separately reviewed cleanup procedure; never auto-rewrite history.
