---
name: ha-investigate
description: Read-only inspection of the live Home Assistant instance over SSH. Use this for checking HA status, logs, entities, config entries, Lovelace dashboards, and storage files. All operations are strictly read-only — no state is modified. Use this instead of raw SSH commands for any HA inspection task.
---

# ha-investigate: Safe HA Inspection

Use this skill for any read-only inspection of the live HA instance. It wraps SSH commands in a safelisted script so a single invocation covers multiple reads without per-command approval prompts.

**Never run raw SSH reads directly** — use this skill instead.

## Commands

```bash
# HA core status + running addons
python .github/skills/ha-investigate/investigate.py status

# Logs (last 50 lines, or filtered)
python .github/skills/ha-investigate/investigate.py logs
python .github/skills/ha-investigate/investigate.py logs --filter influx --lines 20
python .github/skills/ha-investigate/investigate.py logs --filter "ERROR|WARNING"

# Entities (all, by config entry, or by domain)
python .github/skills/ha-investigate/investigate.py entities
python .github/skills/ha-investigate/investigate.py entities --config-entry 01KKYRH6NVQGV2WVY4AYPWFNNC
python .github/skills/ha-investigate/investigate.py entities --domain sensor

# Config entries (all integrations, or by domain)
python .github/skills/ha-investigate/investigate.py config-entries
python .github/skills/ha-investigate/investigate.py config-entries --domain influxdb

# Lovelace dashboard view summary
python .github/skills/ha-investigate/investigate.py lovelace
python .github/skills/ha-investigate/investigate.py lovelace --dashboard lovelace

# Read a .storage file (safelisted keys only)
python .github/skills/ha-investigate/investigate.py storage core.entity_registry
python .github/skills/ha-investigate/investigate.py storage lovelace.lovelace_domov

# Read a config file from HA
python .github/skills/ha-investigate/investigate.py file /homeassistant/configuration.yaml
```

## Safety

- **Read-only**: no writes, no restarts, no state changes
- **Safelisted paths**: `storage` command only accepts known `.storage/` keys; `file` command only allows paths under `/homeassistant/`, `/config/`, `/tmp/`
- SSH is always available even if HA core is not running (SSH addon is a separate supervisor process)

## When to use vs ha-deploy

| Task | Skill |
|------|-------|
| Check logs, entities, status | `ha-investigate` |
| Validate config | `ha-deploy --check-only` |
| Pull + restart | `ha-deploy` |
