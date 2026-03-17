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
import json

HA_HOST = "root@homeassistant.local"

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

# Safelist of file paths allowed to be read from HA instance
ALLOWED_FILE_PREFIXES = (
    "/homeassistant/",
    "/config/",
    "/tmp/",
)


def ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", HA_HOST, cmd],
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
        out = ssh(f"ha core logs 2>/dev/null | grep -i '{pattern}' | tail -{lines}")
    else:
        out = ssh(f"ha core logs 2>/dev/null | tail -{lines}")
    print(out)


def cmd_entities(args):
    """List entities, optionally filtered by config entry ID or domain."""
    config_entry = getattr(args, "config_entry", None)
    domain = getattr(args, "domain", None)

    if config_entry:
        jq_filter = f'.data.entities[] | select(.config_entry_id=="{config_entry}") | .entity_id'
    elif domain:
        jq_filter = f'.data.entities[] | select(.entity_id | startswith("{domain}.")) | .entity_id'
    else:
        jq_filter = ".data.entities[] | .entity_id"

    out = ssh(f"jq -r '{jq_filter}' /homeassistant/.storage/core.entity_registry 2>/dev/null | sort")
    print(out)


def cmd_config_entries(args):
    """List config entries, optionally filtered by domain."""
    domain = getattr(args, "domain", None)
    if domain:
        jq_filter = f'.data.entries[] | select(.domain=="{domain}") | {{domain, title, state, source}}'
    else:
        jq_filter = '.data.entries[] | {domain, title, state}'
    out = ssh(f"jq '{jq_filter}' /homeassistant/.storage/core.config_entries 2>/dev/null")
    print(out)


def cmd_lovelace(args):
    """Dump Lovelace dashboard config."""
    dashboard = getattr(args, "dashboard", None) or "lovelace_domov"
    key = f"lovelace.{dashboard}" if not dashboard.startswith("lovelace") else dashboard
    if key not in ALLOWED_STORAGE:
        print(f"Error: '{key}' not in allowed storage safelist: {sorted(ALLOWED_STORAGE)}", file=sys.stderr)
        sys.exit(1)
    out = ssh(f"jq '.data.config.views | to_entries | .[] | {{index: .key, path: .value.path, title: .value.title, icon: .value.icon, cards: (.value.cards | length)}}' /homeassistant/.storage/{key} 2>/dev/null")
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
    path = args.path
    if not any(path.startswith(p) for p in ALLOWED_FILE_PREFIXES):
        print(f"Error: path '{path}' not under allowed prefixes: {ALLOWED_FILE_PREFIXES}", file=sys.stderr)
        sys.exit(1)
    out = ssh(f"cat '{path}' 2>/dev/null")
    print(out)


def main():
    parser = argparse.ArgumentParser(description="Read-only HA instance inspection")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="HA core status and addon overview")

    p_logs = sub.add_parser("logs", help="HA core logs")
    p_logs.add_argument("--filter", metavar="PATTERN", help="grep filter pattern")
    p_logs.add_argument("--lines", type=int, default=50, help="Number of lines (default: 50)")

    p_ent = sub.add_parser("entities", help="List entities")
    p_ent.add_argument("--config-entry", metavar="ID", help="Filter by config entry ID")
    p_ent.add_argument("--domain", help="Filter by domain (e.g. sensor, binary_sensor)")

    p_ce = sub.add_parser("config-entries", help="List config entries")
    p_ce.add_argument("--domain", help="Filter by integration domain")

    p_lv = sub.add_parser("lovelace", help="Show Lovelace dashboard view summary")
    p_lv.add_argument("--dashboard", default="lovelace_domov", help="Dashboard storage key suffix")

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
