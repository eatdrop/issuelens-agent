from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from issuelens.reporting import RunArtifacts


class RunArtifactsTests(unittest.TestCase):
    def test_rejects_run_id_path_traversal(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_root = Path(root) / "runs"

            with self.assertRaisesRegex(ValueError, "run_id"):
                RunArtifacts(run_root, "../escape")

            self.assertFalse((Path(root) / "escape").exists())

    def test_resume_rejects_symbolic_link_trace(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            run_root = Path(root) / "runs"
            run_path = run_root / "resume"
            run_path.mkdir(parents=True)
            external = Path(root) / "external.txt"
            external.write_text("unchanged\n", encoding="utf-8")
            try:
                (run_path / "trace.jsonl").symlink_to(external)
            except OSError:
                self.skipTest("symbolic links are not available")

            with self.assertRaisesRegex(ValueError, "symbolic link"):
                RunArtifacts(run_root, "resume", resume=True)

            self.assertEqual(external.read_text(encoding="utf-8"), "unchanged\n")


if __name__ == "__main__":
    unittest.main()
