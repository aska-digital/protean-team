#!/usr/bin/env python3
"""
Tests for build/check-spawn-contract.py and its repo examples.

Uses only stdlib and matches repository conventions. Runs from a fresh clone.
"""

import os
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "build")


class TestSpawnContractChecker(unittest.TestCase):
    """Tests for check-spawn-contract.py validator."""

    def test_script_exists(self):
        path = os.path.join(BUILD, "check-spawn-contract.py")
        self.assertTrue(os.path.isfile(path), f"not found at {path}")

    def test_script_syntax(self):
        path = os.path.join(BUILD, "check-spawn-contract.py")
        with open(path, encoding="utf-8") as f:
            compile(f.read(), path, "exec")

    def test_self_test_passes(self):
        result = subprocess.run(
            [sys.executable, os.path.join(BUILD, "check-spawn-contract.py"),
             "--self-test"],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_example_check_passes(self):
        result = subprocess.run(
            [sys.executable, os.path.join(BUILD, "check-spawn-contract.py"),
             "--example-check"],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_valid_example_accepted(self):
        result = subprocess.run(
            [sys.executable, os.path.join(BUILD, "check-spawn-contract.py"),
             os.path.join(ROOT, "examples", "spawn-contract.valid.yaml")],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_invalid_example_rejected(self):
        result = subprocess.run(
            [sys.executable, os.path.join(BUILD, "check-spawn-contract.py"),
             os.path.join(ROOT, "examples", "spawn-contract.invalid.yaml")],
            capture_output=True, text=True, cwd=ROOT, timeout=120,
        )
        self.assertNotEqual(result.returncode, 0,
                            "invalid example must be rejected")

    def test_template_exists(self):
        path = os.path.join(ROOT, "templates", "contracts",
                            "spawn-contract.md.tmpl")
        self.assertTrue(os.path.isfile(path), f"not found at {path}")

    def test_runbook_exists(self):
        path = os.path.join(ROOT, "choreography",
                            "subagent-fleet-runbook.md")
        self.assertTrue(os.path.isfile(path), f"not found at {path}")


if __name__ == "__main__":
    unittest.main()
