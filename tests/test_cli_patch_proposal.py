from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from issuelens.cli import main
from issuelens.repository import ReadOnlyRepository


DIFF = """\
--- a/app.py
+++ b/app.py
@@ -1 +1 @@
-value = 1
+value = 2
"""
UNSAFE_DIFF = """\
--- a/../secret.py
+++ b/../secret.py
@@ -1 +1 @@
-old
+new
"""


class PatchProposalCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.repository_root = self.root / "repository"
        self.repository_root.mkdir()
        self.source_path = self.repository_root / "app.py"
        self.source_path.write_text("value = 1\n", encoding="utf-8")
        self.diff_path = self.root / "candidate.diff"
        self.diff_path.write_text(DIFF, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _run(self) -> tuple[int, str]:
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = main(
                [
                    "patch-proposal",
                    "--repo",
                    str(self.repository_root),
                    "--diff",
                    str(self.diff_path),
                ]
            )
        return exit_code, output.getvalue()

    def test_outputs_deterministic_read_only_proposal(self) -> None:
        repository = ReadOnlyRepository(self.repository_root)
        before_snapshot = repository.snapshot_hash()
        before_content = self.source_path.read_bytes()
        before_modified_ns = self.source_path.stat().st_mtime_ns
        before_entries = sorted(self.repository_root.rglob("*"))

        first_exit, first_output = self._run()
        second_exit, second_output = self._run()
        payload = json.loads(first_output)

        self.assertEqual(first_exit, 0)
        self.assertEqual(second_exit, 0)
        self.assertEqual(second_output, first_output)
        self.assertEqual(payload["base_snapshot_hash"], before_snapshot)
        self.assertEqual(payload["changed_paths"], ["app.py"])
        self.assertEqual(payload["changed_file_count"], 1)
        self.assertEqual(payload["added_lines"], 1)
        self.assertEqual(payload["removed_lines"], 1)
        self.assertEqual(len(payload["proposal_hash"]), 64)
        self.assertTrue(payload["repository_unchanged"])
        self.assertEqual(self.source_path.read_bytes(), before_content)
        self.assertEqual(
            self.source_path.stat().st_mtime_ns,
            before_modified_ns,
        )
        self.assertEqual(
            sorted(self.repository_root.rglob("*")),
            before_entries,
        )
        self.assertEqual(repository.snapshot_hash(), before_snapshot)

    def test_rejects_unsafe_diff_path(self) -> None:
        self.diff_path.write_text(UNSAFE_DIFF, encoding="utf-8")

        with self.assertRaisesRegex(SystemExit, "unsafe path"):
            self._run()

        self.assertEqual(
            self.source_path.read_text(encoding="utf-8"),
            "value = 1\n",
        )

    def test_rejects_malformed_diff(self) -> None:
        self.diff_path.write_text("not a diff\n", encoding="utf-8")

        with self.assertRaisesRegex(SystemExit, "unexpected content"):
            self._run()

    def test_rejects_oversized_diff(self) -> None:
        self.diff_path.write_text(
            "x" * 2_000_001,
            encoding="utf-8",
        )

        with self.assertRaisesRegex(SystemExit, "maximum size"):
            self._run()

    def test_rejects_symbolic_link_diff(self) -> None:
        real_diff = self.root / "real.diff"
        real_diff.write_text(DIFF, encoding="utf-8")
        self.diff_path.unlink()
        try:
            self.diff_path.symlink_to(real_diff)
        except OSError:
            self.skipTest("symbolic links are not available")

        with self.assertRaisesRegex(SystemExit, "symbolic link"):
            self._run()


if __name__ == "__main__":
    unittest.main()
