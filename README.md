# Home Assistant Configuration

Personal [Home Assistant](https://www.home-assistant.io/) setup running on **HA OS**, managing lights, shutters, garden, and more across a family home — fully automated with Zigbee remotes and smart scenes.

---

## Hardware

| Category | Devices |
|----------|---------|
| **Zigbee coordinator** | ZHA via USB stick |
| **Light remotes** | Philips Hue RWL021 dimmers, IKEA STYRBAR (E2001/E2002) |
| **Gesture control** | Aqara Magic Cube |
| **Lights** | Philips Hue bulbs, IKEA TRÅDFRI, Ledvance/OSRAM |
| **Shutters** | Zigbee shutter controllers |
| **Audio** | Samsung Soundbar (living room) |
| **Monitoring** | Glances (system stats) |

---

## Integrations

| Integration | Purpose |
|-------------|---------|
| **ZHA** | All Zigbee devices (lights, remotes, shutters) with automatic OTA firmware updates via IKEA/Ledvance/Sonoff providers |
| **InfluxDB** | Long-term state history for dashboards and analysis |
| **Glances** | HA host system monitoring (CPU, RAM, disk) |
| **Samsung Soundbar** | Media player control in the living room |
| **Google TTS** | Text-to-speech announcements |
| **Car integration** | Presence/availability tracking |
| **HACS** | Community components (`zha_toolkit`) |

---

## Automations

### 💡 Light Control
All Zigbee remotes use the [Awesome HA Blueprints](https://epmatt.github.io/awesome-ha-blueprints/) controller + hook architecture. Each remote has a **controller** automation (maps hardware ZHA events to abstract actions) and a **hook** automation (translates abstract actions to light service calls with brightness/colour stepping).

Rooms covered: entry hall, staircase, bedroom, wardrobe, living room (main + dining + secondary), kitchen, kids room (x2), office.

**Entry hall**: motion sensor triggers lights on/off automatically.

### 🪟 Shutter Control
IKEA STYRBAR remotes control motorised shutters in the living room, kids room, and office.

### 🌿 Garden
- Lights turn on at dusk, off close to midnight
- Water pump runs on a daily irrigation schedule

### 🚿 Utilities
- Hot water circulation triggered on demand, auto-off after 90 seconds
- Toilet towel heater auto-off after 1 hour

### 🎵 Morning Routine
Living room radio starts automatically when morning lights turn on.

### 🔊 Aqara Magic Cube
Custom gestures in the living room mapped to media/light scenes.

### 🧹 Vacuum
Robot vacuum triggered automatically when the house is empty in the morning.

### 🎄 Seasonal
Christmas indoor and outdoor lights on/off schedules (disabled when not in use).

---

## Blueprint Setup (Awesome HA Blueprints)

The remote control automations use a two-automation pattern:

```
Physical button press
  → ZHA event (e.g. command: "on", cluster 6)
  → Controller blueprint   maps ZHA command → abstract action (button_on_short)
  → fires ahb_controller_event
  → Hook blueprint         maps action → light.turn_on / light.turn_off / brightness step
```

Blueprint files live in [`blueprints/automation/EPMatt/`](blueprints/automation/EPMatt/):

| File | Purpose |
|------|---------|
| `philips_324131092621.yaml` | Philips Hue RWL021 dimmer controller |
| `ikea_e2001_e2002_new.yaml` | IKEA STYRBAR controller |
| `light_new.yaml` | Hook – Light (local modified version, use this) |
| `light.yaml` | Original EPMatt hook (reference copy) |

After editing any blueprint: **Developer Tools → YAML → Reload Automations**.

---

## Repository Structure

```
/
├── configuration.yaml       # Main HA config (ZHA, InfluxDB, Samsung Soundbar, etc.)
├── automations.yaml         # All automations (UI-managed + manual)
├── scripts.yaml             # Reusable scripts
├── scenes.yaml              # Scenes
├── groups.yaml              # Entity groups
├── customize.yaml           # Entity customizations
├── blueprints/              # Automation blueprints
│   └── automation/EPMatt/   # Awesome HA Blueprints (controller + hook)
├── glances/                 # Glances monitoring config
├── www/                     # Lovelace frontend resources
└── .github/
    ├── copilot-instructions.md          # Copilot workspace context
    └── skills/analyze-ha-traces/       # Trace analysis skill + tests
```

Secrets are stored in `secrets.yaml` (gitignored) and referenced with `!secret` throughout.

---

## Development Workflow

- **Local machine**: create a branch, open a PR — Copilot review runs automatically
- **HA instance**: pushes directly to `master` (SSH deploy key in bypass list)
- Branch protection enforces PRs for all other contributors

### Diagnosing broken automations

Download trace JSON files from **Settings → Automations → [automation] → Traces** and analyze with the built-in skill:

```bash
# All traces in the current directory
python .github/skills/analyze-ha-traces/analyze_trace.py .

# Specific controller + hook pair
python .github/skills/analyze-ha-traces/analyze_trace.py controller.json hook.json
```

See [`.github/skills/analyze-ha-traces/SKILL.md`](.github/skills/analyze-ha-traces/SKILL.md) for interpretation guide and known issues.

### Running skill tests

```bash
python .github/skills/analyze-ha-traces/tests/test_analyze_trace.py
```

---

## Known Issues & Fixes Applied

| Version | Breaking change | Fix |
|---------|----------------|-----|
| HA 2026.3 | `color_temp` / `min_mireds` / `max_mireds` light attributes removed | `light_new.yaml` migrated to `color_temp_kelvin` / `min_color_temp_kelvin` / `max_color_temp_kelvin` |
| zigpy 1.0.0 (Feb 2026) | Philips RWL021 OFF button renamed from `off_short_release` → `off_with_effect` | Added `- off_with_effect` to `button_off_short` mapping in Philips blueprint |
| zigpy 1.0.0 (Feb 2026) | IKEA STYRBAR sends duplicate ZHA events ~35–60ms apart per press | `helper_debounce_delay = 75ms` set on all STYRBAR controller automations |
