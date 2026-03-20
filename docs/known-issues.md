# Known Issues & Fixes Applied

A running log of breaking changes encountered during HA/integration updates and the fixes applied. Keep this file up to date when a PR fixes a compatibility issue — it serves as context for diagnosing future regressions.

---

## How to use this file

When an HA update, integration update, or blueprint change breaks something:
1. Diagnose using the trace analyzer (see [`SKILL.md`](../.github/skills/analyze-ha-traces/SKILL.md))
2. Apply the fix
3. Add an entry here **in the PR that contains the fix**, so the log stays in sync with the actual changes

---

## Log

### HA 2026.3 — Light `color_temp` attributes removed

**Affected:** All remotes using `light_new.yaml` hook blueprint (brightness/colour temperature stepping)

**Symptom:** Hook automation crashed at init with `TypeError: NoneType + int` — **all** button actions stopped working, not just colour temperature ones.

**Root cause:** HA 2026.3 removed the `color_temp` (mireds), `kelvin`, `min_mireds`, and `max_mireds` light state attributes. The hook blueprint's variable block read these at startup; getting `None` caused an arithmetic crash before any trigger was registered.

**Fix applied in:** `blueprints/automation/EPMatt/light_new.yaml`
- Variables block: replaced `color_temp` → `color_temp_kelvin`, `min_mireds` → `min_color_temp_kelvin`, `max_mireds` → `max_color_temp_kelvin`
- All `light.turn_on` service calls: replaced `color_temp:` (mireds) → `color_temp_kelvin:`
- Step direction inverted where needed: kelvin is opposite to mireds (higher = cooler/whiter)
- Step size changed from 50 mireds → 200 kelvin

**Watch out for:** Any blueprint or custom card that reads `color_temp`, `min_mireds`, or `max_mireds` from light state attributes.

---

### zigpy 1.0.0 (Feb 2026) — Philips RWL021 OFF button command renamed

**Affected:** Philips Hue RWL021 dimmer — OFF button only

**Symptom:** OFF button press visible in ZHA device events but no action fired by the controller automation (`⚠ no choose branch matched`).

**Root cause:** zigpy 1.0.0 renamed the ZHA command for the Philips RWL021 OFF button from `off_short_release` to `off_with_effect` (cluster 0x0006).

**Fix applied in:** `blueprints/automation/EPMatt/philips_324131092621.yaml`
- Added `- off_with_effect` alongside the existing `- off_short_release` in the `button_off_short` ZHA actions mapping (kept both for backward compatibility)

---

### zigpy 1.0.0 (Feb 2026) — IKEA STYRBAR duplicate ZHA events

**Affected:** All IKEA STYRBAR (E2001/E2002) controller automations

**Symptom:** Short press (single) incorrectly detected as double press. `trigger_delta` in traces showed ~35–60ms between two identical events for a single button press.

**Root cause:** zigpy 1.0.0 regression causes STYRBAR to emit two identical ZHA events per physical button press, ~35–60ms apart. With `helper_debounce_delay = 0`, the first run writes the helper timestamp immediately; the second run arrives 35–60ms later, sees `trigger_delta < helper_double_press_delay (500ms)`, and fires the double-press action.

**Fix applied:** Set `helper_debounce_delay = 75` on all three STYRBAR controller automations via HA UI (Kids room bed light, Kids room table light, Office lights).

**Why 75ms works:** The automation uses `mode: restart` — a new trigger cancels the previous run. With 75ms debounce, the first run is killed by the second event (at ~35–60ms) before it writes the helper, so the second run sees the old (large) delta and correctly fires single press. Genuine human double presses are naturally >150ms apart, so they still work.

**Follow-up recommendation:** Set `helper_debounce_delay` to `75-100` for any new STYRBAR automations created from the blueprint. The currently working automations were adjusted manually in HA UI to `75`.
