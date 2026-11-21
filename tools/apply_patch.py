"""Apply a difflib/git-style unified diff (as written by tools/mutate.py) with only the stdlib.
Usage: python apply_patch.py <patch> <root>"""
import re, sys, os
patch, root = sys.argv[1], sys.argv[2]
text = open(patch, encoding="utf-8").read().split("\n")
if text and text[-1] == "":
    text.pop()
i = 0
while i < len(text):
    m = re.match(r"^diff --git a/(\S+) b/(\S+)$", text[i])
    if not m:
        i += 1
        continue
    path = os.path.join(root, m.group(2))
    src = open(path, encoding="utf-8", newline="").read().split("\n")
    out, pos = [], 0
    i += 1
    while i < len(text) and not text[i].startswith("diff --git"):
        h = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", text[i])
        i += 1
        if not h:
            continue
        start = int(h.group(1)) - (1 if h.group(2) != "0" else 0)
        out += src[pos:start]
        pos = start
        while i < len(text) and not text[i].startswith(("@@", "diff --git")):
            l = text[i]
            if l[:1] == " " or l == "":
                out.append(src[pos]); pos += 1
            elif l[0] == "-":
                pos += 1
            elif l[0] == "+":
                out.append(l[1:])
            i += 1
    out += src[pos:]
    open(path, "w", encoding="utf-8", newline="").write("\n".join(out))
