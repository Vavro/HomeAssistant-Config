#!/usr/bin/env python3
"""
Tests for analyze_trace.py

Run from repo root:
    python .github/skills/analyze-ha-traces/tests/test_analyze_trace.py

Each test runs the analyzer against a fixture file and asserts expected
strings appear (or don't appear) in the output. Fixtures are minimal
anonymized reproductions of real traces encountered in the field.

Adding a new test:
  1. Save a real trace to tests/fixtures/<descriptive_name>.json
     - Remove or anonymize device_ieee, entity_ids if desired
     - Keep the minimum trace nodes needed to reproduce the scenario
  2. Add a test function below following the existing pattern
  3. Run the suite to confirm it passes
"""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "analyze_trace.py"
FIXTURES = Path(__file__).parent / "fixtures"

PASS = 0
FAIL = 0


def run(fixture_name: str) -> str:
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(FIXTURES / fixture_name)],
        capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return (result.stdout or "") + (result.stderr or "")


def check(name: str, output: str, must_contain: list, must_not_contain: list = None):
    global PASS, FAIL
    errors = []
    for s in must_contain:
        if s not in output:
            errors.append(f"  MISSING: {repr(s)}")
    for s in (must_not_contain or []):
        if s in output:
            errors.append(f"  UNEXPECTED: {repr(s)}")
    if errors:
        print(f"❌ {name}")
        for e in errors:
            print(e)
        print("  --- output ---")
        for line in output.splitlines():
            print("  " + line)
        FAIL += 1
    else:
        print(f"✓  {name}")
        PASS += 1


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_hook_init_crash_color_temp():
    """
    Fixture: Hook blueprint crashes at init because HA 2026.3 removed
    color_temp/min_mireds/max_mireds light attributes.
    The automation aborts before any action runs.
    Expected: error shown with helpful hint about color_temp_kelvin.
    """
    out = run("hook_init_crash_color_temp.json")
    check(
        "hook_init_crash_color_temp",
        out,
        must_contain=[
            "❌",
            "TypeError",
            "NoneType",
            "color_temp_kelvin",           # hint shown
            "Living room main light remote control hook",
        ],
        must_not_contain=[
            "light.turn_on",               # no service call should be made
            "light.turn_off",
        ]
    )


def test_controller_duplicate_zha_event():
    """
    Fixture: IKEA STYRBAR sends two identical 'off' ZHA events ~35ms apart
    (zigpy 1.0.0 regression). trigger_delta=34.7ms triggers the duplicate
    event warning. Double-press detector fires button_down_double incorrectly.
    Expected: delta warning, event fired is button_down_double.
    """
    out = run("controller_duplicate_zha_event.json")
    check(
        "controller_duplicate_zha_event",
        out,
        must_contain=[
            "⚠",
            "delta < 150ms",
            "button_down_double",           # wrong action fired due to duplicate
            "Kids Room table light controller",
            "34.7",                         # actual delta shown
        ]
    )


def test_hook_success_turn_off():
    """
    Fixture: Hook receives button_off_short action, matches turn_off mapping,
    calls light.turn_off successfully.
    Expected: success indicator, service call shown, correct automation name.
    """
    out = run("hook_success_turn_off.json")
    check(
        "hook_success_turn_off",
        out,
        must_contain=[
            "✓",
            "light.turn_off",
            "Living room main light remote control hook",
            "button_off_short",
        ],
        must_not_contain=[
            "❌",
            "TypeError",
        ]
    )


def test_controller_no_branch_matched():
    """
    Fixture: Philips RWL021 sends 'off_with_effect' ZHA command (zigpy 1.0.0
    rename) but controller blueprint only maps 'off_short_release'. No choose
    branch matches, only the helper input_text.set_value runs.
    Expected: warning about no branch matched.
    """
    out = run("controller_no_branch_matched.json")
    check(
        "controller_no_branch_matched",
        out,
        must_contain=[
            "no choose branch matched",
            "Living room main light remote control",
            "off_with_effect",
        ],
        must_not_contain=[
            "ahb_controller_event",        # event should NOT have fired
        ]
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"Running tests against: {SCRIPT}\n")
    test_hook_init_crash_color_temp()
    test_controller_duplicate_zha_event()
    test_hook_success_turn_off()
    test_controller_no_branch_matched()
    print(f"\n{PASS + FAIL} tests: {PASS} passed, {FAIL} failed")
    sys.exit(0 if FAIL == 0 else 1)
