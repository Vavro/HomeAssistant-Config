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

**Always validate before restarting HA.** Use the supervisor CLI over SSH:

```bash
ssh root@homeassistant.local "ha core check"
```

This runs a full config parse without restarting. Exit code 0 = valid. Any errors are printed to stdout. Only restart after a clean check.

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

Dashboard configurations are YAML-mode files loaded via `lovelace:` in `configuration.yaml`:

| File | Dashboard |
|------|-----------|
| `ui-lovelace.yaml` | Default dashboard |
| `lovelace-domov.yaml` | Domov (rooms + car) dashboard |
| `lovelace-location.yaml` | Location dashboard |

Resources (custom cards) are registered in `configuration.yaml` under `lovelace: resources:`. Custom card JS files live in `www/`.

### HACS Custom Cards in Use

| Card | Resource path | Purpose |
|------|--------------|---------|
| `apexcharts-card` | `/hacsfiles/apexcharts-card/apexcharts-card.js` | Advanced charts (mileage, etc.) |
| `flex-table-card` | `/hacsfiles/flex-table-card/flex-table-card.js` | Flexible table layouts |
| `template-entity-row` | `/hacsfiles/lovelace-template-entity-row/template-entity-row.js` | Jinja2-templated entity rows that render identically to native HA rows |
| `card-mod` | `/hacsfiles/lovelace-card-mod/card-mod.js` | Conditional CSS styling on any card |

### Dashboard Editing Workflow

Lovelace YAML changes do **not** require an HA restart — a browser refresh is enough. The edit cycle is:

```bash
# 1. Edit YAML locally
# 2. Lint
yamllint lovelace-domov.yaml
# 3. Deploy via SCP (instant — no restart needed)
scp lovelace-domov.yaml root@homeassistant.local:/homeassistant/lovelace-domov.yaml
# 4. Screenshot to verify visually
python .github/scripts/ha_screenshot.py yaml-domov/7
# 5. View screenshot in .tmp/, iterate
```

### Visual Feedback Loop (Playwright Screenshots)

A Playwright-based screenshot tool at `.github/scripts/ha_screenshot.py` captures dashboard screenshots for visual iteration without relying on user screenshots.

**Prerequisites:** `pip install playwright && playwright install chromium`

**Auth setup:** Create a `.env` file (gitignored) with:
```
HA_URL=http://homeassistant.local:8123
HA_USERNAME=copilot
HA_PASSWORD=<password>
```

The script authenticates via the HA login UI form, caches the session in `.tmp/ha_storage_state.json` (gitignored), and reuses it on subsequent runs. Use `--relogin` to force a fresh login.

**Usage:**
```bash
# Screenshot a specific view (dashboard/view_index)
python .github/scripts/ha_screenshot.py yaml-domov/7
# Custom viewport size
python .github/scripts/ha_screenshot.py yaml-domov/7 --width 1400 --height 1000
```

Output: `.tmp/screenshot-yaml-domov-7.png` (gitignored via `.tmp/`)

**Note:** HA long-lived API tokens do NOT work for frontend auth — the frontend requires OAuth tokens from the login flow. The script must use username/password login.

### Sections View Layout

The car dashboard (view 7 in `lovelace-domov.yaml`) uses the `sections` view type for explicit grid control:

```yaml
type: sections
max_columns: 3
sections:
  - type: grid  # Column 1
    cards:
      - type: picture-entity
        layout_options:
          grid_columns: 4  # Full section width
      - type: entities
        layout_options:
          grid_columns: 4
  - type: grid  # Column 2
    cards: ...
```

**Key constraints:**
- Each section is a `type: grid` with `cards:`
- Use `layout_options: grid_columns: 4` for full-width cards
- Use `layout_options: grid_rows: N` to control card height (e.g., map cards)
- **Custom cards (apexcharts-card) reject `layout_options`** — omit it for those cards; they auto-size to full width

### Card Styling with template-entity-row + card-mod

**Do NOT use markdown cards for data display** — HA sanitizes CSS (strips flexbox, grid, table-layout) and `<ha-icon>` inside markdown renders white instead of themed blue.

Use `template-entity-row` for native-looking rows with templated state/icons:
```yaml
- type: custom:template-entity-row
  entity: sensor.tire_pressure_front_left
  icon: mdi:car-tire-alert
  name: Front Left
  state: "{{ states('sensor.actual') }} / {{ states('sensor.target') }} kPa"
  secondary: "Δ {{ diff }} kPa"
```

Use `card-mod` for conditional icon colors:
```yaml
  card_mod:
    style: |
      :host {
        --card-mod-icon-color: {% if val <= 10 %} #4caf50 {% elif val <= 20 %} #ff9800 {% else %} #f44336 {% endif %};
      }
```

**card-mod notes:** Use `--card-mod-icon-color` (not deprecated `--paper-item-icon-color`). Use `var(--state-icon-color)` for default themed icon color.

### Debugging Card Errors

Custom card errors appear as red ⊘ cards. The error message is buried in HA's deep shadow DOM. Use Playwright to extract it:

```javascript
// In page.evaluate():
function findInShadow(root, selector, depth) {
  // Recursively search shadow roots for 'hui-error-card'
  // Read e._config for the error message
}
```

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

**Before opening a PR:** use the `analyze-ha-traces` skill to verify any automation changes work correctly, and rely on the Copilot automated PR review for code quality.  
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

### Deploying Local Changes to HA ("uptake")

After merging a PR, always follow this sequence — **never skip the check step**:

```bash
# 1. Pull latest master
# 2. Validate config (MUST pass before restart)
# 3. Restart HA
ssh root@homeassistant.local "cd /homeassistant && git pull && ha core check && ha core restart"
```

If `ha core check` fails, **do not restart** — diagnose and fix the config error first. A failed restart can leave HA in a broken state.

## Skills

Use these skills instead of raw SSH or shell commands:

| Task | Skill |
|------|-------|
| Deploy after merging a PR (pull → validate → restart) | `ha-deploy` |
| Inspect HA status, logs, entities, config entries, Lovelace | `ha-investigate` |
| Diagnose why an automation didn't fire | `analyze-ha-traces` |

**Note on `.storage/`:** Contains ALL UI-managed HA config — dashboards, entity registry, device registry, all integration credentials, helpers, auth. Never write to `.storage/` files without explicit user confirmation.

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

Controller blueprints live in `/homeassistant/blueprints/automation/EPMatt/`:
- `philips_324131092621.yaml` — Philips Hue RWL021 dimmer
- `ikea_e2001_e2002_new.yaml` — IKEA STYRBAR (E2001/E2002)

Hook blueprints:
- `light_new.yaml` — "Hook - Light Edited" (local modified version, use this one)
- `light.yaml` — original EPMatt hook

### Known Issues (2026)

**HA 2026.3 (March 2026):** `color_temp`, `kelvin`, `min_mireds`, `max_mireds` light state attributes removed. Use `color_temp_kelvin`, `min_color_temp_kelvin`, `max_color_temp_kelvin` instead. Affects hook blueprint variable block and all `light.turn_on` service calls using `color_temp:`.

**zigpy 1.0.0 (Feb 2026):** Philips RWL021 OFF button now sends `off_with_effect` (ZCL cluster 0x0006) instead of `off_short_release`. IKEA STYRBAR sends duplicate `on`/`off` events ~35–60ms apart per press. Fix: add `- off_with_effect` to Philips controller blueprint; set `helper_debounce_delay = 100` for STYRBAR automations.

