#!/usr/bin/env python3
"""
HA Automation Trace Analyzer
=============================
Analyzes Home Assistant automation trace JSON files downloaded from the HA UI.

Usage:
    python .github/skills/analyze-ha-traces/analyze_trace.py <trace_file.json> [more_files ...]
    python .github/skills/analyze-ha-traces/analyze_trace.py .   # all trace *.json in current dir

Pass controller + hook traces together to see the full event chain.

Awesome HA Blueprints (https://epmatt.github.io/awesome-ha-blueprints/):
  Controller traces show: ZHA command -> mapped action -> ahb_controller_event fired
  Hook traces show:       ahb_controller_event action -> light/cover service call

Key things to look for:
  - trigger_delta < helper_double_press_delay  -> double-press detection fired
  - trigger_delta very small (< 100ms)         -> duplicate hardware events (debounce needed)
  - ❌ error in variables block                -> automation abort before any action runs
  - No service calls, no errors               -> action did not match any choose branch
  - color_temp / min_mireds / max_mireds       -> removed in HA 2026.3 (use color_temp_kelvin)
"""

import json
import sys
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _inner(data: dict) -> dict:
    return data.get("trace", {}).get("trace", {})


def _all_vars(inner: dict) -> dict:
    result = {}
    for key in sorted(inner):
        for node in inner[key]:
            result.update(node.get("changed_variables") or {})
    return result


def _errors(inner: dict, outer: dict = None) -> list:
    out = []
    # top-level error: automation crashed before any step ran (e.g. variable init failure)
    if outer and outer.get("error"):
        out.append(("(init)", outer["error"]))
    for path, nodes in inner.items():
        for node in nodes:
            if node.get("error"):
                out.append((path, node["error"]))
    return out


def _matched_branches(inner: dict) -> list:
    out = []
    for path, nodes in inner.items():
        if "/choose/" in path and "/conditions" not in path and "/sequence" not in path:
            for node in nodes:
                if (node.get("result") or {}).get("result") is True:
                    out.append(path)
    return out


def _service_calls(inner: dict) -> list:
    out = []
    for path, nodes in inner.items():
        for node in nodes:
            params = (node.get("result") or {}).get("params") or {}
            if params.get("domain") and params.get("service"):
                out.append((path, params))
    return out


def _event_fires(inner: dict) -> list:
    out = []
    for path, nodes in inner.items():
        for node in nodes:
            r = node.get("result") or {}
            if r.get("event"):
                out.append((path, r["event"], r.get("event_data") or {}))
    return out


def _zha_trigger_data(outer: dict) -> dict:
    nodes = (outer.get("trace") or {}).get("trigger/1", [{}])
    return (
        (nodes[0].get("changed_variables") or {})
        .get("trigger", {})
        .get("event", {})
        .get("data", {})
    )


def _timestamp(outer: dict) -> str:
    ts = outer.get("timestamp") or {}
    if isinstance(ts, dict):
        s = ts.get("start", "")
    else:
        s = str(ts)
    return s[:19].replace("T", " ")


def _blueprint(outer: dict) -> str:
    bp = (outer.get("blueprint_inputs") or {}).get("blueprint") or {}
    return bp.get("path", "")


def _alias(outer: dict) -> str:
    return (outer.get("config") or {}).get("alias", "")


def _auto_type(item_id: str, alias: str, bp: str) -> str:
    combined = (item_id + " " + alias + " " + bp).lower()
    if "hook" in combined:
        return "ahb_hook"
    if any(x in combined for x in ["ikea", "philips", "aqara", "styrbar", "hue", "tradfri", "sonoff", "xiaomi", "osram"]):
        return "ahb_controller"
    # blueprint path contains controller keyword
    if "controller" in combined and "hook" not in combined:
        return "ahb_controller"
    return "generic"


