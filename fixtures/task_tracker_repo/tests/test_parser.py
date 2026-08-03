import unittest

from src.task_tracker.parser import parse_due_date


class DueDateParserTests(unittest.TestCase):
    def test_none_is_allowed(self) -> None:
        self.assertIsNone(parse_due_date(None))

    def test_iso_timestamp(self) -> None:
        parsed = parse_due_date("2026-07-29T08:30:00")
        self.assertEqual(parsed.year, 2026)


if __name__ == "__main__":
    unittest.main()
