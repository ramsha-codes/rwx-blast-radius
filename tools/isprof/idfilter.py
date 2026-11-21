"""Validation helper: keep only the tests whose node ids are listed in $ISPROF_IDS (one per line)."""
import os
def pytest_collection_modifyitems(config, items):
    p = os.environ.get("ISPROF_IDS")
    if not p:
        return
    keep = set(open(p, encoding="utf-8").read().split("\n")) - {""}
    sel = [i for i in items if i.nodeid in keep]
    config.hook.pytest_deselected(items=[i for i in items if i.nodeid not in keep])
    items[:] = sel
