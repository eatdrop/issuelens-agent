import tempfile
import unittest
from pathlib import Path

from issuelens.repository import ReadOnlyRepository, RepositoryAccessError


class RepositorySafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "safe.py").write_text("value = 1\n", encoding="utf-8")
        self.repository = ReadOnlyRepository(self.root)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_rejects_parent_traversal(self) -> None:
        with self.assertRaises(RepositoryAccessError):
            self.repository.read_text("../secret.txt")

    def test_rejects_absolute_paths(self) -> None:
        with self.assertRaises(RepositoryAccessError):
            self.repository.read_text("/etc/passwd")

    def test_snapshot_changes_when_repository_changes(self) -> None:
        before = self.repository.snapshot_hash()
        (self.root / "safe.py").write_text("value = 2\n", encoding="utf-8")
        after = self.repository.snapshot_hash()
        self.assertNotEqual(before, after)

    def test_symlink_escape_is_not_listed(self) -> None:
        outside = self.root.parent / f"{self.root.name}-outside.txt"
        outside.write_text("secret\n", encoding="utf-8")
        try:
            (self.root / "leak.txt").symlink_to(outside)
            self.assertNotIn("leak.txt", self.repository.list_files())
        finally:
            outside.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
