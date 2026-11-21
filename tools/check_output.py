"""Format sanity check of an output file: one line per commit, no dup commits/tests."""
import collections, json, os, sys
out, commits = sys.argv[1], sys.argv[2]
raw = open(out, "rb").read()
text = raw.decode("utf-8")
rows = [json.loads(line) for line in text.split("\n") if line]
count = collections.Counter(r["commit"] for r in rows)
expected = {f[:-6] for f in os.listdir(commits) if f.endswith(".patch")}
dup_tests = [r["commit"] for r in rows
             if len([n for w in r["workers"] for n in w]) != len({n for w in r["workers"] for n in w})]
print(len(rows), "lines;", "duplicate commits:", [k for k, v in count.items() if v > 1],
      "missing:", sorted(expected - set(count)), "unknown:", sorted(set(count) - expected),
      "commits with repeated tests:", dup_tests, "bytes:", len(raw),
      "BOM:", raw[:3] == b"\xef\xbb\xbf", "workers<=8:", all(len([w for w in r["workers"] if w]) <= 8 for r in rows))
