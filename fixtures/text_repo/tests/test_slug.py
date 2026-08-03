import unittest

from src.text_tools.slug import slugify, truncate


class TextToolTests(unittest.TestCase):
    def test_ascii_slug(self) -> None:
        self.assertEqual(slugify("Hello Agent"), "hello-agent")

    def test_truncate(self) -> None:
        self.assertEqual(truncate("abcdef", 3), "abc")


if __name__ == "__main__":
    unittest.main()
