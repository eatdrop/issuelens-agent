import unittest

from issuelens.diff_parser import parse_unified_diff
from issuelens.diff_policy import DiffPathPolicyError, validate_diff_paths


def _one_line_diff(old_path: str, new_path: str) -> str:
    return (
        f"--- {old_path}\n"
        f"+++ {new_path}\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )


class DiffPathPolicyTests(unittest.TestCase):
    def test_normalizes_git_prefixes_and_checks_allowlist(self) -> None:
        parsed = parse_unified_diff(
            _one_line_diff("a/src/service.py", "b/src/service.py")
        )

        result = validate_diff_paths(
            parsed,
            allowed_paths={"src/service.py"},
        )

        self.assertEqual(result.changed_paths, ("src/service.py",))

    def test_accepts_new_and_deleted_repository_files(self) -> None:
        new_file = parse_unified_diff(
            """--- /dev/null
+++ b/src/new.py
@@ -0,0 +1 @@
+value = 1
"""
        )
        deleted_file = parse_unified_diff(
            """--- a/src/old.py
+++ /dev/null
@@ -1 +0,0 @@
-value = 1
"""
        )

        self.assertEqual(
            validate_diff_paths(new_file).changed_paths,
            ("src/new.py",),
        )
        self.assertEqual(
            validate_diff_paths(deleted_file).changed_paths,
            ("src/old.py",),
        )

    def test_rejects_posix_windows_and_backslash_paths(self) -> None:
        unsafe_pairs = [
            ("/etc/passwd", "/etc/passwd"),
            ("C:/secret.txt", "C:/secret.txt"),
            ("a/src\\service.py", "b/src\\service.py"),
        ]

        for old_path, new_path in unsafe_pairs:
            with self.subTest(old_path=old_path):
                parsed = parse_unified_diff(_one_line_diff(old_path, new_path))
                with self.assertRaises(DiffPathPolicyError):
                    validate_diff_paths(parsed)

    def test_rejects_parent_traversal_and_git_metadata(self) -> None:
        unsafe_pairs = [
            ("a/../../secret.txt", "b/../../secret.txt"),
            ("a/.git/config", "b/.git/config"),
        ]

        for old_path, new_path in unsafe_pairs:
            with self.subTest(old_path=old_path):
                parsed = parse_unified_diff(_one_line_diff(old_path, new_path))
                with self.assertRaises(DiffPathPolicyError):
                    validate_diff_paths(parsed)

    def test_rejects_path_outside_allowlist(self) -> None:
        parsed = parse_unified_diff(
            _one_line_diff("a/src/service.py", "b/src/service.py")
        )

        with self.assertRaisesRegex(DiffPathPolicyError, "not authorized"):
            validate_diff_paths(parsed, allowed_paths={"src/other.py"})

    def test_rejects_renames(self) -> None:
        parsed = parse_unified_diff(
            _one_line_diff("a/src/old_name.py", "b/src/new_name.py")
        )

        with self.assertRaisesRegex(DiffPathPolicyError, "renames are not allowed"):
            validate_diff_paths(parsed)

    def test_rejects_duplicate_file_patches(self) -> None:
        parsed = parse_unified_diff(
            _one_line_diff("a/src/service.py", "b/src/service.py")
            + _one_line_diff("a/src/service.py", "b/src/service.py")
        )

        with self.assertRaisesRegex(DiffPathPolicyError, "duplicate file patch"):
            validate_diff_paths(parsed)


if __name__ == "__main__":
    unittest.main()
