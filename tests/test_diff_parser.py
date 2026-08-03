import unittest

from issuelens.diff_parser import UnifiedDiffParseError, parse_unified_diff


class UnifiedDiffParserTests(unittest.TestCase):
    def test_parses_single_file_hunk_and_counts_changes(self) -> None:
        parsed = parse_unified_diff(
            """diff --git a/src/math.py b/src/math.py
index 1111111..2222222 100644
--- a/src/math.py
+++ b/src/math.py
@@ -1,3 +1,5 @@ calculate
 def divide(left, right):
-    return left / right
+    if right == 0:
+        raise ValueError("zero denominator")
+    return left / right
 """
        )

        self.assertEqual(parsed.changed_file_count, 1)
        file_patch = parsed.files[0]
        self.assertEqual(file_patch.old_path, "a/src/math.py")
        self.assertEqual(file_patch.new_path, "b/src/math.py")
        self.assertFalse(file_patch.is_new_file)
        self.assertFalse(file_patch.is_deleted_file)
        self.assertEqual(file_patch.hunks[0].section, "calculate")
        self.assertEqual(file_patch.hunks[0].added_line_count, 3)
        self.assertEqual(file_patch.hunks[0].removed_line_count, 1)

    def test_parses_multiple_files(self) -> None:
        parsed = parse_unified_diff(
            """--- a/one.py
+++ b/one.py
@@ -1 +1 @@
-old
+new
--- a/two.py
+++ b/two.py
@@ -2 +2 @@
-before
+after
"""
        )

        self.assertEqual(parsed.changed_file_count, 2)
        self.assertEqual(
            [file_patch.new_path for file_patch in parsed.files],
            ["b/one.py", "b/two.py"],
        )

    def test_parses_new_and_deleted_files(self) -> None:
        new_file = parse_unified_diff(
            """--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+value = 1
+print(value)
"""
        ).files[0]
        deleted_file = parse_unified_diff(
            """--- a/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-value = 1
-print(value)
"""
        ).files[0]

        self.assertTrue(new_file.is_new_file)
        self.assertFalse(new_file.is_deleted_file)
        self.assertTrue(deleted_file.is_deleted_file)

    def test_supports_omitted_counts_and_no_newline_marker(self) -> None:
        parsed = parse_unified_diff(
            """--- a/message.txt
+++ b/message.txt
@@ -1 +1 @@
-old
\\ No newline at end of file
+new
\\ No newline at end of file
"""
        )

        hunk = parsed.files[0].hunks[0]
        self.assertEqual((hunk.old_count, hunk.new_count), (1, 1))
        self.assertEqual(len(hunk.lines), 4)

    def test_rejects_hunk_count_mismatch(self) -> None:
        with self.assertRaisesRegex(
            UnifiedDiffParseError, "hunk line counts do not match"
        ):
            parse_unified_diff(
                """--- a/file.py
+++ b/file.py
@@ -1,2 +1,2 @@
-old
+new
"""
            )

    def test_rejects_malformed_hunk_header(self) -> None:
        with self.assertRaisesRegex(UnifiedDiffParseError, "malformed hunk header"):
            parse_unified_diff(
                """--- a/file.py
+++ b/file.py
@@ invalid @@
-old
+new
"""
            )

    def test_rejects_non_diff_text(self) -> None:
        with self.assertRaisesRegex(UnifiedDiffParseError, "unexpected content"):
            parse_unified_diff("please change file.py")


if __name__ == "__main__":
    unittest.main()
