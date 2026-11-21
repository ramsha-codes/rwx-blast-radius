#!/usr/bin/env python3
"""Regression test: patches under sqlglotc/ must select tests/test_sqlglotc.py (not an empty set).
Self-contained: builds a tests list from the committed map. Run: python tools/test_sqlglotc_selection.py
"""
import gzip
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import selector  # noqa: E402

PATCH = """diff --git a/{p} b/{p}
--- a/{p}
+++ b/{p}
@@ -9,1 +9,1 @@
-SQLGLOT_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sqlglot")
+SQLGLOT_SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sqlglotx")
"""


class SqlglotcSelection(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(selector.MAP_PATH, "rt", encoding="utf-8") as f:
            ids = json.load(f)["tests"]
        cls.tests = [{"id": i, "number": n, "file": i.split("::")[0], "seconds": 0.01}
                     for n, i in enumerate(ids)]
        cls.expected = {t["number"] for t in cls.tests if t["file"] == "tests/test_sqlglotc.py"}
        cls.sel = selector.Selector(cls.tests)

    def test_expected_tests_exist(self):
        self.assertEqual(len(self.expected), 3)

    def test_setup_py_selects_sqlglotc_tests_only(self):
        nums, why = self.sel.select(PATCH.format(p="sqlglotc/setup.py"))
        self.assertEqual(nums, self.expected, why)

    def test_other_sqlglotc_files_select_them_too(self):
        for p in ("sqlglotc/pyproject.toml", "sqlglotc/MANIFEST.in"):
            nums, why = self.sel.select(PATCH.format(p=p))
            self.assertEqual(nums, self.expected, p)

    def test_docs_under_sqlglotc_stay_inert(self):
        nums, _ = self.sel.select(PATCH.format(p="sqlglotc/README.md"))
        self.assertEqual(nums, set())

    def test_not_all_tests(self):
        nums, _ = self.sel.select(PATCH.format(p="sqlglotc/setup.py"))
        self.assertLess(len(nums), 10)


if __name__ == "__main__":
    unittest.main()
