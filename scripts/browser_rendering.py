"""Synthetic browser-only reflow/forced-color checks, not real OS or screen-reader proof."""

import json

MEASURE = """(() => {
  const visible = node => node.getClientRects().length > 0;
  const controls = [...document.querySelectorAll('a,button,input,select')].filter(visible);
  const active = getComputedStyle(document.querySelector('.nav-item.active'));
  const inactive = getComputedStyle(document.querySelector('.nav-item:not(.active)'));
  const focused = document.activeElement;
  const style = getComputedStyle(focused);
  const forced = matchMedia('(forced-colors: active)').matches;
  const disabled = controls.filter(node => node.disabled);
  const bad = controls.filter(node => {
    const r = node.getBoundingClientRect();
    return r.left < -1 || r.right > innerWidth + 1;
  });
  return {
    css_width: innerWidth,
    no_horizontal_overflow: document.documentElement.scrollWidth <= innerWidth + 1,
    controls_fit: bad.length === 0,
    overflow_control_ids: bad.map(node => node.id || node.tagName),
    selected_navigation_visible: (parseFloat(active.borderLeftWidth) >= 2 &&
      active.borderLeftStyle !== 'none') || active.boxShadow !== 'none' ||
      active.backgroundColor !== inactive.backgroundColor || active.color !== inactive.color,
    focused_control_visible: visible(focused) && focused.getBoundingClientRect().top >= -1 &&
      focused.getBoundingClientRect().bottom <= innerHeight + 1,
    focus_outline_visible: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 3 &&
      style.outlineColor !== 'rgba(0, 0, 0, 0)',
    disabled_palette_unfaded: !forced || disabled.every(node =>
      getComputedStyle(node).opacity === '1'),
    forced_colors_active: forced,
    disabled_controls_checked: disabled.length,
    controls_checked: controls.length
  };
})()"""


async def audit_rendering(send, evaluate, session, *, signed_in):
    cases = []
    try:
        await send("Page.bringToFront", session=session)
        for width, height in [(1280, 900), (640, 450), (320, 225)]:
            await send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": width,
                    "height": height,
                    "deviceScaleFactor": 1,
                    "mobile": False,
                },
                session,
            )
            for theme in ("light", "dark"):
                for forced in (False, True):
                    await send(
                        "Emulation.setEmulatedMedia",
                        {
                            "features": [
                                {"name": "forced-colors", "value": "active" if forced else "none"},
                                {"name": "prefers-color-scheme", "value": theme},
                            ]
                        },
                        session,
                    )
                    await evaluate(
                        'if(document.body.classList.contains("dark") !== '
                        + json.dumps(theme == "dark")
                        + ') document.getElementById("theme").click();true'
                    )
                    # Native keyboard modality, then focus an actual visible form control.
                    await send(
                        "Input.dispatchKeyEvent",
                        {
                            "type": "keyDown",
                            "key": "Tab",
                            "code": "Tab",
                            "windowsVirtualKeyCode": 9,
                        },
                        session,
                    )
                    await send(
                        "Input.dispatchKeyEvent",
                        {"type": "keyUp", "key": "Tab", "code": "Tab", "windowsVirtualKeyCode": 9},
                        session,
                    )
                    target = "history-key" if signed_in else "password"
                    await evaluate(
                        "document.getElementById(" + json.dumps(target) + ").focus();"
                        "new Promise(resolve => requestAnimationFrame(() => "
                        "requestAnimationFrame(resolve)))"
                    )
                    result = await evaluate(MEASURE)
                    result.update(
                        theme=theme,
                        forced_expected=forced,
                        view="authenticated" if signed_in else "signed_out",
                    )
                    checks = [
                        "no_horizontal_overflow",
                        "controls_fit",
                        "selected_navigation_visible",
                        "focused_control_visible",
                        "focus_outline_visible",
                        "disabled_palette_unfaded",
                    ]
                    result["passed"] = all(result[key] for key in checks) and (
                        result["forced_colors_active"] == forced
                    )
                    cases.append(result)
    finally:
        await send("Emulation.setEmulatedMedia", {"features": []}, session)
        await send("Emulation.clearDeviceMetricsOverride", session=session)
        await evaluate(
            'if(document.body.classList.contains("dark")) '
            'document.getElementById("theme").click();true'
        )
    return {
        "passed": all(case["passed"] for case in cases),
        "cases": cases,
        "real_browser_zoom_tested": False,
        "real_os_high_contrast_tested": False,
        "reflow_equivalence": "1280 at 100%, 640 at 200%, 320 at 400%",
    }
