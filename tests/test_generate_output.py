"""Output preservation with synthetic templates and mocked source gates."""

import contextlib
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

BUILD = Path(__file__).resolve().parents[1] / "build"
sys.path.insert(0, str(BUILD))
# genericize derives an identity inventory at import time. Use no live fleet.
with mock.patch("os.path.expanduser", return_value="/nonexistent/test-profiles"):
    spec = importlib.util.spec_from_file_location("generate", BUILD / "generate.py")
    generate = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generate)


class GenerateOutputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.templates = self.root / "templates"
        self.templates.mkdir()
        (self.templates / "note.md").write_text("Team: {TEAM_NAME}\n")
        self.out = self.root / "kit"
        (self.out / "nested").mkdir(parents=True)
        (self.out / "last-good.bin").write_bytes(b"\x00last good\xff")
        (self.out / "nested" / "note.md").write_text("keep this too")
        self.before = self.snapshot()
        self.output_mode = self.out.stat().st_mode & 0o777
        for name, value in {
            "ROOT": str(self.root), "TEMPLATES": str(self.templates),
            "MANIFEST": str(self.root / "absent-manifest.tsv"),
            "AUTHORED_FRESH": [],
        }.items():
            patcher = mock.patch.object(generate, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        for name, value in {
            "load_manifest": {"note.md": ("SHIPPABLE", "TEMPLATE")},
            "parse_review": {}, "load_pack_schema": None,
        }.items():
            patcher = mock.patch.object(generate, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def snapshot(self):
        return {str(p.relative_to(self.out)): p.read_bytes()
                for p in self.out.rglob("*") if p.is_file()}

    def run_generator(self, *args, gate_code=0):
        gate_results = [mock.Mock(returncode=code, stdout="")
                        for code in (gate_code if isinstance(gate_code, list) else [gate_code] * 2)]
        with mock.patch.object(sys, "argv", ["generate.py", "--out", str(self.out), *args]), \
                mock.patch.object(generate.subprocess, "run", side_effect=gate_results), \
                contextlib.redirect_stdout(io.StringIO()) as output:
            code = generate.main()
        return code, output.getvalue()

    def assert_preserved(self):
        self.assertEqual(self.snapshot(), self.before)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["kit", "templates"])

    def test_declared_schema_failure_preserves_last_good(self):
        with mock.patch.object(generate, "load_pack_schema", return_value={"NEVER_USED"}):
            code, output = self.run_generator()
        self.assertEqual(code, 1)
        self.assertIn("DECLARED PLACEHOLDER(S) NOT RESOLVED", output)
        self.assert_preserved()

    def test_strict_failure_preserves_last_good(self):
        (self.templates / "note.md").write_text("{MISSING}\n")
        code, output = self.run_generator("--strict")
        self.assertEqual(code, 1)
        self.assertIn("UNRESOLVED PLACEHOLDERS", output)
        self.assert_preserved()

    def test_gate_failure_preserves_last_good(self):
        for gates in ([1], [0, 1]):
            with self.subTest(gates=gates):
                code, _ = self.run_generator(gate_code=gates)
                self.assertEqual(code, 1)
                self.assert_preserved()

    def test_generation_exception_preserves_last_good_and_cleans_candidate(self):
        # Fail late, after a template has already been written.
        with mock.patch.object(generate, "validate_schema", side_effect=OSError("synthetic failure")):
            with self.assertRaisesRegex(OSError, "synthetic failure"):
                self.run_generator()
        self.assert_preserved()

    def test_success_replaces_output_and_reports_requested_path(self):
        code, output = self.run_generator()
        self.assertEqual(code, 0)
        self.assertEqual((self.out / "note.md").read_text(), "Team: Your Team\n")
        self.assertEqual(self.out.stat().st_mode & 0o777, self.output_mode)
        self.assertTrue((self.out / "AUDIT.md").is_file())
        self.assertFalse((self.out / "last-good.bin").exists())
        self.assertIn(f"Kit assembled at {self.out}", output)
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["kit", "templates"])

    def test_failed_candidate_promotion_restores_last_good(self):
        replace = os.replace
        calls = []

        def fail_second_replace(src, dst):
            calls.append((src, dst))
            if len(calls) == 2:
                raise OSError("synthetic promotion failure")
            return replace(src, dst)

        with mock.patch.object(generate.os, "replace", side_effect=fail_second_replace):
            with self.assertRaisesRegex(OSError, "synthetic promotion failure"):
                self.run_generator()
        self.assertEqual(len(calls), 3)
        self.assert_preserved()

    def test_failed_rollback_keeps_backup_and_reports_its_path(self):
        replace = os.replace
        backups = []

        def fail_promotion_and_rollback(src, dst):
            if not backups:
                backups.append(Path(dst))
                return replace(src, dst)
            raise OSError("synthetic rename failure")

        with mock.patch.object(generate.os, "replace", side_effect=fail_promotion_and_rollback):
            with self.assertRaisesRegex(OSError, "previous output retained at") as error:
                self.run_generator()
        backup = backups[0]
        self.assertIn(str(backup), str(error.exception))
        self.assertEqual({str(p.relative_to(backup)): p.read_bytes()
                          for p in backup.rglob("*") if p.is_file()}, self.before)
        self.assertFalse(self.out.exists())
        self.assertFalse(any(".build-" in p.name for p in self.root.iterdir()))

    def test_success_creates_previously_absent_output(self):
        import shutil
        shutil.rmtree(self.out)
        code, _ = self.run_generator()
        self.assertEqual(code, 0)
        self.assertEqual((self.out / "note.md").read_text(), "Team: Your Team\n")
        self.assertTrue((self.out / "AUDIT.md").is_file())

    def test_success_preserves_existing_output_root_permissions(self):
        self.out.chmod(0o750)
        code, _ = self.run_generator()
        self.assertEqual(code, 0)
        self.assertEqual(self.out.stat().st_mode & 0o777, 0o750)


if __name__ == "__main__":
    unittest.main()
