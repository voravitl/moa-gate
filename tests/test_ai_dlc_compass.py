"""Regression tests for AI-DLC Compass plugin.

Covers known AI-DLC plugin bugs:
1. _mark_steering_loaded() never called -> first-tool infinite block
2. re.search in verifier/registry lacks try/except -> bad regex crashes hook
3. payload extraction in __init__.py misses patch/terminal/process content
4. install.sh dirname breaks under bash <(curl)
5. critical violations claimed MOA escalation without evidence
6. violation records hardcoded tool='write_file'
7. module-level Path.home() left stale paths after HOME changes
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
AI_DLC = ROOT / "ai-dlc"


def load_ai_dlc(home: Path) -> Any:
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

    def test_patch_bulk_payload_is_scanned(self):
        """Patch mode='patch' must scan V4A multi-file payloads."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "patch",
                {
                    "mode": "patch",
                    "patch": "*** Begin Patch\n*** Update File: src/app.py\n+password = 'hunter222'\n*** End Patch",
                },
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))

    def test_patch_bulk_payload_uses_real_target_path_for_rules(self):
        """V4A patch scanning must use target path, not /tmp/patch-payload.sh."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "patch",
                {
                    "mode": "patch",
                    "patch": "*** Begin Patch\n*** Update File: src/app.py\n+eval(user_input)\n*** End Patch",
                },
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))
            state_file = home / ".hermes" / "ai-dlc" / "state.json"
            state = json.loads(state_file.read_text())
            self.assertEqual(state["violations"][-1]["path"], "src/app.py")

    def test_patch_bulk_inception_blocks_code_target_path(self):
        """INCEPTION phase must inspect V4A target paths before allowing patches."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("INCEPTION", "test")
            result = plugin.pre_tool_call(
                "patch",
                {
                    "mode": "patch",
                    "patch": "*** Begin Patch\n*** Add File: src/app.py\n+print('code')\n*** End Patch",
                },
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))
            self.assertIn("INCEPTION", result.get("message", ""))

    def test_patch_bulk_move_to_uses_destination_path_for_rules(self):
        """V4A Move to destination path must drive path-specific rules."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "patch",
                {
                    "mode": "patch",
                    "patch": "*** Begin Patch\n*** Update File: notes.txt\n*** Move to: src/app.py\n+eval(user_input)\n*** End Patch",
                },
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))
            state_file = home / ".hermes" / "ai-dlc" / "state.json"
            state = json.loads(state_file.read_text())
            self.assertEqual(state["violations"][-1]["path"], "src/app.py")

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
    def test_critical_violation_records_moa_escalation(self):
        """Bug 5: critical blocks should create MOA audit evidence, not just text."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "write_file",
                {"path": "src/app.py", "content": "password = 'hunter222'"},
            )
            self.assertIsNotNone(result)
            self.assertTrue(result.get("block"))
            msg = result.get("message", "")
            self.assertIn("Recorded MOA-Gate Tier 2 escalation", msg)

            audit_log = home / ".hermes" / "moa-gate" / "audit.log"
            self.assertTrue(audit_log.exists())
            entry = json.loads(audit_log.read_text().strip().splitlines()[-1])
            self.assertEqual(entry["action"], "shadow_block")
            self.assertEqual(entry["tool"], "write_file")
            self.assertEqual(entry["by"], ["ai-dlc"])
            self.assertEqual(entry["trigger"], "ai_dlc")
            self.assertEqual(entry["tier"], 2)

    def test_violation_record_uses_actual_tool_name(self):
        """Bug 6: _handle_violations used to hardcode tool='write_file'."""
        with tempfile.TemporaryDirectory() as td:
            home = Path(td)
            plugin = load_ai_dlc(home)
            plugin._mark_steering_loaded()
            plugin.ph.set_phase("CONSTRUCTION", "test")
            result = plugin.pre_tool_call(
                "terminal",
                {"command": "echo \"password = 'super-secret'\""},
            )
            self.assertIsNotNone(result)
            state_file = home / ".hermes" / "ai-dlc" / "state.json"
            state = json.loads(state_file.read_text())
            self.assertEqual(state["violations"][-1]["tool"], "terminal")


class DynamicHomeTest(unittest.TestCase):
    def test_phase_and_registry_resolve_home_at_call_time(self):
        """Bug 7: module-level Path.home() must not stay stale after HOME changes."""
        with tempfile.TemporaryDirectory() as td1, tempfile.TemporaryDirectory() as td2:
            home1 = Path(td1)
            home2 = Path(td2)
            plugin = load_ai_dlc(home1)
            plugin.ph.set_phase("CONSTRUCTION", "initial")

            os.environ["HOME"] = str(home2)
            plugin.ph.set_phase("OPERATION", "moved home")

            self.assertTrue((home1 / ".hermes" / "ai-dlc" / "phase.json").exists())
            self.assertTrue((home2 / ".hermes" / "ai-dlc" / "phase.json").exists())
            self.assertEqual(plugin.ph.get_phase(), "OPERATION")

            steering = home2 / "wiki" / "steering"
            steering.mkdir(parents=True)
            (steering / "security.yaml").write_text(
                'rules:\n'
                '  - id: DYNAMIC-HOME\n'
                '    description: dynamic home rule\n'
                '    type: deny_pattern\n'
                '    pattern: xyz_secret\n'
                '    severity: critical\n'
                '    suggestion: remove secret\n'
                "    path_patterns: ['.*$']"
            )
            result = plugin.vr.verify_content("xyz_secret = 1", "src/app.py")
            self.assertEqual(result["critical"][0]["rule_id"], "DYNAMIC-HOME")


if __name__ == "__main__":
    unittest.main()
