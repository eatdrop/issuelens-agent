import unittest

from src.calculator import divide


class DivisionByZeroHiddenTests(unittest.TestCase):
    def test_error_message_is_actionable(self) -> None:
        with self.assertRaisesRegex(ValueError, "right must not be zero"):
            divide(-1, 0)

    def test_nonzero_divisor_still_works(self) -> None:
        self.assertEqual(divide(9, 3), 3)


if __name__ == "__main__":
    unittest.main()
