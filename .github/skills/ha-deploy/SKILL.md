---
name: ha-deploy
description: Safely deploy latest HA config changes to the Home Assistant instance. Runs git pull → config validation → smart reload or restart. Use this whenever the user says "deploy", "uptake", "apply to HA", or after merging a PR that changes configuration.yaml, automations.yaml, scripts.yaml, blueprints, or custom_components.
---

# ha-deploy: Safe HA Deployment

Use this skill whenever changes need to be applied to the live HA instance. **Never run `ha core restart` directly** — always go through this skill.

## Running the skill

```bash
# Default: pull + validate + smart reload (or restart if needed)
python .github/skills/ha-deploy/deploy.py

# Validate only (no apply) — useful before merging a PR
python .github/skills/ha-deploy/deploy.py --check-only

# Force full restart even if smart reload would suffice
python .github/skills/ha-deploy/deploy.py --force-restart

# Skip pull, just check + full restart (e.g. after manual config edit on HA)
python .github/skills/ha-deploy/deploy.py --restart-only

# Override SSH target or repo path (or set HA_HOST / HA_REPO_DIR env vars)
python .github/skills/ha-deploy/deploy.py --host root@192.168.1.x --repo-dir /homeassistant
```

## Smart reload (zero downtime)

For most changes — automations, scripts, scenes, blueprints, groups, customize — the skill
calls the HA REST API to reload only what changed. No restart, no downtime.

| Changed files | Action | Downtime |
|---|---|---|
| `automations.yaml`, `automations/` | `automation.reload` | None |
| `scripts.yaml`, `scripts/` | `script.reload` | None |
| `scenes.yaml`, `scenes/` | `scene.reload` | None |
| `blueprints/` | `automation.reload` | None |
| `groups.yaml` | `homeassistant.reload_groups` | None |
| `customize.yaml` | `homeassistant.reload_custom_templates` | None |
| `configuration.yaml` or anything else | Full restart | ~60s |

Smart reload requires a one-time token setup (see below). Without it, falls back to full restart.

## One-time token setup (required for smart reload)

1. In HA UI: **Profile → Security → Long-Lived Access Tokens → Create Token**
2. Copy the token, then SSH to HA and run:
   ```bash
   echo "YOUR_TOKEN_HERE" > /homeassistant/.ha_token
   chmod 600 /homeassistant/.ha_token
   ```
3. The token file is gitignored and stays only on the HA instance.

## What it does (full flow)

1. **`git pull origin master`** — pulls latest master onto the HA instance
2. **Detects changed files** — `git diff HEAD@{1} HEAD --name-only`
3. **`ha core check`** — validates the full config; aborts if any error
4. **Smart reload** — calls targeted HA reload services (if token available and only reloadable files changed)
5. **Full restart** — only if `configuration.yaml` or other restart-required files changed
6. **Polls for online** — waits up to 120s for HA to report `state: running` (restart path only)
7. **Rollback instructions** — if HA doesn't recover, prints SSH commands to diagnose and revert

## Guardrails

- **Config check MUST pass** before any apply (reload or restart)
- Smart reload falls back to full restart if the token is missing or a reload call fails
- If HA doesn't come back within 120s, SSH is still available (SSH addon is a separate supervisor process)
- Rollback: `ssh root@homeassistant.local "cd /homeassistant && git fetch origin && git reset --hard origin/master && ha core check && ha core restart"`

## When NOT to use this skill

- Changes to `.storage/` files (Lovelace dashboards, entity registry) — require explicit user approval
- HACS component installs — done via HACS UI, not git
