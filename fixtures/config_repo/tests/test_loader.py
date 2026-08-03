import json
import tempfile
import unittest
from pathlib import Path

from src.config.loader import get_timeout, load_config


class ConfigLoaderTests(unittest.TestCase):
    def test_loads_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "config.json"
            path.write_text(json.dumps({"timeout": 10}), encoding="utf-8")
            self.assertEqual(load_config(path), {"timeout": 10})

    def test_default_timeout(self) -> None:
        self.assertEqual(get_timeout({}), 30)


if __name__ == "__main__":
    unittest.main()
