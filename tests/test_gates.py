#!/usr/bin/env python3
"""
Test suite for verify-all.py and surface-scan.py.

Uses only stdlib and matches repository conventions. Runs from a fresh clone.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

# Add build directory to path for imports
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BUILD = os.path.join(ROOT, "build")


class TestGenericizePortability(unittest.TestCase):
    """Tests for genericize.py CI portability (missing source handling)."""

    def test_derive_identity_inventory_missing_source(self):
        """derive_identity_inventory should return empty lists when source is absent."""
        import importlib.util
        spec = importlib.util.spec_from_file_location("genericize",
            os.path.join(BUILD, "genericize.py"))
        assert spec is not None
        genericize = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(genericize)

        # Test with non-existent path
        handles, names = genericize.derive_identity_inventory("/nonexistent/path/here")
        self.assertEqual(handles, [])
        self.assertEqual(names, [])

        # Test with path that exists but is not a directory
        with tempfile.NamedTemporaryFile(delete=False) as f:
            tmpfile = f.name
        try:
            handles, names = genericize.derive_identity_inventory(tmpfile)
            self.assertEqual(handles, [])
            self.assertEqual(names, [])
        finally:
            os.unlink(tmpfile)


class TestVerifyAll(unittest.TestCase):
    """Tests for verify-all.py gate runner."""

    def test_script_exists(self):
        """verify-all.py should exist in build directory."""
        path = os.path.join(BUILD, "verify-all.py")
        self.assertTrue(os.path.isfile(path), f"verify-all.py not found at {path}")

    def test_script_syntax(self):
        """verify-all.py should have valid Python syntax."""
        path = os.path.join(BUILD, "verify-all.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        # Should not raise SyntaxError
        compile(source, path, "exec")

    def test_all_required_release_gates_pass(self):
        """Exercise actual gates from a committed, self-contained snapshot."""
        required = [
            "sweep-gate.py", "review-gate.py", "surface-scan.py",
            "check-artifact-contract self-test", "preflight/check self-test",
            "report/check self-test", "check-contracts aggregate",
            "fresh-clone fork-dryrun", "check-unique-headings",
            "check-internal-names", "review-repair self-test",
            "review-repair fixtures",
        ]
        # An ordinary repository avoids a worktree .git file carrying a local
        # path. Copy candidate source files without generated instance data;
        # keep all privacy gates enabled in the resulting snapshot.
        files = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
             "--exclude=.pytest_cache/"],
            cwd=ROOT, capture_output=True, check=True,
        ).stdout.decode().split("\0")
        with tempfile.TemporaryDirectory(prefix="release-gates-", dir="/tmp") as tmp:
            snapshot = os.path.join(tmp, "repo")
            home = os.path.join(tmp, "home")
            os.makedirs(snapshot)
            os.makedirs(home)
            env = dict(os.environ, HOME=home, GIT_CONFIG_NOSYSTEM="1",
                       GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                       GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")
            for name in filter(None, files):
                source = os.path.join(ROOT, name)
                if not os.path.isfile(source):
                    continue
                destination = os.path.join(snapshot, name)
                os.makedirs(os.path.dirname(destination), exist_ok=True)
                shutil.copy2(source, destination)
            # Force-add the copied source: tracked files may intentionally
            # match .gitignore (for example the shipped names blocklist).
            for args in (["init", "-b", "main"], ["add", "-f", "-A"],
                         ["commit", "-m", "candidate fixture"],
                         ["remote", "add", "origin", snapshot]):
                subprocess.run(["git"] + args, cwd=snapshot, env=env,
                               capture_output=True, check=True)
            result = subprocess.run(
                [sys.executable, os.path.join(snapshot, "build", "verify-all.py")],
                capture_output=True, text=True, cwd=snapshot, env=env, timeout=300,
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        executed = [line.removeprefix("STEP: ") for line in result.stdout.splitlines()
                    if line.startswith("STEP: ")]
        self.assertEqual(executed, required)
        for name in required:
            self.assertIn("✓ PASS: " + name, result.stdout)
        self.assertIn("Failed: 0", result.stdout)


class TestSurfaceScanEmptyIdentifiers(unittest.TestCase):
    """Tests for surface-scan.py handling empty/missing identifiers.yaml."""

    def test_builtin_terms_defined(self):
        """Built-in safety terms should be defined in surface-scan."""
        path = os.path.join(BUILD, "surface-scan.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        self.assertIn("_BUILTIN_SAFETY_TERMS", source)
        self.assertIn("strong_terms", source)

    def test_strong_terms_includes_builtin(self):
        """strong_terms() should include _BUILTIN_SAFETY_TERMS."""
        path = os.path.join(BUILD, "surface-scan.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        # Should set strong = set(_BUILTIN_SAFETY_TERMS)
        self.assertIn("set(_BUILTIN_SAFETY_TERMS)", source)

    def test_surface_scan_passes_when_clean(self):
        """surface-scan should pass on clean repository."""
        path = os.path.join(BUILD, "surface-scan.py")
        result = subprocess.run(
            [sys.executable, path],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60
        )
        self.assertEqual(result.returncode, 0,
            f"surface-scan failed:\n{result.stdout}\n{result.stderr}")
        self.assertIn("PASS", result.stdout)


class TestGateScripts(unittest.TestCase):
    """Tests for individual gate scripts."""

    def test_sweep_gate_syntax(self):
        """sweep-gate.py should have valid syntax."""
        path = os.path.join(BUILD, "sweep-gate.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        compile(source, path, "exec")

    def test_review_gate_syntax(self):
        """review-gate.py should have valid syntax."""
        path = os.path.join(BUILD, "review-gate.py")
        with open(path, encoding="utf-8") as f:
            source = f.read()
        compile(source, path, "exec")

    def test_check_artifact_contract_selftest(self):
        """check-artifact-contract.py --self-test should pass."""
        path = os.path.join(BUILD, "check-artifact-contract.py")
        result = subprocess.run(
            [sys.executable, path, "--self-test"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60
        )
        self.assertEqual(result.returncode, 0,
            f"check-artifact-contract self-test failed:\n{result.stdout}\n{result.stderr}")

    def test_preflight_check_selftest(self):
        """preflight/check.py --selftest should pass."""
        path = os.path.join(BUILD, "preflight", "check.py")
        result = subprocess.run(
            [sys.executable, path, "--selftest"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60
        )
        self.assertEqual(result.returncode, 0,
            f"preflight/check self-test failed:\n{result.stdout}\n{result.stderr}")

    def test_report_check_selftest(self):
        """report/check.py --selftest should pass."""
        path = os.path.join(BUILD, "report", "check.py")
        result = subprocess.run(
            [sys.executable, path, "--selftest"],
            capture_output=True,
            text=True,
            cwd=ROOT,
            timeout=60
        )
        self.assertEqual(result.returncode, 0,
            f"report/check self-test failed:\n{result.stdout}\n{result.stderr}")


class TestGitHubWorkflow(unittest.TestCase):
    """Tests for GitHub Actions workflow."""

    def test_workflow_exists(self):
        """verify.yml should exist in .github/workflows."""
        path = os.path.join(ROOT, ".github", "workflows", "verify.yml")
        self.assertTrue(os.path.isfile(path), f"verify.yml not found at {path}")

    def test_workflow_syntax(self):
        """verify.yml should be valid YAML."""
        import yaml
        path = os.path.join(ROOT, ".github", "workflows", "verify.yml")
        with open(path, encoding="utf-8") as f:
            workflow = yaml.safe_load(f)
        self.assertIn("name", workflow)
        self.assertIn(True, workflow)  # 'on' is parsed as True in Python YAML
        self.assertIn("jobs", workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