def _fmt(v) -> str:
    if isinstance(v, float):
        return str(round(v, 1))
    return str(v)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def analyze(filepath: str) -> dict:
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    outer = data.get("trace") or {}
    inner = _inner(data)
    bp = _blueprint(outer)
    item_id = outer.get("item_id", Path(filepath).stem)
    alias = _alias(outer)
    display_name = alias or item_id

    return {
        "filepath": filepath,
        "item_id": item_id,
        "alias": alias,
        "display_name": display_name,
        "blueprint": bp,
        "timestamp": _timestamp(outer),
        "state": outer.get("state", "?"),
        "script_execution": outer.get("script_execution", "?"),
        "trigger_str": outer.get("trigger", "?"),
        "auto_type": _auto_type(item_id, alias, bp),
        "vars": _all_vars(inner),
        "errors": _errors(inner, outer),
        "matched_branches": _matched_branches(inner),
        "service_calls": _service_calls(inner),
        "event_fires": _event_fires(inner),
        "zha_data": _zha_trigger_data(outer),
    }


# ---------------------------------------------------------------------------
# Printing
# ---------------------------------------------------------------------------

W = 68

def _section(title: str):
    print(f"\n  {title}")
    print(f"  {'─' * (W - 4)}")


def print_trace(r: dict):
    ok = not r["errors"] and r["script_execution"] in ("finished",)
    icon = "✓" if ok else "❌"
    print(f"\n{'═' * W}")
    print(f"  {icon}  {r['display_name']}")
    if r["alias"] and r["alias"] != r["item_id"]:
        print(f"     id: {r['item_id']}")
    print(f"     {r['timestamp']}  |  {r['state']} / {r['script_execution']}")
    if r["blueprint"]:
        print(f"     blueprint: {r['blueprint']}")
    print(f"{'═' * W}")

    v = r["vars"]

    # TRIGGER
    _section("TRIGGER")
    print(f"    {r['trigger_str']}")
    zha = r["zha_data"]
    if zha.get("command"):
        args_str = f"  args={zha['args']}" if zha.get("args") else ""
        print(f"    ZHA command   : {zha['command']}{args_str}  (cluster {zha.get('cluster_id', '?')})")
    if "trigger_action" in v:
        td = v.get("trigger_delta")
        delta = f"  ← delta {round(td, 1)}ms" if td is not None else ""
        print(f"    mapped action : {v['trigger_action']}{delta}")
        if td is not None and td < 150:
            print(f"    ⚠  delta < 150ms — likely hardware duplicate event (set helper_debounce_delay > {int(td)+10}ms)")
    if "action" in v and r["auto_type"] == "ahb_hook":
        print(f"    hook action   : {v['action']}")

    # ERRORS
    if r["errors"]:
        _section(f"ERRORS  ({len(r['errors'])})")
        for path, err in r["errors"]:
            print(f"    [{path}]")
            print(f"    {err}")
            # Common known issues
            if "NoneType" in err and "int" in err:
                print(f"    ↳ Template arithmetic on None — likely HA 2026.3 removed attribute")
                print(f"      (color_temp/min_mireds/max_mireds → use color_temp_kelvin)")

    # AHB CONTROLLER
    if r["auto_type"] == "ahb_controller":
        _section("CONTROLLER")
        ctrl_keys = [
            "trigger_action", "trigger_delta",
            "helper_debounce_delay", "helper_double_press_delay", "adjusted_double_press_delay",
            "button_up_double_press", "button_down_double_press",
            "button_left_double_press", "button_right_double_press",
        ]
        for k in ctrl_keys:
            if k in v:
                print(f"    {k:<38} {_fmt(v[k])}")

        if r["event_fires"]:
            _section("EVENT FIRED  →  hook will trigger on this")
            for _, name, data in r["event_fires"]:
                action = data.get("action", "")
                ctrl = data.get("controller", "")
                print(f"    {name}  action={action}  controller={ctrl}")

        branches = r["matched_branches"]
        if branches:
            print(f"\n    matched branch: {max(branches, key=lambda x: x.count('/'))}")
        elif not r["errors"]:
            print(f"\n    ⚠  no choose branch matched — action not in any mapping")

    # AHB HOOK
    elif r["auto_type"] == "ahb_hook":
        _section("HOOK VARIABLES")
        hook_keys = [
            "action", "turn_on", "turn_off",
            "brightness_up", "brightness_up_repeat", "brightness_down", "brightness_down_repeat",
            "color_up", "color_down", "color_up_temp", "color_down_temp",
            "toggle",
            "light_color_mode_id", "current_temp", "min_temp", "max_temp",
            "smooth_power_off", "force_brightness",
        ]
        for k in hook_keys:
            if k in v:
                print(f"    {k:<38} {_fmt(v[k])}")

        branches = r["matched_branches"]
        if branches:
            deepest = max(branches, key=lambda x: x.count("/"))
            print(f"\n    matched branch: {deepest}")
        elif not r["errors"]:
            print(f"\n    ⚠  no choose branch matched — action '{v.get('action', '?')}' not in mapping")

        if r["service_calls"]:
            _section("SERVICE CALLS")
            for path, params in r["service_calls"]:
                print(f"    {params.get('domain')}.{params.get('service')}")
                sd = params.get("service_data") or {}
                tgt = params.get("target") or {}
                if sd:
                    print(f"      data   : {sd}")
                if tgt:
                    print(f"      target : {tgt}")
        elif not r["errors"]:
            print(f"\n    ⚠  no service calls executed")

    # GENERIC
    else:
        if r["matched_branches"]:
            _section("MATCHED BRANCHES")
            for b in r["matched_branches"]:
                print(f"    {b}")
        if r["service_calls"]:
            _section("SERVICE CALLS")
            for _, params in r["service_calls"]:
                print(f"    {params.get('domain')}.{params.get('service')}")
                sd = params.get("service_data") or {}
                if sd:
                    print(f"      data: {sd}")
        if r["event_fires"]:
            _section("EVENTS FIRED")
            for _, name, data in r["event_fires"]:
                print(f"    {name}  {data}")

    # ONE-LINE RESULT
    print()
    if r["errors"]:
        short = r["errors"][0][1][:70]
        print(f"  RESULT  ❌  {short}")
    elif r["service_calls"]:
        p = r["service_calls"][0][1]
        print(f"  RESULT  ✓   {p.get('domain')}.{p.get('service')}")
    elif r["event_fires"]:
        _, en, ed = r["event_fires"][0]
        print(f"  RESULT  ✓   fired {en}  action={ed.get('action', '')}")
    elif r["script_execution"] == "finished":
        print(f"  RESULT  ✓   finished  (no service calls / events)")
    else:
        print(f"  RESULT  ?   {r['script_execution']}")


