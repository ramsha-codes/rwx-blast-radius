#!/usr/bin/env python3
"""Regression tests for the identity-swap profile (Milestone 8). Self-contained: uses only the committed map
and profile, fabricating the patch text. Run: python tools/test_isprof_selection.py"""
import gzip, json, sys, unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
import selector as S


def patch(path, line, old, new):
    return (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -{line},1 +{line},1 @@\n"
            f"-{old}\n+{new}\n")


class IdentitySwap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with gzip.open(S.MAP_PATH, "rt", encoding="utf-8") as f:
            ids = json.load(f)["tests"]
        cls.tests = [{"id": i, "number": n, "file": i.split("::")[0], "seconds": 0.01} for n, i in enumerate(ids)]
        cls.on = S.Selector(cls.tests)
        cls.off = S.Selector(cls.tests, profile_path=None)
        cls.prof = cls.on._load_profile()
        # a profiled site whose certification actually removes covered tests
        cls.site = None
        for key, k in cls.prof["sites"].items():
            path, line, end, ordn, op = key.rsplit(":", 4)
            if line != end or ordn != "0":
                continue
            ent = cls.on.map["files"].get(path)
            if ent and cls.on.sets[ent["l2s"][int(line)]] & cls.prof["sets"][k]:
                cls.site = (path, int(line), op)
                break

    def swap(self, op):
        path, line, kind = self.site
        old = "        if a is b:" if kind == "is" else "        if a is not b:"
        new = "        if a == b:" if kind == "is" else "        if a != b:"
        return patch(path, line, old, new)

    def test_profile_loaded_and_site_found(self):
        self.assertTrue(self.prof)
        self.assertIsNotNone(self.site)

    def test_pure_swap_narrows_and_never_widens(self):
        t = self.swap("x")
        a, b = self.on.select(t)[0], self.off.select(t)[0]
        self.assertTrue(b is None or (a is not None and a < b), (len(a or []), len(b or [])))

    def test_disabled_or_bad_profile_is_coverage_only(self):
        t = self.swap("x")
        base = self.off.select(t)
        self.assertEqual(S.Selector(self.tests, profile_path=Path("/nonexistent")).select(t), base)
        import tempfile, os
        d = tempfile.mkdtemp()
        p = os.path.join(d, "p.gz")
        good = json.load(gzip.open(S.PROFILE_PATH, "rt"))
        for bad in (dict(good, tests_sha="0" * 40), dict(good, version=9)):
            with gzip.open(p, "wt") as f:
                json.dump(bad, f)
            self.assertEqual(S.Selector(self.tests, profile_path=Path(p)).select(t), base)
        with open(p, "wb") as fh:
            fh.write(b"garbage")
        self.assertEqual(S.Selector(self.tests, profile_path=Path(p)).select(t), base)

    def test_non_swaps_are_not_narrowed(self):
        path, line, kind = self.site
        for old, new in (("        if a == b:", "        if a is b:"),       # reverse direction
                         ("        if a is b:", "        if a is not b:"),
                         ("        if a is b:", "        if a != b:"),
                         ("        if a is b:", "        if a == c:"),       # swap plus another change
                         ("        if a is b or c is d:", "        if a == b or c is d:")):  # two `is`
            t = patch(path, line, old, new)
            self.assertEqual(self.on.select(t), self.off.select(t), (old, new))

    def test_unprofiled_line_is_not_narrowed(self):
        path, line, kind = self.site
        t = patch(path, line + 1, "        if a is b:", "        if a == b:")
        self.assertEqual(self.on.select(t), self.off.select(t))

    def test_multi_block_file_is_not_narrowed(self):
        path, line, kind = self.site
        t = (f"diff --git a/{path} b/{path}\n--- a/{path}\n+++ b/{path}\n@@ -{line},1 +{line},1 @@\n"
             f"-        if a is b:\n+        if a == b:\n@@ -{line + 40},1 +{line + 40},1 @@\n-        x = True\n+        x = False\n")
        self.assertEqual(self.on.select(t), self.off.select(t))


if __name__ == "__main__":
    unittest.main()
