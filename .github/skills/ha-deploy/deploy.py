#!/usr/bin/env python3
"""
ha-deploy: Pull latest master to HA, validate config, then reload or restart
only what changed — minimising downtime.

Usage:
    python .github/skills/ha-deploy/deploy.py
    python .github/skills/ha-deploy/deploy.py --check-only    # validate, no apply
    python .github/skills/ha-deploy/deploy.py --restart-only  # skip pull, full restart
    python .github/skills/ha-deploy/deploy.py --force-restart # ignore smart reload, always restart

Environment overrides:
    HA_HOST      SSH target          (default: root@homeassistant.local)
    HA_REPO_DIR  Git repo on HA      (default: /homeassistant)
    HA_API_URL   HA REST API URL     (default: http://localhost:8123)

Smart reload requires a long-lived access token stored on the HA instance at
{HA_REPO_DIR}/.ha_token (chmod 600). Without it, falls back to full restart.
See SKILL.md for one-time setup instructions.
"""
import subprocess
import sys
import time
import argparse
import os

HA_HOST = os.environ.get("HA_HOST", "root@homeassistant.local")
HA_REPO_DIR = os.environ.get("HA_REPO_DIR", "/homeassistant")
HA_API_URL = os.environ.get("HA_API_URL", "http://localhost:8123")
RESTART_TIMEOUT = 120  # seconds to wait for HA to come back

