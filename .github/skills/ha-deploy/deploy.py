#!/usr/bin/env python3
"""
ha-deploy: Pull latest master to HA, validate config, restart if valid.

Usage:
    python .github/skills/ha-deploy/deploy.py
    python .github/skills/ha-deploy/deploy.py --check-only   # validate without restart
    python .github/skills/ha-deploy/deploy.py --restart-only # skip pull, just check+restart

Environment overrides:
    HA_HOST     SSH target (default: root@homeassistant.local)
    HA_REPO_DIR Git repo path on HA instance (default: /homeassistant)
"""
import subprocess
import sys
import time
import argparse
import os

HA_HOST = os.environ.get("HA_HOST", "root@homeassistant.local")
HA_REPO_DIR = os.environ.get("HA_REPO_DIR", "/homeassistant")
RESTART_TIMEOUT = 120  # seconds to wait for HA to come back

SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]


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


def git_pull() -> bool:
    step("Pulling latest master onto HA instance...")
    # Verify we're on master before pulling
    branch = ssh(f"cd {HA_REPO_DIR} && git rev-parse --abbrev-ref HEAD")
    current = branch.stdout.strip()
    if current != "master":
        warn(f"HA repo is on branch '{current}', not master — switching to master first")
        result = ssh(f"cd {HA_REPO_DIR} && git checkout master")
        if result.returncode != 0:
            fail(f"Could not switch to master:\n{result.stderr}")
            return False

    result = ssh(f"cd {HA_REPO_DIR} && git pull origin master")
    if result.returncode != 0:
        fail(f"git pull failed:\n{result.stderr}")
        return False
    print(result.stdout.strip())
    ok("Pull complete")
    return True


def check_config() -> bool:
    step("Validating HA configuration (ha core check)...")
    result = ssh("ha core check")
    if result.returncode != 0:
        fail("Config check FAILED — will not restart.")
        print(result.stdout)
        print(result.stderr)
        print("\n    Fix the config error and run again.")
        return False
    ok("Config valid")
    return True


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
    global HA_HOST, HA_REPO_DIR

    parser = argparse.ArgumentParser(description="Deploy latest HA config safely")
    parser.add_argument("--check-only", action="store_true", help="Validate config without restarting")
    parser.add_argument("--restart-only", action="store_true", help="Skip git pull, just check+restart")
    parser.add_argument("--host", default=HA_HOST, help=f"SSH target (default: {HA_HOST})")
    parser.add_argument("--repo-dir", default=HA_REPO_DIR, help=f"Repo path on HA (default: {HA_REPO_DIR})")
    args = parser.parse_args()

    HA_HOST = args.host
    HA_REPO_DIR = args.repo_dir

    print("=" * 55)
    print("  ha-deploy: safe HA config deployment")
    print("=" * 55)

    if not args.restart_only:
        if not git_pull():
            sys.exit(1)

    if not check_config():
        sys.exit(1)

    if args.check_only:
        print("\n--check-only: skipping restart.")
        sys.exit(0)

    if not restart_ha():
        sys.exit(1)

    if not wait_for_ha():
        sys.exit(1)

    print("\n" + "=" * 55)
    print("  ✅ Deploy complete — HA is running.")
    print("=" * 55)


if __name__ == "__main__":
    main()
