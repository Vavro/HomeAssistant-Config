#!/usr/bin/env python3
"""
ha-investigate: Safe read-only inspection of the live HA instance over SSH.

All commands are strictly read-only. No state is modified.

Usage:
    python .github/skills/ha-investigate/investigate.py status
    python .github/skills/ha-investigate/investigate.py logs [--filter PATTERN] [--lines N]
    python .github/skills/ha-investigate/investigate.py entities [--config-entry ID] [--domain DOMAIN]
    python .github/skills/ha-investigate/investigate.py config-entries [--domain DOMAIN]
    python .github/skills/ha-investigate/investigate.py lovelace [--dashboard NAME]
    python .github/skills/ha-investigate/investigate.py storage STORAGE_KEY
    python .github/skills/ha-investigate/investigate.py file PATH
"""
import subprocess
import sys
import argparse
import os
import re
import shlex

HA_HOST = os.environ.get("HA_HOST", "root@homeassistant.local")
SSH_OPTS = ["-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3"]

# Safelist of .storage keys allowed to be read
ALLOWED_STORAGE = {
    "lovelace.lovelace_domov",
    "lovelace.lovelace",
    "lovelace.map",
    "lovelace.dashboard_location",
    "lovelace_dashboards",
    "lovelace_resources",
    "core.entity_registry",
    "core.device_registry",
    "core.area_registry",
    "core.config_entries",
}

# Safelist of file path prefixes allowed to be read from HA instance
ALLOWED_FILE_PREFIXES = (
    "/homeassistant/",
    "/config/",
    "/tmp/",
)

# Validation patterns
_RE_CONFIG_ENTRY_ID = re.compile(r'^[A-Z0-9]{26}$')
_RE_DOMAIN = re.compile(r'^[a-z][a-z0-9_]*$')


def _validate_config_entry_id(value: str) -> str:
    if not _RE_CONFIG_ENTRY_ID.match(value):
        print(f"Error: invalid config entry ID '{value}' (expected 26 uppercase alphanumeric chars)", file=sys.stderr)
        sys.exit(1)
    return value


def _validate_domain(value: str) -> str:
    if not _RE_DOMAIN.match(value):
        print(f"Error: invalid domain '{value}' (expected lowercase letters, digits, underscores)", file=sys.stderr)
        sys.exit(1)
    return value


def _validate_file_path(path: str) -> str:
    """Normalize path, reject traversal, verify against safelist prefixes."""
    normalized = os.path.normpath(path)
    # Reject any path with remaining .. components after normalization
    if ".." in normalized.split(os.sep):
        print(f"Error: path traversal detected in '{path}'", file=sys.stderr)
        sys.exit(1)
    # normpath on Linux uses / separator; force it
    normalized = normalized.replace("\\", "/")
    if not any(normalized.startswith(p) for p in ALLOWED_FILE_PREFIXES):
        print(f"Error: path '{normalized}' not under allowed prefixes: {ALLOWED_FILE_PREFIXES}", file=sys.stderr)
        sys.exit(1)
    return normalized


def ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", *SSH_OPTS, HA_HOST, cmd],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0 and result.stderr:
        print(f"[ssh stderr] {result.stderr.strip()}", file=sys.stderr)
    return result.stdout


def cmd_status(args):
    """HA core status, version, and addon overview."""
    print("=== HA Core Info ===")
    print(ssh("ha core info 2>/dev/null"))
    print("=== Running Addons ===")
    print(ssh("ha addons list 2>/dev/null | grep -E 'name:|state:' | paste - -"))


def cmd_logs(args):
    """HA core logs, optionally filtered."""
    lines = getattr(args, "lines", 50)
    pattern = getattr(args, "filter", None)
    if pattern:
        # Use shlex.quote to safely pass the pattern to the remote shell
        quoted_pattern = shlex.quote(pattern)
        out = ssh(f"ha core logs 2>/dev/null | grep -i {quoted_pattern} | tail -{lines}")
    else:
        out = ssh(f"ha core logs 2>/dev/null | tail -{lines}")
    print(out)


