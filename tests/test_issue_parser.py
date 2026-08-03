import unittest

from issuelens.issue_parser import parse_issue


class IssueParserTests(unittest.TestCase):
    def test_extracts_identifiers_files_and_exceptions(self) -> None:
        issue = parse_issue(
            "# `divide` fails\n"
            "`tests/test_calculator.py` expects `ValueError`, "
            "not ZeroDivisionError."
        )
        self.assertEqual(issue.title, "`divide` fails")
        self.assertIn("divide", issue.identifiers)
        self.assertIn("tests/test_calculator.py", issue.file_hints)
        self.assertIn("ValueError", issue.exception_hints)
        self.assertIn("ZeroDivisionError", issue.exception_hints)


if __name__ == "__main__":
    unittest.main()
