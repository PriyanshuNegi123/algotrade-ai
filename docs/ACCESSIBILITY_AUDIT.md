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

Pending: VoiceOver/screen-reader reading order, authenticated dynamic announcements and
error focus, disabled/loaded expiry states, forced-colors, zoom and broader text/graphical
contrast. No production-readiness or complete AA claim. Hosted CI remains unconfirmed.