def cmd_entities(args):
    """List entities, optionally filtered by config entry ID or domain."""
    config_entry = getattr(args, "config_entry", None)
    domain = getattr(args, "domain", None)

    if config_entry:
        _validate_config_entry_id(config_entry)
        # Use jq --arg to avoid interpolating user input into the jq program
        out = ssh(f"jq -r --arg id {shlex.quote(config_entry)} "
                  f"'.data.entities[] | select(.config_entry_id==$id) | .entity_id' "
                  f"/homeassistant/.storage/core.entity_registry 2>/dev/null | sort")
    elif domain:
        _validate_domain(domain)
        out = ssh(f"jq -r --arg prefix {shlex.quote(domain + '.')} "
                  f"'.data.entities[] | select(.entity_id | startswith($prefix)) | .entity_id' "
                  f"/homeassistant/.storage/core.entity_registry 2>/dev/null | sort")
    else:
        out = ssh("jq -r '.data.entities[] | .entity_id' /homeassistant/.storage/core.entity_registry 2>/dev/null | sort")
    print(out)


def cmd_config_entries(args):
    """List config entries, optionally filtered by domain."""
    domain = getattr(args, "domain", None)
    if domain:
        _validate_domain(domain)
        out = ssh(f"jq --arg domain {shlex.quote(domain)} "
                  f"'.data.entries[] | select(.domain==$domain) | {{domain, title, state, source}}' "
                  f"/homeassistant/.storage/core.config_entries 2>/dev/null")
    else:
        out = ssh("jq '.data.entries[] | {domain, title, state}' /homeassistant/.storage/core.config_entries 2>/dev/null")
    print(out)


def cmd_lovelace(args):
    """Show Lovelace dashboard view summary."""
    dashboard = getattr(args, "dashboard", None) or "lovelace_domov"
    key = f"lovelace.{dashboard}" if not dashboard.startswith("lovelace.") else dashboard
    if key not in ALLOWED_STORAGE:
        print(f"Error: '{key}' not in allowed storage safelist: {sorted(ALLOWED_STORAGE)}", file=sys.stderr)
        sys.exit(1)
    out = ssh(f"jq '.data.config.views | to_entries | .[] | "
              f"{{index: .key, path: .value.path, title: .value.title, icon: .value.icon, cards: (.value.cards | length)}}' "
              f"/homeassistant/.storage/{key} 2>/dev/null")
    print(out)


def cmd_storage(args):
    """Read a .storage file (safelisted keys only)."""
    key = args.key
    if key not in ALLOWED_STORAGE:
        print(f"Error: '{key}' not in allowed storage safelist.", file=sys.stderr)
        print(f"Allowed: {sorted(ALLOWED_STORAGE)}", file=sys.stderr)
        sys.exit(1)
    out = ssh(f"cat /homeassistant/.storage/{key} 2>/dev/null")
    print(out)


def cmd_file(args):
    """Read a file from the HA instance (safelisted path prefixes only)."""
    path = _validate_file_path(args.path)
    out = ssh(f"cat {shlex.quote(path)} 2>/dev/null")
    print(out)


def main():
    parser = argparse.ArgumentParser(description="Read-only HA instance inspection")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="HA core status and addon overview")

    p_logs = sub.add_parser("logs", help="HA core logs")
    p_logs.add_argument("--filter", metavar="PATTERN", help="grep filter pattern")
    p_logs.add_argument("--lines", type=int, default=50, help="Number of lines (default: 50)")

    p_ent = sub.add_parser("entities", help="List entities")
    p_ent.add_argument("--config-entry", metavar="ID", help="Filter by config entry ID (26-char alphanumeric)")
    p_ent.add_argument("--domain", help="Filter by domain (e.g. sensor, binary_sensor)")

    p_ce = sub.add_parser("config-entries", help="List config entries")
    p_ce.add_argument("--domain", help="Filter by integration domain")

    p_lv = sub.add_parser("lovelace", help="Show Lovelace dashboard view summary")
    p_lv.add_argument("--dashboard", default="lovelace_domov", help="Dashboard name (default: lovelace_domov)")

    p_st = sub.add_parser("storage", help="Read a .storage file (safelisted)")
    p_st.add_argument("key", help=f"Storage key. Allowed: {sorted(ALLOWED_STORAGE)}")

    p_fi = sub.add_parser("file", help="Read a file from HA instance (safelisted paths)")
    p_fi.add_argument("path", help="Absolute path on HA instance")

    args = parser.parse_args()
    {
        "status": cmd_status,
        "logs": cmd_logs,
        "entities": cmd_entities,
        "config-entries": cmd_config_entries,
        "lovelace": cmd_lovelace,
        "storage": cmd_storage,
        "file": cmd_file,
    }[args.command](args)


if __name__ == "__main__":
    main()
