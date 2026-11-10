# Dashboard accessibility verification

Verified 2026-11-06T19:04:02.904861+00:00 UTC. Scope: P1-UI-AUDIT-A, keyboard focus, form-control
contrast and narrow-screen reflow. The overall accessibility audit remains **partial**.

## Corrected defects

- Light focus outline was #8eafff (2.16:1 against white). Theme focus colors now use
  #245bd7 light / #9cb9ff dark; sidebar links use #a8c3ff against the fixed dark navigation.
- Input/select borders used decorative panel borders (1.15:1 against the light input
  background). Dedicated control borders are #7a8799 light / #8494ac dark.
- Select and skip-link main targets now have explicit focus styles. Date input segments
  use :focus-within because Chrome can clear the host :focus-visible state while a native
  date segment retains focus. The existing 3px outline and 4px offset remain.
- At 320px, a content-grid minimum and nonwrapping connection link expanded the page
  to342px. Mobile grid tracks now use minmax(0,1fr), and that link wraps.

Only frontend/css/app.css changed runtime behavior. Decorative panel borders, text,
authentication, APIs, metadata gates and trading settings retain their existing behavior.

## Actual isolated Chrome results

| Viewport | Theme | Distinct Tab targets | Minimum focus contrast | Minimum form border contrast | Horizontal overflow |
|---|---|---|---|---|---|
| 1280px | Light | 18 | 5.51:1 | 3.40:1 | None |
| 1280px | Dark | 18 | 7.90:1 | 4.98:1 | None |
| 320px | Light | 18 | 5.51:1 | 3.40:1 | None |
| 320px | Dark | 18 | 7.90:1 | 4.98:1 | None |

First Tab reaches the skip link; Enter focuses main. Enter activates the theme button.
Tab traversal includes native date segments and the enabled interval select. All tested
controls retain a solid3px outline. Contrast uses sRGB relative luminance from computed
styles: outline against its adjacent background across the4px gap; control border against
both inside and outside backgrounds. Measurements wait for theme transitions to settle.

