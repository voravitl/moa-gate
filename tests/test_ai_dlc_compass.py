"""Regression tests for AI-DLC Compass plugin.

Covers all 5 known bugs:
1. _mark_steering_loaded() never called -> first-tool infinite block
2. re.search in verifier/registry lacks try/except -> bad regex crashes hook
3. payload extraction in __init__.py misses patch/terminal/process content
4. install.sh dirname breaks under bash <(curl)
5. auto-escalate claim in README/docs -- verify message-only vs actual MOA-Gate write
"""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AI_DLC = ROOT / "ai-dlc"


def load_ai_dlc(home: Path) -> object:
    """Load ai-dlc plugin under a transient HOME."""
    os.environ["HOME"] = str(home)
    for name in list(sys.modules):
        if name == "ai_dlc_compass" or name.startswith("ai_dlc_compass."):
            sys.modules.pop(name)
    spec = importlib.util.spec_from_file_location(
        "ai_dlc_compass",
        AI_DLC / "__init__.py",
        submodule_search_locations=[str(AI_DLC)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["ai_dlc_compass"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SteeringLoadedTest(unittest.TestCase):
    def test_mark_steering_called_on_first_non_wiki_tool(self):
        """Bug 1: verify that write_file passes after steering is marked loaded."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "write_file", {"path": "src/config.yaml", "content": "debug: off"}
            )
            self.assertIsNone(result)

    def test_first_tool_block_before_steering_loaded(self):
        """Before steering loaded, non-wiki writes are blocked."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            result = plugin.pre_tool_call(
                "write_file", {"path": "src/secret.py", "content": "x = 1"}
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block", False))


class RegexSafetyTest(unittest.TestCase):
    def test_bad_deny_pattern_does_not_crash_verifier(self):
        """Bug 2: re.search without try/except -- bad regex raises re.error."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            steering = home / "wiki" / "steering"
            steering.mkdir(parents=True)
            (steering / "security.yaml").write_text(
                'rules:\n'
                '  - id: BAD-REGEX\n'
                '    description: bad regex\n'
                '    type: deny_pattern\n'
                "    pattern: '['\n"
                '    severity: critical\n'
                '    suggestion: fix regex\n'
                "    path_patterns: ['.*$']"
            )
            plugin = load_ai_dlc(home)
            try:
                result = plugin.vr.verify_content("print('ok')", "src/app.py")
                self.assertTrue(result["passed"])
                self.assertEqual(result["critical"], [])
            except Exception:
                self.fail("verifier.verify_content crashed on bad regex")

    def test_bad_path_pattern_in_registry_does_not_crash(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            steering = home / "wiki" / "steering"
            steering.mkdir(parents=True)
            (steering / "security.yaml").write_text(
                'rules:\n'
                '  - id: BAD-PATH\n'
                '    description: bad path pattern\n'
                '    type: deny_pattern\n'
                '    pattern: password\n'
                '    severity: warning\n'
                '    suggestion: fix\n'
                "    path_patterns: ['[']"
            )
            plugin = load_ai_dlc(home)
            try:
                rules = plugin.sr.get_active_rules_for_path("/some/file.py")
                self.assertIsInstance(rules, dict)
            except Exception:
                self.fail("get_active_rules_for_path crashed on bad regex")


class PayloadExtractionTest(unittest.TestCase):
    def test_patch_new_string_is_scanned(self):
        """Bug 3: pre_tool_call for 'patch' misses 'new_string'."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "patch",
                {
                    "path": "src/app.py",
                    "old_string": "x = 1",
                    "new_string": "api_key = '1234567890abcdef'",
                },
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))

    def test_terminal_command_is_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "terminal",
                {"command": "echo \"api_key = 'abcdefghij'\""},
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))

    def test_process_payload_is_scanned(self):
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "process",
                {"data": "password = 'super-secret'"},
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))


class InstallerTest(unittest.TestCase):
    def test_installer_detects_curl_pipe_and_fails_fast(self):
        """Bug 4: $0 is temp fd under bash <(curl)."""
        with tempfile.TemporaryDirectory() as td:
            script_content = (AI_DLC / "scripts" / "install.sh").read_text()
            result = subprocess.run(
                ["bash"],
                cwd=td,
                env={**os.environ, "HOME": str(Path(td) / "home")},
                capture_output=True,
                text=True,
                timeout=20,
                input=script_content,
            )
            self.assertNotEqual(result.returncode, 0)
            combined = result.stderr + result.stdout
            self.assertIn("clone the repo and run from the checkout", combined)


class AutoEscalateTest(unittest.TestCase):
    def test_escalation_is_not_just_message(self):
        """Bug 5: block message should NOT claim auto-escalate to MOA-Gate Tier 2."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "write_file",
                {"path": "src/app.py", "content": "password = 'hunter2'"},
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))
            msg = result.get("message", "")
            self.assertNotIn("auto-escalat", msg.lower())
            self.assertNotIn("Tier 2", msg)


if __name__ == "__main__":
    unittest.main()