SSH_OPTS = ["-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]

# Files/prefixes that only need a targeted reload (no HA restart).
# Each entry: (path_prefix, service_domain, service_name, human_label)
_RELOAD_MAP = [
    ("automations.yaml", "automation", "reload", "automations"),
    ("automations/", "automation", "reload", "automations"),
    ("scripts.yaml", "script", "reload", "scripts"),
    ("scripts/", "script", "reload", "scripts"),
    ("scenes.yaml", "scene", "reload", "scenes"),
    ("scenes/", "scene", "reload", "scenes"),
    ("blueprints/", "automation", "reload", "automations (blueprints changed)"),
    ("groups.yaml", "homeassistant", "reload_groups", "groups"),
    ("customize.yaml", "homeassistant", "reload_core_config", "entity customizations"),
]


def ssh(cmd: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", *SSH_OPTS, HA_HOST, cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def step(msg: str):
    print(f"\n>>> {msg}")


def ok(msg: str):
    print(f"    ✅ {msg}")


def fail(msg: str):
    print(f"    ❌ {msg}")


def warn(msg: str):
    print(f"    ⚠️  {msg}")


def git_pull() -> tuple[bool, list[str]]:
    """Pull latest master. Returns (success, list_of_changed_files)."""
    step("Pulling latest master onto HA instance...")
    branch = ssh(f"cd {HA_REPO_DIR} && git rev-parse --abbrev-ref HEAD")
    if branch.stdout.strip() != "master":
        warn(f"HA repo is on branch '{branch.stdout.strip()}', switching to master first")
        r = ssh(f"cd {HA_REPO_DIR} && git checkout master")
        if r.returncode != 0:
            fail(f"Could not switch to master:\n{r.stderr}")
            return False, []

    # Capture SHA before pulling so we can diff reliably (HEAD@{1} requires reflog)
    before = ssh(f"cd {HA_REPO_DIR} && git rev-parse HEAD")
    before_sha = before.stdout.strip() if before.returncode == 0 else None

    result = ssh(f"cd {HA_REPO_DIR} && git pull origin master")
    if result.returncode != 0:
        fail(f"git pull failed:\n{result.stderr}")
        return False, []

    pull_output = result.stdout.strip()
    print(f"    {pull_output}")

    if "Already up to date" in pull_output:
        ok("Already up to date — nothing to apply")
        return True, []

    # Determine exactly which files changed during this pull
    if before_sha:
        diff = ssh(f"cd {HA_REPO_DIR} && git diff {before_sha} HEAD --name-only")
        if diff.returncode == 0:
            changed = [f.strip() for f in diff.stdout.strip().splitlines() if f.strip()]
        else:
            warn("Could not diff changes — assuming full restart is needed")
            changed = ["__unknown__"]
    else:
        warn("Could not capture pre-pull SHA — assuming full restart is needed")
        changed = ["__unknown__"]

    ok(f"Pull complete — {len(changed)} file(s) changed")
    return True, changed


def classify_changes(files: list[str]) -> tuple[set[tuple[str, str, str]], bool]:
    """
    Classify changed files into reload actions vs. full-restart required.

    Returns:
        reload_actions: set of (domain, service, label) — deduplicated
        needs_restart:  True if any changed file requires a full HA restart
    """
    reload_actions: set[tuple[str, str, str]] = set()
    needs_restart = False

    for f in files:
        matched = False
        for prefix, domain, service, label in _RELOAD_MAP:
            if prefix.endswith("/"):
                matched = f.startswith(prefix)
            else:
                matched = (f == prefix)
            if matched:
                reload_actions.add((domain, service, label))
                break
        if not matched:
            needs_restart = True

    return reload_actions, needs_restart


def check_config() -> bool:
    step("Validating HA configuration (ha core check)...")
    result = ssh("ha core check")
    if result.returncode != 0:
        fail("Config check FAILED — will not apply.")
        print(result.stdout)
        print(result.stderr)
        print("\n    Fix the config error and run again.")
        return False
    ok("Config valid")
    return True


def call_ha_service(domain: str, service: str) -> bool:
    """Call a HA service via the REST API over SSH using the stored token."""
    cmd = (
        f'HA_TOKEN=$(cat {HA_REPO_DIR}/.ha_token 2>/dev/null) && '
        f'[ -n "$HA_TOKEN" ] && '
        f'curl -s -o /dev/null -w "%{{http_code}}" '
        f'--connect-timeout 10 --max-time 30 '
        f'-X POST "{HA_API_URL}/api/services/{domain}/{service}" '
        f'-H "Authorization: Bearer $HA_TOKEN" '
        f'-H "Content-Type: application/json" '
        f"-d '{{}}'"
    )
    result = ssh(cmd)
    return result.returncode == 0 and result.stdout.strip() == "200"


def smart_reload(reload_actions: set[tuple[str, str, str]]) -> bool:
    """Call selective reload services. Returns False if token is missing."""
    # Verify token exists before attempting reloads
    token_check = ssh(f"test -s {HA_REPO_DIR}/.ha_token && echo ok")
    if token_check.stdout.strip() != "ok":
        warn(f"No token at {HA_REPO_DIR}/.ha_token — falling back to full restart")
        warn("See SKILL.md for one-time token setup instructions")
        return False

    step("Applying changes via selective reload (no HA restart)...")
    all_ok = True
    seen_services: set[tuple[str, str]] = set()
    for domain, service, label in sorted(reload_actions):
        if (domain, service) in seen_services:
            continue  # already reloaded this service (e.g. automations + blueprints both → automation.reload)
        seen_services.add((domain, service))
        if call_ha_service(domain, service):
            ok(f"Reloaded {label} ({domain}.{service})")
        else:
            warn(f"Reload failed for {label} ({domain}.{service}) — will fall back to full restart")
            all_ok = False

    return all_ok


def restart_ha() -> bool:
    step("Restarting HA core...")
    result = ssh("ha core restart")
    if result.returncode != 0:
        fail(f"Restart command failed:\n{result.stderr}")
        return False
    ok("Restart command accepted — waiting for HA to come back online...")
    return True


def wait_for_ha() -> bool:
    step(f"Polling HA for up to {RESTART_TIMEOUT}s...")
    deadline = time.time() + RESTART_TIMEOUT
    dots = 0
    while time.time() < deadline:
        result = ssh("ha core info 2>/dev/null | grep -c 'state: running'")
        if result.returncode == 0 and result.stdout.strip() == "1":
            ok("HA is back online")
            return True
        time.sleep(5)
        dots += 1
        print(f"    ...waiting ({dots * 5}s)", end="\r")

    fail(f"HA did not come back within {RESTART_TIMEOUT}s.")
    print(f"""
    SSH is still available (SSH addon is separate from HA core).
    To diagnose:
        ssh {HA_HOST} "ha core logs 2>/dev/null | tail -30"

    To rollback to last known-good origin/master and retry:
        ssh {HA_HOST} "cd {HA_REPO_DIR} && git fetch origin && git reset --hard origin/master && ha core check && ha core restart"
    """)
    return False


def main():
    global HA_HOST, HA_REPO_DIR, HA_API_URL

    parser = argparse.ArgumentParser(description="Deploy latest HA config safely")
    parser.add_argument("--check-only", action="store_true", help="Validate config without applying")
    parser.add_argument("--restart-only", action="store_true", help="Skip git pull, just check + full restart")
    parser.add_argument("--force-restart", action="store_true", help="Always do full restart, skip smart reload")
    parser.add_argument("--host", default=HA_HOST, help=f"SSH target (default: {HA_HOST})")
    parser.add_argument("--repo-dir", default=HA_REPO_DIR, help=f"Repo path on HA (default: {HA_REPO_DIR})")
    parser.add_argument("--api-url", default=HA_API_URL, help=f"HA REST API URL (default: {HA_API_URL})")
    args = parser.parse_args()

    HA_HOST = args.host
    HA_REPO_DIR = args.repo_dir
    HA_API_URL = args.api_url

    print("=" * 55)
    print("  ha-deploy: safe HA config deployment")
    print("=" * 55)

    changed_files: list[str] = []

    if not args.restart_only:
        success, changed_files = git_pull()
        if not success:
            sys.exit(1)
        if not changed_files and not args.force_restart:
            print("\n  Nothing changed — no reload or restart needed.")
            sys.exit(0)

    if not check_config():
        sys.exit(1)

    if args.check_only:
        print("\n--check-only: skipping apply.")
        sys.exit(0)

    # Determine whether smart reload is possible
    use_smart_reload = not args.force_restart and not args.restart_only and bool(changed_files)

    if use_smart_reload:
        reload_actions, needs_restart = classify_changes(changed_files)

        if needs_restart:
            unmatched = [
                f for f in changed_files
                if not any(f == p or f.startswith(p) for p, *_ in _RELOAD_MAP)
            ]
            warn(f"Full restart needed — these files require it: {', '.join(unmatched)}")
        elif reload_actions:
            if smart_reload(reload_actions):
                print("\n" + "=" * 55)
                print("  ✅ Deploy complete — reloaded without restart.")
                print("=" * 55)
                sys.exit(0)
            else:
                warn("Smart reload failed — falling back to full restart")

    # Full restart path
    if not restart_ha():
        sys.exit(1)
    if not wait_for_ha():
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  ✅ Deploy complete — HA is running.")
    print("=" * 55)


if __name__ == "__main__":
    main()