The W3C [non-text contrast guidance](https://www.w3.org/WAI/WCAG21/Understanding/non-text-contrast.html)
sets a3:1 requirement for relevant control and focus-state cues. These results cover the
listed cues only and do not establish complete WCAG conformance.

## Reproduction and limits

Serve frontend files through an isolated loopback static server with /assets mapped to
frontend; return401 for private API requests. Use a fresh Chrome profile and select its
page CDP target. Do not connect this audit to the operator account or broker. Reveal the
history/chain forms solely in the synthetic page so their ordinary controls can be tabbed;
keep disabled expiry/capture controls disabled. Wait for page readiness/theme transitions.
At each viewport/theme, focus skip, traverse with native Tab events, inspect computed
outline/border colors and bounding boxes. Native date segments can take multiple Tab stops.
No order/submit/import/capture button is activated. Safe aggregate results are in the ignored
reports/dashboard_keyboard_audit.json; one-time harness is local and not a CI test.

Pending: VoiceOver/screen-reader reading order and spoken announcements,
disabled/loaded expiry workflows, physical high contrast, browser-menu zoom and broader text/graphical
contrast. No production-readiness or complete AA claim. Hosted CI remains unconfirmed.

## Authentication focus and error semantics — 10 November 2026

An isolated Chrome/SQLite audit found that successful sign-in and keyboard sign-out hid
the focused control without assigning a visible replacement. Failed passwords had no
programmatic error association or invalid-field state; the existing live status was not
explicitly atomic. These were browser-observed defects, not a broker/authentication failure.

The password now references the status message with aria-describedby. A rejected password
is marked aria-invalid only after a 401; editing clears it. Rate-limit and service failures
do not mark the password wrong. The sign-in form exposes aria-busy and the status region is
atomic. Existing password clearing, cookie, CSRF, Origin and server authentication remain
unchanged. All messages remain fixed text; no secret or raw server error is inserted.

Successful sign-in focuses the Account overview heading, outside the ordinary Tab sequence,
with a visible theme-aware outline and scroll margin. Failure and sign-out focus the password
after the final message is set. When loading overview hides the previously focused account
content, focus returns to sign-in. A still-visible focused control keeps focus on refresh.
Initial page loading does not autofocus or bypass the existing skip-link sequence.

Reproduce with an existing local Chrome executable:

```sh
uv run python -m scripts.verify_oauth_browser \
  --chrome-binary '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --auth-accessibility
```

Fourteen authentication checks pass, alongside the existing OAuth isolation proof. Native
Enter submits the bad-password form and activates sign-out. Chrome's accessibility tree
contains the password error description. DOM checks cover invalid-state reset, password
clearing, atomic status, cleared busy state, successful/expired-session/sign-out focus,
visible-control focus preservation and synthetic 429/503 failures. Those service failures
are intercepted within the temporary browser fixture; they are not operational incidents.

The audit uses a fresh disposable Chrome profile, migrated temporary SQLite and synthetic
credentials. External requests are blocked or intercepted, and token exchange is mocked.
No real profile, operational DB/account, broker or screen-reader speech engine is used.
Zero JavaScript exceptions; temporary listeners/profile/DB/vault are removed. Safe aggregate
receipt:`.local/verification/auth_accessibility_acceptance.json`, ignored/private.
The first harness run needed native Enter text to trigger browser form submission; corrected
before collecting baseline/final results. Baseline failed five of the original seven checks;
the final expanded fourteen checks pass. Full PostgreSQL regression:728passed/0failed/0skipped,
one existing Starlette warning. Ruff121files/format and mypy50backendfiles passed.

This verifies accessible browser semantics and focus behavior. Actual VoiceOver reading and
spoken announcements and the wider audit remain pending. See emulated rendering checks below; this does
not establish full WCAG AA conformance or complete P1-UI-AUDIT.

Primary guidance: [W3C error identification with ARIA](https://www.w3.org/WAI/WCAG22/Techniques/aria/ARIA21.html)
and [status messages](https://www.w3.org/WAI/WCAG21/Understanding/status-messages).

## Forced colors and zoom-equivalent reflow — 10 November 2026

```sh
uv run python -m scripts.verify_oauth_browser \
  --chrome-binary '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' \
  --auth-accessibility --render-accessibility
```

The matrix covers signed-in/signed-out views, light/dark themes through the real theme
button, forced colors on/off and CSS viewports1280×900,640×450,320×225. These are100%,200%,
400% reflow equivalents for a1280×900 starting viewport. Chrome metrics/media emulation
does not exercise browser-menu zoom, text-only enlargement or physical OS high contrast.

All24baseline cases had no page horizontal overflow, visible controls within horizontal
bounds, a distinct current navigation item and visible focused form controls/outlines.
Six signed-in forced-color cases still faded disabled buttons with opacity0.65. The CSS
now uses opacity1 and system GrayText for disabled text/borders only in forced colors.
This preserves the system palette without forced-color-adjust:none. Disabled controls are
exempt from WCAG contrast requirements; the old opacity is not presented as a proven WCAG
contrast violation. Normal themes and disabled behavior are unchanged.

All24final rendering cases pass, alongside14authentication checks and existing OAuth
isolation checks, with0JavaScript exceptions. Cases report visible/disabled control counts;
an empty disabled set is not claimed as disabled-control coverage. Full disposable
PostgreSQL suite728passed/0failed/0skipped;one existing Starlette warning. Ruff122files,
format and mypy50backendfiles passed.

The fixture needed Page.bringToFront after popup return because background animation
frames were suspended. Expected baseline failure diagnostics were separated from JSON
before retaining receipts. Both are harness corrections, not product behavior changes.
Ignored private receipts:render_accessibility_baseline.json and
render_accessibility_acceptance.json under.local/verification. All browser work used fresh
profiles, temporary SQLite, synthetic credentials, mocked exchange and blocked external
requests. No operational profile/account/database or broker was tested.

References:[W3C320CSS-pixel reflow](https://www.w3.org/WAI/WCAG21/Understanding/reflow) and
[forced-color behavior](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/At-rules/@media/forced-colors).
The [inactive-control exception](https://www.w3.org/WAI/WCAG22/Understanding/non-text-contrast)
is documented separately from this palette improvement.
Screen-reader speech, physical palettes, actual browser zoom controls, text-only resizing
and the wider audit remain pending; no full WCAG AA conformance claim.
