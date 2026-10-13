#!/usr/bin/env python3
"""Exercise the real fresh-clone script against committed candidate fixtures."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = "scripts/fresh-clone-test.sh"
LIVE = ("build/manifest.tsv", "build/REVIEW.md", "build/identifiers.yaml")
FROZEN = ("build/manifest.frozen.tsv", "build/REVIEW.frozen.md",
          "templates/MANIFEST.md", "build/internal-name-blocklist.yaml")


class TestFreshClone(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory(prefix="clone-contract-", dir="/tmp")
        self.addCleanup(self.work.cleanup)
        self.base = Path(self.work.name)
        home = self.base / "home"
        home.mkdir()
        self.env = dict(os.environ, HOME=str(home), HERMES_HOME=str(home),
                        GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME="fixture", GIT_AUTHOR_EMAIL="fixture@example.invalid",
                        GIT_COMMITTER_NAME="fixture", GIT_COMMITTER_EMAIL="fixture@example.invalid")

    def commit(self, repo):
        # Preserve copied source even when an already-tracked path matches an
        # ignore rule. No generated output is added to these source fixtures.
        for args in (["init", "-b", "main"], ["add", "-f", "-A"],
                     ["commit", "-m", "fresh-clone source fixture"],
                     ["remote", "add", "origin", str(repo)]):
            # Object creation can launch background maintenance before the
            # next local clone. Keep this short-lived fixture stable.
            subprocess.run(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false"] + args,
                           cwd=repo, env=self.env,
                           capture_output=True, check=True)

    def run_clone(self, repo):
        return subprocess.run(["bash", SCRIPT], cwd=repo, env=self.env,
                              capture_output=True, text=True, timeout=300)

    def test_clean_candidate_clone_reproduces_without_a_failure_banner(self):
        repo = self.base / "clean"
        repo.mkdir()
        names = subprocess.check_output(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard",
             "--exclude=.pytest_cache/"], cwd=ROOT,
        ).decode().split("\0")
        for name in filter(None, names):
            source = ROOT / name
            if source.is_file():
                destination = repo / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        self.commit(repo)
        result = self.run_clone(repo)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn("FAIL:", result.stdout + result.stderr)
        self.assertIn("=== FRESH-CLONE TEST: PASS ===", result.stdout)
        self.assertIn("all live artifacts absent", result.stdout)
        self.assertIn("all frozen artifacts present", result.stdout)

    def test_each_artifact_contract_violation_stops_before_generation(self):
        for index, (path, unexpected) in enumerate(
                [(name, True) for name in LIVE] + [(name, False) for name in FROZEN]):
            with self.subTest(path=path, unexpected=unexpected):
                repo = self.base / ("invalid-%d" % index)
                (repo / "scripts").mkdir(parents=True)
                shutil.copy2(ROOT / SCRIPT, repo / SCRIPT)
                for name in FROZEN:
                    file = repo / name
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text("synthetic fixture\n", encoding="utf-8")
                if unexpected:
                    file = repo / path
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_text("unexpected synthetic live artifact\n", encoding="utf-8")
                else:
                    (repo / path).unlink()
                self.commit(repo)
                result = self.run_clone(repo)
                self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
                self.assertIn("FAIL: " + path, result.stdout)
                self.assertNotIn("[3/5]", result.stdout)
                self.assertNotIn("=== FRESH-CLONE TEST: PASS ===", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
