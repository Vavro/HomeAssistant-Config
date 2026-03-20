---
name: analyze-ha-traces
description: Analyze Home Assistant automation trace JSON files to diagnose why automations are not working. Use this when the user downloads trace files from the HA UI and wants to understand what happened, why a switch didn't trigger a light, or why an automation failed.
---

# Analyzing Home Assistant Automation Traces

When the user has downloaded trace JSON files from the HA UI (Settings → Automations → [automation] → Traces), use the script in this skill directory to analyze them — do NOT write ad-hoc Python code.

## Running the analyzer

```bash
# Single trace
python .github/skills/analyze-ha-traces/analyze_trace.py "trace automation.my_auto 2026-03-16T20_07_05.json"

# Controller + hook pair together (always do this for Awesome HA Blueprints)
python .github/skills/analyze-ha-traces/analyze_trace.py "trace automation.controller 2026-03-16T20_07_05.json" "trace automation.hook 2026-03-16T20_07_05.json"

# All traces in current directory at once
python .github/skills/analyze-ha-traces/analyze_trace.py .
```

Always run `.` first to get a summary of all traces, then drill into specific ones if needed.

## Interpreting output

The script auto-detects the automation type and shows:

**For Awesome HA Blueprints controller automations:**
- `ZHA command` — raw command sent by the device
- `mapped action` — abstract name the blueprint mapped it to (e.g. `button_off_short`)
- `trigger_delta` — milliseconds since the previous event from same device
- `EVENT FIRED` — what `ahb_controller_event` action was sent to the hook
- Key variables: `helper_debounce_delay`, `helper_double_press_delay`, `button_X_double_press`

**For Awesome HA Blueprints hook automations:**
- `hook action` — the action received from the controller
- `turn_on/turn_off/brightness_up` etc. — the mapping for this controller model
- `matched branch` — which choose branch executed
- `SERVICE CALLS` — what light/cover/media service was actually called

**For any automation:**
- `❌ (init)` error — automation crashed before any step ran (common after HA updates)
- `⚠ no choose branch matched` — action string not in any mapping

## Common diagnosis patterns

### Hook never fires / light doesn't respond
1. Run the hook traces — if they show `❌ TypeError: NoneType + int` at `(init)`, the hook blueprint crashed during variable initialization
2. This means ALL buttons are broken, not just one
3. Cause: HA 2026.3 removed `color_temp`/`min_mireds`/`max_mireds` light attributes
4. Fix: replace with `color_temp_kelvin`/`min_color_temp_kelvin`/`max_color_temp_kelvin` in the hook blueprint

### Wrong action fires (e.g. double press instead of single press)
1. Look at `trigger_delta` in controller trace
2. If delta < 100ms: device is sending duplicate hardware events (zigpy regression, ~Feb 2026)
3. Fix: set `helper_debounce_delay = 100` in the controller automation
4. Do NOT disable double press — the debounce preserves it for genuine human double clicks (>150ms)

### Specific button stopped working (others still work)
1. Look at `ZHA command` in controller trace
2. Compare with the blueprint's `actions_mapping` ZHA section
3. If the ZHA command (e.g. `off_with_effect`) is not in the mapping, add it
4. Common after zigpy 1.0.0 (Feb 2026): Philips RWL021 OFF button changed from `off_short_release` to `off_with_effect`

### How to download traces
HA UI: Settings → Automations → click the automation → clock icon (top right) → download individual JSON files.
For Awesome HA Blueprints: download both the **controller** trace AND the **hook** trace for the same button press (match by timestamp). HA only keeps the last 5 traces per automation — do one button press type at a time if you need to avoid overwriting.

## Awesome HA Blueprints architecture

```
Physical button press
  → ZHA event (command: "off", cluster 6)
  → Controller blueprint (maps ZHA command → abstract action e.g. button_off_short)
  → fires ahb_controller_event (action: button_off_short, controller: <device_id>)
  → Hook blueprint (maps abstract action → light.turn_off / light.turn_on etc.)
```

Blueprint files live in `/config/blueprints/automation/EPMatt/` on the HA instance:
- `philips_324131092621.yaml` — Philips Hue RWL021 dimmer (model 324131137411)
- `ikea_e2001_e2002_new.yaml` — IKEA STYRBAR (E2001/E2002)
- `light_new.yaml` — Hook - Light Edited (the active modified hook, use this one)
- `light.yaml` — original EPMatt hook (not used)

After editing any blueprint: Developer Tools → YAML → Reload Automations.

## Developing and extending this skill

### Directory structure

```
.github/skills/analyze-ha-traces/
  analyze_trace.py        ← main analyzer script
  SKILL.md                ← this file
  tests/
    test_analyze_trace.py ← test runner
    fixtures/             ← minimal anonymized trace JSON files
      hook_init_crash_color_temp.json
      controller_duplicate_zha_event.json
      hook_success_turn_off.json
      controller_no_branch_matched.json
```

### Running tests

```bash
python .github/skills/analyze-ha-traces/tests/test_analyze_trace.py
```

All tests must pass before pushing changes to the analyzer.

### Adding a new test case

1. **Save a real trace as a fixture** in `tests/fixtures/<descriptive_name>.json`
   - Anonymize `device_ieee` and `entity_id` if desired (not required — no secrets in traces)
   - Keep only the trace nodes needed to reproduce the scenario (trigger, variables, key action nodes)
   - Name it after the scenario: `hook_success_turn_on.json`, `controller_off_with_effect.json` etc.

2. **Add a test function** in `test_analyze_trace.py`:
   ```python
   def test_my_scenario():
       """One-line description of what this tests and why the fixture exists."""
       out = run("my_fixture.json")
       check(
           "my_scenario",
           out,
           must_contain=["expected string", "another string"],
           must_not_contain=["string that must not appear"],
       )
   ```

3. **Call it** at the bottom of the file and run the suite.

### What makes a good fixture

- **Minimal** — only the trace nodes that matter for the scenario
- **Self-contained** — no external dependencies
- **Documented** — the test docstring explains what broke, what the root cause was, and what the fix was
- The `config.alias` field should be a realistic automation name so name detection is tested too