def print_summary(results: list):
    print(f"\n{'═' * W}")
    print(f"  SUMMARY  ({len(results)} traces)")
    print(f"{'═' * W}")
    print(f"  {'Time':<10} {'Automation':<38} Result")
    print(f"  {'─'*10} {'─'*38} {'─'*16}")
    for r in results:
        ts = r["timestamp"][11:19]
        name = r["display_name"][:38]
        if r["errors"]:
            status = "❌ " + r["errors"][0][1][:22]
        elif r["service_calls"]:
            p = r["service_calls"][0][1]
            status = f"✓ {p.get('domain')}.{p.get('service')}"
        elif r["event_fires"]:
            _, en, ed = r["event_fires"][0]
            status = f"✓ {en}({ed.get('action', '')[:12]})"
        else:
            status = f"✓ {r['script_execution']}"
        print(f"  {ts:<10} {name:<38} {status}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def collect_files(args: list) -> list:
    files = []
    for arg in args:
        p = Path(arg)
        if p.is_dir():
            files.extend(sorted(p.glob("trace *.json")))
            files.extend(sorted(p.glob("trace automation*.json")))
        elif p.exists():
            files.append(p)
        else:
            print(f"Warning: not found: {arg}", file=sys.stderr)
    # deduplicate preserving order
    seen, unique = set(), []
    for f in files:
        key = str(f.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    files = collect_files(args)
    if not files:
        print("No trace files found.", file=sys.stderr)
        sys.exit(1)

    print(f"Analyzing {len(files)} trace file(s)...")

    results = []
    for f in files:
        try:
            results.append(analyze(str(f)))
        except Exception as e:
            print(f"  Error reading {f.name}: {e}", file=sys.stderr)

    results.sort(key=lambda x: x["timestamp"])

    for r in results:
        print_trace(r)

    if len(results) > 1:
        print_summary(results)


if __name__ == "__main__":
    main()
