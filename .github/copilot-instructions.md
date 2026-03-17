# Home Assistant Configuration

This repository contains a Home Assistant configuration and automation setup.

## Repository Structure

| Path | Purpose |
|------|---------|
| `configuration.yaml` | Main entry point; typically uses `!include` directives to split config |
| `automations.yaml` | Automation definitions (or `automations/` directory with split files) |
| `scripts.yaml` | Reusable scripts |
| `scenes.yaml` | Scene definitions |
| `groups.yaml` | Group definitions |
| `secrets.yaml` | Sensitive values (API keys, passwords) — **never commit this file** |
| `packages/` | Optional: grouped config by domain or room using the [packages pattern](https://www.home-assistant.io/docs/configuration/packages/) |
| `custom_components/` | Custom integrations installed locally |
| `www/` | Lovelace frontend resources |

## Config Validation

Validate the configuration without restarting Home Assistant:

```bash
# Inside the HA container or on the host
hass --script check_config --config /path/to/config

# Or via the Developer Tools > YAML > Check Configuration in the HA UI
```

## Key Conventions

### Secrets

All credentials, tokens, and passwords go in `secrets.yaml` and are referenced with `!secret`:

```yaml
# secrets.yaml
mqtt_password: my_password

# configuration.yaml
mqtt:
  password: !secret mqtt_password
```

### Splitting Configuration

Large config sections use `!include` or `!include_dir_merge_list`:

```yaml
# configuration.yaml
automation: !include_dir_merge_list automations/
script: !include scripts.yaml
```

### Automations

Automations created via the UI are written to `automations.yaml`. Hand-authored automations in the `automations/` directory use the same schema. Every automation should have a unique `id`:

```yaml
- id: "unique_id_here"
  alias: "Descriptive Name"
  trigger: ...
  condition: ...
  action: ...
```

### Templates

Jinja2 templates are used throughout for dynamic values:

```yaml
value_template: "{{ states('sensor.temperature') | float }}"
```

Use the **Template Editor** in Developer Tools to test templates interactively.

### Packages Pattern

The packages pattern allows grouping related config (automations, sensors, scripts) by room or feature into a single file:

```yaml
# configuration.yaml
homeassistant:
  packages: !include_dir_named packages/

# packages/living_room.yaml
automation:
  - id: living_room_lights
    ...
sensor:
  - platform: ...
```

## Entity Naming

Follow HA's `domain.entity_id` convention. Entity IDs use `snake_case`. Friendly names are set via `friendly_name` attribute or in the UI.

## Lovelace

Dashboard configuration lives in `ui-lovelace.yaml` (storage mode stores it in `.storage/` instead). Resources such as custom cards go in `www/`.

## Development Workflow

### Repository

- Public GitHub repo: https://github.com/Vavro/HomeAssistant-Config
- **Never commit `secrets.yaml`** — it is gitignored. All credentials use `!secret` references in YAML.
- The repo is public — double-check no inline credentials before committing.

### Branch Policy

| Who | Where | How |
|-----|-------|-----|
| HA instance (deploy key) | Automations edited via HA UI | Push directly to `master` |
| Local machine / Copilot | Blueprints, config, scripts, new features | Feature branch → PR → merge |

**Before opening a PR:** run the code-review skill to catch issues.  
**Never push directly to `master` from local** — use a PR even for small changes.

### Typical Local Workflow

```bash
git checkout -b fix/description
# make changes
git add .
git commit -m "description"
git push origin fix/description
# open PR on GitHub, review, merge
```

### Syncing HA Changes Locally

After the HA instance pushes UI-driven changes to `master`:
```bash
git pull origin master
```

### Deploying Local Changes to HA

After merging a PR:
```bash
# on HA via SSH
ssh root@homeassistant.local "cd /config && git pull && ha core restart"
```

## Diagnosing Automation Problems

### Downloading Traces

In HA UI: **Settings → Automations → [automation] → Traces** (clock icon top right).
Download the JSON files. For Awesome HA Blueprints, download both the **controller** trace and the **hook** trace for the same button press.

### Analyzing Traces

Use the built-in script — no approval needed, no ad-hoc code required:

```bash
# Single trace
python .github/skills/analyze-ha-traces/analyze_trace.py "trace automation.my_auto 2026-03-16T20_07_05.json"

# Controller + hook pair together
python .github/skills/analyze-ha-traces/analyze_trace.py "trace automation.controller 2026-03-16T20_07_05.json" "trace automation.hook 2026-03-16T20_07_05.json"

# All traces in current directory
python .github/skills/analyze-ha-traces/analyze_trace.py .
```

The script reads all variables, matched branches, service calls, events fired, and errors from each trace and prints a structured summary.

### What to Look For

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `❌ TypeError: NoneType + int` at `(init)` | HA 2026.3 removed `color_temp`/`min_mireds`/`max_mireds` light attributes | Replace with `color_temp_kelvin`/`min_color_temp_kelvin`/`max_color_temp_kelvin` in hook blueprint |
| Controller fires but hook never triggers | Hook crash at init (see above) | Fix hook blueprint |
| `trigger_delta` very small (< 100ms) | Device sends duplicate ZHA events per press (zigpy regression) | Set `helper_debounce_delay = 100` in controller automation |
| `trigger_delta < helper_double_press_delay`, wrong action fires | Duplicate hardware event detected as double press | Same — set debounce delay |
| OFF button fires `off_with_effect` instead of `off_short_release` | ZHA quirk command rename (zigpy 1.0.0, Feb 2026) | Add `- off_with_effect` to `button_off_short` in controller blueprint ZHA mapping |
| No choose branch matched | Action string not in any mapping | Check ZHA command names match blueprint's `actions_mapping` |

### Awesome HA Blueprints Architecture

```
Physical button press
  → ZHA event  (command: "off", cluster 6)
  → Controller blueprint  (maps ZHA command → abstract action e.g. button_off_short)
  → fires ahb_controller_event  (action: button_off_short)
  → Hook blueprint  (maps abstract action → light.turn_off / light.turn_on etc.)
```

Controller blueprints live in `/config/blueprints/automation/EPMatt/`:
- `philips_324131092621.yaml` — Philips Hue RWL021 dimmer
- `ikea_e2001_e2002_new.yaml` — IKEA STYRBAR (E2001/E2002)

Hook blueprints:
- `light_new.yaml` — "Hook - Light Edited" (local modified version, use this one)
- `light.yaml` — original EPMatt hook

### Known Issues (2026)

**HA 2026.3 (March 2026):** `color_temp`, `kelvin`, `min_mireds`, `max_mireds` light state attributes removed. Use `color_temp_kelvin`, `min_color_temp_kelvin`, `max_color_temp_kelvin` instead. Affects hook blueprint variable block and all `light.turn_on` service calls using `color_temp:`.

**zigpy 1.0.0 (Feb 2026):** Philips RWL021 OFF button now sends `off_with_effect` (ZCL cluster 0x0006) instead of `off_short_release`. IKEA STYRBAR sends duplicate `on`/`off` events ~35–60ms apart per press. Fix: add `- off_with_effect` to Philips controller blueprint; set `helper_debounce_delay = 100` for STYRBAR automations.

