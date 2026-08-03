import unittest

from src.calculator import divide


class DivisionByZeroReproductionTests(unittest.TestCase):
    def test_zero_divisor_uses_domain_error(self) -> None:
        with self.assertRaises(ValueError):
            divide(1, 0)


if __name__ == "__main__":
    unittest.main()
