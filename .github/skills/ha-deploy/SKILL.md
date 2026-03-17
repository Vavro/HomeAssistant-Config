---
name: ha-deploy
description: Safely deploy latest HA config changes to the Home Assistant instance. Runs git pull → config validation → restart with online polling. Use this whenever the user says "deploy", "uptake", "apply to HA", or after merging a PR that changes configuration.yaml, automations.yaml, scripts.yaml, blueprints, or custom_components.
---

# ha-deploy: Safe HA Deployment

Use this skill whenever changes need to be applied to the live HA instance. **Never run `ha core restart` directly** — always go through this skill.

## Running the skill

```bash
# Full deploy: pull + validate + restart
python .github/skills/ha-deploy/deploy.py

# Validate only (no restart) — useful before merging a PR
python .github/skills/ha-deploy/deploy.py --check-only

# Restart only (skip pull) — if HA is already on latest but needs a restart
python .github/skills/ha-deploy/deploy.py --restart-only
```

## What it does

1. **`git pull`** — pulls latest master onto the HA instance (`/homeassistant`)
2. **`ha core check`** — validates the full config; aborts if any error
3. **`ha core restart`** — restarts HA core (~60s downtime)
4. **Polls for online** — waits up to 120s for HA to report `state: running`
5. **Rollback instructions** — if HA doesn't recover, prints SSH commands to diagnose and revert

## Guardrails

- **Config check MUST pass** before restart is attempted
- If HA doesn't come back within 120s, SSH is still available (SSH addon is a separate supervisor process — it survives HA core failures)
- Rollback: `git revert HEAD --no-edit && ha core check && ha core restart`

## When NOT to use this skill

- Changes to `.storage/` files (Lovelace dashboards, entity registry) — those take effect on next browser refresh or HA restart, but require explicit user approval before touching
- HACS component installs — those need to be done via the HACS UI, not via git
