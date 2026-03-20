"""Unit tests for deploy.py — pure logic only (no SSH, no subprocess)."""
import importlib
import sys
import os
import types
import pytest

# ---------------------------------------------------------------------------
# Bootstrap: import deploy.py without triggering SSH or argparse side-effects
# ---------------------------------------------------------------------------

def _load_deploy():
    """Load deploy module, stubbing subprocess so SSH calls are never made."""
    stub = types.ModuleType("subprocess")
    stub.run = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("SSH called in tests"))
    stub.CompletedProcess = object  # type hint only
    sys.modules.setdefault("subprocess", stub)

    spec = importlib.util.spec_from_file_location(
        "deploy",
        os.path.join(os.path.dirname(__file__), "deploy.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


deploy = _load_deploy()
classify_changes = deploy.classify_changes
_RELOAD_MAP = deploy._RELOAD_MAP


# ---------------------------------------------------------------------------
# classify_changes
# ---------------------------------------------------------------------------

class TestClassifyChanges:
    def test_empty_list_no_restart(self):
        actions, needs_restart = classify_changes([])
        assert actions == set()
        assert needs_restart is False

    def test_automations_yaml(self):
        actions, needs_restart = classify_changes(["automations.yaml"])
        assert ("automation", "reload", "automations") in actions
        assert needs_restart is False

    def test_automations_subdir(self):
        actions, needs_restart = classify_changes(["automations/presence.yaml"])
        assert ("automation", "reload", "automations") in actions
        assert needs_restart is False

    def test_scripts_yaml(self):
        actions, needs_restart = classify_changes(["scripts.yaml"])
        assert ("script", "reload", "scripts") in actions
        assert needs_restart is False

    def test_scenes_yaml(self):
        actions, needs_restart = classify_changes(["scenes.yaml"])
        assert ("scene", "reload", "scenes") in actions
        assert needs_restart is False

    def test_blueprints_dir(self):
        actions, needs_restart = classify_changes(["blueprints/automation/EPMatt/light_new.yaml"])
        assert ("automation", "reload", "automations (blueprints changed)") in actions
        assert needs_restart is False

    def test_groups_yaml(self):
        actions, needs_restart = classify_changes(["groups.yaml"])
        assert ("homeassistant", "reload_groups", "groups") in actions
        assert needs_restart is False

    def test_customize_yaml(self):
        actions, needs_restart = classify_changes(["customize.yaml"])
        assert ("homeassistant", "reload_custom_templates", "custom templates") in actions
        assert needs_restart is False

    def test_configuration_yaml_forces_restart(self):
        actions, needs_restart = classify_changes(["configuration.yaml"])
        assert needs_restart is True

    def test_unknown_file_forces_restart(self):
        actions, needs_restart = classify_changes(["www/custom-card.js"])
        assert needs_restart is True

    def test_mixed_reloadable_and_restart(self):
        """If any file needs a restart, the flag is set regardless of reloadables."""
        actions, needs_restart = classify_changes(["automations.yaml", "configuration.yaml"])
        assert ("automation", "reload", "automations") in actions
        assert needs_restart is True

    def test_deduplication(self):
        """automations.yaml + blueprints both map to automation.reload — only one service call."""
        actions, needs_restart = classify_changes([
            "automations.yaml",
            "automations/lights.yaml",
            "blueprints/automation/EPMatt/light.yaml",
        ])
        # There may be two distinct tuples (different labels) but both call automation.reload.
        # Verify the unique (domain, service) pairs — should be exactly one.
        unique_services = {(d, s) for d, s, _ in actions}
        assert unique_services == {("automation", "reload")}
        assert needs_restart is False

    def test_multiple_distinct_reloads(self):
        actions, needs_restart = classify_changes(["automations.yaml", "scripts.yaml", "scenes.yaml"])
        assert ("automation", "reload", "automations") in actions
        assert ("script", "reload", "scripts") in actions
        assert ("scene", "reload", "scenes") in actions
        assert needs_restart is False

    def test_dotfile_in_repo_forces_restart(self):
        """Files like .gitignore that have no reload mapping require restart."""
        actions, needs_restart = classify_changes([".gitignore"])
        assert needs_restart is True
